"""R51 exact existing gate-CC helpers; current three-action static features only."""
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import tempfile
import time

import numpy as np
import sklearn
from threadpoolctl import threadpool_limits

from .common import sha
from .measure_compact_prefetch import atomic
from .route_phase_2022 import load_formula
from .structural_clusters import DATA, ROOT, read_csv

SOURCE = Path(__file__).with_name('gate_cost_transfer.cpp')
HEADERS = [ROOT / 'src/ta100' / n for n in ('cnf_data.hpp', 'graph_features.hpp', 'graph_extra_features.hpp')]


def initialize_worker():
    global _thread_limit
    _thread_limit = threadpool_limits(limits=1)


def conditional_reassociate(x, seed):
    """Null within exactly one train/inner/held partition; never cross it."""
    tick = time.process_time()
    x = x.copy()
    selected = (x[:, 42] > 0) & (x[:, 46] > 0)
    strata = np.c_[np.floor(x[:, :2] / np.log(4)).astype(int), np.floor(x[:, 46] * 4).astype(int)]
    _, group = np.unique(strata, axis=0, return_inverse=True)
    permutation = np.arange(len(x))
    rng = np.random.default_rng(seed)
    for g in np.unique(group[selected]):
        ids = np.flatnonzero(selected & (group == g))
        permutation[ids] = rng.permutation(ids)
    before = x[:, 51:].copy()
    x[:, 51:] = before[permutation]
    return x, {'seed': seed, 'selected_parents': int(selected.sum()),
        'changed_vectors': int((np.linalg.norm(x[:, 51:] - before, axis=1) > 1e-6).sum()),
        'CPU_s': time.process_time() - tick, 'no_sources_outside_partition': True}


def build(out):
    before = resource.getrusage(resource.RUSAGE_CHILDREN); wall = time.monotonic()
    binary = out / 'native_gate_cost'
    command = [shutil.which('clang++') or shutil.which('g++'), '-std=c++17', '-O3', '-DNDEBUG', str(SOURCE), '-o', str(binary)]
    response = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (out / 'build.log').write_text(response.stdout + response.stderr)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    atomic(out / 'build_receipt.json', {'command': command, 'exit': response.returncode,
        'source_sha256': sha(SOURCE), 'header_hashes': {str(p.relative_to(ROOT)): sha(p) for p in HEADERS},
        'binary_sha256': sha(binary) if binary.exists() else None,
        'child_CPU_s': after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
        'wall_s': time.monotonic() - wall, 'already_in_owner_total': True})
    assert response.returncode == 0 and binary.exists(), 'R51 native build failed'
    return binary


def native_call(raw, binary, scratch):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    wall = time.monotonic()
    native = {'CPU_s': None, 'exit': None}
    result, error = None, None
    try:
        with tempfile.TemporaryDirectory(dir=scratch) as name:
            path = Path(name) / 'input.cnf'; path.write_bytes(raw)
            response = subprocess.run([str(binary), str(path)], capture_output=True, text=True, timeout=8)
            native.update(exit=response.returncode, stderr=response.stderr[-4000:])
            if response.returncode:
                raise RuntimeError(f'R51 native exit{response.returncode}: {response.stderr[-1000:]}')
            result = json.loads(response.stdout)
            assert result['schema'] == 'forcephase.gate_cost.R51.v1'
            assert result['SAT_calls'] == result['assignments_constructed'] == 0
            for k, n in [('shared8', 8), ('full16', 16), ('local16', 16)]:
                assert np.asarray(result[k]).shape == (n,) and np.isfinite(result[k]).all()
    except Exception as e:
        error = repr(e)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    native.update(CPU_s=after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
        wall_s=time.monotonic() - wall, error=error,
        cumulative_children_max_RSS_platform_units=after.ru_maxrss)
    return result, native


