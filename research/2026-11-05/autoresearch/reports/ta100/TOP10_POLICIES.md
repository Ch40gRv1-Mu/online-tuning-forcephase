# 前10种不同策略

从已有100轮排名只读导出；88轮产生同一旧静态规则，合并后共有13种不同规则。没有重新拟合、评分或开启gate/test。

按同一60题开发反馈上的成本增量排序；成本含PAR2超时罚分，未扣提取/探针费用。以下为原始精度阈值。

所有策略：资源资格不满足，或当前实际访问分支所需字段缺失/非有限时，返回phase=true；不默认回退另一棵静态树。

基础字段：s_positive_fraction=正文字出现占比；s_mean_length=平均子句长度；s_length_std=子句长度标准差；g_cycle_excess_per_incidence=按incidence归一化环冗余。

## 1. I001

相对旧静态：+0.1601%；相对固定true：+5.4392%。

- `s_positive_fraction <= 0.388031304508 and s_positive_fraction <= 0.196010372787` → **true**
- `s_positive_fraction <= 0.388031304508 and s_positive_fraction > 0.196010372787` → **false**
- `s_positive_fraction > 0.388031304508 and td_chrono_share <= 0.226738` → **false**
- `s_positive_fraction > 0.388031304508 and td_chrono_share > 0.226738` → **true**

`td_chrono_share`：前缀中实际采用chronological backtracking的冲突份额。

公式：`c_chrono_frac`；条件：共同native-D动作前前缀。

原始结果：`outputs/ta100/B01/I001/result.json`；SHA256：`5559f0925e4b786c570fa5f2f9a4268437acc84debc7650cb97d379d3e2810f5`。

## 2. I002（88轮相同规则）

相对旧静态：+0.0000%；相对固定true：+5.2876%。

- `s_positive_fraction <= 0.388031304508 and s_positive_fraction <= 0.196010372787` → **true**
- `s_positive_fraction <= 0.388031304508 and s_positive_fraction > 0.196010372787` → **false**
- `s_positive_fraction > 0.388031304508 and s_length_std <= 0.46287575042025` → **false**
- `s_positive_fraction > 0.388031304508 and s_length_std > 0.46287575042025` → **true**

原始结果：`outputs/ta100/B01/I002/result.json`；SHA256：`d3f28cbad7ca0f7c5f477665655779077862841f0a9fe7366df0b84594e5acfa`。

## 3. I027

相对旧静态：-0.0648%；相对固定true：+5.2263%。

- `g_cycle_excess_per_incidence <= 0.48654943603899997 and g_cycle_excess_per_incidence <= 0.448787720882375` → **true**
- `g_cycle_excess_per_incidence <= 0.48654943603899997 and g_cycle_excess_per_incidence > 0.448787720882375` → **false**
- `g_cycle_excess_per_incidence > 0.48654943603899997 and graph_diffusion_return <= 0.00514181419561497` → **false**
- `g_cycle_excess_per_incidence > 0.48654943603899997 and graph_diffusion_return > 0.00514181419561497` → **true**

`graph_diffusion_return`：Tests repeated-walk trapping and local circulation, rather than the sign alignment of the leading eigenvector.

公式：`S=D^(-1/2) A D^(-1/2) on the unsigned incidence graph. f=tr(S^4)/max(1,n+m), estimated by mean_{8 fixed seeds} z^T S^4 z/(n+m) for Rademacher z.`；条件：8个固定探针；不是signed leading-mode。

原始结果：`outputs/ta100/B03/I027/result.json`；SHA256：`a6d717ced301ad8b7424f617c46c8c7662fc61bf01c1007db99b84f75fee43dd`。

## 4. I069

相对旧静态：-1.6824%；相对固定true：+3.6942%。

- `s_positive_fraction <= 0.388031304508 and s_positive_fraction <= 0.196010372787` → **true**
- `s_positive_fraction <= 0.388031304508 and s_positive_fraction > 0.196010372787` → **false**
- `s_positive_fraction > 0.388031304508 and algebra_convex_fractional_pressure <= -0.010195831732056088` → **true**
- `s_positive_fraction > 0.388031304508 and algebra_convex_fractional_pressure > -0.010195831732056088` → **false**

`algebra_convex_fractional_pressure`：Fractional directional pressure after relaxation of clause satisfaction.

公式：`Starting x=.5,64 projected subgradient steps minimize sum_C max(0,1-sum_l truth(l))+.05sum_i(x_i-.5)^2-h_i*x_i, h_i=(pos_i-neg_i)/degree_i. eta=.05/sqrt(t+1)/sqrt(maxdegree); clip[0,1]. Return mean(x-.5).`；条件：F*；固定算法，非LP最优解。

原始结果：`outputs/ta100/B07/I069/result.json`；SHA256：`5f94a8dd5e5bfa7b0521529c13e5c3af8b9db97b7bbcaa7b697ae01be04ff5c0`。

## 5. I098

相对旧静态：-1.7322%；相对固定true：+3.6471%。

- `s_positive_fraction <= 0.388031304508 and s_positive_fraction <= 0.196010372787` → **true**
- `s_positive_fraction <= 0.388031304508 and s_positive_fraction > 0.196010372787` → **false**
- `s_positive_fraction > 0.388031304508 and td_conflict_burstiness <= 2.8081808542` → **false**
- `s_positive_fraction > 0.388031304508 and td_conflict_burstiness > 2.8081808542` → **true**

