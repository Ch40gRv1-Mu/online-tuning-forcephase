"""R36 same-capacity direct-cost trees: fixed-grid greedy versus horizon2."""
import numpy as np
from .interpretable_cost_tree import _leaf

QUANTILES = np.arange(1, 8)/8
MIN_LEAF = 40
MAX_DEPTH = 4
EPSILON = 1e-8


def candidate_grid(x):
    out = []
    for feature in range(x.shape[1]):
        values = x[:, feature].astype(np.float64)
        for threshold in np.unique(np.quantile(values, QUANTILES)):
            count = int((values <= threshold).sum())
            if MIN_LEAF <= count <= len(x)-MIN_LEAF:
                out.append((feature, float(threshold)))
    return out


def _first_strict_best(scores, baseline):
    best, value = None, float(baseline)
    for j, score in enumerate(scores):
        if score < value-EPSILON:
            best, value = j, float(score)
    return best


def fit(x, costs, names, algorithm):
    assert algorithm in {'greedy', 'horizon2'}
    x = np.asarray(x, dtype=np.float32)
    c = np.asarray(costs, dtype=np.float64)
    assert x.ndim == 2 and c.shape == (len(x), 3) and len(names) == x.shape[1]
    assert np.isfinite(x).all() and np.isfinite(c).all() and (c >= 0).all()
    candidates = candidate_grid(x)
    masks = np.column_stack([x[:, f].astype(np.float64) <= t for f, t in candidates]) if candidates else np.zeros((len(x), 0), bool)
    diagnostics = []
    checked = 0

    def grow(ids, depth):
        nonlocal checked
        values, mask = c[ids], masks[ids]
        leaf = _leaf(values)
        if depth >= MAX_DEPTH or len(ids) < 2*MIN_LEAF or not candidates:
            return leaf
        counts = mask.sum(axis=0)
        admissible = (counts >= MIN_LEAF) & (counts <= len(ids)-MIN_LEAF)
        if not admissible.any():
            return leaf
        a = mask.astype(np.float64)
        total = values.sum(axis=0)
        left_cost = a.T @ values
        immediate = left_cost.min(axis=1)+(total-left_cost).min(axis=1)
        scores = immediate.copy()
        baseline = float(total.min())
        if algorithm == 'horizon2' and MAX_DEPTH-depth >= 2:
            intersections = a.T @ a
            ll = np.stack([a.T @ (a*values[:, action, None]) for action in range(3)], axis=-1)
            lr = left_cost[:, None, :]-ll
            rl = left_cost[None, :, :]-ll
            rr = total-left_cost[:, None, :]-left_cost[None, :, :]+ll
            valid_left = (intersections >= MIN_LEAF) & (counts[:, None]-intersections >= MIN_LEAF)
            valid_right = (counts[None, :]-intersections >= MIN_LEAF) & (
                len(ids)-counts[:, None]-counts[None, :]+intersections >= MIN_LEAF)
            best_left = np.minimum(left_cost.min(axis=1),
                np.where(valid_left, ll.min(axis=2)+lr.min(axis=2), np.inf).min(axis=1))
            best_right = np.minimum((total-left_cost).min(axis=1),
                np.where(valid_right, rl.min(axis=2)+rr.min(axis=2), np.inf).min(axis=1))
            scores = best_left+best_right
            if depth == 0:
                # Check real training intersections against literal membership arithmetic.
                points = sorted({0, len(candidates)//2, len(candidates)-1})
                for root in points:
                    for child in points:
                        literal = mask[:, root] & mask[:, child]
                        assert intersections[root, child] == literal.sum()
                        assert np.allclose(ll[root, child], values[literal].sum(axis=0), rtol=1e-12, atol=1e-7)
                        checked += 1
        scores[~admissible] = np.inf
        selected = _first_strict_best(scores, baseline)
        if selected is None:
            return leaf
        feature, threshold = candidates[selected]
        left_ids = ids[mask[:, selected]]
        right_ids = ids[~mask[:, selected]]
        assert min(len(left_ids), len(right_ids)) >= MIN_LEAF
        diagnostics.append({'depth': depth, 'training_n': len(ids), 'feature': names[feature],
            'threshold': threshold, 'leaf_cost': baseline,
            'immediate_cost': float(immediate[selected]), 'preview_cost': float(scores[selected]),
            'zero_immediate_gateway': bool(immediate[selected] >= baseline-EPSILON)})
        left, right = grow(left_ids, depth+1), grow(right_ids, depth+1)
        if 'feature_index' not in left and 'feature_index' not in right and left['action_index'] == right['action_index']:
            return leaf
        return {'feature_index': feature, 'feature': names[feature], 'threshold': threshold,
                'left': left, 'right': right}

    model = {'schema': 'forcephase.R36.fixed_grid_cost_tree.v1', 'algorithm': algorithm,
        'tree': grow(np.arange(len(x)), 0), 'feature_names': names,
        'max_depth': MAX_DEPTH, 'max_leaves': 2**MAX_DEPTH, 'min_leaf': MIN_LEAF,
        'quantiles': QUANTILES.tolist(), 'fixed_training_grid_candidates': len(candidates),
        'preview_checks': checked, 'node_diagnostics': diagnostics, 'teacher_used': False}
    return model
