"""External-only cohort filter. Never reads our D/F+/Fminus measurements."""
import argparse
import csv
import io
import math
import zipfile
from pathlib import Path
from .common import load_manifest, sha, write

POLICY = "official_all_tracks_unsolved_v1"
TRACKS = {"anni-seq.csv": 5000, "anni-par.csv": 5000, "anni-clo.csv": 1000}
SOURCE_URL = "https://satcompetition.github.io/2022/downloads/sc2022-detailed-results.zip"


def score_status(cells, cutoff):
    """Official table stores accepted solve time or PAR2 penalty, not raw timeout time."""
    penalty = 2 * cutoff
    values = []
    for cell in cells:
        try:
            value = float(cell)
            if not math.isfinite(value) or value < 0 or value > penalty: return None
            values.append(value)
        except (ValueError, TypeError): return None
    if not values: return None
    # Some officially accepted results slightly exceed nominal cutoff. They are
    # still non-penalty scores; do not relabel them as unsolved.
    return any(v < penalty for v in values)


def exclude(states):
    return len(states) == 3 and all(s is False for s in states)


def filter_manifest(master, archive, out):
    master, archive, out = Path(master), Path(archive), Path(out)
    receipt_path = out.with_suffix(".receipt.json")
    excluded_path = out.with_name(out.stem + ".excluded.csv")
    if any(p.exists() for p in [out, receipt_path, excluded_path]):
        raise ValueError("filter outputs are immutable; use a new output version")
    rows = load_manifest(master)
    if len(rows) != 5355 or any(r["role"] != "baseline_development" for r in rows):
        raise ValueError("filter requires the complete 5355-row development master")
    ids = {r["instance_key"] for r in rows}; tables = {}; track_stats = {}; seq_best = {}
    with zipfile.ZipFile(archive) as z:
        for name, cutoff in TRACKS.items():
            with z.open(name) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
                fields = reader.fieldnames
                if fields[:4] != ["hash", "benchmark", "verified-result", "claimed-result"]:
                    raise ValueError("unexpected official CSV schema")
                solvers = fields[4:]; table = {}; overruns = 0
                for row in reader:
                    h = row["hash"]
                    if h in table: raise ValueError("duplicate official hash")
                    cells = [row[s] for s in solvers]
                    table[h] = score_status(cells, cutoff)
                    if name == "anni-seq.csv":
                        solved = [float(c) for c in cells if 0 <= float(c) < 2*cutoff]
                        seq_best[h] = min(solved) if solved else None
                    overruns += sum(cutoff <= float(c) < 2*cutoff for c in cells)
                if len(table) != 5355: raise ValueError("official track is incomplete")
                tables[name] = table
                track_stats[name] = {"solver_columns": len(solvers), "rows": len(table),
                    "exact_master_hash_matches": len(set(table)&ids),
                    "official_solved_rows": sum(v is True for v in table.values()),
                    "official_all_penalty_rows": sum(v is False for v in table.values()),
                    "accepted_nonpenalty_scores_at_or_above_cutoff": overruns}
    kept = []; excluded = []; uncertain_kept = []; any_solved = 0
    for row in rows:
        h = row["instance_key"]; states = [tables[n].get(h) for n in TRACKS]
        if exclude(states):
            excluded.append({"instance_key": h, "reason": "all_three_tracks_all_solver_scores_are_PAR2_penalties",
                "sequential_solver_columns": track_stats["anni-seq.csv"]["solver_columns"],
                "parallel_solver_columns": track_stats["anni-par.csv"]["solver_columns"],
                "cloud_solver_columns": track_stats["anni-clo.csv"]["solver_columns"]})
        else:
            kept.append(row)
            if any(s is True for s in states): any_solved += 1
            else: uncertain_kept.append(h)
    if len(kept) + len(excluded) != 5355: raise AssertionError("lost master input")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["instance_key", "url", "role"], lineterminator="\n")
        writer.writeheader(); writer.writerows({k:r[k] for k in writer.fieldnames} for r in kept)
    with excluded_path.open("x", newline="") as f:
        fields = ["instance_key", "reason", "sequential_solver_columns", "parallel_solver_columns", "cloud_solver_columns"]
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(excluded)
    result = {"schema": "anni2022.external_cohort_filter.v1", "policy": POLICY,
        "selection_uses_our_phase_outcomes": False, "selection_uses_known_sat_answer_or_family": False,
        "source_url": SOURCE_URL, "official_archive_sha256": sha(archive), "filter_source_sha256": sha(Path(__file__)),
        "master_manifest_sha256": sha(master), "master_inputs": 5355, "manifest_sha256": sha(out),
        "retained_count": len(kept), "excluded_count": len(excluded), "retained_with_official_solve": any_solved,
        "retained_uncertain_count": len(uncertain_kept), "retained_uncertain_ids": uncertain_kept,
        "retained_ids": [r["instance_key"] for r in kept], "excluded_ids": [r["instance_key"] for r in excluded],
        "excluded_csv_sha256": sha(excluded_path), "tracks": track_stats,
        "planned_three_action_runs": len(kept)*3, "solver_T600_upper_cpu_hours": len(kept)*3*600/3600,
        "comparison_only_not_active": {"sequential_ever_solved_count": sum(seq_best.get(h) is not None for h in ids),
            "sequential_best_score_at_most_600_count": sum(seq_best.get(h) is not None and seq_best[h] <= 600 for h in ids)},
        "interpretation": "Conservative external difficulty restriction; no impossibility claim and no full5355 performance claim"}
    write(receipt_path, result)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument("--master",required=True);p.add_argument("--official-archive",required=True)
    p.add_argument("--out",required=True);a=p.parse_args();r=filter_manifest(a.master,a.official_archive,a.out)
    print({k:r[k] for k in ["policy","master_inputs","retained_count","excluded_count","retained_with_official_solve","retained_uncertain_count","planned_three_action_runs","solver_T600_upper_cpu_hours"]})


if __name__=="__main__":main()
