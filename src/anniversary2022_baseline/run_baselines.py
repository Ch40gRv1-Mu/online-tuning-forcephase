import argparse
import fcntl
import json
import os
import queue
import shutil
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .common import ACTIONS, cpu_total, fingerprint, process_state, read, sha, source_identity, utc, validate_spec, write
from .stage_inputs import stage
from .run_one import run_one


def connect(root):
    db = sqlite3.connect(str(Path(root) / "queue.sqlite"))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def progress(db, root, spec, started, prior_cpu, cpu0, prior_wall=0.):
    counts = dict(db.execute("SELECT state,count(*) FROM jobs GROUP BY state").fetchall())
    inputs = dict(db.execute("SELECT state,count(*) FROM inputs GROUP BY state").fetchall())
    completed = counts.get("COMPLETE", 0); expected = spec["expected_inputs"] * 3
    errors = counts.get("INVALID", 0) + counts.get("BLOCKED", 0)
    status = "COMPLETE_VALID_MATRIX" if completed == expected else "COMPLETE_WITH_UNRESOLVED_ERRORS" if completed + errors == expected else "PARTIAL"
    wall = time.monotonic() - started
    snapshot = {"status": status, "scope": spec["status"], "expected_runs": expected,
                "jobs": counts, "inputs": inputs, "completed_valid": completed,
                "session_wall_s": wall, "measured_cpu_s": prior_cpu + cpu_total() - cpu0,
                "total_execution_wall_s": prior_wall + wall,
                "remaining_runs": expected - completed - errors, "updated_utc": utc(),
                "eta_scope": "observed end-to-end rate; includes download and checking so far",
                "eta_remaining_wall_s": (expected-completed-errors) * (prior_wall+wall)/completed if completed and prior_wall+wall >= 1 else None}
    write(Path(root) / "progress.json", snapshot)
    return snapshot


