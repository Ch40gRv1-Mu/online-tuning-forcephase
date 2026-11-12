# Astra bounded exploratory review — 2026-11-10

Status: COMPLETE; exploratory assessment only, no fitted/validated policy. Owner: parent chat, with this explicitly requested Astra review. Start 22:15:34 UTC; hard deadline 22:18:34 UTC. Partial assessment was saved within the first minute. Completion: 2026-11-10 22:17:17 UTC. No SAT solving, downloads, literature browsing, threshold search, or other-agent delegation occurred.

## Answer

There is a plausible signed-encoding clue, but no established structural rule. In the selected cached panel, F− winners tend to have more binary clauses, slightly more negative literals, and shorter average clauses. The distributions overlap extensively, including almost equally sized, almost entirely binary instances that prefer different actions. Consequently neither “binary-rich means F−” nor “negative-heavy means F−” is supported as a dependable rule. The existing data also do not support a blanket “long clauses favor F−” account.

Study: the completed **official_all_tracks_unsolved_v1 filtered 4,719-instance** CaDiCaL T600 seed-0 baseline. Every row is permitted development data; an independent test remains to be selected. The question is structural explanation of relative D/F+/F− preference, not absolute difficulty. Only pure CNF structure is eligible as an input. Names, paths, identities, known answers, terminal conflicts and final runtimes are not predictors.

## Actual measurements

Full-cohort tolerance groups are D 1,141; F+ 698; F− 692; near-tie 1,016; all-timeout 1,172. Thus 2,531 have a unique near-best action under max(0.1 seconds, 1% of fastest); 1,172 provide no resolved winner. These labels do not demonstrate cross-seed stability. The 1,016 near-ties should not be forced into three-class labels.

D is the best fixed control: summed PAR2 is 1,852,408.783 seconds, versus F+ 2,209,608.117 and F− 2,227,254.988. Free VBS is 1,651,370.313, a 10.853% improvement over D before any feature or routing cost. This is headroom, not a selector result. There are 483 parents with at least one F action that solves when D times out or is at least twice as fast when both solve; they generate 571 action rows, so action counts must not be added as distinct parents.

Wrong-switch costs matter: across the full matrix, positive F+-versus-D PAR2 differences sum to 115,291.905 seconds of potential savings, while negative differences sum to 472,491.239 seconds of losses. Corresponding F− totals are 134,049.609 saved versus 508,895.814 lost. These are descriptive sums over different instances, not achievable policy returns. Neither F action is safe to select globally. Timeout-related PAR2 differences are not runtime speedup ratios.

Only **138/4,719 (2.92%)** have reusable structure, leaving 4,581 without structural observations. Cached group counts are D 46, F+ 22, F− 24, near-tie 12, all-timeout 34. This is a selected, previously examined old exploratory panel, not a representative subsample and not validation. Cache association uses the exact GBD key and old SHA-bound CNF statistics; the new cluster's raw-input SHA receipts were not locally verified.

Descriptive medians, with interquartile intervals in brackets where useful:

| Statistic | D (46) | F+ (22) | F− (24) |
|---|---:|---:|---:|
| Binary-clause fraction | .201 [.011, .702] | .104 [.002, .611] | .397 [.091, .682] |
| Mean clause length | 2.959 [2.531, 3.360] | 2.991 [2.672, 4.134] | 2.766 [2.429, 3.140] |
| Negative-literal fraction | .501 [.499, .571] | .501 [.500, .561] | .536 [.501, .585] |
| Negative-only minus positive-only clause fraction | .028 | .001 | .089 |
| Variables | 3,594.5 | 2,310 | 6,380.5 |

Intervals use inclusive empirical quartiles. These are descriptions chosen for this review, not feature-selection evidence or predictors. Size differs too, leaving encoding and scale confounded. All-timeout rows have negative-literal median .545 and mean-clause-length median 2.749: a feature associated with F− among resolved cases may also mark unresolved difficulty, so censoring cannot be discarded in cost comparisons.

Concrete counterexamples, using anonymous row references solely to locate evidence:

