"""R41 full-capacity, fixed-pair entropy ablations; no new solver observations."""
from concurrent.futures import ProcessPoolExecutor
import os
import json
import resource
import signal
import time

import numpy as np
from sklearn.ensemble import ExtraTreesRegressor
from threadpoolctl import threadpool_limits

from .common import sha
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS, calibrate, choose
from .recover_compact_cpu import OUT as RETRY
from .score_interpretable_two_percent import evaluate
from .score_static_seed_agreement import load_views
from .score_width_budget_recovery import timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv

OUT = DATA / 'mechanism_R41_20261111'
DROP = {'drop_legacy_balance': (21, 26), 'drop_degree_control': (36, 41)}


def fit_job(job):
    mode, kind, fold, train_x, train_y, val_x, held_x, val_cost, held_ids = job
    cpu, wall = time.process_time(), time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R41 fold600wall')))
    signal.alarm(600)
    try:
        with threadpool_limits(limits=1):
            model = ExtraTreesRegressor(n_estimators=256, max_depth=12,
                min_samples_leaf=4, max_features=.8, n_jobs=1,
                random_state=20261111 + fold)
            model.fit(train_x, train_y)
            assert model.n_features_in_ == 40 and model.n_outputs_ == 2
            vp, hp = model.predict(val_x) * 1200, model.predict(held_x) * 1200
            cut = calibrate(vp, val_cost, np.zeros(len(val_cost)))
            action = choose(hp, cut)
        return {'mode': mode, 'kind': kind, 'fold': fold, 'held_ids': held_ids,
            'actions': action, 'validation_scores': vp, 'held_scores': hp,
            'margin_PAR2_s': cut,
            'nodes': sum(t.tree_.node_count for t in model.estimators_),
            'CPU_s': time.process_time() - cpu, 'wall_s': time.monotonic() - wall}
    finally:
        signal.alarm(0)


