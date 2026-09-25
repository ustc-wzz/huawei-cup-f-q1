#!/usr/bin/env python3
"""从问题一到问题四顺序执行正式 notebook，并生成全部分析产物。"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import argparse
import hashlib
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


MIRRORS = ["notebook_source.py", "Q2/notebook_source.py", "Q3/notebook_source.py", "Q4/notebook_source.py"]


def read_mirror(path: Path):
    """Read the shared percent-cell mirror format used by all four notebooks."""
    cells, lines, kind = [], [], None
    def append():
        if kind is None:
            return
        source = "\n".join(lines).strip("\n")
        if kind == "markdown":
            source = "\n".join(line[2:] if line.startswith("# ") else "" if line == "#" else line
                               for line in source.splitlines())
            cells.append(nbformat.v4.new_markdown_cell(source))
        else:
            cells.append(nbformat.v4.new_code_cell(source))
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# %%"):
            append()
            kind = "markdown" if "[markdown]" in line else "code"
            lines = []
        else:
            lines.append(line)
    append()
    return cells


def verify_delivery(index: int) -> dict:
    notebook = nbformat.read(ROOT / NOTEBOOKS[index-1], as_version=4)
    source = read_mirror(ROOT / MIRRORS[index-1])
    assert [c.source.strip() for c in notebook.cells] == [c.source.strip() for c in source]
    code = [c for c in notebook.cells if c.cell_type == "code"]
    assert all(c.execution_count is not None for c in code)
    assert not any(o.output_type == "error" for c in code for o in c.outputs)
    texts = [c.source for c in notebook.cells if c.cell_type == "markdown"]
    for cell in code:
        for output in cell.outputs:
            text = output.get("data", {}).get("text/markdown")
            if text is not None:
                texts.append("".join(text) if isinstance(text, list) else text)
    assert all(not any(ord(ch) < 32 and ch not in "\n\r\t" for ch in t) for t in texts)
    assert all("\\[" not in t and "\\]" not in t for t in texts)
    directory = ROOT / ["output_q1/length_domain_calibrated22", "output_q2_shared",
                        "output_q3_resource", "output_q4_evolution"][index-1]
    manifest = directory / "input_manifest.json"
    if manifest.exists():
        records = json.loads(manifest.read_text())
        assert all(hashlib.sha256((ROOT/r["path"]).read_bytes()).hexdigest() == r["sha256"] for r in records)
    checks = dict(status="passed", notebook_cells=len(notebook.cells), executed_code_cells=len(code),
                  mirror_exact=True, no_error_outputs=True, input_hashes_current=True if manifest.exists() else None,
                  markdown_no_control_characters=True, math_block_delimiters_compatible=True)
    if index in (3, 4):
        figures = list((directory / "figures").glob("*.png"))
        assert len(figures) == {3: 12, 4: 7}[index]
        assert all(p.with_suffix(".pdf").exists() for p in figures)
        checks["figures_png_pdf_pairs"] = len(figures)
    (directory / "delivery_checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2)+"\n")
    return checks


def rebuild_and_execute(index: int) -> None:
    target = ROOT / NOTEBOOKS[index-1]
    notebook = nbformat.v4.new_notebook(cells=read_mirror(ROOT / MIRRORS[index-1]),
        metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
    nbformat.write(notebook, target)
    execute_notebook(target)
    verify_delivery(index)


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
        def progress(cell, cell_index, **kwargs):
            if cell.cell_type == "code":
                print(f"{path.name}: 单元 {cell_index} 完成", flush=True)
        client.on_cell_executed = progress
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
        execute_notebook(ROOT / name)
        verify_delivery(index)
    print("四问全部完成。结果入口：output_q1/、output_q2_shared/、output_q3_resource/、output_q4_evolution/", flush=True)


if __name__ == "__main__":
    main()
