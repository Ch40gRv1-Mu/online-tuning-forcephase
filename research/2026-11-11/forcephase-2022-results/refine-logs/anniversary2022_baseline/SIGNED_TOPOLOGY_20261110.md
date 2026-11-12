# Signed binary topology, gate and exclusion discovery

Use the existing complete seed-0 T600 PAR2 matrix for all 4,719 officially retained Anniversary 2022 development formulas. Keep the prior grouped five folds. The 24 matched cases shown to Astra inform mechanisms only. Use no solver jobs, answer labels, family or identifying metadata in the policy. The GBD hash joins inputs and ensures the same formula. No gate or independent test.

## Extraction

Collect every manifest formula with cached raw size ≤1,500,000 bytes, ≤100,000 variables, and at least one binary clause. This is 1,988 formulas determined by the structural snapshot. The eligibility rule is independent of the action outcomes. Fall back to D for all others and on extraction failure, keeping their cost in the denominator. Stream public benchmark data and retain measurements with verification of GBD hash, clause count and binary count. Reuse locally verified panel files where available. Bound transfers, parsing time, graph size and second-hop edge count. Preserve failed records. Time extractor and verification separately.

Four predefined blocks on the raw signed formula:

- Binary implication SCC shares and signed condensed-DAG depth. Nontrivial SCCs can describe equivalence or constraint structure. Depth is longest directed path on the condensation of the binary implication graph.
- Signed reach and complementary collisions at depth two. For each of up to 64 sampled active variables, probe both signs using a fixed sampler, include all first hops and at most 512 second-hop arcs per root. Record truncation. Sampling and clipping can depend on variable numbering.
- Distinct signed two-input AND gate motifs, orientation and binary fan-out balance. This is exact pattern matching for the stated three clauses, with an implication-degree proxy for extra fan-out.
- Mirrored positive and negative choices, lengths 3 to 32, internal complementary binary exclusion and maximum average external exclusion degree per choice. Tail summaries extend the older choice/exclusion features, with the old mechanism recorded as related.

## Replay

For each view, use the existing train-only robust scaling and K-means action-fit protocol at K=12 and 24, with at least 30 train members per switching cluster. Evaluate all four new blocks, their equal-weight combination, and size-only and previous combined-view controls using exactly the same eligibility and folds. Select a new block and K in the two inner training splits by summed PAR2 savings, including fixed D, and report the nested outer result. Separately fit one guarded threshold and action for each new block with the same standard capacity as previous stumps. Report descriptive signed relative-gain correlations and the number switched, solved and worsened versus D. Compute paired group intervals on out-of-fold costs. These are exploratory development replays. Multiple fixed variants will be visible, including failed ones.

Report a free-feature score and score with measured extractor CPU charged to all extracted rows routed by that view. Apply the 600-second total cutoff to solved time plus extraction time, with PAR2=1,200 for timeouts. Feature latency, source eligibility lookup, existing feature availability and real end-to-end launch overhead still need deployment measurement. A small gain or interval crossing zero is a lead only. A result on the 1,988 eligible inputs is insufficient without the full-cohort fallback score.

## Directional comparison on the same extraction

Test the mechanisms as four directional guards in addition to unsupervised partitions. H01 uses the sign with longer two-hop reach if it does not have more complementary collisions. H06 uses the sign with longer condensation depth under the same guard. H09 uses a binary fan-out proxy when its direction agrees with the signed gate-count imbalance. H14 uses only a strong internal-exclusion asymmetry and nonzero external bottleneck, with choice-clause polarity reversed for the action. Its strength is choice density divided by one plus log external maximum. These two proxies do not implement the catalogue's full boundary and concentration measures.

Report the fixed directional rules and their train-only minimum-strength variants with fixed D as an option. The training threshold grid is zero and the 25th, 50th, 75th and 90th percentiles of nonzero guarded strength. A threshold requires at least 30 training switches and positive training savings after measured feature CPU. Selection of fixed D in a fold omits extraction for that fold. All alternatives use the same availability, folds and evaluation matrix, with no extra feature extraction. This comparison is frozen before reading the topology replay results.
