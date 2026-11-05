#!/usr/bin/env python3
"""Create an owner-fixed public static-feature shard; never copy TA labels."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

import node_worker as worker


def prepare_manifest(payload, source_sha, experiment_id, node_id, shard_index, shard_count):
    if not worker.SAFE_ID.fullmatch(experiment_id) or not worker.SAFE_ID.fullmatch(node_id):
        raise ValueError("unsafe experiment/node id")
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("invalid fixed shard index/count")
    raw_tasks = payload["ready_tasks"] if "ready_tasks" in payload else payload.get("tasks")
    if not isinstance(raw_tasks, list):
        raise ValueError("public task input needs tasks or ready_tasks")
    tasks = [worker.normalize_task(t, source_sha) for t in raw_tasks]
    if len({t["task_key"] for t in tasks}) != len(tasks):
        raise ValueError("duplicate public task identities")
    tasks.sort(key=lambda t: t["task_key"])
    shard = [t for i, t in enumerate(tasks) if i % shard_count == shard_index]
    return {"schema_version": worker.SCHEMA, "experiment_id": experiment_id,
            "shard_id": f"shard-{shard_index:03d}-of-{shard_count:03d}", "node_id": node_id,
            "extractor_source_sha256": source_sha, "profile": worker.PROFILE, "tasks": shard}


def build_bundle(public_tasks, source, output, experiment_id, node_id, shard_index, shard_count):
    source = Path(source)
    payload = json.loads(Path(public_tasks).read_text())
    manifest = prepare_manifest(payload, worker.sha(source), experiment_id, node_id, shard_index, shard_count)
    worker_path = Path(worker.__file__)
    files = {"manifest.json": worker.canonical(manifest) + b"\n",
             "cnf_structure.cpp": source.read_bytes(), "node_worker.py": worker_path.read_bytes()}
    files["run.sh"] = ("#!/bin/sh\nset -eu\ncd -- \"$(dirname -- \"$0\")\"\n"
                       "exec python3 node_worker.py --manifest manifest.json --extractor-source cnf_structure.cpp "
                       f"--output-dir output --node-id {node_id} \"$@\"\n").encode()
    files["README.md"] = ("# Public static-feature shard\n\n"
        "Requires Python 3.10+ on Linux/macOS, g++/clang++ with C++17, and HTTPS access to the public CNF source.\n"
        "No TA timings, labels, credentials, private attachments or SAT solver are included.\n"
        "Run `sh run.sh --max-workers 1` after the owner assigns resource slots.\n"
        "The worker additionally caps concurrency by available memory/disk. Extraction uses at most 2 CPU seconds, "
        "8 wall seconds and 3GiB address space per child. Download/decompression costs are reported separately.\n"
        "The output directory is locked to this manifest/node. Completed receipts are immutable and SHA-bound; "
        "failed receipts are retained, and unresolved in-flight work blocks resubmission.\n"
        "Return output/results/*.json, output/completion.json and output/build/*.identity.json to the owner.\n"
        "Do not edit or mix shards, delete lock/identity records, or run a second copy against the same output.\n").encode()
    files["BUNDLE_MANIFEST.json"] = worker.canonical({"schema_version": 1,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
        "node_id": node_id, "task_count": len(manifest["tasks"])}) + b"\n"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz, tarfile.open(fileobj=gz, mode="w") as archive:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), 0, 0o755 if name == "run.sh" else 0o644
            archive.addfile(info, io.BytesIO(data))
    return {"bundle": str(output), "bundle_sha256": worker.sha(output), "node_id": node_id,
            "tasks": len(manifest["tasks"]), "shard_id": manifest["shard_id"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-tasks", required=True, type=Path)
    parser.add_argument("--extractor-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--shard-index", required=True, type=int)
    parser.add_argument("--shard-count", required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.public_tasks, args.extractor_source, args.output, args.experiment_id,
                                  args.node_id, args.shard_index, args.shard_count)))


if __name__ == "__main__":
    main()
