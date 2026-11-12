"""R55 export existing classifiers; isolated real CNF route qualification after R53."""
import time

START_CPU, START_WALL = time.process_time(), time.monotonic()

import argparse
import fcntl
import json
import os
from pathlib import Path
import resource
import signal
import subprocess

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .classifier_mean_candidate import SCHEMA, preference_scores, predict_vector, route_cnf
from .common import sha
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS, calibrate
from .score_static_cost_classifier import scores as old_scores
from .score_static_seed_agreement import load_views
from .structural_clusters import ACTIONS, DATA, ROOT, load, read_csv

OUT = DATA / 'mechanism_R55_classifier_serving_20261111'
SPEC = ROOT / 'configs/anniversary2022_baseline/R55_classifier_serving_20261111.json'
R53 = DATA / 'mechanism_R53_streaming_20261111'


def inputs(spec):
    for relative, expected in spec['input_sha256'].items():
        assert sha(ROOT / relative) == expected, relative
    keys, _, costs, _, _, _ = load()
    split = read_csv(SPLITS)
    assert [r['instance_key'] for r in split] == keys
    x, valid = load_views(keys)[0]['linear42']
    assert valid.all() and len(keys) == 4719
    inner = np.array([r['inner_validation'] == 'True' for r in split])
    return keys, costs, x, inner


def export(spec):
    OUT.mkdir(exist_ok=False)
    keys, costs, x, inner = inputs(spec)
    original = ROOT / spec['old_model']
    old = joblib.load(original)
    models = old['models']
    assert old['view'] == 'linear42' and len(models) == 3
    assert all(m.n_features_in_ == 42 and m.n_estimators == 256 and
        m.max_depth == 12 and m.min_samples_leaf == 8 for m in models)
    for model in models:
        model.n_jobs = 1
    validation = np.asarray([old_scores(m, x[inner]) for m in models])
    assert old['cut'] == calibrate(validation.min(axis=0), costs[inner], np.zeros(inner.sum()))
    cut = calibrate(validation.mean(axis=0), costs[inner], np.zeros(inner.sum()))
    payload = {'schema': SCHEMA, 'models': models, 'view': 'linear42',
        'aggregation': 'mean_probability_difference', 'cut': cut,
        'original_model_sha256': sha(original), 'trained_parameters_changed': False}
    actual = preference_scores(payload, x[inner])
    assert np.allclose(actual, validation.mean(axis=0), rtol=0, atol=1e-15)
    path = OUT / 'model.joblib'
    joblib.dump(payload, path, compress=3)
    loaded = joblib.load(path)
    assert np.array_equal(preference_scores(loaded, x[inner]), actual)
    old_policy = json.loads((ROOT / spec['old_resource_policy']).read_text())
    policy = {k: old_policy[k] for k in ('first_binary', 'first_binary_sha256',
        'retry_binary', 'retry_binary_sha256', 'first_requested_CPU_s',
        'retry_requested_CPU_s', 'retry_only_on_exit', 'alarm_per_attempt_s', 'wrapper_per_attempt_s')}
    policy.update(schema=SCHEMA, model_file='model.joblib', model_sha256=sha(path),
        feature_source_sha256=sha(ROOT / 'src/anniversary2022_baseline/linear42_only_vector.py'),
        router_source_sha256=sha(ROOT / 'src/anniversary2022_baseline/classifier_mean_candidate.py'),
        feature_count=42, reused_models=3, new_fits=0,
        training_parents=int((~inner).sum()), inner_validation_parents=int(inner.sum()),
        classifier_score_margin=cut, score_units='class-score difference, not seconds',
        feature_failure='paid D, no classifier query after failure',
        decision='Average three classifier F-minus-D class scores; best F only above inner-fitted margin, else D',
        claim='Static candidate export; old OOF evidence is2.349987% paid PAR2, not a score of this fitted model on its own training inputs')
    atomic(OUT / 'policy.json', policy)
    fixtures = json.loads((ROOT / spec['old_fixtures']).read_text())['fixtures']
    index = {k: i for i, k in enumerate(keys)}
    expected = []
    for fixture in fixtures:
        action, score = predict_vector(loaded, x[index[fixture['association_key']]])
        expected.append({**fixture, 'reference_action': ACTIONS[action],
            'reference_preference_score': score.tolist()})
    atomic(OUT / 'fixtures.json', {'scope': 'Frozen earlier implementation fixtures, not a performance sample',
        'fixtures': expected})
    atomic(OUT / 'export.json', {'status': 'complete', 'source_sha256': sha(__file__),
        'spec_sha256': sha(SPEC), 'model_sha256': sha(path), 'model_bytes': path.stat().st_size,
        'new_fits': 0, 'trained_parameters_changed': False,
        'classifier_score_margin': cut, 'inner_predictions_match': int(inner.sum()),
        'real_CNF_route_status': 'NOT_EXECUTED_WAIT_FOR_R53_TERMINAL',
        'no_performance_scoring_of_full_development_model': True})


