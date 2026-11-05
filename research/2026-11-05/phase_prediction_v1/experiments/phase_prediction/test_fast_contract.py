"""User-directed fast budget must be explicit; no protected rows or relabeling."""
import copy
import json
import unittest
from pathlib import Path
import run_matrix


class FastContract(unittest.TestCase):
    def panel(self):
        project=Path(__file__).resolve().parents[2]
        spec=json.loads((project/'configs/experiments/phase_prediction_v1/fast60_dev40_v1_spec.json').read_text())
        rows=[{'hash':f'{i:032x}','role':'development_fit' if i<24 else 'development_feedback'} for i in range(40)]
        return spec,rows

    def test_eight_workers_fit_declared_cpu_and_memory_envelopes(self):
        spec,rows=self.panel()
        self.assertAlmostEqual(run_matrix.validate_spec(spec,rows),320*60/3600)
        self.assertEqual(spec['workers']*spec['memory_bytes'],12*1024**3)
        self.assertEqual(spec['workers']*spec['proof_file_limit_bytes']+12*1024**3,20*1024**3)

    def test_short_budget_cannot_silently_enter_original_long_contract(self):
        spec,rows=self.panel();spec.pop('fast_development')
        with self.assertRaisesRegex(ValueError,'cutoff'):run_matrix.validate_spec(spec,rows)
        spec,rows=self.panel();spec['cutoff_s']=120
        with self.assertRaisesRegex(ValueError,'fast development'):run_matrix.validate_spec(spec,rows)

    def test_protected_roles_missing_seeds_or_changed_resource_caps_rejected(self):
        spec,rows=self.panel()
        for update in ({'seeds':[0]},{'memory_bytes':3*1024**3},{'proof_file_limit_bytes':8*1024**3}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                run_matrix.validate_spec({**spec,**update},rows)
        protected=copy.deepcopy(rows);protected[-1]['role']='development_gate'
        with self.assertRaises(ValueError):run_matrix.validate_spec(spec,protected)


if __name__=='__main__':unittest.main()
