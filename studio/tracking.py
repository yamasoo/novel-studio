# -*- coding: utf-8 -*-
"""
把 AI 回傳的結構化 JSON 回寫到追蹤檔。
所有寫檔都在這裡，由 Python 決定格式，AI 只負責內容。
"""
import os
import re
import subprocess
import time

from . import project, prompts, textguard
from . import fmkeys, layout, sections
from . import lang as lang_mod
from . import tables

# 回寫資料（英文鍵）與檔案裡的段落／欄位名稱（中文，檔案格式到 P3 才換）
SUMMARY_KEYS = (("what_happened", "發生了什麼"), ("situation_change", "局面變化"), ("new_elements", "新出現的人事物"),
                ("ends_on", "結尾停在"))
STATE_KEYS = (("current_position", "目前位置"), ("main_progress", "主線進度"), ("present_characters", "在場角色"),
              ("next_chapter_promises", "下一章承諾"), ("long_term_constraints", "長期約束"),
              ("continuity_risks", "連續性風險"), ("active_foreshadowing", "活躍伏筆"))
CHAR_KEYS = (("identity", "身分"), ("location", "位置"), ("goal", "目標"), ("physical_state", "身體狀態"),
             ("emotional_state", "情緒狀態"), ("abilities_resources", "能力與資源"), ("relationship_changes", "關係變化"),
             ("known_secrets", "知道的秘密"), ("unfinished_business", "未了結的事"))
STATE_SECTIONS = [label for _, label in STATE_KEYS]
FS_HEADERS = ["編號", "內容", "埋設章", "預計回收", "最後出現", "狀態", "重要度"]
TL_HEADERS = ["編號", "故事時間", "實際發生（作者真相）", "讀者目前知道", "揭示章", "相關角色"]
CHAR_FIELDS = [label for _, label in CHAR_KEYS]
GLOSS_HEADERS = ["名詞", "類別", "說明", "注意"]
RP_HEADERS = ["編號", "類型", "內容", "作者真相", "種下章", "回收章", "相關角色"]
RP_TYPES = ("已知", "懸念", "誤認")
RP_FILE = layout.READER_KNOWLEDGE
RP_DRAFT = layout.READER_KNOWLEDGE_DRAFT
RP_NEW_BOOK_ROWS = 15   # 時間線超過這麼多列又沒有帳本，視為舊書，不自動建立
BACKUP_KEEP = 30        # 每組（標籤_原檔名）保留最新幾份

REVISION_NOTE = ("\n【注意：這是修訂舊章】追蹤資料已經更新到第%d章，這次是重新整理較早的第%d章。"
                 "state_card、characters 與 relations 請給空物件／空陣列（目前狀態與關係以最新章為準，不能倒退）；"
                 "只修正和這章有關的伏筆、時間線列、名詞，以及這章的摘要。")


def writeback_schema():
    return prompts.cur()["writeback_schema"]


def revision_note(tracked, no):
    return prompts.cur()["revision_note"].format(tracked=tracked, n=no)


def _chno(s):
    m = re.search(r"\d+", str(s or ""))
    return int(m.group(0)) if m else 0


def tracked_to(book_dir):
    p = layout.path(book_dir, layout.STATE_CARD)
    if not os.path.isfile(p):
        return 0
    fm, _ = project.split_frontmatter(project.read_text(p))
    return _chno(fm.get("updated_through"))


def _bump_updated(text, label):
    """frontmatter 的「更新至」只往前，不倒退。"""
    m = re.search(r"^(?:updated_through|更新至):(.*)$", text, re.M)
    if m and _chno(m.group(1)) >= _chno(label):
        return text
    if m:
        return text[:m.start()] + "updated_through: %s" % fmkeys.ch_value(label) + text[m.end():]
    return text


# ---------------------------------------------------------------------------
# Markdown 表格的讀寫（保留表格前後的文字）
# ---------------------------------------------------------------------------
def _split_table(text):
    lines = text.split("\n")
    for i in range(len(lines) - 1):
        if lines[i].strip().startswith("|") and re.match(r"^\s*\|[\s:\-|]+\|\s*$", lines[i + 1]):
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            headers = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            rows = []
            for l in lines[i + 2:j]:
                cells = [c.strip() for c in l.strip().strip("|").split("|")]
                cells += [""] * (len(headers) - len(cells))
                rows.append(dict(zip(headers, cells)))
            return "\n".join(lines[:i]), headers, rows, "\n".join(lines[j:])
    return text.rstrip() + "\n\n", None, [], ""


