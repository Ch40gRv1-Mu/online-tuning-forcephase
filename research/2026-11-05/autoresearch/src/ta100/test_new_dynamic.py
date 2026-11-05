"""New observer parser/merger properties on synthetic traces and receipts."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_worker as worker
import merge_new_dynamic as merger


def header():
    return {"type": "header", "schema": 2, "controller": "v2", "observer": worker.OBSERVER,
            "mode": 3, "track": "C", "a0": "NATIVE", "a1": "NATIVE", "init": 0,
            "win": 2000000000, "at": 1000, "period": 0, "maxsw": 1, "rlim": 0,
            "opt_phase": 1, "opt_forcephase": 0, "opt_seed": 0}


def checkpoint():
    values = dict.fromkeys(worker.COLUMNS, .25)
    values["td_reason_depth"] = None
    return {"type": "checkpoint", "crossed": [1000, 1000], "conflicts": 1100, "action": "NATIVE",
            "f": {"r_switches": 0}, "learned": 100, "process_cpu_s": 1.5,
            "ta100": {"observer": worker.OBSERVER, "features": values,
                      "support": {"learned": 90, "reason_queries": 2}, "caps": {"reason_cap": True}}}


class ParserProperties(unittest.TestCase):
    def test_runtime_namespace_does_not_mutate_old_probe_module(self):
        import dynamic_probe as old
        self.assertIsNot(old, worker.runtime)
        self.assertEqual(old.OBSERVER_VERSION, "ta-probe-v1")
        self.assertNotEqual(old.PROFILE, worker.PROFILE)

    def test_per_field_null_is_qualified_and_later_terminal_or_partial_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "log.jsonl"
            path.write_text(json.dumps(header()) + "\n" + json.dumps(checkpoint()) + '\n{"unrelated_partial":')
            result = worker.parse_telemetry(path, require_complete=True)
            self.assertEqual(result["status"], "COMPLETE")
            self.assertIsNone(result["features"]["td_reason_depth"])
            self.assertEqual(sum(result["per_field_available"].values()), 19)

    def test_cpu_includes_observer_and_both_event_supports_are_required(self):
        cp = checkpoint()
        cp["process_cpu_s"] = 2.0001
        self.assertEqual(worker.validate_checkpoint(cp)["status"], "MISSING")
        cp = checkpoint(); cp["ta100"]["support"]["learned"] = 19
        self.assertEqual(worker.validate_checkpoint(cp)["status"], "MISSING")
        for change in ({"action": "NEGATIVE"}, {"f": {"r_switches": 1}}, {"ta100": None}):
            with self.assertRaises(ValueError): worker.validate_checkpoint(checkpoint() | change)

    def test_old_observer_or_duplicate_cpu_or_nonfinite_new_field_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "log.jsonl"
            old = header() | {"observer": "ta-probe-v1"}
            path.write_text(json.dumps(old) + "\n" + json.dumps(checkpoint()) + "\n")
            with self.assertRaises(ValueError): worker.parse_telemetry(path)
            duplicated = json.dumps(checkpoint())[:-1] + ',"process_cpu_s":0.1}\n'
            path.write_text(json.dumps(header()) + "\n" + duplicated)
            with self.assertRaises(ValueError): worker.parse_telemetry(path)
        cp = checkpoint(); cp["ta100"]["features"][worker.COLUMNS[0]] = float("nan")
        with self.assertRaises(ValueError): worker.validate_checkpoint(cp)

    def test_full_source_binding_checked_before_any_task_can_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / "src"; source.mkdir()
            cpp = source / "ta100_observer.cpp"; cpp.write_text("synthetic-only source fixture")
            files = {cpp.name: worker.sha(cpp)}
            bundle = hashlib.sha256(worker.runtime.common.canonical(files)).hexdigest()
            binding = root / "TA100_SOURCE_BINDINGS.json"
            binding.write_text(json.dumps({"observer": worker.OBSERVER, "all_source_files": files, "observer_source_sha256": bundle}))
            manifest = {"observer_source_sha256": bundle, "solver_binary_sha256": "b" * 64,
                        "cpu_helper_sha256": worker.QUALIFIED_CPU_HELPER_SHA, "profile": worker.PROFILE,
                        "experiment_id": "synthetic", "shard_id": "pilot40", "node_id": "testnode",
                        "allocated_cpu_s": 1000, "tasks": [{"instance_id": "p" + str(i), "role": "development_fit",
                            "input_sha256": "d" * 64, "public_url": "https://benchmark-database.de/file/p" + str(i)} for i in range(40)]}
            path = root / "manifest.json"; path.write_text(json.dumps(manifest))
            original_sha = worker.sha
            def fixture_sha(path):
                if str(path) == "synthetic-helper": return worker.QUALIFIED_CPU_HELPER_SHA
                if str(path) == "synthetic-binary": return "b" * 64
                return original_sha(path)
            with mock.patch.object(worker, "sha", side_effect=fixture_sha):
                result = worker.load_manifest(path, "synthetic-binary", "synthetic-helper", binding)
                self.assertEqual(len(result["tasks"]), 40)
                cpp.write_text("changed source")
                with self.assertRaises(ValueError): worker.load_manifest(path, "synthetic-binary", "synthetic-helper", binding)


class MergeProperties(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.receipts = self.root / "results"; self.receipts.mkdir()
        self.manifest_path, self.index_path = self.root / "manifest.json", self.root / "index.json"
        identity = {"observer_source_sha256": "a" * 64, "solver_binary_sha256": "b" * 64,
                    "cpu_helper_sha256": worker.QUALIFIED_CPU_HELPER_SHA}
        self.manifest = {**identity, "profile": worker.PROFILE, "node_id": "synthetic", "tasks": []}
        index = {}
        for i in range(40):
            task = worker.runtime.normalize_task({"instance_id": "p" + str(i), "role": "development_fit" if i < 30 else "development_feedback",
                "input_sha256": "d" * 64, "public_url": "https://benchmark-database.de/file/p" + str(i)}, self.manifest)
            self.manifest["tasks"].append(task)
            cp = checkpoint()
            record = {**identity, "profile": worker.PROFILE, "task_key": task["task_key"], "id": task["instance_id"],
                      "instance_id": task["instance_id"], "role": task["role"], "input_sha256": task["input_sha256"],
                      "node_id": "synthetic", "status": "COMPLETE" if i else "EARLY_SOLVED_UNVERIFIED", "answer_adopted": False,
                      "source_check": "input_sha256_match", "checkpoint": cp,
                      "features": cp["ta100"]["features"] if i else None,
                      "preparation_cpu_s": .1, "feature_cpu_s": 1.6, "controller_cpu_s": .1,
                      "total_accounted_cpu_s": 1.8, "feature_wall_s": 2.0}
            record["receipt_content_sha256"] = hashlib.sha256(worker.runtime.common.canonical(record)).hexdigest()
            path = self.receipts / (task["task_key"] + ".json"); path.write_text(json.dumps(record))
            index[task["task_key"]] = worker.sha(path)
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.index_path.write_text(json.dumps({"manifest_sha256": worker.sha(self.manifest_path), "receipts": index}))

    def merge(self, output=None):
        return merger.merge(self.manifest_path, self.receipts, self.index_path, output,
            expected_manifest_sha256=worker.sha(self.manifest_path), expected_receipt_index_sha256=worker.sha(self.index_path))

    def test_pilot40_is_coverage_only_preserves_missing_and_costs(self):
        result = self.merge()
        self.assertTrue(result["complete"]); self.assertFalse(result["analysis_population_ready"])
        self.assertEqual(len(result["features"]), 40)
        self.assertEqual(result["availability"]["qualified_observations"], 39)
        self.assertTrue(all(v is None for v in result["features"]["p0"].values()))
        self.assertIsNone(result["features"]["p1"]["td_reason_depth"])
        self.assertAlmostEqual(result["cost_summary"]["new_probe_cpu_s"], 72)

    def test_partial_or_hash_changed_receipts_never_publish_table(self):
        path = next(self.receipts.iterdir()); path.write_text(path.read_text() + " ")
        out = self.root / "out.json"
        with self.assertRaises(ValueError): self.merge(out)
        self.assertFalse(out.exists())
        path.unlink()
        with self.assertRaises(FileNotFoundError): self.merge(out)
        self.assertFalse(out.exists())

    def test_gate_task_is_forbidden_and_old_profile_cannot_reuse(self):
        self.manifest["tasks"][0]["role"] = "development_gate"
        self.manifest_path.write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError): self.merge()
        self.manifest["profile"] = {"observer": "ta-probe-v1"}
        self.manifest_path.write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError): self.merge()


if __name__ == "__main__": unittest.main()
