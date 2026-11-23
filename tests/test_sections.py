# -*- coding: utf-8 -*-
"""段落標題三語別名表（v3 P3 第五批）：讀得懂三種語言的標題、localize 只換範本認得的東西。"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import contract, drift, goals, project, relations, sections, tracking, volume  # noqa: E402
from studio import layout  # noqa: E402


class LookupTest(unittest.TestCase):
    def test_id_of(self):
        self.assertEqual("one_line", sections.id_of("character", "一句話"))
        self.assertEqual("one_line", sections.id_of("character", "One line"))
        self.assertEqual("one_line", sections.id_of("character", "one line"))
        self.assertEqual("one_line", sections.id_of("character", "ひとこと"))
        self.assertEqual("main_progress", sections.id_of("state-card", "2. Main-line progress"))
        self.assertEqual("current_position", sections.id_of(None, "1. 目前位置"))
        self.assertIsNone(sections.id_of("character", "作者自己加的段落"))

    def test_every_label_maps_back(self):
        for doc, rows in sections.DOCS.items():
            for row in rows:
                for lab in row[1:4] + tuple(row[4]):
                    self.assertEqual(row[0], sections.id_of(doc, lab), (doc, lab))

    def test_find(self):
        body = "## One line\nA lantern.\n\n## Outer\nbrass\n"
        self.assertEqual("A lantern.", sections.find(body, "character", "one_line").strip())
        self.assertEqual("", sections.find(body, "character", "arc"))

    def test_label_follows_write(self):
        self.assertEqual("Plot points", sections.label("chapter-card", "plot_points", "en"))
        self.assertEqual("プロットポイント", sections.label("chapter-card", "plot_points", "ja"))
        self.assertEqual("情節點", sections.label("chapter-card", "plot_points", "zh-TW"))
        old = sections.WRITE
        sections.WRITE = "zh-TW"
        try:
            self.assertEqual("情節點", sections.label("chapter-card", "plot_points", "en"))
        finally:
            sections.WRITE = old


class LocalizeTest(unittest.TestCase):
    def setUp(self):
        self.old = sections.WRITE
        sections.WRITE = "book"

    def tearDown(self):
        sections.WRITE = self.old

    def test_only_known_lines(self):
        t = ("---\ntype: character\nname: 林晚\n---\n\n# 林晚\n\n## 一句話\n- 想要：報仇\n\n## 外在\n- 年齡／身分：十七\n"
             "- 作者的欄：照舊\n\n## 作者的段落\n- 想要：這裡也是範本欄位\n\n```\n## 一句話\n```\n")
        out = sections.localize(t, "character", "en")
        self.assertIn("## One line\n- Wants: 報仇\n", out)
        self.assertIn("## Outer\n- Age / status: 十七\n- 作者的欄：照舊\n", out)
        self.assertIn("## 作者的段落\n", out)
        self.assertIn("```\n## 一句話\n```", out)                 # 程式碼區塊不動
        self.assertIn("name: 林晚", out)                          # frontmatter 不動
        self.assertIn("# 林晚\n", out)                            # 作者取的標題不動

    def test_round_trip_ja(self):
        for f in os.listdir(os.path.join(ROOT, "plugin", "skills", "novel-setup", "templates")):
            p = os.path.join(ROOT, "plugin", "skills", "novel-setup", "templates", f)
            t = project.read_text(p)
            back = sections.localize_doc(sections.localize_doc(t, "ja"), "zh-TW")
            self.assertEqual(t, back, f)

    def test_numbered_and_volume_heads(self):
        t = "---\ntype: book-outline\n---\n\n## 分卷\n\n### 第一卷：退婚\n- 篇幅：第1～60章\n"
        out = sections.localize(t, "book-outline", "en")
        self.assertIn("## Volumes\n\n### Volume 1: 退婚\n- Length: 第1～60章\n", out)
        t = "---\ntype: volume-outline\n---\n\n### 單元一：鋪子（第001～010章）\n"
        self.assertIn("### Unit 1: 鋪子 (ch. 1–10)", sections.localize(t, "volume-outline", "en"))
        self.assertIn("### ユニット一：鋪子（第001～010章）", sections.localize(t, "volume-outline", "ja"))
        t = "---\ntype: state-card\n---\n\n# 狀態卡\n\n## 2. 主線進度\n"
        self.assertEqual("---\ntype: state-card\n---\n\n# State card\n\n## 2. Main-line progress\n",
                         sections.localize(t, "state-card", "en"))

    def test_same_language_untouched(self):
        t = "---\ntype: chapter-card\n---\n\n## 篇章鉤子\n- 停在: 門口\n"
        self.assertEqual(t, sections.localize(t, "chapter-card", "zh-TW"))


class ReadersTest(unittest.TestCase):
    """英文、日文標題的檔，讀取結果跟中文標題一樣。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.book = os.path.join(self.tmp, "b")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), self.book)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _localize_book(self, lang):
        old = sections.WRITE
        sections.WRITE = "book"
        try:
            for dp, _, fs in os.walk(self.book):
                if ".studio" in dp or "_templates" in dp:
                    continue
                for f in fs:
                    if f.endswith(".md"):
                        p = os.path.join(dp, f)
                        t = project.read_text(p)
                        t2 = sections.localize_doc(t, lang)
                        if t2 != t:
                            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                                fh.write(t2)
        finally:
            sections.WRITE = old

    def _snapshot(self):
        d = self.book
        cards = [project.read_text(layout.path(d, layout.CHAPTER_CARDS, layout.chapter_md(n))) for n in (1, 2, 3)]
        style = project.read_text(layout.path(d, layout.STYLE))
        vol = project.read_text(layout.path(d, layout.OUTLINE_VOLUME_ONE))
        return {
            "chars": [(e["name"], e["summary"]) for e in project.list_entries(d, layout.CHARACTERS)],
            "hook": project.read_hook(d),
            "goals": [goals.freeze_goals(c) for c in cards],
            "names": [drift.card_names(c) for c in cards],
            "content": [len(drift.content_of_card(c).splitlines()) for c in cards],   # 欄位名稱會換語言，只比行數
            "dont": contract._section(style, "dont"),
            "basics": contract._section(style, "basics"),
            "contract": volume.contract_bullets(vol),
        }

    def test_same_results(self):
        base = self._snapshot()
        self.assertTrue(base["hook"] and base["chars"][0][1] and base["contract"] and any(base["goals"]))
        for lang in ("en", "ja"):
            self._localize_book(lang)
            got = self._snapshot()
            if lang == "en":       # 卷契約的欄位名稱換成英文，內容不變
                got["contract"] = [x.split(":", 1)[1].strip() for x in got["contract"]]
                want = [x.split("：", 1)[1].strip() for x in base["contract"]]
                self.assertEqual(want, got.pop("contract"))
                base_c = dict(base)
                base_c.pop("contract")
                self.assertEqual(base_c, got, lang)
            else:
                got.pop("contract")
                base_c = dict(base)
                base_c.pop("contract")
                self.assertEqual(base_c, got, lang)

    def test_relations_section(self):
        body = "## Relationships\n- 沈既白：前未婚夫\n\n## Notes\n"
        self.assertIn("沈既白", relations._section(body))

    def test_character_state_keeps_english_fields(self):
        p = layout.path(self.book, layout.CHARACTER_STATES, "林晚.md")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write("---\ntype: character-state\nname: 林晚\n---\n\n# 林晚\n\n- Identity: 林家女兒\n- Location: 鹽倉\n")
        tracking.apply_writeback(self.book, 3, "t", 100, {"characters": [{"name": "林晚", "location": "鋪子"}]})
        text = project.read_text(p)
        self.assertIn("身分：林家女兒", text)          # 英文欄位的舊值有帶過來
        self.assertIn("位置：鋪子", text)

    def test_merge_aligns_languages(self):
        old = "---\ntype: character\nname: 林晚\n---\n\n# 林晚\n\n## One line\nA girl.\n\n## Outer\n\n## Notes\n"
        new = "---\ntype: character\nname: 林晚\n---\n\n# 林晚\n\n## 一句話\n一個女孩。\n\n## 外在\n- 年齡／身分：十七\n"
        text, conflicts = project.merge_entry(old, new)
        self.assertEqual(["一句話"], conflicts)
        self.assertIn("## Outer\n- 年齡／身分：十七", text)
        self.assertNotIn("\n## 外在", text)


