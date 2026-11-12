"""R50 width x polarity contingency; features only, existing runtime labels reused."""
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import hashlib
import json
from pathlib import Path
import signal
import time

import numpy as np
import sklearn
from threadpoolctl import threadpool_limits

from .common import sha
from .measure_compact_prefetch import atomic
from .route_phase_2022 import load_formula
from .scc_quotient_features import parse
from .structural_clusters import DATA, ROOT, read_csv

WIDTH_UPPER = (0, 1, 2, 3, 4, 8, 16, 32)


def initialize_worker():
    global _thread_limit
    _thread_limit = threadpool_limits(limits=1)


def table(widths, positive):
    wb = np.searchsorted(WIDTH_UPPER, widths, side='left')
    pb = np.select((widths == 0, positive == 0, 4 * positive < widths,
        2 * positive < widths, 2 * positive == widths, 4 * positive <= 3 * widths,
        positive < widths), (3, 0, 1, 2, 3, 4, 5), default=6)
    counts = np.bincount(7 * wb + pb, minlength=63).reshape(9, 7)
    null_pb = np.random.default_rng(20261150).permutation(pb)
    null = np.bincount(7 * wb + null_pb, minlength=63).reshape(9, 7)
    assert np.array_equal(counts.sum(axis=0), null.sum(axis=0))
    assert np.array_equal(counts.sum(axis=1), null.sum(axis=1))
    return counts, null


def semantic_checks():
    widths, positive = np.array([1, 1, 2, 2, 3, 4, 4, 0]), np.array([0, 1, 0, 2, 1, 1, 3, 0])
    a, _ = table(widths, positive)
    b, _ = table(widths, widths - positive)
    assert np.array_equal(a, b[:, ::-1]) and a.sum() == len(widths)
    assert a[1, 0] == a[1, 6] == a[2, 0] == a[2, 6] == 1
    assert a[0, 3] == 1 and a[4, 2] == a[4, 4] == 1
    return {'complement_reverses_polarity_columns': True, 'empty_is_neutral_bin': True,
        'quarter_boundaries_exact': True, 'marginal_invariants': True, 'SAT_calls': 0}


def extract(raw):
    tick = time.process_time()
    nodes, clause, m, n = parse(raw)
    widths = np.bincount(clause, minlength=m)
    positive = np.bincount(clause, weights=(nodes & 1) == 0, minlength=m).astype(np.int64)
    parse_cpu = time.process_time() - tick
    tick = time.process_time()
    # Same deterministic table routine also constructs the predeclared null.
    counts, null = table(widths, positive)
    probability = counts / max(m, 1)
    independent = np.outer(counts.sum(axis=1), counts.sum(axis=0)) / max(m * m, 1)
    actual, marginal, control = np.sqrt(probability).ravel(), np.sqrt(independent).ravel(), np.sqrt(null / max(m, 1)).ravel()
    # All views conservatively pay the same shared vectorized construction.
    table_cpu = time.process_time() - tick
    selected = counts > 0
    mi = float((probability[selected] * np.log(probability[selected] / independent[selected])).sum()) if m else 0.
    distinct = bool(np.linalg.norm(actual - control) > 1e-6)
    informative = bool(m >= 40 and mi > .01 and distinct)
    assert min(mi, 0) >= -1e-12 and all(a.shape == (63,) and np.isfinite(a).all() for a in (actual, marginal, control))
    assert np.isclose((actual * actual).sum(), float(m > 0), rtol=0, atol=1e-12)
    return actual, marginal, control, {'parse_CPU_s': parse_cpu, 'table_CPU_s': table_cpu,
        'clauses': m, 'active_variables': n, 'literal_occurrences': len(nodes),
        'width_polarity_mutual_information_nats': max(mi, 0.),
        'actual_null_distinct': distinct, 'informative': informative}


