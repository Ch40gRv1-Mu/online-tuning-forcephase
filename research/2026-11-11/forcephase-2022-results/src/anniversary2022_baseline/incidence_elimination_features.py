"""R49 full incidence graph fill; exact bounded operations, no CNF solving."""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
import ctypes
import hashlib
import json
from pathlib import Path
import platform
import resource
import shutil
import signal
import subprocess
import time

import numpy as np
import sklearn
from threadpoolctl import threadpool_limits

from .common import sha
from .measure_compact_prefetch import atomic
from .route_phase_2022 import load_formula
from .scc_quotient_features import normalize, parse
from .structural_clusters import DATA, ROOT, read_csv

SOURCE = Path(__file__).with_name('incidence_elimination.cpp')
RECEIPT_NAMES = ('eliminated_nodes', 'eliminated_variables', 'eliminated_clauses',
    'prefix_max_degree', 'fill_edges_added', 'pair_checks', 'residual_edges', 'residual_min_degree', 'stop_reason')


def build(out):
    wall = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    binary = out / 'native' / ('incidence_elimination.dylib' if platform.system() == 'Darwin' else 'incidence_elimination.so')
    binary.parent.mkdir()
    compiler = shutil.which('clang++') or shutil.which('g++')
    assert compiler and not binary.exists()
    command = [compiler, '-std=c++17', '-O3', '-DNDEBUG',
        *(['-dynamiclib'] if platform.system() == 'Darwin' else ['-shared', '-fPIC']), str(SOURCE), '-o', str(binary)]
    response = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (out / 'build.log').write_text(response.stdout + response.stderr)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    atomic(out / 'build_receipt.json', {'command': command, 'exit': response.returncode,
        'source_sha256': sha(SOURCE), 'binary_sha256': sha(binary) if binary.exists() else None,
        'child_CPU_s': after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
        'wall_s': time.monotonic() - wall, 'already_in_owner_total_do_not_charge_again': True})
    assert response.returncode == 0 and binary.exists(), 'Native compile failed; preserve build cost'
    return binary


def initialize_worker(binary):
    global _native, _thread_limit
    _thread_limit = threadpool_limits(limits=1)
    _native = ctypes.CDLL(str(binary))
    integer = np.ctypeslib.ndpointer(dtype=np.int32, flags='C_CONTIGUOUS')
    longint = np.ctypeslib.ndpointer(dtype=np.int64, flags='C_CONTIGUOUS')
    real = np.ctypeslib.ndpointer(dtype=np.float64, flags='C_CONTIGUOUS')
    _native.incidence_elimination.argtypes = [ctypes.c_int32] * 3 + [integer, integer, real, real, longint]
    _native.incidence_elimination.restype = ctypes.c_int
    _native.typed_simple_rewire.argtypes = [ctypes.c_int32] * 4 + [integer, integer, integer, longint]
    _native.typed_simple_rewire.restype = ctypes.c_int


def graph_profile(variable, clause, bias, nc):
    v, c = np.ascontiguousarray(variable, dtype=np.int32), np.ascontiguousarray(clause, dtype=np.int32)
    bias = np.ascontiguousarray(bias, dtype=np.float64)
    out, rec = np.zeros(44, np.float64), np.zeros(9, np.int64)
    code = _native.incidence_elimination(len(bias), nc, len(v), v, c, bias, out, rec)
    assert code == 0, f'Native graph error {code}'
    assert np.isfinite(out).all() and (out[:20] >= 0).all()
    assert rec[5] <= 500000 and rec[3] <= 128 and rec[4] <= min(1000000, 4 * len(v) + 1024)
    assert rec[0] == rec[1] + rec[2] and rec[6] >= 0
    assert (rec[0] == len(bias) + nc) == bool(out[10])
    assert bool(out[10]) or rec[8] in (1, 2, 3)
    assert np.isclose(out[20::3].sum(), out[1], rtol=0, atol=1e-12)
    return out, {k: int(v) for k, v in zip(RECEIPT_NAMES, rec)}


