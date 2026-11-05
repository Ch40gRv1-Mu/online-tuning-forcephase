"""Synthetic algebra semantics only: no benchmark import, solver or outcome files."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).parent


class AlgebraProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            raise unittest.SkipTest('C++17 compiler unavailable')
        cls.binary = cls.directory / 'algebra'
        subprocess.run([compiler, '-O3', '-std=c++17', str(SOURCE / 'algebra_core.cpp'), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def features(self, clauses, n=None, group='algebra18'):
        n = n if n is not None else max((abs(l) for c in clauses for l in c), default=0)
        path = self.directory / 'synthetic.cnf'
        path.write_text(f'p cnf {n} {len(clauses)}\n' + ''.join(' '.join(map(str, c)) + ' 0\n' for c in clauses))
        result = json.loads(subprocess.check_output([str(self.binary), '--module', group, str(path)]))
        self.assertEqual(len(result['features']), {'algebra18': 18, 'algebra10': 10, 'algebra8': 8}[group])
        return result['features']

    def test_horn_objective_and_frustrated_triangle(self):
        all_pairs = [[1, 2], [-1, 2], [1, -2], [-1, -2]]
        self.assertEqual(self.features(all_pairs)['algebra_renamable_horn_deficit'], .25)
        triangle = self.features([[1, 2], [2, 3], [1, 3]])
        self.assertAlmostEqual(triangle['algebra_ising_frustration'], 1 / 3)
        self.assertEqual(triangle['algebra_raw_submodular_fraction'], 0)
        self.assertAlmostEqual(triangle['algebra_cover_packing_gap'], 1 / 3)
        gauge = self.features([[-1, 2], [-2, 3], [-3, 1]])
        self.assertEqual(gauge['algebra_ising_frustration'], 0)
        self.assertEqual(gauge['algebra_raw_submodular_fraction'], 1)

    def test_exact_complement_autarky_and_matching(self):
        opposite = self.features([[1], [-1]])
        self.assertEqual(opposite['algebra_literal_complement_pairing'], 1)
        self.assertEqual(opposite['algebra_majority_autarky_support'], 0)
        positive = self.features([[1, 2], [2, 3]])
        self.assertEqual(positive['algebra_majority_autarky_support'], 1)
        overfull = self.features([[1, 2]] * 3)
        self.assertAlmostEqual(overfull['algebra_hall_deficiency'], 1 / 3)

    def test_polarity_inversion_of_convex_and_bp_pressure(self):
        positive, negative = self.features([[1]]), self.features([[-1]])
        for key in ['algebra_convex_fractional_pressure', 'algebra_bp_cavity_polarity']:
            self.assertGreater(positive[key], 0)
            self.assertAlmostEqual(positive[key], -negative[key])
        self.assertIsNone(positive['algebra_signed_mode_alignment'])
        self.assertEqual(self.features([[1], [-1]])['algebra_bp_cavity_polarity'], 0)

    def test_signed_rank_and_energy_walsh_are_different_objects(self):
        rank2 = self.features([[1, 2], [1, -2]])
        rank1 = self.features([[1, 2], [1, 2]])
        self.assertEqual(rank2['algebra_signed_real_rank_deficit'], 0)
        self.assertEqual(rank1['algebra_signed_real_rank_deficit'], .5)
        self.assertAlmostEqual(self.features([[1, 2, 3]])['algebra_high_order_walsh_mass'], 1 / 7)
        base = [[1, 2, 3], [1, 2]]
        a = self.features(base)['algebra_high_order_walsh_mass']
        b = self.features(base + [[1, 2, 3]])['algebra_high_order_walsh_mass']
        self.assertNotEqual(a, b)  # Logical conjunction unchanged; real energy changed.

    def test_cooperative_escape_and_plateau_component(self):
        # z-satisfied clauses alter majority counts without changing x/y energy at z=1.
        clauses = [[-1, 2], [1, -2], [1], [2], [-1, 3], [-1, 3], [-2, 3], [-2, 3]]
        result = self.features(clauses)
        self.assertAlmostEqual(result['algebra_two_flip_cooperative_escape'], 1 / 3)
        self.assertEqual(result['algebra_plateau_connectedness'], .5)
        one = self.features([[1]])
        self.assertAlmostEqual(one['algebra_sls_state_recurrence'], 127 / 129)
        self.assertEqual(one['algebra_persistent_unsat_core'], 0)

    def test_subcube_probabilities_have_exact_small_cases(self):
        key = 'algebra_falsifying_subcube_covariance'
        self.assertEqual(self.features([[1], [2]])[key], 0)
        self.assertAlmostEqual(self.features([[1], [1]])[key], 1 / 3)
        self.assertEqual(self.features([[1], [-1]])[key], -1)

    def test_sample_identity_and_degenerate_denominators(self):
        key = 'algebra_canonical_lz78_ratio'
        self.assertEqual(self.features([[1, -2]], n=2)[key], self.features([[1, -2]], n=100)[key])
        boundary = self.features([[1]] * 512 + [[-1]])
        self.assertEqual(boundary['algebra_literal_complement_pairing'], 0)
        empty = self.features([[]])
        self.assertIsNone(empty['algebra_cover_packing_gap'])
        self.assertIsNone(empty['algebra_plateau_connectedness'])
        self.assertIsNone(empty['algebra_falsifying_subcube_covariance'])
        self.assertEqual(empty['algebra_hall_deficiency'], 1)


if __name__ == '__main__':
    unittest.main()
