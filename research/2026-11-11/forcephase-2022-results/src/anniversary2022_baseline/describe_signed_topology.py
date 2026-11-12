"""Describe the structure of the 24-cluster candidate on the development cohort."""

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

from .collect_signed_topology import FEATURES
from .structural_clusters import ACTIONS, GROUPS, distances, fit_cluster_actions, kmeans, load, standardize, write_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    args = parser.parse_args()
    keys, _, costs, winners, _, _ = load()
    with (args.results / "feature_receipts.jsonl").open() as stream:
        records = [json.loads(line) for line in stream]
    available = {r["instance_key"]: r["features"] for r in records if r["status"] == "ok"}
    columns = [name for block in FEATURES.values() for name in block]
    weights = np.concatenate([np.full(len(block), 1 / np.sqrt(len(block))) for block in FEATURES.values()])
    indices = [i for i, key in enumerate(keys) if key in available]
    raw = np.array([[available[keys[i]][name] for name in columns] for i in indices])
    cost, winner = costs[indices], winners[indices]
    x, _ = standardize(raw, raw, weights)
    centers = kmeans(x, 24, starts=4)
    labels = distances(x, centers).argmin(axis=1)
    actions = fit_cluster_actions(labels, cost, 24)

    report = []
    population = np.median(x, axis=0)
    for k in range(24):
        mask = labels == k
        if not mask.any():
            continue
        local = cost[mask]
        action = actions[k]
        counts = Counter(winner[mask])
        offset = np.median(x[mask], axis=0) - population
        top = np.argsort(np.abs(offset))[-3:][::-1]
        report.append({
            "cluster": k + 1, "parents": int(mask.sum()), "fit_action": ACTIONS[action],
            "fit_total_PAR2_savings_vs_D": float((local[:, 0] - local[:, action]).sum()),
            **{name + "_clear_winners": counts[name] for name in GROUPS},
            **{name + "_mean_PAR2": float(local[:, j].mean()) for j, name in enumerate(ACTIONS)},
            "top_median_structure_offsets": ", ".join(f"{columns[j]} {offset[j]:+.2f}" for j in top),
            **{name + "_median": float(value) for name, value in zip(columns, np.median(raw[mask], axis=0))},
        })
    write_csv(args.results / "cluster_profiles.csv", report)


if __name__ == "__main__":
    main()
