#!/usr/bin/env python3
"""Write the M5 freeze file and held-out experiment specs.

  scripts/make_m5.py --candidate <config> --candidate-name "<label>" \
      [--schedule-family sw1k_X,sw10k_X,sw100k_X] [--reverse <config>] [--extra cfg ...]

Creates configs/m5_freeze.json and configs/experiments/m5_heldout.json
(test + t2026, seeds 0/1/2, T = 300 s, LRAT proofs).  Must be committed
before any held-out run; the commit hash is then recorded by m5_eval.py.
"""

import argparse
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--candidate-name", required=True)
    ap.add_argument("--schedule-family", default="")
    ap.add_argument("--reverse", default="")
    ap.add_argument("--online", default="pol_m3_D_K1000_time")
    ap.add_argument("--extra", nargs="*", default=[])
    a = ap.parse_args()
    statics = ["D", "Iminus", "Fminus", "Fplus"]
    family = [c for c in a.schedule_family.split(",") if c]
    configs = statics + [a.candidate] + [c for c in family if c != a.candidate]
    if a.reverse:
        configs.append(a.reverse)
    if a.online:
        configs.append(a.online)
    configs += [c for c in a.extra if c not in configs]
    exp = {"name": "m5_heldout",
           "description": "M5 frozen held-out evaluation: family-disjoint test split and temporal t2026 pool; "
                          "seeds 0 (original) and 1, 2 (cnfscramble perm); T = 300 s; LRAT proofs; telemetry",
           "instances": {"splits": ["test", "t2026"]}, "configs": configs, "seeds": [0, 1, 2],
           "timeout": 300, "memory_mb": 16000, "proof": "lrat"}
    with open(os.path.join(ROOT, "configs", "experiments", "m5_heldout.json"), "w") as f:
        json.dump(exp, f, indent=1)
    names = {"D": "D (stock)", "Iminus": "I− (validation-SBS)", "Fminus": "F− (forced negative)",
             "Fplus": "F+ (forced positive)"}
    nice = {"sw1k_Crev": "F−→D @1e3", "sw10k_Crev": "F−→D @1e4", "sw100k_Crev": "F−→D @1e5",
            "sw1k_C": "D→F− @1e3", "sw10k_C": "D→F− @1e4 (fixed schedule)", "sw100k_C": "D→F− @1e5",
            "sw10k_CrevIn": "F−→I− @1e4", "pol_m3_D_K1000_time": "M3 one-shot selector (time-only, @1e3)"}
    for c in configs:
        if c not in names and c != a.candidate:
            names[c] = nice.get(c, c)
    freeze = {
        "frozen_utc": None, "frozen_commit": None,
        "T": 300, "seeds": [0, 1, 2], "bootstrap": 10000,
        "primary": {"name": a.candidate_name, "config": a.candidate,
                    "hypothesis": "mean PAR2 on the family-disjoint test split is at least 5% lower than the "
                                  "validation-SBS (I−), with the 95% family-cluster bootstrap CI excluding 0, and "
                                  "mean solved count per seed not lower than I−"},
        "sbs_name": "I− (validation-SBS)",
        "config_names": names,
        "report_order": [a.candidate_name, "I− (validation-SBS)", "D (stock)", "F− (forced negative)",
                         "F+ (forced positive)", "static selector D/F−"] + [names[c] for c in configs
                                                                           if c not in statics + [a.candidate]]
                        + (["random switching time"] if family else []),
        "static_selector": {"name": "static selector D/F−", "model_file": "configs/policies/static_selector_DF.json"},
    }
    if family:
        freeze["random_switch_time"] = {"name": "random switching time", "branches": family, "salt": 20261018,
                                        "note": "per (instance, seed) uniform choice among the switching times of "
                                                "the candidate's schedule family; same switch budget (one switch)"}
    with open(os.path.join(ROOT, "configs", "m5_freeze.json"), "w") as f:
        json.dump(freeze, f, indent=1, ensure_ascii=False)
    print(json.dumps(exp, indent=1))
    print(json.dumps(freeze, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
