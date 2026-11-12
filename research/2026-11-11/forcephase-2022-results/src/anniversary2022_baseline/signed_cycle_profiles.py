"""R46 full-incidence forest parity descriptors, never CNF assignment search."""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import signal
import time

import numpy as np
import scipy
import sklearn
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, minimum_spanning_tree
from threadpoolctl import threadpool_limits

from .common import sha
from .literal_color_features import rewire
from .measure_compact_prefetch import atomic
from .route_phase_2022 import load_formula
from .scc_quotient_features import normalize, parse
from .structural_clusters import DATA, ROOT, read_csv

SEEDS = (20261146, 20261147, 20261148)


def initialize_worker():
    global _worker_thread_limiter
    _worker_thread_limiter = threadpool_limits(limits=1)


def forest_profile(variable, clause, negative, nv, widths, seed):
    length, nc = len(variable), len(widths)
    nn, u, v = nv + nc, variable, nv + clause
    if not length:
        return np.zeros(16), {'MST_calls': 0, 'parity_CC_calls': 0, 'parallel_slots': 0}
    permutation = np.random.default_rng(seed).permutation(length)
    weight = np.empty(length, np.int64)
    weight[permutation] = np.arange(1, length + 1)
    key = u.astype(np.int64) * nn + v
    order = np.lexsort((weight, key))
    keep = np.r_[True, key[order][1:] != key[order][:-1]]
    slots = order[keep]
    graph = coo_matrix((weight[slots].astype(float), (u[slots], v[slots])), shape=(nn, nn)).tocsr()
    forest = minimum_spanning_tree(graph).tocoo()
    ranks = forest.data.astype(np.int64)
    assert np.array_equal(ranks, forest.data) and np.all((ranks >= 1) & (ranks <= length))
    chosen = permutation[ranks - 1]
    tu, tv, ts = u[chosen], v[chosen], negative[chosen]
    assert np.array_equal(np.minimum(forest.row, forest.col), tu)
    assert np.array_equal(np.maximum(forest.row, forest.col), tv)
    lift = coo_matrix((np.ones(2 * len(chosen), np.int8),
        (np.r_[2 * tu, 2 * tu + 1], np.r_[2 * tv + ts, 2 * tv + (ts ^ 1)])),
        shape=(2 * nn, 2 * nn)).tocsr()
    _, labels = connected_components(lift, directed=False)
    assert np.all(labels[::2] != labels[1::2])
    spin = np.where(labels[::2] > labels[1::2], -1., 1.)
    _, comp = np.unique(np.minimum(labels[::2], labels[1::2]), return_inverse=True)
    count = int(comp.max()) + 1
    assert len(chosen) == nn - count and np.all(comp[u] == comp[v])
    vd = np.bincount(u, minlength=nv).astype(float)
    cv, cc = comp[:nv], comp[nv:]
    vn = np.bincount(cv, minlength=count)
    cm = np.bincount(cc, minlength=count)
    vmass = np.bincount(cv, weights=vd, minlength=count)
    signed_mass = np.bincount(cv, weights=vd * spin[:nv], minlength=count)
    signed_count = np.bincount(cv, weights=spin[:nv], minlength=count)
    anchor = np.full(count, nv, int)
    np.minimum.at(anchor, cv, np.arange(nv))
    assert np.all(anchor < nv)
    flip = (signed_mass < 0) | ((signed_mass == 0) & (signed_count < 0)) | (
        (signed_mass == 0) & (signed_count == 0) & (spin[anchor] < 0))
    spin *= np.where(flip[comp], -1., 1.)
    assert np.all(spin[tu] * spin[tv] == 1 - 2 * ts)
    bad = spin[u] * spin[v] != 1 - 2 * negative
    bad_count = np.bincount(comp[u], weights=bad, minlength=count)
    edge_mass = np.bincount(comp[u], minlength=count)
    balanced = bad_count == 0
    weighted_coherence = np.abs(signed_mass) / np.maximum(vmass, 1)
    largest = int(vn.argmax())
    clause_spin = spin[nv:]
    mean = lambda a: float(a.mean()) if len(a) else 0.
    result = [bad.mean(), bad.sum() / max(length - len(chosen), 1),
        np.abs(signed_mass).sum() / max(length, 1),
        np.abs(signed_count).sum() / max(nv, 1), weighted_coherence[largest],
        vn[balanced].sum() / max(nv, 1), edge_mass[balanced].sum() / max(length, 1),
        float(spin[u][bad].sum()) / max(int(bad.sum()), 1),
        mean(clause_spin), np.dot(widths, clause_spin) / max(length, 1)]
    classes = (widths == 2, widths == 3, widths >= 4)
    result.extend(mean(clause_spin[c]) for c in classes)
    result.extend(float(bad[c[clause]].sum()) / max(int(c[clause].sum()), 1) for c in classes)
    result = np.array(result)
    assert result.shape == (16,) and np.isfinite(result).all()
    return result, {'MST_calls': 1, 'parity_CC_calls': 1,
        'parallel_slots': int(length - len(slots)), 'forest_edges': len(chosen),
        'unsigned_components': count, 'all_tree_parities_satisfied': True,
        'all_original_edges_within_forest_components': True}


