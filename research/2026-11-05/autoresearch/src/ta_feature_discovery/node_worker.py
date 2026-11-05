#!/usr/bin/env python3
"""Run only an owner's public-CNF static-feature shard. No SAT solver calls."""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import contextlib
import fcntl
import gzip
import hashlib
import json
import lzma
import math
import os
from pathlib import Path
import platform
import queue
import re
import resource
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

PROFILE = {"kind": "cnf_static_v1", "extract_cpu_s": 2.0,
           "extract_wall_s": 8.0, "extract_memory_bytes": 3 * 1024**3,
           "max_plain_bytes": 100_000_000, "max_download_bytes": 128 * 1024**2}
SCHEMA = 1
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
TASK_KEYS = {"task_key", "instance_id", "id", "role", "public_url", "input_sha256",
             "source_sha256", "compressed_sha256", "metadata"}
META_KEYS = {"variables", "clauses", "bytes"}
HOSTS = {"benchmark-database.de", "satcompetition.github.io", "zenodo.org"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + str(os.getpid()) + "-" + str(threading.get_ident()))
    with temporary.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def public_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or p.hostname not in HOSTS or p.username or p.password or p.fragment:
        raise ValueError("public_url must be credential-free HTTPS on an approved public host")
    if p.port not in (None, 443):
        raise ValueError("nonstandard public URL port")
    return url


def task_key(task, extractor_sha):
    identity = {"instance_id": task["instance_id"], "input_sha256": task["input_sha256"],
                "extractor_source_sha256": extractor_sha, "profile": PROFILE}
    return hashlib.sha256(canonical(identity)).hexdigest()


def normalize_task(raw, extractor_sha, allowed_roles=None):
    if not isinstance(raw, dict) or set(raw) - TASK_KEYS:
        raise ValueError("unexpected task fields; timing, labels and credentials must not be bundled")
    task = dict(raw)
    instance = task.get("instance_id", task.get("id"))
    if not isinstance(instance, str) or not SAFE_ID.fullmatch(instance):
        raise ValueError("unsafe instance_id")
    allowed_roles = {"development_fit", "development_feedback"} if allowed_roles is None else set(allowed_roles)
    if task.get("role") not in allowed_roles:
        raise ValueError("task role is outside this explicitly authorized manifest")
    digest = task.get("input_sha256", task.get("source_sha256"))
    if not isinstance(digest, str) or not SHA.fullmatch(digest):
        raise ValueError("a frozen decompressed input SHA256 is required")
    if task.get("source_sha256", digest) != digest:
        raise ValueError("conflicting input SHA aliases")
    compressed = task.get("compressed_sha256")
    if compressed is not None and (not isinstance(compressed, str) or not SHA.fullmatch(compressed)):
        raise ValueError("invalid compressed SHA256")
    metadata = task.get("metadata", {})
    if not isinstance(metadata, dict) or set(metadata) - META_KEYS:
        raise ValueError("unexpected public metadata")
    for value in metadata.values():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("metadata values must be nonnegative integers")
    if metadata.get("bytes", 0) > PROFILE["max_plain_bytes"] or metadata.get("variables", 0) > 5_000_000:
        raise ValueError("task exceeds the frozen public-input qualification")
    task.update(instance_id=instance, input_sha256=digest, public_url=public_url(task["public_url"]))
    task.pop("id", None)
    task.pop("source_sha256", None)
    expected = task_key(task, extractor_sha)
    if task.get("task_key", expected) != expected:
        raise ValueError("task_key does not bind this input, extractor and profile")
    task["task_key"] = expected
    return task


