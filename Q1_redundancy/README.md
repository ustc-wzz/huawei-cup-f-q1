# 固定预处理的冗余赋权对照

从项目根目录运行：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python Q1_redundancy/run_experiment.py
python Q1_redundancy/summarize.py
python Q1_redundancy/evaluate_reviews.py
```

依赖numpy、pandas、scipy；需要既有Q1导出的all_indicators_A1/A2/A3.csv.gz、indicator_weights.csv、sample_Q_A1.csv及A1原文附件。输出目录output_q1_redundancy独立于主模型。

分层抽样和副本噪声固定种子。盲评表已有文件不覆盖；评审只接收blind_review或本地盲评包.zip，不能接收analyst_key.csv。随机层/分歧层、各评审独立报告，不把同一文本对的两个评审当独立样本。仅42对为小规模试验，结论需保留不确定性。
