"""LPN instance sampler and SAT reductions for the forcephase mechanism study.

An instance is (A, y) with A in GF(2)^{m x n}. "planted": y = A s + e with
wt(e) = w exactly; "random": y uniform. The SAT question is

    exists e in GF(2)^m with wt(e) <= t and y + e in colspace(A)

Encodings (variables e_1..e_m always come first):
  syndrome  He = Hy for a systematic parity-check matrix H of colspace(A)
  secret    e_i = y_i + <a_i, s> with explicit secret variables s
  flipe     syndrome encoding with every e_i literal negated (e' = not e),
            same logical problem, but the planted solution becomes dense
XOR constraints are cut into chunks of <= 4 variables with Tseitin auxiliaries;
wt(e) <= t uses Sinz's sequential counter.

Usage:
  python3 lpn_gen.py --grid sparse_main --manifest benchmarks/lpn_sparse_main.csv
"""

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fplib  # noqa: E402

LPN_DIR = fplib.FP_WORK / "lpn"
PLAIN = fplib.FP_WORK / "cnf-plain"
ENCODINGS = ("syndrome", "secret", "flipe")
# Sparse-secret family: planted s has weight exactly k (secret drawn like the
# noise, as after the Hermite-normal-form transform), so the "mostly 0"
# information lives in the solution, not (unless explicit) in the constraints.
#   implicit      secret encoding, wt(e) <= t only; s unconstrained
#   explicit      implicit + wt(s) <= k
#   implicitflip  implicit with every s literal negated (solution dense in s')
SPARSE_ENCODINGS = ("implicit", "explicit", "implicitflip")
SECRET_LIKE = ("secret", "implicit", "explicit", "implicitflip")


# ------------------------------------------------------------ GF(2) algebra
def parity(x):
    return x.bit_count() & 1


def rref(rows):
    """Reduced row echelon form of GF(2) row bitmasks; returns (rows, pivots)."""
    rows = [r for r in rows]
    piv, r = [], 0
    width = max((x.bit_length() for x in rows), default=0)
    for c in range(width):
        sel = next((i for i in range(r, len(rows)) if rows[i] >> c & 1), None)
        if sel is None:
            continue
        rows[r], rows[sel] = rows[sel], rows[r]
        for i in range(len(rows)):
            if i != r and rows[i] >> c & 1:
                rows[i] ^= rows[r]
        piv.append(c)
        r += 1
        if r == len(rows):
            break
    return rows[:r], piv


def columns(A, n, m):
    """Columns of A (m rows of n-bit ints) as m-bit ints."""
    return [sum(((A[i] >> j) & 1) << i for i in range(m)) for j in range(n)]


def parity_check(A, n, m):
    """Systematic basis of colspace(A)^perp as m-bit ints (H rows)."""
    R, piv = rref(columns(A, n, m))
    pivset = set(piv)
    H = []
    for f in range(m):
        if f in pivset:
            continue
        h = 1 << f
        for row, p in zip(R, piv):
            if row >> f & 1:
                h |= 1 << p
        H.append(h)
    return H


def in_colspace(A, n, m, v):
    R, piv = rref(columns(A, n, m))
    for row, p in zip(R, piv):
        if v >> p & 1:
            v ^= row
    return v == 0


def log2_expected_solutions(n, m, t, enc="syndrome", k=None):
    """log2 of the expected number of solutions for uniform y.
    syndrome-like: E[#e with wt<=t, y+e in C] for a rank-n code;
    explicit: E[#(s, e) with wt(s)<=k, wt(e)<=t]."""
    vol = lambda N, r: sum(math.comb(N, i) for i in range(r + 1))  # noqa: E731
    if enc == "explicit":
        return math.log2(vol(n, k)) + math.log2(vol(m, t)) - m
    return n - m + math.log2(vol(m, t))


# ------------------------------------------------------------------ sampling
def sample(n, m, w, kind, seed, k=None):
    """k=None: uniform secret (original family, unchanged stream);
    k given: planted secret of weight exactly k (sparse-secret family)."""
    tag = f"lpn:{n}:{m}:{w}:{kind}:{seed}" + ("" if k is None else f":k{k}")
    rng = random.Random(tag)
    A = [rng.getrandbits(n) for _ in range(m)]
    s = e = None
    if kind == "planted":
        s = rng.getrandbits(n) if k is None else sum(1 << j for j in rng.sample(range(n), k))
        e = sum(1 << i for i in rng.sample(range(m), w))
        y = sum((parity(A[i] & s) ^ (e >> i & 1)) << i for i in range(m))
    elif kind == "random":
        y = rng.getrandbits(m)
    else:
        raise ValueError(kind)
    return A, y, s, e


