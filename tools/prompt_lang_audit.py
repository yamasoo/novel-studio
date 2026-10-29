#!/usr/bin/env python3
"""提示詞語言稽核（不呼叫真的模型、不花錢，push 前可以跑）：python tools/prompt_lang_audit.py

做法
  用假的 provider 取代 providers.chat：記下工作台送出的每則訊息，回傳事先準備好的假 JSON／假正文。
  對一本 3 章的小測試書依序跑：從正文建立設定 → 採用草稿 → 整理名詞表 → 回寫追蹤（一般＋修訂舊章）
  → 單章審查 → 依意見修訂 → 讀者認知轉換與比對 → 章綱核對 → 寫下一章 → 視覺卡 → 插圖提示詞 → 共用文風設計。
  英文、日文書：列出訊息裡的中文句子（JSON 鍵、中文列舉值、資料夾路徑、第NNN章、檔案裡的標題與欄位名不算），有就回傳 1。
  三種書都會另外確認「提示詞載入的是它自己那一版的 skill 內文」（plugin／plugin-en／plugin-ja）：
  該版的句子不在、或混進別版的句子，一樣回傳 1。plugin/ 只是基底資料夾，真正切換發生在
  context.lang_plugin／context.skill_ref（依 prompts.cur_lang()），這條檢查就是防止那個切換壞掉。
  繁中書：不檢查語言，只用來比對「改前改後送出的訊息是否逐字相同」。

用法
  python tools/prompt_lang_audit.py                      英文、日文都跑（內建測試書）
  python tools/prompt_lang_audit.py --lang zh-TW --dump out/before   把訊息存成 out/before/zh-TW.json
  python tools/prompt_lang_audit.py --lang zh-TW --compare out/before  和上次存的逐字比對（不同就回傳 1）
  python tools/prompt_lang_audit.py --lang en --src <書目錄>         改用某本書的前 3 章當測試書（只讀，不會動到原書）
  -v 列出每一則有問題的訊息片段

內建測試書在 tools/audit_fixtures/：英文是《Treasure Island》前 3 章節錄（公有領域），日文、繁中是原創短文。
"""
import argparse
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from studio import enums, glossary_org, importer, jsonkeys, lang as lang_mod, native, native_files, project, prompts, providers, reverse, revision, runner, shared, textguard  # noqa: E402

PLUGIN_DIR = os.path.join(ROOT, "plugin")
FIXTURES = os.path.join(HERE, "audit_fixtures")

