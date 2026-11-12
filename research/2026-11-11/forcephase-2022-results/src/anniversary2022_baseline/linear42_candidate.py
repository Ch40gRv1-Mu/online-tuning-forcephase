"""Callable R12-style linear42/min3 candidate; no SAT solver is executed."""

import argparse
import json
from pathlib import Path
import resource
import subprocess
import time

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha, write
from .linear42_only_vector import linear42_vector
from .route_phase_2022 import SOLVER_FLAGS
from .structural_clusters import ACTIONS


def predict_vector(payload, vector):
    x = np.asarray(vector, dtype=np.float32)
    assert payload["view"] == "linear42" and x.shape == (42,) and np.isfinite(x).all()
    assert len(payload["models"]) == 3 and all(m.n_features_in_ == 42 for m in payload["models"])
    gain = np.min([m.predict(x[None])[0] * 1200 for m in payload["models"]], axis=0)
    cut = payload["cut"]
    action = 0 if cut is None or gain.max() <= cut else int(gain.argmax()) + 1
    return action, gain


def route_cnf(payload, binary, cnf):
    started, cpu = time.monotonic(), time.process_time()
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    child_cpu = children.ru_utime + children.ru_stime
    if sha(binary) != payload["native_binary_sha256"]:
        raise ValueError("native feature binary is not the frozen candidate binary")
    receipt = {"action": "D", "status": "feature_error", "short_search_calls": 0, "SAT_calls": 0}
    vector = None
    try:
        result = subprocess.run([str(binary.resolve()), str(cnf.resolve())], capture_output=True, timeout=14)
        if result.returncode != 0 or len(result.stdout) > 1_000_000:
            raise ValueError(f"native extraction exit={result.returncode}: {result.stderr.decode(errors='replace')[:200]}")
        raw = json.loads(result.stdout)
        vector = linear42_vector(raw["features"])
        tick = time.process_time()
        action, gain = predict_vector(payload, vector)
        receipt.update(status="ok", action=ACTIONS[action], min_predicted_PAR2_savings=gain.tolist(),
                       decision_CPU_s=time.process_time() - tick)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        receipt["error"] = str(error)
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    native_cpu = usage.ru_utime + usage.ru_stime - child_cpu
    receipt.update(native_CPU_s=native_cpu, parent_CPU_s=time.process_time() - cpu,
                   routing_CPU_s=native_cpu + time.process_time() - cpu,
                   wall_s=time.monotonic() - started, solver_flags=list(SOLVER_FLAGS[receipt["action"]]))
    return receipt, vector


def main(args):
    tick = time.process_time()
    payload = joblib.load(args.model)
    load_cpu = time.process_time() - tick
    receipt, _ = route_cnf(payload, args.native_binary, args.cnf)
    receipt.update(model_sha256=sha(args.model), model_load_CPU_s=load_cpu,
                   scope="Candidate inference only; no solver or performance confirmation")
    if args.out:
        write(args.out, receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--native-binary", type=Path, required=True)
    p.add_argument("--cnf", type=Path, required=True)
    p.add_argument("--out", type=Path)
    with threadpool_limits(limits=1):
        main(p.parse_args())
