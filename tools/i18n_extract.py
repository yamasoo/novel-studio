#!/usr/bin/env python3
"""從前端檔案抓出所有含中文的介面文字，產生語言檔的索引（key＝中文原文，value 留空等翻譯）。

用法：python tools/i18n_extract.py [--merge static/locales/en.json] [--no-py] [--py-only]
  不加 --merge：印出統計並寫 tools/i18n_keys.json
  加 --merge：列出該語言檔還沒翻的 key（缺口），方便補翻譯
  預設連 app.py、studio/*.py 的後端訊息一起掃（用 ast）：HTTPException、raise *Error、emit(log/error/start/cancelled)、
  log(…)、call(label=…)、Job 的 title、job.result。--no-py 只掃前端，--py-only 只掃後端。
  後端字串的 %s／%d／{}／f-string 變數一律換成 {0}、{1}…；還原不了的（動態拼接）列在「需要手動處理」。
文字裡的變數（${...}）會換成 {0}、{1}…；HTML 標籤把文字切成一段一段，和執行期看到的文字節點一致。"""
import json, re, sys, os, ast, glob

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


# ---------------------------------------------------------------- 後端（Python）
PY_FILES = ["app.py"] + sorted(os.path.relpath(p, ROOT).replace("\\", "/") for p in glob.glob(os.path.join(ROOT, "studio", "*.py")))
EMIT_KINDS = {"log", "error", "start", "cancelled"}
_PCT = re.compile(r"%[-+ #0]*(?:\d+|\*)?(?:\.\d+)?[sdrfiu]")
_BRACE = re.compile(r"\{[A-Za-z_0-9\.\[\]]*(?:![rs])?(?::[^{}]*)?\}")
_DYN = "\x00"   # 動態片段的標記，最後換成 {0}、{1}…


