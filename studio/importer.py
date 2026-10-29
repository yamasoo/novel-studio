# -*- coding: utf-8 -*-
"""
匯入舊稿：TXT／Markdown／Word（.docx），或直接貼上文字。
全部在本機處理：判斷編碼、（選用）簡體轉台灣繁體、依章節標題拆章、整理段落，寫進正文或候選稿。
"""
import base64
import io
import os
import re
import shutil
import time
import zipfile
from xml.etree import ElementTree as ET

from . import lang as lang_mod, project

NUM = r"[0-9０-９一二三四五六七八九十百千零〇兩]+"
SEP = r"(?:\s*$|[\s:：、.．·\-—　]+(.*?)\s*$)"
CHAPTER_RE = re.compile(r"^\s*(?:#{1,4}\s*)?第\s*(" + NUM + r")\s*[章回節话話]" + SEP)
EN_RE = re.compile(r"^\s*(?:#{1,4}\s*)?chapter\s*(\d+|[IVXLC]+)" + SEP, re.I)   # 阿拉伯數字或羅馬數字（CHAPTER VI）
# 英文的「PART II」單獨一行：卷名，不當成章節，也不放進正文（下一行若是全大寫的卷名也一起略過）
EN_PART_RE = re.compile(r"^\s*(?:PART|Part)\s+([IVXLC]+|\d+)\s*$")
# 序章、尾聲這類特殊章：中文、英文（Prologue 等，不分大小寫）、日文（プロローグ 等）
SPECIAL_RE = re.compile(r"^\s*(?:#{1,4}\s*)?(序章|序幕|楔子|引子|序|尾聲|終章|後記|番外(?:\s*" + NUM + r")?"
                        r"|(?i:prologue|epilogue|interlude|afterword)"
                        r"|プロローグ|エピローグ|幕間|(?:閑話|番外編)(?:\s*" + NUM + r")?)" + SEP)
VOLUME_RE = re.compile(r"^\s*(?:#{1,4}\s*)?第\s*" + NUM + r"\s*[卷部集篇]\b.*$|^\s*(?:#{1,4}\s*)?第\s*" + NUM + r"\s*[卷部集篇](\s|$|[:：])")
MD_HEAD_RE = re.compile(r"^\s*#{1,3}\s+(.+?)\s*$")
MAX_TITLE = 30

_CN = {c: i for i, c in enumerate("零一二三四五六七八九")}
_CN.update({"〇": 0, "兩": 2})


class ImportError_(project.ProjectError):
    pass


_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s):
    s = s.upper()
    total = 0
    for i, ch in enumerate(s):
        v = _ROMAN.get(ch, 0)
        nxt = _ROMAN.get(s[i + 1], 0) if i + 1 < len(s) else 0
        total += -v if v < nxt else v
    return total


def en_num(s):
    return int(s) if s.isdigit() else roman_to_int(s)


def cn_to_int(s):
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if s.isdigit():
        return int(s)
    total, section, num = 0, 0, 0
    units = {"十": 10, "百": 100, "千": 1000}
    for ch in s:
        if ch in _CN:
            num = _CN[ch]
        elif ch in units:
            section += (num or 1) * units[ch]
            num = 0
        elif ch == "萬":
            total += (section + num) * 10000
            section, num = 0, 0
    return total + section + num


