"""Synthetic properties for the bounded learner; no benchmark data is loaded."""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cluster
import learning


def row(i, x=0.0, y=0.0, costs=(1.0, 10.0), role="development_fit", group=None):
    features = {name: float(x) for name in learning.PRIMARY_FEATURES}
    features["s_mean_length"] = float(x)
    features["s_positive_fraction"] = float(y)
    return {
        "id": str(i), "group": str(i) if group is None else group,
        "role": role, "eligible": True, "feature_status": "AVAILABLE",
        "features": features, "costs": dict(zip(learning.ACTIONS, costs)),
        "statuses": {a: "SAT" for a in learning.ACTIONS},
        "wall_times": dict(zip(learning.ACTIONS, costs)), "feature_cpu_s": 0.5,
    }


class LearningProperties(unittest.TestCase):
    def test_role_barriers_reject_gate_and_feedback_training(self):
        for role in ("development_gate", "final_test", "development_feedback"):
            with self.assertRaises(ValueError):
                learning.fit_policy([row(1, role=role)])
        model = learning.fit_policy([row(i) for i in range(24)])
        with self.assertRaises(ValueError):
            learning.evaluate_policy(model, [row(99, role="development_gate")])

    def test_pending_blocks_feature_learning_but_not_label_screen(self):
        rows = [row(i) for i in range(24)]
        rows[0]["feature_status"] = "PENDING"
        self.assertEqual(learning.baseline_and_oracle(rows)["parents"], 24)
        with self.assertRaises(ValueError):
            learning.fit_policy(rows)
        with self.assertRaises(ValueError):
            cluster.fit_clusters(rows)
        payload = {"static_complete": False, "rows": rows}
        self.assertEqual(len(learning.validate_development_payload(payload, require_static=False)), 24)
        with self.assertRaises(ValueError):
            learning.validate_development_payload(payload)

    def test_global_depth_two_search_finds_neutral_root_interaction(self):
        rows = []
        for x in (0, 1):
            for y in (0, 1):
                for _ in range(12):
                    rows.append(row(len(rows), x, y, (1.0, 50.0) if x == y else (50.0, 1.0)))
        stump = learning.fit_policy(rows, ("s_mean_length", "s_positive_fraction"), max_depth=1)
        tree = learning.fit_policy(rows, ("s_mean_length", "s_positive_fraction"), max_depth=2)
        self.assertEqual(stump["training"]["policy_total_cost_s"], stump["training"]["baseline_total_cost_s"])
        self.assertEqual(tree["training"]["policy_total_cost_s"], 48.0)
        self.assertEqual(len(learning._used_features(tree["tree"])), 2)
        actual = sum(r["costs"][a] for r, a in zip(rows, learning.predict_policy(tree, rows)))
        self.assertEqual(actual, tree["training"]["policy_total_cost_s"])

    def test_missing_and_ineligible_fall_back_and_keep_cost_denominator(self):
        rows = [row(i, 0, costs=(1.0, 100.0)) for i in range(12)]
        rows += [row(i + 12, 1, costs=(100.0, 1.0)) for i in range(12)]
        policy = learning.fit_policy(rows, ("s_mean_length",))
        cases = [row(100, 1, costs=(100.0, 1.0), role="development_feedback"),
                 row(101, 1, costs=(100.0, 1.0), role="development_feedback"),
                 row(102, 1, costs=(100.0, 1.0), role="development_feedback")]
        cases[1]["features"]["s_mean_length"] = None
        cases[1]["feature_status"] = "UNAVAILABLE"
        cases[2]["eligible"] = False
        cases[2]["feature_status"] = "EXCLUDED"
        evaluated = learning.evaluate_policy(policy, cases, bootstrap_samples=50)
        self.assertEqual([r["action"] for r in evaluated["per_row"]], ["true", "false", "false"])
        self.assertEqual(evaluated["metrics"]["parents"], 3)
        self.assertEqual(evaluated["metrics"]["policy_total_cost_s"], 201.0)

    def test_min_leaf_and_fit_quantile_boundaries(self):
        rows = [row(i, i, costs=(1.0, 100.0) if i < 35 else (1000.0, 1.0)) for i in range(40)]
        policy = learning.fit_policy(rows, ("s_mean_length",), min_leaf=12)
        def walk(node, subset):
            if "action" in node:
                self.assertGreaterEqual(len(subset), 12)
                return
            quantiles = set(float(x) for x in __import__("numpy").quantile(list(range(40)), learning.QUANTILES))
            self.assertIn(node["threshold"], quantiles)
            walk(node["left"], [r for r in subset if r["features"][node["feature"]] <= node["threshold"]])
            walk(node["right"], [r for r in subset if r["features"][node["feature"]] > node["threshold"]])
        walk(policy["tree"], rows)

    def test_cost_objective_beats_accuracy_and_cpu_is_not_added(self):
        rows = [row(i, costs=(1.0, 2.0)) for i in range(23)]
        rows += [row(23, costs=(10000.0, 1.0))]
        policy = learning.fit_policy(rows, [])
        self.assertEqual(policy["baseline_action"], "true")
        feedback = [copy.deepcopy(r) for r in rows]
        for r in feedback:
            r["role"] = "development_feedback"
            r["feature_cpu_s"] = 1e9
        result = learning.evaluate_policy(policy, feedback, bootstrap_samples=40)
        self.assertEqual(result["metrics"]["policy_total_cost_s"], 47.0)
        self.assertTrue(result["metrics"]["feature_cpu_not_added_to_TA_wall"])
        self.assertEqual(result["metrics"]["observed_feature_cpu_s"], 24e9)

    def test_timeout_is_unknown_and_status_not_cost_defines_solved(self):
        a = row(1, costs=(10000.0, 10000.0), role="development_feedback")
        a["statuses"] = dict.fromkeys(learning.ACTIONS, "TIMEOUT")
        a["wall_times"] = dict.fromkeys(learning.ACTIONS, 5000.5)
        self.assertIsNone(learning.clear_action(a))
        b = row(2, costs=(10000.0, 10000.0), role="development_feedback")
        # Retain an odd late source success: it is not inferred to be TIMEOUT.
        policy = learning.fit_policy([row(i) for i in range(24)], [])
        result = learning.evaluate_policy(policy, [a, b], bootstrap_samples=30)
        self.assertEqual(result["metrics"]["solved"], 1)
        self.assertEqual(result["metrics"]["clear_parents"], 0)
        self.assertEqual(result["metrics"]["late_source_success_parents"], 1)

    def test_single_timeout_uses_conservative_cutoff_bound(self):
        a = row(1, costs=(4999.9, 10000.0))
        a["statuses"]["true"] = "TIMEOUT"
        a["wall_times"]["true"] = 5001.0
        self.assertIsNone(learning.clear_action(a))
        a["costs"]["false"] = a["wall_times"]["false"] = 20.0
        self.assertEqual(learning.clear_action(a), "false")

    def test_group_bootstrap_does_not_count_equivalent_rows_as_independent(self):
        policy = learning.fit_policy([row(i) for i in range(24)], [])
        rows = [row(i + 100, costs=(1.0, 100.0), role="development_feedback", group="one-group") for i in range(4)]
        result = learning.evaluate_policy(policy, rows, bootstrap_samples=100)
        boot = result["metrics"]["bootstrap"]
        self.assertEqual(boot["groups"], 1)
        self.assertEqual(boot["cost_ratio_95"], [1.0, 1.0])
        json.dumps(result, allow_nan=False)

    def test_forbidden_features_and_three_feature_policy_are_rejected(self):
        with self.assertRaises(ValueError):
            learning.fit_policy([row(i) for i in range(24)], ["family"])
        model = learning.fit_policy([row(i) for i in range(24)], [])
        model["tree"] = {"feature": "family", "threshold": 1.0,
                         "left": {"action": "false"}, "right": {"action": "true"}}
        with self.assertRaises(ValueError):
            learning.predict_policy(model, [row(100)])


