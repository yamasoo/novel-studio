# -*- coding: utf-8 -*-
"""讀者認知帳本的回歸測試（v3 P2：讀者認知表改英文鍵）。

示範書沒有讀者認知帳本，快照測不到。這裡自備一份夠大的帳本（超過篩選門檻、有作者自己加的欄），跑：
- 上下文：reader_for（整列帶＋只列內容）、reader_for_writeback
- 回寫：新增、回收（upsert）
- 從時間線轉換：merge＋save_draft（模型條目是中文鍵）
- 回收比對：recon_packs、apply_recon（回收、部分揭曉、合併、不合格略過）、採用草稿
- 回寫檢查：章綱點名的 R 編號、「懸念久未回收」提醒
預期結果（reader_table_golden.json）是用改英文鍵之前的程式產生的，必須逐字相同。

重產預期結果：UPDATE_SNAPSHOT=1 python -m pytest tests/test_reader_table.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import context, jsonkeys, layout, prompts, reader_ledger, tracking, wb_check  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "snapshots", "reader_table_golden.json")
UPDATE = os.environ.get("UPDATE_SNAPSHOT") == "1"

TYPES = ["懸念", "誤認", "已知", "懸念"]


def reader_table(n=60):
    rows = ["| 編號 | 類型 | 內容 | 作者真相 | 種下章 | 回收章 | 相關角色 | 作者備註 |",
            "|---|---|---|---|---|---|---|---|"]
    for i in range(1, n + 1):
        t = TYPES[i % 4]
        rec = "" if i % 3 else "第%03d章" % (i // 3 + 2)
        rows.append("| R%03d | %s | 讀者第%d個疑問：沈家帳本的缺頁和林晚的玉珮有沒有關係，周叔是否知情（E%03d） | 答案%d：沈仲廉藏起缺頁 | 第%03d章 | %s | %s | 備%d |"
                    % (i, t, i, i, i, max(1, i // 2), rec, ["林晚", "沈既白", "周叔"][i % 3], i))
    return ("---\n類型: 讀者認知\n更新至: 第030章\n---\n\n# 讀者認知\n\n> 說明。\n\n" + "\n".join(rows) + "\n")


def scenario():
    out = {}
    tmp = tempfile.mkdtemp()
    try:
        book = os.path.join(tmp, "退婚之後")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), book)
        rp = layout.path(book, layout.READER_KNOWLEDGE)
        with open(rp, "w", encoding="utf-8", newline="\n") as f:
            f.write(reader_table())
        prompts.set_lang("zh-TW")

        def rd(rel):
            p = layout.path(book, rel)
            return open(p, encoding="utf-8").read() if os.path.isfile(p) else None

        scope = "本章回收 R004、R010；周叔與沈既白對質。"
        out["reader_for_10"] = context.reader_for(book, scope, 10)
        out["reader_for_25_28"] = context.reader_for(book, "林晚", 25, 28)
        out["reader_for_writeback"] = context.reader_for_writeback(book)
        out["has_ledger"] = context.has_reader_ledger(book)
        out["alerts_40"] = wb_check.alerts(book, 40)
        # 回寫：回收 R004、更新 R005、新增一條懸念、沒內容的新條目略過
        data = {"summary": {"發生了什麼": "對質。"},
                "reader": [{"編號": "R004", "回收章": "第031章"},
                           {"編號": "R005", "內容": "讀者改為懷疑周叔"},
                           {"編號": "新", "類型": "誤認", "內容": "讀者以為玉珮是假的", "種下章": "第031章"},
                           {"編號": "新", "內容": ""}]}
        out["writeback"] = tracking.apply_writeback(book, 31, "對質", 2500, jsonkeys.to_keys(json.loads(json.dumps(data, ensure_ascii=False))))   # 和實際流程一樣先經 jsonkeys 換成英文鍵
        out["ledger_after_wb"] = rd(layout.READER_KNOWLEDGE)
        # 從時間線轉換（繁中提示詞的模型條目是中文鍵，和實際流程一樣先經 jsonkeys；重複內容要去掉）
        items = reader_ledger.merge([jsonkeys.to_keys({"items": [
            {"類型": "懸念", "內容": "誰拿走了缺頁", "種下章": "第002章", "來源": "E001"},
            {"類型": "已知", "內容": "林晚被退婚", "種下章": "第001章"},
            {"類型": "懸念", "內容": "缺頁在誰手上", "種下章": "第004章"},
            {"類型": "誤認", "內容": "讀者以為大伯母是主謀", "種下章": "第003章", "作者真相": "其實是沈仲廉"},
            {"類型": "懸念", "內容": "誰拿走了缺頁", "種下章": "第005章"}]})])
        out["merge"] = jsonkeys.to_zh(items, values=False)   # 用中文鍵記錄，舊程式（中文鍵）與新程式（英文鍵）可以直接比
        out["save_draft"] = reader_ledger.save_draft(book, items)
        out["draft"] = rd(layout.READER_KNOWLEDGE_DRAFT)
        # 回收比對（比對草稿）
        packs = reader_ledger.recon_packs(book, 60000)
        out["recon_packs"] = [[lb, msg] for lb, msg, _ in packs]
        draft_rows = reader_ledger.ledger_source(book)[1]
        ids = sorted(str(r.get("編號") or r.get("id") or "") for r in draft_rows)
        out["draft_ids"] = ids
        out["apply_recon"] = reader_ledger.apply_recon(book, [jsonkeys.to_keys({"changes": [
            {"編號": "R001", "動作": "回收", "回收章": "第002章", "理由": "第2章揭曉"},
            {"編號": "R003", "動作": "部分", "內容": "讀者知道大伯母有參與", "理由": "部分揭曉"},
            {"編號": "R002", "動作": "合併", "合併到": "R001", "理由": "重複"},
            {"編號": "R004", "動作": "回收", "回收章": "第001章", "理由": "已知的不比對"},
            {"編號": "R999", "動作": "回收", "回收章": "第020章"},
            {"編號": "R003", "動作": "回收", "回收章": "第999章"}]})])
        out["draft_after_recon"] = rd(layout.READER_KNOWLEDGE_DRAFT)
        out["adopt"] = tracking.adopt_reader_draft(book)
        out["ledger_after_adopt"] = rd(layout.READER_KNOWLEDGE)
        # 正式帳本的回收比對（沒有草稿時）
        out["recon_on_ledger"] = reader_ledger.apply_recon(book, [jsonkeys.to_keys({"changes": [
            {"編號": "R003", "動作": "回收", "回收章": "第002章", "理由": "x"}]})])
        out["draft_from_ledger"] = rd(layout.READER_KNOWLEDGE_DRAFT)
    finally:
        shutil.rmtree(tmp)
    return json.loads(json.dumps(out, ensure_ascii=False, default=str))


class ReaderTableTest(unittest.TestCase):
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

    def test_scenario_reaches_the_filtered_paths(self):
        got = scenario()
        self.assertLess(got["reader_for_10"].count("\n| R"), 60, "帳本應該被篩選過")
        self.assertIn("作者備註", got["ledger_after_wb"], "作者加的欄寫回時不能掉")
        self.assertTrue(any(a.get("kind") == "懸念久未回收" for a in got["alerts_40"]))
        self.assertIn("回收 1 條、部分揭曉 1 條、合併 1 條", got["apply_recon"])
        self.assertIn("回收 1 條", got["recon_on_ledger"])


if __name__ == "__main__":
    unittest.main()
