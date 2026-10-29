# -*- coding: utf-8 -*-
"""由 A 書產生 B 書的骨架（P6 Step 3）：一句話前提、主角、卷綱。

輸入只有「風格指紋」與「結構 DNA」——數字、代表句（人名已遮）、章長曲線。
不會把來源的正文、設定、追蹤帶進提示詞，所以情節不可能從這裡漏過去。

硬約束（報告要求）：不得沿用來源的角色名、地名、專有名詞、事件順序。
產出後會用 similarity.names_in 檢查，撞到就要求重寫一次。

產出寫到 候選/新書草稿/，不直接改 設定/：先給人看，滿意再套用。
"""
import json
import os
import re

from . import fingerprint, project, providers, sdna, similarity

REL_DIR = "候選/新書草稿"
RULE = """你在幫作者開一本新書的骨架。只輸出一個 JSON 物件，不要說明、不要程式碼圍欄。

硬性限制：
- 不得使用下面「禁用名單」裡的任何名字（角色名、地名、組織名）——那是另一本書的。
- 不得沿用另一本書的事件順序或橋段；這是一本新書。
- 名字要原創，不要諧音、不要只改一個字。

文風參考（照這個語感寫設定與卷綱，但不要抄句子）：
%s"""
SCHEMA = """{
 "書名建議": "兩到六個字",
 "一句話前提": "誰在什麼處境下、想要什麼、被什麼擋住",
 "賣點": ["三到五條"],
 "主角": [{"名字": "", "定位": "", "動機": "", "弱點": ""}],
 "世界觀要點": ["五到八條"],
 "語感說明": "一句話描述這本新書要維持的語感"
}"""
VOL_RULE = """根據下面的前提與主角，排出第一卷到第二卷的卷綱。只輸出 JSON：
{
 "卷綱": [{"卷": 1, "名稱": "", "章數": 30, "主線": "", "卷末狀態": ""}]
}
章數請參考骨架的平均章數（會給你）。不要寫章節細節。"""


def _cfg():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(here, "config.json")
    if not os.path.isfile(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def provider(pid=None):
    """跟回歸測試同一套規則：不能是 claude_code（要走 /chat/completions）。"""
    cfg = _cfg()
    prov = providers.resolve(cfg.get("providers") or providers.DEFAULT_PROVIDERS,
                             pid or cfg.get("default_provider") or "")
    if not prov:
        raise SystemExit("找不到執行者：%s" % (pid or cfg.get("default_provider")))
    if prov.get("type") == "claude_code":
        raise SystemExit("Claude Code 不能用在這裡（要走 API），請用 --provider 指定 API 執行者。")
    if not str(prov.get("model") or "").strip():
        raise SystemExit("執行者「%s」沒有 model。" % prov.get("id"))
    if not providers.key_status(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), prov):
        raise SystemExit("執行者「%s」還沒有 API 金鑰（設定頁 → AI 執行者，或環境變數）。" % prov.get("id"))
    return prov


def forbidden(source_dir):
    """禁用名單：來源書的角色、勢力、世界觀條目。"""
    return sorted(set(fingerprint._entity_names(source_dir)))


def _style_brief(fp, dna, exemplars=3):
    m = (fp or {}).get("文字指標") or {}
    ch = (fp or {}).get("章節") or {}
    parts = ["對白比例 %s" % (m.get("對白比例") or "—"),
             "平均句長 %s" % (m.get("平均句長") or "—"),
             "短句比例 %s" % (m.get("短句比例") or "—"),
             "平均段長 %s" % (m.get("平均段長") or "—")]
    if (dna or {}).get("視角"):
        parts.append("視角 %s" % dna["視角"].get("人稱"))
    if ch:
        parts.append("平均章長約 %s 字" % ch.get("平均章長"))
    out = "、".join(parts)
    samples = [s for s in ((fp or {}).get("代表句") or [])][:exemplars]
    if samples:
        out += "\n代表句（語感參考，人名已遮；不要照抄）：\n" + "\n".join("- " + s for s in samples)
    return out


