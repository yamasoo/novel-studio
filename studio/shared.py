# -*- coding: utf-8 -*-
"""
共用庫：放在書庫資料夾的 _共用/ 底下，所有書都能用，不在工作台程式資料夾裡（不會進 git）。

_共用/
├── 文風/<名稱>.md        可重複使用的文風（套用時複製到書的 設定/文風.md）
├── 結構/<名稱>.md        章節結構（套用時複製到書的 設定/章節結構/）
└── 作者偏好.md           跨書的長期偏好、常犯的毛病、禁用詞（直接生效，不複製）

文風分析、結構套用、禁用詞比對都在本機完成，不呼叫 AI。
"""
import os
import re
import shutil
import time
from collections import Counter

from . import project

SHARED = "_共用"
HERE = os.path.dirname(os.path.abspath(__file__))
PRESET_DIR = os.path.join(HERE, "presets", "結構")
STYLE_TEMPLATE = os.path.join(os.path.dirname(HERE), "plugin", "skills", "novel-setup", "templates", "文風.md")
METRICS_HEAD = "## 文字指標（程式統計）"

PREFS_TEMPLATE = """---
類型: 共用作者偏好
---

# 共用作者偏好

> 所有書都會套用。寫作、改稿、審查時 AI 會讀這份檔案；「禁用詞」一節由程式在「檢查用語與 AI 味」時逐字比對，不用呼叫 AI。
> 某本書要例外，寫在那本書的 設定/作者偏好.md，以那本書為準。

## 長期偏好
<!-- 一條一行。例：對白後面少用「他說」「她說」，看得出是誰說的就省略 -->
-

## 常犯的毛病
<!-- 你知道自己（或 AI）常犯、希望寫作時避開、審查時特別抓出來的。例：同一段連續三句都用「她」開頭 -->
-

## 禁用詞
<!-- 一行一個，程式會逐字比對。「→」後面寫建議（選填）。用 /.../ 包起來代表正規表示式。
例：
- 不由得 → 直接寫動作
- 嘴角勾起一抹
- /眼[中底]閃過一[絲抹道]/ → 改成具體的表情或動作
-->
-
"""


class SharedError(project.ProjectError):
    pass


# ---------------------------------------------------------------------------
# 路徑
# ---------------------------------------------------------------------------
def shared_dir(library, create=False):
    if not library:
        raise SharedError("還沒有設定書庫資料夾")
    d = os.path.join(library, SHARED)
    if create:
        for sub in ("文風", "結構"):
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        p = os.path.join(d, "作者偏好.md")
        if not os.path.isfile(p):
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(PREFS_TEMPLATE)
    return d


def shared_of_book(book_dir):
    return os.path.join(os.path.dirname(os.path.normpath(book_dir)), SHARED)


def _name_ok(name):
    name = (name or "").strip()
    if not name or re.search(r'[\\/:*?"<>|]', name) or name.startswith("."):
        raise SharedError("名稱不能空白，也不能有 \\ / : * ? \" < > | 這些符號")
    return name


def safe_shared_path(library, rel):
    d = os.path.normpath(shared_dir(library))
    p = os.path.normpath(os.path.join(d, rel or ""))
    if not (p == d or p.startswith(d + os.sep)):
        raise SharedError("路徑不合法")
    return p


def _backup(book_dir, path, tag):
    if os.path.isfile(path):
        bak = os.path.join(book_dir, ".studio", "備份")
        os.makedirs(bak, exist_ok=True)
        shutil.copy2(path, os.path.join(bak, "%s_%s_%d.md" % (tag, os.path.splitext(os.path.basename(path))[0], int(time.time()))))


