# -*- coding: utf-8 -*-
"""反推的 API 層：/reverse 對照欄位、/reverse/diff、/reverse/cards、/bible 的草稿分頁、adopt 路由。"""
import os
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

import app as app_mod

OLD_OUTLINE = """---
類型: 全書大綱
---

# 全書大綱

## 總覽
- 作者核過的主線。
"""

NEW_OUTLINE = """---
類型: 全書大綱
---

# 全書大綱

## 總覽
- 從正文反推的主線。
"""

OLD_VOL = "---\n類型: 卷綱\n卷名: 開場\n章節範圍: 第001章～第010章\n---\n\n# 卷綱：開場\n\n- 作者版。\n"
NEW_VOL = OLD_VOL.replace("作者版", "反推版")

OLD_CARD = "---\n類型: 章綱\n章號: 1\n章名: 大夜班\n---\n\n# 第1章 大夜班\n\n- 作者定的鉤子。\n"
NEW_CARD = OLD_CARD.replace("作者定的鉤子", "反推的鉤子")


def _write(root, rel, text):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


class ReverseApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = self.tmp.name
        self.book_id = "測試書"
        self.book = os.path.join(self.lib, self.book_id)
        _write(self.book, "大綱/全書大綱.md", OLD_OUTLINE)
        _write(self.book, "大綱/卷綱_第1卷.md", OLD_VOL)
        _write(self.book, "大綱/章綱/第001章.md", OLD_CARD)
        _write(self.book, "正文/第001章_大夜班.md", "第一章正文。\n")
        _write(self.book, ".studio/反推/草稿/大綱/全書大綱.md", NEW_OUTLINE)
        _write(self.book, ".studio/反推/草稿/大綱/卷綱_第一卷.md", NEW_VOL)
        _write(self.book, ".studio/反推/草稿/大綱/章綱/第001章_大夜班.md", NEW_CARD)
        _write(self.book, "大綱/章綱/反推/第002章_兩邊.md", NEW_CARD.replace("大夜班", "兩邊"))

        self.patch = mock.patch.dict(app_mod.CONFIG, {"library": self.lib})
        self.patch.start()
        self.client = TestClient(app_mod.app, base_url="http://127.0.0.1:8765")
        self.headers = {"x-fe-token": app_mod.fe.token}

    def tearDown(self):
        self.client.close()
        self.patch.stop()
        self.tmp.cleanup()

    def url(self, rest):
        return "/api/books/" + quote(self.book_id) + rest

    def test_reverse_state_drafts_carry_plan_fields(self):
        r = self.client.get(self.url("/reverse"))
        self.assertEqual(200, r.status_code, r.text)
        drafts = r.json()["state"]["drafts"]
        plan = {x["rel"]: x for x in drafts["大綱"]}
        outline = plan["大綱/全書大綱.md"]
        self.assertEqual(len(OLD_OUTLINE), outline["chars_old"])
        self.assertEqual(len(NEW_OUTLINE), outline["chars_new"])
        self.assertTrue(outline["exists"])
        self.assertEqual("keep", outline["default_mode"])
        self.assertLess(outline["similarity"], 1.0)
        self.assertEqual("大綱/卷綱_第1卷.md", plan["大綱/卷綱_第一卷.md"]["target"])
        chapter = drafts["章綱"][0]
        self.assertEqual("copy", chapter["default_mode"])
        self.assertEqual("大綱/章綱/反推/第001章_大夜班.md", chapter["target"])

    def test_reverse_diff_returns_blocks(self):
        r = self.client.get(self.url("/reverse/diff"), params={"group": "大綱", "rel": "大綱/全書大綱.md"})
        self.assertEqual(200, r.status_code, r.text)
        d = r.json()
        self.assertEqual("大綱/全書大綱.md", d["old_rel"])
        self.assertTrue(any(b["type"] == "change" for b in d["blocks"]))

    def test_reverse_cards_lists_adopted_cards(self):
        r = self.client.get(self.url("/reverse/cards"))
        self.assertEqual(200, r.status_code, r.text)
        cards = r.json()["cards"]
        self.assertEqual(1, len(cards))
        self.assertEqual("大綱/章綱/反推/第002章_兩邊.md", cards[0]["rel"])
        self.assertEqual(2, cards[0]["no"])
        self.assertEqual("兩邊", cards[0]["name"])

    def test_bible_lists_reverse_draft_count_without_mixing(self):
        r = self.client.get(self.url("/bible"))
        self.assertEqual(200, r.status_code, r.text)
        b = r.json()
        self.assertEqual(3, b["reverse_drafts"])
        self.assertEqual([], b["草稿"])

    def test_adopt_route_honours_mode_and_files(self):
        r = self.client.post(self.url("/reverse/adopt"), headers=self.headers,
                             json={"group": "大綱", "mode": "keep", "files": ["大綱/全書大綱.md", "大綱/卷綱_第一卷.md"]})
        self.assertEqual(200, r.status_code, r.text)
        self.assertEqual(2, r.json()["kept"])
        self.assertEqual(0, r.json()["adopted"])
        self.assertEqual(OLD_OUTLINE, open(os.path.join(self.book, "大綱", "全書大綱.md"), encoding="utf-8").read())

        r = self.client.post(self.url("/reverse/adopt"), headers=self.headers,
                             json={"group": "大綱", "mode": "replace", "files": ["大綱/全書大綱.md"]})
        self.assertEqual(200, r.status_code, r.text)
        body = r.json()
        self.assertEqual(1, body["adopted"])
        self.assertEqual(1, body["backed_up"])
        self.assertTrue(os.path.isfile(os.path.join(self.book, ".studio", "備份", body["backups"][0])))

    def test_adopt_route_rejects_mode_not_allowed_for_group(self):
        r = self.client.post(self.url("/reverse/adopt"), headers=self.headers,
                             json={"group": "大綱", "mode": "copy", "files": ["大綱/全書大綱.md"]})
        self.assertEqual(400, r.status_code)
        self.assertIn("不支援", r.json()["error"])


if __name__ == "__main__":
    unittest.main()
