"""Frozen TA-R04: two dynamic fields, bounded trees and frozen static fallback.

Only the central owner invokes this after committing source and a complete
192-task dynamic snapshot. No solver, gate/test, or adaptive proposal search.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import time

for _key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_key] = "1"

import learning

ROUND_ID = "TA-R04"
PROPOSALS = (
    {"id": "r04_glue_mean", "dynamic_field": "c_glue_mean"},
    {"id": "r04_target_level", "dynamic_field": "x_level_avg"},
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def save_new(path, value):
    path = Path(path)
    encoded = json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with path.open("x") as handle:
        handle.write(encoded)


def validate_snapshot(data):
    rows = learning.validate_development_payload(data)
    if data.get("dynamic_complete") is not True or data.get("dynamic_summary", {}).get("scheduled") != 192:
        raise ValueError("R04 requires all 192 dynamic tasks terminal, never the 40-task pilot")
    fit = [r for r in rows if r["role"] == learning.FIT_ROLE]
    feedback = [r for r in rows if r["role"] == learning.FEEDBACK_ROLE]
    if len(fit) != 180 or len(feedback) != 60:
        raise ValueError("expected complete 180-fit/60-feedback population")
    if {r["group"] for r in fit} & {r["group"] for r in feedback}:
        raise ValueError("equivalence groups cross development roles")
    terminal = {"COMPLETE", "MISSING", "EARLY_SOLVED_UNVERIFIED", "FAILED", "RESOURCE_UNAVAILABLE"}
    scheduled = [r for r in rows if r.get("dynamic_status") != "NOT_SCHEDULED"]
    if len(scheduled) != 192 or any(r.get("dynamic_status") not in terminal for r in scheduled):
        raise ValueError("dynamic row terminal counts differ from manifest")
    complete = [r for r in scheduled if r["dynamic_status"] == "COMPLETE"]
    if len(complete) != data["dynamic_summary"].get("complete_vectors"):
        raise ValueError("complete-vector summary differs from parent records")
    for row in rows:
        present = {name for name in learning.DYNAMIC_FEATURES if learning.feature_value(row, name) is not None}
        if row.get("dynamic_status") == "COMPLETE":
            if present != learning.DYNAMIC_FEATURES:
                raise ValueError("COMPLETE parent lacks the qualified six-field vector")
        elif present:
            raise ValueError("unavailable parent publishes a partial dynamic vector")
    bindings = data.get("dynamic_bindings", {})
    if len(bindings.get("receipts", {})) != 192 or any(
            not isinstance(bindings.get(k), str) or len(bindings[k]) != 64
            for k in ("static_dataset_sha256", "manifest_sha256", "receipt_index_sha256")):
        raise ValueError("missing immutable dynamic stage bindings")
    return fit, feedback


def load_static_reference(path):
    source = json.loads(Path(path).read_text())
    policy = source.get("policy", source)
    learning.validate_policy(policy)
    if policy.get("fallback_policy") is not None or learning._used_features(policy["tree"]) & learning.DYNAMIC_FEATURES:
        raise ValueError("strongest-static reference must be an already frozen static policy")
    return policy


def fit_candidate(fit, dynamic_field):
    if dynamic_field not in {p["dynamic_field"] for p in PROPOSALS}:
        raise ValueError("field was not predeclared for R04")
    fallback = learning.fit_policy(fit, learning.PRIMARY_FEATURES, max_depth=1, min_leaf=12,
                                   min_relative_improvement=0.01)
    used = sorted(learning._used_features(fallback["tree"]))
    if len(used) > 1:
        raise ValueError("static fallback exceeds a one-feature stump")
    policy = learning.fit_policy(fit, used + [dynamic_field], max_depth=2, min_leaf=12,
                                 min_relative_improvement=0.01, fallback_policy=fallback)
    return policy, fallback


def _comparisons(policy, fallback, rows, static_reference, baseline_action, samples=2000, seed=20261104):
    return {
        "fit_best_constant": learning.evaluate_policy(policy, rows, baseline_action=baseline_action,
                                                       bootstrap_samples=samples, seed=seed),
        "frozen_static_fallback": learning.evaluate_policy(policy, rows, baseline_policy=fallback,
                                                           bootstrap_samples=samples, seed=seed),
        "strongest_static_reference": learning.evaluate_policy(policy, rows, baseline_policy=static_reference,
                                                                bootstrap_samples=samples, seed=seed),
    }


def candidate_job(job):
    fit, feedback, proposal, static_reference, cv = job
    cpu, wall = time.process_time(), time.monotonic()
    baseline = learning.baseline_and_oracle(fit)["baseline_action"]
    policy, fallback = fit_candidate(fit, proposal["dynamic_field"])
    evaluations = _comparisons(policy, fallback, feedback, static_reference, baseline)
    folds_out = []
    if cv:
        groups = sorted({r["group"] for r in fit}, key=lambda g:
                        hashlib.sha256(("ta-fit-cv-v1:" + g).encode()).hexdigest())
        folds = {g: i % 5 for i, g in enumerate(groups)}
        for fold in range(5):
            train = [r for r in fit if folds[r["group"]] != fold]
            heldout = [dict(r, role=learning.FEEDBACK_ROLE) for r in fit if folds[r["group"]] == fold]
            # Refit the fallback inside each training fold. The full-fit static
            # reference is never scored on these fit-fold validation parents.
            fold_policy, fold_fallback = fit_candidate(train, proposal["dynamic_field"])
            fold_best = learning.baseline_and_oracle(train)["baseline_action"]
            folds_out.append({"fold": fold, "policy": fold_policy, "fallback_policy": fold_fallback,
                              "evaluation": learning.evaluate_policy(fold_policy, heldout, baseline_action=fold_best,
                                                                     bootstrap_samples=0),
                              "vs_fallback": learning.evaluate_policy(fold_policy, heldout, baseline_policy=fold_fallback,
                                                                      bootstrap_samples=0)})
    return {"round_id": ROUND_ID, "proposal": proposal, "policy": policy, "fallback_policy": fallback,
            "fit_best_constant": baseline, "evaluation": evaluations["fit_best_constant"],
            "comparisons": evaluations, "fit_group_cv": folds_out,
            "process_cpu_s": time.process_time() - cpu, "wall_s": time.monotonic() - wall}


def run(dataset_path, strongest_static_path, output_dir, *, cv=True,
        expected_dataset_sha256=None, expected_static_reference_sha256=None):
    dataset_sha, reference_sha = sha(dataset_path), sha(strongest_static_path)
    if expected_dataset_sha256 is not None and dataset_sha != expected_dataset_sha256:
        raise ValueError("dataset differs from frozen SHA")
    if expected_static_reference_sha256 is not None and reference_sha != expected_static_reference_sha256:
        raise ValueError("static reference differs from frozen SHA")
    data = json.loads(Path(dataset_path).read_text())
    fit, feedback = validate_snapshot(data)
    static_reference = load_static_reference(strongest_static_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    proposals = {"round_id": ROUND_ID, "proposals": list(PROPOSALS), "max_candidates": 2,
                 "static_fallback": "fit-only primary10 depth1 cost tree, separately refitted within each CV fold",
                 "candidate_max_depth": 2, "union_numeric_feature_cap": 2, "min_leaf": 12,
                 "min_relative_fit_improvement": 0.01, "feedback_bootstrap_samples": 2000,
                 "cv": "five deterministic equivalence-group folds; diagnostic only"}
    receipt = {"round_id": ROUND_ID, "dataset_sha256": dataset_sha,
               "static_reference_sha256": reference_sha,
               "static_reference_policy_sha256": learning.policy_sha256(static_reference),
               "source_sha256": sha(__file__), "learning_sha256": sha(learning.__file__),
               "proposals_sha256": hashlib.sha256(_canonical(proposals)).hexdigest(),
               "fit_n": len(fit), "feedback_n": len(feedback), "workers": 2,
               "started_ns": time.time_ns(), "dynamic_summary": data["dynamic_summary"]}
    save_new(output / "PROPOSALS.json", proposals)
    save_new(output / "RUN_STARTED.json", receipt)
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(candidate_job, (fit, feedback, p, static_reference, cv)) for p in PROPOSALS]
            # No candidate feedback files are published until both jobs finish.
            results = [future.result() for future in futures]
        for result in results:
            save_new(output / (result["proposal"]["id"] + ".json"), result)
        complete = {**receipt, "status": "COMPLETE", "members": {
            p.name: sha(p) for p in sorted(output.glob("*.json"))}}
        save_new(output / "COMPLETE.json", complete)
        return complete
    except Exception as exc:
        save_new(output / "FAILED.json", {**receipt, "status": "FAILED", "error": type(exc).__name__ + ": " + str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--strongest-static", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-dataset-sha256")
    parser.add_argument("--expected-static-reference-sha256")
    parser.add_argument("--no-cv", action="store_true")
    args = parser.parse_args()
    result = run(args.dataset, args.strongest_static, args.out, cv=not args.no_cv,
                 expected_dataset_sha256=args.expected_dataset_sha256,
                 expected_static_reference_sha256=args.expected_static_reference_sha256)
    print(json.dumps({"status": result["status"], "round_id": ROUND_ID, "out": str(args.out)}))


if __name__ == "__main__":
    main()
