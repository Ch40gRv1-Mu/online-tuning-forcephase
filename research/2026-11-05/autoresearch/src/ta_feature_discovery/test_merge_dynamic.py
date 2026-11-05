"""Synthetic immutable dynamic merge properties; no benchmark data or solver."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic_probe as probe
import learning
import merge_dynamic as merger
from test_learning import row


class MergeProperties(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.static = self.root / "static.json"
        self.manifest = self.root / "manifest.json"
        self.index = self.root / "receipts.json"
        self.receipts = self.root / "results"
        self.receipts.mkdir()
        self.payload = {"static_complete": True, "feature_names": list(learning.PRIMARY_FEATURES),
                        "rows": [row(i, i % 2, role=learning.FIT_ROLE if i < 180 else learning.FEEDBACK_ROLE)
                                 for i in range(240)]}
        identity = {"observer_source_sha256": probe.OBSERVER_SOURCE_SHA,
                    "solver_binary_sha256": "d" * 64, "cpu_helper_sha256": "e" * 64}
        self.m = {**identity, "profile": probe.PROFILE, "node_id": "node1", "allocated_cpu_s": 3600,
                  "experiment_id": "synth", "shard_id": "shard1", "tasks": []}
        for i in range(40):
            task = probe.normalize_task({"instance_id": str(i), "input_sha256": "b" * 64,
                "role": learning.FIT_ROLE, "public_url": "https://benchmark-database.de/file/" + str(i)}, identity)
            self.m["tasks"].append(task)
            self.payload["rows"][i]["feature_source"] = {"input_sha256": "b" * 64}
            values = {key: float(i + 1) for key in probe.FEATURE_MAP}
            checkpoint = {"action": "NATIVE", "crossed": [1000, 1000], "conflicts": 1100,
                          "learned": 1000, "process_cpu_s": 1.5,
                          "f": {"r_switches": 0, **{raw: values[key] for key, raw in probe.FEATURE_MAP.items()}}}
            record = {**identity, "profile": probe.PROFILE, "task_key": task["task_key"],
                      "id": str(i), "instance_id": str(i), "input_sha256": "b" * 64,
                      "role": learning.FIT_ROLE, "node_id": "node1", "status": "COMPLETE" if i < 20 else "MISSING",
                      "source_check": "input_sha256_match", "features": values if i < 20 else None,
                      "checkpoint": checkpoint, "answer_adopted": False,
                      "preparation_cpu_s": 0.1, "feature_cpu_s": 1.6, "controller_cpu_s": 0.1,
                      "total_accounted_cpu_s": 1.8, "feature_wall_s": 2.0}
            self.write_receipt(record)
        self.save_json(self.static, self.payload)
        self.save_json(self.manifest, self.m)
        self.refresh_index()

    def save_json(self, path, value):
        path.write_text(json.dumps(value, sort_keys=True) + "\n")

    def write_receipt(self, record):
        record.pop("receipt_content_sha256", None)
        record["receipt_content_sha256"] = merger.canonical_sha(record)
        self.save_json(self.receipts / (record["task_key"] + ".json"), record)

    def refresh_index(self):
        self.save_json(self.index, {"manifest_sha256": merger.sha(self.manifest),
            "receipts": {t["task_key"]: merger.sha(self.receipts / (t["task_key"] + ".json")) for t in self.m["tasks"]}})

    def merge(self, output=None):
        return merger.merge_dynamic(self.static, self.manifest, self.receipts, self.index, output,
                                    expected_static_sha256=merger.sha(self.static),
                                    expected_manifest_sha256=merger.sha(self.manifest),
                                    expected_receipt_index_sha256=merger.sha(self.index))

    def mutate_record(self, i, **change):
        key = self.m["tasks"][i]["task_key"]
        record = json.loads((self.receipts / (key + ".json")).read_text())
        record.update(change)
        self.write_receipt(record)
        self.refresh_index()

    def test_preserves_population_static_fields_labels_and_missing_fees(self):
        result = self.merge()
        self.assertTrue(result["dynamic_complete"])
        self.assertEqual(result["dynamic_summary"]["complete_vectors"], 20)
        self.assertAlmostEqual(result["dynamic_summary"]["total_accounted_cpu_s"], 72)
        self.assertEqual(result["dynamic_summary"]["coverage_scheduled"], .5)
        for before, after in zip(self.payload["rows"], result["rows"]):
            for key in ("costs", "statuses", "wall_times", "feature_cpu_s", "group", "role", "eligible"):
                self.assertEqual(before[key], after[key])
            for key, value in before["features"].items():
                self.assertEqual(value, after["features"][key])
        self.assertEqual(set(result["rows"][0]["features"]) - set(self.payload["rows"][0]["features"]), learning.DYNAMIC_FEATURES)
        self.assertEqual(result["rows"][20]["features"], self.payload["rows"][20]["features"])
        self.assertEqual(result["rows"][-1]["dynamic_status"], "NOT_SCHEDULED")

    def test_partial_manifest_or_missing_file_cannot_publish_feedback(self):
        index = json.loads(self.index.read_text())
        index["receipts"].pop(next(iter(index["receipts"])))
        self.save_json(self.index, index)
        with self.assertRaises(ValueError):
            self.merge()
        self.refresh_index()
        next(self.receipts.iterdir()).unlink()
        with self.assertRaises(FileNotFoundError):
            self.merge()

    def test_raw_receipt_hash_and_self_digest_both_required(self):
        key = self.m["tasks"][0]["task_key"]
        path = self.receipts / (key + ".json")
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaises(ValueError):
            self.merge()
        path.write_bytes(original)
        record = json.loads(original)
        record["feature_wall_s"] = 3.0
        self.save_json(path, record)
        self.refresh_index()
        with self.assertRaises(ValueError):
            self.merge()

    def test_wrong_method_input_role_or_unqualified_checkpoint_rejected(self):
        cases = [{"solver_binary_sha256": "a" * 64}, {"input_sha256": "a" * 64},
                 {"role": "development_gate"}, {"status": "RUNNING"}, {"answer_adopted": True},
                 {"checkpoint": {"action": "FALSE"}}]
        key = self.m["tasks"][0]["task_key"]
        original = json.loads((self.receipts / (key + ".json")).read_text())
        for change in cases:
            self.write_receipt(original | change)
            self.refresh_index()
            with self.assertRaises(ValueError, msg=str(change)):
                self.merge()
        self.write_receipt(original)

    def test_noncomplete_partial_vector_and_bad_costs_rejected(self):
        self.mutate_record(20, features={"d_glue_mean": 1.0})
        with self.assertRaises(ValueError):
            self.merge()
        self.mutate_record(20, features=None, total_accounted_cpu_s=0.1)
        with self.assertRaises(ValueError):
            self.merge()

    def test_failed_and_early_answers_retained_without_features(self):
        self.mutate_record(20, status="FAILED")
        self.mutate_record(21, status="EARLY_SOLVED_UNVERIFIED")
        result = self.merge()
        self.assertEqual(len(result["rows"]), 240)
        self.assertEqual(result["dynamic_summary"]["statuses"]["FAILED"], 1)
        self.assertEqual(result["rows"][21]["costs"], self.payload["rows"][21]["costs"])

    def test_static_barrier_and_protected_parent_rejected(self):
        self.payload["static_complete"] = False
        self.save_json(self.static, self.payload)
        with self.assertRaises(ValueError):
            self.merge()
        self.payload["static_complete"] = True
        self.payload["rows"][-1]["role"] = "development_gate"
        self.save_json(self.static, self.payload)
        with self.assertRaises(ValueError):
            self.merge()

    def test_output_is_immutable_and_idempotent(self):
        output = self.root / "merged.json"
        self.merge(output)
        self.merge(output)
        output.write_text("{}")
        with self.assertRaises(FileExistsError):
            self.merge(output)


if __name__ == "__main__":
    unittest.main()
