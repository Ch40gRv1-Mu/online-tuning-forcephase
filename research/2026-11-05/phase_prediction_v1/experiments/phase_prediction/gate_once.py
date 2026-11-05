"""Consume one complete, frozen gate receipt; never run a solver or update memory.

The closed execution controller must produce SHA-bound actual deployment-style
records. Development-only runners continue to reject these protected roles.
"""
import argparse
import csv
import fcntl
import hashlib
import json
import math
import random
import signal
import statistics
from pathlib import Path, PurePosixPath

import deployment_consistency
import policy
import run_pilot as common

ORIGINAL_DEVELOPMENT_SHA = '07bc7d3e6c85a064dcfbb11a685f9d2363d02b441cbe0e19f11981b436a42ff9'
DEV40_SHA = 'bc62884e0cbbb30cb25958103819065de954c3c84d6cfdac6e326bd85295d5f6'
FLAGS = {**common.FLAGS, 'Iminus': ['--phase=0', '--forcephase=0']}
LABELS = {'candidate', 'strong_static', 'simple_control'}
TOOLS = {
    'solver_sha256': 'b57d545231cab5a90357242cc838847356354324d891ef8ddaadcbf224e66bdb',
    'checker_sha256': 'eb89bf384e1384af0d4e6ba81904c193f57e7848f357f1a6541e7f0bb6286603',
    'extractor_sha256': '2f4cc472d4430b10785688b68ec0afb5d80e18eb7c90564754d08214c398f334',
    'cpu_budget_executor_sha256': '7b0e95364847b13f54268cd2b2f5e383839169ca0a613460b05e202c11d8d3e2',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def configuration(config):
    if config.get('kind') == 'policy' and set(config) == {'kind', 'tree'}:
        policy.validate(config['tree'])
        tree = config['tree']
    elif config.get('kind') == 'fixed_action' and set(config) == {'kind', 'action'}:
        if config['action'] not in FLAGS:
            raise ValueError('unknown fixed control')
        tree = {'action': config['action']}
    else:
        raise ValueError('invalid frozen configuration')
    # A constant learned policy and the same fixed action share one physical run.
    return tree, digest(tree)


def bound_json(path, expected_sha):
    path = Path(path)
    if common.sha(path) != expected_sha:
        raise ValueError('changed bound artifact')
    return json.loads(path.read_text())


def finite_nonnegative(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('invalid CPU cost')
    return value


def frozen_parents(plan):
    path = Path(plan['original_development_csv'])
    if common.sha(path) != ORIGINAL_DEVELOPMENT_SHA:
        raise ValueError('changed original development freeze')
    with path.open() as f:
        eligible = [r for r in csv.DictReader(f) if r['role'] == 'development_gate'
                    and int(r['bytes']) <= 100000000 and int(r['variables']) <= 5000000]
    if len(eligible) != 51 or plan['parent_hashes'] != [r['hash'] for r in eligible[:16]]:
        raise ValueError('gate must use the first sixteen original eligible parents')
    prepared = bound_json(plan['prepared_parents_path'], plan['prepared_parents_sha256'])
    if [r['hash'] for r in prepared] != plan['parent_hashes'] or len({r['hash'] for r in prepared}) != 16:
        raise ValueError('changed prepared gate cohort')
    if any(r['role'] != 'development_gate' for r in prepared):
        raise ValueError('gate role mismatch')
    for parent in prepared:
        if common.sha(Path(parent['path'])) != parent['sha256']:
            raise ValueError('gate formula changed')
    return prepared


def deployed_candidate(plan, candidate_tree):
    """Require the actual eight-unit evidence, not an asserted PASS boolean."""
    dev = Path(plan['development_cohort_path'])
    if common.sha(dev) != DEV40_SHA:
        raise ValueError('changed source development cohort')
    with dev.open() as f:
        rows = list(csv.DictReader(f))
    selected = [r for r in rows if r['role'] == 'development_fit'][:4]
    selected += [r for r in rows if r['role'] == 'development_feedback'][:4]
    root = Path(plan['deployment_root'])
    done = bound_json(root / 'results/completion.json', plan['deployment_completion_sha256'])
    candidate_sha = policy.validate(candidate_tree)
    if done['status'] != 'COMPLETE' or done['parents'] != 8 or done['runs'] != 8 or \
            done['identity']['unit_identity']['policy_sha256'] != candidate_sha:
        raise ValueError('candidate has no complete actual deployment')
    if [r['parent_hash'] for r in done['receipts']] != [r['hash'] for r in selected]:
        raise ValueError('wrong fixed deployment subset')
    for i, (parent, receipt) in enumerate(zip(selected, done['receipts'])):
        unit = root / 'results/units' / f"{i:02d}_{parent['hash']}"
        r = bound_json(unit / 'record.json', receipt['record_sha256'])
        if r['policy'] != candidate_tree or r['role'] != parent['role'] or \
                r['input_sha256'] != parent['expected_sha256_cnf'] or r['identity'] != done['identity']['unit_identity']:
            raise ValueError('wrong deployed candidate or parent')
        if r['identity'].get('budget_mode') != 'fractional_process_CPU_and_native_wall_T' or \
                r['identity']['cutoff_s'] != 600 or r['identity']['seed'] != 0 or \
                any(r['identity'][k] != sha for k, sha in TOOLS.items()):
            raise ValueError('candidate deployment used unqualified or changed tools/settings')
        deployment_consistency.check(unit)
    return {'parents': 8, 'completion_sha256': plan['deployment_completion_sha256']}


def frozen_selection(plan):
    """Bind the candidate and both controls to actual bounded development."""
    memory = Path(plan['development_episodes_path'])
    if common.sha(memory) != plan['development_episodes_sha256']:
        raise ValueError('development history changed after finalist freeze')
    episodes = [json.loads(s) for s in memory.read_text().splitlines() if s]
    if any(e['split_role'] not in ('development_fit', 'development_feedback') for e in episodes):
        raise ValueError('protected feedback in development memory')
    formal = [e for e in episodes if e.get('evaluation_kind') == 'new_server_formal_static_cost_matrix']
    if len({e['episode_id'] for e in formal}) != len(formal) or \
            len({e['evaluation_cases_sha256'] for e in formal}) != 1:
        raise ValueError('duplicate episodes or changed formal development panel')
    rounds = sorted({e['round'] for e in formal})
    if not rounds or rounds[-1] < 4 or rounds[-1] > 8 or rounds != list(range(2, rounds[-1] + 1)) or \
            any(not 1 <= sum(e['round'] == r for e in formal) <= 2 for r in rounds):
        raise ValueError('required bounded actual development rounds incomplete')
    chosen = [e for e in formal if e['episode_id'] == plan['chosen_episode_id']]
    if len(chosen) != 1:
        raise ValueError('missing or duplicate selected development episode')
    episode = chosen[0]
    if episode['panel_contract'] != {'required_seeds': [0, 1], 'cutoff_s': 600, 'independent_parents': 40} or \
            episode['fit_parents'] != 24 or episode['feedback_parents'] != 16 or \
            not math.isfinite(episode['reward']) or episode['reward'] <= 0:
        raise ValueError('no positive complete formal development candidate')
    proposal_plan = bound_json(plan['chosen_proposal_plan_path'], episode['plan_sha256'])
    if proposal_plan['round'] != episode['round']:
        raise ValueError('wrong selected proposal round')
    index = int(episode['episode_id'].rsplit('_', 1)[1])
    proposal = proposal_plan['proposals'][index]
    control = episode['matched_simple_control']
    if (control['depth'], control['min_leaf']) != (proposal['depth'], proposal['min_leaf']) or \
            control['input_features'] != sorted(policy.STATIC):
        raise ValueError('simple control capacity mismatch')
    policy.validate(episode['policy'], max_depth=proposal['depth'])
    policy.validate(control['policy'], max_depth=proposal['depth'])
    expected = {'candidate': {'kind': 'policy', 'tree': episode['policy']},
                'strong_static': {'kind': 'fixed_action', 'action': episode['frozen_static_baseline_from_fit']},
                'simple_control': {'kind': 'policy', 'tree': control['policy']}}
    if plan['configurations'] != expected:
        raise ValueError('gate candidate or controls differ from frozen development selection')
    return {'episode_id': episode['episode_id'], 'memory_sha256': plan['development_episodes_sha256']}


def actual_cost(unit, record_sha, parent, config, plan):
    """Independently reconstruct actual h+t and proof/model verification."""
    unit = Path(unit)
    r = bound_json(unit / 'record.json', record_sha)
    tree, config_sha = configuration(config)
    if r['role'] != 'development_gate' or r.get('training_eligible') is not False or \
            r.get('performance_valid') is not True or r.get('contended') is not False:
        raise ValueError('protected, failed, or contended measurement is ineligible')
    if r['input_sha256'] != parent['sha256'] or r['policy'] != tree or \
            r['identity']['policy_sha256'] != config_sha:
        raise ValueError('gate configuration/input identity mismatch')
    if r['identity']['seed'] != 0 or r['cutoff_s'] != 600 or r['identity']['cutoff_s'] != 600:
        raise ValueError('gate seed/cutoff changed')
    for key in ('solver_sha256', 'checker_sha256', 'extractor_sha256', 'cpu_budget_executor_sha256'):
        if r['identity'][key] != plan['tool_identity'][key]:
            raise ValueError('gate tool identity changed')
    if r['identity'].get('verification') != 'timed_binary_LRAT_lrat_trim' or \
            r['identity'].get('budget_mode') != 'fractional_process_CPU_and_native_wall_T':
        raise ValueError('unqualified gate timing/verification mode')
    if r['identity'].get('memory_bytes') != 3 * 1024**3 or \
            r['identity'].get('proof_file_limit_bytes') != 8 * 1024**3:
        raise ValueError('gate resource contract changed')
    if not isinstance(r['features'], dict) or not set(r['features']) <= policy.STATIC:
        raise ValueError('forbidden gate policy input')
    for value in r['features'].values():
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError('non-numeric gate policy input')
    action = policy.decide(tree, r['features']) if config['kind'] == 'policy' else config['action']
    if action != r['action']:
        raise ValueError('gate action disagrees with frozen configuration')
    for name, sha in r['evidence_sha256'].items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.parts[0] != 'logs':
            raise ValueError('unsafe evidence path')
        if common.sha(unit / name) != sha:
            raise ValueError('gate raw evidence changed')
    if 'feature' in tree and 'logs/features.log' not in r['evidence_sha256']:
        raise ValueError('gate feature observation is not bound')
    if 'feature' in tree:
        raw = json.loads((unit / 'logs/features.log').read_text())
        if not set(raw) <= policy.STATIC | {'feature_wall_s'} or \
                {k: v for k, v in raw.items() if k in policy.STATIC} != r['features']:
            raise ValueError('gate features disagree with actual observation')
    elif r['features']:
        raise ValueError('fixed action must skip feature extraction')
    h = finite_nonnegative(r['feature_and_decision_cpu_s'])
    if r['solver'] is None:
        if h < 600 or r['status'] != 'OBSERVATION_BUDGET_EXHAUSTED' or \
                r['verify'] != 'NOT_ANSWERED' or r['solver_invocation']:
            raise ValueError('invalid observation-budget outcome')
        expected, solved = 1200, False
    else:
        t = finite_nonnegative(r['solver']['cpu_s'])
        cmd = r['solver_invocation']
        if Path(cmd[-2]).resolve() != Path(parent['path']).resolve() or common.sha(Path(cmd[0])) != TOOLS['solver_sha256']:
            raise ValueError('wrong actual formula or solver')
        for prefix, value in zip(('--phase=', '--forcephase='), FLAGS[action]):
            if [x for x in cmd if x.startswith(prefix)] != [value]:
                raise ValueError('wrong actual gate solver flags')
        if [x for x in cmd if x.startswith('--seed=')] != ['--seed=0'] or \
                '--lrat' not in cmd or '--binary=true' not in cmd or cmd[cmd.index('-t') + 1] != '600':
            raise ValueError('wrong actual gate seed/proof/time invocation')
        executed = r['budget_executor_invocation']
        if h >= 600 or len(executed) != len(cmd) + 2 or executed[2:] != cmd or \
                common.sha(Path(executed[0])) != TOOLS['cpu_budget_executor_sha256'] or \
                r['solver']['command'][-len(executed):] != executed or \
                abs(float(executed[1]) - (600 - h)) > 1e-7:
            raise ValueError('wrong actual remaining CPU budget')
        if 'logs/solver.log' not in r['evidence_sha256']:
            raise ValueError('missing actual solver evidence')
        verify = r['verify']
        if verify == 'VERIFIED_LRAT':
            import re
            if r['status'] != 'UNSAT' or r['solver']['exit_code'] != 20 or r['checker']['exit_code'] != 20 or \
                    'logs/checker.log' not in r['evidence_sha256'] or \
                    not re.search(r'^s VERIFIED', (unit / 'logs/checker.log').read_text(), re.M):
                raise ValueError('invalid binary LRAT evidence')
            checker_cmd = r['checker']['command'][-4:]
            if len(checker_cmd) != 4 or common.sha(Path(checker_cmd[0])) != TOOLS['checker_sha256'] or \
                    checker_cmd[1:] != ['--no-trim', cmd[-2], cmd[-1]]:
                raise ValueError('wrong actual checker invocation')
        elif verify == 'VERIFIED_MODEL':
            if r['status'] != 'SAT' or r['solver']['exit_code'] != 10 or \
                    not common.check_model(Path(parent['path']), (unit / 'logs/solver.log').read_text(), parent['header_variables']):
                raise ValueError('invalid actual model')
        elif verify != 'NOT_ANSWERED' or r['status'] not in ('UNKNOWN', 'TIMEOUT') or \
                (r['solver']['exit_code'] not in (0, -signal.SIGPROF) and not r['solver'].get('watchdog_killed')):
            raise ValueError('engineering failure cannot be scored as timeout')
        solved = verify.startswith('VERIFIED_') and h + t <= 600
        expected = h + t if solved else 1200
    stored_score = finite_nonnegative(r['par2'])
    if not isinstance(r['resolved'], bool) or r['resolved'] != solved or abs(stored_score - expected) > 1e-8:
        raise ValueError('gate stored score disagrees with actual total cost')
    return expected


def compare(candidate, control):
    if len(candidate) != 16 or len(control) != 16:
        raise ValueError('sixteen independent paired parents required')
    base = statistics.mean(control)
    if base <= 0:
        raise ValueError('nonpositive gate control cost')
    reward = 1 - statistics.mean(candidate) / base
    rng = random.Random(20261104)
    draws = []
    for _ in range(2000):
        indices = [rng.randrange(16) for _ in range(16)]
        denominator = statistics.mean(control[i] for i in indices)
        if denominator <= 0:
            raise ValueError('degenerate paired control resample')
        draws.append(1 - statistics.mean(candidate[i] for i in indices) / denominator)
    draws.sort()
    interval = [draws[50], draws[1950]]
    return {'relative_par2_improvement': reward, 'paired_parent_95pct_interval': interval,
            'candidate_mean_par2': statistics.mean(candidate), 'control_mean_par2': base,
            'passes': reward >= .02 and interval[0] > 0}


def consume(study_root, plan_path, completion_path):
    root = Path(study_root).resolve()
    plan_path, completion_path = Path(plan_path), Path(completion_path)
    plan = json.loads(plan_path.read_text())
    if Path(plan['study_root']).resolve() != root or plan['phase'] != 'development_gate' or \
            plan['cutoff_s'] != 600 or plan['seeds'] != [0] or set(plan['configurations']) != LABELS:
        raise ValueError('unfrozen gate phase, settings or controls')
    if plan['configurations']['candidate']['kind'] != 'policy' or \
            plan['configurations']['strong_static']['kind'] != 'fixed_action':
        raise ValueError('candidate/control roles changed')
    if plan['tool_identity'] != TOOLS:
        raise ValueError('gate does not use the fixed qualified tools')
    configs = {name: configuration(c) for name, c in plan['configurations'].items()}
    unique = {sha for _, sha in configs.values()}
    if len(unique) > 3:
        raise ValueError('gate physical configuration cap')
    identity = {'plan_sha256': common.sha(plan_path), 'completion_sha256': common.sha(completion_path),
                'decision_code_sha256': common.sha(Path(__file__)),
                'deployment_checker_sha256': common.sha(Path(deployment_consistency.__file__)),
                'common_sha256': common.sha(Path(common.__file__)), 'policy_sha256': common.sha(Path(policy.__file__))}
    directory = root / 'results/closed_gate_once'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.owner.lock').open('a+') as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('gate decision already has an active owner')
        claim = directory / 'claim.json'
        if claim.exists():
            if json.loads(claim.read_text()) != identity:
                raise ValueError('gate already consumed with another bound identity')
            binding = json.loads((directory / 'decision_binding.json').read_text())
            report = bound_json(directory / 'decision.json', binding['decision_sha256'])
            if report['identity'] != identity:
                raise ValueError('changed stored gate decision')
            for entry in json.loads(completion_path.read_text())['records']:
                unit = Path(entry['unit_path'])
                record = bound_json(unit / 'record.json', entry['record_sha256'])
                for name, sha in record['evidence_sha256'].items():
                    rel = PurePosixPath(name)
                    if rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.parts[0] != 'logs' or \
                            common.sha(unit / name) != sha:
                        raise ValueError('stored decision evidence changed')
            return {**report, 'reused_stored_decision': True}
        parents = frozen_parents(plan)
        selection = frozen_selection(plan)
        deployed = deployed_candidate(plan, configs['candidate'][0])
        for key, sha in TOOLS.items():
            if common.sha(Path(plan['tool_paths'][key])) != sha:
                raise ValueError('gate tool file changed')
        qualified = bound_json(plan['cpu_qualification_path'], plan['cpu_qualification_sha256'])
        if qualified['status'] != 'PASS' or qualified['wrapper_sha256'] != TOOLS['cpu_budget_executor_sha256'] or \
                qualified['solver_sha256'] != TOOLS['solver_sha256'] or qualified['checker_sha256'] != TOOLS['checker_sha256']:
            raise ValueError('actual CPU-timer qualification missing')
        done = json.loads(completion_path.read_text())
        if done['status'] != 'COMPLETE' or done['phase'] != 'development_gate' or \
                done['plan_sha256'] != identity['plan_sha256']:
            raise ValueError('incomplete or changed gate execution')
        expected = {(p['hash'], 0, c) for p in parents for c in unique}
        entries = done['records']
        keys = [(r['parent_hash'], r['seed'], r['configuration_sha256']) for r in entries]
        if len(keys) != len(set(keys)) or set(keys) != expected:
            raise ValueError('incomplete or duplicate physical gate matrix')
        by_key = dict(zip(keys, entries))
        costs = {}
        for label, (_, sha) in configs.items():
            values = []
            for parent in parents:
                receipt = by_key[parent['hash'], 0, sha]
                values.append(actual_cost(receipt['unit_path'], receipt['record_sha256'], parent,
                                          plan['configurations'][label], plan))
            costs[label] = values
        # No validity error above has exposed a gate comparison. Consume the
        # one permitted decision before computing or displaying its feedback.
        with claim.open('x') as f:
            json.dump(identity, f, sort_keys=True, indent=2)
        results = {label: compare(costs['candidate'], costs[label]) for label in ('strong_static', 'simple_control')}
        report = {'phase': 'development_gate', 'identity': identity, 'independent_parents': 16,
                  'unique_physical_configurations': len(unique), 'cutoff_s': 600,
                  'deployment_prerequisite': deployed, 'comparisons': results,
                  'frozen_development_selection': selection,
                  'confirmation_permitted': all(r['passes'] for r in results.values()),
                  'context_updates_written': 0,
                  'scope': 'One final gate decision only; no final-test conclusion and no tuning feedback.'}
        common.write(directory / 'decision.json', report)
        with (directory / 'decision_binding.json').open('x') as f:
            json.dump({'decision_sha256': common.sha(directory / 'decision.json')}, f)
        return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--study-root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--completion', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(consume(a.study_root, a.plan, a.completion)))


if __name__ == '__main__':
    main()
