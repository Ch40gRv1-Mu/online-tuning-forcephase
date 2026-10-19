#!/usr/bin/env python3
"""Audit v2: strict rebuild of the M3 same-state dataset.

  scripts/audit_v2/m3_build_strict.py --runs results/m2_census/runs.csv --runs results/m3_replay/runs.csv \
      --static results/static_features_dev.csv --out results/audit_v2/m3/dataset_strict.csv \
      [--report results/audit_v2/m3/gate_summary.md] [--allow-errors]

Same rows and columns as scripts/m3_build.py (round 1) plus 'category' and
'detail' from scripts/audit_v2/gate.py.  Unlike round 1, a missing/corrupt
telemetry file is a data error (not "no decision point"), a missing replay is
a data error (never back-filled with the base cost), digests must match and
the switch must actually have been applied at the checkpoint.  Without
--allow-errors the script exits non-zero on any data error (only
'censored_unmatched' is an allowed exception, with training weight 0).
"""

import argparse
import collections
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import fprun  # noqa: E402
import gate  # noqa: E402

PAIRS = [  # (base config, alt config, K, track, direction, action after switch)
    ("D", "sw1k_C", 1000, "C", "nat2neg", "NEGATIVE"),
    ("D", "sw10k_C", 10000, "C", "nat2neg", "NEGATIVE"),
    ("D", "sw100k_C", 100000, "C", "nat2neg", "NEGATIVE"),
    ("D", "sw10k_P", 10000, "P", "nat2neg", "NEGATIVE"),
    ("Fminus", "sw10k_Crev", 10000, "C", "neg2nat", "NATIVE"),
    ("Iminus", "sw1k_Cin", 1000, "C", "in2neg", "NEGATIVE"),
    ("Iminus", "sw10k_Cin", 10000, "C", "in2neg", "NEGATIVE"),
    ("Iminus", "sw100k_Cin", 100000, "C", "in2neg", "NEGATIVE"),
]
KEY = ["config", "instance", "seed", "variant", "repeat"]


