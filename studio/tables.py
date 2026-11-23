# -*- coding: utf-8 -*-
"""追蹤表的欄位：程式內部用英文鍵，檔案裡的表頭維持原樣（v3 結構英文化 P2）。

磁碟上的追蹤表（關係、伏筆、時間線…）表頭是中文，P2 不改檔案內容；這裡只在讀表、寫表的
邊界把「表頭 ↔ 英文鍵」換算。之後 P3 改存 JSON 時，只要換掉讀寫這一層，用資料的程式不必再改。

- 英文鍵沿用 jsonkeys 已有的英文字（who、toward、attitude…）。
- 認不得的表頭（作者自己加的欄）原樣當鍵，寫回時也原樣寫回，不會掉資料。
- 介面與送給模型的表格要顯示表頭：用 columns()／md()，標籤就是原本的中文表頭，輸出逐字不變。
"""
import re

from . import enums, project

# 每張表：(英文鍵, 檔案裡的表頭)，順序就是預設欄位順序
COLUMNS = {
    "foreshadow": (
        ("id", "編號"), ("content", "內容"), ("planted_in", "埋設章"), ("planned_payoff", "預計回收"),
        ("last_seen", "最後出現"), ("status", "狀態"), ("priority", "重要度"),
    ),
    "timeline": (
        ("id", "編號"), ("story_time", "故事時間"), ("what_really_happened", "實際發生（作者真相）"),
        ("reader_knows_now", "讀者目前知道"), ("revealed_in", "揭示章"), ("related_characters", "相關角色"),
    ),
    "reader": (
        ("id", "編號"), ("type", "類型"), ("content", "內容"), ("author_truth", "作者真相"),
        ("planted_chapter", "種下章"), ("resolved_in", "回收章"), ("related_characters", "相關角色"),
    ),
    "glossary": (
        ("term", "名詞"), ("kind", "類別"), ("explanation", "說明"), ("note", "注意"),
    ),
    "relations": (
        ("id", "編號"), ("who", "誰"), ("toward", "對誰"), ("relationship", "關係"), ("attitude", "態度"),
        ("start_chapter", "起始章"), ("end_chapter", "結束章"), ("reason", "變化原因"),
    ),
}


def keys(kind):
    return [k for k, _ in COLUMNS[kind]]


def headers(kind):
    return [hd for _, hd in COLUMNS[kind]]


def key_of(kind, header):
    """表頭 → 英文鍵；認不得的表頭原樣回傳。"""
    for k, hd in COLUMNS[kind]:
        if header == hd:
            return k
    return header


def header_of(kind, key):
    """英文鍵 → 表頭；認不得的鍵原樣回傳（作者自己加的欄）。"""
    for k, hd in COLUMNS[kind]:
        if key == k:
            return hd
    return key


def row_to_keys(kind, row):
    """表頭當鍵的列（任何語言）→ 英文鍵、內部值的列。"""
    out = {}
    for h, v in row.items():
        k = _key_any(kind, h)
        out[k] = internal(kind, k, v)
    return out


def row_to_headers(kind, row):
    return {header_of(kind, k): v for k, v in row.items()}


def rows_to_keys(kind, rows):
    return [row_to_keys(kind, r) for r in rows]


def rows_to_headers(kind, rows):
    return [row_to_headers(kind, r) for r in rows]


def columns(kind, hdrs=None):
    """給介面用的欄位清單：[{key, label}]；hdrs 是檔案裡實際的表頭（含作者加的欄），沒給就用預設。"""
    hdrs = list(hdrs) if hdrs else headers(kind)
    return [{"key": _key_any(kind, h), "label": h} for h in hdrs]


def file_keys(t):
    """tables.read() 結果裡、檔案實際欄位的英文鍵（含作者加的欄，順序照檔案）。"""
    return [c["key"] for c in t["columns"]]


def read(book_dir, kind, rel):
    """讀一張追蹤表：{exists, file, headers, columns, rows（英文鍵）}。headers 是檔案裡的原始表頭。"""
    t = project.read_table(book_dir, rel)
    out = {"exists": t["exists"], "headers": t["headers"], "columns": columns(kind, t["headers"]),
           "rows": rows_to_keys(kind, t["rows"])}
    if "file" in t:
        out["file"] = t["file"]
    return out


def md(kind, ks, rows, lang=None):
    """英文鍵的列 → 送給模型的 Markdown 表格。表頭與固定值依目前任務的語言（v3 P4）；
    繁中和以前 context.table_md(中文表頭, 中文鍵的列) 逐字相同。"""
    if not rows:
        return ""
    if lang is None:
        from . import prompts, sections
        lang = sections.write_lang(prompts.cur_lang())
    hs = [label(kind, k, lang) for k in ks]
    out = ["| " + " | ".join(hs) + " |", "|" + "---|" * len(hs)]
    if lang in _LI:
        out += ["| " + " | ".join(display(kind, k, r.get(k, ""), lang) for k in ks) + " |" for r in rows]
    else:
        out += ["| " + " | ".join(r.get(k, "") for k in ks) + " |" for r in rows]
    return "\n".join(out)


