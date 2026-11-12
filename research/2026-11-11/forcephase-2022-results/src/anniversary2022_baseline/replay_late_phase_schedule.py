"""Score late alternate-phase slices on the D branch of the frozen SCC rule."""

import argparse
from collections import Counter
from pathlib import Path
import time

import numpy as np

from .common import sha, write
from .score_scc_complement_stump import metrics
from .short_phase_schedule import replay
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


PREFIXES = (120, 180, 240, 300, 360, 420, 480, 540)
SLICES = (30, 60, 90, 120, 180, 240, 300)
DISPATCH_CPU = 0.05


def evaluate(costs, baseline, h, enabled, candidates, dispatch):
    result = [baseline.copy()]
    for action, prefix, length in candidates[1:]:
        raw = replay(costs[enabled], action, prefix, length, dispatch)
        paid = raw + h[enabled]
        selected = baseline.copy()
        selected[enabled] = np.where(paid <= 600, paid, 1200)
        result.append(selected)
    return np.column_stack(result)


def choose_held_out(grid, blocks):
    _, group = np.unique(blocks, return_inverse=True)
    column_total = grid.sum(axis=0)
    choices = np.zeros(len(group), dtype=int)
    for value in np.unique(group):
        use = group == value
        train_total = column_total - grid[use].sum(axis=0)
        best = int(np.argmin(train_total))
        if train_total[0] - train_total[best] > 1e-8:
            choices[use] = best
    return choices


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, _, _ = load()
    frozen_path = DATA / "scc_root_up_20261110/predictions.csv"
    fixed_path = DATA / "scc_width_fixed_20261110/predictions.csv"
    blocks_path = DATA / "scc_blocked_replay_20261110/predictions.csv"
    frozen = {r["instance_key"]: r for r in read_csv(frozen_path)}
    fixed = {r["instance_key"]: r for r in read_csv(fixed_path)}
    blocks = {r["instance_key"]: r for r in read_csv(blocks_path)}
    if set(keys) != set(frozen) or frozen.keys() != fixed.keys() or frozen.keys() != blocks.keys():
        raise ValueError("mismatched complete 2022 cohort")
    h = np.array([float(frozen[k]["old_extractor_cpu_s"]) if frozen[k]["original_scope"] == "True" else 0
                  for k in keys])
    baseline = np.array([float(frozen[k]["SCC_original_par2"]) for k in keys])
    base_actions = np.array([ACTIONS.index(frozen[k]["SCC_original_action"]) for k in keys])
    enabled = base_actions == 0
    morphology = np.array([frozen[k]["shape_block"] for k in keys])
    coarse = np.array([fixed[k]["coarse_cluster_group"] for k in keys])
    dominant = np.array([blocks[k]["root_unit_block"] in ("units:49", "units:56") for k in keys])
    candidates = [(0, 0, 0)] + [(a, d, f) for a in (1, 2) for d in PREFIXES for f in SLICES
                                 if d + f + DISPATCH_CPU <= 600]
    grid = evaluate(costs, baseline, h, enabled, candidates, DISPATCH_CPU)
    costly = evaluate(costs, baseline, h, enabled, candidates, 0.5)
    all_rows = np.arange(len(keys))
    results = {}
    rows = [{"instance_key": key, "SCC_par2": float(baseline[i])} for i, key in enumerate(keys)]
    for name, groups in (("shape", morphology), ("coarse_cluster", coarse)):
        choice = choose_held_out(grid, groups)
        paid = grid[all_rows, choice]
        action = base_actions.copy()
        action[enabled] = np.array([spec[0] for spec in candidates])[choice[enabled]]
        result = metrics(costs, baseline, paid, action, groups, dominant)
        result["choices_by_parent"] = dict(Counter(
            f"{ACTIONS[candidates[c][0]]}/{candidates[c][1]}/{candidates[c][2]}" for c in choice[enabled]
        ))
        result["scheduled_dispatches"] = int(sum(np.sum(
            (choice == c) & enabled & (costs[:, 0] > candidates[c][1])) for c in np.unique(choice) if c))
        result["cpu_startup_sensitivity_0_5"] = metrics(
            costs, baseline, costly[all_rows, choice], action, groups, dominant)["against_SCC"]
        results[name] = result
        for i, row in enumerate(rows):
            row[name + "_candidate"] = int(choice[i])
            row[name + "_par2"] = float(paid[i])
        print(name, result["against_SCC"]["par2_improvement_pct"],
              result["against_SCC"]["paired_group_bootstrap_95_pct"],
              result["incremental_D_timeouts_rescued"], result["incremental_SCC_solves_lost"],
              result["choices_by_parent"], flush=True)
    best_fixed = int(grid.sum(axis=0).argmin())
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", rows)
    write(args.out / "summary.json", {
        "parents": len(keys), "D_branch": int(enabled.sum()), "dispatch_CPU_s_assumed": DISPATCH_CPU,
        "specs": [{"alternate": ACTIONS[a], "D_prefix": d, "alternate_slice": f} for a, d, f in candidates],
        "best_in_sample_index": best_fixed,
        "best_in_sample_increment_s": float((baseline - grid[:, best_fixed]).sum()),
        "input_sha256": {"SCC_replay": sha(frozen_path), "structural_clusters": sha(fixed_path),
                         "root_unit_blocks": sha(blocks_path)},
        "results": results, "new_solver_calls": 0,
        "analysis_cpu_s": time.process_time() - cpu, "analysis_wall_s": time.monotonic() - start,
    })


if __name__ == "__main__":
    main()
