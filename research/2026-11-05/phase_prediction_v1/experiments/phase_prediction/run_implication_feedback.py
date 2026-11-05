"""Reuse the fixed new binary parser on48feedback parents, without solving."""
import argparse
import csv
import json
import os
import queue
import resource
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
    p.add_argument('--spec', type=Path, required=True)
    p.add_argument('--cohort', type=Path, required=True)
    a = p.parse_args()
    spec = json.loads(a.spec.read_text())
    if common.sha(a.cohort) != spec['cohort_sha256']:
        raise ValueError('changed frozen cohort')
    with a.cohort.open() as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 48 or len({r['hash'] for r in rows}) != 48 or any(r['role'] != 'development_feedback' for r in rows):
        raise ValueError('not fixed48 feedback')
    binary = a.base/'bin/cnf_implication_v1'
    if common.sha(binary) != spec['binary_sha256']:
        raise ValueError('changed extractor')
    stage = a.base/'phases/implication_feedback48_v1'
    for name in ('results', 'logs', 'metadata'):
        (stage/name).mkdir(parents=True, exist_ok=True)
    (stage/'metadata/cohort.csv').write_bytes(a.cohort.read_bytes())
    (stage/'metadata/spec.json').write_bytes(a.spec.read_bytes())
    identity = {**spec, 'runner_sha256': common.sha(Path(__file__)), 'spec_sha256': common.sha(a.spec)}
    common.write(stage/'results/identity.json', identity)
    start, wall = cpu(), time.monotonic()
    cores = queue.Queue()
    for c in sorted(os.sched_getaffinity(0))[:8]:
        cores.put(c)
    records, lock = {}, threading.Lock()
    def one(row):
        core = cores.get()
        record = {'hash': row['hash'], 'role': row['role'], 'identity': identity}
        try:
            if cpu()-start > 900:
                raise RuntimeError('association extraction envelope reached')
            path = a.base/'data'/(row['hash']+'.cnf')
            if common.sha(path) != row['sha256']:
                raise ValueError('changed input')
            record['input_sha256'] = row['sha256']
            child, text = common.child([binary, path], stage/'logs'/(row['hash']+'.log'), 10, core, memory=1536*1024**2)
            record['child'] = child
            if child['exit_code'] != 0:
                raise RuntimeError('feature error '+str(child['exit_code']))
            record.update(status='VALID', features=json.loads(text)['features'], feature_cpu_s=child['cpu_s'])
        except Exception as e:
            record.update(status='FEATURE_ERROR', error=type(e).__name__+': '+str(e))
        finally:
            cores.put(core)
        with lock:
            records[row['hash']] = record
            common.write(stage/'results'/(row['hash']+'.json'), record)
            common.write(stage/'results/progress.json', {'completed': len(records), 'scheduled': 48})
    with ThreadPoolExecutor(8) as pool:
        for result in as_completed([pool.submit(one, row) for row in rows]):
            result.result()
    completion = {'status': 'COMPLETE_WITH_COVERAGE', 'parents': 48, 'valid': sum(r['status'] == 'VALID' for r in records.values()),
                  'failed': [h for h, r in records.items() if r['status'] != 'VALID'], 'identity': identity,
                  'process_and_waited_children_cpu_s': cpu()-start, 'wall_s': time.monotonic()-wall, 'new_solver_calls': 0}
    common.write(stage/'results/completion.json', completion)
    print(json.dumps(completion))


if __name__ == '__main__':
    main()
