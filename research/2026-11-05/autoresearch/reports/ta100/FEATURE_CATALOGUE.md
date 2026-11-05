# TA100 特征目录

更新：2026-11-05T06:55:15.312352+00:00。共 **100 个冻结机制提案**：70 个输入侧结构/有界辅助计算、30 个原生求解前缀动态描述量。RA16/17包含有界noisy-local-walk辅助轨迹，不能称70项都是纯静态计数。它们不是100项原创发明，也不表示100项均有用。此快照已有 **100/100** 份正式完成评分记录。

本目录只汇总冻结定义、来源、实际列名、既有覆盖和fit诊断。未拟合、重新评分或读取gate/test。新阶段严格禁止使用已消费gate，5355最终测试仍封存。机器目录：[FEATURE_CATALOGUE.json](FEATURE_CATALOGUE.json)；必要FIT去重：[FIT_FEATURE_DEDUP.json](FIT_FEATURE_DEDUP.json)。

## 读法与限制

- 覆盖写为“fit观测数/180；feedback观测数/60”；原有48资源排除父题仍在评估人口中回退。实际采集名单是144fit+48feedback，共192。null包括零分母、未到checkpoint、资源超限和采集失败，不等于0。
- 动态量只来自共同native-D前缀的合格动作前checkpoint，不使用TA终局计数作特征；它们在TA旧wall标签上的比较是探索信号，不是新硬件端到端部署收益。
- 静态bounded sample、F*与LOCALcube的条件写在条目；样本宽度/同调/曲率不能冒称全图证书。ROOT18的F*固定first512非重言width≤16，保留重复；LOCALcube固定top12 degree变量。
- 表中“采用”只复制既有fit程序是否使用新列，不代表改善已确认。constant/no-observation/within-block别名等既有诊断原样进入机器目录；本目录不改已有结果。
- 5项在当前fit中恒定，只说明本面板缺乏变异。TD12、TD15、TD16三项原因链特征的fit观测分别为7、10、10，feedback各仅1；应称信息不足，不能据此证明机制无用。

## 必要跨块FIT去重

已检查 100/100 个有发布特征表的列，仅FIT数值且要求**完全相同观测ID支持集**；未使用feedback数值/结果或目标标签。逐值exact组 0 个，保留ties的正/反单调组 0 个，|Pearson r|≥0.995诊断对 0 个。高相关不等于机制重复；若出现alias需语义反例或root处理，不能靠改名计数。

## 冻结定义与观测

## B01 · I001–I010

配置：[configs/ta100/B01.json](../../configs/ta100/B01.json)；定义源：[configs/ta100/dynamic_registry_v1.json](../../configs/ta100/dynamic_registry_v1.json)。提取器源码SHA：`9c90920660fc24299079dd7345d635a642c8e42d302aad2773aee53ac712137e`。完整protocol/registry/依赖/binary/feature-table SHA均在机器目录逐项保存。

### I001 · TD01 · 前缀中实际采用chronological backtracking的冲突份额。

