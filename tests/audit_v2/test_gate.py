#!/usr/bin/env python3
"""Regression tests for the audit v2 data gate (docs/CORRECTION_PROTOCOL.md §4).

  python3 tests/audit_v2/test_gate.py          (stdlib unittest; the end-to-end
                                                 case needs the analysis venv)

Each case builds hand-made run summaries and telemetry files that represent a
scientifically meaningful situation and checks the category, and that every
data error blocks the formal analysis (gate.enforce raises, the strict builder
exits non-zero).
"""

import csv
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "audit_v2"))
import gate  # noqa: E402

HDR = {"type": "header", "schema": 1, "track": "C", "mode": 3}


def cp(lo, hi, conflicts, digest):
    return {"type": "checkpoint", "crossed": [lo, hi], "conflicts": conflicts, "time": 1.0, "digest": digest,
            "f": {"x": 1}}


def sw(conflicts, action="NEGATIVE", reason="schedule"):
    return {"type": "switch", "reason": reason, "action": action, "conflicts": conflicts}


def fin(switches):
    return {"type": "final", "switches": switches}


def write(dirpath, name, recs, truncate=False):
    path = os.path.join(dirpath, name + ".jsonl.gz")
    text = "".join(json.dumps(r) + "\n" for r in recs)
    if truncate:
        text = text[:-15]
    with gzip.open(path, "wt") as f:
        f.write(text)
    return path


