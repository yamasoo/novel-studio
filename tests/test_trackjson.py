# -*- coding: utf-8 -*-
"""追蹤表的 JSON 正本（v3 P3 第六批）：.md 與 JSON 怎麼保持一致。"""
import json
import re
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import layout, migrate, project, tables, tracking, trackjson  # noqa: E402

FS = layout.FORESHADOWING


class TrackJsonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.book = os.path.join(self.tmp, "b")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), self.book)
        self.md = layout.path(self.book, FS)
        self.js = layout.path(self.book, trackjson.json_rel(FS))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _parse_md(self):
        h, r = project.parse_md_table(project.read_text(self.md))
        return {"exists": True, "headers": h, "rows": r, "file": FS}

    def test_demo_json_matches_md(self):
        for rel in trackjson.CANON:
            if os.path.isfile(layout.path(self.book, rel)):
                self.assertEqual("same", trackjson.state(self.book, rel)[0], rel)
        self.assertEqual(self._parse_md(), project.read_table(self.book, FS))

    def test_write_mirrors(self):
        text = project.read_text(self.md).replace("| F001 |", "| F001 |", 1) + "\n"
        project.write_atomic(self.md, text)
        self.assertEqual("same", trackjson.state(self.book, FS)[0])
        d = json.load(open(self.js, encoding="utf-8"))
        self.assertEqual(["id", "content", "planted_in", "planned_payoff", "last_seen", "status", "priority"],
                         [c["key"] for c in d["columns"]])
        self.assertEqual(2, d["updated_through"])

    def test_md_edited_by_hand_wins(self):
        with open(self.md, "a", encoding="utf-8", newline="\n") as f:      # 不經 write_atomic：像技能或編輯器直接改
            f.write("| F099 | 手動加的 | 第002章 |  | 第002章 | 已埋 | 低 |\n")
        self.assertEqual("md", trackjson.state(self.book, FS)[0])
        rows = project.read_table(self.book, FS)["rows"]
        self.assertEqual("手動加的", rows[-1]["內容"])
        self.assertEqual(["tracking/foreshadowing.md"], [r for r in trackjson.sync(self.book) if r == FS])
        self.assertEqual("same", trackjson.state(self.book, FS)[0])
        self.assertEqual("手動加的", json.load(open(self.js, encoding="utf-8"))["items"][-1]["content"])

    def test_json_edited_by_tool_wins(self):
        d = json.load(open(self.js, encoding="utf-8"))
        d["items"][0]["content"] = "工具改的"
        with open(self.js, "w", encoding="utf-8") as f:
            f.write(trackjson.dump(d))
        self.assertEqual("json", trackjson.state(self.book, FS)[0])
        self.assertEqual("工具改的", project.read_table(self.book, FS)["rows"][0]["內容"])   # 讀取以 JSON 為準
        before = project.read_text(self.md)
        trackjson.sync(self.book)
        after = project.read_text(self.md)
        self.assertIn("工具改的", after)
        self.assertEqual(before.split("|")[0], after.split("|")[0], "表格前面的內容不動")
        self.assertEqual("same", trackjson.state(self.book, FS)[0])

    def test_deleted_md_means_no_table(self):
        os.remove(self.md)
        self.assertEqual("deleted", trackjson.state(self.book, FS)[0])
        self.assertFalse(project.read_table(self.book, FS)["exists"])
        trackjson.sync(self.book)
        self.assertFalse(os.path.exists(self.js))

    def test_json_only_renders_md(self):
        d = json.load(open(self.js, encoding="utf-8"))
        d.pop("md_sha")
        os.remove(self.md)
        with open(self.js, "w", encoding="utf-8") as f:
            f.write(trackjson.dump(d))
        self.assertEqual("json_only", trackjson.state(self.book, FS)[0])
        trackjson.sync(self.book)
        self.assertEqual(len(d["items"]), len(tables.read(self.book, "foreshadow", FS)["rows"]))
        self.assertEqual("same", trackjson.state(self.book, FS)[0])

    def test_reading_never_writes(self):
        os.remove(self.js)
        project.read_table(self.book, FS)
        tables.read(self.book, "foreshadow", FS)
        self.assertFalse(os.path.exists(self.js))

    def test_writeback_keeps_json_in_step(self):
        os.remove(self.js)
        tracking.apply_writeback(self.book, 3, "t", 100, {"foreshadow": [{"id": "F001", "last_seen": "第003章"}]})
        for rel in trackjson.CANON:
            if os.path.isfile(layout.path(self.book, rel)):
                self.assertEqual("same", trackjson.state(self.book, rel)[0], rel)

    def test_missing_json_is_not_old_format(self):
        os.remove(self.js)
        self.assertFalse(migrate.needs_migration(self.book))

    def test_drafts_have_no_json(self):
        p = layout.path(self.book, ".studio/reverse/drafts/" + FS)
        project.write_atomic(p, project.read_text(self.md))
        self.assertFalse(os.path.exists(p[:-3] + ".json"))


if __name__ == "__main__":
    unittest.main()


