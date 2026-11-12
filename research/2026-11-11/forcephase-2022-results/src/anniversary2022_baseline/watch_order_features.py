"""Static literal-order proxies for initial watched clauses, without search."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .common import sha, write
from .route_phase_2022 import load_formula
from .scc_quotient_features import normalize, parse
from .structural_clusters import DATA, ROOT, read_csv


def stable_clauses(raw):
    nodes, clauses, m, n = parse(raw)
    _, _, _, meta = normalize(nodes, clauses, m)
    _, first = np.unique(clauses * max(2 * n, 1) + nodes, return_index=True)
    first.sort()
    nodes, clauses = nodes[first], clauses[first]
    keep = ~meta["tautology"][clauses]
    remap = np.cumsum(~meta["tautology"]) - 1
    nodes, clauses = nodes[keep], remap[clauses[keep]]
    widths = np.bincount(clauses, minlength=int((~meta["tautology"]).sum()))
    return nodes, clauses, widths, n


def describe(nodes, clauses, widths, n):
    long = np.flatnonzero(widths >= 3)
    if not len(long):
        return np.zeros(24)
    starts = np.r_[0, widths.cumsum()]
    a, b = starts[long], starts[long] + 1
    positive = (nodes & 1) == 0
    category = 2 * positive[a].astype(int) + positive[b]
    count = np.bincount(category, minlength=4)
    span = np.abs(nodes[a] // 2 - nodes[b] // 2) / max(n - 1, 1)
    degree = np.bincount(nodes // 2, minlength=n)
    leading = np.r_[count / len(long),
                    np.bincount(category, weights=np.log1p(widths[long]), minlength=4) / np.maximum(count, 1),
                    np.bincount(category, weights=span, minlength=4) / np.maximum(count, 1)]
    positions = np.arange(len(nodes)) - starts[clauses]
    tail = positions >= 2
    pair_degree = np.log1p(degree[np.c_[nodes[a] // 2, nodes[b] // 2]])
    pair_rank = np.c_[nodes[a] // 2, nodes[b] // 2] / max(n - 1, 1)
    detail = []
    for direction in (True, False):
        opposed = np.c_[positive[a] != direction, positive[b] != direction]
        both = opposed.all(axis=1)
        first_matching = np.full(len(widths), np.inf)
        use = tail & (positive == direction)
        np.minimum.at(first_matching, clauses[use], positions[use] - 1)
        absent = ~np.isfinite(first_matching[long])
        reads = np.minimum(first_matching[long], widths[long] - 2)
        detail.extend((both.mean(), np.sum(reads[both] / (widths[long][both] - 2)) / max(both.sum(), 1),
                       np.sum(absent & both) / max(both.sum(), 1),
                       pair_rank[opposed].mean() if opposed.any() else 0,
                       pair_degree[opposed].sum() / max(pair_degree.sum(), 1e-30),
                       np.mean(opposed.sum(axis=1) == 1)))
    result = np.r_[leading, detail]
    assert result.shape == (24,) and np.isfinite(result).all()
    return result


def extract(raw):
    nodes, clauses, widths, n = stable_clauses(raw)
    real = describe(nodes, clauses, widths, n)
    order = np.lexsort((np.random.default_rng(20261111).random(len(nodes)), clauses))
    control = describe(nodes[order], clauses, widths, n)
    return real, control


def check_semantics():
    left = stable_clauses(b"p cnf 4 1\n1 2 -3 -4 0\n")
    right = stable_clauses(b"p cnf 4 1\n-3 -4 1 2 0\n")
    a, b = describe(*left), describe(*right)
    assert a[3] == 1 and b[0] == 1 and a[12] == 0 and b[12] == 1
    fixed = stable_clauses(b"p cnf 4 2\n2 2 1 3 0\n1 -1 4 0\n")
    assert fixed[0].tolist() == [2, 0, 4] and fixed[2].tolist() == [3]
    return {"ordered_first_two_signs": True, "stable_literal_dedup_and_tautology": True,
            "solver_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    checks = check_semantics()
    with np.load(DATA / "mechanism_R02_features_20261111/features.npz") as archive:
        keys, valid, base, old_fee = archive["keys"], archive["valid"], archive["base14"], archive["fee"]
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
            raise ValueError("CNF bytes differ from verified input")
        identity_cpu = time.thread_time() - t
        real, control = extract(raw)
        return key, real, control, {"instance_key": key, "feature_CPU_s": time.thread_time() - began - identity_cpu,
                                   "identity_CPU_s": identity_cpu, "raw_bytes": len(raw)}

    views = {"base14": base, "watch_order38": np.zeros((len(keys), 38)), "random_literal38": np.zeros((len(keys), 38))}
    fee = np.zeros(len(keys))
    index = {key: i for i, key in enumerate(keys)}
    with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
        for count, (key, real, control, record) in enumerate(pool.map(job, keys[valid]), 1):
            i = index[key]
            views["watch_order38"][i] = np.r_[base[i], real]
            views["random_literal38"][i] = np.r_[base[i], control]
            fee[i] = record["feature_CPU_s"]
            stream.write(json.dumps(record) + "\n")
            if count % 400 == 0:
                stream.flush()
                print(f"Extracted {count}/2843 static literal-order profiles", flush=True)
            if time.monotonic() - start > 600:
                raise TimeoutError("static literal-order extraction exceeded ten minutes")
    np.savez_compressed(args.out / "features.npz", keys=keys, valid=valid, fee=old_fee + fee,
                        views=np.asarray(list(views)), **views)
    write(args.out / "collection.json", {"parents": len(keys), "qualified": int(valid.sum()),
          "new_profile_CPU_s": float(fee.sum()), "reused_component_CPU_s": float(old_fee.sum()),
          "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
          "new_solver_calls": 0, "short_search_calls": 0, "semantics_checks": checks,
          "source_sha256": sha(__file__), "verified_byte_receipts_sha256": sha(source),
          "parser_source_sha256": sha(Path(__file__).with_name("scc_quotient_features.py")),
          "pinned_sources": {name: sha(ROOT / "work/default_D_source_20261111" / name)
                             for name in ("clause.cpp", "external_propagate.cpp", "internal.hpp")},
          "features_sha256": sha(args.out / "features.npz")})


if __name__ == "__main__":
    main()
