# -*- coding: utf-8 -*-
"""讀取小說專案資料夾：書架、章節、設定、追蹤表格、警示。"""
import os
import re
import time

import yaml

CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff]")
CH_NUM = re.compile(r"第0*(\d+)章")

# 書目錄內允許瀏覽的資料夾
BROWSABLE = ["設定", "大綱", "正文", "追蹤", "候選", "範例", "_範本"]


class ProjectError(Exception):
    pass


# ---------------------------------------------------------------------------
# 基本工具
# ---------------------------------------------------------------------------
def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _read_maybe(path):
    """讀檔；檔案剛好被搬走或刪掉時（例如自動流程正在把候選稿移到正文）回傳 None。"""
    try:
        return read_text(path)
    except (FileNotFoundError, PermissionError):
        return None


def split_frontmatter(text):
    """回傳 (dict, body)。frontmatter 格式錯誤時回傳空 dict。"""
    if text.startswith("---"):
        lines = text.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                raw = "\n".join(lines[1:i])
                body = "\n".join(lines[i + 1:])
                try:
                    data = yaml.safe_load(raw) or {}
                    if not isinstance(data, dict):
                        data = {}
                except yaml.YAMLError:
                    data = {}
                return data, body
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
    m = CH_NUM.search(name)
    return int(m.group(1)) if m else None


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
    # 第001章_章名.md
    stem = os.path.splitext(name)[0]
    parts = stem.split("_", 1)
    return parts[1] if len(parts) == 2 else ""


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


def list_books(library):
    books = []
    if not library or not os.path.isdir(library):
        return books
    for name in sorted(os.listdir(library)):
        d = os.path.join(library, name)
        if not os.path.isdir(d) or name.startswith(".") or name == "_共用":
            continue
        info = {"id": name, "name": name, "is_book": is_book(d)}
        if info["is_book"]:
            chs = scan_chapters(d)
            written = [c for c in chs if c["text_file"]]
            info.update({
                "chapters_written": len(written),
                "chapters_planned": len(chs),
                "chars": sum(c["chars"] for c in written),
                "hook": read_hook(d),
                "updated": latest_mtime(d),
                "pending_candidates": sum(1 for c in chs if c["candidate_file"]),
            })
            from . import lang as lang_mod
            info["lang"] = lang_mod.book_lang(d)
            info["unit"] = lang_mod.count_unit(info["lang"])
        books.append(info)
    books.sort(key=lambda b: (not b["is_book"], -(b.get("updated") or 0)))
    return books


def read_hook(book_dir):
    p = os.path.join(book_dir, "設定", "故事核心.md")
    if not os.path.isfile(p):
        return ""
    _, body = split_frontmatter(read_text(p))
    m = re.search(r"##\s*一句話鉤子\s*\n(.*?)(?=\n##|\Z)", body, re.S)
    if not m:
        return ""
    txt = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip()
    return txt.split("\n")[0][:80]


def latest_mtime(book_dir):
    newest = 0
    for sub in ("正文", "大綱", "追蹤", "設定", "候選"):
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
    return d


# ---------------------------------------------------------------------------
# 章節
# ---------------------------------------------------------------------------
def _scan_dir(d, pattern=".md"):
    out = {}
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.endswith(pattern):
                n = chapter_no(f)
                if n is not None:
                    out.setdefault(n, f)
    return out


def scan_chapters(book_dir):
    cards = _scan_dir(os.path.join(book_dir, "大綱", "章綱"))
    texts = _scan_dir(os.path.join(book_dir, "正文"))
    cands = _scan_dir(os.path.join(book_dir, "候選"))
    sums = _scan_dir(os.path.join(book_dir, "追蹤", "章節摘要"))
    nums = sorted(set(cards) | set(texts) | set(cands))
    rows = []
    for n in nums:
        row = {"no": n, "title": "", "card_file": None, "card_status": None,
               "card_target": None, "text_file": None, "chars": 0,
               "candidate_file": None, "candidate_chars": 0,
               "summary_file": None, "func": ""}
        card_text = _read_maybe(os.path.join(book_dir, "大綱", "章綱", cards[n])) if n in cards else None
        if card_text is not None:
            p = os.path.join(book_dir, "大綱", "章綱", cards[n])
            fm, body = split_frontmatter(card_text)
            row["card_file"] = rel_of(book_dir, p)
            row["card_status"] = fm.get("狀態")
            row["card_target"] = fm.get("字數目標")
            row["title"] = str(fm.get("章名") or "")
            m = re.search(r"-\s*功能：([^\n<]*)", body)
            if m:
                row["func"] = m.group(1).strip()
        text = _read_maybe(os.path.join(book_dir, "正文", texts[n])) if n in texts else None
        if text is not None:
            p = os.path.join(book_dir, "正文", texts[n])
            row["text_file"] = rel_of(book_dir, p)
            row["chars"] = count_chars(text)
            row["title"] = row["title"] or chapter_title_from_filename(texts[n])
        cand = _read_maybe(os.path.join(book_dir, "候選", cands[n])) if n in cands else None
        if cand is not None:
            p = os.path.join(book_dir, "候選", cands[n])
            row["candidate_file"] = rel_of(book_dir, p)
            row["candidate_chars"] = count_chars(cand)
            row["title"] = row["title"] or chapter_title_from_filename(cands[n])
        if n in sums:
            row["summary_file"] = rel_of(book_dir, os.path.join(book_dir, "追蹤", "章節摘要", sums[n]))
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


