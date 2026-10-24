# -*- coding: utf-8 -*-
"""讀取小說專案資料夾：書架、章節、設定、追蹤表格、警示。"""
import os
import re
import time

import yaml

CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
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
    return len(CJK.findall(body))


def chapter_no(name):
    m = CH_NUM.search(name)
    return int(m.group(1)) if m else None


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
        if not os.path.isdir(d) or name.startswith("."):
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
        if n in cards:
            p = os.path.join(book_dir, "大綱", "章綱", cards[n])
            fm, body = split_frontmatter(read_text(p))
            row["card_file"] = rel_of(book_dir, p)
            row["card_status"] = fm.get("狀態")
            row["card_target"] = fm.get("字數目標")
            row["title"] = str(fm.get("章名") or "")
            m = re.search(r"-\s*功能：([^\n<]*)", body)
            if m:
                row["func"] = m.group(1).strip()
        if n in texts:
            p = os.path.join(book_dir, "正文", texts[n])
            row["text_file"] = rel_of(book_dir, p)
            row["chars"] = count_chars(read_text(p))
            row["title"] = row["title"] or chapter_title_from_filename(texts[n])
        if n in cands:
            p = os.path.join(book_dir, "候選", cands[n])
            row["candidate_file"] = rel_of(book_dir, p)
            row["candidate_chars"] = count_chars(read_text(p))
            row["title"] = row["title"] or chapter_title_from_filename(cands[n])
        if n in sums:
            row["summary_file"] = rel_of(book_dir, os.path.join(book_dir, "追蹤", "章節摘要", sums[n]))
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
            out.append({
                "file": rel_of(book_dir, p),
                "name": str(fm.get("名稱") or os.path.splitext(f)[0]),
                "type": fm.get("類型"),
                "status": fm.get("狀態"),
                "role": fm.get("定位"),
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
    # 伏筆
    fs = read_table(book_dir, "追蹤/伏筆.md")
    for r in fs["rows"]:
        st = r.get("狀態", "")
        if st in ("已回收", "廢棄"):
            continue
        imp = r.get("重要度", "")
        last = _ch(r.get("最後出現")) or _ch(r.get("埋設章"))
        due = _ch(r.get("預計回收"))
        label = "%s（%s）" % (r.get("編號", ""), r.get("內容", "")[:20])
        if imp in ("高", "中") and last and latest - last > stale_foreshadow:
            alerts.append({"level": "warn", "kind": "伏筆久未出現",
                           "text": "%s 已 %d 章沒有出現。" % (label, latest - last)})
        if due and latest > due:
            alerts.append({"level": "warn", "kind": "伏筆逾期",
                           "text": "%s 預計第%d章回收，目前已到第%d章。" % (label, due, latest)})
    # 角色久未登場
    cs_dir = os.path.join(book_dir, "追蹤", "角色狀態")
    if os.path.isdir(cs_dir):
        for f in os.listdir(cs_dir):
            if f.endswith(".md"):
                cfm, _ = split_frontmatter(read_text(os.path.join(cs_dir, f)))
                last = _ch(cfm.get("最後登場"))
                if last and latest - last > stale_character:
                    alerts.append({"level": "info", "kind": "角色久未登場",
                                   "text": "%s 已 %d 章沒有登場。" % (
                                       cfm.get("名稱") or os.path.splitext(f)[0], latest - last)})
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
