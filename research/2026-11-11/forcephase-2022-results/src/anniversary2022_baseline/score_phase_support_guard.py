"""Abstain from frozen phase switches without matched training support."""

import argparse
from collections import Counter
import json
from pathlib import Path
import time

import numpy as np

from .common import sha, write
from .score_scc_complement_stump import MIN_SWITCH, MIN_SWITCH_BLOCKS
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


MAX_DISTANCE = 2.0


def select_peers(x, sample, support):
    # Standardize only within the training branch. Keep distance meaningful
    # for held-out points that extend past the training feature range.
    scale = x.std(axis=0)
    scale[scale == 0] = 1
    distance = (((x - sample) / scale) ** 2).sum(axis=1)
    threshold = np.partition(distance, MIN_SWITCH - 1)[MIN_SWITCH - 1]
    take = distance <= threshold
    if threshold > MAX_DISTANCE ** 2 or len(np.unique(support[take])) < MIN_SWITCH_BLOCKS:
        return None
    return take


def evaluate(x, eligible, frozen, costs, live_h, histogram_h, fine, groups, conservative):
    actions = np.zeros(len(x), dtype=int)
    h = live_h.copy()
    switches = Counter()
    support_summary = Counter()
    for group in np.unique(groups):
        test = groups == group
        train = ~test
        for a in (1, 2):
            possible = eligible & (frozen == a)
            use = train & possible
            held = np.flatnonzero(test & possible)
            support_summary["proposed"] += len(held)
            if use.sum() < MIN_SWITCH or len(set(fine[use])) < MIN_SWITCH_BLOCKS:
                support_summary["training_branch_too_small"] += len(held)
                continue
            h[held] += histogram_h[held]
            train_groups = fine[use]
            _, group_idx = np.unique(train_groups, return_inverse=True)
            baseline = costs[use, 0]
            trained = timed_cost(costs[use, a], live_h[use] + histogram_h[use], 600)
            gain = baseline - trained
            solve_delta = (trained < 1200).astype(int) - (baseline < 1200)
            for i in held:
                neighbors = select_peers(x[use], x[i], train_groups)
                if neighbors is None:
                    support_summary["too_distant_or_concentrated"] += 1
                    continue
                saving = gain[neighbors].sum()
                if conservative:
                    by_group = np.bincount(group_idx[neighbors], weights=gain[neighbors])
                    saving -= max(0, by_group.max())
                if saving <= 0 or (conservative and solve_delta[neighbors].sum() < 0):
                    support_summary["insufficient_gain"] += 1
                    continue
                actions[i] = a
                switches[ACTIONS[a]] += 1
    return actions, h, dict(switches), dict(support_summary)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, _, _ = load()
    paths = {
        "live_policy": DATA / "live_feature_route_20261110/predictions.csv",
        "live_features": DATA / "live_feature_route_20261110/feature_receipts.jsonl",
        "histogram_features": DATA / "static_unit_pressure_20261110/feature_receipts.jsonl",
        "fine_groups": DATA / "scc_root_up_20261110/predictions.csv",
        "coarse_groups": DATA / "scc_width_fixed_20261110/predictions.csv",
    }
    live, fine, coarse = ({r["instance_key"]: r for r in read_csv(paths[key])}
                           for key in ("live_policy", "fine_groups", "coarse_groups"))
    def receipts(key):
        with paths[key].open() as stream:
            return {r["instance_key"]: r for r in map(json.loads, stream) if r["status"] == "ok"}

    measured = receipts("live_features")
    histogram = receipts("histogram_features")
    if set(keys) != live.keys() or live.keys() != fine.keys() or live.keys() != coarse.keys() or \
            measured.keys() != histogram.keys() or len(measured) != 2843:
        raise ValueError("unbound feature measurements or archived predictions")
    eligible = np.array([k in measured for k in keys])
    frozen = np.array([ACTIONS.index(live[k]["action"]) for k in keys])
    h = np.array([measured.get(k, {}).get("feature_CPU_s", 0.0) for k in keys])
    extra = np.array([histogram.get(k, {}).get("feature_cpu_s", 0.0) for k in keys])
    baseline = costs[:, 0]
    reference = timed_cost(costs[np.arange(len(keys)), frozen], h, 600)
    if not np.allclose(reference, [float(live[k]["PAR2"]) for k in keys], rtol=0, atol=1e-9):
        raise ValueError("measured two-threshold policy does not reproduce")
    names = ("raw_binary_share", "pure_positive_share", "pure_negative_share")
    vectors = np.zeros((len(keys), 5))
    for i, k in enumerate(keys):
        if k not in measured:
            continue
        r, f = measured[k], histogram[k]["features"]
        vectors[i] = [r["scc_demand_share"] or 0, r["mean_width"], *[f[n] for n in names]]
    if not np.isfinite(vectors).all():
        raise ValueError("invalid structural features")

    shape = np.array([fine[k]["shape_block"] for k in keys])
    broad = np.array([coarse[k]["coarse_cluster_group"] for k in keys])
    rows = [{"instance_key": k, "D_PAR2": baseline[i], "fixed_PAR2": reference[i]} for i, k in enumerate(keys)]
    results = {}
    for split, blocks in (("fine_shape", shape), ("coarse_cluster", broad)):
        for conservative in (False, True):
            label = split + ("_guarded" if conservative else "_mean")
            action, cost, switches, support = evaluate(vectors, eligible, frozen, costs, h, extra, shape,
                                                       blocks, conservative)
            paid = timed_cost(costs[np.arange(len(keys)), action], cost, 600)
            result = {"vs_D": assess(baseline, paid, blocks, 600),
                      "vs_measured_rule": assess(reference, paid, blocks, 600),
                      "switches": switches, "support": support, "additional_CPU_s": float((cost - h).sum())}
            if split == "coarse_cluster":
                result["exact_interval_vs_D"] = exact_small_block_interval(baseline, paid, blocks)
            results[label] = result
            for i, row in enumerate(rows):
                row[label + "_action"] = ACTIONS[action[i]]
                row[label + "_PAR2"] = float(paid[i])
            print(label, result["vs_D"]["gain_pct"], result["vs_D"]["solved"],
                  result.get("exact_interval_vs_D", result["vs_D"]["block_interval_95_pct"]),
                  switches, support, flush=True)
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", rows)
    write(args.out / "summary.json", {
        "parents": len(keys), "scope_with_costed_features": int(eligible.sum()),
        "new_solver_calls": 0, "new_feature_calls": 0, "results": results,
        "analysis_CPU_s": time.process_time() - cpu, "elapsed_wall_s": time.monotonic() - start,
        "input_sha256": {name: sha(path) for name, path in paths.items()},
    })


if __name__ == "__main__":
    main()
