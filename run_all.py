#!/usr/bin/env python3
"""从问题一到问题四顺序执行正式 notebook，并生成全部分析产物。"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager

ROOT = Path(__file__).resolve().parent
NOTEBOOKS = [
    "0924_F题_问题一.ipynb",
    "0924_问题二.ipynb",
    "0925_问题三.ipynb",
    "0925_问题四.ipynb",
]


def execute_notebook(path: Path) -> None:
    notebook = nbformat.read(path, as_version=4)
    with tempfile.TemporaryDirectory(prefix="f-repro-kernel-") as tmp:
        kernel_dir = Path(tmp) / "python-local"
        kernel_dir.mkdir()
        (kernel_dir / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "F题复现环境", "language": "python",
        }), encoding="utf-8")
        manager = KernelManager(
            kernel_name="python-local",
            kernel_spec_manager=KernelSpecManager(kernel_dirs=[tmp]),
        )
        client = NotebookClient(
            notebook, km=manager, timeout=3600,
            resources={"metadata": {"path": str(ROOT)}},
        )
        try:
            client.execute()
        finally:
            if manager.has_kernel:
                manager.shutdown_kernel(now=True)
            nbformat.write(notebook, path)
    errors = [
        (index, output.get("ename", "Error"), output.get("evalue", ""))
        for index, cell in enumerate(notebook.cells)
        for output in cell.get("outputs", [])
        if output.get("output_type") == "error"
    ]
    if errors:
        raise RuntimeError(f"{path.name} 执行失败：{errors[0]}")
    print(f"完成：{path.name}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="依次执行 F 题四问 notebook")
    parser.add_argument("--start-at", type=int, choices=range(1, 5), default=1,
                        help="从第几问开始；跳过的前序结果必须已存在")
    args = parser.parse_args()
    os.environ.setdefault("MPLBACKEND", "Agg")
    required = [ROOT / "real_attachments/A_data_value/signals_cache",
                ROOT / "real_attachments/B_scaling_laws",
                ROOT / "real_attachments/C_efficiency_evolution",
                ROOT / "算力约束下提升大语言模型能力的资源配置建模.docx"]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("复现输入缺失：" + ", ".join(missing))

    for index, name in enumerate(NOTEBOOKS, start=1):
        if index < args.start_at:
            continue
        if index == 2:
            print("导出问题一当前模型与数据，生成问题二输入…", flush=True)
            subprocess.run([sys.executable, str(ROOT / "Q2/export_q1_inputs.py")],
                           cwd=ROOT, check=True)
        if index == 3:
            print("审计问题一评分与问题二接口，生成第三问质量情景输入…", flush=True)
            subprocess.run([sys.executable, str(ROOT / "Q3/audit_quality_interface.py")],
                           cwd=ROOT, check=True)
        execute_notebook(ROOT / name)
    print("四问全部完成。结果入口：output_q1/、output_q2_shared/、output_q3_resource/、output_q4_evolution/", flush=True)


if __name__ == "__main__":
    main()
