#!/usr/bin/env python3
"""Build the M3 one-shot dataset from census and replay runs (dev only).

  scripts/m3_build.py --runs results/m2_census/runs.csv --runs results/m3_replay/runs.csv \
      --static results/static_features_dev.csv --out results/m3/dataset.csv

For every dev instance, prefix length K and replay pair (base, alt):
  base = D (NATIVE from the start), alt = sw{K}_C / sw{K}_P (same NATIVE
  prefix, NEGATIVE after the first restart with >= K conflicts), or
  base = Fminus, alt = sw{K}_Crev (NEGATIVE prefix, NATIVE afterwards).
The features are those of the base run's telemetry checkpoint at K (the
deployed controller sees exactly these, up to timing features).  The prefix
of the alt run is checked by comparing its checkpoint digest at K with the
base run's digest.  If the base run finished before reaching K there is no
decision point: has_decision = 0 and both costs equal the base cost.
"""

import argparse
import gzip
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import fprun  # noqa: E402

PAIRS = [  # (base config, alt config, K, track, direction)
    ("D", "sw1k_C", 1000, "C", "nat2neg"),
    ("D", "sw10k_C", 10000, "C", "nat2neg"),
    ("D", "sw100k_C", 100000, "C", "nat2neg"),
    ("D", "sw10k_P", 10000, "P", "nat2neg"),
    ("Fminus", "sw10k_Crev", 10000, "C", "neg2nat"),
    ("Iminus", "sw1k_Cin", 1000, "C", "in2neg"),
    ("Iminus", "sw10k_Cin", 10000, "C", "in2neg"),
    ("Iminus", "sw100k_Cin", 100000, "C", "in2neg"),
]


def telemetry(run_id):
    p = os.path.join(fprun.raw_dir(run_id), "telemetry.jsonl.gz")
    if not os.path.exists(p):
        return []
    out = []
    with gzip.open(p, "rt") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def checkpoint_at(tel, K):
    for x in tel:
        if x.get("type") == "checkpoint" and x["crossed"][0] <= K <= x["crossed"][1]:
            return x
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", action="append", required=True)
    ap.add_argument("--static", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    df = pd.concat([pd.read_csv(p, dtype={"instance": str}) for p in a.runs], ignore_index=True)
    df = df[df.split.isin(["train", "val"]) & (df.seed == 0) & (df.get("repeat", 0) == 0)]
    by = {(r.config, r.instance): r for r in df.itertuples()}
    static = pd.read_csv(a.static, dtype={"instance": str}).set_index("instance")
    rows = []
    tel_cache = {}
    insts = sorted(df[df.config == "D"].instance.unique())
    for base, alt, K, track, direction in PAIRS:
        if not any(df.config == alt):
            continue
        for h in insts:
            b = by.get((base, h))
            if b is None or b.status == "missing":
                continue
            if b.run_id not in tel_cache:
                tel_cache[b.run_id] = telemetry(b.run_id)
            cp = checkpoint_at(tel_cache[b.run_id], K)
            row = {"instance": h, "family_group": b.family_group, "family": b.family, "split": b.split,
                   "gbd_result": b.gbd_result, "K": K, "track": track, "direction": direction,
                   "base": base, "alt": alt, "has_decision": int(cp is not None),
                   "cost_base": b.par2, "status_base": b.status, "result_base": b.result,
                   "static_cpu": static.loc[h, "cpu_time"] if h in static.index else np.nan}
            if cp is None:
                row.update({"cost_alt": b.par2, "status_alt": b.status, "alt_run": 0, "digest_ok": np.nan})
            else:
                r = by.get((alt, h))
                row["cp_conflicts"] = cp["conflicts"]
                row["cp_time"] = cp["time"]
                if r is None or r.status == "missing":
                    row.update({"cost_alt": np.nan, "status_alt": "missing", "alt_run": 0, "digest_ok": np.nan})
                else:
                    t2 = telemetry(r.run_id)
                    cp2 = checkpoint_at(t2, K)
                    sw = [x for x in t2 if x.get("type") == "switch"]
                    row.update({"cost_alt": r.par2, "status_alt": r.status, "result_alt": r.result, "alt_run": 1,
                                "digest_ok": int(cp2 is not None and cp2["digest"] == cp["digest"]),
                                "switch_conflicts": sw[0]["conflicts"] if sw else np.nan,
                                "switch_applied": int(bool(sw))})
                for k, v in cp["f"].items():
                    row["f_" + k] = v
            rows.append(row)
    out = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out.to_csv(a.out, index=False)
    summ = out.groupby(["alt"]).agg(n=("instance", "size"), decisions=("has_decision", "sum"),
                                    alt_runs=("alt_run", "sum"), digest_ok=("digest_ok", "sum"),
                                    missing=("status_alt", lambda s: (s == "missing").sum()))
    print(summ)


if __name__ == "__main__":
    main()
