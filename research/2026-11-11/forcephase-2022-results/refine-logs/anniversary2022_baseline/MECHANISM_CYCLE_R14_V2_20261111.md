# R14 v2 构建及入口修复

R14首个构建因Mac SDK只有libarchive链接声明而缺头文件失败，实测编译1.450115CPU秒/3.531103墙钟秒，work/native_gbd_features_20261111/build.json保留。随后提取入口在导入sklearn私有DTYPE位置时失败、0输入完成；错误日志保留，CPU未完整计量不填零。没有运行SAT或删除原结果。

本次冻结修复：为已存在的macOS libarchive提供公开v3.7.7的两个声明头，逐文件SHA/许可证保留，不改GBDc统计实现；读取实际sklearn.ensemble._forest.BaseForest._validate_X_predict源码，当前版本直接使用dtype=np.float32，不再尝试导入不存在的私有DTYPE常量。只有新构建实际exit0后才启动新提取身份。原记录不覆盖。

继承R14全部样本2843、资源、停止规则、模型和统计要求；输出改native_GBD_route_v2_20261111，构建work/native_gbd_features_v2_20261111。此更改只修复输入入口，不是另选成功样本、修改特征语义或改变科学目标。代码/补充协议先提交，再构建/正式测量，不做额外pilot或dryrun。

v2实际构建成功（2.488160CPU秒），随后原生计算已执行，但SQLite参考列为文本导致比较入口类型错误，保存failure.json（native0.114521CPU秒、parent1.111979CPU秒），不覆盖。v3在同一参考记录上显式转float，算法/名单/门槛不变，继续使用已绑定的v2二进制，输出native_GBD_route_v3_20261111。修复先提交后正式执行。
