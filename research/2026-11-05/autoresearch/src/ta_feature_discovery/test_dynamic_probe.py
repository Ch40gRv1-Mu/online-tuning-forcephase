"""Observer/dispatch properties with source and synthetic logs, never SAT runs."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import dynamic_probe as p
import node_worker as common


class ProbeProperties(unittest.TestCase):
    def header(self):
        return {"type": "header", "schema": 2, "controller": "v2", "observer": p.OBSERVER_VERSION,
                "mode": 3, "track": "C", "a0": "NATIVE", "a1": "NATIVE", "init": 0,
                "at": 1000, "period": 0, "maxsw": 1, "rlim": 0,
                "opt_phase": 1, "opt_forcephase": 0, "opt_seed": 0}

    def checkpoint(self):
        return {"type": "checkpoint", "crossed": [1000, 1000], "conflicts": 1100,
                "action": "NATIVE", "learned": 1050, "process_cpu_s": 1.25,
                "f": {"r_switches": 0, **dict.fromkeys(p.FEATURE_MAP.values(), 1.5)}}

    def parse(self, rows, tail=b""):
        with tempfile.TemporaryDirectory() as root:
            log = Path(root) / "telemetry.jsonl"
            log.write_bytes(b"".join(common.canonical(r) + b"\n" for r in rows) + tail)
            return p.parse_telemetry(log)

    def task(self):
        return {"instance_id": "instance1", "input_sha256": "b" * 64,
                "role": "development_fit", "public_url": "https://benchmark-database.de/file/x"}

    def identity(self):
        return dict(zip(p.IDENTITY_FIELDS, ("c" * 64, "d" * 64, "e" * 64)))

    def test_complete_checkpoint_and_partial_terminal_tail(self):
        result = self.parse([self.header(), self.checkpoint()], b'{"type":"final"')
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(set(result["features"]), set(p.FEATURE_MAP))

    def test_old_observer_cannot_silently_reuse_missing_event_identity(self):
        header = self.header()
        header.pop("observer")
        with self.assertRaises(ValueError):
            self.parse([header, self.checkpoint()])

    def test_minimum_learning_and_cpu_limit_are_not_inferred_from_conflicts(self):
        for change, reason in (({"learned": 19}, "fewer_than_20_learned_events"),
                               ({"process_cpu_s": 2.000001}, "checkpoint_after_cpu_limit")):
            record = self.checkpoint() | change
            self.assertEqual(self.parse([self.header(), record])["missing_reason"], reason)
        for key in ("learned", "process_cpu_s"):
            record = self.checkpoint()
            record.pop(key)
            with self.assertRaises(ValueError):
                self.parse([self.header(), record])

    def test_undefined_dynamic_vector_retains_missing_status(self):
        record = self.checkpoint()
        record["f"]["x_glue_ratio"] = None
        result = self.parse([self.header(), record])
        self.assertEqual(result["status"], "MISSING")
        self.assertNotIn("features", result)

    def test_actions_before_checkpoint_and_wrong_crossing_rejected(self):
        with self.assertRaises(ValueError):
            self.parse([self.header(), {"type": "switch", "reason": "schedule"}, self.checkpoint()])
        record = self.checkpoint() | {"crossed": [2000, 5000]}
        with self.assertRaises(ValueError):
            self.parse([self.header(), record])

    def test_terminal_answer_is_never_used_as_a_feature_or_checkpoint(self):
        result = self.parse([self.header(), {"type": "final", "result": 10, "learned": 1000}])
        self.assertIsNone(result)
        self.assertFalse(p.PROFILE["early_answers_adopted"])

    def test_patch_adds_only_three_logging_fields_to_exact_qualified_source(self):
        source = Path(__file__).resolve().parents[2] / "work/phase_prediction_20261104/project/solver/fpcontrol.cpp"
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "fpcontrol.cpp"
            identity = p.patch_observer(source, target)
            self.assertEqual(identity["base_observer_source_sha256"], p.BASE_OBSERVER_SHA)
            self.assertEqual(identity["observer_source_sha256"], p.OBSERVER_SOURCE_SHA)
            text, before = target.read_text(), source.read_text()
            self.assertIn('\\"observer\\":\\"ta-probe-v1\\"', text)
            self.assertIn('now.learned, absolute_process_time ()', text)
            self.assertEqual(text.count("void Controller::at_restart"), before.count("void Controller::at_restart"))
            with self.assertRaises(ValueError):
                p.patch_observer(target, Path(root) / "second.cpp")
            with self.assertRaises(FileExistsError):
                p.patch_observer(source, target)

    def test_task_identity_includes_both_binaries_observer_and_profile(self):
        task = p.normalize_task(self.task(), self.identity())
        changed = self.identity() | {"solver_binary_sha256": "f" * 64}
        self.assertNotEqual(task["task_key"], p.normalize_task(self.task(), changed)["task_key"])
        with self.assertRaises(ValueError):
            p.normalize_task(task, changed)
        for change in ({"role": "development_gate"}, {"winner": "true"}):
            with self.assertRaises(ValueError):
                p.normalize_task(self.task() | change, self.identity())

    def test_receipt_reuse_is_strict_and_inflight_does_not_requeue(self):
        task, identity = p.normalize_task(self.task(), self.identity()), self.identity()
        record = {**identity, "task_key": task["task_key"], "input_sha256": task["input_sha256"],
                  "profile": p.PROFILE, "status": "MISSING", "total_accounted_cpu_s": 2.05}
        record["receipt_content_sha256"] = hashlib.sha256(common.canonical(record)).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            result = root / "results" / (task["task_key"] + ".json")
            common.atomic_json(result, record)
            with mock.patch.object(common, "prepare_input", side_effect=AssertionError("no rerun")):
                got, reused = p.process_task(task, Path("unused"), Path("unused"), identity, root, "node1", None)
            self.assertTrue(reused)
            self.assertEqual(got, record)
            result.unlink()
            common.atomic_json(root / "inflight" / (task["task_key"] + ".json"), {"pid": 99999})
            with self.assertRaises(RuntimeError):
                p.process_task(task, Path("unused"), Path("unused"), identity, root, "node1", None)

    def test_resource_caps_share_finite_memory_and_cpu_allocation(self):
        g = 1024**3
        self.assertEqual(p.worker_capacity(".", 8, memory=16*g, disk=30*g, cpus=2), 2)
        self.assertEqual(p.worker_capacity(".", 30, memory=100*g, disk=100*g, cpus=30), 8)
        self.assertEqual(p.worker_capacity(".", 8, memory=16*g, disk=12*g, cpus=8), 0)
        self.assertEqual(p.parse_cpu_set("1,4-6"), {1, 4, 5, 6})
        for value in ("-1", "3-1", ""):
            with self.assertRaises(ValueError):
                p.parse_cpu_set(value)


if __name__ == "__main__":
    unittest.main()
