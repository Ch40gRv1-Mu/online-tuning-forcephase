"""Necessary synthetic semantic checks; never opens research CNFs or labels."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).parent


class GraphProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            raise unittest.SkipTest('C++17 compiler unavailable')
        cls.binaries = {}
        for kind, filename in [('first', 'graph_core.cpp'), ('extra', 'graph_extra_core.cpp')]:
            target = cls.directory / kind
            subprocess.run([compiler, '-O3', '-std=c++17', str(SOURCE / filename), '-o', str(target)], check=True)
            cls.binaries[kind] = target

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def evaluate(self, clauses, n, group):
        path = self.directory / 'synthetic.cnf'
        path.write_text(f'p cnf {n} {len(clauses)}\n' + ''.join(' '.join(map(str, c)) + ' 0\n' for c in clauses))
        binary = self.binaries['first' if group == 'graph10' else 'extra']
        record = json.loads(subprocess.check_output([str(binary), '--module', group, str(path)]))
        self.assertEqual(len(record['features']), 10)
        self.assertEqual(set(record['features']), set(record['blocks']))
        return record['features']

    def test_recursive_core_and_separator_have_distinct_semantics(self):
        path = self.evaluate([[1, 2], [2, 3]], 3, 'graph10')
        self.assertEqual(path['graph_core_retention'], 0)
        self.assertAlmostEqual(path['graph_articulation_fragility'], 2 / 9)
        cycle = self.evaluate([[1, 2], [1, 2]], 2, 'graph10')
        self.assertEqual(cycle['graph_core_retention'], 1)
        self.assertEqual(cycle['graph_butterfly_overlap'], .5)

    def test_joint_sign_arity_and_horn_interface(self):
        tied = self.evaluate([[1], [-2, -3]], 3, 'graph10')
        self.assertAlmostEqual(tied['graph_sign_arity_information'], 1)
        interface = self.evaluate([[1, 2], [-1, 3]], 3, 'graph10')
        self.assertEqual(interface['graph_horn_interface'], .25)
        self.assertIsNone(interface['graph_incidence_assortativity'])  # Constant arity is undefined.

    def test_triangle_filling_and_chordality_are_not_cycle_rank(self):
        cycle = [[1, 2], [2, 3], [3, 4], [4, 1]]
        triangle = [[1, 2], [2, 3], [1, 3]]
        self.assertEqual(self.evaluate(cycle, 4, 'graph40')['graph_betti1'], .25)
        self.assertEqual(self.evaluate(triangle, 3, 'graph40')['graph_betti1'], 0)
        self.assertGreater(self.evaluate(cycle, 4, 'graph30')['graph_chordality'], 0)
        self.assertEqual(self.evaluate(triangle, 3, 'graph30')['graph_chordality'], 0)
        self.assertEqual(self.evaluate([[1, 2], [1, 2]], 2, 'graph20')['graph_gyo'], 0)

    def test_complete_majority_requires_all_six_clauses(self):
        clauses = [[-1, -2, 4], [-1, -3, 4], [-2, -3, 4], [1, 2, -4], [1, 3, -4], [2, 3, -4]]
        self.assertEqual(self.evaluate(clauses, 4, 'graph30')['graph_majority_gate_coverage'], .25)
        self.assertEqual(self.evaluate(clauses[:-1], 4, 'graph30')['graph_majority_gate_coverage'], 0)

    def test_signed_gate_direction_and_composed_forcing_cost(self):
        gate = [[-3, 1], [-3, 2], [3, -1, -2]]
        self.assertEqual(self.evaluate(gate, 3, 'graph30')['graph_gate_output_direction'], 1)
        self.assertEqual(self.evaluate([[-x for x in c] for c in gate], 3, 'graph30')['graph_gate_output_direction'], -1)
        self.assertAlmostEqual(self.evaluate(gate, 3, 'graph40')['graph_controllability'], .2)
        shared = gate + [[-5, 3], [-5, 4], [5, -3, -4], [-6, 3], [-6, 7], [6, -3, -7]]
        self.assertAlmostEqual(self.evaluate(shared, 7, 'graph10')['graph_gate_sharing'], 1 / 6)
        self.assertEqual(self.evaluate(shared, 7, 'graph10')['graph_circuit_residual_interface'], 0)

    def test_local_nonlinear_predicate_excludes_reserved_affine_parity(self):
        parity = [[1, 2, 3], [1, -2, -3], [-1, 2, -3], [-1, -2, 3]]
        f = self.evaluate(parity, 3, 'graph40')
        self.assertIsNone(f['graph_anf_degree'])
        self.assertEqual(f['graph_other_functional'], 0)
        # z <-> (a XOR (b AND c)): total nonlinear function outside AND/ITE/MAJ.
        nonlinear = []
        for mask in range(16):
            a, b, c, z = ((mask >> j) & 1 for j in range(4))
            if z != (a ^ (b & c)):
                nonlinear.append([-(j + 1) if (mask >> j) & 1 else j + 1 for j in range(4)])
        result = self.evaluate(nonlinear, 4, 'graph40')
        self.assertEqual(result['graph_other_functional'], 1)
        self.assertEqual(result['graph_anf_degree'], .5)

    def test_sign_bundling_detects_more_than_sign_arity_mi(self):
        balanced = [[1, 2, -3, -4], [-1, -2, 3, 4]]
        bundled = [[1, 2, 3, 4], [-1, -2, -3, -4]]
        self.assertAlmostEqual(self.evaluate(balanced, 4, 'graph10')['graph_sign_arity_information'], 0)
        self.assertAlmostEqual(self.evaluate(bundled, 4, 'graph10')['graph_sign_arity_information'], 0)
        a = self.evaluate(balanced, 4, 'graph40')['graph_sign_bundling']
        b = self.evaluate(bundled, 4, 'graph40')['graph_sign_bundling']
        self.assertGreater(b, a)

    def test_empty_population_is_missing_not_fake_zero(self):
        for group in ['graph10', 'graph20', 'graph30', 'graph40']:
            self.assertTrue(all(v is None for v in self.evaluate([[]], 0, group).values()))


if __name__ == '__main__':
    unittest.main()
