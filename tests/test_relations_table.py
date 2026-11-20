# -*- coding: utf-8 -*-
"""角色關係表的回歸測試（v3 P2：關係表改英文鍵）。

示範書沒有關係表，快照測不到，所以這裡自備一份：讀表、送給模型的上下文、回寫（新增／變更／同章重跑／
修訂舊章不動）、從角色檔建草稿、採用草稿、關係圖、新書建表。預期結果（relations_golden.json）是用
改英文鍵之前的程式產生的；檔案內容與上下文必須逐字相同，關係圖的列只差在鍵名。

重產預期結果：UPDATE_SNAPSHOT=1 python -m pytest tests/test_relations_table.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import context, jsonkeys, layout, prompts, relations  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "snapshots", "relations_golden.json")
UPDATE = os.environ.get("UPDATE_SNAPSHOT") == "1"

REL = """---
類型: 關係
更新至: 第002章
---

# 角色關係

| 編號 | 誰 | 對誰 | 關係 | 態度 | 起始章 | 結束章 | 變化原因 | 備註 |
|---|---|---|---|---|---|---|---|---|
| L001 | 林晚 | 沈既白 | 前未婚夫 | 警戒 | 第001章 |  |  | 作者加的欄 |
| L002 | 沈既白 | 林晚 | 前未婚夫 | 愧疚 | 第001章 | 第002章 | 退婚當天後悔 |  |
| L003 | 沈既白 | 林晚 | 舊識 | 好奇 | 第002章 |  | 看見浮字 |  |
| L004 | 林晚 | 小翠 | 主僕 | 信任 | 第001章 |  |  |  |
"""

# 模型回傳的資料（繁中提示詞是中文鍵）；實際流程會先經 jsonkeys.to_keys 換成英文鍵，見 _m()
ITEMS = [{"誰": "林晚", "對誰": "沈既白", "關係": "合作", "態度": "半信半疑", "原因": "一起查帳"},
         {"誰": "小翠", "對誰": "林晚", "關係": "主僕", "態度": "忠心"},
         {"誰": "林晚", "對誰": "小翠", "關係": "主僕", "態度": "信任"},
         {"誰": "林晚", "對誰": "林晚", "關係": "自己"},
         {"誰": "", "對誰": "沈既白", "關係": "x"}]


def _m(items):
    return jsonkeys.to_keys(json.loads(json.dumps(items, ensure_ascii=False)), values=False)


def scenario():
    out = {}
    tmp = tempfile.mkdtemp()
    try:
        book = os.path.join(tmp, "退婚之後")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), book)
        rel_path = layout.path(book, layout.RELATIONS)
        with open(rel_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(REL)
        prompts.set_lang("zh-TW")

        def rd(rel):
            p = layout.path(book, rel)
            return open(p, encoding="utf-8").read() if os.path.isfile(p) else None

        text2 = context.chapter_text(book, 2)[1] or ""
        out["relations_for"] = context.relations_for(book, text2)
        out["relations_for_history"] = context.relations_for(book, text2, history=True)
        out["relations_for_writeback"] = context.relations_for_writeback(book, text2)
        out["active"] = len(relations.active(relations.read_rows(book)))
        out["apply3"] = relations.apply_changes(book, 3, _m(ITEMS))
        out["file_after3"] = rd(layout.RELATIONS)
        out["apply3_again"] = relations.apply_changes(book, 3, _m([{"誰": "林晚", "對誰": "沈既白", "關係": "盟友", "原因": "改口"}]))
        out["file_after3_again"] = rd(layout.RELATIONS)
        out["apply_revision"] = relations.apply_changes(book, 1, _m(ITEMS), revision=True)
        out["file_after_rev"] = rd(layout.RELATIONS)
        out["build_draft"] = relations.build_draft(book)
        out["draft_file"] = rd(layout.RELATIONS_DRAFT)
        out["adopt"] = relations.adopt_draft(book)
        out["file_after_adopt"] = rd(layout.RELATIONS)
        g = relations.graph_data(book)
        out["graph_nodes"] = g["nodes"]
        out["graph_rows"] = g["rows"]
        os.remove(rel_path)
        out["apply_new"] = relations.apply_changes(book, 2, _m(ITEMS[:2]))
        out["file_new"] = rd(layout.RELATIONS)
    finally:
        shutil.rmtree(tmp)
    return json.loads(json.dumps(out, ensure_ascii=False))


class RelationsTableTest(unittest.TestCase):
    maxDiff = None

    def test_matches_golden(self):
        got = scenario()
        if UPDATE or not os.path.exists(GOLDEN):
            with open(GOLDEN, "w", encoding="utf-8", newline="\n") as f:
                json.dump(got, f, ensure_ascii=False, indent=1, sort_keys=True)
                f.write("\n")
            if not UPDATE:
                self.skipTest("第一次執行：已產生預期結果，請確認後提交")
            return
        with open(GOLDEN, encoding="utf-8") as f:
            want = json.load(f)
        for k in sorted(set(want) | set(got)):
            with self.subTest(part=k):
                self.assertEqual(want.get(k), got.get(k))

    def test_english_keys_and_extra_column(self):
        got = scenario()
        self.assertTrue(got["graph_rows"])
        self.assertTrue({"id", "who", "toward", "relationship", "start_chapter"} <= set(got["graph_rows"][0]))
        self.assertIn("作者加的欄", got["file_after3"], "作者自己加的欄位寫回時不能掉")

    def test_model_items_with_english_keys(self):
        """模型給中文鍵（繁中書）或英文鍵（英文、日文書），經 jsonkeys.to_keys 後結果都一樣。"""
        tmp = tempfile.mkdtemp()
        try:
            res = []
            for items in ([{"誰": "林晚", "對誰": "沈既白", "關係": "合作", "原因": "查帳"}],
                          [{"who": "林晚", "toward": "沈既白", "relationship": "合作", "reason": "查帳"}]):
                book = os.path.join(tmp, "b%d" % len(res))
                shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), book)
                with open(layout.path(book, layout.RELATIONS), "w", encoding="utf-8", newline="\n") as f:
                    f.write(REL)
                relations.apply_changes(book, 3, _m(items))
                res.append(open(layout.path(book, layout.RELATIONS), encoding="utf-8").read())
            self.assertEqual(res[0], res[1])
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
