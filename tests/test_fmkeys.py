# -*- coding: utf-8 -*-
"""frontmatter 的鍵：程式內部英文，檔案裡中文、英文寫法都認（v3 P3 第四批）。"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import fmkeys, project, shared  # noqa: E402

ZH = "---\n類型: 章綱\n章號: 3\n章名: 鋪子裡的帳\n狀態: 草稿\n自訂: x\n---\n\n# 第3章\n"
EN = "---\ntype: 章綱\nchapter: 3\ntitle: 鋪子裡的帳\nstatus: 草稿\n自訂: x\n---\n\n# 第3章\n"


class FmKeysTest(unittest.TestCase):
    def test_read_both_spellings(self):
        for text in (ZH, EN):
            fm, body = project.split_frontmatter(text)
            self.assertEqual({"type": "章綱", "chapter": 3, "title": "鋪子裡的帳", "status": "草稿", "自訂": "x"}, fm)
            self.assertEqual("\n# 第3章\n", body)
        self.assertEqual("類型", list(project.split_frontmatter_raw(ZH)[0])[0], "raw 照檔案裡的寫法")

    def test_first_spelling_wins(self):
        fm, _ = project.split_frontmatter("---\n狀態: 草稿\nstatus: approved\n---\n")
        self.assertEqual("草稿", fm["status"])

    def test_set_keeps_file_spelling(self):
        self.assertIn("\n狀態: 已確認\n", project.set_frontmatter_field(ZH, "status", "已確認"))
        self.assertIn("\nstatus: 已確認\n", project.set_frontmatter_field(EN, "status", "已確認"))
        self.assertIn("\n狀態: 已確認\n", project.set_frontmatter_field(ZH, "狀態", "已確認"), "中文鍵也收")

    def test_new_line_follows_write_setting(self):
        self.assertEqual("en", fmkeys.WRITE, "v3 寫英文鍵")
        self.assertEqual("---\ntype: 卷綱\ntitle: 舊帳\n---\n", project.set_frontmatter_field("---\ntype: 卷綱\n---\n", "title", "舊帳"))
        self.assertEqual("---\n類型: 卷綱\ntitle: 舊帳\n---\n", project.set_frontmatter_field("---\n類型: 卷綱\n---\n", "title", "舊帳"),
                         "插在中文的類型後面")
        old = fmkeys.WRITE
        try:
            fmkeys.WRITE = "zh"
            out = project.set_frontmatter_field("---\n類型: 卷綱\n---\n", "title", "舊帳")
            self.assertEqual("---\n類型: 卷綱\n卷名: 舊帳\n---\n", out, "title 依文件類型寫成卷名")
            self.assertIn("書名: 書", project.set_frontmatter_field("---\n類型: 故事核心\n---\n", "title", "書"))
        finally:
            fmkeys.WRITE = old

    def test_shared_set_fm_removes_both_spellings(self):
        text = "---\n名稱: 甲\nname: 乙\n語言: ja\n---\n本文\n"
        self.assertEqual("---\n語言: ja\n---\n本文\n", shared.set_fm(text, "name", None))
        self.assertEqual("---\n名稱: 甲\nname: 乙\nlang: en\n---\n本文\n", shared.set_fm(text, "lang", "en"))

    def test_every_zh_key_maps(self):
        for zh, en in fmkeys.ZH2EN.items():
            self.assertRegex(en, r"^[a-z_]+$", zh)
            self.assertIn(zh, fmkeys.file_keys(en))


if __name__ == "__main__":
    unittest.main()
