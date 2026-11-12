"""Two frozen, small PAR2 policies; no teacher, IDs or held-out data used.

fit(X_train42, costs_train3, teacher_optional=None, algorithm='direct_cost')
returns JSON-compatible dict. predict(model, X42) returns action names;
predict_indices(model, X42) returns 0/1/2. Costs must be D/Fplus/Fminus PAR2
seconds. Fit on each authorized outer training fold. Do not reuse example
JSON as an out-of-fold policy. Inputs are original linear42, float32.
"""
import numpy as np

ACTIONS = ('D', 'Fplus', 'Fminus')
MAX_DEPTH = 4
MIN_LEAF = 40
# Legacy float-bin key bugs preclude a straightforward semantic interpretation.
# Exclusion fixed before either fit, not selected from outcome comparisons.
ALLOWED_FEATURES = tuple(i for i in range(42) if i not in (21, 26))
NAMES = (['log1p_variables_maxID', 'log1p_clauses', 'empty_fraction']
         + [f'clause_length_{i}_fraction' for i in range(1, 10)]
         + ['clause_length_10plus_fraction', 'positive_fraction',
            'negative_fraction', 'horn_fraction', 'invhorn_fraction']
         + [f'{p}_{s}' for p in ('balancecls', 'balancevars')
            for s in ('mean', 'variance', 'min', 'max', 'entropy')]
         + [f'{p}_{s}' for p in ('vcg_vdegree', 'hornvars', 'invhornvars')
            for s in ('log1p_mean', 'log1p_CV2', 'min_over_mean',
                      'log1p_max_over_mean', 'entropy')])
LOG_FEATURES = (0, 1, 27, 28, 30, 32, 33, 35, 37, 38, 40)


def _inputs(X):
    X = np.asarray(X, dtype=np.float32)
    if X.ndim != 2 or X.shape[1] != 42:
        raise ValueError('Expected n x 42 original linear42 matrix')
    return X


def _leaf(C):
    sums = C.sum(axis=0)
    # np.argmin gives D, then Fplus, then Fminus on exact ties.
    action = int(np.argmin(sums))
    return {'action_index': action, 'action': ACTIONS[action],
            'training_n': len(C), 'training_mean_costs': C.mean(axis=0).tolist()}


def _split_node(feature, threshold, left, right, C):
    # Exact same-action subtrees can be removed without changing predictions.
    if ('feature_index' not in left and 'feature_index' not in right
            and left['action_index'] == right['action_index']):
        return _leaf(C)
    return {'feature_index': int(feature), 'feature': NAMES[feature],
            'threshold': float(threshold), 'left_operator': '<=',
            'threshold_natural_approx': float(np.expm1(threshold))
                if feature in LOG_FEATURES else float(threshold),
            'natural_name': NAMES[feature].replace('log1p_', ''),
            'left': left, 'right': right}


