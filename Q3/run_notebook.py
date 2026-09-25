"""使用当前Python从镜像生成并执行问题3，执行后统一核验。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_all import rebuild_and_execute

if __name__ == "__main__":
    rebuild_and_execute(3)