- `cached_98` prefers D and `cached_12` prefers F−. Both have 945 variables; clause counts are 61,409 versus 61,855 and binary fractions .999267 versus .999272. Negative-literal fractions are .978492 versus .992414. Therefore even very similar size and binary density do not determine the preference. These rows were selected as illustrative counterexamples, not a statistically matched sample.
- `cached_76` prefers D despite negative-literal fraction .993676 and binary fraction .999081.
- `cached_109` prefers F+ despite binary fraction .980392. `cached_28` prefers F− with no binary clauses. `cached_38` prefers F− despite negative-literal fraction only .303569.

## Two falsifiable hypotheses to freeze next

These are conjectures, not measured mechanisms. No values for these new descriptors were extracted in this review. Their purpose is to distinguish signed constraint organization from raw size/binary-density effects; they do not assert the semantic type or family of any instance.

**1. Paired choice/exclusion structure, rather than binary count alone, favors sparse assignments in a specific sign direction.** For a canonicalized CNF (deduplicate literals, discard tautological clauses, deduplicate identical clauses), consider each all-positive or all-negative clause C with 3–32 distinct variables. Define q(C) as the proportion of its unordered variable pairs for which the opposite-sign binary clause exists. For a positive C, count clauses (¬xi ∨ ¬xj); for a negative C, count (xi ∨ xj). With m the canonical clause count, define E = [sum q(C) over positive C − sum q(C) over negative C] / max(1,m), and U using the sum rather than the difference. E>0 measures positive choices paired with negative exclusions and conjecturally favors F−; E<0 conjecturally favors F+. This is a partial syntactic motif, not proof of a complete exactly-one encoding.

Suggested comparison: freeze E before extracting it, then compare matched-capacity simple selectors using E versus unsigned U and existing coarse polarity/binary controls on the same development rows, with D as the cost baseline. Assess whether any gain remains after accounting for log variable/clause counts; retain near-ties and all-timeout rows in cost scoring. Failure: E adds no out-of-fold cost benefit beyond unsigned density/size, reverses its proposed direction, or its extraction cost consumes the benefit. Sequential/cardinality encodings without these literal pairs are a known coverage limitation. Do not search the 3–32 limit after inspecting outcomes.

**2. Concentration of polarity across variables matters beyond the global negative-literal fraction.** Let n_i and p_i be negative and positive occurrences of active variable i, d_i=n_i+p_i, b_i=(n_i−p_i)/d_i. Define S3 = sum_i d_i*b_i^3 / sum_i d_i, with value zero when no literals exist. This signed third moment emphasizes variables with concentrated polarity; unlike the existing absolute imbalance, it retains direction. Conjecture: positive S3 is more associated with F− benefit and negative S3 with F+ benefit than the global negative fraction alone, because a small group of consistently signed variables may be obscured by balanced auxiliary occurrences.

Suggested comparison: use S3 as one predeclared replacement for global negative-literal fraction under the same model capacity and folds, report incremental out-of-fold PAR2 improvement relative to D and the existing-sign control, and inspect size-adjusted results. Failure: S3 is effectively redundant with global polarity, yields no incremental benefit, or helps only in the selected 138-row cache and disappears with broader coverage. This statistic does not by itself reveal causal gates or dependency direction.

## Missing evidence and handoff

No conclusion about structure can be assigned to the 4,581 rows without features. Before a formal comparison, the parent owner must freeze the extraction/comparison procedure, establish compatible input identity, and collect the chosen descriptors on a predetermined development manifest without rerunning the complete solver matrix. A directionally successful exploratory comparison still requires a separately selected independent test; single-seed labels do not establish stable winners. Feature extraction cost is currently unmeasured, so deployment economics remain unanswered.

Completed: bounded review, whole-cohort cost summaries, cached distribution descriptions, counterexamples, and two defined hypotheses. Remaining within this review: none. New formal extraction and scoring: not started. Next executable action: parent owner freezes the first paired-motif extractor and its same-capacity control comparison, starting from existing permitted inputs and preserving D fallback for missing features; S3 is a secondary candidate, not a prerequisite. New solver CPU: 0; reused logical costs above are not new compute. Local review/analysis overhead is not separately metered.

Evidence files, all in this report's directory: `all_preferences.csv`, `summary.json`, `astra_structure_view.csv`, `F_actions_opportunities_vs_D.csv`, `F_actions_losses_vs_D.csv`. Protocol: `refine-logs/anniversary2022_baseline/VBS_PREFERENCE_20261110.md`.