前缀中实际采用chronological backtracking的冲突份额。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；主冲突回退事件。操作：chronological份额。
- 条件：共同native-D动作前前缀。
- 实际列：`td_chrono_share`；novelty key：`backtracking_mode_mix`。
- 精确定义：前缀中实际采用chronological backtracking的冲突份额。
- 当前覆盖fit/feedback：**93/180；28/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)；[来源2](https://www.cs.toronto.edu/~meel/Papers/sat20-sm.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I002 · TD02 · 自然重启中保留至少一个决策层的次数份额；不是重启频率。

自然重启中保留至少一个决策层的次数份额；不是重启频率。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；自然restart事件。操作：保留决策层的份额。
- 条件：不以restart频率代替。
- 实际列：`td_restart_reuse_share`；novelty key：`restart_prefix_preservation`。
- 精确定义：自然重启中保留至少一个决策层的次数份额；不是重启频率。
- 当前覆盖fit/feedback：**93/180；28/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/restart.cpp)；[来源2](https://www.cs.toronto.edu/~fbacchus/csc2512/Readings/Pipatsrisawat-Darwiche2007_Chapter_ALightweightComponentCachingSc.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I003 · TD03 · target、saved、其余三个决策相位来源桶的归一化熵。

target、saved、其余三个决策相位来源桶的归一化熵。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；target/saved/其余phase来源。操作：来源分布归一化熵。
- 条件：同一checkpoint三个互斥来源桶。
- 实际列：`td_phase_source_entropy`；novelty key：`native_source_arbitration`。
- 精确定义：target、saved、其余三个决策相位来源桶的归一化熵。
- 当前覆盖fit/feedback：**93/180；28/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/decide.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I004 · TD04 · 固定变量样本中已定义target phase的活跃变量比例。

固定变量样本中已定义target phase的活跃变量比例。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；已定义target的活跃变量样本。操作：target覆盖比例。
- 条件：固定变量样本；未知值保留缺失。
- 实际列：`td_target_support`；novelty key：`target_phase_domain_coverage`。
- 精确定义：固定变量样本中已定义target phase的活跃变量比例。
- 当前覆盖fit/feedback：**93/180；28/60**；状态：`SCORED_COMPLETE`（训练面板中恒定；已记录该负结果）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/decide.cpp)；[来源2](https://github.com/arminbiere/cadical/blob/master/src/restart.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。
- 既有fit数值诊断：`[{"column":"td_target_support","fit_support":93,"kind":"observed_constant","value":1.0}]`。

### I005 · TD05 · best_assigned与target_assigned的带符号相对差；当前active归一化因子在比值中抵消。

best_assigned与target_assigned的带符号相对差；当前active归一化因子在比值中抵消。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；best与target进度记忆。操作：归一化signed lag。
- 条件：共同checkpoint的两个记忆状态。
- 实际列：`td_best_target_gap`；novelty key：`target_memory_progress_lag`。
- 精确定义：best_assigned与target_assigned的带符号相对差；当前active归一化因子在比值中抵消。
- 当前覆盖fit/feedback：**93/180；28/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/decide.cpp)；[来源2](https://github.com/arminbiere/cadical/blob/master/src/restart.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I006 · TD06 · 当前mode内trail长度快EMA相对慢EMA的偏离。

当前mode内trail长度快EMA相对慢EMA的偏离。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；trail长度EMA。操作：快/慢前沿momentum。
- 条件：当前solver mode动作前状态。
- 实际列：`td_trail_momentum`；novelty key：`assignment_frontier_momentum`。
- 精确定义：当前mode内trail长度快EMA相对慢EMA的偏离。
- 当前覆盖fit/feedback：**93/180；28/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/averages.hpp)；[来源2](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I007 · TD07 · 当前冗余子句数量相对于仍存不可冗余子句数量。

当前冗余子句数量相对于仍存不可冗余子句数量。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；保留的学习数据库。操作：冗余/不可冗余数据库负荷。
- 条件：共同checkpoint；不读终局。
- 实际列：`td_learned_database_load`；novelty key：`learned_database_accumulation`。
- 精确定义：当前冗余子句数量相对于仍存不可冗余子句数量。
- 当前覆盖fit/feedback：**93/180；28/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I008 · TD08 · target已定义样本的负相位比例减去全部活跃样本saved负相位比例。

target已定义样本的负相位比例减去全部活跃样本saved负相位比例。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；target与saved phase向量。操作：两者负phase边际差。
- 条件：target已定义样本与完整活跃样本。
- 实际列：`td_saved_target_polarity_gap`；novelty key：`phase_memory_distribution_tension`。
- 精确定义：target已定义样本的负相位比例减去全部活跃样本saved负相位比例。
- 当前覆盖fit/feedback：**93/180；28/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/decide.cpp)；[来源2](https://www.cs.toronto.edu/~meel/Papers/sat20-sm.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I009 · TD09 · 当前mode学习子句长度EMA相对于整个前缀learnt literal/learnt clause均值的对数偏离。

当前mode学习子句长度EMA相对于整个前缀learnt literal/learnt clause均值的对数偏离。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；学习子句宽度EMA/前缀累计均值。操作：宽度regime shift。
- 条件：共同prefix与当前mode，不能混终局。
- 实际列：`td_learned_size_regime`；novelty key：`learned_width_regime_shift`。
- 精确定义：当前mode学习子句长度EMA相对于整个前缀learnt literal/learnt clause均值的对数偏离。
- 当前覆盖fit/feedback：**93/180；28/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/averages.hpp)；[来源2](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)；[来源3](https://fmv.jku.at/papers/FleuryBiere-SAT2021.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I010 · TD10 · 实际backtrack level EMA与潜在nonchronological backjump level EMA的归一化差。

实际backtrack level EMA与潜在nonchronological backjump level EMA的归一化差。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；actual backtrack与potential jump层。操作：归一化保留层差。
- 条件：与冲突层/平均jump分别定义。
- 实际列：`td_actual_potential_backtrack_gap`；novelty key：`chronological_retained_depth`。
- 精确定义：实际backtrack level EMA与潜在nonchronological backjump level EMA的归一化差。
- 当前覆盖fit/feedback：**93/180；28/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/averages.hpp)；[来源2](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)；[来源3](https://www.cs.toronto.edu/~meel/Papers/sat20-sm.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

## B02 · I011–I020

配置：[configs/ta100/B02.json](../../configs/ta100/B02.json)；定义源：[configs/ta100/core_registry_v1.json](../../configs/ta100/core_registry_v1.json)。提取器源码SHA：`9680b5385f8d9958ca04f70df00dee4cf8a8f66fed4f11b694b9d559699b61f9`。完整protocol/registry/依赖/binary/feature-table SHA均在机器目录逐项保存。

### I011 · nodes_01 · Raw repeated signed literals within original clauses

Raw repeated signed literals within original clauses

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；原始子句的signed literals。操作：原始宽度减去去重宽度。
- 条件：共享parser原始统计。
- 实际列：`f_core_literal_repetition`；novelty key：`literal_repetition`。
- 精确定义：sum_C (raw_width(C)-distinct_signed_width(C)) / raw_literal_count
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://fmv.jku.at/papers/EenBiere-SAT05.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I012 · nodes_02 · Original clause tautology burden

Original clause tautology burden

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；单个原始子句。操作：互补literal是否同句。
- 条件：不把普通重复当重言。
- 实际列：`f_core_tautology`；novelty key：`tautology`。
- 精确定义：count_C[exists x: x and -x in C] / M
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://fmv.jku.at/papers/EenBiere-SAT05.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I013 · nodes_03 · Repeated canonical short constraints

Repeated canonical short constraints

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；短canonical子句多重集。操作：相同signed clause重复率。
- 条件：固定短子句上下文。
- 实际列：`f_core_duplicate_clause`；novelty key：`duplicate_clause`。
- 精确定义：sum_S max(freq(S)-1,0) / count_C[non-tautological and width<=8]
- 当前覆盖fit/feedback：**126/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://fmv.jku.at/papers/EenBiere-SAT05.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I014 · nodes_04 · Short strict-subsumption witnesses

Short strict-subsumption witnesses

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；signed子句包含关系。操作：较短子句subsumes较长子句。
- 条件：固定context与完整环境检查。
- 实际列：`f_core_subsumption`；novelty key：`subsumption`。
- 精确定义：count_C[3<=width(C)<=8 and exists D in F: 2<=width(D)<width(C) and D subset C] / eligible_C
- 当前覆盖fit/feedback：**95/180；36/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://fmv.jku.at/papers/EenBiere-SAT05.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I015 · nodes_05 · Width-four self-subsuming resolution

Width-four self-subsuming resolution

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；含pivot的子句对。操作：self-subsuming resolution可缩短率。
- 条件：width4与完整证书。
- 实际列：`f_core_self_subsumption`；novelty key：`self_subsumption`。
- 精确定义：count_C[width(C)=4 and exists l in C: (C minus l) union {-l} in F] / count_C[width(C)=4]
- 当前覆盖fit/feedback：**69/180；19/60**；状态：`SCORED_COMPLETE`（训练面板中恒定；已记录该负结果）。
- 来源启发：[来源1](https://fmv.jku.at/papers/EenBiere-SAT05.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。
- 既有fit数值诊断：`[{"column":"f_core_self_subsumption","fit_support":69,"kind":"observed_constant","value":0.0}]`。

### I016 · nodes_06 · Davis-Putnam raw elimination fanout

Davis-Putnam raw elimination fanout

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；pivot的正负occurrence。操作：Davis–Putnam潜在交叉fanout。
- 条件：输入静态计数；非实际solver消解。
- 实际列：`f_core_resolution_fanout`；novelty key：`resolution_growth`。
- 精确定义：sum_v p_v*n_v / sum_v(p_v+n_v), with one occurrence per non-tautological clause/literal
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://fmv.jku.at/papers/EenBiere-SAT05.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I017 · nodes_07 · Tautological resolvents suppressing elimination blowup

Tautological resolvents suppressing elimination blowup

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；有界resolution parents。操作：resolvent重言比例。
- 条件：有界parent与partner环境。
- 实际列：`f_core_resolvent_tautology`；novelty key：`resolvent_tautology`。
- 精确定义：tautological R(C,D,v) / eligible resolution pairs; parents have3..8 literals and at least one parent width>=4; p_v*n_v<=64
- 当前覆盖fit/feedback：**58/180；18/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://fmv.jku.at/papers/EenBiere-SAT05.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I018 · nodes_08 · Original blocked-clause witness direction

Original blocked-clause witness direction

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；原始clause/literal环境。操作：blockedness与signed对比。
- 条件：所有所需partner检查完成才有值。
- 实际列：`f_core_blocked_polarity`；novelty key：`blockedness`。
- 精确定义：(count_C[positive blocking literal] - count_C[negative blocking literal]) / eligible_C
- 当前覆盖fit/feedback：**96/180；33/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www.cs.helsinki.fi/u/mjarvisa/papers/jarvisalo-biere-heule.tacas10.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I019 · nodes_09 · Exact signed occurrence-column interchangeability

Exact signed occurrence-column interchangeability

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；原始变量列。操作：完全相同occurrence列twins。
- 条件：精确全列相等；非graph WL近似。
- 实际列：`f_core_variable_twins`；novelty key：`variable_twins`。
- 精确定义：variables in size>=2 classes of equal (positive_clause_ID_set,negative_clause_ID_set) / active_variables
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（训练面板中恒定；已记录该负结果）。
- 来源启发：[来源1](https://www.aloul.net/Papers/faloul_dac02_sym.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。
- 既有fit数值诊断：`[{"column":"f_core_variable_twins","fit_support":134,"kind":"observed_constant","value":0.0}]`。

### I020 · nodes_10 · One-step local search directional gain

One-step local search directional gain

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；majority参考赋值。操作：单变量flip收益。
- 条件：静态固定赋值；不是双翻合作逃逸。
- 实际列：`f_core_majority_flip_gain`；novelty key：`local_flip_gain`。
- 精确定义：(count_v[gain(v)>0 and majority(v)=false] - count_v[gain(v)>0 and majority(v)=true]) / active_variables; gain=make-break
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www.cs.ubc.ca/~hoos/SATLIB/ubcsat/algorithms/SelLevMit92.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

## B03 · I021–I030

配置：[configs/ta100/B03.json](../../configs/ta100/B03.json)；定义源：[configs/ta100/graph_registry_v1.json](../../configs/ta100/graph_registry_v1.json)。提取器源码SHA：`c42eed86bca482aa13bc52606903cfe90ec5f17d68f3f598302a120cf7dfd63b`。完整protocol/registry/依赖/binary/feature-table SHA均在机器目录逐项保存。

### I021 · S01 · Variable-degree/constraint-arity endpoint coupling

Tests whether high-degree variables preferentially carry long constraints, a joint incidence pattern absent from the marginal degree and length summaries.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；变量—子句边。操作：度与arity的Pearson相关。
- 条件：完整非重言 incidence；零端点方差缺失。
- 实际列：`graph_incidence_assortativity`；novelty key：`incidence_joint_degree_arity_assortativity`。
- 精确定义：r=PearsonCorr_{(v,C) in E}(d_v,k_C), where k_C=|vars(C)| and d_v=#clauses containing v. Return null for zero endpoint variance.
- 当前覆盖fit/feedback：**116/180；39/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/cond-mat/0209450)。仅支持机制背景，不声称文献证明该phase特征有效。

### I022 · S02 · Sign/constraint-arity dependence

Measures whether encoding polarity is distributed differently between short and long constraints, even at identical total positive fraction.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；文字sign与子句arity。操作：归一化互信息。
- 条件：固定arity桶；sign熵为零缺失。
- 实际列：`graph_sign_arity_information`；novelty key：`literal_sign_constraint_arity_mutual_information`。
- 精确定义：I(S;K)=sum_{s,k} p(s,k) log[p(s,k)/(p(s)p(k))] over literal occurrences, with K=min(clause_literal_count,9), S=positive/negative; normalize by H(S) when nonzero.
- 当前覆盖fit/feedback：**128/180；42/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www.cs.ubc.ca/labs/algorithms/Projects/SATzilla/Report_SAT_features.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I023 · S03 · Horn/non-Horn shared-variable interface

Quantifies interaction between a tractable Horn portion and the remaining constraints, instead of just the Horn-clause fraction.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；Horn/非Horn共享变量。操作：共享incidence质量。
- 条件：非重言原始输入；无UP。
- 实际列：`graph_horn_interface`；novelty key：`horn_nonhorn_incidence_interface`。
- 精确定义：Let h_v and a_v count incidences of v in Horn and non-Horn clauses. f=sum_v min(h_v,a_v)/max(1,L).
- 当前覆盖fit/feedback：**128/180；42/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www.cs.ubc.ca/labs/algorithms/Projects/SATzilla/Report_SAT_features.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I024 · S04 · Repeated two-variable constraint overlap

Detects constraints repeatedly addressing the same variable pairs: local overlap concentration, beyond total cycle excess.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；共同出现在子句中的变量对。操作：butterfly重叠碰撞计数。
- 条件：完整有界pair枚举；超限缺失。
- 实际列：`graph_butterfly_overlap`；novelty key：`incidence_butterfly_overlap_reuse`。
- 精确定义：q_uv=#clauses containing both u and v. B=sum_{u<v} choose(q_uv,2); f=B/max(1,sum_C choose(k_C,2)).
- 当前覆盖fit/feedback：**86/180；31/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/1801.00338)。仅支持机制背景，不声称文献证明该phase特征有效。

### I025 · S05 · Recursive incidence-core retention

Measures how much survives recursive leaf removal, exposing an irreducible interaction core.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；无向incidence图。操作：递归2-core剥离。
- 条件：剥离到固定点；无赋值。
- 实际列：`graph_core_retention`；novelty key：`incidence_iterated_core_retention`。
- 精确定义：Peel all degree<2 vertices from the undirected incidence graph to a fixed point. f=#retained variable vertices/max(1,n).
- 当前覆盖fit/feedback：**128/180；42/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/cs/0310049)。仅支持机制背景，不声称文献证明该phase特征有效。

### I026 · S06 · Articulation separation mass

