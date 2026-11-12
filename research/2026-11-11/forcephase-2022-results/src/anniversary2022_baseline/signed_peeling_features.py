"""Static bipartite peeling roles and polarity, without assignment or search."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.sparse import coo_matrix
from threadpoolctl import threadpool_limits

from .common import sha, write
from .route_phase_2022 import load_formula
from .scc_quotient_features import normalize, parse
from .structural_clusters import DATA, ROOT, read_csv


def peeling(variable, clause, widths, n):
    """Synchronous degree<2 removal depth, implemented with a linear FIFO."""
    m = len(widths)
    left, right = variable, n + clause
    graph = coo_matrix((np.ones(2 * len(left), dtype=np.int8),
                       (np.r_[left, right], np.r_[right, left])), shape=(n + m, n + m)).tocsr()
    original = np.diff(graph.indptr)
    degree = original.copy()
    removed, queued = np.zeros(n + m, bool), np.zeros(n + m, bool)
    depth = np.zeros(n + m, int)
    frontier = np.flatnonzero(degree < 2)
    queued[frontier] = True
    depth[frontier] = 1
    queue = deque(frontier.tolist())
    while queue:
        u = queue.popleft()
        removed[u] = True
        for v in graph.indices[graph.indptr[u]:graph.indptr[u + 1]]:
            if removed[v]:
                continue
            degree[v] -= 1
            if degree[v] == 1 and not queued[v]:
                queued[v] = True
                depth[v] = depth[u] + 1
                queue.append(int(v))
    core = (~removed) & (original > 0)
    assert np.all(degree[core] >= 2)
    # 0: first shell, 1: removal rounds2/3, 2: rounds>=4, 3:2-core.
    role = np.where(core, 3, np.where(depth <= 1, 0, np.where(depth <= 3, 1, 2)))
    return role[:n], role[n:], depth[:n], depth[n:], original[:n]


def grouped(values, roles, weights=None):
    weight = np.ones(len(roles)) if weights is None else weights
    denominator = np.bincount(roles, weights=weight, minlength=4)
    return np.concatenate([np.bincount(roles, weights=weight * value, minlength=4) /
                           np.maximum(denominator, 1e-30) for value in values])


def shuffle_roles(roles, strata, rng):
    result = roles.copy()
    for group in np.unique(strata):
        ids = np.flatnonzero(strata == group)
        result[ids] = roles[rng.permutation(ids)]
        assert np.array_equal(np.bincount(result[ids], minlength=4),
                              np.bincount(roles[ids], minlength=4))
    return result


def signed_summary(vfields, cfields, vrole, crole, degree):
    # Five variable means plus one degree-weighted bias; six clause means.
    return np.r_[grouped(vfields, vrole), grouped(vfields[:1], vrole, degree),
                 grouped(cfields, crole)]


def extract(raw):
    tick = time.thread_time()
    nodes, clause, m, n = parse(raw)
    nodes, clause, widths, _ = normalize(nodes, clause, m)
    variable = nodes // 2
    vrole, crole, vdepth, cdepth, degree = peeling(variable, clause, widths, n)
    active, nonempty = degree > 0, widths > 0
    active_degree = degree[active]
    vrole, vdepth = vrole[active], vdepth[active]
    active_crole, active_cdepth = crole[nonempty], cdepth[nonempty]
    vmass = np.bincount(vrole, minlength=4) / max(len(vrole), 1)
    cmass = np.bincount(active_crole, minlength=4) / max(len(active_crole), 1)
    full_vrole = np.full(n, -1, int); full_vrole[active] = vrole
    edge_v, edge_c = full_vrole[variable], crole[clause]
    depth_positive = vdepth[vdepth > 0]
    topology = np.r_[vmass, cmass,
                     np.log1p(max(vdepth.max(initial=0), active_cdepth.max(initial=0))),
                     np.log1p(depth_positive.mean()) if len(depth_positive) else 0,
                     np.mean((edge_v == 3) & (edge_c == 3)) if len(nodes) else 0,
                     np.mean((edge_v == 3) != (edge_c == 3)) if len(nodes) else 0]
    positive = (nodes & 1) == 0
    pos_degree = np.bincount(variable, weights=positive, minlength=n)
    raw_bias = (2 * pos_degree - degree) / np.maximum(degree, 1)
    weight = np.exp2(-np.minimum(np.maximum(widths[clause] - 1, 0), 60))
    weighted = np.bincount(variable, weights=weight * (2 * positive.astype(float) - 1), minlength=n)
    absolute = np.bincount(variable, weights=weight, minlength=n)
    pressure = weighted / np.maximum(absolute, 1e-30)
    pure = (pos_degree == degree).astype(float) - (pos_degree == 0)
    vf = np.array([raw_bias, np.abs(raw_bias), pressure, np.abs(pressure), pure])[:, active]
    pos = np.bincount(clause, weights=positive, minlength=len(widths))
    proportion = pos / np.maximum(widths, 1)
    cf = np.array([proportion, np.abs(2 * proportion - 1), pos == widths, pos == 0,
                   pos <= 1, widths - pos <= 1])[:, nonempty].astype(float)
    actual = signed_summary(vf, cf, vrole, active_crole, active_degree)
    actual_cpu = time.thread_time() - tick
    tick = time.thread_time()
    rng = np.random.default_rng(20261120)
    random_vrole = shuffle_roles(vrole, np.floor(np.log2(active_degree)).astype(int), rng)
    random_crole = shuffle_roles(active_crole, widths[nonempty], rng)
    control = signed_summary(vf, cf, random_vrole, random_crole, active_degree)
    random_cpu = time.thread_time() - tick
    assert topology.shape == (12,) and actual.shape == control.shape == (48,)
    assert np.isfinite(np.r_[topology, actual, control]).all()
    return topology, actual, control, {"actual_extract_CPU_s": actual_cpu,
              "random_additional_CPU_s": random_cpu, "active_variables": int(active.sum()),
              "nonempty_clauses": int(nonempty.sum()),
              "mixed_roles": bool(np.sum(vmass >= .01) >= 2 or np.sum(cmass >= .01) >= 2),
              "variable_role_mass": vmass.tolist(), "clause_role_mass": cmass.tolist(),
              "maximum_peeling_round": float(np.expm1(topology[8]))}


def semantic_checks():
    tree = extract(b"p cnf 3 2\n1 2 0\n2 3 0\n")[0]
    cycle = extract(b"p cnf 3 3\n1 2 0\n2 3 0\n3 1 0\n")[0]
    assert np.allclose(tree[:4], [2/3, 1/3, 0, 0]) and np.isclose(np.expm1(tree[8]), 3)
    assert np.array_equal(cycle[:8], [0, 0, 0, 1, 0, 0, 0, 1])
    negative = extract(b"p cnf 3 2\n-1 -2 0\n-2 -3 0\n")[0]
    assert np.array_equal(tree, negative)
    return {"path_removal_rounds": True, "cycle_2core": True,
            "unsigned_complement_invariance": True, "solver_calls": 0}


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        checks = semantic_checks()
        reference = DATA / "mechanism_R16_features_20261111/features.npz"
        with np.load(reference) as z:
            keys, eligible, base = z["keys"].tolist(), z["eligible"].copy(), z["base43"].copy()
        assert len(keys) == 4719 and eligible.sum() == 1890
        identity = {r["instance_key"]: r["raw_sha256"] for r in map(json.loads,
                    (DATA / "cnf_graph_cnn_20261110/feature_receipts.jsonl").read_text().splitlines())}
        panel = ROOT / "work/astra_structure_panel_20261110"
        fallback = {r["instance_key"]: panel / "cnf" / (r["case"] + ".cnf")
                    for r in read_csv(panel / "association_only.csv")}
        index = {key: i for i, key in enumerate(keys)}
        topo, actual, random = np.zeros((len(keys), 12)), np.zeros((len(keys), 48)), np.zeros((len(keys), 48))
        mixed, feature_cpu = np.zeros(len(keys), bool), np.zeros(len(keys))

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
            t, a, r, record = extract(raw)
            record.update(instance_key=key, raw_sha256=identity[key], read_CPU_s=read_cpu,
                          identity_CPU_s=identity_cpu)
            return key, t, a, r, record

        completed = 0
        with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
            todo = iter(k for k, e in zip(keys, eligible) if e)
            pending = deque(pool.submit(job, next(todo)) for _ in range(4))
            while pending:
                key, t, a, r, record = pending.popleft().result()
                i = index[key]
                topo[i], actual[i], random[i] = t, a, r
                mixed[i] = record["mixed_roles"]
                feature_cpu[i] = record["read_CPU_s"] + record["actual_extract_CPU_s"]
                stream.write(json.dumps(record) + "\n")
                completed += 1
                if completed % 200 == 0:
                    stream.flush()
                    print(f"EXTRACTED {completed}/1890 signed peeling profiles", flush=True)
                if time.monotonic() - start > 900:
                    raise TimeoutError("signed peeling extraction exceeded fifteen minutes")
                key = next(todo, None)
                if key is not None:
                    pending.append(pool.submit(job, key))
        np.savez_compressed(args.out / "features.npz", keys=np.array(keys), eligible=eligible, mixed=mixed,
                            topology55=np.c_[base, topo], signed103=np.c_[base, topo, actual],
                            random103=np.c_[base, topo, random], measured_feature_CPU_s=feature_cpu)
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "eligible": completed,
              "mixed_role_parents": int(mixed.sum()), "physical_CPU_s": time.process_time() - cpu,
              "wall_s": time.monotonic() - start, "new_solver_calls": 0, "short_search_calls": 0,
              "semantic_checks": checks, "source_sha256": sha(__file__), "reference_sha256": sha(reference),
              "features_sha256": sha(args.out / "features.npz"),
              "fee_scope": "Extraction metered for ledger; first predictive score deliberately assumes acquisition/query free"})
    except Exception as error:
        write(args.out / "failure.json", {"status": "failed", "error": repr(error),
              "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    with threadpool_limits(limits=1):
        main(parser.parse_args())
