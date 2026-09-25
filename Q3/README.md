# 问题三复现

主文档为根目录 `0925_问题三.ipynb`，文本镜像 `Q3/notebook_source.py`，求解器 `Q3/resource_model.py`，入口 `Q3/run_notebook.py`。全部结果写入 `output_q3_resource/`，不修改问题一、二主文件或接口。

本次实际使用 Python 3.12.14。已有当前工作区环境时，在项目根目录执行：

```bash
Q1/.venv/bin/python Q3/run_notebook.py
```

新环境可用 Python 3.12 创建虚拟环境后安装 `Q3/requirements.txt`。运行入口使用当前解释器的临时 Jupyter kernel，不更改全局内核注册。notebook也可在安装了这些依赖的内核中从项目根目录逐单元执行。

必须先准备本地原始附件及问题一评分缓存；它们按项目约定不纳入Git。具体路径与哈希见 `Q3/quality_audit/input_manifest.json`、`output_q3_resource/input_manifest.json`。必需输入包括：

- 一、二问固定主文件、镜像及最终JSON接口。
- `output_q1/length_domain_calibrated22/tables/` 下A1/A2/A3的sample_Q和length_calibration表。
- 原题DOCX、领域映射表、B1/B7 CSV、C7架构表。

运行会重新执行质量接口审查，从当前输入复核锚点与质量上限，再完成全部预算扫描、敏感性、独立优化、导数检查和图表。无提质基线、成本分解、观测覆盖、转移解析候选与全局数值结果分别保存，避免混同。

入口文件：`output_q3_resource/results_summary.md`（实际结论）、`verification.json`（验证）、`q3_interface.json`（后续接口）。`模型建立.md`和`模型求解.md`由最终执行生成，数值源于CSV；PNG和PDF图件在figures目录。

主质量上限是用户确认的最高50%文档均值增量参照，并非真实最高质量；采用同一D成本代理，不能据此保证足量原始Token供给。s_Q仍未识别，正向提质和高预算规模存在外推。数值核验不等于真实训练验证。
