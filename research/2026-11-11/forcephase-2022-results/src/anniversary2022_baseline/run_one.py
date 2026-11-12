import argparse
import gzip
import math
import os
import signal
import subprocess
import time
import uuid
from collections import deque
from pathlib import Path
from .common import ACTIONS, check_model, fingerprint, parse_stats, process_state, read, sha, utc, write


def limited_process(command, log, cpu_limit, wall_limit, memory, file_limit, affinity, active_path, grace=5):
    actual = ["prlimit", f"--as={memory}", f"--fsize={file_limit}",
              f"--cpu={math.ceil(cpu_limit)+2}:{math.ceil(cpu_limit)+4}", "--",
              "taskset", "-c", str(affinity), *map(str, command)]
    begin = time.monotonic(); reason = None; stop_at = None; hard_kill = False
    with Path(log).open("xb") as f:
        child = subprocess.Popen(actual, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        state = process_state(child.pid)
        write(active_path, {"pid": child.pid, "start_ticks": state["start_ticks"] if state else None,
                            "command": actual, "started_utc": utc()})
        while True:
            pid, status, usage = os.wait4(child.pid, os.WNOHANG)
            if pid: break
            now = time.monotonic(); current = process_state(child.pid)
            if reason is None:
                if current and current["cpu_s"] >= cpu_limit:
                    reason = "CPU_LIMIT"; stop_at = now
                    try: os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
                elif now - begin >= wall_limit:
                    reason = "WALL_WATCHDOG"; stop_at = now
                    try: os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
            elif not hard_kill and now - stop_at >= grace:
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                hard_kill = True
            time.sleep(0.02)
        child.returncode = os.waitstatus_to_exitcode(status)
    Path(active_path).unlink(missing_ok=True)
    return {"command": actual, "exit_code": child.returncode,
            "cpu_user_s": usage.ru_utime, "cpu_system_s": usage.ru_stime,
            "cpu_s": usage.ru_utime + usage.ru_stime, "wall_s": time.monotonic() - begin,
            "maxrss_kib": usage.ru_maxrss, "stop_reason": reason,
            "hard_kill": hard_kill, "cpu_affinity": affinity}


def run_one(spec, staged, action, seed, root, affinity, measurement_identity):
    root = Path(root)
    key = {"identity": measurement_identity, "input_sha256": staged["input_sha256"], "action": action, "seed": seed}
    run_id = fingerprint(key)
    destination = root / "runs" / run_id / "result.json"
    if destination.exists():
        result = read(destination)
        if result["measurement_key"] != key: raise ValueError("run identity collision")
        return result, True
    directory = destination.parent
    if directory.exists():
        raise RuntimeError("unfinished attempt preserved; recovery requires a distinct attempt namespace")
    directory.mkdir(parents=True)
    if sha(staged["path"]) != staged["input_sha256"]:
        raise ValueError("staged input changed before execution")
    T = spec["cutoff_s"]
    proof, log = directory / "solver.lrat", directory / "solver.log"
    command = [spec["solver_path"], *ACTIONS[action], f"--seed={seed}", "--stats", "--lrat", "--binary=true",
               "-t", str(math.ceil(spec["wall_watchdog_s"])), staged["path"], str(proof)]
    physical_id = str(uuid.uuid4()); started = utc(); thread0 = time.thread_time()
    measured = limited_process(command, log, T, spec["wall_watchdog_s"], spec["memory_bytes"],
                               spec["proof_limit_bytes"], affinity, directory / "active.json",
                               spec.get("termination_grace_s", 5))
    with log.open(errors="replace") as f:
        tail = "".join(deque(f, maxlen=1000))
    (directory / "last1000.log").write_text(tail)
    stats = parse_stats(tail)
    raw_answer = {10: "SAT", 20: "UNSAT"}.get(measured["exit_code"])
    if measured["stop_reason"] == "CPU_LIMIT": status = "CPU_TIMEOUT"
    elif measured["stop_reason"] == "WALL_WATCHDOG": status = "WALL_WATCHDOG"
    elif raw_answer: status = raw_answer
    elif measured["exit_code"] == 0: status = "UNKNOWN"
    else: status = "ERROR"
    if raw_answer and measured["cpu_s"] > T: status = "CPU_TIMEOUT"
    verification = "NOT_ANSWERED"; checker_result = None; verification_cpu = 0.
    proof_bytes = proof.stat().st_size if proof.exists() else 0
    if status == "SAT":
        check_begin = time.thread_time()
        verification = "VERIFIED_MODEL" if check_model(staged["path"], log) else "INVALID_MODEL"
        verification_cpu = time.thread_time() - check_begin
    elif status == "UNSAT":
        checker_log = directory / "checker.log"
        checker_result = limited_process([spec["checker_path"], "--no-trim", staged["path"], str(proof)],
            checker_log, spec["checker_cpu_s"], spec["checker_wall_s"], spec["memory_bytes"],
            spec["proof_limit_bytes"], affinity, directory / "checker_active.json",
            spec.get("termination_grace_s", 5))
        verification_cpu = checker_result["cpu_s"]
        verified_line = any(line.strip() == "s VERIFIED" for line in checker_log.read_text(errors="replace").splitlines())
        verification = "VERIFIED_LRAT" if checker_result["exit_code"] == 20 and verified_line else "PENDING_VERIFICATION"
    resolved = status in {"SAT", "UNSAT"} and verification.startswith("VERIFIED_") and measured["cpu_s"] <= T
    valid = resolved or status in {"CPU_TIMEOUT", "UNKNOWN"}
    proof_digest = sha(proof) if proof.exists() and status == "UNSAT" else None
    if proof.exists() and (resolved or status in {"CPU_TIMEOUT", "UNKNOWN"}): proof.unlink()
    log_digest = sha(log)
    with log.open("rb") as src, gzip.open(directory / "solver.log.gz", "wb") as out:
        import shutil
        shutil.copyfileobj(src, out)
    log.unlink()
    result = {**measured, **stats, "schema": "anni2022.run.v1", "run_id": run_id,
              "physical_execution_id": physical_id, "measurement_key": key,
              "instance_key": staged["instance_key"], "input_sha256": staged["input_sha256"],
              "action": action, "seed": seed, "started_utc": started, "finished_utc": utc(),
              "status": status, "answer_reported": raw_answer, "verification_status": verification,
              "verification_cpu_s": verification_cpu, "checker": checker_result,
              "resolved": resolved, "valid_measurement": valid, "cutoff_s": T,
              "par2": measured["cpu_s"] if resolved else 2*T if valid else None,
              "conflicts_observation": "termination" if measured["stop_reason"] and stats["conflicts"] is not None else
                   "terminal" if stats["conflicts"] is not None else "missing",
              "log_sha256": log_digest, "compressed_log_sha256": sha(directory / "solver.log.gz"),
              "tail_log_sha256": sha(directory / "last1000.log"),
              "proof_bytes": proof_bytes, "proof_sha256": proof_digest,
              "physical_cpu_s": measured["cpu_s"] + (checker_result["cpu_s"] if checker_result else 0.) + time.thread_time() - thread0}
    write(destination, result)
    return result, False


def main():
    p = argparse.ArgumentParser(); p.add_argument("--spec", required=True); p.add_argument("--staged", required=True)
    p.add_argument("--action", choices=list(ACTIONS), required=True); p.add_argument("--root", required=True)
    p.add_argument("--cpu", type=int, required=True); a = p.parse_args()
    raise SystemExit("Use run_baselines: direct execution requires the shared owner/resource ledger")


if __name__ == "__main__": main()
