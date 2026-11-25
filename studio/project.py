# -*- coding: utf-8 -*-
"""讀取小說專案資料夾：書架、章節、設定、追蹤表格、警示。"""
import os
import re
import time
import json
import threading

import yaml

from . import enums
from . import fmkeys, layout, sections
from . import ids

CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff]")
# 章號：v3 的 ch-0001（也收 ch-001、ch1、CH-1），以及舊的「第001章」（技能或手寫的舊檔名照樣認得）
CH_NUM = re.compile(r"^ch-?0*(\d+)|第0*(\d+)章", re.I)

# 書目錄內允許瀏覽的資料夾
BROWSABLE = [layout.BIBLE, layout.OUTLINE, layout.MANUSCRIPT, layout.TRACKING, layout.CANDIDATES, layout.SAMPLES, layout.TEMPLATES]


class ProjectError(Exception):
    pass


# ---------------------------------------------------------------------------
# 基本工具
# ---------------------------------------------------------------------------
def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_atomic(path, text, newline="\n"):
    """寫檔：先寫同目錄的暫存檔，再 os.replace 換上去。

    寫到一半失敗（磁碟滿、被同步程式鎖住、行程被砍）時原檔維持舊內容，
    不會留下半個檔。暫存檔名帶 pid：上次中斷留下的 .tmp 不會擋住這次，
    兩個流程也不會互踩同一個暫存檔。呼叫端原本在處理的 OSError 照樣往上拋。
    """
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    if path.endswith(".md"):
        try:
            from . import trackjson
            trackjson.mirror(path, text)        # 五張追蹤表：旁邊的 JSON 正本跟著更新（其他檔不處理）
        except Exception:                       # JSON 沒寫成也沒關係：下次讀取發現對不上，會以 .md 為準
            pass
    return path


def _read_maybe(path):
    """讀檔；檔案剛好被搬走或刪掉時（例如自動流程正在把候選稿移到正文）回傳 None。"""
    try:
        return read_text(path)
    except (FileNotFoundError, PermissionError):
        return None


# 「欄名：」被標點轉換寫成全形冒號的行（舊版把 frontmatter 也送進 textguard，見 normalize_frontmatter）
FM_COLON = re.compile(r"^([^\s:：][^：:]{0,40})：(\s|$)")


def _repair_fm_line(line):
    return FM_COLON.sub(r"\1:\2", line)


def normalize_frontmatter(text):
    """把 frontmatter 裡寫成全形冒號的「欄名：」改回半形；正文一個字都不動。"""
    if not text.startswith("---"):
        return text
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fixed = [_repair_fm_line(x) for x in lines[1:i]]
            if fixed == lines[1:i]:
                return text
            return "\n".join([lines[0]] + fixed + lines[i:])
    return text


def split_frontmatter(text):
    """回傳 (dict, body)，dict 的鍵一律英文（type、status、name…，見 fmkeys）。frontmatter 格式錯誤時回傳空 dict。"""
    from . import fmkeys
    fm, body = split_frontmatter_raw(text)
    return fmkeys.to_en(fm), body


def split_frontmatter_raw(text):
    """回傳 (dict, body)，鍵照檔案裡的寫法。frontmatter 格式錯誤時回傳空 dict。

    欄名寫成全形冒號的舊檔（標點轉換吃進 frontmatter）先在這裡修好再解析，
    不然名稱、定位、狀態會整份讀不到；寫回檔案由 normalize_frontmatter 負責。
    """
    if text.startswith("---"):
        lines = text.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                raw = "\n".join(lines[1:i])
                body = "\n".join(lines[i + 1:])
                fixed = "\n".join(_repair_fm_line(x) for x in lines[1:i])
                for cand in (raw, fixed):
                    try:
                        data = yaml.safe_load(cand) or {}
                    except yaml.YAMLError:
                        data = {}
                    if isinstance(data, dict) and data:
                        return data, body
                return {}, body
    return {}, text


