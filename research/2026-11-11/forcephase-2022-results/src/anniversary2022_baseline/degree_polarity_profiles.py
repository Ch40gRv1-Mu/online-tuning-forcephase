"""R44 raw degree-conditioned signed marginals, no assignments or SAT search."""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import signal
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .measure_compact_prefetch import atomic
from .route_phase_2022 import load_formula
from .scc_quotient_features import parse
from .structural_clusters import DATA, ROOT, read_csv


def band_profile(degree, bias):
    if not len(degree):
        return np.zeros(48)
    band = np.minimum(5, np.floor(np.log2(degree)).astype(int))
    count = np.bincount(band, minlength=6)
    mass = np.bincount(band, weights=degree, minlength=6)
    avg = lambda x: np.bincount(band, weights=x, minlength=6) / np.maximum(count, 1)
    return np.c_[count / len(degree), mass / degree.sum(), avg(bias), avg(bias ** 2),
        avg(np.abs(bias)), np.bincount(band, weights=degree * bias, minlength=6) / np.maximum(mass, 1),
        avg(bias == 1), avg(bias == -1)].ravel()


def extract(raw, nmax):
    tick = time.process_time()
    nodes, _, _, n = parse(raw)
    parse_cpu = time.process_time() - tick
    tick = time.process_time()
    counts = np.bincount(nodes, minlength=2 * n).reshape(n, 2).astype(float)
    degree = counts.sum(axis=1)
    assert np.all(degree > 0) and n <= nmax
    bias = (counts[:, 0] - counts[:, 1]) / np.maximum(degree, 1)
    mean = lambda a: float(a.mean()) if len(a) else 0.
    common = np.array([n / max(nmax, 1), counts[:, 0].sum() / max(degree.sum(), 1),
        mean(bias), mean(bias ** 2), mean(np.abs(bias)), mean(bias == 0), mean(bias == 1), mean(bias == -1)])
    common_cpu = time.process_time() - tick
    tick = time.process_time()
    actual = band_profile(degree, bias)
    if n:
        table = actual.reshape(6, 8)
        assert np.allclose([table[:, 0].sum(), table[:, 1].sum()], 1)
        assert np.allclose(table[:, 0] @ table[:, 2:5], common[[2, 3, 4]])
        assert np.isclose(table[:, 1] @ table[:, 5], 2 * common[1] - 1)
        assert np.allclose(table[:, 0] @ table[:, 6:8], common[[6, 7]])
    actual_cpu = time.process_time() - tick
    tick = time.process_time()
    shuffled = bias[np.random.default_rng(20261144).permutation(n)]
    control = band_profile(degree, shuffled)
    assert np.array_equal(np.sort(bias), np.sort(shuffled))
    assert np.array_equal(actual.reshape(6, 8)[:, :2], control.reshape(6, 8)[:, :2])
    null_cpu = time.process_time() - tick
    assert np.isfinite(np.r_[common, actual, control]).all()
    return common, actual, control, {'active_variables': n, 'raw_occurrences': len(nodes),
        'parse_CPU_s': parse_cpu, 'common_CPU_s': common_cpu, 'actual_band_CPU_s': actual_cpu,
        'decoupled_band_CPU_s': null_cpu, 'degree_mass_and_bias_multiset_preserved': True,
        'informative': bool(np.linalg.norm(actual - control) > 1e-6)}


