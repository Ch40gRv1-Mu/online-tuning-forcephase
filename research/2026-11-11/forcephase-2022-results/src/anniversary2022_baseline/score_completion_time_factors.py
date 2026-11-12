"""R28: exact paired completion/time factorization, matched cached R27 control."""

import argparse
import fcntl
import json
from pathlib import Path
import signal
import time

import numpy as np
from sklearn.ensemble import ExtraTreesRegressor
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import calibrate, choose, SPLITS
from .score_static_seed_agreement import load_views, SEEDS
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess
from .structural_clusters import ACTIONS, BASE, DATA, load, read_csv, write_csv


def factors(cost):
    solved = cost <= 600
    completed_time = cost * solved
    completion = 2 * (solved[:, 1:].astype(float) - solved[:, :1])
    speed = (completed_time[:, :1] - completed_time[:, 1:]) / 600
    return np.c_[completion, speed]


def combine(y):
    return 600 * (y[:, :2] + y[:, 2:])


def fail_timeout(*_):
    raise TimeoutError("R28 exceeded fifteen-minute watchdog")


def main(args):
    wall, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve prior R28 results")
        signal.signal(signal.SIGALRM, fail_timeout)
        signal.alarm(900)
        scores, fits = {}, []
        try:
            base_dir = DATA / "mechanism_R27_20261111"
            base = json.loads((base_dir / "summary.json").read_text())
            assert base["status"] == "complete" and base["completed_outer_fits"] == 84
            keys, _, costs, _, _, _ = load()
            assert len(keys) == 4719
            y = factors(costs)
            assert np.allclose(combine(y), costs[:, :1] - costs[:, 1:], rtol=0, atol=1e-10)
            assert np.all(y[(costs == 1200).all(axis=1)] == 0)
            split = read_csv(SPLITS)
            original = read_csv(DATA / "mechanism_R11_20261111/predictions.csv")
            base_rows = read_csv(base_dir / "predictions.csv")
            assert [r["instance_key"] for r in split] == [r["instance_key"] for r in original] == [r["instance_key"] for r in base_rows] == keys
            x, valid = load_views(keys)[0]["linear42"]
            assert valid.all() and x.shape == (4719, 42)
            x = x.astype(np.float32)
            inner = np.array([r["inner_validation"] == "True" for r in split])
            iso, coarse, fine = [np.array([r[k + "_group"] for r in split]) for k in ("iso", "coarse", "fine")]
            output = [{"instance_key": k, "D_PAR2": float(costs[i, 0])} for i, k in enumerate(keys)]
            fold_dir = args.out / "fold_arrays"
            fold_dir.mkdir(exist_ok=True)
            for mode, count in (("iso_diagnostic", 5), ("coarse", 4), ("fine", 5)):
                folds = np.array([int(r["diagnostic_iso_fold"]) for r in original]) if mode == "iso_diagnostic" else np.array([int(r[mode + "_fold"]) for r in split])
                blocks = fine if mode == "fine" else coarse
                action, raw = np.zeros(len(keys), int), np.zeros(len(keys), int)
                cuts = []
                for fold in range(count):
                    held = folds == fold
                    train, val = ~held & ~inner, ~held & inner
                    assert not (set(iso[held]) & set(iso[train | val]))
                    assert not (set(fine[train]) & set(fine[val]))
                    with np.load(base_dir / "fold_arrays" / f"{mode}_relative_control_{fold}.npz") as old:
                        assert np.array_equal(old["held_ids"], np.flatnonzero(held))
                        assert np.array_equal(old["validation_ids"], np.flatnonzero(val))
                    vp, hp = [], []
                    for seed in SEEDS:
                        began = time.process_time()
                        model = ExtraTreesRegressor(n_estimators=256, max_depth=12,
                            min_samples_leaf=4, max_features=.8, random_state=seed + fold, n_jobs=4)
                        model.fit(x[train], y[train])
                        model.n_jobs = 1
                        pv, ph = model.predict(x[val]), model.predict(x[held])
                        vp.append(pv); hp.append(ph)
                        fits.append({"mode": mode, "fold": fold, "seed": seed,
                                     "training_parents": int(train.sum()), "validation_parents": int(val.sum()),
                                     "CPU_s": time.process_time() - began,
                                     "actual_nodes": int(sum(t.tree_.node_count for t in model.estimators_))})
                    vp, hp = np.asarray(vp), np.asarray(hp)
                    validation = np.min([combine(p) for p in vp], axis=0)
                    prediction = np.min([combine(p) for p in hp], axis=0)
                    cut = calibrate(validation, costs[val], np.zeros(val.sum()))
                    action[held], raw[held] = choose(prediction, cut), choose(prediction, 0)
                    cuts.append({"fold": fold, "margin_PAR2_s": cut})
                    np.savez_compressed(fold_dir / f"{mode}_{fold}.npz", held_ids=np.flatnonzero(held),
                        validation_ids=np.flatnonzero(val), validation_factors=vp, held_factors=hp)
                selected = costs[np.arange(len(keys)), action]
                reference = np.array([float(r[mode + "_relative_control_PAR2"]) for r in base_rows])
                score = assess(costs[:, 0], selected, blocks, 600)
                score.update(cuts=cuts, actions={a: int(np.sum(action == i)) for i, a in enumerate(ACTIONS)},
                    matched_relative_control=assess(reference, selected, blocks, 600),
                    zero_margin=assess(costs[:, 0], costs[np.arange(len(keys)), raw], blocks, 600))
                if mode != "fine":
                    score["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], selected, coarse)
                if mode == "iso_diagnostic":
                    score["within_iso_parent_interval"] = assess(costs[:, 0], selected, iso, 600)
                scores[mode] = score
                for i, row in enumerate(output):
                    row[mode + "_action"] = ACTIONS[action[i]]
                    row[mode + "_PAR2"] = float(selected[i])
                write_csv(args.out / "predictions.csv", output)
                write(args.out / "summary.json", {"status": "running", "scores": scores, "fits": fits})
                print(f"SCORED {mode}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}, rescue/lost={score['newly_solved']}/{score['lost_solves']}", flush=True)
            passed = all(scores[m]["gain_pct"] >= 2 and scores[m].get("exact_eight_block_95_pct", scores[m]["block_interval_95_pct"])[0] > 0 for m in ("coarse", "fine"))
            write(args.out / "summary.json", {"status": "complete", "parents": 4719, "scores": scores,
                "fits": fits, "completed_outer_fits": len(fits), "screen_passed": bool(passed),
                "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - wall,
                "semantic_checks": {"exact_PAR2_factorization_all4719": True, "no_fabricated_all_timeout_targets": True},
                "source_sha256": sha(__file__), "base_receipt_sha256": sha(base_dir / "summary.json"),
                "GBD_sha256": sha(BASE), "splits_sha256": sha(SPLITS),
                "scope": "Repeated2022 development, nominal intervals; query/acquisition free prediction screen",
                "new_solver_calls": 0, "short_search_calls": 0, "new_feature_extractions": 0})
        except BaseException as exc:
            write(args.out / "failure.json", {"status": "failed", "error": repr(exc), "completed_fits": len(fits),
                "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - wall})
            raise
        finally:
            signal.alarm(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
