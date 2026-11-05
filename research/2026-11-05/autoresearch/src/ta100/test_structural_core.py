"""Compile and test tiny synthetic CNFs only; never read research instances."""
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest


class CoreProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory()
        cls.binary=Path(cls.temporary.name)/"core"
        source=Path(__file__).with_name("structural_core.cpp")
        subprocess.run(["g++","-O2","-std=c++17",str(source),"-o",str(cls.binary)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def run_cnf(self,n,clauses,block=None):
        path=Path(self.temporary.name)/"synthetic.cnf"
        path.write_text("p cnf %d %d\n"%(n,len(clauses))+"".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        args=[str(self.binary)]
        if block:args += ["--block",block]
        result=subprocess.run(args+[str(path)],capture_output=True,text=True,check=True)
        return json.loads(result.stdout)

    def test_distinct_normalization_and_subsumption_mechanisms(self):
        result=self.run_cnf(4,[[1,1,2],[3,-3],[2,1],[1,2,4]])
        f=result["features"]
        self.assertAlmostEqual(f["f_core_literal_repetition"],.1)
        self.assertAlmostEqual(f["f_core_tautology"],.25)
        self.assertAlmostEqual(f["f_core_duplicate_clause"],1/3)
        self.assertEqual(f["f_core_subsumption"],1)
        self.assertIsNone(f["f_core_self_subsumption"])
        self.assertEqual(result["blocks"]["f_core_self_subsumption"]["status"],"UNDEFINED")

    def test_width4_strengthening_twins_and_growth(self):
        f=self.run_cnf(4,[[1,2,3,4],[-1,2,3,4]])["features"]
        self.assertEqual(f["f_core_self_subsumption"],1)
        self.assertEqual(f["f_core_variable_twins"],.75)
        self.assertEqual(f["f_core_resolution_fanout"],.125)
        self.assertEqual(f["f_core_resolvent_tautology"],0)
        self.assertEqual(f["f_core_blocked_polarity"],1)

    def test_resolution_nonpivot_complements(self):
        f=self.run_cnf(4,[[1,2,3,4],[-1,-2,3,4]])["features"]
        self.assertEqual(f["f_core_resolvent_tautology"],1)
        self.assertEqual(f["f_core_blocked_polarity"],.5)

    def test_no_unit_propagation_or_binary_parity_proxy_in_strengthening(self):
        result=self.run_cnf(3,[[1],[-1,2],[-2,3],[1,2,3],[-1,2,3]])
        self.assertIsNone(result["features"]["f_core_self_subsumption"])
        self.assertEqual(result["metadata"]["raw_clauses"],5)
        self.assertEqual(result["metadata"]["raw_literals"],11)

    def test_rename_and_clause_order_invariance(self):
        clauses=[[1,2,3,4],[-1,2,3,4],[1,-2],[-1,-2],[1,1,3],[1,-1]]
        base=self.run_cnf(4,clauses)["features"]
        perm={1:3,2:4,3:1,4:2}
        changed=[[perm[abs(l)]*(1 if l>0 else -1) for l in c] for c in reversed(clauses)]
        other=self.run_cnf(4,changed)["features"]
        self.assertEqual(base,other)

    def test_majority_flip_gain_matches_literal_evaluation_reference(self):
        rng=random.Random(12)
        for _ in range(8):
            clauses=[[v*(1 if rng.random()<.5 else -1) for v in rng.sample(range(1,6),rng.randint(1,4))] for _ in range(12)]
            p={v:sum(v in c for c in clauses) for v in range(1,6)}
            n={v:sum(-v in c for c in clauses) for v in range(1,6)}
            assignment={v:p[v]>n[v] for v in range(1,6)}
            unsat=lambda a:sum(not any(a[abs(l)]==(l>0) for l in c) for c in clauses)
            base=unsat(assignment);count=0
            for v in assignment:
                trial={**assignment,v:not assignment[v]}
                if base-unsat(trial)>0:count+=-1 if assignment[v] else 1
            active=sum(p[v]+n[v]>0 for v in assignment)
            actual=self.run_cnf(5,clauses,block="local_flip_gain")
            self.assertAlmostEqual(actual["features"]["f_core_majority_flip_gain"],count/active)

    def test_missing_is_null_not_invented_zero_and_module_selection(self):
        empty=self.run_cnf(0,[])
        self.assertTrue(all(value is None for value in empty["features"].values()))
        one=self.run_cnf(2,[[1,2]],block="variable_twins")
        self.assertEqual(one["features"],{"f_core_variable_twins":1})

    def test_header_and_input_limit_fail_without_numeric_vector(self):
        path=Path(self.temporary.name)/"bad.cnf"
        for content in ("p cnf 5000001 0\n","p cnf 1 2\n1 0\n","p cnf 1 1\n2 0\n"):
            path.write_text(content)
            result=subprocess.run([str(self.binary),str(path)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(result.stdout,"")


if __name__=="__main__":unittest.main()
