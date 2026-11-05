"""Small, auditable policy grammar for feedback-driven in-context updates.

The actor is the current Codex agent. It proposes JSON decision trees from
development feedback; this module validates and executes them. No external
model service, dynamic Python evaluation, or problem metadata is needed.
"""

import hashlib
import json
import math
from pathlib import Path

ACTIONS = {"D", "Fplus", "Fminus"}
STATIC = {
    "s_header_variables", "s_variables", "s_clauses", "s_log_variables", "s_log_clauses",
    "s_cv_ratio", "s_mean_length", "s_length_std", "s_max_length", "s_unit_fraction",
    "s_binary_fraction", "s_ternary_fraction", "s_long_fraction", "s_empty_fraction",
    "s_positive_fraction", "s_horn_fraction", "s_antihorn_fraction", "s_pure_variable_fraction",
    "s_mean_polarity_imbalance", "s_jw_positive_fraction", "g_components",
    "g_largest_component_fraction", "g_cycle_excess", "g_cycle_excess_per_incidence",
    "g_leaf_variable_fraction", "g_degree_two_fraction", "g_degree_mean", "g_degree_cv",
    "g_degree_p50", "g_degree_p90", "g_degree_max", "g_degree_entropy_normalized",
    "g_gate_motif_fraction", "g_gate_motifs_exact",
}


def validate(policy, allowed=STATIC, max_depth=3):
    def walk(node, depth):
        if not isinstance(node, dict):
            raise ValueError("policy node must be a mapping")
        if set(node) == {"action"}:
            if node["action"] not in ACTIONS:
                raise ValueError("unknown action")
            return
        if set(node) != {"feature", "threshold", "missing", "left", "right"}:
            raise ValueError("invalid policy schema")
        if depth >= max_depth or node["feature"] not in allowed:
            raise ValueError("unsupported depth or forbidden feature")
        threshold = node["threshold"]
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold):
            raise ValueError("non-numeric threshold")
        if node["missing"] not in ("left", "right"):
            raise ValueError("missing branch required")
        walk(node["left"], depth+1)
        walk(node["right"], depth+1)
    walk(policy, 0)
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def decide(policy, features):
    validate(policy)
    node = policy
    while "action" not in node:
        value = features.get(node["feature"])
        if value is None:
            branch = node["missing"]
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("invalid feature value")
            branch = "left" if value <= node["threshold"] else "right"
        node = node[branch]
    return node["action"]


def append_episode(path, episode):
    """An immutable development-only feedback record, not an optimizer itself."""
    if episode.get("split_role") not in {"development_fit", "development_feedback"}:
        raise ValueError("test/gate results cannot enter the policy-update context")
    if not episode.get("policy") or "reward" not in episode:
        raise ValueError("policy and observed reward required")
    reward = episode["reward"]
    if isinstance(reward, bool) or not isinstance(reward, (int, float)) or not math.isfinite(reward):
        raise ValueError("reward must be a measured finite number")
    record = {**episode, "policy_sha256": validate(episode["policy"])}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record
