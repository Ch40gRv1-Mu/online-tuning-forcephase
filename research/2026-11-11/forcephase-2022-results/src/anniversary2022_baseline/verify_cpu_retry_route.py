"""Actual serving-branch checks after the fixed recovery measurement ends."""

import fcntl
import json
from pathlib import Path
import resource
import time

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .linear42_candidate import predict_vector
from .measure_compact_prefetch import atomic
from .recover_compact_cpu import ORIGINAL, OUT, route
from .route_phase_2022 import SOLVER_FLAGS
from .score_static_seed_agreement import load_views
from .structural_clusters import ACTIONS, load


def main():
    wall, cpu = time.monotonic(), time.process_time()
    usage0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    assert json.loads((OUT / "owner.json").read_text())["status"] == "complete"
    assert not (OUT / "route_verification.json").exists()
    rows, failure, status = [], None, "failed"
    with (OUT / "owner.lock").open("a") as lock, threadpool_limits(limits=1):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            policy = json.loads((OUT / "policy.json").read_text())
            assert sha(Path(policy["model"])) == policy["model_sha256"]
            payload = joblib.load(policy["model"])
            keys = load()[0]
            x, valid = load_views(keys)[0]["linear42"]
            assert valid.all()
            refs = dict(zip(keys, x))
            first = [json.loads(f.read_text()) for f in (ORIGINAL / "records").glob("*.json")]
            normal = [r for r in first if r["status"] == "ok" and Path(r["download"]["path"]).is_file()]
            retry = [json.loads(f.read_text()) for f in (OUT / "records").glob("*.json")]
            retry = sorted([r for r in retry if Path(r["download"]["path"]).is_file()], key=lambda r: r["ordinal"])
            good = [r for r in retry if r["status"] == "ok"]
            bad = [r for r in retry if r["status"] != "ok"]
            assert normal and good and bad
            chosen_good = next((r for r in good if r["full_model_action"] != "D"), good[0])
            fixtures = [("ordinary_first_attempt", min(normal, key=lambda r: Path(r["download"]["path"]).stat().st_size)),
                        ("previously_restored_input", chosen_good), ("previously_exhausted_input", bad[0])]
            atomic(OUT / "route_fixtures.json", {"purpose": "Implementation branches only, not a performance cohort",
                "selection": "Smallest cached ordinary input; first cached restored nonD if present; first cached exhausted input. No SAT outcomes used.",
                "fixtures": [{"branch": label, "association_key": r["instance_key"], "path": r["download"]["path"],
                    "wire_sha256": r["download"]["wire_sha256"]} for label, r in fixtures]})
            for label, row in fixtures:
                key, path = row["instance_key"], Path(row["download"]["path"])
                assert sha(path) == row["download"]["wire_sha256"]
                receipt = route(payload, policy, path)
                rows.append({"fixture_branch": label, "association_key": key, "receipt": receipt})
                attempts = receipt["attempts"]
                assert len(attempts) == (2 if attempts[0]["native_exit"] == -24 else 1)
                if attempts[-1]["native_exit"] == 0:
                    action, gains = predict_vector(payload, refs[key])
                    assert receipt["status"] == "ok" and receipt["action"] == ACTIONS[action]
                    assert np.allclose(receipt["min_predicted_PAR2_savings"], gains, rtol=0, atol=1e-8)
                else:
                    assert receipt["status"] == "feature_error" and receipt["action"] == "D"
                assert receipt["solver_flags"] == list(SOLVER_FLAGS[receipt["action"]])
            assert any(len(r["receipt"]["attempts"]) == 2 for r in rows), "Actual retry branch not observed; do not claim its verification"
            status = "complete_actual_serving_consistency"
        except BaseException as exc:
            failure = repr(exc)
            raise
        finally:
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            atomic(OUT / "route_verification.json", {"status": status, "error": failure, "results": rows,
                "physical_parent_CPU_s": time.process_time() - cpu,
                "physical_child_CPU_s": usage.ru_utime + usage.ru_stime - usage0.ru_utime - usage0.ru_stime,
                "wall_s": time.monotonic() - wall, "source_sha256": sha(__file__),
                "actual_retry_branches_observed": sum(len(r["receipt"]["attempts"]) == 2 for r in rows),
                "actual_native_calls": sum(len(r["receipt"]["attempts"]) for r in rows),
                "new_solver_calls": 0, "new_model_fits": 0,
                "claim": "Actual native-to-resident-selector branch consistency; cached vectors validate but never route. Not new parent labels, performance reward or same-machine solver deployment."})
    print(json.dumps({"status": status, "fixture_count": len(rows)}))


if __name__ == "__main__":
    main()
