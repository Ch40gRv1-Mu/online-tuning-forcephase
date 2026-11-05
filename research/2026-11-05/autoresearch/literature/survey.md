# 研究背景（启动时查阅）

- Xu, Hutter, Hoos, Leyton-Brown，SATzilla: Portfolio-based Algorithm Selection for SAT，JAIR 2008。按实例选求解器并明确优化运行时间/解题比例等目标；本研究迁移到同一求解器的phase配置，不假定其结论直接成立。[原文](https://arxiv.org/abs/1111.2249)
- Bischl等，ASlib: A Benchmark Library for Algorithm Selection，2016修订版。提供算法选择问题、特征与运行结果的统一比较框架；本研究保存配置成本三元组与特征开销，避免只看赢家准确率。[原文](https://arxiv.org/abs/1506.02465)
- Hadar Shavit, Holger H. Hoos，Revisiting SATZilla Features in 2024，SAT 2024。重新考察SAT特征提取、预处理与时间限制，支持把提取预算作为实验对象；不据此断言某特征能选择forcephase。[会议原文](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.27)

这些文献用于定位方法，不构成本项目特征有效性的证据。来源在2026-10-29启动阶段读取。后续遇到机制问题再定向补充，不以长文献整理推迟正式实验。
