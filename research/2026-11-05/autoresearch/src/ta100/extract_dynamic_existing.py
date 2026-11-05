"""TA100 first10: qualified existing native checkpoint, no labels or solver.

The owner commits this source/protocol before calling extract_features. All192
manifest tasks must be terminal; publish no partial table. The root scorer
retains the full240 population and gives unmatched48 parents null inputs.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ta_feature_discovery"))
import dynamic_probe as probe
import merge_dynamic as merger

COLUMNS = (
    "td_chrono_share", "td_restart_reuse_share", "td_phase_source_entropy",
    "td_target_support", "td_best_target_gap", "td_trail_momentum",
    "td_learned_database_load", "td_saved_target_polarity_gap",
    "td_learned_size_regime", "td_actual_potential_backtrack_gap",
)
ROUNDING_TOLERANCE = 1e-5


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        return None
    return float(value)


def _fraction(value):
    number = _number(value)
    if number is None or not -ROUNDING_TOLERANCE <= number <= 1 + ROUNDING_TOLERANCE:
        return None
    return min(1.0, max(0.0, number))


def checkpoint_features(checkpoint):
    """Pure arithmetic on one qualified checkpoint; no fitting or thresholds."""
    fields = checkpoint.get("f", {})
    out = dict.fromkeys(COLUMNS)
    for column, field in ((COLUMNS[0], "c_chrono_frac"), (COLUMNS[1], "c_reuse_frac"),
                          (COLUMNS[3], "x_target_set_frac")):
        out[column] = _fraction(fields.get(field))
    target, saved = (_fraction(fields.get(name)) for name in ("c_target_src_frac", "c_saved_src_frac"))
    if target is not None and saved is not None and target + saved <= 1 + ROUNDING_TOLERANCE:
        p = [target, saved, max(0.0, 1 - target - saved)]
        total = sum(p)
        p = [value / total for value in p]
        out[COLUMNS[2]] = -sum(value * math.log(value) for value in p if value > 0) / math.log(3)
    best, target_count = (_number(fields.get(name)) for name in ("x_best_frac", "x_target_frac"))
    if best is not None and target_count is not None and min(best, target_count) >= 0 and best + target_count > 0:
        out[COLUMNS[4]] = (best - target_count) / (abs(best) + abs(target_count))
    momentum = _number(fields.get("x_trail_ratio"))
    if momentum is not None and momentum >= 0:
        out[COLUMNS[5]] = momentum - 1
    database = _number(fields.get("x_red_per_irr"))
    if database is not None and database >= 0:
        out[COLUMNS[6]] = database
    target_negative, saved_negative = (_fraction(fields.get(name)) for name in ("x_target_neg_frac", "x_saved_neg_frac"))
    if target_negative is not None and saved_negative is not None:
        out[COLUMNS[7]] = target_negative - saved_negative
    recent_size, cumulative_size = (_number(fields.get(name)) for name in ("x_size_avg", "c_size_mean"))
    if recent_size is not None and cumulative_size is not None and min(recent_size, cumulative_size) > 0:
        out[COLUMNS[8]] = math.log(recent_size / cumulative_size)
    actual, potential = (_number(fields.get(name)) for name in ("x_level_avg", "x_jump_avg"))
    if actual is not None and potential is not None and min(actual, potential) >= 0 and actual + potential > 0:
        out[COLUMNS[9]] = (actual - potential) / (abs(actual) + abs(potential))
    return {name: value if value is None or math.isfinite(value) else None for name, value in out.items()}


def features_for_receipt(record):
    if record.get("status") != "COMPLETE":
        return dict.fromkeys(COLUMNS)
    # Preserve the prior qualified-event contract, including raw six-vector
    # equality, NATIVE, no prior action, >=20 events, CPU<=2 and input SHA check.
    merger._validate_complete(record)
    return checkpoint_features(record["checkpoint"])


def extract_features(manifest_path, receipts_dir, receipt_index_path, output_path=None, *,
                     expected_manifest_sha256, expected_receipt_index_sha256):
    cpu, wall = time.process_time(), time.monotonic()
    manifest, manifest_sha = merger._read_bound(manifest_path, expected_manifest_sha256)
    index, index_sha = merger._read_bound(receipt_index_path, expected_receipt_index_sha256)
    if manifest.get("profile") != probe.PROFILE or manifest.get("observer_source_sha256") != probe.OBSERVER_SOURCE_SHA:
        raise ValueError("existing probe method/profile is not qualified")
    for key in probe.IDENTITY_FIELDS:
        merger._check_sha(manifest.get(key))
    tasks = [probe.normalize_task(raw, manifest) for raw in manifest.get("tasks", [])]
    if len(tasks) != 192 or len({t["instance_id"] for t in tasks}) != 192 or len({t["task_key"] for t in tasks}) != 192:
        raise ValueError("the complete fixed192 public task manifest is required")
    entries = index.get("receipts", {})
    if index.get("manifest_sha256") != manifest_sha or set(entries) != {t["task_key"] for t in tasks}:
        raise ValueError("receipt index does not bind all192 manifest tasks")
    features, roles, statuses, source_receipts = {}, {}, collections.Counter(), {}
    reused_cpu = 0.0
    for task in tasks:
        path = Path(receipts_dir) / (task["task_key"] + ".json")
        if not path.exists():
            path = Path(receipts_dir) / "results" / path.name
        record, receipt_sha = merger._read_bound(path, entries[task["task_key"]])
        unsigned = {key: value for key, value in record.items() if key != "receipt_content_sha256"}
        if record.get("receipt_content_sha256") != merger.canonical_sha(unsigned):
            raise ValueError("invalid receipt content binding")
        expected = {"task_key": task["task_key"], "id": task["instance_id"], "instance_id": task["instance_id"],
                    "role": task["role"], "input_sha256": task["input_sha256"], "profile": probe.PROFILE,
                    "node_id": manifest.get("node_id"), **{k: manifest[k] for k in probe.IDENTITY_FIELDS}}
        if any(record.get(key) != value for key, value in expected.items()):
            raise ValueError("receipt method/task/role/input identity mismatch")
        if record.get("status") not in merger.TERMINAL or record.get("answer_adopted") is not False:
            raise ValueError("partial/unknown task or unverified adopted answer")
        charged = _number(record.get("total_accounted_cpu_s"))
        if charged is None or charged < 0:
            raise ValueError("invalid reused CPU cost")
        reused_cpu += charged
        identifier = task["instance_id"]
        features[identifier] = features_for_receipt(record)
        roles[identifier] = task["role"]
        statuses[record["status"]] += 1
        source_receipts[identifier] = {"task_key": task["task_key"], "receipt_sha256": receipt_sha,
                                       "input_sha256": task["input_sha256"]}
    counts = {column: {role: sum(features[i][column] is not None for i in features if roles[i] == role)
                       for role in ("development_fit", "development_feedback")} for column in COLUMNS}
    result = {"schema": "ta100.existing_dynamic_feature_table.v1", "complete": True,
              "expected_instance_ids": sorted(features), "columns": list(COLUMNS), "features": features,
              "bindings": {"base_manifest_sha256": manifest_sha, "receipt_index_sha256": index_sha,
                           "source_sha256": merger.sha(__file__), "probe_parser_sha256": merger.sha(probe.__file__),
                           **{k: manifest[k] for k in probe.IDENTITY_FIELDS}, "receipts": source_receipts},
              "availability": {"statuses": dict(statuses), "per_column_by_role": counts},
              "cost_summary": {"new_solver_cpu_s": 0.0, "reused_probe_cpu_s": reused_cpu,
                               "new_extraction_cpu_s": time.process_time() - cpu,
                               "new_extraction_wall_s": time.monotonic() - wall,
                               "cost_note": "Reused probe CPU is not new physical work; do not add this CPU to TA wall time."},
              "missing_contract": "Root scorer retains all240parents, unmatched48null. Any missing queried field uses fixed-control fallback.",
              "metadata_not_model_input": {"roles": roles, "fixed_population": 240}}
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as handle:
            handle.write(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "receipts-dir", "receipt-index", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-receipt-index-sha256", required=True)
    args = parser.parse_args()
    result = extract_features(args.manifest, args.receipts_dir, args.receipt_index, args.output,
                              expected_manifest_sha256=args.expected_manifest_sha256,
                              expected_receipt_index_sha256=args.expected_receipt_index_sha256)
    print(json.dumps({"complete": result["complete"], "parents": len(result["features"]),
                      "columns": len(COLUMNS), "cost_summary": result["cost_summary"]}))


if __name__ == "__main__":
    main()