# ---------------------------------------------------------------------------
# 假資料：各語言的自由文字（鍵與列舉值照目前的格式，維持中文）
# ---------------------------------------------------------------------------
V = {
    "en": {
        "names": ["Jim Hawkins", "the captain", "Black Dog"], "alias": ["Billy Bones"],
        "place": "Admiral Benbow", "item": "sea-chest", "org": "Flint's crew", "item2": "black spot",
        "who": "the innkeeper's son and narrator", "did": "watches the captain and keeps the inn",
        "happened": "A scarred old seaman takes a room at the inn and pays Jim to watch for a one-legged man.",
        "change": "The inn now lives under the captain's shadow.", "new": "the captain", "end": "Black Dog arrives at the inn.",
        "goal": "keep the inn running", "block": "the captain's temper", "func": "set up the mystery", "feel": "unease",
        "point": "The captain arrives with his sea-chest.", "hook": "A stranger asks for Bill.",
        "event": "Black Dog finds the captain at the inn.", "knows": "The reader knows the captain fears someone.",
        "fs": "The captain fears a seafaring man with one leg.", "rp": "Who is the one-legged man?",
        "truth": "He is Long John Silver.", "one": "A frightened old pirate hiding at a seaside inn.",
        "rel": "Jim: wary loyalty", "arc": "from bully to hunted man", "state": "hiding at the inn",
        "world": "England in the eighteenth century, a coastal inn near Bristol.", "rule": "Pirates still hunt their old shipmates.",
        "cls": "inn", "topic": "geography", "sec": "Places", "desc": "A small inn on the coast.",
        "fac": "The pirates who sailed with Captain Flint.", "arc_sum": "The captain hides at the inn until his past finds him.",
        "unit": "The captain's last days", "summary": "The chapter is mostly consistent.",
        "issue": "The captain's age is unclear.", "fix": "Give one concrete detail about his age.",
        "quote": "the brown old seaman", "report": "Updated the summary and the state card.",
        "card_tags": "old sailor, scar, tarred pigtail", "card_desc": "A tall, heavy, nut-brown old sailor.",
        "scene": "night, inn parlour, candlelight", "action": "drinking rum at the table",
        "body": "The fog came in off the cove before dawn. Jim set the shutters and listened for the tap of a stick.",
        "style": "Plain, concrete first-person narration.", "bg": "Background",
    },
    "ja": {
        "names": ["宗一郎", "澪", "健太"], "alias": ["灯台守"],
        "place": "岬の灯台", "item": "懐中時計", "org": "港の漁協", "item2": "手紙",
        "who": "岬の灯台を四十年守る老人", "did": "差出人のない手紙を受け取り、開けずにしまう",
        "happened": "灯台守の宗一郎のもとに差出人のない手紙が届き、少女の澪が訪ねてくる。",
        "change": "二十年前の夜の記憶が動きだす。", "new": "澪", "end": "澪が祖母の手紙のことを尋ねる。",
        "goal": "灯を守る", "block": "嵐と過去", "func": "謎の提示", "feel": "静かな不安",
        "point": "健太が差出人のない手紙を届ける。", "hook": "少女が祖母の手紙のことを尋ねる。",
        "event": "二十年前、灯台の灯が一晩だけ消えた。", "knows": "読者は灯が消えた夜に何かあったと知っている。",
        "fs": "棚の上の止まった懐中時計。", "rp": "手紙には何が書かれているのか。",
        "truth": "あの夜、行けなかったことへの謝罪。", "one": "過去に縛られた灯台守。",
        "rel": "澪：祖母の知り合いとして警戒しつつ信頼", "arc": "閉ざした心がひらく", "state": "灯台で嵐に備えている",
        "world": "現代日本の小さな港町と岬の灯台。", "rule": "灯台の灯は一晩も絶やしてはならない。",
        "cls": "建物", "topic": "地理", "sec": "場所", "desc": "岬に立つ古い灯台。",
        "fac": "港の漁師たちの組合。", "arc_sum": "嵐の夜、宗一郎は二十年前と向き合う。",
        "unit": "嵐の夜", "summary": "おおむね整合している。",
        "issue": "嵐の時刻が前章とずれている。", "fix": "時刻を前章に合わせる。",
        "quote": "雨は夜九時に横なぐりになった", "report": "要約と状態カードを更新した。",
        "card_tags": "old man, white beard, glasses", "card_desc": "痩せた白髭の老人、老眼鏡。",
        "scene": "night, lighthouse, storm", "action": "lighting the lamp",
        "body": "朝の海は凪いでいた。宗一郎は階段を一段ずつ数えながら、手紙のことを考えた。",
        "style": "静かで具体的な三人称。",
    },
    "zh-TW": {
        "names": ["阿福伯", "小澪", "阿健"], "alias": ["燈塔守"],
        "place": "岬角燈塔", "item": "懷錶", "org": "港口漁會", "item2": "信",
        "who": "守岬角燈塔四十年的老人", "did": "收到沒有寄件人的信，沒拆就收起來",
        "happened": "燈塔守阿福伯收到一封沒有寄件人的信，女孩小澪找上門。",
        "change": "二十年前那一夜的記憶被翻出來。", "new": "小澪", "end": "小澪問起阿嬤的信。",
        "goal": "守住燈", "block": "颱風與過去", "func": "提出謎團", "feel": "安靜的不安",
        "point": "阿健送來沒有寄件人的信。", "hook": "女孩問起阿嬤的信。",
        "event": "二十年前燈塔的燈熄了一整夜。", "knows": "讀者知道燈熄的那晚出過事。",
        "fs": "架上停了二十年的懷錶。", "rp": "信裡寫了什麼？",
        "truth": "那晚沒能赴約的道歉。", "one": "被過去綁住的燈塔守。",
        "rel": "小澪：把她當故人的孫女，戒備中帶著信任", "arc": "封閉的心慢慢打開", "state": "在燈塔準備迎接颱風",
        "world": "現代臺灣的小港鎮與岬角燈塔。", "rule": "燈塔的燈一晚都不能熄。",
        "cls": "建築", "topic": "地理", "sec": "地點", "desc": "立在岬角的老燈塔。",
        "fac": "港口漁民的組織。", "arc_sum": "颱風夜，阿福伯面對二十年前的事。",
        "unit": "颱風夜", "summary": "整體大致一致。",
        "issue": "颱風來的時間和上一章對不上。", "fix": "把時間改成和上一章一致。",
        "quote": "晚上九點，雨開始橫著打", "report": "更新了摘要與狀態卡。",
        "card_tags": "old man, white beard, glasses", "card_desc": "瘦高的白鬍子老人，戴老花眼鏡。",
        "scene": "night, lighthouse, storm", "action": "lighting the lamp",
        "body": "早上的海很平。阿福伯一階一階數著樓梯，心裡想著那封信。",
        "style": "安靜、具體的第三人稱。",
    },
}


