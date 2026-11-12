"""Extract bounded signed-graph features from the official development cohort."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import fcntl
import gzip
import hashlib
import io
import json
import lzma
import math
from pathlib import Path
import resource
import sqlite3
import subprocess
import time
import urllib.request

from .positive_binary_replay import BASE, MANIFEST, MeteredInput, rows, write_json


FEATURES = {
    "scc": ("nontrivial_scc_share", "largest_scc_share", "scc_polarity_separation",
            "log_dag_max_depth", "log_dag_mean_depth", "signed_dag_depth"),
    "reach": ("signed_reach", "absolute_reach_gap", "mean_reach",
              "collision_rate", "signed_collision_rate"),
    "gates": ("gate_density", "gate_sign_balance", "gate_fanout_balance"),
    "exclusion": ("choice_density", "positive_inside_exclusion", "negative_inside_exclusion",
                  "log_positive_external_max", "log_negative_external_max"),
}
BOUNDARY = {
    "equivalence_demand": ("oriented_scc_demand", "scc_demand_share"),
    "gate_boundary": ("gate_boundary_sign", "gate_boundary_strength"),
    "component_disagreement": ("block_disagreement", "block_signed_demand", "block_coherence", "largest_block_share"),
    "repair_concentration": ("plus_repair_concentration", "minus_repair_concentration", "opposed_clause_contrast"),
    "static_unit_pressure": ("aligned_unit_contrast", "opposed_unit_contrast", "conflict_contrast", "unit_pressure"),
}
PRESSURE = {
    "static_unit_pressure": BOUNDARY["static_unit_pressure"],
    "raw_sign_width": ("pure_positive_share", "pure_negative_share", "raw_binary_share", "raw_mean_width"),
}
FEATURE_SETS = {"topology": FEATURES, "boundary": BOUNDARY, "pressure": PRESSURE, "boundary-transfer": BOUNDARY}


def eligible(feature_set="topology"):
    manifest = {row["instance_key"]: row["url"] for row in rows(MANIFEST)}
    with sqlite3.connect(f"file:{BASE}?mode=ro", uri=True) as db:
        counts = {key: tuple(map(int, fields)) for key, *fields in db.execute(
            "select hash,bytes,variables,clauses,cls2 from features") if key in manifest}
    assert len(manifest) == 4719 and counts.keys() == manifest.keys()
    original = {key for key, (size, variables, _, binary) in counts.items()
                if size <= 1_500_000 and variables <= 100_000 and binary > 0}
    expanded = {key for key, (size, *_) in counts.items() if size <= 3_000_000}
    scope = {"pressure": expanded, "boundary-transfer": expanded - original}.get(feature_set, original)
    return {key: (manifest[key], counts[key][0], *counts[key][2:]) for key in scope}


def download(url, max_bytes):
    with urllib.request.urlopen(url, timeout=15) as response:
        meter = MeteredInput(response)
        with io.BufferedReader(meter) as data:
            magic = data.peek(6)
            if magic.startswith(b"\xfd7zXZ\x00"):
                plain = lzma.LZMAFile(data)
            elif magic.startswith(b"\x1f\x8b"):
                plain = gzip.GzipFile(fileobj=data)
            else:
                plain = data
            with plain:
                raw = plain.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("DIMACS stream exceeded the extraction limit")
    return raw, meter.bytes_read


def measure(key, item, command, checker, local_file, names, cache, feature_set, cache_only):
    start, cpu = time.monotonic(), time.thread_time()
    url, _, clauses, binary = item
    record = {"instance_key": key, "status": "error"}
    pressure = feature_set == "pressure"
    max_bytes = 3_050_000 if feature_set in ("pressure", "boundary-transfer") else 1_550_000
    try:
        if local_file is None:
            if cache_only:
                raise FileNotFoundError("formula absent from local cache")
            raw, wire_bytes = download(url, max_bytes)
        else:
            if local_file.suffix == ".gz":
                with gzip.open(local_file, "rb") as stream:
                    raw = stream.read(max_bytes + 1)
            else:
                raw = local_file.read_bytes()
            wire_bytes = 0
            if len(raw) > max_bytes:
                raise ValueError("cached DIMACS exceeds extraction limit")
        record.update(raw_bytes=len(raw), wire_bytes=wire_bytes)
        verification = command if pressure else [str(checker)]
        verified = subprocess.check_output(verification, input=raw, timeout=5).decode().split()
        if (verified[0], int(verified[1]), int(verified[2])) != (key, clauses, binary):
            raise ValueError("GBD hash or clause counts differ")
        if pressure:
            # The same pass produces both the verified identity and features.
            values = [float(verified[4]), 0, 0, *map(float, verified[5:])]
        else:
            record["identity_cpu_s"] = float(verified[4])
            proc = subprocess.run(command, input=raw, capture_output=True, timeout=10, check=True)
            values = list(map(float, proc.stdout.split()))
        if len(values) != len(names) + 3 or not all(map(math.isfinite, values)):
            raise ValueError("invalid feature vector")
        record.update(status="ok", feature_cpu_s=values[0], active_binary_variables=int(values[1]),
                      truncated_root_share=values[2], features=dict(zip(names, values[3:])))
        if cache and local_file is None:
            path = cache / (key + ".cnf.gz")
            temporary = path.with_suffix(".part")
            try:
                temporary.write_bytes(gzip.compress(raw, compresslevel=1, mtime=0))
                temporary.replace(path)
            except OSError as exc:
                record["cache_error"] = str(exc)
    except (OSError, ValueError, EOFError, lzma.LZMAError, subprocess.SubprocessError) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    record.update(wall_s=time.monotonic() - start, worker_cpu_s=time.thread_time() - cpu)
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--checker", required=True, type=Path)
    ap.add_argument("--parser", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--panel", type=Path)
    ap.add_argument("--feature-set", choices=FEATURE_SETS, default="topology")
    ap.add_argument("--cache", type=Path)
    ap.add_argument("--cache-only", action="store_true")
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    dataset = eligible(args.feature_set)
    existing = {}
    if args.panel:
        existing = {r["instance_key"]: args.panel / "cnf" / (r["case"] + ".cnf")
                    for r in rows(args.panel / "association_only.csv")}
    args.out.mkdir(parents=True, exist_ok=True)
    records = args.out / "records"
    records.mkdir(exist_ok=True)
    checker, parser = args.checker.resolve(), args.parser.resolve()
    mode = "boundary" if args.feature_set == "boundary-transfer" else args.feature_set
    command = [str(parser)] + (["--" + mode] if mode != "topology" else [])
    names = [name for block in FEATURE_SETS[args.feature_set].values() for name in block]
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)
    for executable in (checker, parser):
        if not executable.is_file():
            ap.error(f"missing executable {executable}")

    def collect(key):
        path = records / (key + ".json")
        if path.exists():
            record = json.loads(path.read_text())
            if record["instance_key"] != key:
                raise ValueError("record key mismatch")
            return record
        local = existing.get(key)
        if local is None and args.cache:
            cached = args.cache / (key + ".cnf.gz")
            if cached.is_file():
                local = cached
        record = measure(key, dataset[key], command, checker, local, names, args.cache, args.feature_set, args.cache_only)
        write_json(path, record)
        return record

    with (args.out / "collector.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        spec = {"feature_set": args.feature_set, "feature_names": names,
                "parser_sha256": hashlib.sha256(parser.read_bytes()).hexdigest(),
                "checker_sha256": hashlib.sha256(checker.read_bytes()).hexdigest(),
                "dataset_sha256": hashlib.sha256(json.dumps(dataset, sort_keys=True).encode()).hexdigest()}
        identity = args.out / "extraction_spec.json"
        if identity.exists():
            if json.loads(identity.read_text()) != spec:
                raise ValueError("existing output belongs to another extraction")
        elif any(records.iterdir()):
            raise ValueError("existing records have no matching extraction identity")
        else:
            write_json(identity, spec)
        ordered = sorted(dataset, key=lambda key: (dataset[key][1], key))
        print(f"{len(ordered)} feature-eligible formulas, {args.workers} workers.", flush=True)
        counts = Counter()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for i, record in enumerate(pool.map(collect, ordered), 1):
                counts[record["status"]] += 1
                if i % 200 == 0 or i == len(ordered):
                    print(f"{i}/{len(ordered)} processed, {counts['ok']} verified.", flush=True)
        child_end = resource.getrusage(resource.RUSAGE_CHILDREN)
        write_json(args.out / "collection.json", {
            "eligible": len(ordered), "counts": counts, "elapsed_wall_s": time.monotonic() - start,
            "feature_set": args.feature_set,
            "collector_cpu_s": time.process_time() - cpu,
            "child_cpu_s": child_end.ru_utime + child_end.ru_stime - children.ru_utime - children.ru_stime,
        })


if __name__ == "__main__":
    main()
