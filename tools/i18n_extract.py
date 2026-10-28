#!/usr/bin/env python3
"""從前端檔案抓出所有含中文的介面文字，產生語言檔的索引（key＝中文原文，value 留空等翻譯）。

用法：python tools/i18n_extract.py [--merge static/locales/en.json]
  不加 --merge：印出統計並寫 tools/i18n_keys.json
  加 --merge：列出該語言檔還沒翻的 key（缺口），方便補翻譯
文字裡的變數（${...}）會換成 {0}、{1}…；HTML 標籤把文字切成一段一段，和執行期看到的文字節點一致。"""
import json, re, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FILES = ["static/app.js", "static/index.html", "static/relgraph.js"]
CJK = re.compile(r"[぀-ヿ㐀-鿿]")


def js_strings(src):
    """依序取出 JS 裡的字串字面值（'…' "…" `…`），略過註解與 regex 不處理的情況（誤判只會多抓、不會漏）。"""
    i, n = 0, len(src)
    out = []
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i); i = n if j < 0 else j; continue
        if src.startswith("/*", i):
            j = src.find("*/", i); i = n if j < 0 else j + 2; continue
        if c in "'\"":
            j = i + 1; buf = []
            while j < n and src[j] != c and src[j] != "\n":
                if src[j] == "\\": buf.append(src[j:j + 2]); j += 2; continue
                buf.append(src[j]); j += 1
            out.append("".join(buf)); i = j + 1; continue
        if c == "`":
            j = i + 1; buf = []; depth = 0
            while j < n:
                ch = src[j]
                if depth == 0:
                    if ch == "\\": buf.append(src[j:j + 2]); j += 2; continue
                    if ch == "`": break
                    if src.startswith("${", j): depth = 1; buf.append("\x00"); j += 2; continue
                    buf.append(ch); j += 1
                else:   # 在 ${ } 裡：字串與巢狀樣板要整段略過，裡面的樣板文字另外抓
                    if ch == "{": depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0: j += 1; continue
                    elif ch in "'\"`":
                        k = j + 1
                        while k < n and src[k] != ch:
                            k += 2 if src[k] == "\\" else 1
                        inner = src[j:k + 1]
                        out.extend(js_strings(inner)) if ch == "`" else out.append(inner[1:-1])
                        j = k + 1; continue
                    j += 1
            out.append("".join(buf)); i = j + 1; continue
        i += 1
    return out


def segments(s):
    """一個字串 → 介面文字片段（切掉 HTML 標籤、變數換成 {n}）。"""
    res = []
    # 屬性：title / placeholder / aria-label
    for m in re.finditer(r'(?:title|placeholder|aria-label)=\\?"([^"\\]*)', s):
        res.append(m.group(1))
    body = re.sub(r"<[^>]*>", "\x01", s)   # 標籤 → 分隔
    for part in body.split("\x01"):
        res.append(part)
    out = []
    for p in res:
        k = 0
        def rep(_):
            nonlocal k
            k += 1; return "{%d}" % (k - 1)
        p = re.sub(r"\x00", rep, p)
        p = p.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"').strip()
        if CJK.search(p): out.append(p)
    return out


def fold_units(src):
    """字數單位：`${unitCh(...)}` 在執行時是「字」或「詞」，翻譯鍵一律以「字」為準（「詞」那組另外手動補在語言檔）。
    另外，標了 `// i18n-skip` 的整行不抓（單位函式本身）。"""
    src = "\n".join(ln for ln in src.split("\n") if "// i18n-skip" not in ln)
    out, i, tag = [], 0, "${unitCh("
    while True:
        j = src.find(tag, i)
        if j < 0:
            out.append(src[i:]); break
        out.append(src[i:j])
        k, depth = j + len(tag), 1
        while k < len(src) and depth:
            depth += {"(": 1, ")": -1}.get(src[k], 0)
            k += 1
        i = k + 1 if src[k:k + 1] == "}" else k      # 吃掉結尾的 }
        out.append("字")
    return "".join(out)


def extract():
    keys = {}
    for f in FILES:
        src = fold_units(open(os.path.join(ROOT, f), encoding="utf-8").read())
        strs = [src] if f.endswith(".html") else js_strings(src)
        for s in strs:
            for seg in segments(s):
                keys[seg] = keys.get(seg, 0) + 1
    return keys


if __name__ == "__main__":
    keys = extract()
    if "--merge" in sys.argv:
        loc = json.load(open(sys.argv[sys.argv.index("--merge") + 1], encoding="utf-8"))
        miss = [k for k in keys if k not in loc]
        print("缺 %d / %d" % (len(miss), len(keys)))
        for k in miss: print(" ", k)
    else:
        json.dump(dict(sorted(keys.items(), key=lambda x: (-x[1], x[0]))), open(os.path.join(HERE, "i18n_keys.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        print("介面文字 %d 條（出現 %d 次）" % (len(keys), sum(keys.values())))
        print("含變數的 %d 條" % sum(1 for k in keys if re.search(r"\{\d+\}", k)))
        print("長度超過 40 字的 %d 條" % sum(1 for k in keys if len(k) > 40))
