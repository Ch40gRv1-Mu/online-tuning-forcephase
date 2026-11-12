"""Compare Fplus and Fminus on the same frozen SCC switch set."""

import argparse
from pathlib import Path
import time

import numpy as np

from .common import write
from .score_signed_topology import metrics
from .structural_clusters import ACTIONS, DATA, load, read_csv


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    started, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, groups, _ = load()
    rows = {r["instance_key"]: r for r in read_csv(DATA / "scc_demand_transfer_20261110/predictions.csv")}
    if set(keys) != set(rows):
        raise ValueError("incomplete fixed SCC replay")
    original = np.array([rows[key]["newly_covered"] == "False" for key in keys])
    extracted = np.array([rows[key]["extracted"] == "True" for key in keys])
    switches = np.array([rows[key]["action"] == "Fminus" for key in keys])
    probes = original & extracted
    switches &= probes
    h = np.array([float(rows[key]["feature_cpu_s"]) for key in keys]) * probes
    charged = np.where((costs < 1200) & (costs + h[:, None] <= 600), costs + h[:, None], 1200)
    saved = {}
    for j in (1, 2):
        choices = np.where(switches, j, 0)
        saved[ACTIONS[j]] = {
            **metrics(costs, charged, choices, probes, groups),
            "switches": int(switches.sum()),
            "D_timeouts_rescued": int((switches & (costs[:, 0] == 1200) & (charged[:, j] < 1200)).sum()),
            "D_solves_lost": int((switches & (costs[:, 0] < 1200) & (charged[:, j] == 1200)).sum()),
            "switches_improved": int((switches & (charged[:, j] < costs[:, 0])).sum()),
            "switches_worsened": int((switches & (charged[:, j] > costs[:, 0])).sum()),
        }
    overlap = (charged[:, 1] < costs[:, 0]) & (charged[:, 2] < costs[:, 0]) & switches
    rescue_overlap = overlap & (costs[:, 0] == 1200)
    result = {"parents": len(keys), "rule": "original scope and SCC demand > 0.10",
              "both_forced_actions_improve": int(overlap.sum()), "both_rescue_D_timeout": int(rescue_overlap.sum()),
              "results": saved, "new_solver_calls": 0,
              "analysis_cpu_s": time.process_time() - cpu, "analysis_wall_s": time.monotonic() - started}
    write(args.out, result)
    for action, scores in saved.items():
        print(action, scores["with_extractor_cpu"], "rescues", scores["D_timeouts_rescued"])
    print("Both improve:", result["both_forced_actions_improve"], "both rescue:", result["both_rescue_D_timeout"])


if __name__ == "__main__":
    main()
