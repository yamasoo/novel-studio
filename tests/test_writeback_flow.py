# -*- coding: utf-8 -*-
"""一章回寫的完整流程回歸測試（v3 P2：jsonkeys 反轉）。

用假模型回傳固定的 JSON，跑 native._writeback（解析 → 鍵名換算 → 語言檢查 → apply_writeback → 回寫檢查），
涵蓋章節摘要、狀態卡、伏筆、時間線、讀者認知、角色狀態（含沿用舊值）、角色關係、新增物（名詞與角色）、匯報，
以及「角色填了關係變化卻沒給 relations」的提醒。

三種情境：
- 繁中書：中文鍵（繁中提示詞的格式）
- 英文書：英文鍵、英文列舉值（要換回固定詞）、鍵名大小寫不一、認不得的選項值
- 英文書：語言不對時的重試（第二次回傳才是英文）
預期結果（writeback_flow_golden.json）用改之前的程式產生，必須逐字相同。

重產預期結果：UPDATE_SNAPSHOT=1 python -m pytest tests/test_writeback_flow.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import layout, native, project, prompts  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "snapshots", "writeback_flow_golden.json")
UPDATE = os.environ.get("UPDATE_SNAPSHOT") == "1"


class FakeJob:
    def __init__(self, book):
        self.book_dir, self.id, self.logs = book, "test", []

    def emit(self, kind, **kw):
        self.logs.append(kw.get("text", ""))


class FakeCtx(native.Ctx):
    def __init__(self, book, outputs):
        super().__init__(FakeJob(book), {"id": "fake", "type": "openai", "max_output": 4096, "context_tokens": 32768},
                         ROOT, None, None)
        self.outputs = list(outputs)

    def call(self, messages, json_mode=False, max_tokens=None, label="", stage=None, recover=None):
        self.truncated = False
        return self.outputs.pop(0)


ZH = {
    "summary": {"發生了什麼": "林晚帶周叔查帳，發現帳本缺頁。", "局面變化": "沈家的把柄浮上檯面。", "新出現的人事物": "暗格", "結尾停在": "門外有人。"},
    "state_card": {"目前位置": ["卷一／第4章", "故事內時間：退婚後第三天"], "主線進度": "查帳", "在場角色": ["林晚：冷靜", "周叔：緊張"],
                   "下一章承諾": ["揭開暗格"], "長期約束": [], "連續性風險": ["玉珮只剩半塊"], "活躍伏筆": ["F001 玉珮"]},
    "foreshadow": [{"編號": "新", "內容": "暗格裡的信", "埋設章": "第004章", "預計回收": "第010章", "最後出現": "第004章", "狀態": "已埋", "重要度": "高"}],
    "timeline": [{"編號": "新", "故事時間": "退婚後第三天", "實際發生（作者真相）": "周叔早就知道暗格", "讀者目前知道": "暗格存在", "揭示章": "未揭示", "相關角色": "周叔"}],
    "reader": [{"編號": "新", "類型": "懸念", "內容": "暗格裡是什麼？", "作者真相": "", "種下章": "第004章", "回收章": "", "相關角色": "林晚"}],
    "characters": [{"名稱": "林晚", "身分": "林家二小姐", "位置": "鋪子後院", "目標": "", "身體狀態": "疲倦", "情緒狀態": "警覺",
                    "能力與資源": ["帳本", "半塊玉珮"], "關係變化": "開始懷疑周叔", "知道的秘密": "帳本缺頁", "未了結的事": "退婚"},
                   {"名稱": "周叔", "身分": "老掌櫃", "位置": "鋪子", "關係變化": "無"}],
    "relations": [{"誰": "林晚", "對誰": "周叔", "關係": "主僕", "態度": "懷疑", "原因": "周叔知道暗格卻沒說"}],
    "new_entities": [{"類型": "名詞", "名稱": "暗格", "說明": "鋪子後院牆裡的暗格"}, {"類型": "角色", "名稱": "周叔", "說明": "林家鋪子的老掌櫃"},
                     {"類型": "地點", "名稱": "不存在的地方", "說明": "正文沒有"}],
    "report": "本章更新了伏筆與讀者認知。",
}

ZH_NO_REL = {"summary": {"發生了什麼": "隔天。"},
             "characters": [{"名稱": "林晚", "關係變化": "決定信任沈既白"}],
             "report": "只有角色變化。"}

EN = {
    "Summary": {"what_happened": "Mara walks the road.", "situation_change": "The milestone is gone.", "new_elements": "the toll-house",
                "ends_on": "A lantern goes out."},
    "state_card": {"current_position": ["Vol 1 / Ch 2"], "main_progress": ["Searching"], "present_characters": ["Mara: tired"],
                   "next_chapter_promises": ["Find the stone"], "long_term_constraints": ["No magic"], "continuity_risks": [],
                   "active_foreshadowing": ["F001 the stone"]},
    "foreshadow": [{"id": "new", "content": "The missing milestone", "planted_in": "Chapter 2", "planned_payoff": "",
                    "last_seen": "Chapter 2", "status": "planted", "priority": "high"},
                   {"ID": "F001", "Last_Seen": "Chapter 2", "status": "developing", "priority": "very important"}],
    "timeline": [{"id": "new", "story_time": "Day 2", "what_really_happened": "The toll-keeper moved the stone",
                  "reader_knows_now": "It is missing", "revealed_in": "not revealed", "related_characters": "Mara"}],
    "reader": [{"id": "new", "type": "question", "content": "Who moved the stone?", "author_truth": "", "planted_chapter": "Chapter 2",
                "resolved_in": "", "related_characters": "Mara"}],
    "characters": [{"name": "Mara", "identity": "courier", "location": "the road", "goal": "deliver the letter",
                    "physical_state": "tired", "emotional_state": "worried", "abilities_resources": ["lantern"],
                    "relationship_changes": "trusts the toll-keeper less", "known_secrets": "", "unfinished_business": "the letter"}],
    "relations": [{"who": "Mara", "toward": "Toll-keeper", "relationship": "stranger", "attitude": "suspicious", "reason": "he lied"}],
    "new_entities": [{"type": "place", "name": "Toll-house", "explanation": "a house by the road"},
                     {"type": "character", "name": "Toll-keeper", "explanation": "keeps the toll-house"}],
    "report": "Updated the foreshadowing.",
}

EN_BAD = {"summary": {"what_happened": "瑪拉走在路上，發現里程碑不見了，這是中文的句子。", "situation_change": "局面改變了，這也是中文的一段內容。",
                      "new_elements": "收費站與一個不認識的老人家出現", "ends_on": "燈籠熄滅了，夜裡一片漆黑看不見"},
          "report": "這次回寫用中文寫了匯報，語言不對。"}
EN_GOOD = {"summary": {"what_happened": "Mara notices the milestone is gone.", "situation_change": "Things changed.",
                       "new_elements": "none", "ends_on": "Night falls."},
           "report": "Second try in English."}


def _files(book, rels):
    out = {}
    for rel in rels:
        p = layout.path(book, rel)
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                out[rel + "/" + name] = project.read_text(os.path.join(p, name))
        elif os.path.isfile(p):
            out[rel] = project.read_text(p)
    return out


def _run(book, no, outputs):
    c = FakeCtx(book, [json.dumps(o, ensure_ascii=False) for o in outputs])
    prompts.set_lang(c.lang)
    res = native._writeback(c, no)
    return {"result": res, "logs": c.job.logs, "lang_issues": c.lang_issues}


WATCH = (layout.SUMMARIES, layout.STATE_CARD, layout.FORESHADOWING, layout.TIMELINE, layout.READER_KNOWLEDGE,
         layout.CHARACTER_STATES, layout.RELATIONS, layout.GLOSSARY, layout.CHARACTERS, layout.CHAPTER_CARDS)


def _book(tmp, name, chapters):
    """複製一份乾淨的示範書，再補上追蹤進度之後的幾章正文（示範書追蹤到第 2 章，回寫第 3 章以後才不是修訂舊章）。"""
    book = os.path.join(tmp, name)
    if os.path.isdir(book):
        shutil.rmtree(book)
    shutil.copytree(os.path.join(ROOT, "demo", name), book)
    for no, (title, text) in chapters.items():
        with open(layout.path(book, layout.MANUSCRIPT, layout.chapter_md(no)), "w", encoding="utf-8", newline="\n") as f:
            f.write("# %s\n\n%s\n" % (title, text))
    return book


ZH_CH = {3: ("暗格", "林晚跟著周叔走進鋪子後院。牆裡有個暗格，帳本缺了一頁。林晚看著周叔，開始懷疑他。" * 3),
         4: ("隔天", "隔天林晚想了一夜，決定先信沈既白一次。" * 3)}
EN_CH = {3: ("The Toll-house", "Mara reached the Toll-house. The Toll-keeper said the milestone had never been there. " * 3)}


def scenario():
    out = {}
    tmp = tempfile.mkdtemp()
    try:
        book = _book(tmp, "退婚之後", ZH_CH)
        out["zh"] = _run(book, 3, [ZH])
        out["zh_no_rel"] = _run(book, 4, [ZH_NO_REL])
        out["zh_files"] = _files(book, WATCH)

        book = _book(tmp, "en_TheLanternRoad", EN_CH)
        out["en"] = _run(book, 3, [EN])
        out["en_files"] = _files(book, WATCH)

        book = _book(tmp, "en_TheLanternRoad", EN_CH)
        out["en_retry"] = _run(book, 3, [EN_BAD, EN_GOOD])
        out["en_retry_summary"] = _files(book, (layout.SUMMARIES,))
    finally:
        shutil.rmtree(tmp)
        prompts.set_lang("zh-TW")
    text = json.dumps(out, ensure_ascii=False, default=str).replace(tmp, "<tmp>")
    return json.loads(text)


class WritebackFlowTest(unittest.TestCase):
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
            if isinstance(want.get(k), dict) and isinstance(got.get(k), dict):
                for kk in sorted(set(want[k]) | set(got[k])):
                    with self.subTest(part=k, item=kk):
                        self.assertEqual(want[k].get(kk), got[k].get(kk))
            else:
                with self.subTest(part=k):
                    self.assertEqual(want.get(k), got.get(k))

    def test_scenario_reaches_the_paths(self):
        got = scenario()
        r = got["zh"]["result"]
        for part in ("章節摘要", "狀態卡", "伏筆（新增 1", "時間線（新增 1", "讀者認知", "角色狀態（林晚、周叔）", "名詞表（暗格、周叔、不存在的地方）"):
            self.assertIn(part, r)
        self.assertIn("關係", r)
        self.assertIn("登記成新增物、但正文找不到：不存在的地方", r)
        self.assertIn("本章更新了伏筆與讀者認知。", r)
        self.assertTrue(any("關係變化" in x or "relations" in x for x in [got["zh_no_rel"]["result"]]), got["zh_no_rel"]["result"])
        zf = got["zh_files"]
        lin = next(v for k, v in zf.items() if k.endswith("林晚.md") and layout.CHARACTER_STATES in k)
        self.assertIn("- 能力與資源：帳本；半塊玉珮", lin)
        self.assertIn("周叔", "".join(v for k, v in zf.items() if k.startswith(layout.CHARACTERS + "/")))
        er = got["en"]
        self.assertIn("very important", "".join(er["logs"]), "認不得的選項值要提醒")
        ef = got["en_files"]
        self.assertIn("| planted |", ef[layout.FORESHADOWING], "英文書：固定值換成英文的標準寫法（v3 第六批）")
        self.assertIn("| question |", ef.get(layout.READER_KNOWLEDGE, ""))
        self.assertTrue(any("語言不對" in x for x in got["en_retry"]["logs"]))
        self.assertIn("Mara notices", "".join(got["en_retry_summary"].values()))


if __name__ == "__main__":
    unittest.main()