def pick(item, kind, key, *aliases):
    """從模型回傳的一筆資料（jsonkeys.to_keys 換過的英文鍵）取值；aliases：同一欄在模型資料裡的其他英文鍵。"""
    for k in (key,) + aliases:
        if k in item and item[k] not in (None, ""):
            return item[k]
    return None


# ---------------------------------------------------------------------------
# v3 P3 第六批：表頭與固定值依書的語言（.md），JSON 存英文 ID 與整數章號。
# 程式拿到的列（rows_to_keys／read）一律是「內部值」：固定詞用中文（已埋、懸念…）、章號照檔案寫的
# 中文寫法（第003章），跟以前完全一樣；繁中書的檔案也完全不變。
# ---------------------------------------------------------------------------
# 英文、日文表頭：key → (English, 日本語)
LABELS = {
    "foreshadow": {"id": ("ID", "番号"), "content": ("Content", "内容"), "planted_in": ("Planted in", "仕込んだ章"),
                   "planned_payoff": ("Planned payoff", "回収予定"), "last_seen": ("Last seen", "最後に出た章"),
                   "status": ("Status", "状態"), "priority": ("Priority", "重要度")},
    "timeline": {"id": ("ID", "番号"), "story_time": ("Story time", "作中の時間"),
                 "what_really_happened": ("What really happened (author's truth)", "実際に起きたこと（作者の真実）"),
                 "reader_knows_now": ("What the reader knows now", "読者がいま知っていること"),
                 "revealed_in": ("Revealed in", "明かす章"), "related_characters": ("Characters involved", "関係する人物")},
    "reader": {"id": ("ID", "番号"), "type": ("Type", "種類"), "content": ("Content", "内容"),
               "author_truth": ("Author's truth", "作者の真実"), "planted_chapter": ("Planted in", "仕込んだ章"),
               "resolved_in": ("Resolved in", "回収した章"), "related_characters": ("Characters involved", "関係する人物")},
    "glossary": {"term": ("Term", "用語"), "kind": ("Category", "分類"), "explanation": ("Explanation", "説明"),
                 "note": ("Note", "注意")},
    "relations": {"id": ("ID", "番号"), "who": ("Who", "誰が"), "toward": ("Toward", "誰に"),
                  "relationship": ("Relationship", "関係"), "attitude": ("Attitude", "態度"),
                  "start_chapter": ("From chapter", "開始章"), "end_chapter": ("Until chapter", "終了章"),
                  "reason": ("Why it changed", "変化の理由")},
}
# 固定值的欄：(表, 鍵) → enums 的 kind
# 名詞表的「類別」是半自由的寫法（作者寫「地名」「人名」），照原樣不換。
VALUE_KIND = {("foreshadow", "status"): ("fs_status",), ("foreshadow", "priority"): ("level",), ("reader", "type"): ("type",)}
# 章號的欄（整欄就是一個章號時，JSON 存整數）
CHAPTER_COLS = {"foreshadow": ("planted_in", "last_seen", "planned_payoff"), "timeline": ("revealed_in",),
                "reader": ("planted_chapter", "resolved_in"), "relations": ("start_chapter", "end_chapter")}
_LI = {"en": 0, "ja": 1}


def label(kind, key, lang="zh-TW"):
    """寫進 .md 的表頭；認不得的鍵（作者加的欄）原樣。"""
    if lang in _LI and key in LABELS.get(kind, {}):
        return LABELS[kind][key][_LI[lang]]
    return header_of(kind, key)


def _key_any(kind, header):
    """三種語言的表頭都對回英文鍵；認不得原樣（作者加的欄）。"""
    k = key_of(kind, header)
    if k != header:
        return k
    h = str(header).strip().lower()
    for key, labs in LABELS.get(kind, {}).items():
        if h in (labs[0].lower(), labs[1].lower()) or h == key:
            return key
    return header


_CH_ZH = re.compile(r"^第\s*\d+\s*章$")
_CH_OTHER = re.compile(r"^(?:ch(?:apter)?\.?|ch-)\s*0*(\d+)$", re.I)       # 英文書的章號寫法
_CH_ANY = re.compile(r"^(?:第\s*0*(\d+)\s*章|(?:ch(?:apter)?\.?|ch-)\s*0*(\d+)|0*(\d+))$", re.I)


