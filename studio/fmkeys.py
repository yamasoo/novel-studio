# -*- coding: utf-8 -*-
"""frontmatter 的鍵：程式內部一律英文，檔案裡的寫法在這裡換算（v3 規格第 4 節）。

- 讀：project.split_frontmatter 回傳英文鍵。檔案裡寫中文鍵（v2 與目前的範本）或英文鍵都認。
- 寫：project.set_frontmatter_field 收英文鍵。檔案裡已經有那一行就照原本的寫法改；
  沒有就寫英文鍵（WRITE）。程式自己組的 frontmatter 一律英文鍵；舊書由移轉工具一次換好。
- 「章名」「書名」「卷名」在 v3 都叫 title（WRITE 是 zh 時依文件類型挑中文寫法）。
"""
import re


# (英文鍵, 中文鍵)。同一個英文鍵可以有好幾個中文寫法（title）。
PAIRS = [
    ("type", "類型"), ("status", "狀態"), ("name", "名稱"), ("aliases", "別名"), ("role", "定位"),
    ("category", "分類"), ("tags", "標籤"), ("first_appearance", "首次登場"), ("last_appearance", "最後登場"),
    ("related_characters", "相關角色"), ("chapter", "章號"), ("title", "章名"), ("title", "書名"), ("title", "卷名"),
    ("volume", "所屬卷"), ("unit", "所屬單元"), ("target_length", "字數目標"), ("length", "字數"),
    ("updated_through", "更新至"), ("chapter_range", "章節範圍"), ("lang", "語言"), ("chapter_length", "每章字數"),
    ("default", "預設"), ("scope", "適用"), ("structure", "結構"), ("source", "來源"),
]
ZH2EN = {zh: en for en, zh in PAIRS}
EN2ZH = {}
for _en, _zh in PAIRS:
    EN2ZH.setdefault(_en, _zh)
TITLE_BY_TYPE = {"章綱": "章名", "卷綱": "卷名", "故事核心": "書名"}   # literal-ok: v2 的文件類型值

WRITE = "en"        # 新加的欄位用哪一種寫法（P3 第四批前半是 zh，後半起 en）


def en(key):
    """檔案裡的鍵 → 英文鍵；不認得的原樣（作者自己加的欄位）。"""
    return ZH2EN.get(key, key)


def to_en(fm):
    """frontmatter dict 的鍵換成英文；同一個欄位寫了兩次（中文、英文都有）以先出現的為準。"""
    out = {}
    for k, v in (fm or {}).items():
        k2 = en(k) if isinstance(k, str) else k
        if k2 not in out:
            out[k2] = v
    return out


def file_keys(key):
    """這個英文鍵在檔案裡可能的寫法（比對既有的行用）。"""
    return [key] + [zh for e, zh in PAIRS if e == key]


def write_key(key, doc_type=""):
    """新加一行時寫成什麼鍵。doc_type：這份文件的「類型」（決定 title 寫成章名／卷名／書名）。"""
    if WRITE == "en" or key not in EN2ZH:
        return key
    if key == "title":
        return TITLE_BY_TYPE.get(str(doc_type or ""), EN2ZH[key])
    return EN2ZH[key]


# ---------------------------------------------------------------------------
# 值：type、status、role、category、default 的固定詞（v3 規格第 5 節）。
# 檔案裡寫中文或英文 ID 都認；程式交給介面與提示詞的是 disp()（目前是中文顯示字，P5 改成 ID＋標籤），
# 寫回檔案用 write_value()（WRITE_VALUES 決定寫中文還是英文 ID）。
# ---------------------------------------------------------------------------
VALUES = {
    "type": [("character", "角色"), ("faction", "勢力"), ("world", "世界觀"), ("story-core", "故事核心"),
             ("style", "文風"), ("glossary", "名詞表"), ("author-prefs", "作者偏好"), ("book-outline", "全書大綱"),
             ("volume-outline", "卷綱"), ("chapter-card", "章綱"), ("chapter-summary", "章節摘要"),
             ("character-state", "角色狀態"), ("state-card", "狀態卡"), ("timeline", "時間線"),
             ("foreshadowing", "伏筆總表"), ("foreshadowing", "伏筆"), ("reader-knowledge", "讀者認知"),
             ("relations", "關係"), ("continuation-contract", "續寫合約"), ("shared-author-prefs", "共用作者偏好"),
             ("chapter-structure", "章節結構")],
    "status": [("draft", "草稿"), ("canon", "正式"), ("approved", "已確認"), ("written", "已寫"), ("stub", "待填")],
    "role": [("protagonist", "主角"), ("main-supporting", "主要配角"), ("supporting", "配角"),
             ("antagonist", "反派"), ("minor", "路人")],
    "category": [("power-system", "力量體系"), ("geography-climate", "地理與氣候"), ("history", "歷史與年表"),
                 ("society-politics", "社會與政治"), ("economy", "經濟與物資"), ("religion", "宗教信仰"),
                 ("culture", "文化與風俗"), ("technology", "科技原理"), ("vehicles-weapons", "載具與兵器"),
                 ("ecology", "生態與資源"), ("other", "其他")],
    "default": [("true", "是")],
}
_V_EN = {k: {zh: en for en, zh in pairs} for k, pairs in VALUES.items()}
_V_ZH = {}
for _k, _pairs in VALUES.items():
    _V_ZH[_k] = {}
    for _en, _zh in _pairs:
        _V_ZH[_k].setdefault(_en, _zh)