def fit(X_train42, costs_train3, teacher_optional=None, algorithm='direct_cost'):
    """Fit one of exactly two fixed candidates; teacher_optional is unused.

    direct_cost: enumerate all training adjacent-value cutpoints, greedily
    minimize sum of children's minimum total PAR2. Split only on strict gain.
    gain_regression: CART squared-error splits on actual [D-F+, D-F-], then
    choose minimum-cost action in each training leaf. This preserves margin
    information even when a split does not immediately change the best action.
    Both use <=4 conditions per path, <=16 leaves and min_leaf40.
    """
    X = _inputs(X_train42)
    C = np.asarray(costs_train3, dtype=np.float64)
    if C.shape != (len(X), 3) or not len(X):
        raise ValueError('Expected nonempty matching n x 3 PAR2 matrix')
    if not np.isfinite(X).all() or not np.isfinite(C).all() or (C < 0).any():
        raise ValueError('Training features/costs must be finite; costs nonnegative')
    if algorithm == 'direct_cost':
        def grow(ids, depth):
            c = C[ids]
            leaf = _leaf(c)
            if depth >= MAX_DEPTH or len(ids) < 2 * MIN_LEAF:
                return leaf
            total = c.sum(axis=0)
            best_score = float(total.min())
            best = None
            # Feature and cutpoint ordering deterministically break ties.
            for feature in ALLOWED_FEATURES:
                order = np.argsort(X[ids, feature], kind='stable')
                values = X[ids[order], feature]
                cuts = np.flatnonzero(values[:-1] < values[1:]) + 1
                cuts = cuts[(cuts >= MIN_LEAF) & (len(ids)-cuts >= MIN_LEAF)]
                if not len(cuts):
                    continue
                cumulative = np.cumsum(c[order], axis=0)[cuts-1]
                scores = cumulative.min(axis=1) + (total-cumulative).min(axis=1)
                k = int(np.argmin(scores))
                if scores[k] < best_score - 1e-8:
                    best_score = float(scores[k])
                    cut = int(cuts[k])
                    threshold = (float(values[cut-1]) + float(values[cut])) / 2
                    best = feature, threshold, ids[order[:cut]], ids[order[cut:]]
            if best is None:
                return leaf
            f, t, a, b = best
            return _split_node(f, t, grow(a, depth+1), grow(b, depth+1), c)
        tree = grow(np.arange(len(X)), 0)
    elif algorithm == 'gain_regression':
        from sklearn.tree import DecisionTreeRegressor
        gains = C[:, [0]] - C[:, 1:]
        estimator = DecisionTreeRegressor(max_depth=MAX_DEPTH,
            min_samples_leaf=MIN_LEAF, random_state=20261111)
        estimator.fit(X[:, ALLOWED_FEATURES], gains)
        t = estimator.tree_
        def convert(node, ids):
            if t.feature[node] < 0:
                return _leaf(C[ids])
            f = ALLOWED_FEATURES[t.feature[node]]
            threshold = float(t.threshold[node])
            mask = X[ids, f].astype(np.float64) <= threshold
            return _split_node(f, threshold,
                convert(t.children_left[node], ids[mask]),
                convert(t.children_right[node], ids[~mask]), C[ids])
        tree = convert(0, np.arange(len(X)))
    else:
        raise ValueError('algorithm must be direct_cost or gain_regression')
    return {'schema': 'forcephase.interpretable_cost_tree.v1',
            'algorithm': algorithm, 'max_depth': MAX_DEPTH,
            'max_leaves': 16, 'min_samples_leaf': MIN_LEAF,
            'allowed_feature_indices': list(ALLOWED_FEATURES),
            'excluded_legacy_entropy_indices': [21, 26],
            'input_cast': 'float32; compare thresholds in float64',
            'actions': list(ACTIONS), 'teacher_used': False,
            'invalid_row_action': 'D', 'tree': tree,
            'features': [{'index': i, 'name': n,
                'transform': 'log1p' if i in LOG_FEATURES else 'identity',
                'eligible': i in ALLOWED_FEATURES} for i, n in enumerate(NAMES)]}


def predict_indices(model, X):
    X = _inputs(X)
    result = np.zeros(len(X), dtype=np.int8)
    ids = np.flatnonzero(np.isfinite(X).all(axis=1))
    def visit(node, rows):
        if 'feature_index' not in node:
            result[rows] = node['action_index']
            return
        left = X[rows, node['feature_index']].astype(np.float64) <= node['threshold']
        visit(node['left'], rows[left])
        visit(node['right'], rows[~left])
    visit(model['tree'], ids)
    return result


def predict(model, X):
    return np.asarray(ACTIONS)[predict_indices(model, X)]


def rules(model):
    """Export all mutually exclusive leaves as JSON-compatible conjunctions."""
    result = []
    def walk(node, path):
        if 'feature_index' not in node:
            result.append(dict(node, conditions=path))
            return
        base = {k: node[k] for k in ('feature_index', 'feature', 'threshold',
                'threshold_natural_approx', 'natural_name')}
        walk(node['left'], path + [dict(base, operator='<=')])
        walk(node['right'], path + [dict(base, operator='>')])
    walk(model['tree'], [])
    return result
