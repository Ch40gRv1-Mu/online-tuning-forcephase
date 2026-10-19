#!/usr/bin/env python3
"""Audit v2: the single pre-specified M3 correction (docs/CORRECTION_PROTOCOL.md §5).

  scripts/audit_v2/m3_train_v2.py --dataset results/audit_v2/m3/dataset_strict.csv \
      --census results/m2_census/runs.csv --static results/static_features_dev.csv \
      --folds reports/m3/folds.csv --out reports/audit_v2/m3/revised \
      --policy-dir configs/policies/audit_v2

Runs the unchanged round-1 procedure (scripts/m3_train.py: same K, prefixes,
feature groups, model grid, cost-sensitive weights, nested CV seeds, bootstrap)
with exactly these differences:
  1. the dataset comes from the strict gate; the run aborts unless every row is
     valid_pair / solved_before_K / budget_before_K / censored_unmatched;
  2. 'x_saved_flip_frac' is removed from the P group and therefore from 'all'
     (and from the shuffled-label controls that use these groups);
  3. the outer folds computed by the procedure are checked to be identical to
     the round-1 file reports/m3/folds.csv (family membership unchanged).
Exported policies go to a new directory; round-1 policy files are untouched.
"""

import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import gate  # noqa: E402
import m3_train  # noqa: E402  (round-1 procedure, unchanged)

FLIP = "x_saved_flip_frac"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--census", required=True)
    ap.add_argument("--static", required=True)
    ap.add_argument("--folds", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--policy-dir", required=True)
    a = ap.parse_args()
    ds = pd.read_csv(a.dataset, dtype={"instance": str})
    gate.enforce(ds.category)  # hard failure on any data error
    # 2. remove the invalid feature everywhere it is used
    assert FLIP in m3_train.P_GROUP
    m3_train.P_GROUP = [f for f in m3_train.P_GROUP if f != FLIP]
    for name, cols in list(m3_train.FEATURE_SETS.items()):
        m3_train.FEATURE_SETS[name] = [f for f in cols if f != FLIP]
    assert all(FLIP not in cols for cols in m3_train.FEATURE_SETS.values())
    # 3. outer folds must equal the round-1 assignment
    round1 = pd.read_csv(a.folds, dtype={"instance": str})
    census = pd.read_csv(a.census, dtype={"instance": str})
    census = census[census.split.isin(["train", "val"])]
    insts = sorted(census[census.config == "D"].instance.unique())
    meta = census.drop_duplicates("instance").set_index("instance")
    groups = meta.loc[insts, "family_group"].values
    outer = m3_train.group_folds(groups, 5, m3_train.FOLD_SEED)
    mine = pd.DataFrame({"instance": insts, "family_group": groups, "fold": outer})
    r1 = round1.set_index("instance").loc[insts]
    if not (r1.fold.values == outer).all() or not (r1.family_group.values == groups).all():
        raise SystemExit("outer folds differ from round 1 -- aborting")
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.policy_dir, exist_ok=True)
    with open(os.path.join(a.out, "feature_sets.txt"), "w") as f:
        for name, cols in m3_train.FEATURE_SETS.items():
            f.write(f"{name} ({len(cols)}): {' '.join(cols)}\n")
    sys.argv = ["m3_train.py", "--dataset", a.dataset, "--census", a.census, "--static", a.static,
                "--out", a.out, "--policy-dir", a.policy_dir]
    m3_train.main()
    # the procedure rewrites folds.csv in --out; confirm it is the round-1 file
    if not pd.read_csv(os.path.join(a.out, "folds.csv"), dtype={"instance": str}).equals(round1):
        raise SystemExit("folds written by the revised run differ from round 1")


if __name__ == "__main__":
    main()
