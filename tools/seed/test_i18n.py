"""多语言（i18n）的测试：不依赖系统语言、不改仓库文件。"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "seed"))

from seedbank import i18n  # noqa: E402


class NormalizeTest(unittest.TestCase):
    def test_known_codes(self):
        self.assertEqual(i18n.normalize_locale("zh_CN"), "zh_CN")
        self.assertEqual(i18n.normalize_locale("en_US"), "en_US")
        self.assertEqual(i18n.normalize_locale("ja_JP"), "ja_JP")
        self.assertEqual(i18n.normalize_locale("ko_KR"), "ko_KR")

    def test_common_variants(self):
        self.assertEqual(i18n.normalize_locale("zh"), "zh_CN")
        self.assertEqual(i18n.normalize_locale("zh-CN"), "zh_CN")
        self.assertEqual(i18n.normalize_locale("zh_Hans_CN"), "zh_CN")
        self.assertEqual(i18n.normalize_locale("en-US"), "en_US")
        self.assertEqual(i18n.normalize_locale("en"), "en_US")
        self.assertEqual(i18n.normalize_locale("ja"), "ja_JP")
        self.assertEqual(i18n.normalize_locale("ko-KR"), "ko_KR")

    def test_unknown_falls_back_to_default(self):
        self.assertEqual(i18n.normalize_locale("fr_FR"), "zh_CN")
        self.assertEqual(i18n.normalize_locale(""), "zh_CN")
        self.assertEqual(i18n.normalize_locale(None), "zh_CN")


class DetectTest(unittest.TestCase):
    def test_env_wins(self):
        with mock.patch.dict(os.environ, {"SEEDBANK_LANG": "en_US"}, clear=False):
            self.assertEqual(i18n.detect_locale(), "en_US")

    def test_locale_env(self):
        env = {key: "" for key in ("SEEDBANK_LANG", "LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ["LANG"] = "ja_JP.UTF-8"
            try:
                self.assertEqual(i18n.detect_locale(), "ja_JP")
            finally:
                os.environ.pop("LANG", None)


class TranslateTest(unittest.TestCase):
    def setUp(self):
        self._old_locale = i18n.get_locale()
        self._saved_cache = dict(i18n._cache)
        i18n._cache["en_US"] = {"你好": "Hello", "第 {day} 天": "Day {day}"}

    def tearDown(self):
        i18n.set_locale(self._old_locale)
        i18n._cache.clear()
        i18n._cache.update(self._saved_cache)

    def test_translate_hit(self):
        i18n.set_locale("en_US")
        self.assertEqual(i18n.t("你好"), "Hello")

    def test_translate_missing_returns_source(self):
        i18n.set_locale("en_US")
        self.assertEqual(i18n.t("还没翻的句子"), "还没翻的句子")

    def test_format_args(self):
        i18n.set_locale("en_US")
        self.assertEqual(i18n.t("第 {day} 天", day=3), "Day 3")

    def test_format_bad_args_does_not_raise(self):
        i18n.set_locale("en_US")
        self.assertEqual(i18n.t("你好", extra=1), "Hello")

    def test_text_placeholder_does_not_collide_with_source_argument(self):
        i18n.set_locale("en_US")
        i18n._cache["en_US"]["说明：{text}"] = "Description: {text}"
        self.assertEqual(i18n.t("说明：{text}", text="value {kept}"), "Description: value {kept}")
        self.assertEqual(i18n.t("未翻译：{text}", text="value"), "未翻译：value")

    def test_desktop_text_placeholder_in_translations_and_fallback(self):
        from seedbank.desktop.text import t
        for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            i18n.set_locale(locale)
            with self.subTest(locale=locale):
                self.assertIn("fixture reason", t("理由：{text}", text="fixture reason"))
                self.assertEqual(t("未翻译：{text}", text="fixture"), "未翻译：fixture")

    def test_zh_default_identity(self):
        i18n.set_locale("zh_CN")
        self.assertEqual(i18n.t("你好"), "你好")
        i18n.set_locale("zh")
        self.assertEqual(i18n.t("你好"), "你好")


class LocaleFilesTest(unittest.TestCase):
    def test_labels_exist(self):
        for code in i18n.available_locales():
            self.assertTrue(i18n.locale_label(code).strip())

    def test_locale_json_files_are_valid(self):
        folder = ROOT / "tools" / "seed" / "seedbank" / "locales"
        for code in i18n.available_locales():
            path = folder / f"{code}.json"
            if not path.exists():
                continue  # 允许暂时没有该语言文件（回落中文）
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict, f"{code}.json 必须是对象")
            for key, value in data.items():
                self.assertIsInstance(key, str)
                self.assertIsInstance(value, str)

    def test_keys_file_is_list(self):
        path = ROOT / "tools" / "seed" / "seedbank" / "locales" / "_keys.json"
        if not path.exists():
            self.skipTest("还没有生成 _keys.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)


if __name__ == "__main__":
    unittest.main()
