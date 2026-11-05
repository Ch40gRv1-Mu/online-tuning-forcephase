#!/usr/bin/env python3
"""One frozen candidate, one gate consumption; no fitting or feedback updates."""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import time

for _key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_key] = "1"

import numpy as np
import learning
import node_worker as worker
import prepare_inputs as inputs

GATE = "development_gate"
GLOBAL_GATE_LEDGER = inputs.PROJECT / "reports/phase_prediction_v1/GATE_CONSUMED.json"


def frozen_candidate(path, expected_sha):
    if not worker.SHA.fullmatch(expected_sha) or worker.sha(path) != expected_sha:
        raise ValueError("candidate file differs from the explicitly frozen SHA")
    raw = json.loads(Path(path).read_text())
    policy = raw.get("policy", raw)
    learning.validate_policy(policy)
    return policy


def load_gate_roles(path, expected=60):
    selected, groups, seen = [], collections.defaultdict(set), set()
    with Path(path).open(newline="") as stream:
        for row in csv.DictReader(stream):
            h = inputs.identifier(row["hash"])
            if h in seen:
                raise ValueError("duplicate frozen parent identity")
            seen.add(h)
            group = row.get("isohash") or h
            if group.lower() in {"empty", "none", "unknown"}:
                group = h
            groups[group].add(row["role"])
            if row["role"] == GATE:
                selected.append({**row, "hash": h, "group": group})
    if len(selected) != expected or any(GATE in roles and len(roles) != 1 for roles in groups.values()):
        raise ValueError("gate population count/equivalence isolation differs from the freeze")
    return selected


def prepare_public(args):
    policy = frozen_candidate(args.candidate, args.expected_candidate_sha256)
    if policy.get("required_dynamic_features") or learning._used_features(policy["tree"]) & learning.DYNAMIC_FEATURES:
        raise ValueError("dynamic winner requires a separately frozen dynamic gate collector")
    roles = load_gate_roles(args.roles)
    checksums = inputs.load_checksums(args.checksums)
    excluded = {r["hash"]: r["reason"] for r in json.loads(args.exclusions.read_text())}
    source_sha = worker.sha(args.extractor_source)
    tasks, exclusions = [], []
    for row in roles:
        h = row["hash"]
        eligible = h not in excluded and int(row.get("bytes") or 0) <= 100_000_000 and int(row.get("variables") or 0) <= 5_000_000
        if not eligible:
            exclusions.append({"instance_id": h, "reason": excluded.get(h, "frozen_public_resource_limit")})
            continue
        identity = checksums.get(h)
        if not identity or identity.get("input_bytes") is None:
            raise ValueError("gate input lacks frozen raw SHA/exact bytes_cnf")
        metadata = {k: int(row[k]) for k in ("variables", "clauses") if row.get(k)}
        metadata["bytes"] = identity["input_bytes"]
        task = {"instance_id": h, "role": GATE, "public_url": row.get("url") or "https://benchmark-database.de/file/" + h,
                "input_sha256": identity["input_sha256"], "compressed_sha256": identity["compressed_sha256"], "metadata": metadata}
        tasks.append(worker.normalize_task(task, source_sha, allowed_roles={GATE}))
    if len(tasks) != args.expected_eligible:
        raise ValueError("eligible gate count differs from frozen expected count")
    manifest = {"schema_version": 1, "experiment_id": args.experiment_id, "shard_id": "one-time-gate",
                "node_id": args.node_id, "extractor_source_sha256": source_sha, "profile": worker.PROFILE,
                "gate_candidate_sha256": args.expected_candidate_sha256,
                "role_manifest_sha256": worker.sha(args.roles),
                "resource_exclusions_sha256": worker.sha(args.exclusions),
                "checksum_manifests": [{"path": str(p), "sha256": worker.sha(p)} for p in args.checksums],
                "gate_population_ids": [r["hash"] for r in roles], "resource_exclusions": exclusions, "tasks": tasks}
    inputs.save_new(args.output, manifest)
    return {"manifest": str(args.output), "gate_parents": len(roles), "tasks": len(tasks),
            "candidate_sha256": args.expected_candidate_sha256, "manifest_sha256": worker.sha(args.output)}


