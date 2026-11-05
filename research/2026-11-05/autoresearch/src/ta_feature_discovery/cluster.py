"""Fit-only ten-feature K-means++/Lloyd diagnostics, without sklearn.

Only complete, eligible fit vectors determine transformations and centers.
Incomplete rows return None rather than receiving an invented cluster/action.
"""
from __future__ import annotations

import hashlib
import itertools

import numpy as np

try:
    from .learning import ACTIONS, PRIMARY_FEATURES, clear_action, feature_value, require_static_ready, validate_rows
except ImportError:  # Direct module use from the source directory.
    from learning import ACTIONS, PRIMARY_FEATURES, clear_action, feature_value, require_static_ready, validate_rows

LOG_FEATURES = frozenset({"s_mean_length", "s_length_std"})


def _raw_vector(row: dict, features: tuple[str, ...]) -> list[float] | None:
    result = []
    for name in features:
        value = feature_value(row, name)
        if value is None or (name in LOG_FEATURES and value < 0):
            return None
        result.append(float(np.log1p(value)) if name in LOG_FEATURES else value)
    return result


def _assign(x: np.ndarray, centers: np.ndarray) -> np.ndarray:
    return ((x[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)


def _kmeans(x: np.ndarray, k: int, seed: int, max_iter: int = 100) -> dict:
    rng = np.random.default_rng(seed)
    chosen = [int(rng.integers(len(x)))]
    centers = [x[chosen[0]].copy()]
    for _ in range(1, k):
        distance = ((x[:, None, :] - np.array(centers)[None, :, :]) ** 2).sum(axis=2).min(axis=1)
        total = float(distance.sum())
        if total > 0:
            selected = int(rng.choice(len(x), p=distance / total))
        else:
            selected = next((i for i in range(len(x)) if i not in chosen), chosen[0])
        chosen.append(selected); centers.append(x[selected].copy())
    centers = np.array(centers)
    previous = None
    for iteration in range(max_iter):
        labels = _assign(x, centers)
        if previous is not None and np.array_equal(labels, previous):
            break
        new_centers = centers.copy()
        for j in range(k):
            members = x[labels == j]
            if len(members):
                new_centers[j] = members.mean(axis=0)
        centers = new_centers
        previous = labels
    labels = _assign(x, centers)
    inertia = float(((x - centers[labels]) ** 2).sum())
    return {"seed": seed, "centers": centers.tolist(), "inertia": inertia,
            "iterations": iteration + 1, "counts": np.bincount(labels, minlength=k).tolist()}


def fit_clusters(fit_rows, k: int = 2, seed: int = 20261104, n_init: int = 10) -> dict:
    rows = validate_rows(fit_rows, fit_only=True)
    require_static_ready(rows)
    if k not in (2, 3) or n_init != 10:
        raise ValueError("frozen clustering permits only k2/k3 and ten initializations")
    features = tuple(PRIMARY_FEATURES)
    vectors = [_raw_vector(row, features) for row in rows]
    complete = [i for i, v in enumerate(vectors) if v is not None]
    model = {"schema": "ta_fit_clusters_v1", "k": k, "features": list(features),
             "log1p_features": sorted(LOG_FEATURES), "seed": seed, "n_init": n_init,
             "fit_parents": len(rows), "fit_complete_parents": len(complete),
             "fit_missing_parents": len(rows) - len(complete),
             "missing_behavior": "unassigned; downstream policy falls back to its fixed action"}
    if len(complete) < k:
        return {**model, "status": "INSUFFICIENT_COMPLETE_FIT", "centers": [], "initializations": []}
    x = np.array([vectors[i] for i in complete], dtype=float)
    median = np.median(x, axis=0)
    q1, q3 = np.quantile(x, (0.25, 0.75), axis=0)
    scale = q3 - q1
    scale[scale == 0] = 1.0
    standardized = (x - median) / scale
    inits = []
    for number in range(n_init):
        actual_seed = int(hashlib.sha256(f"ta-cluster-v1:{seed}:{number}".encode()).hexdigest()[:16], 16)
        inits.append(_kmeans(standardized, k, actual_seed))
    best_number = min(range(n_init), key=lambda i: (inits[i]["inertia"], i))
    best = inits[best_number]
    return {**model, "status": "FITTED", "median": median.tolist(), "scale": scale.tolist(),
            "centers": best["centers"], "inertia": best["inertia"],
            "selected_initialization": best_number,
            "effective_clusters": sum(n > 0 for n in best["counts"]),
            "initializations": inits}


def _validate_model(model: dict) -> None:
    if model.get("schema") != "ta_fit_clusters_v1" or model.get("k") not in (2, 3):
        raise ValueError("unsupported clustering model")
    if tuple(model.get("features", [])) != tuple(PRIMARY_FEATURES):
        raise ValueError("unexpected or forbidden clustering feature")
    if model.get("status") == "FITTED":
        dimensions = len(PRIMARY_FEATURES)
        centers = np.array(model["centers"], dtype=float)
        median = np.array(model["median"], dtype=float)
        scale = np.array(model["scale"], dtype=float)
        if (centers.shape != (model["k"], dimensions) or median.shape != (dimensions,) or
                scale.shape != (dimensions,) or not np.isfinite(centers).all() or
                not np.isfinite(median).all() or not np.isfinite(scale).all() or (scale <= 0).any()):
            raise ValueError("invalid frozen transform or centers")


def assign_clusters(model: dict, rows) -> list[int | None]:
    _validate_model(model)
    rows = validate_rows(rows)
    require_static_ready(rows)
    if model.get("status") != "FITTED":
        return [None] * len(rows)
    center = np.array(model["centers"], dtype=float)
    median = np.array(model["median"], dtype=float)
    scale = np.array(model["scale"], dtype=float)
    result = []
    for row in rows:
        vector = _raw_vector(row, tuple(PRIMARY_FEATURES))
        if vector is None:
            result.append(None)
        else:
            x = (np.array(vector, dtype=float) - median) / scale
            result.append(int(((center - x) ** 2).sum(axis=1).argmin()))
    return result


def _profiles_for_labels(rows: list[dict], labels: list[int | None], k: int, min_cluster_size: int) -> list[dict]:
    profiles = []
    for j in range(k):
        members = [row for row, label in zip(rows, labels) if label == j]
        sums = {a: sum(float(row["costs"][a]) for row in members) for a in ACTIONS}
        preferred = min(ACTIONS, key=lambda a: (sums[a], ACTIONS.index(a))) if members else None
        if members and sums["false"] == sums["true"]:
            preferred = None
        clear = [clear_action(row) for row in members]
        clear_count = sum(action is not None for action in clear)
        quantiles = {}
        for name in PRIMARY_FEATURES:
            available = [feature_value(row, name) for row in members]
            available = [v for v in available if v is not None]
            quantiles[name] = [float(x) for x in np.quantile(available, (0.1, 0.5, 0.9))] if available else None
        statuses_available = all(all(a in row.get("statuses", {}) for a in ACTIONS) for row in members)
        double_timeouts = sum(all(row["statuses"][a] == "TIMEOUT" for a in ACTIONS) for row in members) if statuses_available else None
        profiles.append({
            "cluster": j, "parents": len(members), "groups": len({r["group"] for r in members}),
            "total_cost_s": sums, "mean_cost_s": {a: sums[a] / len(members) if members else None for a in ACTIONS},
            "preferred_action": preferred, "clear_parents": clear_count,
            "clear_counts": {a: clear.count(a) for a in ACTIONS}, "double_timeouts": double_timeouts,
            "preference_supported": len(members) >= min_cluster_size and clear_count >= 6 and preferred is not None,
            "feature_quantiles_10_50_90": quantiles,
        })
    return profiles


def cluster_profiles(model: dict, fit_rows, min_cluster_size: int = 12) -> dict:
    _validate_model(model)
    rows = validate_rows(fit_rows, fit_only=True)
    require_static_ready(rows)
    labels = assign_clusters(model, rows)
    profiles = _profiles_for_labels(rows, labels, model["k"], min_cluster_size)
    consistency = [[] for _ in range(model["k"])]
    if model.get("status") == "FITTED":
        reference = np.array(model["centers"])
        for initial in model["initializations"]:
            centers = np.array(initial["centers"])
            # Align labels only by frozen feature-space centers, never by outcomes.
            mapping = min(itertools.permutations(range(model["k"])),
                          key=lambda p: sum(float(((reference[j] - centers[p[j]]) ** 2).sum()) for j in range(model["k"])))
            trial = {**model, "centers": initial["centers"]}
            trial_labels = assign_clusters(trial, rows)
            inverse = {old: new for new, old in enumerate(mapping)}
            aligned = [None if label is None else inverse[label] for label in trial_labels]
            trial_profiles = _profiles_for_labels(rows, aligned, model["k"], min_cluster_size)
            for j, profile in enumerate(trial_profiles):
                consistency[j].append(profile["preferred_action"])
    for j, profile in enumerate(profiles):
        directions = consistency[j]
        profile["initialization_preferred_actions"] = directions
        profile["preferred_action_agreement"] = (directions.count(profile["preferred_action"]) / len(directions)
                                                 if directions and profile["preferred_action"] is not None else None)
    return {"role": "development_fit", "parents": len(rows), "assigned": sum(x is not None for x in labels),
            "missing": sum(x is None for x in labels), "profiles": profiles,
            "note": "Fit-only descriptive grouping; a cluster is not a validated routing policy."}