def collect_one(job):
    key, path, expected = job
    cpu, wall = time.process_time(), time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R50 input30wall')))
    signal.alarm(30)
    identity_cpu = 0.
    try:
        raw = load_formula(Path(path)); read_cpu = time.process_time() - cpu
        tick = time.process_time()
        assert hashlib.sha256(raw).hexdigest() == expected, 'R50 cached input SHA mismatch'
        identity_cpu = time.process_time() - tick
        actual, marginal, control, r = extract(raw)
        elapsed = time.process_time() - cpu
        if elapsed > 10: raise TimeoutError('R50 input10CPU')
        r.update(instance_key=key, status='ok', raw_sha256=expected, raw_bytes=len(raw),
            physical_CPU_s=elapsed, identity_CPU_s=identity_cpu, read_CPU_s=read_cpu,
            wall_s=time.monotonic() - wall, shared_fee_CPU_s=read_cpu + r['parse_CPU_s'] + r['table_CPU_s'])
        return key, actual, marginal, control, r
    except Exception as error:
        elapsed = time.process_time() - cpu
        return key, *[np.zeros(63) for _ in range(3)], {'instance_key': key, 'status': 'ERROR',
            'error': repr(error), 'raw_sha256': expected, 'physical_CPU_s': elapsed,
            'identity_CPU_s': identity_cpu, 'wall_s': time.monotonic() - wall,
            'shared_fee_CPU_s': max(0, elapsed - identity_cpu), 'informative': False, 'actual_null_distinct': False}
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
        jobs.append((key, str(path), identities[key]))
    index = {k: i for i, k in enumerate(keys)}
    blocks = {k: np.zeros((4719, 63)) for k in ('joint', 'marginal', 'decoupled')}
    okay, informative = ~eligible.copy(), np.zeros(4719, bool)
    fee = np.zeros(4719)
    records = out / 'feature_records'; records.mkdir()
    distinct = errors = completed = 0
    with ProcessPoolExecutor(max_workers=4, initializer=initialize_worker) as pool:
        todo = iter(jobs)
        pending = {pool.submit(collect_one, next(todo)) for _ in range(4)}
        while pending:
            done, pending = wait(pending, timeout=max(1, 900 - (time.monotonic() - began)), return_when=FIRST_COMPLETED)
            if not done: raise TimeoutError('R50 collection15wallmin')
            for future in done:
                key, a, m, n, r = future.result()
                i = index[key]
                for kind, v in zip(('joint', 'marginal', 'decoupled'), (a, m, n)): blocks[kind][i] = v
                okay[i], informative[i], fee[i] = r['status'] == 'ok', r['informative'], r['shared_fee_CPU_s']
                distinct += r['actual_null_distinct']; errors += r['status'] != 'ok'; completed += 1
                atomic(records / (key + '.json'), {'receipt': r, 'joint63': a.tolist(), 'marginal63': m.tolist(), 'decoupled63': n.tolist()})
                if completed % 200 == 0:
                    atomic(out / 'progress.json', {'stage': 'collection', 'completed': completed, 'expected': 2325,
                        'informative': int(informative.sum()), 'wall_s': time.monotonic() - began})
                    print(f'R50 collected {completed}/2325 clause-polarity tables', flush=True)
                job = next(todo, None)
                if job is not None: pending.add(pool.submit(collect_one, job))
    arrays = {k: np.c_[base, v] for k, v in blocks.items()}
    assert all(a.shape == (4719, 106) for a in arrays.values())
    fees = {k: fee.copy() for k in arrays}
    np.savez_compressed(out / 'features.npz', keys=np.array(keys), eligible=eligible, valid=okay,
        informative=informative, **arrays, **{k + '_fee': v for k, v in fees.items()})
    atomic(out / 'collection.json', {'parents': 4719, 'attempted': completed, 'successful': int(okay[eligible].sum()),
        'failed': errors, 'actual_null_distinct': distinct, 'informative': int(informative.sum()),
        'wall_s': time.monotonic() - began, 'semantic_checks': checks, 'source_sha256': sha(__file__),
        'reference_sha256': sha(reference), 'features_sha256': sha(out / 'features.npz'),
        'new_solver_calls': 0, 'new_external_native_extractor_processes': 0, 'python_profile_workers': 4,
        'library_versions': {'numpy': np.__version__, 'sklearn': sklearn.__version__}})
    return keys, eligible, okay, informative, arrays, fees
