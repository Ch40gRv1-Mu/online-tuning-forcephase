"""Replay the frozen root-unit-propagation refinement on 2022 timings."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import math
from pathlib import Path
import resource
import subprocess
import time

import numpy as np

from .common import sha, write
from .structural_clusters import ACTIONS, DATA, load, read_csv, summarize_policy, write_csv


SCC_THRESHOLD = 0.10
FIXED_SHARE_THRESHOLD = 0.90
SOLVER_BUDGET = 600
FEATURE_TIMEOUT = 5
MAX_BYTES = 3_050_000


def measure(key, target, raw_cache, case_cache, verifier, extractor):
    result = {"instance_key": key, "status": "missing_input", "extra_cpu_s": 0.0}
    compressed = raw_cache / f"{key}.cnf.gz"
    if not compressed.is_file() and key not in case_cache:
        return result
    try:
        if compressed.is_file():
            with gzip.open(compressed, "rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
        else:
            raw = case_cache[key].read_bytes()
        if len(raw) > MAX_BYTES:
            raise ValueError("cached CNF exceeds resource scope")
        checked = subprocess.check_output([str(verifier)], input=raw, timeout=FEATURE_TIMEOUT).split()
        if checked[0].decode() != key:
            raise ValueError("cached CNF identity mismatch")
        result["verified"] = True
        result["identity_cpu_s"] = float(checked[4])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result.update(status="input_error", error=type(error).__name__ + ": " + str(error))
        return result

    try:
        text = subprocess.check_output([str(extractor), "--root-up"], input=raw, timeout=FEATURE_TIMEOUT)
        cpu, score, fixed, conflict, assigned, residual, binaries, clauses, original_binaries = map(float, text.split())
        result["extra_cpu_s"] = cpu
        if not math.isclose(score, target, rel_tol=1e-9, abs_tol=1e-11):
            raise ValueError("original SCC score disagrees with bound receipt")
        if not (math.isfinite(cpu) and 0 <= cpu <= FEATURE_TIMEOUT and 0 <= fixed <= 1 + 1e-12 and conflict in (0, 1)):
            raise ValueError("invalid root propagation receipt")
        result.update(status="root_conflict" if conflict else "ok", score=score,
                      fixed_demand_share=min(1, fixed), root_assigned_variables=int(assigned),
                      residual_clauses=int(residual), residual_binary=int(binaries),
                      input_clauses=int(clauses), input_binary=int(original_binaries))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result.update(status="extractor_error", extra_cpu_s=FEATURE_TIMEOUT,
                      error=type(error).__name__ + ": " + str(error))
    return result


def par2(costs, actions, h):
    selected = costs[np.arange(len(costs)), actions]
    return np.where((selected < 2 * SOLVER_BUDGET) & (selected + h <= SOLVER_BUDGET),
                    selected + h, 2 * SOLVER_BUDGET)


def summarize(costs, actions, h, groups, shapes):
    paid = par2(costs, actions, h)
    baseline = costs[:, 0]
    details = summarize_policy(costs, actions, groups, chosen=paid)
    detail_shape = summarize_policy(costs, actions, shapes, chosen=paid)
    return {
        **details,
        "paired_structural_block_bootstrap_95_pct": detail_shape["paired_group_bootstrap_95_pct"],
        "rescued_D_timeouts": int(((baseline == 1200) & (paid < 1200)).sum()),
        "lost_D_solves": int(((baseline < 1200) & (paid == 1200)).sum()),
        "net_savings_s": float((baseline - paid).sum()),
        "assessed_feature_cpu_s": float(h.sum()),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--case-panel", type=Path, required=True)
    ap.add_argument("--verifier", type=Path, required=True)
    ap.add_argument("--extractor", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4, choices=range(1, 9))
    args = ap.parse_args()
    start, cpu_start = time.monotonic(), time.process_time()
    usage0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    keys, X, costs, _, groups, _ = load()
    matrix_path = DATA / "raw_data_20261110/matrix.csv"
    source_path = DATA / "scc_demand_transfer_20261110/predictions.csv"
    matrix = {r["instance_key"]: r for r in read_csv(matrix_path)}
    source = {r["instance_key"]: r for r in read_csv(source_path)}
    if matrix.keys() != source.keys() or set(keys) != set(source):
        raise ValueError("mismatched retained 2022 population")
    if any(matrix[k]["complete"] != "True" or any(float(matrix[k][a + "_par2"]) != costs[i, j]
                                                  for j, a in enumerate(ACTIONS)) for i, k in enumerate(keys)):
        raise ValueError("inconsistent or incomplete imported timing matrix")
    original = np.array([source[k]["newly_covered"] == "False" for k in keys])
    probe = np.array([source[k]["extracted"] == "True" for k in keys])
    trigger = np.array([source[k]["action"] == "Fminus" for k in keys])
    if not np.array_equal(trigger, [float(source[k]["scc_demand_share"] or 0) > SCC_THRESHOLD for k in keys]):
        raise ValueError("baseline action disagrees with frozen threshold")
    if (int(probe.sum()), int(trigger.sum()), int((trigger & original).sum())) != (2843, 293, 254):
        raise ValueError("unexpected scope or baseline support")
    case_cache = {r["instance_key"]: args.case_panel / "cnf" / (r["case"] + ".cnf")
                  for r in read_csv(args.case_panel / "association_only.csv")}
    selected_keys = [k for k, switched in zip(keys, trigger) if switched]
    args.out.mkdir(parents=True, exist_ok=False)

    def extract(k):
        return measure(k, float(source[k]["scc_demand_share"]), args.cache, case_cache,
                       args.verifier.resolve(), args.extractor.resolve())

    collection_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        receipts = {r["instance_key"]: r for r in pool.map(extract, selected_keys)}
    with (args.out / "feature_receipts.jsonl").open("w") as stream:
        for receipt in receipts.values():
            stream.write(json.dumps(receipt, sort_keys=True) + "\n")
    elapsed = time.monotonic() - collection_start
    usage1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    new_h = np.array([receipts.get(k, {}).get("extra_cpu_s", 0) for k in keys])
    old_h = np.array([float(source[k]["feature_cpu_s"]) for k in keys])
    ok = np.array([receipts.get(k, {}).get("status") == "ok" for k in keys])
    retained = np.array([receipts.get(k, {}).get("fixed_demand_share", -1) >= FIXED_SHARE_THRESHOLD for k in keys]) & ok

    # Block on similar unsigned CNF size and clause shape as a dependence sensitivity.
    bins = np.column_stack((np.floor(X[:, 0] / math.log(2)),
                            np.floor(np.expm1(X[:, 2]) * 2),
                            np.minimum(19, np.floor(X[:, 4] * 20)),
                            np.minimum(49, np.floor(X[:, 3] * 50)))).astype(int)
    shapes = np.array(["/".join(map(str, row)) for row in bins])
    groups = np.asarray(groups)
    policies = {
        "fixed_D": (np.zeros(len(keys), dtype=int), np.zeros(len(keys))),
        "SCC_original": (2 * (trigger & original), old_h * original),
        "SCC_root_guard_original": (2 * (retained & original), (old_h + new_h) * original),
        "SCC_root_guard_Fplus_original": ((retained & original).astype(int), (old_h + new_h) * original),
        "SCC_root_mixed_original": (np.where(retained & original, 2, ok & trigger & original), (old_h + new_h) * original),
        "SCC_extended": (2 * trigger, old_h),
        "SCC_root_guard_extended": (2 * retained, old_h + new_h),
    }
    report = {}
    predictions = [{"instance_key": key, "shape_block": shapes[i],
                    "original_scope": bool(original[i] and probe[i]),
                    "old_extractor_cpu_s": old_h[i], "root_extractor_cpu_s": new_h[i],
                    "root_status": receipts.get(key, {}).get("status", "not_triggered"),
                    "fixed_demand_share": receipts.get(key, {}).get("fixed_demand_share")}
                   for i, key in enumerate(keys)]
    extended_only = ~original & probe
    for name, (action, cost) in policies.items():
        result = summarize(costs, action, cost, groups, shapes)
        if name.endswith("extended"):
            mask = extended_only
            result["added_855_only"] = summarize(costs[mask], action[mask], cost[mask], groups[mask], shapes[mask])
        report[name] = result
        for i, value in enumerate(par2(costs, action, cost)):
            predictions[i][name + "_action"] = ACTIONS[action[i]]
            predictions[i][name + "_par2"] = float(value)
        print(f"{name}: {result['par2_improvement_pct']:+.6f}%, "
              f"solved {result['solved']}, fixed-shape interval {result['paired_structural_block_bootstrap_95_pct']}", flush=True)

    reference_action, reference_h = policies["SCC_original"]
    candidate_action, candidate_h = policies["SCC_root_guard_original"]
    delta = par2(costs, reference_action, reference_h) - par2(costs, candidate_action, candidate_h)
    _, block_index = np.unique(shapes, return_inverse=True)
    gains = np.bincount(block_index, weights=costs[:, 0] - par2(costs, candidate_action, candidate_h))
    rescues = (costs[:, 0] == 1200) & (par2(costs, candidate_action, candidate_h) < 1200)
    report["primary_increment"] = {
        "saved_PAR2_s_against_SCC_original": float(delta.sum()),
        "removed_switches": int(((reference_action == 2) & (candidate_action == 0)).sum()),
        "rescues": int(rescues.sum()), "rescue_shape_blocks": int(len(set(shapes[rescues]))),
        "shape_blocks": len(gains), "largest_block_gain_s": float(gains.max()),
        "net_gain_without_largest_block_s": float(gains.sum() - gains.max()),
    }
    write_csv(args.out / "predictions.csv", predictions)
    write(args.out / "summary.json", {
        "parents": len(keys), "root_feature_attempts": len(receipts), "root_feature_ok": int(ok.sum()),
        "root_feature_retained": int(retained.sum()), "old_matrix_sha256": sha(matrix_path),
        "old_predictions_sha256": sha(source_path), "extractor_sha256": sha(args.extractor),
        "verifier_sha256": sha(args.verifier), "new_solver_calls": 0,
        "collection_wall_s": elapsed, "total_wall_s": time.monotonic() - start,
        "collector_and_analysis_cpu_s": time.process_time() - cpu_start,
        "child_cpu_s": usage1.ru_utime + usage1.ru_stime - usage0.ru_utime - usage0.ru_stime,
        "incremental_root_feature_cpu_s": float(new_h.sum()), "policies": report,
    })


if __name__ == "__main__":
    main()
