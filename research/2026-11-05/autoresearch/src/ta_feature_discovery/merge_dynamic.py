"""Merge a fully terminal dynamic stage into an immutable development snapshot.

This command performs no fitting or solver work. Raw receipt bytes must be
bound by an independently saved SHA index; self-digests are checked as well.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import math
from pathlib import Path

try:
    from . import dynamic_probe as probe, learning
except ImportError:
    import dynamic_probe as probe
    import learning

TERMINAL = frozenset({"COMPLETE", "MISSING", "EARLY_SOLVED_UNVERIFIED", "FAILED", "RESOURCE_UNAVAILABLE"})


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha(value):
    return hashlib.sha256(probe.common.canonical(value)).hexdigest()


def _number(value):
    if isinstance(value, (str, bool)) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("nonfinite or nonnumeric dynamic value/accounting")
    return float(value)


def _check_sha(value):
    if not isinstance(value, str) or not probe.common.SHA.fullmatch(value):
        raise ValueError("invalid SHA256 binding")
    return value


def _read_bound(path, expected):
    digest = sha(path)
    if expected is not None and digest != _check_sha(expected):
        raise ValueError("raw file SHA256 differs from frozen binding: " + str(path))
    return json.loads(Path(path).read_text()), digest


def _validate_complete(record):
    values = record.get("features")
    if not isinstance(values, dict) or set(values) != set(probe.FEATURE_MAP):
        raise ValueError("COMPLETE requires exactly six dynamic fields")
    result = {raw: _number(values[output]) for output, raw in probe.FEATURE_MAP.items()}
    checkpoint = record.get("checkpoint", {})
    crossed = checkpoint.get("crossed", [])
    if (checkpoint.get("action") != "NATIVE" or len(crossed) != 2 or crossed[0] != 1000 or
            crossed[1] < 1000 or checkpoint.get("conflicts", 0) < 1000 or
            checkpoint.get("f", {}).get("r_switches") != 0 or
            not isinstance(checkpoint.get("learned"), int) or isinstance(checkpoint.get("learned"), bool) or
            checkpoint["learned"] < probe.PROFILE["min_learned"] or
            not 0 <= _number(checkpoint.get("process_cpu_s")) <= probe.PROFILE["cpu_limit_s"]):
        raise ValueError("unqualified COMPLETE checkpoint")
    for name, value in result.items():
        if _number(checkpoint.get("f", {}).get(name)) != value:
            raise ValueError("dynamic vector differs from raw checkpoint")
    if record.get("source_check") != "input_sha256_match":
        raise ValueError("COMPLETE lacks input identity verification")
    return result


def merge_dynamic(static_path, manifest_path, receipts_dir, receipt_sha_index_path,
                  output_path=None, *, expected_static_sha256=None,
                  expected_manifest_sha256=None, expected_receipt_index_sha256=None):
    """Return merged payload; optionally save a new immutable JSON file.

    SHA index format: {"manifest_sha256": RAW_MANIFEST_SHA,
    "receipts": {TASK_KEY: RAW_RECEIPT_SHA}}. The index's digest is preserved
    in the result and may be supplied as a frozen expected digest at invocation.
    The manifest contains exactly 40 or 192 disjoint fit/feedback tasks.
    """
    payload, static_sha = _read_bound(static_path, expected_static_sha256)
    rows = learning.validate_development_payload(payload)
    if len(rows) != 240 or collections.Counter(r["role"] for r in rows) != {
            learning.FIT_ROLE: 180, learning.FEEDBACK_ROLE: 60}:
        raise ValueError("a complete 180-fit/60-feedback static snapshot is required")
    if any(set(r["features"]) & learning.DYNAMIC_FEATURES for r in rows):
        raise ValueError("input must be a static-only immutable snapshot")
    by_id = {r["id"]: r for r in rows}
    manifest, manifest_sha = _read_bound(manifest_path, expected_manifest_sha256)
    if manifest.get("profile") != probe.PROFILE:
        raise ValueError("dynamic method profile differs from frozen implementation")
    if manifest.get("observer_source_sha256") != probe.OBSERVER_SOURCE_SHA:
        raise ValueError("unqualified observer method SHA")
    for field in probe.IDENTITY_FIELDS:
        _check_sha(manifest.get(field))
    if not isinstance(manifest.get("node_id"), str) or not probe.common.SAFE_ID.fullmatch(manifest["node_id"]):
        raise ValueError("invalid manifest node")
    tasks = [probe.normalize_task(t, manifest) for t in manifest.get("tasks", [])]
    if len(tasks) not in (40, 192) or len({t["task_key"] for t in tasks}) != len(tasks) or len({t["instance_id"] for t in tasks}) != len(tasks):
        raise ValueError("dynamic manifest must contain exactly 40 or 192 unique tasks")
    for task in tasks:
        row = by_id.get(task["instance_id"])
        if row is None or row["role"] != task["role"] or not row.get("eligible", True):
            raise ValueError("task identity/role/eligibility differs from static population")
        source = row.get("feature_source", {})
        known_sha = source.get("input_sha256")
        if known_sha is not None and task["input_sha256"] != known_sha:
            raise ValueError("dynamic input SHA differs from static input SHA")
    index, index_sha = _read_bound(receipt_sha_index_path, expected_receipt_index_sha256)
    if index.get("manifest_sha256") != manifest_sha:
        raise ValueError("receipt index belongs to another raw manifest")
    entries = index.get("receipts")
    if not isinstance(entries, dict) or set(entries) != {t["task_key"] for t in tasks}:
        raise ValueError("all manifest tasks must have a raw receipt SHA; partial feedback is forbidden")
    merged = copy.deepcopy(payload)
    out_rows = {r["id"]: r for r in merged["rows"]}
    for row in out_rows.values():
        row["dynamic_status"] = "NOT_SCHEDULED"
        row["dynamic_cpu_s"] = None
    statuses, fee, child_cpu, wall = collections.Counter(), 0.0, 0.0, 0.0
    by_role = {role: collections.Counter() for role in (learning.FIT_ROLE, learning.FEEDBACK_ROLE)}
    receipt_bindings = {}
    for task in tasks:
        key = task["task_key"]
        receipt_path = Path(receipts_dir) / (key + ".json")
        if not receipt_path.exists():
            receipt_path = Path(receipts_dir) / "results" / (key + ".json")
        record, raw_sha = _read_bound(receipt_path, _check_sha(entries[key]))
        unsigned = {k: v for k, v in record.items() if k != "receipt_content_sha256"}
        if record.get("receipt_content_sha256") != canonical_sha(unsigned):
            raise ValueError("receipt canonical content digest mismatch")
        expected = {"task_key": key, "instance_id": task["instance_id"], "id": task["instance_id"],
                    "role": task["role"], "input_sha256": task["input_sha256"], "profile": probe.PROFILE,
                    "node_id": manifest["node_id"], **{k: manifest[k] for k in probe.IDENTITY_FIELDS}}
        if any(record.get(k) != value for k, value in expected.items()):
            raise ValueError("receipt method/task/input/role identity mismatch")
        status = record.get("status")
        if status not in TERMINAL or record.get("answer_adopted") is not False:
            raise ValueError("nonterminal receipt or unverified adopted answer")
        charged = _number(record.get("total_accounted_cpu_s"))
        components = [_number(record.get(k)) for k in ("preparation_cpu_s", "feature_cpu_s", "controller_cpu_s")]
        elapsed = _number(record.get("feature_wall_s"))
        if min([charged, elapsed] + components) < 0 or not math.isclose(charged, sum(components), abs_tol=1e-6, rel_tol=1e-6):
            raise ValueError("invalid dynamic cost accounting")
        row = out_rows[task["instance_id"]]
        if status == "COMPLETE":
            row["features"].update(_validate_complete(record))
        elif record.get("features") is not None:
            raise ValueError("non-COMPLETE task must not publish a partial vector")
        row.update(dynamic_status=status, dynamic_cpu_s=charged,
                   dynamic_source={"task_key": key, "input_sha256": task["input_sha256"],
                                   "receipt_sha256": raw_sha, "receipt_content_sha256": record["receipt_content_sha256"],
                                   "telemetry_sha256": record.get("telemetry_sha256")})
        statuses[status] += 1
        by_role[row["role"]][status] += 1
        fee += charged; child_cpu += components[1]; wall += elapsed
        receipt_bindings[key] = raw_sha
    merged.update(schema="ta_feature_discovery.development.dynamic.v1", dynamic_complete=True,
                  dynamic_method={"profile": probe.PROFILE, **{k: manifest[k] for k in probe.IDENTITY_FIELDS},
                                  "feature_map": dict(probe.FEATURE_MAP)},
                  dynamic_bindings={"static_dataset_sha256": static_sha, "manifest_sha256": manifest_sha,
                                    "receipt_index_sha256": index_sha, "receipts": receipt_bindings},
                  dynamic_summary={"parents": 240, "scheduled": len(tasks), "statuses": dict(statuses),
                                   "by_role": {k: dict(v) for k, v in by_role.items()},
                                   "complete_vectors": statuses["COMPLETE"],
                                   "coverage_scheduled": statuses["COMPLETE"] / len(tasks),
                                   "coverage_population": statuses["COMPLETE"] / 240,
                                   "total_accounted_cpu_s": fee, "child_cpu_s": child_cpu,
                                   "sum_child_wall_s": wall,
                                   "cost_units": "local CPU/wall; never added to TA wall target",
                                   "fallback": "frozen static policy for every unavailable dynamic vector"})
    merged["feature_names"] = list(payload.get("feature_names", [])) + sorted(learning.DYNAMIC_FEATURES)
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(merged, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if output.exists():
            if output.read_text() != encoded:
                raise FileExistsError("refusing to overwrite an immutable dynamic snapshot")
        else:
            with output.open("x") as handle:
                handle.write(encoded)
    return merged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("static", "manifest", "receipts-dir", "receipt-index", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in ("static", "manifest", "receipt-index"):
        parser.add_argument("--expected-" + name + "-sha256")
    args = parser.parse_args()
    result = merge_dynamic(args.static, args.manifest, args.receipts_dir, args.receipt_index, args.output,
                           expected_static_sha256=args.expected_static_sha256,
                           expected_manifest_sha256=args.expected_manifest_sha256,
                           expected_receipt_index_sha256=args.expected_receipt_index_sha256)
    print(json.dumps(result["dynamic_summary"], sort_keys=True))


if __name__ == "__main__":
    main()