def tel_path(run_id):
    return os.path.join(fprun.raw_dir(run_id), "telemetry.jsonl.gz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", action="append", required=True)
    ap.add_argument("--static", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--allow-errors", action="store_true")
    a = ap.parse_args()
    df = pd.concat([pd.read_csv(p, dtype={"instance": str}) for p in a.runs], ignore_index=True)
    df = df[df.split.isin(["train", "val"]) & (df.seed == 0) & (df["repeat"].fillna(0) == 0)]
    dup = df[df.duplicated(KEY, keep=False)]
    dup_keys = set(zip(dup.config, dup.instance))
    df = df.drop_duplicates(KEY)
    by = {(r.config, r.instance): r for r in df.itertuples()}
    static = pd.read_csv(a.static, dtype={"instance": str}).set_index("instance")
    insts = sorted(df[df.config == "D"].instance.unique())
    cache = {}

    def tel(run):
        if run.run_id not in cache:
            cache[run.run_id] = gate.load_telemetry(tel_path(run.run_id))
        return cache[run.run_id]

    rows = []
    for base_c, alt_c, K, track, direction, action in PAIRS:
        for h in insts:
            b = by.get((base_c, h))
            r = by.get((alt_c, h))
            if b is not None and b.status == "missing":
                b = None
            if r is not None and r.status == "missing":
                r = None
            def summ(x):
                return None if x is None else {"status": x.status, "terminated_by": x.terminated_by,
                                               "exit_code": x.exit_code, "cpu": x.cpu}
            bsum, asum = summ(b), summ(r)
            btel = tel(b) if b is not None else ([], "telemetry_missing")
            atel = tel(r) if r is not None else None
            cat, det = gate.classify_pair(bsum, btel, asum, atel, K, action, track)
            if (base_c, h) in dup_keys or (alt_c, h) in dup_keys:
                cat, det = "duplicate_key", {}
            row = {"instance": h, "family_group": None if b is None else b.family_group,
                   "family": None if b is None else b.family, "split": None if b is None else b.split,
                   "gbd_result": None if b is None else b.gbd_result, "K": K, "track": track,
                   "direction": direction, "base": base_c, "alt": alt_c, "category": cat,
                   "detail": json.dumps(det, sort_keys=True),
                   "cost_base": None if b is None else b.par2, "status_base": None if b is None else b.status,
                   "result_base": None if b is None else b.result,
                   "static_cpu": static.loc[h, "cpu_time"] if h in static.index else np.nan,
                   "base_run_id": None if b is None else b.run_id, "alt_run_id": None if r is None else r.run_id}
            if cat in ("solved_before_K", "budget_before_K"):
                row.update({"has_decision": 0, "alt_run": 0, "cost_alt": row["cost_base"],
                            "status_alt": row["status_base"]})
            elif cat in ("valid_pair", "censored_unmatched"):
                cp = gate.checkpoint_at(btel[0], K)
                row.update({"has_decision": 1, "alt_run": 1, "cost_alt": r.par2, "status_alt": r.status,
                            "result_alt": r.result, "cp_conflicts": cp["conflicts"], "cp_time": cp["time"],
                            "digest_ok": 1 if cat == "valid_pair" else np.nan,
                            "switch_applied": 1 if cat == "valid_pair" else 0})
                for k, v in cp["f"].items():
                    row["f_" + k] = v
            else:  # data error: no cost is filled in
                row.update({"has_decision": np.nan, "alt_run": int(r is not None), "cost_alt": np.nan,
                            "status_alt": None if r is None else r.status})
            rows.append(row)
    out = pd.DataFrame(rows)
    for col in ("switch_applied", "cost_alt", "has_decision", "alt_run", "status_alt"):
        if col not in out:
            out[col] = np.nan
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out.to_csv(a.out, index=False)
    T = 300.0
    summ = []
    for (alt_c, K, direction, track), g in out.groupby(["alt", "K", "direction", "track"], sort=False):
        c = g.category.value_counts()
        both_to = (g.category == "valid_pair") & (g.cost_base >= 2 * T) & (g.cost_alt >= 2 * T)
        pos = (g.category == "valid_pair") & ~both_to & (g.cost_base != g.cost_alt)
        summ.append({"alt": alt_c, "K": K, "prefix": {"nat2neg": "D", "in2neg": "I−", "neg2nat": "F−"}[direction],
                     "track": track, "instances": len(g),
                     "solved_before_K": int(c.get("solved_before_K", 0)),
                     "budget_before_K": int(c.get("budget_before_K", 0)),
                     "valid_pair": int(c.get("valid_pair", 0)),
                     "censored_unmatched": int(c.get("censored_unmatched", 0)),
                     "data_errors": int(sum(c.get(e, 0) for e in gate.ERRORS)),
                     "switches_applied": int(g.switch_applied.fillna(0).sum()),
                     "valid_both_timeout": int(both_to.sum()), "positive_weight_labels": int(pos.sum())})
    s = pd.DataFrame(summ)
    tot = s[[c for c in s.columns if c not in ("alt", "K", "prefix", "track")]].sum()
    errors = out[out.category.isin(gate.ERRORS)]
    exc = out[out.category.isin(gate.EXCEPTION)]
    lines = ["# M3 strict data gate (generated by scripts/audit_v2/m3_build_strict.py)\n",
             "One row per (instance, base, alt, K, track, direction) over all 817 dev instances. Categories as in "
             "docs/CORRECTION_PROTOCOL.md §4. 'positive_weight_labels' = valid pairs that are not both timeouts and "
             "whose two costs differ.\n",
             "| alt | K | prefix | track | instances | solved_before_K | budget_before_K | valid_pair | "
             "censored_unmatched | data_errors | switches_applied | valid_both_timeout | positive_weight_labels |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in s.itertuples():
        lines.append(f"| {r.alt} | {r.K} | {r.prefix} | {r.track} | {r.instances} | {r.solved_before_K} | "
                     f"{r.budget_before_K} | {r.valid_pair} | {r.censored_unmatched} | {r.data_errors} | "
                     f"{r.switches_applied} | {r.valid_both_timeout} | {r.positive_weight_labels} |")
    lines.append("| **all 8 groups** | | | | " + " | ".join(str(int(tot[c])) for c in tot.index) + " |")
    train = s[s.alt.isin(["sw1k_C", "sw10k_C", "sw100k_C", "sw1k_Cin", "sw10k_Cin", "sw100k_Cin"])]
    t2 = train[[c for c in train.columns if c not in ("alt", "K", "prefix", "track")]].sum()
    lines.append("| **6 training groups** (C, D and I− prefix) | | | | " +
                 " | ".join(str(int(t2[c])) for c in t2.index) + " |")
    lines.append(f"\nReplays run (alt records present): all 8 groups {int(out.alt_run.fillna(0).sum())}, "
                 f"of which valid_pair {int(tot['valid_pair'])} and censored_unmatched {int(tot['censored_unmatched'])}; "
                 f"6 training groups {int(out[out.alt.isin(train.alt)].alt_run.fillna(0).sum())} "
                 f"(valid {int(t2['valid_pair'])}).\n")
    lines.append(f"Data errors: {len(errors)}. Exceptions (censored_unmatched): {len(exc)}.\n")
    if len(exc):
        lines.append("| instance | alt | K | base status | alt status | base checkpoint conflicts / CPU s |\n|---|---|---|---|---|---|")
        for r in exc.itertuples():
            d = json.loads(r.detail)
            lines.append(f"| {r.instance} | {r.alt} | {r.K} | {r.status_base} | {r.status_alt} | "
                         f"{d['base_cp_conflicts']} / {d['base_cp_time']:.1f} |")
    killed = out[out.detail.str.contains("killed_after_cutoff")]
    lines.append(f"\nRows using a telemetry log of a run SIGKILLed after the CPU cutoff (protocol appendix A): "
                 f"{len(killed)}.\n")
    if len(killed):
        lines.append("| instance | alt | category | base status | alt status | detail |\n|---|---|---|---|---|---|")
        for r in killed.itertuples():
            lines.append(f"| {r.instance[:12]} | {r.alt} | {r.category} | {r.status_base} | {r.status_alt} | {r.detail} |")
    if len(errors):
        lines.append("\n## Data errors\n\n| instance | alt | category | detail |\n|---|---|---|---|")
        for r in errors.itertuples():
            lines.append(f"| {r.instance} | {r.alt} | {r.category} | {r.detail} |")
    text = "\n".join(lines) + "\n"
    if a.report:
        with open(a.report, "w") as f:
            f.write(text)
        s.to_csv(os.path.splitext(a.report)[0] + ".csv", index=False)
        out[out.category.isin(gate.ERRORS + gate.EXCEPTION)].to_csv(
            os.path.splitext(a.report)[0] + "_exceptions.csv", index=False)
    print(text)
    if not a.allow_errors:
        gate.enforce(out.category)


if __name__ == "__main__":
    main()
