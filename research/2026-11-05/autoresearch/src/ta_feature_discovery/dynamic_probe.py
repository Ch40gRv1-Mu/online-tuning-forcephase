#!/usr/bin/env python3
"""Owner-fixed native-D feature prefixes; no phase comparison or answer labels."""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import queue
import resource
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

import node_worker as common

BASE_OBSERVER_SHA = "d6194cc12ff5a6c570a767053f1bc8460440e3f27bd25576b0164987470bc770"
OBSERVER_SOURCE_SHA = "d92d0ef0638397fb6eddaad64a5b2d8619e8cf5d805d9f56dd469005bef16015"
OBSERVER_VERSION = "ta-probe-v1"
FEATURE_MAP = {"d_glue_mean": "c_glue_mean", "d_raw_glue_low_fraction": "c_glue_low_frac",
               "d_glue_fast_slow_ratio": "x_glue_ratio", "d_minimized_learned_length": "c_minsize_mean",
               "d_backtrack_target_level": "x_level_avg", "d_backjump_span": "c_backjump_mean"}
FLAGS = ["--phase=1", "--forcephase=0", "--fpc=3", "--fpctrack=0", "--fpca0=0", "--fpca1=0",
         "--fpcinit=0", "--fpcat=1000", "--fpcperiod=0", "--fpcmaxsw=1", "--fpcrlim=0",
         "--fpcwin=2000000000", "--seed=0", "--stats"]
PROFILE = {"kind": "native_d_prefix_v1", "observer": OBSERVER_VERSION,
           "cpu_limit_s": 2.0, "wall_limit_s": 10.0, "memory_bytes": 1536 * 1024**2,
           "file_limit_bytes": 1024**3, "checkpoint_conflicts": 1000, "min_learned": 20,
           "reservation_cpu_s": 60.0, "max_stage_cpu_s": 3600.0, "max_workers": 8,
           "early_answers_adopted": False, "flags": FLAGS}
IDENTITY_FIELDS = ("observer_source_sha256", "solver_binary_sha256", "cpu_helper_sha256")


def patch_observer(source, output):
    """Only add header identity and two checkpoint observations; no search change."""
    source, output = Path(source), Path(output)
    if common.sha(source) != BASE_OBSERVER_SHA:
        raise ValueError("observer patch requires the exact qualified FPC2 source")
    text = source.read_text()
    # Restrict edits to these two logging blocks.  Existing numeric features and
    # action order remain byte-identical to the qualified FPC2 implementation.
    header_old = '  fputs ("]}\\n", log);\n  fflush (log);\n}\n\n/*------------------------------------------------------------------------*/\n\nvoid Controller::take'
    header_new = '  fputs ("],\\"observer\\":\\"' + OBSERVER_VERSION + '\\"}\\n", log);\n  fflush (log);\n}\n\n/*------------------------------------------------------------------------*/\n\nvoid Controller::take'
    cp_old = '      write_features (features_cp);\n      fputs ("}\\n", log);'
    cp_new = ('      fprintf (log, ",\\"learned\\":%" PRId64\n'
              '                    ",\\"process_cpu_s\\":%.9f",\n'
              '               now.learned, absolute_process_time ());\n'
              '      write_features (features_cp);\n      fputs ("}\\n", log);')
    for old, new in ((header_old, header_new), (cp_old, cp_new)):
        if text.count(old) != 1:
            raise ValueError("qualified observer logging anchor is not unique")
        text = text.replace(old, new)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(text)
    return {"base_observer_source_sha256": BASE_OBSERVER_SHA,
            "observer_source_sha256": common.sha(output), "observer": OBSERVER_VERSION}


def task_key(task, identity):
    return hashlib.sha256(common.canonical({"instance_id": task["instance_id"],
        "input_sha256": task["input_sha256"], "profile": PROFILE,
        **{key: identity[key] for key in IDENTITY_FIELDS}})).hexdigest()