def consume_once(ledger, binding):
    """An incomplete/failed evaluation stays consumed; never silently restart it."""
    ledger = Path(ledger)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("x") as stream:
        stream.write(json.dumps({**binding, "status": "CONSUMED", "started_unix": time.time()}, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def load_gate_receipts(directories, manifest):
    tasks = {t["instance_id"]: worker.normalize_task(t, manifest["extractor_source_sha256"], allowed_roles={GATE})
             for t in manifest["tasks"]}
    selected = {}
    for directory in directories:
        for path in sorted(Path(directory).glob("*.json")):
            raw = json.loads(path.read_text())
            h = raw.get("instance_id")
            if h not in tasks:
                raise ValueError("gate receipt directory contains an out-of-manifest instance")
            if h in selected:
                raise ValueError("duplicate gate measurement; choose its frozen receipt explicitly")
            record = worker.reusable(path, tasks[h], manifest["extractor_source_sha256"])
            if record.get("role") != GATE or record.get("gate_candidate_sha256") != manifest["gate_candidate_sha256"]:
                raise ValueError("gate receipt is not bound to the frozen candidate and true gate role")
            if not worker.SHA.fullmatch(str(record.get("extractor_binary_sha256", ""))):
                raise ValueError("gate extractor binary identity missing")
            if record.get("status") not in {"COMPLETE", "FAILED", "TIMEOUT", "RESOURCE_UNAVAILABLE"}:
                raise ValueError("gate receipt is not terminal")
            selected[h] = record
    if set(selected) != set(tasks):
        raise ValueError("all eligible gate tasks need terminal receipts before one evaluation")
    return selected


def build_rows(roles, labels, manifest, receipts):
    tasks = {t["instance_id"] for t in manifest["tasks"]}
    rows = []
    for role in roles:
        h = role["hash"]
        record = receipts.get(h)
        complete = record is not None and record["status"] == "COMPLETE"
        values = inputs.extract_values(record["features"]) if complete else {k: None for k in inputs.FEATURES}
        rows.append({"id": h, "group": role["group"], "role": GATE, "eligible": h in tasks,
                     "feature_status": "AVAILABLE" if complete else ("UNAVAILABLE" if h in tasks else "EXCLUDED"),
                     "features": values, "feature_cpu_s": None if record is None else record["total_accounted_cpu_s"],
                     "costs": {a: learning.cost_for_result(labels[(h,a)]["status"], labels[(h,a)]["wall"]) for a in learning.ACTIONS},
                     "statuses": {a: labels[(h,a)]["status"] for a in learning.ACTIONS},
                     "wall_times": {a: labels[(h,a)]["wall"] for a in learning.ACTIONS}})
    return rows


def evaluate_frozen(policy, rows, *, expected_n=60, bootstrap_samples=2000):
    learning.validate_policy(policy)
    if len(rows) != expected_n or len({r["id"] for r in rows}) != expected_n or any(r["role"] != GATE for r in rows):
        raise ValueError("evaluate all original gate parents exactly once, without role relabeling")
    if any(r["feature_status"] == "PENDING" for r in rows):
        raise ValueError("partial gate feature evaluation is forbidden")
    per_row = []
    for row in rows:
        if set(row["costs"]) != set(learning.ACTIONS) or any(not math.isfinite(x) or x < 0 for x in row["costs"].values()):
            raise ValueError("invalid gate source costs")
        action, reason = learning._predict_one(policy, row)
        base_action = policy["baseline_action"]
        cost, baseline = row["costs"][action], row["costs"][base_action]
        per_row.append({"id": row["id"], "group": row["group"], "role": GATE, "action": action,
            "baseline_action": base_action, "prediction_reason": reason, "cost_s": cost,
            "baseline_cost_s": baseline, "delta_s": cost-baseline,
            "clear_action": learning.clear_action(row), "selected_status": row["statuses"][action],
            "baseline_status": row["statuses"][base_action]})
    selected = np.array([r["cost_s"] for r in per_row]); baseline = np.array([r["baseline_cost_s"] for r in per_row])
    total, base_total = float(selected.sum()), float(baseline.sum())
    improvement = 1-total/base_total if base_total else None
    bootstrap = learning._paired_bootstrap(rows, selected, baseline, bootstrap_samples, 20261104)
    bootstrap["note"] = "One frozen candidate; paired equivalence-group gate interval, no gate-driven fitting."
    interval = bootstrap.get("improvement_95")
    switches = [r for r in per_row if r["action"] != r["baseline_action"]]
    clear = [r for r in per_row if r["clear_action"] is not None]
    clear_switches = [r for r in switches if r["clear_action"] is not None]
    gross_gain = sum(-r["delta_s"] for r in per_row if r["delta_s"] < 0)
    metrics = {"parents": len(rows), "role": GATE, "baseline_action": policy["baseline_action"],
        "constant_total_cost_s": {a: sum(r["costs"][a] for r in rows) for a in learning.ACTIONS},
        "oracle_total_cost_s": sum(min(r["costs"].values()) for r in rows),
        "policy_total_cost_s": total, "baseline_total_cost_s": base_total, "relative_improvement": improvement,
        "bootstrap": bootstrap, "passes_frozen_2pct_and_positive_interval": improvement is not None and improvement >= .02 and interval is not None and interval[0] > 0,
        "switches": len(switches), "clear_parents": len(clear),
        "clear_accuracy": sum(r["action"] == r["clear_action"] for r in clear)/len(clear) if clear else None,
        "baseline_clear_accuracy": sum(r["baseline_action"] == r["clear_action"] for r in clear)/len(clear) if clear else None,
        "baseline_clear_accuracy": sum(r["baseline_action"] == r["clear_action"] for r in clear)/len(clear) if clear else None,
        "clear_switches": len(clear_switches), "switch_coverage": len(switches)/len(rows),
        "clear_switch_precision": sum(r["action"] == r["clear_action"] for r in clear_switches)/len(clear_switches) if clear_switches else None,
        "gross_gain_s": gross_gain, "gross_loss_s": sum(r["delta_s"] for r in per_row if r["delta_s"] > 0),
        "largest_gain_fraction": max(0.,max(-r["delta_s"] for r in per_row))/gross_gain if gross_gain else None,
        "fallback_counts": dict(collections.Counter(r["prediction_reason"] for r in per_row)),
        "static_feature_available": sum(r["feature_status"] == "AVAILABLE" for r in rows),
        "resource_eligible": sum(r["eligible"] for r in rows),
        "observed_feature_cpu_s": sum(r["feature_cpu_s"] or 0 for r in rows), "feature_cpu_not_added_to_TA_wall": True,
        "solved": sum(r["selected_status"] in {"SAT", "UNSAT"} for r in per_row),
        "baseline_solved": sum(r["baseline_status"] in {"SAT", "UNSAT"} for r in per_row),
        "max_regression_s": max(0., max(r["delta_s"] for r in per_row)),
        "worst_losses": sorted((r for r in per_row if r["delta_s"] > 0), key=lambda r:(-r["delta_s"],r["id"]))[:10]}
    return {"metrics": metrics, "per_row": per_row}


def run_evaluation(args):
    policy = frozen_candidate(args.candidate, args.expected_candidate_sha256)
    if args.ledger.resolve() != GLOBAL_GATE_LEDGER.resolve():
        raise ValueError("the original gate opportunity uses the shared project GATE_CONSUMED.json ledger")
    if args.ledger.exists():
        raise FileExistsError("the original single gate opportunity is already consumed")
    manifest = json.loads(args.manifest.read_text())
    if manifest.get("gate_candidate_sha256") != args.expected_candidate_sha256:
        raise ValueError("gate manifest differs from frozen candidate SHA")
    if worker.sha(args.roles) != manifest["role_manifest_sha256"]:
        raise ValueError("gate role source differs from frozen manifest")
    if policy.get("required_dynamic_features") or learning._used_features(policy["tree"]) & learning.DYNAMIC_FEATURES:
        raise ValueError("dynamic gate evaluation needs its frozen collector and merge contract")
    roles = load_gate_roles(args.roles)
    if [r["hash"] for r in roles] != manifest["gate_population_ids"]:
        raise ValueError("gate population/order differs from frozen manifest")
    receipts = load_gate_receipts(args.node_result_dirs, manifest)
    if args.output.exists():
        raise FileExistsError("gate output exists; inspect immutable result instead of rerunning")
    binding = {"candidate_sha256": args.expected_candidate_sha256, "manifest_sha256": worker.sha(args.manifest),
               "role_manifest_sha256": worker.sha(args.roles), "source_sha256": worker.sha(args.source),
               "output": str(args.output.resolve()), "evaluator_source_sha256": worker.sha(__file__)}
    consume_once(args.ledger, binding)  # Must precede every access to gate timings.
    labels = inputs.load_labels(args.source, {r["hash"] for r in roles})
    if args.paired_csv is not None:
        inputs.compare_labels(labels, inputs.load_labels(args.paired_csv, {r["hash"] for r in roles}))
        binding["companion_pairs_sha256"] = worker.sha(args.paired_csv)
    rows = build_rows(roles, labels, manifest, receipts)
    result = {**binding, "status": "COMPLETE", "evaluation": evaluate_frozen(policy, rows),
              "no_fitting_or_feedback_updates": True}
    inputs.save_new(args.output, result)
    # Append-only completion receipt: never modify the initial consumption.
    inputs.save_new(args.ledger.with_name(args.ledger.name + ".complete.json"),
                    {**binding, "result_sha256": worker.sha(args.output), "status": "COMPLETE"})
    return {"status": "COMPLETE", "output": str(args.output), "candidate_sha256": args.expected_candidate_sha256}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare-public")
    evaluate = sub.add_parser("evaluate-once")
    for command in (prepare, evaluate):
        command.add_argument("--candidate", required=True, type=Path)
        command.add_argument("--expected-candidate-sha256", required=True)
        command.add_argument("--roles", required=True, type=Path)
        command.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--checksums", required=True, nargs="+", type=Path)
    prepare.add_argument("--exclusions", required=True, type=Path)
    prepare.add_argument("--extractor-source", required=True, type=Path)
    prepare.add_argument("--node-id", required=True)
    prepare.add_argument("--experiment-id", default="ta_gate_static_v1")
    prepare.add_argument("--expected-eligible", type=int, default=51)
    evaluate.add_argument("--manifest", required=True, type=Path)
    evaluate.add_argument("--source", required=True, type=Path)
    evaluate.add_argument("--paired-csv", type=Path)
    evaluate.add_argument("--node-result-dirs", required=True, nargs="+", type=Path)
    evaluate.add_argument("--ledger", type=Path, default=GLOBAL_GATE_LEDGER)
    args = parser.parse_args()
    print(json.dumps(prepare_public(args) if args.command == "prepare-public" else run_evaluation(args)))


if __name__ == "__main__":
    main()
