"""实验 10-2 启动入口：默认只检查，--run 才调用真实模型。"""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

from runtime_config import require_api_key


COURSE_ROOT = Path(__file__).resolve().parent.parent / "third_party/ai-agent-book"
EXPERIMENT = COURSE_ROOT / "chapter10" / "book-translation"
MODEL = "deepseek-flash"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="真实翻译自带四章，产生模型 API 费用")
    args = parser.parse_args()

    script = EXPERIMENT / "demo.py"
    chapters = sorted((EXPERIMENT / "sample_book").glob("*.md"))
    if not script.is_file() or len(chapters) != 4:
        raise RuntimeError("实验入口或自带四章样例不完整，停止运行。")

    print(f"模型：{MODEL}；接口：https://api.deepseek.com", flush=True)
    print("输入：自带英文四章；输出：中文；仅运行管理者组。", flush=True)
    if not args.run:
        print("配置检查通过，未调用任何模型 API。添加 --run 才会真实翻译。", flush=True)
        return 0

    key = require_api_key()
    # 只配置子进程，不修改系统环境、原配置文件或课程源码。
    child_env = os.environ.copy()
    child_env.update({
        "OPENAI_API_KEY": key,
        "OPENAI_BASE_URL": "https://api.deepseek.com",
        "OPENAI_MODEL": MODEL,
        "LLM_PROVIDER": "openai",
        "PYTHONIOENCODING": "utf-8",
    })
    run_name = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    output = Path(__file__).resolve().parent / "runs" / run_name
    print(f"本次输出目录：{output}", flush=True)
    command = [sys.executable, "-B", "-X", "utf8", str(script),
               "--skip-single", "--out-dir", str(output), "--model", MODEL]
    return subprocess.run(command, cwd=EXPERIMENT, env=child_env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
