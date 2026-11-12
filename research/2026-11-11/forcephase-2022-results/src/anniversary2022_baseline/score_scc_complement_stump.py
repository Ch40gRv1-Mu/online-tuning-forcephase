"""Fit a paid one-threshold add-on to the frozen 2022 SCC policy by structural holdout."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time

import numpy as np

from .common import sha, write
from .phase_rule_2022 import SCC_CUT, WIDTH_CUT, choose_action
from .score_scc_root_guard import par2
from .structural_clusters import ACTIONS, DATA, load, read_csv, summarize_policy, write_csv


FEATURES = {
    "signed_histogram": ("pure_positive_share", "pure_negative_share", "raw_binary_share", "raw_mean_width"),
    "static_pressure": ("aligned_unit_contrast", "opposed_unit_contrast", "conflict_contrast", "unit_pressure"),
}
QUANTILES = (0.1, 0.25, 0.5, 0.75, 0.9)
MIN_SWITCH = 32
MIN_SWITCH_BLOCKS = 4


def fit_stump(values, gain, block_ids, acquisition, robust, allow_switch=None):
    """Fit a switch leaf with an all-D default and paid acquisition on eligible rows."""
    selected = None
    best = 0.0
    cost_by_block = np.bincount(block_ids, weights=acquisition)
    fixed_cost = acquisition.sum()
    allow_switch = np.ones(len(values), dtype=bool) if allow_switch is None else allow_switch
    if allow_switch.sum() < MIN_SWITCH:
        return None
    for j, column in enumerate(values.T):
        for threshold in np.unique(np.quantile(column[allow_switch], QUANTILES)):
            lower = column <= threshold
            for left in (True, False):
                use = (lower if left else ~lower) & allow_switch
                if use.sum() < MIN_SWITCH:
                    continue
                blocks = block_ids[use]
                if len(np.unique(blocks)) < MIN_SWITCH_BLOCKS:
                    continue
                for action in (1, 2):
                    savings = gain[use, action]
                    total = savings.sum() - fixed_cost
                    if total <= best:
                        continue
                    if robust:
                        by_block = np.bincount(blocks, weights=savings, minlength=len(cost_by_block)) - cost_by_block
                        total -= max(0, by_block.max())
                    if total > best:
                        best = total
                        selected = j, float(threshold), left, action
    return selected


def replay(values, eligible, costs, base_action, h_scc, h_add, block_index, robust, support_index=None,
           allow_switch=None):
    baseline = par2(costs, base_action, h_scc)
    charged_D = par2(costs, base_action, h_scc + h_add)
    acquisition = charged_D - baseline
    gain = np.column_stack([charged_D - par2(costs, np.full(len(costs), a, dtype=int), h_scc + h_add)
                            for a in range(3)])
    actions = base_action.copy()
    overhead = h_scc.copy()
    choices = {}
    support_index = block_index if support_index is None else support_index
    allow_switch = eligible if allow_switch is None else allow_switch
    for block in np.unique(block_index[eligible]):
        test = eligible & (block_index == block)
        train = eligible & (block_index != block)
        rule = fit_stump(values[train], gain[train], support_index[train], acquisition[train], robust,
                         allow_switch[train])
        choices[int(block)] = rule
        if rule is not None:
            j, threshold, left, action = rule
            switch = test & allow_switch & ((values[:, j] <= threshold) == left)
            actions[switch] = action
            overhead[test] += h_add[test]
    return actions, overhead, choices


def metrics(costs, base, selected, actions, blocks, dominant):
    reference = costs.copy()
    reference[:, 0] = base
    gain = base - selected
    _, i = np.unique(blocks, return_inverse=True)
    block_gain = np.bincount(i, weights=gain)
    return {
        "against_D": summarize_policy(costs, actions, blocks, chosen=selected),
        "against_SCC": summarize_policy(reference, actions, blocks, chosen=selected),
        "incremental_D_timeouts_rescued": int(((base == 1200) & (selected < 1200)).sum()),
        "incremental_SCC_solves_lost": int(((base < 1200) & (selected == 1200)).sum()),
        "incremental_gain_s": float(gain.sum()),
        "incremental_gain_outside_dominant_38_s": float(gain[~dominant].sum()),
        "positive_gain_blocks": int((block_gain > 1e-8).sum()),
        "negative_gain_blocks": int((block_gain < -1e-8).sum()),
        "gain_after_removing_largest_gain_block_s": float(gain.sum() - max(0, block_gain.max())),
    }


def fixed_and_coarse(keys, costs, base_action, baseline, h_scc, h_add, eligible, blocks, dominant, widths):
    original_path = DATA / "scc_demand_transfer_20261110/predictions.csv"
    structural_path = DATA / "structural_clusters_20261110/instances.csv"
    original = {r["instance_key"]: r for r in read_csv(original_path)}
    structural = {r["instance_key"]: r for r in read_csv(structural_path)}
    if set(original) != set(keys) or set(structural) != set(keys):
        raise ValueError("incomplete original scores or structural clusters")
    scc_scores = [float(original[k]["scc_demand_share"]) if original[k]["newly_covered"] == "False" and
                  original[k]["extracted"] == "True" else None for k in keys]
    if [choose_action(value) for value in scc_scores] != [ACTIONS[i] for i in base_action]:
        raise ValueError("frozen SCC stage does not reproduce")
    actions = np.array([ACTIONS.index(choose_action(scc_scores[i], widths[i] if eligible[i] else None))
                        for i in range(len(keys))])
    fixed = par2(costs, actions, h_scc + h_add)
    results = {"fixed_5_73": metrics(costs, baseline, fixed, actions, blocks, dominant)}
    results["fixed_5_73"]["startup_cost_sensitivity"] = [
        {"extra_CPU_s_per_acquisition": cost,
         **metrics(costs, baseline, par2(costs, actions, h_scc + h_add + cost * eligible),
                   actions, blocks, dominant)["against_SCC"]}
        for cost in (0.05, 0.5)
    ]
    rows = [{"instance_key": k, "frozen_action": ACTIONS[actions[i]], "frozen_par2": float(fixed[i]),
             "SCC_par2": float(baseline[i]), "D_par2": float(costs[i, 0])} for i, k in enumerate(keys)]
    groups = {"coarse_cluster": np.array([structural[k]["cluster"] for k in keys]),
              "variable_octave": np.array([block.split("/")[0] for block in blocks])}
    _, support = np.unique(blocks, return_inverse=True)
    for name, coarse in groups.items():
        _, group_index = np.unique(coarse, return_inverse=True)
        learned, h, choices = replay(widths[:, None], eligible, costs, base_action, h_scc, h_add,
                                     group_index, False, support_index=support)
        selected = par2(costs, learned, h)
        result = metrics(costs, baseline, selected, learned, coarse, dominant)
        result["held_rules"] = {coarse[group_index == group][0]:
                                {"threshold": rule[1], "side": "<=" if rule[2] else ">", "action": ACTIONS[rule[3]]}
                                if rule else None for group, rule in choices.items()}
        result["additional_switches"] = int((learned != base_action).sum())
        results[name] = result
        for i, row in enumerate(rows):
            row[name + "_group"] = coarse[i]
            row[name + "_action"] = ACTIONS[learned[i]]
            row[name + "_par2"] = float(selected[i])
    for name, result in results.items():
        print(name, "gain vs SCC", result["against_SCC"]["par2_improvement_pct"],
              result["against_SCC"]["paired_group_bootstrap_95_pct"],
              "gain vs D", result["against_D"]["par2_improvement_pct"],
              "solved", result["against_D"]["solved"], flush=True)
    return rows, results, {"original_SCC_scores": sha(original_path), "coarse_cluster_groups": sha(structural_path)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fixed-validation", action="store_true")
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, _, _ = load()
    scc_path = DATA / "scc_root_up_20261110/predictions.csv"
    block_path = DATA / "scc_blocked_replay_20261110/predictions.csv"
    feat_path = DATA / "static_unit_pressure_20261110/feature_receipts.jsonl"
    scc = {r["instance_key"]: r for r in read_csv(scc_path)}
    block_rows = {r["instance_key"]: r for r in read_csv(block_path)}
    with feat_path.open() as stream:
        measured = {r["instance_key"]: r for r in map(json.loads, stream)}
    if set(keys) != set(scc) or scc.keys() != block_rows.keys() or not set(measured) <= set(keys):
        raise ValueError("invalid full-cohort identity")
    blocks = np.array([block_rows[k]["shape_block"] for k in keys])
    if not np.array_equal(blocks, [scc[k]["shape_block"] for k in keys]):
        raise ValueError("mismatched frozen structural blocks")
    dominant = np.array([block_rows[k]["root_unit_block"] in ("units:49", "units:56") for k in keys])
    _, block_index = np.unique(blocks, return_inverse=True)
    base_action = np.array([ACTIONS.index(scc[k]["SCC_original_action"]) for k in keys])
    h_scc = np.array([float(scc[k]["old_extractor_cpu_s"]) if scc[k]["original_scope"] == "True" else 0
                      for k in keys])
    baseline = par2(costs, base_action, h_scc)
    if not np.allclose(baseline, [float(scc[k]["SCC_original_par2"]) for k in keys], rtol=0, atol=1e-10):
        raise ValueError("frozen SCC replay does not reproduce")
    eligible = np.array([base_action[i] == 0 and measured.get(k, {}).get("status") == "ok"
                         for i, k in enumerate(keys)])
    h_add = np.array([measured[k]["feature_cpu_s"] if eligible[i] else 0.0 for i, k in enumerate(keys)])
    if (int(eligible.sum()), int((base_action != 0).sum()), int(dominant.sum())) != (2589, 254, 38):
        raise ValueError("unexpected switch or feature coverage")
    if not np.all(np.isfinite(h_add) & (h_add >= 0)):
        raise ValueError("invalid feature cost")

    identities = {"root_replay": sha(scc_path), "block_assignments": sha(block_path), "signed_receipts": sha(feat_path)}
    if args.fixed_validation:
        widths = np.array([measured[k]["features"]["raw_mean_width"] if eligible[i] else 0.0
                           for i, k in enumerate(keys)])
        rows, results, additional = fixed_and_coarse(keys, costs, base_action, baseline, h_scc, h_add,
                                                      eligible, blocks, dominant, widths)
        args.out.mkdir(parents=True, exist_ok=False)
        write_csv(args.out / "predictions.csv", rows)
        write(args.out / "summary.json", {"parents": len(keys), "thresholds": {"SCC": SCC_CUT, "width": WIDTH_CUT},
              "inputs_sha256": identities | additional, "new_solver_calls": 0, "new_feature_calls": 0,
              "analysis_cpu_s": time.process_time() - cpu, "analysis_wall_s": time.monotonic() - start,
              "policies": results})
        return

    results = {}
    rules = []
    rows = [{"instance_key": k, "shape_block": blocks[i], "eligible_addon": bool(eligible[i]),
             "base_action": ACTIONS[base_action[i]], "base_par2": baseline[i]} for i, k in enumerate(keys)]
    for view, names in FEATURES.items():
        values = np.array([[measured[k]["features"][name] if eligible[i] else 0.0 for name in names]
                           for i, k in enumerate(keys)])
        if not np.isfinite(values).all():
            raise ValueError("invalid measured features")
        for robust in (False, True):
            label = view + ("_block_guard" if robust else "")
            actions, h, choices = replay(values, eligible, costs, base_action, h_scc, h_add, block_index, robust)
            selected = par2(costs, actions, h)
            result = metrics(costs, baseline, selected, actions, blocks, dominant)
            result.update(additional_feature_cpu_s=float((h - h_scc).sum()),
                          additional_switches=int((actions != base_action).sum()),
                          held_blocks_with_rule=sum(rule is not None for rule in choices.values()))
            result["selected_rules_by_held_block"] = dict(Counter(
                (names[r[0]] + "/" + ACTIONS[r[3]]) if r else "keep_SCC" for r in choices.values()
            ))
            results[label] = result
            for i, row in enumerate(rows):
                row[label + "_action"] = ACTIONS[actions[i]]
                row[label + "_par2"] = selected[i]
            for block, rule in choices.items():
                rules.append({"policy": label, "held_block": blocks[block_index == block][0],
                              "feature": names[rule[0]] if rule else "",
                              "threshold": rule[1] if rule else "",
                              "side": ("<=" if rule[2] else ">") if rule else "",
                              "action": ACTIONS[rule[3]] if rule else "D"})
            print(f"{label}: {result['against_SCC']['par2_improvement_pct']:+.6f}% vs SCC, "
                  f"solved {result['against_SCC']['solved']}, {result['additional_switches']} new switches",
                  flush=True)
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", rows)
    write_csv(args.out / "training_rules.csv", rules)
    write(args.out / "summary.json", {
        "parents": len(keys), "eligible_addon": int(eligible.sum()), "frozen_scc_switches": int((base_action != 0).sum()),
        "oracle_headroom_on_eligible_s": float((costs[eligible, 0] - costs[eligible].min(axis=1)).sum()),
        "inputs_sha256": identities,
        "new_solver_calls": 0, "new_feature_calls": 0, "analysis_cpu_s": time.process_time() - cpu,
        "analysis_wall_s": time.monotonic() - start, "policies": results,
    })


if __name__ == "__main__":
    main()