def load_manifest(path, source, gate_candidate=None, gate_candidate_sha256=None):
    raw = json.loads(Path(path).read_text())
    source_sha = sha(source)
    if raw.get("extractor_source_sha256") != source_sha:
        raise ValueError("extractor source SHA differs from owner manifest")
    if raw.get("profile", PROFILE) != PROFILE:
        raise ValueError("profile differs from frozen static limits")
    if not SAFE_ID.fullmatch(str(raw.get("experiment_id", ""))) or not SAFE_ID.fullmatch(str(raw.get("shard_id", ""))):
        raise ValueError("safe experiment_id and shard_id are required")
    if gate_candidate is not None and gate_candidate_sha256 is not None:
        raise ValueError("provide the frozen gate candidate file or its SHA, not both")
    expected_gate_sha = sha(gate_candidate) if gate_candidate is not None else gate_candidate_sha256
    if expected_gate_sha is not None:
        if not isinstance(expected_gate_sha, str) or not SHA.fullmatch(expected_gate_sha):
            raise ValueError("explicit gate candidate SHA must be 64 lowercase hex characters")
        if raw.get("gate_candidate_sha256") != expected_gate_sha:
            raise ValueError("gate candidate SHA differs from the frozen manifest")
        if not raw["tasks"] or any(t.get("role") != "development_gate" for t in raw["tasks"]):
            raise ValueError("gate authorization requires exclusively development_gate tasks")
        allowed_roles = {"development_gate"}
    else:
        if "gate_candidate_sha256" in raw:
            raise ValueError("gate manifest requires --gate-candidate with the frozen candidate file")
        allowed_roles = None
    tasks = [normalize_task(t, source_sha, allowed_roles=allowed_roles) for t in raw["tasks"]]
    if len({t["task_key"] for t in tasks}) != len(tasks):
        raise ValueError("duplicate task identity in shard")
    raw["tasks"] = tasks
    raw["profile"] = PROFILE
    return raw


@contextlib.contextmanager
def owner_lock(output, identity):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".owner.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("this output already has a healthy owner") from exc
        binding = output / "owner_binding.json"
        if binding.exists() and json.loads(binding.read_text()) != identity:
            raise ValueError("output directory belongs to a different manifest/node")
        if not binding.exists():
            atomic_json(binding, identity)
        atomic_json(output / "owner_observation.json", {"pid": os.getpid(), "hostname": socket.gethostname(),
                                                     "node_id": identity["node_id"], "started_unix": time.time()})
        yield


def available_memory():
    if Path("/proc/meminfo").exists():
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    if sys.platform == "darwin":
        value = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True, timeout=3).stdout
        page = int(re.search(r"page size of (\d+) bytes", value).group(1))
        counts = [int(m.group(1)) for m in re.finditer(r"Pages (?:free|inactive|speculative):\s+(\d+)", value)]
        return page * sum(counts)
    raise RuntimeError("cannot determine available memory; unsupported node platform")


