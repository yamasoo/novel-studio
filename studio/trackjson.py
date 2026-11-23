# -*- coding: utf-8 -*-
"""五張追蹤表的 JSON 正本（v3 規格第 9 節）：伏筆、時間線、讀者認知、角色關係、名詞表。

檔案：每張表的 `.md` 旁邊有一份同名 `.json`，例如 tracking/foreshadowing.md ↔ tracking/foreshadowing.json。

    {"schema_version": 3, "table": "foreshadow", "updated_through": 12,
     "columns": [{"key": "id", "label": "編號"}, ...],      ← 含作者自己加的欄，順序照表格
     "items": [{"id": "F001", "content": "...", ...}, ...],
     "md_sha": "...", "items_sha": "..."}

兩份怎麼保持一致（作者在 2026-11-22 選定「.md 較新就讀回 JSON」）：
- 工作台寫表格時照舊寫 `.md`，寫完由 project.write_atomic 順手更新 JSON（mirror）。
- Claude Code 技能與作者會直接改 `.md`；之後讀取時發現 `.md` 跟 JSON 記的指紋（md_sha）不同，就以 `.md` 為準。
- 其他工具改了 JSON（items 跟 items_sha 對不上、`.md` 沒動）就以 JSON 為準，sync() 時重寫 `.md` 的表格。
- **讀取不寫檔**：只有寫表格、sync()、移轉工具會寫 JSON。
"""
import hashlib
import json
import os
import re

from . import layout

SCHEMA = 3
# 書裡的相對路徑 → tables.COLUMNS 的表名
CANON = {
    layout.FORESHADOWING: "foreshadow",
    layout.TIMELINE: "timeline",
    layout.READER_KNOWLEDGE: "reader",
    layout.RELATIONS: "relations",
    layout.GLOSSARY: "glossary",
}


def json_rel(rel):
    return rel[:-3] + ".json"


