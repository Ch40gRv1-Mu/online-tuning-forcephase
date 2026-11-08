import argparse
import gzip
import lzma
import os
import shutil
import threading
import time
import urllib.request
from pathlib import Path
from .common import load_manifest, read, sha, write


def stage(row, root, spec, cpu_tokens=None):
    root = Path(root); key = row["instance_key"]
    dst = root / "cache" / (key + ".cnf")
    receipt = root / "input_receipts" / (key + ".json")
    if receipt.exists() and dst.exists():
        r = read(receipt)
        if sha(dst) != r["input_sha256"]:
            raise ValueError("cached input changed")
        return r
    dst.parent.mkdir(parents=True, exist_ok=True)
    partial, encoded = dst.with_suffix(".part"), dst.with_suffix(".download")
    begin, cpu0 = time.monotonic(), time.thread_time()
    reserve = spec["disk_reserve_bytes"]
    def copy_checked(src, target):
        while True:
            if time.monotonic() - begin > spec.get("download_wall_s", 1800):
                raise TimeoutError("input staging wall limit reached")
            block = src.read(1 << 20)
            if not block: break
            if shutil.disk_usage(root).free - len(block) < reserve:
                raise RuntimeError("disk reserve blocks input staging")
            target.write(block)
    try:
        with urllib.request.urlopen(row["url"], timeout=30) as src, encoded.open("wb") as target:
            copy_checked(src, target)
        with encoded.open("rb") as header_file:
            magic = header_file.read(6)
        previous_affinity = None
        if cpu_tokens is not None:
            cpu = cpu_tokens.get(); previous_affinity = os.sched_getaffinity(0)
            os.sched_setaffinity(0, {cpu})
        try:
            opener = lzma.open if magic.startswith(b"\xfd7zXZ\x00") else gzip.open if magic.startswith(b"\x1f\x8b") else open
            with opener(encoded, "rb") as src, partial.open("wb") as target:
                copy_checked(src, target)
            header = None
            with partial.open("rb") as f:
                for line in f:
                    if line.lstrip().startswith(b"p "):
                        fields = line.split()
                        if len(fields) != 4 or fields[1] != b"cnf": raise ValueError("not plain DIMACS CNF")
                        header = [int(fields[2]), int(fields[3])]; break
                    if line.strip() and not line.lstrip().startswith(b"c"):
                        raise ValueError("input is not DIMACS")
            if header is None: raise ValueError("DIMACS header missing")
            digest = sha(partial)
            if row.get("expected_sha256_cnf") and digest != row["expected_sha256_cnf"]:
                raise ValueError("public input SHA mismatch")
            if receipt.exists() and read(receipt)["input_sha256"] != digest:
                raise ValueError("re-downloaded input differs")
            compressed_digest = sha(encoded)
            partial.replace(dst)
        finally:
            if cpu_tokens is not None:
                os.sched_setaffinity(0, previous_affinity)
                cpu_tokens.put(cpu)
        r = {"instance_key": key, "path": str(dst.resolve()), "input_sha256": digest,
             "compressed_sha256": compressed_digest, "bytes": dst.stat().st_size,
             "variables": header[0], "clauses": header[1], "url": row["url"],
             "preparation_thread_cpu_s": time.thread_time() - cpu0, "preparation_wall_s": time.monotonic() - begin}
        write(receipt, r); encoded.unlink()
        return r
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def main():
    p = argparse.ArgumentParser(); p.add_argument("--manifest", required=True); p.add_argument("--root", required=True)
    p.add_argument("--spec", required=True); a = p.parse_args(); spec = read(a.spec)
    for row in load_manifest(a.manifest): print(stage(row, a.root, spec))


if __name__ == "__main__": main()
