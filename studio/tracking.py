# -*- coding: utf-8 -*-
"""
把 AI 回傳的結構化 JSON 回寫到追蹤檔。
所有寫檔都在這裡，由 Python 決定格式，AI 只負責內容。
"""
import os
import re
import subprocess
import time

from . import project

STATE_SECTIONS = ["目前位置", "主線進度", "在場角色", "下一章承諾", "長期約束", "連續性風險", "活躍伏筆"]
FS_HEADERS = ["編號", "內容", "埋設章", "預計回收", "最後出現", "狀態", "重要度"]
TL_HEADERS = ["編號", "故事時間", "實際發生（作者真相）", "讀者目前知道", "揭示章", "相關角色"]
CHAR_FIELDS = ["身分", "位置", "目標", "身體狀態", "情緒狀態", "能力與資源", "關係變化", "知道的秘密", "未了結的事"]
GLOSS_HEADERS = ["名詞", "類別", "說明", "注意"]
RP_HEADERS = ["編號", "類型", "內容", "作者真相", "種下章", "回收章", "相關角色"]
RP_TYPES = ("已知", "懸念", "誤認")
RP_FILE = "追蹤/讀者認知.md"
RP_DRAFT = "追蹤/讀者認知_草稿.md"
RP_NEW_BOOK_ROWS = 15   # 時間線超過這麼多列又沒有帳本，視為舊書，不自動建立

# 給 AI 看的回寫格式說明（放進提示詞）
WRITEBACK_SCHEMA = """請只輸出一個 JSON 物件，格式如下（只列出有變化的項目；沒有就給空陣列）：
{
  "summary": {"發生了什麼": "2～4 句", "局面變化": "…", "新出現的人事物": "沒有就寫「無」", "結尾停在": "…"},
  "state_card": {
    "目前位置": ["卷／章：…", "故事內時間：…", "主要場景：…"],
    "主線進度": ["走到哪一步：…", "下一個目標：…"],
    "在場角色": ["角色名：一句近況"],
    "下一章承諾": ["…"],
    "長期約束": ["…"],
    "連續性風險": ["…"],
    "活躍伏筆": ["F001 一句說明"]
  },
  "foreshadow": [
    {"編號": "既有編號，新伏筆寫「新」", "內容": "…", "埋設章": "第NNN章", "預計回收": "打算回收的那一章，只寫「第NNN章」；沒定就留空（要推進或呼應的章不要寫在這裡）", "最後出現": "第NNN章", "狀態": "已埋|推進中|已回收|廢棄", "重要度": "高|中|低"}
  ],
  "timeline": [
    {"編號": "既有編號，新事件寫「新」", "故事時間": "…", "實際發生（作者真相）": "…", "讀者目前知道": "…", "揭示章": "第NNN章或未揭示", "相關角色": "…"}
  ],
  "reader": [
    {"編號": "既有編號，新條目寫「新」", "類型": "已知|懸念|誤認", "內容": "讀者知道的事／在等答案的問題／誤以為的事", "作者真相": "真相或答案（作者沒定就留空）", "種下章": "第NNN章", "回收章": "揭曉或澄清的那一章；還沒回收就留空", "相關角色": "…"}
  ],
  "characters": [
    {"名稱": "角色名", "身分": "…", "位置": "…", "目標": "…", "身體狀態": "…", "情緒狀態": "…", "能力與資源": "…", "關係變化": "…", "知道的秘密": "…", "未了結的事": "…"}
  ],
  "new_entities": [
    {"類型": "角色|勢力|名詞|地點|物品|規則", "名稱": "…", "說明": "正文中出現的資訊，不要補寫"}
  ],
  "report": "給作者的白話匯報，2～5 句：這章更新了哪些追蹤資料、有什麼要作者注意"
}
規則：
- state_card 是本章結束後的「現在」狀態，七欄都要給完整內容（會整份覆寫），過時的內容拿掉。
- characters 只列本章有登場或有變化的角色；「知道的秘密」只寫角色在故事裡已經知道的事。
- foreshadow 與 timeline 只列本章新增或有變動的列，既有列要保留原編號。
- reader 是讀者認知帳本：本章讓讀者開始等答案的事記「懸念」、讓讀者誤以為的事記「誤認」、讀者新知道且會影響後續閱讀的關鍵資訊記「已知」；本章揭曉或澄清了舊的懸念、誤認，就用原編號填「回收章」。作者真相沒有把握就留空，不要自己編答案。
- 只寫正文裡真的發生的事，章綱計畫了但正文沒寫出來的不要寫。"""


