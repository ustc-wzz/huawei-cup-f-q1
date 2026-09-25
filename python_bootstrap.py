"""用用户已有的 Python 3.8+ 准备包内 Python；不修改系统安装或 PATH。"""
import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import zipfile


def platform_key():
    system=platform.system()
    machine=platform.machine().lower()
    machine={'amd64':'x86_64','aarch64':'arm64'}.get(machine,machine)
    # A 32-bit Windows Python may report x86 on a 64-bit Windows installation.
    if system=='Windows' and os.environ.get('PROCESSOR_ARCHITEW6432','').lower()=='amd64':machine='x86_64'
    return system+'-'+machine


def download_uv(root):
    manifest=json.loads((root/'bootstrap_uv.json').read_text(encoding='utf-8'))
    key=platform_key()
    if key not in manifest['platforms']:
        raise RuntimeError('自动准备暂不支持此系统架构：'+key+'；支持Windows x64、macOS Intel/Apple Silicon、Linux x64。')
    record=manifest['platforms'][key]
    folder=root/'.repro-tools';folder.mkdir(exist_ok=True)
    target=folder/('uv.exe' if os.name=='nt' else 'uv')
    marker=folder/'uv.sha256'
    def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    if target.is_file() and marker.is_file() and digest(target)==marker.read_text(encoding='ascii').strip():return target
    print('下载包内环境工具 uv '+manifest['version']+'（PyPI，校验SHA256）…',flush=True)
    with tempfile.TemporaryDirectory(dir=folder) as temporary:
        archive=Path(temporary)/'uv.whl'
        with urllib.request.urlopen(record['url'],timeout=120) as source,archive.open('wb') as dest:
            while True:
                block=source.read(1024*1024)
                if not block:break
                dest.write(block)
        if digest(archive)!=record['sha256']:raise RuntimeError('uv下载校验失败，请重试。')
        with zipfile.ZipFile(archive) as z:
            members=[n for n in z.namelist() if n.endswith('/scripts/'+target.name)]
            if len(members)!=1:raise RuntimeError('uv安装包结构异常')
            staged=Path(temporary)/target.name;staged.write_bytes(z.read(members[0]));staged.chmod(0o755)
        os.replace(staged,target)
    marker.write_text(digest(target),encoding='ascii')
    return target


def compatible_python(python):
    if not python.is_file():return False
    try:
        result=subprocess.run([str(python),'-c','import sys,struct;sys.exit(sys.version_info[:2] not in [(3,12),(3,13)] or struct.calcsize("P")!=8)'],capture_output=True)
        return result.returncode==0
    except OSError:return False


def prepare_python(root):
    root=Path(root)
    environment=root/'.repro-env'
    python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if compatible_python(python):return python
    uv=download_uv(root)
    env=os.environ.copy()
    env.update(UV_PYTHON_INSTALL_DIR=str(root/'.repro-python'),UV_CACHE_DIR=str(root/'.repro-tools/cache'),UV_PYTHON_PREFERENCE='only-managed',UV_PYTHON_DOWNLOADS='automatic',UV_NO_CONFIG='1')
    # Keep an incompatible or incomplete environment for recovery; never erase it.
    if environment.exists():environment.rename(root/('.repro-env.previous-'+str(time.time_ns())))
    print('当前Python用于启动；正在包内自动准备64位Python 3.12，不修改系统Python。首次需要联网。',flush=True)
    subprocess.run([str(uv),'venv','--python','3.12','--seed',str(environment)],env=env,cwd=root,check=True)
    if not compatible_python(python):raise RuntimeError('包内Python准备失败，请检查网络后重试。')
    return python
