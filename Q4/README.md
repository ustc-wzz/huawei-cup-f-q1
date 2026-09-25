# 问题四复现入口

固定主文档：`0925_问题四.ipynb`；文本镜像：`Q4/notebook_source.py`；版本v0.6.0。正式输出在`output_q4_evolution/`，其中`results_summary.md`为结果入口，`模型建立.md`、`模型求解.md`为完整论文方法和求解章节。

在项目根目录运行：

```bash
Q1/.venv/bin/python Q4/run_notebook.py
```

新环境安装`Q4/requirements.txt`后，可使用自己的Python解释器运行同一入口。临时Jupyter内核始终调用当前解释器，不改全局内核。Python 3.12为本次运行环境。仅运行数值阶段可执行`Q4/run_analysis.py`；完整交付应运行notebook入口，以生成核验、图件与报告。

依赖本地`real_attachments/C_efficiency_evolution/`下的C1、C3、C4、C5、C6和C8，以及既有问题二接口、问题三配置和求解器。原始附件与缓存不上传Git。输入路径及哈希见输出目录的`input_manifest.json`、`c8_input_manifest.json`；前面三问主文件和接口只读。

核心方法为时间→N/D→能力的带噪声结构中介模型，规模响应承接问题二标度律形状。完整ND样本的发布时代归因、榜单提交时间的描述性预测、分层Loss桥接分别保存，不混淆因果假设、真实观测、元数据估计和情景外推。

JSON截断不直接删除原件：所有解析错误进入台账，同目录可解析评测按文件名时间戳取最新；无有效文件时仅退出逐任务分析。逐任务结果采用MuSR三个叶子任务的独立归一化与等权聚合。

随机种子20260925，机构bootstrap 400次。预测起点是最后可比附件观测日2025-03-13，目标为2026-03-13和2027-03-13，不是从运行日开始的实时预测。高可比桥接出界返回缺失；长期预测区间条件于标度迁移和技术趋势情景，不能当成已验证的真实能力上限。

文件分工：`data_pipeline.py`负责证据与匹配，`evolution_model.py`负责模型、推导对应计算与验证实验，`verify.py`负责独立恒等式/边界核验，`plots.py`与`report.py`从最终表格生成图和论文章节。
