# TA100 静态机制来源与去重记录

2026-11-05，目录状态更新。这里的40个图/结构机制均已实现，并已由root统一collector在192个获准开发fit/feedback实例上完成正式采集；各列可观测覆盖不同，不能把采集终局等同于全部有值或有收益。它们是基于既有文献概念的研究提案，不是40项原创发明。评分与总迭代完成状态以中央记录和[特征目录](../reports/ta100/FEATURE_CATALOGUE.md)为准。本新阶段严格禁止读取或使用已消费gate；5355最终测试继续封存。

每项的精确公式、实现上限、缺失语义和 novelty_key 见 [static_candidates.json](../work/ta100/static_candidates.json)。40项C++实现已分组冻结并完成必要合成性质检查；首10与后30使用独立源码快照。此处成本栏表示算法工作量，实际CPU/墙钟与失败费用以中央collector receipts为准。

## 新颖性判定

- 按“输入对象 × 数学运算 × 机制”去重。阈值、分位数、均值/尾部、log、归一化和采样预算变化不增加机制数。
- 对照旧 `cnf_structure.cpp` 的全部 emit 字段（34 个描述量及诊断元数据）、旧 H01–H06 的 signed/root-UP/短轨迹/条件传播，以及另一个 owner 的 implication-SCC/depth、完整 ternary parity、choice/exclusion-block 定义；只读定义，没有读取其 protected 结果。
- Root 预留 renamable-Horn、Ising/符号挫折、submodularity、全局文字补对称、autarky、Hall matching、packing/hitting、signed leading eigenmode、LP pressure、BP。Node agent 预留 canonical redundancy、resolution growth、blockedness、local orbit、flip-energy、covered literals、ITE。此清单不占用这些机制。
- Node 原先图机制候选中的 core、articulation、modularity、butterfly、assortativity、fractal 已显式交给本 graph owner，不能双计。
- 邻近概念仍由 root 中央裁决。例如局部 transitivity、triangle-filled homology 和度归一化 diffusion 都研究图，但分别计算闭合、同调与输运；若某个 proposed proxy 实际退化为已有量，应合并并补真正不同的机制，不能靠字段名凑数。

## 原始来源

文献支持底层概念或算法；具体归一化标量、bounded proxy 和 phase 相关解释均是待测提案，不能写成文献证明了 phase 选择收益。没有直接引文。