def set_fm(text, key, value):
    """在 frontmatter 設定（value=None 時刪除）一個鍵；沒有 frontmatter 就新增。只處理單行值。"""
    line = None if value is None else "%s: %s" % (key, value)
    if text.startswith("---"):
        lines = text.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                fm = lines[1:i]
                fm = [x for x in fm if not re.match(r"%s\s*:" % re.escape(key), x)]
                if line:
                    fm.append(line)
                return "\n".join(["---"] + fm + lines[i:])
    return ("---\n%s\n---\n\n" % line + text) if line else text


def clean_body(text):
    """去掉 frontmatter、HTML 註解、空的項目符號，判斷檔案是否還只是空範本。"""
    body = project.split_frontmatter(text or "")[1]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"(?m)^\s*-\s*$\n?", "", body)
    body = re.sub(r"(?m)^>.*$\n?", "", body)
    return body.strip()


def _meaningful(text):
    body = clean_body(text)
    return bool(re.sub(r"(?m)^#.*$", "", body).strip())


# ---------------------------------------------------------------------------
# 共用作者偏好（直接生效）
# ---------------------------------------------------------------------------
def prefs_for_context(book_dir):
    p = os.path.join(shared_of_book(book_dir), "作者偏好.md")
    if not os.path.isfile(p):
        return ""
    text = project.read_text(p)
    return clean_body(text) if _meaningful(text) else ""


# ---------------------------------------------------------------------------
# 文風庫
# ---------------------------------------------------------------------------
def list_styles(library):
    d = os.path.join(shared_dir(library), "文風")
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".md"):
                p = os.path.join(d, f)
                text = project.read_text(p)
                m = parse_metrics(text)
                summ = ("平均句長 %s 字・對白 %s・段長 %s 字" % (m.get("平均句長"), m.get("對白比例"), m.get("平均段長"))
                        if m else _first_line(text))
                out.append({"name": f[:-3], "file": "文風/" + f, "mtime": os.path.getmtime(p),
                            "summary": summ, "has_metrics": bool(m),
                            "sample": m.get("樣本字數") if m else None})
    return out


def _first_line(text):
    for ln in clean_body(text).split("\n"):
        s = ln.strip().lstrip("-").strip()
        if s and not s.startswith(("#", "|", "語言地區", "標點")) and "：" in s and not s.endswith("："):
            return s[:60]
    return ""


def create_style(library, name, source=None, sample_text=None, exclude=()):
    """source: None（空白範本）或 ("book", 書目錄)。sample_text 有值時附上文字指標與範例段落。"""
    name = _name_ok(name)
    d = os.path.join(shared_dir(library, create=True), "文風")
    p = os.path.join(d, name + ".md")
    if os.path.exists(p):
        raise SharedError("已經有叫「%s」的文風了" % name)
    if source and source[0] == "book":
        src = os.path.join(source[1], "設定", "文風.md")
        if not os.path.isfile(src):
            raise SharedError("這本書還沒有 設定/文風.md")
        text = project.read_text(src)
    else:
        text = project.read_text(STYLE_TEMPLATE) if os.path.isfile(STYLE_TEMPLATE) else "---\n類型: 文風\n---\n\n# 文風\n"
    text = set_fm(set_fm(text, "名稱", name), "類型", "文風")
    text = re.sub(r"(?m)^# 本書文風\s*$", "# 文風：%s" % name, text, count=1)
    if sample_text:
        text = put_metrics(text, analyze(sample_text, exclude))
        text = put_samples(text, sample_text)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return {"name": name, "file": "文風/" + name + ".md"}


def restat_style(library, name, sample_text):
    p = os.path.join(shared_dir(library), "文風", _name_ok(name) + ".md")
    if not os.path.isfile(p):
        raise SharedError("找不到這個文風")
    text = put_metrics(project.read_text(p), analyze(sample_text))
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return parse_metrics(text)