`td_conflict_burstiness`：相邻主分析冲突间自由决策数间隔的变异系数；不是间隔均值。

公式：`sqrt(mean(gap^2)-mean(gap)^2)/mean(gap)`；条件：至少32个间隔；非mean rate。

原始结果：`outputs/ta100/B10/I098/result.json`；SHA256：`73d1f8528b987b5517b687812e54f1bbdcede137e0f5accaddf0053f970c1894`。

## 6. I059

相对旧静态：-1.8831%；相对固定true：+3.5041%。

- `s_positive_fraction <= 0.388031304508 and s_positive_fraction <= 0.196010372787` → **true**
- `s_positive_fraction <= 0.388031304508 and s_positive_fraction > 0.196010372787` → **false**
- `s_positive_fraction > 0.388031304508 and graph_nonbacktracking <= 3.9407252165999047` → **true**
- `s_positive_fraction > 0.388031304508 and graph_nonbacktracking > 3.9407252165999047` → **false**

`graph_nonbacktracking`：Measures onward branching once immediate edge reversal is forbidden.

公式：`Let x_0(u->v)=1 and x_{t+1}(u->v)=sum_{w in N(v),w!=u} x_t(v->w). f=sum x_3 / max(1,sum x_2).`；条件：有界样本；非普通walk返回率。

原始结果：`outputs/ta100/B06/I059/result.json`；SHA256：`0637cb846d7d3fbdabffdb76f12ece13da626e7204a895b63ae41adff8c557c4`。

## 7. I095

相对旧静态：-2.1017%；相对固定true：+3.2971%。

- `s_positive_fraction <= 0.388031304508 and s_positive_fraction <= 0.196010372787` → **true**
- `s_positive_fraction <= 0.388031304508 and s_positive_fraction > 0.196010372787` → **false**
- `s_positive_fraction > 0.388031304508 and td_blocker_success_share <= 0.6019017555777499` → **true**
- `s_positive_fraction > 0.388031304508 and td_blocker_success_share > 0.6019017555777499` → **false**

`td_blocker_success_share`：主搜索传播检查中，因blocking literal已满足而跳过reason子句读取的比例。

公式：`satisfied_blocker_skips/watch_entries_examined`；条件：只加计数，不改变watch顺序。

原始结果：`outputs/ta100/B10/I095/result.json`；SHA256：`3947d6cc5d09ab063cf4ef825af8f2e348a0b3c7e963f0cc4f429b52365118d9`。

## 8. I003

相对旧静态：-2.2518%；相对固定true：+3.1549%。

- `s_mean_length <= 2.673101892945 and s_mean_length <= 2.5630158765375004` → **true**
- `s_mean_length <= 2.673101892945 and s_mean_length > 2.5630158765375004` → **false**
- `s_mean_length > 2.673101892945 and td_phase_source_entropy <= 0.40352420417540247` → **false**
- `s_mean_length > 2.673101892945 and td_phase_source_entropy > 0.40352420417540247` → **true**

`td_phase_source_entropy`：target、saved、其余三个决策相位来源桶的归一化熵。

公式：`p=[c_target_src_frac,c_saved_src_frac,1-c_target_src_frac-c_saved_src_frac]; H=-sum(p_i*ln(p_i))/ln(3)`；条件：同一checkpoint三个互斥来源桶。

原始结果：`outputs/ta100/B01/I003/result.json`；SHA256：`ee52194d74a556e72b4cb72d53a62affcf3916c16ac0d567be1590a89a577cf6`。

## 9. I066

相对旧静态：-2.4713%；相对固定true：+2.9470%。

- `s_mean_length <= 2.673101892945 and s_mean_length <= 2.5630158765375004` → **true**
- `s_mean_length <= 2.673101892945 and s_mean_length > 2.5630158765375004` → **false**
- `s_mean_length > 2.673101892945 and algebra_hall_deficiency <= 0.58056640625` → **true**
- `s_mean_length > 2.673101892945 and algebra_hall_deficiency > 0.58056640625` → **false**

`algebra_hall_deficiency`：Deficit of distinct variable resources for constraints.

公式：`Compute exact maximum clause-variable bipartite matching on F*. Return(m-matching_size)/m; empty clauses are unmatched rows, without adopting a SAT answer.`；条件：F*；空子句为unmatched row。

原始结果：`outputs/ta100/B07/I066/result.json`；SHA256：`03e64019b5e9e4008b91ebeb301ec26846f21a6a9bdabc82d69b54448bc44d32`。

## 10. I099

相对旧静态：-2.5027%；相对固定true：+2.9173%。

- `s_mean_length <= 2.673101892945 and s_mean_length <= 2.5630158765375004` → **true**
- `s_mean_length <= 2.673101892945 and s_mean_length > 2.5630158765375004` → **false**
- `s_mean_length > 2.673101892945 and td_glue_size_dependence <= 0.751223465906` → **true**
- `s_mean_length > 2.673101892945 and td_glue_size_dependence > 0.751223465906` → **false**

`td_glue_size_dependence`：学习子句按固定长度桶分层后，Glue与长度的有序联合相关；使用Spearman桶秩协方差。

公式：`corr(rank_bin(learned_size),rank_bin(glue))`；条件：81格；常数边缘分布缺失。

原始结果：`outputs/ta100/B10/I099/result.json`；SHA256：`bc0341b33fb686eeb2865fce65cfe141228df62498ba703fc54236545af677f8`。

