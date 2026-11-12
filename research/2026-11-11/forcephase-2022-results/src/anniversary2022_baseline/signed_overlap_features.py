"""Static signs of clause overlaps, with exact variable-marginal controls."""

import argparse
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from .collect_static_mechanism import collect
from .scc_quotient_features import normalize, parse


CAP = 2_000_000


def signature(inverse, pattern, groups):
    counts = np.bincount(4 * inverse + pattern, minlength=4 * groups).reshape(-1, 4).astype(float)
    frequency = counts.sum(axis=1)
    same_by_pattern = counts * (counts - 1) / 2
    same = same_by_pattern.sum(axis=1)
    opposed = counts[:, 0] * counts[:, 3] + counts[:, 1] * counts[:, 2]
    mixed = (counts[:, 0] * counts[:, 1] + counts[:, 0] * counts[:, 2] +
             counts[:, 1] * counts[:, 3] + counts[:, 2] * counts[:, 3])
    total = frequency * (frequency - 1) / 2
    assert np.allclose(same + opposed + mixed, total)
    repeated = frequency >= 2
    scale = max(total.sum(), 1)
    result = np.r_[
        counts.sum(axis=0) / max(frequency.sum(), 1), same_by_pattern.sum(axis=0) / scale,
        same.sum() / scale, opposed.sum() / scale, mixed.sum() / scale,
        np.mean(mixed[repeated] / total[repeated]) if repeated.any() else 0,
        np.mean(counts[repeated].max(axis=1) / frequency[repeated]) if repeated.any() else 0,
        (same_by_pattern[:, 0].sum() - same_by_pattern[:, 3].sum()) / max(same.sum(), 1),
        np.dot(mixed, (counts[:, 0] - counts[:, 3]) / np.maximum(frequency, 1)) / max(mixed.sum(), 1),
        np.log1p(groups * np.dot(mixed, mixed) / max(mixed.sum() ** 2, 1)),
        np.log1p(groups * np.dot(opposed, opposed) / max(opposed.sum() ** 2, 1)),
        np.mean((opposed[repeated] > 0) & (mixed[repeated] > 0)) if repeated.any() else 0]
    assert result.shape == (18,) and np.isfinite(result).all()
    return result, frequency


def shuffled_signs(nodes, n):
    variables = nodes // 2
    rng = np.random.default_rng(20261111)
    grouped = np.argsort(variables, kind="stable")
    shuffled = np.lexsort((rng.random(len(nodes)), variables))
    assert np.array_equal(variables[grouped], variables[shuffled])
    signs = nodes & 1
    control = np.empty_like(signs)
    control[shuffled] = signs[grouped]
    assert np.array_equal(np.bincount(variables, weights=control, minlength=n),
                          np.bincount(variables, weights=signs, minlength=n))
    return control


def extract(raw):
    nodes, clauses, m, n = parse(raw)
    nodes, clauses, widths, _ = normalize(nodes, clauses, m)
    starts = np.r_[0, widths.cumsum()]
    eligible = (widths >= 2) & (widths <= 8)
    emitted = int(np.sum(widths[eligible] * (widths[eligible] - 1) // 2))
    inventory = np.array([np.log1p(emitted), 0., 0., 0.,
                          widths[eligible].sum() / max(len(nodes), 1), float(emitted <= CAP)])
    observed, randomized = np.zeros(18), np.zeros(18)
    groups = 0
    if 0 < emitted <= CAP:
        left, right = [], []
        for k in range(2, 9):
            ids = np.flatnonzero(widths == k)
            if not len(ids):
                continue
            a, b = np.triu_indices(k, 1)
            left.append((starts[ids, None] + a).ravel())
            right.append((starts[ids, None] + b).ravel())
        left, right = np.concatenate(left), np.concatenate(right)
        assert len(left) == emitted
        pair = (nodes[left] // 2) * n + nodes[right] // 2
        unique, inverse = np.unique(pair, return_inverse=True)
        groups = len(unique)
        signs = nodes & 1
        control = shuffled_signs(nodes, n)
        observed, frequency = signature(inverse, 2 * signs[left] + signs[right], groups)
        randomized, control_frequency = signature(inverse, 2 * control[left] + control[right], groups)
        assert np.array_equal(frequency, control_frequency)
        inventory[1:4] = [np.log1p(groups), frequency[frequency >= 2].sum() / emitted, frequency.max() / emitted]
    return {"unsigned_overlap20": inventory, "signed_overlap38": np.r_[inventory, observed],
            "shuffled_sign38": np.r_[inventory, randomized]}, {
        "emitted_variable_pairs": emitted, "distinct_variable_pairs": groups,
        "pair_statistics_available": emitted <= CAP}


def check_semantics():
    raw = b"p cnf 2 4\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n"
    values, meta = extract(raw)
    signature_ = values["signed_overlap38"][6:]
    assert meta["emitted_variable_pairs"] == 4 and meta["distinct_variable_pairs"] == 1
    assert np.allclose(signature_[8:11], [0, 1 / 3, 2 / 3])
    return {"opposed_and_mixed_variable_pair_multiplicities": True,
            "per_variable_signed_degree_preserved": True, "solver_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        collect(args.out, extract, {"unsigned_overlap20": 6, "signed_overlap38": 24,
                                  "shuffled_sign38": 24}, check_semantics, __file__)
