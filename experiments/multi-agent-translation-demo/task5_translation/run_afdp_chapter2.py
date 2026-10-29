"""第二章翻译实验：默认仅检查；--run 才调用 DeepSeek 并记录每个 Agent。"""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

from terminology_candidates import extract_term_candidates
from translation_evidence import EvidenceRecorder, mechanical_checks, write_json
from runtime_config import KEY_FILE, require_api_key


HERE = Path(__file__).resolve().parent
DATASET = HERE / "afdp_c2_chapter2_20261026"
COURSE_ROOT = HERE.parent / "third_party/ai-agent-book"
COURSE_ROLES = COURSE_ROOT / "chapter10/book-translation/agents.py"
MODEL = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_dataset(root=DATASET, *, source_pdf=None):
    root = Path(root).resolve()
    manifest = json.loads((root / "source_manifest.json").read_text(encoding="utf-8"))
    manifest["source_pdf_verified"] = False
    if source_pdf is not None:
        if sha256(source_pdf) != manifest["source_sha256"]:
            raise ValueError("指定源 PDF 与原文准备记录不一致。")
        manifest["source_pdf_verified"] = True
    clean = (root / "source_chapter2_clean.txt").read_text(encoding="utf-8")
    if hashlib.sha256(clean.encode("utf-8")).hexdigest() != manifest["clean_text_sha256"]:
        raise ValueError("完整第二章原文发生变化。")
    units = []
    previous_end = 0
    for item in manifest["units"]:
        path = (root / item["file"]).resolve()
        if not path.is_relative_to(root) or sha256(path) != item["sha256"]:
            raise ValueError("输入块路径或内容不符合原文准备记录。")
        heading, body = path.read_text(encoding="utf-8").split("\n\n", 1)
        if heading != "# " + item["title"] or body.strip() != clean[item["clean_start"]:item["clean_end"]].strip():
            raise ValueError("原文块与完整第二章不一致。")
        if item["clean_start"] != previous_end:
            raise ValueError("原文块之间存在遗漏或重叠。")
        previous_end = item["clean_end"]
        units.append({"id": path.name[:2], "title": item["title"], "text": body.strip(), "path": path, "pdf_pages": item["pdf_pages"]})
    if previous_end != len(clean) or len(units) != 4 or len({u["title"] for u in units}) != 4:
        raise ValueError("第二章必须完整覆盖为四个具有不同名称的原文块。")
    return manifest, units


def load_course_roles(recorder):
    """复用教材四个角色的提示词构造，只替换模型收发与记录函数。"""
    spec = importlib.util.spec_from_file_location("afdp_course_roles", COURSE_ROLES)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法读取教材角色代码。")
    roles = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(roles)
    roles.llm_chat = recorder.chat
    return roles


