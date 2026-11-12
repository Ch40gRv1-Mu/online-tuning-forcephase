"""R29 full-clause Horn-renaming implication SCCs; static graph operations only."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import itertools
import json
from pathlib import Path
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from threadpoolctl import threadpool_limits

from .common import sha, write
from .global_signed_response import prepare
from .literal_color_features import rewire
from .route_phase_2022 import load_formula
from .structural_clusters import DATA, ROOT, read_csv


PAIR_CAP = 500000
LOCAL_NAMES = ("log_pairs_per_variable", "positive_pair_fraction", "negative_pair_fraction",
    "mixed_pair_fraction", "participating_variable_fraction", "mean_signed_outdegree_balance",
    "absolute_outdegree_balance", "one_sided_outdegree_fraction", "log_variable_pair_degree_cv2",
    "log_max_pair_degree_over_mean", "pair_degree_entropy", "log_mean_pair_degree")
GLOBAL_NAMES = ("SCC_count_per_literal", "largest_SCC_mass", "nontrivial_literal_fraction",
    "complement_coincidence_fraction", "degree_weighted_complement_coincidence",
    "conflicting_component_fraction", "largest_conflicting_component_mass", "internal_edge_fraction",
    "component_collision", "component_entropy", "nontrivial_component_fraction",
    "nontrivial_component_sign_imbalance", "branching_component_literal_fraction",
    "outdegree_weighted_component_mass_polarity", "outdegree_weighted_conflict_polarity",
    "sink_literal_fraction", "source_literal_fraction", "sink_polarity", "source_polarity",
    "log_condensation_depth", "mean_normalized_depth", "depth_polarity",
    "log_condensation_outdegree_cv2", "second_normalized_depth_moment")


def pairs(nodes, widths, binary_only=False):
    starts = np.r_[0, widths.cumsum()[:-1]]
    left, right = [], []
    for width in np.unique(widths):
        if width < 2 or (binary_only and width != 2):
            continue
        ids = np.flatnonzero(widths == width)
        a, b = np.triu_indices(int(width), k=1)
        left.append(nodes[(starts[ids, None] + a).ravel()])
        right.append(nodes[(starts[ids, None] + b).ravel()])
    if not left:
        return np.zeros(0, int), np.zeros(0, int)
    return np.concatenate(left), np.concatenate(right)


def describe(nodes, widths, n, binary_only=False, deadline=None):
    a, b = pairs(nodes, widths, binary_only)
    if not len(a):
        return np.zeros(12), np.zeros(24), {"pairs": 0, "complement_coincidences": 0}
    rows, cols = np.r_[a ^ 1, b ^ 1], np.r_[b, a]
    out = np.bincount(rows, minlength=2*n).astype(float)
    incoming = np.bincount(cols, minlength=2*n)
    active = out + incoming > 0
    var_active = active[::2] | active[1::2]
    nv, nl = int(var_active.sum()), int(active.sum())
    degree = out[::2] + out[1::2]
    vd = degree[var_active]
    balance = (out[::2] - out[1::2])[var_active] / np.maximum(vd, 1)
    mass = vd / vd.sum()
    mean = vd.mean()
    pp, nn = ((a & 1) == 0) & ((b & 1) == 0), ((a & 1) != 0) & ((b & 1) != 0)
    local = np.array([np.log1p(len(a)/max(n, 1)), pp.mean(), nn.mean(), np.mean(~pp & ~nn),
        nv/max(n, 1), balance.mean(), np.abs(balance).mean(), np.mean(np.abs(balance) == 1),
        np.log1p(vd.var()/max(mean**2, 1e-30)), np.log1p(vd.max()/max(mean, 1e-30)),
        -mass @ np.log(mass)/np.log(max(nv, 2)), np.log1p(mean)])
    graph = coo_matrix((np.ones(len(rows), np.int32), (rows, cols)), shape=(2*n, 2*n)).tocsr()
    count, label = connected_components(graph, directed=True, connection="strong")
    sizes = np.bincount(label, weights=active, minlength=count)
    present = sizes > 0
    component_count = int(present.sum())
    bad = (label[::2] == label[1::2]) & var_active
    conflict = np.zeros(count, bool)
    conflict[label[::2][bad]] = True
    nontrivial = sizes[label] > 1
    sign = 1. - 2*(np.arange(2*n) & 1)
    signed_size = np.bincount(label, weights=sign*active, minlength=count)
    lr, lc = label[rows], label[cols]
    cross = lr != lc
    outgoing = np.bincount(lr[cross], minlength=count)
    arriving = np.bincount(lc[cross], minlength=count)
    sink, source = present & (outgoing == 0), present & (arriving == 0)
    # Construct the condensation DAG with distinct edges, not weighted duplicates.
    dag = coo_matrix((np.ones(cross.sum(), np.int32), (lr[cross], lc[cross])), shape=(count, count)).tocsr()
    dag.data[:] = 1
    d_out = np.diff(dag.indptr)
    d_in = np.bincount(dag.indices, minlength=count)
    depth = np.zeros(count, int)
    edge_nodes = (d_out + d_in) > 0
    queue = deque(np.flatnonzero(edge_nodes & (d_in == 0)).tolist())
    processed = 0
    while queue:
        v = queue.popleft()
        dest = dag.indices[dag.indptr[v]:dag.indptr[v+1]]
        if len(dest):
            np.maximum.at(depth, dest, depth[v]+1)
            d_in[dest] -= 1
            queue.extend(dest[d_in[dest] == 0].tolist())
        processed += 1
        if deadline is not None and processed % 1024 == 0 and time.thread_time() > deadline:
            raise TimeoutError("Horn SCC condensation exceeded per-formula CPU allowance")
    assert processed == edge_nodes.sum()
    p = sizes[present]/nl
    dmax = int(depth.max(initial=0))
    out_mean = d_out[present].mean()
    global_values = np.array([component_count/nl, sizes.max()/nl,
        np.mean(nontrivial[active]), np.mean(bad[var_active]), degree @ bad/max(degree.sum(), 1),
        conflict.sum()/component_count, sizes[conflict].max(initial=0)/nl, np.mean(~cross),
        p @ p, -p @ np.log(p)/np.log(max(component_count, 2)), np.sum(sizes > 1)/component_count,
        np.abs(signed_size[sizes > 1]).sum()/max(sizes[sizes > 1].sum(), 1),
        sizes[d_out >= 2].sum()/nl, out @ (sign*sizes[label]/nl)/out.sum(),
        out @ (sign*conflict[label])/out.sum(), sizes[sink].sum()/nl, sizes[source].sum()/nl,
        signed_size[sink].sum()/nl, signed_size[source].sum()/nl, np.log1p(dmax),
        sizes @ depth/nl/max(dmax, 1), signed_size @ depth/nl/max(dmax, 1),
        np.log1p(d_out[present].var()/max(out_mean**2, 1e-30)),
        sizes @ (depth.astype(float)**2)/nl/max(dmax**2, 1)])
    assert local.shape == (12,) and global_values.shape == (24,)
    assert np.isfinite(local).all() and np.isfinite(global_values).all()
    if deadline is not None and time.thread_time() > deadline:
        raise TimeoutError("Horn graph extraction exceeded per-formula CPU allowance")
    return local, global_values, {"pairs": len(a), "complement_coincidences": int(bad.sum()),
        "participating_variables": nv, "SCCs": component_count, "condensation_depth": dmax}


def extract(raw):
    tick = time.thread_time()
    nodes, clause, widths, degree, _ = prepare(raw)
    parse_cpu = time.thread_time() - tick
    pair_count = int((widths*(widths-1)//2).sum())
    if pair_count > PAIR_CAP:
        return None, {"pair_count": pair_count, "eligible": False, "parse_CPU_s": parse_cpu}
    deadline = time.thread_time() + 10
    tick = time.thread_time()
    local, actual, rec = describe(nodes, widths, len(degree), deadline=deadline)
    actual_cpu = time.thread_time() - tick
    tick = time.thread_time()
    _, binary, _ = describe(nodes, widths, len(degree), binary_only=True, deadline=deadline)
    binary_cpu = time.thread_time() - tick
    tick = time.thread_time()
    null_nodes = rewire(nodes, clause, widths)
    null_local, null, _ = describe(null_nodes, widths, len(degree), deadline=deadline)
    assert np.allclose(local, null_local, atol=1e-12, rtol=1e-12)
    null_cpu = time.thread_time() - tick
    informative = np.max(np.abs(actual-null), initial=0) > 1e-6 and np.max(np.abs(actual-binary), initial=0) > 1e-6
    rec.update(eligible=True, pair_count=pair_count, parse_CPU_s=parse_cpu, actual_CPU_s=actual_cpu,
        binary_CPU_s=binary_cpu, rewired_CPU_s=null_cpu, informative=bool(informative))
    return (local, binary, actual, null), rec


def semantic_checks():
    examples = [b"p cnf 3 1\n1 2 3 0\n",
        b"p cnf 2 4\n1 2 0\n1 -2 0\n-1 2 0\n-1 -2 0\n",
        b"p cnf 3 4\n1 2 3 0\n1 -2 3 0\n-1 2 3 0\n-1 -2 3 0\n",
        b"p cnf 2 2\n1 0\n-1 0\n"]
    for raw in examples:
        nodes, clause, widths, degree, _ = prepare(raw)
        _, _, rec = describe(nodes, widths, len(degree))
        orientations = itertools.product((0, 1), repeat=len(degree))
        feasible = any(np.all(np.bincount(clause, weights=((nodes & 1) == np.asarray(bits)[nodes//2]), minlength=len(widths)) <= 1)
                       for bits in orientations)
        assert feasible == (rec["complement_coincidences"] == 0)
    # The four ternary clauses are satisfied by z=true, yet not Horn-renamable.
    example = examples[2]
    nodes, clause, widths, degree, _ = prepare(example)
    assignment = np.array([False, False, True])
    assert np.all(np.bincount(clause, weights=(assignment[nodes//2] != (nodes & 1)), minlength=len(widths)) > 0)
    assert describe(nodes, widths, len(degree))[2]["complement_coincidences"] > 0
    a = extract(b"p cnf 3 2\n1 2 3 0\n-1 2 0\n")[0]
    b = extract(b"p cnf 3 2\n-3 1 0\n3 1 2 0\n")[0]
    assert np.allclose(a[0], b[0]) and np.allclose(a[2], b[2])
    return {"exhaustive_small_renaming_equivalence": True,
        "Horn_nonrenamability_is_not_original_UNSAT": True,
        "variable_rename_clause_order_invariance": True,
        "rewire_local_pair_margins": True, "SAT_or_CDCL_calls": 0}


def main(args):
    wall, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        checks = semantic_checks()
        reference = DATA / "mechanism_R21_features_20261111/features.npz"
        with np.load(reference) as z:
            keys, admitted = z["keys"].tolist(), z["eligible"].copy()
            base = z["topology63"][:, :42].copy()
        assert len(keys) == 4719 and admitted.sum() == 2325
        identity_file = DATA / "cnf_graph_cnn_20261110/feature_receipts.jsonl"
        identity = {r["instance_key"]: r["raw_sha256"] for r in map(json.loads, identity_file.read_text().splitlines())}
        panel = ROOT / "work/astra_structure_panel_20261110"
        fallback = {r["instance_key"]: panel / "cnf" / (r["case"]+".cnf") for r in read_csv(panel / "association_only.csv")}
        index = {k: i for i, k in enumerate(keys)}
        eligible, informative = np.zeros(len(keys), bool), np.zeros(len(keys), bool)
        local = np.zeros((len(keys), 12))
        binary, actual, null = [np.zeros((len(keys), 24)) for _ in range(3)]

        def job(key):
            tick = time.thread_time()
            path = ROOT / "work/signed_boundary_20261110/cnf_cache" / (key+".cnf.gz")
            if not path.is_file():
                path = fallback[key]
            raw = load_formula(path)
            read_cpu = time.thread_time() - tick
            tick = time.thread_time()
            assert hashlib.sha256(raw).hexdigest() == identity[key]
            identity_cpu = time.thread_time() - tick
            values, rec = extract(raw)
            rec.update(instance_key=key, raw_sha256=identity[key], read_CPU_s=read_cpu, identity_CPU_s=identity_cpu)
            return key, values, rec

        completed = 0
        with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
            todo = iter(k for k, a in zip(keys, admitted) if a)
            pending = deque(pool.submit(job, next(todo)) for _ in range(4))
            while pending:
                key, value, rec = pending.popleft().result()
                i = index[key]
                if value is not None:
                    local[i], binary[i], actual[i], null[i] = value
                    eligible[i], informative[i] = True, rec["informative"]
                stream.write(json.dumps(rec)+"\n")
                completed += 1
                if completed % 200 == 0:
                    stream.flush()
                    print(f"EXTRACTED {completed}/2325 Horn-renaming graphs", flush=True)
                if time.monotonic() - wall > 900:
                    raise TimeoutError("Horn-renaming collector exceeded fifteen minutes")
                key = next(todo, None)
                if key is not None:
                    pending.append(pool.submit(job, key))
        common = np.c_[base, eligible, local]
        np.savez_compressed(args.out / "features.npz", keys=np.array(keys), eligible=eligible,
            informative=informative, local55=common, binary79=np.c_[common, binary],
            actual79=np.c_[common, actual], rewired79=np.c_[common, null])
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "attempted": completed,
            "eligible": int(eligible.sum()), "resource_excluded_pairs": int(np.sum(admitted & ~eligible)),
            "informative": int(informative.sum()), "physical_CPU_s": time.process_time()-cpu,
            "wall_s": time.monotonic()-wall, "semantic_checks": checks,
            "feature_names": {"local": LOCAL_NAMES, "global": GLOBAL_NAMES},
            "source_sha256": sha(__file__), "reference_sha256": sha(reference),
            "identities_sha256": sha(identity_file), "features_sha256": sha(args.out / "features.npz"),
            "SAT_or_CDCL_calls": 0, "scope": "Normalized formula Horn-renaming metagraph, not original SAT truth; null is a configuration multigraph"})
    except Exception as exc:
        write(args.out / "failure.json", {"status": "failed", "error": repr(exc),
            "physical_CPU_s": time.process_time()-cpu, "wall_s": time.monotonic()-wall})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    with threadpool_limits(limits=1):
        main(parser.parse_args())
