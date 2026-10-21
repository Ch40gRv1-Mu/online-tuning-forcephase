"""Correctness of the LPN -> SAT reductions on tiny instances.

For every (encoding, kind, size, seed): brute-force the LPN question (all e
with wt(e) <= t; for the explicit sparse-secret encoding all s with
wt(s) <= k), solve the CNF with CaDiCaL under D and F-, and require
  - SAT/UNSAT agrees with brute force,
  - SAT models decode to an e that passes the independent LPN check,
  - UNSAT answers carry an LRAT proof accepted by lrat-check,
  - H is a valid parity-check matrix (H A = 0, rank m - rank A).
Usage: python3 test_reduction.py
"""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fplib  # noqa: E402
import lpn_gen as L  # noqa: E402

OUT = fplib.FP_WORK / "lpn-test"
OUT.mkdir(parents=True, exist_ok=True)


def brute(A, y, n, m, t):
    for k in range(t + 1):
        for pos in itertools.combinations(range(m), k):
            e = sum(1 << i for i in pos)
            if L.in_colspace(A, n, m, y ^ e):
                return True
    return False


fails, runs, n_sat, n_unsat = [], 0, 0, 0
for (n, m, t) in [(4, 10, 1), (5, 12, 2), (6, 14, 2), (7, 14, 3)]:
    for kind in ("planted", "random"):
        for seed in range(8):
            A, y, s, e = L.sample(n, m, t, kind, seed)
            H = L.parity_check(A, n, m)
            cols = L.columns(A, n, m)
            rank = len(L.rref(cols)[0])
            if any(L.parity(h & c) for h in H for c in cols) or len(H) != m - rank:
                fails.append(("bad H", n, m, kind, seed))
            truth = brute(A, y, n, m, t)
            if kind == "planted" and not truth:
                fails.append(("planted not SAT", n, m, seed))
            for enc in L.ENCODINGS:
                f = L.encode(A, y, n, m, t, enc)
                cnf = OUT / f"{enc}-{n}-{m}-{t}-{kind}-{seed}.cnf"
                fplib.write_dimacs(cnf, f.nv, f.cls)
                meta = {"n": n, "m": m, "t": t, "enc": enc, "A": A, "y": y}
                for cfg in ("D", "Fm"):
                    proof = cnf.with_suffix(f".{cfg}.lrat")
                    r = fplib.run_solver(cnf, cfg, ["--lrat", "--binary=false"], proof=proof, timeout=60)
                    runs += 1
                    got = r["status"]
                    if got == "SAT":
                        n_sat += 1
                        ok, _ = L.check_semantics(meta, fplib.parse_witness(r["_stdout"]))
                        if not (truth and ok and fplib.check_model(cnf, fplib.parse_witness(r["_stdout"]))):
                            fails.append(("SAT wrong", enc, n, m, kind, seed, cfg, truth, ok))
                    elif got == "UNSAT":
                        n_unsat += 1
                        chk = fplib.lrat_check(cnf, proof)
                        if truth or chk != "VERIFIED":
                            fails.append(("UNSAT wrong", enc, n, m, kind, seed, cfg, truth, chk))
                    else:
                        fails.append(("no answer", enc, n, m, kind, seed, cfg, got))
                    proof.unlink(missing_ok=True)


def brute_explicit(A, y, n, m, t, k):
    for r in range(k + 1):
        for pos in itertools.combinations(range(n), r):
            sv = sum(1 << j for j in pos)
            if sum(L.parity(A[i] & sv) ^ (y >> i & 1) for i in range(m)) <= t:
                return True
    return False


# Sparse-secret family (planted s of weight k): implicit / explicit / implicitflip.
for (n, m, t, k) in [(5, 12, 2, 1), (6, 15, 2, 1), (7, 18, 3, 2), (8, 21, 3, 2)]:
    for kind in ("planted", "random"):
        for seed in range(8):
            A, y, s, e = L.sample(n, m, t, kind, seed, k)
            if kind == "planted" and (s.bit_count() != k or e.bit_count() != t):
                fails.append(("bad planted weights", n, m, seed))
            truth_imp = brute(A, y, n, m, t)
            truth_exp = brute_explicit(A, y, n, m, t, k)
            if kind == "planted" and not (truth_imp and truth_exp):
                fails.append(("planted not SAT", n, m, seed))
            for enc in L.SPARSE_ENCODINGS:
                truth = truth_exp if enc == "explicit" else truth_imp
                f = L.encode(A, y, n, m, t, enc, k)
                cnf = OUT / f"{enc}-{n}-{m}-{t}-k{k}-{kind}-{seed}.cnf"
                fplib.write_dimacs(cnf, f.nv, f.cls)
                meta = {"n": n, "m": m, "t": t, "k": k, "enc": enc, "A": A, "y": y}
                for cfg in ("D", "Fm"):
                    proof = cnf.with_suffix(f".{cfg}.lrat")
                    r = fplib.run_solver(cnf, cfg, ["--lrat", "--binary=false"], proof=proof, timeout=60)
                    runs += 1
                    got = r["status"]
                    if got == "SAT":
                        n_sat += 1
                        w = fplib.parse_witness(r["_stdout"])
                        ok, _ = L.check_semantics(meta, w)
                        if not (truth and ok and fplib.check_model(cnf, w)):
                            fails.append(("SAT wrong", enc, n, m, kind, seed, cfg, truth, ok))
                    elif got == "UNSAT":
                        n_unsat += 1
                        chk = fplib.lrat_check(cnf, proof)
                        if truth or chk != "VERIFIED":
                            fails.append(("UNSAT wrong", enc, n, m, kind, seed, cfg, truth, chk))
                    else:
                        fails.append(("no answer", enc, n, m, kind, seed, cfg, got))
                    proof.unlink(missing_ok=True)

print(f"{runs} solver runs: {n_sat} SAT (models semantically checked), {n_unsat} UNSAT (LRAT checked)")
print("failures:", fails if fails else "none")
sys.exit(1 if fails else 0)