Measures the fraction of variable pairs whose connection relies on one variable, a decomposition bottleneck hidden by connected-component size.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；无向图单变量割点。操作：最大被割开变量对质量。
- 条件：完整incidence图；不使用有向SCC。
- 实际列：`graph_articulation_fragility`；novelty key：`incidence_single_variable_separator_fragility`。
- 精确定义：For each variable v in an original component with N variable vertices, let s_i be variable counts in components after deleting v. f=max_v[((N-1)^2-sum_i s_i^2)/max(1,n^2)].
- 当前覆盖fit/feedback：**128/180；42/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://epubs.siam.org/doi/abs/10.1137/0201010)。仅支持机制背景，不声称文献证明该phase特征有效。

### I027 · S07 · Unsigned incidence diffusion return

Tests repeated-walk trapping and local circulation, rather than the sign alignment of the leading eigenvector.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；无符号归一化邻接算子。操作：S^4随机trace/返回估计。
- 条件：8个固定探针；不是signed leading-mode。
- 实际列：`graph_diffusion_return`；novelty key：`unsigned_incidence_diffusion_return`。
- 精确定义：S=D^(-1/2) A D^(-1/2) on the unsigned incidence graph. f=tr(S^4)/max(1,n+m), estimated by mean_{8 fixed seeds} z^T S^4 z/(n+m) for Rademacher z.
- 当前覆盖fit/feedback：**126/180；40/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://cs.yale.edu/publications/techreports/tr1029.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I028 · S08 · Variable co-occurrence transitivity

Measures whether neighboring variables also interact with each other, a local closure mechanism beyond node degrees or incidence cycle rank.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；变量共现primal图。操作：三角形/闭合wedge比例。
- 条件：精确有界投影；超限缺失。
- 实际列：`graph_primal_transitivity`；novelty key：`primal_transitivity_wedge_closure`。
- 精确定义：On the deduplicated primal graph G_V, f=3*triangle_count/max(1,sum_v choose(deg_GV(v),2)).
- 当前覆盖fit/feedback：**61/180；18/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www.cs.ubc.ca/labs/algorithms/Projects/SATzilla/Report_SAT_features.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I029 · S09 · Recognized-gate output sharing

Measures repeated use of intermediate results: DAG sharing rather than the existing number of gate-shaped templates.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；已验证AND数据流。操作：中间输出fanout共享。
- 条件：只用无歧义完整门模板。
- 实际列：`graph_gate_sharing`；novelty key：`recognized_gate_dataflow_sharing`。
- 精确定义：Detect complete signed AND templates z<->(a and b), retain uniquely defined output variables. Let f_u=#retained gates using variable u as an input. f=sum_u max(0,f_u-1)/max(1,sum_u f_u).
- 当前覆盖fit/feedback：**66/180；23/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://research.jku.at/de/publications/extracting-hardware-circuits-from-cnf-formulas/)；[来源2](https://github.com/arminbiere/cadical/blob/rel-3.0.1/src/congruence.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I030 · S10 · Recovered-circuit/residual constraint interface

Distinguishes an internally closed circuit from gate outputs heavily constrained by a non-circuit residual.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；恢复电路与残余约束。操作：输出在非门子句中的incidence比例。
- 条件：已识别门定义并集外部界面。
- 实际列：`graph_circuit_residual_interface`；novelty key：`recognized_circuit_residual_interface`。
- 精确定义：Let O be uniquely defined gate outputs and T the set of defining clauses of retained gates. f=sum_{v in O} #incidences(v,C notin T)/max(1,sum_{v in O}d_v).
- 当前覆盖fit/feedback：**66/180；23/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://research.jku.at/de/publications/extracting-hardware-circuits-from-cnf-formulas/)。仅支持机制背景，不声称文献证明该phase特征有效。

## B04 · I031–I040

配置：[configs/ta100/B04.json](../../configs/ta100/B04.json)；定义源：[configs/ta100/graph_registry_v3.json](../../configs/ta100/graph_registry_v3.json)。提取器源码SHA：`44f7de9321146d4f6ea5d195ac747300e74851fd82e21215ad205c2551a5223e`。完整protocol/registry/依赖/binary/feature-table SHA均在机器目录逐项保存。

### I031 · S31 · Composed forcing-cost direction

Approximates which value is cheaper to force through a whole recovered cone rather than from a local sign count.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；可求值组合门cone。操作：CC0/CC1 forcing-cost递推。
- 条件：排除歧义/循环部分并记录coverage。
- 实际列：`graph_controllability`；novelty key：`circuit_combinational_controllability`。
- 精确定义：On the acyclic evaluable gate portion, primary inputs have CC0=CC1=1. AND literal z: CC0(z)=1+min(CC0(a),CC0(b)); CC1(z)=1+CC1(a)+CC1(b), swapping 0/1 for negated literals. f=mean[(CC1(v)-CC0(v))/(CC1(v)+CC0(v))] over defined outputs.
- 当前覆盖fit/feedback：**65/180；21/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://doi.org/10.1109/TCS.1979.1084687)；[来源2](https://research.jku.at/de/publications/extracting-hardware-circuits-from-cnf-formulas/)。仅支持机制背景，不声称文献证明该phase特征有效。

### I032 · S32 · Signal observability bottleneck

Measures difficulty of exposing an internal signal at an interface, distinct from forcing its value.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；界面向内部的门cone。操作：反向CO observability递推。
- 条件：相同可求值gate portion。
- 实际列：`graph_observability`；novelty key：`circuit_combinational_observability`。
- 精确定义：Initialize CO(v)=0 for recovered outputs used by residual constraints or with no gate consumer. For signed AND z<-a,b, candidate CO(a)=CO(z)+CC1(b)+1 and CO(b)=CO(z)+CC1(a)+1; take minima over consumers. f=mean(CO/(CO+CC0+CC1)) over finite defined outputs.
- 当前覆盖fit/feedback：**65/180；21/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://doi.org/10.1109/TCS.1979.1084687)；[来源2](https://research.jku.at/de/publications/extracting-hardware-circuits-from-cnf-formulas/)。仅支持机制背景，不声称文献证明该phase特征有效。

### I033 · S33 · Opposite-polarity ancestor reuse

Detects local binateness from opposite uses of one source, even when fan-in simply shares variables.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；两hop signed祖先集合。操作：同源相反sign的binate比例。
- 条件：有界cone；非无符号reconvergence。
- 实际列：`graph_binate_cones`；novelty key：`reconvergent_cone_binate_support`。
- 精确定义：For each unambiguous gate cone expanded to two hops, collect signed ancestor literals. f=#cones containing both u and not-u for some ancestor / #fully expanded cones.
- 当前覆盖fit/feedback：**72/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://research.jku.at/de/publications/extracting-hardware-circuits-from-cnf-formulas/)；[来源2](https://arxiv.org/abs/q-bio/0606013)。仅支持机制背景，不声称文献证明该phase特征有效。

### I034 · S34 · Non-template functional local relations

Finds functional structure missed by the reserved local gate and parity libraries.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；3–4变量局部Boolean关系。操作：非保留模板的total函数决定性。
- 条件：排除affine/AND/OR/MAJ/ITE/cardinality。
- 实际列：`graph_other_functional`；novelty key：`non_template_local_functional_determination`。
- 精确定义：For a sampled support S with3..4 variables, evaluate conjunction of all clauses wholly contained in S. Count S if some variable is a total deterministic function of the rest (exactly one output value for every input row), excluding affine, AND/OR, majority, ITE and cardinality/exclusion relations. f=#qualified supports/#evaluated supports.
- 当前覆盖fit/feedback：**115/180；38/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://research.jku.at/de/publications/extracting-hardware-circuits-from-cnf-formulas/)；[来源2](https://arxiv.org/abs/2105.10386)。仅支持机制背景，不声称文献证明该phase特征有效。

### I035 · S35 · Local nested canalization

Measures hierarchical dominating inputs rather than symmetric or parity-like dependence.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；局部Boolean满足谓词。操作：最大嵌套canalization深度。
- 条件：≤16 truth rows；固定有界support。
- 实际列：`graph_canalizing_depth`；novelty key：`local_function_canalizing_hierarchy`。
- 精确定义：For each sampled nonconstant local satisfaction predicate on3..4 variables, recursively find a literal restriction making the predicate constant, continue on the other branch, and maximize chain length. f=mean(max_depth/arity).
- 当前覆盖fit/feedback：**115/180；38/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/q-bio/0606013)。仅支持机制背景，不声称文献证明该phase特征有效。

### I036 · S36 · Nonlinear local algebraic degree

Tests genuine higher-order interaction order, without recovering or counting affine parity equations.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；局部Boolean满足谓词。操作：GF2 ANF最高非零次数。
- 条件：排除affine；不是实数energy Walsh。
- 实际列：`graph_anf_degree`；novelty key：`non_affine_local_polynomial_degree`。
- 精确定义：For each nonconstant local predicate on3..4 variables, compute ANF coefficients by the Boolean Mobius transform; discard affine predicates. f=mean(max nonzero monomial degree/arity).
- 当前覆盖fit/feedback：**111/180；38/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/2105.10386)；[来源2](https://arxiv.org/abs/q-bio/0606013)。仅支持机制背景，不声称文献证明该phase特征有效。
- 非别名见证：This transforms the Boolean satisfaction predicate of a bounded local subformula overGF2 and excludes affine cases. Root Walsh measures real-valued unsatisfied-clause-count energy. Duplicating a clause leaves this Boolean predicate unchanged but changes the root energy: not aliases.

### I037 · S37 · Within-constraint sign bundling

Tests whether like-polarity literals bundle within constraints more than an independent-sign baseline predicts, even when sign-vs-arity first moments agree.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；同arity的clause sign-count。操作：相对独立二项分布的KL。
- 条件：width1..64条件人口；非clause-pair subcube。
- 实际列：`graph_sign_bundling`；novelty key：`within_clause_sign_binomial_deviance`。
- 精确定义：For non-tautological clauses with1<=k<=64, let P_k(j) be the observed clause-frequency distribution of j positive literals conditional on arity k; let p be positive literal fraction in this eligible population. f=sum_k P(k)*KL(P_k || Binomial(k,p)). Degenerate p=0/1 is defined by its exact limiting distribution.
- 当前覆盖fit/feedback：**132/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/cond-mat/0209450)。仅支持机制背景，不声称文献证明该phase特征有效。

