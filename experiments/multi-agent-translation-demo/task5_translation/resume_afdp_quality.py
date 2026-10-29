"""显式续行：请求完全一致时复用本轮已保存响应，仅剩余步骤访问 API。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

from run_afdp_chapter2 import BASE_URL, DATASET, HERE, MODEL, load_dataset, sha256
from runtime_config import require_api_key
from run_afdp_quality import MAX_CALLS, execute_quality_workflow
from translation_evidence import EvidenceRecorder, write_json


class ReplayClient:
    def __init__(self, client, source_run, replay_limit, new_call_limit):
        self.client = client
        self.api_key = client.api_key
        self.source_run = Path(source_run)
        self.saved_calls = json.loads((self.source_run / "agent_calls.json").read_text(encoding="utf-8"))[:replay_limit]
        if len(self.saved_calls) != replay_limit:
            raise ValueError("原始调用记录数量不足，不能续行。")
        self.new_call_limit = new_call_limit
        self.replayed_call_count = 0
        self.new_call_count = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **request):
        if self.replayed_call_count < len(self.saved_calls):
            call = self.saved_calls[self.replayed_call_count]
            folder = (self.source_run / call["directory"]).resolve()
            if not folder.is_relative_to(self.source_run.resolve()):
                raise ValueError("保存的响应路径越界。")
            saved_request = json.loads((folder / "request.json").read_text(encoding="utf-8"))
            if request != saved_request:
                raise ValueError("当前请求与保存请求不一致，停止复用，也不重新收费请求。")
            raw = json.loads((folder / "response.json").read_text(encoding="utf-8"))
            self.replayed_call_count += 1
            print(f"[复用已收响应] {self.replayed_call_count}：未发起新的 API 请求", flush=True)
            return SimpleNamespace(model_dump=lambda **kwargs: raw)
        if self.new_call_count >= self.new_call_limit:
            raise RuntimeError("本轮剩余 API 请求预算耗尽。")
        self.new_call_count += 1
        return self.client.chat.completions.create(**request)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--source-pdf", type=Path)
    args = parser.parse_args()
    source = args.source_run.resolve()
    if not source.is_relative_to((DATASET / "runs").resolve()):
        raise ValueError("续行来源必须是当前翻译数据集的运行目录。")
    old_state = json.loads((source / "run_manifest.json").read_text(encoding="utf-8"))
    saved = json.loads((source / "agent_calls.json").read_text(encoding="utf-8"))
    if old_state["workflow_status"] != "failed" or len(saved) != 6 or saved[-1]["stage"] != "initial_review":
        raise ValueError("本次续行器仅处理六次响应已保存、在初审引文校验处停止的这一轮。")
    manifest, units = load_dataset(source_pdf=args.source_pdf)
    if manifest["source_sha256"] != old_state["source_sha256"]:
        raise ValueError("原文来源变化，不能复用先前响应。")
    from openai import OpenAI
    key = require_api_key()
    root = DATASET / "runs" / datetime.now(timezone.utc).strftime("continued-%Y%m%dT%H%M%S%fZ")
    root.mkdir(parents=True, exist_ok=False)
    (root / "inputs").mkdir()
    for unit in units:
        shutil.copyfile(unit["path"], root / "inputs" / unit["path"].name)
    shutil.copyfile(DATASET / "source_manifest.json", root / "source_manifest.json")
    state = {"workflow_status": "running", "quality_status": "pending", "model": MODEL, "max_calls": MAX_CALLS, "source_run": source.name, "source_sha256": manifest["source_sha256"], "historical_model_request_count": len(saved), "new_model_request_limit": MAX_CALLS - len(saved), "continuation_reason": "仅复用与当前请求完全相同的历史回答；请求内容改变则显式停止，不混用不同版本译文。", "code_sha256": {p.name: sha256(p) for p in (Path(__file__), HERE / "run_afdp_quality.py", HERE / "translation_agent.py", HERE / "translation_evidence.py", HERE / "run_afdp_chapter2.py", HERE / "terminology_candidates.py")}}
    recorder = EvidenceRecorder(root, MODEL, [u["title"] for u in units], max_calls=MAX_CALLS)
    state["source_pdf_verified"] = manifest["source_pdf_verified"]
    state["code_sha256"]["runtime_config.py"] = sha256(HERE / "runtime_config.py")
    write_json(root / "run_manifest.json", state)
    print("续行证据目录：" + str(root), flush=True)
    replay = None
    exit_code = 1
    try:
        with OpenAI(api_key=key, base_url=BASE_URL, timeout=120.0, max_retries=0) as client:
            replay = ReplayClient(client, source, len(saved), MAX_CALLS - len(saved))
            state.update(execute_quality_workflow(replay, recorder, units))
        exit_code = 0 if state["blocker_count"] == 0 else 2
    except (Exception, KeyboardInterrupt) as exc:
        state.update(workflow_status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed", error_type=type(exc).__name__, error_message=str(exc).replace(key, "[REDACTED]"))
        print("续行未通过：" + state["error_message"], flush=True)
        exit_code = 130 if isinstance(exc, KeyboardInterrupt) else 1
    finally:
        for index, call in enumerate(recorder.calls[:len(saved)]):
            call["reused_response"] = True
            call["original_run"] = source.name
            call["original_directory"] = saved[index]["directory"]
            call["original_receipt_sha256"] = sha256(source / saved[index]["directory"] / "receipt.json")
            write_json(root / call["directory"] / "receipt.json", call)
        recorder.write_index()
        state.update(replayed_response_count=replay.replayed_call_count if replay else 0, new_model_request_count=replay.new_call_count if replay else 0, total_round_model_requests=len(saved) + (replay.new_call_count if replay else 0), recorded_responses=len(recorder.calls), finished_utc=datetime.now(timezone.utc).isoformat())
        write_json(root / "run_manifest.json", state)
    print("质量状态：" + state["quality_status"], flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
