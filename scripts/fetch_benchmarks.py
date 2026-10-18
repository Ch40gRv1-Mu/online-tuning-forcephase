#!/usr/bin/env python3
"""Download and checksum the CNF instances listed in benchmarks/manifest.csv.

Usage: scripts/fetch_benchmarks.py [--splits train,val,test,t2026] [--jobs 6] [--hash-file list.txt]

Files go to $FP_DATA/benchmarks/cnf/<hash>.cnf.xz (FP_DATA defaults to
/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase).  For every
file the SHA-256 of the compressed download, the SHA-256 of the decompressed
CNF and its DIMACS header are written to benchmarks/checksums.csv (merged
with existing rows, sorted by hash).  Existing files whose recorded
compressed hash matches are not downloaded again.
"""

import argparse
import concurrent.futures as cf
import csv
import hashlib
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("FP_DATA", "/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase")
CNF_DIR = os.path.join(DATA, "benchmarks", "cnf")
CHECKSUMS = os.path.join(ROOT, "benchmarks", "checksums.csv")
FIELDS = ["hash", "sha256_xz", "sha256_cnf", "header_vars", "header_clauses", "bytes_xz",
          "bytes_cnf", "downloaded_utc"]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(row, known):
    h = row["hash"]
    dst = os.path.join(CNF_DIR, h + ".cnf.xz")
    if h in known and os.path.exists(dst) and sha256_file(dst) == known[h]["sha256_xz"]:
        return known[h], "cached"
    tmp = dst + ".part"
    for attempt in range(5):
        try:
            with urllib.request.urlopen(row["url"], timeout=300) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            break
        except Exception as e:  # retry transient network errors
            if attempt == 4:
                return None, f"download failed: {e}"
            time.sleep(10 * (attempt + 1))
    os.replace(tmp, dst)
    # decompress stream: hash, size and header
    p = subprocess.Popen(["xz", "-dc", dst], stdout=subprocess.PIPE)
    hc = hashlib.sha256()
    n = 0
    header = None
    buf = b""
    for chunk in iter(lambda: p.stdout.read(1 << 20), b""):
        hc.update(chunk)
        n += len(chunk)
        if header is None:
            buf += chunk
            for line in buf.split(b"\n"):
                if line.startswith(b"p cnf"):
                    header = line.split()[2:4]
                    break
            if header is None and len(buf) > 1 << 22:
                header = [b"?", b"?"]
    if p.wait() != 0:
        return None, "xz decompression failed"
    res = {"hash": h, "sha256_xz": sha256_file(dst), "sha256_cnf": hc.hexdigest(),
           "header_vars": header[0].decode() if header else "?",
           "header_clauses": header[1].decode() if header else "?",
           "bytes_xz": os.path.getsize(dst), "bytes_cnf": n,
           "downloaded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    return res, "downloaded"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", default="train,val,test,t2026")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--hash-file", help="only fetch the hashes listed in this file")
    a = ap.parse_args()
    os.makedirs(CNF_DIR, exist_ok=True)
    splits = set(a.splits.split(","))
    rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "benchmarks", "manifest.csv")))
            if r["split"] in splits]
    if a.hash_file:
        keep = {l.split()[0] for l in open(a.hash_file) if l.strip() and not l.startswith("#")}
        rows = [r for r in rows if r["hash"] in keep]
    known = {}
    if os.path.exists(CHECKSUMS):
        known = {r["hash"]: r for r in csv.DictReader(open(CHECKSUMS))}
    out = dict(known)
    status = {}
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        futs = {ex.submit(fetch, r, known): r for r in rows}
        for i, fut in enumerate(cf.as_completed(futs)):
            r = futs[fut]
            res, st = fut.result()
            status[st] = status.get(st, 0) + 1
            if res:
                out[r["hash"]] = res
                gv, gc = r["variables"], r["clauses"]
                if str(res["header_vars"]) != str(gv) or str(res["header_clauses"]) != str(gc):
                    print(f"note: header {res['header_vars']} {res['header_clauses']} vs GBD {gv} {gc} for {r['hash']}")
            else:
                print(f"FAILED {r['hash']}: {st}", file=sys.stderr)
            if i % 100 == 0:
                print(f"{i}/{len(rows)} {status}", flush=True)
    with open(CHECKSUMS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for h in sorted(out):
            w.writerow({k: out[h][k] for k in FIELDS})
    print("done", status)


if __name__ == "__main__":
    main()