def count_chars(text):
    _, body = split_frontmatter(text)
    body = re.sub(r"^#.*$", "", body, flags=re.M)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    cjk = len(CJK.findall(body))
    # 英文等以字母為主的稿子：改算詞數（中文為主時結果與原本相同）
    words = len(re.findall(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", body))
    return words if words > cjk else cjk


def safe_filename(name, maxlen=40):
    """標題、名稱 → 檔名用的字串。只去掉 Windows 不能用的字元（\\ / : * ? " < > |）和換行，
    保留空白（連續空白縮成一個、頭尾去掉），太長就截斷，空字串回傳「未命名」。
    匯入、整理名詞表、從正文建立設定都用這一個，檔名規則才會一致。"""
    s = re.sub(r'[\\/:*?"<>|]+', "", str(name or ""))
    s = re.sub(r"\s+", " ", s).strip()                 # 換行、tab、全形空白一律變成一個半形空白
    if len(s) > maxlen:
        cut = s[:maxlen]
        if s[maxlen] != " " and " " in cut and cut.rfind(" ") >= maxlen * 0.6:
            cut = cut[:cut.rfind(" ")]                  # 英文標題：盡量斷在單字之間，不把單字切一半
        s = cut
    s = s.strip().rstrip(".")                           # 截斷後再清一次；Windows 檔名不能以「.」或空白結尾
    return s.strip() or "未命名"


def chapter_no(name):
    m = CH_NUM.search(os.path.basename(name))
    return int(m.group(1) or m.group(2)) if m else None


_DUE = re.compile(r"^\s*第\s*(\d+)\s*(?:章)?(?:\s*[～~\-–至到]\s*第?\s*(\d+))?\s*章(.*)$", re.S)


def due_chapter(s):
    """伏筆「預計回收」→ 章號。只有寫成「第N章」（可接「回收」「前後」或範圍）才算；
    「第N章起推進」「第N章呼應」「第二幕」「未排定」都不算回收章，不判逾期。"""
    m = _DUE.match(str(s or ""))
    if not m:
        return None
    rest = m.group(3).strip()
    if rest.startswith(("起", "開始", "呼應", "推進", "再", "埋", "提及")):
        return None
    n = int(m.group(2) or m.group(1))
    return n + 2 if rest.startswith(("前後", "左右")) else n


def chapter_title_from_filename(name):
    """舊檔名（第001章_章名.md）裡的章名；v3 的 ch-0001.md 沒有章名，回傳空字串。"""
    stem = os.path.splitext(os.path.basename(name))[0]
    if stem.lower().startswith("ch"):
        return ""
    parts = stem.split("_", 1)
    return parts[1] if len(parts) == 2 else ""


_HEADING = re.compile(r"^#\s+(.+?)\s*$", re.M)
_HEADING_NO = re.compile(r"^(?:第\s*0*\d+\s*[章話回]|chapter\s+\d+)\s*[:：.\-–—、]?\s*", re.I)


def heading_title(text):
    """正文第一個一級標題裡的章名：「# 第1章 退婚當天」→「退婚當天」；沒有章號就用整個標題。"""
    _, body = split_frontmatter(text or "")
    m = _HEADING.search(body)
    if not m:
        return ""
    return _HEADING_NO.sub("", m.group(1).strip(), count=1).strip()


def chapter_title(name, text=None):
    """正文、候選稿的章名：舊檔名裡的章名 → 正文的一級標題。（有章綱時，章綱的「章名」優先，由呼叫端決定）"""
    return chapter_title_from_filename(name) or (heading_title(text) if text is not None else "")


def safe_path(book_dir, rel):
    """把相對路徑解析到書目錄內，防止跳出。"""
    if rel is None:
        raise ProjectError("缺少路徑")
    rel = rel.replace("\\", "/").lstrip("/")
    full = os.path.normpath(os.path.join(book_dir, rel))
    root = os.path.normpath(book_dir)
    if os.path.commonpath([full, root]) != root:
        raise ProjectError("路徑超出書目錄")
    return full


def rel_of(book_dir, full):
    return os.path.relpath(full, book_dir).replace("\\", "/")


# ---------------------------------------------------------------------------
# 書架
# ---------------------------------------------------------------------------
def is_book(path):
    return os.path.isfile(os.path.join(path, "CLAUDE.md"))


_CACHE_LOCK = threading.Lock()
_INFO_CACHE = None
_CACHE_VERSION = 2          # 書架統計的算法一改就 +1，舊快取自動失效
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")


def _cache_path():
    return os.path.join(_CACHE_DIR, "books.json")


def _cache_get():
    """書架統計的磁碟快取（只用 stat 指紋失效，重啟後第一次也能快）。"""
    global _INFO_CACHE
    if _INFO_CACHE is None:
        try:
            with open(_cache_path(), encoding="utf-8") as f:
                _INFO_CACHE = json.load(f)
        except (OSError, ValueError):
            _INFO_CACHE = {}
    return _INFO_CACHE


def _cache_save():
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        p = _cache_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(_INFO_CACHE, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, p)
    except OSError:
        pass


def _scan_fingerprint(book_dir):
    """只用 stat 的版本指紋：檔案數、總大小、最新 mtime（不讀內容）。

    書的內容一改，mtime 或大小就會變；夠用來判斷快取能不能重用。
    """
    count = total = 0
    newest = 0.0
    for sub in (layout.MANUSCRIPT, layout.OUTLINE, layout.TRACKING, layout.BIBLE, layout.CANDIDATES):
        for root, _dirs, files in os.walk(os.path.join(book_dir, sub)):
            for f in files:
                if not f.endswith(".md"):
                    continue
                try:
                    st = os.stat(os.path.join(root, f))
                except OSError:
                    continue
                count += 1
                total += st.st_size
                if st.st_mtime > newest:
                    newest = st.st_mtime
    return [count, total, newest]


def list_books(library):
    books = []
    if not library or not os.path.isdir(library):
        return books
    from . import lang as lang_mod
    with _CACHE_LOCK:
        cache = _cache_get()
        dirty = False
        for name in sorted(os.listdir(library)):
            d = os.path.join(library, name)
            if not os.path.isdir(d) or name.startswith(".") or name == layout.SHARED:
                continue
            info = {"id": name, "name": name, "is_book": is_book(d)}
            from . import migrate
            if info["is_book"] and migrate.needs_migration(d):
                info["needs_migration"] = True      # 舊格式（v2）：要先轉換才能開，不算統計
                books.append(info)
                continue
            if info["is_book"]:
                fp = _scan_fingerprint(d)
                hit = cache.get(d)
                if hit and hit.get("v") == _CACHE_VERSION and hit.get("fp") == fp:
                    info.update(hit.get("info") or {})
                else:
                    chs = scan_chapters(d)
                    written = [c for c in chs if c["text_file"]]
                    stats = {
                        "chapters_written": len(written),
                        "chapters_planned": len(chs),
                        "chars": sum(c["chars"] for c in written),
                        "hook": read_hook(d),
                        "pending_candidates": sum(1 for c in chs if c["candidate_file"]),
                    }
                    info.update(stats)
                    cache[d] = {"v": _CACHE_VERSION, "fp": fp, "info": stats}
                    dirty = True
                info["updated"] = fp[2]          # 最新 mtime（跟 latest_mtime 同義）
                info["lang"] = lang_mod.book_lang(d)
                info["unit"] = lang_mod.count_unit(info["lang"])
            books.append(info)
        if dirty:
            _cache_save()
    books.sort(key=lambda b: (not b["is_book"], -(b.get("updated") or 0)))
    return books


def read_hook(book_dir):
    p = layout.path(book_dir, layout.STORY_CORE)
    if not os.path.isfile(p):
        return ""
    _, body = split_frontmatter(read_text(p))
    m = re.search(r"##\s*" + sections.head_rx("story-core", "hook") + r"\s*\n(.*?)(?=\n##|\Z)", body, re.S | re.I)
    if not m:
        return ""
    txt = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip()
    return txt.split("\n")[0][:80]


def latest_mtime(book_dir):
    newest = 0
    for sub in (layout.MANUSCRIPT, layout.OUTLINE, layout.TRACKING, layout.BIBLE, layout.CANDIDATES):
        d = os.path.join(book_dir, sub)
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(".md"):
                    try:
                        newest = max(newest, os.path.getmtime(os.path.join(root, f)))
                    except OSError:
                        pass
    return newest


def create_book(library, name):
    name = name.strip()
    if not name or re.search(r'[\\/:*?"<>|]', name):
        raise ProjectError("書名不能空白，也不能包含 \\ / : * ? \" < > |")
    d = os.path.join(library, name)
    if os.path.exists(d):
        raise ProjectError("已經有同名資料夾")
    os.makedirs(d)
    from . import bookmeta
    bookmeta.write(d)      # 書名、格式版本、建立日期；語言等作者選了再寫（沒寫時照舊看故事核心）
    return d


# ---------------------------------------------------------------------------
# 章節
# ---------------------------------------------------------------------------
def _scan_dir(d, pattern=".md"):
    out = {}
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):     # 同一章有好幾份時固定挑 ch-0003.md（排在 .v2 與舊檔名前面）
            if f.endswith(pattern):
                n = chapter_no(f)
                if n is not None:
                    out.setdefault(n, f)
    return out


def scan_chapters(book_dir):
    cards = _scan_dir(layout.path(book_dir, layout.CHAPTER_CARDS))
    texts = _scan_dir(layout.path(book_dir, layout.MANUSCRIPT))
    cands = _scan_dir(layout.path(book_dir, layout.CANDIDATES))
    sums = _scan_dir(layout.path(book_dir, layout.SUMMARIES))
    nums = sorted(set(cards) | set(texts) | set(cands))
    rows = []
    for n in nums:
        row = {"no": n, "title": "", "card_file": None, "card_status": None,
               "card_target": None, "text_file": None, "chars": 0,
               "candidate_file": None, "candidate_chars": 0,
               "summary_file": None, "func": ""}
        card_text = _read_maybe(layout.path(book_dir, layout.CHAPTER_CARDS, cards[n])) if n in cards else None
        if card_text is not None:
            p = layout.path(book_dir, layout.CHAPTER_CARDS, cards[n])
            fm, body = split_frontmatter(card_text)
            row["card_file"] = rel_of(book_dir, p)
            row["card_status"] = fmkeys.disp("status", fm.get("status"))
            row["card_target"] = fm.get("target_length")
            row["title"] = str(fm.get("title") or "")
            m = re.search(r"-\s*功能：([^\n<]*)", body)
            if m:
                row["func"] = m.group(1).strip()
        text = _read_maybe(layout.path(book_dir, layout.MANUSCRIPT, texts[n])) if n in texts else None
        if text is not None:
            p = layout.path(book_dir, layout.MANUSCRIPT, texts[n])
            row["text_file"] = rel_of(book_dir, p)
            row["chars"] = count_chars(text)
            row["title"] = row["title"] or chapter_title(texts[n], text)
        cand = _read_maybe(layout.path(book_dir, layout.CANDIDATES, cands[n])) if n in cands else None
        if cand is not None:
            p = layout.path(book_dir, layout.CANDIDATES, cands[n])
            row["candidate_file"] = rel_of(book_dir, p)
            row["candidate_chars"] = count_chars(cand)
            row["title"] = row["title"] or chapter_title(cands[n], cand)
        if n in sums:
            row["summary_file"] = rel_of(book_dir, layout.path(book_dir, layout.SUMMARIES, sums[n]))
        if row["card_file"] or row["text_file"] or row["candidate_file"]:
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Markdown 表格（伏筆、時間線、名詞表、作者偏好）
# ---------------------------------------------------------------------------
def parse_md_table(text):
    """抓出檔案中第一個 Markdown 表格，回傳 (headers, rows[dict])。"""
    _, body = split_frontmatter(text)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    lines = [l.strip() for l in body.split("\n")]
    headers, rows = None, []
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1]):
            headers = [c.strip() for c in l.strip("|").split("|")]
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                if any(cells):
                    cells += [""] * (len(headers) - len(cells))
                    rows.append(dict(zip(headers, cells)))
                i += 1
            break
        i += 1
    return headers or [], rows


