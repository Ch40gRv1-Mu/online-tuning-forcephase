#!/usr/bin/env python3
"""Audit v2 behaviour tests of the v2 controller on real runs.

  tests/audit_v2/test_controller_v2.py [--jobs 32] [--out results/audit_v2/controller_v2]

Instances: 12 dev instances chosen by a fixed rule (census D solved in 3-40 s,
first 12 by hash) plus 8 generated medium formulas (random 3-SAT, PHP).  Every
run uses a conflict limit of 1e5 ('-c'), so it stops at a deterministic point
and the statistics of v1/v2/upstream are comparable even when not solved.
Checks (v2 = build/fpc2, v1 = build/fpc, U = build/upstream):
  E  search equivalence: controller-off, telemetry-only, fixed NEGATIVE,
     frozen schedule sw10k_Crev (F- -> D @1e4) and a one-shot policy on a
     non-timing feature give identical search statistics (conflicts,
     decisions, propagations, restarts, rephased) and identical final digest
     and switch points under v1 and v2 (and equal to upstream where defined)
  R  record semantics on v2 logs (telemetry run and a repeat policy with
     1e3-conflict windows): schema 2; the first record of each stream has a
     null flip; the first record of each stream after a sample rebuild
     (compaction) has a null flip; a checkpoint and a window written at the
     same restart report the same pre-action action and identical state
     features; no record is written after an action within the same hook
  C  compactions were exercised (count of runs with compacts > 0)
"""

import argparse
import concurrent.futures as cf
import gzip
import json
import os
import random
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import fprun  # noqa: E402

B = {v: os.path.join(ROOT, "build", v, "cadical") for v in ("upstream", "fpc", "fpc2")}
STATS = ("conflicts", "decisions", "propagations", "restarts", "rephased")
POLICY = "fpc-policy 1\ntype oneshot\nprefix 1000\nthreshold 0.5\nmodel tree ( c_glue_mean 8 L 0.9 0.1 )\n"
REPEAT = "fpc-policy 1\ntype repeat\nenter 0.5\nexit 0.5\nmodel tree ( w_glue_mean 6 R 0 ( r_stable 0.5 L 1 0 ) )\n"
STATE_FEATURES = ("x_saved_neg_frac", "x_target_set_frac", "x_target_neg_frac", "x_glue_fast", "x_best_frac",
                  "r_log_conflicts", "r_stable", "r_action", "r_switches", "c_glue_mean")


LIMIT = 100000  # conflict limit: every run stops at a deterministic point


