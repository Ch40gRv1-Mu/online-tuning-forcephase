"""Export current T600 VBS labels, opportunity/loss tables and safe cached features."""
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

ACTIONS = ("D", "Fplus", "Fminus")
FEATURES = ["variables", "clauses", "literals", "clause_variable_ratio", "mean_clause_length", "unit_fraction", "binary_fraction",
            "ternary_fraction", "negative_literal_fraction", "pure_variable_fraction", "mean_variable_polarity_imbalance",
            "horn_clause_fraction", "dual_horn_clause_fraction", "positive_only_clause_fraction", "negative_only_clause_fraction",
            "variable_degree_cv", "components", "largest_component_fraction"]


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write_csv(p, rows, fields=None):
    with Path(p).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    p = argparse.ArgumentParser(); p.add_argument("--matrix", type=Path, required=True); p.add_argument("--cache", type=Path, required=True); p.add_argument("--out", type=Path, required=True); a = p.parse_args()
    start = time.monotonic(); cpu = time.process_time(); a.out.mkdir(parents=True, exist_ok=False)
    source = list(csv.DictReader(a.matrix.open())); assert len(source) == 4719
    exported = []; opportunities = []; loss = []
    for i, r in enumerate(source):
        solved = {x: r[x + "_status"] in {"SAT", "UNSAT"} and float(r[x + "_cpu_s"]) <= 600 for x in ACTIONS}
        costs = {x: float(r[x + "_par2"]) for x in ACTIONS}
        times = {x: float(r[x + "_cpu_s"]) for x in ACTIONS if solved[x]}
        best = min(times.values(), default=None)
        exact = [x for x in ACTIONS if solved[x] and times[x] == best]
        near = [x for x in ACTIONS if solved[x] and times[x] <= max(best * 1.01, best + .1)] if best is not None else []
        group = near[0] if len(near) == 1 else "near_tie" if near else "all_timeout"
        vbs_cost = best if best is not None else 1200
        row = {"instance_key": r["instance_key"], "preference_group": group, "exact_VBS_actions": "|".join(exact), "near_best_actions": "|".join(near),
               "solved_actions": "|".join(x for x in ACTIONS if solved[x]), "VBS_cpu_s": best, "VBS_par2": vbs_cost,
               "D_to_VBS_par2_gain_s": costs["D"] - vbs_cost}
        for x in ACTIONS:
            for suffix in ["status", "cpu_s", "conflicts", "par2"]: row[x + "_" + suffix] = r[x + "_" + suffix]
            row[x + "_regret_to_VBS_par2_s"] = costs[x] - vbs_cost
        for x in ACTIONS[1:]:
            gain = costs["D"] - costs[x]
            only_x = solved[x] and not solved["D"]
            both = solved[x] and solved["D"]
            twofold = both and times[x] * 2 <= times["D"] and times["D"] >= 1
            row[x + "_vs_D_par2_gain_s"] = gain
            row[x + "_only_solved_vs_D"] = only_x
            row[x + "_2x_faster_than_D_both_solved"] = twofold
            item = {"instance_key": r["instance_key"], "action": x, "preference_group": group, "D_status": r["D_status"], "action_status": r[x + "_status"],
                    "D_cpu_s": r["D_cpu_s"], "action_cpu_s": r[x + "_cpu_s"], "PAR2_gain_vs_D_s": gain,
                    "opportunity_type": "only_action_solved" if only_x else "both_solved_at_least_2x" if twofold else "", 
                    "D_to_action_time_ratio": times["D"] / times[x] if both else None,
                    "time_ratio_lower_bound_if_D_timeout": 600 / times[x] if only_x else None}
            if only_x or twofold: opportunities.append(item)
            if gain < 0: loss.append(item)
        exported.append(row)
    exported.sort(key=lambda r: (-r["D_to_VBS_par2_gain_s"], r["instance_key"]))
    counts = collections.Counter(r["preference_group"] for r in exported)
    assert sum(counts.values()) == 4719
    write_csv(a.out / "all_preferences.csv", exported)
    (a.out / "groups").mkdir()
    for group in (*ACTIONS, "near_tie", "all_timeout"):
        write_csv(a.out / "groups" / (group + ".csv"), [r for r in exported if r["preference_group"] == group], list(exported[0]))
    opportunities.sort(key=lambda r: -r["PAR2_gain_vs_D_s"]); loss.sort(key=lambda r: r["PAR2_gain_vs_D_s"])
    write_csv(a.out / "F_actions_opportunities_vs_D.csv", opportunities)
    write_csv(a.out / "F_actions_losses_vs_D.csv", loss)
    index = {r["instance_key"]: r for r in exported}; features = []; profiles = {}
    for c in csv.DictReader(a.cache.open()):
        if c["id"] not in index: continue
        # The whitelist intentionally strips all family/answer/old-performance fields.
        f = {"row_ref": "cached_" + str(len(features) + 1), "instance_key": c["id"], "cnf_sha256": c["cnf_sha256"], "preference_group": index[c["id"]]["preference_group"]}
        for name in FEATURES:
            v = float(c[name]); assert math.isfinite(v); f[name] = v
        features.append(f)
    write_csv(a.out / "cached_structure_associations.csv", features)
    blinded = [{k: v for k, v in r.items() if k not in {"instance_key", "cnf_sha256"}} for r in features]
    write_csv(a.out / "astra_structure_view.csv", blinded)
    for group in (*ACTIONS, "near_tie", "all_timeout"):
        subset = [r for r in features if r["preference_group"] == group]
        profiles[group] = {"n": len(subset), "medians": {f: statistics.median(r[f] for r in subset) if subset else None for f in FEATURES}}
    summary = {"scope": "EXPLORATORY_4719_DEVELOPMENT_NOT_CONFIRMATION", "label_definition": "unique action within max(1% of fastest,0.1 seconds); otherwise near_tie; all_timeout unlabelled",
               "cohort": len(exported), "groups": dict(counts), "opportunity_action_rows": len(opportunities), "opportunity_parents": len({r["instance_key"] for r in opportunities}),
               "opportunities_by_action": {x: {"only_action_solved": sum(r["action"] == x and r["opportunity_type"] == "only_action_solved" for r in opportunities),
                                                       "both_solved_at_least_2x": sum(r["action"] == x and r["opportunity_type"] == "both_solved_at_least_2x" for r in opportunities)} for x in ACTIONS[1:]},
               "features_available": len(features), "features_missing": len(exported)-len(features), "feature_columns": FEATURES, "feature_group_profiles": profiles,
               "cached_feature_identity": "Exact GBD-key association to old SHA-bound CNF statistics; new cluster input SHA receipts not present locally. Not a new full-cohort feature extraction.",
               "missingness_and_sampling": "Old exploratory300 cache is selected and previously examined; not representative or untouched validation. Descriptive evidence only.",
               "input_SHA256": {"matrix": sha(a.matrix), "old_cache": sha(a.cache)}, "new_solver_calls": 0,
               "elapsed_wall_s": time.monotonic()-start, "process_cpu_s": time.process_time()-cpu}
    (a.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"feature_group_profiles", "feature_columns"}}, ensure_ascii=False))


if __name__ == "__main__": main()
