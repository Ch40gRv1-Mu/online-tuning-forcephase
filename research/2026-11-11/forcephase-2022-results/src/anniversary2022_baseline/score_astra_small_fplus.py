"""Training-fold refit of Astra's small-formula Fplus rule template."""

import argparse
import fcntl
import itertools
from pathlib import Path
import time

import numpy as np

from .common import sha, write
from .predict_relative_cost import SPLITS
from .score_static_seed_agreement import load_views
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


QUANTILES = (0., .05, .1, .2, .3, .4, .5, .6, .7, .8, .9, .95, 1.)
VIEWS = {"two_conditions": (1, 16), "three_conditions": (1, 16, 21)}


def fit_box(x, gains, features):
    cuts = [np.unique(np.quantile(x[:, j], QUANTILES)) for j in features]
    cells = np.array([np.searchsorted(cut, x[:, j], side="left") for j, cut in zip(features, cuts)]).T
    shape = tuple(len(c) for c in cuts)
    flat = np.ravel_multi_index(cells.T, shape)
    size = int(np.prod(shape))
    count = np.bincount(flat, minlength=size).reshape(shape)
    gain = np.bincount(flat, weights=gains, minlength=size).reshape(shape)
    for axis in range(len(features)):
        count, gain = count.cumsum(axis=axis), gain.cumsum(axis=axis)
    best, key = None, None
    for at in itertools.product(*[range(k) for k in shape]):
        if count[at] < 32 or gain[at] <= 1e-8:
            continue
        active = sum(i < len(cut) - 1 for i, cut in zip(at, cuts))
        candidate = (float(gain[at]), -active, int(count[at]), tuple(-i for i in at))
        if key is None or candidate > key:
            key = candidate
            best = {"features": list(features), "thresholds": [float(cut[i]) for i, cut in zip(at, cuts)],
                    "training_support": int(count[at]), "training_gain_PAR2_s": float(gain[at]),
                    "active_conditions": active, "action": "Fplus", "otherwise": "D"}
    return best


def match(x, rule):
    if rule is None:
        return np.zeros(len(x), bool)
    return np.all(x[:, rule["features"]] <= rule["thresholds"], axis=1)


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve the frozen Astra-template result")
        try:
            keys, _, costs, _, _, _ = load()
            split = read_csv(SPLITS)
            assert [r["instance_key"] for r in split] == keys
            x, valid = load_views(keys)[0]["linear42"]
            assert valid.all()
            source = DATA / "astra_linear42_rules_20261111/summary.json"
            import json
            assert json.loads(source.read_text())["status"] == "complete"
            old = read_csv(DATA / "mechanism_R12_20261111/predictions.csv")
            iso_rows = read_csv(DATA / "mechanism_R11_20261111/predictions.csv")
            assert [r["instance_key"] for r in old] == [r["instance_key"] for r in iso_rows] == keys
            iso = np.array([r["iso_group"] for r in split])
            coarse = np.array([r["coarse_group"] for r in split])
            fine = np.array([r["fine_group"] for r in split])
            inner = np.array([r["inner_validation"] == "True" for r in split])
            rows = [{"instance_key": k, "D_PAR2": float(costs[i, 0])} for i, k in enumerate(keys)]
            scores, fits = {}, []
            all_gain = costs[:, 0] - costs[:, 1]
            for mode, count in (("iso_diagnostic", 5), ("coarse", 4), ("fine", 5)):
                folds = np.array([int(r["diagnostic_iso_fold"]) for r in iso_rows]) if mode == "iso_diagnostic" else np.array([int(r[mode + "_fold"]) for r in split])
                groups = fine if mode == "fine" else coarse
                teacher = np.array([ACTIONS.index(r[mode + "_linear42_min3_action"]) for r in old])
                for name, features in VIEWS.items():
                    action, raw_action = np.zeros(len(keys), int), np.zeros(len(keys), int)
                    rules = []
                    for fold in range(count):
                        if time.monotonic() - start > 300:
                            raise TimeoutError("simple Astra rule comparison exceeded five minutes")
                        held = folds == fold
                        train, val = ~held & ~inner, ~held & inner
                        assert not (set(iso[held]) & set(iso[train | val]))
                        assert not (set(fine[train]) & set(fine[val]))
                        tick = time.process_time()
                        rule = fit_box(x[train], all_gain[train], features)
                        val_match = match(x[val], rule)
                        val_gain = float(all_gain[val][val_match].sum())
                        enabled = bool(rule is not None and val_match.sum() >= 8 and val_gain > 0)
                        selected = match(x[held], rule)
                        raw_action[held] = selected.astype(int)
                        action[held] = selected.astype(int) if enabled else 0
                        record = {"fold": fold, "rule": rule, "validation_support": int(val_match.sum()),
                                  "validation_gain_PAR2_s": val_gain, "enabled": enabled,
                                  "train_parents": int(train.sum()), "validation_parents": int(val.sum()),
                                  "held_parents": int(held.sum())}
                        rules.append(record)
                        fits.append({"mode": mode, "template": name, "fold": fold,
                                     "CPU_s": time.process_time() - tick})
                    selected = costs[np.arange(len(keys)), action]
                    raw_selected = costs[np.arange(len(keys)), raw_action]
                    trigger = action == 1
                    score = assess(costs[:, 0], selected, groups, 600)
                    score.update(rules=rules, triggers=int(trigger.sum()),
                                 teacher_Fplus_matches=int(np.sum(trigger & (teacher == 1))),
                                 teacher_Fplus_precision=float(np.mean(teacher[trigger] == 1)) if trigger.any() else None,
                                 teacher_Fplus_recall=float(np.sum(trigger & (teacher == 1)) / max(np.sum(teacher == 1), 1)),
                                 raw_no_validation_gate=assess(costs[:, 0], raw_selected, groups, 600))
                    if mode != "fine":
                        score["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], selected, coarse)
                    scores[mode + "_" + name] = score
                    for i, row in enumerate(rows):
                        row[mode + "_" + name + "_action"] = ACTIONS[action[i]]
                        row[mode + "_" + name + "_PAR2"] = float(selected[i])
                    write_csv(args.out / "predictions.csv", rows)
                    write(args.out / "summary.json", {"status": "running", "scores": scores, "fits": fits})
                    print(f"SCORED {mode}_{name}: gain={score['gain_pct']:+.6f}%, triggers={score['triggers']}, solved={score['solved']}", flush=True)
            passed = {}
            for name in VIEWS:
                ok = True
                for mode in ("coarse", "fine"):
                    s = scores[mode + "_" + name]
                    ci = s.get("exact_eight_block_95_pct", s["block_interval_95_pct"])
                    ok &= s["gain_pct"] >= 2 and ci[0] > 0
                passed[name] = bool(ok)
            write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "scores": scores,
                  "rule_fits": len(fits), "fits": fits, "screen_passed": passed,
                  "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
                  "source_sha256": sha(__file__), "astra_summary_sha256": sha(source),
                  "splits_sha256": sha(SPLITS), "new_solver_calls": 0, "short_search_calls": 0,
                  "cost_scope": "Feature/decision cost free optimistic prediction screen",
                  "scope": "Teacher-inspired feature templates, thresholds fit original training folds; repeatedly-developed2022, no independent confirmation"})
        except Exception as error:
            write(args.out / "failure.json", {"status": "failed", "error": repr(error),
                  "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start})
            raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    main(p.parse_args())
