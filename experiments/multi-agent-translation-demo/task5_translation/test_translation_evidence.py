"""只验证证据保存与错误边界，不调用模型、不评价翻译质量。"""

import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def response(text, finish_reason="stop"):
    body = {
        "id": "test-response-id",
        "model": "test-model",
        "choices": [{"finish_reason": finish_reason, "message": {"content": text}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }
    return SimpleNamespace(model_dump=lambda **kwargs: body)


def fake_client(*responses):
    pending = iter(responses)
    return SimpleNamespace(
        api_key="test-secret-never-log",
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: next(pending))),
    )


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("translation_evidence")
        except ModuleNotFoundError:
            self.fail("尚未实现每次 Agent 调用的证据保存功能。")
        temp_root = Path(__file__).resolve().parent / ".test_tmp"
        temp_root.mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recorder = self.module.EvidenceRecorder(self.root, "deepseek-flash", ["Part 1"])

    def test_saves_input_raw_response_and_usage_without_credentials(self):
        messages = [{"role": "user", "content": "原文及术语表"}]
        self.recorder.set_context("draft", "01")
        result = self.recorder.chat(fake_client(response("译文")), None, "Translation", messages)
        self.assertEqual(result, "译文")
        folder = self.root / self.recorder.calls[0]["directory"]
        self.assertEqual(json.loads((folder / "request.json").read_text(encoding="utf-8"))["messages"], messages)
        self.assertEqual((folder / "output.txt").read_text(encoding="utf-8"), "译文")
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["response_id"], "test-response-id")
        self.assertEqual(receipt["usage"]["total_tokens"], 120)
        self.assertEqual(receipt["manual_review"], "pending")
        for path in folder.iterdir():
            self.assertNotIn("test-secret-never-log", path.read_text(encoding="utf-8"))

    def test_candidate_extractor_uses_term_features_and_excludes_plain_words(self):
        try:
            candidates_module = importlib.import_module("terminology_candidates")
        except ModuleNotFoundError:
            self.fail("尚未实现基于特征的候选术语提取。")
        units = [
            {
                "id": "01",
                "title": "Part 1",
                "text": (
                    "PLANNING\n"
                    "Planning is a problem-solving methodology. Planning informs execution. "
                    "The air tasking order (ATO) is refined during preparation. "
                    "Commanders retain initiative and build momentum."
                ),
            },
            {
                "id": "02",
                "title": "Part 2",
                "text": (
                    "Planning continues during execution. "
                    "Are we doing things right (measures of performance)? "
                    "Are we doing the right things (measures of effectiveness)?"
                ),
            },
        ]
        candidates = candidates_module.extract_term_candidates(units)
        by_name = {item["en"].casefold(): item for item in candidates}
        self.assertIn("planning", by_name)
        self.assertIn("air tasking order (ato)", by_name)
        self.assertIn("measures of performance", by_name)
        self.assertIn("measures of effectiveness", by_name)
        self.assertNotIn("initiative", by_name)
        self.assertNotIn("momentum", by_name)
        self.assertGreaterEqual(by_name["planning"]["exact_count"], 3)
        self.assertEqual(by_name["planning"]["section_count"], 2)
        self.assertIn("section_heading", by_name["planning"]["signals"])
        self.assertIn("explicit_definition", by_name["planning"]["signals"])
        self.assertTrue(by_name["planning"]["evidence"])
        self.assertTrue(all(item["exact_count"] >= 1 for item in candidates))

    def test_candidate_extractor_does_not_treat_predicate_sentences_as_terms(self):
        candidates_module = importlib.import_module("terminology_candidates")
        units = [
            {
                "id": "01",
                "title": "Part 1",
                "text": (
                    "History shows that decentralized execution is effective. "
                    "The most relevant USAF structure is the air expeditionary task force (AETF). "
                    "The single most important element of design is the objective."
                ),
            }
        ]
        names = {item["en"].casefold() for item in candidates_module.extract_term_candidates(units)}
        self.assertNotIn("history shows that decentralized execution", names)
        self.assertNotIn("the most relevant usaf structure", names)
        self.assertNotIn("the single most important element of design", names)
        self.assertIn("air expeditionary task force (aetf)", names)

    def test_candidate_extractor_handles_quotes_levels_acronyms_and_list_boundaries(self):
        candidates_module = importlib.import_module("terminology_candidates")
        units = [
            {
                "id": "01",
                "title": "Part 1",
                "text": (
                    "The doctrine avoids the label “operational C2”. "
                    "Another commonly used term is the “3rd echelon.” "
                    "The Airborne Warning and Control System (AWACS) supports operations. "
                    "The activities are planning, preparing, executing, and assessing.\n"
                    "Distributed\nControl as a sub-theater echelon. Subsequently, forces act."
                ),
            }
        ]
        candidates = candidates_module.extract_term_candidates(units)
        names = {item["en"].casefold() for item in candidates}
        self.assertIn("operational c2", names)
        self.assertIn("3rd echelon", names)
        self.assertIn("airborne warning and control system (awacs)", names)
        self.assertNotIn("planning preparing", names)
        self.assertNotIn("control as a sub-theater echelon", names)
        awacs = next(item for item in candidates if item["en"].casefold().endswith("(awacs)"))
        self.assertIn("AWACS", awacs["evidence"])

    def test_invalid_glossary_is_preserved_and_fails_visibly(self):
        text = '{"glossary": [{"en": "C2"}]}'
        with self.assertRaises(ValueError):
            self.recorder.chat(fake_client(response(text)), None, "Glossary", [], json_mode=True)
        folder = self.root / self.recorder.calls[0]["directory"]
        self.assertEqual((folder / "output.txt").read_text(encoding="utf-8"), text)
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["usage"]["total_tokens"], 120)

    def test_glossary_requires_traceable_candidate_and_inclusion_signals(self):
        text = json.dumps(
            {
                "glossary": [
                    {
                        "candidate_id": "T001",
                        "zh": "指挥与控制过程",
                        "category": "process",
                        "definition": "重大C2活动序列",
                        "review_status": "candidate",
                    }
                ]
            },
            ensure_ascii=False,
        )
        with self.assertRaisesRegex(ValueError, "inclusion_signals"):
            self.recorder.chat(fake_client(response(text)), None, "Glossary", [], json_mode=True)

    def test_glossary_unknown_candidate_id_is_failed_in_call_receipt(self):
        self.recorder.set_glossary_candidates(
            [{"candidate_id": "T001", "signals": ["section_heading"]}]
        )
        text = json.dumps(
            {
                "glossary": [
                    {
                        "candidate_id": "T999",
                        "zh": "未知术语",
                        "category": "other",
                        "definition": "不存在的候选",
                        "inclusion_signals": ["section_heading"],
                        "review_status": "candidate",
                    }
                ]
            },
            ensure_ascii=False,
        )
        with self.assertRaisesRegex(ValueError, "候选表之外"):
            self.recorder.chat(fake_client(response(text)), None, "Glossary", [], json_mode=True)
        folder = self.root / self.recorder.calls[0]["directory"]
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "failed")

    def test_glossary_invented_signal_is_failed_in_call_receipt(self):
        self.recorder.set_glossary_candidates(
            [{"candidate_id": "T001", "signals": ["section_heading"]}]
        )
        text = json.dumps(
            {
                "glossary": [
                    {
                        "candidate_id": "T001",
                        "zh": "规划",
                        "category": "activity",
                        "definition": "核心活动",
                        "inclusion_signals": ["acronym_full_form"],
                        "review_status": "candidate",
                    }
                ]
            },
            ensure_ascii=False,
        )
        with self.assertRaisesRegex(ValueError, "不存在的收录信号"):
            self.recorder.chat(fake_client(response(text)), None, "Glossary", [], json_mode=True)
        folder = self.root / self.recorder.calls[0]["directory"]
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "failed")

    def test_glossary_rejects_extra_fields_that_repeat_candidate_evidence(self):
        text = json.dumps(
            {
                "glossary": [
                    {
                        "candidate_id": "T001",
                        "zh": "规划",
                        "category": "activity",
                        "definition": "核心活动",
                        "inclusion_signals": ["section_heading"],
                        "review_status": "candidate",
                        "evidence": "不应由模型重复抄写",
                    }
                ]
            },
            ensure_ascii=False,
        )
        with self.assertRaisesRegex(ValueError, "额外字段"):
            self.recorder.chat(fake_client(response(text)), None, "Glossary", [], json_mode=True)

    def test_glossary_rejects_top_level_fields_that_repeat_evidence(self):
        text = json.dumps(
            {
                "glossary": [
                    {
                        "candidate_id": "T001",
                        "zh": "规划",
                        "category": "activity",
                        "definition": "核心活动",
                        "inclusion_signals": ["section_heading"],
                        "review_status": "candidate",
                    }
                ],
                "evidence": "不应在顶层重复的整段证据",
            },
            ensure_ascii=False,
        )
        with self.assertRaisesRegex(ValueError, "顶层额外字段"):
            self.recorder.chat(fake_client(response(text)), None, "Glossary", [], json_mode=True)

    def test_glossary_rejects_unknown_category(self):
        text = json.dumps(
            {
                "glossary": [
                    {
                        "candidate_id": "T001",
                        "zh": "规划",
                        "category": "随便写的类别",
                        "definition": "核心活动",
                        "inclusion_signals": ["section_heading"],
                        "review_status": "candidate",
                    }
                ]
            },
            ensure_ascii=False,
        )
        with self.assertRaisesRegex(ValueError, "category"):
            self.recorder.chat(fake_client(response(text)), None, "Glossary", [], json_mode=True)

    def test_compact_glossary_selection_for_one_hundred_terms_fits_output_budget(self):
        runner = importlib.import_module("run_afdp_chapter2")
        candidates = [
            {
                "candidate_id": f"T{i:03d}",
                "en": f"Doctrine Term {i}",
                "exact_count": i,
                "section_count": 2,
                "signals": ["explicit_definition"],
                "feature_score": 5,
                "evidence": f"SOURCE_TERM_{i}",
                "locations": ["Part 1", "Part 2"],
            }
            for i in range(1, 101)
        ]
        selections = [
            {
                "candidate_id": f"T{i:03d}",
                "zh": f"条令术语{i}",
                "category": "doctrine_concept",
                "definition": "具有明确条令定义的专业概念",
                "inclusion_signals": ["explicit_definition"],
                "review_status": "candidate",
            }
            for i in range(1, 101)
        ]
        client = fake_client(response(json.dumps({"glossary": selections}, ensure_ascii=False)))
        glossary = runner.comprehensive_glossary_agent(client, self.recorder, candidates)
        folder = self.root / self.recorder.calls[0]["directory"]
        output = (folder / "output.txt").read_text(encoding="utf-8")
        with patch.dict("os.environ", {"TIKTOKEN_CACHE_DIR": os.environ.get("TIKTOKEN_CACHE_DIR", str(Path(gettempdir()) / "data-gym-cache"))}):
            import tiktoken
            token_count = len(tiktoken.get_encoding("o200k_base").encode(output))
        self.assertEqual(len(glossary), 100)
        self.assertLess(token_count, self.recorder.max_output_tokens)

    def test_comprehensive_glossary_has_no_count_cap_and_accepts_more_than_ten_terms(self):
        try:
            runner = importlib.import_module("run_afdp_chapter2")
        except ModuleNotFoundError:
            self.fail("尚未实现第二章实验入口。")
        terms = [
            {
                "candidate_id": f"T{i:03d}",
                "zh": f"术语{i}",
                "category": "doctrine_concept",
                "definition": "本章专业概念",
                "inclusion_signals": ["explicit_definition"],
                "review_status": "candidate",
            }
            for i in range(1, 13)
        ]
        candidates = [
            {
                "candidate_id": f"T{i:03d}",
                "en": f"Term {i}",
                "exact_count": i,
                "section_count": 2,
                "signals": ["explicit_definition"],
                "feature_score": 5,
                "evidence": f"SOURCE_TERM_{i}",
                "locations": ["Part 1", "Part 2"],
            }
            for i in range(1, 13)
        ]
        client = fake_client(response(json.dumps({"glossary": terms}, ensure_ascii=False)))
        glossary = runner.comprehensive_glossary_agent(client, self.recorder, candidates)
        self.assertEqual(len(glossary), 12)
        self.assertEqual(glossary[0]["en"], "Term 1")
        self.assertEqual(glossary[0]["evidence"], "SOURCE_TERM_1")
        self.assertEqual(glossary[0]["exact_count"], 1)
        request = json.loads(
            (self.root / self.recorder.calls[0]["directory"] / "request.json").read_text(encoding="utf-8")
        )
        prompt = "\n".join(message["content"] for message in request["messages"])
        self.assertIn("不设置数量上限", prompt)
        self.assertIn("低频但关键", prompt)
        self.assertIn("原文依据", prompt)
        self.assertIn("exact_count", prompt)
        self.assertIn("普通词", prompt)
        self.assertNotIn("完整原文如下", prompt)
        self.assertNotIn("6-10", prompt)

    def test_comprehensive_glossary_separates_included_and_excluded_candidates(self):
        runner = importlib.import_module("run_afdp_chapter2")
        candidates = [
            {
                "candidate_id": "T001",
                "en": "C2 process",
                "exact_count": 3,
                "section_count": 2,
                "signals": ["explicit_definition"],
                "feature_score": 5,
                "evidence": "The C2 process is an iterative series of activities.",
                "locations": ["Part 1", "Part 2"],
            },
            {
                "candidate_id": "T002",
                "en": "process should",
                "exact_count": 2,
                "section_count": 2,
                "signals": ["cross_section"],
                "feature_score": 2,
                "evidence": "The assessment process should begin during planning.",
                "locations": ["Part 1", "Part 2"],
            },
        ]
        answer = {
            "glossary": [
                {
                    "candidate_id": "T001",
                    "zh": "指挥与控制过程",
                    "category": "process",
                    "definition": "由主要指挥与控制活动构成的迭代过程",
                    "inclusion_signals": ["explicit_definition"],
                    "review_status": "candidate",
                }
            ],
            "excluded": [
                {
                    "candidate_id": "T002",
                    "reason": "谓语句片段，不是需要统一译法的概念",
                }
            ],
        }
        client = fake_client(response(json.dumps(answer, ensure_ascii=False)))

        glossary = runner.comprehensive_glossary_agent(client, self.recorder, candidates)

        self.assertEqual([term["candidate_id"] for term in glossary], ["T001"])
        self.assertEqual(self.recorder.calls[0]["status"], "format_valid_semantics_unreviewed")

    def test_glossary_requires_a_decision_for_every_candidate(self):
        self.recorder.set_glossary_candidates(
            [
                {"candidate_id": "T001", "signals": ["explicit_definition"]},
                {"candidate_id": "T002", "signals": ["cross_section"]},
            ]
        )
        answer = {
            "glossary": [
                {
                    "candidate_id": "T001",
                    "zh": "指挥与控制过程",
                    "category": "process",
                    "definition": "主要指挥与控制活动的迭代过程",
                    "inclusion_signals": ["explicit_definition"],
                    "review_status": "candidate",
                }
            ],
            "excluded": [],
        }

        with self.assertRaisesRegex(ValueError, "未处理的候选"):
            self.recorder.chat(
                fake_client(response(json.dumps(answer, ensure_ascii=False))),
                None,
                "Glossary",
                [],
                json_mode=True,
            )

    def test_glossary_rejects_candidate_in_both_included_and_excluded(self):
        self.recorder.set_glossary_candidates(
            [{"candidate_id": "T001", "signals": ["explicit_definition"]}]
        )
        answer = {
            "glossary": [
                {
                    "candidate_id": "T001",
                    "zh": "指挥与控制过程",
                    "category": "process",
                    "definition": "主要指挥与控制活动的迭代过程",
                    "inclusion_signals": ["explicit_definition"],
                    "review_status": "candidate",
                }
            ],
            "excluded": [
                {"candidate_id": "T001", "reason": "不应同时出现"}
            ],
        }

        with self.assertRaisesRegex(ValueError, "同时出现在"):
            self.recorder.chat(
                fake_client(response(json.dumps(answer, ensure_ascii=False))),
                None,
                "Glossary",
                [],
                json_mode=True,
            )

    def test_truncated_output_cannot_be_reported_as_success(self):
        with self.assertRaisesRegex(ValueError, "length"):
            self.recorder.chat(fake_client(response("不完整译文", "length")), None, "Translation", [])
        folder = self.root / self.recorder.calls[0]["directory"]
        self.assertTrue((folder / "response.json").is_file())
        self.assertEqual(self.recorder.calls[0]["status"], "failed")

    def test_unknown_manager_revision_target_is_rejected(self):
        text = '{"revise": ["不存在的章节"], "reason": "需要修订"}'
        with self.assertRaises(ValueError):
            self.recorder.chat(fake_client(response(text)), None, "Manager", [], json_mode=True)

    def test_draft_and_revision_are_distinct_immutable_records(self):
        client = fake_client(response("初稿"), response("修订稿"))
        self.recorder.set_context("draft", "01")
        self.recorder.chat(client, None, "Translation", [])
        first = self.root / self.recorder.calls[0]["directory"] / "output.txt"
        self.recorder.set_context("revision", "01")
        self.recorder.chat(client, None, "Translation", [])
        second = self.root / self.recorder.calls[1]["directory"] / "output.txt"
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_text(encoding="utf-8"), "初稿")
        self.assertEqual(second.read_text(encoding="utf-8"), "修订稿")

    def test_malformed_json_does_not_turn_into_an_empty_report(self):
        with self.assertRaises(ValueError):
            self.recorder.chat(fake_client(response("不是 JSON")), None, "Proofreading", [], json_mode=True)

    def test_connection_failure_preserves_request_and_does_not_link_missing_output(self):
        client = fake_client()
        def fail(**kwargs):
            raise RuntimeError("连接失败 test-secret-never-log")
        client.chat.completions.create = fail
        with self.assertRaises(RuntimeError):
            self.recorder.chat(client, None, "Translation", [])
        self.recorder.write_index()
        folder = self.root / self.recorder.calls[0]["directory"]
        self.assertTrue((folder / "request.json").is_file())
        self.assertFalse((folder / "output.txt").exists())
        self.assertNotIn("test-secret-never-log", (folder / "receipt.json").read_text(encoding="utf-8"))
        guide = (self.root / "review_guide.md").read_text(encoding="utf-8")
        self.assertIn("未收到模型正文", guide)
        self.assertNotIn("output.txt)", guide)

    def test_call_limit_stops_before_sending_another_request(self):
        self.recorder.max_calls = 1
        client = fake_client(response("第一份译文"))
        self.recorder.chat(client, None, "Translation", [])
        with self.assertRaisesRegex(RuntimeError, "调用上限"):
            self.recorder.chat(client, None, "Translation", [])

    def test_http_error_preserves_error_body_and_request_id_without_secrets(self):
        import httpx
        from openai import APIStatusError
        client = fake_client()
        body = {"error": {"message": "请求失败 test-secret-never-log"}}
        http_response = httpx.Response(429, json=body, headers={"x-request-id": "provider-error-42", "set-cookie": "do-not-save"}, request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"))
        def fail(**kwargs):
            raise APIStatusError("限流", response=http_response, body=body)
        client.chat.completions.create = fail
        with self.assertRaises(APIStatusError):
            self.recorder.chat(client, None, "Translation", [])
        folder = self.root / self.recorder.calls[0]["directory"]
        saved = json.loads((folder / "error_response.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["status_code"], 429)
        self.assertEqual(saved["request_id"], "provider-error-42")
        self.assertIn("请求失败", saved["body_text"])
        self.assertNotIn("test-secret-never-log", json.dumps(saved))
        self.assertNotIn("do-not-save", json.dumps(saved))

    def test_keyboard_interrupt_marks_the_call_as_interrupted(self):
        client = fake_client()
        def stop(**kwargs):
            raise KeyboardInterrupt()
        client.chat.completions.create = stop
        with self.assertRaises(KeyboardInterrupt):
            self.recorder.chat(client, None, "Translation", [])
        self.assertEqual(self.recorder.calls[0]["status"], "interrupted")

    def test_workflow_preserves_each_role_and_keeps_manager_away_from_body(self):
        try:
            runner = importlib.import_module("run_afdp_chapter2")
        except ModuleNotFoundError:
            self.fail("尚未实现第二章实验入口。")
        units = [{"id": f"{i:02}", "title": f"Part {i}", "text": f"SOURCE_UNIQUE_{i}: C2 2025", "pdf_pages": [i]} for i in range(1, 5)]
        self.recorder.titles = [unit["title"] for unit in units]
        glossary = (
            '{"glossary":[{"candidate_id":"T001","zh":"指挥与控制",'
            '"category":"acronym","definition":"指挥与控制的缩写",'
            '"inclusion_signals":["section_heading"],'
            '"review_status":"candidate"}],'
            '"excluded":['
            '{"candidate_id":"T002","reason":"普通文本片段"},'
            '{"candidate_id":"T003","reason":"普通文本片段"},'
            '{"candidate_id":"T004","reason":"普通文本片段"}]}'
        )
        report = '{"issues":[{"chapter":"Part 1","type":"术语不一致","detail":"统一术语"}],"chapters_need_revision":["Part 1"],"summary":"第一块需修订"}'
        decision = '{"revise":["Part 1"],"reason":"根据审校意见统一术语"}'
        client = fake_client(*[response(text) for text in [glossary, "DRAFT_UNIQUE_1 指挥与控制", "DRAFT_UNIQUE_2 指挥与控制", "DRAFT_UNIQUE_3 指挥与控制", "DRAFT_UNIQUE_4 指挥与控制", report, decision, "修订后的第一块 指挥与控制"]])
        with patch.dict("os.environ", {"TIKTOKEN_CACHE_DIR": os.environ.get("TIKTOKEN_CACHE_DIR", str(Path(gettempdir()) / "data-gym-cache"))}):
            roles = runner.load_course_roles(self.recorder)
            result = runner.execute_workflow(roles, client, self.recorder, units)
        self.assertEqual(result["quality_status"], "pending_human_review")
        self.assertEqual(len(self.recorder.calls), 8)
        self.assertIn("DRAFT_UNIQUE_1", (self.root / "translations/draft/01.md").read_text(encoding="utf-8"))
        self.assertIn("修订后的第一块", (self.root / "translations/final/01.md").read_text(encoding="utf-8"))
        manager_call = next(call for call in self.recorder.calls if call["agent"] == "Manager")
        manager_input = (self.root / manager_call["directory"] / "request.json").read_text(encoding="utf-8")
        self.assertNotIn("SOURCE_UNIQUE_", manager_input)
        self.assertNotIn("DRAFT_UNIQUE_", manager_input)
        self.assertTrue((self.root / "manager_decision.json").is_file())


if __name__ == "__main__":
    unittest.main()
