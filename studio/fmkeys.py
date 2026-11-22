# -*- coding: utf-8 -*-
"""frontmatter 的鍵：程式內部一律英文，檔案裡的寫法在這裡換算（v3 規格第 4 節）。

- 讀：project.split_frontmatter 回傳英文鍵。檔案裡寫中文鍵（v2 與目前的範本）或英文鍵都認。
- 寫：project.set_frontmatter_field 收英文鍵。檔案裡已經有那一行就照原本的寫法改；
  沒有就寫英文鍵（WRITE）。程式自己組的 frontmatter 一律英文鍵；舊書由移轉工具一次換好。
- 「章名」「書名」「卷名」在 v3 都叫 title（WRITE 是 zh 時依文件類型挑中文寫法）。
"""

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