def _extract(v, nos):
    a, b, c = v["names"]
    return {"chapters": [{
        "章": no,
        "摘要": {"發生了什麼": v["happened"], "局面變化": v["change"], "新出現的人事物": v["new"], "結尾停在": v["end"]},
        "章綱": {"主角想做什麼": v["goal"], "阻礙": v["block"], "局面變成": v["change"], "讀者為什麼往下看": v["hook"],
               "功能": v["func"], "情緒": v["feel"], "情節點": [v["point"]], "章末鉤子": v["hook"]},
        "人物": [{"名稱": a, "別名": [], "身分": v["who"], "本章": v["did"], "重要": "主要"},
               {"名稱": b, "別名": v["alias"] if no == 1 else [], "身分": v["who"], "本章": v["did"], "重要": "主要"},
               {"名稱": c, "別名": [], "身分": v["who"], "本章": v["did"], "重要": "次要"}],
        "名詞": [{"名詞": v["place"], "類別": "地點", "小類": v["cls"], "說明": v["desc"]},
               {"名詞": v["item"], "類別": "物品", "小類": "", "說明": v["fs"]},
               {"名詞": v["org"], "類別": "組織", "小類": "", "說明": v["fac"]}],
        "事件": [{"故事時間": "", "實際發生": v["event"], "讀者知道": v["knows"], "相關角色": a}] if no == 1 else [],
        "伏筆": [{"編號": "新", "動作": "埋", "內容": v["fs"], "重要度": "高"}] if no == 1 else [],
        "讀者": [{"編號": "新", "類型": "懸念", "內容": v["rp"], "作者真相": "", "動作": "新"}] if no == 1 else [],
    } for no in nos]}


def _chars(v):
    st = {k: v["state"] for k in ("身分", "位置", "目標", "身體狀態", "情緒狀態", "能力與資源", "關係變化", "知道的秘密", "未了結的事")}
    return {"角色": [{"名稱": n, "別名": [], "定位": "主角" if i == 0 else "配角", "一句話": v["one"], "年齡身分": v["who"],
                    "外貌": v["card_desc"], "想要": v["goal"], "害怕": v["fs"], "缺陷": v["block"], "底線": v["goal"],
                    "秘密": v["truth"], "說話方式": v["style"], "關係": [v["rel"]], "角色弧線": v["arc"], "目前狀態": st}
                   for i, n in enumerate(v["names"])]}


def _world(v):
    return {"世界觀": [{"名稱": v.get("bg", "背景設定"), "分類": "歷史與年表", "標籤": [v["cls"]], "一句話": v["world"], "規則": [v["rule"]],
                     "代價與限制": [v["rule"]], "與劇情的關係": v["world"]}]}


def _book(v):
    return {"故事核心": {"書名": "", "一句話鉤子": v["one"], "題材": v["world"], "目標讀者": v["feel"], "敘事視角": v["style"],
                     "賣點": [v["hook"]], "主角想要": v["goal"], "主角需要": v["arc"], "主角缺陷": v["block"], "金手指": "",
                     "故事引擎": v["hook"], "主要對手": v["names"][2], "衝突根源": v["truth"], "讀者契約": [v["hook"]],
                     "終局方向": v["truth"], "升級台階": [v["arc"]]},
            "全書": {"主線一句話": v["arc_sum"], "終局": v["truth"]},
            "卷": [{"卷名": v["unit"], "起": 1, "訖": 3, "本卷目標": v["goal"], "主要對手": v["names"][2], "卷末變化": v["change"],
                   "卷末大高潮": v["event"], "卷末新鉤子": v["hook"], "人物弧線": [v["arc"]]}]}


def _state(v):
    return {k: [v["state"]] for k in ("目前位置", "主線進度", "在場角色", "下一章承諾", "長期約束", "連續性風險", "活躍伏筆")}


def _writeback(v):
    a, b, c = v["names"]
    return {"summary": {"發生了什麼": v["happened"], "局面變化": v["change"], "新出現的人事物": "無", "結尾停在": v["end"]},
            "state_card": _state(v),
            "foreshadow": [{"編號": "新", "內容": v["fs"], "埋設章": "第003章", "預計回收": "", "最後出現": "第003章", "狀態": "已埋", "重要度": "中"}],
            "timeline": [{"編號": "新", "故事時間": "", "實際發生（作者真相）": v["event"], "讀者目前知道": v["knows"], "揭示章": "第003章", "相關角色": a}],
            "reader": [{"編號": "新", "類型": "懸念", "內容": v["rp"], "作者真相": "", "種下章": "第003章", "回收章": "", "相關角色": a}],
            "characters": [{"名稱": a, "身分": v["who"], "位置": v["place"], "目標": v["goal"], "身體狀態": v["state"], "情緒狀態": v["feel"],
                            "能力與資源": v["item"], "關係變化": v["rel"], "知道的秘密": v["truth"], "未了結的事": v["rp"]}],
            "relations": [{"誰": a, "對誰": b, "關係": v["rel"], "態度": v["feel"], "原因": v["did"]}],
            "new_entities": [{"類型": "物品", "名稱": v["item2"], "說明": v["desc"]}],
            "report": v["report"]}


def _localize(data, lang):
    """英文、日文書的假回覆照新格式：英文鍵、英文／日文列舉值（測試解析端能換回中文）。"""
    if lang == "zh-TW":
        return data
    if isinstance(data, list):
        return [_localize(x, lang) for x in data]
    if not isinstance(data, dict):
        return data
    out = {}
    for k, v in data.items():
        if isinstance(v, str) and k in jsonkeys.VALUE_KINDS:
            kind = jsonkeys.VALUE_KINDS[k]
            v = ("new" if lang == "en" else "新規") if (kind == "id" and v == "新") else enums.show(kind, v, lang)
        elif isinstance(v, str) and k in ("severity", "category"):
            v = enums.show("severity" if k == "severity" else "review_cat", v, lang)
        else:
            v = _localize(v, lang)
        out[k] = v
    return jsonkeys.to_en(out)


