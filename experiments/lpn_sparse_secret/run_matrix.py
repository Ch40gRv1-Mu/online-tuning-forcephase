"""Resumable runner for a static-configuration matrix.

Every run has a stable run_id = <exp>:<hash>:<config>:s<seed>. The ledger
results/<exp>/runs.jsonl (inside this directory) is append-only; already-recorded run_ids are skipped
on resume, never re-run to replace an unfavourable outcome. Raw solver logs
live in $LPN_WORK/runs/<exp>/ (witness lines kept until verify_runs.py has
checked them).

Usage:
  python3 scripts/run_matrix.py --exp m2_pilot --manifest benchmarks/pilot.csv \
      --configs D,Im,Fm,Fp,D_noR,Im_noR,S --seeds 0 --timeout 60 --workers 8
"""

import argparse
import os
import time
import csv
import datetime
import json
import platform
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fplib  # noqa: E402

PLAIN = fplib.FP_WORK / "cnf-plain"
CONTENTION_RATIO = 1.10  # wall/cpu above this => measurement invalid, rerun
MAX_ATTEMPTS = 4         # original + up to 3 reruns


def is_contended(rec):
    if "contended" in rec:
        return rec["contended"]
    return rec["cpu_s"] > 1 and rec["wall_s"] / rec["cpu_s"] > CONTENTION_RATIO


def wait_for_quiet(limit):
    while os.getloadavg()[0] >= limit:
        time.sleep(15)


def plain_cnf(h, expect_sha=None):
    """Generated CNFs live in $LPN_WORK/cnf-plain; verify the hash if known."""
    dst = PLAIN / f"{h}.cnf"
    if not dst.exists():
        raise FileNotFoundError(f"{dst} missing: run lpn_gen.py for this grid first")
    if expect_sha and fplib.sha256_file(dst) != expect_sha:
        raise RuntimeError(f"CNF hash mismatch for {h}: regenerate with lpn_gen.py")
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--configs", required=True)
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--timeout", type=int, required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--order-seed", type=int, default=1)
    ap.add_argument("--quiet-load", type=float, default=None,
                    help="before each launch wait until 1-min load average < this")
    ap.add_argument("--max-wall-hours", type=float, default=None,
                    help="stop scheduling new runs after this much wall-clock time")
    ap.add_argument("--max-core-hours", type=float, default=None,
                    help="stop scheduling new runs once worst-case budget is hit")
    a = ap.parse_args()

    configs = a.configs.split(",")
    seeds = [int(s) for s in a.seeds.split(",")]
    rows = list(csv.DictReader(open(a.manifest)))
    res_dir = fplib.RESULTS / a.exp
    res_dir.mkdir(parents=True, exist_ok=True)
    log_dir = fplib.FP_WORK / "runs" / a.exp
    log_dir.mkdir(parents=True, exist_ok=True)
    ledger = res_dir / "runs.jsonl"
    done, attempts, latest = set(), {}, {}
    if ledger.exists():
        for line in open(ledger):
            rec = json.loads(line)
            attempts[rec["run_id"]] = attempts.get(rec["run_id"], 0) + 1
            latest[rec["run_id"]] = rec
    for rid, rec in latest.items():
        if not is_contended(rec) or attempts[rid] >= MAX_ATTEMPTS:
            done.add(rid)

    jobs = [(r, c, s) for r in rows for c in configs for s in seeds]
    random.Random(a.order_seed).shuffle(jobs)  # spread configs over time
    todo = [j for j in jobs if f"{a.exp}:{j[0]['hash']}:{j[1]}:s{j[2]}" not in done]
    worst = len(jobs) * a.timeout / 3600
    meta = {
        "exp": a.exp, "manifest": a.manifest, "configs": {c: fplib.CONFIGS[c] for c in configs},
        "seeds": seeds, "timeout_s": a.timeout, "workers": a.workers,
        "order_seed": a.order_seed, "n_jobs": len(jobs), "n_todo": len(todo),
        "worst_case_core_hours": worst,
        "binary": str(fplib.CADICAL), "binary_sha256": fplib.sha256_file(fplib.CADICAL),
        "common_flags": ["--stats", "--seed=<seed>", "-t <timeout>"],
        "max_wall_hours": a.max_wall_hours, "max_core_hours": a.max_core_hours,
        "host": platform.node(), "python": sys.version.split()[0],
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with open(res_dir / "run_meta.jsonl", "a") as f:
        f.write(json.dumps(meta) + "\n")
    print(f"{len(jobs)} jobs, {len(todo)} to run, worst case {worst:.2f} core-h", flush=True)

    fetch_log = Path(a.manifest).with_name(Path(a.manifest).stem + "_fetch.jsonl")
    shas = {}
    if fetch_log.exists():
        shas = {json.loads(l)["hash"]: json.loads(l)["sha256_cnf"] for l in open(fetch_log)}
    for h in sorted({j[0]["hash"] for j in todo}):
        plain_cnf(h, shas.get(h))
    print("plain CNFs ready and hash-checked", flush=True)

    lock = threading.Lock()
    budget = {"used_h": 0.0, "stopped": False}
    t_start = time.monotonic()

    def one(job):
        row, cfg, seed = job
        if a.max_wall_hours and time.monotonic() - t_start > a.max_wall_hours * 3600:
            budget["stopped"] = True
        if budget["stopped"]:
            return None
        h = row["hash"]
        run_id = f"{a.exp}:{h}:{cfg}:s{seed}"
        cnf = PLAIN / f"{h}.cnf"
        if a.quiet_load:
            with lock:
                wait_for_quiet(a.quiet_load)
        log = log_dir / f"{h}.{cfg}.s{seed}.log"
        r = fplib.run_solver(cnf, cfg, ["--stats", f"--seed={seed}"],
                             timeout=a.timeout, stdout_path=log)
        r.pop("_stdout")
        # Solved only if answered within the CaDiCaL wall limit AND the
        # child CPU time is within T (primary metric is single-core CPU).
        solved = r["status"] in ("SAT", "UNSAT") and r["cpu_s"] <= a.timeout
        contended = r["cpu_s"] > 1 and r["wall_s"] / r["cpu_s"] > CONTENTION_RATIO
        rec = {"run_id": run_id, "attempt": attempts.get(run_id, 0) + 1,
               "contended": contended, "exp": a.exp, "hash": h, "config": cfg, "seed": seed,
               "timeout_s": a.timeout, "family": row["family"], "group": row["group"],
               "split": row["family_split"], "gbd_result": row["result"],
               "solved_within_T": solved, "log": str(log),
               "finished": datetime.datetime.now(datetime.timezone.utc).isoformat(), **r}
        with lock:
            with open(ledger, "a") as f:
                f.write(json.dumps(rec) + "\n")
            budget["used_h"] += r["cpu_s"] / 3600
            if a.max_core_hours and budget["used_h"] >= a.max_core_hours:
                budget["stopped"] = True
        return rec

    n = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(one, j) for j in todo]
        for fut in as_completed(futs):
            rec = fut.result()
            if rec is None:
                continue
            n += 1
            if n % 25 == 0 or n == len(todo):
                print(f"[{n}/{len(todo)}] {rec['config']:7s} {rec['status']:8s} "
                      f"cpu={rec['cpu_s']:.1f}s used={budget['used_h']:.2f}h", flush=True)
    if budget["stopped"]:
        print("STOPPED: core-hour or wall-clock budget reached; rerun to resume.")


if __name__ == "__main__":
    main()
