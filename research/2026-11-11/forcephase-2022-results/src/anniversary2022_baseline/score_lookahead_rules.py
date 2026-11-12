"""R36 complete original folds; no partial remote seed results or new SAT runs."""
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path
import resource
import signal
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .lookahead_cost_tree import fit
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS
from .recover_compact_cpu import ORIGINAL, OUT as RETRY
from .score_interpretable_two_percent import evaluate
from .score_static_seed_agreement import load_views
from .score_width_budget_recovery import timed_cost
from .semantic_cost_tree import predict, rules
from .semantic_readable_features import transform, feature_names
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv

OUT = DATA/'mechanism_R36_20261111'


def fit_fold(job):
    mode, algorithm, fold, x, c, train, held = job
    cpu = time.process_time()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('formal fold600wall limit')))
    signal.alarm(600)
    try:
        with threadpool_limits(limits=1):
            model = fit(x[train], c[train], feature_names('raw40'), algorithm)
            action = predict(model, x[held])
            leaf_rules = rules(model)
            assert all(r['training_n'] >= 40 for r in leaf_rules)
        return {'mode': mode, 'algorithm': algorithm, 'fold': fold, 'model': model,
                'held_ids': np.flatnonzero(held), 'actions': action, 'rules': leaf_rules,
                'CPU_s': time.process_time()-cpu, 'train_parents': int(train.sum())}
    finally:
        signal.alarm(0)


