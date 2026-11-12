"""R47 maximal matching covers of polarity cooccurrence obstructions."""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import signal
import time

import numpy as np
import sklearn
from threadpoolctl import threadpool_limits

from .common import sha
from .literal_color_features import rewire
from .measure_compact_prefetch import atomic
from .route_phase_2022 import load_formula
from .scc_quotient_features import normalize, parse
from .structural_clusters import DATA, ROOT, read_csv

SEEDS = (202611470, 202611471, 202611472)


def initialize_worker():
    global _worker_thread_limiter
    _worker_thread_limiter = threadpool_limits(limits=1)


def hyperedges(variable, positive, widths):
    start = np.r_[0, widths.cumsum()]
    edges = [[], []]
    for i in range(len(widths)):
        a, b = start[i:i + 2]
        v, p = variable[a:b], positive[a:b]
        for k, selected in enumerate((v[p], v[~p])):
            edge = sorted(set(selected.tolist())) if len(selected) >= 2 else []
            edges[k].append(edge if len(edge) >= 2 else [])
    return edges


def cover_once(edges, order, n):
    covered = np.zeros(n, bool)
    pairs = 0
    for i in order:
        pending = -1
        for v in edges[i]:
            if covered[v]:
                continue
            if pending < 0:
                pending = v
            else:
                covered[pending] = covered[v] = True
                pairs += 1
                pending = -1
    assert int(covered.sum()) == 2 * pairs
    assert all(sum(not covered[v] for v in edge) <= 1 for edge in edges)
    return covered, pairs


def pair_profile(variable, clause, positive, widths, n, edges, order):
    length, degree = len(variable), np.bincount(variable, minlength=n)
    results, covers = [], []
    for edge in edges:
        covered, pairs = cover_once(edge, order, n)
        covers.append(covered)
        removed = covered[variable]
        residual = np.bincount(clause[~removed], minlength=len(widths))
        touched = np.bincount(clause[removed], minlength=len(widths)) > 0
        results.extend([pairs / max(n, 1), degree[covered].sum() / max(length, 1),
            positive[removed].sum() / max(int(removed.sum()), 1),
            float(np.mean(residual == 1)) if len(widths) else 0,
            np.dot(residual.astype(float), residual) / max(float(np.dot(widths.astype(float), widths)), 1),
            float(touched.mean()) if len(widths) else 0])
    intersection = covers[0] & covers[1]
    results.extend([intersection.sum() / max(n, 1), degree[intersection].sum() / max(length, 1)])
    result = np.array(results)
    assert result.shape == (14,) and np.isfinite(result).all()
    return result


def full_profile(variable, clause, positive, widths, n):
    edges = hyperedges(variable, positive, widths)
    rows = np.array([pair_profile(variable, clause, positive, widths, n, edges,
        np.random.default_rng(seed).permutation(len(widths))) for seed in SEEDS])
    return np.r_[rows.mean(axis=0), rows.std(axis=0), rows.max(axis=0)]


def semantic_checks():
    variable, clause = np.array([0, 1, 1, 2, 0, 2]), np.repeat(np.arange(3), 2)
    widths = np.array([2, 2, 2])
    positive = np.ones(6, bool)
    e, inverse = hyperedges(variable, positive, widths), hyperedges(variable, ~positive, widths)
    rows = []
    for seed in SEEDS:
        order = np.random.default_rng(seed).permutation(3)
        p = pair_profile(variable, clause, positive, widths, 3, e, order)
        q = pair_profile(variable, clause, ~positive, widths, 3, inverse, order)
        assert np.isclose(p[0], 1 / 3) and np.isclose(p[3], 2 / 3) and np.isclose(p[4], 1 / 6)
        assert p[6] == 0 and np.allclose(p[[0, 1, 3, 4, 5]], q[[6, 7, 9, 10, 11]])
        assert p[2] == 1 and q[8] == 0 and np.allclose(p[12:], q[12:])
        rows.append({'seed': seed, 'triangle_matching_lower_fraction': float(p[0]),
                     'triangle_cover_upper_fraction': float(2 * p[0]), 'complement_direction_mapping': True})
    v, c, w = np.array([0, 1]), np.array([0, 0]), np.array([2])
    p = pair_profile(v, c, np.ones(2, bool), w, 2, hyperedges(v, np.ones(2, bool), w), np.array([0]))
    assert p[0] == .5 and p[1] == 1 and p[4] == 0
    return {'fixtures': rows, 'single_edge_matching': 1, 'matching_passes': 14, 'CNF_solver_calls': 0,
            'deletion_is_not_original_formula_conditioning': True}


