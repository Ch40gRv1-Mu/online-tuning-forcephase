"""Immutable TA100 observer table from a complete SHA-bound public shard.

No labels, model fitting, solver calls or partial-feedback scoring. A40-task
table is a pilot coverage receipt only; the common scorer requires full192.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_worker as worker

TERMINAL = {"COMPLETE", "MISSING", "EARLY_SOLVED_UNVERIFIED", "FAILED", "RESOURCE_UNAVAILABLE"}


def read_bound(path, expected):
    digest = worker.sha(path)
    if not isinstance(expected, str) or digest != expected:
        raise ValueError("raw file differs from frozen SHA: " + str(path))
    return json.loads(Path(path).read_text(), object_pairs_hook=worker._no_duplicate_keys), digest


def merge(manifest_path, receipts_dir, receipt_index_path, output_path=None, *,
          expected_manifest_sha256, expected_receipt_index_sha256):
    cpu, wall = time.process_time(), time.monotonic()
    manifest, manifest_sha = read_bound(manifest_path, expected_manifest_sha256)
    index, index_sha = read_bound(receipt_index_path, expected_receipt_index_sha256)
    if manifest.get("profile") != worker.PROFILE:
        raise ValueError("new dynamic profile differs from frozen worker source/limits")
    for name in worker.runtime.IDENTITY_FIELDS:
        value = manifest.get(name)
        if not isinstance(value, str) or not worker.runtime.common.SHA.fullmatch(value):
            raise ValueError("missing new method identity: " + name)
    if manifest["cpu_helper_sha256"] != worker.QUALIFIED_CPU_HELPER_SHA:
        raise ValueError("receipt stage did not use the qualified fractional CPU helper")
    tasks = [worker.runtime.normalize_task(task, manifest) for task in manifest.get("tasks", [])]
    if len(tasks) not in (40, 152, 192) or len({t["instance_id"] for t in tasks}) != len(tasks) or len({t["task_key"] for t in tasks}) != len(tasks):
        raise ValueError("complete fixed40/152/192 unique tasks required")
    entries = index.get("receipts")
    if index.get("manifest_sha256") != manifest_sha or not isinstance(entries, dict) or set(entries) != {t["task_key"] for t in tasks}:
        raise ValueError("raw SHA index must bind every task; partial publication forbidden")
    features, roles, records, statuses = {}, {}, {}, collections.Counter()
    observed_cpu, child_cpu, child_wall = 0.0, 0.0, 0.0
    for task in tasks:
        key = task["task_key"]
        path = Path(receipts_dir) / (key + ".json")
        if not path.exists(): path = Path(receipts_dir) / "results" / path.name
        record, receipt_sha = read_bound(path, entries[key])
        unsigned = {k: v for k, v in record.items() if k != "receipt_content_sha256"}
        if record.get("receipt_content_sha256") != hashlib.sha256(worker.runtime.common.canonical(unsigned)).hexdigest():
            raise ValueError("receipt canonical content SHA mismatch")
        expected = {"task_key": key, "id": task["instance_id"], "instance_id": task["instance_id"],
                    "role": task["role"], "input_sha256": task["input_sha256"], "profile": worker.PROFILE,
                    "node_id": manifest.get("node_id"), **{k: manifest[k] for k in worker.runtime.IDENTITY_FIELDS}}
        if any(record.get(k) != v for k, v in expected.items()):
            raise ValueError("receipt task/input/new-method/role identity mismatch")
        status = record.get("status")
        if status not in TERMINAL or record.get("answer_adopted") is not False:
            raise ValueError("nonterminal receipt or newly adopted unverified answer")
        parts = [record.get(k) for k in ("preparation_cpu_s", "feature_cpu_s", "controller_cpu_s")]
        total, elapsed = record.get("total_accounted_cpu_s"), record.get("feature_wall_s")
        if any(not worker.numeric(v) or v < 0 for v in parts + [total, elapsed]):
            raise ValueError("invalid physical CPU/wall accounting")
        if abs(sum(parts) - total) > max(1e-6, 1e-6 * total):
            raise ValueError("CPU components do not match charged total")
        values = dict.fromkeys(worker.COLUMNS)
        if status == "COMPLETE":
            if record.get("source_check") != "input_sha256_match":
                raise ValueError("qualified record lacks input identity verification")
            parsed = worker.validate_checkpoint(record.get("checkpoint", {}))
            if parsed["status"] != "COMPLETE" or parsed["features"] != record.get("features"):
                raise ValueError("COMPLETE receipt differs from actual qualified checkpoint")
            values = parsed["features"]
        elif record.get("features") is not None:
            raise ValueError("unqualified task publishes a vector")
        identifier = task["instance_id"]
        features[identifier], roles[identifier] = values, task["role"]
        observation = record.get("checkpoint", {}).get("ta100")
        records[identifier] = {"task_key": key, "receipt_sha256": receipt_sha, "input_sha256": task["input_sha256"],
                               "status": status, "support": observation.get("support") if isinstance(observation, dict) else None,
                               "caps": observation.get("caps") if isinstance(observation, dict) else None,
                               "telemetry_sha256": record.get("telemetry_sha256"), "charged_cpu_s": total}
        statuses[status] += 1
        observed_cpu += total; child_cpu += parts[1]; child_wall += elapsed
    coverage = {column: {role: sum(features[i][column] is not None for i in features if roles[i] == role)
                         for role in ("development_fit", "development_feedback")} for column in worker.COLUMNS}
    result = {"schema": "ta100.new_dynamic_feature_table.v1", "complete": True,
              "analysis_population_ready": len(tasks) == 192,
              "expected_instance_ids": sorted(features), "columns": list(worker.COLUMNS), "features": features,
              "bindings": {"base_manifest_sha256": manifest_sha, "receipt_index_sha256": index_sha,
                           "source_sha256": worker.sha(__file__), "worker_source_sha256": worker.sha(worker.__file__),
                           **{k: manifest[k] for k in worker.runtime.IDENTITY_FIELDS}, "receipts": records},
              "availability": {"scheduled": len(tasks), "statuses": dict(statuses),
                               "qualified_observations": statuses["COMPLETE"], "per_column_by_role": coverage},
              "cost_summary": {"new_probe_cpu_s": observed_cpu, "new_child_cpu_s": child_cpu,
                               "sum_child_wall_s": child_wall, "merge_cpu_s_to_payload": time.process_time() - cpu,
                               "merge_wall_s_to_payload": time.monotonic() - wall,
                               "observer_build_cost": "Referenced separately once by immutable build receipt; not charged again per field or shard.",
                               "not_added_to_TA_wall": True},
              "metadata_not_model_input": {"roles": roles, "fixed_full_population": 240},
              "missing_contract": "Root retains all240 parents, unavailable field/unmatched48null, fixed-control fallback; pilot40 never scored."}
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x") as stream:
            stream.write(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "receipts-dir", "receipt-index", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-receipt-index-sha256", required=True)
    args = parser.parse_args()
    result = merge(args.manifest, args.receipts_dir, args.receipt_index, args.output,
                   expected_manifest_sha256=args.expected_manifest_sha256,
                   expected_receipt_index_sha256=args.expected_receipt_index_sha256)
    print(json.dumps({"complete": result["complete"], "analysis_population_ready": result["analysis_population_ready"],
                      "availability": result["availability"], "cost_summary": result["cost_summary"]}, sort_keys=True))


if __name__ == "__main__": main()