def _chapter_int(v):
    m = _CH_ANY.match(str(v or "").strip())
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def internal(kind, key, v):
    """任何語言寫的儲存格 → 程式內部值。繁中檔案寫的值一律原樣（所以繁中書的行為完全不變）。"""
    if v is None:
        return ""
    if isinstance(v, bool):
        v = str(v).lower()
    if isinstance(v, int):
        return "第%03d章" % v if key in CHAPTER_COLS.get(kind, ()) else str(v)     # literal-ok: 內部章號寫法
    s = str(v)
    eks = VALUE_KIND.get((kind, key))
    if eks and s.strip():
        if any(s == zh for ek in eks for zh, _ in enums.TABLES[ek]):
            return s
        for ek in eks:                      # JSON 的英文 ID 先比（faction 是「勢力」，不是名詞分類的「組織」）
            hit = _from_id(ek, s)
            if hit:
                return hit
        for ek in eks:
            hit = enums.norm(ek, s)
            if hit:
                return hit
        return s
    if key in CHAPTER_COLS.get(kind, ()) and _CH_OTHER.match(s.strip()):
        return "第%03d章" % int(_CH_OTHER.match(s.strip()).group(1))     # literal-ok: 內部章號寫法（英文、日文的 Ch. 3、第3章 不補零的照原樣）
    return s


def value_id(ek, zh):
    """中文固定詞 → 英文 ID（第一個英文同義詞，空白換成 -）。"""
    for z, syn in enums.TABLES[ek]:
        if z == zh:
            en = next((x for x in syn if re.match(r"[A-Za-z]", x)), None)
            return re.sub(r"\s+", "-", en.strip().lower()) if en else zh
    return None


def _from_id(ek, s):
    k = s.strip().lower()
    for z, _ in enums.TABLES[ek]:
        if value_id(ek, z) == k:
            return z
    return None


def to_json(kind, key, v):
    """內部值 → JSON：固定詞存英文 ID、單一章號存整數，其他原樣（字串）。"""
    s = internal(kind, key, v)
    for ek in VALUE_KIND.get((kind, key), ()):
        vid = value_id(ek, s) if s else None
        if vid:
            return vid
    if key in CHAPTER_COLS.get(kind, ()):
        n = _chapter_int(s)
        if n is not None:
            return n
    return s


def display(kind, key, v, lang="zh-TW"):
    """內部值 → 寫進 .md 的寫法（依書的語言）。繁中原樣。"""
    s = internal(kind, key, v)
    if lang not in _LI or not s:
        return s
    for ek in VALUE_KIND.get((kind, key), ()):
        if any(s == zh for zh, _ in enums.TABLES[ek]):
            return enums.show(ek, s, lang)
    if key in CHAPTER_COLS.get(kind, ()) and _CH_ZH.match(s.strip()):
        n = _chapter_int(s)
        return ("Ch. %d" if lang == "en" else "第%d章") % n
    return s


def render(kind, ks, rows, lang="zh-TW"):
    """英文鍵、內部值的列 → .md 表格（表頭與固定值依語言；繁中與以前 tracking._render_table 逐字相同）。"""
    hs = [label(kind, k, lang) for k in ks]
    out = ["| " + " | ".join(hs) + " |", "|" + "|".join(["---"] * len(hs)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_cell(display(kind, k, r.get(k, ""), lang)) for k in ks) + " |")
    return "\n".join(out)


def _cell(v):
    return str(v if v is not None else "").replace("|", "／").replace("\n", " ").strip()


DOC_KIND = {"foreshadowing": "foreshadow", "timeline": "timeline", "reader-knowledge": "reader",
            "relations": "relations", "glossary": "glossary"}


def relocalize(text, kind, lang):
    """把文件裡第一張表格（表頭與固定值）換成 lang 的寫法；表格前後的文字不動。
    目標是繁中時，表頭已經是繁中的表格不動（繁中書的檔案完全不變），英文、日文的表格才換回來。"""
    if not text:
        return text
    lines = text.split("\n")
    for i in range(len(lines) - 1):
        if lines[i].strip().startswith("|") and re.match(r"^\s*\|[\s:\-|]+\|\s*$", lines[i + 1]):
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            hs = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            ks = [_key_any(kind, h) for h in hs]
            if lang not in _LI and all(h == header_of(kind, k) for h, k in zip(hs, ks)):
                return text
            rows = []
            for l in lines[i + 2:j]:
                cells = [c.strip() for c in l.strip().strip("|").split("|")]
                cells += [""] * (len(hs) - len(cells))
                rows.append({k: internal(kind, k, c) for k, c in zip(ks, cells)})
            return "\n".join(lines[:i] + render(kind, ks, rows, lang).split("\n") + lines[j:])
    return text
