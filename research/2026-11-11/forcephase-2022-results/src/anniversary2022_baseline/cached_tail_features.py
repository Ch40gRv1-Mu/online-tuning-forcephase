"""Test previously unused graph-tail and polarity-range cache summaries."""

import argparse
from pathlib import Path
import sqlite3
import time

import numpy as np

from .common import sha, write
from .structural_clusters import BASE, load
from .structural_views import features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    keys, base, _, _, _, _ = load()
    names = ["vcg_vdegree", "vcg_cdegree", "vg_degree", "cg_degree"]
    fields = [name + "_" + stat for name in names for stat in ("mean", "variance", "min", "max", "entropy")]
    fields += [name + "_" + stat for name in ("balancecls", "balancevars") for stat in ("min", "max", "entropy")]
    with sqlite3.connect("file:" + str(BASE) + "?mode=ro", uri=True) as db:
        data = {key: values for key, *values in db.execute("select hash," + ",".join(fields) + " from features")}
    raw = np.array([data[key] for key in keys], dtype=float)
    valid = np.isfinite(raw).all(axis=1) & (raw >= 0).all(axis=1)
    safe = np.where(np.isfinite(raw), np.maximum(raw, 0), 0)
    tail = []
    for i in range(4):
        mean, variance, minimum, maximum, entropy = safe[:, 5 * i:5 * (i + 1)].T
        tail.extend((np.log1p(mean), np.log1p(variance / np.maximum(mean ** 2, 1e-12)),
                     np.log1p(maximum / np.maximum(mean, 1e-12)),
                     minimum / np.maximum(mean, 1e-12), entropy))
    for i in range(2):
        minimum, maximum, entropy = safe[:, 20 + 3 * i:23 + 3 * i].T
        tail.extend((maximum - minimum, entropy))
    tail = np.column_stack(tail)
    assert tail.shape == (len(keys), 24) and np.isfinite(tail).all()
    control = features(keys, base)[0]["combined"]
    views = {"base28": control, "tail24": tail, "base_plus_tail52": np.c_[control, tail]}
    args.out.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(args.out / "features.npz", keys=np.asarray(keys), valid=valid, fee=np.zeros(len(keys)),
                        views=np.asarray(list(views)), **views,
                        cost_status=np.asarray("GBD acquisition unmeasured optimistic zero; predictive evidence only"))
    write(args.out / "collection.json", {"parents": len(keys), "qualified": int(valid.sum()),
          "physical_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
          "new_CNF_feature_calls": 0, "new_solver_calls": 0, "short_search_calls": 0,
          "source_sha256": sha(__file__), "GBD_sha256": sha(BASE),
          "fields": fields, "features_sha256": sha(args.out / "features.npz"),
          "deployment_acquisition_CPU_s": None})


if __name__ == "__main__":
    main()
