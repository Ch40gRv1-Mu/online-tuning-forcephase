"""Frozen eight-unit T60 deployment, one owner and per-unit completion receipts."""
import argparse
import csv
import fcntl
import io
import json
import os
import re
import resource
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import deploy_static60 as deploy_static
import deployment_consistency
import policy
import run_pilot as common


def selected_parents(parents):
    if len(parents) != 40 or len({r['hash'] for r in parents}) != 40:
        raise ValueError('complete frozen forty-parent source required')
    if any(r['role'] not in ('development_fit', 'development_feedback') or not re.fullmatch('[0-9a-f]{32}', r['hash']) for r in parents):
        raise ValueError('protected role or invalid association key')
    fit = [r for r in parents if r['role'] == 'development_fit']
    fb = [r for r in parents if r['role'] == 'development_feedback']
    if len(fit) != 24 or len(fb) != 16:
        raise ValueError('wrong frozen split')
    return fit[:4]+fb[:4]


def physical():
    c = resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.process_time()+c.ru_utime+c.ru_stime


def run_batch(spec_path, parents_path, policy_path, root):
    began = physical()
    spec_path, parents_path, policy_path, root = map(Path, (spec_path, parents_path, policy_path, root))
    spec = json.loads(spec_path.read_text())
    parents = json.loads(parents_path.read_text())
    tree = json.loads(policy_path.read_text())
    chosen = selected_parents(parents)
    if common.sha(parents_path) != spec['parent_manifest_sha256'] or [r['hash'] for r in chosen] != spec['selected_parent_hashes']:
        raise ValueError('changed frozen parent order')
    if policy.validate(tree) != spec['policy_sha256'] or spec['seed'] != 0 or spec['total_cpu_budget_s'] != 60:
        raise ValueError('changed policy or budget')
    if spec['memory_bytes'] != 1536*1024**2 or spec['proof_file_limit_bytes'] != 1024**3 or len(set(spec['cpus'])) != 8:
        raise ValueError('unfrozen resource profile')
    if not spec['cpu_budget_executor']:
        raise ValueError('qualified fractional CPU executor required')
    for kind in ('completion', 'integrity'):
        path = Path(spec['source_'+kind+'_path'])
        data = json.loads(path.read_text())
        if common.sha(path) != spec['source_'+kind+'_sha256'] or data['parents'] != 40 or data['runs'] != 320:
            raise ValueError('changed or incomplete source matrix')
        if (kind == 'completion' and data['status'] != 'COMPLETE') or (kind == 'integrity' and not data['complete_and_valid']):
            raise ValueError('source matrix is not valid')
    if spec['max_new_physical_cpu_hours']*3600 < 8*(60+30+120):
        raise ValueError('insufficient fixed-unit expense envelope')
    identity = {'spec_sha256': common.sha(spec_path), 'parents_sha256': common.sha(parents_path),
                'policy_file_sha256': common.sha(policy_path), 'unit_identity': deploy_static.execution_identity(spec),
                'batch_runner_sha256': common.sha(Path(__file__)),
                'consistency_checker_sha256': common.sha(Path(deployment_consistency.__file__))}
    root.mkdir(parents=True, exist_ok=True)
    with (root/'.owner.lock').open('a+') as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('deployment already has an active owner')
        for name in ('metadata', 'results', 'results/units'):
            (root/name).mkdir(exist_ok=True)
        prior = root/'results/identity.json'
        if prior.exists() and json.loads(prior.read_text()) != identity:
            raise ValueError('changed deployment identity')
        if not prior.exists():
            common.write(prior, identity)
        units = [root/'results/units'/f"{i:02d}_{r['hash']}" for i, r in enumerate(chosen)]
        for unit in units:
            if unit.exists() and not (unit/'record.json').exists():
                raise RuntimeError('incomplete unit preserved; inspect original owner, no duplicate execution')
        for name, data in (('spec', spec), ('policy', tree), ('parents', chosen)):
            path = root/'metadata'/(name+'.json')
            if path.exists() and json.loads(path.read_text()) != data:
                raise ValueError('changed frozen metadata')
            if not path.exists():
                common.write(path, data)
        owner.seek(0)
        owner.truncate()
        owner.write(json.dumps({'pid': os.getpid(), 'identity': identity}))
        owner.flush()
        lock = threading.Lock()
        receipts = {}
        def one(index):
            unit, parent = units[index], chosen[index]
            reused = (unit/'record.json').exists()
            if not reused:
                if physical()-began+210 > spec['max_new_physical_cpu_hours']*3600:
                    raise RuntimeError('physical CPU envelope reached')
                deploy_static.run_one({**spec, 'cpu': spec['cpus'][index]}, parent, tree, unit)
            r = json.loads((unit/'record.json').read_text())
            if r['identity'] != identity['unit_identity'] or r['input_sha256'] != parent['sha256'] or r['role'] != parent['role']:
                raise ValueError('unit identity/parent mismatch')
            checked = deployment_consistency.check(unit)
            binding = {'parent_hash': parent['hash'], 'record_sha256': common.sha(unit/'record.json'),
                       'spec_sha256': identity['spec_sha256'], 'policy_sha256': spec['policy_sha256']}
            bound = unit/'batch_binding.json'
            if bound.exists() and json.loads(bound.read_text()) != binding:
                raise ValueError('changed completed-unit binding')
            if not bound.exists():
                common.write(bound, binding)
            receipt = {**binding, 'role': parent['role'], 'consistency': checked, 'reused_this_launch': reused}
            with lock:
                receipts[index] = receipt
                common.write(root/'results/progress.json', {'completed': len(receipts), 'scheduled': 8,
                             'physical_this_launch_cpu_s': physical()-began, 'stopped': False})
            return receipt
        completed = root/'results/completion.json'
        if completed.exists():
            old = json.loads(completed.read_text())
            if old['status'] != 'COMPLETE' or old['identity'] != identity:
                raise ValueError('changed completion')
            if any(not (unit/'record.json').exists() for unit in units):
                raise ValueError('completed unit missing; refuse new execution')
            for i in range(8):
                one(i)
            return {**old, 'reused_existing_completed_stage': True}
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(one, i) for i in range(8)]
                for future in as_completed(futures):
                    future.result()
            result = {'status': 'COMPLETE', 'parents': 8, 'runs': 8, 'identity': identity,
                      'receipts': [receipts[i] for i in range(8)],
                      'physical_this_launch_cpu_s': physical()-began,
                      'accounting': 'Process and waited children; final outer GNU-time is physical billing.'}
            common.write(completed, result)
            return result
        except BaseException as error:
            common.write(root/'results'/f'failure_{time.time_ns()}.json',
                         {'status': 'STOPPED_ERROR', 'error': type(error).__name__+': '+str(error),
                          'completed': len(receipts), 'physical_this_launch_cpu_s': physical()-began,
                          'identity': identity, 'note': 'Do not relabel failure as timeout or re-run healthy units.'})
            raise


def main():
    p = argparse.ArgumentParser()
    for name in ('spec', 'parents', 'policy', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(run_batch(a.spec, a.parents, a.policy, a.out)))


if __name__ == '__main__':
    main()
