"""Full-incidence community polarity features, computed before SAT search."""

import argparse
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


SEED = 20261111
CHANNELS = 8


def describe(incidence, signed, degree, widths, labels):
    indicator = np.eye(CHANNELS)[labels]
    counts = incidence.T @ indicator
    clause_label = counts.argmax(axis=1)
    clause_indicator = np.eye(CHANNELS)[clause_label]
    weighted = incidence.multiply(1 / np.maximum(widths, 1))
    unsigned = weighted @ clause_indicator
    demand = signed.multiply(1 / np.maximum(widths, 1)) @ clause_indicator
    mass = unsigned.sum(axis=0)
    total = max(float(mass.sum()), 1e-30)
    signed_community = demand.sum(axis=0)
    signed_variable = demand.sum(axis=1)
    unsigned_variable = unsigned.sum(axis=1)
    absolute_variable = np.abs(demand).sum(axis=1)
    boundary = np.count_nonzero(unsigned, axis=1) > 1
    ambiguity = 1 - np.abs(signed_variable) / np.maximum(absolute_variable, 1e-30)
    positive = np.maximum(signed_community, 0).sum()
    negative = np.maximum(-signed_community, 0).sum()
    community_degree = indicator.T @ degree
    probability = community_degree / max(degree.sum(), 1)
    p = probability[probability > 0]
    mixing = 1 - counts.max(axis=1) / np.maximum(widths, 1)
    mixing[widths == 0] = 0
    pairs = np.sum(widths * np.maximum(widths - 1, 0))
    observed = (np.sum(counts * np.maximum(counts - 1, 0)) / max(pairs, 1))
    expected = np.dot(probability, probability)
    bmass = max(float(unsigned_variable[boundary].sum()), 1e-30)
    imass = max(float(unsigned_variable[~boundary].sum()), 1e-30)
    coherent = np.abs(signed_community) > .5 * mass
    result = np.array([
        observed - expected, mixing.mean() if len(mixing) else 0,
        np.dot(mixing, widths) / max(widths.sum(), 1),
        -np.dot(p, np.log(p)) / np.log(CHANNELS), probability.max(),
        np.abs(signed_community).sum() / total,
        1 - abs(signed_community.sum()) / max(np.abs(signed_community).sum(), 1e-30),
        boundary.mean() if len(boundary) else 0,
        degree[boundary].sum() / max(degree.sum(), 1),
        np.dot(ambiguity[boundary], unsigned_variable[boundary]) / bmass,
        signed_variable[boundary].sum() / bmass,
        np.abs(signed_variable[boundary]).sum() / bmass,
        signed_variable[~boundary].sum() / imass,
        np.abs(signed_variable[~boundary]).sum() / imass,
        min(positive, negative) / total, mass[coherent].sum() / total])
    assert result.shape == (16,) and np.isfinite(result).all()
    return result


