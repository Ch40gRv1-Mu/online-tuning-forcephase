"""Freeze a fresh competition cohort and screen only for the fixed SCC rule."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import lzma
import math
from pathlib import Path
import sqlite3
import subprocess
import time

from .collect_signed_topology import BOUNDARY, download
from .common import read, sha, utc, write
from .structural_clusters import write_csv


TRACKS = {f"main_{year}": 400 for year in (2023, 2024, 2025, 2026)}
SUBMISSIONS = {"submissions_2026": 1096}
THRESHOLD = 0.10
GBD_URL = "https://benchmark-database.de/file/"


def source_cohort(meta, base, exclusions, track_sizes):
    with sqlite3.connect(f"file:{meta.resolve()}?mode=ro", uri=True) as db:
        iso = dict(db.execute("select hash,isohash2 from features"))
        tracks = {name: {key for (key,) in db.execute("select hash from track where value=?", (name,))}
                  for name in track_sizes}
    if any(len(keys) != track_sizes[name] for name, keys in tracks.items()):
        raise ValueError("incomplete competition-track metadata")
    with sqlite3.connect(f"file:{base.resolve()}?mode=ro", uri=True) as db:
        features = {key: (size, variables, clauses, binary) for key, size, variables, clauses, binary
                    in db.execute("select hash,bytes,variables,clauses,cls2 from features")
                    if key in iso}
    exposed = set()
    for spec in exclusions:
        file, field = spec.rsplit(":", 1)
        with Path(file).open(newline="") as stream:
            exposed.update(row[field] for row in csv.DictReader(stream))
    exposed_iso = {iso[key] for key in exposed if key in iso and iso[key] not in ("", "empty")}
    source = set().union(*tracks.values())
    cohort = []
    excluded = []
    seen = set()
    ordered = sorted(source, key=lambda key: hashlib.sha256(("scc-fresh-v1:" + key).encode()).hexdigest())
    for key in ordered:
        group = iso.get(key)
        if key in exposed or group in exposed_iso:
            reason = "prior_exposure_exact_or_equivalence"
        elif not group or group == "empty":
            reason = "missing_equivalence_key"
        elif group in seen:
            reason = "duplicate_equivalence_group"
        else:
            seen.add(group)
            try:
                size, variables, clauses, binary = map(int, features[key])
            except (KeyError, ValueError, TypeError):
                excluded.append({"instance_key": key, "reason": "missing_resource_metadata"})
                continue
            if size <= 1_500_000 and variables <= 100_000 and binary > 0:
                cohort.append({"instance_key": key, "group": group, "url": GBD_URL + key,
                               "bytes_gbd": size, "variables_gbd": variables,
                               "clauses": clauses, "binary": binary})
                continue
            reason = "outside_frozen_resource_scope"
        excluded.append({"instance_key": key, "reason": reason})
    return cohort, excluded, tracks


def screen(row, root, verifier, extractor):
    started, cpu = time.monotonic(), time.thread_time()
    key = row["instance_key"]
    result = {"instance_key": key, "status": "error"}
    names = [name for block in BOUNDARY.values() for name in block]
    for attempt in range(2):
        try:
            raw, encoded_bytes = download(row["url"], 1_550_000)
            identity = subprocess.check_output([str(verifier)], input=raw, timeout=8).decode().split()
            if (identity[0], int(identity[1]), int(identity[2])) != (key, row["clauses"], row["binary"]):
                raise ValueError("GBD identity or clause counts differ")
            values = list(map(float, subprocess.check_output([str(extractor), "--boundary"], input=raw, timeout=12).split()))
            if len(values) != len(names) + 3 or not all(map(math.isfinite, values)):
                raise ValueError("invalid SCC feature vector")
            feature = dict(zip(names, values[3:]))["scc_demand_share"]
            (root / "cache" / (key + ".cnf")).write_bytes(raw)
            result.update(status="ok", input_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw),
                          wire_bytes=encoded_bytes, identity_cpu_s=float(identity[4]), screen_cpu_s=values[0],
                          scc_demand_share=feature, screened_action="Fminus" if feature > THRESHOLD else "D")
            break
        except (OSError, ValueError, EOFError, lzma.LZMAError, subprocess.SubprocessError) as exc:
            result.setdefault("errors", []).append({"attempt": attempt + 1, "error": str(exc)})
    result.update(wall_s=time.monotonic() - started, worker_cpu_s=time.thread_time() - cpu)
    write(root / "records" / (key + ".json"), result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--meta", type=Path, required=True)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--exclude", action="append", required=True, metavar="CSV:HASH_COLUMN")
    ap.add_argument("--verifier", type=Path, required=True)
    ap.add_argument("--extractor", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--source", choices=("main", "submissions"), required=True)
    args = ap.parse_args()
    started = time.monotonic()
    rows, excluded, tracks = source_cohort(args.meta, args.base, args.exclude,
                                          TRACKS if args.source == "main" else SUBMISSIONS)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "cache").mkdir()
    if rows:
        write_csv(args.out / "eligible.csv", rows)
    else:
        (args.out / "eligible.csv").write_text("instance_key,group,url,bytes_gbd,variables_gbd,clauses,binary\n")
    write_csv(args.out / "exclusions.csv", excluded)
    receipt = {"source_tracks": {key: len(val) for key, val in tracks.items()},
               "eligible": len(rows), "excluded": len(excluded), "eligible_sha256": sha(args.out / "eligible.csv"),
               "exclusions_sha256": sha(args.out / "exclusions.csv"),
               "gbd_meta_sha256": sha(args.meta), "gbd_base_sha256": sha(args.base),
               "exposure_source_sha256": [sha(item.rsplit(":", 1)[0]) for item in args.exclude],
               "extractor_sha256": sha(args.extractor), "verifier_sha256": sha(args.verifier),
               "threshold": THRESHOLD, "created_utc": utc()}
    write(args.out / "cohort_receipt.json", receipt)

    def extract(row):
        return screen(row, args.out, args.verifier.resolve(), args.extractor.resolve())

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(extract, rows))
    final = []
    for row, result in zip(rows, results):
        assert row["instance_key"] == result["instance_key"]
        if result["status"] == "ok":
            final.append({**row, **{name: result[name] for name in
                         ("input_sha256", "raw_bytes", "scc_demand_share", "screened_action")}})
    if final:
        write_csv(args.out / "screened.csv", final)
    else:
        (args.out / "screened.csv").write_text("instance_key,screened_action\n")
    write(args.out / "screen_summary.json", {
        "eligible": len(rows), "feature_verified": len(final), "failed": len(rows) - len(final),
        "switches": sum(row["screened_action"] == "Fminus" for row in final),
        "screened_sha256": sha(args.out / "screened.csv"), "wall_s": time.monotonic() - started,
        "measured_CPU_s": sum(r.get("identity_cpu_s", 0) + r.get("screen_cpu_s", 0) + r["worker_cpu_s"] for r in results),
    })
    print(read(args.out / "screen_summary.json"))


if __name__ == "__main__":
    main()
