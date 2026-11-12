"""Truncate the archived trajectories and test Fplus-first recovery on the width branch."""

import argparse
from collections import Counter
import json
from pathlib import Path
import time

import numpy as np

from .common import sha, write
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


BUDGETS = (60, 120, 300, 600)
SLICES = (30, 60, 90, 120, 180, 240, 300, 360, 420, 480, 540)
OVERHEAD = 0.05
MIN_WIDTH_TRAIN = 32
RNG_SEED = 20261110


def timed_cost(runtime, overhead, budget):
    end = runtime + overhead
    return np.where(end <= budget, end, 2 * budget)


def assess(reference, selected, blocks, budget):
    gain = reference - selected
    _, index = np.unique(blocks, return_inverse=True)
    denom = np.bincount(index, weights=reference)
    by_block = np.bincount(index, weights=gain)
    rng = np.random.default_rng(RNG_SEED)
    samples = []
    for _ in range(20):
        ids = rng.integers(len(denom), size=(100, len(denom)))
        samples.extend(100 * by_block[ids].sum(axis=1) / denom[ids].sum(axis=1))
    solved = selected < 2 * budget
    reference_solved = reference < 2 * budget
    return {
        "reference_mean_PAR2": float(reference.mean()),
        "selected_mean_PAR2": float(selected.mean()),
        "gain_pct": float(100 * gain.sum() / reference.sum()),
        "block_interval_95_pct": np.quantile(samples, [0.025, 0.975]).tolist(),
        "reference_solved": int(reference_solved.sum()),
        "solved": int(solved.sum()),
        "newly_solved": int((solved & ~reference_solved).sum()),
        "lost_solves": int((reference_solved & ~solved).sum()),
    }


def choose(grid, groups, width):
    out = np.zeros(len(groups), dtype=int)
    for block in np.unique(groups[width]):
        train = width & (groups != block)
        if train.sum() < MIN_WIDTH_TRAIN:
            continue
        cost = grid[train].sum(axis=0)
        best = int(cost.argmin())
        if cost[0] - cost[best] > 1e-8:
            out[width & (groups == block)] = best
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    started, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, _, _ = load()
    source = {
        "SCC": DATA / "scc_root_up_20261110/predictions.csv",
        "fixed": DATA / "scc_width_fixed_20261110/predictions.csv",
        "width_costs": DATA / "static_unit_pressure_20261110/feature_receipts.jsonl",
    }
    scc = {r["instance_key"]: r for r in read_csv(source["SCC"])}
    fixed = {r["instance_key"]: r for r in read_csv(source["fixed"])}
    with source["width_costs"].open() as stream:
        features = {r["instance_key"]: r for r in map(json.loads, stream) if r["status"] == "ok"}
    if set(keys) != set(scc) or scc.keys() != fixed.keys() or not features.keys() <= fixed.keys():
        raise ValueError("mismatched 2022 population")
    rows = np.arange(len(keys))
    base = np.array([ACTIONS.index(fixed[k]["frozen_action"]) for k in keys])
    scc_actions = np.array([ACTIONS.index(scc[k]["SCC_original_action"]) for k in keys])
    h_scc = np.array([float(scc[k]["old_extractor_cpu_s"]) if scc[k]["original_scope"] == "True" else 0.0
                      for k in keys])
    h = h_scc + np.array([features[k]["feature_cpu_s"] if k in features and scc_actions[i] == 0 else 0.0
                          for i, k in enumerate(keys)])
    fine = np.array([scc[k]["shape_block"] for k in keys])
    coarse = np.array([fixed[k]["coarse_cluster_group"] for k in keys])
    width = base == 1
    if width.sum() != 259:
        raise ValueError("unexpected width branch")
    baseline = timed_cost(costs[rows, base], h, 600)
    if not np.allclose(baseline, [float(fixed[k]["frozen_par2"]) for k in keys], rtol=0, atol=1e-10):
        raise ValueError("frozen T600 replay does not reproduce")
    budgets = {}
    for budget in BUDGETS:
        control = timed_cost(costs[:, 0], 0, budget)
        scc_cost = timed_cost(costs[rows, scc_actions], h_scc, budget)
        paid = timed_cost(costs[rows, base], h, budget)
        budgets[str(budget)] = {"vs_D": assess(control, paid, fine, budget),
                               "vs_SCC": assess(scc_cost, paid, fine, budget)}
        print("cutoff", budget, budgets[str(budget)]["vs_D"], flush=True)

    def options(startup):
        choices = [baseline]
        for cutoff in SLICES:
            paid = baseline.copy()
            f, d = costs[width, 1], costs[width, 0]
            direct = (f <= cutoff) & (f + h[width] <= 600)
            fallback = timed_cost(d, h[width] + cutoff + startup, 600)
            paid[width] = np.where(direct, f + h[width], fallback)
            choices.append(paid)
        return np.column_stack(choices)

    grid = options(OVERHEAD)
    slower = options(0.5)
    results = {}
    predictions = [{"instance_key": k, "Fplus_width_branch": bool(width[i]),
                    "baseline_PAR2": float(baseline[i])} for i, k in enumerate(keys)]
    for name, groups in (("fine_shape", fine), ("coarse_cluster", coarse)):
        selected = choose(grid, groups, width)
        scored = assess(baseline, grid[rows, selected], groups, 600)
        scored["slice_by_width_parent"] = dict(Counter(
            str(SLICES[i - 1]) if i else "full_Fplus" for i in selected[width]))
        scored["startup_sensitivity_0_5"] = assess(baseline, slower[rows, selected], groups, 600)
        results[name] = scored
        for i, r in enumerate(predictions):
            r[name + "_slice_index"] = int(selected[i])
            r[name + "_PAR2"] = float(grid[i, selected[i]])
        print(name, scored["gain_pct"], scored["block_interval_95_pct"],
              scored["newly_solved"], scored["lost_solves"], scored["slice_by_width_parent"], flush=True)
    best = int(grid.sum(axis=0).argmin())
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", predictions)
    write(args.out / "summary.json", {
        "parents": len(keys), "width_branch_parents": int(width.sum()),
        "budgets": budgets, "width_recovery": results, "Fplus_slices": SLICES,
        "in_sample_best_Fplus_slice": SLICES[best - 1] if best else "full_Fplus",
        "in_sample_best_savings_s": float((baseline - grid[:, best]).sum()),
        "dispatch_CPU_s_assumed": OVERHEAD, "input_sha256": {name: sha(path) for name, path in source.items()},
        "new_solver_calls": 0, "analysis_CPU_s": time.process_time() - cpu,
        "elapsed_wall_s": time.monotonic() - started,
    })


if __name__ == "__main__":
    main()
