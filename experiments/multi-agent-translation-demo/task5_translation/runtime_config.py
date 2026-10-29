"""发布版配置：密钥仅从当前进程或项目本地 .env 读取，不打印、不写入日志。"""

import os
from pathlib import Path


KEY_FILE = Path(__file__).resolve().parent / ".env"


def require_api_key():
    from dotenv import dotenv_values
    key = os.environ.get("DEEPSEEK_API_KEY") or dotenv_values(KEY_FILE).get("DEEPSEEK_API_KEY")
    if not key or key.startswith(("your-", "sk-your", "<", "replace")):
        raise ValueError("真实运行需要 DEEPSEEK_API_KEY；配置进程环境或 task5_translation/.env。不要提交密钥。")
    return key