def read_table(book_dir, rel):
    from . import trackjson
    t = trackjson.read(book_dir, rel)       # 五張正本：JSON 是最新的就讀 JSON（.md 被改過就照舊解析 .md）
    if t is not None:
        return t
    p = os.path.join(book_dir, rel)
    if not os.path.isfile(p):
        return {"exists": False, "headers": [], "rows": []}
    h, r = parse_md_table(read_text(p))
    return {"exists": True, "headers": h, "rows": r, "file": rel}


# ---------------------------------------------------------------------------
# 設定集
# ---------------------------------------------------------------------------
WORLD_CATS = ["力量體系", "地理與氣候", "歷史與年表", "社會與政治", "經濟與物資", "宗教信仰",
              "文化與風俗", "科技原理", "載具與兵器", "生態與資源", "其他"]
# 角色的「定位」固定詞（與 enums 同一份，介面與批次修改都從這裡取）
CHAR_ROLES = [zh for zh, _ in enums.TABLES["role"]]
DEFAULT_ROLE = "supporting"
REV_SECTION = "從正文反推（未併入，請核對）"


def set_frontmatter_field(text, key, value):
    """只改 frontmatter 裡 key 那一行；沒有就插在 type 後面；沒有 frontmatter 就補一段。其他內容不動。

    key 是英文鍵（中文鍵也收）。檔案裡已有那一行就照原本的寫法（中文或英文）改，新加的行由 fmkeys 決定寫法。"""
    from . import fmkeys
    key = fmkeys.en(key)
    value = fmkeys.write_value(key, value)
    text = normalize_frontmatter(text)
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return "---\n%s: %s\n---\n\n%s" % (fmkeys.write_key(key), value, text)
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ProjectError("frontmatter 格式錯誤，無法寫入分類")
    for i in range(1, end):
        for k in fmkeys.file_keys(key):
            if lines[i].startswith(k + ":"):
                lines[i] = "%s: %s" % (k, value)
                return "\n".join(lines)
    types = fmkeys.file_keys("type")
    pos = next((i + 1 for i in range(1, end) if lines[i].split(":", 1)[0] in types), 1)
    doc_type = split_frontmatter(text)[0].get("type", "")
    lines.insert(pos, "%s: %s" % (fmkeys.write_key(key, doc_type), value))
    return "\n".join(lines)


