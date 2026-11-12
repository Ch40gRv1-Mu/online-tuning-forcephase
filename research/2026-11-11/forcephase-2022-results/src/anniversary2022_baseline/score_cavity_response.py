"""First bounded test of complete-CNF algebraic response versus static marginals."""

import argparse
import fcntl
from pathlib import Path
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import calibrate, choose, gains, measured_gains, SPLITS
from .score_static_learnability import fit
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve existing algebraic-response scores")
        keys, _, costs, _, _, _ = load()
        split = read_csv(SPLITS)
        assert [r["instance_key"] for r in split] == keys
        with np.load(args.features) as archive:
            assert archive["keys"].tolist() == keys
            inputs = {"base43": (archive["base43"], archive["base_fee"]),
                      "uniform79": (archive["uniform79"], archive["uniform_fee"]),
                      "paired79": (archive["paired79"], archive["paired_fee"])}
        inner = np.array([r["inner_validation"] == "True" for r in split])
        iso = np.array([r["iso_group"] for r in split])
        fine = np.array([r["fine_group"] for r in split])
        coarse = np.array([r["coarse_group"] for r in split])
        output = [{"instance_key": k, "D_PAR2": float(costs[i, 0])} for i, k in enumerate(keys)]
        results, fits = {}, []
        for mode, count in (("coarse", 4), ("fine", 5)):
            folds = np.array([int(r[mode + "_fold"]) for r in split])
            groups = coarse if mode == "coarse" else fine
            for view, (x, acquisition) in inputs.items():
                name = mode + "_" + view
                actions, free_actions = np.zeros(len(keys), dtype=int), np.zeros(len(keys), dtype=int)
                fees, free_fees = np.zeros(len(keys)), np.zeros(len(keys))
                cuts = []
                for fold in range(count):
                    if time.monotonic() - start > 900:
                        raise TimeoutError("cavity-response comparison exceeded fifteen minutes")
                    held = folds == fold
                    train, val = ~held & ~inner, ~held & inner
                    assert not (set(iso[held]) & set(iso[train | val]))
                    assert not (set(fine[train]) & set(fine[val]))
                    tick = time.process_time()
                    model = fit("expressive", x[train], costs[train], 20261111 + fold)
                    vp = gains(model, x[val], "trees_relative")
                    cut = calibrate(vp, costs[val], acquisition[val])
                    free_cut = calibrate(vp, costs[val], np.zeros(val.sum()))
                    ids = np.flatnonzero(held)
                    hp, h = measured_gains(model, x[ids], "trees_relative")
                    actions[ids], free_actions[ids] = choose(hp, cut), choose(hp, free_cut)
                    if cut is not None:
                        fees[ids] = acquisition[ids] + h
                    if free_cut is not None:
                        free_fees[ids] = h
                    fits.append({"mode": mode, "view": view, "fold": fold, "CPU_s": time.process_time() - tick})
                    cuts.append({"fold": fold, "margin_PAR2_s": cut, "free_margin_PAR2_s": free_cut})
                selected = timed_cost(costs[np.arange(len(keys)), actions], fees, 600)
                free_selected = timed_cost(costs[np.arange(len(keys)), free_actions], free_fees, 600)
                score = assess(costs[:, 0], selected, groups, 600)
                score.update(cuts=cuts, free_features=assess(costs[:, 0], free_selected, groups, 600),
                             actions={a: int((actions == i).sum()) for i, a in enumerate(ACTIONS)})
                if mode == "coarse":
                    score["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], selected, coarse)
                results[name] = score
                for i, row in enumerate(output):
                    row[name + "_action"] = ACTIONS[actions[i]]
                    row[name + "_PAR2"] = float(selected[i])
                    row[name + "_decision_CPU_s"] = float(fees[i])
                write_csv(args.out / "predictions.csv", output)
                write(args.out / "summary.json", {"status": "running", "scores": results, "fits": fits})
                print(f"SCORED {name}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}", flush=True)
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "scores": results, "fits": fits,
              "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
              "new_solver_calls": 0, "short_search_calls": 0, "source_sha256": sha(__file__),
              "features_sha256": sha(args.features), "splits_sha256": sha(SPLITS),
              "cost_scope": "Native basic extraction charged on measured2843 only; unknown1876 optimistic zero. Algebraic increments measured1890. Not full deployment."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
