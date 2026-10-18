#!/usr/bin/env python3
"""Build the benchmark manifest and frozen splits from GBD metadata.

Usage: scripts/build_manifest.py --gbd DIR [--out benchmarks/]

Inputs: GBD 'meta.db' and 'base.db' (downloaded from
https://benchmark-database.de/getdatabase/{meta,base}; SHA-256 recorded in
benchmarks/SOURCES.md).  Pool: SAT Competition main tracks 2023-2026.

Rules (fixed before any solver run, see docs/EXPERIMENT_LOG.md):
  * inclusion: GBD 'bytes' (uncompressed sanitized CNF) <= 100e6;
  * family group = conservative alias map over GBD 'family' (merging names
    that denote the same or a closely related generator), then union-find
    over identical GBD isohash so that isomorphic duplicates share a group;
    'unknown' family is grouped by author;
  * dev pool = instances in main 2023-2025; family groups of the dev pool
    are assigned to train/validation/test (about 60/20/20 of instances)
    with a seeded greedy random assignment;
  * temporal pool 't2026' = main 2026 instances that are not in the dev
    pool (by hash or isohash); each is tagged 'seen' (group in dev train or
    validation), 'devtest' (group in dev test) or 'new'.
Outputs: benchmarks/manifest.csv and benchmarks/family_groups.csv.
"""

import argparse
import collections
import csv
import os
import random
import sqlite3

YEARS_DEV = (2023, 2024, 2025)
YEAR_TEMPORAL = 2026
MAX_BYTES = 100e6
SPLIT_SEED = 20261018
FRACTIONS = {"train": 0.6, "val": 0.2, "test": 0.2}