class Gate(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def tel(self, name, recs, **kw):
        return gate.load_telemetry(write(self.d, name, recs, **kw))

    def base(self, status="timeout"):
        return {"status": status, "terminated_by": "cpu" if status == "timeout" else None,
                "exit_code": -15 if status == "timeout" else 10, "cpu": 300.1 if status == "timeout" else 5.0}

    def classify(self, b_recs, a_recs, b_status="timeout", a_status="timeout", K=1000, action="NEGATIVE",
                 a_run=None):
        bt = self.tel("b", b_recs)
        at = None if a_recs is None else self.tel("a", a_recs)
        a = None if a_recs is None else (a_run or self.base(a_status))
        return gate.classify_pair(self.base(b_status), bt, a, at, K, action, "C")[0]

    def test_valid_pair(self):
        b = [HDR, cp(1000, 1000, 1200, "aa"), fin(0)]
        a = [HDR, cp(1000, 1000, 1200, "aa"), sw(1200), fin(1)]
        self.assertEqual(self.classify(b, a), "valid_pair")

    def test_missing_file_is_error(self):
        t = gate.load_telemetry(os.path.join(self.d, "nope.jsonl.gz"))
        self.assertEqual(t[1], "telemetry_missing")
        c = gate.classify_pair(self.base(), t, None, None, 1000, "NEGATIVE", "C")[0]
        self.assertEqual(c, "telemetry_missing")
        with self.assertRaises(gate.GateError):
            gate.enforce([c])

    def test_truncated_jsonl_is_corrupt(self):
        t = self.tel("t", [HDR, cp(1000, 1000, 1200, "aa"), fin(0)], truncate=True)
        self.assertEqual(t[1], "telemetry_corrupt")

    def test_missing_final_is_incomplete_unless_killed_after_cutoff(self):
        recs = [HDR, cp(1000, 1000, 1200, "aa"), sw(1200)]
        t = self.tel("a", recs)
        self.assertEqual(t[1], "telemetry_incomplete")
        b = [HDR, cp(1000, 1000, 1200, "aa"), fin(0)]
        # SIGTERM-terminated run without final -> error
        self.assertEqual(self.classify(b, recs), "telemetry_incomplete")
        # SIGKILL after the CPU cutoff (appendix A) -> pair checks still apply and pass
        killed = {"status": "timeout", "terminated_by": "cpu", "exit_code": -9, "cpu": 310.2}
        self.assertEqual(self.classify(b, recs, a_run=killed), "valid_pair")
        # but a killed run that is not a timeout at the cutoff is not covered
        early = dict(killed, cpu=120.0)
        self.assertEqual(self.classify(b, recs, a_run=early), "telemetry_incomplete")

    def test_missing_alt_is_error_not_backfilled(self):
        b = [HDR, cp(1000, 1000, 1200, "aa"), fin(0)]
        self.assertEqual(self.classify(b, None), "alt_missing")

    def test_missing_base(self):
        c = gate.classify_pair(None, ([], "telemetry_missing"), None, None, 1000, "NEGATIVE", "C")[0]
        self.assertEqual(c, "base_missing")

    def test_digest_mismatch(self):
        b = [HDR, cp(1000, 1000, 1200, "aa"), fin(0)]
        a = [HDR, cp(1000, 1000, 1200, "bb"), sw(1200), fin(1)]
        self.assertEqual(self.classify(b, a), "digest_mismatch")

    def test_wrong_direction(self):
        b = [HDR, cp(1000, 1000, 1200, "aa"), fin(0)]
        a = [HDR, cp(1000, 1000, 1200, "aa"), sw(1200, action="NATIVE"), fin(1)]
        self.assertEqual(self.classify(b, a), "direction_error")

    def test_should_switch_but_did_not(self):
        b = [HDR, cp(1000, 1000, 1200, "aa"), fin(0)]
        a = [HDR, cp(1000, 1000, 1200, "aa"), fin(0)]
        self.assertEqual(self.classify(b, a), "switch_error")

    def test_switch_not_at_checkpoint(self):
        b = [HDR, cp(1000, 1000, 1200, "aa"), fin(0)]
        a = [HDR, cp(1000, 1000, 1200, "aa"), sw(1500), fin(1)]
        self.assertEqual(self.classify(b, a), "switch_error")

    def test_legal_preprocessing_solve(self):
        b = [HDR, fin(0)]  # solved during preprocessing: no checkpoint at all
        self.assertEqual(self.classify(b, None, b_status="solved"), "solved_before_K")

    def test_legal_solve_before_threshold(self):
        b = [HDR, cp(1000, 1000, 1100, "aa"), cp(2000, 5000, 6000, "cc"), fin(0)]
        self.assertEqual(self.classify(b, None, b_status="solved", K=10000), "solved_before_K")
        self.assertEqual(self.classify(b, None, b_status="timeout", K=10000), "budget_before_K")

    def test_unexpected_alt_when_no_decision_point(self):
        b = [HDR, fin(0)]
        a = [HDR, fin(0)]
        self.assertEqual(self.classify(b, a, b_status="solved"), "unexpected_alt")

    def test_budget_boundary_double_timeout_only(self):
        b = [HDR, cp(100000, 100000, 100001, "aa"), fin(0)]
        a = [HDR, cp(50000, 50000, 50001, "zz"), fin(0)]
        self.assertEqual(self.classify(b, a, K=100000), "censored_unmatched")
        gate.enforce(["censored_unmatched", "valid_pair"])  # allowed exception
        # not generalised: alt solved before reaching the checkpoint -> error
        self.assertEqual(self.classify(b, a, a_status="solved", K=100000), "switch_error")
        # not generalised: base solved -> error
        self.assertEqual(self.classify(b, a, b_status="solved", K=100000), "switch_error")

    def test_enforce_blocks_every_error(self):
        for e in gate.ERRORS:
            with self.assertRaises(gate.GateError):
                gate.enforce(["valid_pair", e])


class StrictBuilderEndToEnd(unittest.TestCase):
    """Strict builder must exit non-zero on duplicate keys / missing replays."""

    PY = os.environ.get("FP_PY", "/mnt/data/zhaofeng/venvs/online-tuning-forcephase/bin/python")

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.data = os.path.join(self.d, "data")

    def tearDown(self):
        shutil.rmtree(self.d)

    def run_builder(self, rows):
        fields = ["run_id", "config", "instance", "family", "family_group", "split", "gbd_result", "seed",
                  "variant", "repeat", "status", "result", "par2", "cpu", "exit_code", "terminated_by"]
        p = os.path.join(self.d, "runs.csv")
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in fields})
        st = os.path.join(self.d, "static.csv")
        with open(st, "w") as f:
            f.write("instance,cpu_time\ninst1,0.1\n")
        env = dict(os.environ, FP_DATA=self.data)
        return subprocess.run([self.PY, os.path.join(ROOT, "scripts", "audit_v2", "m3_build_strict.py"),
                               "--runs", p, "--static", st, "--out", os.path.join(self.d, "out.csv")],
                              capture_output=True, text=True, env=env)

    def raw(self, run_id, recs):
        d = os.path.join(self.data, "runs", "raw", run_id[:2], run_id)
        os.makedirs(d, exist_ok=True)
        write(d, "telemetry", recs)

    def row(self, run_id, config, status="timeout"):
        return {"run_id": run_id, "config": config, "instance": "inst1", "family": "f", "family_group": "g",
                "split": "train", "gbd_result": "sat", "seed": 0, "variant": "orig", "repeat": 0,
                "status": status, "result": "", "par2": 600 if status == "timeout" else 5.0,
                "cpu": 300.1, "exit_code": -15, "terminated_by": "cpu"}

    def base_rows(self):
        recs = [HDR, cp(1000, 100000, 120000, "aa"), fin(0)]
        rows = []
        for i, c in enumerate(["D", "Fminus", "Iminus"]):
            rid = f"b{i}" + "0" * 38
            self.raw(rid, recs)
            rows.append(self.row(rid, c))
        return rows

    def test_missing_replays_block(self):
        r = self.run_builder(self.base_rows())  # base reached K but no replay exists
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("alt_missing", r.stdout + r.stderr)

    def test_duplicate_key_blocks(self):
        rows = self.base_rows()
        rows.append(dict(rows[0], run_id="c" * 40))
        self.raw("c" * 40, [HDR, fin(0)])
        r = self.run_builder(rows)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("duplicate_key", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
