"""Fixed block-scaled linear readout for frozen square-root graph patterns."""

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler


def fit(capacity, x, costs, seed):
    # The seed argument is deliberately unused: this readout is deterministic.
    basic = Pipeline([("scale", StandardScaler()),
                      ("clip", FunctionTransformer(np.clip, kw_args={"a_min": -10, "a_max": 10}))])
    transformers = [("basic", basic, slice(0, 43))]
    weights = {"basic": 1 / np.sqrt(43)}
    if x.shape[1] > 43:
        transformers.append(("patterns", StandardScaler(with_std=False), slice(43, x.shape[1])))
        # Four unit-norm Hellinger histograms, so this block has norm about1.
        weights["patterns"] = .5
    preprocess = ColumnTransformer(transformers, transformer_weights=weights, sparse_threshold=0)
    model = Pipeline([("input", preprocess),
                      ("relative_PAR2", Ridge(alpha=10., solver="cholesky"))])
    model.fit(x, (costs[:, :1] - costs[:, 1:]) / 1200)
    return model
