"""从当前结果刷新合并正文；保留第一、二问的方法论及结尾引用。"""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parent

def refresh():
    path=ROOT/'论文正文.md'
    text=path.read_text()
    head=text.split('# 第三部分')[0]
    tail='# 结论与局限'+text.split('# 结论与局限',1)[1]
    head=head.replace(r'\sum_{k\ne j}|r_{jk}|',r'\sum_{k\ne j}r_{jk}^{2}')
    start=head.index('## 4 模型求解与结果')+len('## 4 模型求解与结果')
    end=head.index('| 数据集 | 全局冲突率',start)
    summary=(ROOT/'output_q1/length_domain_calibrated22/results_summary.md').read_text().split('\n',1)[1]
    head=head[:start]+'\n\n'+summary+'\n'+head[end:]
    # Remove a stale hand-written quality-increment sentence; the generated table above replaces it.
    import re
    head=re.sub(r'加入配比质量指数的排序增益为.*?因果效应证据。','质量附加特征的当前检验结果见本节自动生成表；其改善不构成质量因果效应证据。',head)
    method=(ROOT/'output_q3_resource/模型建立.md').read_text().split('## 上限情景与临界收益决策')[0]
    q3=method+'\n'+(ROOT/'output_q3_resource/模型求解.md').read_text()
    q3=q3.replace('](figures/','](output_q3_resource/figures/')
    q4=(ROOT/'output_q4_evolution/模型建立.md').read_text()+'\n'+(ROOT/'output_q4_evolution/模型求解.md').read_text()
    q4=q4.replace('](figures/','](output_q4_evolution/figures/')
    path.write_text(head+'# 第三部分 问题三 算力约束下的条件资源配置\n\n'+q3+'\n# 第四部分 问题四 技术演进与前沿预测\n\n'+q4+'\n'+tail)

if __name__=='__main__':refresh()