def comprehensive_glossary_agent(client, tracker, candidates, source_context="", feedback=""):
    """依据可核验特征筛选正式术语；数量由概念决定，不设置业务数量上限。"""
    tracker.set_glossary_candidates(candidates)
    messages = [
        {
            "role": "system",
            "content": (
                "你是军事条令术语专家。候选已经由程序根据频次、章节分布、标题、定义句、缩写和概念对等特征提取。"
                "你的任务是判断候选的术语性并建立面向概念的中文术语表。只输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请从候选表中筛选所有真正需要统一翻译的术语，不设置数量上限，数量由概念及证据决定。\n"
                "收录依据包括：明确的定义或专门解释；章节标题、核心阶段或正式子活动；正式缩写及全称；"
                "条令框架、流程、权限或组织概念；必须区分的概念对；跨章节重复且需要固定译法；"
                "低频但关键、且误译会改变关键含义的概念。\n"
                "频次只是特征之一。不得仅因高频收录普通词；排除没有领域特殊含义的普通词、普通动作、"
                "一次性案例描述、人名、数字以及无需统一译法的词。不得添加候选表之外的词。\n"
                "必须排除截断短语，不能把词组的一半当成独立概念。全称、缩写和词形变体属于同一概念时，"
                "选择一个最完整的候选收录，其他候选明确排除为重复概念。不能把不同概念强行合并。"
                "依据原文判断 command 和 control 的差别，不能把两个词都机械译成控制。"
                "原文未解释的缩写不得猜测全称；含义无法确认则标 needs_domain_review。\n"
                "必须对每个候选做出且只做出一次决定：正式收录的放入 glossary；不收录的放入 excluded，"
                "并用简短 reason 说明排除原因。禁止把不收录项放进 glossary，也禁止用空 inclusion_signals 表示排除。\n"
                "只返回候选的 candidate_id，不要重复抄写 en、evidence、频次和位置，程序会按编号合并原文依据。"
                "inclusion_signals 只能引用该候选 signals 中真正支持收录的信号。"
                "definition 必须简洁。译法存在领域争议时 review_status=needs_domain_review，否则为 candidate。\n"
                "输出 JSON，格式为："
                '{"glossary":[{"candidate_id":"候选编号","zh":"中文译法",'
                '"category":"doctrine_concept/process/activity/authority/organization/acronym/other",'
                '"definition":"本章语境中的简洁定义","inclusion_signals":["候选已有的收录信号"],'
                '"review_status":"candidate 或 needs_domain_review"}],'
                '"excluded":[{"candidate_id":"候选编号","reason":"普通词、句子片段、重复概念或其他排除原因"}]}。\n\n'
                "候选术语及客观特征如下：\n\n"
                + json.dumps(candidates, ensure_ascii=False, indent=2)
                + ("\n\n【原文语境】\n" + source_context if source_context else "")
                + ("\n\n【需处理的审校反馈】\n" + feedback if feedback else "")
            ),
        },
    ]
    raw = tracker.chat(
        client,
        tracker,
        "Glossary",
        messages,
        json_mode=True,
        note="基于频次、章节分布、结构信号和原文依据筛选术语；不设置数量上限",
    )
    selections = json.loads(raw)["glossary"]
    candidates_by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    glossary = []
    for selection in selections:
        candidate = candidates_by_id.get(selection["candidate_id"])
        if candidate is None:
            raise ValueError("Glossary Agent 引用了候选表之外的编号：" + selection["candidate_id"])
        invalid_signals = set(selection["inclusion_signals"]) - set(candidate["signals"])
        if invalid_signals:
            raise ValueError("Glossary Agent 使用了候选中不存在的收录信号：" + ", ".join(sorted(invalid_signals)))
        glossary.append({
            **candidate,
            "zh": selection["zh"],
            "category": selection["category"],
            "pos": selection["category"],
            "definition": selection["definition"],
            "inclusion_signals": selection["inclusion_signals"],
            "review_status": selection["review_status"],
        })
    return glossary


