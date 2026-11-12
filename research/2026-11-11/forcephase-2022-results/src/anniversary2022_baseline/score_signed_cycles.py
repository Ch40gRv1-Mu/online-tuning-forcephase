"""R46 full-incidence forest parity; unchanged R44 scoring/cost engine."""
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
from .signed_cycle_profiles import collect
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS, calibrate, choose
from .recover_compact_cpu import OUT as RETRY
from .score_interpretable_two_percent import evaluate
from .score_static_seed_agreement import load_views
from .score_width_budget_recovery import timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv

OUT = DATA / 'mechanism_R46_20261111'


def fit_job(job):
    mode, kind, fold, x, y, vx, hx, vc, ids = job
    cpu, wall = time.process_time(), time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R46 fold600wall')))
    signal.alarm(600)
    try:
        with threadpool_limits(limits=1):
            model = ExtraTreesRegressor(n_estimators=256, max_depth=12, min_samples_leaf=4,
                max_features=.8, n_jobs=1, random_state=20261111 + fold)
            model.fit(x, y)
            vp, hp = model.predict(vx) * 1200, model.predict(hx) * 1200
            assert model.n_features_in_ == 99 and np.isfinite(vp).all() and np.isfinite(hp).all()
            cut = calibrate(vp, vc, np.zeros(len(vc)))
            action = choose(hp, cut)
        return {'mode': mode, 'kind': kind, 'fold': fold, 'held_ids': ids, 'actions': action,
            'validation_scores': vp, 'held_scores': hp, 'margin_PAR2_s': cut,
            'nodes': sum(t.tree_.node_count for t in model.estimators_),
            'CPU_s': time.process_time() - cpu, 'wall_s': time.monotonic() - wall}
    finally:
        signal.alarm(0)


