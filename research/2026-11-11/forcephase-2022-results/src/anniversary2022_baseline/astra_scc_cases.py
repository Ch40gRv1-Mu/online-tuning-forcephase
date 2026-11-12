"""Build an anonymized matched-case panel for explaining SCC guard outcomes."""

import argparse
import gzip
import json
import math
from pathlib import Path
import subprocess
import time

import numpy as np

from .positive_binary_replay import write_json
from .structural_clusters import ACTIONS, DATA, FEATURES, distances, load, read_csv, standardize, write_csv


def case_pairs(keys, X, groups, outcomes, cache, already_shown):
    available = np.array([(cache / (key + ".cnf.gz")).is_file() and key in outcomes for key in keys])
    shown_groups = {group for key, group in zip(keys, groups) if key in already_shown}
    available &= np.array([group not in shown_groups for group in groups])
    gain = np.array([float(outcomes[key]["D_par2"]) - float(outcomes[key]["selected_par2"])
                     if key in outcomes else 0 for key in keys])
    d_cost = np.array([float(outcomes[key]["D_par2"]) if key in outcomes else 1200 for key in keys])
    demand = np.array([float(outcomes[key]["scc_demand_share"]) if key in outcomes else 0 for key in keys])
    switched = demand > 0.10
    paid = np.column_stack((X, np.log1p(demand)))
    scaled, _ = standardize(paid[available], paid[available], np.ones(paid.shape[1]))
    scaled_by_row = np.zeros_like(paid)
    scaled_by_row[available] = scaled

    used = set()
    selections = []
    for rescued in (True, False):
        winners = np.flatnonzero(available & switched & (gain > 10) & ((d_cost == 1200) == rescued))
        ordered = sorted(winners, key=lambda index: (-gain[index], keys[index]))
        made = 0
        for anchor in ordered:
            if groups[anchor] in used:
                continue
            unused = np.array([group not in used and group != groups[anchor] for group in groups])
            candidates = np.flatnonzero(available & unused & switched & (d_cost < 1200) &
                                        ((gain < -2) | (gain < -np.maximum(0.02, 0.10 * d_cost))))
            if not len(candidates):
                break
            match = int(candidates[distances(scaled_by_row[anchor:anchor + 1],
                                             scaled_by_row[candidates]).argmin()])
            controls = np.flatnonzero(available & unused & ~switched &
                                      np.array([group != groups[match] for group in groups]))
            if not len(controls):
                break
            control = int(controls[distances(scaled_by_row[anchor:anchor + 1],
                                             scaled_by_row[controls]).argmin()])
            selections.append((int(anchor), match, control))
            used.update(groups[index] for index in selections[-1])
            made += 1
            if made == 3:
                break
    if len(selections) != 6:
        raise ValueError("insufficient distinct examples for the frozen six-triplet panel")
    return selections


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--previous-cases", type=Path, required=True)
    ap.add_argument("--checker", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    start = time.monotonic()
    keys, X, _, _, groups, _ = load()
    matrix = {r["instance_key"]: r for r in read_csv(DATA / "raw_data_20261110/matrix.csv")}
    runs = {(r["instance_key"], r["action"]): r for r in read_csv(DATA / "raw_data_20261110/runs.csv")}
    frozen = DATA / "scc_demand_transfer_20261110"
    outputs = {r["instance_key"]: r for r in read_csv(frozen / "predictions.csv")
               if r["newly_covered"] == "False" and r["extracted"] == "True"}
    previous = {r["instance_key"] for r in read_csv(args.previous_cases)}
    pairs = case_pairs(keys, X, groups, outputs, args.cache, previous)
    args.out.mkdir(parents=True, exist_ok=False)
    cnfs = args.out / "cnf"
    cnfs.mkdir()
    panel = []
    association = []
    terminal = []
    parser_cpu = 0
    for number, triple in enumerate(pairs, 1):
        for j, i in enumerate(triple, 1):
            key = keys[i]
            name = f"pair_{number:02d}_case_{j}"
            with gzip.open(args.cache / (key + ".cnf.gz"), "rb") as stream:
                raw = stream.read(1_550_001)
            if len(raw) > 1_550_000:
                raise ValueError("cached formula outside original input bound")
            plain = b"".join(line for line in raw.splitlines(keepends=True) if not line.lstrip().startswith(b"c"))
            checked = subprocess.check_output([str(args.checker.resolve())], input=plain, timeout=8).split()
            if checked[0].decode() != key:
                raise ValueError("anonymization changed the GBD input identity")
            parser_cpu += float(checked[4])
            (cnfs / f"{name}.cnf").write_bytes(plain)
            outcome = outputs[key]
            association.append({"case": name, "instance_key": key})
            panel.append({
                "case": name, "matched_set": number, "role": ("Fminus_gain", "Fminus_loss", "D_guard")[j - 1],
                "plain_bytes": len(plain), "scc_demand_share": outcome["scc_demand_share"],
                "routed_action": outcome["action"], "feature_cpu_s": outcome["feature_cpu_s"],
                "charged_policy_PAR2": outcome["selected_par2"],
                **{a + "_PAR2": matrix[key][a + "_par2"] for a in ACTIONS},
                **dict(zip(FEATURES, X[i])),
            })
            for action in ACTIONS:
                run = runs[key, action]
                terminal.append({"case": name, "action": action, "solved_within_600": run["resolved"],
                                 **{field: run[field] for field in
                                    ("cpu_s", "conflicts", "decisions", "propagations", "restarts")}})
    write_csv(args.out / "panel.csv", panel)
    write_csv(args.out / "terminal_diagnostics.csv", terminal)
    write_csv(args.out / "association_only.csv", association)
    write_json(args.out / "policy_result.json", json.loads((frozen / "summary.json").read_text()))
    write_json(args.out / "receipt.json", {"source": "Anniversary 2022 retained cohort",
        "case_count": len(panel), "case_count_previously_shown": 0, "matched_triplets": len(pairs),
        "new_solver_calls": 0, "gbd_verification_cpu_s": parser_cpu,
        "panel_preparation_wall_s": time.monotonic() - start})
    print(f"Prepared and hash-verified {len(panel)} new-to-Astra 2022 examples.")


if __name__ == "__main__":
    main()
