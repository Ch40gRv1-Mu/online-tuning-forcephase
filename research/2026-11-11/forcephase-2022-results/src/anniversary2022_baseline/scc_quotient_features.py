"""Measure static signed-equivalence quotients; never assign or search."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from .common import sha, write
from .route_phase_2022 import load_formula
from .structural_clusters import DATA, ROOT, read_csv


def parse(raw):
    body, header = [], None
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(b"c"):
            continue
        if line.startswith(b"p"):
            fields = line.split()
            assert header is None and fields[:2] == [b"p", b"cnf"] and len(fields) == 4
            header = tuple(map(int, fields[2:]))
        else:
            body.append(line)
    assert header is not None
    tokens = np.fromstring(b" ".join(body).decode("ascii"), dtype=np.int64, sep=" ")
    ends = np.flatnonzero(tokens == 0)
    assert len(ends) == header[1] and len(tokens) and tokens[-1] == 0
    widths = np.diff(np.r_[-1, ends]) - 1
    literals = tokens[tokens != 0]
    ids, variables = np.unique(np.abs(literals), return_inverse=True)
    assert not len(ids) or ids[-1] <= header[0]
    nodes = 2 * variables + (literals < 0)
    clauses = np.repeat(np.arange(len(widths)), widths)
    return nodes, clauses, len(widths), len(ids)


def normalize(nodes, clauses, m):
    """Remove duplicate literals and tautologies without unit propagation."""
    order = np.lexsort((nodes, clauses))
    nodes, clauses = nodes[order], clauses[order]
    distinct = np.r_[True, (nodes[1:] != nodes[:-1]) | (clauses[1:] != clauses[:-1])]
    if not len(nodes):
        distinct = np.zeros(0, dtype=bool)
    duplicates = len(nodes) - int(distinct.sum())
    nodes, clauses = nodes[distinct], clauses[distinct]
    opposite = (clauses[1:] == clauses[:-1]) & (nodes[1:] // 2 == nodes[:-1] // 2)
    tautology = np.zeros(m, dtype=bool)
    tautology[clauses[1:][opposite]] = True
    widths = np.bincount(clauses, minlength=m)
    keep = ~tautology[clauses]
    remap = np.cumsum(~tautology) - 1
    return (nodes[keep], remap[clauses[keep]], widths[~tautology],
            {"tautology": tautology, "widths_before_tautology": widths, "duplicates": duplicates})


def representatives(nodes, widths, n):
    """Use the minimum-variable literal in each binary implication SCC."""
    starts = np.r_[0, widths.cumsum()]
    binary = np.flatnonzero(widths == 2)
    a, b = nodes[starts[binary]], nodes[starts[binary] + 1]
    edges = coo_matrix((np.ones(2 * len(a), dtype=np.int8),
                        (np.r_[a ^ 1, b ^ 1], np.r_[b, a])), shape=(2 * n, 2 * n)).tocsr()
    count, labels = connected_components(edges, directed=True, connection="strong")
    minima = np.full(count, 2 * n, dtype=np.int64)
    np.minimum.at(minima, labels, np.arange(2 * n))
    mapping = minima[labels]
    # Contradictory SCCs do not have a signed equivalence quotient. Retain
    # their original nodes; expose no satisfiability flag to the predictor.
    bad = labels[::2] == labels[1::2]
    conflicting = np.zeros(count, dtype=bool)
    conflicting[labels[::2][bad]] = True
    identity = conflicting[labels]
    mapping[identity] = np.arange(2 * n)[identity]
    assert np.array_equal(mapping[1::2], mapping[::2] ^ 1)
    assert np.array_equal(mapping[mapping], mapping)
    return mapping


def describe(nodes, clauses, widths):
    """36 matched raw/quotient features, with no formula identifier."""
    m = len(widths)
    if not len(nodes):
        return np.zeros(36)
    ids, variables = np.unique(nodes // 2, return_inverse=True)
    n, length = len(ids), len(nodes)
    positive = (nodes & 1) == 0
    pos = np.bincount(clauses, weights=positive, minlength=m)
    nonempty = widths > 0
    pp, nn = nonempty & (pos == widths), nonempty & (pos == 0)
    half = np.exp2(-np.minimum(widths, 60))
    average = widths.mean() if m else 0
    clause_view = [np.log1p(average), np.log1p(widths.var() / max(average ** 2, 1e-30)),
                   np.mean(widths == 1), np.mean(widths == 2), np.mean(widths == 3),
                   np.mean(widths > 3), np.mean(pp), np.mean(nn), np.mean(pos <= 1),
                   np.mean(widths - pos <= 1), np.dot(pp, half) / max(m, 1),
                   np.dot(nn, half) / max(m, 1), positive.mean(),
                   np.mean(pos / np.maximum(widths, 1))]
    degree = np.bincount(variables, minlength=n).astype(float)
    positive_degree = np.bincount(variables, weights=positive, minlength=n)
    weight = np.exp2(-np.minimum(np.maximum(widths[clauses] - 1, 0), 60))
    weighted_positive = np.bincount(variables, weights=weight * positive, minlength=n)
    weighted_negative = np.bincount(variables, weights=weight * ~positive, minlength=n)
    bias = (weighted_positive - weighted_negative) / np.maximum(weighted_positive + weighted_negative, 1e-30)
    pure_sign = (positive_degree == degree).astype(float) - (positive_degree == 0)
    bins = np.minimum(3, np.arange(n) * 4 // n)
    count = np.bincount(bins, minlength=4)
    bands = [np.bincount(bins, weights=x, minlength=4) / np.maximum(count, 1)
             for x in (bias, 1 - bias ** 2, pure_sign)]
    mass = np.bincount(bins, weights=degree, minlength=4) / length
    tail = [np.log1p(degree.var() / max(degree.mean() ** 2, 1e-30)),
            np.mean(pure_sign > 0), np.mean(pure_sign < 0), np.log1p(n / max(m, 1)),
            np.abs(bias).mean(), np.dot(bias, degree) / length]
    result = np.r_[clause_view, *bands, mass, tail]
    assert result.shape == (36,) and np.isfinite(result).all()
    return result


def extract(raw):
    nodes, clauses, m, n = parse(raw)
    nodes, clauses, widths, _ = normalize(nodes, clauses, m)
    before = describe(nodes, clauses, widths)
    if not n:
        return before, before.copy(), np.zeros(6)
    mapping = representatives(nodes, widths, n)
    substituted = mapping[nodes]
    qnodes, qclauses, qwidths, extra = normalize(substituted, clauses, len(widths))
    after = describe(qnodes, qclauses, qwidths)
    active_before = len(np.unique(nodes // 2))
    active_after = len(np.unique(qnodes // 2))
    metadata = np.array([
        (active_before - active_after) / max(active_before, 1),
        np.mean(mapping[::2] & 1), extra["tautology"].mean() if len(widths) else 0,
        extra["duplicates"] / max(len(nodes), 1), np.mean(substituted != nodes) if len(nodes) else 0,
        np.mean((widths > 2) & (extra["widths_before_tautology"] == 2) & ~extra["tautology"])
        if len(widths) else 0])
    assert np.isfinite(metadata).all()
    return before, after, metadata


def check_semantics():
    # Negated equivalence x=-y, with a longer clause whose first two
    # literals become duplicates. This checks signs, representative choice,
    # tautology removal and shortening on the extractor's actual path.
    raw = b"p cnf 3 3\n1 2 0\n-1 -2 0\n1 -2 3 0\n"
    nodes, clauses, m, n = parse(raw)
    nodes, clauses, widths, _ = normalize(nodes, clauses, m)
    mapping = representatives(nodes, widths, n)
    assert mapping.tolist() == [0, 1, 1, 0, 4, 5]
    qnodes, _, qwidths, extra = normalize(mapping[nodes], clauses, len(widths))
    assert qnodes.tolist() == [0, 4] and qwidths.tolist() == [2]
    assert extra["tautology"].tolist() == [True, True, False] and extra["duplicates"] == 1
    return {"negated_equivalence_minimum_representative": True,
            "tautology_and_duplicate_rewrite": True, "solver_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    checks = check_semantics()
    with np.load(DATA / "mechanism_R02_features_20261111/features.npz") as archive:
        keys, valid, base = archive["keys"], archive["valid"], archive["base14"]
        old_fee = archive["fee"]
    source = DATA / "cnf_graph_cnn_20261110/feature_receipts.jsonl"
    identities = {r["instance_key"]: r["raw_sha256"] for r in map(json.loads, source.read_text().splitlines())}
    panel = ROOT / "work/astra_structure_panel_20261110"
    files = {r["instance_key"]: panel / "cnf" / (r["case"] + ".cnf")
             for r in read_csv(panel / "association_only.csv")}
    args.out.mkdir(parents=True, exist_ok=False)

    def job(key):
        began = time.thread_time()
        path = ROOT / "work/signed_boundary_20261110/cnf_cache" / (key + ".cnf.gz")
        if not path.is_file():
            path = files[key]
        raw = load_formula(path)
        t = time.thread_time()
        if hashlib.sha256(raw).hexdigest() != identities[key]:
            raise ValueError("CNF bytes differ from verified input")
        identity_cpu = time.thread_time() - t
        values = extract(raw)
        return key, values, {"instance_key": key, "feature_CPU_s": time.thread_time() - began - identity_cpu,
                             "identity_CPU_s": identity_cpu, "raw_bytes": len(raw),
                             "collapsed_variable_share": float(values[2][0])}

    views = {"raw56": np.zeros((len(keys), 56)), "quotient56": np.zeros((len(keys), 56)),
             "paired92": np.zeros((len(keys), 92))}
    new_fee = np.zeros(len(keys))
    index = {key: i for i, key in enumerate(keys)}
    with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
        for count, (key, values, record) in enumerate(pool.map(job, keys[valid]), 1):
            i = index[key]
            raw, quotient, change = values
            common = np.r_[base[i], change]
            views["raw56"][i] = np.r_[common, raw]
            views["quotient56"][i] = np.r_[common, quotient]
            views["paired92"][i] = np.r_[common, raw, quotient]
            new_fee[i] = record["feature_CPU_s"]
            stream.write(json.dumps(record) + "\n")
            if count % 400 == 0:
                stream.flush()
                print(f"Extracted {count}/2843 static SCC quotients", flush=True)
            if time.monotonic() - start > 600:
                raise TimeoutError("static extraction exceeded ten minutes")
    np.savez_compressed(args.out / "features.npz", keys=keys, valid=valid, fee=old_fee + new_fee,
                        views=np.asarray(list(views)), **views)
    write(args.out / "collection.json", {"parents": len(keys), "qualified": int(valid.sum()),
          "new_profile_CPU_s": float(new_fee.sum()), "reused_component_CPU_s": float(old_fee.sum()),
          "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
          "new_solver_calls": 0, "short_search_calls": 0, "semantics_checks": checks,
          "source_sha256": sha(__file__), "verified_byte_receipts_sha256": sha(source),
          "pinned_decompose_sha256": sha(ROOT / "work/default_D_source_20261111/decompose.cpp"),
          "features_sha256": sha(args.out / "features.npz")})


if __name__ == "__main__":
    main()
