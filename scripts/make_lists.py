#!/usr/bin/env python3
"""Derive instance lists for follow-up experiments from the M2 census (dev only).

  scripts/make_lists.py

Writes benchmarks/derived/:
  m1_over1s.txt          train+val instances where D (seed 0) was solved with CPU >= 1 s
  m3_cross_<K>.txt       train+val instances whose D run reached checkpoint K
                         (first restart with >= K conflicts) before finishing;
                         only these have a decision point at K
  m3rev_cross_<K>.txt    same for the F- run (reverse replay F- prefix -> D)
These rules only use dev-split census data and are fixed before any M3 run.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fprun  # noqa: E402

KS = (1000, 10000, 100000)


def records(exp_path, config):
    exp = fprun.load_experiment(exp_path)
    exp["configs"] = [config]
    out = {}
    for run in fprun.plan(exp):
        p = fprun.result_path(run["run_id"])
        if os.path.exists(p):
            out[run["key"]["instance"]] = fprun.load_json(p)
    return out, len(fprun.plan(exp))


def crossed(rec, K):
    tel = rec.get("telemetry") or {}
    return any(c["crossed"][0] <= K <= c["crossed"][1] or c["crossed"][1] >= K for c in tel.get("checkpoints") or [])


def write(name, hashes, comment):
    d = os.path.join(fprun.ROOT, "benchmarks", "derived")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w") as f:
        f.write(f"# {comment}\n")
        for h in sorted(hashes):
            f.write(h + "\n")
    print(f"{name}: {len(hashes)}")


def main():
    census = os.path.join(fprun.ROOT, "configs", "experiments", "m2_census.json")
    D, nD = records(census, "D")
    F, nF = records(census, "Fminus")
    if len(D) != nD or len(F) != nF:
        raise SystemExit(f"census incomplete: D {len(D)}/{nD}, F- {len(F)}/{nF}")
    write("m1_over1s.txt", [h for h, r in D.items() if r["status"] == "solved" and r["cpu"] >= 1.0],
          "train+val instances where census D (seed 0) solved with CPU >= 1 s (M1 overhead set)")
    for K in KS:
        write(f"m3_cross_{K}.txt", [h for h, r in D.items() if crossed(r, K)],
              f"train+val instances whose census D run reached checkpoint {K} (decision point exists)")
        write(f"m3rev_cross_{K}.txt", [h for h, r in F.items() if crossed(r, K)],
              f"train+val instances whose census F- run reached checkpoint {K}")


if __name__ == "__main__":
    main()
