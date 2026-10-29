"""逐次保存 Agent 的模型输入、原始响应、格式检查和人工复核入口。"""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time


REVIEW_QUESTIONS = {
    "Glossary": ["候选特征是否足以支持收录？", "Agent 是否排除了普通词和候选噪声？", "译法是否符合本章语境？", "是否遗漏低频但关键的概念或缩写？"],
    "Translation": ["是否漏译、增译或改变原文含义？", "数字、否定和条件是否保留？", "术语是否统一，中文是否自然？"],
    "Proofreading": ["指出的问题能否在译文中定位？", "问题是否真实，建议是否可执行？", "是否漏掉了人工发现的问题？本角色未读取原文。"],
    "Manager": ["修订对象是否对应审校意见？", "修订理由是否有报告依据？", "是否忽略问题或要求无依据的重译？"],
}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_output(agent, content, titles, json_mode, glossary_candidates=None):
    if not isinstance(content, str) or not content.strip():
        raise ValueError("模型没有返回非空文字。")
    if not json_mode:
        return None
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("需要 JSON 对象，不能用空对象兜底其他类型。")
    if agent == "Glossary":
        top_level_extra = set(data) - {"glossary", "excluded"}
        if top_level_extra:
            raise ValueError("Glossary 响应包含不允许的顶层额外字段：" + ", ".join(sorted(top_level_extra)))
        terms = data.get("glossary")
        if not isinstance(terms, list) or not terms:
            raise ValueError("glossary 必须是非空列表。")
        excluded = data.get("excluded", [])
        if not isinstance(excluded, list):
            raise ValueError("excluded 必须是列表。")
        required = ("candidate_id", "zh", "category", "definition", "review_status")
        included_candidate_ids = set()
        for term in terms:
            if not isinstance(term, dict) or any(not isinstance(term.get(k), str) or not term[k].strip() for k in required):
                raise ValueError("每个术语选择都必须有非空 candidate_id、zh、category、definition 和 review_status。")
            allowed_fields = set(required) | {"inclusion_signals"}
            extra_fields = set(term) - allowed_fields
            if extra_fields:
                raise ValueError("术语选择包含不允许的额外字段：" + ", ".join(sorted(extra_fields)))
            inclusion_signals = term.get("inclusion_signals")
            if not isinstance(inclusion_signals, list) or not inclusion_signals or any(not isinstance(v, str) or not v.strip() for v in inclusion_signals):
                raise ValueError("每个术语选择都必须有非空 inclusion_signals 列表。")
            if not re.fullmatch(r"T\d{3,}", term["candidate_id"]):
                raise ValueError("术语 candidate_id 格式无效。")
            if term["review_status"] not in {"candidate", "needs_domain_review"}:
                raise ValueError("术语 review_status 只能是 candidate 或 needs_domain_review。")
            if term["category"] not in {"doctrine_concept", "process", "activity", "authority", "organization", "acronym", "other"}:
                raise ValueError("术语 category 不在允许的类别中。")
            if term["candidate_id"] in included_candidate_ids:
                raise ValueError("术语选择中有重复候选编号。")
            if glossary_candidates is not None:
                candidate = glossary_candidates.get(term["candidate_id"])
                if candidate is None:
                    raise ValueError("Glossary Agent 引用了候选表之外的编号：" + term["candidate_id"])
                invalid_signals = set(inclusion_signals) - set(candidate["signals"])
                if invalid_signals:
                    raise ValueError("Glossary Agent 使用了候选中不存在的收录信号：" + ", ".join(sorted(invalid_signals)))
            included_candidate_ids.add(term["candidate_id"])
        excluded_candidate_ids = set()
        for decision in excluded:
            if not isinstance(decision, dict) or set(decision) != {"candidate_id", "reason"}:
                raise ValueError("每个排除决定只能包含 candidate_id 和 reason。")
            if any(not isinstance(decision[k], str) or not decision[k].strip() for k in ("candidate_id", "reason")):
                raise ValueError("每个排除决定都必须有非空 candidate_id 和 reason。")
            candidate_id = decision["candidate_id"]
            if not re.fullmatch(r"T\d{3,}", candidate_id):
                raise ValueError("排除项 candidate_id 格式无效。")
            if candidate_id in excluded_candidate_ids:
                raise ValueError("排除决定中有重复候选编号。")
            if glossary_candidates is not None and candidate_id not in glossary_candidates:
                raise ValueError("Glossary Agent 排除了候选表之外的编号：" + candidate_id)
            excluded_candidate_ids.add(candidate_id)
        overlap = included_candidate_ids & excluded_candidate_ids
        if overlap:
            raise ValueError("候选不能同时出现在 glossary 和 excluded：" + ", ".join(sorted(overlap)))
        if glossary_candidates is not None:
            unresolved = set(glossary_candidates) - included_candidate_ids - excluded_candidate_ids
            if unresolved:
                raise ValueError("Glossary Agent 存在未处理的候选：" + ", ".join(sorted(unresolved)))
    elif agent == "Proofreading":
        if not isinstance(data.get("issues"), list) or not isinstance(data.get("summary"), str):
            raise ValueError("审校报告缺少 issues 列表或 summary 文字。")
        for issue in data["issues"]:
            if not isinstance(issue, dict) or issue.get("chapter") not in titles:
                raise ValueError("审校问题引用了未知章节。")
            if any(not isinstance(issue.get(k), str) or not issue[k].strip() for k in ("type", "detail")):
                raise ValueError("审校问题缺少 type 或 detail。")
        targets = data.get("chapters_need_revision")
        if not isinstance(targets, list) or any(not isinstance(t, str) or t not in titles for t in targets):
            raise ValueError("审校报告的待修订章节无效。")
    elif agent == "Manager":
        targets = data.get("revise")
        if not isinstance(targets, list) or any(not isinstance(t, str) or t not in titles for t in targets):
            raise ValueError("Manager 的 revise 必须引用已有章节。")
        if len(targets) != len(set(targets)) or not isinstance(data.get("reason"), str) or not data["reason"].strip():
            raise ValueError("Manager 重复指定章节或缺少修订理由。")
    return data


