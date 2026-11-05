"""Synthetic exact-population receipt merge; no TA labels or research CNFs."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import merge_static as m
import static_worker as w


class MergeProperties(unittest.TestCase):
    def fixture(self,root):
        manifest={"profile":w.PROFILE,"method":{"group":"core10","extractor_source_sha256":"a"*64,
            "parser_source_sha256":"b"*64,"binary_sha256":"c"*64,"cpu_helper_sha256":"d"*64,
            "worker_source_sha256":"e"*64,"base_worker_source_sha256":"f"*64,"dependency_sha256":{}},
            "feature_keys":["f_test"],"public_manifest_sha256":"0"*64,"tasks":[]}
        for i,role in enumerate(("development_fit","development_feedback")):
            task={"instance_id":"synthetic"+str(i),"role":role,"input_sha256":str(i+1)*64,
                "public_url":"https://benchmark-database.de/file/x","metadata":{"variables":2,"clauses":1,"bytes":18}}
            manifest["tasks"].append(w.normalize_task(task,manifest))
        path=root/"manifest.json";path.write_text(json.dumps(manifest));results=root/"results";results.mkdir()
        for i,task in enumerate(manifest["tasks"]):
            record={"task_key":task["task_key"],"id":task["instance_id"],"instance_id":task["instance_id"],
                "role":task["role"],"input_sha256":task["input_sha256"],"profile":w.PROFILE,
                "method":manifest["method"],"feature_keys":manifest["feature_keys"],"status":"COMPLETE" if not i else "RESOURCE_LIMIT",
                "features":{"f_test":.5 if not i else None},"blocks":{"f_test":{"status":"COMPLETE" if not i else "RESOURCE_LIMIT"}},
                "extractor_metadata":{"header_variables":2,"header_clauses":1,"raw_clauses":1,"input_bytes":18},
                "source_check":"input_sha256_match","feature_cpu_s":.15,"feature_wall_s":2.,
                "preparation_cpu_s":.2,"preparation_wall_s":1.,"controller_cpu_s":.05,"total_accounted_cpu_s":.4}
            record["receipt_content_sha256"]=hashlib.sha256(w.base.canonical(record)).hexdigest()
            w.base.atomic_json(results/(task["task_key"]+".json"),record)
        return path,results,manifest

    def test_cpp_source_binding_full_population_null_fallback_and_costs(self):
        with tempfile.TemporaryDirectory() as root:
            path,results,manifest=self.fixture(Path(root))
            table,index=m.merge(path,[results],expected_count=2)
            self.assertEqual(table["bindings"]["source_sha256"],"a"*64)
            self.assertNotEqual(table["bindings"]["source_sha256"],table["bindings"]["table_builder_sha256"])
            self.assertEqual(len(table["features"]),2)
            self.assertIsNone(table["features"]["synthetic1"]["f_test"])
            self.assertEqual(table["physical_costs"]["total_accounted_cpu_s"],.8)
            self.assertEqual(table["coverage"],{"f_test":1})
            self.assertEqual(len(index["records"]),2)

    def test_partial_population_fails_before_any_table(self):
        with tempfile.TemporaryDirectory() as root:
            path,results,manifest=self.fixture(Path(root))
            next(results.glob('*.json')).unlink()
            with self.assertRaises(ValueError):m.merge(path,[results],expected_count=2)

    def test_corrupt_or_nonidentical_duplicate_cannot_replace_existing_measurement(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);path,results,manifest=self.fixture(root)
            other=root/"other";other.mkdir()
            p=next(results.glob('*.json'));(other/p.name).write_bytes(p.read_bytes())
            table,index=m.merge(path,[results,other],expected_count=2)
            self.assertEqual(table["physical_costs"]["total_accounted_cpu_s"],.8)
            record=json.loads(p.read_text());record["controller_cpu_s"]+=.1;record["total_accounted_cpu_s"]+=.1
            record.pop("receipt_content_sha256")
            record["receipt_content_sha256"]=hashlib.sha256(w.base.canonical(record)).hexdigest()
            w.base.atomic_json(other/p.name,record)
            with self.assertRaises(ValueError):m.merge(path,[results,other],expected_count=2)

    def test_protected_role_and_input_identity_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path,results,manifest=self.fixture(Path(root))
            manifest["tasks"][0]["role"]="development_gate";path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):m.merge(path,[results],expected_count=2)


if __name__=="__main__":unittest.main()
