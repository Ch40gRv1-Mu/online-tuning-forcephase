"""Replay pause, short alternate phase, then resume D within a shared CPU budget."""

import argparse
import json
from pathlib import Path
import time

import numpy as np

from .structural_clusters import ACTIONS, load, summarize_policy, write_csv


PREFIX = (0, 0.1, 1, 10, 60)
PROBE = (0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 40, 80)
OVERHEAD = 0.05


def replay(costs, action, prefix, probe, overhead):
    if action == 0:
        return costs[:, 0]
    baseline = costs[:, 0]
    alternate = costs[:, action]
    alternate_finish = prefix + alternate + overhead
    resume_finish = baseline + probe + overhead
    return np.where(
        baseline <= prefix, baseline,
        np.where((alternate <= probe) & (alternate_finish <= 600), alternate_finish,
                 np.where(resume_finish <= 600, resume_finish, 1200)),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start, cpu_start = time.monotonic(), time.process_time()
    keys, _, costs, _, groups, folds = load()
    candidates = [(0, 0, 0)] + [(a, d, f) for a in (1, 2) for d in PREFIX for f in PROBE]
    predicted_costs = np.array([replay(costs, *spec, OVERHEAD) for spec in candidates]).T
    indices = np.zeros(len(keys), dtype=int)
    chosen = []
    for fold in range(5):
        test = folds == fold
        choice = int(predicted_costs[~test].sum(axis=0).argmin())
        indices[test] = choice
        a, d, f = candidates[choice]
        chosen.append({"fold": fold, "phase": ACTIONS[a], "D_prefix_cpu_s": d, "F_probe_cpu_s": f})
    held_out = predicted_costs[np.arange(len(keys)), indices]
    result = summarize_policy(np.stack([costs[:, 0], held_out], axis=1), np.ones(len(keys), dtype=int), groups)
    del result["actions"]
    result["schedules_by_training_fold"] = chosen
    result["fixed_D_solved"] = int((costs[:, 0] < 1200).sum())
    result["assumed_cpu_overhead_s"] = OVERHEAD
    result["held_out_sensitivity"] = []
    for overhead in (0, 0.01, 0.05, 0.1, 0.5):
        adjusted = np.empty(len(keys))
        for choice in np.unique(indices):
            mask = indices == choice
            adjusted[mask] = replay(costs[mask], *candidates[choice], overhead)
        result["held_out_sensitivity"].append({
            "overhead_s": overhead, "mean_par2": float(adjusted.mean()),
            "solved": int((adjusted < 1200).sum()),
            "improvement_pct": float(100 * (1 - adjusted.sum() / costs[:, 0].sum())),
        })
    best = int(predicted_costs.sum(axis=0).argmin())
    a, d, f = candidates[best]
    result["best_fixed_schedule_in_sample"] = {"phase": ACTIONS[a], "D_prefix_cpu_s": d, "F_probe_cpu_s": f,
                                               "mean_par2": float(predicted_costs[:, best].mean())}
    result.update(parents=len(keys), new_solver_calls=0, elapsed_wall_s=time.monotonic() - start,
                  analysis_CPU_s=time.process_time() - cpu_start)
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", [
        {"instance_key": key, "fold": int(folds[i]), "D_par2": costs[i, 0], "selected_par2": held_out[i]}
        for i, key in enumerate(keys)
    ])
    (args.out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