### I038 · S38 · Module-to-module encoding disagreement

Detects oppositely encoded modules whose global sign bias cancels.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；样本社区的编码方向。操作：社区间signed bias加权方差。
- 条件：复用固定partition，仅样本变量。
- 实际列：`graph_community_polarity`；novelty key：`community_encoding_polarity_heterogeneity`。
- 精确定义：For the fixed unsigned sample partition from S11, b_g=(positive-negative full-input literal incidences of sampled variables in community g)/literal_count_g. f=sum_g weight_g*(b_g-b_selected)^2, where b_selected is the mean over the sampled variable population.
- 当前覆盖fit/feedback：**130/180；43/60**；状态：`SCORED_COMPLETE`（训练面板中恒定；已记录该负结果）。
- 来源启发：[来源1](https://arxiv.org/abs/1606.03329)；[来源2](https://arxiv.org/abs/cond-mat/0209450)。仅支持机制背景，不声称文献证明该phase特征有效。
- 既有fit数值诊断：`[{"column":"graph_community_polarity","fit_support":130,"kind":"observed_constant","value":0.0}]`。

### I039 · S39 · Local transport contraction

Measures neighborhood convergence/divergence via optimal transportation, not a Laplacian eigenvalue summary.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；邻接节点的lazy邻域测度。操作：16×16最小成本transport曲率。
- 条件：≤32边；经验邻居测度非全图证书。
- 实际列：`graph_transport_curvature`；novelty key：`incidence_lazy_transport_curvature`。
- 精确定义：For each of32 incidence edges u-v, form16 equal atoms approximating each lazy neighborhood measure:8 at the endpoint and8 seeded sampled neighbors. Solve the16x16 minimum-cost assignment with graph-distance costs in{0,1,2,3}. f=mean(1-W1).
- 当前覆盖fit/feedback：**130/180；43/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/math/0701886)。仅支持机制背景，不声称文献证明该phase特征有效。

### I040 · S40 · Cycles surviving triangle filling

Distinguishes genuine higher-order holes from ordinary cycles that are filled by dense local triangles.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；primal clique二复形。操作：triangle-boundary GF2同调beta1。
- 条件：≤96变量；三角形填充后留下的hole。
- 实际列：`graph_betti1`；novelty key：`primal_triangle_filled_cycle_homology`。
- 精确定义：On a <=96-variable induced primal sample, form its clique2-complex. beta1=E-V+components-rank_GF2(boundaries of all triangles); f=beta1/max(1,E).
- 当前覆盖fit/feedback：**82/180；26/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://gudhi.inria.fr/python/latest/simplex_tree_ref.html)。仅支持机制背景，不声称文献证明该phase特征有效。

## B05 · I041–I050

配置：[configs/ta100/B05.json](../../configs/ta100/B05.json)；定义源：[configs/ta100/graph_registry_v3.json](../../configs/ta100/graph_registry_v3.json)。提取器源码SHA：`44f7de9321146d4f6ea5d195ac747300e74851fd82e21215ad205c2551a5223e`。完整protocol/registry/依赖/binary/feature-table SHA均在机器目录逐项保存。

### I041 · S21 · Crossing constraint supports

Measures whether constraint scopes nest as a hierarchy or cross one another.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；子句support对。操作：相交但互不包含的crossing比例。
- 条件：有界support集合。
- 实际列：`graph_laminarity`；novelty key：`hyperedge_nonlaminar_crossing`。
- 精确定义：For sampled distinct support pairs A,B, f=#(A intersect B nonempty and neither A subset B nor B subset A)/#sampled pairs.
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://research.ibm.com/publications/degrees-of-acyclicity-for-hypergraphs-and-relational-database-schemes)。仅支持机制背景，不声称文献证明该phase特征有效。

### I042 · S22 · Neighborhood set-system expressiveness

Measures whether constraint scopes realize unrestricted local set patterns, a bounded VC-dimension witness.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；support set-system。操作：三变量八种交集mask的shattering见证。
- 条件：有界三元组；无literal sign或SAT判定。
- 实际列：`graph_shattering`；novelty key：`incidence_neighborhood_shattering`。
- 精确定义：For tested triples S of variable vertices, collect masks C intersect S. f=#triples realizing all eight masks/#tested triples.
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://doi.org/10.1016/0097-3165(72)90019-2)。仅支持机制背景，不声称文献证明该phase特征有效。

### I043 · S23 · Algebraic boundary complexity

Measures independent boundary neighborhoods in linear-algebraic terms rather than edge density.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；无符号incidence的平衡cut。操作：cross-cut GF2 rank。
- 条件：固定16个样本cut；非逻辑XOR rank。
- 实际列：`graph_cutrank`；novelty key：`incidence_cutrank_complexity`。
- 精确定义：For16 fixed balanced cuts of a <=128-node unsigned incidence sample, compute GF(2) rank of cross-cut adjacency; f=mean(rank/min(side_sizes)).
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://web.math.princeton.edu/~pds/papers/rankwidth/paper.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。
- 非别名见证：Root algebraA11 is signed local clause-row real rank only. Matrices [[1,1],[1,-1]] and [[1,1],[1,1]] have identical unsigned incidence cut-rank but different signed real rank. Object and field differences are explicit, not a raw-rank rename.

### I044 · S24 · Induced-cycle/chordality defect

Detects whether all long induced cycles admit chords, a perfect-elimination structural class.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；primal诱导图。操作：MCS后邻居非clique缺陷。
- 条件：≤96变量；与宽度阈值不同。
- 实际列：`graph_chordality`；novelty key：`primal_chordality_defect`。
- 精确定义：Run maximum cardinality search on a bounded induced primal sample. For each vertex test whether its later neighbors form a clique; f=violating vertices / eligible vertices.
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://web.math.princeton.edu/~pds/papers/rankwidth/paper.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I045 · S25 · Geodesic tree-likeness

Tests thin/tree-like metric geometry even in graphs with many short cycles.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；四点距离结构。操作：归一化Gromov delta。
- 条件：≤128个连通quadruple。
- 实际列：`graph_hyperbolicity`；novelty key：`incidence_metric_hyperbolicity`。
- 精确定义：For128 sampled connected quadruples, sort the three distance-pair sums a>=b>=c; delta=(a-b)/2. f=max(delta)/max(1,sample_diameter).
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www-sop.inria.fr/members/David.Coudert/code/hyperbolicity.shtml)。仅支持机制背景，不声称文献证明该phase特征有效。

### I046 · S26 · Majority/carry functional motifs

Identifies threshold/carry gates rather than AND/OR or affine parity logic.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；六子句majority/carry关系。操作：完整MAJ门输出覆盖。
- 条件：要求全部六句；不计XOR/ITE。
- 实际列：`graph_majority_gate_coverage`；novelty key：`complete_majority_gate_templates`。
- 精确定义：Count complete signed z<->MAJ(a,b,c) six-clause templates: (-a or -b or z),(-a or -c or z),(-b or -c or z),(a or b or -z),(a or c or -z),(b or c or -z). f=#covered output variables/n.
- 当前覆盖fit/feedback：**120/180；39/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://research.jku.at/de/publications/extracting-hardware-circuits-from-cnf-formulas/)。仅支持机制背景，不声称文献证明该phase特征有效。

### I047 · S27 · Reconvergent dataflow diamond

Captures correlated fan-in from a diverged-and-rejoined signal, unlike simple fan-out sharing.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；门依赖fanin。操作：两hop共同祖先reconvergence。
- 条件：唯一、完整门；截断cone不作零。
- 实际列：`graph_reconvergence`；novelty key：`recognized_gate_reconvergence`。
- 精确定义：For each retained gate z<-a,b, check whether a,b have a common defined ancestor within two gate hops. f=#such gates/#eligible retained gates.
- 当前覆盖fit/feedback：**63/180；21/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://research.jku.at/de/publications/extracting-hardware-circuits-from-cnf-formulas/)；[来源2](https://pubmed.ncbi.nlm.nih.gov/12399590/)。仅支持机制背景，不声称文献证明该phase特征有效。

### I048 · S28 · Gate output encoding direction

