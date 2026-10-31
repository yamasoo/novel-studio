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

from . import fingerprint, project, prompts, providers, sdna, similarity, spawn, tracking

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


def _ask(prov, rule, user, max_tokens=4000):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    msgs = [{"role": "system", "content": rule}, {"role": "user", "content": user}]
    # stage="structured"：推理模型的「思考」也算在 max_tokens 裡。不指定階段的話
    # 思考會照模型預設開著，常把輸出額度吃完，回來只剩空字串或被截斷的 JSON。
    text, _ = providers.chat(root, prov, msgs, json_mode=True, max_tokens=max_tokens, stage="structured")
    try:
        data = providers.parse_json(text)
    except providers.ProviderError:
        # 模型偶爾還是會把 JSON 寫壞：把原輸出帶回去，明確要求只重出 JSON 一次。
        retry = msgs + [{"role": "assistant", "content": text},
                        {"role": "user", "content": prompts.cur()["json_retry_short"]}]
        text, _ = providers.chat(root, prov, retry, json_mode=True, max_tokens=max_tokens, stage="structured")
        data = providers.parse_json(text)
    if not isinstance(data, dict):
        raise SystemExit("模型沒有回傳 JSON 物件")
    return data


def generate(prov, source_dir, note="", lang=None, rounds=0, progress=None):
    """跑兩次呼叫：premise／主角／世界觀，再一次卷綱。撞名就重試一次。

    progress(msg)：給工作台顯示「現在在做什麼」；不給就安靜跑。
    """
    say = progress or (lambda _msg: None)
    say("量參考書的文風指紋…")
    fp = fingerprint.build(source_dir)
    say("量結構 DNA…")
    dna = sdna.build(source_dir, fp)
    lang = lang or fp.get("語言") or "zh-TW"
    say("整理禁用名單…")
    ban = forbidden(source_dir)
    style = _style_brief(fp, dna)
    rule = (RULE % style) + "\n\n禁用名單：" + ("、".join(ban) if ban else "（無）")
    user = "請開一本 %s 的新書。%s\n\n只輸出這個結構的 JSON：\n%s" % (
        lang, ("作者補充：" + note) if note else "", SCHEMA)

    say("產生骨架（第 1 次模型呼叫）…")
    data = _ask(prov, rule, user)
    hit = _guard(data, source_dir)
    if hit:
        say("有名字撞到來源，帶著名單重寫一次…")
        fix = ("你用了禁用名單裡的名字：%s。請全部換成原創的名字，其他內容可以保留。\n\n"
               "原本的 JSON：\n%s" % ("、".join(hit), json.dumps(data, ensure_ascii=False)))
        data = _ask(prov, rule, fix)
        hit = _guard(data, source_dir)

    say("產生卷綱（第 2 次模型呼叫）…")
    volumes = _ask(prov, rule + "\n\n" + VOL_RULE,
                   "前提：%s\n主角：%s\n骨架平均章數：約 %s 章\n只輸出 JSON。" % (
                       data.get("一句話前提", ""),
                       "、".join(c.get("名字", "") for c in (data.get("主角") or [])),
                       (dna.get("章節") or {}).get("平均") or 3000),
                   max_tokens=3000)   # 推理模型：思考也算在 max_tokens，別給太小
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


# ---------------------------------------------------------------------------
# 新書「用骨架直接開書」：把骨架寫成正式專案（跳過開書訪談）
# ---------------------------------------------------------------------------
def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _as_int(value, default):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _vol_rows(volumes):
    """骨架的卷綱 → 累積章節範圍。第 1 卷從第 1 章開始，第 2 卷接在第 1 卷後面。"""
    rows = []
    start = 1
    for i, v in enumerate(volumes, 1):
        if not isinstance(v, dict):
            continue
        n = max(1, _as_int(v.get("章數"), 30))
        no = _as_int(v.get("卷"), i)
        rows.append({"no": no, "name": str(v.get("名稱") or "第%d卷" % no),
                     "lo": start, "hi": start + n - 1, "n": n,
                     "main": str(v.get("主線") or "").strip(),
                     "end": str(v.get("卷末狀態") or "").strip()})
        start += n
    return rows


