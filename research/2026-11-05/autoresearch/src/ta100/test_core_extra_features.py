"""Finite synthetic template proofs and bounded-context properties only."""
import itertools
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


class ExtraProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory();cls.root=Path(cls.temporary.name)
        header=Path(__file__).with_name('core_extra_features.hpp').resolve()
        wrapper=cls.root/'wrapper.cpp'
        wrapper.write_text('#include "'+str(header)+'"\nint main(int n,char**v){auto f=ta100::read_cnf(v[1]);auto b=ta100_core_extra::compute(f,n>2?0.:1.);ta100::emit(f,b,"extra2");}\n')
        cls.binary=cls.root/'extra'
        subprocess.run(['g++','-O2','-std=c++17',str(wrapper),'-o',str(cls.binary)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()
    def run_cnf(self,n,clauses,budget_zero=False):
        path=self.root/'fixture.cnf';path.write_text('p cnf %d %d\n'%(n,len(clauses))+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
        return json.loads(subprocess.run([str(self.binary),str(path)]+(['zero'] if budget_zero else []),capture_output=True,text=True,check=True).stdout)
    def test_four_clause_template_is_exact_truth_table_definition(self):
        clauses=[[-1,-2,4],[-1,2,-4],[1,-3,4],[1,3,-4]]
        for bits in itertools.product((False,True),repeat=4):
            assignment=dict(enumerate(bits,1))
            actual=all(any(assignment[abs(l)]==(l>0) for l in c) for c in clauses)
            expected=assignment[4]==(assignment[2] if assignment[1] else assignment[3])
            self.assertEqual(actual,expected)
        self.assertEqual(self.run_cnf(4,clauses)['features']['f_core_ite_output'],.25)
    def test_incomplete_template_or_ternary_parity_is_not_ite(self):
        incomplete=[[-1,-2,4],[-1,2,-4],[1,-3,4]]
        self.assertEqual(self.run_cnf(4,incomplete)['features']['f_core_ite_output'],0)
        parity=[[1,2,3],[1,-2,-3],[-1,2,-3],[-1,-2,3]]
        self.assertEqual(self.run_cnf(3,parity)['features']['f_core_ite_output'],0)
    def test_sign_and_variable_rename_invariance_inside_fixed_context(self):
        clauses=[[-1,-2,4],[-1,2,-4],[1,-3,4],[1,3,-4]]
        transform={1:-3,2:1,3:-4,4:2}
        mapped=[[transform[abs(l)]*(1 if l>0 else -1) for l in c] for c in clauses]
        self.assertEqual(self.run_cnf(4,clauses)['features'],self.run_cnf(4,mapped)['features'])
    def test_covered_literal_intersection_without_propagation(self):
        out=self.run_cnf(4,[[1,2],[-1,3],[-1,3,4]])
        self.assertEqual(out['features']['f_core_covered_intersection'],1)
        self.assertEqual(out['blocks']['f_core_covered_intersection']['denominator'],3)
    def test_empty_candidates_and_budget_are_missing_not_zero(self):
        empty=self.run_cnf(1,[[1]])
        self.assertTrue(all(v is None for v in empty['features'].values()))
        limited=self.run_cnf(3,[[1,2,3]],True)
        self.assertTrue(all(v is None for v in limited['features'].values()))
        self.assertTrue(all(v['status']=='TIMEOUT' for v in limited['blocks'].values()))
    def test_context_cap_does_not_claim_unseen_template(self):
        clauses=[[5,6,7]]*256+[[-1,-2,4],[-1,2,-4],[1,-3,4],[1,3,-4]]
        out=self.run_cnf(7,clauses)
        self.assertEqual(out['features']['f_core_ite_output'],0)
        self.assertEqual(out['blocks']['f_core_ite_output']['denominator'],3)


if __name__=='__main__':unittest.main()
