"""Score structural feature views and sparse guards against the fixed-D baseline."""

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .collect_signed_topology import FEATURE_SETS, eligible
from .positive_binary_replay import write_json
from .structural_clusters import ACTIONS, correlation, fit_stump, load, summarize_policy, write_csv
from .structural_views import features, predict


def metrics(costs, charged, actions, probes, groups):
    rows = np.arange(len(costs))
    paid = np.where(probes, charged[rows, actions], costs[rows, actions])
    return {
        "free": summarize_policy(costs, actions, groups),
        "with_extractor_cpu": summarize_policy(costs, actions, groups, chosen=paid),
        "probed_parents": int(probes.sum()),
    }


def replay(X, weights, k, costs, folds, inner, valid, net_costs):
    out = np.zeros(len(costs), dtype=int)
    gains = np.zeros(5)
    for fold in range(5):
        test = folds == fold
        train = ~test
        score = test & valid
        out[score] = predict(X, costs, train & valid, score, weights, k)
        if inner is None:
            continue
        for part in (0, 1):
            val = train & valid & (inner == part)
            pred = predict(X, costs, train & valid & ~val, val, weights, k)
            gains[fold] += (costs[val, 0] - net_costs[val, pred]).sum()
    return out, gains


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--collection", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--pressure-reference", type=Path)
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    collection = json.loads((args.collection / "collection.json").read_text())
    feature_set = collection.get("feature_set", "topology")
    feature_names = FEATURE_SETS[feature_set]
    keys, base, costs, _, groups, folds = load()
    dataset = eligible(feature_set)
    assert len(dataset) == collection["eligible"]
    receipts = {key: json.loads((args.collection / "records" / (key + ".json")).read_text()) for key in dataset}
    assert all(key == row["instance_key"] for key, row in receipts.items())
    successful = {key: row for key, row in receipts.items() if row["status"] == "ok"}
    assert len(successful) == collection["counts"]["ok"]
    valid = np.array([key in successful for key in keys])
    h = np.array([successful.get(key, {}).get("feature_cpu_s", 0) for key in keys])
    net_costs = np.where((costs < 1200) & (costs + h[:, None] <= 600), costs + h[:, None], 1200)
    assert np.array_equal(costs[~valid], net_costs[~valid])

    blocks = {
        name: np.array([[successful[key]["features"][feature] for feature in names] if key in successful
                        else [0] * len(names) for key in keys])
        for name, names in feature_names.items()
    }
    weights = {name: np.full(block.shape[1], 1 / np.sqrt(block.shape[1])) for name, block in blocks.items()}
    if feature_set == "pressure":
        if args.pressure_reference is None:
            ap.error("pressure scoring requires the earlier verified boundary receipts")
        with args.pressure_reference.open() as stream:
            reference = {row["instance_key"]: row["features"] for row in map(json.loads, stream)
                         if row["status"] == "ok"}
        names = feature_names["static_unit_pressure"]
        common = successful.keys() & reference.keys()
        assert common and np.allclose(
            [[successful[key]["features"][name] for name in names] for key in common],
            [[reference[key][name] for name in names] for key in common],
            rtol=1e-9, atol=1e-11,
        )
        new_views = ("static_unit_pressure",)
    else:
        blocks[feature_set + "_combined"] = np.column_stack(list(blocks.values()))
        weights[feature_set + "_combined"] = np.concatenate(list(weights.values()))
        new_views = tuple(blocks)
    controls, control_weights = features(keys, base)
    for name in ("size", "combined"):
        blocks[name] = controls[name]
        weights[name] = control_weights[name]
    inner = np.array([int(hashlib.sha256(("signed_topology_inner_v1:" + group).encode()).hexdigest(), 16) % 2
                      for group in groups])

    variants = []
    candidates = []
    predictions = {}
    for view, X in blocks.items():
        is_new = view in new_views
        for k in (12, 24):
            actions, gains = replay(X, weights[view], k, costs, folds, inner if is_new else None, valid, net_costs)
            name = f"{view}_{k}"
            if is_new:
                candidates.append((name, actions, gains))
            probes = valid if is_new or view == "raw_sign_width" else np.zeros(len(keys), dtype=bool)
            result = metrics(costs, net_costs, actions, probes, groups)
            variants.append({"name": name, **result})
            predictions[name] = actions
            print(f"{name}: {result['with_extractor_cpu']['par2_improvement_pct']:+.4f}%", flush=True)

    selected = np.zeros(len(keys), dtype=int)
    probed = np.zeros(len(keys), dtype=bool)
    choices = []
    for fold in range(5):
        name, actions, gains = max(candidates, key=lambda item: item[2][fold])
        test = folds == fold
        if gains[fold] > 0:
            selected[test] = actions[test]
            probed[test] = valid[test]
            choices.append({"fold": fold, "policy": name, "inner_net_gain_s": float(gains[fold])})
        else:
            choices.append({"fold": fold, "policy": "fixed_D"})

    stumps = []
    for view, names in feature_names.items():
        X = blocks[view]
        actions = np.zeros(len(keys), dtype=int)
        rules = []
        for fold in range(5):
            test = (folds == fold) & valid
            train = (folds != fold) & valid
            rule = fit_stump(X[train], costs[train])
            if rule:
                j, cut, left, action = rule
                actions[test] = np.where((X[test, j] <= cut) == left, action, 0)
                rules.append({"fold": fold, "feature": names[j], "threshold": cut,
                              "left": left, "action": ACTIONS[action]})
            else:
                rules.append({"fold": fold, "action": "D"})
        predictions[view + "_stump"] = actions
        stumps.append({"name": view, "rules": rules, **metrics(costs, net_costs, actions, valid, groups)})

    relative = np.log((costs[valid, :1] + 1) / (costs[valid, 1:] + 1))
    size = np.digitize(base[valid, 0], np.quantile(base[valid, 0], np.arange(1, 5) / 5))
    associations = []
    for view, names in feature_names.items():
        for j, name in enumerate(names):
            column = blocks[view][valid, j]
            associations.append({
                "view": view, "feature": name, "covered": int(valid.sum()),
                "Fplus_rho": correlation(column, relative[:, 0]),
                "Fminus_rho": correlation(column, relative[:, 1]),
                "Fplus_rho_within_size": correlation(column, relative[:, 0], size),
                "Fminus_rho_within_size": correlation(column, relative[:, 1], size),
            })
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "correlations.csv", associations)
    write_csv(args.out / "predictions.csv", [
        {"instance_key": key, "fold": int(folds[i]), "extracted": bool(valid[i]), "feature_cpu_s": h[i],
         "nested_probed": bool(probed[i]), "nested_action": ACTIONS[selected[i]],
         "D_par2": costs[i, 0], "nested_par2": (net_costs if probed[i] else costs)[i, selected[i]],
         **{name + "_action": ACTIONS[value[i]] for name, value in predictions.items()}}
        for i, key in enumerate(keys)
    ])
    with (args.out / "feature_receipts.jsonl").open("w") as stream:
        for key in sorted(receipts):
            stream.write(json.dumps(receipts[key], separators=(",", ":")) + "\n")
    result = {
        "parents": len(keys), "eligible": len(dataset), "features_measured": len(successful),
        "unavailable_uses_D": len(keys) - len(successful), "variants": variants, "stumps": stumps,
        "nested": metrics(costs, net_costs, selected, probed, groups), "nested_fold_choices": choices,
        "new_solver_calls": 0, "collection": collection, "sum_feature_cpu_s": float(h.sum()),
        "sum_identity_cpu_s": sum(r.get("identity_cpu_s", 0) for r in receipts.values()),
        "root_truncation_any_formulas": sum(r["truncated_root_share"] > 0 for r in successful.values()),
        "scoring_cpu_s": time.process_time() - cpu, "scoring_wall_s": time.monotonic() - start,
    }
    if feature_set == "pressure":
        prior = eligible()
        old = valid & np.array([key in prior for key in keys])
        new = valid & ~old
        transfer = []
        for view in ("static_unit_pressure", "raw_sign_width"):
            for k in (12, 24):
                actions = np.zeros(len(keys), dtype=int)
                actions[new] = predict(blocks[view], costs, old, new, weights[view], k)
                subgroup = metrics(costs[new], net_costs[new], actions[new], np.ones(new.sum(), dtype=bool),
                                   np.asarray(groups)[new])
                transfer.append({"view": view, "clusters": k, **subgroup})
        result["newly_covered_transfer"] = {"training": int(old.sum()), "evaluated": int(new.sum()),
                                            "prior_feature_values_checked": len(common) * len(names),
                                            "variants": transfer}
    write_json(args.out / "summary.json", result)
    print(json.dumps({key: result[key] for key in ("nested", "nested_fold_choices")}, indent=2))


if __name__ == "__main__":
    main()
