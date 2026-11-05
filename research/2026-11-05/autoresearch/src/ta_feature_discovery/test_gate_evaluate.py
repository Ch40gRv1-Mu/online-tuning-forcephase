"""Synthetic one-time gate properties; no real gate rows, labels or CNFs."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import gate_evaluate as g
import node_worker as w


class GateProperties(unittest.TestCase):
    def policy(self):
        return {"schema": "ta_cost_tree_v1", "baseline_action": "false", "tree": {
            "feature": "s_mean_length", "threshold": 2., "left": {"action": "true"}, "right": {"action": "false"}}}

    def task(self):
        return {"instance_id": "a"*32, "role": g.GATE, "input_sha256": "b"*64,
                "public_url": "https://benchmark-database.de/file/x"}

    def test_gate_worker_requires_candidate_hash_and_exclusively_true_gate_roles(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source, candidate, path = root/"extractor.cpp", root/"candidate.json", root/"manifest.json"
            source.write_text("// synthetic extractor, never compiled\n")
            candidate.write_text(json.dumps(self.policy()))
            manifest = {"experiment_id": "gate1", "shard_id": "gate", "extractor_source_sha256": w.sha(source),
                        "profile": w.PROFILE, "gate_candidate_sha256": w.sha(candidate), "tasks": [self.task()]}
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): w.load_manifest(path, source)
            self.assertEqual(w.load_manifest(path, source, candidate)["tasks"][0]["role"], g.GATE)
            self.assertEqual(w.load_manifest(path, source, gate_candidate_sha256=w.sha(candidate))["tasks"][0]["role"], g.GATE)
            for digest in ("f"*64, "f"*32, "", "F"*64):
                with self.assertRaises(ValueError): w.load_manifest(path, source, gate_candidate_sha256=digest)
            with self.assertRaises(ValueError): w.load_manifest(path, source, candidate, w.sha(candidate))
            candidate.write_text(candidate.read_text()+"\n")
            with self.assertRaises(ValueError): w.load_manifest(path, source, candidate)
            manifest["gate_candidate_sha256"] = w.sha(candidate)
            manifest["tasks"][0]["role"] = "development_fit"
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): w.load_manifest(path, source, candidate)

    def test_default_worker_role_barrier_unchanged(self):
        with self.assertRaises(ValueError): w.normalize_task(self.task(), "c"*64)
        task = w.normalize_task(self.task(), "c"*64, allowed_roles={g.GATE})
        self.assertEqual(task["role"], g.GATE)

    def test_consumption_is_append_only_even_after_failure_or_candidate_change(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"gate-consumption.json"
            g.consume_once(path, {"candidate_sha256": "c"*64})
            original = path.read_bytes()
            for digest in ("c"*64, "d"*64):
                with self.assertRaises(FileExistsError):
                    g.consume_once(path, {"candidate_sha256": digest})
            self.assertEqual(path.read_bytes(), original)

    def test_candidate_guard_precedes_labels_and_gate_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            candidate = Path(root)/"candidate.json"
            candidate.write_text(json.dumps(self.policy()))
            with mock.patch.object(g, "load_gate_roles", side_effect=AssertionError("must not read roles")):
                class Args: pass
                args=Args(); args.candidate=candidate; args.expected_candidate_sha256="f"*64
                with self.assertRaises(ValueError): g.prepare_public(args)

    def test_all_sixty_gate_parents_retained_with_missing_and_resource_fallback(self):
        rows=[]
        for i in range(60):
            rows.append({"id": str(i), "group": str(i), "role": g.GATE, "eligible": i<51,
                "feature_status": "AVAILABLE" if i<50 else ("UNAVAILABLE" if i==50 else "EXCLUDED"),
                "features": {"s_mean_length": 1. if i<50 else None}, "feature_cpu_s": .1 if i<51 else None,
                "costs": {"false": 10., "true": 1.}, "statuses": {"false": "SAT", "true": "SAT"},
                "wall_times": {"false": 10., "true": 1.}})
        with mock.patch.object(g.learning, "fit_policy", side_effect=AssertionError("gate never fits")):
            result=g.evaluate_frozen(self.policy(), rows, bootstrap_samples=20)
        self.assertEqual(result["metrics"]["parents"],60)
        self.assertEqual(result["metrics"]["resource_eligible"],51)
        self.assertEqual(result["metrics"]["policy_total_cost_s"],150.)
        self.assertTrue(all(r["role"]==g.GATE for r in result["per_row"]))
        with self.assertRaises(ValueError): g.evaluate_frozen(self.policy(),rows[:-1])
        rows[0]["role"]="development_feedback"
        with self.assertRaises(ValueError): g.evaluate_frozen(self.policy(),rows)

    def test_pending_population_cannot_be_scored(self):
        row={"id":"a","role":g.GATE,"feature_status":"PENDING"}
        with self.assertRaises(ValueError): g.evaluate_frozen(self.policy(),[row],expected_n=1)


if __name__ == "__main__": unittest.main()
