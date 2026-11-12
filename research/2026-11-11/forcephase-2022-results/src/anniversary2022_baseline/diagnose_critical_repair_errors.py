"""Describe complete R25 held-out errors; never fit or route from case identity."""

import argparse
import json
from pathlib import Path
import time

import numpy as np

from .common import sha, write
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


LOCAL = ("opposed_fraction", "critical_fraction", "blocked_fraction", "root_support",
         "root_fanout", "root_entropy", "mean_fanout", "root_blocked")
GLOBAL = ("flow_mass", "flow_concentration", "flow_entropy", "flow_root_cosine", "flow_root_support",
          "flow_blocked", "flow_dangling", "flow_fanout", "flow_branching", "flow_cycle",
          "flow_component_size", "root_reachable", "reach_blocked", "reach_max_SCC", "flow_sink", "flow_source")


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    original = json.loads((args.root / "summary.json").read_text())
    assert original["status"] == "complete"
    assert not (args.root / "error_diagnosis.json").exists()
    keys, _, costs, _, _, _ = load()
    rows = read_csv(args.root / "predictions.csv")
    assert [r["instance_key"] for r in rows] == keys
    with np.load(args.features) as z:
        assert z["keys"].tolist() == keys
        eligible, fields = z["eligible"].copy(), z["actual115"][:, 43:].copy()
    result, cases = {}, []
    for mode in ("coarse", "fine"):
        name = mode + "_actual115"
        selected = np.array([float(r[name + "_PAR2"]) for r in rows])
        actions = np.array([ACTIONS.index(r[name + "_action"]) for r in rows])
        assert np.array_equal(selected, costs[np.arange(len(keys)), actions])
        delta = costs[:, 0] - selected
        switched = actions != 0
        ds, ss = costs[:, 0] < 600, selected < 600
        strata = {"rescued": switched & ~ds & ss, "lost_solve": switched & ds & ~ss,
                  "both_solved": switched & ds & ss, "both_censored": switched & ~ds & ~ss}
        result[mode] = {}
        for label, mask in strata.items():
            result[mode][label] = {"parents": int(mask.sum()), "net_PAR2_s": float(delta[mask].sum()),
                                  "gross_positive_PAR2_s": float(np.maximum(delta[mask], 0).sum()),
                                  "gross_negative_PAR2_s": float(np.minimum(delta[mask], 0).sum()),
                                  "median_D_time_when_solved": float(np.median(costs[mask & ds, 0])) if np.any(mask & ds) else None}
        for label, mask in (("eligible2325", eligible), ("remaining2394", ~eligible)):
            result[mode][label] = {"parents": int(mask.sum()), "switches": int(np.sum(mask & switched)),
                                  "net_PAR2_s": float(delta[mask].sum())}
        negatives = np.flatnonzero(switched & (delta < 0))
        positives = np.flatnonzero(switched & (delta > 0))
        extreme = [("loss", i) for i in sorted(negatives, key=lambda i: delta[i])[:12]]
        extreme += [("gain", i) for i in sorted(positives, key=lambda i: -delta[i])[:12]]
        for kind, i in extreme:
            row = {"instance_key_association_only": keys[i], "mode": mode, "case": kind,
                   "chosen_action": ACTIONS[actions[i]], "D_PAR2": float(costs[i, 0]),
                   "Fplus_PAR2": float(costs[i, 1]), "Fminus_PAR2": float(costs[i, 2]),
                   "net_PAR2_s": float(delta[i]), "resource_eligible": bool(eligible[i])}
            for phase, offset in (("plus", 0), ("minus", 24)):
                for j, feature in enumerate(LOCAL + GLOBAL):
                    row[phase + "_" + feature] = float(fields[i, offset + j]) if eligible[i] else None
            cases.append(row)
    write_csv(args.root / "counterexamples_association_only.csv", cases)
    write(args.root / "error_diagnosis.json", {"status": "complete", "parents": len(keys), "results": result,
          "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
          "source_sha256": sha(__file__), "original_scores_sha256": sha(args.root / "summary.json"),
          "features_sha256": sha(args.features), "new_models": 0, "new_solver_calls": 0,
          "scope": "Post-score development error analysis; identities associate cases only, no policy fitted"})
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=DATA / "mechanism_R25_20261111")
    p.add_argument("--features", type=Path, default=DATA / "mechanism_R25_features_v2_20261111/features.npz")
    main(p.parse_args())