def _sha(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _items_sha(columns, items):
    return _sha(json.dumps([columns, items], ensure_ascii=False, sort_keys=True))


def kind_of_path(path):
    """絕對路徑 → (表名, 書的相對路徑)；不是五張正本之一（含 .studio 裡的草稿）回 (None, None)。"""
    p = path.replace("\\", "/")
    if "/.studio/" in p:
        return None, None
    for rel, kind in CANON.items():
        if p.endswith("/" + rel):
            return kind, rel
    return None, None


def _from_md(kind, text):
    from . import project, tables, fmkeys
    fm, _ = project.split_frontmatter(text)
    headers, rows = project.parse_md_table(text)
    cols = tables.columns(kind, headers) if headers else []
    # 固定詞存英文 ID、單一章號存整數（tables.to_json）；其他欄照檔案的字
    items = [{k: tables.to_json(kind, k, v) for k, v in tables.row_to_keys(kind, r).items()} for r in rows]
    data = {"schema_version": SCHEMA, "table": kind}
    ut = fmkeys.ch_int(fm.get("updated_through"))
    if ut is not None:
        data["updated_through"] = ut
    data.update({"columns": cols, "items": items, "md_sha": _sha(text), "items_sha": _items_sha(cols, items)})
    return data


def dump(d):
    """一欄、一列各占一行（git 的差異與合併以列為單位，比整份縮排好讀）。"""
    one = lambda v: json.dumps(v, ensure_ascii=False)
    out = ["{"]
    keys = list(d)
    for i, k in enumerate(keys):
        end = "," if i < len(keys) - 1 else ""
        v = d[k]
        if k in ("columns", "items") and isinstance(v, list) and v:
            out.append(' %s: [' % one(k))
            out += ["  %s%s" % (one(x), "," if j < len(v) - 1 else "") for j, x in enumerate(v)]
            out.append(" ]" + end)
        else:
            out.append(" %s: %s%s" % (one(k), one(v), end))
    return "\n".join(out) + "\n}\n"


def mirror(path, text=None):
    """`.md` 寫好之後更新旁邊的 JSON。不是正本的檔不處理。"""
    kind, _ = kind_of_path(path)
    if not kind:
        return None
    if text is None:
        if not os.path.isfile(path):
            return None
        from . import project
        text = project.read_text(path)
    data = _from_md(kind, text)
    from . import project
    project.write_atomic(path[:-3] + ".json", dump(data))
    return data


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and isinstance(d.get("items"), list) else None
    except (OSError, ValueError):
        return None


def state(book_dir, rel):
    """回傳 (狀態, JSON 資料)。狀態：
    same＝兩份一致；md＝.md 改過（或沒有 JSON），以 .md 為準；json＝只有 JSON 改過；
    json_only＝沒有 .md、JSON 是別的工具建的（沒記過 md_sha）；
    deleted＝.md 被刪了（JSON 記過 md_sha）：當成這張表已經拿掉；none＝兩份都沒有。"""
    md_p = os.path.join(book_dir, *rel.split("/"))
    js_p = os.path.join(book_dir, *json_rel(rel).split("/"))
    d = _load_json(js_p) if os.path.isfile(js_p) else None
    if not os.path.isfile(md_p):
        if not d:
            return "none", None
        return ("deleted" if d.get("md_sha") else "json_only"), d
    if d is None:
        return "md", None
    from . import project
    md_ok = d.get("md_sha") == _sha(project.read_text(md_p))
    json_ok = d.get("items_sha") == _items_sha(d.get("columns") or [], d.get("items") or [])
    if md_ok and json_ok:
        return "same", d
    if json_ok or not md_ok:
        return "md", d                  # .md 改過（兩份都改過時也以 .md 為準：那是作者或技能動的）
    return "json", d


def read(book_dir, rel):
    """給 project.read_table 用：只有 JSON 改過（或沒有 .md）時從 JSON 組出 {headers, rows（表頭當鍵）}；
    兩份一致時回 None，照舊解析 .md（值就是檔案寫的字，跟以前逐字相同）。"""
    if rel not in CANON:
        return None
    st, d = state(book_dir, rel)
    if st not in ("json", "json_only"):
        return None
    from . import tables
    kind = CANON[rel]
    cols = d.get("columns") or []
    headers = [c.get("label") or c.get("key") for c in cols]
    rows = [{(c.get("label") or c.get("key")): tables.internal(kind, c.get("key"), it.get(c.get("key")))
             for c in cols} for it in d.get("items") or []]
    return {"exists": True, "headers": headers, "rows": rows, "file": rel}


def _cell(v):
    return str(v if v is not None else "").replace("|", "／").replace("\n", " ").strip()


def render_table(cols, items):
    hs = [c.get("label") or c.get("key") for c in cols]
    out = ["| " + " | ".join(hs) + " |", "|" + "|".join(["---"] * len(hs)) + "|"]
    for it in items:
        out.append("| " + " | ".join(_cell(it.get(c.get("key"), "")) for c in cols) + " |")
    return "\n".join(out)


def _splice(text, table):
    """把 text 裡第一張表格換成 table；沒有表格就接在最後。"""
    lines = text.split("\n")
    for i in range(len(lines) - 1):
        if lines[i].strip().startswith("|") and re.match(r"^\s*\|[\s:\-|]+\|\s*$", lines[i + 1]):
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            return "\n".join(lines[:i] + table.split("\n") + lines[j:])
    return text.rstrip("\n") + "\n\n" + table + "\n"


def _new_md(kind, d):
    from . import fmkeys
    doc = {"foreshadow": "foreshadowing", "timeline": "timeline", "reader": "reader-knowledge",
           "relations": "relations", "glossary": "glossary"}[kind]
    head = "---\ntype: %s\n" % doc
    if d.get("updated_through") is not None:
        head += "updated_through: %s\n" % fmkeys.ch_value(d["updated_through"])
    return head + "---\n\n"


def sync(book_dir):
    """把只在 JSON 改過的表寫回 .md、沒有 JSON 的表補上 JSON。回傳處理過的相對路徑。"""
    from . import project
    done = []
    for rel, kind in CANON.items():
        st, d = state(book_dir, rel)
        md_p = os.path.join(book_dir, *rel.split("/"))
        if st in ("json", "json_only"):
            from . import lang as lang_mod, sections, tables
            old = project.read_text(md_p) if os.path.isfile(md_p) else _new_md(kind, d)
            ks = [c.get("key") for c in d.get("columns") or []] or tables.keys(kind)
            rows = [{k: tables.internal(kind, k, it.get(k)) for k in ks} for it in d.get("items") or []]
            table = tables.render(kind, ks, rows, sections.write_lang(lang_mod.book_lang(book_dir)))
            project.write_atomic(md_p, _splice(old, table))   # 寫完會 mirror
            done.append(rel)
        elif st == "md" and (d is None or d.get("md_sha") != _sha(project.read_text(md_p))):
            mirror(md_p)
            done.append(rel)
        elif st == "deleted":
            os.remove(os.path.join(book_dir, *json_rel(rel).split("/")))
            done.append(rel)
    return done


def pending(book_dir):
    """還沒有 JSON（或 JSON 跟 .md 對不上）的正本表格。"""
    return [rel for rel in CANON if state(book_dir, rel)[0] in ("md", "json", "json_only")]


def missing(book_dir):
    """書架偵測用（只看檔案在不在，不讀內容）：有 .md 卻沒有 JSON 的正本表格。"""
    return [rel for rel in CANON
            if os.path.isfile(os.path.join(book_dir, *rel.split("/")))
            and not os.path.isfile(os.path.join(book_dir, *json_rel(rel).split("/")))]