def apply_style(library, name, book_dir):
    src = os.path.join(shared_dir(library), "文風", _name_ok(name) + ".md")
    if not os.path.isfile(src):
        raise SharedError("找不到這個文風")
    dst = os.path.join(book_dir, "設定", "文風.md")
    _backup(book_dir, dst, "文風")
    text = project.read_text(src)
    text = set_fm(set_fm(set_fm(text, "類型", "文風"), "來源", "共用文風「%s」" % name), "名稱", None)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return "設定/文風.md"


def save_style_from_book(library, name, book_dir, overwrite=False):
    name = _name_ok(name)
    src = os.path.join(book_dir, "設定", "文風.md")
    if not os.path.isfile(src):
        raise SharedError("這本書還沒有 設定/文風.md")
    d = os.path.join(shared_dir(library, create=True), "文風")
    dst = os.path.join(d, name + ".md")
    if os.path.exists(dst) and not overwrite:
        raise SharedError("已經有叫「%s」的文風了" % name)
    text = set_fm(set_fm(project.read_text(src), "名稱", name), "來源", None)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return {"name": name}


def delete_item(library, kind, name):
    sub = {"style": "文風", "structure": "結構"}[kind]
    p = os.path.join(shared_dir(library), sub, _name_ok(name) + ".md")
    if not os.path.isfile(p):
        raise SharedError("找不到這個檔案")
    trash = os.path.join(shared_dir(library), ".刪除")
    os.makedirs(trash, exist_ok=True)
    os.replace(p, os.path.join(trash, "%s_%s_%d.md" % (sub, name, int(time.time()))))


# ---------------------------------------------------------------------------
# 文字指標（本機統計）
# ---------------------------------------------------------------------------
CJK = re.compile(r"[㐀-鿿豈-﫿]")
SENT_END = re.compile(r"[。！？!?]+[」』]?|……+[」』]?")
PUNCT_KEYS = [("逗號", "，"), ("頓號", "、"), ("驚嘆號", "！"), ("問號", "？"), ("刪節號", "……"), ("破折號", "——")]
# 數值越大／越小代表什麼（給作者看的說明）
METRIC_NOTES = {
    "平均句長": "字；越短節奏越快",
    "短句比例": "8 字以下的句子",
    "長句比例": "30 字以上的句子",
    "平均段長": "字",
    "單句成段": "只有一句的段落比例",
    "對白比例": "引號內字數佔全部",
    "對白段比例": "含對白的段落比例",
    "每千字的": "「的」字密度，越高修飾越多",
    "每千字地": "「地」字密度，越高副詞越多",
    "每千字AI味信號": "程式偵測到的常見 AI 套語",
}


def _prose(text):
    body = project.split_frontmatter(text)[1].replace("\r\n", "\n")
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"(?m)^\s*#.*$", "", body)
    body = re.sub(r"(?m)^\s*([-*_]){3,}\s*$", "", body)
    return body


def _paragraphs(body):
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if len(paras) <= 2 and body.count("\n") > 4:
        paras = [ln.strip() for ln in body.split("\n") if ln.strip()]
    return [re.sub(r"\s+", "", p.lstrip("　 ")) for p in paras]


