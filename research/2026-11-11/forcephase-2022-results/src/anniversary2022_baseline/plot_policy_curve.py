"""Add the measured two-threshold selector to the archived 2022 CPU curves."""

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from raw_data_figures import ACTIONS, COLORS, LABEL, save, sha


POLICY = "Two-threshold"
PURPLE = "#983fa5"
CUTOFF = 600


def load_curves(baseline, predictions):
    with (baseline / "matrix.csv").open() as stream:
        matrix = list(csv.DictReader(stream))
    with predictions.open() as stream:
        selected = list(csv.DictReader(stream))
    indexed = {row["instance_key"]: row for row in selected}
    ids = {row["instance_key"] for row in matrix}
    assert len(ids) == len(matrix) == len(indexed) == len(selected) == 4719
    assert ids == set(indexed)
    curves = {action: [] for action in (*ACTIONS, "VBS", POLICY)}
    for row in matrix:
        assert row["complete"] == "True"
        costs = {action: float(row[action + "_par2"]) for action in ACTIONS}
        for action, cost in costs.items():
            assert 0 <= cost <= CUTOFF or cost == 2 * CUTOFF
            if cost <= CUTOFF:
                curves[action].append(cost)
        best = min(costs.values())
        if best <= CUTOFF:
            curves["VBS"].append(best)
        choice = indexed[row["instance_key"]]
        assert choice["action"] == choice["frozen_action"]
        overhead = float(choice["feature_CPU_s"])
        assert overhead >= 0 and math.isfinite(overhead)
        paid = costs[choice["action"]] + overhead
        expected = paid if paid <= CUTOFF else 2 * CUTOFF
        assert math.isclose(float(choice["PAR2"]), expected, abs_tol=1e-8)
        if expected <= CUTOFF:
            curves[POLICY].append(expected)
    published = json.loads((baseline / "curve_data.json").read_text())["cpu_s"]
    for action in (*ACTIONS, "VBS"):
        assert sorted(curves[action]) == sorted(published[action])
    curves = {name: np.sort(values) for name, values in curves.items()}
    return curves, matrix, selected


def style_axes(ax):
    ax.grid(alpha=.17)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlim(0, CUTOFF)


def main_plot(curves, out):
    fig, ax = plt.subplots(figsize=(10.6, 6.4))
    fig.subplots_adjust(left=.095, right=.96, top=.82, bottom=.17)
    fig.text(.095, .94, "2022 Anniversary · CaDiCaL baseline + policy",
             fontsize=18.5, weight="bold", color="#172a3c")
    fig.text(.095, .89,
             "4,719 retained formulas  ·  seed 0  ·  600 CPU-second limit  ·  measured selector cost",
             fontsize=10.3, color="#526273")
    for name in (*ACTIONS, POLICY, "VBS"):
        times, counts = np.unique(curves[name], return_counts=True)
        color = PURPLE if name == POLICY else COLORS[name]
        linestyle = "--" if name == "VBS" else "-"
        width = 2.3 if name in {"D", "VBS"} else 1.9
        if name == POLICY:
            linestyle = (0, (5, 2.2, 1.3, 2.2))
            width = 2.6
        ax.step(np.r_[0, times, CUTOFF], np.r_[0, counts.cumsum(), len(curves[name])],
                where="post", color=color, linewidth=width, linestyle=linestyle,
                label=f"{LABEL.get(name, name)}  ·  {len(curves[name]):,} solved",
                zorder=6 if name == POLICY else 3)
    style_axes(ax)
    ax.set_ylim(0, 4719)
    ax.set_yticks([0, 1000, 2000, 3000, 4000, 4719],
                  ["0", "1,000", "2,000", "3,000", "4,000", "4,719"])
    ax.set_xticks([0, 60, 120, 240, 360, 480, 600])
    ax.set_ylabel("Number of verified instances solved", labelpad=10)
    ax.set_xlabel("CPU budget per instance (seconds)", labelpad=10)
    ax.legend(loc="upper left", frameon=True, facecolor="white", edgecolor="#dde4eb",
              fontsize=10, ncol=2)
    fig.text(.095, .073,
             "Policy replay adds measured CNF reading, decompression and selection CPU to archived solver time.",
             fontsize=8.4, color="#526273")
    fig.text(.095, .047,
             "The two thresholds were developed on this 2022 pool. VBS is the per-formula three-action oracle.",
             fontsize=8.4, color="#526273")
    fig.text(.095, .021,
             "Official all-track-unsolved filtering retains 4,719 of 5,355 formulas, with 636 excluded.",
             fontsize=8.4, color="#637286")
    save(fig, out, "runtime_with_policy")


