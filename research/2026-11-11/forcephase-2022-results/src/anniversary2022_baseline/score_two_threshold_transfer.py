"""Train both frozen feature directions without any held-out structural group outcomes."""

import argparse
from itertools import combinations_with_replacement
import json
import math
from pathlib import Path
import time

import numpy as np

from .common import sha, write
from .score_scc_complement_stump import MIN_SWITCH, MIN_SWITCH_BLOCKS, QUANTILES
from .score_width_budget_recovery import assess
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


def enough(mask, groups):
    return mask.sum() >= MIN_SWITCH and len(np.unique(groups[mask])) >= MIN_SWITCH_BLOCKS


def fit(scc, width, paid, direct_D, eligible, support):
    best = None
    largest = 0
    valid_scc = eligible & np.isfinite(scc) & (scc > 0)
    scc_cuts = np.unique(np.quantile(scc[valid_scc], QUANTILES)) if valid_scc.any() else ()
    acquisition_loss = (paid[:, 0] - direct_D).sum()
    plus_gain = paid[:, 0] - paid[:, 1]
    minus_gain = paid[:, 0] - paid[:, 2]
    for scc_cut in (None, *scc_cuts):
        use_minus = eligible & (scc > scc_cut) if scc_cut is not None else np.zeros(len(scc), dtype=bool)
        if scc_cut is not None and not enough(use_minus, support):
            continue
        scc_gain = minus_gain[use_minus].sum() - acquisition_loss
        width_scope = eligible & ~use_minus
        width_cuts = np.unique(np.quantile(width[width_scope], QUANTILES)) if width_scope.any() else ()
        if scc_cut is not None and scc_gain > largest:
            largest, best = scc_gain, (float(scc_cut), None)
        for width_cut in width_cuts:
            use_plus = width_scope & (width > width_cut)
            if not enough(use_plus, support):
                continue
            gain = scc_gain + plus_gain[use_plus].sum()
            if gain > largest:
                largest, best = gain, (None if scc_cut is None else float(scc_cut), float(width_cut))
    return best


def replay(scc, width, costs, paid, eligible, fine, blocks):
    actions = np.zeros(len(scc), dtype=int)
    chosen = costs[:, 0].copy()
    rules = {}
    for group in np.unique(blocks):
        test = blocks == group
        train = ~test
        rule = fit(scc[train], width[train], paid[train], costs[train, 0], eligible[train], fine[train])
        rules[group] = rule
        if rule is not None:
            scc_cut, width_cut = rule
            use = test & eligible
            if width_cut is not None:
                actions[use & (width > width_cut)] = 1
            if scc_cut is not None:
                actions[use & (scc > scc_cut)] = 2
            chosen[use] = paid[use, actions[use]]
    return actions, chosen, rules


def exact_small_block_interval(baseline, chosen, blocks):
    _, ids = np.unique(blocks, return_inverse=True)
    b = np.bincount(ids, weights=baseline)
    g = np.bincount(ids, weights=baseline - chosen)
    n = len(b)
    if n != 8:
        raise ValueError("exact calculation is restricted to the eight frozen clusters")
    distribution = []
    for draw in combinations_with_replacement(range(n), n):
        count = np.bincount(draw, minlength=n)
        multiplicity = math.factorial(n) // math.prod(math.factorial(int(c)) for c in count)
        distribution.append((100 * np.dot(count, g) / np.dot(count, b), multiplicity))
    distribution.sort()
    values, weights = map(np.asarray, zip(*distribution))
    cdf = np.cumsum(weights) / n ** n
    return values[np.searchsorted(cdf, [0.025, 0.975])].tolist()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, _, _ = load()
    files = {
        "live_features": args.live / "feature_receipts.jsonl",
        "live_policy": args.live / "predictions.csv",
        "coarse_groups": DATA / "scc_width_fixed_20261110/predictions.csv",
        "fine_groups": DATA / "scc_root_up_20261110/predictions.csv",
    }
    fixed, coarse, fine = ({r["instance_key"]: r for r in read_csv(files[name])}
                           for name in ("live_policy", "coarse_groups", "fine_groups"))
    with files["live_features"].open() as stream:
        features = {r["instance_key"]: r for r in map(json.loads, stream) if r["status"] == "ok"}
    if set(keys) != fixed.keys() or fixed.keys() != coarse.keys() or fixed.keys() != fine.keys() or len(features) != 2843:
        raise ValueError("unbound 2022 inputs")
    eligible = np.array([k in features for k in keys])
    scc = np.array([features.get(k, {}).get("scc_demand_share") for k in keys], dtype=float)
    width = np.array([features.get(k, {}).get("mean_width", 0) for k in keys])
    h = np.array([features.get(k, {}).get("feature_CPU_s", 0) for k in keys])
    paid = np.where(costs + h[:, None] <= 600, costs + h[:, None], 1200)
    shape = np.array([fine[k]["shape_block"] for k in keys])
    broad = np.array([coarse[k]["coarse_cluster_group"] for k in keys])
    frozen = np.array([float(fixed[k]["PAR2"]) for k in keys])
    rows = [{"instance_key": k, "coarse_cluster": broad[i], "D_PAR2": costs[i, 0],
             "fixed_PAR2": frozen[i]} for i, k in enumerate(keys)]
    results = {}
    for name, groups in (("fine_shape", shape), ("coarse_cluster", broad)):
        actions, chosen, rules = replay(scc, width, costs, paid, eligible, shape, groups)
        result = assess(costs[:, 0], chosen, groups, 600)
        if name == "coarse_cluster":
            result["exact_block_interval_95_pct"] = exact_small_block_interval(costs[:, 0], chosen, broad)
        result["thresholds_by_held_group"] = rules
        result["action_counts"] = {a: int((actions == i).sum()) for i, a in enumerate(ACTIONS)}
        results[name] = result
        for i, row in enumerate(rows):
            row[name + "_action"] = ACTIONS[actions[i]]
            row[name + "_PAR2"] = float(chosen[i])
        print(name, result["gain_pct"], result["block_interval_95_pct"], result["solved"],
              result["action_counts"], flush=True)
    fixed_by_cluster = {g: float((costs[broad == g, 0] - frozen[broad == g]).sum()) for g in np.unique(broad)}
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", rows)
    write(args.out / "summary.json", {"parents": len(keys), "frozen_fixed_exact_coarse_95_pct":
          exact_small_block_interval(costs[:, 0], frozen, broad), "frozen_net_savings_by_cluster_s": fixed_by_cluster,
          "results": results, "new_solver_calls": 0, "analysis_CPU_s": time.process_time() - cpu,
          "elapsed_wall_s": time.monotonic() - start, "input_sha256": {k: sha(v) for k, v in files.items()}})


if __name__ == "__main__":
    main()
