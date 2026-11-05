"""One-owner extraction of new signed-choice features, fit only, no SAT calls."""
import argparse
import csv
import json
import os
import queue
import resource
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import run_pilot as common


def cpu():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.process_time()+r.ru_utime+r.ru_stime


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--cohort', type=Path, required=True)
    p.add_argument('--cohort-sha256', required=True)
    a = p.parse_args()
    if common.sha(a.cohort) != a.cohort_sha256:
        raise ValueError('changed frozen fit cohort')
    with a.cohort.open() as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 144 or len({r['hash'] for r in rows}) != 144 or any(r['role'] != 'development_fit' for r in rows):
        raise ValueError('not the fixed fit-only144')
    stage = a.base/'phases/choice_fit144_v1'
    for name in ('results', 'logs', 'metadata'):
        (stage/name).mkdir(parents=True, exist_ok=True)
    (stage/'metadata/cohort.csv').write_bytes(a.cohort.read_bytes())
    started, wall = cpu(), time.monotonic()
    binary = a.base/'bin/cnf_choice_v1'
    source = Path(__file__).with_name('cnf_choice.cpp')
    if binary.exists():
        raise ValueError('refuse rebuilding an existing extractor')
    subprocess.run(['g++', '-O3', '-std=c++17', str(source), '-o', str(binary)], check=True)
    identity = {'binary_sha256': common.sha(binary), 'source_sha256': common.sha(source),
                'runner_sha256': common.sha(Path(__file__)), 'cohort_sha256': a.cohort_sha256,
                'common_sha256': common.sha(Path(common.__file__))}
    common.write(stage/'results/identity.json', identity)
    # Complete pairwise exclusion and literal-sign invariance properties.
    complete = [[1,2,3],[-1,-2],[-1,-3],[-2,-3]]
    cases = [('complete', complete), ('incomplete', complete[:-1]),
             ('renamed', [[(1 if v>0 else -1)*{1:3,2:1,3:2}[abs(v)] for v in c] for c in complete]),
             ('flipped', [[-v for v in c] for c in complete])]
    tests = {}
    for name, clauses in cases:
        path = stage/'metadata'/(name+'.cnf')
        path.write_text('p cnf 3 '+str(len(clauses))+'\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
        tests[name] = json.loads(subprocess.check_output([binary, path], text=True))['features']
    if tests['complete']['e_block_variable_fraction'] != 1 or tests['incomplete']['e_block_variable_fraction'] != 0:
        raise ValueError('complete exclusion block recognition failed')
    if tests['complete'] != tests['renamed']:
        raise ValueError('renaming invariance failed')
    if tests['complete']['e_positive_block_literal_fraction'] != 1 or tests['flipped']['e_positive_block_literal_fraction'] != 0:
        raise ValueError('global-sign choice orientation reversal failed')
    for name in tests['complete']:
        if name != 'e_positive_block_literal_fraction' and tests['complete'][name] != tests['flipped'][name]:
            raise ValueError('unsigned choice geometry changed under sign reversal')
    common.write(stage/'metadata/definition_checks.json', {'status': 'PASS', 'vectors': tests})
    cpus = queue.Queue()
    for c in sorted(os.sched_getaffinity(0))[:8]:
        cpus.put(c)
    lock, records = threading.Lock(), {}
    def one(row):
        core = cpus.get()
        path = a.base/'data'/(row['hash']+'.cnf')
        record = {'hash': row['hash'], 'role': row['role'], 'identity': identity}
        try:
            if cpu()-started > 3600:
                raise RuntimeError('stage CPU envelope reached')
            if common.sha(path) != row['sha256']:
                raise ValueError('changed cached public input')
            record['input_sha256'] = row['sha256']
            measured, text = common.child([binary, path], stage/'logs'/(row['hash']+'.log'), 10, core, memory=1536*1024**2)
            record['child'] = measured
            if measured['exit_code'] != 0:
                raise RuntimeError('extractor exit '+str(measured['exit_code']))
            observed = json.loads(text)
            record.update(status='VALID', features=observed['features'], feature_cpu_s=measured['cpu_s'], input_statistics={k: v for k, v in observed.items() if k != 'features'})
        except Exception as e:
            record.update(status='FEATURE_ERROR', error=type(e).__name__+': '+str(e))
        finally:
            cpus.put(core)
        with lock:
            common.write(stage/'results'/(row['hash']+'.json'), record)
            records[row['hash']] = record
            progress = {'completed': len(records), 'scheduled': 144, 'valid': sum(r['status'] == 'VALID' for r in records.values()),
                        'process_and_waited_children_cpu_s': cpu()-started, 'wall_s': time.monotonic()-wall}
            common.write(stage/'results/progress.json', progress)
            print(json.dumps(progress), flush=True)
    with ThreadPoolExecutor(8) as pool:
        for result in as_completed([pool.submit(one, r) for r in rows]):
            result.result()
    completion = {'status': 'COMPLETE_WITH_COVERAGE', 'parents': 144,
                  'valid': sum(r['status'] == 'VALID' for r in records.values()),
                  'failed': [h for h, r in records.items() if r['status'] != 'VALID'],
                  'identity': identity, 'new_solver_calls': 0,
                  'process_and_waited_children_cpu_s': cpu()-started, 'wall_s': time.monotonic()-wall}
    common.write(stage/'results/completion.json', completion)
    print(json.dumps(completion), flush=True)


if __name__ == '__main__':
    main()
