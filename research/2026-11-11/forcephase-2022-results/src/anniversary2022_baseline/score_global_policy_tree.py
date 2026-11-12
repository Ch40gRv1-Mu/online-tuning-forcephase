"""R48 fixed-grid joint depth-three policies, all original fourteen folds."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
import resource
import signal
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .global_depth3_tree import (fit_target, predicate_pool, predict, size,
                                 threshold_tree)
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS, QUANTILES
from .recover_compact_cpu import OUT as RETRY
from .score_interpretable_two_percent import evaluate
from .score_static_seed_agreement import SEEDS, load_views
from .score_width_budget_recovery import timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv

OUT = DATA / 'mechanism_R48_20261111'
TEACHERS = DATA / 'interpretable_soft_rules_20261111/teacher_targets'
TARGETS = ('true_cost', 'teacher_soft')
METHODS = ('greedy', 'global')
VARIANTS = ('raw', 'inner_margin')


def calibrate_tree(tree, x, costs, native, failed):
    """Only true inner costs calibrate; static leaves require no acquisition."""
    _, confidence = predict(tree, x)
    cuts = np.unique(np.maximum(0, np.r_[0, np.quantile(confidence, QUANTILES)]))
    best, best_cut, best_cost = {'action': 0}, None, float(costs[:, 0].sum())
    for cut in cuts:
        candidate = threshold_tree(tree, float(cut))
        actions, _ = predict(candidate, x)
        needs_input = 'action' not in candidate
        if needs_input:
            actions[failed] = 0
        fee = native + .003 * ~failed if needs_input else np.zeros(len(x))
        paid = timed_cost(costs[np.arange(len(x)), actions], fee, 600)
        if paid.sum() < best_cost - 1e-8:
            best, best_cut, best_cost = candidate, float(cut), float(paid.sum())
    return best, best_cut


def human_rules(tree):
    output = []
    def visit(t, conditions):
        if 'action' in t:
            output.append({'conditions': conditions, 'action': ACTIONS[t['action']],
                           'training_support': t.get('training_support')})
            return
        condition = {'feature_index': t['feature_index'], 'threshold': t['threshold']}
        visit(t['left'], conditions + [{**condition, 'operator': '<='}])
        visit(t['right'], conditions + [{**condition, 'operator': '>'}])
    visit(tree, [])
    assert len(output) <= 8 and all(len(r['conditions']) <= 3 for r in output)
    return output


def fit_job(job):
    mode, fold, x, targets, vx, hx, vc, native, failed, ids = job
    cpu, wall = time.process_time(), time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R48 fold360wall')))
    signal.alarm(360)
    try:
        with threadpool_limits(limits=1):
            predicates, B = predicate_pool(x)
            policies, diagnostics = {}, {}
            for target_name, target in zip(TARGETS, targets):
                models, certificate = fit_target(x, target, predicates, B, search_wall_s=120)
                diagnostics[target_name] = certificate
                for method, raw in models.items():
                    calibrated, cut = calibrate_tree(raw, vx, vc, native, failed)
                    for variant, tree in (('raw', raw), ('inner_margin', calibrated)):
                        name = f'{target_name}_{method}_{variant}'
                        actions, _ = predict(tree, hx)
                        policies[name] = {'tree': tree, 'held_actions': actions,
                            'requires_features': 'action' not in tree,
                            'margin_PAR2_s': cut if variant == 'inner_margin' else None,
                            'nodes': size(tree), 'rules': human_rules(tree)}
            return {'mode': mode, 'fold': fold, 'held_ids': ids, 'policies': policies,
                'certificates': diagnostics, 'train_parents': len(x), 'validation_parents': len(vx),
                'held_parents': len(hx), 'rule_fits': 4,
                'CPU_s': time.process_time() - cpu, 'wall_s': time.monotonic() - wall,
                'max_RSS_platform_units': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    finally:
        signal.alarm(0)


def interval(score):
    return score.get('exact_eight_block_95_pct', score['block_interval_95_pct'])


def main():
    wall, cpu = time.monotonic(), time.process_time()
    initial = resource.getrusage(resource.RUSAGE_CHILDREN)
    OUT.mkdir(exist_ok=False)
    source = Path(__file__).with_name('global_depth3_tree.py')
    atomic(OUT / 'owner.json', {'pid': os.getpid(), 'source_sha256': sha(__file__),
        'optimizer_source_sha256': sha(source), 'expected_jobs': 14, 'expected_rule_fits': 56,
        'started_UTC': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'remote_R35_untouched': True})
    completed, failures, status = [], [], 'running'
    try:
        keys, _, costs, _, _, _ = load()
        x, valid = load_views(keys)[0]['linear42']
        assert len(keys) == 4719 and valid.all() and np.isfinite(x).all()
        x = x.astype(np.float32)
        splits = read_csv(SPLITS)
        iso_rows = read_csv(DATA / 'mechanism_R11_20261111/predictions.csv')
        original = read_csv(DATA / 'mechanism_R12_20261111/predictions.csv')
        old_summary = json.loads((DATA / 'mechanism_R12_20261111/summary.json').read_text())
        recovery = read_csv(RETRY / 'predictions.csv')
        assert all([r['instance_key'] for r in rows] == keys for rows in (splits, iso_rows, original, recovery))
        native = np.array([float(r['first_acquisition_CPU_s']) + float(r['second_acquisition_CPU_s']) for r in recovery])
        failed = np.array([r['still_failed_paidD'] == 'True' for r in recovery])
        assert failed.sum() == 25 and np.isfinite(native).all() and (native >= 0).all()
        inner = np.array([r['inner_validation'] == 'True' for r in splits])
        iso, coarse, fine = [np.array([r[k + '_group'] for r in splits]) for k in ('iso', 'coarse', 'fine')]
        folds = {'iso_diagnostic': np.array([int(r['diagnostic_iso_fold']) for r in iso_rows]),
            **{m: np.array([int(r[m + '_fold']) for r in splits]) for m in ('coarse', 'fine')}}
        jobs, cache_receipts = [], []
        for mode, assignment in folds.items():
            for fold in np.unique(assignment):
                held, train, val = assignment == fold, (assignment != fold) & ~inner, (assignment != fold) & inner
                assert not set(iso[held]) & set(iso[train | val])
                assert not set(fine[train]) & set(fine[val])
                cache = TEACHERS / f'{mode}_{fold}.npz'
                receipt = json.loads(cache.with_suffix('.json').read_text())
                assert sha(cache) == receipt['cache_sha256'] and receipt['split_sha256'] == sha(SPLITS)
                assert receipt['aggregation'] == 'per-direction min3'
                with np.load(cache, allow_pickle=False) as stored:
                    assert stored['keys'].tolist() == keys
                    assert all(np.array_equal(stored[k], v) for k, v in (('train', train), ('val', val), ('held', held)))
                    assert np.array_equal(stored['seeds'], np.array(SEEDS) + fold)
                    soft_train = stored['conservative_gain_PAR2_s'][train]
                # Cached inner/held teacher outputs never enter fitting or calibration.
                teacher_target = np.column_stack((np.zeros(train.sum()), -soft_train))
                assert np.isfinite(teacher_target).all()
                cache_receipts.append({'mode': mode, 'fold': int(fold), 'cache_sha256': receipt['cache_sha256'],
                    'receipt_sha256': sha(cache.with_suffix('.json')), 'only_train_targets_used': True})
                jobs.append((mode, int(fold), x[train], (costs[train], teacher_target),
                    x[val], x[held], costs[val], native[val], failed[val], np.flatnonzero(held)))
        atomic(OUT / 'input_identity.json', {'matrix_sha256': sha(DATA / 'raw_data_20261110/matrix.csv'),
            'splits_sha256': sha(SPLITS), 'teacher_caches': cache_receipts,
            'true_targets': 'Original three-action complete PAR2, not surrogate labels',
            'teacher_targets': 'Training-only min3 predicted advantage; not new measured runtime',
            'inputs': 'Original42 float32; indices21/26 excluded from every predicate',
            'parents': len(keys), 'native_failures_paidD_if_nonconstant': int(failed.sum())})
        fit_wall = time.monotonic()
        with ProcessPoolExecutor(max_workers=4) as pool:
            pending = {pool.submit(fit_job, job): (job[0], job[1]) for job in jobs}
            for future in as_completed(pending, timeout=1800):
                mode, fold = pending[future]
                try:
                    r = future.result()
                    completed.append(r)
                    exported = {**r, 'held_ids': r['held_ids'].tolist(), 'policies': {
                        k: {a: b for a, b in v.items() if a != 'held_actions'} for k, v in r['policies'].items()}}
                    atomic(OUT / 'fold_policies' / f'{mode}_{fold}.json', exported)
                    np.savez_compressed(OUT / f'{mode}_{fold}.npz', held_ids=r['held_ids'],
                        **{name: p['held_actions'] for name, p in r['policies'].items()})
                except BaseException as error:
                    failures.append({'mode': mode, 'fold': int(fold), 'error': repr(error)})
                    atomic(OUT / f'{mode}_{fold}_failure.json', failures[-1])
                atomic(OUT / 'progress.json', {'completed_jobs': len(completed), 'failed_jobs': failures,
                    'expected_jobs': 14, 'completed_rule_fits': 4 * len(completed),
                    'wall_s': time.monotonic() - wall})
        assert not failures and len(completed) == 14, 'No partial outer feedback allowed'
        fit_wall = time.monotonic() - fit_wall
        names = [f'{t}_{m}_{v}' for t in TARGETS for m in METHODS for v in VARIANTS]
        output = [{'instance_key': k} for k in keys]
        scores, paired = {}, {}
        for mode, assignment in folds.items():
            group, paid_by_name = fine if mode == 'fine' else coarse, {}
            for name in (*names, 'cached_min3'):
                action, enabled = np.zeros(len(keys), int), np.zeros(len(keys), bool)
                if name == 'cached_min3':
                    old_name = mode + '_linear42_min3'
                    action = np.array([ACTIONS.index(r[old_name + '_action']) for r in original])
                    enabled = np.array([old_summary['scores'][old_name]['cuts'][f]['margin_PAR2_s'] is not None for f in assignment])
                else:
                    coverage = np.zeros(len(keys), int)
                    for r in completed:
                        if r['mode'] == mode:
                            ids, p = r['held_ids'], r['policies'][name]
                            action[ids], enabled[ids] = p['held_actions'], p['requires_features']
                            coverage[ids] += 1
                    assert (coverage == 1).all()
                raw = costs[np.arange(len(keys)), action]
                action[failed & enabled] = 0
                paid = timed_cost(costs[np.arange(len(keys)), action], native * enabled, 600)
                s = evaluate(costs[:, 0], paid, group, coarse, mode)
                s.update(free_unmasked=evaluate(costs[:, 0], raw, group, coarse, mode),
                    actions={a: int((action == j).sum()) for j, a in enumerate(ACTIONS)},
                    query_unmeasured_optimistic_zero=True, acquisition_parents=int(enabled.sum()),
                    logical_acquisition_CPU_s=float((native * enabled).sum()))
                scores[mode + '_' + name], paid_by_name[name] = s, paid
                for i, row in enumerate(output):
                    row[mode + '_' + name + '_action'] = ACTIONS[action[i]]
                    row[mode + '_' + name + '_PAR2'] = float(paid[i])
                print(f"R48 {mode}_{name}: gain={s['gain_pct']:+.6f}%, solved={s['solved']}", flush=True)
            for target in TARGETS:
                for variant in VARIANTS:
                    candidate = f'{target}_global_{variant}'
                    for control in (f'{target}_greedy_{variant}', 'cached_min3'):
                        paired[mode + '_' + candidate + '_over_' + control] = evaluate(
                            paid_by_name[control], paid_by_name[candidate], group, coarse, mode)
        milestone = {name: bool(scores['iso_diagnostic_' + name]['gain_pct'] >= 2 and
            interval(scores['iso_diagnostic_' + name])[0] > 0) for name in names}
        promotion = {}
        for target in TARGETS:
            candidate = f'{target}_global_inner_margin'
            passed = True
            for mode in ('coarse', 'fine'):
                s = scores[mode + '_' + candidate]
                passed &= s['gain_pct'] >= 2 and interval(s)[0] > 0
                for control in (f'{target}_greedy_inner_margin', 'cached_min3'):
                    s = paired[mode + '_' + candidate + '_over_' + control]
                    passed &= s['gain_pct'] > 0 and interval(s)[0] >= 0
            promotion[candidate] = bool(passed)
        write_csv(OUT / 'predictions.csv', output)
        status = 'complete'
        atomic(OUT / 'summary.json', {'status': status, 'parents': len(keys), 'completed_jobs': len(completed),
            'completed_rule_fits': 4 * len(completed), 'scores': scores, 'paired_comparisons': paired,
            'readable_mixed_two_pct_milestone': milestone, 'promotion': promotion,
            'certificates': [{k: v for k, v in r.items() if k not in ('held_ids', 'policies')} for r in completed],
            'all_target_fits_certified': all(c['certified_finite_grid_training_optimum'] for r in completed for c in r['certificates'].values()),
            'fit_stage_wall_s': fit_wall, 'source_sha256': sha(__file__), 'optimizer_source_sha256': sha(source),
            'new_solver_calls': 0, 'new_feature_extractions': 0, 'new_teacher_fits': 0,
            'scope': 'All4719 repeated2022 development. Native8+16 paid; query0 optimistic. Static leaves skip input acquisition. No end-to-end or independent confirmation.',
            'capacity': 'Depth<=3, <=8 leaves, support40; exact only if all finite-grid roots completed or lower bound attained.'})
    except BaseException as error:
        status = 'failed'
        atomic(OUT / 'failure.json', {'status': status, 'error': repr(error), 'completed_jobs': len(completed),
            'completed_rule_fits': 4 * len(completed), 'failed_jobs': failures, 'reward': None})
        raise
    finally:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        atomic(OUT / 'resources.json', {'status': status, 'completed_jobs': len(completed),
            'completed_rule_fits': 4 * len(completed), 'physical_parent_CPU_s': time.process_time() - cpu,
            'physical_child_CPU_s': usage.ru_utime + usage.ru_stime - initial.ru_utime - initial.ru_stime,
            'wall_s': time.monotonic() - wall, 'new_solver_calls': 0})


if __name__ == '__main__':
    main()