# --------------------------------------------------------------- CNF builder
class CNF:
    def __init__(self):
        self.nv, self.cls = 0, []

    def new(self):
        self.nv += 1
        return self.nv

    def xor(self, vs, rhs, cut=4):
        vs = list(vs)
        while len(vs) > cut:
            a = self.new()
            self._xor_small(vs[:cut - 1] + [a], 0)  # a = xor of the chunk
            vs = [a] + vs[cut - 1:]
        self._xor_small(vs, rhs)

    def _xor_small(self, vs, rhs):
        if not vs:
            if rhs:
                self.cls.append([])
            return
        for bits in range(1 << len(vs)):
            if bits.bit_count() % 2 != rhs:  # forbid every wrong-parity assignment
                self.cls.append([-v if bits >> i & 1 else v for i, v in enumerate(vs)])

    def at_most(self, xs, t):
        """Sinz sequential counter: sum(xs) <= t."""
        m = len(xs)
        if t >= m:
            return
        if t == 0:
            self.cls.extend([-x] for x in xs)
            return
        r = [[self.new() for _ in range(t)] for _ in range(m - 1)]
        self.cls.append([-xs[0], r[0][0]])
        self.cls.extend([-r[0][j]] for j in range(1, t))
        for i in range(1, m - 1):
            self.cls.append([-xs[i], r[i][0]])
            self.cls.append([-r[i - 1][0], r[i][0]])
            for j in range(1, t):
                self.cls.append([-xs[i], -r[i - 1][j - 1], r[i][j]])
                self.cls.append([-r[i - 1][j], r[i][j]])
            self.cls.append([-xs[i], -r[i - 1][t - 1]])
        self.cls.append([-xs[m - 1], -r[m - 2][t - 1]])


def encode(A, y, n, m, t, enc, k=None):
    f = CNF()
    E = [f.new() for _ in range(m)]  # e_i is variable i+1
    if enc in ("syndrome", "flipe"):
        for h in parity_check(A, n, m):
            f.xor([E[i] for i in range(m) if h >> i & 1], parity(h & y))
    elif enc in SECRET_LIKE:  # s_j is variable m+j+1
        S = [f.new() for _ in range(n)]
        for i in range(m):
            f.xor([E[i]] + [S[j] for j in range(n) if A[i] >> j & 1], y >> i & 1)
    else:
        raise ValueError(enc)
    f.at_most(E, t)
    if enc == "explicit":
        f.at_most(S, k)
    flip = set(E) if enc == "flipe" else (set(S) if enc == "implicitflip" else None)
    if flip:
        f.cls = [[-l if abs(l) in flip else l for l in c] for c in f.cls]
    return f


def decode_bits(model, first, count, flip=False):
    """Bits of variables first..first+count-1 as an int (bit i = var first+i)."""
    x = 0
    for i in range(count):
        bit = bool(model.get(first + i, False)) != flip
        x |= int(bit) << i
    return x


def check_semantics(meta, model):
    """Independent LPN check of a SAT model. Returns (ok, {"e", "s"}).
    syndrome/flipe: wt(e) <= t and y+e in colspace(A);
    secret-like: wt(e) <= t and A s = y + e (explicit: also wt(s) <= k)."""
    n, m, t, enc = meta["n"], meta["m"], meta["t"], meta["enc"]
    A, y = meta["A"], meta["y"]
    e = decode_bits(model, 1, m, flip=enc == "flipe")
    if enc in ("syndrome", "flipe"):
        return e.bit_count() <= t and in_colspace(A, n, m, y ^ e), {"e": e, "s": None}
    s = decode_bits(model, m + 1, n, flip=enc == "implicitflip")
    ok = e.bit_count() <= t and all(parity(A[i] & s) ^ (e >> i & 1) == (y >> i & 1) for i in range(m))
    if enc == "explicit":
        ok = ok and s.bit_count() <= meta["k"]
    return ok, {"e": e, "s": s}


# ------------------------------------------------------------------ writing
def instance_id(enc, n, m, t, w, kind, seed, k=None):
    return f"lpn-{enc}-n{n}-m{m}-t{t}-w{w}-{kind}-s{seed}" + ("" if k is None else f"-k{k}")


