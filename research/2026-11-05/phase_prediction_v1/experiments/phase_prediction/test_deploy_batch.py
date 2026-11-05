"""Ownership/checkpoint unit tests only; synthetic results never enter research memory."""
import fcntl,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import deploy_batch as batch
import deploy_static,policy
import run_pilot as common

class DeploymentCheckpoint(unittest.TestCase):
    def fixture(self,root):
        complete=root/'source_complete.json';complete.write_text('{"status":"COMPLETE","parents":40,"runs":320}')
        integrity=root/'source_integrity.json';integrity.write_text('{"complete_and_valid":true,"parents":40,"runs":320}')
        parents=[{'hash':f'{i:032x}','role':'development_fit' if i<24 else 'development_feedback',
            'path':'public.cnf','sha256':'bound-input','header_variables':1} for i in range(40)]
        pp=root/'parents.json';pp.write_text(json.dumps(parents))
        tree={'action':'D'};tp=root/'policy.json';tp.write_text(json.dumps(tree))
        spec={'parent_manifest_sha256':common.sha(pp),'selected_parent_hashes':[r['hash'] for r in batch.selected_parents(parents)],
            'source_completion_path':str(complete),'source_completion_sha256':common.sha(complete),
            'source_integrity_path':str(integrity),'source_integrity_sha256':common.sha(integrity),
            'policy_sha256':policy.validate(tree),'seed':0,'total_cpu_budget_s':600,
            'proof_file_limit_bytes':8*1024**3,'max_new_physical_cpu_hours':2.,
            'cpu_budget_executor':'qualified-helper','cpu_budget_executor_sha256':'qualified-wrapper',
            'cpu_budget_qualification_sha256':'qualified-gate',
            'solver_sha256':'solver','checker_sha256':'checker','extractor_sha256':'extractor'}
        sp=root/'spec.json';sp.write_text(json.dumps(spec));return sp,pp,tp

    def fake_unit(self,spec,parent,tree,unit):
        unit.mkdir(parents=True)
        common.write(unit/'record.json',{'identity':deploy_static.execution_identity(spec),
            'input_sha256':parent['sha256'],'role':parent['role']})

    def test_completed_units_are_not_reexecuted_or_completion_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);paths=self.fixture(root);out=root/'deployment'
            with patch.object(batch.deploy_static,'run_one',side_effect=self.fake_unit) as run, \
                 patch.object(batch.deployment_consistency,'check',return_value={'status':'UNIT_TEST_ONLY'}):
                first=batch.run_batch(*paths,out);before=(out/'results/completion.json').read_bytes()
                second=batch.run_batch(*paths,out)
            self.assertEqual(first['runs'],8);self.assertEqual(run.call_count,8)
            self.assertTrue(second['reused_existing_completed_stage'])
            self.assertEqual((out/'results/completion.json').read_bytes(),before)

    def test_incomplete_unit_requires_inspection_instead_of_duplicate_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);paths=self.fixture(root);out=root/'deployment'
            (out/'results/units'/('00_'+'0'*32)).mkdir(parents=True)
            with patch.object(batch.deploy_static,'run_one') as run:
                with self.assertRaisesRegex(RuntimeError,'incomplete unit'):batch.run_batch(*paths,out)
            run.assert_not_called();self.assertTrue(list((out/'results').glob('failure_*.json')))

    def test_second_owner_cannot_touch_a_healthy_deployment(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);paths=self.fixture(root);out=root/'deployment';out.mkdir()
            with (out/'.owner.lock').open('w+') as owner:
                owner.write('existing-owner');owner.flush();fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError,'active owner'):batch.run_batch(*paths,out)
            self.assertEqual((out/'.owner.lock').read_text(),'existing-owner')

    def test_protected_role_or_changed_policy_rejected_before_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);sp,pp,tp=self.fixture(root);out=root/'deployment'
            tp.write_text('{"action":"Fplus"}')
            with self.assertRaises(ValueError):batch.run_batch(sp,pp,tp,out)
            self.assertFalse(out.exists())
            tp.write_text('{"action":"D"}');parents=json.loads(pp.read_text());parents[0]['role']='development_gate';pp.write_text(json.dumps(parents))
            with self.assertRaises(ValueError):batch.run_batch(sp,pp,tp,out)
            self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