Restores the absolute output orientation discarded by unsigned template coverage.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；门输出literal。操作：signed AND输出正负方向差。
- 条件：保留绝对输出orientation。
- 实际列：`graph_gate_output_direction`；novelty key：`recognized_gate_output_polarity`。
- 精确定义：For retained signed AND templates z<->(a and b), f=(#z>0-#z<0)/#retained gates.
- 当前覆盖fit/feedback：**63/180；21/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://research.jku.at/de/publications/extracting-hardware-circuits-from-cnf-formulas/)。仅支持机制背景，不声称文献证明该phase特征有效。

### I049 · S29 · Competing functional definitions

Tests functional aliasing/competing local explanations, which can invalidate a single recovered DAG.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；变量的局部函数定义。操作：多个完整定义的歧义比例。
- 条件：精确重复不是新定义。
- 实际列：`graph_gate_ambiguity`；novelty key：`gate_definition_ambiguity`。
- 精确定义：f=#variables with more than one distinct complete gate-definition signature/#variables with at least one complete definition.
- 当前覆盖fit/feedback：**63/180；21/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://research.jku.at/de/publications/extracting-hardware-circuits-from-cnf-formulas/)。仅支持机制背景，不声称文献证明该phase特征有效。

### I050 · S30 · Repeated computed-function congruence

Finds multiple variables that compute the same function of the same signals, even without identical clauses.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；signed input-pair函数类。操作：重复计算同函数的congruence。
- 条件：不要求输出变量拥有相同外部邻域。
- 实际列：`graph_gate_congruence`；novelty key：`circuit_structural_congruence`。
- 精确定义：Group unambiguous signed AND gates by normalized signed input pair; f=sum_classes max(0,class_size-1)/#retained_gates.
- 当前覆盖fit/feedback：**63/180；21/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/rel-3.0.1/src/congruence.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

## B06 · I051–I060

配置：[configs/ta100/B06.json](../../configs/ta100/B06.json)；定义源：[configs/ta100/graph_registry_v3.json](../../configs/ta100/graph_registry_v3.json)。提取器源码SHA：`44f7de9321146d4f6ea5d195ac747300e74851fd82e21215ad205c2551a5223e`。完整protocol/registry/依赖/binary/feature-table SHA均在机器目录逐项保存。

### I051 · S11 · Constraint communities

Separates strongly localized modules from globally intertwined constraints.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；有界incidence样本的社区。操作：四轮label传播后的modularity。
- 条件：≤128节点固定样本；非全图最优值。
- 实际列：`graph_modularity`；novelty key：`unsigned_constraint_community_modularity`。
- 精确定义：Q=sum_g[e_g/E-(vol_g/(2E))^2] for the unsigned bounded incidence sample partition from four fixed label-propagation sweeps.
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（训练面板中恒定；已记录该负结果）。
- 来源启发：[来源1](https://arxiv.org/abs/1606.03329)。仅支持机制背景，不声称文献证明该phase特征有效。
- 既有fit数值诊断：`[{"column":"graph_modularity","fit_support":125,"kind":"observed_constant","value":0.0}]`。

### I052 · S12 · Metric self-similarity

Tests multi-scale self-similarity, rather than one connectivity or degree statistic.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；图距离几何。操作：半径1/2/4球覆盖的log斜率。
- 条件：≤128节点样本；非全图fractal维数证书。
- 实际列：`graph_box_scaling`；novelty key：`incidence_box_cover_scaling`。
- 精确定义：Fit the slope d=-slope(log r,log N_cover(r)) for r=1,2,4 on a fixed bounded incidence neighborhood; N_cover is greedy radius-r ball cover.
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/1308.5046)。仅支持机制背景，不声称文献证明该phase特征有效。

### I053 · S13 · Planarity obstruction witness

Finds unavoidable nonplanar wiring, a topological obstruction to planar separator intuition.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；incidence非平面wiring。操作：K3,3共同邻居见证率。
- 条件：有界变量三元组；零不证明平面。
- 实际列：`graph_k33_witness`；novelty key：`incidence_nonplanar_minor_witness`。
- 精确定义：f=#tested variable triples with at least three common clause neighbors / #tested triples; each success is an explicit K3,3 subgraph witness.
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://jgaa.info/index.php/jgaa/article/view/paper91)。仅支持机制背景，不声称文献证明该phase特征有效。

### I054 · S14 · Induced elimination width

Measures separator width required by an elimination ordering rather than literal resolvent growth.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；primal样本分解。操作：贪心min-fill消除宽度。
- 条件：≤96变量诱导样本；非全图treewidth证书。
- 实际列：`graph_elimination_width`；novelty key：`primal_elimination_separator_width`。
- 精确定义：On a fixed <=96-variable induced primal sample, repeatedly remove the vertex with minimum fill-edge count; f=max live-neighbor count / max(1,sample_variables-1).
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://web.math.princeton.edu/~pds/papers/rankwidth/paper.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I055 · S15 · Random-deletion connectivity robustness

Measures distributed connectivity resilience under many simultaneous removals, distinct from a single articulation bottleneck.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；多点随机删除后的连接。操作：最大分量曲线AUC。
- 条件：固定删除率与种子；非逻辑restriction。
- 实际列：`graph_percolation`；novelty key：`unsigned_vertex_percolation_robustness`。
- 精确定义：For fixed deletion rates q=0,1/4,1/2,3/4,1 on a <=128-node incidence sample, measure largest surviving variable-component fraction (zero if no survivors); average three seeds at interior q; f is the trapezoidal area on[0,1].
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/cond-mat/0209450)。仅支持机制背景，不声称文献证明该phase特征有效。

### I056 · S16 · Shortest-path load centralization

Finds vertices through which many shortest information paths pass, including non-articulation bottlenecks.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；无向最短路径流。操作：最大归一化betweenness。
- 条件：固定16个源的有界样本。
- 实际列：`graph_betweenness`；novelty key：`geodesic_flow_bottleneck`。
- 精确定义：On a <=128-node incidence sample, compute Brandes betweenness for 16 fixed source vertices; f=max normalized internal-vertex dependency.
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://cs.yale.edu/publications/techreports/tr1029.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I057 · S17 · Metric access efficiency

Measures usable global access distance, distinct from self-similar cover scaling or walk returns.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；变量对距离。操作：倒数距离平均。
- 条件：有界样本；不连通对计零。
- 实际列：`graph_harmonic_access`；novelty key：`incidence_harmonic_access_distance`。
- 精确定义：f=mean_{distinct connected sampled variable pairs}(1/d_incidence(u,v)); disconnected pairs contribute zero.
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www.cs.ubc.ca/labs/algorithms/Projects/SATzilla/Report_SAT_features.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I058 · S18 · Alternative-path detour

Measures how efficiently alternative routes replace a direct edge, beyond whether the edge is merely a bridge.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；删去单边后的替代路径。操作：倒数detour长度平均。
- 条件：≤32样本边；断开取零。
- 实际列：`graph_detour`；novelty key：`incidence_replacement_path_detour`。
- 精确定义：For up to32 sampled incidence edges e=(u,v), remove e and find d_{G-e}(u,v); f=mean(1/d), taking zero when disconnected.
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://cs.yale.edu/publications/techreports/tr1029.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I059 · S19 · Nonbacktracking branch growth

Measures onward branching once immediate edge reversal is forbidden.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；不立即反向的有向边walk。操作：三步nonbacktracking增长。
- 条件：有界样本；非普通walk返回率。
- 实际列：`graph_nonbacktracking`；novelty key：`incidence_nonbacktracking_branch_growth`。
- 精确定义：Let x_0(u->v)=1 and x_{t+1}(u->v)=sum_{w in N(v),w!=u} x_t(v->w). f=sum x_3 / max(1,sum x_2).
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://cs.yale.edu/publications/techreports/tr1029.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I060 · S20 · Unsigned join-tree reducibility

Tests alpha-acyclic join structure, which can be reducible even when the incidence graph has cycles.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；无符号support超图。操作：GYO删除后的剩余质量。
- 条件：有界sample；与signed subsumption不同。
- 实际列：`graph_gyo`；novelty key：`hypergraph_join_tree_reducibility`。
- 精确定义：Run GYO rules on sampled variable-support hyperedges: delete degree<=1 variables and contained support edges to a fixed point. f=remaining incidence mass / initial incidence mass.
- 当前覆盖fit/feedback：**125/180；40/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://research.ibm.com/publications/degrees-of-acyclicity-for-hypergraphs-and-relational-database-schemes)；[来源2](https://web.cecs.pdx.edu/~maier/TheoryBook/MAIER/C13.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

## B07 · I061–I070

配置：[configs/ta100/B07.json](../../configs/ta100/B07.json)；定义源：[configs/ta100/algebra_registry_v1.json](../../configs/ta100/algebra_registry_v1.json)。提取器源码SHA：`7d847b3727af046838299c5d670d7891a22df83c2b382b6c47235f0faa58834d`。完整protocol/registry/依赖/binary/feature-table SHA均在机器目录逐项保存。

### I061 · RA01 · Approximate renamable-Horn deficit

Encoding orientation relative to a tractable constraint class.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_fixed_iteration`）；变量sign重命名与子句正literal对。操作：12轮coordinate下降。
- 条件：F*；不称精确renamable-Horn。
- 实际列：`algebra_renamable_horn_deficit`；novelty key：`horn_variable_orientation_pair_deficit`。
- 精确定义：Minimize sum_C choose(np_C,2) under variable sign flips. Starting with no flips, run12 coordinate passes in local first-appearance variable order; flip only on strict reduction. Divide final violated pairs by sum_C choose(width_C,2).
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://people.mpi-inf.mpg.de/~mehlhorn/ftp/RenamingHorn.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I062 · RA02 · Optimized signed coupling frustration

Frustration remaining after a bounded gauge search.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_fixed_iteration`）；signed pairwise coupling J。操作：12轮spin下降后的frustration。
- 条件：F*；有非零|J|质量。
- 实际列：`algebra_ising_frustration`；novelty key：`signed_pairwise_optimized_gauge_frustration`。
- 精确定义：J_ij=sum_C 2^-width_C sign_i sign_j over distinct variable pairs. Start all spins+1;12 greedy coordinate sweeps minimize sum J_ij s_i s_j, flipping only on strict decrease. Return |J| mass with J_ij s_i s_j>0 divided by total |J|.
- 当前覆盖fit/feedback：**132/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www.cs.cornell.edu/~rdz/Papers/KZ-PAMI04.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I063 · RA03 · Raw-coordinate submodular coupling fraction

