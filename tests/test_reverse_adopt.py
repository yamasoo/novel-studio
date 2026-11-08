# -*- coding: utf-8 -*-
"""反推草稿的採用安全：章綱另存、逐檔三選、覆蓋先備份、卷綱檔名統一。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import project, reverse

OLD_OUTLINE = """---
類型: 全書大綱
---

# 全書大綱

## 總覽
- 作者核過的主線。

## 分卷
### 第一卷：開場
- 作者寫的卷。
"""

NEW_OUTLINE = """---
類型: 全書大綱
---

# 全書大綱

## 總覽
- 從正文反推的主線。

## 分卷
### 第一卷：開場
- 反推寫的卷。
"""

OLD_VOL = """---
類型: 卷綱
卷名: 開場
章節範圍: 第001章～第010章
---

# 卷綱：開場

## 卷契約
- 本卷賣點：作者版。
"""

NEW_VOL = OLD_VOL.replace("作者版", "反推版")

OLD_CARD = """---
類型: 章綱
章號: 1
章名: 大夜班
---

# 第1章 大夜班

## 章末鉤子
- 停在：作者定的鉤子。
"""

NEW_CARD = OLD_CARD.replace("作者定的鉤子", "反推的鉤子")

OLD_FS = """---
類型: 伏筆
更新至: 第001章
---

# 伏筆總表

| 編號 | 內容 |
|---|---|
| F001 | 作者寫的伏筆 |
"""

NEW_FS = OLD_FS.replace("作者寫的伏筆", "反推的伏筆")

OLD_CHAR = """---
類型: 角色
名稱: 周遠
狀態: 正式
---

# 周遠

## 一句話
作者寫的設定。

## 作者專屬
只有作者知道的事。
"""

NEW_CHAR = """---
類型: 角色
名稱: 周遠
狀態: 草稿
---

# 周遠

## 一句話
從正文反推的一句話。

## 作者專屬
只有作者知道的事。

## 新段落
反推多出來的段落。
"""

NEW_CORE = """---
類型: 故事核心
---

# 故事核心