def _response(lang, label, msgs, vlang=None):
    """依任務標籤（工作台內部用的中文）挑假回覆。回傳字串。vlang：假資料的文字用哪個語言（測試語言重試時故意給中文）。"""
    v = V[vlang or lang]
    P = prompts.pack(lang)
    pat = lambda key: re.compile("^" + re.sub(r"\\\{\w+\\\}", ".*?", re.escape(P[key])) + "$")
    m = re.search(r"第(\d+)～(\d+)章", label)
    js = lambda d: json.dumps(_localize(d, lang), ensure_ascii=False)
    if label.startswith("逐章抽取"):
        return js(_extract(v, list(range(int(m.group(1)), int(m.group(2)) + 1))))
    if label.startswith("整理角色"):
        return js(_chars(v))
    if label == "整理背景設定":
        return js(_world(v))
    if "劇情段落" in label:
        return js({"段落摘要": v["arc_sum"], "單元": [{"名稱": v["unit"], "起訖": "1-3", "起點局面": v["change"], "衝突": v["block"],
                                                  "小高潮": v["event"], "結果與代價": v["truth"]}]})
    if label.startswith("整理故事核心"):
        return js(_book(v))
    if label == "整理狀態卡":
        return js(_state(v))
    if pat("gl_lbl_cls").match(label):
        return js({"名詞": [{"名詞": v["place"], "大類": "地點", "小類": v["cls"], "主題": v["topic"], "處理": "保留"},
                          {"名詞": v["item"], "大類": "物品", "小類": "", "主題": "", "處理": "保留"},
                          {"名詞": v["org"], "大類": "組織", "小類": "", "主題": "", "處理": "保留"}]})
    if pat("gl_lbl_fac").match(label):
        return js({"勢力": [{"名稱": v["org"], "別名": [], "沿革": "", "內部編組": [], "一句話": v["fac"], "規模與地盤": v["place"],
                           "首領": v["names"][2], "主要成員": v["names"][2], "資源與手段": v["item"], "想要什麼": v["goal"],
                           "和誰有衝突": v["names"][0], "和誰有合作": "", "內部規矩": v["rule"], "對主角的態度": v["feel"],
                           "相關角色": [v["names"][2]], "需要作者確認": ""}], "不是勢力": []})
    if pat("gl_lbl_topic").match(label):
        return js({"一句話": v["world"], "分區": [{"標題": v["sec"], "條目": [{"名詞": v["place"], "說明": v["desc"]}]}],
                   "規則與限制": [v["rule"]], "與劇情的關係": v["world"]})
    if pat("gl_lbl_own").match(label):
        return js({"條目": [{"名稱": v["place"], "一句話": v["desc"], "特性": [v["desc"]], "來歷": v["world"], "在故事中的作用": v["hook"],
                           "目前狀態": v["state"], "限制與代價": [v["rule"]]}]})
    if "追蹤資料" in label or label in ("重新輸出 JSON", "重新產生 JSON"):
        return js(_writeback(v))
    if label.startswith("審查第"):
        return js({"summary": v["summary"], "items": [
            {"severity": "必須修", "category": "設定", "quote": v["quote"], "issue": v["issue"], "suggestion": v["fix"]},
            {"severity": "提醒", "category": "文字", "quote": "", "issue": v["issue"], "suggestion": v["fix"]}]})
    if label.startswith("修訂第") or (label.startswith("寫第") and not label.endswith("對帳")):
        no = re.search(r"\d+", label).group(0)
        return "# 第%s章 %s\n\n%s\n\n%s%s\n%s" % (no, v["unit"], v["body"], v["body"], native.DELIM, v["report"])
    if label.endswith("前對帳"):
        return js({"final_state": [v["state"]], "events": [{"event": v["point"], "conflict": False, "realization": v["did"]}]})
    if label.startswith("核對第"):
        return js({"goals": [{"id": "G1", "status": "completed", "evidence": [v["quote"]], "note": ""}]})
    if label.startswith("轉換讀者認知"):
        return js({"items": [{"類型": "懸念", "內容": v["rp"], "作者真相": v["truth"], "種下章": "第001章", "回收章": "",
                            "相關角色": v["names"][0], "來源": "E001"}]})
    if label.startswith("比對讀者認知"):
        return js({"changes": [{"編號": "R001", "動作": "部分", "回收章": "", "內容": v["rp"], "合併到": "", "理由": v["knows"]}]})
    if label == "視覺卡":
        return js({"tags": v["card_tags"], "description": v["card_desc"]})
    if label == "插圖提示詞":
        return js({"chars": [{"name": v["names"][0], "position": "left", "action": v["action"]}], "action_tags": v["action"],
                   "scene_tags": v["scene"], "composition": "medium shot", "sentences": v["card_desc"]})
    if label in ("設計文風", "調整文風"):
        return "<<<文風>>>\n---\n類型: 文風\n狀態: 草稿\n名稱: test\n---\n\n# 文風：test\n\n%s\n\n## 範例段落\n%s\n<<<結束>>>\n%s" % (
            v["style"], v["body"], v["report"])
    if label == "試寫文風":
        return v["body"]
    return "{}"