def difference_plot(curves, out):
    events = np.unique(np.concatenate(([0, CUTOFF], *curves.values())))
    difference = (np.searchsorted(curves[POLICY], events, side="right")
                  - np.searchsorted(curves["D"], events, side="right"))
    fig, ax = plt.subplots(figsize=(10.6, 4.6))
    fig.subplots_adjust(left=.095, right=.96, top=.77, bottom=.24)
    fig.text(.095, .92, "Two-threshold policy · solved-count difference from D",
             fontsize=17.5, weight="bold", color="#172a3c")
    fig.text(.095, .85,
             "Same 4,719 formulas  ·  policy includes measured selection CPU  ·  2022 development replay",
             fontsize=10.3, color="#526273")
    ax.axhline(0, color="#637286", linewidth=1)
    ax.step(events, difference, where="post", color=PURPLE, linewidth=1.6)
    ax.fill_between(events, 0, difference, where=difference >= 0,
                    step="post", color=PURPLE, alpha=.16)
    ax.fill_between(events, 0, difference, where=difference < 0,
                    step="post", color="#d28132", alpha=.18)
    style_axes(ax)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xticks([0, 1, 10, 60, 120, 300, 600],
                  ["0", "1", "10", "60", "120", "300", "600"])
    ax.set_xlabel("CPU budget per instance (seconds, symlog scale)", labelpad=9)
    ax.set_ylabel("Solved by policy − solved by D", labelpad=9)
    ax.annotate(f"+{difference[-1]} at 600 s", (600, difference[-1]),
                xytext=(-9, 16), textcoords="offset points", ha="right",
                color=PURPLE, fontsize=11, weight="bold")
    fig.text(.095, .055,
             "Positive values favor the policy. The expanded early-time scale shows the selection-cost penalty.",
             fontsize=9, color="#526273")
    save(fig, out, "policy_minus_D")
    return events, difference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    base = root / "outputs/anniversary2022_baseline"
    baseline = base / "raw_data_20261110"
    predictions = base / "live_feature_route_20261110/predictions.csv"
    out = args.out or base / "policy_curve_20261110"
    out.mkdir(parents=True, exist_ok=True)
    curves, matrix, selected = load_curves(baseline, predictions)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.labelcolor": "#344658", "xtick.color": "#526273",
                         "ytick.color": "#526273", "pdf.fonttype": 42})
    main_plot(curves, out)
    events, difference = difference_plot(curves, out)
    with (out / "curve_points.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["cpu_budget_s", *curves, "policy_minus_D"])
        counts = {name: np.searchsorted(times, events, side="right")
                  for name, times in curves.items()}
        for index, event in enumerate(events):
            writer.writerow([event, *(counts[name][index] for name in curves), difference[index]])
    mean_d = sum(float(row["D_par2"]) for row in matrix) / len(matrix)
    mean_policy = sum(float(row["PAR2"]) for row in selected) / len(selected)
    receipt = {
        "source_sha256": {str(path.relative_to(root)): sha(path) for path in
                          (baseline / "matrix.csv", baseline / "curve_data.json", predictions)},
        "generator_sha256": sha(__file__),
        "cohort": len(matrix), "cutoff_cpu_s": CUTOFF,
        "solved": {name: len(times) for name, times in curves.items()},
        "policy_feature_CPU_s": sum(float(row["feature_CPU_s"]) for row in selected),
        "mean_PAR2_s": {"D": mean_d, POLICY: mean_policy},
        "PAR2_gain_over_D_pct": 100 * (mean_d - mean_policy) / mean_d,
        "new_solver_calls": 0,
        "evaluation": "2022 development replay with measured selector CPU and archived solver CPU",
        "difference_min": int(difference.min()), "difference_max": int(difference.max()),
        "files_sha256": {path.name: sha(path) for path in sorted(out.iterdir())
                         if path.name != "receipt.json"},
    }
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({key: receipt[key] for key in
                     ("solved", "mean_PAR2_s", "PAR2_gain_over_D_pct",
                      "difference_min", "difference_max")}, indent=2))


if __name__ == "__main__":
    main()
