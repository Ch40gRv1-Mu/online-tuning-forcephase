# R23 冻结图模式的固定线性readout

R22完整27树拟合失败：primary免费coarse−0.5609%、fine−0.6874%，没有新增部署。下一问题只为readout：512平方根归一化模式的联合线性相似度，能否比单坐标随机阈值树更有效？不改图、bin、轮数、null或资格，不重新提取CNF，也不声称新算法。当前chat owner，不delegation，goalactive，静态预测无短搜索。

全部retained4719重复开发、原seed0 T600成本、coarse4/fine5及原inner/iso隔离完全复用。2325纯资源资格覆盖oracle4.8249个百分点，2240非null模式覆盖4.7209，R22信息屏障已完整通过；1172全删失、2279可靠clear。使用现成R22 SHA绑定feature文件，base43和unsigned555、primary signed555、rewired555四view，不读family/身份/答案/终局统计入模。没有新solver或虚拟label。

唯一新模型固定Ridge alpha10、Cholesky、带intercept，相对PAR2差额目标不变。每fold只从train拟合基本43维均值/std，标准化后clip±10、整体除sqrt43；图512维只减训练均值、不按每bin方差放大，乘0.5（四轮各单位范数），保持平方根模式内积的意义。全部变换由native sklearn pipeline序列化；deterministic，无训练seed重复或alpha候选。36外层fit，inner只在旧quantile家族选margin，held费用为0的乐观预测情景。连续validation/held分数保存。

沿同screen：primary在两原留出均改善>=2%、对D名义区间下界>0，且相对basic/unsigned/rewired三对照的配对增量方向及区间支持，才导出预定四全开发模型、进真实费用/部署；否则停止此readout，不扫alpha/scale/clip或挑最好view当成功。所有2022仍已见开发，名义区间未校正适应性选择，不是独立确认，目标未完成。

协议/源先提交再执行；四BLAS线程、无需特征提取、<1GiB预计内存。15分钟硬限、0.25CPU核时，目标含准备十分钟内第一正式评分。现有real matrix/feature费用只逻辑复用，不重复记物理；保存失败和实际进程费，不另开audit/dryrun/热query/部署。执行score_literal_linear.py，模型literal_linear_readout.py，输出mechanism_R23_20261111。