class ClusterProperties(unittest.TestCase):
    def make_fit(self):
        return [row(i, 1.0 if i < 20 else 10.0, costs=(1.0, 4.0) if i < 20 else (4.0, 1.0)) for i in range(40)]

    def test_centers_do_not_use_outcome_labels(self):
        fit = self.make_fit()
        one = cluster.fit_clusters(fit, 2)
        flipped = copy.deepcopy(fit)
        for r in flipped:
            r["costs"] = {a: r["costs"][b] for a, b in zip(learning.ACTIONS, reversed(learning.ACTIONS))}
            r["wall_times"] = dict(r["costs"])
        two = cluster.fit_clusters(flipped, 2)
        self.assertEqual(one["centers"], two["centers"])
        self.assertEqual(one["median"], two["median"])
        self.assertEqual(len(one["initializations"]), 10)

    def test_feedback_assignment_never_refits_and_missing_is_unassigned(self):
        model = cluster.fit_clusters(self.make_fit(), 2)
        before = json.dumps(model, sort_keys=True)
        feedback = [row(90, 100000.0, role="development_feedback"), row(91, 2, role="development_feedback")]
        feedback[1]["features"]["s_mean_length"] = None
        labels = cluster.assign_clusters(model, feedback)
        self.assertIsNotNone(labels[0]); self.assertIsNone(labels[1])
        self.assertEqual(json.dumps(model, sort_keys=True), before)
        with self.assertRaises(ValueError):
            cluster.fit_clusters(feedback)
        with self.assertRaises(ValueError):
            cluster.assign_clusters(model, [row(99, role="development_gate")])

    def test_profiles_are_fit_only_and_degenerate_centers_are_honest(self):
        fit = [row(i) for i in range(30)]
        model = cluster.fit_clusters(fit, 3)
        self.assertEqual(model["effective_clusters"], 1)
        profiles = cluster.cluster_profiles(model, fit)
        self.assertEqual(sum(p["parents"] for p in profiles["profiles"]), 30)
        self.assertEqual(sum(p["parents"] == 0 for p in profiles["profiles"]), 2)
        with self.assertRaises(ValueError):
            cluster.cluster_profiles(model, [row(100, role="development_feedback")])
        json.dumps(profiles, allow_nan=False)


