# 华为杯 F 题四问完整复现包（v0.8.0）

这个目录是独立运行包，包含四份最终 notebook、它们依赖的脚本和本地原始附件。运行入口会按问题一 → 问题二 → 问题三 → 问题四的顺序执行全部 notebook；问题一后会自动导出问题二所需输入，问题三前会自动审计问题一评分与问题二接口。所有图表、表格、验证文件和接口均从当前附件重新生成。

## 目录结构

```text
F题_四问完整复现包/
├── 0924_F题_问题一.ipynb
├── 0924_问题二.ipynb
├── 0925_问题三.ipynb
├── 0925_问题四.ipynb
├── run_all.py
├── requirements.txt
├── environment.yml
├── Q2/ Q3/ Q4/                 # notebook 调用的计算、审计和报告代码
├── real_attachments/           # 复现所需附件；来源清单见 source_manifest.json
└── 算力约束下提升大语言模型能力的资源配置建模.docx
```

## 环境与运行

建议 Python 3.12。用 Conda：

```bash
conda env create -f environment.yml
conda activate huawei-cup-f-repro
python run_all.py
```

或用 Python 自带虚拟环境：

```bash
python3.12 -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python run_all.py
```

完整计算耗时较长；问题一需要逐条解压并处理质量记录。完整运行建议保持设备接通电源并预留至少 5 GB 可用空间。若某一问中断或失败，在前序结果已生成的前提下可从该问续跑，例如第二问失败后运行 `python run_all.py --start-at 2`；第三问或第四问依次用 `--start-at 3`、`--start-at 4`。无需 GPU、R、Node.js 或网络下载。

## 运行产物

- `output_q1/length_domain_calibrated22/`：22指标评分、冲突诊断、领域配比拟合和问题一接口。
- `output_q2_shared/`：共同修正标度律、验证表、图件及 `q2_interface.json`。
- `Q3/quality_audit/`、`output_q3_resource/`：质量接口核查、资源情景结果、敏感性、验证和 `q3_interface.json`。
- `output_q4_evolution/`：时间—规模—能力分解、数据核查、前沿情景、图件和验证报告。

每份 notebook 执行后会保存带运行输出的 notebook；重新运行会覆盖其中的执行结果以及对应结果目录。四问之间通过 JSON 接口和已生成的表格衔接，不能跳过前序问题直接运行后序问题。

## 证据口径

原始附件来源、版本与部分合成数据说明见 `real_attachments/source_manifest.json`。包内只复制四份 notebook 实际读取的附件；未复制重复的未压缩缓存和未使用的 RegMix 原始文本。附件 B 中标记为半合成或外推的数据不代表独立实测。问题二质量刻度、问题三质量供给与问题四长期前沿均沿用各 notebook 中声明的识别假设和外推边界；运行成功不等于这些假设获得新的实证验证。

## 复现与定位故障

入口遇到首个错误即停止，并保留已完成 notebook 的输出。根据终端最后一段 traceback 定位对应 notebook 或接口审计；修复输入后用 `--start-at` 从失败问续跑。`run_all.py` 使用当前 Python 解释器启动临时 Jupyter 内核，不依赖系统预先注册 `python3` kernel。

本版使用平方Pearson冗余度，四问已顺序重算；具体改动见CHANGELOG.md。质量评分变化不等于独立盲评准确性提高。
