"""Create matched, anonymized examples for structural hypothesis generation."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import gzip
import json
import lzma
from pathlib import Path
import sqlite3
import subprocess
import urllib.request

import numpy as np

from .structural_clusters import ACTIONS, BASE, DATA, FEATURES, ROOT, distances, load, read_csv, standardize, write_csv


def stage(row, output, checker):
    with urllib.request.urlopen(row["url"], timeout=20) as response:
        encoded = response.read(8 * 1024**2 + 1)
    if len(encoded) > 8 * 1024**2:
        raise ValueError("example transfer exceeded 8 MiB")
    if encoded.startswith(b"\xfd7zXZ\x00"):
        plain = lzma.decompress(encoded)
    elif encoded.startswith(b"\x1f\x8b"):
        plain = gzip.decompress(encoded)
    else:
        plain = encoded
    if len(plain) > 4 * 1024**2:
        raise ValueError("example DIMACS exceeded 4 MiB")
    # Preserve the input sequence, literal spelling, and whitespace apart from comments.
    plain = b"".join(line for line in plain.splitlines(keepends=True) if not line.lstrip().startswith(b"c"))
    receipt = subprocess.check_output([str(checker.resolve())], input=plain, timeout=20).decode().split()
    if receipt[0] != row["instance_key"]:
        raise ValueError("anonymized CNF identity does not match the recorded benchmark")
    (output / f"{row['case']}.cnf").write_bytes(plain)
    return {"case": row["case"], "bytes": len(plain), "positive_binary": int(receipt[3]), "binary": int(receipt[2])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    args = parser.parse_args()
    ids, X, costs, winners, _, _ = load()
    scaled, _ = standardize(X, X)
    prior = DATA / "structural_clusters_20261110/instances.csv"
    clusters = {row["instance_key"]: int(row["cluster"]) for row in read_csv(prior)}
    with sqlite3.connect(f"file:{BASE}?mode=ro", uri=True) as db:
        size = {key: int(value) for key, value in db.execute("select hash,bytes from features")}
    manifest = {r["instance_key"]: r["url"] for r in read_csv(ROOT / "configs/anniversary2022_baseline/manifest.official-solvable.v1.csv")}
    rank = np.sort(costs, axis=1)
    eligible = (rank[:, 1] - rank[:, 0] >= 2) & (rank[:, 1] >= 1.25 * rank[:, 0]) & np.array([size[k] <= 2_000_000 for k in ids])
    available = np.ones(len(ids), dtype=bool)
    panel = []
    mapping = []
    labels = np.array([clusters[key] for key in ids])
    for cluster in range(1, 9):
        groups = [np.flatnonzero(eligible & available & (winners == a) & (labels == cluster)) for a in ACTIONS]
        if any(not len(group) for group in groups):
            continue
        d, plus, minus = groups
        dp = distances(scaled[d], scaled[plus])
        dm = distances(scaled[d], scaled[minus])
        anchor = int((dp.min(axis=1) + dm.min(axis=1)).argmin())
        triple = [d[anchor], plus[dp[anchor].argmin()], minus[dm[anchor].argmin()]]
        for i in triple:
            available[i] = False
            case = f"case_{len(panel) + 1:02d}"
            row = {"case": case, "triplet": cluster, "winner": winners[i], "estimated_cnf_bytes": size[ids[i]],
                   **{action + "_par2": costs[i, j] for j, action in enumerate(ACTIONS)},
                   **dict(zip(FEATURES, X[i]))}
            panel.append(row)
            mapping.append({"case": case, "instance_key": ids[i], "url": manifest[ids[i]]})
    assert len(panel) >= 6
    args.out.mkdir(parents=True, exist_ok=False)
    cnf = args.out / "cnf"
    cnf.mkdir()
    write_csv(args.out / "panel.csv", panel)
    write_csv(args.out / "association_only.csv", mapping)

    def get(row):
        try:
            return stage(row, cnf, args.checker)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return {"case": row["case"], "error": str(error)}

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(get, mapping))
    (args.out / "cnf_receipts.json").write_text(json.dumps(records, indent=2) + "\n")
    print(f"Selected {len(panel)} examples; verified {sum('error' not in r for r in records)} raw formulas.")


if __name__ == "__main__":
    main()
