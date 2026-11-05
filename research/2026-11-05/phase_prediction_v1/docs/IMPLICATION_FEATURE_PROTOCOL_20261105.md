# New nonduplicated binary-implication features, fit-only first validation

User explicitly requested new features and continuous autoresearch validation,
without duplication of the other agent. Read its public proposals TA-R01/R02/R03
and source feature definitions only; did not read its gate outputs. That owner
covers original length/polarity/graph/motif statistics, clustering and shortD
glue/level probes. This owner covers literal binary-implication SCC/depth and
signed direction, which are absent from those feature lists. No cross-thread
message, delegation, shared-state overwrite or duplicate old extraction.

For each nondegenerate binary clause(a or b), build directed literal edges
not-a→b and not-b→a; skip same-variable binary clauses, deduplicate edges.
Extract exactly8 numeric fields: binary-variable coverage; fraction of literal
vertices in nontrivial SCCs; largestSCC fraction; longestSCC-condensation edge
path; positive-literal fraction among sourceSCC vertices; signed mean downstream
depth asymmetry(posmean-negmean)/(1+posmean+negmean); positive-source-literal
fraction among unique implication edges; exact flag. No answer/contradiction
flag, name, ID or family enters the vector. This is literal implication depth,
distinct from incidence peeling and recognized-gate depth. Unsigned depth alone
cannot encode phase direction; test directional quantities separately.

First formal block is the same144 qualifiedfit parents, original fixed order,
with exact plain-input SHA from depth192 receipts. Existing inputs are cached;
only run the new parser, never old static features or solver outcomes again.
10CPU seconds/1536MiB per parent,8 slots if node idle and memory≥14GiB, graph
cap4M directed edges. Capped/no-edge fields are null with explicit exact flag;
never pass partial graph depth as complete. Keep errors/costs/coverage. Stage
allocation1CPUh within total100h. Two necessary definition properties during
the build: permutation invariance and global-sign reversal (unsigned fields
unchanged, signed asymmetry changes sign and source polarity complements).
These are implementation checks, not an independent audit or solver dry run.

Reuse original-table labels as defined in DEPTH_FEATURES_DIRECT_PROTOCOL:
supported wall-time preference only; no known answer as predictor, no invented
timeout ratio or modernF± mapping. First validate only within fit, five fixed
folds assigned by original parent order modulo5, keeping equivalent groups
together. Fit-only thresholds1/8..7/8, depth1, min12 parents and4 supported
labels/leaf,1% weighted classification-error improvement to split. Exactly two
models: geometry4fields(coverage,SCC fractions,depth), direction3fields(source
polarity,signed depth,edge polarity). Compare fold-fit constant and same-capacity
old34-feature stump reusing existing caches. Retain all144 cases and label
coverage, out-of-fold accuracy/weighted loss and parent-bootstrap2000(seed
20261105) descriptive intervals; report CPU separately, never mix oldTA wall
and currentCPU into deployment gain. No feedback/gate/test results are read.

This first-stage feature characterization is not a new formalRICL reward or a
new held-out evaluation. The shared8-round quota includes both owners; do not
reset it or consume the other owner's reserved rounds. Any later policy update
requires an available recorded slot and frozen actual development evaluation.

First scored feature comparison target30–60minutes from this request, using
complete144fit. Continue only if >half have exact graph and >=20 supported
labels have usable candidate values, and at least one out-of-fold comparison
improves both accuracy and weighted error over its constant with nonzero action
coverage. Otherwise preserve a bounded negative and choose a genuinely new
feature mechanism; do not multiply graph variants or add solver matrices.
No positive claim without later allowed validation. All5355 final candidates
remain sealed; another branch's gate is not a fresh gate for this branch.
