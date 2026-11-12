"""Collect a frozen static mechanism on the existing, byte-bound CNF cache."""

from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .common import sha, write
from .route_phase_2022 import load_formula
from .structural_clusters import DATA, ROOT, read_csv


def collect(out, extractor, dimensions, checks, source):
    start, cpu = time.monotonic(), time.process_time()
    out.mkdir(parents=True, exist_ok=False)
    with (out / "owner.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            check_receipt = checks()
            with np.load(DATA / "mechanism_R02_features_20261111/features.npz") as archive:
                keys, valid, base, old_fee = archive["keys"], archive["valid"], archive["base14"], archive["fee"]
            identities_path = DATA / "cnf_graph_cnn_20261110/feature_receipts.jsonl"
            identities = {r["instance_key"]: r["raw_sha256"]
                          for r in map(json.loads, identities_path.read_text().splitlines())}
            panel = ROOT / "work/astra_structure_panel_20261110"
            files = {r["instance_key"]: panel / "cnf" / (r["case"] + ".cnf")
                     for r in read_csv(panel / "association_only.csv")}
            arrays = {name: np.zeros((len(keys), 14 + d)) for name, d in dimensions.items()}
            fees = np.zeros(len(keys))
            index = {key: i for i, key in enumerate(keys)}

            def job(key):
                begin = time.thread_time()
                path = ROOT / "work/signed_boundary_20261110/cnf_cache" / (key + ".cnf.gz")
                if not path.is_file():
                    path = files[key]
                raw = load_formula(path)
                tick = time.thread_time()
                if hashlib.sha256(raw).hexdigest() != identities[key]:
                    raise ValueError("input differs from previously verified CNF bytes")
                identity_fee = time.thread_time() - tick
                values, metadata = extractor(raw)
                assert values.keys() == dimensions.keys()
                for name, d in dimensions.items():
                    assert values[name].shape == (d,) and np.isfinite(values[name]).all()
                return key, values, {"instance_key": key, "feature_CPU_s": time.thread_time() - begin - identity_fee,
                                     "identity_CPU_s": identity_fee, "raw_bytes": len(raw), **metadata}

            with ThreadPoolExecutor(max_workers=4) as pool, (out / "feature_receipts.jsonl").open("w") as stream:
                for count, (key, values, record) in enumerate(pool.map(job, keys[valid]), 1):
                    i = index[key]
                    for name in dimensions:
                        arrays[name][i] = np.r_[base[i], values[name]]
                    fees[i] = record["feature_CPU_s"]
                    stream.write(json.dumps(record) + "\n")
                    if count % 400 == 0:
                        stream.flush()
                        print(f"Extracted {count}/{valid.sum()} static mechanism profiles", flush=True)
                    if time.monotonic() - start > 900:
                        raise TimeoutError("static mechanism collection exceeded fifteen minutes")
            np.savez_compressed(out / "features.npz", keys=keys, valid=valid, fee=old_fee + fees,
                                views=np.asarray(list(arrays)), **arrays)
            write(out / "collection.json", {"status": "complete", "parents": len(keys), "qualified": int(valid.sum()),
                  "new_profile_CPU_s": float(fees.sum()), "reused_component_CPU_s": float(old_fee.sum()),
                  "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
                  "new_solver_calls": 0, "short_search_calls": 0, "semantics_checks": check_receipt,
                  "collector_source_sha256": sha(__file__), "feature_source_sha256": sha(source),
                  "verified_byte_receipts_sha256": sha(identities_path),
                  "parser_source_sha256": sha(Path(__file__).with_name("scc_quotient_features.py")),
                  "features_sha256": sha(out / "features.npz")})
        except Exception as error:
            write(out / "failure.json", {"status": "failed", "error": repr(error),
                  "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
                  "new_solver_calls": 0, "short_search_calls": 0})
            raise
