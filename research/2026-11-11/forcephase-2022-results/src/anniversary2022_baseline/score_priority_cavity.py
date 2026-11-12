"""Test priority-conditioned fields against pooled and degree-matched controls."""

import argparse
import fcntl
from pathlib import Path
import time

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import calibrate, choose, measured_gains, SPLITS
from .score_static_learnability import fit
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, load, read_csv, write_csv


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("do not overwrite measured priority experiment")
        keys, _, costs, _, _, _ = load()
        split = read_csv(SPLITS)
        assert [r["instance_key"] for r in split] == keys
        with np.load(args.features) as z:
            assert z["keys"].tolist() == keys
            views = {v: (z[v].copy(), z[f].copy()) for v, f in
                     (("pooled115", "pooled_fee"), ("ordered163", "ordered_fee"), ("random163", "random_fee"))}
        iso = np.array([r["iso_group"] for r in split])
        fine = np.array([r["fine_group"] for r in split])
        coarse = np.array([r["coarse_group"] for r in split])
        inner = np.array([r["inner_validation"] == "True" for r in split])
        output = [{"instance_key": k, "D_PAR2": float(costs[i, 0])} for i, k in enumerate(keys)]
        scores, fits, full = {}, [], []
        (args.out / "fold_arrays").mkdir(exist_ok=True)
        for mode, count in (("coarse", 4), ("fine", 5)):
            folds = np.array([int(r[mode + "_fold"]) for r in split])
            groups = coarse if mode == "coarse" else fine
            for view, (x, acquisition) in views.items():
                actions, free_actions = np.zeros(len(keys), int), np.zeros(len(keys), int)
                fees, free_fees = np.zeros(len(keys)), np.zeros(len(keys))
                cuts = []
                for fold in range(count):
                    if time.monotonic() - start > 1200:
                        raise TimeoutError("priority comparison exceeded twenty minutes")
                    held = folds == fold
                    train, val = ~held & ~inner, ~held & inner
                    assert not set(iso[held]) & set(iso[train | val])
                    assert not set(fine[train]) & set(fine[val])
                    tick = time.process_time()
                    model = fit("expressive", x[train], costs[train], 20261111 + fold)
                    vp, vh = measured_gains(model, x[val], "trees_relative")
                    cut = calibrate(vp, costs[val], acquisition[val] + vh)
                    free_cut = calibrate(vp, costs[val], vh)
                    ids = np.flatnonzero(held)
                    hp, h = measured_gains(model, x[ids], "trees_relative")
                    actions[ids], free_actions[ids] = choose(hp, cut), choose(hp, free_cut)
                    if cut is not None:
                        fees[ids] = acquisition[ids] + h
                    if free_cut is not None:
                        free_fees[ids] = h
                    np.savez_compressed(args.out / "fold_arrays" / f"{mode}_{view}_{fold}.npz",
                                        train_ids=np.flatnonzero(train), validation_ids=np.flatnonzero(val),
                                        held_ids=ids, validation_scores=vp, held_scores=hp,
                                        validation_query_CPU_s=vh, held_query_CPU_s=h)
                    fits.append({"mode": mode, "view": view, "fold": fold,
                                 "CPU_s": time.process_time() - tick})
                    cuts.append({"fold": fold, "margin_PAR2_s": cut, "free_margin_PAR2_s": free_cut})
                selected = timed_cost(costs[np.arange(len(keys)), actions], fees, 600)
                free_selected = timed_cost(costs[np.arange(len(keys)), free_actions], free_fees, 600)
                result = assess(costs[:, 0], selected, groups, 600)
                result.update(cuts=cuts, actions={a: int((actions == i).sum()) for i, a in enumerate(ACTIONS)},
                              free_features=assess(costs[:, 0], free_selected, groups, 600))
                if mode == "coarse":
                    result["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], selected, coarse)
                name = mode + "_" + view
                scores[name] = result
                for i, row in enumerate(output):
                    row[name + "_action"] = ACTIONS[actions[i]]
                    row[name + "_PAR2"] = float(selected[i])
                    row[name + "_decision_CPU_s"] = float(fees[i])
                write_csv(args.out / "predictions.csv", output)
                write(args.out / "summary.json", {"status": "running", "scores": scores, "fits": fits})
                print(f"SCORED {name}: gain={result['gain_pct']:+.6f}%, solved={result['solved']}", flush=True)
        # Export the three predetermined alternatives, never the outer-score winner.
        for view, (x, acquisition) in views.items():
            model = fit("expressive", x[~inner], costs[~inner], 20261111)
            vp, vh = measured_gains(model, x[inner], "trees_relative")
            cut = calibrate(vp, costs[inner], acquisition[inner] + vh)
            path = args.out / ("development_" + view + ".joblib")
            joblib.dump({"model": model, "cut": cut, "view": view,
                         "features_sha256": sha(args.features), "actions": ACTIONS}, path)
            full.append({"view": view, "margin_PAR2_s": cut, "model_sha256": sha(path)})
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "scores": scores,
              "fits": fits, "full_development_models": full, "CPU_s": time.process_time() - cpu,
              "wall_s": time.monotonic() - start, "new_solver_calls": 0, "short_search_calls": 0,
              "source_sha256": sha(__file__), "features_sha256": sha(args.features),
              "splits_sha256": sha(SPLITS), "primary_view": "ordered163",
              "cost_scope": "Measured local feature/query CPU plus collaborator solver CPU, exploratory only; native acquisition1876 unknown optimistic zero",
              "claim_scope": "Repeated2022 development, no independent confirmation"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
