"""Extract static order-dependent polarity profiles without assigning variables."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .common import sha, write
from .predict_relative_cost import SPLITS, load_views
from .route_phase_2022 import load_formula
from .structural_clusters import DATA, ROOT, read_csv


BINS = 8
SEED = 20261111


def extract(raw):
    body = []
    declared = None
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(b"c"):
            continue
        if line.startswith(b"p"):
            fields = line.split()
            if declared is not None or fields[:2] != [b"p", b"cnf"] or len(fields) != 4:
                raise ValueError("invalid CNF header")
            declared = tuple(map(int, fields[2:]))
        else:
            body.append(line)
    if declared is None:
        raise ValueError("missing CNF header")
    tokens = np.fromstring(b" ".join(body).decode("ascii"), dtype=np.int64, sep=" ")
    ends = np.flatnonzero(tokens == 0)
    assert len(ends) == declared[1] and len(tokens) and tokens[-1] == 0
    widths = np.diff(np.r_[-1, ends]) - 1
    literals = tokens[tokens != 0]
    ids, v = np.unique(np.abs(literals), return_inverse=True)
    n = len(ids)
    if n == 0:
        return np.zeros(8), np.zeros(76), np.zeros(76)
    assert ids.max() <= declared[0]
    pos = literals > 0
    clause = np.repeat(np.arange(len(widths)), widths)
    weight = np.exp2(-np.minimum(widths[clause] - 1, 60))
    p = np.bincount(v, weights=weight * pos, minlength=n)
    q = np.bincount(v, weights=weight * ~pos, minlength=n)
    degree = np.bincount(v, minlength=n).astype(float)
    bias = (p - q) / np.maximum(p + q, 1e-30)
    ambiguity = np.maximum(0, 1 - bias * bias)
    positive_degree = np.bincount(v, weights=pos, minlength=n)
    pure_sign = (positive_degree == degree).astype(float) - (positive_degree == 0)
    starts = np.r_[0, widths.cumsum()]
    binary = np.flatnonzero(widths == 2)
    a, b = starts[binary], starts[binary] + 1
    keep = v[a] != v[b]
    a, b = a[keep], b[keep]

    def profile(rank):
        bins = np.minimum(BINS - 1, rank * BINS // n)
        counts = np.bincount(bins, minlength=BINS)
        mass = np.bincount(bins, weights=degree, minlength=BINS)
        sums = [np.bincount(bins, weights=x, minlength=BINS) / np.maximum(counts, 1)
                for x in (bias, ambiguity, pure_sign)]
        weighted = np.bincount(bins, weights=degree * bias, minlength=BINS) / np.maximum(mass, 1)
        first_a = rank[v[a]] > rank[v[b]]
        early, late = np.where(first_a, a, b), np.where(first_a, b, a)
        category = 2 * pos[early].astype(int) + pos[late]
        index = category * BINS + bins[v[early]]
        signs = np.bincount(index, minlength=4 * BINS) / max(len(a), 1)
        gap = np.abs(rank[v[a]] - rank[v[b]]) / max(n - 1, 1)
        spans = np.bincount(category, weights=gap, minlength=4) / np.maximum(
            np.bincount(category, minlength=4), 1)
        return np.r_[*sums, weighted, mass / max(degree.sum(), 1), signs, spans]

    pp = pos[a] & pos[b]
    nn = ~pos[a] & ~pos[b]
    marginal = np.array([bias.mean(), np.dot(degree, bias) / max(degree.sum(), 1),
                         ambiguity.mean(), pure_sign.mean(), pp.sum() / max(len(a), 1),
                         nn.sum() / max(len(a), 1), (~pp & ~nn).sum() / max(len(a), 1),
                         np.log1p(degree.var() / max(degree.mean() ** 2, 1e-30))])
    ordered = profile(np.arange(n))
    random_order = profile(np.random.default_rng(SEED).permutation(n))
    assert ordered.shape == random_order.shape == (76,)
    assert np.isfinite(np.r_[marginal, ordered, random_order]).all()
    return marginal, ordered, random_order


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    split = read_csv(SPLITS)
    keys = [row["instance_key"] for row in split]
    rule, valid, old_fee = load_views(keys, None, split, "rule6")["rule6_costed"]
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
            raise ValueError("CNF bytes differ from the already verified input")
        identity_cpu = time.thread_time() - t
        values = extract(raw)
        elapsed = time.thread_time() - began - identity_cpu
        return key, values, {"instance_key": key, "feature_CPU_s": elapsed,
                             "identity_CPU_s": identity_cpu, "raw_bytes": len(raw)}

    arrays = {"base14": np.zeros((len(keys), 14)), "ordered90": np.zeros((len(keys), 90)),
              "random_order90": np.zeros((len(keys), 90))}
    index = {key: i for i, key in enumerate(keys)}
    new_fee = np.zeros(len(keys))
    with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
        for count, (key, values, record) in enumerate(pool.map(job, [k for k, e in zip(keys, valid) if e]), 1):
            i = index[key]
            marginal, ordered, random_order = values
            arrays["base14"][i] = np.r_[rule[i], marginal]
            arrays["ordered90"][i] = np.r_[rule[i], marginal, ordered]
            arrays["random_order90"][i] = np.r_[rule[i], marginal, random_order]
            new_fee[i] = record["feature_CPU_s"]
            stream.write(json.dumps(record) + "\n")
            if count % 400 == 0:
                stream.flush()
                print(f"Extracted {count}/2843 static order profiles", flush=True)
    np.savez_compressed(args.out / "features.npz", keys=np.asarray(keys), valid=valid,
                        fee=old_fee + new_fee, **arrays)
    write(args.out / "collection.json", {"parents": len(keys), "qualified": int(valid.sum()),
          "new_profile_CPU_s": float(new_fee.sum()), "old_component_CPU_s": float(old_fee.sum()),
          "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
          "new_solver_calls": 0, "short_search_calls": 0,
          "source_sha256": sha(__file__), "verified_byte_receipts_sha256": sha(source),
          "features_sha256": sha(args.out / "features.npz")})


if __name__ == "__main__":
    main()
