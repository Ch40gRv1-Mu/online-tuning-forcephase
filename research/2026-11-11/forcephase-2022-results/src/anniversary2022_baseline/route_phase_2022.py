"""Acquire both phase-rule features in one pass over a bounded plain or compressed CNF."""

import argparse
import gzip
import json
import lzma
import math
from pathlib import Path
import subprocess
import time

from .phase_rule_2022 import choose_action


SCC_BYTES = 1_500_000
WIDTH_BYTES = 3_000_000
READ_LIMIT = 3_050_000
PROCESS_LIMIT = 5
SOLVER_FLAGS = {
    "D": ("--phase=1", "--forcephase=0"),
    "Fplus": ("--phase=1", "--forcephase=1"),
    "Fminus": ("--phase=0", "--forcephase=1"),
}


def load_formula(path):
    with path.open("rb") as raw:
        magic = raw.read(6)
        raw.seek(0)
        if magic.startswith(b"\xfd7zXZ\x00"):
            with lzma.LZMAFile(raw) as stream:
                return stream.read(READ_LIMIT + 1)
        if magic.startswith(b"\x1f\x8b"):
            with gzip.GzipFile(fileobj=raw) as stream:
                return stream.read(READ_LIMIT + 1)
        return raw.read(READ_LIMIT + 1)


def route_formula(path, extractor, archived_size=None, verifier=None, expected_key=None):
    """Return an action and measured CPU; optional archival verification is experimental only."""
    started, begin_cpu = time.monotonic(), time.thread_time()
    receipt = {"action": "D", "status": "ineligible", "feature_CPU_s": 0.0}
    parser_cpu = 0.0
    raw = None
    try:
        if archived_size is None or archived_size <= WIDTH_BYTES:
            raw = load_formula(path)
            size = len(raw) if archived_size is None else archived_size
            if len(raw) <= READ_LIMIT and size <= WIDTH_BYTES:
                scope = "scc" if size <= SCC_BYTES else "width"
                output = subprocess.check_output([str(extractor), "--selector", scope], input=raw,
                                                 timeout=PROCESS_LIMIT)
                parser_cpu, scc, width = map(float, output.split())
                if not all(map(math.isfinite, (parser_cpu, scc, width))) or not 0 <= parser_cpu <= PROCESS_LIMIT:
                    raise ValueError("invalid parser metrics")
                if scc < 0:
                    scc = None
                receipt.update(status="ok", action=choose_action(scc, width), raw_bytes=len(raw),
                               scc_demand_share=scc, mean_width=width)
    except (OSError, EOFError, ValueError, lzma.LZMAError, subprocess.SubprocessError) as error:
        receipt.update(status="feature_error", error=type(error).__name__)
        if isinstance(error, subprocess.SubprocessError):
            parser_cpu = PROCESS_LIMIT

    receipt["feature_CPU_s"] = parser_cpu + time.thread_time() - begin_cpu
    receipt["feature_wall_s"] = time.monotonic() - started
    if verifier is not None:
        if raw is None:
            raise ValueError("verification requires a bounded CNF")
        checked = subprocess.check_output([str(verifier)], input=raw, timeout=PROCESS_LIMIT).split()
        if checked[0].decode() != expected_key:
            raise ValueError("cached GBD identity mismatch")
        receipt["identity_CPU_s"] = float(checked[4])
    return receipt


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cnf", type=Path)
    ap.add_argument("--extractor", type=Path, required=True)
    ap.add_argument("--archived-bytes", type=int)
    args = ap.parse_args()
    if not args.extractor.is_file() or not args.cnf.is_file():
        ap.error("existing CNF and selector binary are required")
    if args.archived_bytes is not None and args.archived_bytes <= 0:
        ap.error("archived bytes must be positive")
    result = route_formula(args.cnf, args.extractor.resolve(), args.archived_bytes)
    result["solver_flags"] = SOLVER_FLAGS[result["action"]]
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
