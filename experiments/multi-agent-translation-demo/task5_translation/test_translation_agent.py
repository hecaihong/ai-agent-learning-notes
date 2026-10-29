"""Translation 的来源保全和真实错误回归；不把离线检查当模型准确率。"""

from collections import Counter
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from test_translation_evidence import fake_client, response
from translation_evidence import EvidenceRecorder


class TranslationAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = importlib.import_module("translation_agent")

    def plan(self, text):
        return self.agent.prepare_translation({"id": "01", "title": "Part 1", "text": text})

    def payload(self, plan, texts):
        return {"segments": [{"id": part["id"], "text": text} for part, text in zip(plan["segments"], texts)], "uncertainties": []}

    def test_restores_node_sentence_and_keeps_sidebar_and_every_source_character(self):
        source = "Nodes may span several levels of\nBattle Management Example: Global Air Mobility Adjustment\nThe example reports over 600 missions.\n\noperations and have varying levels of capability."
        plan = self.plan(source)
        body = "\n".join(s["source"] for s in plan["segments"] if s["kind"] == "body")
        sidebar = next(s for s in plan["segments"] if s["kind"] == "sidebar")
        self.assertIn("Nodes may span several levels of operations", body)
        self.assertIn("600 missions", sidebar["source"])
        self.assertEqual(Counter(c for c in source if not c.isspace()), Counter(c for s in plan["segments"] for c in s["source"] if not c.isspace()))
        self.assertTrue(plan["layout_repairs"])

    def test_footnote_continuation_is_not_a_new_note_and_main_sentence_is_joined(self):
        plan = self.plan("AETFs are scalable,\n> 9For orders, see JP\n> 3-30, Joint Air Operations.\n\ntailorable organizations.")
        self.assertEqual([s["note_number"] for s in plan["segments"] if s["kind"] == "footnote"], ["9"])
        self.assertIn("AETFs are scalable, tailorable", plan["segments"][0]["source"])
        payload = self.payload(plan, ["AETF是可扩展、可按需编组的组织。", "关于命令，参见JP 3-30。"])
        self.agent.validate_translation(payload, plan)
        self.assertIn("> ⁹ 关于命令", self.agent.render_translation(payload, plan))

    def test_restores_planning_sentence_around_history_panel(self):
        plan = self.plan("iterative planning adapts to address\n> 7For planning, see JP 5-0.\nHistory of the C2 Process\nThe C2 process is not new.\n\nchanging conditions in the OE .")
        body = next(s["source"] for s in plan["segments"] if s["kind"] == "body")
        self.assertEqual(body, "iterative planning adapts to address changing conditions in the OE .")
        self.assertEqual({s["kind"] for s in plan["segments"]}, {"body", "sidebar", "footnote"})

    def test_incomplete_known_layout_fails_instead_of_guessing(self):
        with self.assertRaisesRegex(ValueError, "侧栏"):
            self.plan("Nodes may span several levels of\nBattle Management Example: Global Air Mobility Adjustment\nNo verifiable continuation.")

    def test_glossary_is_relevant_and_compact_but_preserves_uncertainty(self):
        plan = self.plan("A MTO communicates commander's intent.")
        glossary = [{"en": "MTO", "zh": "任务型命令", "review_status": "needs_domain_review", "evidence": "large metadata", "locations": ["somewhere"]}, {"en": "embedding", "zh": "嵌入向量", "review_status": "candidate"}]
        terms = self.agent.compact_glossary(plan, glossary)
        self.assertEqual(terms, [{"en": "MTO", "zh": "任务型命令", "review_status": "needs_domain_review"}])

    def test_glossary_keeps_full_term_when_source_only_uses_acronym(self):
        plan = self.plan("The AETF conducts the C2 process.")
        term = {"en": "air expeditionary task force (AETF)", "zh": "空中远征特遣部队", "review_status": "candidate"}
        self.assertEqual(self.agent.compact_glossary(plan, [term]), [term])

    def test_compact_glossary_keeps_semantic_definition(self):
        plan = self.plan("Command and control have different meanings.")
        term = {"en": "command", "zh": "指挥", "review_status": "candidate", "definition": "为行动赋予目的并作出决策。", "locations": ["Part 1"], "exact_count": 14}
        result = self.agent.compact_glossary(plan, [term])[0]
        self.assertEqual(result["definition"], term["definition"])
        self.assertNotIn("locations", result)
        self.assertNotIn("exact_count", result)

    def test_complete_line_endings_form_smaller_reviewable_segments(self):
        plan = self.plan("The commander decides.\nThe staff coordinates.\nIt acts.")
        self.assertEqual(len(plan["segments"]), 3)

    def test_missing_duplicate_unknown_and_empty_segments_are_rejected(self):
        plan = self.plan("PLANNING\nPlanning is a methodology.")
        valid = self.payload(plan, ["计划", "计划是一种方法。"])
        self.agent.validate_translation(valid, plan)
        for parts in (valid["segments"][:1], valid["segments"] + valid["segments"][:1], [{"id": "P999", "text": "多余"}] + valid["segments"][1:], [{"id": s["id"], "text": ""} for s in valid["segments"]]):
            with self.subTest(parts=parts), self.assertRaises(ValueError):
                self.agent.validate_translation({"segments": parts, "uncertainties": []}, plan)

    def test_known_untranslated_words_are_rejected_but_names_and_acronyms_allowed(self):
        plan = self.plan("The CW commander acted during the Gulf War.")
        for text in ("CW的 commander作出决定。", "Gulf War期间采取行动。"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "英文残留"):
                self.agent.validate_translation(self.payload(plan, [text]), plan)
        self.agent.validate_translation(self.payload(plan, ["海湾战争期间，CW指挥官Downer采取行动。"]), plan)

    def test_missions_and_sorties_cannot_exchange_units_or_lose_numbers(self):
        examples = [("It flew over 600 missions.", "完成600多架次任务。", "完成600多项任务。"), ("It flew 50-60 combat sorties.", "执行50至60项战斗任务。", "执行50至60战斗架次。"), ("It carried 17,000 tons and 47,000 people.", "运输17000吨和4700人。", "运输17000吨和47000人。")]
        for source, bad, good in examples:
            plan = self.plan(source)
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "数字或单位"):
                self.agent.validate_translation(self.payload(plan, [bad]), plan)
            self.agent.validate_translation(self.payload(plan, [good]), plan)

    def test_quantity_check_allows_common_chinese_word_order(self):
        plan = self.plan("It flew over 600 missions and 50-60 combat sorties.")
        self.agent.validate_translation(self.payload(plan, ["完成600多次空运任务和50—60次战斗出动。"]), plan)

    def test_render_uses_source_order_and_uncertainty_requires_source_evidence(self):
        plan = self.plan("PLANNING\nPlanning uses MTO.")
        payload = self.payload(plan, ["计划", "计划采用MTO。"])
        payload["segments"].reverse()
        payload["uncertainties"] = [{"id": "P002", "source_quote": "MTO", "reason": "待核实译名"}]
        self.agent.validate_translation(payload, plan)
        self.assertEqual(self.agent.render_translation(payload, plan), "计划\n\n计划采用MTO。")
        payload["uncertainties"][0]["source_quote"] = "made up"
        with self.assertRaisesRegex(ValueError, "疑点"):
            self.agent.validate_translation(payload, plan)

    def test_revision_cannot_reintroduce_numeric_unit_error(self):
        from run_afdp_quality import apply_patches
        plan = self.plan("It flew over 600 missions.")
        payload = self.payload(plan, ["完成600多项任务。"])
        with self.assertRaisesRegex(ValueError, "数字或单位"):
            self.agent.patch_translation(payload, plan, [{"old": "600多项任务", "new": "600多架次任务"}], apply_patches)
        self.assertEqual(payload["segments"][0]["text"], "完成600多项任务。")

    def test_failed_response_is_retained_without_retries_or_accepted_draft(self):
        parent = Path(__file__).resolve().parent / ".test_tmp"
        parent.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=parent) as folder:
            recorder = EvidenceRecorder(Path(folder), "test-model", ["Part 1"])
            recorder.set_context("draft", "01")
            client = fake_client(response(json.dumps({"segments": [], "uncertainties": []})))
            with self.assertRaises(ValueError):
                self.agent.translate_unit(client, recorder, {"id": "01", "title": "Part 1", "text": "A sentence."}, [])
            self.assertEqual(len(recorder.calls), 1)
            call_dir = recorder.run_dir / recorder.calls[0]["directory"]
            self.assertTrue((call_dir / "output.txt").exists())
            self.assertEqual(recorder.calls[0]["status"], "failed")

    def test_actual_dataset_plan_preserves_all_source_characters(self):
        dataset = Path(__file__).resolve().parent / "afdp_c2_chapter2_20261026/inputs"
        for path in sorted(dataset.glob("*.md")):
            body = path.read_text(encoding="utf-8").split("\n\n", 1)[1].strip()
            with self.subTest(unit=path.name):
                plan = self.plan(body)
                self.assertEqual(Counter(c for c in body if not c.isspace()), Counter(c for s in plan["segments"] for c in s["source"] if not c.isspace()))


if __name__ == "__main__":
    unittest.main()
