"""Fit one two-threshold policy jointly over four cutoffs of the same archived traces."""

import argparse
import json
from pathlib import Path
import time

import numpy as np

from .common import read, sha, write
from .score_two_threshold_transfer import exact_small_block_interval, replay
from .score_width_budget_recovery import BUDGETS, assess, timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, _, _ = load()
    sources = {
        "features": DATA / "live_feature_route_20261110/feature_receipts.jsonl",
        "fixed": DATA / "live_feature_route_20261110/predictions.csv",
        "fine": DATA / "scc_root_up_20261110/predictions.csv",
        "coarse": DATA / "scc_width_fixed_20261110/predictions.csv",
        "prior_fit": DATA / "two_threshold_transfer_20261110/summary.json",
        "prior_predictions": DATA / "two_threshold_transfer_20261110/predictions.csv",
    }
    with sources["features"].open() as stream:
        measured = {r["instance_key"]: r for r in map(json.loads, stream) if r["status"] == "ok"}
    fixed, fine, coarse, prior = ({r["instance_key"]: r for r in read_csv(sources[n])}
                                  for n in ("fixed", "fine", "coarse", "prior_predictions"))
    if set(keys) != fixed.keys() or fixed.keys() != fine.keys() or fixed.keys() != coarse.keys() or \
            fixed.keys() != prior.keys() or len(measured) != 2843:
        raise ValueError("unbound full 2022 inputs")
    prior_rules = read(sources["prior_fit"])["results"]
    scope = np.array([k in measured for k in keys])
    scc = np.array([measured.get(k, {}).get("scc_demand_share") for k in keys], dtype=float)
    width = np.array([measured.get(k, {}).get("mean_width", 0.0) for k in keys])
    h = np.array([measured.get(k, {}).get("feature_CPU_s", 0.0) for k in keys])
    shape = np.array([fine[k]["shape_block"] for k in keys])
    broad = np.array([coarse[k]["coarse_cluster_group"] for k in keys])
    idx = np.arange(len(keys))
    fixed_actions = np.array([ACTIONS.index(fixed[k]["action"]) for k in keys])

    raw_objective = np.mean([timed_cost(costs, 0, T) / (2 * T) for T in BUDGETS], axis=0)
    paid_objective = np.mean([timed_cost(costs, h[:, None], T) / (2 * T) for T in BUDGETS], axis=0)
    reports = {}
    output = [{"instance_key": k, "fine_shape": shape[i], "coarse_cluster": broad[i]}
              for i, k in enumerate(keys)]
    for grouping, blocks in (("fine_shape", shape), ("coarse_cluster", broad)):
        action, _, rules = replay(scc, width, raw_objective, paid_objective, scope, shape, blocks)
        pay = np.array([rules[g] is not None for g in blocks]) * h
        previous_action = np.array([ACTIONS.index(prior[k][grouping + "_action"]) for k in keys])
        previous_rules = prior_rules[grouping]["thresholds_by_held_group"]
        previous_h = np.array([previous_rules[g] is not None for g in blocks]) * h
        previous_expected = [float(prior[k][grouping + "_PAR2"]) for k in keys]
        if not np.allclose(timed_cost(costs[idx, previous_action], previous_h, 600),
                           previous_expected, rtol=0, atol=1e-9):
            raise ValueError("prior T600 held-out policy does not reproduce")

        result = {"rules": rules, "budgets": {}}
        for i, row in enumerate(output):
            row[grouping + "_action"] = ACTIONS[action[i]]
        for T in BUDGETS:
            d = timed_cost(costs[:, 0], 0, T)
            old = timed_cost(costs[idx, previous_action], previous_h, T)
            paid = timed_cost(costs[idx, action], pay, T)
            fixed_par = timed_cost(costs[idx, fixed_actions], h, T)
            stats = {
                "vs_D": assess(d, paid, blocks, T),
                "vs_T600_trained": assess(old, paid, blocks, T),
                "vs_fixed_two_threshold": assess(fixed_par, paid, blocks, T),
            }
            if grouping == "coarse_cluster":
                stats["exact_interval_vs_D"] = exact_small_block_interval(d, paid, broad)
            result["budgets"][str(T)] = stats
            for i, row in enumerate(output):
                row[f"{grouping}_T{T}_PAR2"] = paid[i]
            print(grouping, T, round(stats["vs_D"]["gain_pct"], 6), stats["vs_D"]["solved"],
                  stats.get("exact_interval_vs_D", stats["vs_D"]["block_interval_95_pct"]), flush=True)
        reports[grouping] = result
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", output)
    write(args.out / "summary.json", {"parents": len(keys), "budget_weights": "equal weights on PAR2/(2T)",
          "results": reports, "inputs_sha256": {n: sha(p) for n, p in sources.items()},
          "new_solver_calls": 0, "new_feature_calls": 0, "analysis_CPU_s": time.process_time() - cpu,
          "elapsed_wall_s": time.monotonic() - start})


if __name__ == "__main__":
    main()
