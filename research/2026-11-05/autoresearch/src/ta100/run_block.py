"""Committed TA100 ten-mechanism block: fit only new candidates, reuse R1.

No solver calls, protected roles, feature acquisition or baseline refitting.
Root owns global history, semantic deduplication and workflow revisions.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

for _key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_key] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ta_feature_discovery"))
import learning
import numpy as np

SAFE_COLUMN = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
BASE10 = tuple(learning.PRIMARY_FEATURES)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        # Workflow02: compact immutable machine records; readable tables are separate.
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def _ids_sha(rows):
    return hashlib.sha256("\n".join(sorted(r["id"] for r in rows)).encode()).hexdigest()


def fold_map(fit):
    groups = sorted({r["group"] for r in fit}, key=lambda g:
                    hashlib.sha256(("ta-fit-cv-v1:" + g).encode()).hexdigest())
    return {group: i % 5 for i, group in enumerate(groups)}


def _numeric(value):
    return value is None or (not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value))


def _safe_columns(columns):
    if (not isinstance(columns, list) or not columns or len(columns) != len(set(columns)) or
            any(not isinstance(x, str) or not SAFE_COLUMN.fullmatch(x) for x in columns)):
        raise ValueError("invalid or duplicate literal feature columns")
    return columns


def validate_and_merge(data, table):
    rows = learning.validate_development_payload(data)
    fit = [r for r in rows if r["role"] == learning.FIT_ROLE]
    feedback = [r for r in rows if r["role"] == learning.FEEDBACK_ROLE]
    if len(fit) != 180 or len(feedback) != 60:
        raise ValueError("only the frozen full240=180fit+60feedback population is allowed")
    if {r["group"] for r in fit} & {r["group"] for r in feedback}:
        raise ValueError("equivalent parents cross development roles")
    eligible = {r["id"] for r in rows if r.get("eligible", True)}
    expected = table.get("expected_instance_ids")
    if table.get("complete") is not True or not isinstance(expected, list) or len(expected) != 192 or len(set(expected)) != 192 or set(expected) != eligible:
        raise ValueError("feature table must complete the exact frozen192 eligible identities")
    columns = _safe_columns(table.get("columns"))
    if set(columns) & set(learning.ALLOWED_FEATURES):
        raise ValueError("new feature table collides with historical feature names")
    values = table.get("features")
    if not isinstance(values, dict) or set(values) != eligible:
        raise ValueError("extra/missing feature identities; partial feedback is forbidden")
    for record in values.values():
        if not isinstance(record, dict) or set(record) != set(columns) or any(not _numeric(x) for x in record.values()):
            raise ValueError("feature rows require exactly declared finite numbers or null")
    bindings = table.get("bindings", {})
    for key in ("base_manifest_sha256", "source_sha256"):
        if not isinstance(bindings.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", bindings[key]):
            raise ValueError("feature source/public-manifest SHA binding is missing")
    merged = copy.deepcopy(rows)
    for row in merged:
        row["features"].update(values.get(row["id"], dict.fromkeys(columns)))
    return [r for r in merged if r["role"] == learning.FIT_ROLE], [r for r in merged if r["role"] == learning.FEEDBACK_ROLE]


def validate_block(block, registry):
    rounds = block.get("rounds", block.get("proposals"))
    if not isinstance(rounds, list) or len(rounds) != 10:
        raise ValueError("freeze exactly10 mechanism rounds per block")
    entries = registry.get("candidates", registry.get("rounds", []))
    if not isinstance(entries, list):
        raise ValueError("invalid registry")
    ids, mechanisms, all_columns = set(), set(), set()
    for proposal in rounds:
        identifier, mechanism = proposal.get("id"), proposal.get("mechanism_key")
        if not isinstance(identifier, str) or not SAFE_ID.fullmatch(identifier) or identifier in ids:
            raise ValueError("unsafe/duplicate round identifier")
        if not isinstance(mechanism, str) or not mechanism or mechanism in mechanisms:
            raise ValueError("missing/duplicate mechanism key")
        columns = _safe_columns(proposal.get("columns"))
        if len(columns) > 3 or set(columns) & set(learning.ALLOWED_FEATURES):
            raise ValueError("each new mechanism declares1..3 novel safe columns")
        wanted_id = proposal.get("registry_id", identifier)
        matches = [entry for entry in entries if (
            entry.get("id") == wanted_id or (entry.get("columns") == columns and
            entry.get("mechanism_key", entry.get("novelty_mechanism_key")) == mechanism))]
        if not any(entry.get("columns") == columns and
                   entry.get("mechanism_key", entry.get("novelty_mechanism_key")) == mechanism for entry in matches):
            raise ValueError("round columns/mechanism do not match the frozen registry")
        ids.add(identifier); mechanisms.add(mechanism); all_columns.update(columns)
    return rounds, sorted(all_columns)


def _cached_actions(evaluation, rows):
    records = evaluation.get("per_row", [])
    if len(records) != len(rows) or {r.get("id") for r in records} != {r["id"] for r in rows}:
        raise ValueError("cached baseline does not cover exactly the required parents")
    by_id = {r["id"]: r for r in rows}
    actions = {}
    for record in records:
        row, action = by_id[record["id"]], record.get("action")
        if action not in learning.ACTIONS or record.get("group") != row["group"] or record.get("role") != learning.FEEDBACK_ROLE:
            raise ValueError("cached baseline parent/group/action identity mismatch")
        if not math.isclose(float(record.get("cost_s", -1)), float(row["costs"][action]), abs_tol=1e-8, rel_tol=1e-12):
            raise ValueError("cached baseline labels differ from current frozen costs")
        actions[row["id"]] = action
    return actions


def validate_baseline(reference, fit, feedback):
    policy = reference.get("policy")
    learning.validate_policy(policy)
    if (policy.get("fallback_policy") is not None or learning._used_features(policy["tree"]) - set(BASE10) or
            policy.get("training", {}).get("ids_sha256") != _ids_sha(fit)):
        raise ValueError("R1 static control must bind this full fit population")
    full = _cached_actions(reference.get("evaluation", {}), feedback)
    fold_records = reference.get("fit_group_cv", [])
    if len(fold_records) != 5 or {r.get("fold") for r in fold_records} != set(range(5)):
        raise ValueError("all5 frozen R1 fit-fold prediction caches are required")
    folds, cached = fold_map(fit), {}
    for record in fold_records:
        i = record["fold"]
        train = [r for r in fit if folds[r["group"]] != i]
        heldout = [r for r in fit if folds[r["group"]] == i]
        old_policy = record.get("policy", {})
        learning.validate_policy(old_policy)
        if old_policy.get("training", {}).get("ids_sha256") != _ids_sha(train):
            raise ValueError("cached R1 fold training identities differ")
        cached[i] = _cached_actions(record.get("evaluation", {}), heldout)
    return full, cached


def compare_cached(selected_evaluation, rows, cached_actions, *, samples=2000, seed=20261104):
    """Reuse one candidate prediction vector with stored R1 actions, no refit."""
    result = copy.deepcopy(selected_evaluation)
    per_row, metrics = result["per_row"], result["metrics"]
    by_id = {r["id"]: r for r in rows}
    for record in per_row:
        row = by_id[record["id"]]
        action = cached_actions[record["id"]]
        cost = float(row["costs"][action])
        record.update(baseline_action=action, baseline_cost_s=cost,
                      baseline_status=row.get("statuses", {}).get(action), delta_s=record["cost_s"] - cost)
    selected = np.array([r["cost_s"] for r in per_row]); base = np.array([r["baseline_cost_s"] for r in per_row])
    delta = selected - base
    total, base_total = float(selected.sum()), float(base.sum())
    ratio = total / base_total if base_total > 0 else None
    clear = [r for r in per_row if r["clear_action"] is not None]
    switches = [r for r in per_row if r["action"] != r["baseline_action"]]
    clear_switches = [r for r in switches if r["clear_action"] is not None]
    gain = float((-delta[delta < 0]).sum()); loss = float(delta[delta > 0].sum())
    fraction = lambda a, b: a / b if b else None
    metrics.update(baseline_action=None, baseline_policy_sha256=None, baseline_source="cached_R1_predictions",
        baseline_total_cost_s=base_total, baseline_mean_cost_s=base_total / len(rows),
        cost_ratio=ratio, relative_improvement=None if ratio is None else 1 - ratio,
        total_delta_s=float(delta.sum()), mean_delta_s=float(delta.mean()),
        baseline_solved=sum(r["baseline_status"] in ("SAT", "UNSAT") for r in per_row),
        baseline_clear_accuracy=fraction(sum(r["baseline_action"] == r["clear_action"] for r in clear), len(clear)),
        switches=len(switches), switch_coverage=len(switches) / len(rows), clear_switches=len(clear_switches),
        clear_switch_coverage=fraction(len(clear_switches), len(clear)),
        clear_switch_precision=fraction(sum(r["action"] == r["clear_action"] for r in clear_switches), len(clear_switches)),
        unlabeled_switches=len(switches) - len(clear_switches), gross_gain_s=gain, gross_loss_s=loss,
        max_regression_s=float(max(0.0, delta.max())),
        largest_gain_fraction=fraction(float(max(0.0, -delta.min())), gain),
        worst_losses=sorted([r for r in per_row if r["delta_s"] > 0], key=lambda r: (-r["delta_s"], r["id"]))[:10],
        TA_scale_break_even_feature_wall_s_per_parent=max(0.0, (base_total - total) / len(rows)),
        bootstrap=learning._paired_bootstrap(rows, selected, base, samples, seed))
    return result


def duplicate_diagnostics(fit, columns):
    reports = []
    for name in columns:
        a = [learning.feature_value(r, name) for r in fit]
        observed = [v for v in a if v is not None]
        if not observed or len(set(observed)) == 1:
            reports.append({"column": name, "kind": "no_observation" if not observed else "observed_constant",
                            "fit_support": len(observed), "value": observed[0] if observed else None})
            continue
        for other in list(BASE10) + [x for x in columns if x < name]:
            b = [learning.feature_value(r, other) for r in fit]
            if [v is None for v in a] != [v is None for v in b] or len(observed) < 12:
                continue
            x = np.array(observed); y = np.array([v for v in b if v is not None])
            if np.allclose(x, y, atol=1e-12, rtol=1e-12):
                reports.append({"column": name, "other": other, "kind": "same_numeric_values", "fit_support": len(x)})
                continue
            order = np.argsort(x, kind="stable")
            dx, dy = np.diff(x[order]), np.diff(y[order])
            same_ties = np.array_equal(dx == 0, dy == 0)
            if same_ties and (np.all(dy >= 0) or np.all(dy <= 0)):
                reports.append({"column": name, "other": other, "kind": "monotonic_order_alias", "fit_support": len(x)})
    return reports


def candidate_job(job):
    fit, feedback, proposal, registered_columns, cached_full, cached_folds = job
    cpu, wall = time.process_time(), time.monotonic()
    try:
        learning.ALLOWED_FEATURES = learning.ALLOWED_FEATURES | frozenset(registered_columns)
        columns = proposal["columns"]
        names = list(BASE10) + columns
        policy = learning.fit_policy(fit, names, max_depth=2, min_leaf=12, min_relative_improvement=.01)
        baseline_action = learning.baseline_and_oracle(fit)["baseline_action"]
        if baseline_action != "true":
            raise ValueError("fit-selected fixed control differs from the frozen true control")
        full = learning.evaluate_policy(policy, feedback, baseline_action="true", bootstrap_samples=2000)
        vs_static = compare_cached(full, feedback, cached_full)
        folds, cv = fold_map(fit), []
        for i in range(5):
            train = [r for r in fit if folds[r["group"]] != i]
            heldout = [dict(r, role=learning.FEEDBACK_ROLE) for r in fit if folds[r["group"]] == i]
            fold_policy = learning.fit_policy(train, names, max_depth=2, min_leaf=12, min_relative_improvement=.01)
            evaluation = learning.evaluate_policy(fold_policy, heldout, bootstrap_samples=0)
            fold_vs_static = compare_cached(evaluation, heldout, cached_folds[i], samples=0)
            cv.append({"fold": i, "policy": fold_policy, "evaluation": fold_vs_static,
                       "vs_fixed_control": evaluation, "vs_static_control": fold_vs_static})
        coverage = {role: {name: sum(learning.feature_value(r, name) is not None for r in pop) for name in columns}
                    for role, pop in ((learning.FIT_ROLE, fit), (learning.FEEDBACK_ROLE, feedback))}
        return {"status": "COMPLETE", "proposal": proposal, "policy": policy, "evaluation": vs_static,
                "primary_reference": "cached_R1_ordinary_tree_old10_static_features",
                "vs_fixed_control": full, "vs_static_control": vs_static, "fit_group_cv": cv,
                "used_new_columns": sorted(learning._used_features(policy["tree"]) & set(columns)),
                "coverage": coverage, "numeric_diagnostics_fit_only": [d for d in duplicate_diagnostics(fit, registered_columns)
                    if d["column"] in columns or d.get("other") in columns],
                "process_cpu_s": time.process_time() - cpu, "wall_s": time.monotonic() - wall}
    except Exception as exc:
        return {"status": "FAILED", "proposal": proposal, "error": type(exc).__name__ + ": " + str(exc),
                "process_cpu_s": time.process_time() - cpu, "wall_s": time.monotonic() - wall}


def _bound_json(path, expected):
    digest = sha(path)
    if not isinstance(expected, str) or digest != expected:
        raise ValueError("file differs from required frozen SHA: " + str(path))
    return json.loads(Path(path).read_text()), digest


def validate_collection_binding(block, table):
    expected = block.get("collection_manifest_sha256")
    bindings = table.get("bindings", {})
    # Static tables separately bind the public population and collection method;
    # new dynamic tables use base_manifest for the full collection manifest.
    actual = bindings.get("collection_manifest_sha256", bindings.get("base_manifest_sha256"))
    if expected is not None and actual != expected:
        raise ValueError("feature collection method/profile differs from the frozen manifest")


def run(block_path, dataset_path, features_path, baseline_path, output_dir, workers=3):
    started = time.monotonic()
    block = json.loads(Path(block_path).read_text())
    registry, registry_sha = _bound_json(block["registry_path"], block["registry_sha256"])
    protocol_path = Path(block.get("protocol_path", "refine-logs/ta100/PROTOCOL.md"))
    if sha(protocol_path) != block.get("protocol_sha256"):
        raise ValueError("protocol SHA differs from frozen block")
    rounds, columns = validate_block(block, registry)
    data = json.loads(Path(dataset_path).read_text()); table = json.loads(Path(features_path).read_text())
    if sha(dataset_path) != block.get("dataset_sha256") or sha(baseline_path) != block.get("baseline_sha256"):
        raise ValueError("dataset or baseline differs from the frozen block SHA")
    if table.get("bindings", {}).get("source_sha256") != block.get("extractor_source_sha256"):
        raise ValueError("feature table source differs from the frozen extractor SHA")
    validate_collection_binding(block, table)
    if block.get("features_sha256") is not None and sha(features_path) != block["features_sha256"]:
        raise ValueError("feature table differs from the frozen raw SHA")
    if not set(columns) <= set(table.get("columns", [])):
        raise ValueError("declared block columns absent from complete feature table")
    fit, feedback = validate_and_merge(data, table)
    reference = json.loads(Path(baseline_path).read_text())
    cached_full, cached_folds = validate_baseline(reference, fit, feedback)
    if not isinstance(workers, int) or not 1 <= workers <= 3:
        raise ValueError("owner may allocate1..3 candidate workers")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    bindings = {"block_sha256": sha(block_path), "dataset_sha256": sha(dataset_path),
                "features_sha256": sha(features_path), "baseline_sha256": sha(baseline_path),
                "source_sha256": sha(__file__), "learning_sha256": sha(learning.__file__),
                "registry_sha256": registry_sha, "protocol_sha256": sha(protocol_path)}
    manifest = {"schema": "ta100.block_execution.v1", "block_id": block.get("block_id"), "rounds": rounds,
                "bindings": bindings, "workers": workers, "fit_n": 180, "feedback_n": 60,
                "cost_summary_shared_once": table.get("cost_summary", table.get("physical_costs", {})),
                "serialization": "compact_json_v2", "started_ns": time.time_ns()}
    save_new(output / "BLOCK_MANIFEST.json", manifest)
    statuses, costs = {}, []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(candidate_job, (fit, feedback, proposal, columns, cached_full, cached_folds)): proposal
                   for proposal in rounds}
        for future in concurrent.futures.as_completed(futures):
            proposal = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"status": "FAILED", "proposal": proposal, "error": type(exc).__name__ + ": " + str(exc),
                          "process_cpu_s": None, "cost_unknown_reason": "worker failed before CPU receipt"}
            result["bindings"] = bindings
            result["feature_fee_reference"] = {"features_sha256": bindings["features_sha256"],
                "shared_once_at_block": True, "not_added_to_TA_wall": True}
            save_new(output / proposal["id"] / "result.json", result)
            statuses[proposal["id"]] = result["status"]
            costs.append(result.get("process_cpu_s"))
    complete = {**manifest, "status": "COMPLETE" if all(s == "COMPLETE" for s in statuses.values()) else "COMPLETE_WITH_FAILURES",
                "terminal_rounds": len(statuses), "statuses": statuses,
                "analysis_cpu_s_known": sum(c for c in costs if c is not None),
                "analysis_cpu_unknown_workers": sum(c is None for c in costs),
                "wall_s": time.monotonic() - started,
                "members": {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob("*.json"))}}
    save_new(output / "COMPLETE.json", complete)
    return complete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("block", "dataset", "features", "baseline", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    result = run(args.block, args.dataset, args.features, args.baseline, args.out, args.workers)
    print(json.dumps({"status": result["status"], "terminal_rounds": result["terminal_rounds"], "out": str(args.out)}))


if __name__ == "__main__":
    main()
