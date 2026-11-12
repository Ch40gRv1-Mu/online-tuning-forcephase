"""Fixed algebraic OR-factor responses; no solver calls or discrete decisions."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import numpy as np
from scipy.special import expit
from threadpoolctl import threadpool_limits

from .common import sha, write
from .route_phase_2022 import load_formula
from .scc_quotient_features import normalize, parse
from .score_static_seed_agreement import load_views
from .structural_clusters import BASE, DATA, ROOT, load, read_csv


STEPS = (3, 6, 12)


def prepare(raw):
    nodes, clause, m, n = parse(raw)
    nodes, clause, widths, _ = normalize(nodes, clause, m)
    variable = nodes // 2
    degree = np.bincount(variable, minlength=n).astype(float)
    sign = 1. - 2. * (nodes & 1)
    raw_bias = np.bincount(variable, weights=sign, minlength=n) / np.maximum(degree, 1)
    return variable, clause, widths, degree, sign, raw_bias


def rollout(data, initial_true):
    variable, clause, widths, degree, sign, raw_bias = data
    n, m = len(degree), len(widths)
    active = degree > 0
    pf = np.where(sign > 0, 1 - initial_true, initial_true)
    snapshots = []
    for step in range(1, 13):
        log_false = np.log(np.clip(pf, 1e-9, 1 - 1e-9))
        clause_log = np.bincount(clause, weights=log_false, minlength=m)
        warning = np.exp(np.minimum(0., clause_log[clause] - log_false))
        incoming = sign * -np.log1p(-np.minimum(warning, 1 - 1e-9))
        field = np.bincount(variable, weights=incoming, minlength=n)
        cavity = np.clip(field[variable] - incoming, -20, 20)
        target = expit(-sign * cavity)
        updated = np.clip(.5 * pf + .5 * target, 1e-9, 1 - 1e-9)
        residual = np.abs(updated - pf)
        pf = updated
        if step not in STEPS:
            continue
        magnetization = np.tanh(np.clip(field, -20, 20) / 2)
        selected = magnetization[active]
        literal_false = np.clip(.5 * (1 - sign * magnetization[variable]), 1e-9, 1 - 1e-9)
        violation = np.exp(np.bincount(clause, weights=np.log(literal_false), minlength=m))
        if not len(selected):
            phi = np.zeros(12)
        else:
            strong_positive, strong_negative = np.mean(selected > .9), np.mean(selected < -.9)
            phi = np.array([selected.mean(), np.abs(selected).mean(), np.mean(selected ** 2),
                            np.dot(degree[active], selected) / max(degree.sum(), 1),
                            strong_positive - strong_negative, strong_positive * strong_negative,
                            residual.mean() if len(residual) else 0,
                            np.quantile(residual, .9) if len(residual) else 0,
                            violation.mean() if len(violation) else 0,
                            violation.var() if len(violation) else 0,
                            np.mean(selected * raw_bias[active]),
                            np.abs(np.clip(field[active], -20, 20)).mean() / 20])
        snapshots.append({"phi": phi, "m": selected, "violation": violation,
                          "residual": float(residual.mean()) if len(residual) else 0})
    return snapshots


def response(plus, minus, active_degree):
    values = []
    for a, b in zip(plus, minus):
        p, q = a["m"], b["m"]
        if not len(p):
            values.extend([0.] * 12)
            continue
        delta, persistent = p - q, (p + q) / 2
        vp, vq = a["violation"], b["violation"]
        values.extend([delta.mean(), np.abs(delta).mean(), np.mean(delta ** 2),
                       persistent.mean(), np.abs(persistent).mean(), np.mean(p * q), np.mean(p * q < 0),
                       np.dot(active_degree, persistent) / max(active_degree.sum(), 1),
                       a["residual"] - b["residual"], (vp - vq).mean() if len(vp) else 0,
                       np.abs(p).mean() - np.abs(q).mean(), np.abs(vp - vq).mean() if len(vp) else 0])
    return np.asarray(values)


def extract(raw):
    tick = time.thread_time()
    data = prepare(raw)
    parse_cpu = time.thread_time() - tick
    tick = time.thread_time()
    uniform = rollout(data, .5)
    uniform_cpu = time.thread_time() - tick
    tick = time.thread_time()
    plus, minus = rollout(data, .55), rollout(data, .45)
    paired = response(plus, minus, data[3][data[3] > 0])
    paired_cpu = time.thread_time() - tick
    uniform_phi = np.concatenate([s["phi"] for s in uniform])
    assert uniform_phi.shape == paired.shape == (36,) and np.isfinite(np.r_[uniform_phi, paired]).all()
    return uniform_phi, paired, {"parse_CPU_s": parse_cpu, "uniform_CPU_s": uniform_cpu,
                                 "paired_CPU_s": paired_cpu, "active_variables": int(np.sum(data[3] > 0))}


def semantic_check():
    positive = prepare(b"p cnf 1 1\n1 0\n")
    negative = prepare(b"p cnf 1 1\n-1 0\n")
    a, b = rollout(positive, .5), rollout(negative, .5)
    assert a[-1]["m"][0] > .99 and b[-1]["m"][0] < -.99
    # Feature equivariance only; no solver-runtime labels are augmented.
    raw = b"p cnf 3 2\n1 2 0\n-2 3 0\n"
    complement = b"p cnf 3 2\n-1 -2 0\n2 -3 0\n"
    x, y = rollout(prepare(raw), .55), rollout(prepare(complement), .45)
    assert all(np.allclose(u["m"], -v["m"], atol=1e-10) for u, v in zip(x, y))
    return {"unit_sign": True, "feature_complement_equivariance": True,
            "solver_calls": 0, "runtime_label_augmentation": False}


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        checks = semantic_check()
        keys, _, _, _, _, _ = load()
        base = load_views(keys)[0]["linear42"][0]
        with sqlite3.connect("file:" + str(BASE) + "?mode=ro", uri=True) as db:
            counts = {k: (float(n), float(d)) for k, n, d in db.execute("select hash,variables,vcg_vdegree_mean from features")}
        eligible = np.array([counts[k][0] <= 100000 and round(counts[k][0] * counts[k][1]) <= 100000 for k in keys])
        source = DATA / "cnf_graph_cnn_20261110/feature_receipts.jsonl"
        identity = {r["instance_key"]: r["raw_sha256"] for r in map(json.loads, source.read_text().splitlines())}
        assert int(eligible.sum()) == 1890 and all(k in identity for k, e in zip(keys, eligible) if e)
        panel = ROOT / "work/astra_structure_panel_20261110"
        fallback = {r["instance_key"]: panel / "cnf" / (r["case"] + ".cnf")
                    for r in read_csv(panel / "association_only.csv")}
        index = {key: i for i, key in enumerate(keys)}
        uniform, paired = np.zeros((len(keys), 36)), np.zeros((len(keys), 36))
        uniform_fee, paired_fee = np.zeros(len(keys)), np.zeros(len(keys))
        native = {r["instance_key"]: r["feature_CPU_s"] for r in map(json.loads,
                  (DATA / "native_GBD_route_v3_20261111/feature_receipts.jsonl").read_text().splitlines()) if r["status"] == "ok"}
        base_fee = np.array([native.get(k, 0.) for k in keys])

        def job(key):
            tick = time.thread_time()
            path = ROOT / "work/signed_boundary_20261110/cnf_cache" / (key + ".cnf.gz")
            if not path.is_file():
                path = fallback[key]
            raw = load_formula(path)
            read_cpu = time.thread_time() - tick
            tick = time.thread_time()
            assert hashlib.sha256(raw).hexdigest() == identity[key]
            check_cpu = time.thread_time() - tick
            u, p, record = extract(raw)
            record.update(instance_key=key, read_CPU_s=read_cpu, identity_CPU_s=check_cpu)
            return key, u, p, record

        completed = 0
        with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
            todo = iter(k for k, e in zip(keys, eligible) if e)
            pending = deque(pool.submit(job, next(todo)) for _ in range(4))
            while pending:
                key, u, p, record = pending.popleft().result()
                i = index[key]
                uniform[i], paired[i] = u, p
                shared = record["parse_CPU_s"] + record["read_CPU_s"]
                uniform_fee[i] = shared + record["uniform_CPU_s"]
                paired_fee[i] = shared + record["paired_CPU_s"]
                stream.write(json.dumps(record) + "\n")
                completed += 1
                if completed % 200 == 0:
                    stream.flush()
                    print(f"EXTRACTED {completed}/1890 algebraic responses", flush=True)
                if time.monotonic() - start > 900:
                    raise TimeoutError("bounded cavity feature collection exceeded fifteen minutes")
                key = next(todo, None)
                if key is not None:
                    pending.append(pool.submit(job, key))
        control = np.c_[base, eligible.astype(float)]
        np.savez_compressed(args.out / "features.npz", keys=np.asarray(keys), eligible=eligible,
                            base43=control, uniform79=np.c_[control, uniform], paired79=np.c_[control, paired],
                            base_fee=base_fee, uniform_fee=base_fee + uniform_fee, paired_fee=base_fee + paired_fee)
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "eligible": completed,
              "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
              "uniform_feature_CPU_s": float(uniform_fee.sum()), "paired_feature_CPU_s": float(paired_fee.sum()),
              "reused_native_basic_CPU_s": float(base_fee.sum()), "semantic_checks": checks,
              "new_solver_calls": 0, "short_search_calls": 0,
              "eligibility": "observed variable maximum <=100000 and literal occurrence count <=100000, input-only",
              "source_sha256": sha(__file__), "features_sha256": sha(args.out / "features.npz")})
    except Exception as error:
        write(args.out / "failure.json", {"status": "failed", "error": repr(error),
              "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
              "new_solver_calls": 0, "short_search_calls": 0})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    with threadpool_limits(limits=1):
        main(parser.parse_args())
