# Structural-feature coverage

Tree-likeness is implemented as incidence-graph cycle excess, variable leaves, degree statistics and component summaries. Local gate-pattern counts are implemented, with an exactness flag. These do not reconstruct a complete directed circuit. Formula depth, graph diameter and leaf-peeling/core depth are not implemented. The depth=2 in round2 is policy-tree capacity, not formula depth.

The graph-only round2 proposal is frozen but unscored. Completed action-cost screens do not constitute a trained tree/depth strategy. Current fast60 matrix must be complete before its graph proposal is scored. A future depth feature needs an explicit graph/root or root-independent definition plus versioned feature, cost, allowlist and proposal; no existing run or proposal has been changed to pretend depth was measured.

The user's question also motivated a descriptive check of already extracted48fit features only, without accessing outcomes or fitting thresholds:

- Strict incidence forests (cycle excess zero): 0/48.
- Normalized cycle-excess range: 0.39565725921 to 0.952037503808; median 0.508396082188.
- Leaf-variable fraction median: 0.0.

These are structural-distribution facts, not policy rewards or evidence for a depth-preference relation.
