import gzip
import hashlib
import lzma
import tempfile
import unittest
from pathlib import Path
from .common import check_model, parse_stats, validate_spec, write
from .export_results import export
from .stage_inputs import stage
from .filter_manifest import exclude, score_status


class ScientificContracts(unittest.TestCase):
    def test_external_filter_preserves_missing_coverage_and_any_solve(self):
        self.assertTrue(exclude([False,False,False]))
        self.assertFalse(exclude([False,None,False]))
        self.assertFalse(exclude([False,True,False]))
        self.assertFalse(exclude([False,False]))

    def test_official_scores_use_penalty_not_nominal_cutoff(self):
        self.assertFalse(score_status(["10000","10000"],5000))
        self.assertTrue(score_status(["2000","1004.301"],1000))
        self.assertIsNone(score_status(["10000","missing"],5000))
        self.assertIsNone(score_status(["nan"],5000))

    def test_missing_statistics_are_not_zero(self):
        self.assertIsNone(parse_stats("s UNKNOWN\n")["conflicts"])
        self.assertEqual(parse_stats("c conflicts: 0 0 per second\n")["conflicts"], 0)
        self.assertEqual(parse_stats("c conflicts: 3\nc conflicts: 9\n")["conflicts"], 9)

    def test_draft_cannot_launch(self):
        with self.assertRaisesRegex(ValueError, "only frozen"):
            validate_spec({"status": "DRAFT_NOT_LAUNCHABLE"}, "/not/a/manifest")

    def test_model_is_checked_against_cnf_not_status(self):
        with tempfile.TemporaryDirectory() as d:
            cnf, log = Path(d)/"x.cnf", Path(d)/"x.log"
            cnf.write_text("p cnf 1 1\n1 0\n")
            log.write_text("s SATISFIABLE\nv -1 0\n")
            self.assertFalse(check_model(cnf, log))
            log.write_text("s SATISFIABLE\nv 1 0\n")
            self.assertTrue(check_model(cnf, log))
            cnf.write_text("p cnf 1 2\n1 0\n0\n")
            self.assertFalse(check_model(cnf, log))

    def test_compression_and_cache_identity(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); data=b"c input fixture\np cnf 1 1\n1 0\n"
            for name, content in [("plain",data),("gzip",gzip.compress(data)),("xz",lzma.compress(data))]:
                source=base/(name+".data");source.write_bytes(content)
                row={"instance_key":name,"url":source.as_uri(),"expected_sha256_cnf":hashlib.sha256(data).hexdigest()}
                out=base/(name+"_root");out.mkdir()
                r=stage(row,out,{"disk_reserve_bytes":1024,"download_wall_s":5})
                self.assertEqual(Path(r["path"]).read_bytes(),data)
                self.assertEqual(stage(row,out,{"disk_reserve_bytes":1024})["input_sha256"],r["input_sha256"])
                Path(r["path"]).write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError,"cached input changed"):
                    stage(row,out,{"disk_reserve_bytes":1024})

    def test_wrong_public_sha_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"source.cnf";source.write_text("p cnf 1 1\n1 0\n")
            out=Path(d)/"out";out.mkdir()
            with self.assertRaisesRegex(ValueError,"SHA mismatch"):
                stage({"instance_key":"bad","url":source.as_uri(),"expected_sha256_cnf":"0"*64},out,{"disk_reserve_bytes":1024})
            self.assertFalse((out/"input_receipts/bad.json").exists())

    def test_partial_export_cannot_claim_complete(self):
        with tempfile.TemporaryDirectory() as d:
            write(Path(d)/"progress.json",{"status":"PARTIAL"})
            with self.assertRaisesRegex(ValueError,"incomplete or invalid"):
                export(d,Path(d)/"result.tar.gz",True)


if __name__=="__main__":unittest.main()
