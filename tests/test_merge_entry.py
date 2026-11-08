# -*- coding: utf-8 -*-
"""角色「定位」補值，以及設定草稿採用時的合併（project.merge_entry／reverse.adopt）。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import project, reverse

OLD = """---
類型: 角色
名稱: 桐生沙耶
別名: []
定位: ""
首次登場: 3
狀態: 正式
---

# 桐生沙耶

## 一句話
作者寫的設定。

## 內在
- 想要：

## 作者專屬
只有作者知道的事。
"""

NEW = """---
類型: 角色
名稱: 桐生沙耶
別名: [沙耶]
定位: 配角
首次登場: 3
狀態: 草稿
來源: 從正文反推
---

# 桐生沙耶

## 一句話
另一種說法。

## 內在
- 想要：活下去。

## 新段落
新來的。
"""


class EnsureRoleTest(unittest.TestCase):
    def test_blank_role_gets_default(self):
        text = "---\n類型: 角色\n名稱: 甲\n定位:\n狀態: 草稿\n---\n\n# 甲\n"
        out = project.ensure_role(text)
        self.assertEqual(project.split_frontmatter(out)[0]["定位"], project.DEFAULT_ROLE)

    def test_missing_role_is_inserted(self):
        out = project.ensure_role("---\n類型: 角色\n名稱: 甲\n---\n\n# 甲\n")
        self.assertEqual(project.split_frontmatter(out)[0]["定位"], project.DEFAULT_ROLE)

    def test_existing_role_is_kept(self):
        text = "---\n類型: 角色\n名稱: 甲\n定位: 主角\n---\n\n# 甲\n"
        self.assertEqual(project.ensure_role(text), text)

    def test_other_types_untouched(self):
        text = "---\n類型: 勢力\n名稱: 甲\n---\n\n# 甲\n"
        self.assertEqual(project.ensure_role(text), text)


class MergeEntryTest(unittest.TestCase):
    def setUp(self):
        self.text, self.conflicts = project.merge_entry(OLD, NEW)
        self.fm = project.split_frontmatter(self.text)[0]

    def test_frontmatter_fills_only_blank(self):
        self.assertEqual(self.fm["別名"], ["沙耶"])
        self.assertEqual(self.fm["定位"], "配角")
        self.assertEqual(self.fm["首次登場"], 3)

    def test_status_and_source_not_overwritten(self):
        self.assertEqual(self.fm["狀態"], "正式")
        self.assertNotIn("來源", self.fm)

    def test_blank_section_gets_draft_content(self):
        self.assertIn("- 想要：活下去。", self.text)

    def test_author_text_kept(self):
        self.assertIn("作者寫的設定。", self.text)
        self.assertIn("只有作者知道的事。", self.text)

    def test_conflict_listed_and_appended(self):
        self.assertEqual(self.conflicts, ["一句話"])
        self.assertIn("## " + project.REV_SECTION, self.text)
        self.assertIn("另一種說法。", self.text)

    def test_new_section_appended(self):
        self.assertIn("## 新段落", self.text)

    def test_layout_is_clean(self):
        self.assertNotIn("## \n", self.text)
        self.assertTrue(self.text.startswith("---\n類型: 角色\n"))
        self.assertIn("---\n\n# 桐生沙耶", self.text)
        self.assertNotIn("\n\n\n", self.text)

    def test_second_merge_reuses_conflict_section(self):
        again, _ = project.merge_entry(self.text, NEW)
        self.assertEqual(again.count("## " + project.REV_SECTION), 1)


class AdoptMergeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.book = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, text):
        p = os.path.join(self.book, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def read(self, rel):
        with open(os.path.join(self.book, *rel.split("/")), encoding="utf-8") as f:
            return f.read()

    def test_existing_file_is_merged_not_replaced(self):
        self.write("設定/角色/桐生沙耶.md", OLD)
        self.write(reverse.DIR + "/草稿/設定/角色/桐生沙耶.md", NEW)
        res = reverse.adopt(self.book, "設定")
        self.assertEqual(res["adopted"], 1)
        self.assertEqual(res["merged"], 1)
        self.assertEqual(res["conflicts"], 1)
        out = self.read("設定/角色/桐生沙耶.md")
        self.assertIn("作者寫的設定。", out)          # 作者寫的還在
        self.assertTrue(os.path.isdir(os.path.join(self.book, ".studio", "備份")))
        self.assertFalse(os.path.isfile(os.path.join(self.book, reverse.DIR, "草稿", "設定", "角色", "桐生沙耶.md")))

    def test_new_file_is_moved(self):
        self.write(reverse.DIR + "/草稿/設定/角色/新角色.md", NEW.replace("桐生沙耶", "新角色"))
        res = reverse.adopt(self.book, "設定")
        self.assertEqual(res["merged"], 0)
        self.assertIn("# 新角色", self.read("設定/角色/新角色.md"))


if __name__ == "__main__":
    unittest.main()