def worker_capacity(output, requested, memory=None, disk=None, cpus=None):
    cpu_count = cpus if cpus is not None else len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1
    memory = available_memory() if memory is None else memory
    disk = shutil.disk_usage(output).free if disk is None else disk
    return max(0, min(requested, cpu_count,
                      max(0, memory - 2 * 1024**3) // PROFILE["extract_memory_bytes"],
                      max(0, disk - 12 * 1024**3) // (256 * 1024**2)))


class ApprovedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def prepare_input(task, directory, cache=None):
    if cache:
        for name in (task["input_sha256"] + ".cnf", task["instance_id"] + ".cnf"):
            p = Path(cache) / name
            if p.is_file():
                if p.stat().st_size > PROFILE["max_plain_bytes"]:
                    raise ValueError("cached input exceeds qualification")
                if sha(p) != task["input_sha256"]:
                    raise ValueError("cached input SHA mismatch")
                return p
    directory = Path(directory)
    packed, plain = directory / "download", directory / "input.cnf"
    opener = urllib.request.build_opener(ApprovedRedirect())
    started = time.monotonic()
    with opener.open(task["public_url"], timeout=30) as src, packed.open("xb") as out:
        written = 0
        while True:
            chunk = src.read(1024**2)
            if not chunk:
                break
            written += len(chunk)
            if written > PROFILE["max_download_bytes"] or time.monotonic() - started > 120:
                raise ValueError("download exceeds bounded preparation limits")
            out.write(chunk)
    if task.get("compressed_sha256") and sha(packed) != task["compressed_sha256"]:
        raise ValueError("compressed input SHA mismatch")
    with packed.open("rb") as stream:
        magic = stream.read(6)
    reader = lzma.open if magic == b"\xfd7zXZ\x00" else gzip.open if magic[:2] == b"\x1f\x8b" else open
    with reader(packed, "rb") as src, plain.open("xb") as out:
        written = 0
        while True:
            chunk = src.read(1024**2)
            if not chunk:
                break
            written += len(chunk)
            if written > PROFILE["max_plain_bytes"]:
                raise ValueError("decompressed input exceeds qualification")
            out.write(chunk)
    if sha(plain) != task["input_sha256"]:
        raise ValueError("decompressed input SHA mismatch")
    if task.get("metadata", {}).get("bytes", plain.stat().st_size) != plain.stat().st_size:
        raise ValueError("input byte count differs from frozen public metadata")
    return plain


def limited_exec(binary, cnf):
    resource.setrlimit(resource.RLIMIT_AS, (PROFILE["extract_memory_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (2, 3))
    signal.setitimer(signal.ITIMER_PROF, PROFILE["extract_cpu_s"])
    os.execv(str(Path(binary).resolve()), [str(Path(binary).resolve()), str(Path(cnf).resolve())])


def run_extractor(binary, cnf, directory, marker):
    directory = Path(directory)
    start = time.monotonic()
    with (directory / "stdout.json").open("xb") as out, (directory / "stderr.txt").open("xb") as err:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_limited_exec", str(binary), str(cnf)],
                                 stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
        atomic_json(marker, {"owner_pid": os.getpid(), "child_pid": child.pid, "hostname": socket.gethostname()})
        killed = False
        while True:
            pid, status, usage = os.wait4(child.pid, os.WNOHANG)
            if pid:
                break
            if time.monotonic() - start >= PROFILE["extract_wall_s"] and not killed:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                killed = True
            time.sleep(.02)
        child.returncode = os.waitstatus_to_exitcode(status)
    elapsed = time.monotonic() - start
    cpu = usage.ru_utime + usage.ru_stime
    timeout = killed or cpu > PROFILE["extract_cpu_s"] or child.returncode in (-signal.SIGPROF, -signal.SIGXCPU)
    details = {"feature_cpu_s": cpu, "feature_wall_s": elapsed, "exit_code": child.returncode,
               "stderr": (directory / "stderr.txt").read_text(errors="replace")[:4000]}
    if timeout:
        return {**details, "status": "TIMEOUT", "features": None}
    if child.returncode:
        return {**details, "status": "FAILED", "features": None}
    try:
        features = json.loads((directory / "stdout.json").read_text())
        if not isinstance(features, dict) or not {"s_variables", "s_clauses", "s_mean_length"} <= set(features):
            raise ValueError("extractor returned an incomplete feature schema")
        if any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)) for v in features.values()):
            raise ValueError("extractor returned a nonnumeric/nonfinite feature")
    except Exception as exc:
        return {**details, "status": "FAILED", "features": None, "error": type(exc).__name__ + ": " + str(exc)}
    return {**details, "status": "COMPLETE", "features": features}


def reusable(path, task, extractor_sha):
    record = json.loads(Path(path).read_text())
    if any(record.get(k) != v for k, v in {"task_key": task["task_key"], "input_sha256": task["input_sha256"],
                                         "extractor_source_sha256": extractor_sha, "profile": PROFILE}.items()):
        raise ValueError("existing receipt identity mismatch")
    expected = record.pop("receipt_content_sha256", None)
    if hashlib.sha256(canonical(record)).hexdigest() != expected:
        raise ValueError("existing receipt content hash mismatch")
    record["receipt_content_sha256"] = expected
    return record


def process_task(task, binary, source_sha, output, node_id, cache, gate_candidate_sha256=None):
    output = Path(output)
    receipt_path = output / "results" / (task["task_key"] + ".json")
    if receipt_path.exists():
        record = reusable(receipt_path, task, source_sha)
        if gate_candidate_sha256 is not None and (record.get("gate_candidate_sha256") != gate_candidate_sha256 or
                                                  record.get("role") != "development_gate"):
            raise ValueError("gate receipt lacks its frozen candidate/role identity")
        return record, True
    marker = output / "inflight" / (task["task_key"] + ".json")
    if marker.exists():
        raise RuntimeError("unresolved in-flight task: require authoritative recovery before resubmission")
    atomic_json(marker, {"owner_pid": os.getpid(), "child_pid": None, "hostname": socket.gethostname()})
    base = {"schema_version": SCHEMA, "task_key": task["task_key"], "id": task["instance_id"],
            "instance_id": task["instance_id"], "role": task["role"], "input_sha256": task["input_sha256"],
            "extractor_source_sha256": source_sha, "extractor_binary_sha256": sha(binary),
            "node_id": node_id, "hostname": socket.gethostname(), "profile": PROFILE,
            "platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
            "features": None, "feature_cpu_s": 0., "feature_wall_s": 0.}
    if gate_candidate_sha256 is not None:
        base["gate_candidate_sha256"] = gate_candidate_sha256
    preparation_cpu, preparation_start = time.thread_time(), time.monotonic()
    record = dict(base)
    try:
        if worker_capacity(output, 1) < 1:
            record.update(status="RESOURCE_UNAVAILABLE", error="node lacks current static-worker headroom")
        else:
            with tempfile.TemporaryDirectory(prefix=task["task_key"] + "-", dir=output / "temporary") as temporary:
                cnf = prepare_input(task, temporary, cache)
                record.update(preparation_cpu_s=time.thread_time() - preparation_cpu,
                              preparation_wall_s=time.monotonic() - preparation_start, source_check="input_sha256_match")
                record.update(run_extractor(binary, cnf, temporary, marker))
                if record["status"] == "COMPLETE":
                    for key, feature in (("variables", "s_header_variables"), ("clauses", "s_clauses")):
                        if key in task.get("metadata", {}) and task["metadata"][key] != record["features"][feature]:
                            raise ValueError("feature/header counts differ from public metadata")
    except Exception as exc:
        record.update(status="FAILED", error=type(exc).__name__ + ": " + str(exc), features=None)
    record.setdefault("preparation_cpu_s", time.thread_time() - preparation_cpu)
    record.setdefault("preparation_wall_s", time.monotonic() - preparation_start)
    record["total_accounted_cpu_s"] = record["preparation_cpu_s"] + record["feature_cpu_s"]
    record["receipt_content_sha256"] = hashlib.sha256(canonical(record)).hexdigest()
    atomic_json(receipt_path, record)
    marker.unlink()
    return record, False


def compile_extractor(source, output, compiler):
    binary = Path(output) / "build" / "cnf_structure"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binding = binary.with_suffix(".identity.json")
    source_sha = sha(source)
    if binary.exists():
        identity = json.loads(binding.read_text())
        if identity["extractor_source_sha256"] != source_sha or identity["binary_sha256"] != sha(binary):
            raise ValueError("compiled extractor identity changed")
        return binary
    start = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    completed = subprocess.run([compiler, "-O3", "-std=c++17", str(Path(source).resolve()), "-o", str(binary)],
                               capture_output=True, text=True, timeout=120)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    identity = {"extractor_source_sha256": source_sha, "compile_wall_s": time.monotonic() - start,
                "compile_cpu_s": after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
                "compiler": compiler, "compile_exit_code": completed.returncode,
                "compiler_stderr": completed.stderr[:4000]}
    if completed.returncode:
        atomic_json(binding, identity)
        raise RuntimeError("extractor compilation failed; evidence retained")
    identity["binary_sha256"] = sha(binary)
    atomic_json(binding, identity)
    return binary


def run(args):
    manifest = load_manifest(args.manifest, args.extractor_source, getattr(args, "gate_candidate", None),
                             getattr(args, "gate_candidate_sha256", None))
    if manifest.get("node_id", args.node_id) != args.node_id or not SAFE_ID.fullmatch(args.node_id):
        raise ValueError("node_id differs from fixed shard")
    identity = {"manifest_sha256": hashlib.sha256(canonical(manifest)).hexdigest(), "node_id": args.node_id}
    output = Path(args.output_dir).resolve()
    with owner_lock(output, identity):
        for name in ("results", "temporary", "inflight"):
            (output / name).mkdir(exist_ok=True)
        capacity = worker_capacity(output, args.max_workers)
        if capacity < 1:
            raise RuntimeError("no available resource-qualified worker slot")
        if args.extractor_binary:
            if not args.expected_binary_sha256 or sha(args.extractor_binary) != args.expected_binary_sha256:
                raise ValueError("prebuilt extractor requires its exact owner-bound binary SHA256")
            binary = args.extractor_binary.resolve()
        else:
            binary = compile_extractor(args.extractor_source, output, args.compiler)
        tasks = queue.Queue()
        for task in manifest["tasks"]:
            tasks.put(task)
        completed, receipts, stop = [], [], threading.Event()
        mutex = threading.Lock()
        def worker():
            while not stop.is_set():
                try:
                    task = tasks.get_nowait()
                except queue.Empty:
                    return
                record, reused = process_task(task, binary, manifest["extractor_source_sha256"], output, args.node_id,
                                              args.input_cache, manifest.get("gate_candidate_sha256"))
                with mutex:
                    completed.append(record)
                    receipts.append({"task_key": task["task_key"], "sha256": sha(output / "results" / (task["task_key"] + ".json")), "reused": reused})
                    atomic_json(output / "progress.json", {"completed": len(completed), "planned": len(manifest["tasks"]),
                                                          "statuses": dict(collections.Counter(r["status"] for r in completed)), "node_id": args.node_id})
                if record["status"] in {"FAILED", "RESOURCE_UNAVAILABLE"}:
                    stop.set()
        with concurrent.futures.ThreadPoolExecutor(max_workers=capacity) as pool:
            for future in [pool.submit(worker) for _ in range(capacity)]:
                future.result()
        summary = {**identity, "schema_version": SCHEMA, "experiment_id": manifest["experiment_id"],
                   "shard_id": manifest["shard_id"], "planned": len(manifest["tasks"]), "completed": len(completed),
                   "statuses": dict(collections.Counter(r["status"] for r in completed)), "receipts": sorted(receipts, key=lambda r: r["task_key"]),
                   "status": "COMPLETE" if len(completed) == len(manifest["tasks"]) else "STOPPED_INCOMPLETE",
                   "worker_count": capacity, "feature_cpu_s": sum(r["feature_cpu_s"] for r in completed),
                   "preparation_cpu_s": sum(r["preparation_cpu_s"] for r in completed),
                   "new_physical_cpu_s": sum(r["total_accounted_cpu_s"] for r, x in zip(completed, receipts) if not x["reused"])}
        atomic_json(output / "completion.json", summary)
        print(json.dumps({k: summary[k] for k in ("status", "planned", "completed", "statuses", "worker_count")}))
        return 0 if summary["status"] == "COMPLETE" and not stop.is_set() else 2


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "_limited_exec":
        limited_exec(sys.argv[2], sys.argv[3])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--extractor-source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--input-cache", type=Path, help="Read-only cached plain CNFs, addressed by SHA or instance ID")
    parser.add_argument("--compiler", default="g++")
    parser.add_argument("--extractor-binary", type=Path, help="Use a qualified prebuilt extractor instead of compiling")
    parser.add_argument("--expected-binary-sha256", help="Required exact SHA256 when --extractor-binary is used")
    gate = parser.add_mutually_exclusive_group()
    gate.add_argument("--gate-candidate", type=Path, help="Local frozen candidate file; gate manifest SHA must match")
    gate.add_argument("--gate-candidate-sha256", help="Owner's exact frozen candidate SHA; no candidate data is transferred")
    args = parser.parse_args()
    if args.max_workers < 1:
        parser.error("--max-workers must be positive")
    try:
        return run(args)
    except Exception as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