class DynamicFallbackProperties(unittest.TestCase):
    def dataset(self):
        rows = []
        for x in (0, 1):
            for dynamic in (0, 1):
                for _ in range(12):
                    r = row(len(rows), x, costs=(1.0, 100.0) if x == dynamic else (100.0, 1.0))
                    r["dynamic_status"] = "COMPLETE"
                    r["features"]["c_glue_mean"] = dynamic
                    rows.append(r)
        # Unavailable high-cost rows must be predicted by a varying static
        # fallback; dropping them or using a constant changes the objective.
        for x in (0, 1):
            for _ in range(24):
                r = row(len(rows), x, costs=(1.0, 300.0) if x == 0 else (300.0, 1.0))
                r["dynamic_status"] = "MISSING"
                rows.append(r)
        return rows

    def test_dynamic_missing_uses_frozen_static_and_full_population_cost(self):
        rows = self.dataset()
        fallback = learning.fit_policy(rows, ("s_mean_length",), max_depth=1)
        frozen = json.dumps(fallback, sort_keys=True)
        policy = learning.fit_policy(rows, ("s_mean_length", "c_glue_mean"), fallback_policy=fallback)
        predictions = learning.predict_policy(policy, rows)
        fallback_actions = learning.predict_policy(fallback, rows)
        self.assertEqual(predictions[48:], fallback_actions[48:])
        self.assertEqual(predictions[48:72], ["false"] * 24)
        self.assertEqual(predictions[72:], ["true"] * 24)
        self.assertEqual(policy["training"]["policy_total_cost_s"], 96.0)
        self.assertEqual(sum(r["costs"][a] for r, a in zip(rows, predictions)), 96.0)
        self.assertEqual(json.dumps(fallback, sort_keys=True), frozen)
        feedback = [copy.deepcopy(r) for r in rows]
        for r in feedback:
            r["role"] = learning.FEEDBACK_ROLE
        scored = learning.evaluate_policy(policy, feedback, baseline_policy=fallback, bootstrap_samples=20)
        self.assertEqual(scored["metrics"]["parents"], 96)
        self.assertEqual(scored["metrics"]["baseline_total_cost_s"], sum(r["costs"][a] for r, a in zip(rows, fallback_actions)))
        self.assertEqual(scored["metrics"]["switches"], 24)

    def test_all_missing_dynamic_exactly_reproduces_static(self):
        rows = self.dataset()
        fallback = learning.fit_policy(rows, ("s_mean_length",), max_depth=1)
        for r in rows:
            r["dynamic_status"] = "MISSING"
            r["features"].pop("c_glue_mean", None)
        policy = learning.fit_policy(rows, ("s_mean_length", "c_glue_mean"), fallback_policy=fallback)
        self.assertEqual(learning.predict_policy(policy, rows), learning.predict_policy(fallback, rows))
        self.assertEqual(policy["training"]["policy_total_cost_s"], policy["training"]["baseline_total_cost_s"])

    def test_union_capacity_and_one_dynamic_field_are_enforced(self):
        rows = self.dataset()
        fallback = learning.fit_policy(rows, ("s_mean_length",), max_depth=1)
        for names in (("s_positive_fraction", "c_glue_mean"),
                      ("c_glue_mean", "c_glue_low_frac"), ("s_mean_length",)):
            with self.assertRaises(ValueError):
                learning.fit_policy(rows, names, fallback_policy=fallback)
        policy = learning.fit_policy(rows, ("s_mean_length", "c_glue_mean"), fallback_policy=fallback)
        policy["required_dynamic_features"] = ["c_glue_mean", "c_glue_low_frac"]
        with self.assertRaises(ValueError):
            learning.validate_policy(policy)

    def test_pending_dynamic_stage_cannot_be_scored_as_static_fallback(self):
        rows = self.dataset()
        fallback = learning.fit_policy(rows, ("s_mean_length",), max_depth=1)
        policy = learning.fit_policy(rows, ("s_mean_length", "c_glue_mean"), fallback_policy=fallback)
        rows[0]["dynamic_status"] = "PENDING"
        with self.assertRaises(ValueError):
            learning.predict_policy(policy, rows)
        with self.assertRaises(ValueError):
            learning.validate_development_payload({"static_complete": True, "dynamic_complete": False, "rows": rows})


if __name__ == "__main__":
    unittest.main()
