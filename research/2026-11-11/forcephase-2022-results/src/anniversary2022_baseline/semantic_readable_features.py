"""Fixed R34 semantic coordinates from the same pre-cast42 CNF statistics."""

import numpy as np
from .interpretable_cost_tree import ALLOWED_FEATURES, NAMES

BASE_NAMES = [NAMES[i] for i in ALLOWED_FEATURES]
EXTRA_NAMES = ["log_clause_to_variable_ID_range_ratio", "log_mean_clause_width",
    "log1p_nonHorn_clause_count", "log1p_nonInverseHorn_clause_count",
    "log1p_pure_positive_clause_count", "log1p_pure_negative_clause_count",
    "Horn_minus_inverseHorn_fraction", "pure_positive_minus_negative_fraction",
    "clause_minus_variable_mean_balance", "log1p_nonHorn_mean_width",
    "log1p_nonInverseHorn_mean_width", "log1p_nonHorn_per_variable_ID_range"]


def transform(values, view):
    x = np.asarray(values, dtype=np.float64)
    one = x.ndim == 1
    if one:
        x = x[None]
    assert x.ndim == 2 and x.shape[1] == 42 and np.isfinite(x).all()
    base = x[:, ALLOWED_FEATURES].astype(np.float32)
    if view == "raw40":
        return base[0] if one else base
    assert view == "semantic52"
    n, m = np.rint(np.expm1(x[:, 0])), np.rint(np.expm1(x[:, 1]))
    assert (n > 0).all() and (m > 0).all()
    literals = np.rint(n * np.expm1(x[:, 27]))
    horn, inverse, positive, negative = [np.rint(m * x[:, i]) for i in (15, 16, 13, 14)]
    horn_literals, inverse_literals = [np.rint(n * np.expm1(x[:, i])) for i in (32, 37)]
    assert (literals >= m).all()
    assert all(((v >= 0) & (v <= m)).all() for v in (horn, inverse, positive, negative))
    assert all(((v >= 0) & (v <= literals)).all() for v in (horn_literals, inverse_literals))
    nonhorn, noninverse = m - horn, m - inverse
    width_h = np.divide(literals - horn_literals, nonhorn, out=np.zeros(len(x)), where=nonhorn > 0)
    width_i = np.divide(literals - inverse_literals, noninverse, out=np.zeros(len(x)), where=noninverse > 0)
    extra = np.c_[np.log(m/n), np.log(literals/m), np.log1p(nonhorn), np.log1p(noninverse),
        np.log1p(positive), np.log1p(negative), np.round(x[:, 15]-x[:, 16], 8),
        np.round(x[:, 13]-x[:, 14], 8), np.round(x[:, 17]-x[:, 22], 8),
        np.log1p(width_h), np.log1p(width_i), np.log1p(nonhorn/n)]
    result = np.c_[base, extra.astype(np.float32)]
    assert result.shape == (len(x), 52) and np.isfinite(result).all()
    return result[0] if one else result


def feature_names(view):
    return BASE_NAMES if view == "raw40" else BASE_NAMES + EXTRA_NAMES
