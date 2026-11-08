import argparse
import csv
import hashlib
import re
from pathlib import Path
from .common import sha, write


def prepare(source, out, expected=5355):
    source, out = Path(source), Path(out)
    if out.exists():
        raise ValueError("manifest is immutable; choose a new output")
    if source.suffix == ".csv":
        with source.open() as f:
            raw = list(csv.DictReader(f))
        rows = [{"instance_key": r.get("hash", r.get("instance_key")), "url": r["url"], "role": "baseline_development"} for r in raw]
    else:
        rows = []
        for url in source.read_text().splitlines():
            url = url.strip()
            if not url or url.startswith("#"):
                continue
            found = re.search(r"(?:/file/|hash=)([a-f0-9]{32})(?:\b|/)", url)
            if not found:
                raise ValueError("URI has no explicit GBD input ID")
            rows.append({"instance_key": found[1], "url": url, "role": "baseline_development"})
    if len(rows) != expected or len({r["instance_key"] for r in rows}) != expected:
        raise ValueError("incomplete or duplicate official input manifest")
    rows.sort(key=lambda r: hashlib.sha256(("anni2022-full-v1:" + r["instance_key"]).encode()).digest())
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["instance_key", "url", "role"])
        w.writeheader(); w.writerows(rows)
    receipt = {"source_sha256": sha(source), "manifest_sha256": sha(out), "inputs": len(rows),
               "role": "baseline_development", "exclusions": [], "prior_roles_preserved_in_source": True}
    write(out.with_suffix(".receipt.json"), receipt)
    return receipt


def main():
    p = argparse.ArgumentParser(); p.add_argument("--source", required=True); p.add_argument("--out", required=True)
    p.add_argument("--expected-count", type=int, default=5355); a = p.parse_args()
    print(prepare(a.source, a.out, a.expected_count))


if __name__ == "__main__": main()
