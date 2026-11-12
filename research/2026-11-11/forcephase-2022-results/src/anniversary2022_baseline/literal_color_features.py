"""Full-formula colored literal neighborhoods; no SAT search or assignments."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha, write
from .route_phase_2022 import load_formula
from .scc_quotient_features import normalize, parse
from .structural_clusters import DATA, ROOT, read_csv


BINS = 128


def mix(value):
    x = np.asarray(value, dtype=np.uint64).copy()
    x ^= x >> 30
    x *= np.uint64(0xbf58476d1ce4e5b9)
    x ^= x >> 27
    x *= np.uint64(0x94d049bb133111eb)
    return x ^ (x >> 31)


def neighbor_sums(colors, indices, degree):
    out1, out2 = np.zeros(len(degree), np.uint64), np.zeros(len(degree), np.uint64)
    active = np.flatnonzero(degree)
    if not len(active):
        return out1, out2
    starts = np.r_[0, degree.cumsum()[:-1]][active]
    selected = colors[indices]
    out1[active] = np.add.reduceat(mix(selected + np.uint64(17)), starts)
    out2[active] = np.add.reduceat(mix(selected + np.uint64(713)), starts)
    return out1, out2


def colors(nodes, clause, widths, n, signed):
    degree = np.bincount(nodes, minlength=2 * n)
    variable_degree = degree[::2] + degree[1::2]
    d = np.minimum(16, np.floor(np.log2(1 + degree))).astype(np.uint64)
    vd = np.repeat(np.minimum(16, np.floor(np.log2(1 + variable_degree))).astype(np.uint64), 2)
    literal_type = (np.arange(2 * n) & 1).astype(np.uint64) if signed else np.zeros(2 * n, np.uint64)
    literals = mix(np.uint64(101) + d + 31 * vd + 1021 * literal_type)
    pos = np.bincount(clause, weights=(nodes & 1) == 0, minlength=len(widths)).astype(int)
    balance_code = np.minimum(pos, 16).astype(np.uint64) if signed else np.zeros(len(widths), np.uint64)
    clauses = mix(np.uint64(7919) + np.minimum(widths, 16).astype(np.uint64) + 37 * balance_code)
    order = np.argsort(nodes, kind="stable")
    literal_neighbors = clause[order]
    histograms = []
    complement = np.arange(2 * n) ^ 1
    for step in range(1, 5):
        l1, l2 = neighbor_sums(clauses, literal_neighbors, degree)
        c1, c2 = neighbor_sums(literals, nodes, widths)
        new_literals = mix(literals + mix(literals[complement] + np.uint64(71)) +
                           3 * l1 + 5 * l2 + np.uint64(1009 * step))
        new_clauses = mix(clauses + 7 * c1 + 11 * c2 + np.uint64(2039 * step))
        literals, clauses = new_literals, new_clauses
        all_colors = np.r_[literals, clauses]
        count = np.bincount((all_colors % BINS).astype(int), minlength=BINS)
        histograms.append(np.sqrt(count / max(len(all_colors), 1)))
    result = np.concatenate(histograms)
    assert result.shape == (512,) and np.isfinite(result).all()
    return result


def rewire(nodes, clause, widths):
    """Configuration multigraph preserving each literal's clause-type counts."""
    pos = np.bincount(clause, weights=(nodes & 1) == 0, minlength=len(widths)).astype(np.int64)
    kind = (widths[clause] * (widths.max(initial=0) + 1) + pos[clause]) * 2 + (nodes & 1)
    order = np.argsort(kind, kind="stable")
    starts = np.r_[0, np.flatnonzero(kind[order][1:] != kind[order][:-1]) + 1, len(nodes)]
    result = nodes.copy()
    rng = np.random.default_rng(20261122)
    for left, right in zip(starts[:-1], starts[1:]):
        ids = order[left:right]
        result[ids] = nodes[rng.permutation(ids)]
    assert np.array_equal(np.bincount(nodes, minlength=nodes.max(initial=0) + 1),
                          np.bincount(result, minlength=nodes.max(initial=0) + 1))
    assert np.array_equal(pos, np.bincount(clause, weights=(result & 1) == 0, minlength=len(widths)))
    return result


