"""Closed-set boundaries and fee/verification semantics; synthetic files only."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gate_once as gate
import policy


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))
    return gate.common.sha(path)


class GateFixture:
    def __init__(self, root):
        self.root = root
        self.tools = {}
        self.paths = {}
        for name in ('solver', 'checker', 'extractor', 'cpu_budget_executor'):
            tool = root / name
            tool.write_text(name)
            self.tools[name + '_sha256'] = gate.common.sha(tool)
            self.paths[name + '_sha256'] = str(tool)
        self.cnf = root / 'input.cnf'
        self.cnf.write_text('p cnf 1 1\n1 0\n')
        self.parents = [{'hash': f'{i:032x}', 'role': 'development_gate', 'path': str(self.cnf),
                         'sha256': gate.common.sha(self.cnf), 'header_variables': 1} for i in range(16)]
        configs = {'candidate': {'kind': 'policy', 'tree': {'action': 'Fplus'}},
                   'strong_static': {'kind': 'fixed_action', 'action': 'D'},
                   'simple_control': {'kind': 'policy', 'tree': {'action': 'Fminus'}}}
        prepared = root / 'prepared.json'
        qualified = root / 'qualification.json'
        qsha = write(qualified, {'status': 'PASS', 'wrapper_sha256': self.tools['cpu_budget_executor_sha256'],
                                'solver_sha256': self.tools['solver_sha256'], 'checker_sha256': self.tools['checker_sha256']})
        frozen = root / 'frozen.csv'
        with frozen.open('w') as f:
            writer = csv.DictWriter(f, fieldnames=['hash', 'role', 'bytes', 'variables'])
            writer.writeheader()
            writer.writerows({'hash': f'{i:032x}', 'role': 'development_gate', 'bytes': 20, 'variables': 1} for i in range(51))
        self.plan = {'study_root': str(root), 'phase': 'development_gate', 'cutoff_s': 600, 'seeds': [0],
                     'configurations': configs, 'tool_identity': self.tools, 'tool_paths': self.paths,
                     'cpu_qualification_path': str(qualified), 'cpu_qualification_sha256': qsha,
                     'parent_hashes': [r['hash'] for r in self.parents], 'original_development_csv': str(frozen),
                     'prepared_parents_path': str(prepared), 'prepared_parents_sha256': write(prepared, self.parents)}
        self.original_sha = gate.common.sha(frozen)
        self.make_deployment()
        proposal_plan = root / 'round4_plan.json'
        psha = write(proposal_plan, {'round': 4, 'proposals': [{'depth': 2, 'min_leaf': 12}]})
        memory = root / 'development_episodes.jsonl'
        episodes = [{'round': r, 'episode_id': f'formal_round{r}_0', 'split_role': 'development_feedback',
                     'evaluation_kind': 'new_server_formal_static_cost_matrix',
                     'evaluation_cases_sha256': 'synthetic-development-cases',
                     'panel_contract': {'required_seeds': [0, 1], 'cutoff_s': 600, 'independent_parents': 40},
                     'fit_parents': 24, 'feedback_parents': 16, 'reward': .1, 'plan_sha256': psha,
                     'policy': configs['candidate']['tree'], 'frozen_static_baseline_from_fit': 'D',
                     'matched_simple_control': {'depth': 2, 'min_leaf': 12, 'input_features': sorted(policy.STATIC),
                                                'policy': configs['simple_control']['tree']}}
                    for r in (2, 3, 4)]
        memory.write_text(''.join(json.dumps(e) + '\n' for e in episodes))
        self.plan.update(development_episodes_path=str(memory), development_episodes_sha256=gate.common.sha(memory),
                         chosen_episode_id='formal_round4_0', chosen_proposal_plan_path=str(proposal_plan))
        self.plan_path = root / 'plan.json'
        self.entries = []
        for index, parent in enumerate(self.parents):
            for label, config in configs.items():
                t = {'candidate': 90., 'strong_static': 100., 'simple_control': 105.}[label]
                unit = root / 'units' / f'{index}_{label}'
                r = self.record(parent, config, unit, t=t)
                self.entries.append({'parent_hash': parent['hash'], 'seed': 0,
                                     'configuration_sha256': gate.configuration(config)[1],
                                     'unit_path': str(unit), 'record_sha256': write(unit / 'record.json', r)})
        self.completion_path = root / 'completion.json'
        self.freeze()

    def record(self, parent, config, unit, t=90., h=.1):
        tree, sha = gate.configuration(config)
        action = tree['action']
        logs = unit / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        (logs / 'solver.log').write_text('s SATISFIABLE\nv 1 0\n')
        cmd = [self.paths['solver_sha256'], *gate.FLAGS[action], '--seed=0', '--lrat', '--binary=true',
               '-t', '600', str(self.cnf), str(logs / 'solver.lrat')]
        executed = [self.paths['cpu_budget_executor_sha256'], str(600 - h), *cmd]
        return {'role': parent['role'], 'training_eligible': parent['role'] != 'development_gate',
                'performance_valid': True, 'contended': False, 'input_sha256': parent['sha256'],
                'policy': tree, 'identity': {**self.tools, 'policy_sha256': sha, 'seed': 0, 'cutoff_s': 600,
                    'verification': 'timed_binary_LRAT_lrat_trim', 'budget_mode': 'fractional_process_CPU_and_native_wall_T',
                    'memory_bytes': 3 * 1024**3, 'proof_file_limit_bytes': 8 * 1024**3},
                'cutoff_s': 600, 'features': {}, 'action': action,
                'evidence_sha256': {'logs/solver.log': gate.common.sha(logs / 'solver.log')},
                'feature_and_decision_cpu_s': h, 'solver': {'cpu_s': t, 'wall_s': t, 'exit_code': 10,
                    'command': executed, 'watchdog_killed': False}, 'checker': None,
                'solver_invocation': cmd, 'budget_executor_invocation': executed,
                'verify': 'VERIFIED_MODEL', 'status': 'SAT', 'resolved': h + t <= 600,
                'par2': h + t if h + t <= 600 else 1200}

    def make_deployment(self):
        dev = self.root / 'dev40.csv'
        rows = [{'hash': f'{i+100:032x}', 'role': 'development_fit' if i < 24 else 'development_feedback',
                 'expected_sha256_cnf': gate.common.sha(self.cnf)} for i in range(40)]
        with dev.open('w') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        self.dev_sha = gate.common.sha(dev)
        dep = self.root / 'deployment'
        selected = rows[:4] + rows[24:28]
        receipts = []
        unit_identity = None
        for i, row in enumerate(selected):
            unit = dep / 'results/units' / f"{i:02d}_{row['hash']}"
            parent = {**row, 'path': str(self.cnf), 'sha256': row['expected_sha256_cnf']}
            r = self.record(parent, self.plan['configurations']['candidate'], unit)
            unit_identity = r['identity']
            receipts.append({'parent_hash': row['hash'], 'record_sha256': write(unit / 'record.json', r)})
        done = {'status': 'COMPLETE', 'parents': 8, 'runs': 8, 'receipts': receipts,
                'identity': {'unit_identity': unit_identity}}
        self.plan.update(development_cohort_path=str(dev), deployment_root=str(dep),
                         deployment_completion_sha256=write(dep / 'results/completion.json', done))

    def freeze(self):
        psha = write(self.plan_path, self.plan)
        write(self.completion_path, {'status': 'COMPLETE', 'phase': 'development_gate',
                                    'plan_sha256': psha, 'records': self.entries})

    def patches(self):
        return patch.multiple(gate, ORIGINAL_DEVELOPMENT_SHA=self.original_sha, DEV40_SHA=self.dev_sha, TOOLS=self.tools)


class GateContract(unittest.TestCase):
    def test_point_gain_without_supported_interval_does_not_open_confirmation(self):
        result = gate.compare([10.] + [100.] * 15, [100.] * 16)
        self.assertGreater(result['relative_par2_improvement'], .02)
        self.assertEqual(result['paired_parent_95pct_interval'][0], 0.)
        self.assertFalse(result['passes'])
        self.assertFalse(gate.compare([98.1] * 16, [100.] * 16)['passes'])

    def test_improving_only_one_control_is_insufficient(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = GateFixture(Path(d))
            for entry in fixture.entries:
                if entry['unit_path'].endswith('simple_control'):
                    unit = Path(entry['unit_path']);r = json.loads((unit / 'record.json').read_text())
                    r['solver']['cpu_s'] = 80.;r['par2'] = 80.1
                    entry['record_sha256'] = write(unit / 'record.json', r)
            fixture.freeze()
            with fixture.patches(): report = gate.consume(fixture.root, fixture.plan_path, fixture.completion_path)
            self.assertTrue(report['comparisons']['strong_static']['passes'])
            self.assertFalse(report['confirmation_permitted'])
            self.assertFalse((fixture.root / 'context').exists())

    def test_once_only_exact_reuse_and_changed_identity_or_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = GateFixture(Path(d))
            with fixture.patches():
                report = gate.consume(fixture.root, fixture.plan_path, fixture.completion_path)
                self.assertTrue(report['confirmation_permitted'])
                self.assertTrue(gate.consume(fixture.root, fixture.plan_path, fixture.completion_path)['reused_stored_decision'])
                unit = Path(fixture.entries[0]['unit_path'])
                (unit / 'logs/solver.log').write_text('changed')
                with self.assertRaisesRegex(ValueError, 'evidence changed'):
                    gate.consume(fixture.root, fixture.plan_path, fixture.completion_path)
                fixture.plan['irrelevant_change'] = True;fixture.freeze()
                with self.assertRaisesRegex(ValueError, 'already consumed'):
                    gate.consume(fixture.root, fixture.plan_path, fixture.completion_path)

    def test_missing_or_duplicate_runs_do_not_consume_gate(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory() as d:
                fixture = GateFixture(Path(d))
                if duplicate: fixture.entries[-1] = fixture.entries[0]
                else: fixture.entries.pop()
                fixture.freeze()
                with fixture.patches(), self.assertRaisesRegex(ValueError, 'incomplete or duplicate'):
                    gate.consume(fixture.root, fixture.plan_path, fixture.completion_path)
                self.assertFalse((fixture.root / 'results/closed_gate_once/claim.json').exists())

    def test_fee_crossing_deadline_and_unverified_model(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = GateFixture(Path(d));entry = fixture.entries[0];unit = Path(entry['unit_path'])
            r = json.loads((unit / 'record.json').read_text())
            r['solver']['cpu_s'] = 599.95;r['resolved'] = False;r['par2'] = 1200
            with fixture.patches():
                sha = write(unit / 'record.json', r)
                self.assertEqual(gate.actual_cost(unit, sha, fixture.parents[0], fixture.plan['configurations']['candidate'], fixture.plan), 1200)
                (unit / 'logs/solver.log').write_text('s SATISFIABLE\nv -1 0\n')
                r['evidence_sha256']['logs/solver.log'] = gate.common.sha(unit / 'logs/solver.log')
                sha = write(unit / 'record.json', r)
                with self.assertRaisesRegex(ValueError, 'invalid actual model'):
                    gate.actual_cost(unit, sha, fixture.parents[0], fixture.plan['configurations']['candidate'], fixture.plan)

    def test_protected_feedback_flag_and_fake_cost_cannot_pass(self):
        for key, value in [('training_eligible', True), ('par2', float('nan')), ('status', 'ERROR')]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as d:
                fixture = GateFixture(Path(d));entry = fixture.entries[0];unit = Path(entry['unit_path'])
                r = json.loads((unit / 'record.json').read_text());r[key] = value
                sha = write(unit / 'record.json', r)
                with fixture.patches(), self.assertRaises(ValueError):
                    gate.actual_cost(unit, sha, fixture.parents[0], fixture.plan['configurations']['candidate'], fixture.plan)

    def test_fixed_iminus_remains_a_control_and_not_a_learnable_action(self):
        tree, sha = gate.configuration({'kind': 'fixed_action', 'action': 'Iminus'})
        self.assertEqual(tree, {'action': 'Iminus'})
        with self.assertRaises(ValueError): policy.validate(tree)
        with self.assertRaises(ValueError): gate.configuration({'kind': 'policy', 'tree': tree})
        self.assertEqual(gate.configuration({'kind': 'fixed_action', 'action': 'D'})[1],
                         gate.configuration({'kind': 'policy', 'tree': {'action': 'D'}})[1])

    def test_deployment_is_real_prerequisite_and_parent_order_is_frozen(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = GateFixture(Path(d))
            fixture.plan['parent_hashes'] = list(reversed(fixture.plan['parent_hashes']))
            with fixture.patches(), self.assertRaisesRegex(ValueError, 'first sixteen'):
                gate.frozen_parents(fixture.plan)
            fixture.plan['deployment_completion_sha256'] = '0' * 64
            with fixture.patches(), self.assertRaisesRegex(ValueError, 'changed bound'):
                gate.deployed_candidate(fixture.plan, {'action': 'Fplus'})

    def test_weaker_or_different_controls_and_unfinished_rounds_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = GateFixture(Path(d))
            fixture.plan['configurations']['strong_static']['action'] = 'Fminus'
            with self.assertRaisesRegex(ValueError, 'controls differ'):
                gate.frozen_selection(fixture.plan)
            memory = Path(fixture.plan['development_episodes_path'])
            memory.write_text('\n'.join(memory.read_text().splitlines()[:2]) + '\n')
            fixture.plan['development_episodes_sha256'] = gate.common.sha(memory)
            with self.assertRaisesRegex(ValueError, 'rounds incomplete'):
                gate.frozen_selection(fixture.plan)

    def test_binary_lrat_requires_exit20_marker_and_matching_proof_command(self):
        for exit_code, marker, valid in [(0, 's VERIFIED\n', False), (20, 'missing\n', False), (20, 's VERIFIED\n', True)]:
            with self.subTest(exit_code=exit_code, marker=marker), tempfile.TemporaryDirectory() as d:
                fixture = GateFixture(Path(d));entry = fixture.entries[0];unit = Path(entry['unit_path'])
                r = json.loads((unit / 'record.json').read_text())
                r.update(status='UNSAT', verify='VERIFIED_LRAT')
                r['solver']['exit_code'] = 20
                log = unit / 'logs/checker.log';log.write_text(marker)
                r['evidence_sha256']['logs/checker.log'] = gate.common.sha(log)
                r['checker'] = {'exit_code': exit_code, 'command': [fixture.paths['checker_sha256'],
                                  '--no-trim', *r['solver_invocation'][-2:]]}
                sha = write(unit / 'record.json', r)
                with fixture.patches():
                    if valid:
                        self.assertAlmostEqual(gate.actual_cost(unit, sha, fixture.parents[0],
                            fixture.plan['configurations']['candidate'], fixture.plan), 90.1)
                    else:
                        with self.assertRaisesRegex(ValueError, 'binary LRAT evidence'):
                            gate.actual_cost(unit, sha, fixture.parents[0], fixture.plan['configurations']['candidate'], fixture.plan)


if __name__ == '__main__':
    unittest.main()