def run(binary, args, cnf, env=None, timeout=600):
    e = dict(os.environ)
    e.update(env or {})
    try:
        p = subprocess.run([binary, "-c", str(LIMIT)] + args + [cnf], capture_output=True, text=True, env=e,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return "wall-timeout", {}
    st = {}
    for line in p.stdout.splitlines():
        m = re.match(r"c (\w+):\s+(\d+)", line)
        if m and m.group(1) in STATS and m.group(1) not in st:
            st[m.group(1)] = int(m.group(2))
    return p.returncode, st


def tel(path):
    return [json.loads(l) for l in open(path)]


def one(task):
    name, cnf, work = task
    out = {"instance": name, "E": [], "R": [], "compacts": None}
    pol = os.path.join(work, "pol.txt")
    rpol = os.path.join(work, "rep.txt")
    open(pol, "w").write(POLICY)
    open(rpol, "w").write(REPEAT)
    cases = {
        "off": (["--fpc=0"], ["--fpc=0"], [], None),
        "telemetry": (["--fpc=1"], ["--fpc=1"], [], None),
        "fixed_neg": (["--fpc=2", "--fpcinit=1"], ["--fpc=2", "--fpcinit=1"],
                      ["--forcephase=1", "--phase=0"], None),
        "sw10k_Crev": (["--fpc=3", "--fpcat=10000", "--fpcinit=1"],) * 2 + ([], None),
        "oneshot": (["--fpc=4"], ["--fpc=4"], [], pol),
    }
    for case, (a1, a2, au, policy) in cases.items():
        logs = {}
        res = {}
        for v, args in (("fpc", a1), ("fpc2", a2)):
            lg = os.path.join(work, f"{case}_{v}.jsonl")
            env = {"FPC_LOG": lg}
            if policy:
                env["FPC_POLICY"] = policy
            res[v] = run(B[v], args, cnf, env)
            logs[v] = tel(lg) if os.path.exists(lg) and args[0] != "--fpc=0" else []
        same = res["fpc"] == res["fpc2"]
        if logs["fpc"] and logs["fpc2"]:
            f1 = [r for r in logs["fpc"] if r["type"] == "final"]
            f2 = [r for r in logs["fpc2"] if r["type"] == "final"]
            s1 = [r["conflicts"] for r in logs["fpc"] if r["type"] == "switch"]
            s2 = [r["conflicts"] for r in logs["fpc2"] if r["type"] == "switch"]
            same = same and f1 and f2 and f1[0]["digest"] == f2[0]["digest"] and s1 == s2
        if case in ("off", "telemetry", "fixed_neg"):
            ru = run(B["upstream"], au, cnf)
            same = same and ru == res["fpc2"]
        out["E"].append({"case": case, "ok": bool(same), "v1": res["fpc"], "v2": res["fpc2"]})
    # record semantics on v2 logs
    for case, args, env in (("telemetry_w1000", ["--fpc=1", "--fpcwin=1000"], {}),
                            ("repeat_w1000", ["--fpc=4", "--fpcwin=1000"], {"FPC_POLICY": rpol})):
        lg = os.path.join(work, f"R_{case}.jsonl")
        rc, _ = run(B["fpc2"], args, cnf, dict(env, FPC_LOG=lg))
        if rc == "wall-timeout" or not os.path.exists(lg):
            out["R"].append({"case": case, "same_hook_pairs": 0, "epochs": None, "problems": ["run failed"]})
            continue
        L = tel(lg)
        probs = []
        if L[0].get("schema") != 2 or L[0].get("controller") != "v2":
            probs.append("schema")
        seen = {"checkpoint": None, "window": None}
        for r in L:
            if r["type"] in seen:
                fl = r["f"]["x_saved_flip_frac"]
                if seen[r["type"]] != r["sample_epoch"] and fl is not None:
                    probs.append(f"{r['type']} flip not null at first record of epoch {r['sample_epoch']}")
                seen[r["type"]] = r["sample_epoch"]
        cps = {r["conflicts"]: r for r in L if r["type"] == "checkpoint"}
        pairs = 0
        for w in (r for r in L if r["type"] == "window"):
            c = cps.get(w["conflicts"])
            if c is None:
                continue
            pairs += 1
            if c["action"] != w["action"]:
                probs.append("same-hook action differs")
            for k in STATE_FEATURES:
                if c["f"].get(k) != w["f"].get(k):
                    probs.append(f"same-hook feature {k} differs")
        # a switch must not be followed by a record of the same hook (records precede actions)
        for i, r in enumerate(L[:-1]):
            if r["type"] == "switch" and r.get("reason") != "init" and L[i + 1]["type"] in ("checkpoint", "window") \
                    and L[i + 1]["conflicts"] == r["conflicts"]:
                probs.append("record written after action in same hook")
        fin = [r for r in L if r["type"] == "final"]
        out["compacts"] = max(out["compacts"] or 0, fin[0]["compacts"] if fin else 0)
        out["R"].append({"case": case, "same_hook_pairs": pairs, "epochs": fin[0]["sample_epoch"] if fin else None,
                         "problems": sorted(set(probs))})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=32)
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "audit_v2", "controller_v2"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    import csv
    rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "results", "m2_census", "runs.csv")))
            if r["config"] == "D" and r["status"] == "solved" and 3 <= float(r["cpu"]) <= 40]
    picks = sorted(r["instance"] for r in rows)[:12]
    work = tempfile.mkdtemp(prefix="v2test_", dir=os.environ.get("FP_TMP"))
    tasks = [(h[:12], fprun.stage_cnf(h, "orig", 0), tempfile.mkdtemp(dir=work)) for h in picks]
    rng = random.Random(7)
    for i in range(6):
        n = rng.choice([180, 200, 220])
        cnf = os.path.join(work, f"r3_{i}.cnf")
        with open(cnf, "w") as f:
            m = int(4.26 * n)
            f.write(f"p cnf {n} {m}\n")
            for _ in range(m):
                vs = rng.sample(range(1, n + 1), 3)
                f.write(" ".join(str(v if rng.random() < .5 else -v) for v in vs) + " 0\n")
        tasks.append((f"r3_{i}", cnf, tempfile.mkdtemp(dir=work)))
    for h in (7, 8):
        cnf = os.path.join(work, f"php{h}.cnf")
        var = lambda p, q: p * h + q + 1
        cls = [[var(p, q) for q in range(h)] for p in range(h + 1)]
        cls += [[-var(p, q), -var(r, q)] for q in range(h) for p in range(h + 1) for r in range(p + 1, h + 1)]
        with open(cnf, "w") as f:
            f.write(f"p cnf {(h + 1) * h} {len(cls)}\n" + "".join(" ".join(map(str, c)) + " 0\n" for c in cls))
        tasks.append((f"php{h}", cnf, tempfile.mkdtemp(dir=work)))
    with cf.ProcessPoolExecutor(a.jobs) as ex:
        res = list(ex.map(one, tasks))
    e_fail = [(r["instance"], e["case"]) for r in res for e in r["E"] if not e["ok"]]
    r_fail = [(r["instance"], x["case"], x["problems"]) for r in res for x in r["R"] if x["problems"]]
    summary = {"instances": len(res), "equivalence_checks": sum(len(r["E"]) for r in res),
               "equivalence_failures": e_fail, "record_checks": sum(len(r["R"]) for r in res),
               "record_failures": r_fail,
               "runs_with_compaction": sum(1 for r in res if (r["compacts"] or 0) > 0),
               "same_hook_pairs": sum(x["same_hook_pairs"] for r in res for x in r["R"]),
               "max_sample_epochs": max((x["epochs"] or 0) for r in res for x in r["R"]),
               "details": res}
    json.dump(summary, open(os.path.join(a.out, "report.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "details"}, indent=1))
    return 1 if e_fail or r_fail else 0


if __name__ == "__main__":
    sys.exit(main())