def ensure_role(text):
    """type 是角色、但 role 空白的設定檔補上預設定位；其他內容不動。"""
    fm, _ = split_frontmatter(text)
    if fmkeys.value_en("type", fm.get("type")) != "character":
        return text
    if str(fm.get("role") or "").strip():
        return text
    return set_frontmatter_field(text, "role", DEFAULT_ROLE)


def _fm_text(v):
    """frontmatter 的值 → 一行的寫法（清單寫成 [a, b]）。"""
    if isinstance(v, list):
        return "[%s]" % ", ".join(str(x) for x in v)
    if v is None:
        return ""
    return str(v)


def _sections(body):
    """正文 → [["", 前言], ["標題", 內文], ...]；只在 ## 這一層切。內文含標題行後面的換行。"""
    parts = re.split(r"(?m)^##[ \t]+(.+)$", body)
    out = [["", parts[0]]]
    for i in range(1, len(parts), 2):
        out.append([parts[i].strip(), parts[i + 1]])
    return out


PLACEHOLDERS = ("待補", "正文未明確", "未明確", "tbd", "—", "-")


def _section_blank(content):
    """段落是不是空的：只剩空白、註解、沒填值的列點（- 想要：）或「待補」這種佔位字。"""
    t = re.sub(r"<!--.*?-->", "", content, flags=re.S)
    t = re.sub(r"^\s*[-*]?\s*$", "", t, flags=re.M)                  # 空行、空列點
    t = re.sub(r"^\s*[-*]?\s*[^：:\n]{1,30}[：:]\s*$", "", t, flags=re.M)   # - 想要：
    t = t.strip().strip("（）()")
    return not t or t.lower() in PLACEHOLDERS


