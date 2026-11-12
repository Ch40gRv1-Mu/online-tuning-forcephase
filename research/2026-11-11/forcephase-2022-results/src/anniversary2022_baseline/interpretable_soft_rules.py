"""Bounded continuous min3-teacher distillation, two frozen candidates.

teacher_optional MUST be n x 2 conservative D-F predictions in PAR2 seconds
from teachers fitted only inside the current outer training set. Full3787
teacher predictions are permitted only for descriptive development examples,
never as labels for original outer-fold validation. This module fits no forest.
"""
import numpy as np

ACTIONS = ('D', 'Fplus', 'Fminus')
ALGORITHMS = ('soft_directional_asinh', 'soft_additive_raw')
MIN_LEAF = 40
ASINH_SCALE = 30.0
NAMES = (['log1p_variables_maxID', 'log1p_clauses', 'empty_fraction']
    + [f'clause_length_{i}_fraction' for i in range(1,10)]
    + ['clause_length_10plus_fraction', 'positive_fraction',
       'negative_fraction', 'horn_fraction', 'invhorn_fraction']
    + [f'{p}_{s}' for p in ('balancecls','balancevars')
       for s in ('mean','variance','min','max','entropy')]
    + [f'{p}_{s}' for p in ('vcg_vdegree','hornvars','invhornvars')
       for s in ('log1p_mean','log1p_CV2','min_over_mean',
                 'log1p_max_over_mean','entropy')])
LOG_FEATURES = (0,1,27,28,30,32,33,35,37,38,40)


def _matrix(X):
    X = np.asarray(X, dtype=np.float32)
    if X.ndim != 2 or X.shape[1] != 42:
        raise ValueError('Expected n x 42 original linear42 features')
    return X


def _serialize(estimator, output_index=None):
    t = estimator.tree_
    def convert(node):
        if t.feature[node] < 0:
            values = t.value[node].reshape(-1)
            score = np.zeros(2)
            if output_index is None:
                score[:] = values
            else:
                score[output_index] = values[0]
            return {'score': score.tolist(), 'training_n':int(t.n_node_samples[node])}
        f, cut = int(t.feature[node]), float(t.threshold[node])
        return {'feature_index':f, 'feature':NAMES[f], 'threshold':cut,
                'threshold_natural_approx':float(np.expm1(cut)) if f in LOG_FEATURES else cut,
                'left_operator':'<=', 'left':convert(t.children_left[node]),
                'right':convert(t.children_right[node])}
    return convert(0)


