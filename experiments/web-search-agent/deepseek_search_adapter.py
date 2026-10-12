import argparse
import json
from pathlib import Path

import requests
from dotenv import dotenv_values

SEARCH_URL = "https://api.deepseek.com/anthropic/v1/messages"
DEFAULT_MODEL = "deepseek-flash"
SUPPORTED_MODELS = ("deepseek-flash", "deepseek-v4-pro")
API_VERSION = "2023-06-01"
MAX_OUTPUT_TOKENS = 4096
MAX_SEARCH_USES = 5
TIMEOUT_SECONDS = 180


def parse_sources(payload):
    if not isinstance(payload, dict):
        raise RuntimeError("接口没有返回有效的 JSON 对象")

    blocks = payload.get("content")
    if not isinstance(blocks, list):
        raise RuntimeError("接口没有返回有效的 content 列表")

    search_blocks = [
        block for block in blocks
        if isinstance(block, dict)
        and block.get("type") == "web_search_tool_result"
    ]
    if not search_blocks:
        raise RuntimeError("没有搜索结果块，本次不能判定为真实搜索")

    sources = {}
    for block in search_blocks:
        items = block.get("content")
        if not isinstance(items, list):
            raise RuntimeError(
                "搜索工具返回错误："
                + json.dumps(items, ensure_ascii=False)
            )

        for item in items:
            if not isinstance(item, dict):
                raise RuntimeError("搜索结果条目格式错误")

            if item.get("type", "").endswith("_error"):
                raise RuntimeError(
                    "搜索工具返回错误："
                    + json.dumps(item, ensure_ascii=False)
                )

            url = item.get("url")
            if (
                item.get("type") == "web_search_result"
                and isinstance(url, str)
                and url
            ):
                sources.setdefault(
                    url, {"title": item.get("title"), "url": url}
                )

    if not sources:
        raise RuntimeError("返回了搜索结果块，但没有可核对的来源")

    return list(sources.values())


def web_search(query, api_key, model=DEFAULT_MODEL):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("搜索问题不能为空")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("没有读取到 DEEPSEEK_API_KEY")

    body = {
        "model": model,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [{
            "role": "user",
            "content": [{
                "type": "text",
                "text": (
                    "请实际调用 web_search 搜索以下问题，并引用来源："
                    + query
                )
            }]
        }],
        "tools": [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": MAX_SEARCH_USES
        }]
    }

    headers = {
        "x-api-key": api_key,
        "Authorization": "Bearer " + api_key,
        "anthropic-version": API_VERSION
    }

    with requests.post(
        SEARCH_URL,
        headers=headers,
        json=body,
        timeout=TIMEOUT_SECONDS,
        allow_redirects=False
    ) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise RuntimeError(
                "搜索接口返回 HTTP " + str(response.status_code)
            )
        payload = response.json()

    # 实验记录不保存包含密钥的请求头。
    return {
        "endpoint": SEARCH_URL,
        "request": body,
        "response": payload
    }


def main():
    parser = argparse.ArgumentParser(
        description="DeepSeek 原生搜索接入验证"
    )
    parser.add_argument("query", help="要搜索的问题")
    parser.add_argument(
        "--model", choices=SUPPORTED_MODELS, default=DEFAULT_MODEL
    )
    parser.add_argument(
        "--output", required=True, help="新建 JSON 实验记录的路径"
    )
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists():
        parser.error("结果文件已经存在，请生成一个新的文件名")
    if not output.parent.is_dir():
        parser.error("结果保存目录不存在")

    env_path = (
        Path(__file__).resolve().parent.parent / "context" / ".env"
    )
    api_key = dotenv_values(env_path).get("DEEPSEEK_API_KEY")

    print("正在请求真实搜索，完成后显示返回的轨迹……")
    record = web_search(args.query, api_key, args.model)

    with output.open("x", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False, indent=2)
    print("原始实验记录已保存：" + str(output))

    sources = parse_sources(record["response"])

    for block in record["response"]["content"]:
        kind = block.get("type")

        if kind == "thinking":
            print("\n💭 思考：\n" + str(block.get("thinking", "")))

        elif kind == "server_tool_use":
            print("\n🔧 行动：" + str(block.get("name")))
            print(json.dumps(
                block.get("input"), ensure_ascii=False, indent=2
            ))

        elif kind == "web_search_tool_result":
            print("\n👀 观察：")
            print(json.dumps(
                block.get("content"), ensure_ascii=False, indent=2
            ))

        elif kind == "text":
            print("\n💬 模型文字：\n" + str(block.get("text", "")))

    print("\n核对到真实搜索结果，来源数量：" + str(len(sources)))


if __name__ == "__main__":
    main()