def _squash(text):
    """比對用：把空白差異抹平。"""
    return re.sub(r"\s+", " ", text).strip()


def merge_entry(old, new, lang=None):
    """把 new（通常是從正文反推的草稿）併進既有設定檔 old，old 的內容一律不被覆蓋。

    - frontmatter：只補 old 空白的欄位；狀態、來源不動。
    - 正文：按「## 標題」對齊。old 沒有的段落接在最後；old 空白（只剩註解或空列點）就用 new 的內容；
      old 已有不同內容時整段保留 old，new 的說法另收進「## 從正文反推（未併入，請核對）」。
    回傳 (text, 未併入的段落標題清單)。
    """
    old, new = normalize_frontmatter(old), normalize_frontmatter(new)
    ofm, _ = split_frontmatter(old)
    nfm, nbody = split_frontmatter(new)
    text = old
    fill = [k for k, v in nfm.items()
            if k not in ("status", "source") and _fm_text(v).strip() and not str(ofm.get(k) or "").strip()]
    for k in reversed(fill):            # set_frontmatter_field 插在「類型」後面，倒著補才會照 new 的順序
        text = set_frontmatter_field(text, k, _fm_text(nfm[k]))
    _, obody = split_frontmatter(text)
    head = text[:len(text) - len(obody)]
    osec = _sections(obody)
    doc = fmkeys.value_en("type", nfm.get("type") or ofm.get("type"))

    def key(t):             # 同一段不同語言的標題對得起來（v2 中文標題 ↔ 英文、日文）
        return sections.id_of(doc, t) or t
    where = {key(s[0]): i for i, s in enumerate(osec) if s[0]}
    conflicts, tail = [], []
    for title, content in _sections(nbody)[1:]:
        i = where.get(key(title))
        if i is None:
            tail.append([title, content])
        elif _section_blank(osec[i][1]):
            osec[i][1] = content
        elif _squash(osec[i][1]) != _squash(content):
            conflicts.append((title, content))
    if conflicts:
        block = "\n\n".join("### %s\n%s" % (t, c.strip()) for t, c in conflicts)
        i = where.get(key(REV_SECTION))
        if i is None:
            tail.append([sections.label("common", "rev_unmerged", lang), "\n" + block])
        else:
            osec[i][1] = osec[i][1].rstrip("\n") + "\n\n" + block
    parts = [((("## %s" % t) + c) if t else c).strip("\n") for t, c in osec + tail]
    body = "\n\n".join(p for p in parts if p) + "\n"
    return head.rstrip("\n") + "\n\n" + body, [t for t, _ in conflicts]


