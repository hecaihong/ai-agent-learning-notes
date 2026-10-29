"""改进版的离线回归；服务替身不用于证明真实译文质量。"""

import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from test_translation_evidence import fake_client, response
from translation_evidence import EvidenceRecorder


class QualityTranslationTests(unittest.TestCase):
    def setUp(self):
        try:
            self.quality = importlib.import_module("run_afdp_quality")
        except ModuleNotFoundError as exc:
            if exc.name != "run_afdp_quality":
                raise
            self.fail("改进版尚未实现：旧工作流没有双语审校、精确修订和最终质量门禁。")
        temp_parent = Path(__file__).resolve().parent / ".test_tmp"
        temp_parent.mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=temp_parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_candidates_include_low_frequency_acronyms_and_exclude_fragments(self):
        text = (
            "PLANNING\nPlanning is a problem-solving methodology. "
            "Direct liaison authorized (DIRLAUTH) links staffs. "
            "The JFC retains OPCON below the CCMD. MTO supports the OE. "
            + "The theater air component conducts major C2 activities. " * 3
        )
        names = {x["en"].casefold() for x in self.quality.quality_candidates(
            [{"id": "01", "title": "Part 1", "text": text}]
        )}
        for acronym in ("dirlauth", "jfc", "opcon", "ccmd", "mto", "oe"):
            self.assertIn(acronym, names)
        self.assertNotIn("theater air", names)
        self.assertNotIn("major c2", names)

    def test_review_quote_alignment_accepts_only_verifiable_layout_changes(self):
        self.assertTrue(hasattr(self.quality, "align_source_quote"), "尚未实现带来源的引文对齐")
        aligned = self.quality.align_source_quote("Its purpose is to\n\ndistill clarity.", "Its purpose is to\ndistill clarity.")
        self.assertEqual(aligned["kind"], "whitespace_only")
        source = "Nodes may span several levels of\nBattle Management Example: Global Air Mobility Adjustment\nThe example has 600 missions.\n\noperations and have varying levels of capability. C2 nodes should know their role."
        quote = "Nodes may span several levels of\noperations and have varying levels of capability."
        aligned = self.quality.align_source_quote(source, quote)
        self.assertEqual(aligned["kind"], "verified_sidebar_interruption")
        self.assertEqual(len(aligned["source_segments"]), 2)
        for segment in aligned["source_segments"]:
            self.assertIn(segment, source)
        with self.assertRaises(ValueError):
            self.quality.align_source_quote(source, "Nodes may attack without authorization.")

    def test_patch_preserves_untargeted_text_and_footnote(self):
        old = "第一段原样保留。\n\n这里进行评做。\n\n> ⁹ 有关命令，参见计划。"
        result = self.quality.apply_patches(old, [{"old": "进行评做", "new": "开展评估"}])
        self.assertEqual(result, "第一段原样保留。\n\n这里开展评估。\n\n> ⁹ 有关命令，参见计划。")

    def test_patch_rejects_ambiguous_and_missing_targets(self):
        for old, quote in (("重复。重复。", "重复"), ("没有这句话。", "不存在")):
            with self.subTest(old=old), self.assertRaises(ValueError):
                self.quality.apply_patches(old, [{"old": quote, "new": "修改"}])

    def test_patch_rejects_overlapping_targets(self):
        with self.assertRaisesRegex(ValueError, "重叠"):
            self.quality.apply_patches("第一段原文。", [{"old": "第一段", "new": "第二段"}, {"old": "一段原文", "new": "别的文字"}])

    def test_gate_rejects_footnote_marker_without_definition(self):
        units = [{"id": "01", "title": "Part 1", "text": "An order. 9\n> 9 For orders, see Planning."}]
        checks = self.quality.delivery_checks(units, {"Part 1": "命令。⁹"}, {"Part 1": "命令。⁹"}, [], {"issues": []})
        self.assertFalse(checks["passed"])
        self.assertEqual(checks["blockers"][0]["kind"], "missing_footnote_definition")

    def test_gate_does_not_treat_reference_publication_number_as_a_footnote(self):
        units = [{"id": "01", "title": "Part 1", "text": "Planning. 7\n> 7For planning, see JP\n> 3-30, Joint Air Operations."}]
        text = "计划。⁷\n\n> ⁷ 参见联合空中作战。"
        checks = self.quality.delivery_checks(units, {"Part 1": text}, {"Part 1": text}, [], {"issues": []})
        self.assertEqual(checks["blockers"], [])

    def test_gate_rejects_new_untranslated_word_and_pending_marker(self):
        units = [{"id": "01", "title": "Part 1", "text": "accompanying plans"}]
        checks = self.quality.delivery_checks(units, {"Part 1": "配套计划。"}, {"Part 1": "accompanying 计划。[待审]"}, [], {"issues": []})
        kinds = {x["kind"] for x in checks["blockers"]}
        self.assertIn("new_lowercase_english", kinds)
        self.assertIn("pending_marker", kinds)

    def test_review_receives_source_and_checks_quotes_against_actual_translation(self):
        units = [{"id": "01", "title": "Part 1", "text": "Nodes have different capabilities."}]
        recorder = EvidenceRecorder(self.root, "test-model", ["Part 1"])
        recorder.set_context("initial_review")
        report = {"issues": [{"chapter": "Part 1", "type": "误译", "severity": "major", "source_quote": "different capabilities", "target_quote": "不存在的译句", "detail": "含义错误"}], "chapters_need_revision": ["Part 1"], "summary": "需要修改"}
        with self.assertRaisesRegex(ValueError, "译文定位"):
            self.quality.bilingual_review(fake_client(response(json.dumps(report))), recorder, units, {"Part 1": "节点能力不同。"}, [])
        request = json.loads((self.root / recorder.calls[0]["directory"] / "request.json").read_text(encoding="utf-8"))
        self.assertIn("Nodes have different capabilities.", request["messages"][1]["content"])
        self.assertEqual(recorder.calls[0]["status"], "failed")

    def test_workflow_runs_final_review_and_keeps_failed_candidate_out_of_delivery(self):
        units = [{"id": "01", "title": "Part 1", "text": "PLANNING\nPlanning is a methodology."}]
        recorder = EvidenceRecorder(self.root, "test-model", ["Part 1"], max_calls=13)
        candidates = self.quality.quality_candidates(units)
        chosen = next(x for x in candidates if x["en"].casefold() == "planning")
        glossary = {"glossary": [{"candidate_id": chosen["candidate_id"], "zh": "计划", "category": "process", "definition": "方法", "inclusion_signals": [chosen["signals"][0]], "review_status": "candidate"}], "excluded": [{"candidate_id": x["candidate_id"], "reason": "非独立概念"} for x in candidates if x is not chosen]}
        issue = {"chapter": "Part 1", "type": "误译", "severity": "major", "source_quote": "Planning", "target_quote": "旧错译", "detail": "译名有误"}
        report = {"issues": [issue], "chapters_need_revision": ["Part 1"], "summary": "需修订"}
        decision = {"revise": ["Part 1"], "repair_glossary": False, "reason": "按已定位错误修订"}
        patches = {"patches": [{"old": "旧错译", "new": "正确译文"}]}
        final_issue = {**issue, "target_quote": "正确译文", "detail": "仍有含义问题"}
        final_report = {**report, "issues": [final_issue]}
        draft = {"segments": [{"id": "P001", "text": "计划"}, {"id": "P002", "text": "旧错译。"}], "uncertainties": []}
        texts = [glossary, draft, report, decision, patches, final_report]
        client = fake_client(*[response(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)) for x in texts])
        result = self.quality.execute_quality_workflow(client, recorder, units)
        self.assertEqual(result["quality_status"], "blocked_by_quality_checks")
        self.assertEqual([c["stage"] for c in recorder.calls][-1], "final_review")
        self.assertFalse((self.root / "chapter2_zh.md").exists())
        self.assertTrue((self.root / "chapter2_candidate_zh.md").exists())
        self.assertEqual((self.root / "translations/draft/01.md").read_text(encoding="utf-8"), "计划\n\n旧错译。")
        self.assertEqual((self.root / "translations/revision/01.md").read_text(encoding="utf-8"), "计划\n\n正确译文。")
        alignment = json.loads((self.root / "translation_alignment_01_revision.json").read_text(encoding="utf-8"))
        self.assertEqual(alignment["segments"][1]["text"], "正确译文。")
        recorder.write_index()
        self.assertNotIn("本角色未读取原文", (self.root / "review_guide.md").read_text(encoding="utf-8"))

    def test_gate_can_pass_complete_translation_but_does_not_mark_human_acceptance(self):
        units = [{"id": "01", "title": "Part 1", "text": "An order. 9\n> 9 For orders, see Planning."}]
        text = "命令。⁹\n\n> ⁹ 有关命令，参见《计划》。"
        checks = self.quality.delivery_checks(units, {"Part 1": text}, {"Part 1": text}, [], {"issues": []})
        self.assertTrue(checks["passed"])
        self.assertEqual(checks["blockers"], [])

    def test_manager_glossary_action_produces_new_version_used_by_revision(self):
        units = [{"id": "01", "title": "Part 1", "text": "PLANNING\nPlanning is a methodology."}]
        recorder = EvidenceRecorder(self.root, "test-model", ["Part 1"], max_calls=13)
        candidates = self.quality.quality_candidates(units)
        chosen = next(x for x in candidates if x["en"].casefold() == "planning")
        def glossary_answer(translation):
            return {"glossary": [{"candidate_id": chosen["candidate_id"], "zh": translation, "category": "process", "definition": "方法", "inclusion_signals": [chosen["signals"][0]], "review_status": "candidate"}], "excluded": [{"candidate_id": x["candidate_id"], "reason": "非独立概念"} for x in candidates if x is not chosen]}
        report = {"issues": [{"chapter": "Part 1", "type": "术语", "severity": "major", "source_quote": "Planning", "target_quote": "旧译", "detail": "核对术语译法"}], "chapters_need_revision": ["Part 1"], "summary": "术语需要修订"}
        draft = {"segments": [{"id": "P001", "text": "计划"}, {"id": "P002", "text": "旧译。"}], "uncertainties": []}
        texts = [glossary_answer("计划"), draft, report, {"revise": ["Part 1"], "repair_glossary": True, "reason": "返修术语"}, glossary_answer("规划"), {"patches": [{"old": "旧译", "new": "规划"}]}, {"issues": [], "chapters_need_revision": [], "summary": "未发现问题"}]
        client = fake_client(*[response(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)) for x in texts])
        result = self.quality.execute_quality_workflow(client, recorder, units)
        self.assertEqual(result["quality_status"], "automatic_checks_passed_pending_human_review")
        self.assertEqual(len([c for c in recorder.calls if c["agent"] == "Glossary"]), 2)
        self.assertEqual(json.loads((self.root / "glossary_v1.json").read_text(encoding="utf-8"))[0]["zh"], "计划")
        self.assertEqual(json.loads((self.root / "glossary_v2.json").read_text(encoding="utf-8"))[0]["zh"], "规划")
        revision = next(c for c in recorder.calls if c["stage"] == "revision")
        request = (self.root / revision["directory"] / "request.json").read_text(encoding="utf-8")
        self.assertIn('"zh": "规划"', json.loads(request)["messages"][1]["content"])

    def test_translation_uncertainty_cannot_disappear_at_delivery_gate(self):
        units = [{"id": "01", "title": "Part 1", "text": "The MTO applies."}]
        text = "MTO适用。"
        checks = self.quality.delivery_checks(units, {"Part 1": text}, {"Part 1": text}, [], {"issues": []}, translation_uncertainties={"Part 1": [{"id": "P001", "source_quote": "MTO", "reason": "译名尚需核实"}]})
        self.assertFalse(checks["passed"])
        self.assertEqual(checks["blockers"][0]["kind"], "translation_uncertainty")


if __name__ == "__main__":
    unittest.main()
