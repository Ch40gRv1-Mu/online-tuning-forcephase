#!/usr/bin/env python3
"""Audit v2, P0: machine-readable integrity audit of every round-1 experiment.

  scripts/audit_v2/integrity.py --out results/audit_v2/integrity [--jobs 32]

For every experiment in configs/experiments/ (except 'smoke', whose records were
made with an earlier host-built binary and are not part of any analysis) and
every planned run: record present and identical key; binary hash = build hash;
instance in manifest/checksums and stored CNF hash verified; T and memory as
specified; status consistent (solved => verified within T, timeout => cutoff);
telemetry present/parsable/complete (appendix A for SIGKILL after cutoff),
schema 1, header consistent with the configuration arguments; actions actually
taken as configured (fixed/telemetry: no switch; schedule: exactly one switch at
the checkpoint covering fpcat iff it was reached; oneshot policy: decision at its
prefix checkpoint iff reached and a switch iff the slot changed; repeat policy:
switch records consistent with the final count); duplicate keys in the
collected CSVs.  Writes summary.md, per-run CSV and exceptions.csv.
"""

import argparse
import collections
import csv
import hashlib
import json
import multiprocessing as mp
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import fprun  # noqa: E402
import gate  # noqa: E402

KEYCOLS = ["config", "instance", "variant", "seed", "repeat"]


def argval(args, name, default):
    for a in args:
        if a.startswith(f"--{name}="):
            return float(a.split("=", 1)[1])
    return default


def check_run(task):
    run, exp_T, exp_mem = task
    rid, key = run["run_id"], run["key"]
    out = {"run_id": rid, "exp": run["exp"], "config": run["config"], "instance": key["instance"],
           "variant": key["variant"], "seed": key["seed"], "repeat": key.get("repeat", 0), "problems": []}
    P = out["problems"]
    path = fprun.result_path(rid)
    if not os.path.exists(path):
        P.append("record_missing")
        return out
    rec = fprun.load_json(path)
    out["status"] = rec["status"]
    if rec["run_id"] != rid or rec["key"] != key:
        P.append("key_mismatch")
    if key["timeout"] != exp_T or key["memory_mb"] != exp_mem:
        P.append("budget_mismatch")
    T = key["timeout"]
    st = rec["status"]
    ver = rec.get("verification") or {}
    if st not in ("solved", "timeout", "memout", "crash", "error", "wrong", "unverified"):
        P.append("status_unknown")
    if st == "solved":
        if ver.get("ok") is not True:
            P.append("solved_not_verified")
        if rec["cpu"] > T or rec["exit_code"] not in (10, 20):
            P.append("solved_inconsistent")
        if (rec["exit_code"] == 10) != (ver.get("method") == "checkmodel"):
            P.append("verification_method_mismatch")
    if st == "timeout" and not (rec["terminated_by"] or rec["cpu"] > T):
        P.append("timeout_inconsistent")
    if st in ("wrong", "unverified", "crash", "error", "memout"):
        P.append(f"status_{st}")
    if not key["telemetry"]:
        return out
    recs, problem = gate.load_telemetry(os.path.join(fprun.raw_dir(rid), "telemetry.jsonl.gz"))
    summ = {"status": st, "terminated_by": rec["terminated_by"], "exit_code": rec["exit_code"], "cpu": rec["cpu"]}
    killed = False
    if problem == "telemetry_incomplete" and gate.killed_after_cutoff(summ, T) and recs:
        killed = True
        out["note"] = "killed_after_cutoff"
    elif problem:
        P.append(problem)
        return out
    h = recs[0]
    args = key["config_args"]
    mode = int(argval(args, "fpc", 1))
    exp_h = {"schema": 1, "mode": mode, "track": "P" if argval(args, "fpctrack", 0) else "C",
             "init": int(argval(args, "fpcinit", 0)), "at": int(argval(args, "fpcat", 10000))}
    for k, v in exp_h.items():
        if h.get(k) != v:
            P.append(f"header_{k}")
    names = {0: "NATIVE", 1: "NEGATIVE", 2: "NATIVE_INIT_NEG", 3: "POSITIVE"}
    a = [names[int(argval(args, "fpca0", 0))], names[int(argval(args, "fpca1", 1))]]
    if h.get("a0") != a[0] or h.get("a1") != a[1]:
        P.append("header_actions")
    switches = [r for r in recs if r.get("type") == "switch"]
    cps = [r for r in recs if r.get("type") == "checkpoint"]
    fin = gate.final(recs)
    if fin is not None and fin.get("switches") != len(switches):
        P.append("final_switch_count")
    out["switches"] = len(switches)
    if mode in (1, 2):
        if switches:
            P.append("unexpected_switch")
    elif mode == 3:
        at = exp_h["at"]
        hit = [c for c in cps if c["crossed"][1] >= at]
        if hit:
            c0 = hit[0]
            target = a[1 - exp_h["init"]]
            if len(switches) != 1 or switches[0]["conflicts"] != c0["conflicts"] or \
                    switches[0].get("action") != target or switches[0].get("reason") != "schedule":
                P.append("schedule_switch_wrong")
        elif switches:
            P.append("schedule_switch_without_checkpoint")
    elif mode == 4:
        pol = open(os.path.join(fprun.ROOT, key["env"]["FPC_POLICY"])).read()
        if "type oneshot" in pol:
            prefix = int(pol.split("prefix", 1)[1].split()[0])
            dec = [r for r in recs if r.get("type") == "decision"]
            reached = any(c["crossed"][1] >= prefix for c in cps)
            if reached != bool(dec):
                P.append("oneshot_decision_inconsistent")
            if dec and (dec[0]["slot"] != exp_h["init"]) != bool(switches):
                P.append("oneshot_switch_inconsistent")
        else:
            if any(s.get("reason") != "repeat" for s in switches):
                P.append("repeat_switch_reason")
    return out


