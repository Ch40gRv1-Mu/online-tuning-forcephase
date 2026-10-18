#!/usr/bin/env python3
"""M0 correctness and semantics suite for online-tuning-forcephase.

Usage: tests/m0_suite.py [--out DIR] [--jobs N] [--quick]

Checks (stdlib only; binaries from build/):
  A  answers of every configuration on small random/structured CNFs agree
     with an independent Python DPLL (itself validated by enumeration);
     every SAT model is checked with tools/checkmodel against the CNF and
     every UNSAT answer with an LRAT proof checked by lrat-trim;
     run with the assertion-checking builds (upstream-check, fpc-check)
  B  switching stress: schedule/random/repeat controllers switching at
     every restart on medium instances, both tracks, with proofs
  C  determinism/equivalence: upstream == fpc-off == telemetry (search
     statistics), CLI configurations == fixed controller actions
  D  replay: checkpoint digest of a telemetry run equals the digest of a
     schedule run at its switch point; repeated runs are identical
  E  edge cases: empty formula, empty clause, root conflict, lucky-solved
  F  option truth table via decision counters (sign and phase source)
  G  rephase interaction when returning from forcing (natural vs fpcrlim)
Writes a JSON report and a text summary to --out.
"""

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = lambda v: os.path.join(ROOT, "build", v, "cadical")
LRAT = os.path.join(ROOT, "build", "tools", "lrat-trim")
CHECKMODEL = os.path.join(ROOT, "build", "tools", "checkmodel")

# Static configurations (CLI) and controller configurations.
CLI = {
    "D": ["--phase=1", "--forcephase=0"],
    "Iminus": ["--phase=0", "--forcephase=0"],
    "Fminus": ["--phase=0", "--forcephase=1"],
    "Fplus": ["--phase=1", "--forcephase=1"],
    "bare_forcephase": ["--forcephase"],
    "D_noR": ["--phase=1", "--forcephase=0", "--rephase=0"],
    "Iminus_noR": ["--phase=0", "--forcephase=0", "--rephase=0"],
    "S_saved": ["--phase=0", "--target=0", "--rephase=0", "--stubbornIOfocused=0"],
}
CTRL = {
    "tel": ["--fpc=1", "--fpcwin=1"],
    "fixC_neg": ["--fpc=2", "--fpcinit=1"],
    "fixP_neg": ["--fpc=2", "--fpcinit=1", "--fpctrack=1"],
    "fixC_initneg": ["--fpc=2", "--fpca0=2"],
    "fixC_pos": ["--fpc=2", "--fpca0=3"],
    "schedC_every": ["--fpc=3", "--fpcat=1", "--fpcperiod=1"],
    "schedP_every": ["--fpc=3", "--fpcat=1", "--fpcperiod=1", "--fpctrack=1"],
    "schedC_every_rlim": ["--fpc=3", "--fpcat=1", "--fpcperiod=1", "--fpcrlim=1"],
    "schedC_initneg_every": ["--fpc=3", "--fpcat=1", "--fpcperiod=1", "--fpca0=2"],
    "randC": ["--fpc=5", "--fpcwin=1", "--fpcprob=500", "--fpcseed=7"],
    "randP": ["--fpc=5", "--fpcwin=1", "--fpcprob=500", "--fpcseed=7", "--fpctrack=1"],
    "policy_repeat": ["--fpc=4", "--fpcwin=1"],
}
POLICY_REPEAT = """fpc-policy 1
type repeat
enter 0.5
exit 0.5
model tree ( w_glue_mean 6 R 0 ( r_stable 0.5 L 1 0 ) )
"""


# ---------------------------------------------------------------- formulas

def write_cnf(path, n, clauses):
    with open(path, "w") as f:
        f.write(f"p cnf {n} {len(clauses)}\n")
        for c in clauses:
            f.write(" ".join(map(str, c)) + " 0\n")


def random_ksat(rng, n, m, k):
    cls = []
    for _ in range(m):
        vs = rng.sample(range(1, n + 1), min(k, n))
        cls.append([v if rng.random() < 0.5 else -v for v in vs])
    return cls


