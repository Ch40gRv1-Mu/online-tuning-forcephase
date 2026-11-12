"""Phase-conditioned critical-clause dependencies, never a SAT search."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import breadth_first_order, connected_components
from threadpoolctl import threadpool_limits

from .common import sha, write
from .global_signed_response import prepare
from .literal_color_features import rewire
from .route_phase_2022 import load_formula
from .structural_clusters import DATA, ROOT, read_csv


def entropy(p):
    p = p[p > 0]
    return float(-p @ np.log(p)) if len(p) else 0.


def graph(nodes, clause, widths, n, phase):
    positive = (nodes & 1) == 0
    satisfied = positive if phase else ~positive
    count = np.bincount(clause, weights=satisfied, minlength=len(widths)).astype(int)
    root = (count == 0) & (widths > 0)
    critical = (count == 1) & (widths >= 2)
    blocked_clause = (count == 1) & (widths == 1)
    source = np.full(len(widths), -1, int)
    selected = critical[clause] & satisfied
    source[clause[selected]] = nodes[selected] // 2
    target = critical[clause] & ~satisfied
    rows, cols = source[clause[target]], nodes[target] // 2
    outcount = np.bincount(source[critical], minlength=n).astype(float)
    values = 1. / np.maximum(widths[clause[target]] - 1, 1) / np.maximum(outcount[rows], 1)
    transition = coo_matrix((values, (rows, cols)), shape=(n, n)).tocsr()
    assert np.allclose(np.asarray(transition.sum(axis=1)).ravel(), outcount > 0)
    root_edge = root[clause]
    demand = np.bincount(nodes[root_edge] // 2,
                         weights=1. / widths[clause[root_edge]], minlength=n).astype(float)
    demand /= max(demand.sum(), 1e-30)
    blocked = np.bincount(nodes[blocked_clause[clause]] // 2, minlength=n) > 0
    _, labels = connected_components(transition, directed=True, connection="strong")
    sizes = np.bincount(labels)
    cycle = (sizes[labels] > 1) | (transition.diagonal() > 0)
    inter = labels[rows] != labels[cols]
    outgoing, incoming = np.zeros(len(sizes), bool), np.zeros(len(sizes), bool)
    outgoing[labels[rows[inter]]] = True
    incoming[labels[cols[inter]]] = True
    local = np.array([root.mean() if len(root) else 0,
                      critical.mean() if len(critical) else 0, blocked.mean() if n else 0,
                      np.mean(demand > 0) if n else 0,
                      demand @ np.log1p(outcount), entropy(demand) / np.log(max(n, 2)),
                      np.log1p(outcount.mean()) if n else 0, demand @ blocked])
    return transition, (rows, cols), demand, blocked, outcount, labels, sizes, cycle, outgoing, incoming, local


def flow(transition, demand, deadline):
    transpose = transition.T.tocsr()
    q = demand.copy()
    if not demand.any():
        return q, 0, 0.
    for iteration in range(1, 513):
        updated = .05 * demand + .95 * (transpose @ q)
        if np.abs(updated - q).sum() <= 1e-9:
            q = updated
            break
        q = updated
        if time.thread_time() > deadline:
            raise TimeoutError("critical-clause feature exceeded per-formula CPU budget")
    else:
        raise ArithmeticError("critical-clause flow failed to converge in512 iterations")
    residual = np.abs(q - .05 * demand - .95 * (transpose @ q)).sum()
    assert residual <= 2e-9 and np.isfinite(q).all() and q.min(initial=0) >= -1e-12
    return q, iteration, float(residual)


def global_fields(data, uniform, deadline):
    transition, (rows, cols), original, blocked, outcount, labels, sizes, cycle, outgoing, incoming, _ = data
    n = len(original)
    if not n:
        return np.zeros(16), {"iterations": 0, "residual": 0.}
    demand = np.ones(n) / n if uniform else original
    q, iterations, residual = flow(transition, demand, deadline)
    normalized = q / max(q.sum(), 1e-30)
    roots = np.flatnonzero(demand > 0)
    if uniform:
        reachable = np.ones(n, bool)
    elif len(roots):
        augmented = coo_matrix((np.ones(len(rows) + len(roots)),
                               (np.r_[rows, np.full(len(roots), n)], np.r_[cols, roots])),
                              shape=(n + 1, n + 1)).tocsr()
        order = breadth_first_order(augmented, n, directed=True, return_predecessors=False)
        reachable = np.zeros(n, bool)
        reachable[order[order < n]] = True
    else:
        reachable = np.zeros(n, bool)
    source = ~incoming[labels]
    sink = ~outgoing[labels]
    values = [q.sum(), np.log1p(n * (normalized @ normalized)),
              entropy(normalized) / np.log(max(n, 2)),
              q @ demand / max(np.linalg.norm(q) * np.linalg.norm(demand), 1e-30),
              normalized @ (demand > 0), normalized @ blocked, normalized @ (outcount == 0),
              normalized @ np.log1p(outcount), normalized @ (outcount >= 2),
              normalized @ cycle, normalized @ (sizes[labels] / n), reachable.mean(),
              np.sum(reachable & blocked) / max(reachable.sum(), 1),
              sizes[labels[reachable]].max(initial=0) / n, normalized @ sink, normalized @ source]
    return np.array(values), {"iterations": iterations, "residual": residual}


def pair(data, use_uniform, deadline):
    blocks, records = [], []
    for d in data:
        g, rec = global_fields(d, use_uniform, deadline)
        blocks.append(np.r_[d[-1], g])
        records.append(rec)
    a, b = blocks
    result = np.r_[a, b, a - b]
    assert result.shape == (72,) and np.isfinite(result).all()
    return result, records


def extract(raw):
    tick = time.thread_time()
    nodes, clause, widths, degree, _ = prepare(raw)
    n = len(degree)
    parse_cpu = time.thread_time() - tick
    deadline = time.thread_time() + 10
    wall = time.monotonic()
    tick = time.thread_time()
    actual_graph = [graph(nodes, clause, widths, n, phase) for phase in (True, False)]
    actual, ar = pair(actual_graph, False, deadline)
    actual_cpu = time.thread_time() - tick
    tick = time.thread_time()
    uniform, ur = pair(actual_graph, True, deadline)
    uniform_cpu = time.thread_time() - tick
    tick = time.thread_time()
    null_nodes = rewire(nodes, clause, widths)
    null_graph = [graph(null_nodes, clause, widths, n, phase) for phase in (True, False)]
    for d, nd in zip(actual_graph, null_graph):
        assert np.allclose(d[-1], nd[-1], atol=1e-12)
        assert np.allclose(d[2], nd[2], atol=1e-12)
    null, nr = pair(null_graph, False, deadline)
    null_cpu = time.thread_time() - tick
    if time.monotonic() - wall > 30:
        raise TimeoutError("critical-clause feature exceeded per-formula wall budget")
    return actual, uniform, null, {"parse_CPU_s": parse_cpu, "actual_CPU_s": actual_cpu,
              "uniform_extra_CPU_s": uniform_cpu, "rewired_CPU_s": null_cpu,
              "actual_flow": ar, "uniform_flow": ur, "rewired_flow": nr,
              "informative": bool(np.linalg.norm(actual - null) > 1e-6)}


def semantic_checks():
    raw = b"p cnf 3 3\n-1 0\n1 -2 0\n2 -3 0\n"
    nodes, clause, widths, degree, _ = prepare(raw)
    d = graph(nodes, clause, widths, len(degree), True)
    assert np.array_equal(d[0].toarray(), [[0, 1, 0], [0, 0, 1], [0, 0, 0]])
    assert np.array_equal(d[2], [1, 0, 0])
    q, _, _ = flow(d[0], d[2], time.thread_time() + 10)
    assert np.allclose(q, [.05, .0475, .045125])
    a = extract(raw)[0]
    negated = b"p cnf 3 3\n1 0\n-1 2 0\n-2 3 0\n"
    b = extract(negated)[0]
    assert np.allclose(a[:24], b[24:48]) and np.allclose(a[48:], -b[48:])
    renamed = b"p cnf 3 3\n1 -2 0\n-3 0\n3 -1 0\n"
    assert np.allclose(a, extract(renamed)[0])
    return {"critical_direction": True, "rooted_chain_mass": True,
            "global_complement_swaps_reference_directions": True,
            "renaming_invariance": True, "SAT_calls": 0, "logical_propagation_calls": 0}


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        checks = semantic_checks()
        reference = DATA / "mechanism_R21_features_20261111/features.npz"
        with np.load(reference) as z:
            keys, eligible, base = z["keys"].tolist(), z["eligible"].copy(), z["topology63"][:, :43].copy()
        assert len(keys) == 4719 and eligible.sum() == 2325
        identity = {r["instance_key"]: r["raw_sha256"] for r in map(json.loads,
                    (DATA / "cnf_graph_cnn_20261110/feature_receipts.jsonl").read_text().splitlines())}
        panel = ROOT / "work/astra_structure_panel_20261110"
        fallback = {r["instance_key"]: panel / "cnf" / (r["case"] + ".cnf")
                    for r in read_csv(panel / "association_only.csv")}
        index = {key: i for i, key in enumerate(keys)}
        actual, uniform, null = [np.zeros((len(keys), 72)) for _ in range(3)]
        informative = np.zeros(len(keys), bool)

        def job(key):
            tick = time.thread_time()
            path = ROOT / "work/signed_boundary_20261110/cnf_cache" / (key + ".cnf.gz")
            if not path.is_file():
                path = fallback[key]
            raw = load_formula(path)
            read_cpu = time.thread_time() - tick
            tick = time.thread_time()
            assert hashlib.sha256(raw).hexdigest() == identity[key]
            identity_cpu = time.thread_time() - tick
            a, u, r, rec = extract(raw)
            rec.update(instance_key=key, raw_sha256=identity[key], read_CPU_s=read_cpu, identity_CPU_s=identity_cpu)
            return key, a, u, r, rec

        completed = 0
        with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
            todo = iter(k for k, e in zip(keys, eligible) if e)
            pending = deque(pool.submit(job, next(todo)) for _ in range(4))
            while pending:
                key, a, u, r, rec = pending.popleft().result()
                i = index[key]
                actual[i], uniform[i], null[i] = a, u, r
                informative[i] = rec["informative"]
                stream.write(json.dumps(rec) + "\n")
                completed += 1
                if completed % 100 == 0:
                    stream.flush()
                    print(f"EXTRACTED {completed}/2325 critical-repair dependencies", flush=True)
                if time.monotonic() - start > 900:
                    raise TimeoutError("critical-repair collection exceeded fifteen minutes")
                key = next(todo, None)
                if key is not None:
                    pending.append(pool.submit(job, key))
        local = np.r_[np.arange(8), np.arange(24, 32), np.arange(48, 56)]
        np.savez_compressed(args.out / "features.npz", keys=np.array(keys), eligible=eligible, informative=informative,
                            local67=np.c_[base, actual[:, local]], actual115=np.c_[base, actual],
                            uniform115=np.c_[base, uniform], rewired115=np.c_[base, null])
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "eligible": completed,
              "informative_parents": int(informative.sum()), "physical_CPU_s": time.process_time() - cpu,
              "wall_s": time.monotonic() - start, "new_solver_calls": 0, "short_search_calls": 0,
              "semantic_checks": checks, "source_sha256": sha(__file__), "reference_sha256": sha(reference),
              "features_sha256": sha(args.out / "features.npz"),
              "scope": "Fractional directed dependency mass, not literal assignments or logical closure"})
    except Exception as error:
        write(args.out / "failure.json", {"status": "failed", "error": repr(error),
              "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    with threadpool_limits(limits=1):
        main(parser.parse_args())
