"""Pool continuous CNF fields by initial variable rank, with matched shuffling."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .cavity_response_features import prepare, rollout, response
from .common import sha, write
from .route_phase_2022 import load_formula
from .structural_clusters import DATA, ROOT, read_csv


def bands(degree):
    """Original sorted active variable order versus degree-stratified shuffle."""
    degree = np.asarray(degree)
    assert np.all(degree > 0)
    n = len(degree)
    ordered = np.minimum(7, np.arange(n) * 8 // max(n, 1))
    shuffled = ordered.copy()
    strata = np.floor(np.log2(degree)).astype(int)
    rng = np.random.default_rng(20261119)
    for group in np.unique(strata):
        ids = np.flatnonzero(strata == group)
        shuffled[ids] = ordered[rng.permutation(ids)]
        assert np.array_equal(np.sort(shuffled[ids]), np.sort(ordered[ids]))
    return ordered, shuffled


def pool(fields, group):
    count = np.bincount(group, minlength=8)
    return np.concatenate([np.bincount(group, weights=f, minlength=8) /
                           np.maximum(count, 1) for f in fields])


def extract(raw):
    tick = time.thread_time()
    data = prepare(raw)
    active = data[3] > 0
    degree = data[3][active]
    parse_cpu = time.thread_time() - tick
    tick = time.thread_time()
    uniform = rollout(data, .5)
    plus, minus = rollout(data, .55), rollout(data, .45)
    pooled = np.r_[np.concatenate([s["phi"] for s in uniform]), response(plus, minus, degree)]
    math_cpu = time.thread_time() - tick
    tick = time.thread_time()
    u, p, q = uniform[-1]["m"], plus[-1]["m"], minus[-1]["m"]
    fields = np.array([u, np.abs(u), .5 * (p + q), np.abs(p - q), p * q,
                       u * data[5][active]])
    # Group generation is included in both alternatives, conservatively.
    ordered, shuffled = bands(degree)
    common_pool_cpu = time.thread_time() - tick
    tick = time.thread_time()
    actual = pool(fields, ordered)
    actual_cpu = common_pool_cpu + time.thread_time() - tick
    tick = time.thread_time()
    control = pool(fields, shuffled)
    control_cpu = common_pool_cpu + time.thread_time() - tick
    assert pooled.shape == (72,) and actual.shape == control.shape == (48,)
    assert np.isfinite(np.r_[pooled, actual, control]).all()
    return pooled, actual, control, {"parse_CPU_s": parse_cpu, "math_CPU_s": math_cpu,
                                   "ordered_pool_CPU_s": actual_cpu,
                                   "random_pool_CPU_s": control_cpu,
                                   "active_variables": len(degree)}


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        reference = DATA / "mechanism_R16_features_20261111/features.npz"
        with np.load(reference) as z:
            keys, eligible, base = z["keys"].tolist(), z["eligible"].copy(), z["base43"].copy()
            expected = np.c_[z["uniform79"][:, 43:], z["paired79"][:, 43:]]
            native_fee = z["base_fee"].copy()
        assert len(keys) == 4719 and eligible.sum() == 1890
        identity = {r["instance_key"]: r["raw_sha256"] for r in map(json.loads,
                    (DATA / "cnf_graph_cnn_20261110/feature_receipts.jsonl").read_text().splitlines())}
        panel = ROOT / "work/astra_structure_panel_20261110"
        fallback = {r["instance_key"]: panel / "cnf" / (r["case"] + ".cnf")
                    for r in read_csv(panel / "association_only.csv")}
        index = {key: i for i, key in enumerate(keys)}
        pooled = np.zeros((len(keys), 72))
        actual, random = np.zeros((len(keys), 48)), np.zeros((len(keys), 48))
        pooled_fee, actual_fee, random_fee = [native_fee.copy() for _ in range(3)]

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
            p, a, r, rec = extract(raw)
            rec.update(instance_key=key, read_CPU_s=read_cpu, identity_CPU_s=identity_cpu,
                       raw_sha256=identity[key])
            assert np.allclose(p, expected[index[key]], rtol=1e-12, atol=1e-12)
            return key, p, a, r, rec

        completed = 0
        with ThreadPoolExecutor(max_workers=4) as executor, (args.out / "feature_receipts.jsonl").open("w") as stream:
            todo = iter(k for k, e in zip(keys, eligible) if e)
            pending = deque(executor.submit(job, next(todo)) for _ in range(4))
            while pending:
                key, p, a, r, rec = pending.popleft().result()
                i = index[key]
                pooled[i], actual[i], random[i] = p, a, r
                shared = rec["read_CPU_s"] + rec["parse_CPU_s"] + rec["math_CPU_s"]
                pooled_fee[i] += shared
                actual_fee[i] += shared + rec["ordered_pool_CPU_s"]
                random_fee[i] += shared + rec["random_pool_CPU_s"]
                stream.write(json.dumps(rec) + "\n")
                completed += 1
                if completed % 200 == 0:
                    stream.flush()
                    print(f"EXTRACTED {completed}/1890 rank-conditioned fields", flush=True)
                if time.monotonic() - start > 600:
                    raise TimeoutError("rank-conditioned extraction exceeded ten minutes")
                key = next(todo, None)
                if key is not None:
                    pending.append(executor.submit(job, key))
        np.savez_compressed(args.out / "features.npz", keys=np.array(keys), eligible=eligible,
                            pooled115=np.c_[base, pooled], ordered163=np.c_[base, pooled, actual],
                            random163=np.c_[base, pooled, random], pooled_fee=pooled_fee,
                            ordered_fee=actual_fee, random_fee=random_fee)
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "eligible": completed,
              "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
              "pooled_logical_CPU_s": float(pooled_fee.sum()),
              "ordered_logical_CPU_s": float(actual_fee.sum()), "random_logical_CPU_s": float(random_fee.sum()),
              "eligibility": "R16 formula-count predicate; nmax<=100000 and literal occurrences<=100000",
              "new_solver_calls": 0, "short_search_calls": 0, "pooled_reference_all_match": True,
              "source_sha256": sha(__file__), "reference_features_sha256": sha(reference),
              "features_sha256": sha(args.out / "features.npz"),
              "unknown_native_acquisition_parents": 1876})
    except Exception as error:
        write(args.out / "failure.json", {"status": "failed", "error": repr(error),
              "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    with threadpool_limits(limits=1):
        main(parser.parse_args())