def extract(raw):
    tick = time.thread_time()
    nodes, clause, m, n = parse(raw)
    nodes, clause, widths, _ = normalize(nodes, clause, m)
    parse_cpu = time.thread_time() - tick
    tick = time.thread_time()
    signed = colors(nodes, clause, widths, n, True)
    signed_cpu = time.thread_time() - tick
    tick = time.thread_time()
    unsigned = colors(nodes, clause, widths, n, False)
    unsigned_cpu = time.thread_time() - tick
    tick = time.thread_time()
    shuffled = rewire(nodes, clause, widths)
    control = colors(shuffled, clause, widths, n, True)
    control_cpu = time.thread_time() - tick
    return signed, unsigned, control, {"parse_CPU_s": parse_cpu, "signed_CPU_s": signed_cpu,
              "unsigned_CPU_s": unsigned_cpu, "rewired_CPU_s": control_cpu,
              "informative": bool(np.linalg.norm(signed - control) > 1e-6),
              "active_variables": n, "literals": len(nodes)}


def semantic_checks():
    a = extract(b"p cnf 3 2\n1 2 0\n-2 3 0\n")
    b = extract(b"p cnf 3 2\n-1 2 0\n3 1 0\n")
    # b renames (1,2,3)->(3,1,2) and reorders clauses.
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
    p = extract(b"p cnf 1 1\n1 0\n")
    q = extract(b"p cnf 1 1\n-1 0\n")
    assert np.array_equal(p[1], q[1]) and not np.array_equal(p[0], q[0])
    return {"renaming_and_clause_order_invariance": True, "unsigned_complement_invariance": True,
            "signed_direction_retained": True, "solver_calls": 0, "label_augmentation": False}


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        checks = semantic_checks()
        reference = DATA / "mechanism_R21_features_20261111/features.npz"
        with np.load(reference) as z:
            keys, eligible = z["keys"].tolist(), z["eligible"].copy()
            base = z["topology63"][:, :43].copy()
        assert len(keys) == 4719 and eligible.sum() == 2325
        identity = {r["instance_key"]: r["raw_sha256"] for r in map(json.loads,
                    (DATA / "cnf_graph_cnn_20261110/feature_receipts.jsonl").read_text().splitlines())}
        panel = ROOT / "work/astra_structure_panel_20261110"
        fallback = {r["instance_key"]: panel / "cnf" / (r["case"] + ".cnf")
                    for r in read_csv(panel / "association_only.csv")}
        index = {key: i for i, key in enumerate(keys)}
        signed, unsigned, null = [np.zeros((len(keys), 512)) for _ in range(3)]
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
            a, b, c, rec = extract(raw)
            rec.update(instance_key=key, raw_sha256=identity[key], read_CPU_s=read_cpu, identity_CPU_s=identity_cpu)
            return key, a, b, c, rec

        completed = 0
        with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
            todo = iter(k for k, e in zip(keys, eligible) if e)
            pending = deque(pool.submit(job, next(todo)) for _ in range(4))
            while pending:
                key, a, b, c, rec = pending.popleft().result()
                i = index[key]
                signed[i], unsigned[i], null[i] = a, b, c
                informative[i] = rec["informative"]
                stream.write(json.dumps(rec) + "\n")
                completed += 1
                if completed % 200 == 0:
                    stream.flush()
                    print(f"EXTRACTED {completed}/2325 literal-color neighborhoods", flush=True)
                if time.monotonic() - start > 900:
                    raise TimeoutError("literal colors exceeded fifteen minutes")
                key = next(todo, None)
                if key is not None:
                    pending.append(pool.submit(job, key))
        np.savez_compressed(args.out / "features.npz", keys=np.array(keys), eligible=eligible, informative=informative,
                            signed555=np.c_[base, signed], unsigned555=np.c_[base, unsigned],
                            rewired555=np.c_[base, null])
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "eligible": completed,
              "informative_parents": int(informative.sum()), "physical_CPU_s": time.process_time() - cpu,
              "wall_s": time.monotonic() - start, "new_solver_calls": 0, "short_search_calls": 0,
              "semantic_checks": checks, "source_sha256": sha(__file__), "reference_sha256": sha(reference),
              "features_sha256": sha(args.out / "features.npz"),
              "scope": "Full normalized formula patterns, color hashes are approximate, no SAT solving or label augmentation"})
    except Exception as error:
        write(args.out / "failure.json", {"status": "failed", "error": repr(error),
              "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    with threadpool_limits(limits=1), np.errstate(over="ignore"):
        main(parser.parse_args())
