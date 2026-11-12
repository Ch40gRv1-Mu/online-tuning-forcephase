"""Replay a conservative nearest-structure selector on held-out folds."""

import argparse
import json
from pathlib import Path
import time

import numpy as np

from .structural_clusters import ACTIONS, distances, load, standardize, summarize_policy, write_csv


def predict(train, test, costs):
    savings = costs[:, :1] - costs[:, 1:]
    actions = []
    support = []
    for block in np.array_split(test, (len(test) + 127) // 128):
        d = np.maximum(distances(block, train), 0)
        boundary = np.partition(d, 31, axis=1)[:, 31]
        for row, cutoff in zip(d, boundary):
            local = savings[row <= cutoff + 1e-12]
            mean = local.mean(axis=0)
            lower = mean - 1.64 * local.std(axis=0, ddof=1) / np.sqrt(len(local))
            eligible = (mean >= 30) & ((local > 0).sum(axis=0) >= 8) & (lower > 0)
            actions.append(int(np.where(eligible, lower, -np.inf).argmax()) + 1 if eligible.any() else 0)
            support.append(len(local))
    return np.array(actions), np.array(support)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start, cpu_start = time.monotonic(), time.process_time()
    keys, X, costs, winners, groups, folds = load()
    actions = np.zeros(len(keys), dtype=int)
    support = np.zeros(len(keys), dtype=int)
    by_fold = []
    for fold in range(5):
        test = folds == fold
        train, held_out = standardize(X[~test], X[test])
        actions[test], support[test] = predict(train, held_out, costs[~test])
        by_fold.append(summarize_policy(costs[test], actions[test], np.array(groups)[test]))
    result = summarize_policy(costs, actions, groups)
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", [
        {"instance_key": key, "fold": int(folds[i]), "neighbors": int(support[i]),
         "action": ACTIONS[actions[i]], "preference_group": winners[i], "D_par2": costs[i, 0],
         "selected_par2": costs[i, actions[i]]}
        for i, key in enumerate(keys)
    ])
    result.update(by_fold=by_fold, parents=len(keys), analysis_CPU_s=time.process_time() - cpu_start,
                  elapsed_wall_s=time.monotonic() - start, new_solver_calls=0, feature_cost_included=False)
    (args.out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