class EvidenceRecorder:
    def __init__(self, run_dir, model, titles, max_calls=11, max_output_tokens=8192):
        self.run_dir = Path(run_dir)
        self.model = model
        self.titles = list(titles)
        self.max_calls = max_calls
        self.max_output_tokens = max_output_tokens
        self.calls = []
        self.context = {"stage": "initial", "unit_id": None}
        self.glossary_candidates = None
        self.review_questions = {agent: list(questions) for agent, questions in REVIEW_QUESTIONS.items()}

    def set_glossary_candidates(self, candidates):
        indexed = {}
        for candidate in candidates:
            candidate_id = candidate.get("candidate_id")
            signals = candidate.get("signals")
            if not isinstance(candidate_id, str) or candidate_id in indexed or not isinstance(signals, list):
                raise ValueError("候选术语编号重复或特征格式无效。")
            indexed[candidate_id] = candidate
        self.glossary_candidates = indexed

    def set_context(self, stage, unit_id=None):
        if not re.fullmatch(r"[a-z_]+", stage) or (unit_id is not None and not re.fullmatch(r"[0-9]{2}", unit_id)):
            raise ValueError("调用阶段或原文块编号无效。")
        self.context = {"stage": stage, "unit_id": unit_id}

    def chat(self, client, tracker, agent, messages, json_mode=False, note="", validator=None):
        """兼容教材 llm_chat 签名；此实验的唯一调用账本是 self.calls。"""
        if agent not in self.review_questions:
            raise ValueError("未知 Agent 角色。")
        if len(self.calls) >= self.max_calls:
            raise RuntimeError("达到本轮调用上限，停止发送模型请求。")
        label = f"{len(self.calls)+1:03d}_{agent.lower()}_{self.context['stage']}"
        if self.context["unit_id"]:
            label += "_" + self.context["unit_id"]
        folder = self.run_dir / "agents" / label
        folder.mkdir(parents=True, exist_ok=False)
        request = {
            "model": self.model, "messages": messages, "temperature": 0.2,
            "max_tokens": self.max_output_tokens,
            "extra_body": {"thinking": {"type": "disabled"}},
        }
        if json_mode:
            request["response_format"] = {"type": "json_object"}
        write_json(folder / "request.json", request)
        receipt = {
            "agent": agent, **self.context, "note": note,
            "directory": folder.relative_to(self.run_dir).as_posix(),
            "requested_model": self.model, "started_utc": datetime.now(timezone.utc).isoformat(),
            "status": "sending", "manual_review": "pending",
            "review_questions": self.review_questions[agent],
        }
        self.calls.append(receipt)
        write_json(folder / "receipt.json", receipt)
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(**request)
            raw = response.model_dump(mode="json")
            write_json(folder / "response.json", raw)
            receipt.update(response_id=raw.get("id"), response_model=raw.get("model"), usage=raw.get("usage"))
            choice = raw["choices"][0]
            content = choice["message"].get("content")
            (folder / "output.txt").write_text(content if isinstance(content, str) else "", encoding="utf-8")
            receipt["finish_reason"] = choice.get("finish_reason")
            if choice.get("finish_reason") != "stop":
                raise ValueError("模型未正常结束：finish_reason=" + str(choice.get("finish_reason")))
            if json_mode:
                parsed = json.loads(content)
                write_json(folder / "parsed.json", parsed)
            validate_output(agent, content, self.titles, json_mode, self.glossary_candidates)
            if validator is not None:
                validator(content)
            receipt["status"] = "format_valid_semantics_unreviewed"
            return content
        except (Exception, KeyboardInterrupt) as exc:
            message = str(exc)
            secret = getattr(client, "api_key", None)
            if secret:
                message = message.replace(secret, "[REDACTED]")
            receipt.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                           error_type=type(exc).__name__, error_message=message)
            error_response = getattr(exc, "response", None)
            if error_response is not None:
                body = error_response.text
                safe_body = body.replace(secret, "[REDACTED]") if secret else body
                request_id = error_response.headers.get("x-request-id")
                write_json(folder / "error_response.json", {
                    "status_code": error_response.status_code, "request_id": request_id,
                    "body_text": safe_body, "credential_redacted": safe_body != body,
                })
                receipt.update(http_status=error_response.status_code, provider_request_id=request_id)
            raise
        finally:
            receipt["latency_seconds"] = round(time.perf_counter() - started, 3)
            write_json(folder / "receipt.json", receipt)

    def write_index(self):
        write_json(self.run_dir / "agent_calls.json", self.calls)
        lines = ["# 每个 Agent 的输出与复核入口", "", "格式检查通过不等于内容正确；所有人工质量判断目前为待复核。", "",
                 "| 调用 | 角色/阶段 | 原始输出 | 输入 | 调用信息 |", "|---|---|---|---|---|"]
        for i, call in enumerate(self.calls, 1):
            d = call["directory"]
            output_link = f"[查看]({d}/output.txt)" if (self.run_dir / d / "output.txt").is_file() else "未收到模型正文"
            lines.append(f"| {i} | {call['agent']} / {call['stage']} | {output_link} | [查看]({d}/request.json) | [查看]({d}/receipt.json) |")
        for agent, questions in self.review_questions.items():
            lines += ["", "## " + agent] + ["- [ ] " + q for q in questions]
        if any(call["stage"] == "final_review" for call in self.calls):
            lines += ["", "本轮包含英中对照及修订后审校。质量是否被拦截请查看 delivery_checks.json；模型复查不替代人工验收。", ""]
        else:
            lines += ["", "修订稿需要另行对照原文复核；原版审校角色检查的是初稿译文，不是原文忠实性或修订后的验收。", ""]
        (self.run_dir / "review_guide.md").write_text("\n".join(lines), encoding="utf-8")


def mechanical_checks(units, translations, glossary, draft=None):
    """返回待人工核查的线索，不把字符串匹配当作语义质量评分。"""
    report = {"kind": "mechanical_signals_only", "semantic_quality": "pending_human_review", "units": []}
    for unit in units:
        source = unit["text"]
        target = translations[unit["title"]]
        numbers = sorted(set(re.findall(r"\b\d+(?:[.,]\d+)*\b", source)))
        normalized_source = re.sub(r"\s+", " ", source).casefold()
        absent = [term for term in glossary if re.sub(r"\s+", " ", term["en"]).casefold() in normalized_source and term["zh"] not in target]
        report["units"].append({
            "unit_id": unit["id"], "title": unit["title"],
            "source_characters": len(source), "translation_characters": len(target),
            "source_numbers_not_found_literally": [n for n in numbers if n not in target],
            "glossary_targets_not_found_literally": absent,
            "changed_after_revision": draft is not None and target != draft[unit["title"]],
            "interpretation": "数字写法或译法变体也会触发线索，须对照原文判读，不能直接视为错误。",
        })
    return report