class TableLanguageTest(unittest.TestCase):
    """表頭與固定值依書的語言（v3 P3 6b）：程式拿到的值不變、JSON 存 ID 與整數。"""

    def test_values(self):
        self.assertEqual("已埋", tables.internal("foreshadow", "status", "planted"))
        self.assertEqual("已埋", tables.internal("foreshadow", "status", "仕込み済み"))
        self.assertEqual("推進中", tables.internal("foreshadow", "status", "developing"))
        self.assertEqual("第003章", tables.internal("foreshadow", "planted_in", "Ch. 3"))
        self.assertEqual("第4章", tables.internal("foreshadow", "planned_payoff", "第4章"))      # 繁中原樣
        self.assertEqual("卷末", tables.internal("foreshadow", "planned_payoff", "卷末"))
        self.assertEqual("very important", tables.internal("foreshadow", "priority", "very important"))
        self.assertEqual("paid-off", tables.to_json("foreshadow", "status", "已回收"))
        self.assertEqual(4, tables.to_json("foreshadow", "planned_payoff", "第4章"))
        self.assertEqual("卷末", tables.to_json("foreshadow", "planned_payoff", "卷末"))
        self.assertEqual("question", tables.to_json("reader", "type", "懸念"))
        self.assertEqual("已回收", tables.internal("foreshadow", "status", "paid-off"))     # JSON 的 ID 讀回來
        self.assertEqual("勢力", tables.internal("reader", "type", "faction"))
        self.assertEqual("地名", tables.internal("glossary", "kind", "地名"))             # 名詞表類別不換

    def test_render(self):
        rows = [{"id": "F001", "content": "x", "planted_in": "第003章", "status": "已埋", "priority": "高"}]
        zh = tables.render("foreshadow", tables.keys("foreshadow"), rows, "zh-TW")
        self.assertEqual(tracking._render_table(tables.headers("foreshadow"), tables.rows_to_headers("foreshadow", rows)), zh)
        en = tables.render("foreshadow", tables.keys("foreshadow"), rows, "en")
        self.assertIn("| ID | Content | Planted in |", en)
        self.assertIn("| F001 | x | Ch. 3 |  |  | planted | high |", en)
        ja = tables.render("foreshadow", tables.keys("foreshadow"), rows, "ja")
        self.assertIn("| F001 | x | 第3章 |  |  | 仕込み済み | 高 |", ja)

    def test_any_language_reads_the_same(self):
        rows = [{"id": "R001", "type": "誤認", "content": "c", "planted_chapter": "第002章", "resolved_in": "第005章"}]
        ks = tables.keys("reader")
        for lang in ("en", "ja"):
            md = "---\ntype: reader-knowledge\n---\n\n" + tables.render("reader", ks, rows, lang) + "\n"
            h, r = project.parse_md_table(md)
            got = tables.rows_to_keys("reader", r)[0]
            self.assertEqual("誤認", got["type"], lang)
            self.assertEqual(2, int(re.search(r"\d+", got["planted_chapter"]).group(0)), lang)

    def test_relocalize_keeps_zh(self):
        text = project.read_text(layout.path(os.path.join(ROOT, "demo", "退婚之後"), FS))
        self.assertEqual(text, tables.relocalize(text, "foreshadow", "zh-TW"))
        en = tables.relocalize(text, "foreshadow", "en")
        self.assertEqual(tables.rows_to_keys("foreshadow", project.parse_md_table(text)[1]),
                         tables.rows_to_keys("foreshadow", project.parse_md_table(en)[1]))
        self.assertEqual(text, tables.relocalize(en, "foreshadow", "zh-TW"), "英文換回繁中，跟原本逐字相同")

    def test_english_book_writeback_and_json(self):
        tmp = tempfile.mkdtemp()
        try:
            b = os.path.join(tmp, "b")
            shutil.copytree(os.path.join(ROOT, "demo", "en_TheLanternRoad"), b)
            tracking.apply_writeback(b, 3, "t", 100, {"foreshadow": [{"id": "新", "content": "a key", "planted_in": "第003章",
                                                                      "status": "已埋", "priority": "高"}]})
            md = project.read_text(layout.path(b, FS))
            self.assertIn("| F005 | a key | Ch. 3 |", md)
            self.assertIn("| planted | high |", md)
            d = json.load(open(layout.path(b, trackjson.json_rel(FS)), encoding="utf-8"))
            last = d["items"][-1]
            self.assertEqual((3, "planted", "high"), (last["planted_in"], last["status"], last["priority"]))
            self.assertEqual("已埋", tables.read(b, "foreshadow", FS)["rows"][-1]["status"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class EnglishModelOutputTest(unittest.TestCase):
    """v3 P4：英文書的模型照新提示詞寫「Ch. 3」「not revealed」，回寫、續寫合約都讀得懂。"""

    def test_ch_and_not_revealed(self):
        from studio import contract
        tmp = tempfile.mkdtemp()
        try:
            b = os.path.join(tmp, "b")
            shutil.copytree(os.path.join(ROOT, "demo", "en_TheLanternRoad"), b)
            tracking.apply_writeback(b, 3, "t", 100, {
                "foreshadow": [{"id": "新", "content": "a key", "planted_in": "Ch. 3", "planned_payoff": "Ch. 9",
                                "last_seen": "Ch. 3", "status": "planted", "priority": "high"}],
                "timeline": [{"id": "新", "story_time": "dawn", "what_really_happened": "the key was swapped",
                              "reader_knows_now": "nothing", "revealed_in": "not revealed", "related_characters": "Wren"}]})
            fs = tables.read(b, "foreshadow", FS)["rows"][-1]
            self.assertEqual(("第003章", "第009章", "已埋"), (fs["planted_in"], fs["planned_payoff"], fs["status"]))
            self.assertIn("| a key | Ch. 3 | Ch. 9 | Ch. 3 | planted | high |", project.read_text(layout.path(b, FS)))
            known, hidden = contract.secrets(b)
            self.assertIn("the key was swapped", [x[1] for x in hidden])
            self.assertNotIn("the key was swapped", [x[1] for x in known])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
