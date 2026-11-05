#!/usr/bin/env python3
"""Export a publication snapshot without raw professor timing tables or Git history."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    records = []

    def write(relative, data, source):
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        records.append({"path": str(relative), "sha256": digest(data), "bytes": len(data), "source": source})

    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    top = {"AGENTS.md", "AUTORESEARCH_WORKFLOW.md", "WORKFLOW_REVIEW_20261104.md", "findings.md", "research-state.yaml", "research-log.md", "ACTIVE_PHASE_PREDICTION_20261104.md"}
    for name in files:
        if not name:
            continue
        p = Path(name)
        include = name in top or p.parts[0] in {"src", "configs", "refine-logs", "literature", "reports"}
        include |= name.startswith("outputs/ta100/") and (p.name in {"STATE.json", "history.jsonl", "proposal.json", "COMPLETE.json"} or p.name.startswith("features_"))
        include |= name in {"outputs/ta_feature_discovery/COST_LEDGER.json", "outputs/ta_feature_discovery/FINAL_SUMMARY.json"}
        if "email_delivery" in p.parts or not include:
            continue
        write(Path("autoresearch") / name, (root / name).read_bytes(), name)

    # These are existing aggregate exports: rules, definitions, intervals and costs.
    for name in ["ALL_100_RULES_AND_RESULTS.json", "ALL_13_POLICIES.json", "all_13_policies.py", "TA100_COMPLETE_REPORT.html", "README_ZH.md"]:
        rel = Path("reports/ta100/email_delivery") / name
        write(Path("autoresearch") / rel, (root / rel).read_bytes(), str(rel))
    for p in sorted((root / "literature").glob("*.md")):
        rel = p.relative_to(root)
        if not any(r["path"] == str(Path("autoresearch") / rel) for r in records):
            write(Path("autoresearch") / rel, p.read_bytes(), str(rel))

    modern = root / "work/phase_prediction_20261104/project"
    archive = modern / "deliverables/forcephase_phase_prediction_v1_20261105.zip"
    excluded = []
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            p = Path(name)
            if name in {"MANIFEST.sha256", "SOURCE_VERSION.json"} or p.name.startswith("professor_pairs_") or p.name == "test_candidates.csv":
                excluded.append(name)
                continue
            write(Path("phase_prediction_v1") / name, z.read(name), "portable_archive:" + name)

    provenance = {
        "schema": "forcephase.weekly_publication.v1",
        "date": "2026-11-05",
        "root_source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "modern_source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=modern, text=True).strip(),
        "modern_portable_archive_sha256": digest(archive.read_bytes()),
        "modern_portable_archive_members_omitted": excluded,
        "scope": "Source, frozen protocols, aggregate TA results, numerical feature caches, own CaDiCaL measurements, negative results and costs. No raw professor timing rows, gate per-instance data, final-test outcomes, credentials or live queues.",
        "source_notes": "Snapshot export, not a Git-history merge. Modern files retain the portable archive's original point-in-time state; later close receipts are kept separately below.",
        "files": sorted(records, key=lambda x: x["path"]),
    }
    for name in ["delivery_receipt.json", "goal_completion_receipt.json"]:
        data = (modern / "deliverables" / name).read_bytes()
        write(Path("phase_prediction_v1/deliverables") / name, data, "modern_current:deliverables/" + name)
    provenance["files"] = sorted(records, key=lambda x: x["path"])
    (out / "PUBLICATION_MANIFEST.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"files": len(records), "bytes": sum(r["bytes"] for r in records), "out": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
