"""R37 block-cut positions; exact R21 free prediction engine, new structural inputs."""

import argparse
import fcntl
import os
from pathlib import Path
import time

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import choose, gains, QUANTILES, SPLITS
from .score_static_learnability import fit
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess
from .structural_clusters import ACTIONS, load, read_csv, write_csv


def calibrate_free(prediction, costs):
    cuts = np.unique(np.maximum(0, np.r_[0, np.quantile(prediction.max(axis=1), QUANTILES)]))
    best_cut, best = None, costs[:, 0].sum()
    for cut in cuts:
        action = choose(prediction, float(cut))
        total = costs[np.arange(len(costs)), action].sum()
        if total < best - 1e-8:
            best_cut, best = float(cut), total
    return best_cut


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve existing block-cut forest outcome")
        write(args.out / "owner.json", {"pid": os.getpid(), "source_sha256": sha(__file__),
            "remote_R35_untouched": True, "no_partial_R35_preferences": True})
        try:
            keys, _, costs, _, _, _ = load()
            split = read_csv(SPLITS)
            assert [r["instance_key"] for r in split] == keys
            with np.load(args.features) as z:
                assert z["keys"].tolist() == keys
                inputs = {view: z[view].copy() for view in ("topology63", "signed111", "random111")}
                eligible, informative = z["eligible"].copy(), z["informative"].copy()
            oracle = costs.min(axis=1)
            sorted_cost = np.sort(costs, axis=1)
            second_lower_bound = np.minimum(sorted_cost[:, 1], 600)
            clear = (sorted_cost[:, 0] < 600) & (second_lower_bound - sorted_cost[:, 0] >
                    np.maximum(.02, .1 * sorted_cost[:, 0]))
            diagnosis = {"parents": len(keys), "cost_valid": len(costs),
                         "clear_parent_labels": int(clear.sum()),
                         "all_censored": int(np.sum(np.all(costs >= 600, axis=1))),
                         "eligible": int(eligible.sum()), "balanced_connector_parents": int(informative.sum()),
                         "eligible_all_censored": int(np.sum(eligible & np.all(costs >= 600, axis=1))),
                         "free_full_oracle_gain_pct": float(100 * (costs[:, 0] - oracle).sum() / costs[:, 0].sum()),
                         "free_eligible_oracle_population_pct": float(100 * (costs[:, 0] - oracle)[eligible].sum() / costs[:, 0].sum()),
                         "free_informative_oracle_population_pct": float(100 * (costs[:, 0] - oracle)[informative].sum() / costs[:, 0].sum()),
                         "new_solver_calls": 0, "short_search_calls": 0}
            if informative.sum() < 50 or diagnosis["free_informative_oracle_population_pct"] < .5:
                write(args.out / "summary.json", {"status": "complete_low_information_no_fits", "diagnosis": diagnosis,
                      "fits": [], "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
                      "source_sha256": sha(__file__), "features_sha256": sha(args.features),
                      "reason": "Preregistered balanced-connector coverage or full-population oracle headroom screen failed"})
                return
            iso = np.array([r["iso_group"] for r in split])
            fine = np.array([r["fine_group"] for r in split])
            coarse = np.array([r["coarse_group"] for r in split])
            inner = np.array([r["inner_validation"] == "True" for r in split])
            output = [{"instance_key": k, "D_PAR2": float(costs[i, 0])} for i, k in enumerate(keys)]
            results, fits, comparisons = {}, [], {}
            (args.out / "fold_arrays").mkdir(exist_ok=True)
            selected_by_mode = {}
            for mode, count in (("coarse", 4), ("fine", 5)):
                folds = np.array([int(r[mode + "_fold"]) for r in split])
                groups = coarse if mode == "coarse" else fine
                selected_by_mode[mode] = {}
                for view, x in inputs.items():
                    actions = np.zeros(len(keys), int)
                    cuts = []
                    for fold in range(count):
                        if time.monotonic() - start > 900:
                            raise TimeoutError("cost-free block-cut score exceeded fifteen minutes")
                        held = folds == fold
                        train, val = ~held & ~inner, ~held & inner
                        assert not (set(iso[held]) & set(iso[train | val]))
                        assert not (set(fine[train]) & set(fine[val]))
                        tick = time.process_time()
                        model = fit("expressive", x[train], costs[train], 20261111 + fold)
                        model.n_jobs = 4
                        vp = gains(model, x[val], "trees_relative")
                        hp = gains(model, x[held], "trees_relative")
                        cut = calibrate_free(vp, costs[val])
                        actions[held] = choose(hp, cut)
                        cuts.append({"fold": fold, "margin_PAR2_s": cut})
                        np.savez_compressed(args.out / "fold_arrays" / f"{mode}_{view}_{fold}.npz",
                                            train_ids=np.flatnonzero(train), validation_ids=np.flatnonzero(val),
                                            held_ids=np.flatnonzero(held), validation_scores=vp, held_scores=hp)
                        fits.append({"mode": mode, "view": view, "fold": fold,
                                     "CPU_s": time.process_time() - tick})
                    selected = costs[np.arange(len(keys)), actions]
                    selected_by_mode[mode][view] = selected
                    result = assess(costs[:, 0], selected, groups, 600)
                    result.update(cuts=cuts, actions={a: int((actions == i).sum()) for i, a in enumerate(ACTIONS)})
                    if mode == "coarse":
                        result["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], selected, coarse)
                    name = mode + "_" + view
                    results[name] = result
                    for i, row in enumerate(output):
                        row[name + "_action"] = ACTIONS[actions[i]]
                        row[name + "_PAR2"] = float(selected[i])
                    write_csv(args.out / "predictions.csv", output)
                    write(args.out / "summary.json", {"status": "running", "scores": results,
                          "fits": fits, "diagnosis": diagnosis})
                    print(f"SCORED {name}: free_gain={result['gain_pct']:+.6f}%, solved={result['solved']}", flush=True)
                for control in ("topology63", "random111"):
                    comparison = assess(selected_by_mode[mode][control], selected_by_mode[mode]["signed111"], groups, 600)
                    if mode == "coarse":
                        comparison["exact_eight_block_95_pct"] = exact_small_block_interval(
                            selected_by_mode[mode][control], selected_by_mode[mode]["signed111"], coarse)
                    comparisons[mode + "_over_" + control] = comparison
            passes = True
            for mode in ("coarse", "fine"):
                result = results[mode + "_signed111"]
                interval = result.get("exact_eight_block_95_pct", result["block_interval_95_pct"])
                passes &= result["gain_pct"] >= 2 and interval[0] > 0
                for control in ("topology63", "random111"):
                    comparison = comparisons[mode + "_over_" + control]
                    ci = comparison.get("exact_eight_block_95_pct", comparison["block_interval_95_pct"])
                    passes &= comparison["gain_pct"] > 0 and ci[0] >= 0
            full = []
            if passes:
                for view, x in inputs.items():
                    model = fit("expressive", x[~inner], costs[~inner], 20261111)
                    cut = calibrate_free(gains(model, x[inner], "trees_relative"), costs[inner])
                    path = args.out / ("development_" + view + ".joblib")
                    joblib.dump({"model": model, "cut": cut, "view": view,
                                 "features_sha256": sha(args.features), "actions": ACTIONS}, path)
                    full.append({"view": view, "model_sha256": sha(path), "margin_PAR2_s": cut})
            write(args.out / "summary.json", {"status": "complete", "scores": results, "fits": fits,
                  "diagnosis": diagnosis, "paired_increment_comparisons": comparisons,
                  "free_screen_passed": bool(passes), "full_development_models": full,
                  "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
                  "source_sha256": sha(__file__), "features_sha256": sha(args.features),
                  "splits_sha256": sha(SPLITS), "new_solver_calls": 0, "short_search_calls": 0,
                  "cost_scope": "Acquisition and decision CPU free optimistic predictive screen, not deployed performance",
                  "claim_scope": "Repeated2022 development; nominal intervals, no independent test"})
        except Exception as error:
            write(args.out / "failure.json", {"status": "failed", "error": repr(error),
                  "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start})
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
