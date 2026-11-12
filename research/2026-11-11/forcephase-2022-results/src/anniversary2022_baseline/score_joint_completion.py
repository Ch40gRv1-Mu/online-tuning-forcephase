"""R27: static joint-completion probabilities versus matched relative-cost trees."""

import argparse
import fcntl
import signal
import time

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import calibrate, choose, gains, SPLITS
from .score_static_learnability import fit as fit_relative
from .score_static_seed_agreement import load_views, SEEDS
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess
from .structural_clusters import ACTIONS, BASE, DATA, load, read_csv, write_csv


def completion_pattern(cost):
    return ((cost <= 600).astype(int) * np.array([1, 2, 4])).sum(axis=1)


def fit_joint(x, cost, seed):
    pattern = completion_pattern(cost)
    model = ExtraTreesClassifier(n_estimators=256, max_depth=12,
                                min_samples_leaf=4, max_features=.8,
                                criterion="log_loss", random_state=seed, n_jobs=4)
    model.fit(x, pattern)
    model.n_jobs = 1
    templates = np.array([cost[pattern == c].mean(axis=0) for c in model.classes_])
    return model, templates


def joint_prediction(model, templates, x):
    probability = model.predict_proba(x)
    expected_cost = probability @ templates
    return expected_cost[:, :1] - expected_cost[:, 1:], expected_cost


def semantic_check():
    bits = np.arange(8)
    solved = (bits[:, None] & np.array([1, 2, 4])) != 0
    cost = np.where(solved, np.array([3., 5., 7.]), 1200.)
    assert np.array_equal(completion_pattern(cost), bits)
    assert completion_pattern(np.array([[600., 1200., 600.]]))[0] == 5
    probability = np.eye(8)
    expected = probability @ cost
    assert np.array_equal(expected, cost)
    assert np.all(choose(expected[:, :1] - expected[:, 1:], 0)[[0, 1, 7]] == 0)
    return {"eight_patterns_and_T600_boundary": True,
            "identity_mixture_reconstructs_training_templates": True,
            "timeout_ties_do_not_create_forced_winner": True}


def fail_timeout(*_):
    raise TimeoutError("R27 complete comparison exceeded fifteen-minute watchdog")