def _ai_signals():
    try:
        import importlib.util
        p = os.path.join(os.path.dirname(HERE), "plugin", "skills", "novel-deslop", "scripts", "check_text.py")
        spec = importlib.util.spec_from_file_location("check_text_for_metrics", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return [pat for _, pat in mod.AI_SIGNALS]
    except Exception:
        return []


_AI = None


def analyze(text, exclude=()):
    """回傳有順序的指標 dict。exclude：不列入高頻詞組的詞（例如本書的人名、地名）。"""
    global _AI
    if _AI is None:
        _AI = _ai_signals()
    body = _prose(text)
    paras = _paragraphs(body)
    joined = "".join(paras)
    total = len(CJK.findall(joined))
    if total < 300:
        raise SharedError("樣本太短了（中文 %d 字）。至少要 300 字，建議 3000 字以上，統計才有參考價值。" % total)
    sents = []
    for p in paras:
        start = 0
        for m in SENT_END.finditer(p):
            sents.append(p[start:m.end()])
            start = m.end()
        if p[start:].strip():
            sents.append(p[start:])
    slen = [len(CJK.findall(s)) for s in sents]
    slen = [n for n in slen if n > 0]
    plen = [len(CJK.findall(p)) for p in paras if CJK.search(p)]
    dlg = sum(len(CJK.findall(m)) for m in re.findall(r"「([^「」]*)」", joined))
    k = 1000.0 / total
    m = {"樣本字數": total,
         "平均句長": round(sum(slen) / len(slen), 1) if slen else 0,
         "短句比例": "%d%%" % round(100.0 * sum(1 for n in slen if n <= 8) / max(1, len(slen))),
         "長句比例": "%d%%" % round(100.0 * sum(1 for n in slen if n >= 30) / max(1, len(slen))),
         "平均段長": round(sum(plen) / len(plen), 1) if plen else 0,
         "單句成段": "%d%%" % round(100.0 * sum(1 for p in paras if len(SENT_END.findall(p)) <= 1) / max(1, len(paras))),
         "對白比例": "%d%%" % round(100.0 * dlg / total),
         "對白段比例": "%d%%" % round(100.0 * sum(1 for p in paras if "「" in p) / max(1, len(paras)))}
    for label, ch in PUNCT_KEYS:
        m["每千字" + label] = round(joined.count(ch) * k, 1)
    m["每千字的"] = round(joined.count("的") * k, 1)
    m["每千字地"] = round(len(re.findall(r"(?<=[一-鿿])地(?=[一-鿿])", joined)) * k, 1)
    m["每千字AI味信號"] = round(sum(len(re.findall(p, joined)) for p in _AI) * k, 1)
    m["高頻詞組"] = "、".join(frequent_phrases(paras, exclude=exclude)) or "（沒有特別重複的詞組）"
    return m


EDGE_HEAD = set("了的著過是在和與就也都又還把被給讓從向對而且")
EDGE_TAIL = set("了的著一是在把被給和與從向對而且就也都又還個")


def frequent_phrases(paras, top=12, exclude=()):
    """出現 3 次以上的 2～4 字詞組（去掉被更長詞組涵蓋的），可以看出口頭禪與慣用語。"""
    cnt = Counter()
    for p in paras:
        for chunk in re.findall(r"[一-鿿]+", p):
            for n in (2, 3, 4):
                for i in range(len(chunk) - n + 1):
                    cnt[chunk[i:i + n]] += 1
    stop = set("一個 不是 什麼 沒有 自己 知道 他們 我們 你們 她們 這個 那個 這樣 那樣 已經 還是 就是 一下 起來 出來 過來 下來 時候 一樣 可以 因為 所以 如果 但是 然後".split())
    ex = [e for e in exclude if e]
    cand = [(w, c) for w, c in cnt.items() if c >= 3 and w not in stop and not re.fullmatch(r"(.)\1+", w)
            and w[0] not in EDGE_HEAD and w[-1] not in EDGE_TAIL
            and not any(e in w or w in e for e in ex)]
    cand.sort(key=lambda x: (-x[1] * (len(x[0]) ** 1.3), x[0]))
    out = []
    for w, c in cand:
        if any(w in o for o, _ in out) or any(o in w and cnt[o] <= c + 1 for o, _ in out):
            continue
        out.append((w, c))
        if len(out) >= top:
            break
    return ["%s×%d" % (w, c) for w, c in out]


def metrics_md(m):
    rows = ["| 指標 | 數值 | 說明 |", "|---|---|---|"]
    for k, v in m.items():
        note = METRIC_NOTES.get(k, "")
        if k.startswith("每千字") and not note:
            note = "每一千個中文字出現幾次"
        rows.append("| %s | %s | %s |" % (k, v, note))
    return (METRICS_HEAD + "\n<!-- 由工作台從範例文字統計，AI 寫稿時會參考這些數字。重新統計會覆蓋這一節。 -->\n"
            + "\n".join(rows) + "\n")


def put_metrics(text, m):
    sec = metrics_md(m)
    pat = re.compile(r"(?ms)^" + re.escape(METRICS_HEAD) + r".*?(?=^## |\Z)")
    if pat.search(text):
        return pat.sub(sec + "\n", text, count=1).rstrip() + "\n"
    anchor = re.search(r"(?m)^## 範例段落", text)
    if anchor:
        return text[:anchor.start()] + sec + "\n" + text[anchor.start():]
    return text.rstrip() + "\n\n" + sec


def put_samples(text, sample, limit=400, most=6):
    """把樣本開頭幾段放進「範例段落」（已經有內容就不動）。"""
    paras = [p for p in _paragraphs(_prose(sample)) if len(CJK.findall(p)) >= 10]
    pick, n = [], 0
    for p in paras:
        pick.append(p)
        n += len(p)
        if n >= limit or len(pick) >= most:
            break
    if not pick:
        return text
    block = "\n\n".join(pick)
    m = re.search(r"(?ms)^## 範例段落\s*\n(.*?)(?=^## |\Z)", text)
    if m:
        existing = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip()
        if existing:
            return text
        return text[:m.start(1)] + "<!-- 從分析樣本擷取的開頭幾段，可以換成你最滿意的段落。 -->\n" + block + "\n\n" + text[m.end(1):]
    return text.rstrip() + "\n\n## 範例段落\n" + block + "\n"


def parse_metrics(text):
    m = re.search(r"(?ms)^" + re.escape(METRICS_HEAD) + r"(.*?)(?=^## |\Z)", text or "")
    if not m:
        return {}
    out = {}
    _, rows = project.parse_md_table(m.group(1))
    for r in rows:
        if r.get("指標"):
            out[r["指標"]] = r.get("數值", "")
    return out


def _num(v):
    try:
        return float(str(v).rstrip("%"))
    except (TypeError, ValueError):
        return None


COMPARE_KEYS = ["平均句長", "短句比例", "長句比例", "平均段長", "單句成段", "對白比例", "每千字逗號",
                "每千字刪節號", "每千字破折號", "每千字驚嘆號", "每千字的", "每千字地", "每千字AI味信號"]


def compare(target, actual):
    """target、actual 都是指標 dict。回傳每列 {指標, 目標, 實際, 差距, 偏離}。"""
    rows = []
    for k in COMPARE_KEYS:
        t, a = _num(target.get(k)), _num(actual.get(k))
        if t is None or a is None:
            continue
        diff = a - t
        # 小數值時用較大的基準，避免 6% → 10% 這種小差距被當成「差很多」
        pct = str(target.get(k, "")).endswith("%")
        base = max(abs(t), 15.0 if pct else 5.0 if k.startswith("每千字") else 8.0)
        rel = abs(diff) / base
        rows.append({"指標": k, "目標": target.get(k), "實際": actual.get(k),
                     "差距": ("+" if diff > 0 else "") + ("%.1f" % diff).rstrip("0").rstrip("."),
                     "偏離": "明顯" if rel >= 0.6 else "稍有" if rel >= 0.3 else ""})
    return rows


def book_names(book_dir):
    """本書的人名、地名、勢力名與別名（分析高頻詞組時排除）。"""
    names = []
    for sub in ("設定/角色", "設定/勢力", "設定/世界觀"):
        for e in project.list_entries(book_dir, sub):
            names.append(e["name"])
            names += [str(a) for a in (e.get("aliases") or [])]
    _, rows = project.parse_md_table(project.read_text(os.path.join(book_dir, "設定", "名詞表.md"))) \
        if os.path.isfile(os.path.join(book_dir, "設定", "名詞表.md")) else ([], [])
    for r in rows:
        v = r.get("名詞") or r.get("名稱") or ""
        if v:
            names.append(v)
    return names


def book_sample(book_dir, a=None, b=None, folder="正文"):
    rows = project.scan_chapters(book_dir)
    key = "text_file" if folder == "正文" else "candidate_file"
    texts = []
    for r in rows:
        if r[key] and (a is None or r["no"] >= a) and (b is None or r["no"] <= b):
            texts.append(project.read_text(os.path.join(book_dir, r[key])))
    return "\n\n".join(texts)


def style_deviation_findings(book_dir, text):
    """給「檢查用語與 AI 味」用：本章和本書文風指標差很多時提醒。"""
    sp = os.path.join(book_dir, "設定", "文風.md")
    if not os.path.isfile(sp):
        return []
    target = parse_metrics(project.read_text(sp))
    if not target:
        return []
    try:
        actual = analyze(text, exclude=book_names(book_dir))
    except SharedError:
        return []
    out = []
    for r in compare(target, actual):
        if r["偏離"] == "明顯" and r["指標"] != "每千字AI味信號":
            out.append({"等級": "提醒", "類型": "文風偏差", "行": 0,
                        "片段": "%s：本章 %s，文風設定 %s" % (r["指標"], r["實際"], r["目標"]),
                        "建議": "和 設定/文風.md 的文字指標差很多；如果是刻意的（例如動作戲句子變短）可以忽略"})
    return out


# ---------------------------------------------------------------------------
# 章節結構
# ---------------------------------------------------------------------------
def _structure_info(path, origin):
    text = project.read_text(path)
    fm, _ = project.split_frontmatter(text)
    name = os.path.splitext(os.path.basename(path))[0]
    return {"name": name, "origin": origin, "scope": str(fm.get("適用") or ""), "summary": _summary(text),
            "default": str(fm.get("預設") or "") in ("是", "true", "True", "yes")}


def _summary(text):
    m = re.search(r"(?m)^>\s*(.+)$", project.split_frontmatter(text)[1])
    return m.group(1).strip()[:80] if m else ""


def list_structures(library):
    out = []
    if os.path.isdir(PRESET_DIR):
        for f in sorted(os.listdir(PRESET_DIR)):
            if f.endswith(".md"):
                out.append(dict(_structure_info(os.path.join(PRESET_DIR, f), "preset"), file="preset:" + f))
    d = os.path.join(shared_dir(library), "結構")
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".md"):
                out.append(dict(_structure_info(os.path.join(d, f), "mine"), file="結構/" + f))
    return out