def main():
    wall, cpu = time.monotonic(), time.process_time()
    usage0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    OUT.mkdir(exist_ok=False)
    atomic(OUT/'owner.json', {'pid':os.getpid(), 'started_UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'source_sha256':sha(__file__), 'expected_fits':28, 'owner':'Current chat; no delegation',
        'no_automatic_resubmission':True, 'remote_R35_untouched':True})
    completed, status = [], 'running'
    try:
        keys, _, costs, _, _, _ = load()
        x, valid = load_views(keys)[0]['linear42']
        assert valid.all()
        x = transform(x, 'raw40')
        split = read_csv(SPLITS)
        old_iso = read_csv(DATA/'mechanism_R11_20261111/predictions.csv')
        assert all([r['instance_key'] for r in table] == keys for table in (split, old_iso))
        first = {k: json.loads((ORIGINAL/'records'/(k+'.json')).read_text()) for k in keys}
        retry = {f.stem: json.loads(f.read_text()) for f in (RETRY/'records').glob('*.json')}
        assert json.loads((RETRY/'completion.json').read_text())['status'] == 'complete'
        available = np.array([first[k]['status'] == 'ok' or (k in retry and retry[k]['status'] == 'ok') for k in keys])
        fees = np.array([first[k]['acquisition_CPU_s']+(retry[k]['retry_acquisition_CPU_s'] if k in retry else 0.) for k in keys])
        assert available.sum() == 4694
        qualification = {'parents': len(keys), 'available': int(available.sum()),
            'distinct_raw40_bundles': len(np.unique(x[available], axis=0)),
            'available_oracle_population_pp': float(100*(costs[:,0]-costs.min(axis=1))[available].sum()/costs[:,0].sum()),
            'new_native_calls': 0, 'new_solver_calls': 0}
        atomic(OUT/'input_qualification.json', qualification)
        assert qualification['distinct_raw40_bundles'] >= 50 and qualification['available_oracle_population_pp'] >= .5
        inner = np.array([r['inner_validation'] == 'True' for r in split])
        iso, coarse, fine = [np.array([r[k+'_group'] for r in split]) for k in ('iso', 'coarse', 'fine')]
        folds = {'iso_diagnostic': np.array([int(r['diagnostic_iso_fold']) for r in old_iso]),
                 **{m: np.array([int(r[m+'_fold']) for r in split]) for m in ('coarse', 'fine')}}
        jobs = []
        for mode in folds:
            for algorithm in ('greedy', 'horizon2'):
                for fold in np.unique(folds[mode]):
                    held = folds[mode] == fold
                    train = ~held & ~inner
                    assert not (set(iso[held]) & set(iso[train | (~held & inner)]))
                    assert not (set(fine[train]) & set(fine[~held & inner]))
                    jobs.append((mode, algorithm, int(fold), x, costs, train, held))
        with ProcessPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(fit_fold, j) for j in jobs]
            for future in futures:
                result = future.result(timeout=max(1, 1800-(time.monotonic()-wall)))
                completed.append(result)
                name = f"{result['mode']}_{result['algorithm']}_{result['fold']}"
                atomic(OUT/'fold_policies'/(name+'.json'), result['model'])
                atomic(OUT/'rules'/(name+'.json'), result['rules'])
                atomic(OUT/'progress.json', {'completed_fits':len(completed), 'total_fits':28,
                    'wall_s':time.monotonic()-wall, 'status':'running'})
        output = [{'instance_key':k} for k in keys]
        scores, selected = {}, {}
        with threadpool_limits(limits=1):
            for mode in folds:
                for algorithm in ('greedy', 'horizon2'):
                    action = np.zeros(len(keys), int)
                    active = np.zeros(len(keys), bool)
                    for result in completed:
                        if result['mode'] != mode or result['algorithm'] != algorithm:
                            continue
                        ids = result['held_ids']
                        action[ids] = result['actions']
                        node = result['model']['tree']
                        constantD = 'feature_index' not in node and node['action_index'] == 0
                        active[ids] = not constantD
                    free = costs[np.arange(len(keys)), action]
                    action[active & ~available] = 0
                    paid = timed_cost(costs[np.arange(len(keys)), action], fees*active, 600)
                    group = fine if mode == 'fine' else coarse
                    score = evaluate(costs[:,0], paid, group, coarse, mode)
                    score['free_unmasked'] = evaluate(costs[:,0], free, group, coarse, mode)
                    score['actions'] = {a:int((action == j).sum()) for j,a in enumerate(ACTIONS)}
                    score['query_CPU_unmeasured_optimistic_zero'] = True
                    score['constantD_skips_native_parents'] = int((~active).sum())
                    key = mode+'_'+algorithm
                    scores[key], selected[key] = score, paid
                    for i,row in enumerate(output):
                        row[key+'_action'] = ACTIONS[action[i]]
                        row[key+'_PAR2'] = float(paid[i])
                    print(f"R36 {key}: {score['gain_pct']:+.6f}%, solved={score['solved']}", flush=True)
            increments = {m:evaluate(selected[m+'_greedy'], selected[m+'_horizon2'],
                        fine if m == 'fine' else coarse, coarse, m) for m in folds}
        write_csv(OUT/'predictions.csv', output)
        primary = scores['iso_diagnostic_horizon2']
        status = 'complete'
        atomic(OUT/'summary.json', {'status':status, 'parents':len(keys), 'scores':scores,
            'paired_horizon2_over_greedy':increments, 'completed_fits':len(completed),
            'primary_two_percent_screen':bool(primary['gain_pct'] >= 2 and
               primary['exact_eight_block_95_pct'][0] > 0 and increments['iso_diagnostic']['gain_pct'] > 0),
            'fit_records':[{k:v for k,v in r.items() if k not in ('model','held_ids','actions','rules')} for r in completed],
            'qualification':qualification, 'new_solver_calls':0, 'new_native_calls':0,
            'source_sha256':sha(__file__), 'learner_source_sha256':sha(Path(__file__).with_name('lookahead_cost_tree.py')),
            'scope':'All4719 repeated2022, original folds, same40 inputs/capacity/grid. Actual prior acquisition fees, query optimistic0. No remote partial R35 outcomes, no independent or same-host deployment claim.'})
    except BaseException as exc:
        atomic(OUT/'failure.json', {'status':'failed', 'error':repr(exc),
                                  'completed_fits':len(completed), 'reward':None})
        raise
    finally:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        atomic(OUT/'resources.json', {'status':status, 'physical_parent_CPU_s':time.process_time()-cpu,
            'physical_child_CPU_s':usage.ru_utime+usage.ru_stime-usage0.ru_utime-usage0.ru_stime,
            'wall_s':time.monotonic()-wall, 'new_solver_calls':0, 'source_sha256':sha(__file__)})


if __name__ == '__main__':
    main()
