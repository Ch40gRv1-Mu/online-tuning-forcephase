"""Describe CNF clusters and evaluate train-only configuration routing."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "outputs/anniversary2022_baseline"
BASE = ROOT / "work/frozen_policy_replay_20261110/gbd_base.sqlite3"
META = ROOT / "work/expanded_parents/gbd_meta.db"
PREFERENCES = DATA / "vbs_preferences_20261110/all_preferences.csv"
SIGNED = DATA / "positive_binary_replay_20261110/predictions.csv"
SEED = 20261110
N_CLUSTERS = 8
ACTIONS = ("D", "Fplus", "Fminus")
GROUPS = (*ACTIONS, "near_tie", "all_timeout")
FEATURE_GROUPS = (
    ("log_variables", "log_clauses_per_variable"),
    ("log_mean_clause_length", "unit_fraction", "binary_fraction", "ternary_fraction", "long_fraction"),
    ("positive_only_fraction", "negative_only_fraction", "inverse_horn_minus_horn"),
    ("log_variable_degree_cv", "log_components_per_variable"),
)
FEATURES = tuple(name for group in FEATURE_GROUPS for name in group)
WEIGHTS = np.array([1 / math.sqrt(len(group)) for group in FEATURE_GROUPS for _ in group])


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load():
    outcomes = sorted(read_csv(PREFERENCES), key=lambda row: row["instance_key"])
    keys = [row["instance_key"] for row in outcomes]
    assert len(keys) == len(set(keys)) == 4719
    allowed = set(keys)
    fields = "hash,clauses,variables,cls1,cls2,cls3,cls4,cls5,cls6,cls7,cls8,cls9,cls10p,positive,negative,horn,invhorn,vcg_cdegree_mean,vcg_vdegree_mean,vcg_vdegree_variance,ccs"
    with sqlite3.connect(f"file:{BASE}?mode=ro", uri=True) as db:
        base = {key: tuple(map(float, values)) for key, *values in db.execute(f"select {fields} from features")
                if key in allowed}
    with sqlite3.connect(f"file:{META}?mode=ro", uri=True) as db:
        iso = {key: group for key, group in db.execute("select hash,isohash2 from features") if key in allowed}
    assert set(base) == allowed
    vectors = []
    for key in keys:
        m, n, *counts, p, q, h, ih, width, degree, variance, components = base[key]
        empty = m - sum(counts)
        assert empty >= 0 and m > 0 and n > 0
        vectors.append((
            math.log1p(n), math.log1p(m / n), math.log1p(width), counts[0] / m, counts[1] / m,
            counts[2] / m, sum(counts[4:]) / m, (p - empty) / m, (q - empty) / m, (ih - h) / m,
            math.log1p(math.sqrt(variance) / max(degree, 1e-12)), math.log1p(components / n),
        ))
    groups = [iso[key] if iso.get(key) not in (None, "", "empty", "None") else key for key in keys]
    folds = np.array([int(hashlib.sha256(("positive_binary_v1:" + group).encode()).hexdigest(), 16) % 5
                      for group in groups])
    costs = np.array([[float(row[action + "_par2"]) for action in ACTIONS] for row in outcomes])
    winners = np.array([row["preference_group"] for row in outcomes])
    X = np.array(vectors)
    assert np.isfinite(X).all() and np.isfinite(costs).all() and set(winners) == set(GROUPS)
    return keys, X, costs, winners, groups, folds


def standardize(train, test, weights=WEIGHTS):
    low, high = np.quantile(train, [0.01, 0.99], axis=0)
    train = np.clip(train, low, high)
    center = train.mean(axis=0)
    scale = train.std(axis=0)
    scale[scale == 0] = 1
    return (train - center) / scale * weights, (np.clip(test, low, high) - center) / scale * weights


def distances(X, centers):
    return (X * X).sum(axis=1)[:, None] + (centers * centers).sum(axis=1) - 2 * X @ centers.T


def kmeans(X, clusters=N_CLUSTERS, starts=8):
    rng = np.random.default_rng(SEED)
    best = None
    for _ in range(starts):
        centers = [X[rng.integers(len(X))]]
        for _ in range(clusters - 1):
            nearest = np.maximum(distances(X, np.array(centers)).min(axis=1), 0)
            centers.append(X[rng.choice(len(X), p=nearest / nearest.sum())])
        centers = np.array(centers)
        previous = None
        for _ in range(100):
            d = distances(X, centers)
            labels = d.argmin(axis=1)
            if np.array_equal(previous, labels):
                break
            previous = labels
            for k in range(clusters):
                members = X[labels == k]
                centers[k] = members.mean(axis=0) if len(members) else X[d.min(axis=1).argmax()]
        d = distances(X, centers)
        inertia = d.min(axis=1).sum()
        if best is None or inertia < best[0]:
            best = inertia, centers.copy()
    return best[1]


def fit_cluster_actions(labels, costs, clusters=N_CLUSTERS):
    actions = np.zeros(clusters, dtype=int)
    for cluster in range(clusters):
        members = costs[labels == cluster]
        if len(members) >= 30:
            actions[cluster] = members.sum(axis=0).argmin()
    return actions


def fit_stump(X, costs):
    best_savings, best = 0.0, None
    for feature, column in enumerate(X.T):
        for cut in np.unique(np.quantile(column, np.arange(1, 8) / 8)):
            for left in (True, False):
                selected = (column <= cut) == left
                if selected.sum() < 30:
                    continue
                savings = (costs[selected, :1] - costs[selected, 1:]).sum(axis=0)
                action = int(savings.argmax())
                if savings[action] > best_savings:
                    best_savings, best = savings[action], (feature, float(cut), left, action + 1)
    return best


def rank(values):
    _, index, counts = np.unique(values, return_inverse=True, return_counts=True)
    return (np.cumsum(counts) - (counts - 1) / 2)[index]


def correlation(x, y, labels=None):
    x, y = rank(x), rank(y)
    if labels is not None:
        for label in np.unique(labels):
            ix = labels == label
            x[ix] -= x[ix].mean()
            y[ix] -= y[ix].mean()
    if x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def summarize_policy(costs, actions, groups, chosen=None):
    if chosen is None:
        chosen = costs[np.arange(len(costs)), actions]
    baseline = costs[:, 0]
    gain = baseline - chosen
    _, group_index = np.unique(groups, return_inverse=True)
    group_cost = np.bincount(group_index, weights=baseline)
    group_gain = np.bincount(group_index, weights=gain)
    rng = np.random.default_rng(SEED)
    samples = []
    for _ in range(20):
        indices = rng.integers(len(group_cost), size=(100, len(group_cost)))
        samples.extend(group_gain[indices].sum(axis=1) / group_cost[indices].sum(axis=1) * 100)
    return {
        "mean_par2": float(chosen.mean()), "solved": int((chosen < 1200).sum()),
        "par2_improvement_pct": float(gain.sum() / baseline.sum() * 100),
        "paired_group_bootstrap_95_pct": np.quantile(samples, [.025, .975]).tolist(),
        "actions": {action: int((actions == i).sum()) for i, action in enumerate(ACTIONS)},
        "better_than_D_parents": int((gain > 0).sum()), "worse_than_D_parents": int((gain < 0).sum()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start, cpu_start = time.monotonic(), time.process_time()
    keys, X, costs, winners, iso, folds = load()
    scaled, _ = standardize(X, X)
    labels = distances(scaled, kmeans(scaled)).argmin(axis=1)
    assert len(set(labels)) == N_CLUSTERS
    order = sorted(range(N_CLUSTERS), key=lambda k: np.median(X[labels == k, 0]))
    labels = np.array([order.index(k) for k in labels])
    cluster_rows = []
    for k in range(N_CLUSTERS):
        mask = labels == k
        local = costs[mask]
        winner_counts = Counter(winners[mask])
        cluster_rows.append({
            "cluster": k + 1, "parents": int(mask.sum()),
            "median_variables": round(float(np.expm1(np.median(X[mask, 0])))),
            "median_binary_fraction": float(np.median(X[mask, FEATURES.index("binary_fraction")])),
            **{f"{label}_count": winner_counts[label] for label in GROUPS},
            **{f"{action}_mean_par2": float(local[:, i].mean()) for i, action in enumerate(ACTIONS)},
            "best_fixed_action": ACTIONS[local.sum(axis=0).argmin()],
            "best_fixed_vs_D_improvement_pct": float(100 * (1 - local.sum(axis=0).min() / local[:, 0].sum())),
        })

    response = np.log((costs[:, :1] + 1) / (costs[:, 1:] + 1))
    known = {row["instance_key"]: int(row["positive_binary_lower"]) / int(row["binary"])
             for row in read_csv(SIGNED) if int(row["binary"]) and row["positive_binary_lower"] == row["positive_binary_upper"]}
    signed = np.array([known.get(key, np.nan) for key in keys])
    correlations = []
    for name, x in [*zip(FEATURES, X.T), ("positive_binary_fraction_exact_subset", signed)]:
        mask = np.isfinite(x)
        y, groups, baseline = response[mask], labels[mask], costs[mask, 0]
        x = x[mask]
        correlations.append({
            "feature": name, "parents": int(mask.sum()),
            "D_cost_rho": correlation(x, baseline),
            "Fplus_gain_rho": correlation(x, y[:, 0]), "Fminus_gain_rho": correlation(x, y[:, 1]),
            "Fplus_gain_rho_within_cluster": correlation(x, y[:, 0], groups),
            "Fminus_gain_rho_within_cluster": correlation(x, y[:, 1], groups),
        })

    cluster_actions = np.zeros(len(keys), dtype=int)
    stump_actions = np.zeros(len(keys), dtype=int)
    fit_details = []
    for fold in range(5):
        test = folds == fold
        train = ~test
        scaled_train, scaled_test = standardize(X[train], X[test])
        centers = kmeans(scaled_train)
        route = fit_cluster_actions(distances(scaled_train, centers).argmin(axis=1), costs[train])
        cluster_actions[test] = route[distances(scaled_test, centers).argmin(axis=1)]
        stump = fit_stump(X[train], costs[train])
        rule = None
        if stump:
            feature, cut, left, action = stump
            stump_actions[test] = np.where((X[test, feature] <= cut) == left, action, 0)
            rule = {"feature": FEATURES[feature], "cut": cut, "side": "<=" if left else ">", "action": ACTIONS[action]}
        fit_details.append({"fold": fold, "parents": int(test.sum()), "cluster_actions": [ACTIONS[x] for x in route], "stump": rule})

    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "clusters.csv", cluster_rows)
    write_csv(args.out / "correlations.csv", correlations)
    write_csv(args.out / "instances.csv", [
        {"instance_key": key, "cluster": int(labels[i] + 1), "fold": int(folds[i]), "observed_preference": winners[i],
         "cluster_policy": ACTIONS[cluster_actions[i]], "stump_policy": ACTIONS[stump_actions[i]],
         **{action + "_par2": costs[i, j] for j, action in enumerate(ACTIONS)}}
        for i, key in enumerate(keys)
    ])
    result = {
        "parents": len(keys), "iso_groups": len(set(iso)), "winner_counts": dict(Counter(winners)),
        "clusters": cluster_rows, "correlations": correlations, "folds": fit_details,
        "fixed_D": summarize_policy(costs, np.zeros(len(keys), dtype=int), iso),
        "cluster_out_of_fold": summarize_policy(costs, cluster_actions, iso),
        "stump_out_of_fold": summarize_policy(costs, stump_actions, iso),
        "input_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE, META, PREFERENCES, SIGNED)},
        "analysis_CPU_s": time.process_time() - cpu_start, "elapsed_wall_s": time.monotonic() - start,
        "new_solver_calls": 0, "deployment_feature_cost_included": False,
    }
    (args.out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("fixed_D", "cluster_out_of_fold", "stump_out_of_fold", "elapsed_wall_s")}, indent=2))


if __name__ == "__main__":
    main()
