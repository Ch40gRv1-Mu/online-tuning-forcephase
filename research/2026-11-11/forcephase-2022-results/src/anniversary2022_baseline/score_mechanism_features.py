"""Test D-motivated static feature hypotheses against existing 2022 labels."""

import argparse
import fcntl
import json
from pathlib import Path
import sqlite3
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import fit, gains, calibrate, choose, measured_gains, SPLITS
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, BASE, DATA, load, read_csv, write_csv
from .structural_views import features


def horn_views(keys, base):
    fields = [f"{kind}vars_{stat}" for kind in ("horn", "invhorn")
              for stat in ("mean", "variance", "max", "entropy")]
    with sqlite3.connect(f"file:{BASE}?mode=ro", uri=True) as db:
        data = {key: values for key, *values in db.execute("select hash," + ",".join(fields) + " from features")}
    raw = np.asarray([data[key] for key in keys], dtype=float)
    valid = np.isfinite(raw).all(1) & (raw >= 0).all(1)
    safe = np.where(np.isfinite(raw), np.maximum(raw, 0), 0)
    left, right = safe[:, :4], safe[:, 4:]

    def summarize(values):
        mean, variance, maximum, entropy = values.T
        return np.column_stack((np.log1p(mean), np.log1p(variance / (mean * mean + 1e-12)),
                                np.log1p(maximum / (mean + 1)), entropy / np.maximum(base[:, 0], 1)))

    h, a = summarize(left), summarize(right)
    hypothesis = np.column_stack((h - a, h + a))
    control = features(keys, base)[0]["combined"]
    return {"base28": control, "horn_heterogeneity8": hypothesis,
            "base_plus_horn": np.column_stack((control, hypothesis))}, valid


def run(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("existing experiment receipt must be preserved")
        keys, base, costs, _, _, _ = load()
        split = read_csv(SPLITS)
        assert [r["instance_key"] for r in split] == keys
        if args.features:
            with np.load(args.features) as data:
                assert data["keys"].tolist() == keys
                valid, acquisition = data["valid"], data["fee"]
                names = data["views"].tolist() if "views" in data else ["base14", "ordered90", "random_order90"]
                views = {name: data[name] for name in names}
                cost_status = str(data["cost_status"]) if "cost_status" in data else "measured multi-step components"
                assert valid.shape == acquisition.shape == (len(keys),)
                assert acquisition.min() >= 0 and np.isfinite(acquisition).all()
                assert all(x.shape[0] == len(keys) and np.isfinite(x).all() for x in views.values())
        else:
            views, valid = horn_views(keys, base)
            acquisition = np.zeros(len(keys))
            cost_status = "unmeasured optimistic zero; predictive evidence only"
        inner = np.array([r["inner_validation"] == "True" for r in split])
        iso = np.array([r["iso_group"] for r in split])
        fine = np.array([r["fine_group"] for r in split])
        coarse = np.array([r["coarse_group"] for r in split])
        output = [{"instance_key": key, "D_PAR2": costs[i, 0], "valid_features": bool(valid[i])}
                  for i, key in enumerate(keys)]
        scores, fits = {}, []
        for mode, count in (("coarse", 4), ("fine", 5)):
            folds = np.array([int(r[mode + "_fold"]) for r in split])
            blocks = coarse if mode == "coarse" else fine
            for view, x in views.items():
                name = mode + "_" + view
                actions = np.zeros(len(keys), dtype=int)
                raw_actions = np.zeros(len(keys), dtype=int)
                fee = np.zeros(len(keys))
                raw_fee = np.zeros(len(keys))
                free_actions = np.zeros(len(keys), dtype=int)
                free_fee = np.zeros(len(keys))
                cuts = []
                for fold in range(count):
                    if time.monotonic() - start > 600:
                        raise TimeoutError("bounded static comparison exceeded ten minutes")
                    test = folds == fold
                    training = ~test & ~inner & valid
                    validation = ~test & inner & valid
                    assert not (set(iso[test]) & set(iso[training | validation]))
                    assert not (set(fine[training]) & set(fine[validation]))
                    begin = time.process_time()
                    model = fit("trees_relative", x[training], costs[training], 20261110 + fold)
                    p = gains(model, x[validation], "trees_relative")
                    cut = calibrate(p, costs[validation], acquisition[validation])
                    free_cut = calibrate(p, costs[validation], np.zeros(validation.sum()))
                    ids = np.flatnonzero(test & valid)
                    p, h = measured_gains(model, x[ids], "trees_relative")
                    actions[ids] = choose(p, cut)
                    raw_actions[ids] = choose(p, 0)
                    raw_fee[ids] = acquisition[ids] + h
                    if cut is not None:
                        fee[ids] = acquisition[ids] + h
                    free_actions[ids] = choose(p, free_cut)
                    if free_cut is not None:
                        free_fee[ids] = h
                    cuts.append({"fold": fold, "margin_PAR2_s": cut, "disabled": cut is None,
                                 "free_margin_PAR2_s": free_cut})
                    fits.append({"name": name, "fold": fold, "train": int(training.sum()),
                                 "validation": int(validation.sum()), "CPU_s": time.process_time() - begin})
                paid = timed_cost(costs[np.arange(len(keys)), actions], fee, 600)
                raw_paid = timed_cost(costs[np.arange(len(keys)), raw_actions], raw_fee, 600)
                free_paid = timed_cost(costs[np.arange(len(keys)), free_actions], free_fee, 600)
                score = assess(costs[:, 0], paid, blocks, 600)
                score.update(actions={a: int((actions == i).sum()) for i, a in enumerate(ACTIONS)},
                             cuts=cuts, zero_margin=assess(costs[:, 0], raw_paid, blocks, 600),
                             free_features=assess(costs[:, 0], free_paid, blocks, 600))
                if mode == "coarse":
                    score["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], paid, blocks)
                scores[name] = score
                for i, row in enumerate(output):
                    row[name + "_action"] = ACTIONS[actions[i]]
                    row[name + "_PAR2"] = float(paid[i])
                    row[name + "_decision_CPU_s"] = float(fee[i])
                write_csv(args.out / "predictions.csv", output)
                write(args.out / "summary.json", {"status": "running", "scores": scores, "fits": fits})
                print(f"SCORED {name}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}, actions={score['actions']}", flush=True)
        write(args.out / "summary.json", {
            "status": "complete", "parents": len(keys), "valid": int(valid.sum()), "scores": scores,
            "fits": fits, "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
            "acquisition_cost": cost_status,
            "new_solver_calls": 0, "new_feature_calls": 0,
            "source_sha256": sha(__file__), "inputs_sha256": {"GBD": sha(BASE), "splits": sha(SPLITS)},
            "feature_archive_sha256": sha(args.features) if args.features else None,
        })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--features", type=Path)
    run(parser.parse_args())