def execute(root, spec_path=None, manifest_path=None):
    root = Path(root).resolve(); root.mkdir(parents=True, exist_ok=True)
    lock = (root / ".owner.lock").open("a+")
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise RuntimeError("healthy owner already holds this queue")
    frozen = root / "metadata"
    if spec_path is None:
        spec_path, manifest_path = frozen / "spec.json", frozen / "manifest.csv"
    spec = read(spec_path); rows = validate_spec(spec, manifest_path)
    identity = {"solver_sha256": spec["solver_sha256"], "checker_sha256": spec["checker_sha256"],
                "solver_commit": spec["solver_commit"], "source": source_identity(),
                "cutoff_s": spec["cutoff_s"], "clock": "solver_process_cpu", "verification": "timed_binary_lrat",
                "memory_bytes": spec["memory_bytes"], "proof_limit_bytes": spec["proof_limit_bytes"],
                "wall_watchdog_s": spec["wall_watchdog_s"], "checker_cpu_s": spec["checker_cpu_s"],
                "checker_wall_s": spec["checker_wall_s"], "host_id": Path("/etc/machine-id").read_text().strip()}
    frozen.mkdir(exist_ok=True)
    if (frozen / "spec.json").exists():
        if read(frozen / "spec.json") != spec or sha(frozen / "manifest.csv") != sha(manifest_path) or read(frozen / "identity.json") != identity:
            raise ValueError("resume identity changed; preserve original run root")
    else:
        write(frozen / "spec.json", spec); shutil.copyfile(manifest_path, frozen / "manifest.csv")
        write(frozen / "identity.json", identity)
    db = connect(root)
    db.executescript("""CREATE TABLE IF NOT EXISTS inputs(k TEXT PRIMARY KEY,ord INTEGER,row_json TEXT,state TEXT,receipt TEXT,error TEXT);
      CREATE TABLE IF NOT EXISTS jobs(k TEXT,action TEXT,seed INTEGER,state TEXT,result TEXT,error TEXT,
        PRIMARY KEY(k,action,seed));""")
    for i, row in enumerate(rows):
        db.execute("INSERT OR IGNORE INTO inputs VALUES(?,?,?,'QUEUED',NULL,NULL)", (row["instance_key"], i, json.dumps(row)))
        for action in ACTIONS:
            db.execute("INSERT OR IGNORE INTO jobs VALUES(?,?,0,'QUEUED',NULL,NULL)", (row["instance_key"], action))
    db.commit()
    # A dropped observer or controller never establishes that a child is dead.
    for path in root.glob("runs/*/*active.json"):
        active = read(path); state = process_state(active["pid"])
        if state and str(state["start_ticks"]) == str(active["start_ticks"]):
            raise RuntimeError("orphan child still active; do not duplicate: " + str(path))
    # Reconcile only immutable complete records. Incomplete attempts remain blocked.
    for path in root.glob("runs/*/result.json"):
        r = read(path)
        if r["measurement_key"]["identity"] != identity: raise ValueError("mixed runtime records")
        state = "COMPLETE" if r["valid_measurement"] else "INVALID"
        db.execute("UPDATE jobs SET state=?,result=?,error=NULL WHERE k=? AND action=? AND seed=?",
                   (state, str(path), r["instance_key"], r["action"], r["seed"]))
    db.execute("UPDATE jobs SET state='BLOCKED',error='incomplete attempt requires versioned recovery' WHERE state='RUNNING'")
    db.execute("UPDATE inputs SET state='QUEUED' WHERE state='STAGING'")
    db.commit()
    cpus = sorted(os.sched_getaffinity(0))[:spec["workers"]]
    memory_available = int(next(x.split()[1] for x in Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:"))) * 1024
    if len(cpus) * spec["memory_bytes"] + spec.get("memory_reserve_bytes", 1024**3) > memory_available:
        raise RuntimeError("frozen worker memory layout does not fit available RAM")
    tokens = queue.Queue()
    for cpu in cpus: tokens.put(cpu)
    write(root / "owner.json", {"pid": os.getpid(), "start_ticks": process_state(os.getpid())["start_ticks"],
                               "started_utc": utc(), "cpus": cpus, "identity_sha256": fingerprint(identity)})
    sessions = root / "sessions"; sessions.mkdir(exist_ok=True)
    prior_cpu = sum(read(p)["physical_cpu_s"] for p in sessions.glob("*.json"))
    prior_wall = sum(read(p)["wall_s"] for p in sessions.glob("*.json"))
    cpu0, started = cpu_total(), time.monotonic()
    session_id = str(uuid.uuid4()); pending_inputs = {}; pending_runs = {}; last_report = 0.; stop_reason = None
    def solve(job, staged):
        cpu = tokens.get()
        previous_affinity = os.sched_getaffinity(0)
        try:
            os.sched_setaffinity(0, {cpu})
            return run_one(spec, staged, job["action"], job["seed"], root, cpu, identity)
        finally:
            os.sched_setaffinity(0, previous_affinity)
            tokens.put(cpu)
    def prepare(row):
        failures = []
        for attempt in range(2):
            try: return stage(row, root, spec, tokens)
            except Exception as e:
                failures.append({"attempt": attempt+1, "error": repr(e), "utc": utc()})
                write(root / "input_failures" / (row["instance_key"] + ".json"), failures)
        raise RuntimeError("input preparation failed twice: " + failures[-1]["error"])
    try:
        with ThreadPoolExecutor(max_workers=spec.get("download_workers", 2)) as downloads, ThreadPoolExecutor(max_workers=len(cpus)) as solvers:
            while True:
                stop_reason = None
                changed = False
                for future, key in list(pending_inputs.items()):
                    if not future.done(): continue
                    del pending_inputs[future]; changed = True
                    try:
                        receipt = future.result()
                        db.execute("UPDATE inputs SET state='READY',receipt=?,error=NULL WHERE k=?", (json.dumps(receipt), key))
                    except Exception as e:
                        db.execute("UPDATE inputs SET state='BLOCKED',error=? WHERE k=?", (repr(e), key))
                        db.execute("UPDATE jobs SET state='BLOCKED',error=? WHERE k=? AND state='QUEUED'", (repr(e), key))
                for future, job in list(pending_runs.items()):
                    if not future.done(): continue
                    del pending_runs[future]; changed = True
                    try:
                        result, reused = future.result(); state = "COMPLETE" if result["valid_measurement"] else "INVALID"
                        db.execute("UPDATE jobs SET state=?,result=? WHERE k=? AND action=? AND seed=?", (state,
                            str(root / "runs" / result["run_id"] / "result.json"), job["k"], job["action"], job["seed"]))
                    except Exception as e:
                        db.execute("UPDATE jobs SET state='BLOCKED',error=? WHERE k=? AND action=? AND seed=?",
                            (repr(e), job["k"], job["action"], job["seed"]))
                finished_inputs = db.execute("SELECT k,receipt FROM inputs WHERE state='READY' AND NOT EXISTS (SELECT 1 FROM jobs WHERE jobs.k=inputs.k AND jobs.state IN ('QUEUED','RUNNING'))").fetchall()
                for item in finished_inputs:
                    db.execute("UPDATE inputs SET state='DONE' WHERE k=?", (item["k"],))
                    if spec.get("evict_completed_inputs", False):
                        staged = json.loads(item["receipt"]); cached = Path(staged["path"])
                        if cached.resolve() != (root/"cache"/(item["k"]+".cnf")).resolve():
                            raise ValueError("refuse to evict an input outside this owned cache")
                        # Failed units retain inputs and proofs for diagnosis.
                        all_valid = db.execute("SELECT count(*) FROM jobs WHERE k=? AND state!='COMPLETE'", (item["k"],)).fetchone()[0] == 0
                        if all_valid: cached.unlink(missing_ok=True)
                db.commit()
                used = prior_cpu + cpu_total() - cpu0
                # Reserve full upper work for in-flight units before further admission.
                unit_upper = spec["cutoff_s"] + spec["checker_cpu_s"] + 1
                budget_ok = used + (len(pending_runs)+1)*unit_upper < spec["max_physical_cpu_hours"]*3600
                if not budget_ok: stop_reason = "BUDGET_ADMISSION_BOUNDARY"
                buffered = db.execute("SELECT count(*) FROM inputs WHERE state IN ('READY','STAGING')").fetchone()[0]
                while budget_ok and buffered < spec.get("prefetch_parents", 16) and len(pending_inputs) < spec.get("download_workers", 2):
                    row = db.execute("SELECT * FROM inputs WHERE state='QUEUED' ORDER BY ord LIMIT 1").fetchone()
                    if row is None: break
                    db.execute("UPDATE inputs SET state='STAGING' WHERE k=?", (row["k"],)); db.commit()
                    pending_inputs[downloads.submit(prepare, json.loads(row["row_json"]))] = row["k"]
                    buffered += 1
                while budget_ok and len(pending_runs) < len(cpus):
                    disk_needed = spec["disk_reserve_bytes"] + (len(pending_runs)+1)*spec["proof_limit_bytes"]
                    if shutil.disk_usage(root).free < disk_needed:
                        stop_reason = "PROOF_DISK_ADMISSION"; break
                    job = db.execute("SELECT jobs.*,inputs.receipt FROM jobs JOIN inputs USING(k) WHERE jobs.state='QUEUED' AND inputs.state='READY' ORDER BY inputs.ord,jobs.action LIMIT 1").fetchone()
                    if job is None: break
                    db.execute("UPDATE jobs SET state='RUNNING' WHERE k=? AND action=? AND seed=?", (job["k"],job["action"],job["seed"])); db.commit()
                    pending_runs[solvers.submit(solve, dict(job), json.loads(job["receipt"]))] = dict(job)
                    budget_ok = used + (len(pending_runs)+1)*unit_upper < spec["max_physical_cpu_hours"]*3600
                if changed or time.monotonic() - last_report >= 2:
                    snap = progress(db, root, spec, started, prior_cpu, cpu0, prior_wall)
                    snap["admission_note"] = stop_reason
                    write(root / "progress.json", snap); last_report = time.monotonic()
                unfinished = db.execute("SELECT count(*) FROM jobs WHERE state IN ('QUEUED','RUNNING')").fetchone()[0]
                if not pending_inputs and not pending_runs and (not unfinished or not budget_ok or stop_reason == "PROOF_DISK_ADMISSION"):
                    break
                time.sleep(0.05)
    finally:
        session = {"physical_cpu_s": cpu_total()-cpu0, "wall_s": time.monotonic()-started,
                   "session_id": session_id, "finished_utc": utc(), "billing": "parent process plus all reaped children; not added again to nested run costs"}
        write(sessions / (session_id+".json"), session)
    snap = progress(db, root, spec, started, prior_cpu, cpu0, prior_wall)
    snap["admission_note"] = stop_reason; write(root / "progress.json", snap)
    if snap["status"] != "PARTIAL": write(root / "completion.json", snap)
    print(json.dumps(snap, sort_keys=True)); db.close(); lock.close()
    return 0 if snap["status"] == "COMPLETE_VALID_MATRIX" else 2


def main():
    p = argparse.ArgumentParser(); p.add_argument("command", choices=["start", "resume", "status"])
    p.add_argument("--root", required=True); p.add_argument("--spec"); p.add_argument("--manifest"); a = p.parse_args()
    if a.command == "status": print(json.dumps(read(Path(a.root)/"progress.json"), indent=2)); return
    if a.command == "start" and (not a.spec or not a.manifest): p.error("start requires --spec and --manifest")
    raise SystemExit(execute(a.root, a.spec if a.command == "start" else None, a.manifest if a.command == "start" else None))


if __name__ == "__main__": main()