def structure_path(library, name, origin):
    name = _name_ok(name)
    if origin == "preset":
        p = os.path.join(PRESET_DIR, name + ".md")
    else:
        p = os.path.join(shared_dir(library), "結構", name + ".md")
    if not os.path.isfile(p):
        raise SharedError("找不到章節結構「%s」" % name)
    return p


def copy_preset(library, name, new_name=None):
    src = structure_path(library, name, "preset")
    new_name = _name_ok(new_name or name)
    d = os.path.join(shared_dir(library, create=True), "結構")
    dst = os.path.join(d, new_name + ".md")
    if os.path.exists(dst):
        raise SharedError("「我的結構」裡已經有「%s」了" % new_name)
    text = set_fm(project.read_text(src), "名稱", new_name)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return {"name": new_name}


def new_structure(library, name):
    name = _name_ok(name)
    d = os.path.join(shared_dir(library, create=True), "結構")
    p = os.path.join(d, name + ".md")
    if os.path.exists(p):
        raise SharedError("已經有叫「%s」的結構了" % name)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(STRUCTURE_TEMPLATE.replace("{name}", name))
    return {"name": name}


STRUCTURE_TEMPLATE = """---
類型: 章節結構
名稱: {name}
適用: 單章
---

# {name}

> 一句話說明這個結構適合什麼樣的章節。

## 節拍
| 節拍 | 篇幅 | 這一段要做到的事 |
|---|---|---|
| 開場 | 15% | |
| 推進 | 35% | |
| 轉折 | 30% | |
| 收尾 | 20% | 章末停在哪裡 |

## 適合
-

## 注意
-
"""