WRITE_VALUES = "en"     # 寫回檔案的值（P3 第四批 4c-1 是 zh，4c-2 起 en）


def value_en(key, v):
    """檔案裡的值 → 英文 ID；認不得的（作者自己寫的）原樣。布林 true 也算「是」。"""
    key = en(key)
    if key not in VALUES or v is None:
        return v
    if v is True and key == "default":
        return "true"
    s = str(v).strip()
    if s in _V_ZH[key]:
        return s
    return _V_EN[key].get(s, v)


def disp(key, v):
    """交給介面、提示詞、設定索引的值：中文顯示字（檔案寫英文 ID 也一樣）。認不得的原樣。"""
    key = en(key)
    if key not in VALUES or v is None:
        return v
    if isinstance(v, str) and v.strip() in _V_EN[key]:
        return v.strip()                    # 本來就是中文（含同義的舊寫法，例如「伏筆」）照原樣
    e = value_en(key, v)
    return _V_ZH[key].get(e, v) if isinstance(e, str) else v


def write_value(key, v):
    """寫進 frontmatter 的值。"""
    key = en(key)
    if key not in VALUES or v is None:
        return v
    return value_en(key, v) if WRITE_VALUES == "en" else disp(key, v)


# ---------------------------------------------------------------------------
# 章號、章節範圍、所屬卷：v3 存整數（first_appearance: 12、chapter_range: [1, 60]、volume: 1）。
# 讀的時候「第012章」「12」「ch-0012」都認（各處原本就只抓數字）；交給介面的照舊是「第012章」。
# ---------------------------------------------------------------------------
CHAPTER_KEYS = ("first_appearance", "last_appearance", "updated_through")
_CN_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def ch_int(v):
    """章號：12、"12"、"第012章"、"ch-0012" → 12；讀不到回 None。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    m = re.search(r"\d+", str(v or ""))
    return int(m.group(0)) if m else None


def ch_disp(v):
    """交給介面與提示詞的章號：第012章（讀不到數字就原樣）。"""
    n = ch_int(v)
    return "第%03d章" % n if n is not None else v       # literal-ok: 介面的章號寫法（P5 改成依語言）


def ch_value(v):
    """寫進 frontmatter 的章號。"""
    n = ch_int(v)
    if n is None:
        return v
    return n if WRITE_VALUES == "en" else "第%03d章" % n   # literal-ok: v2 的章號寫法


def range_value(lo, hi):
    """寫進 frontmatter 的章節範圍：[1, 60]。"""
    return "[%d, %d]" % (int(lo), int(hi)) if WRITE_VALUES == "en" else "第%03d章～第%03d章" % (int(lo), int(hi))   # literal-ok: v2 寫法


def volume_int(v):
    """所屬卷：1、"1"、"第一卷"、"第12卷" → 整數；讀不到回 None。"""
    n = ch_int(v)
    if n is not None:
        return n
    s = re.sub(r"[第卷\s]", "", str(v or ""))      # literal-ok: v2 的卷號寫法
    if not s or any(c not in _CN_DIGITS and c not in "十百" for c in s):
        return None
    total, cur = 0, 0
    for c in s:
        if c == "十":
            total += (cur or 1) * 10
            cur = 0
        elif c == "百":
            total += (cur or 1) * 100
            cur = 0
        else:
            cur = _CN_DIGITS[c]
    return (total + cur) or None


# ---------------------------------------------------------------------------
# 文件檢視器的 frontmatter 小標籤：[[標籤, 值], ...]，照檔案裡的順序。
# 標籤與值都是中文顯示字，前端再用 FE.t 翻成介面語言（跟其他交給介面的值一樣）。
# ---------------------------------------------------------------------------
_RANGE = re.compile(r"^\s*\[\s*(\d+)\s*,\s*(\d+)\s*\]\s*$")


def _view_value(key, v):
    if key in CHAPTER_KEYS or key == "chapter":
        n = ch_int(v)
        return "第%d章" % n if n is not None else v          # literal-ok: 介面的章號寫法（前端翻成各語言）
    if key == "volume":
        n = volume_int(v)
        return "第%d卷" % n if n is not None else v          # literal-ok: 同上
    if key == "chapter_range":
        m = _RANGE.match(str(v))
        return "第%s–%s章" % (m.group(1), m.group(2)) if m else v   # literal-ok: 同上（「第{0}–{1}章」）
    return disp(key, v)


def view(raw_fm):
    """raw_fm：project.split_frontmatter_raw 的結果（檔案裡的鍵與順序）。空值與 [] 不列。"""
    out = []
    doc_type = disp("type", (to_en(raw_fm) or {}).get("type")) or ""
    for k, v in (raw_fm or {}).items():
        if v is None or v == "" or v == [] or str(v).strip() in ("", "[]"):
            continue
        key = en(k) if isinstance(k, str) else k
        if key == "title":
            label = TITLE_BY_TYPE.get(doc_type, "標題")      # literal-ok: 顯示名稱
        else:
            label = EN2ZH.get(key, k)
        val = _view_value(key, v)
        if isinstance(val, list):
            val = "、".join(str(x) for x in val)
        elif isinstance(val, bool):
            val = "是" if val else "否"                       # literal-ok: 顯示名稱
        out.append([str(label), str(val)])
    return out