def php(holes):
    pig = holes + 1
    var = lambda p, h: p * holes + h + 1
    cls = [[var(p, h) for h in range(holes)] for p in range(pig)]
    for h in range(holes):
        for p in range(pig):
            for q in range(p + 1, pig):
                cls.append([-var(p, h), -var(q, h)])
    return pig * holes, cls


def coloring(rng, nodes, edges_p, colors):
    var = lambda v, c: v * colors + c + 1
    cls = [[var(v, c) for c in range(colors)] for v in range(nodes)]
    for v in range(nodes):
        for c in range(colors):
            for d in range(c + 1, colors):
                cls.append([-var(v, c), -var(v, d)])
    for u in range(nodes):
        for v in range(u + 1, nodes):
            if rng.random() < edges_p:
                for c in range(colors):
                    cls.append([-var(u, c), -var(v, c)])
    return nodes * colors, cls


# ------------------------------------------------- independent reference

def dpll(n, clauses):
    """Plain recursive DPLL with unit propagation; returns True iff SAT."""
    def simplify(cls, lit):
        out = []
        for c in cls:
            if lit in c:
                continue
            if -lit in c:
                c = [x for x in c if x != -lit]
                if not c:
                    return None
            out.append(c)
        return out

    def rec(cls):
        while True:
            unit = next((c[0] for c in cls if len(c) == 1), None)
            if unit is None:
                break
            cls = simplify(cls, unit)
            if cls is None:
                return False
        if not cls:
            return True
        lit = cls[0][0]
        for l in (lit, -lit):
            s = simplify(cls, l)
            if s is not None and rec(s):
                return True
        return False

    if any(len(c) == 0 for c in clauses):
        return False
    return rec([list(c) for c in clauses])


def enumerate_sat(n, clauses):
    for a in range(1 << n):
        if all(any((l > 0) == bool(a >> (abs(l) - 1) & 1) for l in c) for c in clauses):
            return True
    return False


# ----------------------------------------------------------------- running

STAT_KEYS = ["conflicts", "decisions", "propagations", "restarts", "rephased",
             "reused", "stabilizing", "learned", "eliminated", "subsumed"]


def run_solver(binary, args, cnf, proof=None, env_extra=None, timeout=600):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    cmd = [binary] + args + [cnf] + ([proof] if proof else [])
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    stats = {}
    status = None
    for line in p.stdout.splitlines():
        if line.startswith("s "):
            status = line[2:].strip()
        m = re.match(r"c (\w+):\s+(\d+)", line)
        if m and m.group(1) in STAT_KEYS:
            stats[m.group(1)] = int(m.group(2))
    return {"code": p.returncode, "status": status, "stats": stats,
            "stdout": p.stdout, "stderr": p.stderr}


def verify(cnf, out_text, code, proof, workdir):
    """Return 'model-ok', 'proof-ok' or a failure string."""
    if code == 10:
        path = os.path.join(workdir, "out.txt")
        with open(path, "w") as f:
            f.write(out_text)
        r = subprocess.run([CHECKMODEL, cnf, path], capture_output=True, text=True)
        return "model-ok" if r.returncode == 0 else "MODEL-FAIL " + r.stdout.strip()
    if code == 20:
        r = subprocess.run([LRAT, "-q", cnf, proof], capture_output=True, text=True)
        return "proof-ok" if r.returncode == 20 else f"PROOF-FAIL rc={r.returncode} {r.stdout[-200:]} {r.stderr[-200:]}"
    return f"NO-ANSWER code={code}"


def job_answer(task):
    """Run one configuration on one formula with proof and verification."""
    name, binary, args, cnf, expected, env_extra = task
    with tempfile.TemporaryDirectory(dir=os.environ.get("FP_TMP")) as d:
        proof = os.path.join(d, "proof.lrat")
        r = run_solver(binary, ["--lrat=1"] + args, cnf, proof, env_extra)
        v = verify(cnf, r["stdout"], r["code"], proof, d)
    got = {10: True, 20: False}.get(r["code"])
    ok = (got is not None and (expected is None or got == expected)
          and v in ("model-ok", "proof-ok"))
    return {"name": name, "cnf": os.path.basename(cnf), "code": r["code"],
            "expected": expected, "verify": v, "ok": ok,
            "stderr": r["stderr"][-300:] if not ok else ""}