# 書裡的結構：設定/章節結構/<名稱>.md，frontmatter「預設: 是」的是全書預設；章綱 frontmatter「結構: 名稱」可單章指定
BOOK_STRUCT_DIR = os.path.join("設定", "章節結構")


def book_structures(book_dir):
    d = os.path.join(book_dir, BOOK_STRUCT_DIR)
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".md"):
                info = _structure_info(os.path.join(d, f), "book")
                info["file"] = "設定/章節結構/" + f
                out.append(info)
    return out


def apply_structure(library, name, origin, book_dir, make_default=False):
    src = structure_path(library, name, origin)
    d = os.path.join(book_dir, BOOK_STRUCT_DIR)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, name + ".md")
    _backup(book_dir, dst, "章節結構")
    text = set_fm(set_fm(project.read_text(src), "預設", None), "名稱", None)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    if make_default or not any(s["default"] for s in book_structures(book_dir)):
        set_book_default(book_dir, name)
    return "設定/章節結構/%s.md" % name


def set_book_default(book_dir, name):
    found = False
    for s in book_structures(book_dir):
        p = os.path.join(book_dir, s["file"])
        text = project.read_text(p)
        new = set_fm(text, "預設", "是" if s["name"] == name else None)
        found = found or s["name"] == name
        if new != text:
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(new)
    if name and not found:
        raise SharedError("這本書沒有「%s」這個結構" % name)