def extract(raw):
    nodes, clauses, m, n = parse(raw)
    nodes, clauses, widths, _ = normalize(nodes, clauses, m)
    if not len(nodes):
        return np.zeros(32), np.zeros(32), {"active_partition_counts": [0, 0]}
    _, variables = np.unique(nodes // 2, return_inverse=True)
    n = int(variables.max()) + 1
    m = len(widths)
    incidence = coo_matrix((np.ones(len(nodes)), (variables, clauses)), shape=(n, m)).tocsr()
    signed = coo_matrix((1. - 2. * (nodes & 1), (variables, clauses)), shape=(n, m)).tocsr()
    degree = np.asarray(incidence.sum(axis=1)).ravel()
    invsqrt = 1 / np.sqrt(np.maximum(degree, 1))
    normalized = incidence.multiply(invsqrt[:, None]).multiply(1 / np.sqrt(np.maximum(widths, 1))).tocsr()
    stationary = np.sqrt(degree)
    stationary /= max(np.linalg.norm(stationary), 1e-30)
    rng = np.random.default_rng(SEED)
    embedding = rng.normal(size=(n, CHANNELS))
    # These are unsigned incidence-matrix operations. They do not assign a
    # SAT variable or execute a solver transition or unit propagation.
    real, control, occupied = [], [], []
    octaves = np.floor(np.log2(np.maximum(degree, 1))).astype(int)
    for step in range(1, 7):
        embedding = normalized @ (normalized.T @ embedding)
        embedding -= stationary[:, None] * (stationary @ embedding)[None, :]
        embedding /= np.maximum(np.linalg.norm(embedding, axis=0), 1e-30)
        if step not in (3, 6):
            continue
        labels = embedding.argmax(axis=1)
        shuffled = labels.copy()
        for octave in np.unique(octaves):
            use = np.flatnonzero(octaves == octave)
            shuffled[use] = rng.permutation(labels[use])
            assert np.array_equal(np.bincount(labels[use], minlength=CHANNELS),
                                  np.bincount(shuffled[use], minlength=CHANNELS))
        real.extend(describe(incidence, signed, degree, widths, labels))
        control.extend(describe(incidence, signed, degree, widths, shuffled))
        occupied.append(int(len(np.unique(labels))))
    return np.array(real), np.array(control), {"active_partition_counts": occupied}


def check_semantics():
    # In two disconnected, oppositely polarized blocks the aligned
    # partition retains opposition while a mixed partition cancels it.
    incidence = coo_matrix(([1.] * 4, ([0, 1, 2, 3], [0, 0, 1, 1])), shape=(4, 2)).tocsr()
    signed = incidence.multiply(np.array([1, 1, -1, -1])[:, None]).tocsr()
    degree, widths = np.ones(4), np.array([2, 2])
    separated = describe(incidence, signed, degree, widths, np.array([0, 0, 1, 1]))
    mixed = describe(incidence, signed, degree, widths, np.array([0, 1, 0, 1]))
    assert separated[0] > mixed[0] and separated[5] == 1 and mixed[5] == 0
    assert separated[6] == 1
    return {"opposed_disconnected_blocks": True, "solver_calls": 0}


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
        real, control, metadata = extract(raw)
        return key, real, control, {"instance_key": key, "feature_CPU_s": time.thread_time() - began - identity_cpu,
                                   "identity_CPU_s": identity_cpu, "raw_bytes": len(raw), **metadata}

    views = {"base14": base, "community46": np.zeros((len(keys), 46)), "random_partition46": np.zeros((len(keys), 46))}
    new_fee = np.zeros(len(keys))
    index = {key: i for i, key in enumerate(keys)}
    with ThreadPoolExecutor(max_workers=2) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
        for count, (key, real, control, record) in enumerate(pool.map(job, keys[valid]), 1):
            i = index[key]
            views["community46"][i] = np.r_[base[i], real]
            views["random_partition46"][i] = np.r_[base[i], control]
            new_fee[i] = record["feature_CPU_s"]
            stream.write(json.dumps(record) + "\n")
            if count % 300 == 0:
                stream.flush()
                print(f"Extracted {count}/2843 incidence community profiles", flush=True)
            if time.monotonic() - start > 900:
                raise TimeoutError("static community extraction exceeded fifteen minutes")
    np.savez_compressed(args.out / "features.npz", keys=keys, valid=valid, fee=old_fee + new_fee,
                        views=np.asarray(list(views)), **views)
    write(args.out / "collection.json", {"parents": len(keys), "qualified": int(valid.sum()),
          "new_profile_CPU_s": float(new_fee.sum()), "reused_component_CPU_s": float(old_fee.sum()),
          "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
          "new_solver_calls": 0, "short_search_calls": 0, "semantics_checks": checks,
          "source_sha256": sha(__file__), "verified_byte_receipts_sha256": sha(source),
          "parser_source_sha256": sha(Path(__file__).with_name("scc_quotient_features.py")),
          "features_sha256": sha(args.out / "features.npz")})


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        main()
