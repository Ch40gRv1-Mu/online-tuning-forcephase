# “Backtracking frequency”图示的术语澄清

本说明仅解释用户提供的图和既有I001记录，不新增求解、拟合或实验评分。

图中frequency应理解为**chrono事件占冲突数的比例**，不是每秒回退次数，也不是对所有回退按距离恰好为1作几何计数。

本实验字段为td_chrono_share，直接读取c_chrono_frac：

```text
(当前stats.chrono − 基准stats.chrono)
-----------------------------------
(当前stats.conflicts − 基准stats.conflicts)
```

首个合格前缀checkpoint使用累积区间；观测取自短原生D探针，不是完整求解终局。

固定源码依据：`work/ta100/observer_base/fpcontrol.cpp:461`，snapshot将stats.chrono复制到now.chrono；分类在同目录`analyze.cpp`的determine_actual_backtrack_level。

图中的“one-level backtrack share”过于简化：分析所得jump本来就等于level−1时，实际只退一层，但该分支不增加stats.chrono；trail-reuse分支选择高于jump的res时，会增加stats.chrono，而res仍可能小于level−1。因此原始统计不能严格等同“只退一层的次数/冲突数”。典型5→4与5→2可以帮助入门理解撤销深度，不能代替代码分类。

背景官方源码：https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp 。执行身份始终以固定本地source绑定为准。

图中+0.209%对应原48个资源合格feedback题：529.994 / 253435.293 = 0.20912399%。主结果保留完整60题：529.994 / 331107.082 = 0.16006725%。这只是对已有逐题成本的分母解释，不是新验证；主结果和全部冻结规则不变。
