"""R54: reuse frozen R13B OOF actions; compose already measured CNF/query fees."""
import time

START_CPU, START_WALL = time.process_time(), time.monotonic()

import fcntl
import json
import os
from pathlib import Path
import resource
import signal

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS, calibrate, choose
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, DATA, ROOT, load, read_csv, write_csv

OUT = DATA / 'mechanism_R54_paid_classifier_20261111'
SPEC = ROOT / 'configs/anniversary2022_baseline/R54_paid_classifier_20261111.json'
VARIANTS = ('mean3', 'min3')


def main():
    OUT.mkdir(exist_ok=False)
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R54 five-minute replay bound')))
    signal.alarm(300)
    status = 'running'
    with (OUT / 'owner.lock').open('w') as lock, threadpool_limits(limits=1):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        atomic(OUT / 'owner.json', {'PID': os.getpid(), 'source_sha256': sha(__file__),
            'spec_sha256': sha(SPEC), 'new_fits': 0, 'new_solver_calls': 0,
            'started_UTC': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        try:
            spec = json.loads(SPEC.read_text())
            for relative, expected in spec['input_sha256'].items():
                assert sha(ROOT / relative) == expected, relative
            keys, _, costs, _, _, _ = load()
            assert len(keys) == 4719
            classifier_dir = DATA / 'mechanism_R13b_20261111'
            classifier = read_csv(classifier_dir / 'predictions.csv')
            cls_summary = json.loads((classifier_dir / 'summary.json').read_text())
            regression = read_csv(DATA / 'mechanism_R12_20261111/predictions.csv')
            reg_summary = json.loads((DATA / 'mechanism_R12_20261111/summary.json').read_text())
            recovery = read_csv(DATA / 'linear42_cpu_recovery_20261111/predictions.csv')
            splits = read_csv(SPLITS)
            diagnostic = read_csv(DATA / 'mechanism_R11_20261111/predictions.csv')
            assert all([r['instance_key'] for r in table] == keys for table in
                (classifier, regression, recovery, splits, diagnostic))
            assert np.allclose(costs[:, 0], [float(r['D_PAR2']) for r in classifier], rtol=0, atol=1e-12)
            folds = np.array([int(r['diagnostic_iso_fold']) for r in diagnostic])
            inner = np.array([r['inner_validation'] == 'True' for r in splits])
            iso = np.array([r['iso_group'] for r in splits])
            fine = np.array([r['fine_group'] for r in splits])
            coarse = np.array([r['coarse_group'] for r in splits])
            native = np.array([float(r['first_acquisition_CPU_s']) + float(r['second_acquisition_CPU_s']) for r in recovery])
            failed = np.array([r['still_failed_paidD'] == 'True' for r in recovery])
            assert failed.sum() == 25 and np.all(np.isfinite(native)) and native.min() >= 0
            checks, scores, selected, output = [], {}, {}, [{'instance_key': k} for k in keys]
            for variant in VARIANTS:
                name = 'iso_diagnostic_linear42_' + variant
                original_action = np.array([ACTIONS.index(r[name + '_action']) for r in classifier])
                query = np.array([float(r[name + '_decision_CPU_s']) for r in classifier])
                # Bind all original held predictions to original training/inner masks.
                for fold in range(5):
                    held, train, val = folds == fold, (folds != fold) & ~inner, (folds != fold) & inner
                    assert not set(iso[held]) & set(iso[train | val])
                    assert not set(fine[train]) & set(fine[val])
                    with np.load(classifier_dir / 'fold_arrays' / f'iso_diagnostic_linear42_{fold}.npz') as z:
                        assert np.array_equal(z['held_ids'], np.flatnonzero(held))
                        assert np.array_equal(z['validation_ids'], np.flatnonzero(val))
                        vp = z['validation_scores'].mean(axis=0) if variant == 'mean3' else z['validation_scores'].min(axis=0)
                        hp = z['held_scores'].mean(axis=0) if variant == 'mean3' else z['held_scores'].min(axis=0)
                    cut = cls_summary['scores'][name]['cuts'][fold]['preference_score_margin']
                    assert cut == calibrate(vp, costs[val], np.zeros(val.sum()))
                    assert np.array_equal(original_action[held], choose(hp, cut))
                    checks.append({'variant': variant, 'fold': fold, 'original_inner_margin': cut,
                        'held_parents': int(held.sum()), 'original_actions_match': True})
                old_paid = timed_cost(costs[np.arange(len(keys)), original_action], query, 600)
                assert np.allclose(old_paid, [float(r[name + '_PAR2']) for r in classifier], rtol=0, atol=1e-12)
                assert np.isclose(assess(costs[:, 0], old_paid, iso, 600)['gain_pct'],
                    cls_summary['scores'][name]['gain_pct'], rtol=0, atol=1e-12)
                enabled = np.array([cls_summary['scores'][name]['cuts'][int(f)]['preference_score_margin'] is not None for f in folds])
                action = original_action.copy()
                action[enabled & failed] = 0
                # No query after acquisition failure; no fee refund after choosing D.
                fee = native * enabled + query * enabled * ~failed
                paid = timed_cost(costs[np.arange(len(keys)), action], fee, 600)
                selected[variant] = paid
                score = assess(costs[:, 0], paid, iso, 600)
                score.update(exact_eight_block_95_pct=exact_small_block_interval(costs[:, 0], paid, coarse),
                    actions={a: int((action == j).sum()) for j, a in enumerate(ACTIONS)},
                    native_logical_CPU_s=float((native * enabled).sum()),
                    query_logical_CPU_s=float((query * enabled * ~failed).sum()),
                    old_free_acquisition_gain_pct=cls_summary['scores'][name]['gain_pct'],
                    scope='Repeated2022 same-mixture development, not independent confirmation or same-host solver deployment')
                scores[variant] = score
                for i, row in enumerate(output):
                    row[variant + '_action'] = ACTIONS[action[i]]
                    row[variant + '_PAR2'] = float(paid[i])
                    row[variant + '_native_CPU_s'] = float(native[i] * enabled[i])
                    row[variant + '_query_CPU_s'] = float(query[i] * enabled[i] * ~failed[i])
                print(f'R54 {variant}: paid_gain={score["gain_pct"]:+.6f}%, solved={score["solved"]}', flush=True)

            # Exact existing best regressor control, with its own measured queries.
            name = 'iso_diagnostic_linear42_min3'
            action = np.array([ACTIONS.index(r[name + '_action']) for r in regression])
            query = np.array([float(r[name + '_decision_CPU_s']) for r in regression])
            enabled = np.array([reg_summary['scores'][name]['cuts'][int(f)]['margin_PAR2_s'] is not None for f in folds])
            action[failed & enabled] = 0
            control = timed_cost(costs[np.arange(len(keys)), action],
                native * enabled + query * enabled * ~failed, 600)
            assert np.allclose(control, [float(r['iso_diagnostic_PAR2']) for r in recovery], rtol=0, atol=1e-12)
            scores['original_regression_min3'] = assess(costs[:, 0], control, iso, 600)
            paired = {v: assess(control, selected[v], iso, 600) for v in VARIANTS}
            for v in VARIANTS:
                paired[v]['exact_eight_block_95_pct'] = exact_small_block_interval(control, selected[v], coarse)
            write_csv(OUT / 'predictions.csv', output)
            status = 'complete'
            atomic(OUT / 'summary.json', {'status': status, 'parents': len(keys), 'primary': 'mean3',
                'scores': scores, 'against_original_regression_min3': paired,
                'old_predictions_and_inner_cuts_reproduced': checks, 'new_fits': 0,
                'new_feature_extractions': 0, 'new_solver_calls': 0, 'short_search_calls': 0,
                'paid_D_acquisition_failures': int(failed.sum()), 'source_sha256': sha(__file__),
                'input_sha256': spec['input_sha256'], 'prospective_scope': spec['prospective_scope'],
                'selection_history': spec['selection_history'], 'trained_parameters_changed': False,
                'deployment_status': 'CNF extraction and old classifier OOF query fees composed across hosts; actual new classifier serving/solver run not performed'})
        except BaseException as error:
            status = 'failed'
            atomic(OUT / 'failure.json', {'status': status, 'error': repr(error), 'reward': None})
            raise
        finally:
            signal.alarm(0)
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            atomic(OUT / 'resources.json', {'status': status,
                'physical_parent_CPU_s': time.process_time() - START_CPU,
                'physical_child_CPU_s': usage.ru_utime + usage.ru_stime,
                'wall_s': time.monotonic() - START_WALL,
                'new_fits': 0, 'new_solver_calls': 0,
                'reused_native_and_runtime_costs_not_recharged_physically': True})


if __name__ == '__main__':
    main()