def collect_one(job):
    key, path, expected, nmax = job
    cpu, wall = time.process_time(), time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R44 input15wall')))
    signal.alarm(15)
    identity_cpu = 0.
    try:
        raw = load_formula(Path(path))
        read_cpu = time.process_time() - cpu
        tick = time.process_time()
        assert hashlib.sha256(raw).hexdigest() == expected, 'R44 cached input SHA mismatch'
        identity_cpu = time.process_time() - tick
        common, actual, control, receipt = extract(raw, nmax)
        elapsed = time.process_time() - cpu
        if elapsed > 5:
            raise TimeoutError('R44 input5CPU')
        shared = read_cpu + receipt['parse_CPU_s'] + receipt['common_CPU_s']
        receipt.update(instance_key=key, status='ok', raw_sha256=expected, raw_bytes=len(raw),
            read_CPU_s=read_cpu, identity_CPU_s=identity_cpu, physical_CPU_s=elapsed,
            wall_s=time.monotonic() - wall, common_fee_CPU_s=shared,
            joint_fee_CPU_s=shared + receipt['actual_band_CPU_s'],
            null_fee_CPU_s=shared + receipt['decoupled_band_CPU_s'])
        return key, common, actual, control, receipt
    except Exception as error:
        elapsed = time.process_time() - cpu
        fee = max(0, elapsed - identity_cpu)
        return key, np.zeros(8), np.zeros(48), np.zeros(48), {
            'instance_key': key, 'status': 'ERROR', 'error': repr(error), 'raw_sha256': expected,
            'physical_CPU_s': elapsed, 'identity_CPU_s': identity_cpu, 'wall_s': time.monotonic() - wall,
            'common_fee_CPU_s': fee, 'joint_fee_CPU_s': fee, 'null_fee_CPU_s': fee, 'informative': False}
    finally:
        signal.alarm(0)


def collect(out):
    began = time.monotonic()
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
    common, actual, control = np.zeros((4719, 8)), np.zeros((4719, 48)), np.zeros((4719, 48))
    okay, informative = ~eligible.copy(), np.zeros(4719, bool)
    fees = {k: np.zeros(4719) for k in ('marginal', 'joint', 'decoupled')}
    records = out / 'feature_records'
    records.mkdir()
    with threadpool_limits(limits=1), ProcessPoolExecutor(max_workers=4) as pool:
        todo = iter(jobs)
        pending = deque(pool.submit(collect_one, next(todo)) for _ in range(4))
        completed = 0
        while pending:
            key, c, a, n, rec = pending.popleft().result(timeout=max(1, 900 - (time.monotonic() - began)))
            i = index[key]
            common[i], actual[i], control[i] = c, a, n
            okay[i], informative[i] = rec['status'] == 'ok', rec['informative']
            for k, field in [('marginal', 'common_fee_CPU_s'), ('joint', 'joint_fee_CPU_s'), ('decoupled', 'null_fee_CPU_s')]:
                fees[k][i] = rec[field]
            atomic(records / (key + '.json'), {'receipt': rec, 'shared8': c.tolist(),
                'joint48': a.tolist(), 'decoupled48': n.tolist()})
            completed += 1
            if completed % 200 == 0:
                atomic(out / 'progress.json', {'stage': 'collection', 'completed': completed, 'expected': 2325,
                    'informative': int(informative.sum()), 'wall_s': time.monotonic() - began})
                print(f'R44 collected {completed}/2325 profiles', flush=True)
            if time.monotonic() - began > 900:
                raise TimeoutError('R44 collection15wallmin')
            job = next(todo, None)
            if job is not None:
                pending.append(pool.submit(collect_one, job))
    arrays = {'marginal': np.c_[base, common, np.zeros_like(actual)],
              'joint': np.c_[base, common, actual], 'decoupled': np.c_[base, common, control]}
    assert all(v.shape == (4719, 99) for v in arrays.values())
    np.savez_compressed(out / 'features.npz', keys=np.array(keys), eligible=eligible, valid=okay,
        informative=informative, **arrays, **{k + '_fee': v for k, v in fees.items()})
    atomic(out / 'collection.json', {'parents': 4719, 'attempted': completed,
        'successful': int(okay[eligible].sum()), 'failed': int((~okay).sum()),
        'informative': int(informative.sum()), 'wall_s': time.monotonic() - began,
        'reference_sha256': sha(reference), 'source_sha256': sha(__file__),
        'features_sha256': sha(out / 'features.npz'), 'new_solver_calls': 0})
    return keys, eligible, okay, informative, arrays, fees