def cnf_check(h, expected):
    p = os.path.join(fprun.DATA, "benchmarks", "cnf", h + ".cnf.xz")
    if not os.path.exists(p):
        return h, "cnf_missing"
    d = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            d.update(chunk)
    return h, None if d.hexdigest() == expected else "cnf_hash_mismatch"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=32)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    man = fprun.manifest()
    checks = {r["hash"]: r for r in csv.DictReader(open(os.path.join(fprun.ROOT, "benchmarks", "checksums.csv")))}
    exps = sorted(f for f in os.listdir(os.path.join(fprun.ROOT, "configs", "experiments")) if f.endswith(".json"))
    tasks, per_exp, seen = [], collections.Counter(), set()
    for f in exps:
        exp = fprun.load_experiment(os.path.join(fprun.ROOT, "configs", "experiments", f))
        if exp["name"] == "smoke":
            continue
        for run in fprun.plan(exp, man):
            per_exp[exp["name"]] += 1
            if run["run_id"] in seen:  # shared runs (e.g. census D = M1 repeat 0) are checked once
                continue
            seen.add(run["run_id"])
            tasks.append((run, exp["timeout"], exp["memory_mb"]))
    insts = sorted({t[0]["key"]["instance"] for t in tasks})
    with mp.Pool(a.jobs) as pool:
        res = pool.map(check_run, tasks, chunksize=64)
        cnf = dict(pool.starmap(cnf_check, [(h, checks[h]["sha256_xz"] if h in checks else "") for h in insts]))
    for r in res:
        if r["instance"] not in man or r["instance"] not in checks:
            r["problems"].append("instance_not_in_manifest")
        if cnf.get(r["instance"]):
            r["problems"].append(cnf[r["instance"]])
    # duplicate keys in the collected CSVs
    dups = []
    for root, _, files in os.walk(os.path.join(fprun.ROOT, "results")):
        for fn in files:
            if fn == "runs.csv" and "audit_v2" not in root:
                rows = list(csv.DictReader(open(os.path.join(root, fn))))
                c = collections.Counter((r["exp"],) + tuple(r[k] for k in KEYCOLS) for r in rows)
                dups += [(os.path.relpath(os.path.join(root, fn), fprun.ROOT),) + k for k, v in c.items() if v > 1]
    with open(os.path.join(a.out, "runs_checked.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run_id", "exp", "config", "instance", "variant", "seed", "repeat", "status", "switches",
                    "note", "problems"])
        for r in res:
            w.writerow([r["run_id"], r["exp"], r["config"], r["instance"], r["variant"], r["seed"], r["repeat"],
                        r.get("status"), r.get("switches"), r.get("note", ""), ";".join(r["problems"])])
    exc = [r for r in res if r["problems"] or r.get("note")]
    with open(os.path.join(a.out, "exceptions.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run_id", "exp", "config", "instance", "status", "note", "problems"])
        for r in exc:
            w.writerow([r["run_id"], r["exp"], r["config"], r["instance"], r.get("status"), r.get("note", ""),
                        ";".join(r["problems"])])
    by = collections.defaultdict(collections.Counter)
    for r in res:
        by[r["exp"]]["runs_checked"] += 1
        by[r["exp"]][r.get("status") or "no_record"] += 1
        for p in r["problems"]:
            by[r["exp"]]["PROBLEM:" + p] += 1
        if r.get("note"):
            by[r["exp"]]["note:" + r["note"]] += 1
    lines = ["# Integrity audit of round-1 experiments (generated by scripts/audit_v2/integrity.py)\n",
             f"Experiments: {len(per_exp)}; planned runs (with shared runs counted per experiment): "
             f"{sum(per_exp.values())}; unique runs checked: {len(res)}; instances: {len(insts)} "
             f"(stored CNF SHA-256 verified against benchmarks/checksums.csv: "
             f"{sum(1 for h in insts if not cnf.get(h))} ok). 'smoke' excluded (made with an earlier host binary). "
             "A run planned by several experiments (e.g. census D = M1 repeat 0) is checked once and listed under the "
             "first experiment spec in alphabetical order.\n",
             "| experiment (owner of the record) | runs checked | solved | timeout | other status | problems | notes |",
             "|---|---|---|---|---|---|---|"]
    for e in sorted(by):
        c = by[e]
        other = sum(v for k, v in c.items() if k not in ("runs_checked", "solved", "timeout") and
                    not k.startswith("PROBLEM:") and not k.startswith("note:"))
        probs = ", ".join(f"{k[8:]} {v}" for k, v in c.items() if k.startswith("PROBLEM:")) or "0"
        notes = ", ".join(f"{k[5:]} {v}" for k, v in c.items() if k.startswith("note:")) or ""
        lines.append(f"| {e} | {c['runs_checked']} | {c['solved']} | {c['timeout']} | {other} | {probs} | {notes} |")
    lines.append(f"\nDuplicate (exp, config, instance, variant, seed, repeat) keys in collected CSVs: {len(dups)}.\n")
    nprob = sum(1 for r in res if r["problems"])
    lines.append(f"Runs with problems: **{nprob}**; runs with notes only (appendix A, SIGKILL after cutoff): "
                 f"{sum(1 for r in res if r.get('note') and not r['problems'])}. Exception list: exceptions.csv.\n")
    with open(os.path.join(a.out, "summary.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(1 if nprob or dups else 0)


if __name__ == "__main__":
    main()