# ---------------------------------------------------------------------------
# 跑一本測試書
# ---------------------------------------------------------------------------
class Recorder:
    def __init__(self, lang, wrong=None):
        self.lang = lang
        self.wrong = dict(wrong or {})   # 標籤開頭 → 前幾次故意回中文
        self.calls = []        # [{"action", "label", "messages"}]
        self.action = ""
        self.label = ""

    def chat(self, home, prov, messages, on_delta=None, on_thinking=None, json_mode=False, max_tokens=None,
             should_stop=None, timeout=600, stage=None):
        self.calls.append({"action": self.action, "label": self.label, "messages": [dict(m) for m in messages]})
        vlang = None
        for pre, n in self.wrong.items():
            if self.label.startswith(pre) and n > 0:
                self.wrong[pre] = n - 1
                vlang = "zh-TW"
        out = _response(self.lang, self.label, messages, vlang)
        return out, {"prompt_tokens": 0, "completion_tokens": 0, "finish_reason": "stop"}


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_text", os.path.join(PLUGIN_DIR, "skills", "novel-deslop", "scripts", "check_text.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_book(library, lang, src=None):
    d = project.create_book(library, "audit-" + lang)
    importer.set_import_lang(d, lang)
    native_files.ensure_skeleton(d, PLUGIN_DIR)
    importer.make_claude_md(d, PLUGIN_DIR, "audit-" + lang)
    src_dir = os.path.join(src, "正文") if src else os.path.join(FIXTURES, lang)
    files = sorted(project._scan_dir(src_dir).items())[:3]
    if len(files) < 3:
        raise SystemExit("測試書至少要 3 章：%s" % src_dir)
    for i, (no, f) in enumerate(files, 1):
        text = project.read_text(os.path.join(src_dir, f))
        name = "第%03d章_%s" % (i, f.split("_", 1)[1] if "_" in f else f)
        with open(os.path.join(d, "正文", name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return d


def run_book(lang, src=None, verbose=False, wrong=None, jobs=None, only=None):
    """wrong：故意回錯語言的步驟（見 Recorder）；jobs：list，收集每個任務的 (動作, 任務紀錄, 結果)；only：只跑到從正文建立設定為止。"""
    rec = Recorder(lang, wrong)
    tmp = tempfile.mkdtemp(prefix="ns_audit_")
    errors = []
    files = {}
    old_chat, old_call = providers.chat, native.Ctx.call
    old_min = glossary_org.OWN_FILE_MIN

    def call(self, messages, json_mode=False, max_tokens=None, label="", stage=None, recover=None):
        rec.label = label
        return old_call(self, messages, json_mode=json_mode, max_tokens=max_tokens, label=label, stage=stage, recover=recover)
    providers.chat = rec.chat
    native.Ctx.call = call
    glossary_org.OWN_FILE_MIN = 1          # 測試書只有 3 章：讓「重要條目獨立成檔」也跑到
    checker = textguard.wrap(_load_checker())     # 和 app.py 一樣包一層語言保護
    prov = {"id": "audit", "type": "openai", "name": "audit", "model": "fake", "context_tokens": 65536, "max_output": 8192}
    try:
        library = os.path.join(tmp, "lib")
        os.makedirs(library)
        book = make_book(library, lang, src)
        bid = os.path.basename(book)

        def act(action, params, book_dir=None, book_id=None):
            rec.action = action
            job = runner.Job(book_id or bid, book_dir or book, action, "", meta={"action": action, "params": params}, provider=prov)
            with contextlib.redirect_stdout(io.StringIO()):
                native.run(job, prov, ROOT, PLUGIN_DIR, checker, {})
            if job.status != "done":
                err = next((e.get("text") for e in reversed(job.events) if e["kind"] == "error"), job.status)
                errors.append("%s：%s" % (action, err))
            if jobs is not None:
                jobs.append((action, [e.get("text", "") for e in job.events if e["kind"] == "log"], job.result or ""))
            return job

        act("reverse", {"upto": 3})
        if only == "reverse":
            files = {k: v for k, v in snapshot(os.path.join(book, reverse.DIR, "草稿")).items()}
            return rec.calls, errors, files
        for g in reverse.GROUPS:
            try:
                reverse.adopt(book, g)
            except project.ProjectError:
                pass
        act("glossary_org", {})
        for g in reverse.GROUPS:
            try:
                reverse.adopt(book, g)
            except project.ProjectError:
                pass
        act("accept", {"chapter": 3})            # 一般回寫
        act("accept", {"chapter": 2})            # 修訂舊章（已追蹤到第3章）
        act("review_notes", {"chapter": 3})
        rv = revision.load_review(book, 3) or {}
        act("revise_notes", {"chapter": 3, "ids": [it["id"] for it in rv.get("items") or []], "extra": ""})
        act("reader_init", {})
        try:
            from studio import tracking
            tracking.adopt_reader_draft(book)
        except Exception:
            pass
        act("reader_reconcile", {})
        act("goal_check", {"chapter": 3})
        card = os.path.join(book, "大綱", "章綱")
        cards = sorted(project._scan_dir(card).items())
        if cards:   # 用第 3 章的章綱當第 4 章，讓「寫下一章」跑得起來
            t = project.read_text(os.path.join(card, cards[-1][1])).replace("章號: 3", "章號: 4").replace("第3章", "第4章")
            with open(os.path.join(card, "第004章_next.md"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(t)
        act("write", {"from": 4, "to": 4})
        chars = project.list_entries(book, "設定/角色")
        if chars:
            act("visual_card", {"file": chars[0]["file"]})
            act("illust_prompt", {"target": "chapter:3", "passage": "...", "chars": [chars[0]["name"]], "places": []})
        shared.shared_dir(library, create=True)
        sd = os.path.join(library, shared.SHARED)
        act("style_design", {"mode": "design", "name": "audit", "genre": "test", "feel": "", "refs": "", "pov": "",
                             "readers": "", "avoid": "", "note": "", "overwrite": True, "sample": "", "exclude": "", "lang": lang},
            book_dir=sd, book_id=shared.SHARED)
        files = snapshot(book)
        files.update({"_共用/" + k: v for k, v in snapshot(sd).items()})
    finally:
        providers.chat, native.Ctx.call = old_chat, old_call
        glossary_org.OWN_FILE_MIN = old_min
        prompts.set_lang("zh-TW")
        shutil.rmtree(tmp, ignore_errors=True)
    return rec.calls, errors, files


def snapshot(book_dir):
    """跑完後書裡的設定、大綱、追蹤、候選（繁中比對「寫出的檔案」也要逐字相同）。備份、任務紀錄這類帶時間的不收。"""
    out = {}
    for top in ("設定", "大綱", "追蹤", "候選", "文風"):
        root = os.path.join(book_dir, top)
        for dp, _, fns in os.walk(root):
            for f in sorted(fns):
                if f.endswith(".md"):
                    full = os.path.join(dp, f)
                    out[os.path.relpath(full, book_dir).replace("\\", "/")] = project.read_text(full)
    return out


# ---------------------------------------------------------------------------
# 找中文句子
# ---------------------------------------------------------------------------
HAN = "㐀-鿿豈-﫿"
HAN_RUN = re.compile("[%s]{2,}" % HAN)
KANA = re.compile("[\u3041-\u3096\u30a1-\u30fa\u30fc]")
# 只在繁體中文出現、日文不用的字（日文寫成新字體或根本不用）：日文書裡出現這些字，幾乎一定是中文句子
ZH_ONLY = set("們這說處關讀應發對將會點與從麼裡寫認歷藝氣變區畫圖戰實讓錄體擇觀覺狀檔沒樣來經號該個嗎呢吧啊哪誰還麼於當並們對話時間書")
ZH_ONLY -= set("認個時間書話當並於")     # 日文也常用的字不算
_PATH = r"(?:設定|大綱|追蹤|正文|候選|範例|_範本|_共用|\.studio)"
STRIP = [
    re.compile(r"(?ms)^---\n.*?\n---\n"),                                    # 檔案的 frontmatter
    re.compile(r"(?m)^[ \t]*#{1,6} .*$"),                                     # 檔案裡的標題（## 一句話）
    re.compile(r"(?m)^[ \t]*(?:[-*]|\d+\.)?[ \t]*[^\s:：|]{1,16}[:：]"),       # 欄位名（- 想要：、身分：）
    re.compile(r"[^\s\"'`(\[（「]*" + _PATH + r"/[^\s\"'`)\],;:）」]*"),      # 路徑
    re.compile(r"第\s*(?:N+|\d+)\s*[章卷]"),                                 # 第NNN章
    re.compile(r"\"[^\"\n]{0,40}\"(?=\s*:)"),                                # JSON 鍵
    re.compile(r"\"[^\"\n]*\|[^\"\n]*\""),                                   # "主角|配角"
    re.compile(r"[「『〔][^」』〕\n]{1,12}[」』〕]"),                              # 「已知」〔懸念〕
    re.compile(r"(?m)^\|.*\|$"),                                             # 表格列
    re.compile(r"<<<[^>\n]*>>>"),
]

_ALLOW = {}


def allowed(lang):
    """「資料格式」的中文詞：該語言的提示詞包與檔案範本裡本來就有的中文（JSON 鍵、列舉值、欄位名）。"""
    if lang not in _ALLOW:
        words = set()
        for v in prompts.pack(lang).values():
            if isinstance(v, str):
                words |= set(HAN_RUN.findall(v))
        tpl = os.path.join(ROOT, "plugin-" + lang, "skills", "novel-setup", "templates")
        if os.path.isdir(tpl):
            for f in os.listdir(tpl):
                words |= set(HAN_RUN.findall(project.read_text(os.path.join(tpl, f))))
        _ALLOW[lang] = words | EXTRA_OK
    return _ALLOW[lang]


# 程式靠它判斷的中文標記（名詞表「注意」欄的「詳見 設定/…」）
EXTRA_OK = {"詳見"}


def _strip(text):
    text = text.split("\n" + "## 回收比對紀錄")[0]     # 讀者認知草稿後面給作者看的比對紀錄（採用時會拿掉）
    for rx in STRIP:
        text = rx.sub(" ", text)
    return text


def bad_segments(text, lang):
    """回傳看起來是中文的片段。
    英文：不在「資料格式」詞表裡的漢字詞（兩字以上）。
    日文：一句裡沒有假名、又有兩個以上繁中專用字（們、這、說、關、讀……）。"""
    s = _strip(text)
    out = []
    if lang == "en":
        ok = allowed(lang)
        for m in re.finditer(r"[%s][%s，。、；：！？（）　]*" % (HAN, HAN), s):
            seg = m.group(0)
            if any(w not in ok for w in HAN_RUN.findall(seg)):
                out.append(seg)
    elif lang == "ja":
        ok = allowed(lang)
        for seg in re.split(r"[\n。！？]", s):
            seg = seg.strip()
            if KANA.search(seg):
                continue
            words = [w for w in HAN_RUN.findall(seg) if w not in ok]
            if sum(1 for w in words for ch in w if ch in ZH_ONLY) >= 2:
                out.append(seg)
    return out


def _book_text(lang, src):
    """測試書正文：從檢查對象中扣掉（日文正文本來就有漢字）。"""
    d = os.path.join(src, "正文") if src else os.path.join(FIXTURES, lang)
    return [project.read_text(os.path.join(d, f)) for _, f in sorted(project._scan_dir(d).items())[:3]]


EDITION = {"zh-TW": "plugin", "en": "plugin-en", "ja": "plugin-ja"}
_PROBE = {}


def edition_probe(ed):
    """該版本 skill 內文裡的一句獨有文字，用來確認提示詞真的載入了那一版。"""
    if ed not in _PROBE:
        p = os.path.join(ROOT, ed, "skills", "novel-write", "references", "writing-craft.md")
        probe = ""
        for line in project.read_text(p).splitlines():
            line = line.strip()
            if len(line) > 30 and not line.startswith(("#", "|", "-", "*", ">", "`")):
                probe = line
                break
        _PROBE[ed] = probe
    return _PROBE[ed]


def check_edition(lang, calls):
    """這本書的提示詞只該載入它自己那一版的 skill 內文（plugin／plugin-en／plugin-ja）。

    報告 A9 說這支工具「固定讀 plugin/」——其實 plugin/ 只是基底，
    真正切換發生在 context.lang_plugin／skill_ref（依 prompts.cur_lang()）。
    與其相信，不如每次跑都驗：該版的句子要在、其他版的句子不能混進來。
    """
    want = EDITION.get(lang)
    if not want:
        return []
    joined = "\n".join(m["content"] for c in calls for m in c["messages"])
    probs = []
    probe = edition_probe(want)
    if not probe:
        probs.append("找不到 %s 的探針句（skills/novel-write/references/writing-craft.md），無法確認載入哪一版" % want)
    elif probe not in joined:
        probs.append("提示詞沒有載入 %s 的 skill 內文（找不到該版獨有的句子）" % want)
    for ed in EDITION.values():
        if ed != want and edition_probe(ed) in joined:
            probs.append("提示詞混入了 %s 的 skill 內文" % ed)
    return probs


def audit(lang, calls, src=None):
    texts = _book_text(lang, src)
    found = {}
    for c in calls:
        for m in c["messages"]:
            body = m["content"]
            for t in texts:
                for para in t.split("\n\n"):
                    if len(para) > 30 and para in body:
                        body = body.replace(para, " ")
            for seg in bad_segments(body, lang):
                key = seg.strip()[:60]
                f = found.setdefault(key, {"count": 0, "where": set()})
                f["count"] += 1
                f["where"].add("%s／%s（%s）" % (c["action"], c["label"], m["role"]))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", default="en,ja", help="en、ja、zh-TW，可用逗號分隔；預設 en,ja")
    ap.add_argument("--src", help="用這本書的前 3 章當測試書（只讀）")
    ap.add_argument("--dump", help="把送出的訊息存到這個資料夾（<語言>.json）")
    ap.add_argument("--compare", help="和這個資料夾裡上次存的訊息逐字比對")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--retry-test", action="store_true", help="測試語言不符時的自動重試與「待核對」標記")
    a = ap.parse_args()
    rc = 0
    if a.retry_test:
        probs = retry_test()
        print("== 語言重試測試：%s" % ("通過" if not probs else "有問題"))
        for x in probs:
            print("  - " + x)
        return 1 if probs else 0
    for lang in [x.strip() for x in a.lang.split(",") if x.strip()]:
        lang = lang_mod.normalize(lang)
        calls, errors, files = run_book(lang, a.src, a.verbose)
        print("== %s：送出 %d 次呼叫" % (lang, len(calls)))
        for e in errors:
            print("  任務失敗：%s" % e)
            rc = 1
        if a.dump:
            os.makedirs(a.dump, exist_ok=True)
            with open(os.path.join(a.dump, lang + ".json"), "w", encoding="utf-8", newline="\n") as f:
                json.dump(calls, f, ensure_ascii=False, indent=1)
            with open(os.path.join(a.dump, lang + ".files.json"), "w", encoding="utf-8", newline="\n") as f:
                json.dump(files, f, ensure_ascii=False, indent=1)
        if a.compare:
            p = os.path.join(a.compare, lang + ".json")
            with open(p, encoding="utf-8") as f:
                old = json.load(f)
            diff = _compare(old, calls)
            pf = os.path.join(a.compare, lang + ".files.json")
            if os.path.isfile(pf):
                with open(pf, encoding="utf-8") as f:
                    old_files = json.load(f)
                for k in sorted(set(old_files) | set(files)):
                    if old_files.get(k) != files.get(k):
                        diff.append("寫出的檔案不同：%s" % k)
            if diff:
                rc = 1
                print("  和 %s 不同：" % p)
                for d in diff[:20]:
                    print("   - " + d)
            else:
                print("  和 %s 逐字相同" % p)
        probs = check_edition(lang, calls)
        if probs:
            rc = 1
            for p in probs:
                print("  版本載入有問題：%s" % p)
        elif not a.compare and not a.dump:
            print("  載入的 skill 版本正確（%s）" % EDITION[lang])
        if lang == "zh-TW":
            continue
        found = audit(lang, calls, a.src)
        in_files = {}
        for rel, text in files.items():
            for seg in bad_segments(text, lang):
                in_files.setdefault(seg.strip()[:60], set()).add(rel)
        if in_files:
            rc = 1
            print("  寫出的檔案有中文句子 %d 種：" % len(in_files))
            for k, rels in sorted(in_files.items()):
                print("   %s" % k)
                if a.verbose:
                    for r in sorted(rels):
                        print("        ← " + r)
        if not found:
            print("  送出的訊息沒有中文句子")
            continue
        rc = 1
        print("  送出的訊息有中文句子 %d 種（共 %d 處）：" % (len(found), sum(f["count"] for f in found.values())))
        for k, f in sorted(found.items(), key=lambda kv: -kv[1]["count"]):
            print("   [%d] %s" % (f["count"], k))
            if a.verbose:
                for w in sorted(f["where"]):
                    print("        ← " + w)
    return rc


def retry_test():
    """語言重試：假 provider 在「整理角色」第一次回中文、第二次回英文 → 要重試一次、任務紀錄有寫、檔案沒有待核對；
    兩次都回中文 → 角色檔備註有「待核對」、任務結果列出步驟。回傳問題清單。"""
    probs = []
    note = prompts.pack("en")["lang_flag_note"]
    for times, expect_flag in ((1, False), (2, True)):
        jobs = []
        calls, errors, files = run_book("en", wrong={"整理角色": times}, jobs=jobs, only="reverse")
        labels = [c["label"] for c in calls]
        logs = [t for _, ls, _ in jobs for t in ls]
        result = "".join(r for _, _, r in jobs)
        chars = {k: v for k, v in files.items() if k.startswith("設定/角色/")}
        name = "回錯 %d 次" % times
        if errors:
            probs.append("%s：任務失敗 %s" % (name, errors))
        if not any(l.endswith("（語言重試）") for l in labels):
            probs.append("%s：沒有重試" % name)
        if not any("請模型重寫一次" in t for t in logs):
            probs.append("%s：任務紀錄沒有寫重試" % name)
        if not chars:
            probs.append("%s：沒有寫出角色檔" % name)
        flagged = [k for k, v in chars.items() if note in v]
        if expect_flag and len(flagged) != len(chars):
            probs.append("%s：角色檔備註沒有標「%s」" % (name, note))
        if expect_flag and note not in result:
            probs.append("%s：任務結果沒有列出語言不符的步驟" % name)
        if not expect_flag and flagged:
            probs.append("%s：重試成功卻標了待核對" % name)
    return probs


def _compare(old, new):
    out = []
    if len(old) != len(new):
        out.append("呼叫次數不同：%d → %d" % (len(old), len(new)))
    for i, (a, b) in enumerate(zip(old, new)):
        if a["label"] != b["label"]:
            out.append("#%d 標籤不同：%s → %s" % (i, a["label"], b["label"]))
        if len(a["messages"]) != len(b["messages"]):
            out.append("#%d（%s）訊息數不同" % (i, a["label"]))
            continue
        for j, (x, y) in enumerate(zip(a["messages"], b["messages"])):
            if x != y:
                xs, ys = x["content"], y["content"]
                k = next((n for n in range(min(len(xs), len(ys))) if xs[n] != ys[n]), min(len(xs), len(ys)))
                out.append("#%d（%s）第%d則訊息不同，從第 %d 字起：%r → %r" % (i, a["label"], j, k, xs[k:k + 40], ys[k:k + 40]))
    return out


if __name__ == "__main__":
    sys.exit(main())