def set_chapter_structure(book_dir, no, name):
    from . import context
    card_path, card = context.card_text(book_dir, no)
    if not card_path:
        raise SharedError("第%d章還沒有章綱" % no)
    if name and not os.path.isfile(os.path.join(book_dir, BOOK_STRUCT_DIR, _name_ok(name) + ".md")):
        raise SharedError("這本書沒有「%s」這個結構，請先從共用庫套用" % name)
    p = os.path.join(book_dir, card_path)
    text = set_fm(project.read_text(p), "結構", name or None)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def structure_for(book_dir, no=None):
    """回傳 (名稱, 內容, 來源說明)。章綱指定的優先，其次是全書預設。"""
    from . import context
    name = None
    if no:
        card_path, card = context.card_text(book_dir, no)
        if card:
            fm, _ = project.split_frontmatter(card)
            name = str(fm.get("結構") or "").strip() or None
    if name:
        p = os.path.join(book_dir, BOOK_STRUCT_DIR, name + ".md")
        if os.path.isfile(p):
            return name, clean_body(project.read_text(p)), "章綱指定"
    for s in book_structures(book_dir):
        if s["default"]:
            return s["name"], clean_body(project.read_text(os.path.join(book_dir, s["file"]))), "全書預設"
    return None, "", ""


CLAUDE_NOTE = ("【章節結構】寫章節或排章綱時：章綱 frontmatter 有「結構: 名稱」就讀 設定/章節結構/名稱.md；"
               "沒有指定就用 設定/章節結構/ 裡 frontmatter 標「預設: 是」的那一份；都沒有就不用。"
               "結構只是節拍參考，章綱的情節點與章末停點優先，篇幅比例不必精確。")


def claude_note(book_dir):
    note = CLAUDE_NOTE
    sd = shared_of_book(book_dir)
    p = os.path.join(sd, "作者偏好.md")
    if os.path.isfile(p) and _meaningful(project.read_text(p)):
        note += ("【共用作者偏好】所有書共用的作者偏好在 %s（用 Read 讀取）。寫作、改稿、去 AI 味、審查時，"
                 "和本書的 設定/作者偏好.md 一起遵守；兩者衝突時以本書為準。不要修改這個共用檔案。" % p)
    return note