REVISION_NOTE = ("\n【注意：這是修訂舊章】追蹤資料已經更新到第%d章，這次是重新整理較早的第%d章。"
                 "state_card 與 characters 請給空物件／空陣列（目前狀態以最新章為準，不能倒退）；"
                 "只修正和這章有關的伏筆、時間線列、名詞，以及這章的摘要。")


def _chno(s):
    m = re.search(r"\d+", str(s or ""))
    return int(m.group(0)) if m else 0


def tracked_to(book_dir):
    p = os.path.join(book_dir, "追蹤", "狀態卡.md")
    if not os.path.isfile(p):
        return 0
    fm, _ = project.split_frontmatter(project.read_text(p))
    return _chno(fm.get("更新至"))


def _bump_updated(text, label):
    """frontmatter 的「更新至」只往前，不倒退。"""
    m = re.search(r"^更新至:(.*)$", text, re.M)
    if m and _chno(m.group(1)) >= _chno(label):
        return text
    if m:
        return text[:m.start()] + "更新至: %s" % label + text[m.end():]
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


def upsert_table(path, default_headers, items, prefix, title, ftype, chapter_label):
    """依「編號」更新或新增表格列。回傳 (新增數, 更新數, 新編號清單)。"""
    if os.path.isfile(path):
        text = project.read_text(path)
    else:
        text = "---\n類型: %s\n更新至: %s\n---\n\n# %s\n\n" % (ftype, chapter_label, title)
    before, headers, rows, after = _split_table(text)
    headers = headers or default_headers
    by_id = {r.get("編號"): r for r in rows if r.get("編號")}
    nums = [int(m.group(1)) for r in rows for m in [re.match(prefix + r"(\d+)", r.get("編號", ""))] if m]
    nxt = max(nums, default=0) + 1
    added, updated, new_ids = 0, 0, []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        rid = str(it.get("編號", "")).strip()
        if rid in by_id:
            for h in headers:
                if h != "編號" and it.get(h) not in (None, ""):
                    if h == "最後出現" and _chno(it[h]) < _chno(by_id[rid].get(h)):
                        continue  # 修訂舊章時不讓「最後出現」倒退
                    by_id[rid][h] = _cell(it[h])
            updated += 1
        else:
            if not re.match(prefix + r"\d+$", rid) or rid in by_id:
                rid = "%s%03d" % (prefix, nxt)
                nxt += 1
            row = {h: _cell(it.get(h, "")) for h in headers}
            row["編號"] = rid
            rows.append(row)
            by_id[rid] = row
            added += 1
            new_ids.append(rid)
    # frontmatter 更新至
    before = _bump_updated(before, chapter_label)
    sep = "" if before.endswith("\n\n") else ("\n" if before.endswith("\n") else "\n\n")
    text = before + sep + _render_table(headers, rows) + ("\n" + after if after.strip() else "\n")
    _write(path, text)
    return added, updated, new_ids


