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

def load_notebook_tools():
    global nbformat, NotebookClient, KernelManager, KernelSpecManager
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
    load_notebook_tools()
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
    load_notebook_tools()
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
        records = json.loads(manifest.read_text(encoding='utf-8'))
        assert all(hashlib.sha256((ROOT/r["path"]).read_bytes()).hexdigest() == r["sha256"] for r in records)
    checks = dict(status="passed", notebook_cells=len(notebook.cells), executed_code_cells=len(code),
                  mirror_exact=True, no_error_outputs=True, input_hashes_current=True if manifest.exists() else None,
                  markdown_no_control_characters=True, math_block_delimiters_compatible=True)
    if index in (3, 4):
        figures = list((directory / "figures").glob("*.png"))
        assert len(figures) == {3: 12, 4: 7}[index]
        assert all(p.with_suffix(".pdf").exists() for p in figures)
        checks["figures_png_pdf_pairs"] = len(figures)
    (directory / "delivery_checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2)+"\n", encoding='utf-8')
    return checks


def rebuild_and_execute(index: int) -> None:
    load_notebook_tools()
    target = ROOT / NOTEBOOKS[index-1]
    notebook = nbformat.v4.new_notebook(cells=read_mirror(ROOT / MIRRORS[index-1]),
        metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
    nbformat.write(notebook, target)
    execute_notebook(target)
    verify_delivery(index)


def execute_notebook(path: Path) -> None:
    load_notebook_tools()
    notebook = nbformat.read(path, as_version=4)
    with tempfile.TemporaryDirectory(prefix="f-repro-kernel-") as tmp:
        kernel_dir = Path(tmp) / "python-local"
        kernel_dir.mkdir()
        (kernel_dir / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-X", "utf8", "-m", "ipykernel_launcher", "-f", "{connection_file}"],
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
    parser.add_argument('--prepare-only', action='store_true', help='检查环境和附件并生成缓存，不运行模型')
    args = parser.parse_args()
    from repro_runtime import ensure_environment, prepare_inputs, configure_fonts
    ensure_environment(Path(__file__).resolve(), sys.argv[1:])
    prepare_inputs(ROOT)
    print('中文字体：'+configure_fonts(), flush=True)
    os.environ.setdefault("MPLBACKEND", "Agg")
    if args.prepare_only:
        from signal_cache import raw_signal_paths, load_signals
        data=ROOT/'real_attachments/A_data_value'
        for prefix, paths, domain in zip(['A1_sample','A2_arxiv','A3_github'],raw_signal_paths(data),[None,'arxiv','github']):
            load_signals(data/'signals_cache',prefix,paths,domain)
        print('环境、字体、原始附件和缓存准备完成。',flush=True)
        return

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
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'准备或运行失败：{error}\n首次安装依赖需联网；修复后重复运行同一命令即可。',file=sys.stderr)
        raise SystemExit(1)
