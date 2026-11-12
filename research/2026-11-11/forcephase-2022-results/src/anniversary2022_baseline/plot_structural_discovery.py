"""Plot exploratory held-out PAR2 comparisons for the structure discovery rounds."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from .structural_clusters import DATA


def summary(name):
    return json.loads((DATA / (name + "_20261110") / "summary.json").read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    topology = summary("signed_topology")
    boundary = summary("signed_boundary")
    expanded = summary("static_unit_pressure")
    fixed_topology = next(row for row in topology["variants"] if row["name"] == "topology_combined_24")
    scc = next(row for row in topology["variants"] if row["name"] == "scc_12")
    boundary_candidate = max(
        (row for row in boundary["variants"] if not row["name"].startswith(("size_", "combined_"))),
        key=lambda row: row["with_extractor_cpu"]["par2_improvement_pct"],
    )
    entries = [
        ("Marginal clusters · training-fold choice", summary("structural_views")["nested_view_choice"], "#566477"),
        ("32 structural neighbors", summary("structural_neighbors"), "#566477"),
        ("SCC and depth · 12 clusters", scc["with_extractor_cpu"], "#007e76"),
        ("Combined signed topology · 24 clusters", fixed_topology["with_extractor_cpu"], "#007e76"),
        ("Signed topology · training-fold choice", topology["nested"]["with_extractor_cpu"], "#007e76"),
        (boundary_candidate["name"].replace("_", " ").capitalize() + " · best fixed boundary view",
         boundary_candidate["with_extractor_cpu"], "#775ba6"),
        ("Boundary and repair · training-fold choice", boundary["nested"]["with_extractor_cpu"], "#775ba6"),
        ("Unit pressure expanded · training-fold choice", expanded["nested"]["with_extractor_cpu"], "#a06026"),
    ]
    fig, ax = plt.subplots(figsize=(10.4, 5.3))
    for y, (_, result, color) in enumerate(entries):
        gain = result["par2_improvement_pct"]
        lo, hi = result["paired_group_bootstrap_95_pct"]
        ax.hlines(y, lo, hi, color=color, lw=2)
        ax.scatter(gain, y, s=46, color=color, zorder=3)
    ax.set_yticks(range(len(entries)), [label for label, _, _ in entries])
    ax.invert_yaxis()
    ax.set_xlabel("Mean PAR2 reduction relative to D")
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=2))
    ax.axvline(0, color="#2f333b", linestyle="--", linewidth=1)
    ax.grid(axis="x", color="#e4e8ed", linewidth=0.8)
    ax.tick_params(length=0, pad=8)
    ax.spines[:].set_visible(False)
    fig.text(0.035, 0.945, "Which CNF structures help select a phase?", fontsize=18, weight="bold", color="#1a2635")
    fig.text(0.035, 0.895, "Anniversary 2022 development cohort · 4,719 formulas · 600 CPU seconds per instance",
             fontsize=10, color="#566477")
    fig.text(0.035, 0.04, "Five held-out folds · paired 95% exploratory intervals · new features charged measured extractor CPU",
             fontsize=9, color="#566477")
    fig.subplots_adjust(left=0.42, right=0.96, top=0.82, bottom=0.19)
    fig.savefig(args.out, dpi=180, facecolor="white")


if __name__ == "__main__":
    main()
