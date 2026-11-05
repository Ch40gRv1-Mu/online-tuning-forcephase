"""Semantic tests for graph statistics, polarity and held-out feedback guards."""

import itertools
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import policy
import run_pilot


class StructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temp.name)/"cnf_structure"
        source = Path(__file__).with_name("cnf_structure.cpp")
        subprocess.run(["g++", "-O2", "-std=c++17", str(source), "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def features(self, clauses, declared=20):
        p = Path(self.temp.name)/"sample.cnf"
        p.write_text(f"c semantic test\np cnf {declared} {len(clauses)}\n" +
                     "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        return json.loads(subprocess.check_output([str(self.binary),str(p)],text=True))

    def test_tree_and_cycle_have_correct_incidence_cycle_rank(self):
        tree=self.features([[1,2],[2,3]])
        cycle=self.features([[1,2],[2,3],[3,1]])
        self.assertEqual(tree["g_cycle_excess"],0)
        self.assertEqual(cycle["g_cycle_excess"],1)
        self.assertAlmostEqual(tree["g_leaf_variable_fraction"],2/3)
        self.assertEqual(tree["s_variables"],3)

    def test_disconnected_and_empty_clauses_are_counted(self):
        f=self.features([[1,2],[3],[]])
        self.assertEqual(f["g_components"],3)
        self.assertEqual(f["g_cycle_excess"],0)
        self.assertAlmostEqual(f["g_largest_component_fraction"],2/3)

    def test_gate_motif_and_graph_ignore_global_sign_names(self):
        clauses=[[1,-2,-3],[-1,2],[-1,3]]
        a=self.features(clauses)
        b=self.features([[-x for x in c] for c in clauses])
        self.assertGreater(a["g_gate_motif_fraction"],0)
        self.assertEqual(a["g_gate_motif_fraction"],b["g_gate_motif_fraction"])
        for k in a:
            if k.startswith("g_"):
                self.assertEqual(a[k],b[k])
        self.assertAlmostEqual(a["s_positive_fraction"]+b["s_positive_fraction"],1)

    def test_duplicate_literals_do_not_create_extra_incidence_edges(self):
        f=self.features([[1,1,2],[2,3]])
        self.assertEqual(f["g_cycle_excess"],0)
        self.assertEqual(f["s_max_length"],3)


class PolicyTests(unittest.TestCase):
    def test_model_verifier_rejects_contradictory_assignments(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'model.cnf';path.write_text('p cnf 2 1\n1 2 0\n')
            self.assertTrue(run_pilot.check_model(path,'v 1 -2 0\n',2))
            self.assertFalse(run_pilot.check_model(path,'v -1 1 -2 0\n',2))

    def rule(self):
        return {"feature":"s_binary_fraction","threshold":0.5,"missing":"left",
                "left":{"action":"D"},"right":{"action":"Fplus"}}

    def test_only_numeric_whitelisted_features_can_select_actions(self):
        rule=self.rule()
        self.assertEqual(policy.decide(rule,{"s_binary_fraction":0.75}),"Fplus")
        self.assertEqual(policy.decide(rule,{}),"D")
        for name in ["family","filename","hash","known_sat","result","conflicts_final"]:
            bad={**rule,"feature":name}
            with self.assertRaises(ValueError):policy.validate(bad)

    def test_nonfinite_or_coded_feature_values_are_rejected(self):
        for v in ["circuit",float("nan"),float("inf"),True]:
            with self.assertRaises(ValueError):policy.decide(self.rule(),{"s_binary_fraction":v})

    def test_test_and_gate_feedback_cannot_enter_context(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"memory.jsonl"
            for role in ["test","protected_candidate","development_gate","exposed_diagnostic"]:
                with self.assertRaises(ValueError):
                    policy.append_episode(path,{"split_role":role,"policy":{"action":"D"},"reward":0.0})
            self.assertFalse(path.exists())
            policy.append_episode(path,{"split_role":"development_feedback","policy":{"action":"D"},"reward":0.0})
            self.assertEqual(len(path.read_text().splitlines()),1)


if __name__=="__main__":unittest.main()
