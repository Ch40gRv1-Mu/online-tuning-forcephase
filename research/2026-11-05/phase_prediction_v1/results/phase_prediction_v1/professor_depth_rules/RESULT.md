# Original-table tree/depth rule comparison

No new SAT solving; all144fit/48feedback parents retained. Original false/true labels have unverified solver semantics.

| Model | Fit-only fitted rule | Feedback supported accuracy | Weighted error rate | Accuracy delta vs fixed | 95% paired interval |
|---|---|---:|---:|---:|---|
| constant | {"action":"true"} | 12/19 | 0.5392568882827695 | 0.0 | [0.0, 0.0] |
| tree_geometry | {"feature":"d_core_vertex_fraction","threshold":0.999780866902625,"missing":"left","left":{"action":"false"},"right":{"action":"true"}} | 12/19 | 0.41641421561503467 | 0.0 | [-0.29411764705882354, 0.2941176470588235] |
| gate_depth_polarity | {"action":"true"} | 12/19 | 0.5392568882827695 | 0.0 | [0.0, 0.0] |
| matched_all43 | {"feature":"s_unit_fraction","threshold":0.000232018561485,"missing":"left","left":{"action":"true"},"right":{"action":"false"}} | 11/19 | 0.5575954073123722 | -0.05263157894736836 | [-0.3333333333333333, 0.21062030075187918] |

Coverage: {"fit": {"parents": 144, "label_counts": {"false": 18, "true": 35}, "reasons": {"neither_solved": 76, "near_tie": 12, "both_solved_clear": 46, "one_solved_supported_bound": 7, "one_solved_weak_bound": 3}, "valid_features": 144, "missing_geometry": 0, "missing_gate_depth": 68}, "feedback": {"parents": 48, "label_counts": {"false": 7, "true": 12}, "reasons": {"neither_solved": 24, "near_tie": 5, "both_solved_clear": 15, "one_solved_supported_bound": 4}, "valid_features": 48, "missing_geometry": 0, "missing_gate_depth": 23}}

Feature-stage cost: {"feature_stage_reported_process_and_waited_children_cpu_s": 140.480687974, "feature_stage_reported_wall_s": 178.23111001200596, "feature_child_cpu_s_sum": 98.471887, "local_analysis_cpu_s": 0.472316}

Original solver version, timeout semantics and phase-direction implementation are unknown.
Single-timeout labels/weights use recorded bounds, not exact runtime ratios.
Unknown labels remain in coverage; accuracy is conditional on supported preferences.
Recognized signed gates are a structural proxy, not a recovered original circuit.
Feedback is exploratory development; these scores are not deployment gains or confirmation.