## 一句話鉤子
反推的核心。
"""


def _write(root, rel, text):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _read(root, rel):
    return project.read_text(os.path.join(root, *rel.split("/")))


def _draft(root, rel, text):
    _write(os.path.join(root, ".studio", "反推", "草稿"), rel, text)


class ReverseAdoptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.book = os.path.join(self.tmp.name, "test-book")
        _write(self.book, "大綱/全書大綱.md", OLD_OUTLINE)
        _write(self.book, "大綱/卷綱_第1卷.md", OLD_VOL)
        _write(self.book, "大綱/章綱/第001章.md", OLD_CARD)
        _write(self.book, "追蹤/伏筆.md", OLD_FS)
        _write(self.book, "設定/角色/周遠.md", OLD_CHAR)
        _draft(self.book, "大綱/全書大綱.md", NEW_OUTLINE)
        _draft(self.book, "大綱/卷綱_第一卷.md", NEW_VOL)   # 舊版中文檔名也要落到「第1卷」
        _draft(self.book, "大綱/章綱/第001章_大夜班.md", NEW_CARD)
        _draft(self.book, "追蹤/伏筆.md", NEW_FS)
        _draft(self.book, "設定/角色/周遠.md", NEW_CHAR)
        _draft(self.book, "設定/故事核心.md", NEW_CORE)

    def tearDown(self):
        self.tmp.cleanup()

    def test_chapter_cards_never_overwrite_formal(self):
        before = _read(self.book, "大綱/章綱/第001章.md")
        mtime = os.path.getmtime(os.path.join(self.book, "大綱", "章綱", "第001章.md"))
        r = reverse.adopt(self.book, "章綱")
        self.assertEqual(before, _read(self.book, "大綱/章綱/第001章.md"))
        self.assertEqual(mtime, os.path.getmtime(os.path.join(self.book, "大綱", "章綱", "第001章.md")))
        self.assertEqual(r["adopted"], 1)
        self.assertTrue(os.path.isfile(os.path.join(self.book, "大綱", "章綱", "反推", "第001章_大夜班.md")))
        self.assertFalse(os.path.isfile(os.path.join(self.book, ".studio", "反推", "草稿", "大綱", "章綱", "第001章_大夜班.md")))

    def test_outline_default_keeps_everything(self):
        old = _read(self.book, "大綱/全書大綱.md")
        vol = _read(self.book, "大綱/卷綱_第1卷.md")
        mt = os.path.getmtime(os.path.join(self.book, "大綱", "全書大綱.md"))
        r = reverse.adopt(self.book, "大綱")
        self.assertEqual(r["kept"], 2)
        self.assertEqual(r["adopted"], 0)
        self.assertEqual(old, _read(self.book, "大綱/全書大綱.md"))
        self.assertEqual(vol, _read(self.book, "大綱/卷綱_第1卷.md"))
        self.assertEqual(mt, os.path.getmtime(os.path.join(self.book, "大綱", "全書大綱.md")))
        # 保留現有時草稿留著，之後還能改選
        self.assertTrue(os.path.isfile(os.path.join(self.book, ".studio", "反推", "草稿", "大綱", "全書大綱.md")))

    def test_replace_backs_up_before_overwriting(self):
        r = reverse.adopt(self.book, "大綱", mode="replace", files=["大綱/全書大綱.md"])
        self.assertEqual(r["adopted"], 1)
        self.assertEqual(r["backed_up"], 1)
        self.assertEqual(len(r["backups"]), 1)
        bak = os.path.join(self.book, ".studio", "備份", r["backups"][0])
        self.assertTrue(os.path.isfile(bak))
        self.assertEqual(OLD_OUTLINE, project.read_text(bak))
        self.assertEqual(NEW_OUTLINE, _read(self.book, "大綱/全書大綱.md"))
        # 只處理指定的那一份
        self.assertTrue(os.path.isfile(os.path.join(self.book, ".studio", "反推", "草稿", "大綱", "卷綱_第一卷.md")))

    def test_settings_merge_never_drops_author_text(self):
        r = reverse.adopt(self.book, "設定")
        text = _read(self.book, "設定/角色/周遠.md")
        self.assertIn("作者寫的設定。", text)
        self.assertIn("只有作者知道的事。", text)
        self.assertEqual(r["merged"], 1)
        self.assertGreater(r["conflicts"], 0)
        self.assertIn("從正文反推（未併入，請核對）", text)
        self.assertEqual(1, r["backed_up"])
        self.assertEqual(NEW_CORE, _read(self.book, "設定/故事核心.md"))

    def test_old_volume_draft_lands_on_numbered_filename(self):
        r = reverse.adopt(self.book, "大綱", mode="replace", files=["大綱/卷綱_第一卷.md"])
        self.assertEqual(r["adopted"], 1)
        self.assertTrue(os.path.isfile(os.path.join(self.book, "大綱", "卷綱_第1卷.md")))
        self.assertEqual(NEW_VOL, _read(self.book, "大綱/卷綱_第1卷.md"))
        self.assertFalse(os.path.exists(os.path.join(self.book, "大綱", "卷綱_第一卷.md")))
        self.assertEqual(r["targets"][0]["dst"], "大綱/卷綱_第1卷.md")

    def test_render_outline_uses_numbered_volume_file(self):
        _outline, vfiles = reverse.render_outline({}, [{"卷名": "開場", "起": 1, "訖": 10}], [])
        self.assertEqual(["大綱/卷綱_第1卷.md"], [rel for rel, _ in vfiles])

    def test_plan_group_similarity_and_defaults(self):
        plan = {x["rel"]: x for x in reverse.plan_group(self.book, "大綱")}
        vol = plan["大綱/卷綱_第一卷.md"]
        self.assertEqual(vol["target"], "大綱/卷綱_第1卷.md")
        self.assertEqual(vol["default_mode"], "keep")
        self.assertEqual(vol["chars_old"], len(OLD_VOL))
        self.assertEqual(vol["chars_new"], len(NEW_VOL))
        self.assertLess(vol["similarity"], 1.0)

        # 完全相同 → 1.0；完全不同 → 接近 0
        _draft(self.book, "大綱/卷綱_第一卷.md", OLD_VOL)
        plan = {x["rel"]: x for x in reverse.plan_group(self.book, "大綱")}
        self.assertEqual(plan["大綱/卷綱_第一卷.md"]["similarity"], 1.0)
        _draft(self.book, "大綱/卷綱_第一卷.md", "\n".join("第%d行：完全不同的內容" % i for i in range(20)) + "\n")
        plan = {x["rel"]: x for x in reverse.plan_group(self.book, "大綱")}
        self.assertLess(plan["大綱/卷綱_第一卷.md"]["similarity"], 0.2)

        chapter = reverse.plan_group(self.book, "章綱")[0]
        self.assertTrue(chapter["exists"])
        self.assertEqual(chapter["target"], "大綱/章綱/反推/第001章_大夜班.md")
        self.assertEqual(chapter["default_mode"], "copy")

    def test_diff_group_compares_against_formal_card(self):
        d = reverse.diff_group(self.book, "章綱", "大綱/章綱/第001章_大夜班.md")
        self.assertEqual(d["old_rel"], "大綱/章綱/第001章.md")
        self.assertTrue(any(b["type"] == "change" for b in d["blocks"]))

    def test_legacy_two_argument_call_and_bad_mode(self):
        r = reverse.adopt(self.book, "追蹤")          # 舊呼叫：只有兩個參數
        self.assertEqual(r["kept"], 1)
        self.assertEqual(OLD_FS, _read(self.book, "追蹤/伏筆.md"))
        with self.assertRaises(project.ProjectError):
            reverse.adopt(self.book, "章綱", mode="replace")
        with self.assertRaises(project.ProjectError):
            reverse.adopt(self.book, "大綱", mode="keep", files=["大綱/不存在.md"])


if __name__ == "__main__":
    unittest.main()
