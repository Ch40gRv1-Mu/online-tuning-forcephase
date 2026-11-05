"""Owner-run complete-snapshot scoring; no solver invocation or gate reads."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import time
from pathlib import Path

for _key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_key] = "1"

import learning
import cluster

FEATURES = [
    "s_mean_length", "s_length_std", "s_binary_fraction", "s_long_fraction",
    "s_positive_fraction", "s_mean_polarity_imbalance",
    "g_cycle_excess_per_incidence", "g_leaf_variable_fraction",
    "g_largest_component_fraction", "g_gate_motif_fraction",
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    def encode(x):
        if hasattr(x, "tolist"):
            return x.tolist()
        raise TypeError(type(x).__name__)
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2,
                                    allow_nan=False, default=encode) + "\n")
    temporary.replace(path)


def group_id(row):
    return str(row.get("group") or row.get("id"))


def validate(data, baseline_only=False):
    rows = data["rows"]
    if any(r["role"] not in ("development_fit", "development_feedback") for r in rows):
        raise ValueError("Only development fit/feedback are permitted")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate parent identifiers")
    fit = [r for r in rows if r["role"] == "development_fit"]
    feedback = [r for r in rows if r["role"] == "development_feedback"]
    if len(fit) != 180 or len(feedback) != 60:
        raise ValueError("Expected the frozen 180/60 parent population")
    if {group_id(r) for r in fit} & {group_id(r) for r in feedback}:
        raise ValueError("Equivalent groups cross development roles")
    if not baseline_only and data.get("static_complete") is not True:
        raise ValueError("Static snapshot is incomplete; no partial feedback scoring")
    return fit, feedback


def fit_and_score(job):
    fit, feedback, proposal, cv = job
    started_cpu, started_wall = time.process_time(), time.monotonic()
    policy = learning.fit_policy(
        fit, allowed_feature_subset=proposal["features"],
        max_depth=proposal.get("max_depth", 2), min_leaf=12,
    )
    scored = learning.evaluate_policy(policy, feedback, bootstrap_samples=2000,
                                      seed=proposal.get("seed", 20261104))
    cv_reports = []
    if cv:
        groups = sorted({group_id(r) for r in fit}, key=lambda g:
                        hashlib.sha256(("ta-fit-cv-v1:" + g).encode()).hexdigest())
        folds = {g: i % 5 for i, g in enumerate(groups)}
        for i in range(5):
            train = [r for r in fit if folds[group_id(r)] != i]
            test = [dict(r, role="development_feedback") for r in fit if folds[group_id(r)] == i]
            fold_policy = learning.fit_policy(
                train, allowed_feature_subset=proposal["features"],
                max_depth=proposal.get("max_depth", 2), min_leaf=12,
            )
            cv_reports.append({"fold": i, "policy": fold_policy,
                               "evaluation": learning.evaluate_policy(
                                   fold_policy, test, bootstrap_samples=0, seed=i)})
    return {"proposal": proposal, "policy": policy, "evaluation": scored,
            "fit_group_cv": cv_reports,
            "process_cpu_s": time.process_time() - started_cpu,
            "wall_s": time.monotonic() - started_wall}


def clustering_job(job):
    fit, k = job
    started = time.process_time()
    model = cluster.fit_clusters(fit, k=k, seed=20261104)
    return {"k": k, "model": model, "fit_profiles": cluster.cluster_profiles(model, fit),
            "process_cpu_s": time.process_time() - started}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--proposals", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--baseline-only", action="store_true")
    p.add_argument("--cluster", action="store_true")
    p.add_argument("--no-cv", action="store_true")
    p.add_argument("--workers", type=int, default=3)
    a = p.parse_args()
    data = json.loads(a.dataset.read_text())
    fit, feedback = validate(data, a.baseline_only)
    if a.out.exists():
        raise FileExistsError("Owner output exists; inspect/reuse instead of overwriting")
    a.out.mkdir(parents=True)
    receipt = {"dataset_sha256": sha(a.dataset), "source_sha256": sha(__file__),
               "learning_sha256": sha(learning.__file__), "cluster_sha256": sha(cluster.__file__),
               "fit_n": len(fit), "feedback_n": len(feedback),
               "baseline_only": a.baseline_only, "started_ns": time.time_ns()}
    save(a.out / "RUN_STARTED.json", receipt)
    sums = {action: sum(r["costs"][action] for r in fit) for action in ("false", "true")}
    best = min(("false", "true"), key=lambda action: sums[action])
    oracle = sum(min(r["costs"].values()) for r in fit)
    baseline = {"fit_cost_sums": sums, "fit_selected_action": best,
                "fit_oracle_cost": oracle,
                "fit_oracle_relative_gain": 1 - oracle / sums[best] if sums[best] else 0,
                "fit_parents": len(fit), "reported_timing_source": "TA"}
    save(a.out / "fit_baseline.json", baseline)
    if a.baseline_only:
        save(a.out / "COMPLETE.json", {**receipt, "status": "COMPLETE_BASELINE_ONLY"})
        print(json.dumps({"status": "COMPLETE_BASELINE_ONLY", "out": str(a.out)}))
        return
    config = json.loads(a.proposals.read_text()) if a.proposals else {}
    proposals = config.get("proposals", [])
    if len(proposals) > 2 or not proposals:
        raise ValueError("Freeze one or two proposals per formal round")
    if len({x["id"] for x in proposals}) != len(proposals):
        raise ValueError("Duplicate proposal identifiers")
    receipt["proposals_sha256"] = sha(a.proposals)
    jobs = [(fit, feedback, prop, not a.no_cv) for prop in proposals]
    control = {"id": "matched_simple_tree", "features": FEATURES, "max_depth": 2}
    jobs.append((fit, feedback, control, not a.no_cv))
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, a.workers)) as pool:
        futures = {pool.submit(fit_and_score, job): job[2]["id"] for job in jobs}
        if a.cluster:
            futures.update({pool.submit(clustering_job, (fit, k)): "cluster_k" + str(k)
                            for k in (2, 3)})
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            save(a.out / (name + ".json"), future.result())
    save(a.out / "COMPLETE.json", {**receipt, "status": "COMPLETE", "members": {
        path.name: sha(path) for path in sorted(a.out.glob("*.json"))}})
    print(json.dumps({"status": "COMPLETE", "out": str(a.out),
                      "proposal_ids": [x["id"] for x in proposals]}))


if __name__ == "__main__":
    main()