def semantic_checks(binary, scratch):
    gate = b'p cnf 3 3\n-3 1 0\n-3 2 0\n3 -1 -2 0\n'
    chain = b'p cnf 5 6\n-3 1 0\n-3 2 0\n3 -1 -2 0\n-5 3 0\n-5 4 0\n5 -3 -4 0\n'
    opposite = b'p cnf 5 6\n3 -1 0\n3 -2 0\n-3 1 2 0\n5 -3 0\n5 -4 0\n-5 3 4 0\n'
    results, resources = [], []
    for raw in (gate, chain, opposite):
        row, rec = native_call(raw, binary, scratch)
        assert rec['error'] is None, rec
        results.append(row); resources.append(rec)
    g, p, q = results
    assert g['evaluable_outputs'] == 1 and np.isclose(g['full16'][0], .2, rtol=0, atol=1e-12)
    assert np.allclose(g['full16'], g['local16'], rtol=0, atol=1e-12)
    assert p['evaluable_outputs'] == 2 and np.isclose(p['full16'][0], (.2 + 3 / 7) / 2, rtol=0, atol=1e-12)
    assert np.isclose(p['local16'][0], .2, rtol=0, atol=1e-12)
    signed = [0, 5, 11, 15]
    assert np.allclose(np.array(p['full16'])[signed], -np.array(q['full16'])[signed], rtol=0, atol=1e-12)
    assert p['full16'][13] == q['full16'][14] and p['full16'][14] == q['full16'][13]
    invariant = [i for i in range(16) if i not in (*signed, 13, 14)]
    assert np.allclose(np.array(p['full16'])[invariant], np.array(q['full16'])[invariant], rtol=0, atol=1e-12)
    return {'native_calls': 3, 'single_AND_contrast': .2, 'two_layer_contrast': p['full16'][0],
        'whole_vs_local_differ': True, 'complement_covariance': True, 'resources': resources, 'SAT_calls': 0}


def collect_one(job):
    key, path, expected, binary, scratch = job
    cpu, wall = time.process_time(), time.monotonic()
    identity_cpu, child_cpu = 0., 0.
    native = None
    try:
        raw = load_formula(Path(path)); read_cpu = time.process_time() - cpu
        tick = time.process_time()
        assert hashlib.sha256(raw).hexdigest() == expected, 'R51 cached input SHA mismatch'
        identity_cpu = time.process_time() - tick
        row, native = native_call(raw, binary, scratch); child_cpu = native['CPU_s']
        assert native['error'] is None, native
        shared, full, local = [np.asarray(row[k], float) for k in ('shared8', 'full16', 'local16')]
        elapsed = time.process_time() - cpu + child_cpu
        if elapsed > 10 or time.monotonic() - wall > 30: raise TimeoutError('R51 parent input budget')
        r = {'instance_key': key, 'status': 'ok', 'raw_sha256': expected, 'raw_bytes': len(raw),
            'physical_CPU_s': elapsed, 'parent_CPU_s': elapsed - child_cpu, 'native_CPU_s': child_cpu,
            'identity_CPU_s': identity_cpu, 'read_CPU_s': read_cpu, 'wall_s': time.monotonic() - wall,
            'shared_fee_CPU_s': max(0, elapsed - identity_cpu),
            'evaluable_outputs': row['evaluable_outputs'], 'gate_variables': row['gate_variables'],
            'ambiguous_gate_variables': row['ambiguous_gate_variables'],
            'whole_local_different': bool(np.linalg.norm(full - local) > 1e-6), 'native': native}
        return key, shared, full, local, r
    except Exception as e:
        elapsed = time.process_time() - cpu + child_cpu
        return key, np.zeros(8), np.zeros(16), np.zeros(16), {'instance_key': key, 'status': 'ERROR',
            'raw_sha256': expected, 'error': repr(e), 'physical_CPU_s': elapsed,
            'identity_CPU_s': identity_cpu, 'shared_fee_CPU_s': max(0, elapsed - identity_cpu),
            'wall_s': time.monotonic() - wall, 'evaluable_outputs': 0, 'gate_variables': 0,
            'whole_local_different': False, 'native': native}


