"""One frozen CPU16 retry after the unchanged compact CPU8 extractor fails."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import resource
import signal
import sqlite3
import socket
import subprocess
import time

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .linear42_candidate import predict_vector
from .linear42_only_vector import linear42_vector
from .measure_compact_prefetch import (atomic, BINARY, MODEL, download, identity,
    prune, timer_for, wait4, wire_bound, WIRE_LIMIT, CONFIG)
from .route_phase_2022 import SOLVER_FLAGS
from .score_static_seed_agreement import load_views
from .structural_clusters import ACTIONS, BASE, DATA, ROOT, load, read_csv


ORIGINAL = DATA / "linear42_compact_cost_v3_20261111"
OUT = DATA / "linear42_cpu_recovery_20261111"
BUILD = ROOT / "work/native_linear42_cpu16_20261111"
SOURCE_SHA = "77f3161c92695042bf018c4f3c591960a42a73f08ec3f06b370155e2a4d6f8f4"


def build(out):
    BUILD.mkdir(exist_ok=True)
    source = ROOT / "src/anniversary2022_baseline/native_linear42.cpp"
    assert sha(source) == SOURCE_SHA
    old = source.read_text()
    assert old.count("rlimit core{0,0}, cpu{8,8};") == 1
    new = old.replace("rlimit core{0,0}, cpu{8,8};", "rlimit core{0,0}, cpu{16,16};")
    target, binary = BUILD / "native_linear42_cpu16.cpp", BUILD / "native_linear42_cpu16"
    receipt_path = out / "build.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        assert target.read_text() == new and sha(binary) == receipt["binary_sha256"]
        return binary
    assert not target.exists() and not binary.exists()
    target.write_text(new)
    vendor = ROOT / "src/anniversary2022_baseline/vendor_gbdc_base_9f3a418"
    command = ["clang++", "-std=c++17", "-O3", "-I" + str(vendor),
        "-I" + str(ROOT / "src/anniversary2022_baseline/vendor_libarchive_headers_3_7_7"),
        str(target), str(vendor / "src/util/CaptureDistribution.cc"), "-larchive", "-o", str(binary)]
    tick = time.monotonic()
    p = subprocess.run(command, capture_output=True, text=True, timeout=120)
    receipt = {"command": command, "exit": p.returncode, "stderr": p.stderr,
        "wall_s": time.monotonic() - tick, "original_source_sha256": sha(source),
        "modified_source_sha256": sha(target), "source_diff": "Only requested RLIMIT_CPU8->16",
        "unchanged_alarm_s": 12, "unchanged_wrapper_s": 14}
    if p.returncode == 0:
        receipt["binary_sha256"] = sha(binary)
    atomic(receipt_path, receipt)
    if p.returncode:
        raise RuntimeError("CPU16 build failed; see preserved build.json")
    return binary


def extract(binary, path):
    """Exactly one actual native call, with its own child CPU and hard wall guard."""
    tick, cpu = time.monotonic(), time.thread_time()
    process = subprocess.Popen([str(binary.resolve()), str(path.resolve())],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    timer = timer_for(process, 14)
    try:
        output = process.stdout.read(1000001)
        if len(output) > 1000000:
            os.kill(process.pid, signal.SIGKILL)
        process.stdout.close()
        code, child, rss = wait4(process)
    except BaseException:
        try:
            os.kill(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            wait4(process)
        except ChildProcessError:
            pass
        raise
    finally:
        timer.cancel()
    result = {"native_exit": code, "native_CPU_s": child, "native_maxrss": rss,
        "native_wall_s": time.monotonic() - tick, "native_binary_sha256": sha(binary)}
    if code == 0:
        result["features"] = json.loads(output)["features"]
    else:
        result["native_error"] = output.decode(errors="replace")[:800]
    result["native_wrapper_parent_CPU_s"] = time.thread_time() - cpu
    return result


def route(payload, policy, cnf):
    """Real two-attempt inference: no cache, instance identity or labels are read."""
    tick, cpu = time.monotonic(), time.process_time()
    usage0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    first, second = Path(policy["first_binary"]), Path(policy["retry_binary"])
    assert sha(first) == policy["first_binary_sha256"] == payload["native_binary_sha256"]
    assert sha(second) == policy["retry_binary_sha256"]
    attempts = [extract(first, cnf)]
    if attempts[0]["native_exit"] == -24:
        attempts.append(extract(second, cnf))
    result = {"action": "D", "status": "feature_error", "attempts": [
        {k: v for k, v in a.items() if k != "features"} for a in attempts]}
    if attempts[-1]["native_exit"] == 0:
        vector = linear42_vector(attempts[-1]["features"])
        action, gains = predict_vector(payload, vector)
        result.update(action=ACTIONS[action], status="ok", min_predicted_PAR2_savings=gains.tolist())
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    result.update(solver_flags=list(SOLVER_FLAGS[result["action"]]),
        routing_CPU_s=time.process_time() - cpu + usage.ru_utime + usage.ru_stime - usage0.ru_utime - usage0.ru_stime,
        wall_s=time.monotonic() - tick, new_solver_calls=0,
        scope="Resident-model candidate inference only; no SAT solver or performance confirmation")
    return result


def measure(args):
    tick, cpu = time.monotonic(), time.process_time()
    usage0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    args.out.mkdir(exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, (ORIGINAL / "owner.lock").open("a") as first_lock, threadpool_limits(limits=1):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(first_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cohort = json.loads((args.out / "cohort.json").read_text())
        header = json.loads((ORIGINAL / "prefix_4719.json").read_text())
        assert header["through"] == 4719 and header["remaining_unmeasured_inputs"] == 0
        assert sha(ORIGINAL / "prefix_4719.json") == cohort["first_profile_sha256"]
        assert sha(ORIGINAL / "measured_costs4719.csv") == cohort["first_cost_table_sha256"]
        first_identity = json.loads((ORIGINAL / "identity.json").read_text())
        assert sha(MODEL) == first_identity["model_sha256"]
        assert sha(BINARY) == first_identity["native_binary_sha256"]
        manifest = read_csv(CONFIG / "manifest.csv")
        all_first = {r["instance_key"]: json.loads((ORIGINAL / "records" / (r["instance_key"] + ".json")).read_text()) for r in manifest}
        rows = [r for r in manifest if all_first[r["instance_key"]]["native"]["native_exit"] == -24]
        assert [r["instance_key"] for r in rows] == [r["instance_key"] for r in cohort["cohort"]]
        assert len(rows) == 68
        for frozen in cohort["cohort"]:
            path = ORIGINAL / "records" / (frozen["instance_key"] + ".json")
            assert sha(path) == frozen["record_sha256"]
        identity_spec = {"source_sha256": sha(__file__), "cohort_sha256": sha(args.out / "cohort.json"),
            "original_binary_sha256": sha(BINARY), "model_sha256": sha(MODEL),
            "original_source_sha256": SOURCE_SHA, "retry_requested_CPU_s": 16,
            "alarm_s": 12, "wrapper_s": 14, "max_prefetch": 4, "timing_lanes": 1}
        if (args.out / "identity.json").exists():
            assert json.loads((args.out / "identity.json").read_text()) == identity_spec
        else:
            atomic(args.out / "identity.json", identity_spec)
        session = str(time.time_ns())
        status = "running"
        atomic(args.out / "owner.json", {"PID": os.getpid(), "host": socket.gethostname(), "status": status})
        try:
            binary = build(args.out)
            policy = {"schema": "forcephase.linear42.min3.cpu_retry.v1", "first_binary": str(BINARY),
                "first_binary_sha256": sha(BINARY), "retry_binary": str(binary),
                "retry_binary_sha256": sha(binary), "model": str(MODEL), "model_sha256": sha(MODEL),
                "retry_only_on_exit": -24, "first_requested_CPU_s": 8, "retry_requested_CPU_s": 16,
                "alarm_per_attempt_s": 12, "wrapper_per_attempt_s": 14,
                "model_weights_retrained": False, "first_and_retry_costs_both_charged": True,
                "claim": "Candidate resource policy; no independent or solver-deployment confirmation"}
            atomic(args.out / "policy.json", policy)
            payload = joblib.load(MODEL)
            assert payload["native_binary_sha256"] == sha(BINARY)
            keys = load()[0]
            reference, valid = load_views(keys)[0]["linear42"]
            assert valid.all()
            refs = dict(zip(keys, reference.astype(np.float32)))
            with sqlite3.connect("file:" + str(BASE) + "?mode=ro", uri=True) as db:
                expected = {k: (int(c), int(b)) for k, c, b in db.execute("select hash,clauses,cls2 from features")}
            records, stages = args.out / "records", args.out / "stages"
            records.mkdir(exist_ok=True); stages.mkdir(exist_ok=True)
            missing = [r for r in rows if not (records / (r["instance_key"] + ".json")).exists()]
            for r in rows:
                path = records / (r["instance_key"] + ".json")
                if path.exists():
                    previous = json.loads(path.read_text())
                    assert previous["retry"]["native_binary_sha256"] == sha(binary)
                    assert previous["first_record_sha256"] == sha(ORIGINAL / "records" / path.name)
            previous_cpu = sum(json.loads(f.read_text())["physical_parent_CPU_s"] + json.loads(f.read_text())["physical_child_CPU_s"]
                for f in (args.out / "sessions").glob("*.json")) if (args.out / "sessions").exists() else 0.
            atomic(args.out / "progress.json", {"status": "running", "completed": len(rows) - len(missing), "total": len(rows)})
            with ThreadPoolExecutor(max_workers=4) as pool:
                pending, position = deque(), 0
                def refill():
                    nonlocal position
                    reserved = sum(item[2] for item in pending)
                    while position < len(missing) and len(pending) < 4 and time.monotonic() - tick < 1500:
                        row = missing[position]; size = wire_bound(row)
                        if pending and reserved + size > WIRE_LIMIT:
                            break
                        pending.append((pool.submit(download, row, args.work), row, size))
                        position += 1; reserved += size
                    assert reserved <= WIRE_LIMIT
                refill()
                for row in missing:
                    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
                    spent = previous_cpu + time.process_time() - cpu + usage.ru_utime + usage.ru_stime - usage0.ru_utime - usage0.ru_stime
                    if spent > 1620 or time.monotonic() - tick > 1620 or not pending:
                        raise TimeoutError("Recovery budget reserved for safe cleanup; keep incomplete reward null")
                    future, claimed, _ = pending.popleft(); assert row == claimed
                    got = future.result()
                    if time.monotonic() - tick > 1620:
                        raise TimeoutError("Recovery wall budget cannot admit another identity/native pass")
                    refill()
                    key = row["instance_key"]; first = all_first[key]; path = Path(got["path"])
                    if got["wire_sha256"] == first["identity"]["wire_sha256"]:
                        ident = {**first["identity"], "reused_physical_measurement": True,
                            "ancestor_first_record_sha256": sha(ORIGINAL / "records" / (key + ".json"))}
                        atomic(stages / (key + ".identity.json"), ident)
                    else:
                        ident = identity(path, row, expected[key], got["wire_sha256"], stages / (key + ".identity.json"))
                    assert ident["verified"] and ident["raw_sha256"] == first["identity"]["raw_sha256"]
                    attempt = extract(binary, path)
                    rec = {"instance_key": key, "ordinal": int(row["ordinal"]), "download": got, "identity": ident,
                        "first_record_sha256": sha(ORIGINAL / "records" / (key + ".json")),
                        "retry": {k: v for k, v in attempt.items() if k != "features"},
                        "status": "retry_error_paidD", "retry_acquisition_CPU_s": attempt["native_CPU_s"] + attempt["native_wrapper_parent_CPU_s"]}
                    if attempt["native_exit"] == 0:
                        t = time.thread_time(); vector = linear42_vector(attempt["features"])
                        rec["retry_acquisition_CPU_s"] += time.thread_time() - t
                        rec["model_input_float32_match"] = bool(np.array_equal(vector.astype(np.float32), refs[key]))
                        if not rec["model_input_float32_match"]:
                            atomic(stages / (key + ".mismatch.json"), {**rec, "actual_vector": vector.tolist(), "reference_vector": refs[key].tolist()})
                            raise ValueError("CPU16 changed the trained feature vector")
                        t = time.thread_time(); action, gains = predict_vector(payload, vector)
                        rec.update(status="ok", full_model_action=ACTIONS[action], full_model_query_CPU_s=time.thread_time() - t,
                            full_model_min_predicted_PAR2_savings=gains.tolist())
                    atomic(records / (key + ".json"), rec)
                    done = len(list(records.glob("*.json")))
                    atomic(args.out / "progress.json", {"status": "running", "completed": done, "total": len(rows)})
                    print(f"RECOVERED {done}/{len(rows)}: {rec['status']}, second={rec['retry_acquisition_CPU_s']:.4f}CPU_s", flush=True)
                    prune(args.work, ORIGINAL / "records", {key} | {item[1]["instance_key"] for item in pending})
            values = [json.loads((records / (r["instance_key"] + ".json")).read_text()) for r in rows]
            atomic(args.out / "completion.json", {"status": "complete", "cohort": len(rows),
                "restored": sum(v["status"] == "ok" for v in values),
                "still_failed_paidD": sum(v["status"] != "ok" for v in values),
                "retry_acquisition_CPU_sum_s": sum(v["retry_acquisition_CPU_s"] for v in values),
                "first_physical_measurements_repeated": 0, "new_solver_calls": 0,
                "source_sha256": sha(__file__), "policy_sha256": sha(args.out / "policy.json")})
            status = "complete"
            atomic(args.out / "progress.json", {"status": status, "completed": len(rows), "total": len(rows)})
        except BaseException as exc:
            status = "failed_invocation"
            atomic(args.out / "failures" / (session + ".json"), {"error": repr(exc), "reward": None,
                "status": status, "completed": len(list((args.out / "records").glob("*.json")))})
            raise
        finally:
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            atomic(args.out / "sessions" / (session + ".json"), {"physical_parent_CPU_s": time.process_time() - cpu,
                "physical_child_CPU_s": usage.ru_utime + usage.ru_stime - usage0.ru_utime - usage0.ru_stime,
                "wall_s": time.monotonic() - tick, "status": status, "source_sha256": sha(__file__),
                "first_logical_fees_not_new_physical_CPU": True, "new_solver_calls": 0})
            atomic(args.out / "owner.json", {"PID": os.getpid(), "host": socket.gethostname(), "status": status})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--work", type=Path, default=ROOT / "work/linear42_large_cost_20261111/cache")
    p.add_argument("--cnf", type=Path)
    args = p.parse_args()
    if args.cnf:
        policy = json.loads((args.out / "policy.json").read_text())
        assert sha(Path(policy["model"])) == policy["model_sha256"]
        with threadpool_limits(limits=1):
            print(json.dumps(route(joblib.load(policy["model"]), policy, args.cnf), indent=2))
    else:
        measure(args)