def main():
    wall, cpu = time.monotonic(), time.process_time()
    initial = resource.getrusage(resource.RUSAGE_CHILDREN)
    OUT.mkdir(exist_ok=False)
    atomic(OUT / 'owner.json', {'pid': os.getpid(), 'source_sha256': sha(__file__),
        'profile_source_sha256': sha(__file__.replace('score_signed_cycles.py', 'signed_cycle_profiles.py')),
        'started_UTC': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'expected_profiles': 2325, 'expected_fits': 42, 'remote_R35_untouched': True})
    completed, status = [], 'running'
    try:
        keys, eligible, valid, informative, views, profile_fee = collect(OUT)
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        collection_cost = {'physical_parent_CPU_s': time.process_time() - cpu,
            'physical_child_CPU_s': after.ru_utime + after.ru_stime - initial.ru_utime - initial.ru_stime,
            'wall_s': time.monotonic() - wall}
        atomic(OUT / 'collection_resources.json', collection_cost)
        bound_keys, _, costs, _, _, _ = load()
        assert keys == bound_keys
        original_x, original_valid = load_views(keys)[0]['linear42']
        assert original_valid.all() and np.allclose(views['joint'][:, :42], original_x, rtol=0, atol=1e-12)
        headroom = float(100 * (costs[:, 0] - costs.min(axis=1))[informative].sum() / costs[:, 0].sum())
        passed = bool(informative.sum() >= 50 and headroom >= .5)
        atomic(OUT / 'information_gate.json', {'passed': passed, 'informative': int(informative.sum()),
            'informative_population_oracle_pct': headroom, 'parents': len(keys)})
        if not passed:
            status = 'complete_low_information_no_fits'
            atomic(OUT / 'summary.json', {'status': status, 'reward': None, 'completed_fits': 0})
            return
        splits = read_csv(SPLITS)
        iso_rows = read_csv(DATA / 'mechanism_R11_20261111/predictions.csv')
        original = read_csv(DATA / 'mechanism_R12_20261111/predictions.csv')
        old_summary = json.loads((DATA / 'mechanism_R12_20261111/summary.json').read_text())
        recovery = read_csv(RETRY / 'predictions.csv')
        assert all([r['instance_key'] for r in table] == keys for table in (splits, iso_rows, original, recovery))
        inner = np.array([r['inner_validation'] == 'True' for r in splits])
        iso, coarse, fine = [np.array([r[k + '_group'] for r in splits]) for k in ('iso', 'coarse', 'fine')]
        folds = {'iso_diagnostic': np.array([int(r['diagnostic_iso_fold']) for r in iso_rows]),
                 **{m: np.array([int(r[m + '_fold']) for r in splits]) for m in ('coarse', 'fine')}}
        jobs = []
        for mode, assignment in folds.items():
            for fold in np.unique(assignment):
                held, train, val = assignment == fold, (assignment != fold) & ~inner & valid, (assignment != fold) & inner & valid
                assert not set(iso[held]) & set(iso[train | val])
                assert not set(fine[train]) & set(fine[val])
                target = (costs[train][:, [0]] - costs[train][:, 1:]) / 1200
                for kind, x in views.items():
                    jobs.append((mode, kind, int(fold), x[train], target, x[val], x[held & valid],
                                 costs[val], np.flatnonzero(held & valid)))
        fit_wall = time.monotonic()
        with ProcessPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(fit_job, job) for job in jobs]
            for future in futures:
                r = future.result(timeout=max(1, 1200 - (time.monotonic() - fit_wall)))
                completed.append(r)
                np.savez_compressed(OUT / f"{r['mode']}_{r['kind']}_{r['fold']}.npz",
                    held_ids=r['held_ids'], validation_scores=r['validation_scores'], held_scores=r['held_scores'])
                atomic(OUT / 'progress.json', {'stage': 'scoring', 'completed_fits': len(completed),
                    'expected_fits': 42, 'wall_s': time.monotonic() - wall})
        native = np.array([float(r['first_acquisition_CPU_s']) + float(r['second_acquisition_CPU_s']) for r in recovery])
        failed = np.array([r['still_failed_paidD'] == 'True' for r in recovery])
        assert failed.sum() == 25
        scores, paired = {}, {}
        output = [{'instance_key': k} for k in keys]
        for mode, assignment in folds.items():
            group, paid_by_kind = fine if mode == 'fine' else coarse, {}
            for kind in (*views, 'cached_min3'):
                if kind == 'cached_min3':
                    name = mode + '_linear42_min3'
                    action = np.array([ACTIONS.index(r[name + '_action']) for r in original])
                    enabled = np.array([old_summary['scores'][name]['cuts'][f]['margin_PAR2_s'] is not None for f in assignment])
                    extra = np.zeros(len(keys))
                else:
                    action, enabled = np.zeros(len(keys), int), np.zeros(len(keys), bool)
                    for r in completed:
                        if r['mode'] == mode and r['kind'] == kind:
                            ids = r['held_ids']
                            action[ids], enabled[assignment == r['fold']] = r['actions'], r['margin_PAR2_s'] is not None
                    extra = profile_fee[kind] * ~failed
                raw = costs[np.arange(len(keys)), action]
                action[failed & enabled] = 0
                if kind != 'cached_min3':
                    action[~valid] = 0
                paid = timed_cost(costs[np.arange(len(keys)), action], (native + extra) * enabled, 600)
                s = evaluate(costs[:, 0], paid, group, coarse, mode)
                s['free_unmasked'] = evaluate(costs[:, 0], raw, group, coarse, mode)
                s['actions'] = {a: int((action == j).sum()) for j, a in enumerate(ACTIONS)}
                s['query_unmeasured_optimistic_zero'] = True
                s['profile_fee_logical_CPU_s'] = float((extra * enabled).sum())
                scores[mode + '_' + kind], paid_by_kind[kind] = s, paid
                for i, row in enumerate(output):
                    row[mode + '_' + kind + '_action'] = ACTIONS[action[i]]
                    row[mode + '_' + kind + '_PAR2'] = float(paid[i])
                print(f"R46 {mode}_{kind}: gain={s['gain_pct']:+.6f}%, solved={s['solved']}", flush=True)
            for candidate, controls in [('joint', ('decoupled', 'marginal', 'cached_min3')),
                                        ('marginal', ('cached_min3',))]:
                for control in controls:
                    paired[mode + '_' + candidate + '_over_' + control] = evaluate(
                        paid_by_kind[control], paid_by_kind[candidate], group, coarse, mode)
        promotion = {}
        for candidate in ('joint', 'marginal'):
            passed = True
            for mode in ('coarse', 'fine'):
                s = scores[mode + '_' + candidate]
                ci = s.get('exact_eight_block_95_pct', s['block_interval_95_pct'])
                passed &= s['gain_pct'] >= 2 and ci[0] > 0
                controls = ('decoupled', 'marginal', 'cached_min3') if candidate == 'joint' else ('cached_min3',)
                for control in controls:
                    s = paired[mode + '_' + candidate + '_over_' + control]
                    ci = s.get('exact_eight_block_95_pct', s['block_interval_95_pct'])
                    passed &= s['gain_pct'] > 0 and ci[0] >= 0
            promotion[candidate] = bool(passed)
        write_csv(OUT / 'predictions.csv', output)
        status = 'complete'
        atomic(OUT / 'summary.json', {'status': status, 'parents': len(keys), 'eligible': int(eligible.sum()),
            'feature_errors': int((~valid).sum()), 'completed_fits': len(completed),
            'promotion': promotion, 'scores': scores, 'paired_comparisons': paired,
            'fit_records': [{k: v for k, v in r.items() if k not in
                ('held_ids', 'actions', 'validation_scores', 'held_scores')} for r in completed],
            'source_sha256': sha(__file__), 'splits_sha256': sha(SPLITS),
            'new_solver_calls': 0, 'scope': 'Repeated2022 development. Profile+native composed measured fees, query0 optimistic; no same-host deployment/confirmation.'})
    except BaseException as error:
        status = 'failed'
        atomic(OUT / 'failure.json', {'status': status, 'error': repr(error),
            'completed_fits': len(completed), 'reward': None})
        raise
    finally:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        atomic(OUT / 'resources.json', {'status': status, 'completed_fits': len(completed),
            'physical_parent_CPU_s': time.process_time() - cpu,
            'physical_child_CPU_s': usage.ru_utime + usage.ru_stime - initial.ru_utime - initial.ru_stime,
            'wall_s': time.monotonic() - wall, 'new_solver_calls': 0})


if __name__ == '__main__':
    main()
