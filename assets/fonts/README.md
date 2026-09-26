# 随包中文字体

Noto Sans SC，来自Google Fonts官方仓库：
https://github.com/google/fonts/tree/main/ofl/notosanssc

下载文件：NotoSansSC[wght].ttf；本包命名为NotoSansSC.ttf。
许可证：SIL Open Font License 1.1，全文见同目录OFL.txt。
字体通过Matplotlib进程内注册，无须管理员权限或系统字体安装。

流程图使用 `NotoSansSC-Regular.ttf`：由上述可变字体通过 fontTools
`instantiateVariableFont(font, {'wght': 400})` 固定为常规字重，许可证不变。
名称表的 family（1/16）、full name（4）、PostScript name（6）分别设为
`Noto Sans SC Diagram`、`Noto Sans SC Diagram Regular`、
`NotoSansSC-Diagram-Regular`，避免注册后影响其他图件的字体匹配。
