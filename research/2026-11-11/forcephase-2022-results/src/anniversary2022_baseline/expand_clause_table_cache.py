"""R52 fixed coverage expansion: reuse R50, extract only518 cached public CNFs."""
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import json
from pathlib import Path
import time

import numpy as np

from .clause_polarity_table import collect_one, initialize_worker
from .common import sha
from .measure_compact_prefetch import CONFIG, atomic
from .structural_clusters import DATA, ROOT, read_csv

OLD = DATA / 'mechanism_R50_20261111'
SOURCE = Path(__file__).with_name('clause_polarity_table.py')


def collect(out):
    began = time.monotonic()
    previous = json.loads((OLD / 'collection.json').read_text())
    assert previous['source_sha256'] == sha(SOURCE) and previous['failed'] == 0
    assert previous['features_sha256'] == sha(OLD / 'features.npz')
    with np.load(OLD / 'features.npz') as z:
        keys, old_eligible, okay = z['keys'].tolist(), z['eligible'].copy(), z['valid'].copy()
        arrays = {k: z[k].copy() for k in ('joint', 'marginal', 'decoupled')}
        fees = {k: z[k + '_fee'].copy() for k in arrays}
        old_informative = z['informative'].copy()
    by_key = {r['instance_key']: r for r in read_csv(CONFIG / 'manifest.csv')}
    eligible = np.array([int(by_key[k]['GBD_plain_bytes']) <= 3000000 for k in keys])
    assert len(keys) == 4719 and old_eligible.sum() == 2325 and eligible.sum() == 2843
    assert not (old_eligible & ~eligible).any()
    added = eligible & ~old_eligible
    assert added.sum() == 518
    identities = {r['instance_key']: r['raw_sha256'] for r in map(json.loads,
        (DATA / 'cnf_graph_cnn_20261110/feature_receipts.jsonl').read_text().splitlines())}
    panel = ROOT / 'work/astra_structure_panel_20261110'
    fallback = {r['instance_key']: panel / 'cnf' / (r['case'] + '.cnf') for r in read_csv(panel / 'association_only.csv')}
    jobs = []
    for key, yes in zip(keys, added):
        if not yes: continue
        path = ROOT / 'work/signed_boundary_20261110/cnf_cache' / (key + '.cnf.gz')
        if not path.is_file(): path = fallback[key]
        assert path.is_file() and key in identities
        jobs.append((key, str(path), identities[key]))
    atomic(out / 'cohort.json', {'new_keys': [j[0] for j in jobs], 'new_parents': 518,
        'all_score_parents': 4719, 'covered_after': 2843, 'reused_old_parents': 2325,
        'selection': 'Pre-existing public plain-byte metadata<=3M, no phase outcomes/family',
        'original_count_qualification_coordinate_42_unchanged': True,
        'old_features_sha256': sha(OLD / 'features.npz'), 'old_source_sha256': sha(SOURCE),
        'manifest_sha256': sha(CONFIG / 'manifest.csv'), 'download_calls': 0})
    index = {k: i for i, k in enumerate(keys)}
    new_informative = np.zeros(4719, bool)
    records = out / 'feature_records'; records.mkdir()
    completed = errors = distinct = 0
    with ProcessPoolExecutor(max_workers=4, initializer=initialize_worker) as pool:
        todo = iter(jobs); pending = {pool.submit(collect_one, next(todo)) for _ in range(4)}
        while pending:
            done, pending = wait(pending, timeout=max(1, 900 - (time.monotonic() - began)), return_when=FIRST_COMPLETED)
            if not done: raise TimeoutError('R52 collection15wallmin')
            for future in done:
                key, a, m, n, r = future.result(); i = index[key]
                for kind, v in zip(('joint', 'marginal', 'decoupled'), (a, m, n)):
                    arrays[kind][i, 43:] = v
                    fees[kind][i] = r['shared_fee_CPU_s']
                okay[i], new_informative[i] = r['status'] == 'ok', r['informative']
                errors += r['status'] != 'ok'; distinct += r['actual_null_distinct']; completed += 1
                atomic(records / (key + '.json'), {'receipt': r, 'joint63': a.tolist(),
                    'marginal63': m.tolist(), 'decoupled63': n.tolist()})
                if completed % 100 == 0:
                    atomic(out / 'progress.json', {'stage': 'collection', 'new_completed': completed,
                        'new_expected': 518, 'reused': 2325, 'wall_s': time.monotonic() - began})
                    print(f'R52 extracted {completed}/518 additional tables; reused2325', flush=True)
                job = next(todo, None)
                if job is not None: pending.add(pool.submit(collect_one, job))
    with np.load(OLD / 'features.npz') as z:
        for k in arrays:
            assert np.array_equal(arrays[k][old_eligible], z[k][old_eligible])
            assert np.array_equal(arrays[k][:, :43], z[k][:, :43])
            assert np.array_equal(fees[k][old_eligible], z[k + '_fee'][old_eligible])
    np.savez_compressed(out / 'features.npz', keys=np.array(keys), eligible=eligible, valid=okay,
        informative=new_informative, newly_covered=added, old_informative=old_informative,
        **arrays, **{k + '_fee': v for k, v in fees.items()})
    atomic(out / 'collection.json', {'parents': 4719, 'new_attempts': completed,
        'new_successful': int(okay[added].sum()), 'new_failed': errors, 'new_distinct': distinct,
        'reused_parents': 2325, 'total_profiled': 2843,
        'new_informative': int(new_informative.sum()), 'all_informative': int((old_informative | new_informative).sum()),
        'wall_s': time.monotonic() - began, 'source_sha256': sha(__file__), 'table_source_sha256': sha(SOURCE),
        'old_features_sha256': sha(OLD / 'features.npz'), 'features_sha256': sha(out / 'features.npz'),
        'new_solver_calls': 0, 'new_downloads': 0, 'old_physical_cost_charged_again': False})
    return keys, eligible, okay, new_informative, arrays, fees