def _cell(v):
    return str(v if v is not None else "").replace("|", "／").replace("\n", " ").strip()


def _render_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_cell(r.get(h, "")) for h in headers) + " |")
    return "\n".join(out)


def upsert_table(path, kind, items, prefix, title, ftype, chapter_label, lang=None):
    """依「編號」更新或新增表格列。回傳 (新增數, 更新數, 新編號清單)。
    kind：tables.COLUMNS 的表名。檔案的表頭照舊；處理過程一律用英文鍵（v3 P2），
    模型給的資料不論是英文鍵或中文鍵（jsonkeys 換過）都認。"""
    if os.path.isfile(path):
        text = project.read_text(path)
    else:
        doc = fmkeys.value_en("type", ftype)
        text = "---\ntype: %s\nupdated_through: %s\n---\n\n# %s\n\n" % (
            fmkeys.write_value("type", ftype), fmkeys.ch_value(chapter_label),
            sections.title(doc, lang) if doc in sections.TITLES else title)
    before, headers, rows, after = _split_table(text)
    headers = headers or tables.headers(kind)
    keys = [tables._key_any(kind, h) for h in headers]
    rows = tables.rows_to_keys(kind, rows)
    by_id = {r.get("id"): r for r in rows if r.get("id")}
    nums = [int(m.group(1)) for r in rows for m in [re.match(prefix + r"(\d+)", r.get("id", ""))] if m]
    nxt = max(nums, default=0) + 1
    added, updated, new_ids = 0, 0, []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        it = tables.row_to_keys(kind, it)
        rid = str(it.get("id", "")).strip()
        if rid in by_id:
            for k in keys:
                if k != "id" and it.get(k) not in (None, ""):
                    if k == "last_seen" and _chno(it[k]) < _chno(by_id[rid].get(k)):
                        continue  # 修訂舊章時不讓「最後出現」倒退
                    by_id[rid][k] = _cell(it[k])
            updated += 1
        else:
            if not re.match(prefix + r"\d+$", rid) or rid in by_id:
                rid = "%s%03d" % (prefix, nxt)
                nxt += 1
            row = {k: _cell(it.get(k, "")) for k in keys}
            row["id"] = rid
            rows.append(row)
            by_id[rid] = row
            added += 1
            new_ids.append(rid)
    # frontmatter 更新至
    before = _bump_updated(before, chapter_label)
    sep = "" if before.endswith("\n\n") else ("\n" if before.endswith("\n") else "\n\n")
    text = before + sep + tables.render(kind, keys, rows, sections.write_lang(lang)) + ("\n" + after if after.strip() else "\n")
    _write(path, text)
    return added, updated, new_ids


# ---------------------------------------------------------------------------
def _write(path, text):
    project.write_atomic(path, text)


