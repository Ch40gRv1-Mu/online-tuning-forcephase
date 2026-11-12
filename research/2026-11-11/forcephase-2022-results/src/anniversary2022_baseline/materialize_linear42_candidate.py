"""Freeze the positive R12 candidate and replay measured acquisition fees."""

import argparse
import fcntl
import json
from pathlib import Path
import resource
import time

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha, write
from .linear42_candidate import predict_vector, route_cnf
from .predict_relative_cost import calibrate, gains, SPLITS
from .score_static_learnability import fit
from .score_static_seed_agreement import load_views, SEEDS
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, BASE, DATA, ROOT, load, read_csv, write_csv


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    usage0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    children0 = usage0.ru_utime + usage0.ru_stime
    args.out.mkdir(parents=True, exist_ok=False)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            keys, _, costs, _, _, _ = load()
            split = read_csv(SPLITS)
            historical = DATA / "mechanism_R12_20261111"
            old = json.loads((historical / "summary.json").read_text())
            prediction = read_csv(historical / "predictions.csv")
            assert old["status"] == "complete" and old["parents"] == 4719
            assert [r["instance_key"] for r in split] == [r["instance_key"] for r in prediction] == keys
            views, _ = load_views(keys)
            x, valid = views["linear42"]
            assert valid.all() and x.shape == (4719, 42)
            inner = np.array([r["inner_validation"] == "True" for r in split])
            models, fits = [], []
            for seed in SEEDS:
                tick = time.process_time()
                models.append(fit("expressive", x[~inner], costs[~inner], seed))
                fits.append({"training_seed": seed, "CPU_s": time.process_time() - tick})
            size = []
            for seed, model in zip(SEEDS, models):
                nodes = sum(t.tree_.node_count for t in model.estimators_)
                leaves = sum(t.tree_.n_leaves for t in model.estimators_)
                internal = nodes - leaves
                size.append({"training_seed": seed, "trees": len(model.estimators_),
                             "nodes": int(nodes), "leaves": int(leaves), "internal_splits": int(internal),
                             "predictive_float_scalars": int(internal + 2 * leaves),
                             "feature_index_choices": int(internal)})
            totals = {key: sum(r[key] for r in size) for key in
                      ("trees", "nodes", "leaves", "internal_splits", "predictive_float_scalars", "feature_index_choices")}
            write(args.out / "model_size.json", {"models": size, "total": totals,
                  "definition": "Each internal split uses a feature index and numeric threshold; each leaf stores2 predicted gains. Float scalar count=split thresholds+2*leaf_count, excludes metadata and redundant stored internal values. Not directly a neural weight count."})
            val_gain = np.min([gains(m, x[inner], "trees_relative") for m in models], axis=0)
            cut = calibrate(val_gain, costs[inner], np.zeros(inner.sum()))
            payload = {"models": models, "view": "linear42", "aggregation": "per_action_min3",
                       "cut": cut, "seeds": SEEDS, "native_binary_sha256": sha(args.native_binary),
                       "vector_source_sha256": sha(ROOT / "src/anniversary2022_baseline/gbd_native_vectors.py")}
            model_path = args.out / "model.joblib"
            joblib.dump(payload, model_path, compress=3)
            loaded = joblib.load(model_path)
            # Serialized behavior must agree with the trained predictor.
            assert np.allclose(predict_vector(loaded, x[np.flatnonzero(inner)[0]])[1], val_gain[0])
            write(args.out / "policy.json", {"schema": "forcephase.linear42.min3.v1",
                  "model_file": "model.joblib", "model_sha256": sha(model_path), "features": "linear42",
                  "model_size": totals,
                  "feature_count": 42, "seeds": SEEDS, "trees_per_model": 256, "max_depth": 12,
                  "min_samples_leaf": 4, "margin_PAR2_s": cut,
                  "decision": "For eachF use minimum predicted D-F gain across3 models; switch to bestF only above margin, elseD",
                  "feature_failure": "D, with failed acquisition CPU still charged",
                  "native_binary_sha256": payload["native_binary_sha256"],
                  "training_parents": int((~inner).sum()), "inner_validation_parents": int(inner.sum()),
                  "dataset_parents": 4719, "GBD_sha256": sha(BASE), "splits_sha256": sha(SPLITS),
                  "historical_evidence_sha256": sha(historical / "summary.json"),
                  "scope": "Executable candidate, not an independently confirmed final policy"})

            native_path = DATA / "native_GBD_route_v3_20261111/feature_receipts.jsonl"
            native = {r["instance_key"]: r for r in map(json.loads, native_path.read_text().splitlines()) if r["status"] == "ok"}
            assert len(native) == 2843
            measured = np.array([k in native for k in keys])
            acquisition = np.array([native[k]["feature_CPU_s"] if k in native else 0. for k in keys])
            coarse = np.array([r["coarse_group"] for r in split])
            fine = np.array([r["fine_group"] for r in split])
            iso_rows = read_csv(DATA / "mechanism_R11_20261111/predictions.csv")
            assert [r["instance_key"] for r in iso_rows] == keys
            results, rows = {}, [{"instance_key": k, "measured_feature_CPU_s": float(acquisition[i]),
                                 "feature_fee_measured": bool(measured[i])} for i, k in enumerate(keys)]
            for mode in ("iso_diagnostic", "coarse", "fine"):
                name = mode + "_linear42_min3"
                folds = np.array([int(r["diagnostic_iso_fold"]) for r in iso_rows]) if mode == "iso_diagnostic" else np.array([int(r[mode + "_fold"]) for r in split])
                enabled = np.array([old["scores"][name]["cuts"][fold]["margin_PAR2_s"] is not None for fold in folds])
                action = np.array([ACTIONS.index(r[name + "_action"]) for r in prediction])
                h = np.array([float(r[name + "_decision_CPU_s"]) for r in prediction])
                selected = costs[np.arange(len(keys)), action]
                original = timed_cost(selected, h, 600)
                assert np.allclose(original, [float(r[name + "_PAR2"]) for r in prediction], atol=1e-8)
                paid = timed_cost(selected, h + acquisition * enabled, 600)
                groups = fine if mode == "fine" else coarse
                result = assess(costs[:, 0], paid, groups, 600)
                result.update(original_gain_pct=old["scores"][name]["gain_pct"],
                              measured_fee_parents=int((measured & enabled).sum()),
                              unknown_fee_parents=int((~measured & enabled).sum()),
                              additional_measured_feature_CPU_s=float((acquisition * enabled).sum()),
                              actions={a: int((action == j).sum()) for j, a in enumerate(ACTIONS)})
                if mode != "fine":
                    result["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], paid, coarse)
                result["unknown_fee_sensitivity"] = []
                for extra in (0., .1, .5, 1., 2., 5., 8.):
                    hypothetical = timed_cost(selected, h + acquisition * enabled + extra * (~measured & enabled), 600)
                    result["unknown_fee_sensitivity"].append({"hypothetical_CPU_s_per_unmeasured": extra,
                          "gain_pct": float(100 * (costs[:, 0] - hypothetical).sum() / costs[:, 0].sum()),
                          "solved": int((hypothetical < 1200).sum())})
                results[mode] = result
                for i, row in enumerate(rows):
                    row[mode + "_action"] = ACTIONS[action[i]]
                    row[mode + "_partial_cost_PAR2"] = float(paid[i])
                print(f"COSTED {mode}: gain={result['gain_pct']:+.6f}%, solved={result['solved']}", flush=True)
            write_csv(args.out / "historical_oof_partial_cost.csv", rows)
            write(args.out / "cost_replay.json", {"status": "complete", "scores": results,
                  "measured_acquisition_parents": 2843, "unmeasured_acquisition_parents": 1876,
                  "scope": "Original4719 OOF actions, measured fees only; unknown fees optimistic0. LocalMac features plus cluster solver CPU, not same-machine end-to-end.",
                  "sensitivity_scope": "Hypothetical successful extraction costs, not observations or modeled resource failures",
                  "native_receipts_sha256": sha(native_path)})

            panel = ROOT / "work/astra_structure_panel_20261110"
            fallback = {r["instance_key"]: panel / "cnf" / (r["case"] + ".cnf") for r in read_csv(panel / "association_only.csv")}
            index = {k: i for i, k in enumerate(keys)}
            checks = []
            with threadpool_limits(limits=1):
                for key in sorted(native)[:8]:
                    cnf = ROOT / "work/signed_boundary_20261110/cnf_cache" / (key + ".cnf.gz")
                    if not cnf.exists():
                        cnf = fallback[key]
                    receipt, vector = route_cnf(loaded, args.native_binary, cnf)
                    assert receipt["status"] == "ok" and np.array_equal(vector.astype(np.float32), x[index[key]].astype(np.float32))
                    assert receipt["action"] == ACTIONS[predict_vector(loaded, x[index[key]])[0]]
                    receipt["instance_key_association_only"] = key
                    checks.append(receipt)
            write(args.out / "input_path_receipts.json", {"status": "complete", "cases": checks,
                  "selection": "First8 sorted previously verified public-input keys, no outcome selection",
                  "scope": "Real CNF input/inference fidelity and fees; not policy performance confirmation"})
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            native_cpu = usage.ru_utime + usage.ru_stime - children0
            write(args.out / "summary.json", {"status": "complete", "full_development_model_fits": 3,
                  "outer_fits": 0, "fits": fits, "training_parents": int((~inner).sum()),
                  "inner_validation_parents": int(inner.sum()), "margin_PAR2_s": cut,
                  "integration_cases": len(checks), "model_sha256": sha(model_path),
                  "model_bytes": model_path.stat().st_size, "model_size": totals,
                  "physical_parent_CPU_s": time.process_time() - cpu, "physical_native_CPU_s": native_cpu,
                  "wall_s": time.monotonic() - start, "new_solver_calls": 0, "short_search_calls": 0,
                  "source_sha256": sha(__file__), "scope": "Candidate materialization and partial-fee replay, no new confirmation or test labels"})
        except Exception as error:
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            write(args.out / "failure.json", {"status": "failed", "error": repr(error),
                  "physical_parent_CPU_s": time.process_time() - cpu,
                  "physical_native_CPU_s": usage.ru_utime + usage.ru_stime - children0,
                  "wall_s": time.monotonic() - start})
            raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--native-binary", type=Path, required=True)
    main(p.parse_args())