def _avg_chars(fp, dna):
    for obj in (dna, fp):
        if not isinstance(obj, dict):
            continue
        ch = obj.get("章節") or {}
        for key in ("平均", "平均章長"):
            n = _as_int(ch.get(key), 0)
            if n > 0:
                return n
    return 3000


def _story_core_md(data, title, lang, dna):
    premise = str(data.get("一句話前提") or "").strip()
    sells = [str(x).strip() for x in (data.get("賣點") or []) if str(x).strip()]
    prots = [p for p in (data.get("主角") or []) if isinstance(p, dict)]
    volumes = [v for v in (data.get("卷綱") or []) if isinstance(v, dict)]
    total = sum(max(1, _as_int(v.get("章數"), 30)) for v in volumes)
    avg = _avg_chars(None, dna)
    pov = ((dna or {}).get("視角") or {}).get("人稱") or "（待補：骨架未指定）"
    L = ["---", "類型: 故事核心", "書名: %s" % title, "狀態: 草稿", "語言: %s" % lang,
         "每章字數: %d" % avg, "---", "",
         "# 故事核心", "", "## 一句話鉤子", premise, "",
         "## 題材與定位",
         "- 題材：（待補：骨架未指定）",
         "- 目標讀者：（待補：骨架未指定）",
         "- 發表平台與更新節奏：（待補：骨架未指定）",
         "- 預計篇幅：共 %d 卷、%d 章（每章約 %d 字）" % (len(volumes), total, avg),
         "- 敘事視角：%s" % pov, "",
         "## 賣點（讀者為什麼看）"]
    L += ["%d. %s" % (i, x) for i, x in enumerate(sells, 1)] or ["1. （待補）"]
    L += ["", "## 主角"]
    for p in prots:
        name = str(p.get("名字") or "（未命名）").strip()
        role = str(p.get("定位") or "").strip()
        motive = str(p.get("動機") or "（待補）").strip()
        weak = str(p.get("弱點") or "（待補）").strip()
        L.append("- **%s**%s：動機 %s；弱點 %s"
                 % (name, ("（%s）" % role) if role else "", motive, weak))
    if not prots:
        L.append("- （待補）")
    L += ["", "## 世界觀", "- 見 `設定/世界觀/世界觀.md`（由骨架帶入）。", "",
          "## 故事引擎", "（待補：骨架沒有這一段，請在設定頁補。）", "",
          "## 核心衝突", "- 主要對手：（待補）", "- 衝突根源：（待補）", "",
          "## 讀者契約", "- （待補）", "",
          "## 終局方向", "（待補）", "",
          "## 升級台階", "1. （待補）"]
    return "\n".join(L) + "\n"


def _world_md(data):
    points = [str(x).strip() for x in (data.get("世界觀要點") or []) if str(x).strip()]
    if not points:
        return ""
    L = ["---", "類型: 世界觀", "分類: 其他", "標籤: []", "名稱: 世界觀要點", "狀態: 草稿", "---", "",
         "# 世界觀要點", ""]
    L += ["- " + x for x in points]
    return "\n".join(L) + "\n"


def _outline_md(data, rows, dna):
    premise = str(data.get("一句話前提") or "").strip()
    total = rows[-1]["hi"] if rows else 0
    avg = _avg_chars(None, dna)
    L = ["---", "類型: 全書大綱", "狀態: 草稿", "---", "", "# 全書大綱", "",
         "## 總覽",
         "- 預計卷數與字數：%d 卷，共 %d 章；以每章約 %d 字計，約 %s 字"
         % (len(rows), total, avg, "{:,}".format(total * avg)),
         "- 主線一句話：%s" % premise,
         "- 終局：（待補）", "", "## 分卷"]
    for r in rows:
        words = "{:,}".format(r["n"] * avg)
        L += ["", "### 第%s卷：%s" % (r["no"], r["name"]),
              "- 篇幅：第%d～%d章，約 %s 字" % (r["lo"], r["hi"], words),
              "- 本卷目標：%s" % (r["main"] or "（待補）"),
              "- 主要對手：（待補）",
              "- 卷末變化：%s" % (r["end"] or "（待補）"),
              "- 卷末大高潮：（待補）",
              "- 本卷埋下、留給後面的東西：（待補）"]
    L += ["", "## 主線伏筆總規劃", "| 伏筆 | 埋設 | 回收 |", "|---|---|---|", "",
          "## 感情線／支線規劃", "- （待補）"]
    return "\n".join(L) + "\n"


