"""R42: D-dependent mean left unconstrained; test odd force-direction prior."""
from concurrent.futures import ProcessPoolExecutor
import json
import os
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

OUT = DATA / 'mechanism_R42_20261111'


def complement(x):
    """Exact coordinate transform; no solver-time symmetry is asserted."""
    y = np.array(x, copy=True)
    y[:, 13], y[:, 14] = x[:, 14], x[:, 13]
    y[:, 15], y[:, 16] = x[:, 16], x[:, 15]
    y[:, 32:37], y[:, 37:42] = x[:, 37:42], x[:, 32:37]
    return y


def fit_job(job):
    mode, kind, fold, x, costs, val_x, held_x, held_ids = job
    cpu, wall = time.process_time(), time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R42 fold600wall')))
    signal.alarm(600)
    try:
        if kind == 'mean':
            target = (costs[:, 0] - costs[:, 1:].mean(axis=1)) / 1200
            leaf = 4
        else:
            target = (costs[:, 2] - costs[:, 1]) / 2400
            if kind == 'odd_prior':
                x, target = np.r_[x, complement(x)], np.r_[target, -target]
            else:
                assert kind == 'no_prior'
                x, target = np.r_[x, x], np.r_[target, target]
            leaf = 8
        with threadpool_limits(limits=1):
            model = ExtraTreesRegressor(n_estimators=256, max_depth=12,
                min_samples_leaf=leaf, max_features=.8, n_jobs=1,
                random_state=20261111 + fold)
            model.fit(x, target)
            vp, hp = model.predict(val_x), model.predict(held_x)
            odd_error = None
            if kind == 'odd_prior':
                vt, ht = model.predict(complement(val_x)), model.predict(complement(held_x))
                vp, hp = (vp - vt) / 2, (hp - ht) / 2
                odd_error = float(max(np.max(np.abs(vp + (vt - model.predict(val_x)) / 2)),
                                      np.max(np.abs(hp + (ht - model.predict(held_x)) / 2))))
                assert odd_error <= 1e-12
        return {'mode': mode, 'kind': kind, 'fold': fold, 'held_ids': held_ids,
            'validation_component': vp, 'held_component': hp, 'training_rows': len(x),
            'nodes': sum(t.tree_.node_count for t in model.estimators_),
            'maximum_model_oddness_error': odd_error,
            'CPU_s': time.process_time() - cpu, 'wall_s': time.monotonic() - wall}
    finally:
        signal.alarm(0)


