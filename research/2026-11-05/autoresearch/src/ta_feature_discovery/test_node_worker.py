"""Implementation properties only: no benchmark download, extractor or SAT run."""
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

import make_node_bundle
import node_worker as w


class NodeContracts(unittest.TestCase):
    def task(self):
        return {"instance_id": "a" * 32, "role": "development_fit",
                "public_url": "https://benchmark-database.de/file/" + "a" * 32,
                "input_sha256": "b" * 64, "metadata": {"variables": 2, "clauses": 1, "bytes": 18}}

    def test_forbidden_labels_and_gate_are_rejected(self):
        for change in ({"wall_time_s": 5}, {"winner": "true"}, {"role": "development_gate"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                w.normalize_task({**self.task(), **change}, "c" * 64)

    def test_public_url_and_bound_input_are_required(self):
        for change in ({"public_url": "http://127.0.0.1/data"},
                       {"public_url": "https://secret@benchmark-database.de/file/x"},
                       {"input_sha256": None}, {"input_sha256": "b" * 32}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                w.normalize_task({**self.task(), **change}, "c" * 64)

    def test_alias_normalization_and_task_identity(self):
        original = w.normalize_task(self.task(), "c" * 64)
        alias = self.task()
        alias["source_sha256"] = alias.pop("input_sha256")
        self.assertEqual(original, w.normalize_task(alias, "c" * 64))
        self.assertNotEqual(original["task_key"], w.normalize_task(self.task(), "d" * 64)["task_key"])

    def test_resource_cap_is_shared_not_agent_count(self):
        g = 1024**3
        self.assertEqual(w.worker_capacity(".", 8, memory=16 * g, disk=30 * g, cpus=8), 4)
        self.assertEqual(w.worker_capacity(".", 1, memory=8 * g, disk=30 * g, cpus=8), 1)
        self.assertEqual(w.worker_capacity(".", 8, memory=16 * g, disk=12 * g, cpus=8), 0)
        self.assertEqual(w.worker_capacity(".", 8, memory=16 * g, disk=30 * g, cpus=0), 0)

    def test_owner_lock_and_manifest_binding(self):
        with tempfile.TemporaryDirectory() as root:
            identity = {"manifest_sha256": "a" * 64, "node_id": "node1"}
            with w.owner_lock(root, identity):
                with self.assertRaises(RuntimeError):
                    with w.owner_lock(root, identity):
                        pass
            with self.assertRaises(ValueError):
                with w.owner_lock(root, {**identity, "node_id": "node2"}):
                    pass

    def test_completed_receipt_reuses_without_preparation_or_extraction(self):
        task = w.normalize_task(self.task(), "c" * 64)
        record = {"task_key": task["task_key"], "input_sha256": task["input_sha256"],
                  "extractor_source_sha256": "c" * 64, "profile": w.PROFILE, "status": "COMPLETE",
                  "features": {"s_mean_length": 2}}
        record["receipt_content_sha256"] = hashlib.sha256(w.canonical(record)).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "results" / (task["task_key"] + ".json")
            w.atomic_json(target, record)
            with mock.patch.object(w, "prepare_input", side_effect=AssertionError("must not prepare")):
                actual, reused = w.process_task(task, Path("unused"), "c" * 64, root, "node1", None)
            self.assertTrue(reused)
            self.assertEqual(actual, record)
            changed = dict(record)
            changed["features"] = {"s_mean_length": 8}
            w.atomic_json(target, changed)
            with self.assertRaises(ValueError):
                w.reusable(target, task, "c" * 64)

    def test_inflight_is_not_automatically_requeued(self):
        task = w.normalize_task(self.task(), "c" * 64)
        with tempfile.TemporaryDirectory() as root:
            w.atomic_json(Path(root) / "inflight" / (task["task_key"] + ".json"), {"child_pid": 999})
            with self.assertRaises(RuntimeError):
                w.process_task(task, Path("unused"), "c" * 64, root, "node1", None)

    def test_shards_are_disjoint_and_cover_tasks(self):
        tasks = []
        for index in range(5):
            tasks.append({**self.task(), "instance_id": "instance" + str(index), "input_sha256": str(index) * 64})
        a = make_node_bundle.prepare_manifest({"ready_tasks": tasks}, "c" * 64, "experiment", "node-a", 0, 2)
        b = make_node_bundle.prepare_manifest({"ready_tasks": tasks}, "c" * 64, "experiment", "node-b", 1, 2)
        first = {t["task_key"] for t in a["tasks"]}
        second = {t["task_key"] for t in b["tasks"]}
        self.assertFalse(first & second)
        self.assertEqual(len(first | second), 5)

    def test_explicit_ready_tasks_never_falls_back_to_pending_tasks(self):
        manifest = make_node_bundle.prepare_manifest(
            {"ready_tasks": [], "tasks": [{"identity_status": "needs_public_identity"}]},
            "c" * 64, "experiment", "node-a", 0, 1)
        self.assertEqual(manifest["tasks"], [])

    def test_bundle_contains_only_selected_public_payload_and_source(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / "extractor.cpp"
            source.write_text("// inert source fixture, never compiled\n")
            tasks = root / "tasks.json"
            tasks.write_text(json.dumps({"tasks": [self.task()], "private_attachment": "MUST_NOT_COPY"}))
            target = root / "bundle.tar.gz"
            info = make_node_bundle.build_bundle(tasks, source, target, "experiment", "node-a", 0, 1)
            self.assertEqual(info["tasks"], 1)
            with tarfile.open(target, "r:gz") as archive:
                self.assertEqual(set(archive.getnames()), {"manifest.json", "cnf_structure.cpp", "node_worker.py", "run.sh", "README.md", "BUNDLE_MANIFEST.json"})
                for member in archive.getmembers():
                    self.assertNotIn(b"MUST_NOT_COPY", archive.extractfile(member).read())
            with self.assertRaises(FileExistsError):
                make_node_bundle.build_bundle(tasks, source, target, "experiment", "node-a", 0, 1)


if __name__ == "__main__":
    unittest.main()
