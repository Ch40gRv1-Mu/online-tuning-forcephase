"""Identity/schema/scheduling properties; no download, feature job or SAT run."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import static_worker as w


class WorkerProperties(unittest.TestCase):
    def manifest(self):
        return {"method": {"group":"core10","extractor_source_sha256":"a"*64,"parser_source_sha256":"b"*64,
            "binary_sha256":"c"*64,"cpu_helper_sha256":"d"*64,"worker_source_sha256":"e"*64,
            "base_worker_source_sha256":"f"*64,"dependency_sha256":{}}, "feature_keys":["f_test"],"profile":w.PROFILE}
    def task(self):
        return {"instance_id":"instance1","role":"development_fit","public_url":"https://benchmark-database.de/file/x",
                "input_sha256":"b"*64,"metadata":{"variables":2,"clauses":1,"bytes":18}}

    def test_gate_labels_and_phase_winners_rejected(self):
        for change in ({"role":"development_gate"},{"role":"final_test"},{"winner":"true"},{"wall_time_s":2.}):
            with self.assertRaises(ValueError):w.normalize_task(self.task()|change,self.manifest())

    def test_feature_names_allow_only_registered_safe_module_prefixes(self):
        for key in ("f_core_twins","graph_degree_arity_mi","algebra_horn_deficit"):
            self.assertTrue(w.FEATURE_NAME.fullmatch(key))
        for key in ("wall_time_s","family","graph_/path","algebra_x;rm","f_a b"):
            self.assertFalse(w.FEATURE_NAME.fullmatch(key))

    def test_task_key_binds_dependency_group_profile_and_feature_schema(self):
        m=self.manifest();task=w.normalize_task(self.task(),m)
        for change in ({"group":"graph10"},{"dependency_sha256":{"graph.hpp":"0"*64}}):
            changed=copy.deepcopy(m);changed["method"].update(change)
            self.assertNotEqual(task["task_key"],w.normalize_task(self.task(),changed)["task_key"])
            with self.assertRaises(ValueError):w.normalize_task(task,changed)

    def test_block_null_and_zero_are_distinct(self):
        m=self.manifest();task=self.task()
        output={"schema":"ta100.static.v1","group":"core10","features":{"f_test":None},
                "blocks":{"f_test":{"status":"CAPPED"}},"metadata":{"header_variables":2,"header_clauses":1,"raw_clauses":1,"input_bytes":18}}
        self.assertEqual(w.validate_output(output,m,task)["features"]["f_test"],None)
        output["features"]["f_test"]=0.
        with self.assertRaises(ValueError):w.validate_output(output,m,task)
        output["blocks"]["f_test"]["status"]="COMPLETE"
        self.assertEqual(w.validate_output(output,m,task)["features"]["f_test"],0.)
        output["features"]["f_test"]=float("nan")
        with self.assertRaises(ValueError):w.validate_output(output,m,task)

    def test_registry_and_header_source_identity_are_strict(self):
        m=self.manifest();task=self.task()
        output={"schema":"ta100.static.v1","group":"core10","features":{"f_test":1.},"blocks":{"f_test":{"status":"COMPLETE"}},
                "metadata":{"header_variables":2,"header_clauses":1,"raw_clauses":1,"input_bytes":18}}
        for mutate in (lambda x:x.update(group="wrong"),lambda x:x["features"].update(undeclared=2),
                       lambda x:x["metadata"].update(header_variables=3)):
            changed=copy.deepcopy(output);mutate(changed)
            with self.assertRaises(ValueError):w.validate_output(changed,m,task)

    def test_receipt_identity_corruption_and_inflight_are_not_requeued(self):
        m=self.manifest();task=w.normalize_task(self.task(),m)
        record={"task_key":task["task_key"],"input_sha256":task["input_sha256"],"method":m["method"],
                "profile":w.PROFILE,"feature_keys":m["feature_keys"],"role":task["role"],"status":"TIMEOUT"}
        record["receipt_content_sha256"]=hashlib.sha256(w.base.canonical(record)).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"receipt.json";w.base.atomic_json(path,record)
            self.assertEqual(w.reusable(path,task,m),record)
            changed=dict(record,status="COMPLETE");w.base.atomic_json(path,changed)
            with self.assertRaises(ValueError):w.reusable(path,task,m)
            class Args:pass
            args=Args();args.output_dir=Path(root)
            w.base.atomic_json(Path(root)/"inflight"/(task["task_key"]+".json"),{"owner_pid":111})
            with self.assertRaises(RuntimeError):w.process_task(args,m,task)

    def test_persistent_public_input_is_sha_bound_immutable_and_reserves_disk(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);cnf=root/"synthetic.cnf";cnf.write_text("p cnf0 0\n")
            digest=w.base.sha(cnf);cache=root/"cache"
            class Disk:free=30*1024**3
            with mock.patch.object(w.shutil,"disk_usage",return_value=Disk()):
                self.assertEqual(w.publish_verified_input(cnf,cache,digest),"PUBLISHED")
                self.assertEqual(w.publish_verified_input(cnf,cache,digest),"REUSED")
            (cache/(digest+".cnf")).write_text("corrupt")
            with self.assertRaises(ValueError):w.publish_verified_input(cnf,cache,digest)
            Disk.free=12*1024**3
            with mock.patch.object(w.shutil,"disk_usage",return_value=Disk()):
                self.assertEqual(w.publish_verified_input(cnf,root/"emptycache",digest),"SKIPPED_DISK_RESERVE")


if __name__=="__main__":unittest.main()
