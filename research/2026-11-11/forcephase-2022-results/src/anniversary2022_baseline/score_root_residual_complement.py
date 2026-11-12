"""Test the change in clause polarity after unit propagation on cached 2022 CNFs."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import math
from pathlib import Path
import resource
import subprocess
import time

import numpy as np

from .common import sha, write
from .score_scc_complement_stump import metrics, replay
from .score_scc_root_guard import FEATURE_TIMEOUT, MAX_BYTES, par2
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


FEATURES = {
    "root-polarity": ("conflict_contrast_change", "new_binary_polarity", "binary_fraction_change", "new_binary_share"),
    "conditioned-up": ("signed_propagation", "absolute_asymmetry", "signed_conflict_rate", "mean_propagation"),
    "signed-walk": ("signed_growth", "alignment_difference", "overlap_difference", "mean_growth"),
    "gate-dependency": ("depth_weighted_controlling_sign", "log_mean_depth", "acyclic_gate_share",
                        "alias_opposition_rate", "gate_density", "unweighted_controlling_sign",
                        "fanout_controlling_sign", "direct_opposition_rate"),
}


def extract(key, cache, case_cache, verifier, extractor, mode):
    path = cache / f"{key}.cnf.gz"
    row = {"instance_key": key, "feature_cpu_s": 0.0, "status": "missing_input"}
    if not path.exists() and key not in case_cache:
        return row
    try:
        if path.exists():
            with gzip.open(path, "rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
        else:
            raw = case_cache[key].read_bytes()
        if len(raw) > MAX_BYTES:
            raise ValueError("cached input exceeds extraction cap")
        check = subprocess.check_output([str(verifier)], input=raw, timeout=FEATURE_TIMEOUT).split()
        if check[0].decode() != key:
            raise ValueError("input identity mismatch")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        row.update(status="input_error", error=str(error))
        return row
    try:
        output = subprocess.check_output([str(extractor), "--" + mode], input=raw, timeout=FEATURE_TIMEOUT)
        cpu, conflict, assigned, *features = map(float, output.split())
        if mode == "conditioned-up":
            branches = features.pop(0)
            if branches not in (0, 1, 2, 3, 4):
                raise ValueError("invalid probe variable count")
            row["probe_variables"] = int(branches)
        if mode == "gate-dependency":
            for name in ("gate_count", "cross_alias_pairs"):
                value = features.pop(0)
                if not math.isfinite(value) or value < 0 or not value.is_integer():
                    raise ValueError("invalid gate coverage count")
                row[name] = int(value)
        if (not all(map(math.isfinite, [cpu, conflict, assigned, *features])) or conflict not in (0, 1)
                or len(features) != len(FEATURES[mode]) or cpu < 0 or cpu > FEATURE_TIMEOUT):
            raise ValueError("invalid feature receipt")
        row.update(status="root_conflict" if conflict else "ok", feature_cpu_s=cpu,
                   identity_cpu_s=float(check[4]), assigned=int(assigned), features=dict(zip(FEATURES[mode], features)))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        row.update(status="extraction_error", feature_cpu_s=FEATURE_TIMEOUT, error=str(error))
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--case-panel", type=Path, required=True)
    ap.add_argument("--verifier", type=Path, required=True)
    ap.add_argument("--extractor", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--mode", choices=FEATURES, default="root-polarity")
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    keys, _, costs, _, _, _ = load()
    source = {
        "SCC": DATA / "scc_root_up_20261110/predictions.csv",
        "fixed_rule": DATA / "scc_width_fixed_20261110/predictions.csv",
        "blocks": DATA / "scc_blocked_replay_20261110/predictions.csv",
        "width": DATA / "static_unit_pressure_20261110/feature_receipts.jsonl",
    }
    scc, fixed, block_rows = ({row["instance_key"]: row for row in read_csv(source[name])}
                              for name in ("SCC", "fixed_rule", "blocks"))
    with source["width"].open() as stream:
        width = {row["instance_key"]: row for row in map(json.loads, stream) if row["status"] == "ok"}
    if set(keys) != set(scc) or scc.keys() != fixed.keys() or scc.keys() != block_rows.keys() or not width.keys() <= scc.keys():
        raise ValueError("mismatched retained 2022 identity")
    base = np.array([ACTIONS.index(fixed[k]["frozen_action"]) for k in keys])
    h = np.array([(float(scc[k]["old_extractor_cpu_s"]) if scc[k]["original_scope"] == "True" else 0.0) +
                  (width[k]["feature_cpu_s"] if k in width and scc[k]["SCC_original_action"] == "D" else 0.0)
                  for k in keys])
    baseline = par2(costs, base, h)
    if not np.allclose(baseline, [float(fixed[k]["frozen_par2"]) for k in keys], rtol=0, atol=1e-10):
        raise ValueError("frozen two-threshold replay mismatch")
    eligible = np.array([base[i] == 0 and key in width for i, key in enumerate(keys)])
    if int(eligible.sum()) != 2330:
        raise ValueError("unexpected remaining cache coverage")
    prior = {r["instance_key"]: args.case_panel / "cnf" / (r["case"] + ".cnf")
             for r in read_csv(args.case_panel / "association_only.csv")}
    work_keys = [key for key, use in zip(keys, eligible) if use]
    args.out.mkdir(parents=True, exist_ok=False)
    acquired = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as workers, (args.out / "feature_receipts.jsonl").open("w") as out:
        records = {}
        def worker(key):
            return extract(key, args.cache, prior, args.verifier.resolve(), args.extractor.resolve(), args.mode)

        for receipt in workers.map(worker, work_keys):
            records[receipt["instance_key"]] = receipt
            out.write(json.dumps(receipt, sort_keys=True) + "\n")
            if len(records) % 400 == 0:
                out.flush()
                print(f"Processed {len(records)}/{len(work_keys)} cached CNFs", flush=True)

    acquisition_wall = time.monotonic() - acquired
    valid = np.array([records.get(k, {}).get("status") == "ok" for k in keys])
    allowed = valid.copy()
    if args.mode == "gate-dependency":
        allowed &= np.array([records.get(k, {}).get("gate_count", 0) > 0 for k in keys])
    extra = np.array([records.get(k, {}).get("feature_cpu_s", 0.0) for k in keys])
    names = FEATURES[args.mode]
    features = np.array([[records[k]["features"][name] if allowed[i] else 0.0 for name in names]
                         for i, k in enumerate(keys)])
    fine = np.array([scc[k]["shape_block"] for k in keys])
    coarse = np.array([fixed[k]["coarse_cluster_group"] for k in keys])
    dominant = np.array([block_rows[k]["root_unit_block"] in ("units:49", "units:56") for k in keys])
    _, support = np.unique(fine, return_inverse=True)
    predictions = [{"instance_key": key, "base_PAR2": float(baseline[i])} for i, key in enumerate(keys)]
    results = {}
    splits = (("fine_shape", fine), ("coarse_cluster", coarse))
    comparisons = [(name, blocks, features, names) for name, blocks in splits]
    if args.mode == "gate-dependency":
        comparisons = [(view + "_" + name, blocks, features[:, sl], names[sl])
                       for name, blocks in splits
                       for view, sl in (("depth_and_alias", slice(0, 4)), ("non_depth", slice(4, 8)))]
    for name, blocks, view_features, view_names in comparisons:
        _, block_id = np.unique(blocks, return_inverse=True)
        action, charged, rules = replay(view_features, eligible, costs, base, h, extra, block_id, False,
                                        support_index=support, allow_switch=allowed)
        net = par2(costs, action, charged)
        result = metrics(costs, baseline, net, action, blocks, dominant)
        result["against_frozen_two_threshold"] = result.pop("against_SCC")
        result["additional_switches"] = int((action != base).sum())
        result["charged_extra_CPU_s"] = float((charged - h).sum())
        result["rules"] = {blocks[block_id == i][0]:
                           [view_names[r[0]], r[1], "<=" if r[2] else ">", ACTIONS[r[3]]] if r else None
                           for i, r in rules.items()}
        results[name] = result
        for i, row in enumerate(predictions):
            row[name + "_action"] = ACTIONS[action[i]]
            row[name + "_par2"] = float(net[i])
        print(name, result["against_frozen_two_threshold"]["par2_improvement_pct"],
              result["against_frozen_two_threshold"]["paired_group_bootstrap_95_pct"],
              result["against_D"]["solved"], result["additional_switches"], flush=True)
    write_csv(args.out / "predictions.csv", predictions)
    final_child = resource.getrusage(resource.RUSAGE_CHILDREN)
    write(args.out / "summary.json", {
        "parents": len(keys), "eligible": len(records), "valid_features": int(valid.sum()),
        "switch_feature_support": int(allowed.sum()), "mode": args.mode,
        "root_conflicts": sum(r["status"] == "root_conflict" for r in records.values()),
        "new_solver_calls": 0, "acquisition_wall_s": acquisition_wall,
        "elapsed_wall_s": time.monotonic() - start, "analysis_and_collection_CPU_s": time.process_time() - cpu,
        "child_CPU_s": final_child.ru_utime + final_child.ru_stime - child.ru_utime - child.ru_stime,
        "extractor_CPU_s": float(extra.sum()), "extractor_sha256": sha(args.extractor),
        "verifier_sha256": sha(args.verifier), "input_sha256": {name: sha(path) for name, path in source.items()},
        "results": results,
    })


if __name__ == "__main__":
    main()
