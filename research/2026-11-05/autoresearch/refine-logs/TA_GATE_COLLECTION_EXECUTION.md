# Static gate collection handoff

The collector completed only public-CNF static feature work. It did not run a SAT solver, read TA gate timings, evaluate a policy or consume the shared one-time scoring ledger. Root owns the sole subsequent gate evaluation on all 60 original parents.

Candidate SHA stayed `1d4a4374b444ff5da12291291fad4ec18893300033c5ec1bca4ef698dc8eb182`. Only public manifests, the static worker/C++ source and the candidate SHA literal were sent to the remote node. The candidate policy file containing development metrics remained local.

Collection began under implementation/protocol commit `e3e3d87` with the original 51-task manifest. Three resource-qualified workers produced 12 COMPLETE and one FAILED receipt, then stopped admission. Owner PID63052 became authoritatively absent. Recovery commit `aac1c0f` assigned only the 38 never-started tasks to a fresh phase, using four currently resource-qualified workers. It produced 36 COMPLETE and two FAILED receipts; owner PID63653 is also absent. The original 13 receipts, including the failed attempt, were not repeated or overwritten.

All three failures report the original `ValueError: download exceeds bounded preparation limits` and retain their CPU costs. Failed inputs are `fcc4c4522c54db2f1cee86fe0fff5f4a`, `5c47810953b22baa5f6f45585430fc77` and `f569dc48ad062a3110ff08a8d59e59ab`. No failed download was retried. The complete original eligible union is therefore 51 terminal receipts: 48 COMPLETE and three FAILED. Evaluation must retain the original 60 rows; the nine frozen resource exclusions plus these three feature failures use the frozen fixed-phase fallback.

Static profile remained 2CPU/8wall/3GiB, mandatory raw SHA/exact bytes/header checks, extractor source SHA `9f59eb26ca048cf8361f172ff2e757847958dc6eaae08bb1c25aba6d5b493b59`, and existing binary SHA `2f4cc472d4430b10785688b68ec0afb5d80e18eb7c90564754d08214c398f334`. Candidate/role binding and all receipt content/file SHA checks passed on delivery. No gate outcome or raw feature distribution was used to change the policy, limits or eligibility.

Accounted extraction/preparation CPU was 9.747090565 +17.590759811 =27.337850376 seconds. Remote delivery validation/archive controller used another 0.129188316 seconds. Active collection wall times, measured from recorded launch to completion-file mtime on the same node, were 174.437953711 and 169.149378777 seconds. Including the documented recovery/commit gap, first launch to final completion was 492.208467007 seconds. Public input transfer, rather than extraction CPU, dominated this stage.

Delivered locally under `work/ta_feature_discovery/static_gate51_v1/`:

- Original 13: `ta-static-gate51-v1/output/results/`.
- Continuation 38: `ta-static-gate-pending38-v2/output/results/`.
- Complete 51-row identity/cost index: `delivery_index51.json`, SHA `5e2c25013bf3fc9be4e1dfb1973012eef6fc94e54523668807b7aa181d4a9c55`.
- Single archive: `delivery_all51.tar.gz`, SHA `82c09ddd14ecbf8601352afbccfe387cc9fb70db4c25729bad22ad919073d6a9`.

Next action: root supplies the original 51-task manifest and both receipt directories to the frozen local `gate_evaluate.py evaluate-once`, which exclusively consumes the original project's shared `GATE_CONSUMED.json` opportunity before loading gate labels. No more collection is required and no collector owner remains running.
