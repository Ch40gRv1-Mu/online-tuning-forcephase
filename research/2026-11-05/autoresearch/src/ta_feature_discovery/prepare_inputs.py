"""Join permitted TA labels and immutable static-feature receipts; never solve SAT.

Only development_fit/development_feedback records are exported.  Source SAT
answers and complete-run counters are labels/diagnostics, never input features.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "work/phase_prediction_20261104/project"
DEFAULT_SOURCE = Path("/Users/expexp/.codex/attachments/d72b682d-d232-4410-838a-6fbcb063bbc5/data.xlsx")
DEFAULT_PAIRS = PROJECT / "results/phase_prediction_v1/professor_pairs.csv"
DEFAULT_ROLES = PROJECT / "results/phase_prediction_v1/development_frozen.csv"
PUBLIC_CHECKSUM_CSV = Path("/Users/expexp/Documents/Codex/2026-10-28/new-chat/work/forcephase/benchmarks/checksums.csv")
LEGACY_EXTRACTOR_SHA = "2f4cc472d4430b10785688b68ec0afb5d80e18eb7c90564754d08214c398f334"
FEATURES = (
    "s_mean_length", "s_length_std", "s_binary_fraction", "s_long_fraction",
    "s_positive_fraction", "s_mean_polarity_imbalance",
    "g_cycle_excess_per_incidence", "g_leaf_variable_fraction",
    "g_largest_component_fraction", "g_gate_motif_fraction",
)
ROLES = {"development_fit", "development_feedback"}
MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"[0-9a-f]{32}", re.I)
NODE_PROFILE = {"kind": "cnf_static_v1", "extract_cpu_s": 2.0,
                "extract_wall_s": 8.0, "extract_memory_bytes": 3 * 1024**3,
                "max_plain_bytes": 100_000_000, "max_download_bytes": 128 * 1024**2}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def canonical_sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def identifier(value) -> str:
    # GBD names use a leading hash, while the descriptive suffix can itself
    # contain hexadecimal seeds.  Directory names and suffixes are not IDs.
    basename = str(value).replace("\\", "/").rsplit("/", 1)[-1]
    match = re.match(r"^([0-9a-f]{32})(?:$|[-_.])", basename, re.I)
    if match is None:
        raise ValueError("source basename must start with a delimited GBD hash")
    return match.group(1).lower()


def number(value, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} is not a numeric measurement")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"invalid {name}")
    return result


def load_roles(path: Path, expected_counts=None):
    """Read public identities/roles, checking equivalence isolation before labels."""
    selected, seen, groups = [], set(), collections.defaultdict(set)
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            h = identifier(row["hash"])
            if h in seen:
                raise ValueError("duplicate hash in role manifest")
            seen.add(h)
            group = row.get("isohash") or h
            if group.lower() in {"empty", "none", "unknown"}:
                group = h
            groups[group].add(row["role"])
            if row["role"] in ROLES:
                selected.append({**row, "hash": h, "group": group})
    if any(len(role_set) > 1 and role_set.intersection(ROLES) for role_set in groups.values()):
        raise ValueError("equivalence group crosses frozen roles")
    counts = dict(collections.Counter(row["role"] for row in selected))
    if expected_counts is not None and counts != expected_counts:
        raise ValueError(f"development role counts differ: {counts}")
    return selected


def xlsx_cells(path: Path):
    """Yield source rows from sheet data using stdlib; no workbook execution."""
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(x.itertext()) for x in shared.findall(MAIN + "si")]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.find(MAIN + "sheets")
        chosen = next((s for s in sheets if s.attrib["name"] == "data"), None)
        if chosen is None:
            raise ValueError("expected workbook sheet data")
        relation_id = chosen.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(x.attrib["Target"] for x in relations if x.attrib["Id"] == relation_id)
        member = target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
        header = None
        with archive.open(member) as stream:
            for _, element in ET.iterparse(stream, events=("end",)):
                if element.tag != MAIN + "row":
                    continue
                values = {}
                for cell in element.findall(MAIN + "c"):
                    column = re.match(r"[A-Z]+", cell.attrib["r"]).group()
                    if header is not None and header.get(column) not in {"ile", "file", "hash", "polarity_mode", "result", "wall_time_s"}:
                        continue
                    kind = cell.attrib.get("t")
                    val = cell.find(MAIN + "v")
                    if kind == "inlineStr":
                        raw = "".join(cell.find(MAIN + "is").itertext())
                    elif val is None:
                        raw = None
                    elif kind == "s":
                        raw = strings[int(val.text)]
                    elif kind == "b":
                        raw = val.text == "1"
                    else:
                        raw = val.text
                    values[column] = raw
                if header is None:
                    header = values
                elif any(x is not None for x in values.values()):
                    yield {header[column]: value for column, value in values.items()}
                element.clear()


def load_labels(path: Path, allowed_ids: set[str]):
    labels = {}

    def add(h, mode, status, wall):
        if h not in allowed_ids:
            return
        status = str(status).upper()
        if status not in {"SAT", "UNSAT", "TIMEOUT"}:
            raise ValueError(f"unexpected reported status for permitted input {h}")
        key = (h, mode)
        if key in labels:
            raise ValueError(f"duplicate permitted source row {h}/{mode}")
        labels[key] = {"status": status, "wall": number(wall, "wall_time_s")}

    if path.suffix.lower() == ".xlsx":
        for row in xlsx_cells(path):
            h = identifier(row.get("ile", row.get("file", row.get("hash"))))
            if h not in allowed_ids:
                continue  # Exclude gate/outside before touching their performance.
            raw_mode = row.get("polarity_mode")
            if raw_mode in (False, "false", "False", "0"):
                mode = "false"
            elif raw_mode in (True, "true", "True", "1"):
                mode = "true"
            else:
                raise ValueError("unrecognized polarity_mode")
            add(h, mode, row["result"], row["wall_time_s"])
    else:
        with path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                h = identifier(row.get("hash", row.get("ile", row.get("file"))))
                if h not in allowed_ids:
                    continue
                for mode in ("false", "true"):
                    add(h, mode, row[f"{mode}_result"], row[f"{mode}_wall_s"])
    for h in allowed_ids:
        if any((h, mode) not in labels for mode in ("false", "true")):
            raise ValueError(f"missing permitted paired source rows {h}")
        solved = {labels[(h, mode)]["status"] for mode in ("false", "true")} - {"TIMEOUT"}
        if len(solved) > 1:
            raise ValueError(f"contradictory reported SAT/UNSAT answers for {h}")
    return labels


def compare_labels(left, right):
    if left.keys() != right.keys():
        raise ValueError("companion source identities differ")
    for key, value in left.items():
        other = right[key]
        if value["status"] != other["status"] or not math.isclose(value["wall"], other["wall"], rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError("attached workbook and companion paired CSV disagree")


def load_checksums(paths):
    output = {}
    for path in paths:
        if path.suffix.lower() == ".csv":
            with path.open(newline="") as stream:
                content = {row["hash"]: row for row in csv.DictReader(stream)}
        else:
            content = json.loads(path.read_text())
        for h, value in content.items():
            if not re.fullmatch(r"[0-9a-f]{32}", h) or not isinstance(value, dict):
                continue
            item = {"input_sha256": value.get("sha256_cnf", value.get("input_sha256")),
                    "compressed_sha256": value.get("sha256_xz", value.get("compressed_sha256")),
                    "input_bytes": value.get("bytes_cnf", value.get("input_bytes"))}
            if item["input_sha256"] is None:
                continue
            if not SHA_RE.fullmatch(item["input_sha256"]):
                raise ValueError("invalid expected public CNF SHA")
            if item["input_bytes"] is not None:
                raw_bytes = number(item["input_bytes"], "public CNF byte count")
                if int(raw_bytes) != raw_bytes:
                    raise ValueError("public CNF byte count must be an integer")
                item["input_bytes"] = int(raw_bytes)
            if h in output:
                previous = output[h]
                if previous["input_sha256"] != item["input_sha256"] or (
                    previous["compressed_sha256"] is not None and item["compressed_sha256"] is not None
                    and previous["compressed_sha256"] != item["compressed_sha256"]) or (
                    previous["input_bytes"] is not None and item["input_bytes"] is not None
                    and previous["input_bytes"] != item["input_bytes"]):
                    raise ValueError("conflicting public checksum manifests")
                item["compressed_sha256"] = item["compressed_sha256"] or previous["compressed_sha256"]
                item["input_bytes"] = item["input_bytes"] if item["input_bytes"] is not None else previous["input_bytes"]
            output[h] = item
    return output


def extract_values(features):
    values = {}
    for key in FEATURES:
        value = features.get(key)
        values[key] = None if value is None else number(value, key)
    if features.get("g_gate_motifs_exact") != 1:
        values["g_gate_motif_fraction"] = None
    return values


def load_cached_features(cache_roots, node_result_dirs, allowed_ids, checksums, extractor_sha, extractor_source_sha, role_by_id=None):
    candidates = collections.defaultdict(list)
    failures = collections.defaultdict(list)
    paths = set()
    for root in cache_roots:
        if root.exists():
            paths.update(p for p in root.rglob("*.features.json") if p.name[:-len(".features.json")] in allowed_ids)
    node_paths = set()
    for root in node_result_dirs:
        if root.exists():
            node_paths.update(root.rglob("*.json"))
    for path in sorted(paths | node_paths):
        record = json.loads(path.read_text())
        h = record.get("hash", record.get("instance_id", record.get("id")))
        if h not in allowed_ids:
            continue
        is_node = path in node_paths
        if is_node:
            if record.get("role") not in ROLES or (role_by_id is not None and record.get("role") != role_by_id[h]):
                raise ValueError("node receipt exposes forbidden role")
            if extractor_source_sha is None or record.get("extractor_source_sha256") != extractor_source_sha:
                continue
            if record.get("profile") != NODE_PROFILE:
                raise ValueError("node feature profile differs from frozen contract")
            unsigned = {k: v for k, v in record.items() if k != "receipt_content_sha256"}
            if record.get("receipt_content_sha256") != canonical_sha(unsigned):
                raise ValueError("node receipt content SHA mismatch")
            if h not in checksums:
                raise ValueError("node receipt lacks a frozen public input checksum")
            if record.get("input_sha256") != checksums[h]["input_sha256"]:
                raise ValueError("node receipt input differs from frozen checksum")
            expected_key = canonical_sha({"instance_id": h, "input_sha256": record["input_sha256"],
                "extractor_source_sha256": extractor_source_sha, "profile": NODE_PROFILE})
            if record.get("task_key") != expected_key:
                raise ValueError("node task key differs from frozen identity")
            if record.get("status") != "COMPLETE":
                attempt_cpu = record.get("total_accounted_cpu_s", record.get("feature_cpu_s"))
                failures[h].append({"path": str(path), "sha256": sha(path), "status": record.get("status"),
                                    "feature_cpu_s": None if attempt_cpu is None else number(attempt_cpu, "failed_feature_cpu_s"),
                                    "input_sha256": record.get("input_sha256"),
                                    "extractor_source_sha256": record.get("extractor_source_sha256"),
                                    "node_id": record.get("node_id"), "task_key": record.get("task_key")})
                continue
            source_sha = record.get("input_sha256")
            binary_sha = record.get("extractor_binary_sha256")
        else:
            if record.get("extractor_sha256") != extractor_sha:
                continue
            if record.get("metadata_count_mismatch") is not False:
                raise ValueError("cached feature input metadata mismatch or unverified flag")
            source_sha, binary_sha = record.get("source_sha256"), record.get("extractor_sha256")
        if not source_sha or not SHA_RE.fullmatch(source_sha) or not binary_sha or not SHA_RE.fullmatch(binary_sha):
            raise ValueError("feature receipt lacks input/extractor SHA identity")
        if h in checksums and source_sha != checksums[h]["input_sha256"]:
            raise ValueError(f"feature input differs from frozen public checksum for {h}")
        values = extract_values(record.get("features", {}))
        cpu = number(record.get("total_accounted_cpu_s", record.get("feature_cpu_s")), "feature_cpu_s")
        candidates[h].append({"values": values, "cpu_s": cpu, "input_sha256": source_sha,
                              "path": str(path), "receipt_sha256": sha(path), "binary_sha256": binary_sha,
                              "source_sha256": record.get("extractor_source_sha256"),
                              "extractor_cpu_s": record.get("feature_cpu_s"),
                              "preparation_cpu_s": record.get("preparation_cpu_s"),
                              "kind": "node_receipt" if is_node else "legacy_pinned_binary"})
    selected = {}
    for h, items in candidates.items():
        if len({item["input_sha256"] for item in items}) != 1:
            raise ValueError("same benchmark has conflicting cached CNF identities")
        if len({canonical_sha(item["values"]) for item in items}) != 1:
            raise ValueError("compatible feature receipts disagree")
        # Fixed canonical order; never choose a receipt for its fastest CPU time.
        selected[h] = {**items[0], "equivalent_receipts": [{"path": i["path"], "sha256": i["receipt_sha256"]} for i in items]}
    return selected, failures


def build_dataset(source, roles_path, cache_roots, checksums_paths=(), exclusions_path=None,
                  paired_csv=None, node_result_dirs=(), extractor_sha=LEGACY_EXTRACTOR_SHA,
                  extractor_source=None, cutoff=5000.0, expected_counts=None):
    cutoff = number(cutoff, "cutoff")
    if cutoff == 0:
        raise ValueError("cutoff must be positive")
    roles = load_roles(roles_path, expected_counts)
    allowed_ids = {row["hash"] for row in roles}
    labels = load_labels(source, allowed_ids)
    companion_sha = None
    if paired_csv is not None:
        compare_labels(labels, load_labels(paired_csv, allowed_ids))
        companion_sha = sha(paired_csv)
    checksums = load_checksums(checksums_paths)
    source_code_sha = sha(extractor_source) if extractor_source is not None else None
    cache, failures = load_cached_features(cache_roots, node_result_dirs, allowed_ids, checksums, extractor_sha, source_code_sha,
                                          {row["hash"]: row["role"] for row in roles})
    exclusions = {}
    if exclusions_path is not None:
        for item in json.loads(exclusions_path.read_text()):
            if item["hash"] in allowed_ids:
                exclusions[item["hash"]] = item["reason"]
    rows, tasks = [], []
    for meta in roles:
        h = meta["hash"]
        eligible = h not in exclusions and int(meta.get("bytes") or 0) <= 100_000_000 and int(meta.get("variables") or 0) <= 5_000_000
        item = cache.get(h) if eligible else None
        status = "EXCLUDED" if not eligible else ("AVAILABLE" if item else ("UNAVAILABLE" if h in failures else "PENDING"))
        feature_source = {"status": status, "reason": exclusions.get(h)}
        if item:
            feature_source.update({k: v for k, v in item.items() if k not in {"values", "cpu_s"}})
        elif h in failures:
            feature_source["prior_attempts"] = failures[h]
        row = {"id": h, "role": meta["role"], "group": meta["group"],
               "costs": {mode: (2 * cutoff if labels[(h, mode)]["status"] == "TIMEOUT" else labels[(h, mode)]["wall"]) for mode in ("false", "true")},
               "statuses": {mode: labels[(h, mode)]["status"] for mode in ("false", "true")},
               "wall_times": {mode: labels[(h, mode)]["wall"] for mode in ("false", "true")},
               "features": item["values"] if item else {key: None for key in FEATURES},
               "feature_cpu_s": item["cpu_s"] if item else (failures[h][0]["feature_cpu_s"] if h in failures else None), "eligible": eligible,
               "feature_status": status, "feature_source": feature_source}
        rows.append(row)
        if status == "PENDING":
            identity = checksums.get(h, {})
            # GBD's feature `bytes` is not the byte length of the downloaded CNF.
            # Only a size from the SHA-bound original-input checksum record may
            # become the worker's exact input-byte assertion.
            task_metadata = {key: int(meta[key]) for key in ("variables", "clauses") if meta.get(key)}
            if identity.get("input_bytes") is not None:
                task_metadata["bytes"] = identity["input_bytes"]
            tasks.append({"instance_id": h, "role": meta["role"], "public_url": meta.get("url") or "https://benchmark-database.de/file/" + h,
                          "input_sha256": identity.get("input_sha256"), "compressed_sha256": identity.get("compressed_sha256"),
                          "identity_status": "FROZEN_PUBLIC_CHECKSUM" if identity else "NEEDS_PUBLIC_IDENTITY",
                          "dispatchable": bool(identity) and h not in failures,
                          "metadata": task_metadata})
    dataset = {"schema": "ta_feature_discovery.development.v1", "source_sha": sha(source),
               "companion_pairs_sha": companion_sha, "role_manifest_sha": sha(roles_path),
               "extractor_binary_sha": extractor_sha, "extractor_source_sha": source_code_sha,
               "score": {"reported_solved": "raw_wall_time_s", "timeout": 2 * cutoff, "cutoff_convention_s": cutoff},
               "feature_names": list(FEATURES), "static_complete": all(r["feature_status"] != "PENDING" for r in rows),
               "rows": rows}
    public_tasks = {"schema": "ta_feature_discovery.public_tasks.v1", "role_manifest_sha": sha(roles_path),
                    "extractor_source_sha256": source_code_sha, "tasks": tasks,
                    "ready_tasks": [{key: value for key, value in task.items() if key not in {"identity_status", "dispatchable"}}
                                    for task in tasks if task["dispatchable"]]}
    return dataset, public_tasks


def save_new(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text() == encoded:
            return
        raise FileExistsError(f"refusing to overwrite a different immutable artifact: {path}")
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(encoded)
        os.link(temporary, path)  # Atomic no-overwrite publication.
    finally:
        os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--pairs-csv", type=Path, default=DEFAULT_PAIRS)
    parser.add_argument("--roles", type=Path, default=DEFAULT_ROLES)
    parser.add_argument("--cache-root", type=Path, action="append")
    parser.add_argument("--node-results-dir", type=Path, action="append", default=[])
    parser.add_argument("--checksums", type=Path, action="append")
    parser.add_argument("--exclusions", type=Path, default=PROJECT / "configs/experiments/phase_prediction_v1/resource_exclusions.json")
    parser.add_argument("--extractor-sha256", default=LEGACY_EXTRACTOR_SHA)
    parser.add_argument("--extractor-source", type=Path, default=PROJECT / "experiments/phase_prediction/cnf_structure.cpp")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/ta_feature_discovery/development.json")
    parser.add_argument("--tasks-output", type=Path, default=ROOT / "outputs/ta_feature_discovery/public_tasks.json")
    args = parser.parse_args(argv)
    checksum_paths = args.checksums or sorted((PROJECT / "configs/experiments/phase_prediction_v1").glob("*checksums*.json"))
    if args.checksums is None and PUBLIC_CHECKSUM_CSV.exists():
        checksum_paths.append(PUBLIC_CHECKSUM_CSV)
    dataset, tasks = build_dataset(args.source, args.roles,
        args.cache_root or [PROJECT / "results/phase_prediction_v1", ROOT / "work/ta_feature_discovery/remote_cache"],
        checksum_paths,
        args.exclusions, args.pairs_csv, args.node_results_dir, args.extractor_sha256,
        args.extractor_source, expected_counts={"development_fit": 180, "development_feedback": 60})
    save_new(args.output, dataset)
    save_new(args.tasks_output, tasks)
    print(json.dumps({"output": str(args.output), "rows": len(dataset["rows"]),
                      "static_complete": dataset["static_complete"],
                      "roles": dict(collections.Counter(r["role"] for r in dataset["rows"])),
                      "feature_status": dict(collections.Counter(r["feature_source"]["status"] for r in dataset["rows"])),
                      "public_tasks": len(tasks["tasks"]), "ready_tasks": len(tasks["ready_tasks"])}))


if __name__ == "__main__":
    main()
