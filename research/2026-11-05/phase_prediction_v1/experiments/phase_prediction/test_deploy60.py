"""Deadline and ownership checks for the new T60 path; no SAT solving."""
import fcntl
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import deploy_static60 as deploy
import deploy_batch60 as batch
import deployment_consistency
import policy
import run_pilot as common


class T60Deployment(unittest.TestCase):
    def test_feature_cpu_reduces_actual_deadline_and_verified_late_answer_scores_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'units').mkdir()
            cnf = root/'input.cnf'
            cnf.write_text('p cnf 1 1\n1 0\n')
            tree = {'feature': 's_mean_length', 'threshold': 2, 'missing': 'left',
                    'left': {'action': 'D'}, 'right': {'action': 'Fminus'}}
            spec = {'total_cpu_budget_s': 60, 'seed': 0, 'cpu': 0,
                    'memory_bytes': 1536*1024**2, 'proof_file_limit_bytes': 1024**3,
                    'policy_sha256': policy.validate(tree)}
            for name in ('solver', 'checker', 'extractor', 'cpu_budget_executor'):
                path = root/name
                path.write_text(name)
                spec[name] = str(path)
                spec[name+'_sha256'] = common.sha(path)
            gate = root/'qualification.json'
            common.write(gate, {'status': 'PASS', 'wrapper_sha256': spec['cpu_budget_executor_sha256'],
                               'solver_sha256': spec['solver_sha256'], 'checker_sha256': spec['checker_sha256']})
            spec.update(cpu_budget_qualification_path=str(gate), cpu_budget_qualification_sha256=common.sha(gate))
            parent = {'role': 'development_fit', 'path': str(cnf), 'sha256': common.sha(cnf), 'header_variables': 1}
            calls = []
            def child(command, log, cutoff, cpu, **kw):
                calls.append((command, cutoff, kw))
                feature = str(command[0]) == spec['extractor']
                text = '{"s_mean_length":1}' if feature else 'v 1 0\n'
                log.write_text(text)
                return {'cpu_s': .25 if feature else 59.8, 'wall_s': .25 if feature else 59.8,
                        'exit_code': 0 if feature else 10, 'watchdog_killed': False,
                        'command': list(map(str, command))}, text
            with patch.object(deploy.common, 'child', side_effect=child):
                r = deploy.run_one(spec, parent, tree, root/'units/one')
            self.assertEqual(r['verify'], 'VERIFIED_MODEL')
            self.assertFalse(r['resolved'])
            self.assertEqual(r['par2'], 120)
            self.assertLessEqual(r['remaining_solver_cpu_budget_s'], 59.75)
            self.assertEqual(calls[0][2]['memory'], 3*1024**3)
            self.assertEqual(calls[1][2]['memory'], 1536*1024**2)
            self.assertEqual(calls[1][2]['file_limit_bytes'], 1024**3)
            self.assertEqual(deployment_consistency.check(root/'units/one')['par2'], 120)

    def test_existing_owner_prevents_all_unit_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            parents = [{'hash': f'{i:032x}', 'role': 'development_fit' if i < 24 else 'development_feedback'} for i in range(40)]
            pp, tp, sp = root/'parents.json', root/'policy.json', root/'spec.json'
            common.write(pp, parents)
            common.write(tp, {'action': 'D'})
            spec = {'parent_manifest_sha256': common.sha(pp), 'selected_parent_hashes': [r['hash'] for r in batch.selected_parents(parents)],
                    'policy_sha256': policy.validate({'action': 'D'}), 'seed': 0, 'total_cpu_budget_s': 60,
                    'memory_bytes': 1536*1024**2, 'proof_file_limit_bytes': 1024**3, 'cpus': list(range(8)),
                    'cpu_budget_executor': 'qualified', 'max_new_physical_cpu_hours': 1,
                    'solver_sha256': 'solver', 'checker_sha256': 'checker', 'extractor_sha256': 'extractor'}
            for kind in ('completion', 'integrity'):
                path = root/(kind+'.json')
                common.write(path, {'parents': 40, 'runs': 320, 'status': 'COMPLETE', 'complete_and_valid': True})
                spec['source_'+kind+'_path'], spec['source_'+kind+'_sha256'] = str(path), common.sha(path)
            common.write(sp, spec)
            out = root/'deployment'
            out.mkdir()
            with (out/'.owner.lock').open('w+') as owner:
                owner.write('live original owner')
                owner.flush()
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(batch.deploy_static, 'execution_identity', return_value={}), patch.object(batch.deploy_static, 'run_one') as unit:
                    with self.assertRaisesRegex(RuntimeError, 'active owner'):
                        batch.run_batch(sp, pp, tp, out)
                unit.assert_not_called()
                self.assertEqual((out/'.owner.lock').read_text(), 'live original owner')


if __name__ == '__main__':
    unittest.main()
