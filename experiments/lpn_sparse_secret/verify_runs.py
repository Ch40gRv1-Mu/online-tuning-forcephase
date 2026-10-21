"""Verify every answered run of an experiment ledger.

SAT   -> model from the run's own log checked against the ORIGINAL CNF.
UNSAT -> independent certification rerun (same binary/CNF/config/seed, plus
         --lrat --binary=false) checked by lrat-check; records whether the
         rerun's conflicts/decisions match the timed run (protocol 8.1).

Append-only ledger results/<exp>/verify.jsonl; resumable. After a SAT log is
checked its witness lines are stripped to save space.

Usage: python3 scripts/verify_runs.py --exp m2_pilot [--workers 4]
"""

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fplib  # noqa: E402

PLAIN = fplib.FP_WORK / "cnf-plain"
PROOFS = fplib.FP_WORK / "proofs"
CHECK_TIMEOUT = 1800
MAX_PROOF_BYTES = 30 * 10**9
MIN_FREE_DISK = int(float(os.environ.get("LPN_MIN_FREE_GB", "20")) * 10**9)  # wait if less free


def cert_timeout(T):
    """Pre-registered: max(180 s, 2T + 60 s) for the proof-producing rerun."""
    return max(180, 2 * T + 60)


def wait_for_disk():
    import shutil
    import time
    while shutil.disk_usage(fplib.FP_WORK).free < MIN_FREE_DISK:
        time.sleep(30)


def check_sat(rec):
    log = Path(rec["log"])
    text = log.read_text(errors="replace")
    vals = fplib.parse_witness(text)
    ok = bool(vals) and fplib.check_model(PLAIN / f"{rec['hash']}.cnf", vals)
    if ok:  # strip witness, keep everything else
        log.write_text("\n".join(l for l in text.splitlines() if not l.startswith("v ")) + "\n")
    return {"run_id": rec["run_id"], "vkey": rec["vkey"], "kind": "model",
            "verify": "VERIFIED_MODEL" if ok else "MODEL_INVALID"}


def certify_unsat(rec):
    PROOFS.mkdir(parents=True, exist_ok=True)
    cnf = PLAIN / f"{rec['hash']}.cnf"
    proof = PROOFS / f"{rec['hash']}.{rec['config']}.s{rec['seed']}.lrat"
    log = Path(rec["log"]).with_suffix(".cert.log")
    wait_for_disk()
    r = fplib.run_solver(cnf, rec["config"],
                         ["--stats", f"--seed={rec['seed']}", "--lrat", "--binary=false"],
                         timeout=cert_timeout(rec["timeout_s"]), proof=proof, stdout_path=log)
    out = {"run_id": rec["run_id"], "vkey": rec["vkey"], "kind": "lrat_rerun", "rerun_status": r["status"],
           "rerun_cpu_s": r["cpu_s"], "rerun_log": str(log),
           "rerun_conflicts": r.get("conflicts"), "rerun_decisions": r.get("decisions"),
           "same_conflicts": r.get("conflicts") == rec.get("conflicts"),
           "same_decisions": r.get("decisions") == rec.get("decisions")}
    if r["status"] != "UNSAT":
        out["verify"] = "UNVERIFIED_RERUN_" + r["status"]
    else:
        size = proof.stat().st_size if proof.exists() else 0
        out["proof_bytes"] = size
        if size > MAX_PROOF_BYTES:
            out["verify"] = "UNVERIFIED_PROOF_TOO_LARGE"
        else:
            import time
            t0 = time.monotonic()
            res = fplib.lrat_check(cnf, proof, timeout=CHECK_TIMEOUT)
            out["check_wall_s"] = time.monotonic() - t0
            out["verify"] = {"VERIFIED": "VERIFIED_LRAT",
                             "CHECK_TIMEOUT": "UNVERIFIED_CHECK_TIMEOUT"}.get(res, "PROOF_FAILED")
            if out["verify"] == "PROOF_FAILED":
                out["check_output"] = res
    proof.unlink(missing_ok=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    res_dir = fplib.RESULTS / a.exp
    latest = {}
    for l in open(res_dir / "runs.jsonl"):
        r = json.loads(l)
        r.setdefault("attempt", 1)
        latest[r["run_id"]] = r  # ledger is append-only: last line wins
    runs = list(latest.values())
    for r in runs:
        r["vkey"] = f"{r['run_id']}#a{r['attempt']}"
    vpath = res_dir / "verify.jsonl"
    done = set()
    if vpath.exists():
        done = {json.loads(l).get("vkey", json.loads(l)["run_id"] + "#a1") for l in open(vpath)}
    sat = [r for r in runs if r["status"] == "SAT" and r["vkey"] not in done]
    unsat = [r for r in runs if r["status"] == "UNSAT" and r["vkey"] not in done]
    print(f"to verify: {len(sat)} SAT models, {len(unsat)} UNSAT certification reruns", flush=True)
    lock = threading.Lock()

    def write(rec):
        with lock, open(vpath, "a") as f:
            f.write(json.dumps(rec) + "\n")

    with ProcessPoolExecutor(a.workers) as ex:
        for rec in ex.map(check_sat, sat):
            write(rec)
            if rec["verify"] != "VERIFIED_MODEL":
                print("MODEL FAILURE", rec, flush=True)
    n = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for rec in ex.map(certify_unsat, unsat):
            write(rec)
            n += 1
            if rec["verify"] != "VERIFIED_LRAT" or n % 20 == 0:
                print(n, rec["run_id"], rec["verify"], flush=True)
    vs = [json.loads(l) for l in open(vpath)]
    from collections import Counter
    print(Counter(v["verify"] for v in vs))


if __name__ == "__main__":
    main()
