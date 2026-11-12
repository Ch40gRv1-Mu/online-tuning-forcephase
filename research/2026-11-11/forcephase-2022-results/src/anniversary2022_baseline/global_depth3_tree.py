"""Finite-grid depth-three policy-tree optimization by exact joint counts."""
from copy import deepcopy
import time

import numpy as np

DEPTH = 3
MIN_LEAF = 40
QUANTILES = (.02, .05, .10, .25, .50, .75, .90, .95, .98)
FEATURES = tuple(i for i in range(42) if i not in (21, 26))


def simplify(tree):
    if 'action' in tree:
        return tree
    left, right = simplify(tree['left']), simplify(tree['right'])
    if 'action' in left and 'action' in right and left['action'] == right['action']:
        return {'action': left['action']}
    return {**tree, 'left': left, 'right': right}


def node(predicate, left, right):
    if predicate['feature_index'] is None:
        return left
    return simplify({'feature_index': predicate['feature_index'], 'threshold': predicate['threshold'],
                     'left': left, 'right': right})


def size(tree):
    return 1 if 'action' in tree else 1 + size(tree['left']) + size(tree['right'])


def predicate_pool(x):
    x = np.asarray(x, np.float32).astype(np.float64)
    predicates = [{'feature_index': None, 'threshold': None}]
    columns = [np.ones(len(x), bool)]
    seen = {np.packbits(columns[0]).tobytes()}
    for j in FEATURES:
        for q in QUANTILES:
            value = np.quantile(x[:, j], q)
            left = x[:, j] <= value
            if min(int(left.sum()), len(x) - int(left.sum())) < MIN_LEAF:
                continue
            threshold = float(x[left, j].max())
            left = x[:, j] <= threshold
            signature = np.packbits(left).tobytes()
            if signature in seen:
                continue
            seen.add(signature)
            predicates.append({'feature_index': j, 'threshold': threshold})
            columns.append(left)
    return predicates, np.column_stack(columns).astype(np.float64)


def predict(tree, x):
    x = np.asarray(x, np.float32).astype(np.float64)
    action, confidence = np.zeros(len(x), int), np.zeros(len(x))

    def visit(t, ids):
        if 'action' in t:
            action[ids], confidence[ids] = t['action'], t.get('confidence_PAR2_s', 0.)
        else:
            left = x[ids, t['feature_index']] <= t['threshold']
            visit(t['left'], ids[left]); visit(t['right'], ids[~left])
    visit(tree, np.arange(len(x)))
    return action, confidence


def bind_statistics(tree, x, target):
    """Training-only confidence; no validation/held outcomes enter these leaves."""
    x = np.asarray(x, np.float32).astype(np.float64)
    tree = deepcopy(tree)

    def visit(t, ids, depth):
        assert depth <= DEPTH
        if 'action' in t:
            n, a = len(ids), t['action']
            assert n == 0 or n >= MIN_LEAF
            assert n or a == 0
            t['training_support'] = n
            t['confidence_PAR2_s'] = float((target[ids, 0] - target[ids, a]).mean()) if n and a else 0.
            return
        assert t['feature_index'] in FEATURES
        left = x[ids, t['feature_index']] <= t['threshold']
        visit(t['left'], ids[left], depth + 1); visit(t['right'], ids[~left], depth + 1)
    visit(tree, np.arange(len(x)), 0)
    return tree


def threshold_tree(tree, cut):
    if cut is None:
        return {'action': 0}
    if 'action' in tree:
        a = tree['action'] if tree['action'] and tree['confidence_PAR2_s'] > cut else 0
        return {'action': int(a)}
    return simplify({**tree, 'left': threshold_tree(tree['left'], cut),
                     'right': threshold_tree(tree['right'], cut)})


def greedy(B, C, predicates):
    def fit(ids, depth):
        total = C[ids].sum(axis=0)
        leaf = {'action': int(total.argmin())}
        if not len(ids) or not depth:
            return leaf
        b = B[ids]
        counts, left = b.sum(axis=0), b.T @ C[ids]
        valid = ((counts == 0) | (counts >= MIN_LEAF)) & (
            (len(ids) - counts == 0) | (len(ids) - counts >= MIN_LEAF))
        scores = left.min(axis=1) + (total - left).min(axis=1)
        scores[~valid] = np.inf
        k = int(scores.argmin())
        if scores[k] >= total.min():
            return leaf
        select = b[:, k] > 0
        return node(predicates[k], fit(ids[select], depth - 1), fit(ids[~select], depth - 1))
    return fit(np.arange(len(B)), DEPTH)


def grams(B, C):
    p = B.shape[1]
    if not len(B):
        return np.zeros((p, p)), np.zeros((p, p, 3))
    count = B.T @ B
    cost = (B.T @ (B[:, :, None] * C[:, None, :]).reshape(len(B), 3 * p)).reshape(p, p, 3)
    return count, cost


