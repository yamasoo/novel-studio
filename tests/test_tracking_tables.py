# -*- coding: utf-8 -*-
"""伏筆表、時間線的回歸測試（v3 P2：追蹤表改英文鍵）。

示範書的伏筆、時間線很短，只走得到「整份帶」的路徑；回寫也不在快照裡。這裡自備一份夠大的表
（超過篩選門檻、有作者自己加的欄），跑：
- 上下文：foreshadow_for（整條帶＋索引）、timeline_for（篩選＋未解疑問）
- 回寫：upsert（新增、更新、修訂舊章不讓「最後出現」倒退、編號補號），模型資料用中文鍵與英文鍵各一次
- 總覽的伏筆提醒、續寫合約（threads、secrets）、回寫檢查（wb_check.check）、讀者認知轉換的提示詞
預期結果（tracking_tables_golden.json）是用改英文鍵之前的程式產生的，必須逐字相同。

重產預期結果：UPDATE_SNAPSHOT=1 python -m pytest tests/test_tracking_tables.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import context, contract, jsonkeys, layout, project, prompts, reader_ledger, tracking, wb_check  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "snapshots", "tracking_tables_golden.json")
UPDATE = os.environ.get("UPDATE_SNAPSHOT") == "1"

STATUSES = ["已埋", "推進中", "已回收", "廢棄", "推進中"]
LEVELS = ["高", "中", "低"]


def fs_table(n=40):
    rows = ["| 編號 | 內容 | 埋設章 | 預計回收 | 最後出現 | 狀態 | 重要度 | 作者備註 |",
            "|---|---|---|---|---|---|---|---|"]
    for i in range(1, n + 1):
        due = 1 if i % 6 == 0 else i + 3      # 一部分預計回收章早於最新章，總覽才會出「已過預計回收」
        rows.append("| F%03d | 第%d條伏筆：林晚在鋪子裡發現的線索之%d，牽涉沈家舊帳 | 第%03d章 | 第%d章 | 第%03d章 | %s | %s | 備%d |"
                    % (i, i, i, max(1, i // 2), due, max(1, i // 2 + 1), STATUSES[i % 5], LEVELS[i % 3], i))
    return "---\n類型: 伏筆總表\n更新至: 第020章\n---\n\n# 伏筆總表\n\n" + "\n".join(rows) + "\n\n> 表格後面的說明文字要保留。\n"


def tl_table(n=90):
    rows = ["| 編號 | 故事時間 | 實際發生（作者真相） | 讀者目前知道 | 揭示章 | 相關角色 |", "|---|---|---|---|---|---|"]
    for i in range(1, n + 1):
        known = ["", "林晚只知道帳本有缺頁", "讀者以為是大伯母做的", "已全部揭曉：沈仲廉挪用公款"][i % 4]
        rev = ["未揭示", "第%03d章" % (i // 3 + 1), "第%03d章" % (i // 4 + 1), "第%03d章" % (i // 5 + 1)][i % 4]
        rows.append("| E%03d | 退婚前%d年 | 沈家第%d筆舊帳由沈仲廉經手，帳目與玉珮有關，詳情涉及當年的鋪子轉手與周叔的證詞 | %s | %s | %s |"
                    % (i, i, i, known, rev, ["林晚", "沈既白", "周叔", "林晚、沈既白"][i % 4]))
    return "---\n類型: 時間線\n更新至: 第020章\n---\n\n# 時間線\n\n" + "\n".join(rows) + "\n"


def scenario():
    out = {}
    tmp = tempfile.mkdtemp()
    try:
        book = os.path.join(tmp, "退婚之後")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), book)
        with open(layout.path(book, layout.FORESHADOWING), "w", encoding="utf-8", newline="\n") as f:
            f.write(fs_table())
        with open(layout.path(book, layout.TIMELINE), "w", encoding="utf-8", newline="\n") as f:
            f.write(tl_table())
        prompts.set_lang("zh-TW")

        def rd(rel):
            p = layout.path(book, rel)
            return open(p, encoding="utf-8").read() if os.path.isfile(p) else None

        scope = "本章林晚和沈既白談 F003、F017 與 E012；周叔出場。"
        out["foreshadow_for_10"] = context.foreshadow_for(book, scope, 10)
        out["foreshadow_for_25_30"] = context.foreshadow_for(book, scope, 25, 30)
        out["timeline_for_10"] = context.timeline_for(book, scope, 10)
        out["timeline_for_30"] = context.timeline_for(book, "周叔 E050", 30)
        out["threads"] = [list(x) for x in contract.threads(book)]
        out["secrets"] = [[list(x) for x in part] for part in contract.secrets(book)]
        ov = project.overview(book, stale_foreshadow=5)
        out["overview_alerts"] = [a for a in ov.get("alerts", []) if "伏筆" in a.get("kind", "")]
        out["wb_check_20"] = wb_check.check(book, 20)
        out["ledger_prompts"] = reader_ledger.prompts(book)
        out["timeline_after_10"] = reader_ledger._timeline_after(book, 10)

        data = {"summary": {"發生了什麼": "林晚查帳。"},
                "foreshadow": [{"編號": "F003", "最後出現": "第021章", "狀態": "推進中"},
                               {"編號": "F004", "最後出現": "第001章"},          # 修訂舊章：最後出現不倒退
                               {"編號": "新", "內容": "鋪子後院的暗格", "埋設章": "第021章", "預計回收": "第030章",
                                "最後出現": "第021章", "狀態": "已埋", "重要度": "高"},
                               {"內容": "沒有編號的新伏筆", "重要度": "中"},
                               "不是 dict 的雜訊"],
                "timeline": [{"編號": "E012", "讀者目前知道": "讀者知道帳本被改過", "揭示章": "第021章"},
                             {"故事時間": "退婚當天", "實際發生（作者真相）": "周叔偷看了帳本", "讀者目前知道": "未知", "揭示章": "未揭示"}]}
        out["writeback"] = tracking.apply_writeback(book, 21, "暗格", 3000, jsonkeys.to_keys(json.loads(json.dumps(data, ensure_ascii=False))))   # 和實際流程一樣先經 jsonkeys
        out["fs_after"] = rd(layout.FORESHADOWING)
        out["tl_after"] = rd(layout.TIMELINE)
        out["wb_check_21"] = wb_check.check(book, 21)
        # 新書：沒有伏筆表、時間線時建立
        os.remove(layout.path(book, layout.FORESHADOWING))
        os.remove(layout.path(book, layout.TIMELINE))
        out["writeback_new"] = tracking.apply_writeback(book, 23, "新表", 1000, jsonkeys.to_keys(json.loads(json.dumps(data, ensure_ascii=False))))
        out["fs_new"] = rd(layout.FORESHADOWING)
        out["tl_new"] = rd(layout.TIMELINE)
    finally:
        shutil.rmtree(tmp)
    return json.loads(json.dumps(out, ensure_ascii=False, default=str))


class TrackingTablesTest(unittest.TestCase):
    maxDiff = None

    def test_matches_golden(self):
        got = scenario()
        if UPDATE or not os.path.exists(GOLDEN):
            os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
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

    def test_english_keys_same_as_jsonkeys_converted(self):
        """模型給英文鍵（英文、日文書）或中文鍵（繁中書）時，經 jsonkeys.to_keys 換算後的回寫結果要相同。"""
        en = {"summary": {"what_happened": "林晚查帳。"},
              "foreshadow": [{"id": "F005", "last_seen": "第022章", "status": "已回收"},
                             {"content": "英文鍵的新伏筆", "planted_in": "第022章", "priority": "低"}],
              "timeline": [{"id": "E013", "revealed_in": "第022章"},
                           {"story_time": "退婚次日", "what_really_happened": "周叔燒了信", "reader_knows_now": "未知"}]}
        res = []
        for data in (jsonkeys.to_keys(en, values=False), jsonkeys.to_keys(jsonkeys.to_zh(json.loads(json.dumps(en)), values=False), values=False)):
            tmp = tempfile.mkdtemp()
            try:
                book = os.path.join(tmp, "b")
                shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), book)
                with open(layout.path(book, layout.FORESHADOWING), "w", encoding="utf-8", newline="\n") as f:
                    f.write(fs_table())
                with open(layout.path(book, layout.TIMELINE), "w", encoding="utf-8", newline="\n") as f:
                    f.write(tl_table())
                log = tracking.apply_writeback(book, 22, "回收", 2000, json.loads(json.dumps(data, ensure_ascii=False)))
                res.append((log[1:3], open(layout.path(book, layout.FORESHADOWING), encoding="utf-8").read(),
                            open(layout.path(book, layout.TIMELINE), encoding="utf-8").read()))
            finally:
                shutil.rmtree(tmp)
        self.assertEqual(res[0], res[1])
        self.assertEqual(["伏筆（新增 1、更新 1）", "時間線（新增 1、更新 1）"], res[0][0])

    def test_scenario_reaches_the_filtered_paths(self):
        """確認測試資料真的走到篩選路徑（不是整份帶）。"""
        got = scenario()
        self.assertIn("作者備註", got["fs_after"], "作者加的欄寫回時不能掉")
        self.assertIn("表格後面的說明文字要保留", got["fs_after"])
        self.assertNotEqual(got["timeline_for_10"].count("\n"), tl_table().count("\n"), "時間線應該被篩選過")
        self.assertTrue(got["overview_alerts"], "總覽應該有伏筆提醒")


if __name__ == "__main__":
    unittest.main()
