"""New TA100 observer identities on the qualified bounded native-D runtime.

Profile/source must be committed and root manifests frozen before any run.
This module never builds, extends a probe budget, or adopts early answers.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ta_feature_discovery"))
_runtime_path = Path(__file__).resolve().parents[1] / "ta_feature_discovery/dynamic_probe.py"
_runtime_spec = importlib.util.spec_from_file_location("ta100_private_probe_runtime", _runtime_path)
runtime = importlib.util.module_from_spec(_runtime_spec)
_runtime_spec.loader.exec_module(runtime)

OBSERVER = "ta100-observer-v1"
QUALIFIED_CPU_HELPER_SHA = "7b0e95364847b13f54268cd2b2f5e383839169ca0a613460b05e202c11d8d3e2"
COLUMNS = (
    "td_learned_pure_sign_balance", "td_reason_sign_transmission", "td_sign_lifetime_gap",
    "td_resolution_compression", "td_reason_depth", "td_reason_reconvergence",
    "td_uip_trail_localization", "td_cut_level_entropy", "td_clause_target_phase_violation",
    "td_conflict_variable_turnover", "td_bump_concentration", "td_activity_rank_enrichment",
    "td_learned_recurrence", "td_learned_postassertion_reuse_age", "td_blocker_success_share",
    "td_restart_signed_retention", "td_chrono_redecision_flip", "td_conflict_burstiness",
    "td_glue_size_dependence", "td_lemma_dependency_depth",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


PROFILE = {**runtime.PROFILE, "kind": "native_d_ta100_prefix_v1", "observer": OBSERVER,
           "max_stage_cpu_s": 1000.0, "min_observed_learned": 20,
           "field_missing_is_independent": True, "feature_names": list(COLUMNS),
           "worker_source_sha256": sha(__file__), "probe_runtime_sha256": sha(runtime.__file__),
           "common_worker_sha256": sha(runtime.common.__file__)}


def _no_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate telemetry JSON field: " + key)
        value[key] = item
    return value


def numeric(value):
    return not isinstance(value, bool) and isinstance(value, (float, int)) and math.isfinite(value)


def validate_checkpoint(row):
    crossed = row.get("crossed", [])
    if (row.get("type") != "checkpoint" or len(crossed) != 2 or crossed[0] != 1000 or crossed[1] < 1000 or
            row.get("conflicts", 0) < 1000 or row.get("action") != "NATIVE" or row.get("f", {}).get("r_switches") != 0):
        raise ValueError("not the first pre-action natural restart crossing1000")
    cpu, learned = row.get("process_cpu_s"), row.get("learned")
    if not numeric(cpu) or cpu < 0 or isinstance(learned, bool) or not isinstance(learned, int) or learned < 0:
        raise ValueError("invalid absolute CPU or learning-event count")
    if cpu > PROFILE["cpu_limit_s"]:
        return {"status": "MISSING", "missing_reason": "observer_computation_after_cpu_limit", "checkpoint": row}
    observation = row.get("ta100")
    if not isinstance(observation, dict) or observation.get("observer") != OBSERVER:
        raise ValueError("missing new observer namespace; oldCOMPLETE cannot be reused")
    observed = observation.get("support", {}).get("learned")
    if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
        raise ValueError("missing main-CDCL observation event support")
    if learned < PROFILE["min_learned"] or observed < PROFILE["min_observed_learned"]:
        return {"status": "MISSING", "missing_reason": "fewer_than20_qualified_learning_events", "checkpoint": row}
    values = observation.get("features")
    if not isinstance(values, dict) or set(values) != set(COLUMNS):
        raise ValueError("observer must emit exactly20 declared fields")
    if any(value is not None and not numeric(value) for value in values.values()):
        raise ValueError("new observer values must be finite numbers or null")
    # Qualification refers to the pre-action observation, not all20 fields.
    return {"status": "COMPLETE", "features": dict(values), "checkpoint": row,
            "per_field_available": {name: values[name] is not None for name in COLUMNS}}


def parse_telemetry(path, require_complete=False):
    path = Path(path)
    if not path.exists(): return None
    content = path.read_bytes()
    if len(content) > 8 * 1024**2:
        raise ValueError("new observer telemetry exceeds8MiB")
    lines = content.splitlines(keepends=True)
    truncated = False
    if lines and not lines[-1].endswith(b"\n"):
        truncated = True
        lines.pop()
    if not lines:
        if require_complete and truncated: raise ValueError("truncated before qualified observer checkpoint")
        return None
    header = json.loads(lines[0], object_pairs_hook=_no_duplicate_keys)
    expected = {"type": "header", "schema": 2, "controller": "v2", "observer": OBSERVER,
                "mode": 3, "track": "C", "a0": "NATIVE", "a1": "NATIVE", "init": 0,
                "win": 2000000000, "at": 1000, "period": 0, "maxsw": 1, "rlim": 0,
                "opt_phase": 1, "opt_forcephase": 0, "opt_seed": 0}
    if any(header.get(key) != value for key, value in expected.items()):
        raise ValueError("new observer header differs from frozen native-D flags")
    for line in lines[1:]:
        record = json.loads(line, object_pairs_hook=_no_duplicate_keys)
        if record.get("type") == "switch":
            raise ValueError("action occurred before the first observation")
        if record.get("type") == "checkpoint":
            return validate_checkpoint(record)
    if require_complete and truncated:
        raise ValueError("truncated before qualified observer checkpoint")
    return None


def load_manifest(path, solver, helper, observer_source):
    manifest = json.loads(Path(path).read_text())
    source_path = Path(observer_source)
    binding = json.loads(source_path.read_text())
    files = binding.get("all_source_files")
    if binding.get("observer") != OBSERVER or not isinstance(files, dict) or not files:
        raise ValueError("new observer requires a full-source bundle manifest")
    digest = hashlib.sha256(runtime.common.canonical(files)).hexdigest()
    if binding.get("observer_source_sha256") != digest:
        raise ValueError("observer full source bundle digest mismatch")
    actual = {str(p.relative_to(source_path.parent / "src")): sha(p)
              for p in (source_path.parent / "src").rglob("*")
              if p.is_file() and p.suffix in (".cpp", ".hpp", ".h", ".c")}
    if actual != files:
        raise ValueError("observer source bundle changed after its immutable receipt")
    expected = {"solver_binary_sha256": sha(solver), "cpu_helper_sha256": sha(helper),
                "observer_source_sha256": digest, "profile": PROFILE}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("manifest binary/helper/source-bundle/profile mismatch")
    if expected["cpu_helper_sha256"] != QUALIFIED_CPU_HELPER_SHA:
        raise ValueError("fractional CPU helper differs from qualified helper")
    for key in ("experiment_id", "shard_id", "node_id"):
        if not runtime.common.SAFE_ID.fullmatch(str(manifest.get(key, ""))):
            raise ValueError("unsafe manifest ownership identity")
    allocation = manifest.get("allocated_cpu_s")
    if not numeric(allocation) or not 0 < allocation <= PROFILE["max_stage_cpu_s"]:
        raise ValueError("owner allocation must stay within1000CPU seconds per stage")
    tasks = [runtime.normalize_task(raw, manifest) for raw in manifest.get("tasks", [])]
    if len(tasks) not in (40, 152, 192) or len({t["task_key"] for t in tasks}) != len(tasks) or len({t["instance_id"] for t in tasks}) != len(tasks):
        raise ValueError("only complete fixed40/152/192 unique public shards are supported")
    manifest["tasks"] = tasks
    return manifest


# The old runtime keeps its exact D command, helper, timeout, owner lock,
# resource admission and failure charging. These replacements define a new
# module/process-local method identity, never edit the old runtime on disk.
runtime.PROFILE = PROFILE
runtime.OBSERVER_VERSION = OBSERVER
runtime.FEATURE_MAP = {name: name for name in COLUMNS}
runtime.parse_telemetry = parse_telemetry
runtime.load_manifest = load_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("profile")
    runner = sub.add_parser("run")
    for name in ("manifest", "solver", "cpu-helper", "observer-source", "output-dir"):
        runner.add_argument("--" + name, type=Path, required=True)
    runner.add_argument("--node-id", required=True)
    runner.add_argument("--cpu-set", required=True)
    runner.add_argument("--max-workers", type=int, default=1)
    runner.add_argument("--input-cache", type=Path)
    args = parser.parse_args()
    print(json.dumps(PROFILE if args.command == "profile" else runtime.run(args), sort_keys=True))


if __name__ == "__main__":
    main()