def qualify(spec):
    # Never overlap actual new native timing with the inherited feature owner.
    terminal = json.loads((R53 / 'resources.json').read_text())
    assert terminal['status'] in ('complete', 'failed')
    owner = json.loads((R53 / 'owner.json').read_text())
    process = subprocess.run(['ps', '-p', str(owner['pid']), '-o', 'command='], capture_output=True, text=True)
    assert 'src.anniversary2022_baseline.stream_clause_features' not in process.stdout, 'R53 owner still live'
    assert not (OUT / 'route_qualification.json').exists()
    keys, _, x, _ = inputs(spec)
    index = {k: i for i, k in enumerate(keys)}
    policy = json.loads((OUT / 'policy.json').read_text())
    model_path = OUT / policy['model_file']
    assert sha(model_path) == policy['model_sha256']
    payload = joblib.load(model_path)
    fixtures = json.loads((OUT / 'fixtures.json').read_text())['fixtures']
    receipts = []
    for fixture in fixtures:
        path = Path(fixture['path'])
        assert sha(path) == fixture['wire_sha256']
        receipt, vector = route_cnf(payload, policy, path)
        # Cached vectors only validate outputs; the actual router reads CNF alone.
        if receipt['status'] == 'ok':
            assert np.array_equal(vector.astype(np.float32), x[index[fixture['association_key']]].astype(np.float32))
            assert receipt['action'] == fixture['reference_action']
            assert np.allclose(receipt['mean_preference_score'], fixture['reference_preference_score'], rtol=0, atol=1e-12)
        else:
            assert receipt['status'] == 'feature_error' and receipt['action'] == 'D'
        if receipt['attempts']:
            assert len(receipt['attempts']) == (2 if receipt['attempts'][0]['native_exit'] == -24 else 1)
        receipts.append({'branch': fixture['branch'], 'association_key': fixture['association_key'], 'receipt': receipt})
        atomic(OUT / 'route_progress.json', {'completed': len(receipts), 'expected': len(fixtures), 'receipts': receipts})
    atomic(OUT / 'route_qualification.json', {'status': 'complete_actual_CNF_to_classifier_consistency',
        'receipts': receipts, 'new_solver_calls': 0, 'new_model_fits': 0,
        'actual_native_calls': sum(len(r['receipt']['attempts']) for r in receipts),
        'actual_retry_observed': any(len(r['receipt']['attempts']) == 2 for r in receipts),
        'scope': 'Implementation fidelity and measured serving expense only, not independent performance confirmation'})


def main(args):
    phase = args.phase
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R55 bounded phase300wall')))
    signal.alarm(300)
    spec = json.loads(SPEC.read_text())
    status = 'running'
    try:
        with threadpool_limits(limits=1):
            if phase == 'export':
                export(spec)
            else:
                with (R53 / 'owner.lock').open('a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    qualify(spec)
        status = 'complete'
    except BaseException as error:
        status = 'failed'
        if OUT.exists():
            atomic(OUT / f'{phase}_failure.json', {'status': 'failed', 'error': repr(error), 'reward': None})
        raise
    finally:
        signal.alarm(0)
        if OUT.exists():
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            atomic(OUT / f'{phase}_resources.json', {'status': status, 'phase': phase,
                'physical_parent_CPU_s': time.process_time() - START_CPU,
                'physical_child_CPU_s': usage.ru_utime + usage.ru_stime,
                'wall_s': time.monotonic() - START_WALL, 'new_fits': 0, 'new_solver_calls': 0})
    print(json.dumps({'phase': phase, 'status': status}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('export', 'qualify'))
    main(parser.parse_args())