- **articulation**：[Depth-First Search and Linear Graph Algorithms](https://epubs.siam.org/doi/abs/10.1137/0201010)。依据：Undirected articulation decomposition. 候选：S06。
- **assort**：[Mixing patterns in networks](https://arxiv.org/abs/cond-mat/0209450)。依据：Endpoint mixing statistics. 候选：S01, S15, S37, S38。
- **boolean**：[Analysis of Boolean Functions, O'Donnell](https://arxiv.org/abs/2105.10386)。依据：Finite Boolean-function analysis. 候选：S34, S36。
- **butterfly**：[Butterfly Counting in Bipartite Networks](https://arxiv.org/abs/1801.00338)。依据：Bipartite butterfly counting. 候选：S04。
- **cadical**：[CaDiCaL congruence implementation, rel-3.0.1](https://github.com/arminbiere/cadical/blob/rel-3.0.1/src/congruence.cpp)。依据：AND and ITE gate recognition. 候选：S09, S30。
- **canalizing**：[Nested Canalyzing, Unate Cascade, and Polynomial Functions](https://arxiv.org/abs/q-bio/0606013)。依据：Canalizing functional hierarchy. 候选：S33, S35, S36。
- **circuit**：[Extracting Hardware Circuits from CNF Formulas](https://research.jku.at/de/publications/extracting-hardware-circuits-from-cnf-formulas/)。依据：CNF circuit reconstruction. 候选：S09, S10, S26, S27, S28, S29, S31, S32, S33, S34。
- **community**：[Community Structure in Industrial SAT Instances](https://arxiv.org/abs/1606.03329)。依据：SAT community structure. 候选：S11, S38。
- **core**：[An O(m) Algorithm for Cores Decomposition](https://arxiv.org/abs/cs/0310049)。依据：Core peeling. 候选：S05。
- **curvature**：[Ricci curvature of Markov chains on metric spaces](https://arxiv.org/abs/math/0701886)。依据：Neighborhood transportation contraction. 候选：S39。
- **fractal**：[The Fractal Dimension of SAT Formulas](https://arxiv.org/abs/1308.5046)。依据：SAT metric self-similarity. 候选：S12。
- **gyo**：[Degrees of acyclicity for hypergraphs and relational database schemes](https://research.ibm.com/publications/degrees-of-acyclicity-for-hypergraphs-and-relational-database-schemes)。依据：Hypergraph acyclicity. 候选：S20, S21。
- **gyo_algorithm**：[Maier: Acyclic Database Schemes, Graham reduction](https://web.cecs.pdx.edu/~maier/TheoryBook/MAIER/C13.pdf)。依据：Unsigned GYO reduction rules. 候选：S20。
- **homology**：[GUDHI Simplex Tree official documentation](https://gudhi.inria.fr/python/latest/simplex_tree_ref.html)。依据：Simplicial homology construction. 候选：S40。
- **hyperbolicity**：[Computing the Gromov Hyperbolicity of Graphs, Coudert](https://www-sop.inria.fr/members/David.Coudert/code/hyperbolicity.shtml)。依据：Four-point graph metric. 候选：S25。
- **motifs**：[Network Motifs: Simple Building Blocks of Complex Networks](https://pubmed.ncbi.nlm.nih.gov/12399590/)。依据：Small wiring patterns. 候选：S27。
- **planar**：[Simplified O(n) Planarity by Edge Addition](https://jgaa.info/index.php/jgaa/article/view/paper91)。依据：Planar embedding recognition. 候选：S13。
- **rankwidth**：[Approximating clique-width and branch-width](https://web.math.princeton.edu/~pds/papers/rankwidth/paper.pdf)。依据：Cut-rank structural width. 候选：S14, S23, S24。
- **satzilla**：[Features for SAT, Xu et al.](https://www.cs.ubc.ca/labs/algorithms/Projects/SATzilla/Report_SAT_features.pdf)。依据：SAT structural feature taxonomy. 候选：S02, S03, S08, S17。
- **scoap**：[Controllability/observability analysis of digital circuits, Goldstein](https://doi.org/10.1109/TCS.1979.1084687)。依据：Circuit testability motivation; DOI metadata verified, full paper unavailable in this session. Proposed recurrences are explicitly specified independently. 候选：S31, S32。
- **vc**：[On the density of families of sets, Sauer](https://doi.org/10.1016/0097-3165(72)90019-2)。依据：Set-system shattering; publication identity verified in author university bibliography: https://profiles.ucalgary.ca/norbert-sauer 候选：S22。
- **walk**：[Random Walks on Graphs: A Survey](https://cs.yale.edu/publications/techreports/tr1029.pdf)。依据：Diffusion and return probabilities. 候选：S07, S16, S18, S19。

## 低成本首批与实现边界

|编号|机制|成本边界|
|---|---|---|
|S01|Variable-degree/constraint-arity endpoint coupling|O(L+n+m) time; O(n+m) storage|
|S02|Sign/constraint-arity dependence|O(L) time; O(1) extra storage|
|S03|Horn/non-Horn shared-variable interface|O(L) time; O(n) storage|
|S04|Repeated two-variable constraint overlap|O(sum_C k_C^2), explicitly capped; bounded map|
|S05|Recursive incidence-core retention|O(L+n+m) time/storage|
|S06|Articulation separation mass|O(L+n+m) time/storage|
|S07|Unsigned incidence diffusion return|O(32L) time; O(n+m) storage|
|S08|Variable co-occurrence transitivity|O(sum k_C^2 + triangle intersections), capped|
|S09|Recognized-gate output sharing|O(L+matched_templates), capped motif map|
|S10|Recovered-circuit/residual constraint interface|O(L+matched_templates), bounded map|

共同 CNF parser 保留原子句索引，排序去重文字并标记重言子句。图模块跳过重言子句；空分母或零方差是 null/UNDEFINED。达到完整枚举 cap 时是 null/RESOURCE_LIMIT，绝不把未完成的枚举前缀当全量零值。采样型定义明确只说明采样对象，不冒称全图 certificate。

首批 header：`src/ta100/graph_features.hpp`，wrapper：`src/ta100/graph_core.cpp`，共享 parser 由 node agent 独占。无 SAT solver 调用。5 CPU 秒、3 GiB、12 秒墙钟的正式进程配置由 root 统一施加；模块在更早的内部 CPU 预算耗尽时逐块写 missing 状态，费用与共享索引准备单独保留。

## 每十项工作流复盘建议

冻结十个机制和实现 → 共享一次 parse/index → 按输入 SHA checkpoint → 完整开发人口齐备后评分 → 同时报覆盖、费用、失败与负结果 → 检查 novelty/廉价基线 → 再冻结下十项。没有覆盖或没有增量时停止该机制；不把 log/quantile/seed 变体算新迭代。新的候选只在获准开发人口中探索；禁止读取或使用gate及5355最终测试，不重新打开旧gate。

## 源码完成与中央去重补充

历史设计快照（2026-11-05，正式采集前）：当时40项源码刚完成并通过必要合成测试，尚未运行真实输入。此历史时态不能当作当前状态。

当前状态：root已完成graph10和graph_all30两组各192个开发实例的正式静态采集。graph10与后30项分开冻结，后者在 `graph_extra_features.hpp`，由后续冻结wrapper统一输出30项；定义中的每十项评分组保持独立。全部header、共享parser、wrapper及binary身份见中央manifest和特征目录。

- S37原提案与root的pairwise falsifying-subcube overlap严格重复，已在提取/评分前替换为within-clause sign bundling的二项独立性偏离，未将重复项计数。
- S23是unsigned adjacency cut-rank；root仅做signed local clause-row real rank。`[[1,1],[1,-1]]`与`[[1,1],[1,1]]`有相同unsigned结构但不同real rank，故对象与运算定义不同。
- S36作用于局部Boolean satisfaction predicate的GF2 ANF；root Walsh作用于实数unsatisfied-clause-count energy。复制一个子句不改变前者而改变后者，是明确的非别名见证。S36排除affine/XOR。
- 其他owner的complete ternary parity和choice/exclusion仍不占用。非模板局部功能提案排除affine、AND/OR、majority、ITE与cardinality函数，避免同一门的符号变体双计。
- 8项必要合成检查通过，零分母/null与完整门模板缺一子句的语义有明确检查；这些检查不是独立audit/dry run。之后的真实CNF提取由root统一正式执行并留有receipts，本目录整理任务没有新提取或重新评分。
