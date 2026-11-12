"""Describe R27 errors; true completion patterns here are outcomes, never inputs."""

import json
import time

import numpy as np

from .common import sha, write
from .score_joint_completion import completion_pattern
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


def main():
    cpu, wall = time.process_time(), time.monotonic()
    root = DATA / "mechanism_R27_20261111"
    summary = json.loads((root / "summary.json").read_text())
    assert summary["status"] == "complete" and summary["completed_outer_fits"] == 84
    keys, _, cost, _, _, _ = load()
    rows = read_csv(root / "predictions.csv")
    previous = read_csv(DATA / "mechanism_R12_20261111/predictions.csv")
    assert [r["instance_key"] for r in rows] == [r["instance_key"] for r in previous] == keys
    assert len(list((root / "fold_arrays").glob("*.npz"))) == 28
    pattern = completion_pattern(cost)
    result = {"parents": len(keys), "patterns": {}, "scores": {}, "counterexamples_association_only": True}
    for bit in range(8):
        mask = pattern == bit
        gain = cost[:, 0] - cost.min(axis=1)
        result["patterns"][str(bit)] = {"parents": int(mask.sum()),
            "budget_completed_actions": [a for j, a in enumerate(ACTIONS) if bit & (1 << j)],
            "oracle_saving_PAR2_s": float(gain[mask].sum()),
            "oracle_headroom_whole_population_pp": float(100 * gain[mask].sum() / cost[:, 0].sum())}
    counterexamples = []
    for mode in ("iso_diagnostic", "coarse", "fine"):
        for kind in ("joint_completion", "relative_control"):
            name = mode + "_" + kind
            action = np.array([ACTIONS.index(r[name + "_action"]) for r in rows])
            selected = cost[np.arange(len(keys)), action]
            assert np.array_equal(selected, np.array([float(r[name + "_PAR2"]) for r in rows]))
            assert np.isclose(100 * (cost[:, 0] - selected).sum() / cost[:, 0].sum(), summary["scores"][name]["gain_pct"])
            gain = cost[:, 0] - selected
            ds, fs = cost[:, 0] <= 600, selected <= 600
            strata = {"rescued": ~ds & fs, "lost_solve": ds & ~fs,
                      "both_solved_switched": ds & fs & (action != 0),
                      "both_censored_switched": ~ds & ~fs & (action != 0)}
            record = {"strata": {s: {"parents": int(mask.sum()), "net_PAR2_s": float(gain[mask].sum())}
                                 for s, mask in strata.items()},
                      "net_by_true_pattern_PAR2_s": {str(b): float(gain[pattern == b].sum()) for b in range(8)}}
            if kind == "relative_control":
                old = np.array([ACTIONS.index(r[mode + "_linear42_min3_action"]) for r in previous])
                record["action_mismatches_to_original_R12"] = int(np.sum(action != old))
            result["scores"][name] = record
            if kind == "joint_completion":
                for at in np.argsort(gain)[:16]:
                    counterexamples.append({"mode": mode, "association_only_key": keys[at],
                        "chosen": ACTIONS[action[at]], "D_PAR2": float(cost[at, 0]),
                        "chosen_PAR2": float(selected[at]), "saving_PAR2_s": float(gain[at]),
                        "true_completion_pattern_outcome_only": int(pattern[at])})
    result.update(CPU_s=time.process_time() - cpu, wall_s=time.monotonic() - wall,
                  source_sha256=sha(__file__), predictions_sha256=sha(root / "predictions.csv"),
                  new_model_fits=0, new_solver_calls=0)
    write(root / "error_diagnosis.json", result)
    write_csv(root / "counterexamples_association_only.csv", counterexamples)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
