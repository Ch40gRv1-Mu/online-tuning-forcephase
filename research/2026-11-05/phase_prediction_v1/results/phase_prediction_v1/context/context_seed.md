# RICL 开发上下文种子

状态：首轮旧成本矩阵 warm start 已记录在 `episodes.jsonl` 和 `round01_feedback.json`；新服务器 reward 仍待开发 pilot。历史离线反馈不能冒充新部署验证。

目标：在 D/F+/F− 中按公式结构和动作前统计选择，减少含部署开销的 PAR2。

约束：不得使用 family、文件名、来源路径、年份、作者或真实 SAT/UNSAT 标签。只读取 development_fit/development_feedback；development_gate 和整个 2022 测试候选集禁止回流。

经验条目：候选规则及 hash、实际开发损失和 reward、错误选择和稳定成功的数值特征画像、修改理由、接受/拒绝决定、预算。所有特征与阈值必须经过 policy.py 白名单。没有 reward 时不能把假设登记为成功经验。

初始基线：always-D、always-Fplus、always-Fminus。

候选方向：子句长度分布、符号统计、变量—子句图树性、局部 gate 编码、经核实的 glue/决策层统计。不能把局部 gate 模式直接等同人工 problem family。

原教授数据缺少对应源码，只支持提出假设，不能直接充当本项目新配置的 reward。采用参数不更新的反馈记忆与规则改进，不宣称已复现 Algorithm Distillation 训练的 transformer。

2026-11-05计时实现观察：native -t是wall上限，固定矩阵使用既有CPU评分及CPU<=T判据，未知不代表精确用满TCPU。正式部署通过额外已资格进程CPU timer扣h并保持相同nativewallT；不改变学习损失。helper工程资格0.53CPU秒不计为policy reward，保护集未用。