# ---------------------------------------------------------------------------
# 讀檔
# ---------------------------------------------------------------------------
def _simplified_set():
    try:
        import importlib.util
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "plugin", "skills", "novel-deslop", "scripts", "check_text.py")
        spec = importlib.util.spec_from_file_location("check_text_for_import", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.SIMPLIFIED_ONLY
    except Exception:
        return set("们这说时发来对会过还没么样经现进动后着里为国")


SIMP = None


def count_simplified(text):
    global SIMP
    if SIMP is None:
        SIMP = _simplified_set()
    return sum(1 for c in text if c in SIMP)


def decode(data):
    """回傳 (文字, 編碼名稱)。"""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", "replace"), "UTF-8"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "UTF-16"
    try:
        return data.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        pass
    cands = []
    for enc, label in (("cp950", "Big5（繁體）"), ("gb18030", "GB18030（簡體）")):
        try:
            t = data.decode(enc)
            cands.append((t, label))
        except UnicodeDecodeError:
            continue
    if len(cands) == 2:
        # 兩種都解得開時：看哪個結果比較像正常中文（常用字比例高、罕用區塊少）
        def score(t):
            common = len(re.findall(r"[的一是不了人我在有他這中大來上個們到說時你地出就那要以會可也著她沒過]", t))
            odd = len(re.findall(r"[㐀-䶿-]", t))
            return common - 5 * odd
        cands.sort(key=lambda x: -score(x[0]))
    if cands:
        return cands[0]
    return data.decode("utf-8", "replace"), "UTF-8（有無法辨識的字元）"


def read_docx(data):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        raise ImportError_("這個 .docx 檔案打不開，可能已損毀，或其實是舊版 .doc 格式（請在 Word 另存成 .docx）")
    root = ET.fromstring(xml)
    W = "{%s}" % ns["w"]
    paras = []
    for p in root.iter(W + "p"):
        buf = []
        for node in p.iter():
            if node.tag == W + "t":
                buf.append(node.text or "")
            elif node.tag == W + "tab":
                buf.append("　")
            elif node.tag in (W + "br", W + "cr"):
                buf.append("\n")
        paras.append("".join(buf))
    return "\n\n".join(paras)


def load_sources(payload):
    """payload: {"files": [{"name", "data"(base64)}], "text": "..."}。回傳 [(來源名稱, 文字, 編碼)]。"""
    out = []
    for f in payload.get("files") or []:
        name = f.get("name") or "未命名"
        try:
            data = base64.b64decode(f.get("data") or "")
        except Exception:
            raise ImportError_("檔案「%s」讀取失敗" % name)
        ext = os.path.splitext(name)[1].lower()
        if ext == ".docx":
            out.append((name, read_docx(data), "Word"))
        elif ext in (".txt", ".md", ".markdown", ".text", ""):
            text, enc = decode(data)
            out.append((name, text, enc))
        else:
            raise ImportError_("不支援「%s」的格式；可以匯入 .txt、.md、.docx" % name)
    if (payload.get("text") or "").strip():
        out.append(("貼上的文字", payload["text"], "—"))
    if not out:
        raise ImportError_("請選擇檔案或貼上文字")
    return out


def to_traditional(text):
    try:
        from opencc import OpenCC
    except ImportError:
        raise ImportError_("簡轉繁需要 OpenCC 套件。請關閉工作台後重新執行 start.bat（會自動安裝），"
                           "或手動執行：.venv\\Scripts\\pip install opencc-python-reimplemented")
    return OpenCC("s2twp").convert(text)


def has_opencc():
    try:
        import opencc  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# 拆章
# ---------------------------------------------------------------------------
def _natural_key(name):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", name)]


def _heading(line, mode):
    """判斷一行是不是章節標題。mode：chapter（第X章、Chapter N、楔子等）或 markdown（# 標題）。
    回傳 (標題上的章號或 None, 章名, 原文) 或 None。"""
    s = line.strip()
    if not s or len(s) > 60:
        return None
    if mode == "chapter":
        for rx, kind in ((CHAPTER_RE, "cn"), (EN_RE, "en"), (SPECIAL_RE, "sp")):
            m = rx.match(s)
            if not m:
                continue
            rest = (m.group(2) or "").strip("#　 ")
            if len(rest) > MAX_TITLE or re.search(r"[。！？!?]", rest[:-1] if rest else ""):
                return None  # 後面接的是句子，不是章名
            if kind == "cn":
                return cn_to_int(m.group(1)), rest, s
            if kind == "en":
                return en_num(m.group(1)), rest, s
            joiner = " " if re.match(r"[A-Za-z]", m.group(1)) else "　"      # 英文的 Prologue 後面接半形空白
            return None, (m.group(1) + (joiner + rest if rest else ""))[:MAX_TITLE], s
        return None
    m = MD_HEAD_RE.match(s)
    if m:
        h = _heading(m.group(1), "chapter")
        return h if h else (None, m.group(1)[:MAX_TITLE], s)
    return None


def _title_key(t):
    """比對章名用：去掉 #、書名號、引號、標點與空白。"""
    from . import search   # 繁簡逐字對照：「風雪夜歸」和「风雪夜归」算同一個章名
    return search.norm(re.sub(r"[#《》〈〉「」『』\"'“”‘’()（）\[\]【】:：、,，.．·\-—\s　]", "", t or ""))


def _merge_duplicate_headings(chunks):
    """同一章的標題連寫兩次（例如「第 7 章　夜襲」下一行又有「# 第七章 夜襲」）：
    章號相同、中間只有空行、章名相同或其中一邊沒寫，就當成同一章。
    做法參考 oh-story-claudecode（MIT）的 drop_adjacent_duplicate_headings，放寬成寫法不同也算。"""
    out, merged = [], 0
    for c in chunks:
        p = out[-1] if out else None
        if (p and p["num"] is not None and p["num"] == c["num"]
                and len(p["lines"]) <= 3 and not any(x.strip() for x in p["lines"])
                and (not _title_key(p["title"]) or not _title_key(c["title"]) or _title_key(p["title"]) == _title_key(c["title"]))):
            p["title"] = p["title"] or c["title"]
            p["lines"] = c["lines"]
            merged += 1
            continue
        out.append(c)
    return out, merged


def _drop_leading_toc(chunks):
    """書開頭的目錄：一串間距很近的章名，後面正文又照同樣順序出現 → 丟掉開頭那串。
    做法參考 oh-story-claudecode（MIT）的 drop_leading_toc。回傳 (章節, 丟掉幾條)。"""
    if len(chunks) < 6:
        return chunks, 0
    for k in range(min(len(chunks) // 2, 500), 2, -1):
        pre = chunks[:k]
        if pre[0]["line"] > 200:
            continue
        gaps = sorted(pre[i]["line"] - pre[i - 1]["line"] for i in range(1, k))
        if gaps[len(gaps) // 2] > 3:
            continue
        sig = [(x["num"], _title_key(x["title"])) for x in pre[:min(8, k)]]
        for j in range(k, len(chunks) - len(sig) + 1):
            if [(x["num"], _title_key(x["title"])) for x in chunks[j:j + len(sig)]] == sig and chunks[j]["line"] - pre[-1]["line"] > 3:
                return chunks[j:], j
    return chunks, 0


def _split(lines, mode, stats=None):
    chunks, cur, preface = [], None, []
    want_title, skip_part_title = False, False   # want_title：英文「CHAPTER VI」後面下一行是章名；skip_part_title：PART 後面的卷名
    for i, ln in enumerate(lines):
        s = ln.strip()
        if skip_part_title and s:
            skip_part_title = False
            if len(s) <= 60 and s == s.upper() and not re.search(r"[.!?]$", s):
                continue   # 「PART II」下一行的卷名（THE SEA COOK）
        if len(s) <= 40 and VOLUME_RE.match(s):
            continue  # 卷名：不當成章節，也不放進正文
        if EN_PART_RE.match(s):
            skip_part_title = True
            continue
        if want_title and s:
            want_title = False
            if cur is not None and not cur["title"] and len(s) <= 100 and not re.search(r"[.!?,;:]$", s):
                cur["title"] = s[:60]     # 「CHAPTER VI」的下一行「THE CAPTAIN'S PAPERS」是章名（英文章名較長，最多取 60 字）
                continue
        h = _heading(ln, mode)
        if h:
            cur = {"num": h[0], "title": h[1], "heading": h[2], "lines": [], "line": i + 1}
            chunks.append(cur)
            want_title = bool(EN_RE.match(s)) and not h[1]
        elif cur is None:
            preface.append(ln)
        else:
            cur["lines"].append(ln)
    chunks, toc = _drop_leading_toc(chunks)
    chunks, merged = _merge_duplicate_headings(chunks)
    if stats is not None:
        stats["toc"] = stats.get("toc", 0) + toc
        stats["merged"] = stats.get("merged", 0) + merged
    for c in chunks:
        c["body"] = "\n".join(c.pop("lines"))
        c.pop("line", None)
    return "\n".join(preface).strip(), chunks


def split_text(text, mode="auto", stats=None):
    """回傳 (前言, [{"num": 標題上的章號或 None, "title", "heading", "body"}])。
    auto：先找「第X章」這類標題，找不到再用 Markdown 的 # 標題。stats 會記下合併與丟掉目錄的數量。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    lines = text.split("\n")
    if mode in ("auto", "chapter"):
        pre, chunks = _split(lines, "chapter", stats)
        if chunks or mode == "chapter":
            return pre, chunks
    return _split(lines, "markdown", stats)


def normalize(body, lang="zh-TW"):
    """整理段落：一段一行、段落之間空一行，去掉段首空白。場景分隔線：中文統一成「＊＊＊」，
    英文統一成「* * *」，日文保留作者原本的寫法（◇、＊、——…各家習慣不同）。"""
    body = body.replace("\t", "").strip("\n")
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    has_blank = re.search(r"\n[ \t　]*\n", body) is not None
    lines = [ln.strip(" 　 ") for ln in body.split("\n")]
    if has_blank:
        paras, buf = [], []
        for ln in lines:
            if ln:
                buf.append(ln)
            elif buf:
                paras.append(buf)
                buf = []
        if buf:
            paras.append(buf)
        # 段內換行：中文直接接起來
        paras = ["".join(p) if all(re.search(r"[一-鿿，。！？」』…—]$", x) for x in p[:-1]) else " ".join(p)
                 for p in paras]
        # 若「空行分段」其實是每一行都隔一個空行，結果一樣；若段落很長且行很多，保留原樣
    else:
        paras = [ln for ln in lines if ln]
    # 場景分隔線（***、＊＊＊、——— 等）：中文統一成「＊＊＊」、英文統一成「* * *」，日文不動
    sep = {"en": "* * *", "ja": None}.get(lang, "＊＊＊")
    if sep:
        paras = [sep if re.fullmatch(r"[-*_=＝—~～·•＊※◆◇○●\s]{3,}", p) else p for p in paras]
    return "\n\n".join(paras)


def count_text(text, lang="zh-TW"):
    """字數：與章節列表同一個算法（project.count_chars）——中日文算字（漢字與假名）、英文算詞。
    lang 保留只為相容舊呼叫；預覽和匯入後的字數才會一致。"""
    return project.count_chars(text or "")


def plan(payload, opts):
    """依選項拆章，回傳預覽資料（不寫檔）。"""
    mode = opts.get("mode") or "auto"
    # 只有繁體中文稿才做簡體偵測與簡轉繁；日文的新字體（伝、戦、竜…）在簡體字表裡，會被誤判
    zh = (opts.get("lang") or "zh-TW") == "zh-TW"
    lang = opts.get("lang") or "zh-TW"
    convert = bool(opts.get("convert")) and zh
    sources = load_sources(payload)
    sources.sort(key=lambda s: (s[0] == "貼上的文字", _natural_key(s[0])))
    infos, chapters, preface_all = [], [], []
    simp_total = 0
    stats = {}
    for name, text, enc in sources:
        simp = count_simplified(text) if zh else 0
        simp_total += simp
        if convert:
            text = to_traditional(text)
        pre, chunks = split_text(text, mode, stats)
        if not chunks:
            # 整個檔案當成一章（一個檔案一章的情況），章號和章名從檔名猜
            stem = os.path.splitext(name)[0]
            m = re.match(r"^(\d+)[\s._\-、]*(.*)$", stem)
            h = _heading(stem, "chapter") or ((int(m.group(1)), (m.group(2) or stem)[:MAX_TITLE], stem) if m
                                              else (None, stem[:MAX_TITLE], stem))
            if len(sources) == 1 and name == "貼上的文字":
                h = (None, "", "")
            chunks = [{"num": h[0], "title": h[1], "heading": "", "body": text}]
            pre = ""
        if pre and count_text(pre, lang) >= 1:
            preface_all.append((name, pre))
        infos.append({"name": name, "encoding": enc, "simplified": simp, "chapters": len(chunks)})
        chapters += chunks
    if opts.get("preface_as_chapter") and preface_all:
        body = "\n\n".join(p for _, p in preface_all)
        chapters.insert(0, {"num": None, "title": opts.get("preface_title") or "序章", "heading": "", "body": body})
        preface_all = []
    # 編號：標題上的章號遞增且不重複就沿用，否則依順序重新編號
    start = int(opts.get("start") or 1)
    nums = [c["num"] for c in chapters]
    use_titles = opts.get("numbering", "auto") != "sequential" and all(n is not None for n in nums) \
        and all(b > a for a, b in zip(nums, nums[1:]))
    if opts.get("numbering") == "titles" and not use_titles:
        raise ImportError_("標題上的章號不連續、重複或有缺（例如有楔子、番外），請改用「依順序重新編號」")
    for i, c in enumerate(chapters):
        c["no"] = c["num"] if use_titles else start + i
        c["text"] = normalize(c["body"], lang)
        c["chars"] = count_text(c["text"], lang)
    chapters = [c for c in chapters if c["chars"] > 0 or c["title"]]
    warnings = []
    if stats.get("merged"):
        warnings.append("有 %d 章的章名連寫了兩次（寫法不同），已經合併成同一章。" % stats["merged"])
    if stats.get("toc"):
        warnings.append("開頭有一份目錄（%d 條章名），已經略過，不當成章節。" % stats["toc"])
    uz = lang_mod.unit_zh(lang)        # 英文書算詞：訊息寫「詞」，其他寫「字」
    _flag_chapters(chapters, convert, warnings, zh, uz)
    if zh and simp_total and not convert:
        warnings.append("偵測到約 %d 個簡體字。可以勾選「轉成台灣繁體」再預覽。" % simp_total)
    if preface_all:
        n = sum(count_text(p, lang) for _, p in preface_all)
        warnings.append("第一個章節標題之前有 %d %s（例如書名、簡介、楔子），預設不會匯入；需要的話勾選「把開頭的文字當成一章」。" % (n, uz))
    return {"sources": infos, "chapters": chapters, "warnings": warnings, "numbered_by_title": use_titles,
            "preface": [{"name": n, "chars": count_text(p, lang), "preview": p.strip()[:80]} for n, p in preface_all]}


def _nos(cs):
    nos = [c["no"] for c in cs]
    s = "、".join("第%d章" % n for n in nos[:12])
    return s + ("……等 %d 章" % len(nos) if len(nos) > 12 else "")


def _flag_chapters(chapters, convert, warnings, zh=True, unit="字"):
    """逐章標出可疑的地方（給預覽表上色），並彙整成提醒。"""
    sizes = sorted(c["chars"] for c in chapters if c["chars"] > 0)
    median = sizes[len(sizes) // 2] if sizes else 0
    prev = None
    for c in chapters:
        f = []
        if c["chars"] < 50:
            f.append("空章")
        elif median >= 500 and c["chars"] < median * 0.2:
            f.append("過短")
        if c["chars"] > 20000 or (median >= 500 and c["chars"] > median * 3):
            f.append("過長")
        n = c.get("num")
        if n is not None and prev is not None:
            if n == prev:
                f.append("重複章號")
            elif n > prev + 1:
                f.append("跳號（缺第%s章）" % ("%d" % (prev + 1) if n == prev + 2 else "%d～%d" % (prev + 1, n - 1)))
            elif n < prev:
                f.append("章號倒退")
        if n is not None:
            prev = n
        simp = count_simplified(c["text"]) if zh else 0
        if simp >= 5:
            f.append(("轉繁後仍有簡體字 %d" if convert else "簡體字 %d") % simp)
        c["flags"] = f
    groups = [("空章", "內容不到 50 %s（可能是目錄或標題誤判）" % unit), ("過短", "比一般章節短很多"),
              ("過長", "比一般章節長很多（可能有章節標題沒被認出來）"), ("重複章號", "章號重複"),
              ("跳號", "章號不連續"), ("章號倒退", "章號比上一章小"), ("簡體字", "含簡體字"), ("轉繁後", "轉繁後仍有簡體字")]
    for key, text in groups:
        cs = [c for c in chapters if any(x.startswith(key) for x in c["flags"])]
        if cs:
            warnings.append("%s：%s。" % (text, _nos(cs)))


def preview(payload, opts):
    r = plan(payload, opts)
    r["chapters"] = [{"no": c["no"], "title": c["title"], "heading": c["heading"], "chars": c["chars"],
                      "flags": c.get("flags") or [], "head": re.sub(r"\s+", " ", c["text"][:60])} for c in r["chapters"]]
    return r


def _fname_title(t):
    return project.safe_filename(t, MAX_TITLE)


def commit(book_dir, payload, opts, checker=None):
    """寫入書目錄。opts: target（"正文"|"候選"）、conflict（"skip"|"overwrite"）、fix_punct。"""
    r = plan(payload, opts)
    target = "候選" if opts.get("target") == "候選" else "正文"
    tdir = os.path.join(book_dir, target)
    os.makedirs(tdir, exist_ok=True)
    existing = project._scan_dir(tdir)
    written, skipped, replaced = [], [], []
    bak = os.path.join(book_dir, ".studio", "備份")
    stamp = int(time.time())
    for c in r["chapters"]:
        no = c["no"]
        title = c["title"]
        heading = "# 第%d章%s" % (no, (" " + title) if title else "")
        text = heading + "\n\n" + c["text"].strip() + "\n"
        if checker and opts.get("fix_punct", True):
            text, _ = checker.fix_punct(text)
        if no in existing:
            if opts.get("conflict") != "overwrite":
                skipped.append(no)
                continue
            os.makedirs(bak, exist_ok=True)
            old = os.path.join(tdir, existing[no])
            shutil.copy2(old, os.path.join(bak, "匯入前_%s_%d_%s" % (target, stamp, existing[no])))
            os.remove(old)
            replaced.append(no)
        name = "第%03d章_%s.md" % (no, _fname_title(title))
        with open(os.path.join(tdir, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        written.append({"no": no, "file": target + "/" + name, "chars": c["chars"]})
    return {"target": target, "written": written, "skipped": skipped, "replaced": replaced,
            "chars": sum(w["chars"] for w in written)}


def set_import_lang(book_dir, value):
    """匯入建立新書時，把「稿子的語言」記成這本書的寫作語言（之後提示詞、CLAUDE.md 都依此）。"""
    if value:
        from . import lang as lang_mod
        lang_mod.set_book_lang(book_dir, value)


def make_claude_md(book_dir, plugin_dir, title):
    """匯入建立新書時，用 novel-setup 的範本產生 CLAUDE.md（基本設定先標「待補」）。"""
    p = os.path.join(book_dir, "CLAUDE.md")
    if os.path.exists(p):
        return
    from . import context, lang as lang_mod
    tpl = os.path.join(context.lang_plugin(plugin_dir, lang_mod.book_lang(book_dir)), "skills", "novel-setup", "references", "claude-md-template.md")
    if not os.path.isfile(tpl):
        tpl = os.path.join(plugin_dir, "skills", "novel-setup", "references", "claude-md-template.md")
    text = ""
    if os.path.isfile(tpl):
        raw = project.read_text(tpl)
        m = re.search(r"---(?:範本開始|TEMPLATE START|テンプレート開始)---\s*\n(.*?)\n---(?:範本結束|TEMPLATE END|テンプレート終了)---", raw, re.S)
        text = m.group(1) if m else ""
    if not text:
        text = "# 《{書名}》寫作專案\n\n{一句話鉤子}\n"
    text = re.sub(r"(?ms)^## (?:本書特別規則|Special rules for this book|この本の特別ルール).*?(?=^## |\Z)", "", text)
    note = {"en": "> Created by importing an old manuscript. The basics are not filled in yet; use the new-book interview or edit this file.",
            "ja": "> 旧稿の取り込みで作成。基本設定はまだ未記入です。開書インタビューを使うか、このファイルを直接編集してください。"}.get(
        lang_mod.book_lang(book_dir), "> 由「匯入舊稿」建立。基本設定還沒填，可以用「開書訪談」或直接編輯這份檔案補齊。")
    for k in ("{書名}", "{Title}"):
        text = text.replace(k, title)
    for k in ("{一句話鉤子}", "{One-line hook}", "{一文の引き}"):
        text = text.replace(k, note)
    todo = {"en": "(to fill in)", "ja": "（未記入）"}.get(lang_mod.book_lang(book_dir), "（待補）")
    text = re.sub(r"\{[^{}\n]*\}", todo, text)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.strip() + "\n")