def write_instance(enc, n, m, t, w, kind, seed, k=None):
    A, y, s, e = sample(n, m, w, kind, seed, k)
    f = encode(A, y, n, m, t, enc, k)
    iid = instance_id(enc, n, m, t, w, kind, seed, k)
    PLAIN.mkdir(parents=True, exist_ok=True)
    LPN_DIR.mkdir(parents=True, exist_ok=True)
    path = PLAIN / f"{iid}.cnf"
    with open(path, "w") as out:
        kk = "" if k is None else f" k={k}"
        out.write(f"c LPN enc={enc} n={n} m={m} t={t} w={w}{kk} kind={kind} seed={seed}\n")
        out.write(f"p cnf {f.nv} {len(f.cls)}\n")
        for c in f.cls:
            out.write(" ".join(map(str, c)) + " 0\n")
    meta = {"id": iid, "enc": enc, "n": n, "m": m, "t": t, "w": w, "k": k, "kind": kind, "seed": seed,
            "A": A, "y": y, "s": s, "e": e, "variables": f.nv, "clauses": len(f.cls),
            "log2_expected_solutions_random_y": log2_expected_solutions(n, m, t, enc, k)}
    (LPN_DIR / f"{iid}.json").write_text(json.dumps(meta))
    return meta, path


# Each grid is a list of blocks: (encodings, [(n, m, t), ...], kinds, seeds).
GRIDS = {
    # dry run: pipeline check + difficulty calibration only (no conclusions)
    "dry": [(ENCODINGS, [(16, 32, 3), (24, 48, 4), (32, 64, 5), (40, 80, 6)],
             ("planted", "random"), range(3))],
    # formal grid, registered in reports/EXPERIMENT_LOG.md before any
    # config-vs-config dry-run comparison was looked at
    "main": [(("syndrome", "flipe"), [(40, 80, 6), (44, 88, 7), (48, 96, 7), (52, 104, 8)],
              ("planted", "random"), range(10, 20)),
             (("secret",), [(20, 40, 4), (24, 48, 4), (28, 56, 5)],
              ("planted", "random"), range(10, 20))],
    # sparse-secret dry run, constant noise rate tau = 1/8: m = 3n,
    # w = t = round(m/8), k = round(n/8); sizes are (n, m, t, k)
    "sparse_dry": [(SPARSE_ENCODINGS, [(n, 3 * n, round(3 * n / 8), round(n / 8)) for n in (16, 24, 32, 40)],
                    ("planted", "random"), range(3))],
    # denser noise, very sparse secret (user's design): e noise rate tau_e in
    # {1/5 (m = 4n), 1/4 (m = 6n)} so the LPN core stays hard and the planted
    # solution unique; secret weight fixed at k = 3
    "sparse_dry2": [(SPARSE_ENCODINGS, [(n, 4 * n, round(4 * n / 5), 3) for n in (24, 32, 40, 48)]
                     + [(n, 6 * n, round(6 * n / 4), 3) for n in (24, 32, 40, 48)],
                     ("planted", "random"), range(2))],
    # end-to-end check in a few minutes (no scientific use)
    "smoke": [(SPARSE_ENCODINGS, [(n, 4 * n, round(4 * n / 5), 2) for n in (12, 16)],
               ("planted", "random"), range(2))],
    # formal sparse-secret grid (pre-registered): same sizes as sparse_dry2,
    # fresh seeds 10-19
    "sparse_main": [(SPARSE_ENCODINGS, [(n, 4 * n, round(4 * n / 5), 3) for n in (24, 32, 40, 48)]
                     + [(n, 6 * n, round(6 * n / 4), 3) for n in (24, 32, 40, 48)],
                     ("planted", "random"), range(10, 20))],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", required=True, choices=sorted(GRIDS))
    ap.add_argument("--manifest", required=True)
    a = ap.parse_args()
    rows, fetch = [], []
    blocks = [(enc, size, kind, seed) for encs, sizes, kinds, seeds in GRIDS[a.grid]
              for size in sizes for enc in encs for kind in kinds for seed in seeds]
    for enc, size, kind, seed in blocks:
        n, m, t = size[:3]
        k = size[3] if len(size) > 3 else None
        meta, path = write_instance(enc, n, m, t, t, kind, seed, k)
        rows.append({"hash": meta["id"], "family": f"lpn-{enc}", "group": f"lpn-{enc}-n{n}",
                     "family_split": "lpn_mech", "result": "sat" if kind == "planted" else "unknown",
                     "enc": enc, "n": n, "m": m, "t": t, "w": t, "k": k, "kind": kind, "seed": seed,
                     "variables": meta["variables"], "clauses": meta["clauses"],
                     "log2_E_random": round(meta["log2_expected_solutions_random_y"], 2)})
        fetch.append({"hash": meta["id"], "sha256_cnf": fplib.sha256_file(path)})
    with open(a.manifest, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(Path(a.manifest).with_name(Path(a.manifest).stem + "_fetch.jsonl"), "w") as f:
        for r in fetch:
            f.write(json.dumps(r) + "\n")
    print(f"{len(rows)} instances -> {a.manifest}")


if __name__ == "__main__":
    main()