TIMING_FEATURES = ("r_time", "c_conf_per_sec", "w_conf_per_sec")


def strip_timing(f):
    return {k: v for k, v in f.items() if k not in TIMING_FEATURES}


def parse_jsonl(path):
    out = []
    with open(path) as f:
        for line in f:
            out.append(json.loads(line))
    return out


# ------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "m0"))
    ap.add_argument("--jobs", type=int, default=min(32, os.cpu_count() or 4))
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="m0_", dir=os.environ.get("FP_TMP"))
    policy_path = os.path.join(work, "policy_repeat.txt")
    with open(policy_path, "w") as f:
        f.write(POLICY_REPEAT)
    penv = {"FPC_POLICY": policy_path}
    rng = random.Random(20261018)
    report = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "checks": {}}
    t0 = time.time()

    # ---------------- A: small formulas vs independent DPLL
    small = []
    n_rand = 60 if a.quick else 240
    for i in range(n_rand):
        n = rng.randint(3, 16)
        k = rng.choice([2, 3, 3, 3, 4])
        ratio = {2: rng.uniform(0.5, 2.0), 3: rng.uniform(2.5, 6.0), 4: rng.uniform(6, 13)}[k]
        m = max(1, int(ratio * n))
        cls = random_ksat(rng, n, m, k)
        small.append((f"rand{i}_n{n}_k{k}", n, cls))
    for h in (2, 3, 4, 5):
        n, cls = php(h)
        small.append((f"php{h}", n, cls))
    for i in range(10):
        n, cls = coloring(rng, rng.randint(4, 6), 0.6, 3)
        small.append((f"col{i}", n, cls))
    small.append(("empty_formula", 0, []))
    small.append(("empty_clause", 2, [[1, 2], []]))
    small.append(("root_conflict", 2, [[1], [-1, 2], [-2]]))
    small.append(("unit_sat", 3, [[1], [-2], [3]]))
    small.append(("all_negative_sat", 8, [[-i for i in range(1, 9)]] + [[-i, -j] for i in range(1, 5) for j in range(5, 9)]))
    small_files = []
    enum_mismatch = []
    for name, n, cls in small:
        path = os.path.join(work, name + ".cnf")
        write_cnf(path, n, cls)
        exp = dpll(n, cls)
        if n <= 12:
            if enumerate_sat(n, cls) != exp:
                enum_mismatch.append(name)
        small_files.append((path, exp))
    report["checks"]["A_reference_validation"] = {
        "formulas": len(small), "dpll_vs_enumeration_mismatches": enum_mismatch,
        "sat": sum(e for _, e in small_files), "unsat": sum(not e for _, e in small_files)}

    tasks = []
    for path, exp in small_files:
        for build in ("upstream-check", "fpc-check"):
            for cname, args in CLI.items():
                tasks.append((f"{build}:{cname}", B(build), args, path, exp, None))
        for cname, args in CTRL.items():
            env = penv if cname == "policy_repeat" else None
            tasks.append((f"fpc-check:{cname}", B("fpc-check"), args, path, exp, env))
    with cf.ProcessPoolExecutor(a.jobs) as ex:
        resA = list(ex.map(job_answer, tasks, chunksize=8))
    failsA = [r for r in resA if not r["ok"]]
    report["checks"]["A_small_vs_reference"] = {
        "runs": len(resA), "failures": failsA[:50], "num_failures": len(failsA),
        "verified_models": sum(r["verify"] == "model-ok" for r in resA),
        "verified_proofs": sum(r["verify"] == "proof-ok" for r in resA)}
    print(f"[A] {len(resA)} runs, {len(failsA)} failures ({time.time()-t0:.0f}s)", flush=True)

    # ---------------- B: switching stress on medium formulas (answers must
    # agree across all configurations and be verified)
    medium = []
    n_med = 6 if a.quick else 16
    for i in range(n_med):
        n = rng.choice([120, 150, 180, 200])
        cls = random_ksat(rng, n, int(4.26 * n), 3)
        medium.append((f"med_r3_{i}_n{n}", n, cls))
    for h in (7, 8):
        n, cls = php(h)
        medium.append((f"med_php{h}", n, cls))
    for i in range(4):
        n, cls = coloring(rng, 40, 0.18, 4)
        medium.append((f"med_col{i}", n, cls))
    med_files = []
    for name, n, cls in medium:
        path = os.path.join(work, name + ".cnf")
        write_cnf(path, n, cls)
        med_files.append(path)
    tasks = []
    for path in med_files:
        for cname, args in list(CLI.items())[:4]:
            tasks.append((f"fpc-check:{cname}", B("fpc-check"), args, path, None, None))
        for cname, args in CTRL.items():
            env = penv if cname == "policy_repeat" else None
            tasks.append((f"fpc-check:{cname}", B("fpc-check"), args, path, None, env))
    with cf.ProcessPoolExecutor(a.jobs) as ex:
        resB = list(ex.map(job_answer, tasks))
    by_cnf = {}
    for r in resB:
        by_cnf.setdefault(r["cnf"], set()).add(r["code"])
    disagreements = {k: sorted(v) for k, v in by_cnf.items() if len(v - {0}) > 1}
    failsB = [r for r in resB if not r["ok"]]
    report["checks"]["B_switching_stress"] = {
        "runs": len(resB), "failures": failsB[:50], "num_failures": len(failsB),
        "answer_disagreements": disagreements}
    print(f"[B] {len(resB)} runs, {len(failsB)} failures, {len(disagreements)} disagreements ({time.time()-t0:.0f}s)", flush=True)

    # switch counts actually happened (from telemetry of a release build)
    sw = {}
    for path in med_files[:4]:
        for cname in ("schedC_every", "schedP_every", "randC", "policy_repeat"):
            log = os.path.join(work, f"sw_{cname}.jsonl")
            env = {"FPC_LOG": log}
            if cname == "policy_repeat":
                env.update(penv)
            run_solver(B("fpc"), CTRL[cname], path, env_extra=env)
            fin = [x for x in parse_jsonl(log) if x["type"] == "final"]
            if fin:
                f = fin[0]
                sw.setdefault(cname, []).append({
                    "cnf": os.path.basename(path), "switches": f["switches"],
                    "occ_conflicts": f["occ_conflicts"], "dec_p_override": f["dec_p_override"],
                    "dec_neg_frac": f["dec_neg"] / max(1, f["dec_free"])})
    report["checks"]["B_switch_counts"] = sw

    # ---------------- C: determinism / equivalence of search statistics
    eq_files = med_files[:]  # medium formulas: thousands of conflicts
    pairs = [
        ("upstream:D", B("upstream"), CLI["D"], "fpc:off", B("fpc"), CLI["D"]),
        ("upstream:D", B("upstream"), CLI["D"], "fpc:tel", B("fpc"), ["--fpc=1", "--fpcwin=100"]),
        ("upstream:Fminus", B("upstream"), CLI["Fminus"], "fpc:fixC_neg", B("fpc"), CTRL["fixC_neg"]),
        ("upstream:Iminus", B("upstream"), CLI["Iminus"], "fpc:fixC_initneg", B("fpc"), CTRL["fixC_initneg"]),
        ("upstream:Fplus", B("upstream"), CLI["Fplus"], "fpc:fixC_pos", B("fpc"), CTRL["fixC_pos"]),
        ("upstream:Fminus", B("upstream"), CLI["Fminus"], "fpc:tel+Fminus", B("fpc"), CLI["Fminus"] + ["--fpc=1"]),
        ("upstream:D+lrat", B("upstream"), CLI["D"] + ["--lrat=1"], "fpc:tel+lrat", B("fpc"), ["--fpc=1", "--lrat=1"]),
    ]
    resC = []
    for path in eq_files:
        for (n1, b1, a1, n2, b2, a2) in pairs:
            env = {"FPC_LOG": os.path.join(work, "c.jsonl")}
            proof = os.path.join(work, "c.proof") if "lrat" in n1 else None
            r1 = run_solver(b1, a1, path, proof)
            r2 = run_solver(b2, a2, path, proof, env)
            resC.append({"cnf": os.path.basename(path), "a": n1, "b": n2,
                         "same": r1["stats"] == r2["stats"] and r1["status"] == r2["status"],
                         "stats_a": r1["stats"], "stats_b": r2["stats"]})
    failsC = [r for r in resC if not r["same"]]
    report["checks"]["C_equivalence"] = {"comparisons": len(resC), "num_failures": len(failsC), "failures": failsC[:20]}
    print(f"[C] {len(resC)} comparisons, {len(failsC)} differ ({time.time()-t0:.0f}s)", flush=True)

    # ---------------- D: replay digests
    resD = []
    for path in med_files:
        tel = os.path.join(work, "d_tel.jsonl")
        run_solver(B("fpc"), ["--fpc=1"], path, env_extra={"FPC_LOG": tel})
        cps = {x["crossed"][1]: x for x in parse_jsonl(tel) if x["type"] == "checkpoint"}
        for K in (1000, 5000, 10000):
            if K not in cps:
                continue
            for track in ("0", "1"):
                logs = []
                for rep in range(2):
                    lg = os.path.join(work, f"d_s{rep}.jsonl")
                    run_solver(B("fpc"), ["--fpc=3", f"--fpcat={K}", f"--fpctrack={track}"], path,
                               env_extra={"FPC_LOG": lg})
                    logs.append(parse_jsonl(lg))
                cp = [x for x in logs[0] if x["type"] == "checkpoint" and x["crossed"][1] == K]
                swr = [x for x in logs[0] if x["type"] == "switch"]
                fin = [[x for x in L if x["type"] == "final"] for L in logs]
                same_prefix = bool(cp) and cp[0]["digest"] == cps[K]["digest"]
                switch_at_cp = bool(swr) and bool(cp) and swr[0]["conflicts"] == cp[0]["conflicts"]
                repeat_identical = (fin[0] and fin[1] and fin[0][0]["digest"] == fin[1][0]["digest"]
                                    and fin[0][0]["conflicts"] == fin[1][0]["conflicts"])
                resD.append({"cnf": os.path.basename(path), "K": K, "track": track,
                             "prefix_digest_equal": same_prefix, "switch_at_checkpoint": switch_at_cp,
                             "repeat_identical": bool(repeat_identical),
                             "nontiming_features_equal": bool(cp) and strip_timing(cp[0]["f"]) == strip_timing(cps[K]["f"]),
                             "ok": same_prefix and switch_at_cp and bool(repeat_identical)
                                   and bool(cp) and strip_timing(cp[0]["f"]) == strip_timing(cps[K]["f"])})
    failsD = [r for r in resD if not r["ok"]]
    # features equal except timing-derived ones
    report["checks"]["D_replay"] = {"cases": len(resD), "num_failures": len(failsD), "failures": failsD[:20],
                                    "nontiming_features_equal": sum(r["nontiming_features_equal"] for r in resD)}
    print(f"[D] {len(resD)} replay cases, {len(failsD)} failures ({time.time()-t0:.0f}s)", flush=True)

    # ---------------- F: option truth table via decision counters
    resF = []
    for path in med_files[:6]:
        for cname, args in [("D", CLI["D"]), ("Iminus", CLI["Iminus"]), ("Fminus", CLI["Fminus"]),
                            ("Fplus", CLI["Fplus"]), ("bare_forcephase", CLI["bare_forcephase"]),
                            ("S_saved", CLI["S_saved"]), ("fixP_neg", CTRL["fixP_neg"]),
                            ("fixC_neg", CTRL["fixC_neg"])]:
            lg = os.path.join(work, "f.jsonl")
            extra = ["--fpc=1"] if not any(x.startswith("--fpc=") for x in args) else []
            run_solver(B("fpc"), args + extra, path, env_extra={"FPC_LOG": lg})
            fin = [x for x in parse_jsonl(lg) if x["type"] == "final"][0]
            src = dict(zip(["force_saved", "api", "forcephase", "target", "saved", "stubborn", "fallback"], fin["dec_src"]))
            free = max(1, fin["dec_free"])
            negf = fin["dec_neg"] / free
            if cname in ("Fminus", "fixC_neg"):
                ok = fin["dec_neg"] == fin["dec_free"] and src["forcephase"] == fin["dec_free"] and fin["rephased"] == 0
            elif cname in ("Fplus", "bare_forcephase"):
                ok = fin["dec_neg"] == 0 and src["forcephase"] == fin["dec_free"] and fin["rephased"] == 0
            elif cname == "fixP_neg":
                ok = fin["dec_neg"] == fin["dec_free"] and fin["dec_p_override"] == fin["dec_free"] and src["forcephase"] == 0
            elif cname == "S_saved":
                ok = src["target"] == 0 and src["forcephase"] == 0 and src["saved"] + src["fallback"] == fin["dec_free"] and fin["rephased"] == 0
            else:
                ok = src["forcephase"] == 0 and src["saved"] + src["target"] + src["fallback"] == fin["dec_free"]
            resF.append({"cnf": os.path.basename(path), "config": cname, "neg_frac": round(negf, 4),
                         "src": src, "rephased": fin["rephased"], "p_override": fin["dec_p_override"],
                         "p_flip": fin["dec_p_flip"], "ok": ok})
    failsF = [r for r in resF if not r["ok"]]
    report["checks"]["F_truth_table"] = {"cases": len(resF), "num_failures": len(failsF), "rows": resF}
    print(f"[F] {len(resF)} truth-table cases, {len(failsF)} failures ({time.time()-t0:.0f}s)", flush=True)

    # ---------------- G: rephase when returning from forcing
    resG = []
    for path in med_files[:8]:
        for rlim in (0, 1):
            lg = os.path.join(work, "g.jsonl")
            run_solver(B("fpc"), ["--fpc=3", "--fpcat=2000", "--fpcperiod=4000", f"--fpcrlim={rlim}", "--fpcwin=100"],
                       path, env_extra={"FPC_LOG": lg})
            L = parse_jsonl(lg)
            switches = [x for x in L if x["type"] == "switch"]
            backs = [x for x in switches if x["action"] == "NATIVE"]
            wins = [x for x in L if x["type"] == "window"]
            # rephases in the first window after returning to native
            after = []
            for s in backs:
                nxt = [w for w in wins if w["conflicts"] > s["conflicts"]][:1]
                after.append(nxt[0]["f"]["w_rephases"] if nxt else None)
            resG.append({"cnf": os.path.basename(path), "rlim": rlim, "switches": len(switches),
                         "returns": len(backs),
                         "overdue_at_return": sum(1 for s in backs if s["rephase_lim"] < s["conflicts"] and rlim == 0),
                         "postponed": sum(1 for s in backs if s["rephase_postponed_from"] >= 0),
                         "rephases_in_window_after_return": after})
    report["checks"]["G_rephase_on_return"] = resG
    print(f"[G] done ({time.time()-t0:.0f}s)", flush=True)

    # ---------------- API priority test (compiled separately)
    api = os.path.join(ROOT, "build", "api_phase_test")
    if os.path.exists(api):
        r = subprocess.run([api], capture_output=True, text=True)
        report["checks"]["API_phase_priority"] = {"rc": r.returncode, "output": r.stdout.splitlines()}
    report["elapsed_s"] = round(time.time() - t0, 1)
    for v in ("upstream", "fpc", "upstream-check", "fpc-check", "tools"):
        p = os.path.join(ROOT, "build", v, "BUILDINFO")
        if os.path.exists(p):
            report.setdefault("builds", {})[v] = open(p).read().splitlines()
    total_fail = (len(failsA) + len(failsB) + len(disagreements) + len(failsC) + len(failsD) + len(failsF)
                  + len(enum_mismatch) + (report["checks"].get("API_phase_priority", {}).get("rc", 0) != 0))
    report["total_failures"] = total_fail
    with open(os.path.join(a.out, "m0_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(f"total failures: {total_fail}; report: {os.path.join(a.out, 'm0_report.json')}")
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
