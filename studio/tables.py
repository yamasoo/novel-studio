# -*- coding: utf-8 -*-
"""追蹤表的欄位：程式內部用英文鍵，檔案裡的表頭維持原樣（v3 結構英文化 P2）。

磁碟上的追蹤表（關係、伏筆、時間線…）表頭是中文，P2 不改檔案內容；這裡只在讀表、寫表的
邊界把「表頭 ↔ 英文鍵」換算。之後 P3 改存 JSON 時，只要換掉讀寫這一層，用資料的程式不必再改。

- 英文鍵沿用 jsonkeys 已有的英文字（who、toward、attitude…）。
- 認不得的表頭（作者自己加的欄）原樣當鍵，寫回時也原樣寫回，不會掉資料。
- 介面與送給模型的表格要顯示表頭：用 columns()／md()，標籤就是原本的中文表頭，輸出逐字不變。
"""
from . import project

# 每張表：(英文鍵, 檔案裡的表頭)，順序就是預設欄位順序
COLUMNS = {
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
    return {key_of(kind, h): v for h, v in row.items()}


def row_to_headers(kind, row):
    return {header_of(kind, k): v for k, v in row.items()}


def rows_to_keys(kind, rows):
    return [row_to_keys(kind, r) for r in rows]


def rows_to_headers(kind, rows):
    return [row_to_headers(kind, r) for r in rows]


def columns(kind, hdrs=None):
    """給介面用的欄位清單：[{key, label}]；hdrs 是檔案裡實際的表頭（含作者加的欄），沒給就用預設。"""
    hdrs = list(hdrs) if hdrs else headers(kind)
    return [{"key": key_of(kind, h), "label": h} for h in hdrs]


def read(book_dir, kind, rel):
    """讀一張追蹤表：{exists, file, headers, columns, rows（英文鍵）}。headers 是檔案裡的原始表頭。"""
    t = project.read_table(book_dir, rel)
    out = {"exists": t["exists"], "headers": t["headers"], "columns": columns(kind, t["headers"]),
           "rows": rows_to_keys(kind, t["rows"])}
    if "file" in t:
        out["file"] = t["file"]
    return out


def md(kind, ks, rows):
    """英文鍵的列 → Markdown 表格（表頭用檔案的中文表頭），和以前 context.table_md(中文表頭, 中文鍵的列) 逐字相同。"""
    if not rows:
        return ""
    hs = [header_of(kind, k) for k in ks]
    out = ["| " + " | ".join(hs) + " |", "|" + "---|" * len(hs)]
    out += ["| " + " | ".join(r.get(k, "") for k in ks) + " |" for r in rows]
    return "\n".join(out)


def pick(item, kind, key, *aliases):
    """從模型回傳的一筆資料取值：英文鍵、表頭（中文）、其他別名都認（jsonkeys 會把英文鍵換成中文）。"""
    for k in (key, header_of(kind, key)) + aliases:
        if k in item and item[k] not in (None, ""):
            return item[k]
    return None
