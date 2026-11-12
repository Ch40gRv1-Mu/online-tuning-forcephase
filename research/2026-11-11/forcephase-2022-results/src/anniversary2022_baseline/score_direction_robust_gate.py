"""Use training evidence shared by Fplus and Fminus to fit a static phase gate."""

import argparse
from collections import Counter
import json
from pathlib import Path
import time

import numpy as np

from .common import sha, write
from .score_scc_complement_stump import QUANTILES
from .score_two_threshold_transfer import enough, exact_small_block_interval
from .score_width_budget_recovery import assess
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


FEATURES = ("SCC_demand_share", "mean_clause_width")
OBJECTIVES = ("selected_direction", "both_directions", "per_input_worst_direction")


def fit(x, eligible, original_D, paid, support, objective):
    fixed_cost = (paid[eligible, 0] - original_D[eligible]).sum()
    advantages = paid[:, :1] - paid[:, 1:]
    best_value, best = 0, None
    for j, column in enumerate(x.T):
        valid = eligible & np.isfinite(column)
        if not valid.any():
            continue
        for cut in np.unique(np.quantile(column[valid], QUANTILES)):
            for left in (True, False):
                mask = valid & ((column <= cut) == left)
                if not enough(mask, support):
                    continue
                gain = advantages[mask]
                totals = gain.sum(axis=0)
                if objective == "selected_direction":
                    criterion = totals.max()
                elif objective == "both_directions":
                    criterion = totals.min()
                else:
                    criterion = gain.min(axis=1).sum()
                score = criterion - fixed_cost
                if score > best_value:
                    best_value = float(score)
                    best = j, float(cut), left, int(totals.argmax()) + 1
    return best


def replay(x, eligible, costs, paid, shape, holdout, objective):
    choice = np.zeros(len(x), dtype=int)
    chosen = costs[:, 0].copy()
    rules = {}
    for group in np.unique(holdout):
        test = holdout == group
        train = ~test
        rule = fit(x[train], eligible[train], costs[train, 0], paid[train], shape[train], objective)
        rules[group] = rule
        if rule is None:
            continue
        j, cut, left, a = rule
        column = x[:, j]
        acquire = test & eligible
        select = acquire & np.isfinite(column) & ((column <= cut) == left)
        choice[select] = a
        chosen[acquire] = paid[acquire, choice[acquire]]
    return choice, chosen, rules


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, _, _ = load()
    paths = {
        "measured_features": DATA / "live_feature_route_20261110/feature_receipts.jsonl",
        "measured_policy": DATA / "live_feature_route_20261110/predictions.csv",
        "coarse": DATA / "scc_width_fixed_20261110/predictions.csv",
        "fine": DATA / "scc_root_up_20261110/predictions.csv",
    }
    base, coarse, fine = ({r["instance_key"]: r for r in read_csv(paths[p])}
                          for p in ("measured_policy", "coarse", "fine"))
    with paths["measured_features"].open() as stream:
        rows = {r["instance_key"]: r for r in map(json.loads, stream) if r["status"] == "ok"}
    if set(keys) != base.keys() or base.keys() != coarse.keys() or base.keys() != fine.keys() or len(rows) != 2843:
        raise ValueError("unbound full-cohort inputs")
    eligible = np.array([k in rows for k in keys])
    x = np.array([[rows.get(k, {}).get("scc_demand_share"), rows.get(k, {}).get("mean_width")]
                  for k in keys], dtype=float)
    h = np.array([rows.get(k, {}).get("feature_CPU_s", 0.0) for k in keys])
    paid = np.where(costs + h[:, None] <= 600, costs + h[:, None], 1200)
    shape = np.array([fine[k]["shape_block"] for k in keys])
    broad = np.array([coarse[k]["coarse_cluster_group"] for k in keys])
    reference = np.array([float(base[k]["PAR2"]) for k in keys])
    baseline = costs[:, 0]
    predicted = [{"instance_key": k, "D_PAR2": baseline[i], "reference_PAR2": reference[i]}
                 for i, k in enumerate(keys)]
    results = {}
    for split, blocks in (("fine_shape", shape), ("coarse_cluster", broad)):
        for objective in OBJECTIVES:
            name = split + "_" + objective
            action, chosen, rules = replay(x, eligible, costs, paid, shape, blocks, objective)
            result = {"vs_D": assess(baseline, chosen, blocks, 600),
                      "vs_measured_two_threshold": assess(reference, chosen, blocks, 600)}
            if split == "coarse_cluster":
                result["exact_interval_vs_D"] = exact_small_block_interval(baseline, chosen, broad)
            result["fits"] = dict(Counter(FEATURES[r[0]] + "/" + ACTIONS[r[3]] if r else "D" for r in rules.values()))
            result["actions"] = dict(Counter(ACTIONS[i] for i in action))
            result["rules"] = {b: [FEATURES[r[0]], r[1], "<=" if r[2] else ">", ACTIONS[r[3]]] if r else None
                               for b, r in rules.items()}
            results[name] = result
            for i, p in enumerate(predicted):
                p[name + "_action"] = ACTIONS[action[i]]
                p[name + "_PAR2"] = chosen[i]
            print(name, result["vs_D"]["gain_pct"],
                  result.get("exact_interval_vs_D", result["vs_D"]["block_interval_95_pct"]),
                  result["vs_D"]["solved"], result["actions"], result["fits"], flush=True)
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", predicted)
    write(args.out / "summary.json", {
        "parents": len(keys), "verified_feature_inputs": int(eligible.sum()), "results": results,
        "analysis_CPU_s": time.process_time() - cpu, "elapsed_wall_s": time.monotonic() - start,
        "new_solver_calls": 0, "new_feature_calls": 0,
        "input_sha256": {p: sha(path) for p, path in paths.items()},
    })


if __name__ == "__main__":
    main()