# ---------------------------------------------------------------------------
def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _lines(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [s.strip(" -") for s in v.split("\n") if s.strip(" -")]
    return []


def chapter_label(no):
    return "第%03d章" % int(no)


def apply_writeback(book_dir, no, title, chars, data, revision=False):
    """回寫一章的追蹤資料。回傳變更摘要（給匯報用）。"""
    label = chapter_label(no)
    log = []

    # 1. 章節摘要
    s = data.get("summary") or {}
    body = "---\n類型: 章節摘要\n章號: %d\n章名: %s\n字數: %d\n---\n\n# 第%d章 %s\n" % (no, title, chars, no, title)
    for k in ("發生了什麼", "局面變化", "新出現的人事物", "結尾停在"):
        body += "\n## %s\n%s\n" % (k, str(s.get(k, "")).strip() or "（無）")
    _write(os.path.join(book_dir, "追蹤", "章節摘要", label + ".md"), body)
    log.append("章節摘要")

    # 2. 狀態卡
    sc = data.get("state_card") or {}
    if sc and not revision:
        p = os.path.join(book_dir, "追蹤", "狀態卡.md")
        text = "---\n類型: 狀態卡\n更新至: %s\n---\n\n# 狀態卡\n" % label
        for i, k in enumerate(STATE_SECTIONS, 1):
            text += "\n## %d. %s\n" % (i, k)
            items = _lines(sc.get(k))
            text += "".join("- %s\n" % x for x in items) if items else "- （無）\n"
        _write(p, text)
        log.append("狀態卡")

    # 3. 伏筆
    fs = data.get("foreshadow") or []
    if fs:
        a, u, ids = upsert_table(os.path.join(book_dir, "追蹤", "伏筆.md"), FS_HEADERS, fs, "F", "伏筆總表", "伏筆總表", label)
        log.append("伏筆（新增 %d、更新 %d）" % (a, u))
    else:
        _touch_updated(os.path.join(book_dir, "追蹤", "伏筆.md"), label)

    # 4. 時間線
    tl = data.get("timeline") or []
    if tl:
        a, u, ids = upsert_table(os.path.join(book_dir, "追蹤", "時間線.md"), TL_HEADERS, tl, "E", "時間線", "時間線", label)
        log.append("時間線（新增 %d、更新 %d）" % (a, u))
    else:
        _touch_updated(os.path.join(book_dir, "追蹤", "時間線.md"), label)

    # 4.5 讀者認知
    rp = []
    for x in data.get("reader") or []:
        if not isinstance(x, dict):
            continue
        old = bool(re.match(r"R\d+$", str(x.get("編號") or "").strip()))
        if not old and not str(x.get("內容") or "").strip():
            continue
        if x.get("類型") not in RP_TYPES:
            x = dict(x)
            x["類型"] = "" if old else "懸念"  # 舊條目沒給類型就不動，新條目預設懸念
        rp.append(x)
    rpath = os.path.join(book_dir, *RP_FILE.split("/"))
    if rp and not os.path.isfile(rpath) and len(project.read_table(book_dir, "追蹤/時間線.md")["rows"]) > RP_NEW_BOOK_ROWS:
        # 舊書還沒建立帳本：只登記新的幾條會變成殘缺的帳本，等作者從時間線轉換
        log.append("讀者認知（還沒建立帳本，略過；可到「伏筆與時間線」的讀者認知分頁從時間線建立）")
    elif rp:
        if not os.path.isfile(rpath):
            write_reader_table(rpath, [], label)
        a, u, ids = upsert_table(rpath, RP_HEADERS, rp, "R", "讀者認知", "讀者認知", label)
        log.append("讀者認知（新增 %d、更新 %d）" % (a, u))
    elif os.path.isfile(os.path.join(book_dir, *RP_FILE.split("/"))):
        _touch_updated(os.path.join(book_dir, *RP_FILE.split("/")), label)

    # 5. 角色狀態
    names = []
    for c in ([] if revision else (data.get("characters") or [])):
        if not isinstance(c, dict) or not str(c.get("名稱", "")).strip():
            continue
        name = re.sub(r'[\\/:*?"<>|]', "", str(c["名稱"]).strip())
        p = os.path.join(book_dir, "追蹤", "角色狀態", name + ".md")
        old = {}
        if os.path.isfile(p):
            for m in re.finditer(r"^- (.+?)：(.*)$", project.split_frontmatter(project.read_text(p))[1], re.M):
                old[m.group(1)] = m.group(2)
        text = "---\n類型: 角色狀態\n名稱: %s\n更新至: %s\n最後登場: %s\n---\n\n# %s：目前狀態\n\n" % (name, label, label, name)
        for f in CHAR_FIELDS:
            v = c.get(f)
            if isinstance(v, list):
                v = "；".join(str(x) for x in v)
            v = str(v).strip() if v not in (None, "") else old.get(f, "")
            text += "- %s：%s\n" % (f, v)
        _write(p, text)
        names.append(name)
    if names:
        log.append("角色狀態（%s）" % "、".join(names))

    # 6. 新增物登記：名詞表＋具名角色
    ents = [e for e in (data.get("new_entities") or []) if isinstance(e, dict) and str(e.get("名稱", "")).strip()]
    if ents:
        gp = os.path.join(book_dir, "設定", "名詞表.md")
        if os.path.isfile(gp):
            text = project.read_text(gp)
        else:
            text = "---\n類型: 名詞表\n---\n\n# 名詞表\n\n"
        before, headers, rows, after = _split_table(text)
        headers = headers or GLOSS_HEADERS
        have = {r.get(headers[0]) for r in rows}
        added = []
        for e in ents:
            nm = _cell(e["名稱"])
            if nm in have:
                continue
            row = {h: "" for h in headers}
            row[headers[0]] = nm
            if len(headers) > 1:
                row[headers[1]] = _cell(e.get("類型", ""))
            if len(headers) > 2:
                row[headers[2]] = _cell(e.get("說明", ""))
            if len(headers) > 3:
                row[headers[3]] = "首次出現：%s" % label
            rows.append(row)
            have.add(nm)
            added.append(nm)
            if e.get("類型") == "角色":
                cp = os.path.join(book_dir, "設定", "角色", re.sub(r'[\\/:*?"<>|]', "", nm) + ".md")
                if not os.path.exists(cp):
                    _write(cp, "---\n類型: 角色\n名稱: %s\n別名: []\n定位: 配角\n首次登場: %s\n狀態: 正式\n---\n\n# %s\n\n## 一句話\n%s\n\n## 備註\n由工作台依正文自動登記，只含正文已出現的資訊。\n"
                           % (nm, label, nm, _cell(e.get("說明", ""))))
        if added:
            sep = "" if before.endswith("\n\n") else "\n"
            _write(gp, before + sep + _render_table(headers, rows) + ("\n" + after if after.strip() else "\n"))
            log.append("名詞表（%s）" % "、".join(added))

    # 7. 章綱狀態
    cards = project._scan_dir(os.path.join(book_dir, "大綱", "章綱"))
    if no in cards:
        p = os.path.join(book_dir, "大綱", "章綱", cards[no])
        t = project.read_text(p)
        t2 = re.sub(r"^狀態:.*$", "狀態: 已寫", t, count=1, flags=re.M)
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


def write_reader_table(path, items, chapter_label_text, draft=False, keep_ids=False, note=""):
    """把讀者認知條目整份寫成表格。轉換時編號從 R001 重新排；回收比對時保留原編號（keep_ids）。
    note：附在表格後面的說明（回收比對的逐條紀錄），採用草稿時會拿掉。"""
    rows = []
    for i, it in enumerate(items, 1):
        row = {h: _cell(it.get(h, "")) for h in RP_HEADERS}
        if not (keep_ids and row["編號"]):
            row["編號"] = "R%03d" % i
        if row["類型"] not in RP_TYPES:
            row["類型"] = "懸念"
        rows.append(row)
    head = "---\n類型: 讀者認知\n更新至: %s\n%s---\n\n# 讀者認知%s\n\n" % (
        chapter_label_text, "狀態: 草稿\n" if draft else "", "（草稿：確認後按「採用」）" if draft else "")
    _write(path, head + RP_INTRO + _render_table(RP_HEADERS, rows) + "\n" + ("\n%s\n\n%s\n" % (RP_NOTE_HEAD, note.strip()) if note.strip() else ""))
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
    text = re.sub(r"(?m)^狀態: 草稿\n", "", text, count=1).replace("# 讀者認知（草稿：確認後按「採用」）", "# 讀者認知", 1)
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


def backup(book_dir, path, tag):
    if not os.path.isfile(path):
        return None
    d = os.path.join(book_dir, ".studio", "備份")
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, "%s_%s.%d.md" % (tag, os.path.splitext(os.path.basename(path))[0], int(time.time())))
    with open(path, encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as g:
        g.write(f.read())
    return dst
