"""Static complete ternary parity motifs and their external signed interfaces."""

import argparse
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from .collect_static_mechanism import collect
from .scc_quotient_features import normalize, parse


def motifs(nodes, clauses, widths):
    ternary = np.flatnonzero(widths == 3)
    starts = np.r_[0, widths.cumsum()]
    if not len(ternary):
        return np.zeros((0, 3), dtype=int), np.zeros(0), np.zeros(len(widths), dtype=bool)
    triples = nodes[starts[ternary, None] + np.arange(3)]
    variables = triples // 2  # normalized literal order is increasing by variable
    groups, inverse = np.unique(variables, axis=0, return_inverse=True)
    pattern = (triples & 1) @ np.array([1, 2, 4])
    bitmap = np.zeros(len(groups), dtype=np.int64)
    np.bitwise_or.at(bitmap, inverse, np.left_shift(1, pattern))
    # Masks 105 and 150 contain all four even / odd forbidden assignments.
    accepted = (bitmap == 105) | (bitmap == 150)
    source = np.zeros(len(widths), dtype=bool)
    source[ternary] = accepted[inverse]
    target = np.where(bitmap[accepted] == 105, 1., -1.)
    return groups[accepted], target, source


def boundary(triples, target, nodes, clauses, widths, motif_clause, n):
    if not len(triples):
        return np.zeros(18)
    member = np.zeros(n, dtype=bool)
    member[triples.ravel()] = True
    selected = member[nodes // 2]
    external = ~motif_clause[clauses]
    weight = external / np.maximum(widths[clauses], 1)
    sign = 1. - 2. * (nodes & 1)
    mass = np.bincount(nodes // 2, weights=weight, minlength=n)
    demand = np.bincount(nodes // 2, weights=weight * sign, minlength=n)
    bias = demand / np.maximum(mass, 1e-30)
    degree = np.bincount(nodes // 2, minlength=n)
    starts = np.r_[0, widths.cumsum()]
    binary = np.flatnonzero(widths == 2)
    a, b = nodes[starts[binary]], nodes[starts[binary] + 1]
    crossing = member[a // 2] ^ member[b // 2]
    endpoint = np.where(member[a // 2], a, b)[crossing]
    inside = member[a // 2] & member[b // 2]
    scale = max(mass[member].sum(), 1e-30)
    exposed = mass > 0
    local_bias = bias[triples]
    product = np.prod(local_bias, axis=1)
    compatibility = target * product
    all_exposed = exposed[triples].all(axis=1)
    strong = np.abs(product) >= .125
    involved_degree = np.bincount(triples.ravel(), minlength=n)[member]
    centered_bias = bias[member] - bias[member].mean()
    log_degree = np.log1p(degree[member])
    covariance = np.mean(centered_bias * (log_degree - log_degree.mean()))
    result = np.array([
        crossing.sum() / max(3 * len(triples), 1), inside.mean() if len(inside) else 0,
        mass[member].sum() / max(mass.sum(), 1e-30), demand[member].sum() / scale,
        np.abs(demand[member]).sum() / scale, exposed[member].mean(),
        np.abs(bias[member]).mean(), covariance,
        np.mean(1. - 2. * (endpoint & 1)) if len(endpoint) else 0,
        np.mean((1. - 2. * (endpoint & 1)) * bias[endpoint // 2]) if len(endpoint) else 0,
        np.sum(weight * selected * (widths[clauses] > 2)) / scale,
        compatibility.mean(), np.abs(product).mean(),
        np.sum((compatibility < 0) & strong & all_exposed) / max(np.sum(strong & all_exposed), 1),
        all_exposed.mean(), bias[triples[:, -1]].mean(),
        np.var(local_bias, axis=1).mean(),
        np.log1p(involved_degree.var() / max(involved_degree.mean() ** 2, 1e-30))])
    assert result.shape == (18,) and np.isfinite(result).all()
    return result


def extract(raw):
    nodes, clauses, m, n = parse(raw)
    nodes, clauses, widths, _ = normalize(nodes, clauses, m)
    triples, target, motif_clause = motifs(nodes, clauses, widths)
    counts = np.bincount(triples.ravel(), minlength=n)
    present = counts > 0
    used = counts[present]
    inventory = np.array([np.log1p(len(triples)), present.sum() / max(n, 1),
                          target.mean() if len(target) else 0, motif_clause.mean() if len(widths) else 0,
                          np.log1p(used.var() / max(used.mean() ** 2, 1e-30)) if len(used) else 0,
                          used.max() / max(used.sum(), 1) if len(used) else 0])
    real = boundary(triples, target, nodes, clauses, widths, motif_clause, n)
    degree = np.bincount(nodes // 2, minlength=n)
    octave = np.floor(np.log2(np.maximum(degree, 1))).astype(int)
    permutation = np.arange(n)
    rng = np.random.default_rng(20261111)
    for block in np.unique(octave):
        ids = np.flatnonzero(octave == block)
        permutation[ids] = rng.permutation(ids)
    random = boundary(permutation[triples], target, nodes, clauses, widths, motif_clause, n)
    return {"motif_inventory20": inventory, "parity_interface38": np.r_[inventory, real],
            "random_interface38": np.r_[inventory, random]}, {
        "parity_triples": len(triples), "parity_variables": int(present.sum()),
        "parity_clauses": int(motif_clause.sum())}


def check_semantics():
    raw = b"p cnf 4 6\n1 2 3 0\n-1 -2 3 0\n-1 2 -3 0\n1 -2 -3 0\n1 4 0\n-2 4 0\n"
    nodes, clauses, m, n = parse(raw)
    nodes, clauses, widths, _ = normalize(nodes, clauses, m)
    triples, target, source = motifs(nodes, clauses, widths)
    assert triples.tolist() == [[0, 1, 2]] and target.tolist() == [1.]
    assert source.tolist() == [True, True, True, True, False, False]
    # Every one of the eight assignments matches the recognized parity.
    for mask in range(8):
        values = np.array([(mask >> i) & 1 for i in range(3)], dtype=bool)
        satisfaction = [np.any(values[nodes[3 * j:3 * j + 3] // 2] != (nodes[3 * j:3 * j + 3] & 1))
                        for j in range(4)]
        assert all(satisfaction) == (values.sum() % 2 == 1)
    result = boundary(triples, target, nodes, clauses, widths, source, n)
    assert np.isclose(result[0], 2 / 3) and result[8] == 0
    return {"complete_parity_and_sign_truth_table": True, "external_binary_boundary": True,
            "solver_calls": 0, "benchmark_assignments": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        collect(args.out, extract, {"motif_inventory20": 6, "parity_interface38": 24,
                                  "random_interface38": 24}, check_semantics, __file__)