How much pairwise interaction already has the submodular coefficient sign in raw coordinates.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；raw signed coupling J。操作：负系数|J|质量比例。
- 条件：原坐标；不进行gauge优化。
- 实际列：`algebra_raw_submodular_fraction`；novelty key：`signed_pairwise_raw_gauge_submodular_mass`。
- 精确定义：For the same raw J, return sum_{J_ij<0}|J_ij|/sum|J_ij|. No spin or gauge optimization.
- 当前覆盖fit/feedback：**132/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www.cs.cornell.edu/~rdz/Papers/KZ-PAMI04.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。
- 非别名见证：RA02 optimizes a spin configuration and counts positive residual terms; RA03 does no optimization and counts negative raw coefficients. Positive triangle yields RA02=1/3,RA03=0; all-negative triangle yields0,1.

### I064 · RA04 · Literal-complement clause pairing

Global complement symmetry of constraint language.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；完整signed clause多重集。操作：literal-complement配对。
- 条件：F*；保留重复row。
- 实际列：`algebra_literal_complement_pairing`；novelty key：`full_clause_literal_complement_symmetry`。
- 精确定义：Fraction of F* clause rows whose sorted all-literal negation also appears in F*. Duplicate rows remain in the fraction; an empty clause is its own complement.
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/2105.10386)。仅支持机制背景，不声称文献证明该phase特征有效。

### I065 · RA05 · Verified bounded majority autarky

Self-satisfying removable support under a fixed assignment.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_fixed_iteration`）；固定majority下的变量集合。操作：验证后的autarky剥离固定点。
- 条件：F*；≤128轮且实际条件验证。
- 实际列：`algebra_majority_autarky_support`；novelty key：`majority_assignment_autarky_fixedpoint_support`。
- 精确定义：Set each variable to its F* majority sign, ties true. Start S=all active variables; synchronously remove every S variable in any clause touched by S but unsatisfied by all S-assigned literals. At most128 passes; verify every remaining touched clause is satisfied. Return |S|/n.
- 当前覆盖fit/feedback：**132/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/1103.3693)。仅支持机制背景，不声称文献证明该phase特征有效。

### I066 · RA06 · Exact Hall matching deficiency

Deficit of distinct variable resources for constraints.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；clause-variable二部图。操作：精确最大matching deficiency。
- 条件：F*；空子句为unmatched row。
- 实际列：`algebra_hall_deficiency`；novelty key：`clause_variable_max_matching_deficiency`。
- 精确定义：Compute exact maximum clause-variable bipartite matching on F*. Return(m-matching_size)/m; empty clauses are unmatched rows, without adopting a SAT answer.
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/1103.3693)。仅支持机制背景，不声称文献证明该phase特征有效。

### I067 · RA07 · Greedy cover-packing gap

Gap between disjoint constraint demands and a shared variable hitting cover.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；变量不相交clauses与hitting变量。操作：贪心cover-packing差。
- 条件：F*；空子句使cover未定义。
- 实际列：`algebra_cover_packing_gap`；novelty key：`clause_packing_variable_cover_duality_gap`。
- 精确定义：Greedily pack variable-disjoint clauses by(width,original clause ID). Greedily hit uncovered clauses by maximum uncovered occurrence, ties lowest original variable ID. Return(cover_size-packing_size)/m.
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/1103.3693)。仅支持机制背景，不声称文献证明该phase特征有效。

### I068 · RA08 · Signed leading-mode/bias alignment

Alignment of aggregate linear pressure with a strong signed interaction direction.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_fixed_iteration`）；signed J与线性bias h。操作：16步mode与h绝对对齐。
- 条件：F*；零mode或bias范数缺失。
- 实际列：`algebra_signed_mode_alignment`；novelty key：`signed_pairwise_mode_linear_bias_alignment`。
- 精确定义：Use16 normalized sparse J power steps, starting x_i=sin(1.7*(i+1)). Let h_i=-sum_C sign_i2^-width_C. Return|dot(x,h)|/||h||, where x is unit norm.
- 当前覆盖fit/feedback：**127/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www.cs.cornell.edu/~rdz/Papers/KZ-PAMI04.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I069 · RA09 · Fixed convex fractional pressure proxy

Fractional directional pressure after relaxation of clause satisfaction.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_fixed_iteration`）；分数变量的convex hinge目标。操作：64步投影subgradient后的方向。
- 条件：F*；固定算法，非LP最优解。
- 实际列：`algebra_convex_fractional_pressure`；novelty key：`fixed_convex_hinge_fractional_polarity`。
- 精确定义：Starting x=.5,64 projected subgradient steps minimize sum_C max(0,1-sum_l truth(l))+.05sum_i(x_i-.5)^2-h_i*x_i, h_i=(pos_i-neg_i)/degree_i. eta=.05/sqrt(t+1)/sqrt(maxdegree); clip[0,1]. Return mean(x-.5).
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.27)；[来源2](https://www.cs.ubc.ca/labs/algorithms/Projects/SATzilla/Report_SAT_features.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I070 · RA10 · Loopy BP cavity polarity

Nonlinear clause-to-variable cavity pressure.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_fixed_iteration`）；OR-factor cavity messages。操作：12轮同步阻尼BP后的方向。
- 条件：F*；clamp固定，不称真实marginal。
- 实际列：`algebra_bp_cavity_polarity`；novelty key：`fixed_damped_or_factor_cavity_polarization`。
- 精确定义：Uniform prior;12 synchronous OR-factor sweeps damped.5. Factor-to-variable log odds are sign(l)*[-log(1-product(other literal false probabilities))]; cavity excludes that factor. Clamp probability to[1e-9,1-1e-9] and log odds to[-20,20]. Return mean(2*p_i-1).
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www.merl.com/publications/docs/TR2001-22.pdf)；[来源2](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.27)。仅支持机制背景，不声称文献证明该phase特征有效。

## B08 · I071–I080

配置：[configs/ta100/B08.json](../../configs/ta100/B08.json)；定义源：[configs/ta100/algebra_registry_v1.json](../../configs/ta100/algebra_registry_v1.json)。提取器源码SHA：`7d847b3727af046838299c5d670d7891a22df83c2b382b6c47235f0faa58834d`。完整protocol/registry/依赖/binary/feature-table SHA均在机器目录逐项保存。

### I071 · RA11 · Signed real-row rank deficiency

Signed linear constraint-direction dependence.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；signed clause-row实数矩阵。操作：Gaussian numerical rank deficiency。
- 条件：first64 F*行；≤1024列；1e-9 pivot。
- 实际列：`algebra_signed_real_rank_deficit`；novelty key：`signed_clause_row_real_rank_deficiency`。
- 精确定义：First64 F* rows; columns are exactly their variables,<=1024. Entries are literal signs. Gaussian partial pivoting with absolute1e-9 pivot threshold. Return1-rank/min(rows,columns).
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/2105.10386)。仅支持机制背景，不声称文献证明该phase特征有效。
- 非别名见证：Graph S23 uses unsigned graph-cut GF2 rank. [[1,1],[1,-1]] vs [[1,1],[1,1]] has identical unsigned incidence but different signed real rank.

### I072 · RA12 · High-order real energy Walsh mass

Higher-order interaction energy beyond linear/quadratic terms.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；实数unsatisfied-clause-count energy。操作：degree≥3 Walsh平方质量。
- 条件：first128 F* width≤8；保留duplicate。
- 实际列：`algebra_high_order_walsh_mass`；novelty key：`real_unsatisfied_count_energy_high_order_walsh`。
- 精确定义：Take first128 F* clauses of width<=8. Expand each U_C=2^-k product_l(1-sign(l)*z_v). Sum coefficients by variable subset with duplicate clauses retained. Return sum_{degree>=3} coefficient^2 / sum_{nonconstant} coefficient^2.
- 当前覆盖fit/feedback：**132/180；43/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/2105.10386)。仅支持机制背景，不声称文献证明该phase特征有效。
- 非别名见证：Graph S36 transforms a Boolean local conjunction predicate overGF2 and excludes affine cases. Duplicating one clause can change this real energy Walsh ratio while leaving that Boolean predicate unchanged; synthetic mixed-width witness verifies the difference.

### I073 · RA13 · Canonical-name LZ78 structural description

Repeated description/grammar in encoding order.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；canonical-name signed token流。操作：LZ78描述比。
- 条件：F*首次出现变量编号；明确order-sensitive。
- 实际列：`algebra_canonical_lz78_ratio`；novelty key：`first_appearance_signed_cnf_lz78_description`。
- 精确定义：Stream F* canonical signed literals in original clause traversal order, renaming variables by first appearance, with0 delimiters. LZ78 phrase factorization counts a final unmatched prefix as a reference phrase. Return phrase_count*log2(max(2,phrase_count))/(tokens*log2(2*n+1)).
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://cs.nyu.edu/home/people/in_memoriam/roweis/csc310-2006/extras/ziv_lempel_1978_variable-rate.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I074 · RA14 · Cooperative two-flip escape

Synergistic escape invisible to single-flip gains.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_auxiliary_landscape`）；majority附近LOCALcube。操作：双翻优于所有单翻的合作比例。
- 条件：top12 degree变量，其余固定majority。
- 实际列：`algebra_two_flip_cooperative_escape`；novelty key：`majority_local_cube_cooperative_two_flip_escape`。
- 精确定义：On the fixed LOCALcube, fraction of q-choose2 bit pairs with E(reference)-E(joint_flip)>0 while each individual gain<=0.
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.27)。仅支持机制背景，不声称文献证明该phase特征有效。

### I075 · RA15 · Majority plateau connectedness

Topology of neutral moves, not merely first-flip gain.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_auxiliary_landscape`）；相同energy的LOCALcube子图。操作：参考点所在中性连通分量。
- 条件：q=0前瞻缺失；非单翻gain。
- 实际列：`algebra_plateau_connectedness`；novelty key：`majority_local_cube_equal_energy_connectivity`。
- 精确定义：Exact BFS component of the majority reference using only hypercube edges whose endpoint energies both equal the reference energy. Return component_size/2^q.
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.27)。仅支持机制背景，不声称文献证明该phase特征有效。

