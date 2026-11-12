# R48 design history — superseded before execution by final protocol

Final authoritative protocol: MECHANISM_CYCLE_R48_GLOBAL_TREE_20261111.md.
It adds the prespecified cached-teacher target alongside measured-cost target,
56 rule fits/14jobs,360wall/job, and constant-leaf acquisition semantics.
The original draft below is retained as design history, not execution status.

Current chat, no delegation. Question left by R31/R32/R36: can joint optimization
find a small readable policy that greedy/receding-horizon search missed? Do not
change or tune stopped R46/R47 feature families. Reuse original numeric42 at
native float32 precision, exclude legacy21/26 (40 usable coordinates), original
4719 exposed2022 full matrix and iso5/coarse4/fine5/inner separation. No new
solving/data/probes or R35 partial preferences. Overall goal remains stable
significant advantage overD; readable mixed2% is a useful separate milestone,
never a replacement for structural/deployment/independent validation.

Proposed finite tree class: depth<=3,<=8leaves, nonempty leaf support>=40, empty
leavesD. Candidate cuts from fit-only quantiles[.02,.05,.10,.25,.50,.75,.90,.95,.98],
drop globally infeasible <40-child cuts, plus constanttrue no-op. Dedup identical
training binary columns deterministically, retaining first feature/cut; this is
column memoization not instance-ID routing. Same candidate pool and capacity
for greedy and global methods. Do not describe this as optimal over arbitrary
continuous thresholds or all possible small policies.

Original PAR2 rounded to microseconds for optimization: integers sum<2^53,
binary-matrix float64 dot products retain integer sums. Quantization original
training objective error at most N*1us versus a truly optimal raw-cost tree;
held scores use unrounded true costs. Subtract per-parent min cost as constant
only to improve arithmetic, not omit censored/zero-regret parents.

Low-memory exact finite-grid method, avoiding a large MILP on this8GiB local
host (actual compressed memory/file-cache pressure observed): letB be binary
predicate columns with column0 constanttrue. For a stateM and actiona, G_a=
B.T diag(M*c_a) B, G_count=B.T diag(M)B. Diagonals give cost/count singles,
G[0,0] total. For splitk and second predicate t, four intersections have costs
G[k,t], S[k]-G[k,t], S[t]-G[k,t], T-S[k]-S[t]+G[k,t]. Take best leaf action in
each, forbid counts1..39, and independently minimize left/right stump choices
for everyk. This solves the best depth2 tree forM without local-gain pruning.

For each top-level predicatej, compute the four Gram matrices of the smaller
of its left/right state; the other side is fullGram-smallGram. Solve the two
depth2 subtrees and choose best root. If ALL roots processed, exact minimum of
the stated discretized training class is certified; if a wall bound stops it,
retain validated greedy incumbent and actual search progress, report only
best-known result/trivial oracle lower bound, never call it globally optimal.
Canonical tie: simpler tree, then deterministic pool order; empty statesD.

Working storage O(NP+P^2), not O(N*leaves*P) huge optimization matrices. Four
single-numerical-thread fold workers initially, all14 complete outer jobs; each
shares quantile/Gram prep between one greedy and one global fit ->28 rule fits.
Per-fit search120wall, outer guard180wall; total20min/2CPUh planning. Record
actual RSS/native calls/CPU separately. Source/protocol must be committed first.
No independent dryrun; the formal fit checks route/leaf support and executable
tree cost exactly against its joint-count objective before any held prediction.

Two prespecified uses of each learned tree: raw leaf actions (readable target)
and original inner-fitted conservative margin. Leaf confidence is training mean
D-minus-selectedF, other direction0, Dleaf0; inner alone decides margin. Same for
greedy/global. Report all modes, not pick best on held feedback. Score free and
full compatible native8+16/25failed paidD, new query initially0 for all methods/
cached originalmin3; nonconstant whole fold pays even on finalD, constantD skips.
Save per-fold executable JSON/natural conditions and completion/gap certificates.

Readable milestone: original mixed fivefold>=2% (with explicit cost boundary),
do not deny it using a substituted transfer target. Whole-goal promotion still
requires original structural regimes>=2%, nominal direction and improvement
over matched greedy/strong original baseline, then separately frozen actual
serving/reproducibility. Failure stops this fixed grid/depth/support/search
scheme; no new depth/quantile/time/seed search from feedback. If implementation
finds the exact method unfit, persist reason and a concrete bounded fallback
without claiming an unexecuted experiment. Current state: draft only.
