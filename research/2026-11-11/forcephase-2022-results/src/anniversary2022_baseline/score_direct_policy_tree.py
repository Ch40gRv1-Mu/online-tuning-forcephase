"""Matched depth-three static trees: direct decision cost versus regression."""

import argparse
import fcntl
from pathlib import Path
import time

import numpy as np
from sklearn.tree import DecisionTreeRegressor
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import calibrate, choose, gains, measured_gains, SPLITS
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


class DirectCostTree:
    def fit(self, x, costs):
        self.nodes = []

        def build(ids, depth):
            here = len(self.nodes)
            local = costs[ids]
            total = local.sum(axis=0)
            node = {"parents": len(ids), "relative_gain": ((total[0] - total[1:]) / len(ids) / 1200).tolist()}
            self.nodes.append(node)
            if depth == 3 or len(ids) < 64:
                return here
            best, chosen = float(total.min()), None
            positions = np.unique(np.quantile(np.arange(1, len(ids)), np.arange(.05, 1, .05)).astype(int))
            positions = positions[(positions >= 32) & (positions <= len(ids) - 32)]
            for feature in range(x.shape[1]):
                order = np.argsort(x[ids, feature], kind="stable")
                values = x[ids[order], feature]
                split = positions[values[positions - 1] < values[positions]]
                prefix = local[order].cumsum(axis=0)
                scores = prefix[split - 1].min(axis=1) + (total - prefix[split - 1]).min(axis=1)
                if not len(scores):
                    continue
                at = int(scores.argmin())
                if scores[at] < best - 1e-8:
                    p = split[at]
                    best = float(scores[at])
                    chosen = feature, float((values[p - 1] + values[p]) / 2), order, p
            if chosen is not None:
                feature, threshold, order, p = chosen
                node.update(feature=feature, threshold=threshold,
                            left=build(ids[order[:p]], depth + 1),
                            right=build(ids[order[p:]], depth + 1))
            return here

        build(np.arange(len(x)), 0)
        return self

    def predict(self, x):
        output = np.zeros((len(x), 2))
        for i, row in enumerate(x):
            node = self.nodes[0]
            while "feature" in node:
                node = self.nodes[node["left"] if row[node["feature"]] <= node["threshold"] else node["right"]]
            output[i] = node["relative_gain"]
        return output


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve existing policy-tree result")
        keys, _, costs, _, _, _ = load()
        split = read_csv(SPLITS)
        assert [row["instance_key"] for row in split] == keys
        inner = np.array([row["inner_validation"] == "True" for row in split])
        fine = np.array([row["fine_group"] for row in split])
        coarse = np.array([row["coarse_group"] for row in split])
        iso = np.array([row["iso_group"] for row in split])
        views = {}
        sources = {}
        for round_id, name in (("R02", "ordered90"), ("R03", "quotient56"), ("R04", "community46")):
            source = DATA / f"mechanism_{round_id}_features_20261111/features.npz"
            with np.load(source) as data:
                assert data["keys"].tolist() == keys
                views[name] = (data[name], data["valid"], data["fee"])
                sources[name] = sha(source)
        rows = [{"instance_key": key, "D_PAR2": float(costs[i, 0])} for i, key in enumerate(keys)]
        scores, models = {}, []
        for mode, count in (("coarse", 4), ("fine", 5)):
            folds = np.array([int(row[mode + "_fold"]) for row in split])
            groups = coarse if mode == "coarse" else fine
            for view, (x, valid, acquisition) in views.items():
                for objective in ("direct_cost", "squared_error"):
                    name = f"{mode}_{view}_{objective}"
                    actions = np.zeros(len(keys), dtype=int)
                    fees = np.zeros(len(keys))
                    free_actions = np.zeros(len(keys), dtype=int)
                    free_fees = np.zeros(len(keys))
                    cuts = []
                    for fold in range(count):
                        if time.monotonic() - start > 600:
                            raise TimeoutError("static tree comparison exceeded ten minutes")
                        held = folds == fold
                        train, val = ~held & ~inner & valid, ~held & inner & valid
                        assert not (set(iso[held]) & set(iso[train | val]))
                        assert not (set(fine[train]) & set(fine[val]))
                        begin = time.process_time()
                        if objective == "direct_cost":
                            model = DirectCostTree().fit(x[train], costs[train])
                        else:
                            model = DecisionTreeRegressor(max_depth=3, min_samples_leaf=32, random_state=20261111 + fold)
                            model.fit(x[train], (costs[train, :1] - costs[train, 1:]) / 1200)
                        p = gains(model, x[val], "trees_relative")
                        cut = calibrate(p, costs[val], acquisition[val])
                        free_cut = calibrate(p, costs[val], np.zeros(val.sum()))
                        ids = np.flatnonzero(held & valid)
                        p, h = measured_gains(model, x[ids], "trees_relative")
                        actions[ids] = choose(p, cut)
                        free_actions[ids] = choose(p, free_cut)
                        if cut is not None:
                            fees[ids] = acquisition[ids] + h
                        if free_cut is not None:
                            free_fees[ids] = h
                        cuts.append({"fold": fold, "margin_PAR2_s": cut, "free_margin_PAR2_s": free_cut,
                                     "train": int(train.sum()), "validation": int(val.sum())})
                        record = {"variant": name, "fold": fold, "CPU_s": time.process_time() - begin}
                        if objective == "direct_cost":
                            record["nodes"] = model.nodes
                        else:
                            record["nodes"] = int(model.tree_.node_count)
                        models.append(record)
                    paid = timed_cost(costs[np.arange(len(keys)), actions], fees, 600)
                    free_paid = timed_cost(costs[np.arange(len(keys)), free_actions], free_fees, 600)
                    score = assess(costs[:, 0], paid, groups, 600)
                    score.update(actions={a: int((actions == i).sum()) for i, a in enumerate(ACTIONS)},
                                 cuts=cuts, free_features=assess(costs[:, 0], free_paid, groups, 600))
                    if mode == "coarse":
                        score["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], paid, groups)
                    scores[name] = score
                    for i, row in enumerate(rows):
                        row[name + "_action"] = ACTIONS[actions[i]]
                        row[name + "_PAR2"] = float(paid[i])
                        row[name + "_decision_CPU_s"] = float(fees[i])
                    write_csv(args.out / "predictions.csv", rows)
                    write(args.out / "summary.json", {"status": "running", "scores": scores, "fits": models})
                    print(f"SCORED {name}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}", flush=True)
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "scores": scores,
              "fits": models, "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
              "new_solver_calls": 0, "short_search_calls": 0, "new_feature_calls": 0,
              "feature_archive_sha256": sources, "splits_sha256": sha(SPLITS), "source_sha256": sha(__file__)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    with threadpool_limits(limits=1):
        main(parser.parse_args())
