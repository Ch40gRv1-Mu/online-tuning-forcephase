"""Count positive binary clauses and replay a prespecified one-feature selector."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import fcntl
from fractions import Fraction
import gzip
import hashlib
import io
import json
import lzma
import math
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "configs/anniversary2022_baseline/manifest.official-solvable.v1.csv"
MATRIX = ROOT / "outputs/anniversary2022_baseline/raw_data_20261110/matrix.csv"
BASE = ROOT / "work/frozen_policy_replay_20261110/gbd_base.sqlite3"
META = ROOT / "work/expanded_parents/gbd_meta.db"
OLD = "9f5e9cae589c2265ee3617130bd0a4c1c2d62f27:results/three_way/winner_profiles.csv"
THRESHOLDS = [Fraction(x) for x in ("0", ".01", ".05", ".1", ".25", ".5", ".75", ".9")]


def rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_json(path, value):
    temporary = path.with_suffix(".part")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def routing(binary, lower, upper, threshold):
    if not binary or upper * threshold.denominator <= threshold.numerator * binary:
        return "D"
    if lower * threshold.denominator > threshold.numerator * binary:
        return "Fminus"
    return None


def inputs():
    manifest = {row["instance_key"]: row for row in rows(MANIFEST)}
    assert len(manifest) == 4719
    with sqlite3.connect(f"file:{BASE}?mode=ro", uri=True) as db:
        stats = {
            key: tuple(map(int, counts))
            for key, *counts in db.execute(
                "select hash, clauses, cls1, cls2, positive, horn, invhorn, bytes from features"
            )
            if key in manifest
        }
    assert set(manifest) == set(stats)
    archived = subprocess.check_output(
        ["git", "-C", str(ROOT / "work/weekly_push_20261105"), "show", OLD], text=True
    )
    old = {
        row["hash"]: (row["p_binpos_frac"], row["p_bin_frac"])
        for row in csv.DictReader(io.StringIO(archived))
        if row["hash"] in manifest and row["p_binpos_frac"]
    }
    result = {}
    for key, (clauses, unit, binary, positive, horn, inverse_horn, size) in stats.items():
        # All positive binaries are non-Horn, all negative binaries are
        # non-inverse-Horn. No unit clause can belong to either class.
        other = clauses - unit - binary
        lower = max(0, positive - (clauses - binary), clauses - horn - other)
        upper = min(binary, positive, clauses - horn, binary - max(0, clauses - inverse_horn - other))
        if not 0 <= lower <= upper <= binary:
            raise ValueError(f"inconsistent GBD counts for {key}")
        source = "GBD_count_bounds"
        if key in old and binary:
            fraction, old_binary_fraction = old[key]
            if math.isclose(binary / clauses, float(old_binary_fraction), rel_tol=5e-6):
                value = Decimal(fraction)
                if value.is_finite():
                    half_unit = Decimal("0.5").scaleb(value.adjusted() - 5) if value else Decimal(0)
                    cache_lower = int(((value - half_unit) * binary).to_integral_value(rounding=ROUND_CEILING))
                    cache_upper = int(((value + half_unit) * binary).to_integral_value(rounding=ROUND_FLOOR))
                    if max(lower, cache_lower) <= min(upper, cache_upper):
                        lower, upper = max(lower, cache_lower), min(upper, cache_upper)
                        source = "historical_profile_and_GBD_counts"
        result[key] = {
            "url": manifest[key]["url"], "size": size, "clauses": clauses,
            "binary": binary, "lower": lower, "upper": upper, "source": source,
        }
    return result


def needs_scan(item):
    return any(routing(item["binary"], item["lower"], item["upper"], t) is None for t in THRESHOLDS)


class MeteredInput(io.RawIOBase):
    def __init__(self, stream):
        self.stream = stream
        self.bytes_read = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        count = self.stream.readinto(buffer)
        self.bytes_read += count
        return count


def scan(key, item, parser, record_path):
    wall_start, cpu_start = time.monotonic(), time.thread_time()
    result = {"status": "error", "instance_key": key}
    wire = None
    raw_bytes = 0
    try:
        with urllib.request.urlopen(item["url"], timeout=15) as response:
            wire = MeteredInput(response)
            with io.BufferedReader(wire, buffer_size=1 << 16) as encoded:
                magic = encoded.peek(6)
                if magic.startswith(b"\xfd7zXZ\x00"):
                    plain = lzma.LZMAFile(encoded)
                elif magic.startswith(b"\x1f\x8b"):
                    plain = gzip.GzipFile(fileobj=encoded)
                else:
                    plain = encoded
                with plain, subprocess.Popen([str(parser)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE) as process:
                    try:
                        while block := plain.read(1 << 20):
                            if time.monotonic() - wall_start > 120:
                                raise TimeoutError("stream wall limit reached")
                            raw_bytes += len(block)
                            process.stdin.write(block)
                        process.stdin.close()
                        stdout, stderr = process.stdout.read(), process.stderr.read()
                        if process.wait() != 0:
                            raise ValueError(stderr.decode(errors="replace").strip())
                    except BaseException:
                        if process.poll() is None:
                            process.kill()
                        raise
        digest, clauses, binary, positive, parser_cpu = stdout.decode().split()
        if (digest, int(clauses), int(binary)) != (key, item["clauses"], item["binary"]):
            raise ValueError("GBD identity or clause counts differ")
        positive = int(positive)
        if not item["lower"] <= positive <= item["upper"]:
            raise ValueError("exact positive binary count disagrees with cached bounds")
        result.update(status="ok", positive_binary=positive, parser_cpu_s=float(parser_cpu))
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    result.update(wall_s=time.monotonic() - wall_start, stream_cpu_s=time.thread_time() - cpu_start,
                  raw_bytes=raw_bytes, wire_bytes=wire.bytes_read if wire else 0)
    write_json(record_path, result)
    return result


def collect(dataset, output, parser, workers, limit):
    output.mkdir(parents=True, exist_ok=True)
    records = output / "records"
    records.mkdir(exist_ok=True)
    with (output / "collector.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        queue = []
        for key, item in sorted(dataset.items(), key=lambda pair: (pair[1]["size"], pair[0])):
            path = records / f"{key}.json"
            if needs_scan(item) and (not path.exists() or json.loads(path.read_text())["status"] != "ok"):
                queue.append((key, item, path))
        if limit is not None:
            queue = queue[:limit]
        print(f"Queued {len(queue)} inputs, {workers} workers", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(scan, key, item, parser, path) for key, item, path in queue]
            for count, job in enumerate(as_completed(futures), 1):
                result = job.result()
                if result["status"] != "ok" or count == len(queue) or count % 25 == 0:
                    print(count, len(queue), result, flush=True)


def fixed_threshold_results(observations, baseline):
    """Bound full-population cost while some actions are undetermined."""
    results = []
    for index, threshold in enumerate(THRESHOLDS):
        switched = []
        unknown = []
        for _, _, options, costs, *_ in observations:
            delta = costs["Fminus"] - costs["D"]
            if options[index] == "Fminus":
                switched.append(delta)
            elif options[index] is None:
                unknown.append(delta)
        known_delta = math.fsum(switched)
        low = known_delta + math.fsum(min(0, x) for x in unknown)
        high = known_delta + math.fsum(max(0, x) for x in unknown)
        results.append({
            "threshold": float(threshold), "known_switches": len(switched),
            "unresolved_actions": len(unknown),
            "total_par2_delta_bounds": [low, high],
            "mean_par2_bounds": [(baseline + d) / len(observations) for d in (low, high)],
            "par2_change_pct_bounds": [d / baseline * 100 for d in (low, high)],
        })
    return results


def score(dataset, output, result_path):
    matrix = {row["instance_key"]: row for row in rows(MATRIX)}
    assert set(matrix) == set(dataset)
    with sqlite3.connect(f"file:{META}?mode=ro", uri=True) as db:
        groups = {key: group for key, group in db.execute("select hash, isohash2 from features") if key in dataset}
    observations = []
    receipts = []
    for key, item in dataset.items():
        path = output / "records" / f"{key}.json"
        lower, upper = item["lower"], item["upper"]
        source = item["source"]
        if path.exists():
            receipt = json.loads(path.read_text())
            receipts.append(receipt)
            if receipt["status"] == "ok":
                assert receipt["instance_key"] == key
                lower = upper = receipt["positive_binary"]
                source = "stream_verified_GBD_hash"
        options = [routing(item["binary"], lower, upper, t) for t in THRESHOLDS]
        group = groups.get(key)
        if group in (None, "", "empty", "None"):
            group = key
        fold = int(hashlib.sha256(("positive_binary_v1:" + group).encode()).hexdigest(), 16) % 5
        row = matrix[key]
        assert row["complete"] == "True"
        costs = {action: float(row[f"{action}_par2"]) for action in ("D", "Fplus", "Fminus")}
        observations.append((key, fold, options, costs, lower, upper, source))

    fitted = {}
    fit_details = []
    for fold in range(5):
        training = [row for row in observations if row[1] != fold]
        best = (0, None)
        for index, threshold in reversed(list(enumerate(THRESHOLDS))):
            switched = [row[3]["Fminus"] - row[3]["D"] for row in training if row[2][index] == "Fminus"]
            delta = math.fsum(switched)
            if len(switched) >= 30 and delta < best[0]:
                best = (delta, index)
        fitted[fold] = best[1]
        # If even each threshold's optimistic completion loses to D, the
        # exact training result is D whatever the remaining feature values.
        train_baseline = math.fsum(row[3]["D"] for row in training)
        candidates = fixed_threshold_results(training, train_baseline)
        certified_D = all(
            candidate["known_switches"] + candidate["unresolved_actions"] < 30
            or candidate["total_par2_delta_bounds"][0] >= 0
            for candidate in candidates
        )
        assert not certified_D or fitted[fold] is None
        fit_details.append({"fold": fold, "threshold": None if best[1] is None else float(THRESHOLDS[best[1]]),
                            "train_delta_par2_s": best[0], "D_certified_with_unresolved_actions": certified_D,
                            "optimistic_train_delta_s_by_threshold": [r["total_par2_delta_bounds"][0] for r in candidates]})

    n = len(observations)
    baseline = math.fsum(row[3]["D"] for row in observations)
    majority_index = THRESHOLDS.index(Fraction(1, 2))
    predictions = []
    majority_low = majority_high = 0.0
    for key, fold, options, costs, lower, upper, source in observations:
        index = fitted[fold]
        selected = options[index] if index is not None else "D"
        majority = options[majority_index]
        candidates = [costs[majority]] if majority else [costs["D"], costs["Fminus"]]
        majority_low += min(candidates)
        majority_high += max(candidates)
        predictions.append({"instance_key": key, "fold": fold, "action": selected or "D",
                            "missing_fallback": selected is None, "binary": dataset[key]["binary"],
                            "positive_binary_lower": lower, "positive_binary_upper": upper,
                            "unresolved_grid_actions": sum(option is None for option in options),
                            "source": source, "D_par2": costs["D"], "Fminus_par2": costs["Fminus"],
                            "selected_par2": costs[selected or "D"], "majority_action": majority or "unknown"})
    cost = math.fsum(row["selected_par2"] for row in predictions)
    result = {
        "population": n, "all_censored": sum(min(row[3].values()) == 1200 for row in observations),
        "ready_all_thresholds": sum(not row["unresolved_grid_actions"] for row in predictions),
        "exact_counts": sum(row["positive_binary_lower"] == row["positive_binary_upper"] for row in predictions),
        "fold_fits": fit_details, "D_mean_par2": baseline / n, "selected_mean_par2": cost / n,
        "all_folds_certified_D": all(row["D_certified_with_unresolved_actions"] for row in fit_details),
        "selected_par2_change_pct": (cost / baseline - 1) * 100,
        "D_solved": sum(row["D_par2"] < 1200 for row in predictions),
        "selected_solved": sum(row["selected_par2"] < 1200 for row in predictions),
        "switches": sum(row["action"] == "Fminus" for row in predictions),
        "selected_threshold_missing_fallbacks": sum(row["missing_fallback"] for row in predictions),
        "improved": sum(row["selected_par2"] < row["D_par2"] for row in predictions),
        "regressed": sum(row["selected_par2"] > row["D_par2"] for row in predictions),
        "fixed_majority_unresolved": sum(row["majority_action"] == "unknown" for row in predictions),
        "fixed_majority_mean_par2_bounds": [majority_low / n, majority_high / n],
        "fixed_majority_change_pct_bounds": [(bound / baseline - 1) * 100 for bound in (majority_low, majority_high)],
        "fixed_threshold_results": fixed_threshold_results(observations, baseline),
        "scan_ok": sum(row["status"] == "ok" for row in receipts),
        "scan_failed": sum(row["status"] != "ok" for row in receipts),
        "wire_bytes": sum(row["wire_bytes"] for row in receipts),
        "raw_bytes": sum(row["raw_bytes"] for row in receipts),
        "stream_cpu_s": sum(row["stream_cpu_s"] for row in receipts),
        "measured_parser_cpu_s": sum(row.get("parser_cpu_s", 0) for row in receipts),
        "input_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "cost_matrix_sha256": hashlib.sha256(MATRIX.read_bytes()).hexdigest(),
        "gbd_base_sha256": hashlib.sha256(BASE.read_bytes()).hexdigest(),
        "historical_profile": OLD, "new_solver_calls": 0, "feature_cost_in_par2": False,
    }
    result_path.mkdir(parents=True, exist_ok=True)
    with (result_path / "predictions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(predictions[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(predictions)
    write_json(result_path / "summary.json", result)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    collection = commands.add_parser("collect")
    collection.add_argument("--parser", type=Path, required=True)
    collection.add_argument("--workers", type=int, default=6)
    collection.add_argument("--limit", type=int)
    scoring = commands.add_parser("score")
    scoring.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    dataset = inputs()
    if args.command == "collect":
        collect(dataset, args.work, args.parser.resolve(), args.workers, args.limit)
    else:
        score(dataset, args.work, args.out)


if __name__ == "__main__":
    main()