def normalize_task(raw, identity):
    raw = dict(raw)
    given = raw.pop("task_key", None)
    task = common.normalize_task(raw, identity["observer_source_sha256"])
    task["task_key"] = task_key(task, identity)
    if given is not None and given != task["task_key"]:
        raise ValueError("dynamic task identity does not match frozen input/observer/binaries")
    return task


def load_manifest(path, solver, helper, observer_source):
    raw = json.loads(Path(path).read_text())
    if common.sha(observer_source) != OBSERVER_SOURCE_SHA:
        raise ValueError("dynamic observer is not the exact logging-only transformation")
    for key, value in {"solver_binary_sha256": common.sha(solver),
                       "cpu_helper_sha256": common.sha(helper),
                       "observer_source_sha256": common.sha(observer_source)}.items():
        if raw.get(key) != value:
            raise ValueError(key + " differs from owner manifest")
    if raw.get("profile") != PROFILE:
        raise ValueError("dynamic profile differs from frozen limits/CLI")
    for key in ("experiment_id", "shard_id", "node_id"):
        if not common.SAFE_ID.fullmatch(str(raw.get(key, ""))):
            raise ValueError("safe " + key + " is required")
    budget = raw.get("allocated_cpu_s")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not 0 < budget <= PROFILE["max_stage_cpu_s"]:
        raise ValueError("central owner must allocate this shard's share of the <=1CPUh stage budget")
    tasks = [normalize_task(t, raw) for t in raw["tasks"]]
    if len({t["task_key"] for t in tasks}) != len(tasks):
        raise ValueError("duplicate dynamic tasks")
    raw["tasks"] = tasks
    return raw


