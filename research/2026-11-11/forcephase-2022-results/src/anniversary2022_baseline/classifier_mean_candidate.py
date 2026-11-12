"""Executable CNF -> R13B mean3 classifier; no benchmark identity/labels at inference."""
import argparse
import json
from pathlib import Path
import time
import resource

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .linear42_only_vector import linear42_vector
from .recover_compact_cpu import extract
from .route_phase_2022 import SOLVER_FLAGS
from .structural_clusters import ACTIONS

SCHEMA = 'forcephase.linear42.cost_classifier.mean3.v1'


def preference_scores(payload, vectors):
    x = np.asarray(vectors, dtype=np.float32)
    if payload['schema'] != SCHEMA or payload['view'] != 'linear42' or x.ndim != 2 or x.shape[1] != 42 or not np.isfinite(x).all():
        raise ValueError('classifier feature/schema mismatch')
    if len(payload['models']) != 3:
        raise ValueError('classifier requires exactly3 frozen models')
    preferences = []
    for model in payload['models']:
        if model.n_features_in_ != 42 or not hasattr(model, 'predict_proba'):
            raise ValueError('regressor or wrong input width supplied as classifier')
        probability = np.zeros((len(x), 3))
        probability[:, model.classes_] = model.predict_proba(x)
        preferences.append(probability[:, 1:] - probability[:, :1])
    score = np.mean(preferences, axis=0)
    assert score.shape == (len(x), 2) and np.isfinite(score).all()
    return score


def predict_vector(payload, vector):
    score = preference_scores(payload, np.asarray(vector)[None])[0]
    cut = payload['cut']
    action = 0 if cut is None or score.max() <= cut else int(score.argmax()) + 1
    return action, score


def route_cnf(payload, policy, cnf):
    cpu, wall = time.process_time(), time.monotonic()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    first, retry = Path(policy['first_binary']), Path(policy['retry_binary'])
    if sha(first) != policy['first_binary_sha256'] or sha(retry) != policy['retry_binary_sha256']:
        raise ValueError('feature binary binding mismatch')
    receipt = {'action': 'D', 'status': 'feature_error', 'attempts': [], 'new_solver_calls': 0}
    vector = None
    if payload['cut'] is None:
        receipt['status'] = 'constant_D_no_acquisition'
    else:
        attempts = [extract(first, cnf)]
        if attempts[0]['native_exit'] == -24:
            attempts.append(extract(retry, cnf))
        receipt['attempts'] = [{k: v for k, v in a.items() if k != 'features'} for a in attempts]
        if attempts[-1]['native_exit'] == 0:
            vector = linear42_vector(attempts[-1]['features'])
            tick = time.process_time()
            action, score = predict_vector(payload, vector)
            receipt.update(status='ok', action=ACTIONS[action],
                mean_preference_score=score.tolist(), query_CPU_s=time.process_time() - tick)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt.update(routing_CPU_s=time.process_time() - cpu + after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
        wall_s=time.monotonic() - wall, solver_flags=list(SOLVER_FLAGS[receipt['action']]),
        scope='Static classifier serving only; no solver run or performance claim')
    return receipt, vector


def main(args):
    policy = json.loads(args.policy.read_text())
    model = args.policy.parent / policy['model_file']
    if policy['schema'] != SCHEMA or sha(model) != policy['model_sha256']:
        raise ValueError('classifier policy/model binding mismatch')
    if sha(__file__) != policy['router_source_sha256']:
        raise ValueError('classifier router source binding mismatch')
    tick = time.process_time()
    payload = joblib.load(model)
    load_cpu = time.process_time() - tick
    receipt, _ = route_cnf(payload, policy, args.cnf)
    receipt.update(model_load_CPU_s=load_cpu, model_sha256=policy['model_sha256'])
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--cnf', type=Path, required=True)
    with threadpool_limits(limits=1):
        main(parser.parse_args())
