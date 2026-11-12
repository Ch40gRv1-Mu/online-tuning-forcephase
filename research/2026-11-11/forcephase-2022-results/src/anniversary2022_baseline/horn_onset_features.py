"""R30 fixed density filtration of the Horn pair graph, no SAT search."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from threadpoolctl import threadpool_limits

from .common import sha, write
from .global_signed_response import prepare
from .route_phase_2022 import load_formula
from .structural_clusters import DATA, ROOT, read_csv


DENSITIES = (.25, .5, 1., 2., 4., 8., None)


def pair_arrays(nodes, clause, widths):
    starts = np.r_[0, widths.cumsum()[:-1]]
    positive = np.bincount(clause, weights=(nodes & 1) == 0, minlength=len(widths)).astype(int)
    left, right, kinds = [], [], []
    for width in np.unique(widths):
        if width < 2:
            continue
        ids = np.flatnonzero(widths == width)
        i, j = np.triu_indices(int(width), k=1)
        a = nodes[(starts[ids, None]+i).ravel()]
        b = nodes[(starts[ids, None]+j).ravel()]
        group = (int(width)*(int(widths.max(initial=0))+1)+np.repeat(positive[ids], len(i)))*4
        left.append(a); right.append(b); kinds.append(group+(a & 1)*2+(b & 1))
    if not left:
        return [np.zeros(0, int) for _ in range(3)]
    return np.concatenate(left), np.concatenate(right), np.concatenate(kinds)


def rewire_pairs(a, b, kinds):
    order = np.argsort(kinds, kind="stable")
    boundaries = np.r_[0, np.flatnonzero(kinds[order][1:] != kinds[order][:-1])+1, len(a)]
    rng = np.random.default_rng(20261131)
    other = b.copy()
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        ids = order[start:end]
        other[ids] = b[rng.permutation(ids)]
    return a, other


def signature(a, b, n):
    if not len(a) or not n:
        return np.zeros(8), np.zeros(8)
    rows, cols = np.r_[a ^ 1, b ^ 1], np.r_[b, a]
    out = np.bincount(rows, minlength=2*n).astype(float)
    degree = out[::2]+out[1::2]
    active = degree > 0
    vd = degree[active]
    balance = (out[::2]-out[1::2])[active]/vd
    pp, nn = ((a & 1) == 0) & ((b & 1) == 0), ((a & 1) != 0) & ((b & 1) != 0)
    local = np.array([active.mean(), np.log1p(len(a)/n),
        np.log1p(vd.var()/max(vd.mean()**2, 1e-30)), np.mean(np.abs(balance) == 1),
        np.abs(balance).mean(), pp.mean(), nn.mean(), np.mean(~pp & ~nn)])
    graph = coo_matrix((np.ones(len(rows), np.int32), (rows, cols)), shape=(2*n, 2*n)).tocsr()
    count, labels = connected_components(graph, directed=True, connection="strong")
    sizes = np.bincount(labels)
    bad = labels[::2] == labels[1::2]
    signs = 1. - 2*(np.arange(2*n) & 1)
    profile = np.array([bad.mean(), degree @ bad/degree.sum(), sizes.max()/(2*n),
        np.mean(sizes[labels] > 1), np.sum((sizes/(2*n))**2), count/(2*n),
        np.mean(labels[rows] == labels[cols]), out @ (signs*np.repeat(bad, 2))/out.sum()])
    assert np.isfinite(local).all() and np.isfinite(profile).all()
    return local, profile


def extract(raw):
    start = time.thread_time()
    nodes, clause, widths, degree, _ = prepare(raw)
    a, b, kinds = pair_arrays(nodes, clause, widths)
    assert len(a) <= 500000
    parse_cpu = time.thread_time()-start
    tick = time.thread_time()
    order = np.random.default_rng(20261130).permutation(len(a))
    locals_, actual, null, sizes = [], [], [], []
    cache = {}
    n = len(degree)
    for density in DENSITIES:
        amount = len(a) if density is None else min(len(a), int(density*n))
        if amount not in cache:
            ids = order[:amount]
            x, y = a[ids], b[ids]
            local, value = signature(x, y, n)
            u, v = rewire_pairs(x, y, kinds[ids])
            null_local, control = signature(u, v, n)
            assert np.array_equal(np.bincount(np.r_[x, y], minlength=2*n), np.bincount(np.r_[u, v], minlength=2*n))
            assert np.allclose(local, null_local, rtol=1e-12, atol=1e-12)
            cache[amount] = local, value, control
        local, value, control = cache[amount]
        locals_.append(local); actual.append(value); null.append(control); sizes.append(amount)
        if time.thread_time()-tick > 10:
            raise TimeoutError("Horn onset graph profile exceeded10 CPU seconds")
    actual, null = np.asarray(actual), np.asarray(null)
    assert np.all(np.diff(actual[:, 0]) >= -1e-12)
    assert np.all(np.diff(actual[:, 2]) >= -1e-12)
    informative = np.max(np.abs(actual-null)) > 1e-6 and np.ptp(actual[:, 0]) > .01
    return np.concatenate(locals_), actual.ravel(), null.ravel(), {
        "parse_pair_CPU_s": parse_cpu, "profile_CPU_s": time.thread_time()-tick,
        "pair_count": len(a), "variables": n, "sample_pair_counts": sizes,
        "conflict_curve": actual[:, 0].tolist(), "null_conflict_curve": null[:, 0].tolist(),
        "informative": bool(informative)}


def semantic_checks():
    a = np.array([0, 0, 1, 1]); b = np.array([2, 3, 2, 3])
    _, full = signature(a, b, 2)
    assert full[0] == 1 and full[2] == 1
    _, low = signature(a[:1], b[:1], 2)
    assert low[0] == 0
    raw = b"p cnf 3 4\n1 2 3 0\n1 -2 3 0\n-1 2 3 0\n-1 -2 3 0\n"
    local, actual, null, rec = extract(raw)
    assert local.shape == actual.shape == null.shape == (56,)
    assert np.all(np.diff(rec["conflict_curve"]) >= 0)
    return {"small_graph_conflict_onset": True, "nested_graph_monotonicity": True,
        "null_exact_literal_and_pair_type_margins": True, "SAT_or_assignment_calls": 0,
        "sampling_variable_rename_invariance_claimed": False}


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        checks = semantic_checks()
        reference = DATA / "mechanism_R29_features_20261111/features.npz"
        with np.load(reference) as z:
            keys, eligible = z["keys"].tolist(), z["eligible"].copy()
            base, full = z["local55"][:, :42].copy(), z["actual79"][:,55:].copy()
        assert len(keys) == 4719 and eligible.sum() == 2281
        identity_file = DATA / "cnf_graph_cnn_20261110/feature_receipts.jsonl"
        identity = {r["instance_key"]: r["raw_sha256"] for r in map(json.loads, identity_file.read_text().splitlines())}
        panel = ROOT / "work/astra_structure_panel_20261110"
        fallback = {r["instance_key"]: panel / "cnf" / (r["case"]+".cnf") for r in read_csv(panel / "association_only.csv")}
        local, actual, null = [np.zeros((len(keys), 56)) for _ in range(3)]
        informative = np.zeros(len(keys), bool)
        index = {k:i for i,k in enumerate(keys)}

        def job(key):
            tick = time.thread_time()
            path = ROOT / "work/signed_boundary_20261110/cnf_cache" / (key+".cnf.gz")
            if not path.is_file(): path = fallback[key]
            raw = load_formula(path)
            read_cpu = time.thread_time()-tick
            tick = time.thread_time()
            assert hashlib.sha256(raw).hexdigest() == identity[key]
            identity_cpu = time.thread_time()-tick
            a, b, c, rec = extract(raw)
            rec.update(instance_key=key, raw_sha256=identity[key], read_CPU_s=read_cpu, identity_CPU_s=identity_cpu)
            return key, a, b, c, rec

        completed = 0
        with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
            todo = iter(k for k,e in zip(keys,eligible) if e)
            pending = deque(pool.submit(job,next(todo)) for _ in range(4))
            while pending:
                key, a, b, c, rec = pending.popleft().result()
                i = index[key]
                local[i], actual[i], null[i] = a,b,c
                informative[i] = rec["informative"]
                stream.write(json.dumps(rec)+"\n")
                completed += 1
                if completed % 200 == 0:
                    stream.flush(); print(f"EXTRACTED {completed}/2281 Horn onset profiles",flush=True)
                if time.monotonic()-start > 900:
                    raise TimeoutError("Horn onset collector exceeded fifteen minutes")
                key = next(todo,None)
                if key is not None: pending.append(pool.submit(job,key))
        common = np.c_[base,eligible,local]
        np.savez_compressed(args.out / "features.npz", keys=np.array(keys),eligible=eligible,
            informative=informative,local99=common,full123=np.c_[common,full],
            actual155=np.c_[common,actual],rewired155=np.c_[common,null])
        write(args.out / "summary.json", {"status":"complete","parents":len(keys),"eligible":completed,
            "informative":int(informative.sum()),"densities":DENSITIES,
            "physical_CPU_s":time.process_time()-cpu,"wall_s":time.monotonic()-start,
            "semantic_checks":checks,"source_sha256":sha(__file__),"reference_sha256":sha(reference),
            "features_sha256":sha(args.out / "features.npz"),"SAT_or_CDCL_calls":0,
            "scope":"One fixed nested random pair ordering; no exact sampling invariance or solver cost claim"})
    except Exception as exc:
        write(args.out / "failure.json", {"status":"failed","error":repr(exc),
            "physical_CPU_s":time.process_time()-cpu,"wall_s":time.monotonic()-start})
        raise


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    with threadpool_limits(limits=1): main(parser.parse_args())
