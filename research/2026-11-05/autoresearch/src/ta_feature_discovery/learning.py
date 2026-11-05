"""Bounded fit-only cost trees and development-only paired evaluation.

TA wall seconds are the prediction target. Feature CPU is reported separately,
never silently added to wall time from another machine. This module performs
no file I/O and cannot load protected data on its own.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from typing import Any, Iterable

import numpy as np

T = 5000.0
TIMEOUT_COST = 2 * T
ACTIONS = ("false", "true")
FIT_ROLE = "development_fit"
FEEDBACK_ROLE = "development_feedback"
PRIMARY_FEATURES = (
    "s_mean_length", "s_length_std", "s_binary_fraction", "s_long_fraction",
    "s_positive_fraction", "s_mean_polarity_imbalance",
    "g_cycle_excess_per_incidence", "g_leaf_variable_fraction",
    "g_largest_component_fraction", "g_gate_motif_fraction",
)
ALLOWED_FEATURES = frozenset(PRIMARY_FEATURES) | frozenset({
    "g_components", "g_cycle_excess", "g_degree_cv", "g_degree_entropy_normalized",
    "g_degree_max", "g_degree_mean", "g_degree_p50", "g_degree_p90",
    "g_degree_two_fraction", "g_gate_motifs_exact", "s_antihorn_fraction",
    "s_clauses", "s_cv_ratio", "s_empty_fraction", "s_header_variables",
    "s_horn_fraction", "s_jw_positive_fraction", "s_log_clauses",
    "s_log_variables", "s_max_length", "s_pure_variable_fraction",
    "s_ternary_fraction", "s_unit_fraction", "s_variables",
    "c_glue_mean", "c_glue_low_frac", "x_glue_ratio", "c_minsize_mean",
    "x_level_avg", "c_backjump_mean",
})
QUANTILES = tuple(i / 8 for i in range(1, 8))
DYNAMIC_FEATURES = frozenset({"c_glue_mean", "c_glue_low_frac", "x_glue_ratio",
                              "c_minsize_mean", "x_level_avg", "c_backjump_mean"})


def _number(value: Any) -> float | None:
    if isinstance(value, (bool, str)) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def cost_for_result(status: str, wall_time_s: float) -> float:
    """Frozen status-based score; late reported successes remain visible."""
    if status == "TIMEOUT":
        return TIMEOUT_COST
    wall = _number(wall_time_s)
    if status not in ("SAT", "UNSAT") or wall is None or wall < 0:
        raise ValueError("unsupported result or invalid wall time")
    return wall


def validate_rows(rows: Iterable[dict], *, fit_only: bool = False) -> list[dict]:
    rows = list(rows)
    allowed = {FIT_ROLE} if fit_only else {FIT_ROLE, FEEDBACK_ROLE}
    seen = set()
    for row in rows:
        if row.get("role") not in allowed:
            raise ValueError("protected or unsupported role; gate/test is forbidden")
        if not isinstance(row.get("id"), str) or row["id"] in seen:
            raise ValueError("missing/duplicate parent identifier")
        seen.add(row["id"])
        if not isinstance(row.get("group"), str) or not row["group"]:
            raise ValueError("missing equivalence group")
        if not isinstance(row.get("features", {}), dict):
            raise ValueError("features must be a numeric mapping")
        for action in ACTIONS:
            value = _number(row.get("costs", {}).get(action))
            if value is None or value < 0:
                raise ValueError("invalid TA cost")
            status = row.get("statuses", {}).get(action)
            if status is not None:
                if status not in ("SAT", "UNSAT", "TIMEOUT"):
                    raise ValueError("unknown reported status")
                if status == "TIMEOUT" and value != TIMEOUT_COST:
                    raise ValueError("TIMEOUT must retain the frozen 10000 score")
                wall = row.get("wall_times", {}).get(action)
                if status != "TIMEOUT" and wall is not None:
                    expected = cost_for_result(status, wall)
                    if not math.isclose(value, expected, rel_tol=1e-12, abs_tol=1e-9):
                        raise ValueError("reported success cost differs from source wall time")
        reported = {row.get("statuses", {}).get(a) for a in ACTIONS}
        if "SAT" in reported and "UNSAT" in reported:
            raise ValueError("contradictory reported answers for one formula")
        cpu = row.get("feature_cpu_s")
        if cpu is not None and (_number(cpu) is None or float(cpu) < 0):
            raise ValueError("invalid feature CPU accounting")
    return rows


def require_static_ready(rows: Iterable[dict]) -> None:
    if any(row.get("feature_status") == "PENDING" for row in rows):
        raise ValueError("static features are PENDING; partial scoring is forbidden")
    if any(row.get("dynamic_status") == "PENDING" for row in rows):
        raise ValueError("dynamic tasks are PENDING; partial scoring is forbidden")


def validate_development_payload(payload: dict, *, require_static: bool = True) -> list[dict]:
    """Caller-facing barrier before splitting the shared development artifact."""
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError("invalid development payload")
    rows = validate_rows(payload["rows"])
    if "dynamic_complete" in payload and payload["dynamic_complete"] is not True:
        raise ValueError("dynamic stage is incomplete; partial feedback is forbidden")
    if require_static:
        if payload.get("static_complete") is not True:
            raise ValueError("static_complete is false; full feature analysis is not ready")
        require_static_ready(rows)
    return rows


def baseline_and_oracle(fit_rows: Iterable[dict]) -> dict:
    """Label-only fit screen, explicitly permitted before features finish."""
    rows = validate_rows(fit_rows, fit_only=True)
    if not rows:
        raise ValueError("fit population is empty")
    costs = _costs(rows)
    sums = costs.sum(axis=0)
    chosen = int(sums.argmin())
    total = float(sums[chosen])
    oracle = float(costs.min(axis=1).sum())
    ratio = _ratio(oracle, total)
    return {"role": FIT_ROLE, "parents": len(rows),
            "baseline_action": ACTIONS[chosen], "constant_total_cost_s": {
                action: float(sums[i]) for i, action in enumerate(ACTIONS)},
            "baseline_total_cost_s": total, "oracle_total_cost_s": oracle,
            "oracle_relative_improvement": None if ratio is None else 1 - ratio,
            "clear_parents": sum(clear_action(row) is not None for row in rows),
            "features_used": False, "cost_units": "TA wall seconds"}


def feature_value(row: dict, name: str) -> float | None:
    if not row.get("eligible", True):
        return None
    features = row.get("features", {})
    if name == "g_gate_motif_fraction" and features.get("g_gate_motifs_exact") == 0:
        return None
    return _number(features.get(name))


def _costs(rows: list[dict]) -> np.ndarray:
    return np.array([[float(r["costs"][a]) for a in ACTIONS] for r in rows], dtype=float)


def _action_index(action: str) -> int:
    if action not in ACTIONS:
        raise ValueError("unsupported action")
    return ACTIONS.index(action)


def _used_features(node: dict) -> set[str]:
    if "action" in node:
        return set()
    return {node["feature"]} | _used_features(node["left"]) | _used_features(node["right"])


def validate_policy(policy: dict) -> None:
    if policy.get("schema") != "ta_cost_tree_v1":
        raise ValueError("unsupported policy schema")
    _action_index(policy.get("baseline_action"))

    def visit(node: dict, depth: int) -> None:
        if not isinstance(node, dict):
            raise ValueError("invalid node")
        if "action" in node:
            if set(node) != {"action"}:
                raise ValueError("invalid leaf fields")
            _action_index(node["action"])
            return
        if depth >= 2 or set(node) != {"feature", "threshold", "left", "right"}:
            raise ValueError("invalid tree shape/depth")
        if node["feature"] not in ALLOWED_FEATURES or _number(node["threshold"]) is None:
            raise ValueError("forbidden feature or invalid threshold")
        visit(node["left"], depth + 1)
        visit(node["right"], depth + 1)

    visit(policy.get("tree"), 0)
    used = _used_features(policy["tree"])
    fallback = policy.get("fallback_policy")
    if fallback is not None:
        if fallback.get("fallback_policy") is not None:
            raise ValueError("nested dynamic fallbacks are forbidden")
        validate_policy(fallback)
        fallback_used = _used_features(fallback["tree"])
        if len(fallback_used) > 1 or fallback_used & DYNAMIC_FEATURES:
            raise ValueError("frozen fallback must use at most one static feature")
        if "action" not in fallback["tree"] and any("action" not in fallback["tree"][side] for side in ("left", "right")):
            raise ValueError("frozen static fallback must have depth at most one")
        required = policy.get("required_dynamic_features")
        if not isinstance(required, list) or len(required) != 1 or required[0] not in DYNAMIC_FEATURES:
            raise ValueError("one declared dynamic field is required")
        if not (used & DYNAMIC_FEATURES) <= set(required):
            raise ValueError("tree uses an undeclared dynamic field")
        used |= fallback_used | set(required)
    if len(used) > 2:
        raise ValueError("policy exceeds the two-feature capacity")


def fit_policy(
    fit_rows: Iterable[dict], allowed_feature_subset: Iterable[str] | None = None,
    max_depth: int = 2, min_leaf: int = 12,
    min_relative_improvement: float = 0.01,
    fallback_policy: dict | None = None,
) -> dict:
    """Fit bounded trees globally, including interactions with a neutral root.

    Every split uses one of seven full-fit quantiles. At depth two, enumerate
    each root and one optional additional feature shared across its children.
    Missing values use the fit-best constant unless an explicit frozen static
    fallback is provided. Dynamic candidates and their fallback share a total
    capacity of two distinct numerical features.
    """
    rows = validate_rows(fit_rows, fit_only=True)
    require_static_ready(rows)
    if not rows:
        raise ValueError("fit population is empty")
    if max_depth not in (0, 1, 2) or not isinstance(min_leaf, int) or min_leaf < 1:
        raise ValueError("invalid capacity")
    if not 0 <= min_relative_improvement < 1:
        raise ValueError("invalid improvement threshold")
    names = list(dict.fromkeys(PRIMARY_FEATURES if allowed_feature_subset is None else allowed_feature_subset))
    if any(name not in ALLOWED_FEATURES for name in names):
        raise ValueError("forbidden feature requested")
    c = _costs(rows)
    baseline_index = int(c.sum(axis=0).argmin())
    baseline_action = ACTIONS[baseline_index]
    base_total = float(c[:, baseline_index].sum())
    fallback_indices = np.full(len(rows), baseline_index, dtype=int)
    active = np.ones(len(rows), dtype=bool)
    required_dynamic = []
    if fallback_policy is not None:
        validate_policy(fallback_policy)
        if fallback_policy.get("fallback_policy") is not None:
            raise ValueError("nested fallback is forbidden")
        fallback_names = _used_features(fallback_policy["tree"])
        if "action" not in fallback_policy["tree"] and any("action" not in fallback_policy["tree"][side] for side in ("left", "right")):
            raise ValueError("frozen static fallback must have depth at most one")
        required_dynamic = sorted(set(names) & DYNAMIC_FEATURES)
        if (len(fallback_names) > 1 or fallback_names & DYNAMIC_FEATURES or
                len(required_dynamic) != 1 or len(set(names) | fallback_names) > 2):
            raise ValueError("dynamic candidate plus frozen static fallback exceeds capacity")
        fallback_indices = np.array([_action_index(_predict_one(fallback_policy, r)[0]) for r in rows])
        active = np.array([r.get("dynamic_status") == "COMPLETE" and
                           all(feature_value(r, name) is not None for name in required_dynamic)
                           for r in rows])
        base_total = float(c[np.arange(len(rows)), fallback_indices].sum())
    fallback_costs = c[np.arange(len(rows)), fallback_indices]
    values = {name: np.array([
        np.nan if feature_value(r, name) is None else feature_value(r, name) for r in rows
    ], dtype=float) for name in names}
    thresholds = {name: np.unique(np.quantile(v[np.isfinite(v)], QUANTILES))
                  if np.isfinite(v).any() else np.array([], dtype=float)
                  for name, v in values.items()}
    tolerance = 1e-10

    def leaf(mask: np.ndarray) -> tuple[dict, float]:
        sums = c[mask].sum(axis=0)
        action = int(sums.argmin()) if mask.any() else baseline_index
        return {"action": ACTIONS[action]}, float(sums[action])

    def child(mask: np.ndarray, features: tuple[str, ...]) -> tuple[dict, float]:
        best_node, best_cost = leaf(mask)
        leaf_cost = best_cost
        for name in features:
            observed = mask & np.isfinite(values[name])
            missing_cost = float(fallback_costs[mask & ~observed].sum())
            for threshold in thresholds[name]:
                left = observed & (values[name] <= threshold)
                right = observed & ~left
                if left.sum() < min_leaf or right.sum() < min_leaf:
                    continue
                lnode, lcost = leaf(left)
                rnode, rcost = leaf(right)
                score = lcost + rcost + missing_cost
                if score < best_cost - tolerance and score <= leaf_cost * (1 - min_relative_improvement):
                    best_cost = score
                    best_node = {"feature": name, "threshold": float(threshold),
                                 "left": lnode, "right": rnode}
        return best_node, best_cost

    tree = json.loads(json.dumps(fallback_policy["tree"])) if fallback_policy is not None else {"action": baseline_action}
    total = base_total
    if max_depth:
        for root_name in names:
            observed = active & np.isfinite(values[root_name])
            missing_cost = float(fallback_costs[~observed].sum())
            for threshold in thresholds[root_name]:
                left = observed & (values[root_name] <= threshold)
                right = observed & ~left
                if left.sum() < min_leaf or right.sum() < min_leaf:
                    continue
                extra_choices = names if max_depth == 2 else [None]
                for extra in extra_choices:
                    permitted = tuple(dict.fromkeys([root_name, extra])) if extra is not None else ()
                    if max_depth == 2:
                        lnode, lcost = child(left, permitted)
                        rnode, rcost = child(right, permitted)
                    else:
                        lnode, lcost = leaf(left)
                        rnode, rcost = leaf(right)
                    score = missing_cost + lcost + rcost
                    if score < total - tolerance and score <= base_total * (1 - min_relative_improvement):
                        tree = {"feature": root_name, "threshold": float(threshold),
                                "left": lnode, "right": rnode}
                        total = score
    identifiers = "\n".join(sorted(r["id"] for r in rows)).encode()
    policy = {
        "schema": "ta_cost_tree_v1", "baseline_action": baseline_action, "tree": tree,
        "training": {
            "role": FIT_ROLE, "parents": len(rows), "groups": len({r["group"] for r in rows}),
            "ids_sha256": hashlib.sha256(identifiers).hexdigest(),
            "allowed_features": names, "quantiles": list(QUANTILES),
            "max_depth": max_depth, "max_features": 2, "min_leaf": min_leaf,
            "min_relative_improvement": min_relative_improvement,
            "baseline_total_cost_s": base_total, "policy_total_cost_s": total,
            "cost_units": "TA wall seconds; feature CPU excluded",
        },
    }
    if fallback_policy is not None:
        policy["fallback_policy"] = json.loads(json.dumps(fallback_policy))
        policy["required_dynamic_features"] = required_dynamic
        policy["training"]["dynamic_complete_fit_parents"] = int(active.sum())
        policy["training"]["fallback_policy_sha256"] = policy_sha256(fallback_policy)
        policy["training"]["comparator"] = "frozen_static_fallback"
    validate_policy(policy)
    return policy


def _predict_one(policy: dict, row: dict) -> tuple[str, str]:
    fallback = policy.get("fallback_policy")
    if fallback is not None and (row.get("dynamic_status") != "COMPLETE" or
            any(feature_value(row, name) is None for name in policy["required_dynamic_features"])):
        return _predict_one(fallback, row)[0], "frozen_static_fallback"
    if not row.get("eligible", True):
        return policy["baseline_action"], "resource_ineligible"
    node = policy["tree"]
    while "action" not in node:
        value = feature_value(row, node["feature"])
        if value is None:
            if fallback is not None:
                return _predict_one(fallback, row)[0], "frozen_static_fallback"
            return policy["baseline_action"], "feature_missing"
        node = node["left"] if value <= node["threshold"] else node["right"]
    return node["action"], "policy"


def predict_policy(policy: dict, rows: Iterable[dict]) -> list[str]:
    validate_policy(policy)
    checked = validate_rows(rows)
    require_static_ready(checked)
    return [_predict_one(policy, row)[0] for row in checked]


def clear_action(row: dict) -> str | None:
    statuses = row.get("statuses", {})
    a, b = (statuses.get(action) for action in ACTIONS)
    if a not in ("SAT", "UNSAT", "TIMEOUT") or b not in ("SAT", "UNSAT", "TIMEOUT"):
        return None
    solved = [action for action in ACTIONS if statuses[action] in ("SAT", "UNSAT")]
    if not solved:
        return None
    winner = min(solved, key=lambda action: row["costs"][action])
    fastest = float(row["costs"][winner])
    other = ACTIONS[1 - ACTIONS.index(winner)]
    slower_bound = T if statuses[other] == "TIMEOUT" else float(row["costs"][other])
    return winner if slower_bound - fastest >= max(0.02, 0.1 * fastest) else None


def _ratio(a: float, b: float) -> float | None:
    return a / b if b > 0 else None


def _paired_bootstrap(
    rows: list[dict], selected: np.ndarray, baseline: np.ndarray,
    samples: int, seed: int,
) -> dict:
    if samples < 1:
        return {"samples": 0, "unit": "equivalence_group"}
    groups = sorted({row["group"] for row in rows})
    index = {g: i for i, g in enumerate(groups)}
    a = np.zeros(len(groups)); b = np.zeros(len(groups)); n = np.zeros(len(groups))
    for i, row in enumerate(rows):
        j = index[row["group"]]
        a[j] += selected[i]; b[j] += baseline[i]; n[j] += 1
    draw = np.random.default_rng(seed).integers(0, len(groups), size=(samples, len(groups)))
    selected_total = a[draw].sum(axis=1)
    base_total = b[draw].sum(axis=1)
    ok = base_total > 0
    ratios = selected_total[ok] / base_total[ok]
    delta_means = (selected_total - base_total) / n[draw].sum(axis=1)
    interval = lambda x: [float(v) for v in np.quantile(x, (0.025, 0.975))] if len(x) else None
    return {"samples": samples, "seed": seed, "unit": "equivalence_group",
            "groups": len(groups), "cost_ratio_95": interval(ratios),
            "improvement_95": interval(1 - ratios), "mean_delta_s_95": interval(delta_means),
            "note": "Exploratory paired interval; feedback reuse is not multiplicity-adjusted."}


def evaluate_policy(
    policy: dict, feedback_rows: Iterable[dict], *, baseline_action: str | None = None,
    bootstrap_samples: int = 2000, seed: int = 20261104,
    baseline_policy: dict | None = None,
) -> dict:
    validate_policy(policy)
    rows = validate_rows(feedback_rows)
    require_static_ready(rows)
    if not rows:
        raise ValueError("evaluation population is empty")
    if len({r["role"] for r in rows}) != 1:
        raise ValueError("evaluate one development role at a time")
    baseline_action = policy["baseline_action"] if baseline_action is None else baseline_action
    _action_index(baseline_action)
    if baseline_policy is not None:
        validate_policy(baseline_policy)
    per_row = []
    for row in rows:
        action, reason = _predict_one(policy, row)
        comparator = baseline_action if baseline_policy is None else _predict_one(baseline_policy, row)[0]
        selected = float(row["costs"][action]); base = float(row["costs"][comparator])
        statuses = row.get("statuses", {})
        per_row.append({
            "id": row["id"], "group": row["group"], "role": row["role"],
            "action": action, "baseline_action": comparator, "prediction_reason": reason,
            "cost_s": selected, "baseline_cost_s": base, "delta_s": selected - base,
            "oracle_cost_s": min(float(row["costs"][a]) for a in ACTIONS),
            "clear_action": clear_action(row), "selected_status": statuses.get(action),
            "baseline_status": statuses.get(comparator),
            "feature_cpu_s": row.get("feature_cpu_s"),
            "source_success_after_5000": any(statuses.get(a) in ("SAT", "UNSAT") and
                                              float(row["costs"][a]) > T for a in ACTIONS),
        })
    selected = np.array([r["cost_s"] for r in per_row])
    base = np.array([r["baseline_cost_s"] for r in per_row])
    delta = selected - base
    clear = [r for r in per_row if r["clear_action"] is not None]
    switches = [r for r in per_row if r["action"] != r["baseline_action"]]
    clear_switches = [r for r in switches if r["clear_action"] is not None]
    complete_statuses = all(r["selected_status"] is not None and r["baseline_status"] is not None for r in per_row)
    feature_cpu = [float(r["feature_cpu_s"]) for r in per_row if r["feature_cpu_s"] is not None]
    total = float(selected.sum()); base_total = float(base.sum())
    cost_ratio = _ratio(total, base_total)
    gain = float((-delta[delta < 0]).sum()); loss = float(delta[delta > 0].sum())
    metrics = {
        "parents": len(rows), "groups": len({r["group"] for r in rows}), "role": rows[0]["role"],
        "baseline_action": baseline_action if baseline_policy is None else None,
        "baseline_policy_sha256": None if baseline_policy is None else policy_sha256(baseline_policy),
        "action_counts": dict(Counter(r["action"] for r in per_row)),
        "policy_total_cost_s": total, "baseline_total_cost_s": base_total,
        "policy_mean_cost_s": total / len(rows), "baseline_mean_cost_s": base_total / len(rows),
        "cost_ratio": cost_ratio, "relative_improvement": None if cost_ratio is None else 1 - cost_ratio,
        "total_delta_s": float(delta.sum()), "mean_delta_s": float(delta.mean()),
        "solved": sum(r["selected_status"] in ("SAT", "UNSAT") for r in per_row) if complete_statuses else None,
        "baseline_solved": sum(r["baseline_status"] in ("SAT", "UNSAT") for r in per_row) if complete_statuses else None,
        "status_diagnostics_complete": complete_statuses,
        "clear_parents": len(clear),
        "clear_accuracy": _ratio(sum(r["action"] == r["clear_action"] for r in clear), len(clear)),
        "baseline_clear_accuracy": _ratio(sum(r["baseline_action"] == r["clear_action"] for r in clear), len(clear)),
        "switches": len(switches), "switch_coverage": len(switches) / len(rows),
        "clear_switches": len(clear_switches),
        "clear_switch_coverage": _ratio(len(clear_switches), len(clear)),
        "clear_switch_precision": _ratio(sum(r["action"] == r["clear_action"] for r in clear_switches), len(clear_switches)),
        "unlabeled_switches": len(switches) - len(clear_switches),
        "fallback_counts": dict(Counter(r["prediction_reason"] for r in per_row)),
        "gross_gain_s": gain, "gross_loss_s": loss,
        "max_regression_s": float(max(0.0, delta.max())),
        "largest_gain_fraction": _ratio(float(max(0.0, -delta.min())), gain),
        "worst_losses": sorted([r for r in per_row if r["delta_s"] > 0], key=lambda r: (-r["delta_s"], r["id"]))[:10],
        "oracle_total_cost_s": sum(r["oracle_cost_s"] for r in per_row),
        "regret_to_oracle_s": sum(r["cost_s"] - r["oracle_cost_s"] for r in per_row),
        "observed_feature_cpu_s": sum(feature_cpu), "feature_cpu_parents": len(feature_cpu),
        "feature_cpu_not_added_to_TA_wall": True,
        "TA_scale_break_even_feature_wall_s_per_parent": max(0.0, (base_total - total) / len(rows)),
        "late_source_success_parents": sum(r["source_success_after_5000"] for r in per_row),
        "bootstrap": _paired_bootstrap(rows, selected, base, bootstrap_samples, seed),
    }
    return {"metrics": metrics, "per_row": per_row}


def policy_sha256(policy: dict) -> str:
    validate_policy(policy)
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


# Explicit convenience alias; neither function chooses its baseline on feedback.
score_policy = evaluate_policy
