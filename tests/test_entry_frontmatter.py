# -*- coding: utf-8 -*-
"""設定檔 frontmatter 不被標點轉換弄壞，以及舊檔（欄名寫成全形冒號）的修復。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import native_files, project, textguard

BAD = "---\n類型： 角色\n名稱： 甲\n定位： 主角\n狀態： 正式\n---\n\n# 甲\n"
GOOD = "---\n類型: 角色\n名稱: 甲\n定位: 主角\n狀態: 正式\n---\n\n# 甲\n"


class FrontmatterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.book = self._tmp.name
        os.makedirs(os.path.join(self.book, ".studio"), exist_ok=True)
        with open(os.path.join(self.book, ".studio", "lang"), "w", encoding="utf-8") as f:
            f.write("zh-TW")

    def tearDown(self):
        self._tmp.cleanup()

    def test_split_reads_broken_frontmatter(self):
        fm, _ = project.split_frontmatter(BAD)
        self.assertEqual(fm["名稱"], "甲")
        self.assertEqual(fm["定位"], "主角")

    def test_normalize_repairs_only_frontmatter(self):
        text = "---\n類型： 角色\n名稱： 甲：乙\n---\n\n# 甲\n\n他說: 走吧。\n"
        out = project.normalize_frontmatter(text)
        self.assertIn("類型: 角色", out)
        self.assertIn("名稱: 甲：乙", out)          # 值裡的全形冒號不動
        self.assertIn("他說: 走吧。", out)          # 正文不動

    def test_normalize_leaves_good_file_alone(self):
        self.assertEqual(project.normalize_frontmatter(GOOD), GOOD)

    def test_set_field_repairs_the_file(self):
        out = project.set_frontmatter_field(BAD, "定位", "配角")
        fm, _ = project.split_frontmatter(out)
        self.assertEqual(fm["定位"], "配角")
        self.assertEqual(fm["名稱"], "甲")
        self.assertEqual(out.count("定位"), 1)

    def test_guard_does_not_touch_frontmatter(self):
        text = GOOD + "\n他說: 走吧。\n"
        out, _ = textguard.guard_text(self.book, text)
        self.assertTrue(out.startswith(GOOD[:GOOD.index("# 甲")].rstrip("\n")))
        self.assertIn("他說： 走吧。", out)          # 正文照樣轉標點

    def test_apply_blocks_keeps_frontmatter_and_fills_role(self):
        rel = "設定/角色/丙.md"
        done, _ = native_files.apply_blocks(
            self.book, [(rel, "---\n類型: 角色\n名稱: 丙\n狀態: 草稿\n---\n\n# 丙\n\n## 一句話\n他說: 走吧。\n")], [], None)
        with open(os.path.join(self.book, *rel.split("/")), encoding="utf-8") as f:
            raw = f.read()
        fm, _ = project.split_frontmatter(raw)
        self.assertEqual(fm["類型"], "角色")
        self.assertEqual(fm["定位"], project.DEFAULT_ROLE)
        self.assertIn("他說： 走吧。", raw)


if __name__ == "__main__":
    unittest.main()