def collect(out):
    began = time.monotonic()
    assert (np.__version__, sklearn.__version__) == ('2.5.4', '1.9.1')
    binary = build(out)
    scratch = out / 'scratch'; scratch.mkdir()
    checks = semantic_checks(binary, scratch)
    reference = DATA / 'mechanism_R38_features_20261111/features.npz'
    with np.load(reference) as z:
        keys, base, eligible = z['keys'].tolist(), z['topology63'][:, :43].copy(), z['eligible'].copy()
    assert len(keys) == 4719 and eligible.sum() == 2325 and np.array_equal(base[:, 42], eligible)
    identities = {r['instance_key']: r['raw_sha256'] for r in map(json.loads,
        (DATA / 'cnf_graph_cnn_20261110/feature_receipts.jsonl').read_text().splitlines())}
    panel = ROOT / 'work/astra_structure_panel_20261110'
    fallback = {r['instance_key']: panel / 'cnf' / (r['case'] + '.cnf') for r in read_csv(panel / 'association_only.csv')}
    jobs = []
    for key, yes in zip(keys, eligible):
        if not yes: continue
        path = ROOT / 'work/signed_boundary_20261110/cnf_cache' / (key + '.cnf.gz')
        if not path.is_file(): path = fallback[key]
        assert path.is_file()
        jobs.append((key, str(path), identities[key], binary, scratch))
    index = {k: i for i, k in enumerate(keys)}
    shared, full, local = np.zeros((4719, 8)), np.zeros((4719, 16)), np.zeros((4719, 16))
    okay, fee, count = ~eligible.copy(), np.zeros(4719), np.zeros(4719, int)
    different = np.zeros(4719, bool)
    records = out / 'feature_records'; records.mkdir()
    completed = errors = 0
    with ProcessPoolExecutor(max_workers=4, initializer=initialize_worker) as pool:
        todo = iter(jobs); pending = {pool.submit(collect_one, next(todo)) for _ in range(4)}
        while pending:
            done, pending = wait(pending, timeout=max(1, 900 - (time.monotonic() - began)), return_when=FIRST_COMPLETED)
            if not done: raise TimeoutError('R51 collection15wallmin')
            for future in done:
                key, c, a, l, r = future.result(); i = index[key]
                shared[i], full[i], local[i] = c, a, l
                okay[i], fee[i], count[i] = r['status'] == 'ok', r['shared_fee_CPU_s'], r['evaluable_outputs']
                different[i] = r['whole_local_different']; errors += r['status'] != 'ok'; completed += 1
                atomic(records / (key + '.json'), {'receipt': r, 'shared8': c.tolist(), 'full16': a.tolist(), 'local16': l.tolist()})
                if completed % 200 == 0:
                    atomic(out / 'progress.json', {'stage': 'collection', 'completed': completed, 'expected': 2325,
                        'whole_local_different': int(different.sum()), 'wall_s': time.monotonic() - began})
                    print(f'R51 collected {completed}/2325 gate-cost features', flush=True)
                job = next(todo, None)
                if job is not None: pending.add(pool.submit(collect_one, job))
    informative = eligible & okay & (count >= 2) & different
    # The null template is reassociated independently inside each outer
    # train/inner/held partition by the scorer, never across parents in folds.
    arrays = {'joint': np.c_[base, shared, full], 'local': np.c_[base, shared, local],
              'decoupled': np.c_[base, shared, full]}
    assert all(a.shape == (4719, 67) for a in arrays.values())
    fees = {k: fee.copy() for k in arrays}
    np.savez_compressed(out / 'features.npz', keys=np.array(keys), eligible=eligible, valid=okay,
        informative=informative, **arrays, **{k + '_fee': v for k, v in fees.items()})
    atomic(out / 'collection.json', {'parents': 4719, 'attempted': completed, 'successful': int(okay[eligible].sum()),
        'failed': errors, 'evaluable_gate_parents': int((count > 0).sum()), 'whole_local_different': int(different.sum()),
        'informative': int(informative.sum()),
        'null_construction': 'Template only here; scorer reassigns independently inside train/inner/held. Physical arithmetic in scorer ledger, query0 optimistic, not deployable null.',
        'native_profile_calls': completed, 'semantic_checks': checks, 'wall_s': time.monotonic() - began,
        'source_sha256': sha(__file__), 'native_source_sha256': sha(SOURCE), 'binary_sha256': sha(binary),
        'header_hashes': {str(p.relative_to(ROOT)): sha(p) for p in HEADERS}, 'reference_sha256': sha(reference),
        'features_sha256': sha(out / 'features.npz'), 'new_solver_calls': 0, 'SAT_UNSAT_auxiliary': False})
    scratch.rmdir()
    return keys, eligible, okay, informative, arrays, fees