def execute_workflow(roles, client, recorder, units):
    root = recorder.run_dir
    for name in ("draft", "revision", "final"):
        (root / "translations" / name).mkdir(parents=True, exist_ok=False)
    (root / "bilingual").mkdir(exist_ok=False)
    candidates = extract_term_candidates(units)
    write_json(root / "term_candidates.json", candidates)
    recorder.set_context("extraction")
    print(f"[Glossary] 从 {len(candidates)} 个带特征候选中筛选术语，不设置数量上限。", flush=True)
    glossary = comprehensive_glossary_agent(client, recorder, candidates)
    write_json(root / "glossary.json", glossary)

    drafts = {}
    file_index = {"term_candidates": "term_candidates.json", "glossary": "glossary.json"}
    for unit in units:
        recorder.set_context("draft", unit["id"])
        print("[Translation] 初译 " + unit["title"], flush=True)
        text = roles.translation_agent(client, recorder, unit["text"], glossary, unit["title"])
        drafts[unit["title"]] = text
        relative = "translations/draft/" + unit["id"] + ".md"
        (root / relative).write_text(text, encoding="utf-8")
        file_index[unit["title"]] = relative

    recorder.set_context("initial_review")
    print("[Proofreading] 审校初稿译文，输出问题清单。", flush=True)
    report = roles.proofreading_agent(client, recorder, drafts, glossary)
    write_json(root / "proofreading_report.json", report)
    file_index["proofreading_report"] = "proofreading_report.json"

    recorder.set_context("decision")
    print("[Manager] 根据审校报告选择修订块。", flush=True)
    task = "将 AFDP 3-0.1 第二章完整译成中文，保持术语一致，不删改事实、数字、条件和否定含义。"
    decision = roles.manager_decision(client, recorder, task, file_index, report)
    write_json(root / "manager_decision.json", decision)
    final = dict(drafts)
    by_title = {u["title"]: u for u in units}
    for title in decision["revise"]:
        unit = by_title[title]
        feedback_items = [issue["detail"] for issue in report["issues"] if issue["chapter"] == title]
        feedback = "\n".join(feedback_items) or decision["reason"]
        recorder.set_context("revision", unit["id"])
        print("[Translation] 按审校意见重译 " + title, flush=True)
        revised = roles.translation_agent(client, recorder, unit["text"], glossary, title, feedback=feedback)
        (root / "translations/revision" / (unit["id"] + ".md")).write_text(revised, encoding="utf-8")
        final[title] = revised

    assembled = []
    for unit in units:
        text = final[unit["title"]]
        (root / "translations/final" / (unit["id"] + ".md")).write_text(text, encoding="utf-8")
        assembled.append("# " + unit["title"] + "\n\n" + text)
        pair = "# " + unit["title"] + "\n\n## 英文原文\n\n" + unit["text"] + "\n\n## 中文译文（待人工复核）\n\n" + text + "\n"
        (root / "bilingual" / (unit["id"] + ".md")).write_text(pair, encoding="utf-8")
    (root / "chapter2_zh.md").write_text("\n\n".join(assembled) + "\n", encoding="utf-8")
    checks = mechanical_checks(units, final, glossary, drafts)
    write_json(root / "quality_checks.json", checks)
    return {"workflow_status": "completed", "quality_status": "pending_human_review", "revised_units": decision["revise"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="真实调用模型，按实际 token 产生费用")
    parser.add_argument("--source-pdf", type=Path, help="可选：额外核验原始 PDF 哈希；默认仅核验随包文本快照")
    args = parser.parse_args()
    manifest, units = load_dataset(source_pdf=args.source_pdf)
    candidates = extract_term_candidates(units)
    tree = ast.parse(COURSE_ROLES.read_text(encoding="utf-8"))
    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if not {"glossary_agent", "translation_agent", "proofreading_agent", "manager_decision"} <= functions:
        raise ValueError("教材角色接口与实验要求不一致。")
    print("输入核对通过：完整第二章文本及四块输入哈希一致。源 PDF 本次核验：" + str(manifest["source_pdf_verified"]), flush=True)
    print(f"候选术语特征提取通过：{len(candidates)} 个候选；正式术语数量由 Agent 依据证据决定。", flush=True)
    print("模型：deepseek-flash；关闭 thinking；最多 11 次请求；每次最多输出 8192 token；不自动重试。", flush=True)
    print("每次保存输入、原始回答、解析结果、响应 ID、usage 和人工复核入口。", flush=True)
    if not args.run:
        print("仅完成本地检查，模型调用次数为 0。添加 --run 才开始收费翻译。", flush=True)
        return 0

    key = require_api_key()
    from openai import OpenAI
    run_name = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    run_dir = DATASET / "runs" / run_name
    run_dir.mkdir(parents=True, exist_ok=False)
    snapshot = run_dir / "inputs"
    snapshot.mkdir()
    for unit in units:
        shutil.copyfile(unit["path"], snapshot / unit["path"].name)
    shutil.copyfile(DATASET / "source_manifest.json", run_dir / "source_manifest.json")
    state = {"workflow_status": "running", "quality_status": "pending_human_review", "model": MODEL,
             "source_sha256": manifest["source_sha256"], "max_calls": 11, "max_output_tokens": 8192,
             "thinking": "disabled", "automatic_retries": 0,
             "adaptations": ["复用教材翻译、审校和 Manager 角色函数，证据记录器替代原 llm_chat。", "Python 先按频次、章节分布、标题、定义句、缩写和概念对生成候选；Glossary Agent 再依据术语性筛选。", "Glossary 不设置术语数量上限，每条正式术语必须保留候选编号、收录理由和原文依据。", "独立编排，不使用教材 EDITORIAL_MANDATE。", "审校检查初稿译文，修订后的语义质量仍待人工复核。"],
             "code_sha256": {str(p): sha256(p) for p in (Path(__file__), HERE / "terminology_candidates.py", HERE / "translation_evidence.py", COURSE_ROLES)}}
    state["source_pdf_verified"] = manifest["source_pdf_verified"]
    state["code_sha256"]["runtime_config.py"] = sha256(HERE / "runtime_config.py")
    write_json(run_dir / "run_manifest.json", state)
    recorder = EvidenceRecorder(run_dir, MODEL, [u["title"] for u in units])
    print("证据与译文目录：" + str(run_dir), flush=True)
    exit_code = 0
    try:
        roles = load_course_roles(recorder)
        with OpenAI(api_key=key, base_url=BASE_URL, timeout=120.0, max_retries=0) as client:
            state.update(execute_workflow(roles, client, recorder, units))
    except Exception as exc:
        state.update(workflow_status="failed", error_type=type(exc).__name__, error_message=str(exc).replace(key, "[REDACTED]"))
        print("实验失败，已保留收到的数据：" + state["error_message"], file=sys.stderr, flush=True)
        exit_code = 1
    except KeyboardInterrupt:
        state.update(workflow_status="interrupted")
        print("实验被中断，已经收到的数据仍保留。", file=sys.stderr, flush=True)
        exit_code = 130
    finally:
        recorder.write_index()
        state["model_request_count"] = len(recorder.calls)
        state["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(run_dir / "run_manifest.json", state)
    print("先打开 review_guide.md 解读每个 Agent；译文质量尚待人工复核。", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