def _guard(data, source_dir):
    """產出裡有沒有撞到來源的名字。回傳撞到的名字清單。"""
    text = json.dumps(data, ensure_ascii=False)
    return similarity.names_in(text, forbidden(source_dir))


def _ask(prov, rule, user, max_tokens=2000):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text, _ = providers.chat(root, prov, [{"role": "system", "content": rule},
                                          {"role": "user", "content": user}],
                             json_mode=True, max_tokens=max_tokens)
    data = providers.parse_json(text)
    if not isinstance(data, dict):
        raise SystemExit("模型沒有回傳 JSON 物件")
    return data


def generate(prov, source_dir, note="", lang=None, rounds=0):
    """跑兩次呼叫：premise／主角／世界觀，再一次卷綱。撞名就重試一次。"""
    fp = fingerprint.build(source_dir)
    dna = sdna.build(source_dir)
    lang = lang or fp.get("語言") or "zh-TW"
    ban = forbidden(source_dir)
    style = _style_brief(fp, dna)
    rule = (RULE % style) + "\n\n禁用名單：" + ("、".join(ban) if ban else "（無）")
    user = "請開一本 %s 的新書。%s\n\n只輸出這個結構的 JSON：\n%s" % (
        lang, ("作者補充：" + note) if note else "", SCHEMA)

    data = _ask(prov, rule, user)
    hit = _guard(data, source_dir)
    if hit:
        fix = ("你用了禁用名單裡的名字：%s。請全部換成原創的名字，其他內容可以保留。\n\n"
               "原本的 JSON：\n%s" % ("、".join(hit), json.dumps(data, ensure_ascii=False)))
        data = _ask(prov, rule, fix)
        hit = _guard(data, source_dir)

    volumes = _ask(prov, rule + "\n\n" + VOL_RULE,
                   "前提：%s\n主角：%s\n骨架平均章數：約 %s 章\n只輸出 JSON。" % (
                       data.get("一句話前提", ""),
                       "、".join(c.get("名字", "") for c in (data.get("主角") or [])),
                       (dna.get("章節") or {}).get("平均") or 3000),
                   max_tokens=1200)
    data["卷綱"] = volumes.get("卷綱") or []
    data["骨架來源"] = os.path.basename(source_dir)
    data["護欄"] = {"撞到名字": _guard(data, source_dir), "禁用名單數": len(ban)}
    data["語言"] = lang
    return data


def save(book_dir, data):
    d = os.path.join(book_dir, *REL_DIR.split("/"))
    os.makedirs(d, exist_ok=True)
    json_p = os.path.join(d, "骨架.json")
    with open(json_p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    md_p = os.path.join(d, "骨架.md")
    with open(md_p, "w", encoding="utf-8", newline="\n") as f:
        f.write(show(data))
    return REL_DIR + "/骨架.json"


def show(data):
    if not data:
        return "（還沒有骨架草稿）"
    L = ["# 新書骨架草稿", "",
         "> 由 P6「A 書→B 書」產生，來源骨架：%s。滿意再手動套用到 設定/ 與 大綱/。" % data.get("骨架來源", "—"), "",
         "## 書名建議", data.get("書名建議") or "—", "",
         "## 一句話前提", data.get("一句話前提") or "—", "",
         "## 賣點"]
    L += ["- " + x for x in (data.get("賣點") or [])] or ["- （無）"]
    L += ["", "## 主角"]
    for c in data.get("主角") or []:
        L.append("- **%s**（%s）：動機 %s；弱點 %s" % (c.get("名字"), c.get("定位"), c.get("動機"), c.get("弱點")))
    L += ["", "## 世界觀要點"]
    L += ["- " + x for x in (data.get("世界觀要點") or [])]
    L += ["", "## 卷綱"]
    for v in data.get("卷綱") or []:
        L.append("- 第%s卷《%s》%s 章：%s（卷末：%s）"
                 % (v.get("卷"), v.get("名稱"), v.get("章數"), v.get("主線"), v.get("卷末狀態")))
    L += ["", "## 護欄", "- 撞到來源名字：%s" % (
        "、".join((data.get("護欄") or {}).get("撞到名字") or []) or "沒有")]
    return "\n".join(L) + "\n"
