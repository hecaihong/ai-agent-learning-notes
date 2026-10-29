"""验证发布包不依赖开发者路径、原 PDF 或真实密钥。"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import run_afdp_chapter2 as runner


class PublicPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp_parent = Path(__file__).resolve().parent / ".test_tmp"
        self.temp_parent.mkdir(exist_ok=True)

    def test_bundled_text_is_verified_without_private_pdf(self):
        manifest, units = runner.load_dataset()
        self.assertFalse(manifest["source_pdf_verified"])
        self.assertEqual(len(units), 4)
        self.assertTrue(runner.COURSE_ROLES.is_file())

    def test_explicit_pdf_must_match_original_hash(self):
        with TemporaryDirectory(dir=self.temp_parent) as folder:
            source = Path(folder) / "wrong.pdf"
            source.write_bytes(b"not the original source")
            with self.assertRaisesRegex(ValueError, "PDF"):
                runner.load_dataset(source_pdf=source)

    def test_environment_key_is_used_without_requiring_local_file(self):
        import runtime_config
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key-from-environment"}):
            self.assertEqual(runtime_config.require_api_key(), "test-key-from-environment")

    def test_missing_key_is_explicit_and_does_not_contain_credentials(self):
        import runtime_config
        with TemporaryDirectory(dir=self.temp_parent) as folder, patch.dict(os.environ, {}, clear=True), patch.object(runtime_config, "KEY_FILE", Path(folder) / ".env"):
            with self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
                runtime_config.require_api_key()


if __name__ == "__main__":
    unittest.main()
