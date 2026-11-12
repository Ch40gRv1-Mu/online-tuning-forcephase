# R38: optimized balanced cuts and boundary levels beyond single articulation

Owner current chat; no delegation. Healthy R35 remote seed replication remains
unchanged; no reading its partial preferences. Only existing retained4719
Anniversary2022 development labels/cached formulas. No SAT/short search/new data.

R37 found11 balanced single-vertex cyclic connectors and0.005428pp headroom,
so that representation stopped. Absence of a single articulation does not rule
out a small balanced multi-edge interface. This refines the regional-structure
hypothesis of R04, NOT a new algorithm family: R04 used6 diffusion rounds and
8 random channels without an explicit balanced-cut objective; R38 uses a fixed
multilevel cut objective and a genuine nested partition/boundary-level curve.
No claim of exact minimum cut, treewidth, circuit depth or superior partitioning
to R04 without a matched comparison. R10 boosting and existing gate-dependency
SCC depth are already tested and are not reintroduced as new features.

Same pure count qualification2325 (nmax<=100k/L<=200k), same base42+bit, all4719
in denominator. Original oracle10.8528%, eligible oracle4.8249pp,540 eligible
triple censored. No family, filenames/metadata, IDs/hashes, answers or terminal
statistics as inputs. Raw SHA/keys are association/integrity only.

Use pinned PyMetis2025.2.2/METIS, public wheel SHA and install cost preserved.
API reference https://documen.tician.de/pymetis/functionality.html . Build the
full unsigned variable-clause incidence graph after the prior literal duplicate/
tautology normalization. Active vertices only, keep clause multiset. Starting
with one group, bisect every group with>=8 vertices and>=1 internal edge for3
levels (max2/4/8 groups); otherwise carry the group unchanged. Each bisection
uses unweighted vertex balance, recursive=True, seed20261138,ncuts1,niter10,
ufactor30, no contiguity constraint. Heuristic results may depend on numbering;
do not claim graph-isomorphism invariance. Partition labels themselves are not
model inputs. Full-graph degrees/incidences, not solver observations, define all
statistics. Each refinement must preserve the previous grouping; cut incidence
mass cannot decrease. Verify each library-reported weighted cut by direct sum.

Six fields per level: cut incidence fraction, mean outgoing/volume over occupied
regions, boundary-variable fraction, boundary-clause fraction, node-mass entropy
normalized by log(max2^level), largest variable-region mass fraction. Two final
fields: degree-weighted first-boundary level (1/2/3, interior4, divided by4) and
fraction of incidences whose BOTH endpoints are final boundary vertices.20 total.
Roles are0 never boundary,1 first boundary at root,2 first at level2,3 first at
level3. Reuse exactly the prior48 signed_summary polarity/pressure/degree fields
by these4 roles, no new assignment/marginal interpretation.

Typed configuration null reuses R22's fixed seed20261122 and exact clause-width,
positive-count, literal-sign strata. It preserves each literal's clause-type
occurrences, clause polarity counts, degrees and first-order fields. Parallel
incidences are kept as positive integer edge weights; it is a multigraph input
control, not a new formula with reused truth labels. Recompute the same full
cut hierarchy/fields on it. Three views: topology63, signed111(primary),
rewired111. Same base43, model capacity/labels; no outer choice of best seed/grid.

Before any fit: actual versus typed-null68-extra-vector L2>1e-6 in>=50 parents
and their full-population permitted oracle>=0.5pp. Otherwise stop with null model
reward. Passing only establishes variation, not predictive value. If passes,
reuse R21 scorer/inner/group isolation, coarse4/fine5,256 trees/depth12/leaf4,
seed20261111+fold,27 fits. Primary must beatD by>=2% in both original regimes,
interval directions support, and beat topology/rewired paired controls before
conditional full-model export/query/deployment. Report all controls/negative
rewards. Existing repeated2022 is not independent confirmation.

Feature/query optimistic0 for prediction screen; retain actual common/real/null
physical CPU separately and count worker imports/prep where measured. Public
dependency install measured too. Four independent single-thread local processes,
per-input10CPU/30wall guard,15min collect+15min score, planning2CPUh, first full
coverage/scored answer target30min from23:29UTC preparation start. Small path,
weighted parallel-edge and disconnected fixtures are integrated semantic checks,
not independent audit/dryrun. Failures preserve partial receipts/cost and prevent
partial feature scoring; don't change live source or duplicate healthy workers.
Freeze source/protocol before formal execution. Outputs
mechanism_R38_features_20261111/mechanism_R38_20261111. Stop this hierarchy/seed/
balance version after complete feedback; no hidden cut/level/seed scanning.