def main():
    wall, cpu = time.monotonic(), time.process_time()
    initial = resource.getrusage(resource.RUSAGE_CHILDREN)
    OUT.mkdir(exist_ok=False)
    atomic(OUT / 'owner.json', {'pid': os.getpid(), 'source_sha256': sha(__file__),
        'started_UTC': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'expected_fits': 28, 'new_solver_calls': 0, 'remote_R35_untouched': True})
    completed, status = [], 'running'
    try:
        keys, _, costs, _, _, _ = load()
        original_x, valid = load_views(keys)[0]['linear42']
        assert valid.all() and original_x.shape == (4719, 42)
        views = {k: np.delete(original_x, indices, axis=1) for k, indices in DROP.items()}
        assert all(x.shape == (4719, 40) and np.isfinite(x).all() for x in views.values())
        splits = read_csv(SPLITS)
        iso_rows = read_csv(DATA / 'mechanism_R11_20261111/predictions.csv')
        original = read_csv(DATA / 'mechanism_R12_20261111/predictions.csv')
        old_summary = json.loads((DATA / 'mechanism_R12_20261111/summary.json').read_text())
        recovery = read_csv(RETRY / 'predictions.csv')
        assert all([r['instance_key'] for r in rows] == keys
                   for rows in (splits, iso_rows, original, recovery))
        inner = np.array([r['inner_validation'] == 'True' for r in splits])
        iso, coarse, fine = [np.array([r[k + '_group'] for r in splits])
                             for k in ('iso', 'coarse', 'fine')]
        folds = {'iso_diagnostic': np.array([int(r['diagnostic_iso_fold']) for r in iso_rows]),
                 **{m: np.array([int(r[m + '_fold']) for r in splits]) for m in ('coarse', 'fine')}}
        jobs = []
        for mode, assignment in folds.items():
            for fold in np.unique(assignment):
                held, train, val = assignment == fold, (assignment != fold) & ~inner, (assignment != fold) & inner
                assert not set(iso[held]) & set(iso[train | val])
                assert not set(fine[train]) & set(fine[val])
                target = costs[train][:, [0]] - costs[train][:, 1:]
                for kind, x in views.items():
                    jobs.append((mode, kind, int(fold), x[train], target / 1200,
                                 x[val], x[held], costs[val], np.flatnonzero(held)))
        with ProcessPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(fit_job, j) for j in jobs]
            for future in futures:
                r = future.result(timeout=max(1, 1200 - (time.monotonic() - wall)))
                completed.append(r)
                name = f"{r['mode']}_{r['kind']}_{r['fold']}"
                np.savez_compressed(OUT / (name + '.npz'), held_ids=r['held_ids'],
                    validation_scores=r['validation_scores'], held_scores=r['held_scores'])
                atomic(OUT / 'progress.json', {'completed_fits': len(completed),
                    'expected_fits': 28, 'wall_s': time.monotonic() - wall})
        fees = np.array([float(r['first_acquisition_CPU_s']) + float(r['second_acquisition_CPU_s'])
                         for r in recovery])
        failed = np.array([r['still_failed_paidD'] == 'True' for r in recovery])
        assert failed.sum() == 25
        scores, paired = {}, {}
        output = [{'instance_key': k} for k in keys]
        for mode, assignment in folds.items():
            group, paid_by_kind = fine if mode == 'fine' else coarse, {}
            for kind in (*DROP, 'cached_seed0', 'cached_min3'):
                if kind.startswith('cached_'):
                    variant = 'seed0' if kind == 'cached_seed0' else 'min3'
                    name = mode + '_linear42_' + variant
                    actions = np.array([ACTIONS.index(r[name + '_action']) for r in original])
                    enabled = np.array([old_summary['scores'][name]['cuts'][f]['margin_PAR2_s'] is not None
                                        for f in assignment])
                else:
                    actions, enabled = np.zeros(len(keys), int), np.zeros(len(keys), bool)
                    for r in completed:
                        if r['mode'] == mode and r['kind'] == kind:
                            ids = r['held_ids']
                            actions[ids], enabled[ids] = r['actions'], r['margin_PAR2_s'] is not None
                raw_cost = costs[np.arange(len(keys)), actions]
                action = actions.copy()
                action[failed & enabled] = 0
                paid = timed_cost(costs[np.arange(len(keys)), action], fees * enabled, 600)
                score = evaluate(costs[:, 0], paid, group, coarse, mode)
                score['free_unmasked'] = evaluate(costs[:, 0], raw_cost, group, coarse, mode)
                score['actions'] = {a: int((action == j).sum()) for j, a in enumerate(ACTIONS)}
                score['query_unmeasured_optimistic_zero'] = True
                scores[mode + '_' + kind], paid_by_kind[kind] = score, paid
                for i, row in enumerate(output):
                    row[mode + '_' + kind + '_action'] = ACTIONS[action[i]]
                    row[mode + '_' + kind + '_PAR2'] = float(paid[i])
                print(f"R41 {mode}_{kind}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}", flush=True)
            for control in ('drop_degree_control', 'cached_seed0', 'cached_min3'):
                paired[mode + '_over_' + control] = evaluate(paid_by_kind[control],
                    paid_by_kind['drop_legacy_balance'], group, coarse, mode)
        passed = True
        for mode in ('coarse', 'fine'):
            s = scores[mode + '_drop_legacy_balance']
            interval = s.get('exact_eight_block_95_pct', s['block_interval_95_pct'])
            passed &= s['gain_pct'] >= 2 and interval[0] > 0
            for control in ('drop_degree_control', 'cached_seed0', 'cached_min3'):
                s = paired[mode + '_over_' + control]
                interval = s.get('exact_eight_block_95_pct', s['block_interval_95_pct'])
                passed &= s['gain_pct'] > 0 and interval[0] >= 0
        write_csv(OUT / 'predictions.csv', output)
        status = 'complete'
        atomic(OUT / 'summary.json', {'status': status, 'parents': len(keys),
            'completed_fits': len(completed), 'primary_screen_passed': bool(passed),
            'scores': scores, 'paired_comparisons': paired, 'dropped_coordinates': DROP,
            'fit_records': [{k: v for k, v in r.items()
                if k not in ('held_ids', 'actions', 'validation_scores', 'held_scores')} for r in completed],
            'source_sha256': sha(__file__), 'splits_sha256': sha(SPLITS),
            'new_solver_calls': 0, 'new_feature_acquisitions': 0,
            'scope': 'Repeated2022 development. Query0 optimistic, original42 measured acquisition fee retained for40. No independent/deployment claim.'})
    except BaseException as error:
        status = 'failed'
        atomic(OUT / 'failure.json', {'status': status, 'error': repr(error),
            'completed_fits': len(completed), 'reward': None})
        raise
    finally:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        atomic(OUT / 'resources.json', {'status': status,
            'physical_parent_CPU_s': time.process_time() - cpu,
            'physical_child_CPU_s': usage.ru_utime + usage.ru_stime - initial.ru_utime - initial.ru_stime,
            'wall_s': time.monotonic() - wall, 'completed_fits': len(completed), 'new_solver_calls': 0})


if __name__ == '__main__':
    main()