### I076 · RA16 · Fixed local-walk state recurrence

Revisitation/cycling in a finite stochastic local landscape.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_auxiliary_trajectory`）；LOCALcube上固定noisy walk状态。操作：128步state recurrence。
- 条件：seed0；总129状态；允许uphill。
- 实际列：`algebra_sls_state_recurrence`；novelty key：`fixed_noisy_walk_local_cube_state_recurrence`。
- 精确定义：Starting at the majority reference,128 steps: with probability1/16 choose a random bit; otherwise choose a minimum-energy neighbor, ties randomized. Always move even uphill. mt19937 seed0, decisions via integer modulo. Return1-unique_visited_states/129.
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.27)；[来源2](https://www.cs.ubc.ca/labs/algorithms/Projects/SATzilla/Report_SAT_features.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I077 · RA17 · Persistent unsatisfied constraint core

Constraint persistence across movement, a different object from state recurrence or plateau geometry.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_auxiliary_trajectory`）；同一walk触及的clauses。操作：持续129状态均unsat的约束比例。
- 条件：仅触及local core且曾unsat的clauses。
- 实际列：`algebra_persistent_unsat_core`；novelty key：`fixed_noisy_walk_persistent_constraint_identity`。
- 精确定义：Using exactly the same129-state trajectory as RA16, among clauses touching the LOCALcube and violated at least once, return the fraction violated in all129 states.
- 当前覆盖fit/feedback：**118/180；38/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.27)。仅支持机制背景，不声称文献证明该phase特征有效。

### I078 · RA18 · Falsifying-subcube covariance

Relative overlap or exclusion of falsifying assignment regions.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；clause-pair falsifying subcubes。操作：精确joint-product相对差。
- 条件：F*所有pair；不是within-clause KL。
- 实际列：`algebra_falsifying_subcube_covariance`；novelty key：`clause_pair_uniform_falsifying_subcube_overlap`。
- 精确定义：All unordered F* clause pairs: P(U_C)=2^-k. Joint probability is0 on any shared opposite literal, otherwise2^-|union variables|. Return sum_pairs(joint-P_C*P_D)/sum_pairs(joint+P_C*P_D).
- 当前覆盖fit/feedback：**134/180；44/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/2105.10386)。仅支持机制背景，不声称文献证明该phase特征有效。

### I079 · NODE_EX01 · 覆盖literal交集暴露

mean_{eligible(C,l)} |(intersection_{D in RC(F,C,l)} (D\{-l}))\C|, RC contains exactly non-tautological resolvent partners.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；covered-literal resolution候选环境。操作：非重言RC的literal intersection减去原clause。
- 条件：first256 context；完整admitted complementary环境。
- 实际列：`f_core_covered_intersection`；novelty key：`covered_literal_candidate_intersection`。
- 精确定义：mean_{eligible(C,l)} |(intersection_{D in RC(F,C,l)} (D\{-l}))\C|, RC contains exactly non-tautological resolvent partners.
- 当前覆盖fit/feedback：**108/180；38/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://arxiv.org/abs/1011.5202)。仅支持机制背景，不声称文献证明该phase特征有效。

### I080 · NODE_EX02 · 完整ITE输出覆盖

number of distinct absolute output variables y with complete (-s,-a,y),(-s,a,-y),(s,-b,y),(s,b,-y) certificate / number of distinct context variables; |y|,|s|,|a|,|b| all distinct.

- 类型/对象：**输入侧结构/有界辅助计算**（`input_structural_or_algebraic`）；四个不同变量的ITE/MUX关系。操作：完整四子句输出覆盖。
- 条件：first256 ternary context；四句必须齐备。
- 实际列：`f_core_ite_output`；novelty key：`complete_four_clause_ite_function`。
- 精确定义：number of distinct absolute output variables y with complete (-s,-a,y),(-s,a,-y),(s,-b,y),(s,b,-y) certificate / number of distinct context variables; |y|,|s|,|a|,|b| all distinct.
- 当前覆盖fit/feedback：**106/180；39/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://cca.informatik.uni-freiburg.de/papers/FleuryBiere-FMSD22.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

## B09 · I081–I090

配置：[configs/ta100/B09.json](../../configs/ta100/B09.json)；定义源：[configs/ta100/dynamic_registry_v2.json](../../configs/ta100/dynamic_registry_v2.json)。提取器源码SHA：`3ebb653dbd66f2c4a166fbde154fb2e342cec428a86fa5aa42b40ddb397e2e74`。完整protocol/registry/依赖/binary/feature-table SHA均在机器目录逐项保存。

### I081 · TD11 · 新学习子句中全正与全负子句的差，占非空学习子句数。