def main():
    wall, cpu = time.monotonic(), time.process_time()
    initial = resource.getrusage(resource.RUSAGE_CHILDREN)
    OUT.mkdir(exist_ok=False)
    atomic(OUT / 'owner.json', {'pid': os.getpid(), 'source_sha256': sha(__file__),
        'started_UTC': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'expected_fits': 42, 'remote_R35_untouched': True,
        'reflection_penalty_not_physical_labels': True})
    completed, status = [], 'running'
    try:
        keys, _, costs, _, _, _ = load()
        x, valid = load_views(keys)[0]['linear42']
        assert valid.all() and x.shape == (4719, 42)
        tx = complement(x)
        assert np.array_equal(complement(tx), x)
        fixed = np.all(x.astype(np.float32) == tx.astype(np.float32), axis=1)
        oracle = costs.min(axis=1)
        oracle[fixed] = costs[fixed][:, :2].min(axis=1)
        headroom = float(100 * (costs[:, 0].sum() - oracle.sum()) / costs[:, 0].sum())
        gate = int((~fixed).sum()) >= 50 and headroom >= .5
        atomic(OUT / 'information_gate.json', {'passed': gate,
            'nonfixed_vectors': int((~fixed).sum()), 'fixed_vectors': int(fixed.sum()),
            'sign_constrained_population_oracle_pct': headroom,
            'involution_exact': True, 'new_physical_labels': 0})
        if not gate:
            status = 'complete_low_information_no_fits'
            atomic(OUT / 'summary.json', {'status': status, 'completed_fits': 0, 'reward': None})
            return
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
        jobs, validation_costs = [], {}
        for mode, assignment in folds.items():
            for fold in np.unique(assignment):
                held, train, val = assignment == fold, (assignment != fold) & ~inner, (assignment != fold) & inner
                assert not set(iso[held]) & set(iso[train | val])
                assert not set(fine[train]) & set(fine[val])
                validation_costs[(mode, int(fold))] = costs[val]
                for kind in ('mean', 'odd_prior', 'no_prior'):
                    jobs.append((mode, kind, int(fold), x[train], costs[train],
                                 x[val], x[held], np.flatnonzero(held)))
        with ProcessPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(fit_job, job) for job in jobs]
            for future in futures:
                r = future.result(timeout=max(1, 1200 - (time.monotonic() - wall)))
                completed.append(r)
                name = f"{r['mode']}_{r['kind']}_{r['fold']}"
                np.savez_compressed(OUT / (name + '.npz'), held_ids=r['held_ids'],
                    validation_component=r['validation_component'], held_component=r['held_component'])
                atomic(OUT / 'progress.json', {'completed_fits': len(completed),
                    'expected_fits': 42, 'wall_s': time.monotonic() - wall})
        fitted = {(r['mode'], r['kind'], r['fold']): r for r in completed}
        fee = np.array([float(r['first_acquisition_CPU_s']) + float(r['second_acquisition_CPU_s']) for r in recovery])
        failed = np.array([r['still_failed_paidD'] == 'True' for r in recovery])
        assert failed.sum() == 25
        scores, paired, cuts = {}, {}, []
        output = [{'instance_key': k} for k in keys]
        for mode, assignment in folds.items():
            group, paid_by_kind = fine if mode == 'fine' else coarse, {}
            for kind in ('odd_prior', 'no_prior', 'cached_seed0', 'cached_min3'):
                if kind.startswith('cached_'):
                    variant = 'seed0' if kind == 'cached_seed0' else 'min3'
                    name = mode + '_linear42_' + variant
                    actions = np.array([ACTIONS.index(r[name + '_action']) for r in original])
                    enabled = np.array([old_summary['scores'][name]['cuts'][f]['margin_PAR2_s'] is not None for f in assignment])
                else:
                    actions, enabled = np.zeros(len(keys), int), np.zeros(len(keys), bool)
                    for fold in np.unique(assignment):
                        u, v = fitted[(mode, 'mean', fold)], fitted[(mode, kind, fold)]
                        assert np.array_equal(u['held_ids'], v['held_ids'])
                        vp = 1200 * np.c_[u['validation_component'] + v['validation_component'],
                                         u['validation_component'] - v['validation_component']]
                        hp = 1200 * np.c_[u['held_component'] + v['held_component'],
                                         u['held_component'] - v['held_component']]
                        vc = validation_costs[(mode, int(fold))]
                        cut = calibrate(vp, vc, np.zeros(len(vc)))
                        ids = u['held_ids']
                        actions[ids], enabled[ids] = choose(hp, cut), cut is not None
                        cuts.append({'mode': mode, 'kind': kind, 'fold': int(fold), 'margin_PAR2_s': cut})
                raw = costs[np.arange(len(keys)), actions]
                action = actions.copy()
                action[failed & enabled] = 0
                paid = timed_cost(costs[np.arange(len(keys)), action], fee * enabled, 600)
                s = evaluate(costs[:, 0], paid, group, coarse, mode)
                s['free_unmasked'] = evaluate(costs[:, 0], raw, group, coarse, mode)
                s['actions'] = {a: int((action == j).sum()) for j, a in enumerate(ACTIONS)}
                s['query_unmeasured_optimistic_zero'] = True
                scores[mode + '_' + kind], paid_by_kind[kind] = s, paid
                for i, row in enumerate(output):
                    row[mode + '_' + kind + '_action'] = ACTIONS[action[i]]
                    row[mode + '_' + kind + '_PAR2'] = float(paid[i])
                print(f"R42 {mode}_{kind}: gain={s['gain_pct']:+.6f}%, solved={s['solved']}", flush=True)
            for control in ('no_prior', 'cached_seed0', 'cached_min3'):
                paired[mode + '_over_' + control] = evaluate(paid_by_kind[control],
                    paid_by_kind['odd_prior'], group, coarse, mode)
        passed = True
        for mode in ('coarse', 'fine'):
            s = scores[mode + '_odd_prior']
            ci = s.get('exact_eight_block_95_pct', s['block_interval_95_pct'])
            passed &= s['gain_pct'] >= 2 and ci[0] > 0
            for control in ('no_prior', 'cached_seed0', 'cached_min3'):
                s = paired[mode + '_over_' + control]
                ci = s.get('exact_eight_block_95_pct', s['block_interval_95_pct'])
                passed &= s['gain_pct'] > 0 and ci[0] >= 0
        write_csv(OUT / 'predictions.csv', output)
        status = 'complete'
        atomic(OUT / 'summary.json', {'status': status, 'parents': len(keys),
            'completed_fits': len(completed), 'primary_screen_passed': bool(passed),
            'scores': scores, 'paired_comparisons': paired, 'cuts': cuts,
            'fit_records': [{k: v for k, v in r.items()
                if k not in ('held_ids', 'validation_component', 'held_component')} for r in completed],
            'source_sha256': sha(__file__), 'splits_sha256': sha(SPLITS),
            'new_solver_calls': 0, 'new_feature_acquisitions': 0,
            'scope': 'Repeated2022 development; reflection is a hypothesis-based training penalty, not measured labels. D-dependent mean not reflected. Query0 optimistic, no deployment/confirmation.'})
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