if __name__ == "__main__":
    unittest.main()


class VolumeSyncTest(unittest.TestCase):
    """採用卷綱時補進全書大綱：英文書寫英文的卷標題與欄位，認得英文的「Length」。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.book = os.path.join(self.tmp, "b")
        shutil.copytree(os.path.join(ROOT, "demo", "en_TheLanternRoad"), self.book)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_new_volume_in_english(self):
        warn = volume._sync_book_outline(self.book, 3, {"title": "The Far Shore", "chapter_range": [61, 90]},
                                         ["- Selling point of this volume: the sea"])
        self.assertFalse(warn)
        text = project.read_text(layout.path(self.book, layout.BOOK_OUTLINE))
        self.assertIn("### Volume 3: The Far Shore\n\n- Length: chapters 61–90\n- Selling point of this volume: the sea\n"
                      "- Volume outline: `outline/volumes/vol-03.md` (approved)", text)

    def test_existing_volume_range_check(self):
        warn = volume._sync_book_outline(self.book, 1, {"title": "x", "chapter_range": [1, 25]}, ["- Payoff at the end: y"])
        self.assertTrue(warn and "1" in warn[0])          # 範圍對不上：只警告、不改

    def test_existing_volume_adds_bullet(self):
        volume._sync_book_outline(self.book, 1, {"title": "x", "chapter_range": [1, 30]}, ["- Payoff at the end: proof"])
        text = project.read_text(layout.path(self.book, layout.BOOK_OUTLINE))
        self.assertIn("- Length: chapters 1-30\n- Payoff at the end: proof\n", text)