def main(args):
    wall, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve the existing R27 identity")
        signal.signal(signal.SIGALRM, fail_timeout)
        signal.alarm(900)
        scores, fits = {}, []
        try:
            check = semantic_check()
            keys, _, costs, _, _, _ = load()
            assert len(keys) == 4719
            assert np.all((costs <= 600) | (costs == 1200))
            rows = read_csv(SPLITS)
            original = read_csv(DATA / "mechanism_R11_20261111/predictions.csv")
            assert [r["instance_key"] for r in rows] == [r["instance_key"] for r in original] == keys
            x, valid = load_views(keys)[0]["linear42"]
            assert valid.all() and x.shape == (4719, 42)
            x = x.astype(np.float32)
            inner = np.array([r["inner_validation"] == "True" for r in rows])
            iso = np.array([r["iso_group"] for r in rows])
            coarse = np.array([r["coarse_group"] for r in rows])
            fine = np.array([r["fine_group"] for r in rows])
            output = [{"instance_key": k, "D_PAR2": float(costs[i, 0])} for i, k in enumerate(keys)]
            fold_dir = args.out / "fold_arrays"
            fold_dir.mkdir(exist_ok=True)
            for mode, count in (("iso_diagnostic", 5), ("coarse", 4), ("fine", 5)):
                folds = np.array([int(r["diagnostic_iso_fold"]) for r in original]) if mode == "iso_diagnostic" else np.array([int(r[mode + "_fold"]) for r in rows])
                blocks = fine if mode == "fine" else coarse
                for kind in ("joint_completion", "relative_control"):
                    action, raw_action = np.zeros(len(keys), int), np.zeros(len(keys), int)
                    cuts = []
                    for fold in range(count):
                        held = folds == fold
                        train, val = ~held & ~inner, ~held & inner
                        assert not (set(iso[held]) & set(iso[train | val]))
                        assert not (set(fine[train]) & set(fine[val]))
                        vp, hp, records = [], [], []
                        for seed in SEEDS:
                            began = time.process_time()
                            if kind == "joint_completion":
                                model, templates = fit_joint(x[train], costs[train], seed + fold)
                                pv, _ = joint_prediction(model, templates, x[val])
                                ph, expected = joint_prediction(model, templates, x[held])
                                record = {"classes": model.classes_.tolist(),
                                          "training_class_counts": [int(np.sum(completion_pattern(costs[train]) == c)) for c in model.classes_],
                                          "training_PAR2_templates": templates.tolist()}
                            else:
                                model = fit_relative("expressive", x[train], costs[train], seed + fold)
                                pv, ph = gains(model, x[val], "trees_relative"), gains(model, x[held], "trees_relative")
                                record = {}
                            vp.append(pv)
                            hp.append(ph)
                            record.update(mode=mode, kind=kind, fold=fold, seed=seed,
                                          training_parents=int(train.sum()), validation_parents=int(val.sum()),
                                          held_parents=int(held.sum()), CPU_s=time.process_time() - began,
                                          actual_nodes=int(sum(t.tree_.node_count for t in model.estimators_)))
                            fits.append(record)
                            records.append(record)
                        vp, hp = np.asarray(vp), np.asarray(hp)
                        validation, prediction = vp.min(axis=0), hp.min(axis=0)
                        cut = calibrate(validation, costs[val], np.zeros(val.sum()))
                        action[held], raw_action[held] = choose(prediction, cut), choose(prediction, 0)
                        cuts.append({"fold": fold, "margin_PAR2_s": cut})
                        np.savez_compressed(fold_dir / f"{mode}_{kind}_{fold}.npz",
                                            held_ids=np.flatnonzero(held), validation_ids=np.flatnonzero(val),
                                            validation_gains=vp, held_gains=hp)
                    selected = costs[np.arange(len(keys)), action]
                    result = assess(costs[:, 0], selected, blocks, 600)
                    result.update(cuts=cuts, actions={a: int(np.sum(action == i)) for i, a in enumerate(ACTIONS)},
                                  zero_margin=assess(costs[:, 0], costs[np.arange(len(keys)), raw_action], blocks, 600))
                    if mode != "fine":
                        result["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], selected, coarse)
                    if mode == "iso_diagnostic":
                        result["within_iso_parent_interval"] = assess(costs[:, 0], selected, iso, 600)
                    name = mode + "_" + kind
                    scores[name] = result
                    for i, row in enumerate(output):
                        row[name + "_action"] = ACTIONS[action[i]]
                        row[name + "_PAR2"] = float(selected[i])
                    write_csv(args.out / "predictions.csv", output)
                    write(args.out / "summary.json", {"status": "running", "scores": scores, "fits": fits})
                    print(f"SCORED {name}: gain={result['gain_pct']:+.6f}%, solved={result['solved']}, rescue/lost={result['newly_solved']}/{result['lost_solves']}", flush=True)
            paired = {}
            for mode in ("iso_diagnostic", "coarse", "fine"):
                reference = np.array([r[mode + "_relative_control_PAR2"] for r in output])
                selected = np.array([r[mode + "_joint_completion_PAR2"] for r in output])
                paired[mode] = assess(reference, selected, fine if mode == "fine" else coarse, 600)
            passed = all(scores[mode + "_joint_completion"]["gain_pct"] >= 2 and
                         scores[mode + "_joint_completion"].get("exact_eight_block_95_pct", scores[mode + "_joint_completion"]["block_interval_95_pct"])[0] > 0
                         for mode in ("coarse", "fine"))
            write(args.out / "summary.json", {"status": "complete", "parents": 4719, "scores": scores,
                  "matched_control_comparison": paired, "fits": fits, "completed_outer_fits": len(fits),
                  "screen_passed": bool(passed), "CPU_s": time.process_time() - cpu,
                  "wall_s": time.monotonic() - wall, "semantic_checks": check,
                  "class_counts_description_only": np.bincount(completion_pattern(costs), minlength=8).tolist(),
                  "scope": "All retained2022 repeatedly-developed parents; nominal intervals, no independent test",
                  "cost_boundary": "Acquisition/query free optimistic prediction screen; actual training/analysis CPU metered",
                  "new_solver_calls": 0, "short_search_calls": 0, "new_feature_extractions": 0,
                  "source_sha256": sha(__file__), "splits_sha256": sha(SPLITS), "GBD_sha256": sha(BASE)})
        except BaseException as exc:
            write(args.out / "failure.json", {"status": "failed", "error": repr(exc), "completed_fits": len(fits),
                  "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - wall})
            raise
        finally:
            signal.alarm(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=__import__("pathlib").Path, required=True)
    main(parser.parse_args())