def semantic_checks():
    u, c, w = np.array([0, 1, 0, 1]), np.array([0, 0, 1, 1]), np.array([2, 2])
    rows = []
    for seed in SEEDS:
        balanced, _ = forest_profile(u, c, np.array([0, 0, 1, 1]), 2, w, seed)
        negative, _ = forest_profile(u, c, np.array([0, 0, 0, 1]), 2, w, seed)
        reverse, _ = forest_profile(u, c, np.array([1, 1, 1, 0]), 2, w, seed)
        assert balanced[0] == 0 and negative[0] == .25
        signed = np.arange(8, 13)
        invariant = np.r_[np.arange(8), np.arange(13, 16)]
        assert np.allclose(negative[signed], -reverse[signed])
        assert np.allclose(negative[invariant], reverse[invariant])
        rows.append({'seed': seed, 'balanced_residual': float(balanced[0]),
            'negative_square_residual': float(negative[0]), 'complement_feature_covariance': True})
    return {'fixtures': rows, 'MST_calls': 9, 'parity_CC_calls': 9,
            'CNF_solver_calls': 0, 'checks_are_not_runtime_symmetry_evidence': True}


def extract(raw, nmax):
    tick = time.process_time()
    nodes, clauses, raw_m, _ = parse(raw)
    raw_length = len(nodes)
    nodes, clauses, widths, _ = normalize(nodes, clauses, raw_m)
    active_clauses = np.flatnonzero(widths)
    clause = np.searchsorted(active_clauses, clauses)
    widths = widths[active_clauses]
    _, variable = np.unique(nodes // 2, return_inverse=True)
    negative = (nodes & 1).astype(np.int64)
    nv, length = int(variable.max()) + 1 if len(variable) else 0, len(variable)
    nc, nn = len(widths), nv + len(widths)
    parse_cpu = time.process_time() - tick
    tick = time.process_time()
    if length:
        g = coo_matrix((np.ones(length), (variable, nv + clause)), shape=(nn, nn)).tocsr()
        components, lab = connected_components(g, directed=False)
        vm, cm = np.bincount(lab[:nv], minlength=components), np.bincount(lab[nv:], minlength=components)
        em = np.bincount(lab[variable], minlength=components)
        tree_components = em == vm + cm - 1
        context = np.array([nv / max(nmax, 1), nc / max(raw_m, 1), np.log1p(components),
            vm.max() / max(nv, 1), cm.max() / max(nc, 1),
            (length - nn + components) / length, em[tree_components].sum() / length,
            (raw_length - length) / max(raw_length, 1)])
    else:
        context = np.array([0., 0., 0., 0., 0., 0., 0., float(raw_length > 0)])
    context_cpu = time.process_time() - tick
    tick = time.process_time()
    actual_rows, actual_recs = [], []
    for seed in SEEDS:
        x, r = forest_profile(variable, clause, negative, nv, widths, seed)
        actual_rows.append(x); actual_recs.append(r)
    actual_rows = np.asarray(actual_rows)
    actual = np.r_[actual_rows.mean(axis=0), actual_rows.std(axis=0), actual_rows.max(axis=0)]
    actual_cpu = time.process_time() - tick
    tick = time.process_time()
    shuffled_nodes = rewire(2 * variable + negative, clause, widths) if length else np.array([], int)
    control_rows, control_recs = [], []
    for seed in SEEDS:
        x, r = forest_profile(shuffled_nodes // 2, clause, shuffled_nodes & 1, nv, widths, seed)
        control_rows.append(x); control_recs.append(r)
    control_rows = np.asarray(control_rows)
    control = np.r_[control_rows.mean(axis=0), control_rows.std(axis=0), control_rows.max(axis=0)]
    null_cpu = time.process_time() - tick
    assert np.isfinite(np.r_[context, actual, control]).all()
    return context, actual, control, {'active_variables': nv, 'active_clauses': nc,
        'raw_occurrences': raw_length, 'normalized_occurrences': length,
        'parse_CPU_s': parse_cpu, 'common_CPU_s': context_cpu, 'actual_profile_CPU_s': actual_cpu,
        'null_profile_CPU_s': null_cpu,
        'MST_calls': sum(r['MST_calls'] for r in actual_recs + control_recs),
        'parity_CC_calls': sum(r['parity_CC_calls'] for r in actual_recs + control_recs),
        'unsigned_CC_calls': int(length > 0),
        'null_parallel_slots': max((r['parallel_slots'] for r in control_recs), default=0),
        'informative': bool(np.linalg.norm(actual - control) > 1e-6)}


def collect_one(job):
    key, path, expected, nmax = job
    cpu, wall = time.process_time(), time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R46 input30wall')))
    signal.alarm(30)
    identity_cpu = 0.
    try:
        raw = load_formula(Path(path))
        read_cpu = time.process_time() - cpu
        tick = time.process_time()
        assert hashlib.sha256(raw).hexdigest() == expected, 'R46 cached input SHA mismatch'
        identity_cpu = time.process_time() - tick
        context, actual, control, rec = extract(raw, nmax)
        elapsed = time.process_time() - cpu
        if elapsed > 10:
            raise TimeoutError('R46 input10CPU')
        common = read_cpu + rec['parse_CPU_s'] + rec['common_CPU_s']
        rec.update(instance_key=key, status='ok', raw_sha256=expected, raw_bytes=len(raw),
            read_CPU_s=read_cpu, identity_CPU_s=identity_cpu, physical_CPU_s=elapsed,
            wall_s=time.monotonic() - wall, common_fee_CPU_s=common,
            joint_fee_CPU_s=common + rec['actual_profile_CPU_s'],
            null_fee_CPU_s=common + rec['null_profile_CPU_s'])
        return key, context, actual, control, rec
    except Exception as error:
        elapsed = time.process_time() - cpu
        fee = max(0, elapsed - identity_cpu)
        return key, np.zeros(8), np.zeros(48), np.zeros(48), {
            'instance_key': key, 'status': 'ERROR', 'error': repr(error), 'raw_sha256': expected,
            'physical_CPU_s': elapsed, 'identity_CPU_s': identity_cpu, 'wall_s': time.monotonic() - wall,
            'common_fee_CPU_s': fee, 'joint_fee_CPU_s': fee, 'null_fee_CPU_s': fee, 'informative': False,
            'MST_calls': None, 'parity_CC_calls': None, 'unsigned_CC_calls': None}
    finally:
        signal.alarm(0)


def collect(out):
    began = time.monotonic()
    assert (scipy.__version__, np.__version__, sklearn.__version__) == ('1.18.1', '2.5.4', '1.9.1')
    checks = semantic_checks()
    reference = DATA / 'mechanism_R38_features_20261111/features.npz'
    with np.load(reference) as z:
        keys, base, eligible = z['keys'].tolist(), z['topology63'][:, :43].copy(), z['eligible'].copy()
    assert len(keys) == 4719 and eligible.sum() == 2325 and np.array_equal(base[:, 42], eligible)
    identities = {r['instance_key']: r['raw_sha256'] for r in map(json.loads,
        (DATA / 'cnf_graph_cnn_20261110/feature_receipts.jsonl').read_text().splitlines())}
    panel = ROOT / 'work/astra_structure_panel_20261110'
    fallback = {r['instance_key']: panel / 'cnf' / (r['case'] + '.cnf') for r in read_csv(panel / 'association_only.csv')}
    jobs = []
    for i, (key, yes) in enumerate(zip(keys, eligible)):
        if not yes:
            continue
        path = ROOT / 'work/signed_boundary_20261110/cnf_cache' / (key + '.cnf.gz')
        if not path.is_file():
            path = fallback[key]
        assert path.is_file()
        jobs.append((key, str(path), identities[key], int(round(np.expm1(base[i, 0])))))
    index = {k: i for i, k in enumerate(keys)}
    context, actual, control = np.zeros((4719, 8)), np.zeros((4719, 48)), np.zeros((4719, 48))
    okay, informative = ~eligible.copy(), np.zeros(4719, bool)
    fees = {k: np.zeros(4719) for k in ('marginal', 'joint', 'decoupled')}
    records = out / 'feature_records'
    records.mkdir()
    totals = {'MST_calls': 0, 'parity_CC_calls': 0, 'unsigned_CC_calls': 0, 'unknown_failed_graph_work': 0}
    with threadpool_limits(limits=1), ProcessPoolExecutor(max_workers=4, initializer=initialize_worker) as pool:
        todo = iter(jobs)
        pending = deque(pool.submit(collect_one, next(todo)) for _ in range(4))
        completed = 0
        while pending:
            key, c, a, n, rec = pending.popleft().result(timeout=max(1, 900 - (time.monotonic() - began)))
            i = index[key]
            context[i], actual[i], control[i] = c, a, n
            okay[i], informative[i] = rec['status'] == 'ok', rec['informative']
            for k, field in [('marginal', 'common_fee_CPU_s'), ('joint', 'joint_fee_CPU_s'), ('decoupled', 'null_fee_CPU_s')]:
                fees[k][i] = rec[field]
            for k in ('MST_calls', 'parity_CC_calls', 'unsigned_CC_calls'):
                if rec[k] is not None:
                    totals[k] += rec[k]
            totals['unknown_failed_graph_work'] += rec['status'] != 'ok'
            atomic(records / (key + '.json'), {'receipt': rec, 'shared8': c.tolist(),
                'joint48': a.tolist(), 'decoupled48': n.tolist()})
            completed += 1
            if completed % 200 == 0:
                atomic(out / 'progress.json', {'stage': 'collection', 'completed': completed, 'expected': 2325,
                    'informative': int(informative.sum()), 'wall_s': time.monotonic() - began})
                print(f'R46 collected {completed}/2325 signed-cycle profiles', flush=True)
            if time.monotonic() - began > 900:
                raise TimeoutError('R46 collection15wallmin')
            job = next(todo, None)
            if job is not None:
                pending.append(pool.submit(collect_one, job))
    arrays = {'marginal': np.c_[base, context, np.zeros_like(actual)],
              'joint': np.c_[base, context, actual], 'decoupled': np.c_[base, context, control]}
    assert all(v.shape == (4719, 99) for v in arrays.values())
    np.savez_compressed(out / 'features.npz', keys=np.array(keys), eligible=eligible, valid=okay,
        informative=informative, **arrays, **{k + '_fee': v for k, v in fees.items()})
    atomic(out / 'collection.json', {'parents': 4719, 'attempted': completed,
        'successful': int(okay[eligible].sum()), 'failed': int((~okay).sum()),
        'informative': int(informative.sum()), 'wall_s': time.monotonic() - began,
        'reference_sha256': sha(reference), 'source_sha256': sha(__file__),
        'features_sha256': sha(out / 'features.npz'), 'new_solver_calls': 0,
        'new_standalone_extractor_processes': 0, 'actual_native_library_calls': totals,
        'semantic_checks': checks, 'library_versions': {'scipy': scipy.__version__,
            'numpy': np.__version__, 'sklearn': sklearn.__version__}})
    return keys, eligible, okay, informative, arrays, fees
