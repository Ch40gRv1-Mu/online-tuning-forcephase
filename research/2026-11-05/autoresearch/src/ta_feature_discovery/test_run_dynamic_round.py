"""Synthetic properties of frozen R04 scheduling and fold-local fallback."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import learning
import run_dynamic_round as runner
from test_learning import row
import test_learning as fixtures


class DynamicRoundProperties(unittest.TestCase):
    def snapshot(self):
        rows = [row(i, role=learning.FIT_ROLE if i < 180 else learning.FEEDBACK_ROLE) for i in range(240)]
        for i, r in enumerate(rows):
            r["dynamic_status"] = "COMPLETE" if i < 192 else "NOT_SCHEDULED"
            if i < 192:
                r["features"].update(dict.fromkeys(learning.DYNAMIC_FEATURES, float(i)))
        return {"rows": rows, "static_complete": True, "dynamic_complete": True,
                "dynamic_summary": {"scheduled": 192, "complete_vectors": 192},
                "dynamic_bindings": {"receipts": {str(i): "f" * 64 for i in range(192)},
                                     **dict.fromkeys(("static_dataset_sha256", "manifest_sha256", "receipt_index_sha256"), "a" * 64)}}

    def test_requires_full192_stage_and_complete_population(self):
        data = self.snapshot()
        fit, feedback = runner.validate_snapshot(data)
        self.assertEqual((len(fit), len(feedback)), (180, 60))
        for change in ({"dynamic_complete": False}, {"dynamic_summary": {"scheduled": 40, "complete_vectors": 40}}):
            with self.assertRaises(ValueError):
                runner.validate_snapshot(data | change)
        for status in ("PENDING", "RUNNING"):
            changed = copy.deepcopy(data)
            changed["rows"][0]["dynamic_status"] = status
            with self.assertRaises(ValueError):
                runner.validate_snapshot(changed)
        changed = copy.deepcopy(data)
        changed["rows"][-1]["role"] = "development_gate"
        with self.assertRaises(ValueError):
            runner.validate_snapshot(changed)

    def test_fold_fallback_is_refitted_and_all_comparisons_keep_feedback(self):
        fit = fixtures.DynamicFallbackProperties().dataset()
        feedback = [copy.deepcopy(r) for r in fit[:24]]
        for i, r in enumerate(feedback):
            r.update(id="feedback" + str(i), group="feedback" + str(i), role=learning.FEEDBACK_ROLE)
        reference = learning.fit_policy(fit, learning.PRIMARY_FEATURES, max_depth=2)
        report = runner.candidate_job((fit, feedback, runner.PROPOSALS[0], reference, True))
        self.assertEqual(len(report["fit_group_cv"]), 5)
        self.assertEqual(set(report["comparisons"]), {"fit_best_constant", "frozen_static_fallback", "strongest_static_reference"})
        self.assertTrue(all(e["metrics"]["parents"] == 24 for e in report["comparisons"].values()))
        full_sha = report["fallback_policy"]["training"]["ids_sha256"]
        held_ids = []
        for fold in report["fit_group_cv"]:
            held = {r["id"] for r in fold["evaluation"]["per_row"]}
            held_ids.extend(held)
            expected = hashlib.sha256("\n".join(sorted(r["id"] for r in fit if r["id"] not in held)).encode()).hexdigest()
            self.assertEqual(fold["fallback_policy"]["training"]["ids_sha256"], expected)
            self.assertNotEqual(expected, full_sha)
            union = learning._used_features(fold["policy"]["tree"]) | learning._used_features(fold["fallback_policy"]["tree"])
            self.assertLessEqual(len(union), 2)
        self.assertEqual(set(held_ids), {r["id"] for r in fit})
        self.assertEqual(len(held_ids), len(fit))

    def test_only_two_predeclared_fields_and_static_reference_only(self):
        self.assertEqual({p["dynamic_field"] for p in runner.PROPOSALS}, {"c_glue_mean", "x_level_avg"})
        fit = fixtures.DynamicFallbackProperties().dataset()
        with self.assertRaises(ValueError):
            runner.fit_candidate(fit, "c_glue_low_frac")
        policy, fallback = runner.fit_candidate(fit, "c_glue_mean")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "reference.json"
            path.write_text(json.dumps({"policy": fallback}))
            self.assertEqual(runner.load_static_reference(path), fallback)
            path.write_text(json.dumps({"policy": policy}))
            with self.assertRaises(ValueError):
                runner.load_static_reference(path)
            path.write_text("{}")
            with self.assertRaises(FileExistsError):
                runner.save_new(path, {"new": True})


if __name__ == "__main__":
    unittest.main()
