"""前文全文搜尋：純本機，直接讀檔，不用模型、不建索引。

- 多個詞用空白分開＝要同時出現在同一份檔案；引號包起來＝完整片語。
- 不分繁簡、不分英文大小寫：比對前把文字逐字轉成同一種寫法（一字對一字，位置不變，前後文仍取原文）。
"""
import os
import re

from . import project

SCOPES = {
    "正文": ("正文", True),
    "候選": ("候選", True),
    "章綱": ("大綱", False),
    "設定": ("設定", False),
    "追蹤": ("追蹤", False),
}
DEFAULT_SCOPES = ("正文",)
CONTEXT = 40          # 前後文各取幾個字
MAX_SNIPPETS = 30     # 每份檔案最多回傳幾處
MAX_FILES = 400

_TABLE = None


def _table():
    """繁→簡逐字對照表（只取一字對一字的）。沒有 OpenCC 時只做英文大小寫。"""
    global _TABLE
    if _TABLE is not None:
        return _TABLE
    tbl = {ord(c): ord(c.lower()) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"}
    try:
        import opencc
        d = os.path.join(os.path.dirname(opencc.__file__), "dictionary")
        for name in ("TSCharacters.txt",):
            p = os.path.join(d, name)
            if not os.path.isfile(p):
                continue
            with open(p, encoding="utf-8") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 2:
                        continue
                    src, dst = parts[0], parts[1].split(" ")[0]
                    if len(src) == 1 and len(dst) == 1 and src != dst:
                        tbl.setdefault(ord(src), ord(dst))
    except Exception:
        pass
    _TABLE = tbl
    return tbl


def norm(s):
    return (s or "").translate(_table())


def parse_query(q):
    terms = [a or b for a, b in re.findall(r'"([^"]+)"|「([^」]+)」', q or "")]
    rest = re.sub(r'"[^"]*"|「[^」]*」', " ", q or "")
    terms += [t for t in rest.split() if t]
    out = []
    for t in terms:
        t = t.strip()
        if t and t not in out:
            out.append(t)
    return out


def _files(book_dir, scope):
    sub, chapters = SCOPES[scope]
    root = os.path.join(book_dir, sub)
    if not os.path.isdir(root):
        return
    if chapters:
        for no, f in sorted(project._scan_dir(root).items()):
            yield {"kind": "chapter", "no": no, "title": project.chapter_title_from_filename(f), "path": sub + "/" + f}
        return
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if not d.startswith("."))
        for f in sorted(fns):
            if not f.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(dp, f), book_dir).replace("\\", "/")
            no = project.chapter_no(f) if rel.startswith(("大綱/章綱/", "追蹤/章節摘要/")) else None
            yield {"kind": "file", "no": no, "title": os.path.splitext(f)[0], "path": rel}


def _segments(text, start, end, spans):
    """把 [start, end) 這段切成一般文字與標亮文字。"""
    segs, pos = [], start
    for a, b in spans:
        a, b = max(a, start), min(b, end)
        if a >= b or a < pos:
            continue
        if a > pos:
            segs.append({"t": text[pos:a]})
        segs.append({"t": text[a:b], "hl": True})
        pos = b
    if pos < end:
        segs.append({"t": text[pos:end]})
    return segs


def search(book_dir, q, scopes=None):
    terms = parse_query(q)
    if not terms:
        return {"query": q, "terms": [], "results": [], "files": 0, "hits": 0}
    scopes = [s for s in (scopes or DEFAULT_SCOPES) if s in SCOPES] or list(DEFAULT_SCOPES)
    nterms = [norm(t) for t in terms]
    results, hits, truncated = [], 0, False
    for scope in scopes:
        for info in _files(book_dir, scope):
            try:
                text = project.read_text(os.path.join(book_dir, info["path"]))
            except OSError:
                continue
            nt = norm(text)
            if not all(t in nt for t in nterms):
                continue
            spans = []
            for t in nterms:
                i = nt.find(t)
                while i >= 0:
                    spans.append((i, i + len(t)))
                    i = nt.find(t, i + len(t))
            spans.sort()
            count = len(spans)
            hits += count
            # 前後文：相鄰的命中併成同一段
            snips, cur = [], None
            for a, b in spans:
                s, e = max(0, a - CONTEXT), min(len(text), b + CONTEXT)
                if cur and s <= cur[1]:
                    cur[1] = max(cur[1], e)
                else:
                    if cur:
                        snips.append(cur)
                    cur = [s, e]
            if cur:
                snips.append(cur)
            out = []
            for s, e in snips[:MAX_SNIPPETS]:
                segs = _segments(text, s, e, spans)
                for sg in segs:
                    sg["t"] = re.sub(r"\s+", " ", sg["t"])
                out.append({"pre": s > 0, "post": e < len(text), "segs": segs})
            results.append(dict(info, scope=scope, count=count, snippets=out, more=max(0, len(snips) - MAX_SNIPPETS)))
            if len(results) >= MAX_FILES:
                truncated = True
                break
        if truncated:
            break
    chap = [r for r in results if r["scope"] == "正文"]
    first = min((r["no"] for r in chap if r.get("no")), default=None)
    return {"query": q, "terms": terms, "scopes": scopes, "results": results, "files": len(results), "hits": hits,
            "chapters": len(chap), "first": first, "truncated": truncated}