# Conservative alias map: GBD family name -> family group.
ALIASES = {
    "circuit-equialence-checking": "circuit-equivalence-checking",
    "equivalence-checking": "circuit-equivalence-checking",
    "minimal-disagreement-parity": "disagreement-parity",
    "minimum-disagreement-parity": "disagreement-parity",
    "graph-coloring": "coloring",
    "coloring-clique": "coloring",
    "coloring-mycielski-graph": "coloring",
    "clique-coloring": "coloring",
    "hamiltonian-cycle": "hamiltonian",
    "binary-pigeon-hole": "pigeon-hole",
    "relativized-pigeon-hole": "pigeon-hole",
    "sudoku-php": "sudoku",
    "ramsey-numbers": "ramsey",
    "waerden": "van-der-waerden",
    "circuit-multiplier": "multiplier",
    "multiplier-circuits": "multiplier",
    "multiplier-circuit-miters": "multiplier",
    "multiplier-equivalence-checking": "multiplier",
    "multiplier-verification": "multiplier",
    "sgen-balanced": "sgen",
    "risc-instruction-removal-golcrest": "risc-instruction-removal",
    "risc-instruction-removal-subrv": "risc-instruction-removal",
    "hardware-bmc": "hardware",
    "hardware-model-checking": "hardware",
    "hardware-verification": "hardware",
    "hypertree-decomposition": "tree-decomposition",
    "prime-testing": "prime-factoring",
}


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[max(a, b)] = min(a, b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gbd", required=True)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "benchmarks"))
    a = ap.parse_args()
    meta = sqlite3.connect(os.path.join(a.gbd, "meta.db"))
    base = sqlite3.connect(os.path.join(a.gbd, "base.db"))
    years = collections.defaultdict(set)
    for y in YEARS_DEV + (YEAR_TEMPORAL,):
        for (h,) in meta.execute("select hash from track where value=?", (f"main_{y}",)):
            years[h].add(y)
    info = {r[0]: r for r in meta.execute(
        "select hash, filename, isohash, family, author, result from features")}
    size = {r[0]: r[1:] for r in base.execute("select hash, variables, clauses, bytes from features")}

    # family groups
    uf = UF()
    raw_group = {}
    for h in years:
        fam = info[h][3]
        g = ALIASES.get(fam, fam)
        if fam == "unknown":
            g = f"unknown-author-{info[h][4]}"
        raw_group[h] = g
        uf.find(g)
    by_iso = collections.defaultdict(list)
    for h in years:
        by_iso[info[h][2]].append(h)
    merged_iso = []
    for iso, hs in by_iso.items():
        for h in hs[1:]:
            if uf.find(raw_group[h]) != uf.find(raw_group[hs[0]]):
                merged_iso.append((raw_group[hs[0]], raw_group[h]))
            uf.union(raw_group[hs[0]], raw_group[h])
    group = {h: uf.find(raw_group[h]) for h in years}

    def included(h):
        b = size[h][2]
        try:
            return float(b) <= MAX_BYTES
        except (TypeError, ValueError):
            return False

    dev = [h for h in years if years[h] & set(YEARS_DEV)]
    dev_iso = {info[h][2] for h in dev}
    temporal = [h for h in years if not (years[h] & set(YEARS_DEV)) and info[h][2] not in dev_iso]
    dup_2026 = [h for h in years if not (years[h] & set(YEARS_DEV)) and info[h][2] in dev_iso]

    # assign dev family groups (counted on included instances)
    counts = collections.Counter(group[h] for h in dev if included(h))
    groups = sorted(counts)
    rng = random.Random(SPLIT_SEED)
    rng.shuffle(groups)
    groups.sort(key=lambda g: -counts[g])  # stable: big groups first, ties shuffled
    total = sum(counts.values())
    target = {s: f * total for s, f in FRACTIONS.items()}
    have = {s: 0 for s in FRACTIONS}
    split_of = {}
    for g in groups:
        # assign to the split with the largest remaining deficit (relative)
        s = max(FRACTIONS, key=lambda s: (target[s] - have[s]) / target[s])
        split_of[g] = s
        have[s] += counts[g]
    # dev groups with no included instance still get a split for bookkeeping
    for h in dev:
        split_of.setdefault(group[h], "excluded-only")

    rows = []
    for h in sorted(years):
        v, c, b = size[h]
        inc = included(h)
        if h in dev:
            split = split_of[group[h]] if inc else "excluded"
            pool = "dev"
            tag = ""
        elif h in temporal:
            pool = "t2026"
            split = "t2026" if inc else "excluded"
            sg = split_of.get(group[h])
            tag = {"train": "seen", "val": "seen", "test": "devtest"}.get(sg, "new")
        else:
            pool = "dup2026"
            split = "excluded"
            tag = "duplicate-of-dev"
        rows.append({
            "hash": h, "filename": info[h][1], "family": info[h][3], "family_group": group[h],
            "author": info[h][4], "result": info[h][5], "years": "+".join(map(str, sorted(years[h]))),
            "isohash": info[h][2], "variables": v, "clauses": c, "bytes": b, "pool": pool,
            "split": split, "temporal_tag": tag,
            "url": f"https://benchmark-database.de/file/{h}",
        })
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "manifest.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(a.out, "family_groups.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["family_group", "split", "dev_included_instances", "gbd_families"])
        fams = collections.defaultdict(set)
        for h in years:
            fams[group[h]].add(info[h][3])
        for g in sorted(fams):
            w.writerow([g, split_of.get(g, "t2026-only"), counts.get(g, 0), ";".join(sorted(fams[g]))])
    summ = collections.Counter((r["pool"], r["split"]) for r in rows)
    print("rows", len(rows), dict(summ))
    print("dev split instances", have, "groups per split",
          collections.Counter(split_of[g] for g in counts))
    print("isohash merges across groups", merged_iso)
    tt = collections.Counter(r["temporal_tag"] for r in rows if r["split"] == "t2026")
    print("t2026 tags", dict(tt), "dup2026", len(dup_2026))
    res = collections.Counter((r["split"], r["result"]) for r in rows)
    print({k: v for k, v in sorted(res.items())})


if __name__ == "__main__":
    main()
