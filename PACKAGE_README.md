# F题四问完整复现包 v0.9.0

完整解压ZIP后，Windows双击 `run_windows.bat`；macOS可运行 `run_macos.command`。也可以在任意工作目录执行 `python 完整包路径/run_all.py`。不要在压缩包预览窗口内直接运行。

需要预先安装64位Python 3.12或3.13，推荐3.12。首次缺少依赖时通常需要联网，程序会自动创建包内 `.repro-env` 并安装；已准备好的独立环境会直接复用，无须重复联网。安装失败后再次运行即可续装，不需要手动创建Conda环境。安装或缓存生成耗时可能较长，终端会显示进度。完整包应放在可写目录。

程序自动完成：检查Python和依赖 → 定位并校验原始附件 → 加载随包中文字体 → 读取完整缓存或从原始数据重建 → 顺序运行四问。A1/A2/A3原始压缩数据全部随包提供；无须创建signals_cache目录。缓存损坏或来源变化会自动重建，已有结果目录允许重复运行并更新输出。

运行结果保存在四份notebook及 `output_q1/`、`output_q2_shared/`、`output_q3_resource/`、`output_q4_evolution/`。质量评分仍采用平方Pearson冗余度，β=0.25；本版只改运行和交付流程，不改变建模假设。

故障排查时可运行 `python run_all.py --prepare-only`，仅检查环境、附件、字体并准备缓存。`--start-at 2`、`--start-at 3`、`--start-at 4`可从失败问续跑，前序结果必须来自同一版输入；默认从第一问完整运行。

中文字体Noto Sans SC随包提供，许可证见 `assets/fonts/OFL.txt`。全部文本文件以UTF-8读写。原始文件校验清单为 `repro_inputs.json`，交付清单为 `PACKAGE_MANIFEST.json`；删除缓存不影响原始文件校验。

本包在macOS完成实际自动安装、冷缓存重建和四问运行验证；Windows x64依赖轮子可用性另行核查，未把静态兼容检查冒充Windows整机实测。模型结果仍受各问声明的半合成数据、质量刻度未识别和跨尺度外推边界限制。
