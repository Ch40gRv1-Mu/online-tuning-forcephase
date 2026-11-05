# Direct tree/depth feature experiment

User priority: find useful structural features quickly, reduce nonproductive
checks, use the existing professor table. No new SAT solving in this experiment.

Input is all previously resource-qualified development_fit144 and
development_feedback48, from the original frozen order and size/variable limits,
not selected by winner. Gate and all5355 final candidates excluded. Public CNFs
only are fetched; the professor table remains local. Missing/failed feature
extractions remain in coverage and expense. Existing T60 results are retained.

Add exactly nine numeric measurements to the existing34: synchronous
incidence-graph leaf-peeling rounds,2-core vertex/edge fractions, geometry-exact
flag; longest path in the SCC condensation of recognized signed AND/OR gate
dependencies, cyclic-variable fraction, gate-variable coverage, positive-output
literal fraction, gate-depth-exact flag. The recognized gate graph is a proxy,
not a uniquely reconstructed original circuit. Geometry limit10M vertices/20M
incidences, gate-edge limit4M; capped measurements become null with exact=0.
No instance/family/name/known-answer/terminal solver features.

Extract at most30CPU seconds and1536MiB per parent, eight slots; failed inputs
may get one3GiB retry with four slots. No solver runs or changed input formula.
Record input/extractor SHA and measured CPU. Feature-stage stop envelope6CPUh;
entire study remains100CPUh. Reuse existing public inputs and valid observations.

Original-table preference labels: both solved, choose faster only if time gap
>=max(0.02s,10% of faster); single solved versus TIMEOUT is a supported preference
only if observed timeout wall >=2*solved wall. Preserve double timeouts and near
ties as unlabelled coverage. Original time-limit/version are not known; report
these as recorded/bounded original-label preferences, not a new PAR2 or verified
runtime guarantee. No SAT/UNSAT answer becomes a predictor.

Two predeclared diagnostic proposals: depth1 tree-geometry stump, and depth1
gate-depth/polarity stump. Thresholds fit-only1/8..7/8 quantiles, at least12 fit
parents and4 labelled fit parents per leaf; require1% reduction in fit weighted
error to split. Label weight min(10,abs(log2(observed wall ratio))) with a floor
of0.1 for both-solved clear labels; single-timeout weight is its recorded lower
bound. Compare fit-selected fixed false/true and a matched stump over all43
numeric fields. Score feedback once, all48 coverage retained, report accuracy,
weighted errors, paired parent bootstrap2000/seed20261105 and extraction CPU.
This is bounded exploratory original-label analysis, not a D/F policy reward or
independent test, and cannot establish modern-solver net benefit.

After this direct result, the same new features may support actual RICL round3
and round4 proposals on the already complete T60 cost matrix. Version feature
allowlists/cost lineage, preserve round2 unchanged, and charge the new combined
extractor. No new solver matrix, gate access or test feedback is authorized here.