def _volume_md(row):
    return """---
類型: 卷綱
卷名: %(name)s
章節範圍: 第%(lo)03d章～第%(hi)03d章
狀態: 已確認
---

# 卷綱：%(name)s

## 卷契約
- 本卷賣點：（待補）
- 主角本卷目標：%(main)s
- 本卷對手：（待補）
- 卷末兌現：%(end)s
- 卷末新鉤子：（待補）

## 本卷常駐規則
- （待補）

## 劇情單元
（由「用參考書骨架直接開書」建立，尚未拆單元；請用「卷先行 → 排這一卷的章綱」。）

## 情緒曲線
（待補）

## 人物弧線
- （待補）

## 本卷伏筆
| 編號 | 內容 | 埋設章 | 回收章 |
|---|---|---|---|
""" % {"name": row["name"], "lo": row["lo"], "hi": row["hi"],
       "main": row["main"] or "（待補）", "end": row["end"] or "（待補）"}


def _claude_md(title, lang, fp, dna, source):
    text = spawn.claude_md(title, lang, fp, dna, source).rstrip()
    note = ("> 由「用參考書骨架直接開書」建立（未經開書訪談）。"
            "目標讀者、平台、篇幅等可在 `設定/故事核心.md` 補；卷綱與章綱可在「大綱」頁調整。")
    return text + "\n\n" + note + "\n"


def apply_new(book_dir, data, title=None, lang="zh-TW", source=""):
    """把骨架寫成正式專案；只給「剛建立、還沒有 CLAUDE.md」的新書用。

    寫入 故事核心／世界觀／全書大綱／卷綱，最後才寫 CLAUDE.md。最後才寫是刻意的：
    前面的檔案失敗時這本書還不是專案，重跑一次就好，不會卡在「已是專案」。
    """
    if not isinstance(data, dict) or not str(data.get("一句話前提") or "").strip():
        raise project.ProjectError("骨架沒有內容，不能套用。")
    volumes = [v for v in (data.get("卷綱") or []) if isinstance(v, dict)]
    if not volumes:
        raise project.ProjectError("骨架沒有卷綱，不能直接開書；請重試產生骨架。")
    title = (title or os.path.basename(book_dir)).strip()
    cpath = os.path.join(book_dir, "CLAUDE.md")
    if os.path.isfile(cpath):
        old = project.read_text(cpath)
        if "用參考書骨架直接開書" not in old:
            raise project.ProjectError("這本書已經是專案，不能用『直接開書』覆蓋；請改用開書訪談或手動套用。")
    fp = _load_json(os.path.join(book_dir, "設定", "風格指紋.json"))
    dna = _load_json(os.path.join(book_dir, "設定", "結構DNA.json"))
    rows = _vol_rows(volumes)
    if not rows:
        raise project.ProjectError("骨架的卷綱格式不對，不能直接開書。")
    files, backups = [], []

    def put(rel, text):
        p = os.path.join(book_dir, *rel.split("/"))
        if os.path.isfile(p):
            b = tracking.backup(book_dir, p, "套用骨架前")
            if b:
                backups.append(project.rel_of(book_dir, b))
        _write(p, text)
        files.append(rel)

    put("設定/故事核心.md", _story_core_md(data, title, lang, dna))
    world = _world_md(data)
    if world:
        put("設定/世界觀/世界觀.md", world)
    put("大綱/全書大綱.md", _outline_md(data, rows, dna))
    for r in rows:
        put("大綱/卷綱_第%d卷.md" % r["no"], _volume_md(r))
    put("CLAUDE.md", _claude_md(title, lang, fp, dna, source))
    return {"files": files, "backups": backups}
