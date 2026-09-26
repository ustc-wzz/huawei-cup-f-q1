# %% [markdown]
# # 第四问补充：月度观测能力前沿
# 使用附件C1与第四问既定许可筛选口径，输出描述性前沿、入榜样本数和前沿规模。
# 2025年3月截至13日；该图不估计因果效应，不替代35个基础模型的结构归因。

# %%
from pathlib import Path
import sys
from IPython.display import Image, Markdown, display
ROOT = Path.cwd()
if not (ROOT / 'Q4').exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / 'Q4'))
from draw_monthly_frontier import run
run()

# %%
display(Image(filename=str(ROOT / 'output_q4_monthly_frontier/monthly_frontier.png'), width=1100))
display(Markdown((ROOT / 'output_q4_monthly_frontier/分析与图注.md').read_text(encoding='utf-8')))
