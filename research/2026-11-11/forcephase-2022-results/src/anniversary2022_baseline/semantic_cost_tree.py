"""R31 direct-cost algorithm, parameterized solely for R34 feature coordinates."""

import numpy as np
from .interpretable_cost_tree import _leaf


def fit(x, costs, names):
    x = np.asarray(x, dtype=np.float32)
    c = np.asarray(costs, dtype=np.float64)
    assert x.shape[0] == len(c) and c.shape[1] == 3 and len(names) == x.shape[1]
    assert np.isfinite(x).all() and np.isfinite(c).all()
    def grow(ids, depth):
        values_c = c[ids]
        leaf = _leaf(values_c)
        if depth >= 4 or len(ids) < 80:
            return leaf
        total = values_c.sum(axis=0)
        best_score, best = float(total.min()), None
        for feature in range(x.shape[1]):
            order = np.argsort(x[ids, feature], kind="stable")
            values = x[ids[order], feature]
            cuts = np.flatnonzero(values[:-1] < values[1:]) + 1
            cuts = cuts[(cuts >= 40) & (len(ids)-cuts >= 40)]
            if not len(cuts):
                continue
            cumulative = np.cumsum(values_c[order], axis=0)[cuts-1]
            scores = cumulative.min(axis=1) + (total-cumulative).min(axis=1)
            k = int(np.argmin(scores))
            if scores[k] < best_score - 1e-8:
                best_score, cut = float(scores[k]), int(cuts[k])
                threshold = (float(values[cut-1]) + float(values[cut]))/2
                best = feature, threshold, ids[order[:cut]], ids[order[cut:]]
        if best is None:
            return leaf
        f, threshold, a, b = best
        left, right = grow(a, depth+1), grow(b, depth+1)
        if "feature_index" not in left and "feature_index" not in right and left["action_index"] == right["action_index"]:
            return leaf
        return {"feature_index": f, "feature": names[f], "threshold": threshold,
                "left": left, "right": right}
    return {"schema": "forcephase.semantic_readable_cost_tree.v1", "tree": grow(np.arange(len(x)), 0),
            "feature_names": names, "max_depth": 4, "max_leaves": 16, "min_leaf": 40,
            "teacher_used": False, "input_cast": "float32; comparisons float64"}


def predict(model, x):
    x = np.asarray(x, dtype=np.float32)
    one = x.ndim == 1
    if one:
        x = x[None]
    result = np.zeros(len(x), dtype=np.int8)
    def walk(node, ids):
        if "feature_index" not in node:
            result[ids] = node["action_index"]
            return
        left = x[ids, node["feature_index"]].astype(np.float64) <= node["threshold"]
        walk(node["left"], ids[left]); walk(node["right"], ids[~left])
    walk(model["tree"], np.arange(len(x)))
    return int(result[0]) if one else result


def rules(model):
    output = []
    def walk(node, conditions):
        if "feature_index" not in node:
            output.append({**node, "conditions": conditions})
            return
        for child, op in (("left", "<="), ("right", ">")):
            walk(node[child], conditions + [{"feature": node["feature"], "operator": op, "threshold": node["threshold"]}])
    walk(model["tree"], [])
    assert len(output) <= 16 and max(len(r["conditions"]) for r in output) <= 4
    return output