def list_entries(book_dir, rel_dir):
    d = safe_path(book_dir, rel_dir)
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if os.path.isfile(p) and f.endswith(".md"):
            fm, body = split_frontmatter(read_text(p))
            one = ""
            m = re.search(r"##\s*" + sections.head_rx(fmkeys.value_en("type", fm.get("type")), "one_line") + r"\s*\n(.*?)(?=\n##|\Z)", body, re.S | re.I)
            if m:
                one = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip().split("\n")[0]
            tags = fm.get("tags") or []
            if isinstance(tags, str):
                tags = re.split(r"[,，、]", tags)
            out.append({
                "file": rel_of(book_dir, p),
                "name": str(fm.get("name") or os.path.splitext(f)[0]),
                "type": fmkeys.disp("type", fm.get("type")),
                "status": fmkeys.disp("status", fm.get("status")),
                "role": fmkeys.disp("role", fm.get("role")),
                "category": str(fmkeys.disp("category", fm.get("category")) or "").strip() or None,
                "tags": [str(x).strip() for x in tags if str(x).strip()],
                "aliases": fm.get("aliases") or [],
                "first": fmkeys.ch_disp(fm.get("first_appearance")),
                "summary": one[:80],
                "mtime": os.path.getmtime(p),
            })
    return out


def bible(book_dir):
    return {
        "characters": list_entries(book_dir, layout.CHARACTERS),
        "factions": list_entries(book_dir, layout.FACTIONS),
        "world": list_entries(book_dir, layout.WORLD),
        "drafts": list_entries(book_dir, layout.BIBLE_DRAFTS),
        "core": [e for e in [
            _single(book_dir, layout.STORY_CORE, "故事核心"),
            _single(book_dir, layout.STYLE, "文風"),  # literal-ok: 設定集分頁的顯示標籤
            _single(book_dir, layout.AUTHOR_PREFS, "作者偏好"),
            _single(book_dir, layout.GLOSSARY, "名詞表"),
        ] if e],
    }


def _single(book_dir, rel, name):
    p = os.path.join(book_dir, rel)
    if not os.path.isfile(p):
        return None
    return {"file": rel, "name": name, "mtime": os.path.getmtime(p)}


def outline_files(book_dir):
    """大綱檔清單：全書大綱最前，接著 `outline/volumes/` 的卷綱依卷號排序，最後是 `outline/` 裡其他的檔。

    以前直接用檔名排序，中文字會排成「一、三、二」（碼位順序），看起來像亂的。
    """
    from . import volume
    rows = []
    for sub in (layout.OUTLINE, layout.VOLUMES_SUBDIR):
        d = layout.path(book_dir, sub)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".md"):
                continue
            name = os.path.splitext(f)[0]
            if sub + "/" + f == layout.BOOK_OUTLINE:
                key = (0, 0)
                name = "全書大綱"   # literal-ok: 顯示名稱（v3 檔名是 book.md），介面文字在 P5 處理
            elif sub == layout.VOLUMES_SUBDIR:
                key = (1, volume._num_from_name(f) or 99)       # vol-01、vol-02…；作者自己取名的照「第N卷」
                m = volume._STEM.match(name)
                if m:      # 顯示「第1卷」「第1幕」＋卷綱裡的卷名（前端只翻「第N卷」，卷名是書的內容）
                    name = ("第%d幕" if m.group(1).lower() == "act" else "第%d卷") % int(m.group(2))   # literal-ok: 顯示名稱
            else:
                try:
                    fm = split_frontmatter(read_text(os.path.join(d, f)))[0]
                except OSError:
                    fm = {}
                if f == layout.TPL_BOOK_OUTLINE or fmkeys.value_en("type", fm.get("type")) == "book-outline":
                    key = (0, 1)
                    name = "全書大綱"   # literal-ok: 顯示名稱（相容舊檔或範本檔名 book-outline.md）
                else:
                    key = (2, 0)
            row = {"file": sub + "/" + f, "name": name}
            if sub == layout.VOLUMES_SUBDIR:
                try:
                    t = split_frontmatter(read_text(os.path.join(d, f)))[0].get("title")
                except OSError:
                    t = None
                if t:
                    row["title"] = str(t)
            rows.append((key, row))
    rows.sort(key=lambda x: (x[0], x[1]["name"]))
    return [r[1] for r in rows]


