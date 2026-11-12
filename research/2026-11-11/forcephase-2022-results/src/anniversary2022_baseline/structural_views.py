"""Compare predefined CNF feature views and select a view inside training folds."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import numpy as np

from .structural_clusters import ACTIONS, BASE, GROUPS, distances, fit_cluster_actions, kmeans, load, standardize, summarize_policy, write_csv


def features(keys, X):
    fields = ["clauses", *(f"cls{i}" for i in range(1, 10)), "cls10p", "balancecls_mean", "balancecls_variance",
              "balancevars_mean", "balancevars_variance", "vcg_vdegree_entropy", "vcg_cdegree_entropy",
              "vg_degree_mean", "cg_degree_mean", "vg_degree_entropy", "cg_degree_entropy"]
    allowed = set(keys)
    with sqlite3.connect(f"file:{BASE}?mode=ro", uri=True) as db:
        cache = {key: tuple(map(float, row)) for key, *row in db.execute(f"select hash,{','.join(fields)} from features")
                 if key in allowed}
    raw = np.array([cache[key] for key in keys])
    width = raw[:, 1:11] / raw[:, :1]
    empty = np.maximum(0, 1 - width.sum(axis=1))
    arity = np.sqrt(np.column_stack((empty, width)))
    polarity = np.column_stack((X[:, 7:10], raw[:, 11:15]))
    graph = np.column_stack((X[:, 10:], raw[:, 15:17], np.log1p(raw[:, 17:19]), raw[:, 19:21]))
    blocks = {"size": X[:, :2], "width": arity, "sign": polarity, "graph": graph}
    weights = {name: np.full(block.shape[1], 1 / np.sqrt(block.shape[1])) for name, block in blocks.items()}
    blocks["combined"] = np.column_stack(list(blocks.values()))
    weights["combined"] = np.concatenate(list(weights.values()))
    assert all(np.isfinite(block).all() for block in blocks.values())
    return blocks, weights


def predict(X, costs, train, test, weights, k):
    train_x, test_x = standardize(X[train], X[test], weights)
    k = min(k, len(np.unique(train_x, axis=0)))
    centers = kmeans(train_x, k, starts=4)
    train_labels = distances(train_x, centers).argmin(axis=1)
    mapping = fit_cluster_actions(train_labels, costs[train], k)
    return mapping[distances(test_x, centers).argmin(axis=1)]


def describe(X, costs, winners, weights, view, k):
    scaled, _ = standardize(X, X, weights)
    labels = distances(scaled, kmeans(scaled, k, starts=4)).argmin(axis=1)
    action = fit_cluster_actions(labels, costs, k)
    cluster_rows = []
    for cluster in range(k):
        selected = labels == cluster
        local = costs[selected]
        n = len(local)
        if n == 0:
            continue
        counts = Counter(winners[selected])
        cluster_rows.append({
            "view": view, "k": k, "cluster": cluster + 1, "parents": n,
            **{g + "_count": counts[g] for g in GROUPS},
            **{a + "_mean_par2": float(local[:, i].mean()) for i, a in enumerate(ACTIONS)},
            "training_action": ACTIONS[action[cluster]],
        })
    return labels, cluster_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start, cpu_start = time.monotonic(), time.process_time()
    keys, base, costs, winners, groups, folds = load()
    blocks, weights = features(keys, base)
    specs = [(view, k) for view in blocks for k in (12, 24, 48)]
    inner = np.array([int(hashlib.sha256(("structural_views_inner_v1:" + group).encode()).hexdigest(), 16) % 2
                      for group in groups])
    oof_actions = np.zeros((len(keys), len(specs)), dtype=int)
    inner_gain = np.zeros((5, len(specs)))
    variant_rows = []
    cluster_rows = []
    labels = []
    for j, (view, k) in enumerate(specs):
        X, w = blocks[view], weights[view]
        for fold in range(5):
            test = folds == fold
            train = ~test
            oof_actions[test, j] = predict(X, costs, train, test, w, k)
            for partition in (0, 1):
                validation = train & (inner == partition)
                chosen = predict(X, costs, train & ~validation, validation, w, k)
                inner_gain[fold, j] += (costs[validation, 0] - costs[validation, chosen]).sum()
        result = summarize_policy(costs, oof_actions[:, j], groups)
        cluster_labels, description = describe(X, costs, winners, w, view, k)
        cluster_rows.extend(description)
        labels.append(cluster_labels)
        result.update(view=view, k=k,
                      clusters_selecting_F_in_sample=sum(row["training_action"] != "D" for row in description))
        variant_rows.append(result)
        print(f"{view}/{k}: held-out PAR2 gain {result['par2_improvement_pct']:+.4f}%, solved {result['solved']}", flush=True)

    selected = np.zeros(len(keys), dtype=int)
    fold_choices = []
    for fold in range(5):
        candidate = int(inner_gain[fold].argmax())
        test = folds == fold
        if inner_gain[fold, candidate] > 0:
            selected[test] = oof_actions[test, candidate]
            fold_choices.append({"fold": fold, "view": specs[candidate][0], "k": specs[candidate][1],
                                 "inner_gain_s": float(inner_gain[fold, candidate])})
        else:
            fold_choices.append({"fold": fold, "view": "fixed_D"})

    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "clusters.csv", cluster_rows)
    write_csv(args.out / "predictions.csv", [
        {"instance_key": key, "fold": int(folds[i]), "winner": winners[i],
         "nested_action": ACTIONS[selected[i]], "D_par2": costs[i, 0], "selected_par2": costs[i, selected[i]],
         **{f"{view}_{k}_cluster": int(labels[j][i] + 1) for j, (view, k) in enumerate(specs)},
         **{f"{view}_{k}_action": ACTIONS[oof_actions[i, j]] for j, (view, k) in enumerate(specs)}}
        for i, key in enumerate(keys)
    ])
    result = {"parents": len(keys), "variants": variant_rows,
              "nested_view_choice": summarize_policy(costs, selected, groups), "nested_fold_choices": fold_choices,
              "elapsed_wall_s": time.monotonic() - start, "analysis_CPU_s": time.process_time() - cpu_start,
              "new_solver_calls": 0, "feature_cost_included": False}
    (args.out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("nested_view_choice", "nested_fold_choices", "elapsed_wall_s")}, indent=2))


if __name__ == "__main__":
    main()