def rewire_simple(variable, clause, positive, widths):
    v, c = np.ascontiguousarray(variable, dtype=np.int32), np.ascontiguousarray(clause, dtype=np.int32)
    if not len(v):
        return v, {'attempted_swaps': 0, 'accepted_swaps': 0}
    pos = np.bincount(c, weights=positive, minlength=len(widths)).astype(np.int64)
    kind = (widths[c] * (widths.max(initial=0) + 1) + pos[c]) * 2 + ~positive
    _, kind = np.unique(kind, return_inverse=True)
    kind = np.ascontiguousarray(kind, dtype=np.int32)
    result, rec = v.copy(), np.zeros(2, np.int64)
    code = _native.typed_simple_rewire(int(v.max()) + 1, len(widths), len(v),
        int(kind.max()) + 1, result, c, kind, rec)
    assert code == 0, f'Native null error {code}'
    # Exact simple degrees, sign/type degrees and within-clause no repetitions.
    assert np.array_equal(np.bincount(v), np.bincount(result, minlength=int(v.max()) + 1))
    multiplier = int(kind.max()) + 1
    assert np.array_equal(np.sort(v.astype(np.int64) * multiplier + kind),
                          np.sort(result.astype(np.int64) * multiplier + kind))
    assert len(np.unique(result.astype(np.int64) * len(widths) + c)) == len(result)
    assert rec[0] == 2 * len(v) and 0 <= rec[1] <= rec[0]
    return result, {'attempted_swaps': int(rec[0]), 'accepted_swaps': int(rec[1])}


def semantic_checks(binary):
    initialize_worker(binary)
    a, ar = graph_profile(np.array([0, 1, 1, 2]), np.array([0, 0, 1, 1]), np.zeros(3), 2)
    b, br = graph_profile(np.array([0, 1, 0, 1]), np.array([0, 0, 1, 1]), np.zeros(2), 2)
    v, c = np.tile(np.arange(3), 3), np.repeat(np.arange(3), 3)
    p, pr = graph_profile(v, c, np.array([1., -.5, .25]), 3)
    q, _ = graph_profile(v, c, np.array([-1., .5, -.25]), 3)
    assert ar['prefix_max_degree'] == 1 and ar['fill_edges_added'] == 0 and a[10] == 1
    assert br['prefix_max_degree'] == 2 and br['fill_edges_added'] == 1 and b[10] == 1
    assert pr['prefix_max_degree'] == 3 and p[10] == 1
    signed = np.arange(21, 44, 3)
    assert np.allclose(p[signed], -q[signed], rtol=0, atol=1e-12)
    mask = np.ones(44, bool); mask[signed] = False
    assert np.array_equal(p[mask], q[mask])
    v, c, widths = np.array([0, 1, 1, 2, 0, 2]), np.repeat(np.arange(3), 2), np.full(3, 2)
    _, null = rewire_simple(v, c, np.ones(6, bool), widths)
    return {'graph_profile_calls': 4, 'native_null_calls': 1, 'path_width': 1, 'cycle_width': 2,
        'K33_width': 3, 'complement_covariance': True, 'simple_literal_type_degree_preserved': True,
        'fixture_null_swaps': null, 'SAT_calls': 0}


