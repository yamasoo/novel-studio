# -*- coding: utf-8 -*-
"""v3 驗收：舊快照套上改名換算後，要跟現在的輸出完全一樣。

- P2：API 回應的鍵（設定集分頁、反推分組、搜尋範圍、追蹤表的欄位）
- P3 第二批：資料夾與系統檔名（換算規則跟移轉工具相同，見 studio/migrate.py）
快照一定會變；這支工具確認「變的只有改名」，沒有夾帶其他行為改變。確認後再用 UPDATE_SNAPSHOT=1 重產快照。

  python tools/snapshot_rename_check.py            # 跟 git 裡的快照比（預設）

  python tools/snapshot_rename_check.py
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from studio import ids, migrate, tables  # noqa: E402
import re  # noqa: E402

_TOK = re.compile(r"[^\s|，、。；：（）()「」『』【】\[\]<>\"'`*,\\{}・;:]+")
_SHARED = sorted(migrate.SHARED_PATHS.values(), key=lambda p: -len(p[0]))


def _path_tok(tok):
    for old, new in _SHARED:
        if tok == old or tok.startswith(old + "/"):
            return new + tok[len(old):]
    return migrate.map_ref(tok)


def convert_paths(v):
    """P3 第二批：快照裡的 v2 路徑（鍵、字串值、檔案內容裡的路徑）換成 v3。"""
    if isinstance(v, dict):
        return {(_path_tok(k) if "/" in k or k in dict(migrate.PAIRS) else k): convert_paths(x) for k, x in v.items()}
    if isinstance(v, list):
        return [convert_paths(x) for x in v]
    if isinstance(v, str):
        whole = _path_tok(v)               # 整個字串就是路徑（檔名可能有空白）
        return whole if whole != v else _TOK.sub(lambda m: _path_tok(m.group(0)), v)
    return v

SNAP = os.path.join(ROOT, "tests", "snapshots", "demo_snapshot.json")


def rename_keys(d, kind):
    return {ids.norm(kind, k): v for k, v in d.items()} if isinstance(d, dict) else d


def transform(old):
    """舊快照 → 依 P2 改名後「應該長的樣子」。"""
    for book, per in old.items():
        if book in ("books", "global"):
            continue
        b = per.get("/bible", {}).get("body")
        if isinstance(b, dict):
            per["/bible"]["body"] = rename_keys(b, "bible_tab")
        r = per.get("/reverse", {}).get("body")
        if isinstance(r, dict) and isinstance(r.get("state"), dict) and "drafts" in r["state"]:
            r["state"]["drafts"] = rename_keys(r["state"]["drafts"], "reverse_group")
        t = per.get("/tracking", {}).get("body")
        if isinstance(t, dict):
            # P2(3)：追蹤表改英文鍵，另附 columns（表頭照舊）
            for name, kind in (("relations", "relations"), ("relations_draft", "relations"),
                               ("foreshadow", "foreshadow"), ("timeline", "timeline"),
                               ("reader", "reader"), ("reader_draft", "reader"), ("glossary", "glossary")):
                x = t.get(name)
                if isinstance(x, dict) and "rows" in x and "columns" not in x:
                    x["rows"] = tables.rows_to_keys(kind, x["rows"])
                    x["columns"] = tables.columns(kind, x.get("headers"))
            g = t.get("relations_graph")
            if isinstance(g, dict) and g.get("rows"):
                g["rows"] = tables.rows_to_keys("relations", g["rows"])
        s = per.get("/search", {}).get("body")
        if isinstance(s, dict):
            if "scopes" in s:
                s["scopes"] = [ids.norm("search_scope", x) for x in s["scopes"]]
            for x in s.get("results") or []:
                x["scope"] = ids.norm("search_scope", x["scope"])
    return convert_paths(old)


def diff(a, b, path="", out=None, limit=40):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append("多出 %s/%s" % (path, k))
            elif k not in b:
                out.append("少了 %s/%s" % (path, k))
            else:
                diff(a[k], b[k], path + "/" + str(k), out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append("長度不同 %s：%d → %d" % (path, len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, "%s[%d]" % (path, i), out, limit)
    elif a != b:
        out.append("值不同 %s：%r → %r" % (path, str(a)[:80], str(b)[:80]))
    return out


def main():
    import test_demo_snapshot as T
    with open(SNAP, encoding="utf-8") as f:
        want = transform(json.load(f))
    T.DemoSnapshotTest.setUpClass()
    try:
        got = json.loads(json.dumps(T.DemoSnapshotTest("test_demo_books_match_snapshot").collect(), ensure_ascii=False, default=str))
    finally:
        T.DemoSnapshotTest.tearDownClass()
    d = diff(want, got)
    if d:
        print("換算後仍有差異（%d 筆以上）：" % len(d))
        for x in d:
            print("  " + x)
        return 1
    print("OK：舊快照換算後與目前輸出完全一致（只有改名）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
