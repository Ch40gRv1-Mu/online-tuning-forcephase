# R51 gate-controllability feature transfer, no new SAT scores

Current-chat owner, no delegation. Previous goal turn was progress: R49/R50
feature extraction and complete three-action scoring closed; neither stable
versusD. Latest user requires CNF features->D/Fplus/Fminus, reusing original
timings. No SAT/UNSAT auxiliary training, answers, family/metadata routing,
short searches, new matrix or R35 partial preference feedback.

Question: does composed directional forcing cost on recognized gate cones
predict the value of D's per-variable saved/target phases better than merely
counting gates/local directions? This is a structural heuristic, not actual
D search state or a minimum SAT assignment cost. DefaultD initially has no
explicit preprocessing/local-search rounds; dynamic rephasing occurs later.
Do not infer startup local walk solely because a function exists in source.

Explicit reuse/dedup: src/ta100/graph_features.hpp gates and
src/ta100/graph_extra_features.hpp controllability are oldTA I031 helpers;
reverse observability is the existing I032 recursion, factored in a thin
wrapper. Existing gate_dependency.hpp already measures SCC/depth/alias/local
direction in current data; do not call gate-depth new. OldTA two-action
false/true timings are NOT current CaDiCaL D/Fplus/Fminus labels. This is a
current-population feature transfer with new controls, not a new algorithm.

Population all4719 retained2022 development, complete14157 seed0/T600 labels
reused; D3385solved/meanPAR2=392.54265364738285s,1172triplecensored,2279clear,
freeoracle10.852813%. Same2325 count-qualification nmax<=100000 and rawL<=200000
from previous fixed feature panels. No additional outcome-based exclusions;
failed extraction paidD and all4719 remain denominator. Entire2022 already
exposed; no independent-test claim. Preserve5355 master and official636filter.

Native wrapper reads current public cached CNF, normalizes via old shared
parser, recognizes exact signed AND z<-a,b from three defining clauses.
Multiple definitions of a variable are ambiguous; exclude these and cycles
from evaluable order, preserve coverage. Primary inputs CC0=CC1=1. At each
evaluable signed gate, CC0(z)=1+min(CC0(a),CC0(b)), CC1(z)=1+CC1(a)+CC1(b),
swapping literal directions as needed, saturating1e12 exactly as old helper.
Reconvergence can double-count support; no exact assignment-cost certificate.
No assignments, SAT propagation, satisfiability classifier or solver invoked.

CO initialization0 for evaluable sinks/residual-interface variables. Reverse
recursion CO(a)=min(CO(a),CO(z)+CC1(b)+1), symmetricallyb, on same defined gates.
Local control keeps exact evaluated gate set/graph/interface but replaces every
defined output CC with single-hop(2,3) or(3,2) by output sign before the same
reverseCO recursion. This isolates composedCC, does not pretend CO became local.

Shared8: gate-variable/active-variable fraction; gate matches/rawM; ambiguous
gate fraction; evaluable/gate fraction; primary-input/active-variable fraction;
gate input sharing/total fanout; mean log1p(fanout)/activeN; mean output sign.
Each full/local block16, for c=(CC1-CC0)/(CC1+CC0), original variable biasb,
degree d, and o=CO/(CO+CC0+CC1): mean c,mean|c|,mean c²,meanlog1p(CCsum),
maxlog1p(CCsum),d-weighted mean c,d-weighted mean|c|,mean c*b,mean|c*b|,
fraction finiteCO,mean o,mean c*o,mean|c|*o,fractionc>0,fractionc<0,
mean[log1p(CC1)-log1p(CC0)]. LastCO means over finite outputs; missing/empty
gate summary0 with explicit shared coverage, never known-answer fallback.

Three67-input views: base42+original eligibilityflag+shared8+full16 (joint),
same with local16 (local), same with conditionally reassociated full16 (null).
Null: independently INSIDE each outer train/inner/held partition, permute16
vectors among successful evaluable formulas in fixed strata
floor(log1pN/log4),floor(log1pM/log4),floor(evaluable_fraction*4). Original51
coordinates stay attached. Seed20261151+fold+100*partition_index+1000*mode_index.
No sources cross partition, no outcomes used in null construction, no change
to real formula or runtime labels. Null is a statistical association control,
not a deployable strategy/CNF or exact preservation of all42 covariates.

Information gate before fits: >=50 valid parents with>=2evaluable outputs and
full/local vector norm difference>1e-6, whole4719 oracle headroom on them>=.5pp.
Then require>=50 changed reassociated training vectors in EVERYouterfold.
If either fails, preserve descriptors/fees with0fit/nullreward; no smaller
gate, replacing parents or best-cutoff selection. All qualified successful
profiles, not just informative ones, enter fixed models.

Four local single-numerical-thread workers, first-completed refill. Native
source+three dependency headers/binary/compiler SHA bound. Internal2.5CPU
budget includes parse; native OS4CPU/5hard,7wall alarm, outer8wall kill,512MiB
RSS checks; common old parser limits100MB/5Mheader/2Mclauses/20MrawL apply as
resource failures, not new cohort selection. Each profile post10CPU/30wall;
collection900wall. Three AND/chain/complement fixture calls embedded in formal
execution, never independent dryrun/audit. Failed logs/CPU kept; no healthy
remote owner touched. First complete score targeted30–60min including prep,
planning2CPUh/30minexecution.

If gates pass, original iso5/coarse4/fine5 with inner group separation, same
256ExtraTrees/depth12/leaf4/.8features/seed20261111+fold,42fits. Target ONLY
(D_PAR2-F_PAR2)/1200, original bounded inner margin. R50 scoring engine
reused with67dimensions/control names; no learner/loss/seed sweep or partial
held scoring. No full-development export or per-row query benchmark yet.

Charge full measured native/read/write/input parse/featureCPU to all views,
even local control (conservative), plus native42 fees8+16/25failedpaidD;
failednative stops before thisfeature. Failedfeature paidD plus expense.
Compiler/fixtures/engineering count physically once in owner ledger, not
fictional per-query費. Null reassociation CPU physically in scorer ledger;
all model/query costs initially optimistic0, not a serving claim. Free unmasked
predictive score separate. TotalT600 h+t<=T otherwise1200; preserve censoring.

Primary joint must show>=2% coarse ANDfine with nominal positive direction
and supported positive increment over local/null/originalmin3. Predeclared
local comparator can promote only with same two-regime threshold/direction
and strong originalmin3 comparison. Then separately freeze serving and
independent confirmation; repeated development nominal intervals do not
confirm goal. Preserve original mixed~2% evidence. Stop this helper/summary/
CPU/strata/seed combination after full feedback, no tuning from held results.

Execute after source+protocol commit:
env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
work/anniversary2022_plot_env/bin/python -m
src.anniversary2022_baseline.score_gate_cost_transfer . Unique output
outputs/anniversary2022_baseline/mechanism_R51_20261111 . No new email,
messages, agents, uploads or SAT-solving submissions.
