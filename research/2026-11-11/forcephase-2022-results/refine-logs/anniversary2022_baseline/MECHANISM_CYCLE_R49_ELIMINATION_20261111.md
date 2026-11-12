# R49 frozen full-incidence elimination-fill comparison

Current-chat owner, no delegation. Previous goal turn was progress: R48 closed
14jobs/56rules/28 finite-grid training-optimum certificates, no successful
readable2% policy. Root goal still active. This protocol/source supersedes the
R49 draft before any extraction or new score. First complete comparison target
30–60min including preparation; no independent audit/dryrun.

Question: does full-graph fill/constraint coupling, coupled to variable polarity,
help choose D/Fplus/Fminus? D uses saved/target per-variable phases, rephasing
and changing search state; graph fill is only a static proxy of coupling, not
a simulation of that state. R48 training optimization failure does not prove
static information absent. Stop prior feature/threshold/seed tuning.

Dedup: old TA100 graph_elimination_width is min-fill on <=96 variable induced
primal sample. This is bounded min-degree elimination of the full normalized
variable-clause incidence graph, no induced local sample or primal clique
projection. Elimination itself is an established reused operation, not a new
algorithm. R33 CNF resolution/BVE, R37 block-cut, R38 METIS partitions, R46
forest parity and R47 Horn covers do not measure this graph fill process.

Data: retained4719 Anniversary2022 all repeatedly exposed development. Original
complete14157 seed0 T600 three-action costs reused, not rerun: D3385 solved,
1172 triple censored,2279 clear labels, meanD PAR2=392.54265364738285s,
free three-action oracle=10.852813%. No new benchmark, known-answer input,
family/identity routing, short searches or R35 partial feedback. Existing
count-only2325 qualification from R38 reused, full4719 score denominator and
native8+16 acquisition fees/25 remaining failed paidD preserved. Input SHA is
association/integrity only, not a feature. No winner-based replacements.

Normalize duplicate literals/tautologies with existing routine, retain all
active variables and nonempty clauses as a simple bipartite graph. Empty/removed
counts are not SAT labels. On each step choose min current degree, ties by
fixed splitmix64(vertex_index+20261149) priority. Remove vertex after making its
neighbors a clique. No SAT variable assignments or CNF resolvents produced.

Hard deterministic limits per profile: stop before next degree>128 or next
step's pair checks exceed500000, or new cumulative fill edges exceed
min(1000000,4*originalL+1024). A fill-limit check may inspect pairs without
committing the step; work still recorded. Complete-order max degree is an
upper bound for this incidence graph's treewidth, not exact treewidth. A capped
prefix max degree is NOT a certified graph bound or full elimination depth.
No depth claim from incomplete orders. Save completion/reason/coverage fields.

New44 coordinates, exact schema (indices relative to new block):
0 nodes removed fraction;1 variable removed fraction;2 clause removed fraction;
3 log1p prefix maximum degree;4 log1p eliminated degree mean;5 log1p eliminated
degree RMS;6 log1p fill/originalL;7 log1p inspected pairs/originalL;8 residual
edges/originalL;9 log1p residual minimum degree;10 complete;11 degree stop;
12 work stop;13 fill stop;14–17 eliminated node-degree shares[<=1,2–4,5–16,>=17];
18/19 original variable/clause incidence mass removed fraction.
20–43 variable elimination-degree bins[<=1,2,3–4,5–8,9–16,17–32,33–64,>=65],
each containing count/nv, signed-bias sum/nv, absolute-bias sum/nv. Bias is original
(positive_degree-negative_degree)/degree. These signs retain original formula
orientation, not synthetic runtime labels. No new regression target supplied.

Matched null refines the earlier configuration null to avoid simple-degree
artifacts: perform exactly2L attempted double-edge swaps, mt19937_64 seed20261149,
choose first edge uniformly and second within identical(width,positive_count,
literal_sign) group. Reject same variable/clause or swaps creating any repeated
variable-clause adjacency. Thus preserve exact simple degrees, each literal's
clause-type counts and each clause's sign counts; no parallel edges. This is a
bounded partially mixed null, NOT a claim of uniform random-graph sampling.
Report attempted/accepted swaps. This differs from R22's multigraph shuffle and
is frozen before results, not a response to model reward. Native invariants
and sign complement/path/cycle/K3,3 fixtures are embedded in formal extraction.

Three fixed same-capacity87-input views: primary joint=original42+qualification
flag+new44; topology=base43+actual20+zeros24; decoupled=base43+null44. Same256
ExtraTrees/depth12/leaf4/.8features, seed20261111+fold, original iso5/coarse4/fine5
and inner calibration, total42fits. Existing R47 scoring/cost engine reused
unchanged apart from view names/dimensions. No learner/grid/seed selection.
Native source build O3 C++17 shared library committed before formal run;
binary/source/compiler hashes and actual build CPU included in owner ledger.

Information gate before fitting: >=50 valid informative parents, and their
free-oracle headroom >=.5 full-population percentage points. Informative means
actual/null feature norm difference>1e-6, at least10% of variable nodes eliminated
in BOTH graphs, and accepted null swaps>0. Do not lower limits or resample to
pass. If fails stop0fit/null reward; complete descriptors/costs still evidence.

Four local single-numerical-thread workers on8GiB host; per-input30wall/post10CPU
guard plus hard graph work caps, failed input paidD and all expenses retained.
Collection<=900wall including build, model collection<=1200wall; plan2CPUh and
30min execution, no large matrix or server timing overlap. Native graph calls
and swap work are separately counted, not called0 because no SAT was used.

Complete folds only: no partial preference scoring. Paid replay uses native fee
plus each view's actual read/parse/profile CPU when reached, including finalD;
failed native stops before profile. Topology pays same actual profile fee as
joint, no fictional cheaper deployment. Null includes its construction work.
New model query initially optimistic0 for candidates and cached originalmin3;
free unmasked score also shown. MainPAR2 is h+t if verified and<=600 else1200,
all failures distinct from solver timeout labels.

Primary promotion requires coarse AND fine>=2% with nominal paired direction,
and positive supported improvement over topology, null and originalmin3.
Secondary topology must pass both regimes and originalmin3 comparison. Only
then separately freeze serving/query/independent confirmation, not declare
success on this reused matrix. Preserve conditional mixed positive evidence.
After full feedback stop this order/caps/bins/null/seed/descriptor scheme;
no parameter sweep from held outcomes. Keep all negative reward and fees.

Command: env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
work/anniversary2022_plot_env/bin/python -m
src.anniversary2022_baseline.score_incidence_elimination . Output unique
outputs/anniversary2022_baseline/mechanism_R49_20261111 . Remote R35owner8458
untouched; no partial seed preferences, messages, email or delegation.