def set_frontmatter_field(text, key, value):
    """只改 frontmatter 裡 key 那一行；沒有就插在「類型」後面；沒有 frontmatter 就補一段。其他內容不動。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return "---\n%s: %s\n---\n\n%s" % (key, value, text)
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ProjectError("frontmatter 格式錯誤，無法寫入分類")
    for i in range(1, end):
        if lines[i].startswith(key + ":"):
            lines[i] = "%s: %s" % (key, value)
            return "\n".join(lines)
    pos = next((i + 1 for i in range(1, end) if lines[i].startswith("類型:")), 1)
    lines.insert(pos, "%s: %s" % (key, value))
    return "\n".join(lines)


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
            m = re.search(r"##\s*一句話\s*\n(.*?)(?=\n##|\Z)", body, re.S)
            if m:
                one = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip().split("\n")[0]
            tags = fm.get("標籤") or []
            if isinstance(tags, str):
                tags = re.split(r"[,，、]", tags)
            out.append({
                "file": rel_of(book_dir, p),
                "name": str(fm.get("名稱") or os.path.splitext(f)[0]),
                "type": fm.get("類型"),
                "status": fm.get("狀態"),
                "role": fm.get("定位"),
                "category": str(fm.get("分類") or "").strip() or None,
                "tags": [str(x).strip() for x in tags if str(x).strip()],
                "aliases": fm.get("別名") or [],
                "first": fm.get("首次登場"),
                "summary": one[:80],
                "mtime": os.path.getmtime(p),
            })
    return out


def bible(book_dir):
    return {
        "角色": list_entries(book_dir, "設定/角色"),
        "勢力": list_entries(book_dir, "設定/勢力"),
        "世界觀": list_entries(book_dir, "設定/世界觀"),
        "草稿": list_entries(book_dir, "設定/草稿"),
        "核心": [e for e in [
            _single(book_dir, "設定/故事核心.md", "故事核心"),
            _single(book_dir, "設定/文風.md", "文風"),
            _single(book_dir, "設定/作者偏好.md", "作者偏好"),
            _single(book_dir, "設定/名詞表.md", "名詞表"),
        ] if e],
    }


def _single(book_dir, rel, name):
    p = os.path.join(book_dir, rel)
    if not os.path.isfile(p):
        return None
    return {"file": rel, "name": name, "mtime": os.path.getmtime(p)}


def outline_files(book_dir):
    d = os.path.join(book_dir, "大綱")
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".md"):
                out.append({"file": "大綱/" + f, "name": os.path.splitext(f)[0]})
    return out


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
    status_count = {"草稿": 0, "已確認": 0, "已寫": 0, "無章綱": 0}
    for c in chs:
        s = c["card_status"] or ("無章綱" if not c["card_file"] else "草稿")
        status_count[s] = status_count.get(s, 0) + 1

    alerts = []
    # 追蹤落後
    state_p = os.path.join(book_dir, "追蹤", "狀態卡.md")
    state_text = read_text(state_p) if os.path.isfile(state_p) else ""
    fm, _ = split_frontmatter(state_text)
    updated_to = _ch(fm.get("更新至"))
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
    fs = read_table(book_dir, "追蹤/伏筆.md")
    quiet, late, seen, dup = [], [], set(), []
    for r in fs["rows"]:
        fid = r.get("編號", "")
        if fid in seen and fid not in dup:
            dup.append(fid)
        seen.add(fid)
        st = r.get("狀態", "")
        if st in ("已回收", "廢棄"):
            continue
        imp = r.get("重要度", "")
        last = _ch(r.get("最後出現")) or _ch(r.get("埋設章"))
        due = due_chapter(r.get("預計回收"))
        label = "%s（%s）" % (fid, r.get("內容", "")[:20])
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
    cs_dir = os.path.join(book_dir, "追蹤", "角色狀態")
    if os.path.isdir(cs_dir):
        stale = []
        for f in os.listdir(cs_dir):
            if not f.endswith(".md"):
                continue
            cfm, _ = split_frontmatter(read_text(os.path.join(cs_dir, f)))
            name = str(cfm.get("名稱") or os.path.splitext(f)[0])
            if any(w in name or w in f for w in ONE_OFF_MARKS):
                continue
            last = _ch(cfm.get("最後登場"))
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
    drafts = list_entries(book_dir, "設定/草稿")
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
    cands = _scan_dir(os.path.join(book_dir, "候選"))
    if no not in cands:
        raise ProjectError("第%d章沒有候選稿" % no)
    src = os.path.join(book_dir, "候選", cands[no])
    dst_dir = os.path.join(book_dir, "正文")
    os.makedirs(dst_dir, exist_ok=True)
    texts = _scan_dir(dst_dir)
    if no in texts:
        # 舊正文先備份
        bak_dir = os.path.join(book_dir, ".studio", "備份")
        os.makedirs(bak_dir, exist_ok=True)
        old = os.path.join(dst_dir, texts[no])
        os.replace(old, os.path.join(bak_dir, "%s.%d.md" % (os.path.splitext(texts[no])[0], int(time.time()))))
    dst = os.path.join(dst_dir, cands[no])
    os.replace(src, dst)
    return rel_of(book_dir, dst)


def discard_candidate(book_dir, no):
    cands = _scan_dir(os.path.join(book_dir, "候選"))
    if no not in cands:
        raise ProjectError("第%d章沒有候選稿" % no)
    bak_dir = os.path.join(book_dir, ".studio", "備份")
    os.makedirs(bak_dir, exist_ok=True)
    src = os.path.join(book_dir, "候選", cands[no])
    os.replace(src, os.path.join(bak_dir, "候選_%s.%d.md" % (os.path.splitext(cands[no])[0], int(time.time()))))
