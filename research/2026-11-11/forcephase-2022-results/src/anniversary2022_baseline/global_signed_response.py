"""Long-range signed incidence responses; linear algebra only, no SAT calls."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import LinearOperator, cg
from threadpoolctl import threadpool_limits

from .common import sha, write
from .literal_color_features import rewire
from .route_phase_2022 import load_formula
from .scc_quotient_features import normalize, parse
from .structural_clusters import DATA, ROOT, read_csv


ALPHAS = (.25, .95, .995)


def unit(vector):
    return vector / max(np.linalg.norm(vector), 1e-30)


def prepare(raw):
    nodes, clause, m, n = parse(raw)
    nodes, clause, widths, _ = normalize(nodes, clause, m)
    degree = np.bincount(nodes // 2, minlength=n)
    active = degree > 0
    mapping = np.cumsum(active) - 1
    nodes = 2 * mapping[nodes // 2] + (nodes & 1)
    degree = degree[active]
    sign = 1. - 2. * (nodes & 1)
    weight = np.exp2(-np.minimum(np.maximum(widths[clause] - 1, 0), 60))
    pressure = np.bincount(nodes // 2, weights=weight * sign, minlength=len(degree))
    pressure /= np.maximum(np.bincount(nodes // 2, weights=weight, minlength=len(degree)), 1e-30)
    pressure[np.abs(pressure) < 1e-12] = 0.
    return nodes, clause, widths, degree, pressure


def coupling(nodes, clause, widths, degree, unsigned=False):
    sign = np.ones(len(nodes)) if unsigned else 1. - 2. * (nodes & 1)
    value = sign / np.sqrt(np.maximum(widths[clause], 1) * degree[nodes // 2])
    # Parallel null edges retain multiplicity through their summed weights.
    matrix = coo_matrix((value, (clause, nodes // 2)), shape=(len(widths), len(degree))).tocsr()
    transpose = matrix.T.tocsr()

    def apply(vector):
        return transpose @ (matrix @ vector)

    return matrix, apply


def solve(apply, rhs, alpha, deadline, counter):
    if np.linalg.norm(rhs) == 0:
        return np.zeros(len(rhs)), 0, 0.
    op = LinearOperator((len(rhs), len(rhs)), matvec=lambda x: x - alpha * apply(x), dtype=float)
    iterations = [0]

    def callback(_):
        iterations[0] += 1
        counter[0] += 1
        if time.thread_time() > deadline:
            raise TimeoutError("linear feature exceeded per-formula CPU budget")

    result, info = cg(op, rhs, rtol=1e-5, atol=0., maxiter=256, callback=callback)
    residual = np.linalg.norm(op @ result - rhs) / np.linalg.norm(rhs)
    if info != 0 or not np.isfinite(result).all() or residual > 2e-5:
        raise ArithmeticError(f"linear response did not converge: info={info}, residual={residual}")
    return result, iterations[0], float(residual)


def response(nodes, clause, widths, degree, pressure, unsigned=False, deadline=None):
    if deadline is None:
        deadline = time.thread_time() + 10.
    n = len(degree)
    if not n:
        return np.zeros(48), {"CG_iterations": 0, "max_relative_residual": 0., "scale_CPU_s": [0.] * 3}
    matrix, apply = coupling(nodes, clause, widths, degree, unsigned)
    u, b, d = np.ones(n) / np.sqrt(n), unit(pressure), unit(degree.astype(float))
    ju, jb = apply(u), apply(b)
    prelude = [pressure.mean(), np.abs(pressure).mean(), np.sqrt(np.mean(pressure ** 2)),
               np.mean(np.abs(pressure) < 1e-12), np.mean(pressure > 0) - np.mean(pressure < 0),
               u @ b, d @ b, u @ ju, b @ jb, u @ jb,
               float(matrix.multiply(matrix).sum()) / n, ju @ ju]
    values = list(prelude)
    counter, residuals, scale_cpu = [0], [], []
    for alpha in ALPHAS:
        tick = time.thread_time()
        yu, _, ru = solve(apply, u, alpha, deadline, counter)
        yb, _, rb = solve(apply, b, alpha, deadline, counter)
        scale_cpu.append(time.thread_time() - tick)
        residuals.extend([ru, rb])
        nu, nb = np.linalg.norm(yu), np.linalg.norm(yb)
        cu, cb = unit(yu), unit(yb)
        tu, tb = 1e-3 * nu / np.sqrt(n), 1e-3 * nb / np.sqrt(n)
        values.extend([np.log1p(max(0., u @ yu)), np.log1p(nu), np.mean(yu < -tu),
                       d @ cu, np.abs(yu).sum() / max(np.sqrt(n) * nu, 1e-30),
                       np.mean(np.abs(yu) > 2 * nu / np.sqrt(n)),
                       np.log1p(max(0., b @ yb)), np.log1p(nb), u @ cb, cu @ cb,
                       np.mean(yb > tb) - np.mean(yb < -tb),
                       np.mean(np.abs(yb) > 2 * nb / np.sqrt(n))])
    result = np.array(values)
    assert result.shape == (48,) and np.isfinite(result).all()
    return result, {"CG_iterations": counter[0], "max_relative_residual": max(residuals),
                    "scale_CPU_s": scale_cpu}


def extract(raw):
    tick = time.thread_time()
    data = prepare(raw)
    parse_cpu = time.thread_time() - tick
    deadline = time.thread_time() + 10.
    wall_start = time.monotonic()
    tick = time.thread_time()
    signed, sr = response(*data, deadline=deadline)
    signed_cpu = time.thread_time() - tick
    tick = time.thread_time()
    unsigned, ur = response(*data, unsigned=True, deadline=deadline)
    unsigned_cpu = time.thread_time() - tick
    tick = time.thread_time()
    nodes, clause, widths, degree, pressure = data
    null_nodes = rewire(nodes, clause, widths)
    null, nr = response(null_nodes, clause, widths, degree, pressure, deadline=deadline)
    null_cpu = time.thread_time() - tick
    if time.monotonic() - wall_start > 30:
        raise TimeoutError("linear feature exceeded per-formula wall budget")
    return signed, unsigned, null, {"parse_CPU_s": parse_cpu, "signed_CPU_s": signed_cpu,
              "unsigned_CPU_s": unsigned_cpu, "rewired_CPU_s": null_cpu,
              "signed_solver": sr, "unsigned_solver": ur, "rewired_solver": nr,
              "informative": bool(np.linalg.norm(signed - null) > 1e-6)}


def semantic_checks():
    raw = b"p cnf 3 2\n1 2 0\n-2 3 0\n"
    data = prepare(raw)
    matrix, apply = coupling(*data[:4])
    gram = matrix.toarray().T @ matrix.toarray()
    eigenvalues = np.linalg.eigvalsh(gram)
    assert eigenvalues.min() >= -1e-12 and eigenvalues.max() <= 1 + 1e-12
    rhs = np.ones(gram.shape[0]) / np.sqrt(gram.shape[0])
    numerical, _, _ = solve(apply, rhs, .995, time.thread_time() + 10, [0])
    assert np.allclose(numerical, np.linalg.solve(np.eye(len(rhs)) - .995 * gram, rhs), atol=1e-7)
    a = extract(raw)[0]
    b = extract(b"p cnf 3 2\n-1 2 0\n3 1 0\n")[0]
    assert np.allclose(a, b, atol=1e-9)
    p, q = extract(b"p cnf 1 1\n1 0\n")[0], extract(b"p cnf 1 1\n-1 0\n")[0]
    assert np.isclose(p[0], -q[0]) and np.isclose(p[20], -q[20])
    return {"normalized_spectrum_bound": True, "CG_dense_agreement": True,
            "renaming_invariance": True, "signed_direction_retained": True,
            "SAT_solver_calls": 0, "runtime_label_augmentation": False}


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
        signed, unsigned, null = [np.zeros((len(keys), 48)) for _ in range(3)]
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
                if completed % 100 == 0:
                    stream.flush()
                    print(f"EXTRACTED {completed}/2325 global signed responses", flush=True)
                if time.monotonic() - start > 900:
                    raise TimeoutError("global response collection exceeded fifteen minutes")
                key = next(todo, None)
                if key is not None:
                    pending.append(pool.submit(job, key))
        np.savez_compressed(args.out / "features.npz", keys=np.array(keys), eligible=eligible, informative=informative,
                            short67=np.c_[base, signed[:, :24]], signed91=np.c_[base, signed],
                            unsigned91=np.c_[base, unsigned], rewired91=np.c_[base, null])
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "eligible": completed,
              "informative_parents": int(informative.sum()), "physical_CPU_s": time.process_time() - cpu,
              "wall_s": time.monotonic() - start, "new_solver_calls": 0, "short_search_calls": 0,
              "semantic_checks": checks, "source_sha256": sha(__file__), "reference_sha256": sha(reference),
              "rewire_source_sha256": sha(ROOT / "src/anniversary2022_baseline/literal_color_features.py"),
              "features_sha256": sha(args.out / "features.npz"), "alphas": ALPHAS,
              "scope": "Input-defined linear features, CG iterations/residuals are ledger only, no SAT search"})
    except Exception as error:
        write(args.out / "failure.json", {"status": "failed", "error": repr(error),
              "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    with threadpool_limits(limits=1):
        main(parser.parse_args())
