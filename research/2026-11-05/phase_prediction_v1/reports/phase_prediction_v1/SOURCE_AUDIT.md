# 相位语义与可部署观测审计

日期：2026-11-04。研究范围：固定 CaDiCaL 3.0.1 commit `c60730422e758ef1cebe7aeddf2dda31c996bf04`。本报告是源码和工程检查记录，不是性能结论。

## 教授实验与本实验的边界

教授的 MiniSAT 版本、修改代码、命令和 phase-saving 设置不可得。因此保留附件中的 false/true 原标签，不能宣称已复现原实验，也不能直接将原标签对应到新 solver 的动作。官方 MiniSAT [Solver.cc](https://github.com/niklasso/minisat/blob/master/minisat/core/Solver.cc) 用 literal sign 构造分支；sign 布尔值与变量赋值真值必须区分。旧固定相位、初始相位和后续 phase saving 也必须区分。

## 本实验的三个动作

| 动作 | 初始 phase | forcephase | 实际语义 |
|---|---:|---:|---|
| D | 1 | 0 | 原版默认，相位可来自 saved/target 等机制 |
| F+ | 1 | 1 | 原版 forcephase 正向选项对 |
| F− | 0 | 1 | 原版 forcephase 负向选项对 |
| I−，仅对照 | 0 | 0 | 负初始相位，后续保留原版相位机制 |

源码 `decide_phase` 中，force-saved 和 API forced phases 优先于 `forcephase`；不能把 F± 描述成覆盖每一种内部赋值的全局强制真/假。`forcephase` 还会抑制原生 rephasing。在线延续采用 **C track 的完整选项对语义**，不是仅翻转自由 decision 的 P track。重启不会增加，saved/target/best phases、学习子句、活动分数和 solver RNG 不被控制器重置。

## 遥测与时间方向

复用本项目审计版 `solver/fpcontrol.cpp`（schema 2），修改点由 `patches/cadical-fpc.patch` 明确列出。glue 累计来自 analyze 的实际 glue；学习长度、回跳和 level 均从 solver 现有计算或只读计数取得。

在线试验固定共同 D 前缀，在首次跨过 K=1000 冲突的自然重启后先记录 checkpoint，再应用一次 keep-D/F+/F−。实际触发冲突数可以大于1000，必须报告。checkpoint 之前早解和未达到预算均保留，不填造观测。只有此处的数值白名单可以进入将来的在线 policy；终局统计和事后 SAT/UNSAT 不可进入。

前缀 FNV 指纹覆盖搜索计数、trail、saved/target phases、部分限制和子句数量。它是确定性重放诊断指纹，**不是完整序列化状态，也不是所有内部状态相同的数学证明**。检查同时要求相同二进制/输入/seed、相同实际冲突与 decision 数、排除 clock/rate 后的相同动作前数值，以及正确的记录/动作顺序。

## 新服务器检查

原版二进制 SHA256：`b57d545231cab5a90357242cc838847356354324d891ef8ddaadcbf224e66bdb`。

独立 FPC2 二进制 SHA256：`b619194fdfd455e8d64f52d8234e0cb0652035acf2214853e1d0ebca6b4e52fd`。

三个人造公式上12项检查通过：每个公式的 D/F± 都比较原版、patched-off、telemetry、fixed-action 的 exit/conflict/decision/propagation/restart/rephase 计数；另比较三个共同前缀延续。一个公式实际到达 checkpoint，触发于1814冲突；另外两个早解，未错误地当作有前缀标签。返回 SAT 检查 model，返回 UNSAT 检查同次运行的 LRAT。

检查资源为2.132435 CPU秒，不代表生产实例的遥测开销。工程凭据位于 `results/phase_prediction_v1/server_receipts/online_gate.json`。正式运行还需逐实例检查前缀和实际费用，不能将合成门禁当作性能收益或普遍 no-op 证明。

## 学习机制定位

当前 Codex 读取开发反馈和有界经验记忆、提出可解释 JSON policy；不更新模型权重。其设计参考 [Reflexion](https://arxiv.org/abs/2303.11366) 的反馈记忆思路。没有训练或复现 [Algorithm Distillation](https://arxiv.org/abs/2210.14215) 的 transformer。所有 reward 必须来自实际成本，测试和 gate 结果不能写回更新上下文。
