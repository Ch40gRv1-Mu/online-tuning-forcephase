#!/usr/bin/env python3
"""Compute cheap static CNF features (tools/cnffeatures) for manifest splits.

  scripts/run_static_features.py --splits train,val [--jobs 32] --out results/static_features_dev.csv

The CNF is staged to node-local storage first (as for solver runs) and
cnffeatures reads the plain file; its CPU time is recorded and charged to the
static selector at evaluation time.
"""

import argparse
import concurrent.futures as cf
import csv
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fprun  # noqa: E402


def one(h):
    cnf = fprun.stage_cnf(h, "orig", 0)
    r = subprocess.run([os.path.join(fprun.TOOLS, "cnffeatures"), cnf], capture_output=True, text=True)
    if r.returncode != 0:
        return {"instance": h, "error": r.stderr.strip()[:200]}
    d = json.loads(r.stdout)
    d["instance"] = h
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", required=True)
    ap.add_argument("--jobs", type=int, default=32)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    man = fprun.manifest()
    hs = sorted(h for h, r in man.items() if r["split"] in set(a.splits.split(",")))
    with cf.ProcessPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(one, hs, chunksize=4))
    keys = ["instance", "header_vars", "header_clauses", "vars", "clauses", "s_log_vars", "s_log_clauses",
            "s_cv_ratio", "s_mean_len", "s_unit_frac", "s_bin_frac", "s_ter_frac", "s_pos_frac", "s_horn_frac",
            "s_antihorn_frac", "cpu_time", "error"]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in keys})
    print(f"{len(rows)} instances, errors: {sum(1 for r in rows if r.get('error'))}")


if __name__ == "__main__":
    main()