def best_depth2(count, W, predicates):
    p, n = len(predicates), int(count[0, 0])
    if n == 0:
        return {'action': 0}, 0.
    if n < MIN_LEAF:
        return None, np.inf
    idx = np.arange(p)
    S, T, support = W[idx, idx], W[0, 0], np.diag(count)
    a, b = W, S[:, None] - W
    c, d = S[None, :] - W, T - S[:, None] - S[None, :] + W
    assert min(a.min(), b.min(), c.min(), d.min()) >= 0
    ca, cb = count, support[:, None] - count
    cc, cd = support[None, :] - count, n - support[:, None] - support[None, :] + count
    okay = lambda z: (z == 0) | (z >= MIN_LEAF)
    left, right = a.min(axis=2) + b.min(axis=2), c.min(axis=2) + d.min(axis=2)
    left[~(okay(ca) & okay(cb))], right[~(okay(cc) & okay(cd))] = np.inf, np.inf
    lt, rt = left.argmin(axis=1), right.argmin(axis=1)
    scores = left[idx, lt] + right[idx, rt]
    k = int(scores.argmin())
    if not np.isfinite(scores[k]):
        return None, np.inf
    tl, tr = int(lt[k]), int(rt[k])
    leaf = lambda cost: {'action': int(cost.argmin())}
    ltree = node(predicates[tl], leaf(a[k, tl]), leaf(b[k, tl]))
    rtree = node(predicates[tr], leaf(c[k, tr]), leaf(d[k, tr]))
    return node(predicates[k], ltree, rtree), float(scores[k])


def fit_target(x, target, predicates, B, search_wall_s=120):
    began, cpu = time.monotonic(), time.process_time()
    units = np.rint(target * 1e6)
    assert np.allclose(units / 1e6, target, rtol=0, atol=5.01e-7)
    offset = units.min(axis=1)
    C = units - offset[:, None]
    assert C.max(axis=1).sum() < 2 ** 52 and (C >= 0).all()
    tick = time.process_time()
    gtree = greedy(B, C, predicates)
    ga, _ = predict(gtree, x)
    gcost = float(C[np.arange(len(x)), ga].sum())
    greedy_cpu = time.process_time() - tick
    tick = time.process_time()
    full_count, full_cost = grams(B, C)
    gram_cpu = time.process_time() - tick
    idx = np.arange(B.shape[1])
    single = full_cost[idx, idx]
    stump_score = single.min(axis=1) + (full_cost[0, 0] - single).min(axis=1)
    root_order = [0] + sorted(range(1, len(predicates)), key=lambda j: (stump_score[j], j))
    best, bestcost = deepcopy(gtree), gcost
    search_started, search_cpu = time.monotonic(), time.process_time()
    completed, certified = 0, False
    for j in root_order:
        if time.monotonic() - search_started >= search_wall_s:
            break
        left = B[:, j] > 0
        if left.sum() <= len(B) / 2:
            lc, lw = grams(B[left], C[left]); rc, rw = full_count - lc, full_cost - lw
        else:
            rc, rw = grams(B[~left], C[~left]); lc, lw = full_count - rc, full_cost - rw
        ltree, lcost = best_depth2(lc, lw, predicates)
        rtree, rcost = best_depth2(rc, rw, predicates)
        if np.isfinite(lcost + rcost):
            candidate = node(predicates[j], ltree, rtree)
            value = lcost + rcost
            if value < bestcost or (value == bestcost and size(candidate) < size(best)):
                best, bestcost = candidate, value
        completed += 1
        if bestcost == 0:
            certified = True
            break
    certified = certified or completed == len(predicates)
    optimized_cpu = time.process_time() - search_cpu
    a, _ = predict(best, x)
    actual_cost = float(C[np.arange(len(x)), a].sum())
    assert actual_cost == bestcost and bestcost <= gcost and bestcost == round(bestcost)
    gtree, best = bind_statistics(gtree, x, target), bind_statistics(best, x, target)
    return {'greedy': gtree, 'global': best}, {
        'predicates': len(predicates), 'completed_roots': completed, 'candidate_roots': len(predicates),
        'certified_finite_grid_training_optimum': bool(certified),
        'certificate': 'all_roots' if completed == len(predicates) else ('oracle_bound_attained' if bestcost == 0 else 'bounded_incumbent'),
        'target_regret_units': bestcost, 'greedy_regret_units': gcost,
        'training_target_sum_s': (bestcost + offset.sum()) / 1e6,
        'greedy_training_target_sum_s': (gcost + offset.sum()) / 1e6,
        'absolute_optimality_gap_bound_units': 0. if certified else bestcost,
        'relative_gap_bound': 0. if certified else (1. if bestcost else 0.),
        'quantization_original_objective_gap_bound_s': len(x) * 1e-6,
        'global_nodes': size(best), 'greedy_nodes': size(gtree),
        'greedy_CPU_s': greedy_cpu, 'full_grams_CPU_s': gram_cpu, 'global_search_CPU_s': optimized_cpu,
        'CPU_s': time.process_time() - cpu, 'wall_s': time.monotonic() - began}
