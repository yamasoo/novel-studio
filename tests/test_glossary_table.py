# -*- coding: utf-8 -*-
"""名詞表的回歸測試（v3 P2：名詞表改英文鍵）。

示範書的名詞表很短，只走得到「整份帶」；名詞整理（glossary_org）要呼叫模型，快照也測不到。
這裡自備一份夠大的名詞表（超過篩選門檻、含稱謂類、說明空白的垃圾條目），用固定回應的假模型跑：
- 上下文：glossary_for（篩選、稱謂類比對出場角色）
- 其他讀名詞表的地方：fidelity._names、contract.build、shared.book_names
- 回寫的新增物登記
- 名詞整理：parse_rows、organize（輸入是 parse_rows 的列，以及反推傳來的中文鍵列）
預期結果（glossary_table_golden.json）是用改英文鍵之前的程式產生的，必須逐字相同。

重產預期結果：UPDATE_SNAPSHOT=1 python -m pytest tests/test_glossary_table.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import context, contract, jsonkeys, fidelity, glossary_org, layout, prompts, shared, tracking  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "snapshots", "glossary_table_golden.json")
UPDATE = os.environ.get("UPDATE_SNAPSHOT") == "1"

CATS = ["地點", "組織", "物品", "能力與技術", "制度與習俗", "稱謂", "事件", "生物"]


def gloss_table(n=120):
    rows = ["| 名詞 | 類別 | 說明 | 注意 |", "|---|---|---|---|"]
    for i in range(1, n + 1):
        cat = CATS[i % len(CATS)]
        desc = ("林晚對長輩的稱呼，第%d種用法" % i) if cat == "稱謂" else ("第%d個%s：位於沈家鋪子附近，和玉珮、帳本缺頁的線索有關，周叔曾提過" % (i, cat))
        if i % 37 == 0:
            desc = "未提及"     # 垃圾條目：整理時刪掉
        name = "名詞%03d／別名%03d" % (i, i) if i % 5 == 0 else "名詞%03d" % i
        rows.append("| %s | %s | %s | 首次出現：第%03d章 |" % (name, cat, desc, i % 9 + 1))
    rows.append("| 天機閣 | 組織 | 江湖情報組織，沈家的往來對象 | 首次出現：第002章 |")
    rows.append("| 青雲劍 | 物品 | 沈既白的佩劍 |  |")
    return "---\ntype: glossary\n---\n\n# 名詞表\n\n" + "\n".join(rows) + "\n"


def stub_step(key, label, text):
    """固定回應：分類給幾個名詞的大類、小類與處理；其他步驟回空的（organize 會走保底路徑）。"""
    if key.startswith("org_cls"):
        return {"名詞": [
            {"名詞": "天機閣", "大類": "組織", "小類": "情報", "處理": "保留"},
            {"名詞": "青雲劍", "大類": "物品", "小類": "兵器", "處理": "獨立"},
            {"名詞": "名詞003", "大類": "能力與技術", "小類": "心法", "處理": "保留"},
            {"名詞": "名詞010", "大類": "地點", "處理": "刪除"},
            {"名詞": "名詞011", "大類": "人物", "處理": "人物"},
        ]}
    if key == "org_fac":
        return {"勢力": [], "不是勢力": [{"名詞": "天機閣", "改成": "其他", "原因": "測試"}]}
    return {}


def run_organize(book, rows):
    written = {}
    summary = glossary_org.organize(book, rows, lambda label, text: {}, lambda rel, t: written.__setitem__(rel, t),
                                    step=stub_step)
    return summary, written


def scenario():
    out = {}
    tmp = tempfile.mkdtemp()
    try:
        book = os.path.join(tmp, "退婚之後")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), book)
        gp = layout.path(book, layout.GLOSSARY)
        with open(gp, "w", encoding="utf-8", newline="\n") as f:
            f.write(gloss_table())
        prompts.set_lang("zh-TW")
        out["glossary_for"] = context.glossary_for(book, "林晚帶著名詞004與別名005去天機閣，遇見名詞016。")
        out["glossary_for_title"] = context.glossary_for(book, "林晚出場。")
        out["fidelity_names"] = fidelity._names(book)
        out["contract"] = contract.build(book).split("產生時間")[0] + contract.build(book).split("\n", 6)[-1]
        out["book_names"] = shared.book_names(book)
        rows = glossary_org.parse_rows(book)
        out["parse_rows_n"] = len(rows)
        out["parse_rows_first"] = [sorted(r.values()) for r in rows[:3]]
        out["organize"] = run_organize(book, rows)
        # 反推傳進來的是中文鍵的列，結果要一樣
        zh_rows = [{"名詞": r.get("名詞", r.get("term")), "類別": r.get("類別", r.get("kind")),
                    "說明": r.get("說明", r.get("explanation")), "注意": r.get("注意", r.get("note"))} for r in rows]
        out["organize_zh_rows_same"] = run_organize(book, zh_rows) == out["organize"]
        # 回寫的新增物登記
        data = {"summary": {"發生了什麼": "x"},
                "new_entities": [{"類型": "名詞", "名稱": "暗格", "說明": "鋪子後院的暗格"},
                                 {"類型": "名詞", "名稱": "天機閣", "說明": "已登記的不重複加"},
                                 {"類型": "地點", "名稱": "後山", "說明": ""}]}
        out["writeback"] = tracking.apply_writeback(book, 3, "暗格", 1000, jsonkeys.to_keys(data))   # 和實際流程一樣先經 jsonkeys
        out["glossary_after_wb"] = open(gp, encoding="utf-8").read()[-400:]
    finally:
        shutil.rmtree(tmp)
    return json.loads(json.dumps(out, ensure_ascii=False, default=str))


class GlossaryTableTest(unittest.TestCase):
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

    def test_scenario_reaches_the_paths(self):
        got = scenario()
        self.assertLess(got["glossary_for"].count("\n"), 120, "名詞表應該被篩選過")
        self.assertIn("稱謂", got["glossary_for_title"], "稱謂類要靠出場角色帶進來")
        self.assertTrue(got["organize_zh_rows_same"], "反推的中文鍵列與 parse_rows 的列，整理結果要一樣")
        summary, written = got["organize"]
        self.assertIn(layout.GLOSSARY, written)
        self.assertIn("刪掉", summary)


if __name__ == "__main__":
    unittest.main()