def _tmpl(node):
    """AST 運算式 → 樣式字串（變數用 \\x00 標記）；回傳 (樣式, 是否完全還原)。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, True
    if isinstance(node, ast.JoinedStr):
        out, ok = [], True
        for v in node.values:
            if isinstance(v, ast.Constant): out.append(str(v.value))
            else: out.append(_DYN)
        return "".join(out), True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        l, ok = _tmpl(node.left)
        if ok and isinstance(node.left, (ast.Constant, ast.JoinedStr, ast.BinOp)):
            return _PCT.sub(_DYN, l.replace("%%", "\x01")).replace("\x01", "%"), True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        l, a = _tmpl(node.left); r, b = _tmpl(node.right)
        return l + r, a and b and (l != _DYN or r != _DYN) or (a or b)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        base, ok = _tmpl(node.func.value)
        if ok and isinstance(node.func.value, ast.Constant):
            return _BRACE.sub(_DYN, base), True
    if isinstance(node, ast.IfExp):
        return _DYN, False
    return _DYN, False


def _tmpl_all(node):
    """像 _tmpl，但「A + (B if c else D)」這種條件拼接會展開成每一種可能的完整字串。"""
    if isinstance(node, ast.IfExp):
        return _tmpl_all(node.body) + _tmpl_all(node.orelse)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        ls, rs = _tmpl_all(node.left), _tmpl_all(node.right)
        if len(ls) * len(rs) > 1:
            return [(l[0] + r[0], l[1] and r[1]) for l in ls for r in rs]
    return [_tmpl(node)]


def _call_name(f):
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


# 任務結果（markdown 報告）是由這些函式拼出來的；掃它們裡面「像報告句子」的字串
RESULT_FUNCS = {
    "goals.py": {"report_md"}, "revision.py": {"review_md"}, "reader_ledger.py": {"save_draft", "apply_recon"},
    "style_design.py": {"finish"}, "native.py": {"deslop_result", "_writeback", "save_illust_result", "save_card_result"},
    "wb_check.py": {"run"}, "native_files.py": {"result_text"}, "fidelity.py": {"run"}, "reverse.py": {"run"},
    "glossary_org.py": {"organize"}, "tracking.py": {"apply_writeback"},
}


RESULT_IGNORE = {"（無）", "首次出現：%s", "第%03d章 %s", "輸出仍被截斷，請到設定調高「最大輸出」後再試。", "可以再試一次，或改用其他模型。"}     # 寫進檔案或 git 提交說明的，不是介面訊息


def _is_report_text(v):
    if v.startswith("---") or "(?" in v or v.endswith((".md", ".json")): return False
    return len(v) >= 4 and ("**" in v or "%" in v or v.startswith(("\n", "；", "- ", "（")) or "。" in v)


def py_strings(src, fname):
    """回傳 [(類別, 樣式, 行號, 完整還原?)]。"""
    tree = ast.parse(src)
    found = []

    def add(kind, node):
        for t, ok in _tmpl_all(node):
            if CJK.search(t):
                found.append((kind, t, getattr(node, "lineno", 0), ok))

    def scan_dyn_consts(kind, node):   # 運算式沒法整個還原（條件、函式回傳…）時，把裡面的中文字面值各自收
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and CJK.search(sub.value):
                found.append((kind + "*", sub.value, sub.lineno, False))

    rf = RESULT_FUNCS.get(os.path.basename(fname), set())
    docs = {ast.get_docstring(n) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.Module, ast.ClassDef))} - {None}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name in rf:
            doc = ast.get_docstring(fn)
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and CJK.search(sub.value) \
                        and re.sub(r"\s+", "", sub.value) not in {re.sub(r"\s+", "", d) for d in docs} and sub.value not in RESULT_IGNORE \
                        and _is_report_text(sub.value):
                    found.append(("任務結果", _PCT.sub(_DYN, sub.value.replace("%%", "%")), sub.lineno, True))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            nm = _call_name(node.func)
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if nm == "HTTPException":
                add("錯誤", kw.get("detail") or (node.args[1] if len(node.args) > 1 else (node.args[0] if node.args else None)))
            elif nm == "emit" and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in EMIT_KINDS:
                v = kw.get("text") or (node.args[1] if len(node.args) > 1 else None)
                if v is not None: add("任務紀錄", v)
            elif nm == "log" and node.args:
                add("任務紀錄", node.args[0])
            elif nm == "call" and "label" in kw:
                add("串流標籤", kw["label"])
            elif nm == "call" and node.args and not isinstance(node.args[0], (ast.List, ast.Name)):   # reverse.py：call("標籤", prompt)
                add("串流標籤", node.args[0])
            elif nm == "step" and len(node.args) > 1:
                add("串流標籤", node.args[1])
            elif nm == "effort_label" or (nm == "think_tag"):
                pass
            elif nm == "append" and node.args and isinstance(node.func, ast.Attribute) \
                    and getattr(node.func.value, "id", "") in ("warnings", "issues", "problems", "notes", "warn", "flags", "f"):
                add("提示", node.args[0])
            elif nm == "Job":
                v = kw.get("title") or (node.args[2] if len(node.args) > 2 else None)
                if v is not None: add("任務標題", v)
        elif isinstance(node, ast.Dict) and fname.endswith(("app.py", "project.py", "wb_check.py", "fidelity.py", "goals.py")):
            for k, v in zip(node.keys, node.values):   # 總覽提醒／保真檢查／回寫檢查的 {"text": …, "kind": …}
                if isinstance(k, ast.Constant) and k.value in ("text", "kind") and isinstance(v, (ast.Constant, ast.BinOp, ast.JoinedStr, ast.IfExp, ast.Call)):
                    for t, ok in _tmpl_all(v):
                        if CJK.search(t) and t != _DYN: found.append(("提示", t, getattr(v, "lineno", 0), ok))
        elif isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            nm = _call_name(node.exc.func)
            if nm.endswith("Error") or nm.endswith("Exception"):
                if node.exc.args: add("錯誤", node.exc.args[0])
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            tg = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(tg, ast.Attribute) and tg.attr == "result":
                add("任務結果", node.value)
            elif isinstance(tg, ast.Name) and tg.id in ("label", "title", "tag", "label_"):
                add("串流標籤", node.value)
    return found


def _num(t):
    k = [0]
    def rep(_):
        k[0] += 1; return "{%d}" % (k[0] - 1)
    return re.sub(_DYN, rep, t)


def result_fragments(t):
    """任務結果是 markdown：渲染後一句會被粗體、連結、清單項目切成好幾個文字節點，key 要照切開後的片段收。"""
    out = []
    for line in t.split("\n"):
        if line.lstrip().startswith("#") and not line.lstrip().startswith("#/"): continue      # markdown 標題多半是寫進檔案的內容
        line = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line)
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", lambda m: "\x01" + m.group(1) + "\x01", line)
        out.extend(p for p in re.split(r"\*\*|\x01", line) if p.strip())
    return out


def extract_py(with_manual=False):
    keys, manual = {}, []
    for f in PY_FILES:
        try:
            src = open(os.path.join(ROOT, f), encoding="utf-8").read()
        except OSError:
            continue
        for kind, t, line, ok in py_strings(src, f):
            for seg in result_fragments(t) if kind == "任務結果" else [t]:
                seg = _num(seg).strip()
                if not CJK.search(seg) or seg in ("（無）",): continue
                if kind.endswith("*") or not ok:
                    manual.append((f, line, kind, seg))
                if not kind.endswith("*"):
                    keys[seg] = keys.get(seg, 0) + 1
    return (keys, manual) if with_manual else keys


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
    if "--py-only" in sys.argv: keys = {}
    else: keys = extract()
    manual = []
    if "--no-py" not in sys.argv:
        pk, manual = extract_py(True)
        for k, v in pk.items(): keys[k] = keys.get(k, 0) + v
    if "--manual" in sys.argv:
        for f, ln, kind, seg in manual: print("%s:%d [%s] %s" % (f, ln, kind, seg))
        sys.exit(0)
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
