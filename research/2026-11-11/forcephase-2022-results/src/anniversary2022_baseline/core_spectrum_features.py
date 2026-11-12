"""Resolve dense constraint cores by variable-degree support, without solving."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import heapq
import json
from pathlib import Path
import sqlite3
import time

import numpy as np
from scipy.sparse import coo_matrix
from threadpoolctl import threadpool_limits

from .common import sha, write
from .route_phase_2022 import load_formula
from .scc_quotient_features import normalize, parse
from .signed_peeling_features import shuffle_roles, signed_summary
from .structural_clusters import BASE, DATA, ROOT, read_csv


def spectrum(variable, clause, widths, n):
    """Variable threshold k, clause threshold2; min-degree peeling for all k."""
    m = len(widths)
    incidence = coo_matrix((np.ones(len(variable), dtype=np.int8),
                           (variable, clause)), shape=(n, m)).tocsr()
    reverse = incidence.T.tocsr()
    clause_alive = widths >= 2
    remaining = widths.copy()
    initial = np.bincount(variable[clause_alive[clause]], minlength=n)
    degree = initial.copy()
    removed = np.zeros(n, bool)
    core, clause_core = np.zeros(n, int), np.zeros(m, int)
    heap = [(int(degree[u]), u) for u in range(n)]
    heapq.heapify(heap)
    level = 0
    while heap:
        d, u = heapq.heappop(heap)
        if removed[u] or d != degree[u]:
            continue
        level = max(level, d)
        core[u] = level
        removed[u] = True
        for c in incidence.indices[incidence.indptr[u]:incidence.indptr[u + 1]]:
            if not clause_alive[c]:
                continue
            remaining[c] -= 1
            if remaining[c] >= 2:
                continue
            clause_alive[c] = False
            clause_core[c] = level
            for v in reverse.indices[reverse.indptr[c]:reverse.indptr[c + 1]]:
                if not removed[v]:
                    degree[v] -= 1
                    heapq.heappush(heap, (int(degree[v]), int(v)))
    assert removed.all() and np.all(core <= initial)
    return core, clause_core, initial


def quantile_role(values):
    if not len(values):
        return np.zeros(0, int)
    # Keep equal core values together; never break ties by variable identifiers.
    return np.searchsorted(np.quantile(values, [.25, .5, .75]), values, side="left")


def extract(raw):
    tick = time.thread_time()
    nodes, clause, m, n = parse(raw)
    nodes, clause, widths, _ = normalize(nodes, clause, m)
    variable = nodes // 2
    degree = np.bincount(variable, minlength=n)
    active, nonempty = degree > 0, widths > 0
    core, ccore, initial = spectrum(variable, clause, widths, n)
    vc, cc = core[active], ccore[nonempty]
    vr, cr = quantile_role(vc), quantile_role(cc)
    vmass = np.bincount(vr, minlength=4) / max(len(vr), 1)
    cmass = np.bincount(cr, minlength=4) / max(len(cr), 1)
    vmax, vmean, cmean = vc.max(initial=0), vc.mean() if len(vc) else 0, cc.mean() if len(cc) else 0
    topology = np.r_[np.log1p(vmax), np.log1p(vmean),
                     np.log1p(vc.var() / max(vmean ** 2, 1e-30)) if len(vc) else 0,
                     np.mean(vc == 0) if len(vc) else 0, np.mean(vc == 1) if len(vc) else 0,
                     np.mean(vc == 2) if len(vc) else 0,
                     np.mean(vc / np.maximum(initial[active], 1)) if len(vc) else 0,
                     np.log1p(cc.max(initial=0)), np.log1p(cmean),
                     np.mean(cc > 0) if len(cc) else 0,
                     np.mean(vc == vmax) if len(vc) else 0,
                     np.mean(core[variable]) / max(vmax, 1) if len(variable) else 0, vmass, cmass]
    positive = (nodes & 1) == 0
    pos_degree = np.bincount(variable, weights=positive, minlength=n)
    bias = (2 * pos_degree - degree) / np.maximum(degree, 1)
    weight = np.exp2(-np.minimum(np.maximum(widths[clause] - 1, 0), 60))
    pressure = np.bincount(variable, weights=weight * (2 * positive.astype(float) - 1), minlength=n)
    pressure /= np.maximum(np.bincount(variable, weights=weight, minlength=n), 1e-30)
    pure = (pos_degree == degree).astype(float) - (pos_degree == 0)
    vf = np.array([bias, np.abs(bias), pressure, np.abs(pressure), pure])[:, active]
    pos = np.bincount(clause, weights=positive, minlength=len(widths))
    proportion = pos / np.maximum(widths, 1)
    cf = np.array([proportion, np.abs(2 * proportion - 1), pos == widths, pos == 0,
                   pos <= 1, widths - pos <= 1])[:, nonempty].astype(float)
    actual = signed_summary(vf, cf, vr, cr, degree[active])
    actual_cpu = time.thread_time() - tick
    tick = time.thread_time()
    rng = np.random.default_rng(20261121)
    # Exact occurrence-degree strata improve the control over coarse degree bins.
    rvr = shuffle_roles(vr, degree[active], rng)
    rcr = shuffle_roles(cr, widths[nonempty], rng)
    control = signed_summary(vf, cf, rvr, rcr, degree[active])
    random_cpu = time.thread_time() - tick
    assert topology.shape == (20,) and actual.shape == control.shape == (48,)
    assert np.isfinite(np.r_[topology, actual, control]).all()
    return topology, actual, control, {"actual_extract_CPU_s": actual_cpu,
              "random_additional_CPU_s": random_cpu, "high_core": bool(vmax >= 3),
              "max_variable_core": int(vmax), "variable_role_mass": vmass.tolist(),
              "clause_role_mass": cmass.tolist(), "active_variables": int(active.sum())}


def semantic_checks():
    def check(raw, expected):
        nodes, clauses, m, n = parse(raw)
        nodes, clauses, widths, _ = normalize(nodes, clauses, m)
        core, _, _ = spectrum(nodes // 2, clauses, widths, n)
        assert np.all(core == expected)
    check(b"p cnf 3 2\n1 2 0\n2 3 0\n", 1)
    check(b"p cnf 3 3\n1 2 0\n2 3 0\n3 1 0\n", 2)
    check(b"p cnf 4 6\n1 2 0\n1 3 0\n1 4 0\n2 3 0\n2 4 0\n3 4 0\n", 3)
    check(b"p cnf 1 1\n1 0\n", 0)
    assert np.array_equal(quantile_role(np.ones(4)), np.zeros(4))
    return {"binary_path_core1": True, "binary_cycle_core2": True,
            "binary_clique_core3": True, "units_not_graph_edges": True,
            "ties_not_split_by_identity": True, "solver_calls": 0}


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        checks = semantic_checks()
        with np.load(DATA / "mechanism_R16_features_20261111/features.npz") as z:
            keys, base = z["keys"].tolist(), z["base43"][:, :42].copy()
        with sqlite3.connect("file:" + str(BASE) + "?mode=ro", uri=True) as db:
            counts = {k: (float(n), round(float(n) * float(d))) for k, n, d in
                      db.execute("select hash,variables,vcg_vdegree_mean from features")}
        eligible = np.array([counts[k][0] <= 100000 and counts[k][1] <= 200000 for k in keys])
        assert eligible.sum() == 2325 and len(keys) == 4719
        base = np.c_[base, eligible.astype(float)]
        identity = {r["instance_key"]: r["raw_sha256"] for r in map(json.loads,
                    (DATA / "cnf_graph_cnn_20261110/feature_receipts.jsonl").read_text().splitlines())}
        assert all(k in identity for k, e in zip(keys, eligible) if e)
        panel = ROOT / "work/astra_structure_panel_20261110"
        fallback = {r["instance_key"]: panel / "cnf" / (r["case"] + ".cnf")
                    for r in read_csv(panel / "association_only.csv")}
        index = {key: i for i, key in enumerate(keys)}
        topo, actual, random = np.zeros((len(keys), 20)), np.zeros((len(keys), 48)), np.zeros((len(keys), 48))
        informative, fee = np.zeros(len(keys), bool), np.zeros(len(keys))

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
            t, a, r, rec = extract(raw)
            rec.update(instance_key=key, raw_sha256=identity[key], read_CPU_s=read_cpu,
                       identity_CPU_s=identity_cpu)
            return key, t, a, r, rec

        completed = 0
        with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
            todo = iter(k for k, e in zip(keys, eligible) if e)
            pending = deque(pool.submit(job, next(todo)) for _ in range(4))
            while pending:
                key, t, a, r, rec = pending.popleft().result()
                i = index[key]
                topo[i], actual[i], random[i] = t, a, r
                informative[i] = rec["high_core"]
                fee[i] = rec["read_CPU_s"] + rec["actual_extract_CPU_s"]
                stream.write(json.dumps(rec) + "\n")
                completed += 1
                if completed % 200 == 0:
                    stream.flush()
                    print(f"EXTRACTED {completed}/2325 variable-core spectra", flush=True)
                if time.monotonic() - start > 900:
                    raise TimeoutError("variable-core collection exceeded fifteen minutes")
                key = next(todo, None)
                if key is not None:
                    pending.append(pool.submit(job, key))
        np.savez_compressed(args.out / "features.npz", keys=np.array(keys), eligible=eligible, informative=informative,
                            topology63=np.c_[base, topo], signed111=np.c_[base, topo, actual],
                            random111=np.c_[base, topo, random], measured_feature_CPU_s=fee)
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "eligible": completed,
              "high_core_parents": int(informative.sum()), "physical_CPU_s": time.process_time() - cpu,
              "wall_s": time.monotonic() - start, "new_solver_calls": 0, "short_search_calls": 0,
              "semantic_checks": checks, "source_sha256": sha(__file__),
              "features_sha256": sha(args.out / "features.npz"),
              "eligibility": "Input nmax<=100000 and literal occurrences<=200000; cache availability not a feature",
              "fee_scope": "Actual collection cost ledger; first predictive score assumes feature/query free"})
    except Exception as error:
        write(args.out / "failure.json", {"status": "failed", "error": repr(error),
              "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    with threadpool_limits(limits=1):
        main(parser.parse_args())
