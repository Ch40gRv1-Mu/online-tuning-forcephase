# TA dynamic prefix execution receipts

Executed 2026-11-05 UTC under implementation commit `d086138`, pilot manifest `f2e8157`, and remaining-task manifest `a8f889a`. Root remained central experiment owner; one delegated dynamic executor launched each disjoint phase once. No full false/true comparison, TA rescoring, independent audit or dry run was performed by this executor.

## Completed observations

|Population|Planned|Complete six-feature vectors|Budget before checkpoint|Early terminal, answer not adopted|
|---|---:|---:|---:|---:|
|Pilot combined|40|20|12|8|
|Remaining combined|152|101|44|7|
|All eligible fit|144|93|41|10|
|All eligible feedback|48|28|15|5|
|All eligible combined|192|121|56|15|

The fixed pilot's 20/40 usable vectors met the frozen coverage threshold exactly. Root then released only the remaining 152 tasks; no pilot task was repeated. All 192 tasks have terminal receipts, with no FAILED or RESOURCE_UNAVAILABLE records. Complete vectors passed the frozen first-checkpoint, native-D, absolute process CPU ≤2, learned-event count ≥20 and six-finite-value checks. Early answers remain unverified and unadopted; existing TA timings alone supply performance labels.

The eligible population has 144 fit and 48 feedback instances. The intended downstream comparison still retains all 180 fit and 60 feedback rows, including the 48 resource-ineligible rows and every missing observation, with static fallback. The dynamic executor did not score either population or choose a rule.

## Identity and execution

Observer source SHA: `d92d0ef0638397fb6eddaad64a5b2d8619e8cf5d805d9f56dd469005bef16015`.

Separate solver binary SHA: `9e4c5104b3e1234e15d0551a86abaf8625147179c69511451bd9ebc9b49bc4eb`.

CPU helper SHA: `7b0e95364847b13f54268cd2b2f5e383839169ca0a613460b05e202c11d8d3e2`.

Pilot ran two workers on CPUs 6–7 alongside the three authorized static workers. Remaining tasks started only after root reported the static owner authoritative terminal; current RAM/disk qualification allowed eight workers on CPUs 0–7. Both dynamic owners are now absent and both completion records report `complete=true`.

A startup-only node-name mismatch was caught before creating a remaining-phase child process. The frozen manifest's actual `node_id` was retained, the prelaunch failure record was preserved, and the one remaining-phase owner was then launched. No SAT task had started during that rejected prelaunch check. Original sources, binaries, static owners and prior receipts were preserved.

## Accounted costs

|Component|CPU seconds|
|---|---:|
|Pilot child processes|34.762587|
|Pilot preparation|1.871205586|
|Pilot controller|0.939095336|
|Pilot total|37.572887922|
|Remaining total|156.685302135|
|All probe child processes|181.298064|
|All probe preparation|9.168241644|
|All probe controller|3.791884413|
|All probe total|194.258190057|
|Observer build including controller|2.681306403|
|Remote delivery validation/archive controller|0.297305150|

These are server CPU costs, not additions to the old TA wall-time measurements. Central allocation was 600 pilot +2800 remaining CPU seconds, plus engineering, within the shared 3600-second dynamic ceiling. Root retains the authoritative project-wide ledger and incidental local/transport engineering accounting.

## Delivered evidence

- Pilot: `work/ta_feature_discovery/dynamic_pilot40_v1/output/` with 40 immutable receipts and 40 raw traces.
- Remaining: `work/ta_feature_discovery/dynamic_remaining152_v1/output/` with 152 immutable receipts and 152 raw traces.
- Build receipt: `work/ta_feature_discovery/dynamic_observer/build_receipt.json`.
- Full 192-row index: `work/ta_feature_discovery/dynamic_remaining152_v1/delivery_index192.json`, SHA `77d0c08d1bf040b03af7a29dc3b853879c70e76c32d2496b7cdb7711ab106edf`.
- Remaining transfer archive SHA: `bf0a241673023cc1239f6f100debd3206bc92ee3d68da6f3f59cf6926a17c583`.

The delivery checked each receipt's canonical content SHA, owner-manifest task/input/role/method association and raw-trace SHA. The local transfer was checked against the same 192-row index. No missing or failed receipt was replaced by an invented vector.

Next action belongs to root: bind the combined 192-task manifest, merge these observations into the original development population, and compare frozen-capacity static versus static-plus-dynamic candidates. No more solver jobs are currently required by this executor.