# ---------------------------------------------------------------------------
# 總覽與警示
# ---------------------------------------------------------------------------
def _ch(s):
    if not s:
        return None
    n = chapter_no(str(s))
    if n is None:
        m = re.search(r"\d+", str(s))
        n = int(m.group(0)) if m else None
    return n


ONE_OFF_MARKS = ("不具名", "一次性")   # 角色名稱含這些字：一次性配角，不提醒久未登場


def overview(book_dir, stale_foreshadow=10, stale_character=15):
    chs = scan_chapters(book_dir)
    written = [c for c in chs if c["text_file"]]
    latest = max((c["no"] for c in written), default=0)
    status_count = {"草稿": 0, "已確認": 0, "已寫": 0, "無章綱": 0}  # literal-ok: 介面的顯示字（card_status 是 disp 過的值），P5 改成 ID
    for c in chs:
        s = c["card_status"] or ("無章綱" if not c["card_file"] else "草稿")  # literal-ok: 介面的顯示字
        status_count[s] = status_count.get(s, 0) + 1

    alerts = []
    # 追蹤落後
    state_p = layout.path(book_dir, layout.STATE_CARD)
    state_text = read_text(state_p) if os.path.isfile(state_p) else ""
    fm, _ = split_frontmatter(state_text)
    updated_to = _ch(fm.get("updated_through"))
    if latest and (updated_to or 0) < latest:
        alerts.append({"level": "warn", "kind": "追蹤落後",
                       "text": "正文已寫到第%d章，但狀態卡只更新到%s。" % (
                           latest, ("第%d章" % updated_to) if updated_to else "（尚未更新）"),
                       "action": "sync_tracking"})
    # 候選稿
    for c in chs:
        if c["candidate_file"]:
            alerts.append({"level": "info", "kind": "候選稿",
                           "text": "第%d章有候選稿等你審閱。" % c["no"], "chapter": c["no"]})
    # 伏筆：合併成「久未出現」「已過預計回收章」兩條，可以展開
    from . import tables   # tables 依賴 project：在函式內匯入，避免循環匯入
    fs = tables.read(book_dir, "foreshadow", layout.FORESHADOWING)   # 列是英文鍵（v3 P2）
    quiet, late, seen, dup = [], [], set(), []
    for r in fs["rows"]:
        fid = r.get("id", "")
        if fid in seen and fid not in dup:
            dup.append(fid)
        seen.add(fid)
        st = r.get("status", "")
        if st in ("已回收", "廢棄"):
            continue
        imp = r.get("priority", "")
        last = _ch(r.get("last_seen")) or _ch(r.get("planted_in"))
        due = due_chapter(r.get("planned_payoff"))
        label = "%s（%s）" % (fid, r.get("content", "")[:20])
        if imp in ("高", "中") and last and latest - last > stale_foreshadow:
            quiet.append((latest - last, label))
        if due and latest > due:
            late.append((latest - due, label, due))
    if quiet:
        quiet.sort(key=lambda x: -x[0])
        alerts.append({"level": "warn", "kind": "伏筆久未出現",
                       "text": "%d 條重要度中以上的伏筆超過 %d 章沒有出現（最久：%s %d 章）。" % (
                           len(quiet), stale_foreshadow, quiet[0][1], quiet[0][0]),
                       "details": ["%s：%d 章沒有出現" % (l, g) for g, l in quiet]})
    if late:
        late.sort(key=lambda x: -x[0])
        alerts.append({"level": "warn", "kind": "伏筆逾期",
                       "text": "%d 條伏筆已過預計回收章（最久：%s 預計第%d章）。" % (len(late), late[0][1], late[0][2]),
                       "details": ["%s：預計第%d章回收，已過 %d 章" % (l, d, g) for g, l, d in late]})
    if dup:
        alerts.append({"level": "warn", "kind": "伏筆編號重複",
                       "text": "伏筆表有重複的編號：%s。請到伏筆表合併或改號。" % "、".join(dup)})
    # 角色久未登場：一次性、不具名的角色不提醒；其餘合併成一條
    cs_dir = layout.path(book_dir, layout.CHARACTER_STATES)
    if os.path.isdir(cs_dir):
        stale = []
        for f in os.listdir(cs_dir):
            if not f.endswith(".md"):
                continue
            cfm, _ = split_frontmatter(read_text(os.path.join(cs_dir, f)))
            name = str(cfm.get("name") or os.path.splitext(f)[0])
            if any(w in name or w in f for w in ONE_OFF_MARKS):
                continue
            last = _ch(cfm.get("last_appearance"))
            if last and latest - last > stale_character:
                stale.append((latest - last, name, last))
        if stale:
            stale.sort(key=lambda x: (-x[0], x[1]))
            top = "、".join("%s %d 章" % (n, g) for g, n, _ in stale[:3])
            alerts.append({"level": "info", "kind": "角色久未登場",
                           "text": "%d 個角色超過 %d 章沒有登場（最久：%s%s）。" % (
                               len(stale), stale_character, top, "……" if len(stale) > 3 else ""),
                           "details": ["%s：%d 章沒有登場（最後第%d章）" % (n, g, l) for g, n, l in stale]})
    # 草稿
    drafts = list_entries(book_dir, layout.BIBLE_DRAFTS)
    if drafts:
        alerts.append({"level": "info", "kind": "設定草稿",
                       "text": "有 %d 份設定草稿等你確認。" % len(drafts)})

    next_no = latest + 1
    next_card = next((c for c in chs if c["no"] == next_no and c["card_file"]), None)
    return {
        "latest": latest,
        "next": {"no": next_no, "has_card": bool(next_card),
                 "title": next_card["title"] if next_card else "",
                 "card_status": next_card["card_status"] if next_card else None},
        "chars": sum(c["chars"] for c in written),
        "chapters": len(chs),
        "written": len(written),
        "status_count": status_count,
        "alerts": alerts,
        "state_card": state_text,
        "hook": read_hook(book_dir),
        "recent": [{"no": c["no"], "title": c["title"], "chars": c["chars"]} for c in written[-5:]][::-1],
    }