新学习子句中全正与全负子句的差，占非空学习子句数。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；新学习clause的sign构成。操作：全正/全负coherence差。
- 条件：非空学习clauses；未到checkpoint缺失。
- 实际列：`td_learned_pure_sign_balance`；novelty key：`learned_clause_sign_coherence`。
- 精确定义：新学习子句中全正与全负子句的差，占非空学习子句数。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)；[来源2](https://www.cs.toronto.edu/~meel/Papers/sat20-sm.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I082 · TD12 · 带唯一决策祖先的抽样隐含赋值中，隐含文字符号与该决策祖先符号一致的比例减去不一致比例。

带唯一决策祖先的抽样隐含赋值中，隐含文字符号与该决策祖先符号一致的比例减去不一致比例。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；有唯一决策祖先的隐含赋值。操作：祖先sign传播对齐。
- 条件：固定sample与唯一祖先条件。
- 实际列：`td_reason_sign_transmission`；novelty key：`implication_sign_transmission`。
- 精确定义：带唯一决策祖先的抽样隐含赋值中，隐含文字符号与该决策祖先符号一致的比例减去不一致比例。
- 当前覆盖fit/feedback：**7/180；1/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/propagate.cpp)；[来源2](https://www.cs.toronto.edu/~fbacchus/csc2512/Readings/Pipatsrisawat-Darwiche2007_Chapter_ALightweightComponentCachingSc.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I083 · TD13 · 本前缀内赋值并撤销且观测完整的正负赋值，其以冲突数计的平均存活期差。

本前缀内赋值并撤销且观测完整的正负赋值，其以冲突数计的平均存活期差。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；已完整观测的赋值生命周期。操作：负/正平均存活期差。
- 条件：明确发生撤销；右删失不伪造。
- 实际列：`td_sign_lifetime_gap`；novelty key：`phase_assignment_persistence`。
- 精确定义：本前缀内赋值并撤销且观测完整的正负赋值，其以冲突数计的平均存活期差。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/propagate.cpp)；[来源2](https://www.cs.toronto.edu/~meel/Papers/sat20-sm.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I084 · TD14 · 主冲突分析中消耗的不同reason子句数量相对于最终1UIP子句文字数的平均比。

主冲突分析中消耗的不同reason子句数量相对于最终1UIP子句文字数的平均比。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；主冲突resolution使用的reasons。操作：不同reason数/最终1UIP宽度。
- 条件：最终有效学习clause事件。
- 实际列：`td_resolution_compression`；novelty key：`resolution_proof_compression`。
- 精确定义：主冲突分析中消耗的不同reason子句数量相对于最终1UIP子句文字数的平均比。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)；[来源2](https://fmv.jku.at/papers/FleuryBiere-SAT2021.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I085 · TD15 · 固定抽样冲突文字至最近决策/根文字的最长理由祖先深度中位数。

固定抽样冲突文字至最近决策/根文字的最长理由祖先深度中位数。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；冲突literal到决策/root的reason链。操作：最长祖先路径深度中位数。
- 条件：固定冲突literal sample。
- 实际列：`td_reason_depth`；novelty key：`implication_ancestry_depth`。
- 精确定义：固定抽样冲突文字至最近决策/根文字的最长理由祖先深度中位数。
- 当前覆盖fit/feedback：**10/180；1/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/propagate.cpp)；[来源2](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I086 · TD16 · 抽样祖先遍历中再次碰到已访问祖先的边数占总祖先边数。

抽样祖先遍历中再次碰到已访问祖先的边数占总祖先边数。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；reason祖先遍历边。操作：重新访问祖先的reconvergence。
- 条件：固定有界祖先遍历。
- 实际列：`td_reason_reconvergence`；novelty key：`implication_dag_reconvergence`。
- 精确定义：抽样祖先遍历中再次碰到已访问祖先的边数占总祖先边数。
- 当前覆盖fit/feedback：**10/180；1/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)；[来源2](https://fmv.jku.at/papers/FleuryBiere-SAT2021.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I087 · TD17 · 当前决策层中，1UIP在trail上距层尾的相对位置的均值。

当前决策层中，1UIP在trail上距层尾的相对位置的均值。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；当前decision level的trail。操作：1UIP到层尾相对位置。
- 条件：最终1UIP与当前层trail长度。
- 实际列：`td_uip_trail_localization`；novelty key：`uip_conflict_locality`。
- 精确定义：当前决策层中，1UIP在trail上距层尾的相对位置的均值。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I088 · TD18 · 每个最终学习子句按其文字decision level占比计算归一化熵，再取前缀均值。

每个最终学习子句按其文字decision level占比计算归一化熵，再取前缀均值。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；学习clause按decision level的占比。操作：normalized level entropy。
- 条件：单层clause按冻结定义取0。
- 实际列：`td_cut_level_entropy`；novelty key：`conflict_cut_level_occupancy`。
- 精确定义：每个最终学习子句按其文字decision level占比计算归一化熵，再取前缀均值。
- 当前覆盖fit/feedback：**76/180；22/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://www.ijcai.org/Proceedings/09/Papers/074.pdf)；[来源2](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I089 · TD19v2 · 每个新学习子句仅当其所有变量TARGET phase已定义时可评价；计算可完整评价学习子句被既有TARGET向量全部否定的比例。无可评价事件为null，未知target事件不当作0。

每个新学习子句仅当其所有变量TARGET phase已定义时可评价；计算可完整评价学习子句被既有TARGET向量全部否定的比例。无可评价事件为null，未知target事件不当作0。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；完整已定义TARGET向量下的学习clause。操作：TARGET全部否定兼容率。
- 条件：仅完整可评价事件；替换旧TD19。
- 实际列：`td_clause_target_phase_violation`；novelty key：`learned_target_memory_constraint_compatibility`。
- 精确定义：每个新学习子句仅当其所有变量TARGET phase已定义时可评价；计算可完整评价学习子句被既有TARGET向量全部否定的比例。无可评价事件为null，未知target事件不当作0。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/decide.cpp)；[来源2](https://www.cs.toronto.edu/~fbacchus/csc2512/Readings/Pipatsrisawat-Darwiche2007_Chapter_ALightweightComponentCachingSc.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I090 · TD20 · 两个相邻固定128分析冲突窗口中，被分析变量集合的Jaccard距离。

两个相邻固定128分析冲突窗口中，被分析变量集合的Jaccard距离。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；相邻128冲突窗口的分析变量集。操作：bottom-k Jaccard turnover。
- 条件：固定k256与seed；非精确全set声称。
- 实际列：`td_conflict_variable_turnover`；novelty key：`search_region_turnover`。
- 精确定义：两个相邻固定128分析冲突窗口中，被分析变量集合的Jaccard距离。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

## B10 · I091–I100

配置：[configs/ta100/B10.json](../../configs/ta100/B10.json)；定义源：[configs/ta100/dynamic_registry_v2.json](../../configs/ta100/dynamic_registry_v2.json)。提取器源码SHA：`3ebb653dbd66f2c4a166fbde154fb2e342cec428a86fa5aa42b40ddb397e2e74`。完整protocol/registry/依赖/binary/feature-table SHA均在机器目录逐项保存。

### I091 · TD21 · 前缀变量冲突分析bump计数分布的Herfindahl指数。

前缀变量冲突分析bump计数分布的Herfindahl指数。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；冲突分析variable bump计数。操作：Herfindahl注意力集中度。
- 条件：共同动作前prefix；非原始activity尺度。
- 实际列：`td_bump_concentration`；novelty key：`search_attention_concentration`。
- 精确定义：前缀变量冲突分析bump计数分布的Herfindahl指数。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I092 · TD22 · 最近抽样256学习子句变量，在动作前checkpoint当前activity前10%中的占比相对基准0.1的偏离。

最近抽样256学习子句变量，在动作前checkpoint当前activity前10%中的占比相对基准0.1的偏离。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；最近学习clause变量与checkpoint activity rank。操作：top decile enrichment。
- 条件：当前动作前rank，非历史pre-bump rank。
- 实际列：`td_activity_rank_enrichment`；novelty key：`conflict_activity_rank_localization`。
- 精确定义：最近抽样256学习子句变量，在动作前checkpoint当前activity前10%中的占比相对基准0.1的偏离。
- 当前覆盖fit/feedback：**62/180；22/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I093 · TD23 · 最近128学习子句分别与前一128窗口的最近文字集合相似度均值；符号保留。

最近128学习子句分别与前一128窗口的最近文字集合相似度均值；符号保留。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；相邻128学习clause窗口。操作：signed minhash最近复发相似度。
- 条件：每clause固定8 minhash。
- 实际列：`td_learned_recurrence`；novelty key：`learned_constraint_recurrence`。
- 精确定义：最近128学习子句分别与前一128窗口的最近文字集合相似度均值；符号保留。
- 当前覆盖fit/feedback：**78/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)；[来源2](https://www.cs.toronto.edu/~fbacchus/csc2512/Readings/Pipatsrisawat-Darwiche2007_Chapter_ALightweightComponentCachingSc.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I094 · TD24v2 · 固定bottom-k256学习子句样本中，明确跳过定义该子句的birth driving assertion后，首次再次作为reason使用的冲突年龄中位数；未复用者保持右删失。

固定bottom-k256学习子句样本中，明确跳过定义该子句的birth driving assertion后，首次再次作为reason使用的冲突年龄中位数；未复用者保持右删失。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；学习lemma首次后续reason复用。操作：跳过birth assertion的复用年龄。
- 条件：bottom-k256；右删失；替换旧TD24。
- 实际列：`td_learned_postassertion_reuse_age`；novelty key：`learned_lemma_postassertion_reuse_latency`。
- 精确定义：固定bottom-k256学习子句样本中，明确跳过定义该子句的birth driving assertion后，首次再次作为reason使用的冲突年龄中位数；未复用者保持右删失。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/propagate.cpp)；[来源2](https://www.ijcai.org/Proceedings/09/Papers/074.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I095 · TD25 · 主搜索传播检查中，因blocking literal已满足而跳过reason子句读取的比例。

主搜索传播检查中，因blocking literal已满足而跳过reason子句读取的比例。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；传播watch entries。操作：blocking-literal shortcut成功率。
- 条件：只加计数，不改变watch顺序。
- 实际列：`td_blocker_success_share`；novelty key：`watcher_short_circuit_success`。
- 精确定义：主搜索传播检查中，因blocking literal已满足而跳过reason子句读取的比例。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/propagate.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I096 · TD26 · 重启前被赋值的固定样本中，重启后仍赋同一符号的负赋值保留率减去正赋值保留率。

重启前被赋值的固定样本中，重启后仍赋同一符号的负赋值保留率减去正赋值保留率。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；restart前后相同变量赋值。操作：负/正same-sign保留率差。
- 条件：同256样本，两个sign均需支持。
- 实际列：`td_restart_signed_retention`；novelty key：`restart_signed_state_retention`。
- 精确定义：重启前被赋值的固定样本中，重启后仍赋同一符号的负赋值保留率减去正赋值保留率。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/restart.cpp)；[来源2](https://www.cs.toronto.edu/~fbacchus/csc2512/Readings/Pipatsrisawat-Darwiche2007_Chapter_ALightweightComponentCachingSc.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I097 · TD27 · chronological回退后，同一变量下次自由决策与撤销赋值符号不同的比例。

chronological回退后，同一变量下次自由决策与撤销赋值符号不同的比例。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；chrono撤销后同变量下次decision。操作：signed redecision transition。
- 条件：匹配后消费状态，非边际saved比例。
- 实际列：`td_chrono_redecision_flip`；novelty key：`chronological_phase_transition`。
- 精确定义：chronological回退后，同一变量下次自由决策与撤销赋值符号不同的比例。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://www.cs.toronto.edu/~meel/Papers/sat20-sm.pdf)；[来源2](https://github.com/arminbiere/cadical/blob/master/src/decide.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I098 · TD28 · 相邻主分析冲突间自由决策数间隔的变异系数；不是间隔均值。

相邻主分析冲突间自由决策数间隔的变异系数；不是间隔均值。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；相邻冲突的decision gap。操作：renewal burstiness/CV。
- 条件：至少32个间隔；非mean rate。
- 实际列：`td_conflict_burstiness`；novelty key：`search_conflict_renewal_dispersion`。
- 精确定义：相邻主分析冲突间自由决策数间隔的变异系数；不是间隔均值。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)。仅支持机制背景，不声称文献证明该phase特征有效。

### I099 · TD29 · 学习子句按固定长度桶分层后，Glue与长度的有序联合相关；使用Spearman桶秩协方差。

学习子句按固定长度桶分层后，Glue与长度的有序联合相关；使用Spearman桶秩协方差。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；学习clause width与glue联合桶。操作：有序桶相关。
- 条件：81格；常数边缘分布缺失。
- 实际列：`td_glue_size_dependence`；novelty key：`learned_level_width_dependence`。
- 精确定义：学习子句按固定长度桶分层后，Glue与长度的有序联合相关；使用Spearman桶秩协方差。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（被训练程序采用）。
- 来源启发：[来源1](https://www.ijcai.org/Proceedings/09/Papers/074.pdf)；[来源2](https://fmv.jku.at/papers/FleuryBiere-SAT2021.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。

### I100 · TD30 · 学习子句的证明依赖深度，定义原始reason子句为0，新子句为1+其已用reason子句最大深度。

学习子句的证明依赖深度，定义原始reason子句为0，新子句为1+其已用reason子句最大深度。

- 类型/对象：**原生求解前缀动态**（`native_solver_prefix`）；学习clause之间的reason证明祖先。操作：lemma依赖深度累积。
- 条件：原始reasons深度0；溢出缺失。
- 实际列：`td_lemma_dependency_depth`；novelty key：`learned_proof_ancestry`。
- 精确定义：学习子句的证明依赖深度，定义原始reason子句为0，新子句为1+其已用reason子句最大深度。
- 当前覆盖fit/feedback：**79/180；25/60**；状态：`SCORED_COMPLETE`（未被训练程序采用）。
- 来源启发：[来源1](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)；[来源2](https://fmv.jku.at/papers/FleuryBiere-SAT2021.pdf)。仅支持机制背景，不声称文献证明该phase特征有效。
