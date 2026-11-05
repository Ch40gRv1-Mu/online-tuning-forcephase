"""Synthetic bounded-block properties; no benchmark features or scores."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_block as runner


def row(i, role, x=0.0, costs=(2.0, 1.0)):
    return {"id": "p" + str(i), "group": "g" + str(i), "role": role,
            "eligible": i < 192, "feature_status": "AVAILABLE" if i < 192 else "EXCLUDED",
            "features": dict.fromkeys(runner.BASE10, x), "costs": dict(zip(runner.learning.ACTIONS, costs)),
            "statuses": dict.fromkeys(runner.learning.ACTIONS, "SAT"),
            "wall_times": dict(zip(runner.learning.ACTIONS, costs)), "feature_cpu_s": None}


def constant_policy(rows, action="true"):
    return {"schema": "ta_cost_tree_v1", "baseline_action": "true", "tree": {"action": action},
            "training": {"ids_sha256": runner._ids_sha(rows)}}


class BlockProperties(unittest.TestCase):
    def test_collection_identity_distinguishes_population_from_method(self):
        block = {"collection_manifest_sha256": "collection"}
        runner.validate_collection_binding(block, {"bindings": {
            "base_manifest_sha256": "population", "collection_manifest_sha256": "collection"}})
        runner.validate_collection_binding(block, {"bindings": {"base_manifest_sha256": "collection"}})
        with self.assertRaises(ValueError):
            runner.validate_collection_binding(block, {"bindings": {
                "base_manifest_sha256": "collection", "collection_manifest_sha256": "wrong_method"}})

    def fixture(self):
        rows = [row(i, runner.learning.FIT_ROLE if i < 180 else runner.learning.FEEDBACK_ROLE) for i in range(240)]
        table = {"complete": True, "expected_instance_ids": [r["id"] for r in rows if r["eligible"]],
                 "columns": ["new_state"], "features": {r["id"]: {"new_state": 0.0} for r in rows if r["eligible"]},
                 "bindings": {"base_manifest_sha256": "a" * 64, "source_sha256": "b" * 64}}
        return {"static_complete": True, "rows": rows}, table

    def test_full240_retained_and_all192_input_identity_barriers(self):
        data, table = self.fixture()
        fit, feedback = runner.validate_and_merge(data, table)
        self.assertEqual((len(fit), len(feedback)), (180, 60))
        self.assertIsNone(feedback[-1]["features"]["new_state"])
        self.assertNotIn("new_state", data["rows"][0]["features"])
        for mutation in ("partial", "extra_id", "nan", "gate", "metadata"):
            bad_data, bad_table = copy.deepcopy(data), copy.deepcopy(table)
            if mutation == "partial": bad_table["complete"] = False
            if mutation == "extra_id": bad_table["features"]["alien"] = {"new_state": 1}
            if mutation == "nan": bad_table["features"]["p0"]["new_state"] = float("nan")
            if mutation == "gate": bad_data["rows"][-1]["role"] = "development_gate"
            if mutation == "metadata": bad_table["features"]["p0"]["answer"] = 10
            with self.assertRaises(ValueError, msg=mutation):
                runner.validate_and_merge(bad_data, bad_table)

    def test_registry_binds10_distinct_mechanisms_and_safe_columns(self):
        entries = [{"id": "TD" + str(i), "novelty_mechanism_key": "mechanism" + str(i), "columns": ["new_" + str(i)]} for i in range(10)]
        block = {"rounds": [{"id": "I" + str(i), "registry_id": e["id"],
                              "mechanism_key": e["novelty_mechanism_key"], "columns": e["columns"]} for i, e in enumerate(entries)]}
        rounds, columns = runner.validate_block(block, {"candidates": entries})
        self.assertEqual((len(rounds), len(columns)), (10, 10))
        for change in ("duplicate", "unsafe", "unregistered"):
            bad = copy.deepcopy(block)
            if change == "duplicate": bad["rounds"][1]["mechanism_key"] = bad["rounds"][0]["mechanism_key"]
            if change == "unsafe": bad["rounds"][0]["columns"] = ["__class__"]
            if change == "unregistered": bad["rounds"][0]["columns"] = ["unknown"]
            with self.assertRaises(ValueError):
                runner.validate_block(bad, {"candidates": entries})

    def test_cached_comparator_matches_existing_policy_evaluator(self):
        rows = [row(i, runner.learning.FEEDBACK_ROLE, i % 2,
                    costs=(1, 10) if i % 2 == 0 else (20, 2)) for i in range(30)]
        candidate = constant_policy(rows)
        baseline = {"schema": "ta_cost_tree_v1", "baseline_action": "true", "tree": {
            "feature": "s_mean_length", "threshold": .5, "left": {"action": "false"}, "right": {"action": "true"}}}
        selected = runner.learning.evaluate_policy(candidate, rows, bootstrap_samples=0)
        cache = dict(zip([r["id"] for r in rows], runner.learning.predict_policy(baseline, rows)))
        actual = runner.compare_cached(selected, rows, cache, samples=20)
        expected = runner.learning.evaluate_policy(candidate, rows, baseline_policy=baseline, bootstrap_samples=20)
        for key in ("relative_improvement", "total_delta_s", "baseline_total_cost_s", "baseline_solved", "switches",
                    "clear_switches", "gross_gain_s", "gross_loss_s", "max_regression_s", "bootstrap"):
            self.assertEqual(actual["metrics"][key], expected["metrics"][key], key)
        self.assertEqual(actual["per_row"], expected["per_row"])

    def test_candidate_fits_only_six_times_and_reuses_five_baseline_caches(self):
        data, table = self.fixture()
        fit, feedback = runner.validate_and_merge(data, table)
        full_policy = constant_policy(fit)
        reference = {"policy": full_policy, "evaluation": runner.learning.evaluate_policy(full_policy, feedback, bootstrap_samples=0), "fit_group_cv": []}
        folds = runner.fold_map(fit)
        for i in range(5):
            train = [r for r in fit if folds[r["group"]] != i]
            held = [dict(r, role=runner.learning.FEEDBACK_ROLE) for r in fit if folds[r["group"]] == i]
            policy = constant_policy(train)
            reference["fit_group_cv"].append({"fold": i, "policy": policy,
                "evaluation": runner.learning.evaluate_policy(policy, held, bootstrap_samples=0)})
        full, cached = runner.validate_baseline(reference, fit, feedback)
        proposal = {"id": "synthetic", "mechanism_key": "synthetic_state", "columns": ["new_state"]}
        original_allowed = runner.learning.ALLOWED_FEATURES
        self.addCleanup(setattr, runner.learning, "ALLOWED_FEATURES", original_allowed)
        with mock.patch.object(runner.learning, "fit_policy", wraps=runner.learning.fit_policy) as fitted:
            result = runner.candidate_job((fit, feedback, proposal, ["new_state"], full, cached))
        self.assertEqual(result["status"], "COMPLETE", result.get("error"))
        self.assertEqual(fitted.call_count, 6)
        self.assertEqual(result["evaluation"]["metrics"]["parents"], 60)
        self.assertEqual(len(result["fit_group_cv"]), 5)
        self.assertEqual(result["used_new_columns"], [])
        self.assertEqual(result["vs_static_control"]["metrics"]["relative_improvement"], 0)
        self.assertTrue(any(d["kind"] == "observed_constant" for d in result["numeric_diagnostics_fit_only"]))


if __name__ == "__main__":
    unittest.main()