def extract(raw, nmax):
    tick = time.process_time()
    nodes, clauses, raw_m, _ = parse(raw)
    raw_length = len(nodes)
    nodes, clauses, widths, _ = normalize(nodes, clauses, raw_m)
    active = np.flatnonzero(widths)
    clause, widths = np.searchsorted(active, clauses), widths[active]
    _, variable = np.unique(nodes // 2, return_inverse=True)
    positive = (nodes & 1) == 0
    n, length = int(variable.max()) + 1 if len(variable) else 0, len(variable)
    parse_cpu = time.process_time() - tick
    tick = time.process_time()
    pos = np.bincount(clause, weights=positive, minlength=len(widths))
    neg = widths - pos
    ph, nh = positive & (pos[clause] > 1), ~positive & (neg[clause] > 1)
    mean = lambda a: float(a.mean()) if len(a) else 0.
    shared = np.array([n / max(nmax, 1), mean(pos <= 1), mean(neg <= 1),
        len(np.unique(variable[ph])) / max(n, 1), len(np.unique(variable[nh])) / max(n, 1),
        ph.sum() / max(length, 1), nh.sum() / max(length, 1),
        (raw_length - length) / max(raw_length, 1)])
    common_cpu = time.process_time() - tick
    tick = time.process_time()
    actual = full_profile(variable, clause, positive, widths, n)
    actual_cpu = time.process_time() - tick
    tick = time.process_time()
    shuffled = rewire(2 * variable + ~positive, clause, widths) if length else np.array([], int)
    control = full_profile(shuffled // 2, clause, (shuffled & 1) == 0, widths, n)
    null_cpu = time.process_time() - tick
    distinct = bool(np.linalg.norm(actual - control) > 1e-6)
    cover_fractions = 2 * actual[[0, 6]]
    unsaturated = bool(cover_fractions.min() < .95)
    assert np.isfinite(np.r_[shared, actual, control]).all() and actual.shape == control.shape == (42,)
    return shared, actual, control, {'active_variables': n, 'normalized_occurrences': length,
        'raw_occurrences': raw_length, 'parse_CPU_s': parse_cpu, 'common_CPU_s': common_cpu,
        'actual_profile_CPU_s': actual_cpu, 'null_profile_CPU_s': null_cpu,
        'actual_null_distinct': distinct, 'unsaturated': unsaturated,
        'mean_Horn_deletion_cover_fraction': float(cover_fractions[0]),
        'mean_inverseHorn_deletion_cover_fraction': float(cover_fractions[1]),
        'informative': distinct and unsaturated, 'matching_passes': 12}


def collect_one(job):
    key, path, expected, nmax = job
    cpu, wall = time.process_time(), time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R47 input30wall')))
    signal.alarm(30)
    identity_cpu = 0.
    try:
        raw = load_formula(Path(path)); read_cpu = time.process_time() - cpu
        tick = time.process_time()
        assert hashlib.sha256(raw).hexdigest() == expected, 'R47 cached input SHA mismatch'
        identity_cpu = time.process_time() - tick
        shared, actual, control, r = extract(raw, nmax)
        elapsed = time.process_time() - cpu
        if elapsed > 10:
            raise TimeoutError('R47 input10CPU')
        common = read_cpu + r['parse_CPU_s'] + r['common_CPU_s']
        r.update(instance_key=key, status='ok', raw_sha256=expected, raw_bytes=len(raw),
            physical_CPU_s=elapsed, identity_CPU_s=identity_cpu, read_CPU_s=read_cpu,
            wall_s=time.monotonic() - wall, common_fee_CPU_s=common,
            joint_fee_CPU_s=common + r['actual_profile_CPU_s'], null_fee_CPU_s=common + r['null_profile_CPU_s'])
        return key, shared, actual, control, r
    except Exception as error:
        elapsed = time.process_time() - cpu; fee = max(0, elapsed - identity_cpu)
        return key, np.zeros(8), np.zeros(42), np.zeros(42), {'instance_key': key, 'status': 'ERROR',
            'error': repr(error), 'raw_sha256': expected, 'physical_CPU_s': elapsed,
            'identity_CPU_s': identity_cpu, 'wall_s': time.monotonic() - wall,
            'common_fee_CPU_s': fee, 'joint_fee_CPU_s': fee, 'null_fee_CPU_s': fee,
            'informative': False, 'actual_null_distinct': False, 'unsaturated': False, 'matching_passes': None}
    finally:
        signal.alarm(0)


def collect(out):
    began = time.monotonic()
    assert (np.__version__, sklearn.__version__) == ('2.5.4', '1.9.1')
    checks = semantic_checks()
    reference = DATA / 'mechanism_R38_features_20261111/features.npz'
    with np.load(reference) as z:
        keys, base, eligible = z['keys'].tolist(), z['topology63'][:, :43].copy(), z['eligible'].copy()
    assert len(keys) == 4719 and eligible.sum() == 2325 and np.array_equal(base[:, 42], eligible)
    identity = {r['instance_key']: r['raw_sha256'] for r in map(json.loads,
        (DATA / 'cnf_graph_cnn_20261110/feature_receipts.jsonl').read_text().splitlines())}
    panel = ROOT / 'work/astra_structure_panel_20261110'
    fallback = {r['instance_key']: panel / 'cnf' / (r['case'] + '.cnf') for r in read_csv(panel / 'association_only.csv')}
    jobs = []
    for i, (key, yes) in enumerate(zip(keys, eligible)):
        if not yes: continue
        path = ROOT / 'work/signed_boundary_20261110/cnf_cache' / (key + '.cnf.gz')
        if not path.is_file(): path = fallback[key]
        assert path.is_file()
        jobs.append((key, str(path), identity[key], int(round(np.expm1(base[i, 0])))))
    index = {k: i for i, k in enumerate(keys)}
    shared, actual, control = np.zeros((4719, 8)), np.zeros((4719, 42)), np.zeros((4719, 42))
    okay, informative = ~eligible.copy(), np.zeros(4719, bool)
    fees = {k: np.zeros(4719) for k in ('marginal', 'joint', 'decoupled')}
    records = out / 'feature_records'; records.mkdir()
    distinct = unsaturated = matching_passes = errors = 0
    with threadpool_limits(limits=1), ProcessPoolExecutor(max_workers=4, initializer=initialize_worker) as pool:
        todo = iter(jobs); pending = deque(pool.submit(collect_one, next(todo)) for _ in range(4))
        completed = 0
        while pending:
            key, c, a, n, r = pending.popleft().result(timeout=max(1, 900 - (time.monotonic() - began)))
            i = index[key]; shared[i], actual[i], control[i] = c, a, n
            okay[i], informative[i] = r['status'] == 'ok', r['informative']
            distinct += r['actual_null_distinct']; unsaturated += r['unsaturated']; errors += r['status'] != 'ok'
            matching_passes += r['matching_passes'] or 0
            for k, f in [('marginal', 'common_fee_CPU_s'), ('joint', 'joint_fee_CPU_s'), ('decoupled', 'null_fee_CPU_s')]:
                fees[k][i] = r[f]
            atomic(records / (key + '.json'), {'receipt': r, 'shared8': c.tolist(), 'joint42': a.tolist(), 'decoupled42': n.tolist()})
            completed += 1
            if completed % 200 == 0:
                atomic(out / 'progress.json', {'stage': 'collection', 'completed': completed, 'expected': 2325,
                    'informative': int(informative.sum()), 'wall_s': time.monotonic() - began})
                print(f'R47 collected {completed}/2325 Horn-deletion profiles', flush=True)
            if time.monotonic() - began > 900: raise TimeoutError('R47 collection15wallmin')
            job = next(todo, None)
            if job is not None: pending.append(pool.submit(collect_one, job))
    arrays = {'marginal': np.c_[base, shared, np.zeros_like(actual)],
              'joint': np.c_[base, shared, actual], 'decoupled': np.c_[base, shared, control]}
    assert all(a.shape == (4719, 93) for a in arrays.values())
    np.savez_compressed(out / 'features.npz', keys=np.array(keys), eligible=eligible, valid=okay,
        informative=informative, **arrays, **{k + '_fee': v for k, v in fees.items()})
    atomic(out / 'collection.json', {'parents': 4719, 'attempted': completed, 'successful': int(okay[eligible].sum()),
        'failed': errors, 'actual_null_distinct': distinct, 'unsaturated_profiles': unsaturated,
        'informative': int(informative.sum()), 'matching_passes': matching_passes,
        'unknown_failed_matching_work': errors, 'wall_s': time.monotonic() - began,
        'semantic_checks': checks, 'source_sha256': sha(__file__), 'reference_sha256': sha(reference),
        'features_sha256': sha(out / 'features.npz'), 'new_solver_calls': 0, 'new_standalone_extractor_processes': 0,
        'library_versions': {'numpy': np.__version__, 'sklearn': sklearn.__version__}})
    return keys, eligible, okay, informative, arrays, fees
