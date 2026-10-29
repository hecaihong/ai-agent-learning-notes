"""续行只复用请求完全相同的已保存响应，不重复收费调用。"""

import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from test_translation_evidence import fake_client, response


class ReplayTests(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("resume_afdp_quality")
        except ModuleNotFoundError as exc:
            if exc.name != "resume_afdp_quality":
                raise
            self.fail("尚未实现显式复用已保存响应的续行器")
        parent = Path(__file__).resolve().parent / ".test_tmp"
        parent.mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        folder = self.root / "agents/001"
        folder.mkdir(parents=True)
        self.request = {"model": "test-model", "messages": [{"role": "user", "content": "原请求"}]}
        for path, value in ((self.root / "agent_calls.json", [{"directory": "agents/001"}]), (folder / "request.json", self.request), (folder / "response.json", {"id": "saved-response", "choices": []})):
            path.write_text(json.dumps(value), encoding="utf-8")

    def test_reuses_saved_response_then_enforces_remaining_api_budget(self):
        client = self.module.ReplayClient(fake_client(response("新请求")), self.root, 1, 1)
        cached = client.chat.completions.create(**self.request).model_dump(mode="json")
        self.assertEqual(cached["id"], "saved-response")
        self.assertEqual(client.new_call_count, 0)
        fresh = client.chat.completions.create(model="test-model", messages=[]).model_dump(mode="json")
        self.assertEqual(fresh["choices"][0]["message"]["content"], "新请求")
        self.assertEqual(client.new_call_count, 1)
        with self.assertRaisesRegex(RuntimeError, "预算"):
            client.chat.completions.create(model="test-model", messages=[])

    def test_changed_request_is_rejected_without_charging_or_skipping_cache(self):
        client = self.module.ReplayClient(fake_client(), self.root, 1, 1)
        with self.assertRaisesRegex(ValueError, "不一致"):
            client.chat.completions.create(model="different-model", messages=[])
        self.assertEqual(client.new_call_count, 0)
        self.assertEqual(client.replayed_call_count, 0)
