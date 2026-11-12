"""Measure native CNF feature fidelity/cost on the frozen cached input block."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import inspect
import json
import os
from pathlib import Path
import resource
import sqlite3
import subprocess
import time

import joblib
import numpy as np
from sklearn.ensemble._forest import BaseForest
from threadpoolctl import threadpool_limits

from .common import sha, write
from .gbd_native_vectors import vectorize
from .route_phase_2022 import load_formula
from .score_static_cost_classifier import scores as class_scores
from .score_static_seed_agreement import load_views
from .structural_clusters import ACTIONS, BASE, DATA, ROOT, load, read_csv


DTYPE = np.float32


def run(args):
    start, cpu = time.monotonic(), time.process_time()
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    child_cpu_start = children.ru_utime + children.ru_stime
    args.out.mkdir(parents=True, exist_ok=False)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=1):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            keys, _, _, _, _, _ = load()
            views, fields = load_views(keys)
            with sqlite3.connect("file:" + str(BASE) + "?mode=ro", uri=True) as db:
                reference = {k: dict(zip(fields + ["ccs"], map(float, values))) for k, *values in
                             db.execute("select hash," + ",".join(fields + ["ccs"]) + " from features")}
            split = read_csv(DATA / "cnf_graph_cnn_20261110/splits.csv")
            validation_source = inspect.getsource(BaseForest._validate_X_predict)
            assert [r["instance_key"] for r in split] == keys and "dtype=np.float32" in validation_source
            eligible = np.array([r["eligible"] == "True" for r in split])
            source = DATA / "cnf_graph_cnn_20261110/feature_receipts.jsonl"
            identities = {r["instance_key"]: r["raw_sha256"] for r in map(json.loads, source.read_text().splitlines())}
            panel = ROOT / "work/astra_structure_panel_20261110"
            fallback = {r["instance_key"]: panel / "cnf" / (r["case"] + ".cnf")
                        for r in read_csv(panel / "association_only.csv")}
            payload = joblib.load(args.model)
            assert payload["view"] == "linear42" and payload["aggregation"] == "min_preference_score"
            index = {key: i for i, key in enumerate(keys)}
            np.savez_compressed(args.out / "reference_vectors.npz", keys=np.asarray(keys), eligible=eligible,
                                **{name: x for name, (x, _) in views.items()})

            def job(key):
                path = ROOT / "work/signed_boundary_20261110/cnf_cache" / (key + ".cnf.gz")
                if not path.is_file():
                    path = fallback[key]
                tick = time.thread_time()
                raw = load_formula(path)
                assert len(raw) <= 3_000_000 and hashlib.sha256(raw).hexdigest() == identities[key]
                identity_cpu = time.thread_time() - tick
                tick = time.thread_time()
                process = subprocess.Popen([str(args.binary), str(path)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                text_ = process.stdout.read(1_000_001)
                process.stdout.close()
                if len(text_) > 1_000_000:
                    process.kill()
                _, status, usage = os.wait4(process.pid, 0)
                process.returncode = os.waitstatus_to_exitcode(status)
                native_cpu = usage.ru_utime + usage.ru_stime
                result = {"instance_key": key, "identity_CPU_s": identity_cpu, "raw_bytes": len(raw),
                          "native_CPU_s": native_cpu, "native_exit": process.returncode}
                if process.returncode:
                    result.update(status="native_failure", detail=text_.decode(errors="replace")[:800],
                                  feature_CPU_s=native_cpu + time.thread_time() - tick)
                    return result
                record = json.loads(text_)
                vectors = vectorize(record["features"])
                result["feature_CPU_s"] = native_cpu + time.thread_time() - tick
                field_mismatch = {f: [record["features"][f], reference[key][f]] for f in fields + ["ccs"]
                                  if not np.isclose(record["features"][f], reference[key][f], rtol=1e-7, atol=1e-9)}
                row = index[key]
                input_match = {name: bool(np.array_equal(x.astype(DTYPE), views[name][0][row].astype(DTYPE)))
                               for name, x in vectors.items()}
                result.update(status="ok" if all(input_match.values()) else "input_mismatch",
                              raw_field_mismatches=field_mismatch, model_input_float32_match=input_match)
                if not all(input_match.values()):
                    return result
                tick = time.thread_time()
                prediction = np.min([class_scores(model, vectors["linear42"][None])[0] for model in payload["models"]], axis=0)
                action = 0 if payload["cut"] is None or prediction.max() <= payload["cut"] else int(prediction.argmax()) + 1
                result.update(decision_CPU_s=time.thread_time() - tick, action=ACTIONS[action],
                              input_source="native CNF statistics, no database lookup for prediction")
                return result

            completed, failures, values = 0, 0, []
            with ThreadPoolExecutor(max_workers=2) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
                remaining = iter(k for k, e in zip(keys, eligible) if e)
                pending = deque(pool.submit(job, next(remaining)) for _ in range(2))
                while pending:
                    record = pending.popleft().result()
                    values.append(record)
                    completed += 1
                    failures += record["status"] != "ok"
                    stream.write(json.dumps(record) + "\n")
                    if completed % 200 == 0:
                        stream.flush()
                        print(f"MEASURED {completed}/{eligible.sum()}, incompatible={failures}", flush=True)
                    if failures >= 16:
                        raise ValueError("native statistics incompatible with trained inputs; preserve failures and diagnose before scoring")
                    if time.monotonic() - start > 900:
                        raise TimeoutError("native feature measurement exceeded fifteen minutes")
                    key = next(remaining, None)
                    if key is not None:
                        pending.append(pool.submit(job, key))
            fees = np.array([r["feature_CPU_s"] for r in values])
            decision = np.array([r.get("decision_CPU_s", 0) for r in values])
            children = resource.getrusage(resource.RUSAGE_CHILDREN)
            physical_child_cpu = children.ru_utime + children.ru_stime - child_cpu_start
            write(args.out / "summary.json", {"status": "complete", "population": len(keys),
                  "cached_resource_block": int(eligible.sum()), "completed": completed, "incompatible": failures,
                  "feature_CPU_sum_s": float(fees.sum()), "decision_CPU_sum_s": float(decision.sum()),
                  "feature_CPU_quantiles_s": dict(zip(("p50", "p90", "p99", "max"), np.quantile(fees, [.5, .9, .99, 1]).tolist())),
                  "physical_parent_CPU_s": time.process_time() - cpu, "physical_native_CPU_s": physical_child_cpu,
                  "wall_s": time.monotonic() - start, "new_solver_calls": 0, "short_search_calls": 0,
                  "score_scope": "Input fidelity and feature/query cost only; full-model training rows are not performance confirmation",
                  "unmeasured_larger_parents": int((~eligible).sum()), "binary_sha256": sha(args.binary),
                  "model_sha256": sha(args.model), "GBD_sha256": sha(BASE), "source_sha256": sha(__file__),
                  "vector_source_sha256": sha(Path(__file__).with_name("gbd_native_vectors.py"))})
        except Exception as error:
            children = resource.getrusage(resource.RUSAGE_CHILDREN)
            write(args.out / "failure.json", {"status": "failed", "error": repr(error),
                  "physical_parent_CPU_s": time.process_time() - cpu,
                  "physical_native_CPU_s": children.ru_utime + children.ru_stime - child_cpu_start,
                  "wall_s": time.monotonic() - start, "new_solver_calls": 0})
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    args.binary = args.binary.resolve()
    run(args)