def worker_capacity(output, requested, memory=None, disk=None, cpus=None):
    cpus = cpus if cpus is not None else len(os.sched_getaffinity(0))
    memory = common.available_memory() if memory is None else memory
    disk = shutil.disk_usage(output).free if disk is None else disk
    return max(0, min(requested, PROFILE["max_workers"], cpus,
        max(0, memory - 2 * 1024**3) // PROFILE["memory_bytes"],
        max(0, disk - 12 * 1024**3) // (PROFILE["file_limit_bytes"] + 256 * 1024**2)))


def parse_telemetry(path, require_complete=False):
    """Inspect only the first pre-action checkpoint; ignore all terminal answers."""
    path = Path(path)
    if not path.exists():
        return None
    data = path.read_bytes()
    if len(data) > 8 * 1024**2:
        raise ValueError("telemetry exceeds bounded observer output")
    lines = data.splitlines(keepends=True)
    if lines and not lines[-1].endswith(b"\n"):
        if require_complete:
            raise ValueError("truncated final telemetry record")
        lines.pop()
    rows = [json.loads(line) for line in lines]
    if not rows:
        return None
    header = rows[0]
    expected = {"type": "header", "schema": 2, "controller": "v2", "observer": OBSERVER_VERSION,
                "mode": 3, "track": "C", "a0": "NATIVE", "a1": "NATIVE", "init": 0,
                "at": 1000, "period": 0, "maxsw": 1, "rlim": 0,
                "opt_phase": 1, "opt_forcephase": 0, "opt_seed": 0}
    if any(header.get(k) != v for k, v in expected.items()):
        raise ValueError("telemetry header differs from the fixed native-D observer")
    for row in rows[1:]:
        if row.get("type") == "checkpoint":
            crossed = row.get("crossed", [])
            if len(crossed) != 2 or crossed[0] != 1000 or crossed[1] < 1000 or row.get("conflicts", 0) < 1000:
                raise ValueError("not the first natural restart crossing 1000 conflicts")
            if row.get("action") != "NATIVE" or row.get("f", {}).get("r_switches") != 0:
                raise ValueError("checkpoint is not before the first action")
            cpu, learned = row.get("process_cpu_s"), row.get("learned")
            if isinstance(cpu, bool) or not isinstance(cpu, (int, float)) or not math.isfinite(cpu) or cpu < 0:
                raise ValueError("observer lacks a valid absolute process CPU time")
            if cpu > 2:
                return {"status": "MISSING", "missing_reason": "checkpoint_after_cpu_limit", "checkpoint": row}
            if isinstance(learned, bool) or not isinstance(learned, int) or learned < 0:
                raise ValueError("observer lacks a valid checkpoint learned-event count")
            if learned < 20:
                return {"status": "MISSING", "missing_reason": "fewer_than_20_learned_events", "checkpoint": row}
            features = {name: row.get("f", {}).get(source) for name, source in FEATURE_MAP.items()}
            if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in features.values()):
                return {"status": "MISSING", "missing_reason": "undefined_dynamic_denominator", "checkpoint": row}
            return {"status": "COMPLETE", "features": features, "checkpoint": row}
        if row.get("type") in {"decision", "switch"}:
            # The controller writes an initial apply record before search.
            if row.get("reason") != "initial":
                raise ValueError("action occurred before the requested observation")
    return None


def limited_exec(helper, solver, cnf, telemetry):
    resource.setrlimit(resource.RLIMIT_AS, (PROFILE["memory_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (PROFILE["file_limit_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    os.environ["FPC_LOG"] = str(Path(telemetry).resolve())
    command = [str(Path(helper).resolve()), "2", str(Path(solver).resolve()), *FLAGS, str(Path(cnf).resolve())]
    os.execv(command[0], command)


def run_probe(solver, helper, cnf, directory, marker):
    directory = Path(directory)
    telemetry = directory / "telemetry.jsonl"
    start, observed, reason, parse_error = time.monotonic(), None, None, None
    with (directory / "stdout.txt").open("xb") as out, (directory / "stderr.txt").open("xb") as err:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_limited_exec",
            str(helper), str(solver), str(cnf), str(telemetry)], stdin=subprocess.DEVNULL,
            stdout=out, stderr=err, start_new_session=True)
        common.atomic_json(marker, {"owner_pid": os.getpid(), "child_pid": child.pid,
                                   "hostname": socket.gethostname()})
        while True:
            pid, status, usage = os.wait4(child.pid, os.WNOHANG)
            if pid:
                break
            try:
                if parse_error is None:
                    observed = parse_telemetry(telemetry)
            except Exception as exc:
                parse_error = type(exc).__name__ + ": " + str(exc)
                reason = "invalid_telemetry"
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if reason is None and observed is not None:
                reason = "checkpoint_observed"
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if time.monotonic() - start >= PROFILE["wall_limit_s"]:
                reason = reason or "wall_limit"
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            time.sleep(.01)
        child.returncode = os.waitstatus_to_exitcode(status)
    cpu, wall = usage.ru_utime + usage.ru_stime, time.monotonic() - start
    # A partial trailing line after SIGPROF is expected.  A complete checkpoint
    # preceding it remains valid; terminal stdout/status is never a feature.
    if parse_error is None and observed is None:
        try:
            observed = parse_telemetry(telemetry)
        except Exception as exc:
            parse_error = type(exc).__name__ + ": " + str(exc)
    details = {"feature_cpu_s": cpu, "feature_wall_s": wall, "exit_code": child.returncode,
               "termination": reason or "process_exit", "stderr": (directory / "stderr.txt").read_text(errors="replace")[:4000],
               "telemetry_sha256": common.sha(telemetry) if telemetry.exists() else None}
    if parse_error is not None:
        return {**details, "status": "FAILED", "error": parse_error, "features": None}
    if observed is not None:
        return {**details, **observed}
    if child.returncode in (10, 20):
        return {**details, "status": "EARLY_SOLVED_UNVERIFIED", "missing_reason": "terminal_before_checkpoint",
                "answer_adopted": False, "features": None}
    if reason == "wall_limit" or child.returncode in (-signal.SIGPROF, -signal.SIGXCPU) or cpu >= 2:
        return {**details, "status": "MISSING", "missing_reason": "budget_before_checkpoint", "features": None}
    return {**details, "status": "FAILED", "error": "unexpected process exit before observation", "features": None}


def reusable(path, task, identity):
    record = json.loads(Path(path).read_text())
    for key, value in {"task_key": task["task_key"], "input_sha256": task["input_sha256"],
                       "profile": PROFILE, **{k: identity[k] for k in IDENTITY_FIELDS}}.items():
        if record.get(key) != value:
            raise ValueError("existing dynamic receipt identity mismatch: " + key)
    content_sha = record.pop("receipt_content_sha256", None)
    if hashlib.sha256(common.canonical(record)).hexdigest() != content_sha:
        raise ValueError("existing dynamic receipt content hash mismatch")
    record["receipt_content_sha256"] = content_sha
    return record


def process_task(task, solver, helper, identity, output, node_id, cache):
    output = Path(output)
    receipt = output / "results" / (task["task_key"] + ".json")
    if receipt.exists():
        return reusable(receipt, task, identity), True
    marker = output / "inflight" / (task["task_key"] + ".json")
    if marker.exists():
        raise RuntimeError("unresolved in-flight probe; no automatic requeue")
    common.atomic_json(marker, {"owner_pid": os.getpid(), "hostname": socket.gethostname()})
    record = {"schema_version": 1, "task_key": task["task_key"], "id": task["instance_id"],
              "instance_id": task["instance_id"], "role": task["role"], "input_sha256": task["input_sha256"],
              **{k: identity[k] for k in IDENTITY_FIELDS}, "profile": PROFILE, "node_id": node_id,
              "hostname": socket.gethostname(), "platform": platform.platform(), "features": None,
              "feature_cpu_s": 0.0, "feature_wall_s": 0.0, "answer_adopted": False}
    prep_cpu, prep_wall = time.thread_time(), time.monotonic()
    try:
        if worker_capacity(output, 1) < 1:
            record.update(status="RESOURCE_UNAVAILABLE", error="no current probe headroom")
        else:
            with tempfile.TemporaryDirectory(prefix=task["task_key"] + "-", dir=output / "temporary") as temporary:
                cnf = common.prepare_input(task, temporary, cache)
                record.update(preparation_cpu_s=time.thread_time() - prep_cpu,
                              preparation_wall_s=time.monotonic() - prep_wall, source_check="input_sha256_match")
                result = run_probe(solver, helper, cnf, temporary, marker)
                # Preserve raw telemetry as evidence, independently bound by SHA.
                trace = Path(temporary) / "telemetry.jsonl"
                if trace.exists():
                    shutil.copyfile(trace, output / "telemetry" / (task["task_key"] + ".jsonl"))
                record.update(result)
    except Exception as exc:
        record.update(status="FAILED", error=type(exc).__name__ + ": " + str(exc), features=None)
    record.setdefault("preparation_cpu_s", time.thread_time() - prep_cpu)
    record.setdefault("preparation_wall_s", time.monotonic() - prep_wall)
    record["controller_cpu_s"] = max(0.0, time.thread_time() - prep_cpu - record["preparation_cpu_s"])
    record["total_accounted_cpu_s"] = record["preparation_cpu_s"] + record["feature_cpu_s"] + record["controller_cpu_s"]
    record["receipt_content_sha256"] = hashlib.sha256(common.canonical(record)).hexdigest()
    common.atomic_json(receipt, record)
    marker.unlink()
    return record, False


def parse_cpu_set(value):
    cpus = set()
    for part in value.split(","):
        span = part.split("-")
        if len(span) == 1:
            cpus.add(int(span[0]))
        elif len(span) == 2:
            lo, hi = map(int, span)
            if not 0 <= lo <= hi:
                raise ValueError("invalid CPU range")
            cpus.update(range(lo, hi + 1))
        else:
            raise ValueError("invalid CPU set")
    if not cpus or min(cpus) < 0:
        raise ValueError("empty or negative CPU set")
    return cpus


def run(args):
    if not sys.platform.startswith("linux"):
        raise RuntimeError("fractional CPU helper is qualified only on Linux")
    manifest = load_manifest(args.manifest, args.solver, args.cpu_helper, args.observer_source)
    if manifest["node_id"] != args.node_id:
        raise ValueError("node differs from central owner's fixed shard")
    cpus = parse_cpu_set(args.cpu_set)
    if not cpus <= os.sched_getaffinity(0):
        raise ValueError("owner CPU allocation is outside current affinity")
    os.sched_setaffinity(0, cpus)
    output = args.output_dir.resolve()
    binding = {"manifest_sha256": hashlib.sha256(common.canonical(manifest)).hexdigest(), "node_id": args.node_id}
    with common.owner_lock(output, binding):
        for name in ("results", "inflight", "temporary", "telemetry"):
            (output / name).mkdir(exist_ok=True)
        slots = worker_capacity(output, args.max_workers)
        if slots < 1:
            raise RuntimeError("no resource-qualified dynamic slots")
        tasks, receipts = queue.Queue(), []
        accounted, reserved = 0.0, 0.0
        for task in manifest["tasks"]:
            receipt = output / "results" / (task["task_key"] + ".json")
            if receipt.exists():
                record = reusable(receipt, task, manifest)
                accounted += record["total_accounted_cpu_s"]
                receipts.append(record)
            else:
                tasks.put(task)
        mutex, stop = threading.Lock(), threading.Event()
        def persist():
            common.atomic_json(output / "progress.json", {**binding, "planned": len(manifest["tasks"]),
                "completed": len(receipts), "statuses": dict(collections.Counter(r["status"] for r in receipts)),
                "accounted_cpu_s": accounted, "reserved_cpu_s": reserved,
                "allocated_cpu_s": manifest["allocated_cpu_s"]})
        def worker():
            nonlocal accounted, reserved
            while not stop.is_set():
                with mutex:
                    if accounted + reserved + PROFILE["reservation_cpu_s"] > manifest["allocated_cpu_s"]:
                        return
                    try:
                        task = tasks.get_nowait()
                    except queue.Empty:
                        return
                    reserved += PROFILE["reservation_cpu_s"]
                    persist()
                record, reused = process_task(task, args.solver, args.cpu_helper, manifest, output,
                                              args.node_id, args.input_cache)
                with mutex:
                    reserved -= PROFILE["reservation_cpu_s"]
                    accounted += record["total_accounted_cpu_s"]
                    receipts.append(record)
                    if record["status"] in {"FAILED", "RESOURCE_UNAVAILABLE"}:
                        stop.set()
                    persist()
        persist()
        with concurrent.futures.ThreadPoolExecutor(max_workers=slots) as pool:
            for future in [pool.submit(worker) for _ in range(slots)]:
                future.result()
        result = {**binding, "schema_version": 1, "planned": len(manifest["tasks"]),
                  "completed": len(receipts), "accounted_cpu_s": accounted,
                  "statuses": dict(collections.Counter(r["status"] for r in receipts)),
                  "complete": len(receipts) == len(manifest["tasks"]), "early_answers_adopted": False}
        common.atomic_json(output / "completion.json", result)
        return result


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_limited_exec":
        limited_exec(*sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    patch = sub.add_parser("patch-observer")
    patch.add_argument("--source", required=True, type=Path)
    patch.add_argument("--output", required=True, type=Path)
    runner = sub.add_parser("run")
    for flag in ("manifest", "solver", "cpu-helper", "observer-source", "output-dir"):
        runner.add_argument("--" + flag, required=True, type=Path)
    runner.add_argument("--node-id", required=True)
    runner.add_argument("--cpu-set", required=True, help="central owner allocated free CPUs, e.g. 4-7")
    runner.add_argument("--max-workers", type=int, default=1)
    runner.add_argument("--input-cache", type=Path)
    args = parser.parse_args()
    print(json.dumps(patch_observer(args.source, args.output) if args.command == "patch-observer" else run(args)))


if __name__ == "__main__":
    main()