# ---------------------------------------------------------------------------
# 候選稿
# ---------------------------------------------------------------------------
def accept_candidate(book_dir, no):
    cands = _scan_dir(layout.path(book_dir, layout.CANDIDATES))
    if no not in cands:
        raise ProjectError("第%d章沒有候選稿" % no)
    src = layout.path(book_dir, layout.CANDIDATES, cands[no])
    dst_dir = layout.path(book_dir, layout.MANUSCRIPT)
    os.makedirs(dst_dir, exist_ok=True)
    texts = _scan_dir(dst_dir)
    if no in texts:
        # 舊正文先備份
        bak_dir = layout.path(book_dir, layout.STUDIO_BACKUP)
        os.makedirs(bak_dir, exist_ok=True)
        old = os.path.join(dst_dir, texts[no])
        os.replace(old, os.path.join(bak_dir, "%s.%d.md" % (os.path.splitext(texts[no])[0], int(time.time()))))
    dst = os.path.join(dst_dir, layout.chapter_md(no))     # 一律存成 ch-0003.md（候選稿可能是舊檔名或 .v2）
    os.replace(src, dst)
    return rel_of(book_dir, dst)


def discard_candidate(book_dir, no):
    cands = _scan_dir(layout.path(book_dir, layout.CANDIDATES))
    if no not in cands:
        raise ProjectError("第%d章沒有候選稿" % no)
    bak_dir = layout.path(book_dir, layout.STUDIO_BACKUP)
    os.makedirs(bak_dir, exist_ok=True)
    src = layout.path(book_dir, layout.CANDIDATES, cands[no])
    os.replace(src, os.path.join(bak_dir, layout.backup_name(layout.CANDIDATES, os.path.splitext(cands[no])[0], time.time())))
