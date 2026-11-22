# -*- coding: utf-8 -*-
"""名詞整理的完整流程回歸測試（v3 P2：jsonkeys 反轉第三批）。

用假模型跑 native.act_glossary_org：分類 → 勢力判定 → 主題檔 → 獨立條目 → 名詞表索引。
假模型依提示詞裡的 schema 判斷是哪一步，回傳固定 JSON：
- 繁中書：中文鍵、中文選項值
- 英文書：英文鍵、英文選項值（含認不得的值、大小寫不一的鍵）
涵蓋：刪除、改成人物、勢力檔（別名、沿革、內部編組、需要作者確認）、「不是勢力」改分類、
主題檔分區、AI 漏掉的條目補到「其他」、出場 5 章以上獨立成檔、名詞表的「詳見」。
另外直接呼叫 glossary_org.organize，模擬反推的入口：步驟結果是中文鍵（反推的 _zh 與 .studio 快取）。
預期結果（glossary_org_flow_golden.json）用改之前的程式產生，必須逐字相同。

重產預期結果：UPDATE_SNAPSHOT=1 python -m pytest tests/test_glossary_org_flow.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import glossary_org, layout, native, project, prompts, reverse  # noqa: E402
from tests.test_writeback_flow import FakeCtx  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "snapshots", "glossary_org_flow_golden.json")
UPDATE = os.environ.get("UPDATE_SNAPSHOT") == "1"

ZH_GLOSS = [("天機閣", "組織", "江湖情報組織"), ("青雲劍", "物品", "沈既白的佩劍"), ("回春堂", "地點", "城南藥鋪"),
            ("紫氣訣", "能力", "沈家心法"), ("廢詞", "物品", "沒用的詞"), ("老王", "人物", "鋪子夥計"),
            ("假組織", "組織", "其實是一件器物"), ("鹽引", "物品", "鹽商的運銷憑證")]
ZH_TEXT = "林晚看見沈既白腰間的青雲劍。回春堂的掌櫃提到天機閣。"
ZH = {
    "cls": {"名詞": [
        {"名詞": "天機閣", "大類": "組織", "小類": "情報", "處理": "保留", "主題": "江湖"},
        {"名詞": "青雲劍", "大類": "物品", "小類": "兵器", "處理": "保留", "主題": "兵器"},
        {"名詞": "回春堂", "大類": "地點", "小類": "藥鋪", "處理": "保留", "主題": "地理"},
        {"名詞": "紫氣訣", "大類": "能力與技術", "小類": "心法", "處理": "保留", "主題": "武學"},
        {"名詞": "廢詞", "大類": "物品", "處理": "刪除"},
        {"名詞": "老王", "大類": "人物", "處理": "人物"},
        {"名詞": "假組織", "大類": "組織", "處理": "保留"},
        {"名詞": "鹽引", "大類": "物品", "處理": "保留", "主題": "兵器"}]},
    "fac": {"勢力": [{"名稱": "天機閣", "別名": ["天機"], "一句話": "江湖情報組織", "沿革": "百年老店", "內部編組": ["暗堂"],
                      "需要作者確認": "是否與沈家同盟", "相關角色": ["林晚"], "首領": "閣主", "規模與地盤": "遍及青州",
                      "對主角的態度": "中立"}],
            "不是勢力": [{"名詞": "假組織", "改成": "物品", "原因": "其實是器物"}]},
    "topic": {"一句話": "書裡的器物與兵器", "分區": [{"標題": "兵器", "條目": [{"名詞": "青雲劍", "說明": "沈既白的佩劍，劍身青色"}]}],
              "規則與限制": ["官府禁止私鑄"], "與劇情的關係": "信物推動退婚線"},
    "own": {"條目": [{"名稱": "青雲劍", "一句話": "沈家祖傳名劍", "特性": ["鋒利", "劍身青色"], "來歷": "祖傳",
                       "在故事中的作用": "退婚的信物", "目前狀態": "在沈既白身上", "限制與代價": "認主"}]},
}

EN_GLOSS = [("Surveyors' Guild", "faction", "official map authority"), ("Hob", "object", "the brass lantern"),
            ("Lantern Road", "place", "the erased trade road"), ("Wayfinding", "ability", "reading old roads"),
            ("Junk word", "object", "not stated in the text"), ("Dessa Pike", "person", "Guild clerk"),
            ("Old Mill", "place", "a mill by the ford")]
EN_TEXT = "Wren walked the Lantern Road with Hob. The Surveyors' Guild watched. "
EN = {
    "cls": {"terms": [
        {"term": "Surveyors' Guild", "main_class": "organization", "subtype": "guild", "handling": "keep", "topic": "Institutions"},
        {"Term": "Hob", "Main_Class": "item", "subtype": "lantern", "handling": "keep", "topic": "Objects"},
        {"term": "Lantern Road", "main_class": "place", "subtype": "road", "handling": "keep", "topic": "Geography"},
        {"term": "Wayfinding", "main_class": "ability", "subtype": "craft", "handling": "keep", "topic": "Craft"},
        {"term": "Dessa Pike", "main_class": "person", "handling": "person"},
        {"term": "Old Mill", "main_class": "landmark", "handling": "keep", "topic": "Geography"}]},
    "fac": {"factions": [{"name": "Surveyors' Guild", "aliases": ["the Guild"], "one_line": "official map authority",
                          "history": "chartered long ago", "sub_units": ["Clerks' Office"], "author_check": "same as the Office?",
                          "related_characters": ["Corvin Tarr"], "leader": "Corvin Tarr", "attitude_to_protagonist": "hostile"}],
            "not_factions": []},
    "topic": {"one_line": "Places along the road", "sections": [{"heading": "Roads", "entries": [
        {"term": "Lantern Road", "explanation": "an erased trade road"}]}], "rules_limits": ["Maps must be sealed"],
              "plot_relevance": "Wren follows it"},
    "own": {"entries": [{"name": "Lantern Road", "one_line": "the erased road", "traits": ["overgrown"], "origin": "old trade",
                         "story_role": "the quest", "current_state": "hidden", "limits_costs": ["only Hob can see it"]}]},
}

# schema 裡才有的鍵，用來判斷是哪一步（先比對較特別的）
STEP_MARKS = (("fac", ("不是勢力", "not_factions")), ("own", ("特性", "traits")), ("topic", ("分區", "sections")),
              ("cls", ("大類", "main_class")))


def which(text):
    for k, marks in STEP_MARKS:
        if any('"%s"' % m in text for m in marks):
            return k
    raise AssertionError("認不出是哪一步：" + text[:200])


class RouteCtx(FakeCtx):
    def __init__(self, book, answers):
        super().__init__(book, [])
        self.answers, self.seen = answers, []

    def call(self, messages, json_mode=False, max_tokens=None, label="", stage=None, recover=None):
        self.truncated = False
        k = which(messages[-1]["content"])
        self.seen.append(k)
        return json.dumps(self.answers[k], ensure_ascii=False)


def _book(tmp, name, gloss, text):
    book = os.path.join(tmp, name)
    if os.path.isdir(book):
        shutil.rmtree(book)
    shutil.copytree(os.path.join(ROOT, "demo", name), book)
    rows = ["| 名詞 | 類別 | 說明 | 注意 |", "|---|---|---|---|"] + ["| %s | %s | %s | 首次出現：第001章 |" % g for g in gloss]
    with open(layout.path(book, layout.GLOSSARY), "w", encoding="utf-8", newline="\n") as f:
        f.write("---\ntype: glossary\n---\n\n# 名詞表\n\n" + "\n".join(rows) + "\n")
    for no in range(3, 9):   # 補幾章，讓常出現的條目超過獨立成檔的門檻
        with open(layout.path(book, layout.MANUSCRIPT, layout.chapter_md(no)), "w", encoding="utf-8", newline="\n") as f:
            f.write("# x%d\n\n%s\n" % (no, text * 3))      # 章名在標題（以前在檔名 x3、x4…）
    return book


def _drafts(book):
    root = os.path.join(book, reverse.DIR, layout.REVERSE_DRAFTS)
    out = {}
    for dp, _, fs in os.walk(root):
        for fn in sorted(fs):
            p = os.path.join(dp, fn)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = project.read_text(p)
    return out


def _act(book, answers):
    c = RouteCtx(book, answers)
    c.job.result = None
    c.job.book_id = "b"
    prompts.set_lang(c.lang)
    native.act_glossary_org(c, {})
    return {"result": c.job.result, "logs": c.job.logs, "steps": c.seen, "drafts": _drafts(book)}


def _reverse_entry(book, answers):
    """反推的入口：organize 收到的步驟結果是中文鍵（反推的 _zh、.studio 快取）。"""
    from studio import jsonkeys
    prompts.set_lang(native.lang_mod.book_lang(book))
    written, seen = {}, []

    def step(key, label, text):
        k = which(text)
        seen.append(k)
        return jsonkeys.to_zh(json.loads(json.dumps(answers[k], ensure_ascii=False)))
    rows = [{"名詞": r["term"], "類別": r["kind"], "說明": r["explanation"], "注意": r["note"]}
            for r in [dict(zip(("term", "kind", "explanation", "note"), (x.get("term", x.get("名詞")), x.get("kind", x.get("類別")),
                                                                         x.get("explanation", x.get("說明")), x.get("note", x.get("注意")))))
                      for x in glossary_org.parse_rows(book)]]
    summary = glossary_org.organize(book, rows, None, lambda rel, t: written.__setitem__(rel, t), step=step)
    return {"result": summary, "steps": seen, "drafts": dict(sorted(written.items()))}


def scenario():
    out = {}
    tmp = tempfile.mkdtemp()
    try:
        out["zh"] = _act(_book(tmp, "退婚之後", ZH_GLOSS, ZH_TEXT), ZH)
        out["en"] = _act(_book(tmp, "en_TheLanternRoad", EN_GLOSS, EN_TEXT), EN)
        out["zh_reverse"] = _reverse_entry(_book(tmp, "退婚之後", ZH_GLOSS, ZH_TEXT), ZH)
        out["en_reverse"] = _reverse_entry(_book(tmp, "en_TheLanternRoad", EN_GLOSS, EN_TEXT), EN)
    finally:
        shutil.rmtree(tmp)
        prompts.set_lang("zh-TW")
    return json.loads(json.dumps(out, ensure_ascii=False, default=str).replace(tmp, "<tmp>"))


class GlossaryOrgFlowTest(unittest.TestCase):
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
            for kk in sorted(set(want.get(k) or {}) | set(got.get(k) or {})):
                a, b = (want.get(k) or {}).get(kk), (got.get(k) or {}).get(kk)
                if isinstance(a, dict) and isinstance(b, dict):
                    for f in sorted(set(a) | set(b)):
                        with self.subTest(part=k, item=kk, file=f):
                            self.assertEqual(a.get(f), b.get(f))
                else:
                    with self.subTest(part=k, item=kk):
                        self.assertEqual(a, b)

    def test_scenario_reaches_the_paths(self):
        got = scenario()
        for k in ("zh", "en", "zh_reverse", "en_reverse"):
            self.assertEqual(["cls", "fac"], got[k]["steps"][:2], k)
            self.assertIn("topic", got[k]["steps"], k)
            self.assertIn("own", got[k]["steps"], k)
        zd = got["zh"]["drafts"]
        fac = next(v for p, v in zd.items() if "天機閣" in p)
        for part in ("## 別名\n天機", "## 沿革\n百年老店", "## 內部編組\n- 暗堂", "## 需要作者確認\n- 是否與沈家同盟", "遍及青州"):
            self.assertIn(part, fac)
        own = next(v for p, v in zd.items() if p.endswith("青雲劍.md"))
        self.assertIn("沈家祖傳名劍", own)
        self.assertIn("認主", own)
        gl = next(v for p, v in zd.items() if p == layout.GLOSSARY)
        self.assertNotIn("廢詞", gl)
        self.assertIn("| 老王 | 人物 |", gl)
        self.assertIn("詳見", gl)
        self.assertIn("官府禁止私鑄", "".join(zd.values()))
        ed = got["en"]["drafts"]
        self.assertIn("## History\nchartered long ago", next(v for p, v in ed.items() if "Surveyors" in p))
        self.assertIn("the erased road", "".join(ed.values()))
        self.assertTrue(any("landmark" in x for x in got["en"]["logs"]), "認不得的選項值要提醒")
        self.assertEqual(got["zh"]["drafts"], {k: v for k, v in got["zh"]["drafts"].items()})


if __name__ == "__main__":
    unittest.main()
