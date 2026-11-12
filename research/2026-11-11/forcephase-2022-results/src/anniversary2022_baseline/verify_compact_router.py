"""Exercise the repaired public route on three existing native-measured inputs."""

import ast
import hashlib
import json
from pathlib import Path
import resource
import time

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .linear42_candidate import route_cnf
from .linear42_only_vector import linear42_vector
from .measure_compact_prefetch import atomic, BINARY, MODEL
from .route_phase_2022 import SOLVER_FLAGS
from .structural_clusters import ACTIONS, DATA, ROOT


def function_hash(path, name):
    tree = ast.parse(Path(path).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def main():
    start, cpu = time.monotonic(), time.process_time()
    child0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    out = DATA / "compact_router_fix_20261111"
    assert not (out / "verification.json").exists()
    root = DATA / "linear42_compact_cost_v3_20261111"
    owner = json.loads((root / "owner.json").read_text())
    assert owner["status"] == "complete_prefix", "Do not overlap the active measurement invocation"
    source = ROOT / "src/anniversary2022_baseline/linear42_candidate.py"
    before = json.loads((out / "before_fix.json").read_text())
    assert function_hash(source, "predict_vector") == before["unchanged_predict_vector_body_sha256"]
    policy = json.loads((MODEL.parent / "policy.json").read_text())
    assert sha(MODEL) == policy["model_sha256"] and sha(BINARY) == policy["native_binary_sha256"]
    fixtures = {}
    for f in (root / "records").glob("*.json"):
        row = json.loads(f.read_text())
        path = Path(row["download"]["path"])
        native = root / "stages" / (row["instance_key"] + ".native.json")
        if row["status"] != "ok" or not path.is_file() or not native.is_file():
            continue
        if row["action"] not in fixtures or path.stat().st_size < fixtures[row["action"]][0]:
            fixtures[row["action"]] = (path.stat().st_size, row, path, native)
    assert set(fixtures) == set(ACTIONS)
    manifest = [{"action_branch": action, "association_key": fixtures[action][1]["instance_key"],
                 "path": str(fixtures[action][2]), "wire_sha256": fixtures[action][1]["download"]["wire_sha256"],
                 "reference_native_receipt": str(fixtures[action][3]),
                 "reference_native_receipt_sha256": sha(fixtures[action][3])} for action in ACTIONS]
    atomic(out / "fixtures.json", {"purpose": "Implementation action-branch coverage only, not a performance cohort",
                                  "selection": "Smallest existing cached measured input for each full-model predicted action; no runtime/answer used",
                                  "fixtures": manifest})
    results = []
    with threadpool_limits(limits=1):
        payload = joblib.load(MODEL)
        for action in ACTIONS:
            _, row, path, native = fixtures[action]
            assert sha(path) == row["download"]["wire_sha256"]
            reference = linear42_vector(json.loads(native.read_text())["features"])
            receipt, vector = route_cnf(payload, BINARY, path)
            assert receipt["status"] == "ok" and receipt["action"] == action, receipt
            assert np.array_equal(vector.astype(np.float32), reference.astype(np.float32))
            assert receipt["solver_flags"] == list(SOLVER_FLAGS[action])
            results.append({"association_key": row["instance_key"], "receipt": receipt,
                            "native_float32_input_match": True,
                            "input_float32_sha256": hashlib.sha256(vector.astype(np.float32).tobytes()).hexdigest()})
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    atomic(out / "verification.json", {"status": "complete_three_actual_route_branches", "results": results,
        "physical_parent_CPU_s": time.process_time() - cpu,
        "physical_child_CPU_s": child.ru_utime + child.ru_stime - child0.ru_utime - child0.ru_stime,
        "wall_s": time.monotonic() - start, "model_sha256": sha(MODEL), "native_binary_sha256": sha(BINARY),
        "route_source_sha256": sha(source), "verification_source_sha256": sha(__file__),
        "model_weights_retrained": False, "new_native_calls": 3, "new_solver_calls": 0,
        "claim": "Actual native-feature to generic route parity only; not three new research parents, not new prediction reward, not solver deployment"})
    print(json.dumps({"status": "complete", "action_branches": list(ACTIONS), "new_solver_calls": 0}))


if __name__ == "__main__":
    main()