def _lines(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [s.strip(" -") for s in v.split("\n") if s.strip(" -")]
    return []


def chapter_label(no):
    return "第%03d章" % int(no)


def apply_writeback(book_dir, no, title, chars, data, revision=False):
    """回寫一章的追蹤資料。data 是英文鍵（jsonkeys.to_keys 換過）。回傳變更摘要（給匯報用）。"""
    label = chapter_label(no)
    log = []
    lang = lang_mod.book_lang(book_dir)
    from . import trackjson
    trackjson.sync(book_dir)            # 先讓 .md 與 JSON 一致（只在 JSON 改過時重寫 .md；沒有 JSON 的補上）
    data, note = textguard.guard_data(book_dir, data)
    if note:
        log.append(note)

    # 1. 章節摘要
    s = data.get("summary") or {}
    body = "---\ntype: chapter-summary\nchapter: %d\ntitle: %s\nlength: %d\n---\n\n# %s\n" % (
        no, title, chars, sections.title("chapter", lang, n=no, title=title))
    for k, _ in SUMMARY_KEYS:
        body += "\n## %s\n%s\n" % (sections.label("chapter-summary", k, lang), str(s.get(k, "")).strip() or sections.none(lang))
    _write(layout.path(book_dir, layout.SUMMARIES, layout.chapter_md(no)), body)
    log.append("章節摘要")

    # 2. 狀態卡
    sc = data.get("state_card") or {}
    if sc and not revision:
        p = layout.path(book_dir, layout.STATE_CARD)
        text = "---\ntype: state-card\nupdated_through: %s\n---\n\n# %s\n" % (fmkeys.ch_value(label), sections.title("state-card", lang))
        for i, (k, _) in enumerate(STATE_KEYS, 1):
            text += "\n## %d. %s\n" % (i, sections.label("state-card", k, lang))
            items = _lines(sc.get(k))
            text += "".join("- %s\n" % x for x in items) if items else "- %s\n" % sections.none(lang)
        _write(p, text)
        log.append("狀態卡")

    # 3. 伏筆
    fs = data.get("foreshadow") or []
    if fs:
        a, u, ids = upsert_table(layout.path(book_dir, layout.FORESHADOWING), "foreshadow", fs, "F", "伏筆總表", "伏筆總表", label, lang)
        log.append("伏筆（新增 %d、更新 %d）" % (a, u))
    else:
        _touch_updated(layout.path(book_dir, layout.FORESHADOWING), label)

    # 4. 時間線
    tl = data.get("timeline") or []
    if tl:
        a, u, ids = upsert_table(layout.path(book_dir, layout.TIMELINE), "timeline", tl, "E", "時間線", "時間線", label, lang)
        log.append("時間線（新增 %d、更新 %d）" % (a, u))
    else:
        _touch_updated(layout.path(book_dir, layout.TIMELINE), label)

    # 4.5 讀者認知
    rp = []
    for x in data.get("reader") or []:
        if not isinstance(x, dict):
            continue
        old = bool(re.match(r"R\d+$", str(x.get("id") or "").strip()))
        if not old and not str(x.get("content") or "").strip():
            continue
        if x.get("type") not in RP_TYPES:
            x = dict(x)
            x["type"] = "" if old else "懸念"  # 舊條目沒給類型就不動，新條目預設懸念
        rp.append(x)
    rpath = os.path.join(book_dir, *RP_FILE.split("/"))
    if rp and not os.path.isfile(rpath) and len(project.read_table(book_dir, layout.TIMELINE)["rows"]) > RP_NEW_BOOK_ROWS:
        # 舊書還沒建立帳本：只登記新的幾條會變成殘缺的帳本，等作者從時間線轉換
        log.append("讀者認知（還沒建立帳本，略過；可到「伏筆與時間線」的讀者認知分頁從時間線建立）")
    elif rp:
        if not os.path.isfile(rpath):
            write_reader_table(rpath, [], label, lang=lang)
        a, u, ids = upsert_table(rpath, "reader", rp, "R", "讀者認知", "讀者認知", label, lang)
        log.append("讀者認知（新增 %d、更新 %d）" % (a, u))
    elif os.path.isfile(os.path.join(book_dir, *RP_FILE.split("/"))):
        _touch_updated(os.path.join(book_dir, *RP_FILE.split("/")), label)

    # 5. 角色狀態
    names = []
    for c in ([] if revision else (data.get("characters") or [])):
        if not isinstance(c, dict) or not str(c.get("name", "")).strip():
            continue
        name = re.sub(r'[\\/:*?"<>|]', "", str(c["name"]).strip())
        p = layout.path(book_dir, layout.CHARACTER_STATES, name + ".md")
        old = {}
        if os.path.isfile(p):
            for m in re.finditer(r"^- (.+?)(?:：|: ?)(.*)$", project.split_frontmatter(project.read_text(p))[1], re.M):
                k = sections.field_id("character-state", m.group(1))
                if k and k not in old:
                    old[k] = m.group(2)
        text = "---\ntype: character-state\nname: %s\nupdated_through: %s\nlast_appearance: %s\n---\n\n# %s\n\n" % (
            name, fmkeys.ch_value(label), fmkeys.ch_value(label), sections.title("character-state", lang, name=name))
        sep = ": " if sections.write_lang(lang) == "en" else "："
        for k, f in sections.fields("character-state", lang):
            v = c.get(k)
            if isinstance(v, list):
                v = "；".join(str(x) for x in v)
            v = str(v).strip() if v not in (None, "") else old.get(k, "")
            text += ("- %s%s%s" % (f, sep, v)).rstrip() + "\n" if sep == ": " else "- %s%s%s\n" % (f, sep, v)
        _write(p, text)
        names.append(name)
    if names:
        log.append("角色狀態（%s）" % "、".join(names))

    # 5.5 角色關係（誰對誰；變了才改，舊的標結束章）
    from . import relations
    r = relations.apply_changes(book_dir, no, data.get("relations"), revision)
    if r:
        log.append(r)

    # 6. 新增物登記：名詞表＋具名角色
    ents = [e for e in (data.get("new_entities") or []) if isinstance(e, dict) and str(e.get("name", "")).strip()]
    if ents:
        gp = layout.path(book_dir, layout.GLOSSARY)
        wl = sections.write_lang(lang)
        if os.path.isfile(gp):
            text = project.read_text(gp)
        else:
            text = "---\ntype: glossary\n---\n\n# %s\n\n" % sections.title("glossary", wl)
        before, headers, rows, after = _split_table(text)
        headers = headers or [tables.label("glossary", k, wl) for k in tables.keys("glossary")]
        have = {r.get(headers[0]) for r in rows}
        added = []
        for e in ents:
            nm = _cell(e["name"])
            if nm in have:
                continue
            row = {h: "" for h in headers}
            row[headers[0]] = nm
            if len(headers) > 1:
                row[headers[1]] = _cell(e.get("type", ""))
            if len(headers) > 2:
                row[headers[2]] = _cell(e.get("explanation", ""))
            if len(headers) > 3:
                row[headers[3]] = FIRST_SEEN[wl] % tables.display("foreshadow", "planted_in", label, wl)
            rows.append(row)
            have.add(nm)
            added.append(nm)
            if e.get("type") == "角色":
                cp = layout.path(book_dir, layout.CHARACTERS, re.sub(r'[\\/:*?"<>|]', "", nm) + ".md")
                if not os.path.exists(cp):
                    _write(cp, sections.localize_doc(
                        "---\ntype: character\nname: %s\naliases: []\nrole: supporting\nfirst_appearance: %s\nstatus: canon\n---\n\n# %s\n\n## 一句話\n%s\n\n## 備註\n%s\n"
                        % (nm, fmkeys.ch_value(label), nm, _cell(e.get("explanation", "")), prompts.pack(sections.write_lang(lang))["wb_auto_char_note"]), lang))
        if added:
            sep = "" if before.endswith("\n\n") else "\n"
            _write(gp, before + sep + _render_table(headers, rows) + ("\n" + after if after.strip() else "\n"))
            log.append("名詞表（%s）" % "、".join(added))

    # 7. 章綱狀態
    cards = project._scan_dir(layout.path(book_dir, layout.CHAPTER_CARDS))
    if no in cards:
        p = layout.path(book_dir, layout.CHAPTER_CARDS, cards[no])
        t = project.read_text(p)
        t2 = re.sub(r"^(?:status|狀態):.*$", "status: written", t, count=1, flags=re.M)
        if t2 != t:
            _write(p, t2)
            log.append("章綱狀態→已寫")
    return log


def _touch_updated(path, label):
    if os.path.isfile(path):
        t = project.read_text(path)
        t2 = _bump_updated(t, label)
        if t2 != t:
            _write(path, t2)


def git_commit(book_dir, message):
    if not os.path.isdir(os.path.join(book_dir, ".git")):
        return False
    try:
        subprocess.run(["git", "add", "-A"], cwd=book_dir, capture_output=True, timeout=30)
        r = subprocess.run(["git", "commit", "-m", message], cwd=book_dir, capture_output=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


RP_INTRO = ("> 讀者讀到目前為止的認知：「已知」是讀者知道的事；「懸念」是讀者在等答案的問題；「誤認」是讀者誤以為的事（反轉用）。\n"
            "> 「作者真相」是答案（選填）；「回收章」空白＝還沒揭曉。寫稿時不能提前回收沒到時候的懸念與誤認。\n\n")


RP_NOTE_HEAD = "## 回收比對紀錄"
FIRST_SEEN = {"zh-TW": "首次出現：%s", "en": "First seen: %s", "ja": "初出：%s"}      # 名詞表「注意」欄


def write_reader_table(path, items, chapter_label_text, draft=False, keep_ids=False, note="", lang=None):
    """把讀者認知條目整份寫成表格。轉換時編號從 R001 重新排；回收比對時保留原編號（keep_ids）。
    note：附在表格後面的說明（回收比對的逐條紀錄），採用草稿時會拿掉。"""
    rows = []
    for i, it in enumerate(items, 1):
        row = {k: _cell(it.get(k, "")) for k in tables.keys("reader")}   # 表格的列、模型的條目都是英文鍵
        if not (keep_ids and row["id"]):
            row["id"] = "R%03d" % i
        row["type"] = tables.internal("reader", "type", row["type"])
        if row["type"] not in RP_TYPES:
            row["type"] = "懸念"
        rows.append(row)
    wl = sections.write_lang(lang if lang else prompts.cur_lang())
    head = "---\ntype: reader-knowledge\nupdated_through: %s\n%s---\n\n# %s%s\n\n" % (
        fmkeys.ch_value(chapter_label_text), "status: draft\n" if draft else "", sections.title("reader-knowledge", wl),
        prompts.pack(wl)["rp_draft_suffix"] if draft else "")
    _write(path, head + prompts.pack(wl)["rp_intro"] + tables.render("reader", tables.keys("reader"), rows, wl) + "\n"
           + ("\n%s\n\n%s\n" % (RP_NOTE_HEAD, note.strip()) if note.strip() else ""))
    return len(rows)


def adopt_reader_draft(book_dir):
    """採用草稿：舊的帳本（如果有）先備份，草稿改名成正式檔，拿掉草稿標記。"""
    src = os.path.join(book_dir, *RP_DRAFT.split("/"))
    dst = os.path.join(book_dir, *RP_FILE.split("/"))
    if not os.path.isfile(src):
        raise project.ProjectError("沒有讀者認知草稿")
    if os.path.isfile(dst):
        backup(book_dir, dst, "讀者認知")
    text = project.read_text(src)
    text = re.sub(r"(?m)^(?:status|狀態): (?:draft|草稿)\n", "", text, count=1).replace("# 讀者認知（草稿：確認後按「採用」）", "# 讀者認知", 1)
    if "\n" + RP_NOTE_HEAD in text:
        text = text.split("\n" + RP_NOTE_HEAD, 1)[0].rstrip() + "\n"
    _write(dst, text)
    os.remove(src)
    return RP_FILE


def discard_reader_draft(book_dir):
    src = os.path.join(book_dir, *RP_DRAFT.split("/"))
    if os.path.isfile(src):
        backup(book_dir, src, "讀者認知草稿")
        os.remove(src)


BACKUP_NAME_RE = re.compile(r"^(.*)\.(\d{9,})\.md$")


def prune_backups(d, name, keep=None):
    """只修剪與這份新備份同一組（標籤_原檔名）的舊檔，留下 epoch 最大的 keep 份（預設 BACKUP_KEEP）。

    檔名樣式由 tracking.backup 決定；其他也寫 .studio/backup 的地方（共用庫備份、匯入備份）
    沿用同一個樣式並呼叫這裡，備份目錄的總量才有上限。
    """
    keep = BACKUP_KEEP if keep is None else keep
    m = BACKUP_NAME_RE.match(name)
    if not m:
        return
    key = m.group(1)
    try:
        names = os.listdir(d)
    except OSError:
        return
    group = []
    for fn in names:
        mm = BACKUP_NAME_RE.match(fn)
        if not mm or mm.group(1) != key:
            continue
        p = os.path.join(d, fn)
        try:
            if os.path.isfile(p):
                group.append((int(mm.group(2)), os.path.getmtime(p), p))
        except OSError:
            continue
    group.sort(key=lambda t: (t[0], t[1]), reverse=True)
    for _, _, p in group[keep:]:
        try:
            os.remove(p)
        except OSError:
            pass


def backup(book_dir, path, tag):
    if not os.path.isfile(path):
        return None
    d = layout.path(book_dir, layout.STUDIO_BACKUP)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, "%s_%s.%d.md" % (tag, os.path.splitext(os.path.basename(path))[0], int(time.time())))
    with open(path, encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as g:
        g.write(f.read())
    prune_backups(d, os.path.basename(dst))
    return dst
