"""Leave structural blocks out when fitting actions for a frozen SCC trigger."""

import argparse
from collections import Counter
import json
from pathlib import Path
import time

import numpy as np

from .common import read, sha, write
from .score_scc_root_guard import FIXED_SHARE_THRESHOLD, par2
from .structural_clusters import ACTIONS, load, read_csv, summarize_policy, write_csv


def blocked_actions(costs, trigger, fixed, overhead, blocks, split):
    """Fit cost-minimizing leaf actions using every block except the predicted block."""
    _, block_index = np.unique(blocks, return_inverse=True)
    actions = np.zeros(len(costs), dtype=int)
    assessed = np.zeros(len(costs))
    fits = Counter()
    leaves = (trigger & fixed, trigger & ~fixed) if split else (trigger,)
    prices = np.column_stack([par2(costs, np.full(len(costs), j, dtype=int), overhead)
                              for j in range(len(ACTIONS))])
    for block in np.unique(block_index):
        test = block_index == block
        train = ~test
        choice = []
        total = prices[train, 0].sum()
        for leaf in leaves:
            available = train & leaf
            leaf_costs = prices[available].sum(axis=0)
            action = int(leaf_costs.argmin())
            total += leaf_costs[action] - leaf_costs[0]
            choice.append(action)
        if total >= costs[train, 0].sum() or not any(choice):
            choice = [0] * len(leaves)
        else:
            assessed[test] = overhead[test]
            for leaf, action in zip(leaves, choice):
                actions[test & leaf] = action
        fits["/".join(ACTIONS[a] for a in choice)] += 1
    return actions, assessed, dict(fits)


def assessment(costs, action, paid, blocks):
    baseline = costs[:, 0]
    savings = baseline - paid
    _, indices = np.unique(blocks, return_inverse=True)
    block_gain = np.bincount(indices, weights=savings)
    influenced = np.bincount(indices, weights=np.abs(savings)) > 0
    rescues = (baseline == 1200) & (paid < 1200)
    losses = (baseline < 1200) & (paid == 1200)
    return {
        **summarize_policy(costs, action, blocks, chosen=paid),
        "rescued_D_timeouts": int(rescues.sum()), "lost_D_solves": int(losses.sum()),
        "rescue_blocks": int(len(set(blocks[rescues]))),
        "net_savings_s": float(savings.sum()),
        "largest_block_gain_s": float(block_gain.max()),
        "net_gain_without_largest_block_s": float(savings.sum() - block_gain.max()),
        "affected_blocks": int(influenced.sum()),
        "blocks": len(block_gain),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root-results", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, _, _ = load()
    root_summary = read(args.root_results / "summary.json")
    source = {r["instance_key"]: r for r in read_csv(args.root_results / "predictions.csv")}
    with (args.root_results / "feature_receipts.jsonl").open() as stream:
        measurements = {r["instance_key"]: r for r in map(json.loads, stream)}
    if set(source) != set(keys) or len(measurements) != root_summary["root_feature_attempts"]:
        raise ValueError("root guard population or feature receipt mismatch")
    original = np.array([source[k]["original_scope"] == "True" for k in keys])
    trigger = np.array([source[k]["SCC_original_action"] == "Fminus" for k in keys])
    fixed = np.array([measurements.get(k, {}).get("status") == "ok" and
                      measurements[k]["fixed_demand_share"] >= FIXED_SHARE_THRESHOLD for k in keys])
    cost_scc = np.array([float(source[k]["old_extractor_cpu_s"]) for k in keys]) * original
    cost_root = cost_scc + np.array([float(source[k]["root_extractor_cpu_s"]) for k in keys]) * trigger
    shape = np.array([source[k]["shape_block"] for k in keys])
    # Hold all triggered formulas with the same nonzero root-unit count together.
    # Keep morphology blocks for untriggered and zero-unit cases.
    root = np.array([f"units:{measurements[k]['root_assigned_variables']}" if trigger[i] and
                     measurements.get(k, {}).get("root_assigned_variables", 0) > 0 else "shape:" + shape[i]
                     for i, k in enumerate(keys)])

    comparison = {}
    predictions = [{"instance_key": key, "shape_block": shape[i], "root_unit_block": root[i]}
                   for i, key in enumerate(keys)]
    for grouping, blocks in (("shape", shape), ("root_unit", root)):
        comparison[grouping] = {}
        for name, split, overhead in (("single_leaf", False, cost_scc), ("root_split", True, cost_root)):
            actions, h, fits = blocked_actions(costs, trigger, fixed, overhead, blocks, split)
            paid = par2(costs, actions, h)
            result = assessment(costs, actions, paid, blocks)
            result["fit_action_counts"] = fits
            comparison[grouping][name] = result
            for i, row in enumerate(predictions):
                row[f"{grouping}_{name}_action"] = ACTIONS[actions[i]]
                row[f"{grouping}_{name}_par2"] = float(paid[i])
            print(grouping, name, round(result["par2_improvement_pct"], 6), result["solved"],
                  result["paired_group_bootstrap_95_pct"], fits, flush=True)
        for name in ("SCC_original", "SCC_root_guard_original"):
            paid = np.array([float(source[k][name + "_par2"]) for k in keys])
            actions = np.array([ACTIONS.index(source[k][name + "_action"]) for k in keys])
            comparison[grouping][name] = assessment(costs, actions, paid, blocks)
        by_block = []
        for block in np.unique(blocks[trigger]):
            use = trigger & (blocks == block)
            a = np.array([float(source[k]["SCC_root_guard_original_par2"]) for k in keys])
            b = np.array([float(source[k]["SCC_original_par2"]) for k in keys])
            by_block.append({"block": block, "triggered": int(use.sum()), "root_guard_retained": int((use & fixed).sum()),
                             "SCC_original_net_savings_s": float((costs[use, 0] - b[use]).sum()),
                             "SCC_root_guard_net_savings_s": float((costs[use, 0] - a[use]).sum()),
                             "root_guard_rescued": int(((costs[:, 0] == 1200) & (a < 1200) & use).sum())})
        args.out.mkdir(parents=True, exist_ok=True)
        write_csv(args.out / f"{grouping}_trigger_blocks.csv", by_block)

    write_csv(args.out / "predictions.csv", predictions)
    write(args.out / "summary.json", {
        "parents": len(keys), "triggered": int(trigger.sum()), "new_solver_calls": 0,
        "root_inputs_sha256": sha(args.root_results / "predictions.csv"),
        "root_features_sha256": sha(args.root_results / "feature_receipts.jsonl"),
        "analysis_cpu_s": time.process_time() - cpu, "analysis_wall_s": time.monotonic() - start,
        "results": comparison,
    })


if __name__ == "__main__":
    main()