def fit(X_train42, costs_train3, teacher_optional=None,
        algorithm='soft_directional_asinh'):
    """Return JSON policy. Real costs are shape-checked, not optimized here.

    soft_directional_asinh: 2 depth4 trees (one per F), each <=16 leaves,
      predicting asinh(conservative_gain_seconds/30). Inverse sinh returns
      seconds for ordinary global margin calibration. No action labels.
    soft_additive_raw: initial mean plus exactly 4 depth3 two-output residual
      trees, each <=8 leaves, fixed learning rate1. All scores in seconds.
    Both retain all42 original fields, including explicitly marked legacy
    balance entropy fields; they are not interpreted as Shannon diversity.
    """
    from sklearn.tree import DecisionTreeRegressor
    X = _matrix(X_train42)
    C = np.asarray(costs_train3,dtype=float)
    if teacher_optional is None:
        raise ValueError('Train-only n x 2 teacher continuous gains are required')
    G = np.asarray(teacher_optional,dtype=float)
    if not len(X) or C.shape != (len(X),3) or G.shape != (len(X),2):
        raise ValueError('Expected nonempty matching X[n,42], costs[n,3], teacher[n,2]')
    if not np.isfinite(X).all() or not np.isfinite(C).all() or not np.isfinite(G).all():
        raise ValueError('Training inputs must be finite')
    if algorithm not in ALGORITHMS:
        raise ValueError('Unknown frozen algorithm')
    trees = []
    if algorithm == 'soft_directional_asinh':
        transformed = np.arcsinh(G/ASINH_SCALE)
        intercept = np.zeros(2)
        for action in range(2):
            est = DecisionTreeRegressor(max_depth=4,min_samples_leaf=MIN_LEAF,
                                        random_state=20261111+action)
            est.fit(X,transformed[:,action])
            trees.append({'coefficient':1.0,'output_index':action,
                          'tree':_serialize(est,action)})
        transform = '30*sinh(sum_score)'
        depths = [4,4]
    else:
        intercept = G.mean(axis=0)
        fitted = np.tile(intercept,(len(X),1))
        for stage in range(4):
            est = DecisionTreeRegressor(max_depth=3,min_samples_leaf=MIN_LEAF,
                                        random_state=20261111+stage)
            est.fit(X,G-fitted)
            fitted += est.predict(X)
            trees.append({'coefficient':1.0,'output_index':None,'tree':_serialize(est)})
        transform = 'identity'
        depths = [3,3,3,3]
    return {'schema':'forcephase.soft_rule_scores.v1','algorithm':algorithm,
        'teacher_target':'per-direction minimum of three outer-train-only D-F predictions, seconds',
        'teacher_fit_inside_this_module':False, 'costs_used_for_fit':False,
        'intercept':intercept.tolist(),'trees':trees,'score_to_PAR2_seconds':transform,
        'asinh_scale_seconds':ASINH_SCALE if algorithm=='soft_directional_asinh' else None,
        'default_margin_PAR2_s':0.0,'max_total_leaves':32,
        'max_depth_per_tree':depths,'min_samples_leaf':MIN_LEAF,
        'feature_count':42,'input_cast':'float32; thresholds compared in float64',
        'invalid_input_gains':[0.0,0.0],
        'features':[{'index':i,'name':name,
                     'transform':'log1p' if i in LOG_FEATURES else 'identity',
                     'legacy_non_Shannon_warning':i in (21,26)}
                    for i,name in enumerate(NAMES)]}


def predict_gains(model, X42):
    """n x 2 predicted D-F gains in original PAR2 seconds, never action labels."""
    X = _matrix(X42)
    good = np.isfinite(X).all(axis=1)
    scores = np.tile(np.asarray(model['intercept'],float),(len(X),1))
    for term in model['trees']:
        coefficient = term['coefficient']
        def visit(node, rows):
            if 'feature_index' not in node:
                scores[rows] += coefficient*np.asarray(node['score'])
                return
            left = X[rows,node['feature_index']].astype(np.float64)<=node['threshold']
            visit(node['left'],rows[left])
            visit(node['right'],rows[~left])
        visit(term['tree'],np.flatnonzero(good))
    if model['score_to_PAR2_seconds']=='30*sinh(sum_score)':
        scores = model['asinh_scale_seconds']*np.sinh(scores)
    scores[~good] = 0.0
    return scores


def predict_indices(model,X42):
    g = predict_gains(model,X42)
    return np.where(g.max(axis=1)>0,g.argmax(axis=1)+1,0).astype(np.int8)


def predict(model,X42):
    return np.asarray(ACTIONS)[predict_indices(model,X42)]


def rules(model):
    """Up to32 leaf conjunctions; choose one per tree then sum score vectors.

    For asinh policy, scores are transformed units, followed by 30*sinh.
    For additive policy, scores are PAR2 seconds. All intervals/weights explicit.
    """
    result=[]
    for j,term in enumerate(model['trees']):
        def visit(node,path):
            if 'feature_index' not in node:
                result.append({'tree_index':j,'conditions':path,
                    'coefficient':term['coefficient'],'score':node['score'],
                    'training_n':node['training_n'],
                    'score_space':'asinh(gain_seconds/30)' if model['asinh_scale_seconds'] else 'PAR2_seconds'})
                return
            base={k:node[k] for k in ('feature_index','feature','threshold','threshold_natural_approx')}
            visit(node['left'],path+[dict(base,operator='<=')])
            visit(node['right'],path+[dict(base,operator='>')])
        visit(term['tree'],[])
    return {'intercept':model['intercept'],'score_to_PAR2_seconds':model['score_to_PAR2_seconds'],
        'execution':'Select exactly one matching leaf per tree; add coefficient*score to intercept; apply output transform; choose largest positive F gain else D.',
        'leaf_rules':result}
