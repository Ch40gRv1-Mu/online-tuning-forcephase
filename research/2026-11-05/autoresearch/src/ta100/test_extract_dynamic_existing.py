"""Synthetic properties only: no real labels, benchmark trace or solver."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_dynamic_existing as extractor


def checkpoint():
    fields = {"c_chrono_frac": .25, "c_reuse_frac": .75, "c_target_src_frac": 1/3,
              "c_saved_src_frac": 1/3, "x_target_set_frac": .5, "x_best_frac": .8,
              "x_target_frac": .4, "x_trail_ratio": 1.2, "x_red_per_irr": 2,
              "x_target_neg_frac": .6, "x_saved_neg_frac": .2, "x_size_avg": 10,
              "c_size_mean": 20, "x_level_avg": 4, "x_jump_avg": 2,
              "c_glue_mean": 2, "c_glue_low_frac": .5, "x_glue_ratio": .9,
              "c_minsize_mean": 4, "c_backjump_mean": 2, "r_switches": 0}
    return {"f": fields, "action": "NATIVE", "crossed": [1000, 1000],
            "conflicts": 1000, "learned": 50, "process_cpu_s": 1.0}


class ArithmeticProperties(unittest.TestCase):
    def test_formulas_use_distinct_state_mechanisms(self):
        values = extractor.checkpoint_features(checkpoint())
        expected = [.25, .75, 1, .5, 1/3, .2, 2, .4, math.log(.5), 1/3]
        self.assertEqual(set(values), set(extractor.COLUMNS))
        for name, value in zip(extractor.COLUMNS, expected):
            self.assertAlmostEqual(values[name], value)

    def test_zero_denominators_bad_domains_and_missing_are_null(self):
        cp = checkpoint()
        cp["f"].update(x_best_frac=0, x_target_frac=0, c_target_src_frac=.8, c_saved_src_frac=.8,
                         c_size_mean=0, x_level_avg=0, x_jump_avg=0, c_chrono_frac=float("nan"))
        values = extractor.checkpoint_features(cp)
        for index in (0, 2, 4, 8, 9):
            self.assertIsNone(values[extractor.COLUMNS[index]])
        self.assertTrue(all(v is None for v in extractor.checkpoint_features({}).values()))

    def test_no_rescue_of_missing_and_no_postcheckpoint_values(self):
        record = {"status": "MISSING", "checkpoint": checkpoint(), "final": {"secret_answer": 10}}
        self.assertTrue(all(v is None for v in extractor.features_for_receipt(record).values()))
        record.update(status="EARLY_SOLVED_UNVERIFIED")
        self.assertTrue(all(v is None for v in extractor.features_for_receipt(record).values()))


class IdentityTableProperties(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.receipts = self.root / "results"
        self.receipts.mkdir()
        self.manifest_path = self.root / "manifest.json"
        self.index_path = self.root / "index.json"
        identity = {"observer_source_sha256": extractor.probe.OBSERVER_SOURCE_SHA,
                    "solver_binary_sha256": "a" * 64, "cpu_helper_sha256": "b" * 64}
        self.manifest = {**identity, "profile": extractor.probe.PROFILE, "node_id": "synthetic", "tasks": []}
        index = {}
        for i in range(192):
            raw = {"instance_id": "p" + str(i), "role": "development_fit" if i < 144 else "development_feedback",
                   "input_sha256": "c" * 64, "public_url": "https://benchmark-database.de/file/p" + str(i)}
            task = extractor.probe.normalize_task(raw, self.manifest)
            self.manifest["tasks"].append(task)
            cp = checkpoint()
            record = {**identity, "profile": extractor.probe.PROFILE, "task_key": task["task_key"],
                      "instance_id": task["instance_id"], "id": task["instance_id"], "role": task["role"],
                      "input_sha256": task["input_sha256"], "node_id": "synthetic", "status": "COMPLETE" if i else "MISSING",
                      "answer_adopted": False, "source_check": "input_sha256_match", "checkpoint": cp,
                      "features": {out: cp["f"][raw] for out, raw in extractor.probe.FEATURE_MAP.items()},
                      "total_accounted_cpu_s": 1.2}
            if not i:
                record["features"] = None
            record["receipt_content_sha256"] = extractor.merger.canonical_sha(record)
            path = self.receipts / (task["task_key"] + ".json")
            path.write_text(json.dumps(record, sort_keys=True))
            index[task["task_key"]] = extractor.merger.sha(path)
        self.manifest_path.write_text(json.dumps(self.manifest, sort_keys=True))
        self.index_path.write_text(json.dumps({"manifest_sha256": extractor.merger.sha(self.manifest_path), "receipts": index}))

    def extract(self, output=None):
        return extractor.extract_features(self.manifest_path, self.receipts, self.index_path, output,
            expected_manifest_sha256=extractor.merger.sha(self.manifest_path),
            expected_receipt_index_sha256=extractor.merger.sha(self.index_path))

    def test_complete192_contract_retains_missing_and_model_metadata_separate(self):
        result = self.extract()
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["expected_instance_ids"]), 192)
        self.assertEqual(len(result["features"]), 192)
        self.assertEqual(result["columns"], list(extractor.COLUMNS))
        self.assertTrue(all(v is None for v in result["features"]["p0"].values()))
        self.assertEqual(set(result["features"]["p1"]), set(extractor.COLUMNS))
        self.assertEqual(result["cost_summary"]["new_solver_cpu_s"], 0)
        self.assertEqual(result["metadata_not_model_input"]["fixed_population"], 240)

    def test_missing_receipt_or_wrong_raw_sha_cannot_publish_partial_table(self):
        path = next(self.receipts.iterdir())
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        out = self.root / "output.json"
        with self.assertRaises(ValueError):
            self.extract(out)
        self.assertFalse(out.exists())
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.extract(out)
        self.assertFalse(out.exists())

    def test_gate_task_rejected_before_receipts_and_output_is_immutable(self):
        self.manifest["tasks"][0]["role"] = "development_gate"
        self.manifest_path.write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError):
            self.extract()
        self.manifest["tasks"][0]["role"] = "development_fit"
        self.manifest_path.write_text(json.dumps(self.manifest, sort_keys=True))
        out = self.root / "output.json"
        self.extract(out)
        with self.assertRaises(FileExistsError):
            self.extract(out)


if __name__ == "__main__":
    unittest.main()