def extract(raw):
    tick = time.process_time()
    nodes, clauses, raw_m, _ = parse(raw)
    raw_length = len(nodes)
    nodes, clauses, widths, _ = normalize(nodes, clauses, raw_m)
    active = np.flatnonzero(widths)
    clause, widths = np.searchsorted(active, clauses), widths[active]
    _, variable = np.unique(nodes // 2, return_inverse=True)
    positive, nv = (nodes & 1) == 0, int(variable.max()) + 1 if len(variable) else 0
    degree = np.bincount(variable, minlength=nv)
    pos = np.bincount(variable, weights=positive, minlength=nv)
    bias = (2 * pos - degree) / np.maximum(degree, 1)
    parse_cpu = time.process_time() - tick
    tick = time.process_time()
    actual, a = graph_profile(variable, clause, bias, len(widths))
    actual_cpu = time.process_time() - tick
    tick = time.process_time()
    shuffled, swaps = rewire_simple(variable, clause, positive, widths)
    control, n = graph_profile(shuffled, clause, bias, len(widths))
    null_cpu = time.process_time() - tick
    distinct = bool(np.linalg.norm(actual - control) > 1e-6)
    covered = bool(min(actual[1], control[1]) >= .10)
    return actual, control, {'active_variables': nv, 'active_clauses': len(widths),
        'raw_occurrences': raw_length, 'normalized_occurrences': len(variable),
        'parse_CPU_s': parse_cpu, 'actual_profile_CPU_s': actual_cpu, 'null_profile_CPU_s': null_cpu,
        'actual_null_distinct': distinct, 'both_variable_elimination_coverage_at_least10pct': covered,
        'informative': bool(distinct and covered and swaps['accepted_swaps'] > 0),
        'actual': a, 'null': n, **swaps}


def collect_one(job):
    key, path, expected = job
    cpu, wall = time.process_time(), time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R49 input30wall')))
    signal.alarm(30)
    identity_cpu = 0.
    try:
        raw = load_formula(Path(path)); read_cpu = time.process_time() - cpu
        tick = time.process_time()
        assert hashlib.sha256(raw).hexdigest() == expected, 'R49 cached input SHA mismatch'
        identity_cpu = time.process_time() - tick
        actual, control, r = extract(raw)
        elapsed = time.process_time() - cpu
        if elapsed > 10: raise TimeoutError('R49 input10CPU')
        common = read_cpu + r['parse_CPU_s']
        r.update(instance_key=key, status='ok', raw_sha256=expected, raw_bytes=len(raw),
            physical_CPU_s=elapsed, identity_CPU_s=identity_cpu, read_CPU_s=read_cpu,
            wall_s=time.monotonic() - wall, joint_fee_CPU_s=common + r['actual_profile_CPU_s'],
            null_fee_CPU_s=common + r['null_profile_CPU_s'],
            max_RSS_platform_units=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return key, actual, control, r
    except Exception as error:
        elapsed = time.process_time() - cpu; fee = max(0, elapsed - identity_cpu)
        return key, np.zeros(44), np.zeros(44), {'instance_key': key, 'status': 'ERROR',
            'error': repr(error), 'raw_sha256': expected, 'physical_CPU_s': elapsed,
            'identity_CPU_s': identity_cpu, 'wall_s': time.monotonic() - wall,
            'joint_fee_CPU_s': fee, 'null_fee_CPU_s': fee, 'informative': False,
            'actual_null_distinct': False, 'both_variable_elimination_coverage_at_least10pct': False,
            'actual': None, 'null': None, 'attempted_swaps': 0, 'accepted_swaps': 0}
    finally:
        signal.alarm(0)


def collect(out):
    began = time.monotonic()
    assert (np.__version__, sklearn.__version__) == ('2.5.4', '1.9.1')
    binary = build(out)
    checks = semantic_checks(binary)
    reference = DATA / 'mechanism_R38_features_20261111/features.npz'
    with np.load(reference) as z:
        keys, base, eligible = z['keys'].tolist(), z['topology63'][:, :43].copy(), z['eligible'].copy()
    assert len(keys) == 4719 and eligible.sum() == 2325 and np.array_equal(base[:, 42], eligible)
    identity = {r['instance_key']: r['raw_sha256'] for r in map(json.loads,
        (DATA / 'cnf_graph_cnn_20261110/feature_receipts.jsonl').read_text().splitlines())}
    panel = ROOT / 'work/astra_structure_panel_20261110'
    fallback = {r['instance_key']: panel / 'cnf' / (r['case'] + '.cnf') for r in read_csv(panel / 'association_only.csv')}
    jobs = []
    for key, yes in zip(keys, eligible):
        if not yes: continue
        path = ROOT / 'work/signed_boundary_20261110/cnf_cache' / (key + '.cnf.gz')
        if not path.is_file(): path = fallback[key]
        assert path.is_file()
        jobs.append((key, str(path), identity[key]))
    index = {k: i for i, k in enumerate(keys)}
    actual, control = np.zeros((4719, 44)), np.zeros((4719, 44))
    okay, informative = ~eligible.copy(), np.zeros(4719, bool)
    fees = {k: np.zeros(4719) for k in ('topology', 'joint', 'decoupled')}
    records = out / 'feature_records'; records.mkdir()
    distinct = covered = errors = complete_actual = complete_null = attempts = accepted = 0
    with ProcessPoolExecutor(max_workers=4, initializer=initialize_worker, initargs=(binary,)) as pool:
        todo = iter(jobs); pending = deque(pool.submit(collect_one, next(todo)) for _ in range(4))
        completed = 0
        while pending:
            key, a, n, r = pending.popleft().result(timeout=max(1, 900 - (time.monotonic() - began)))
            i = index[key]; actual[i], control[i] = a, n
            okay[i], informative[i] = r['status'] == 'ok', r['informative']
            distinct += r['actual_null_distinct']; covered += r['both_variable_elimination_coverage_at_least10pct']
            errors += r['status'] != 'ok'; attempts += r['attempted_swaps']; accepted += r['accepted_swaps']
            complete_actual += bool(a[10]) if r['status'] == 'ok' else False
            complete_null += bool(n[10]) if r['status'] == 'ok' else False
            for k, f in [('topology', 'joint_fee_CPU_s'), ('joint', 'joint_fee_CPU_s'), ('decoupled', 'null_fee_CPU_s')]:
                fees[k][i] = r[f]
            atomic(records / (key + '.json'), {'receipt': r, 'joint44': a.tolist(), 'decoupled44': n.tolist()})
            completed += 1
            if completed % 200 == 0:
                atomic(out / 'progress.json', {'stage': 'collection', 'completed': completed, 'expected': 2325,
                    'informative': int(informative.sum()), 'wall_s': time.monotonic() - began})
                print(f'R49 collected {completed}/2325 incidence-fill profiles', flush=True)
            if time.monotonic() - began > 900: raise TimeoutError('R49 collection15wallmin')
            job = next(todo, None)
            if job is not None: pending.append(pool.submit(collect_one, job))
    arrays = {'topology': np.c_[base, actual[:, :20], np.zeros((4719, 24))],
              'joint': np.c_[base, actual], 'decoupled': np.c_[base, control]}
    assert all(a.shape == (4719, 87) for a in arrays.values())
    np.savez_compressed(out / 'features.npz', keys=np.array(keys), eligible=eligible, valid=okay,
        informative=informative, **arrays, **{k + '_fee': v for k, v in fees.items()})
    atomic(out / 'collection.json', {'parents': 4719, 'attempted': completed, 'successful': int(okay[eligible].sum()),
        'failed': errors, 'actual_null_distinct': distinct, 'both_variable_coverage_at_least10pct': covered,
        'informative': int(informative.sum()), 'complete_actual_orders': complete_actual, 'complete_null_orders': complete_null,
        'attempted_swaps': attempts, 'accepted_swaps': accepted,
        'actual_profile_native_calls': 2 * (completed - errors), 'failed_native_work_unknown': errors,
        'actual_null_native_calls': completed - errors, 'wall_s': time.monotonic() - began,
        'semantic_checks': checks, 'source_sha256': sha(__file__), 'native_source_sha256': sha(SOURCE),
        'native_binary_sha256': sha(binary), 'reference_sha256': sha(reference),
        'features_sha256': sha(out / 'features.npz'), 'new_solver_calls': 0,
        'library_versions': {'numpy': np.__version__, 'sklearn': sklearn.__version__}})
    return keys, eligible, okay, informative, arrays, fees
