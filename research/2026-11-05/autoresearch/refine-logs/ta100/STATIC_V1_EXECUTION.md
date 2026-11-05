# First two TA100 static collection groups

Protocol `d2ef38f`; compiled source snapshot `1c49bf5`; exact public collection manifests and B02/B03 declarations committed as `d823f68`. No TA labels, gate/test data or full SAT runtime labels were collected by this executor.

The isolated `ROOT/ta100/build_v1` archive contained only the shared parser, core/graph sources, all implementation headers, new worker and the original worker copied as `base_static_worker.py`. Two sequential single-compiler builds consumed 7.200083 child CPU seconds plus 0.076523861 controller CPU seconds; wall 7.31545 seconds. No original binary or other owner's source was replaced.

One core owner used two workers, one graph owner used one worker: three shared3GiB static slots total, 5CPU/12wall per group-instance, 1200CPU allocation per group. Both processed the exact192 eligible public fit/feedback inputs, keeping rawSHA/exact-byte/header identities. The original240 downstream population remains unchanged. Both owners have authoritative complete receipts and are absent; no recovery or instance rerun was needed.

|Group|Terminal|Complete group output|Parser resource cap|CPU/wall timeout|Physical CPU seconds|Collection wall seconds|
|---|---:|---:|---:|---:|---:|---:|
|core10|192|178|14|0|135.173515231|70.679219961|
|graph10|192|170|14|8|207.986390997|212.945321560|

The parser's frozen2M-clause/20M-literal internal limits return `RESOURCE_LIMIT` null vectors and continue; such rows are not deleted or reclassified as valid zeros. Individual block denominators/work caps also produce explicit nulls. Core-field availability ranges76–178/192; graph-field availability79–170/192. These counts are not phase-prediction performance.

Delivery validated all384 receipt canonical/file SHA, original public task/input/role associations and complete method/profile fields. A single archive is `work/ta100/collection_delivery_v1/collection_delivery_v1.tar.gz`, SHA `5c227054cd5bbd42b468e980e734e8a241c3ae1a1299f8eafbdcda6f432a2bcb`. Its384-record index SHA is `359545dfb45c1d3aef6a7ccd2fc937109be182c6e50d54b13db15e316319bdf4`. Remote delivery validation/archive CPU was0.421174362 seconds. Total measured collection+build+archive CPU is350.857687451 seconds; incidental development/transport costs remain in root's separate ledger.

After merge code `56f7ea2` was committed, the same immutable receipts produced `outputs/ta100/features_core10_v1.json` and `outputs/ta100/features_graph10_v1.json`, each with a separate full receipt index. Table `bindings.source_sha256` is the C++ extractor source SHA expected by the frozen B02/B03 source guard; parser, dependency headers, worker, complete method, manifest and table-builder SHA are bound separately. Every eligible identity remains present with a numeric value or null. The merger did not read TA labels or fit a policy.

Next actions belong to root: score B02/B03 once on the complete240 development rows, record exploratory results and workflow revisions, and authorize later source/manifest versions separately. Covered-literal/ITE extras are new independent source work; they do not modify or rescue either frozen first collection group.
