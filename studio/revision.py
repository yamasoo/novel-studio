# -*- coding: utf-8 -*-
"""
審查意見與逐段對照修訂。
- 審查：模型逐條列出意見（附正文原句），存在 .studio/審查/第NNN章.json
- 修訂：模型依勾選的意見產生修訂稿，不直接覆蓋；存在 .studio/修訂/第NNN章.json，
  由作者逐段選擇保留原文或採用修訂，再套用成候選稿。
"""
import difflib
import json
import os
import re
import time

from . import goals, project, tracking

SEVERITIES = ["必須修", "建議修", "提醒"]

REVIEW_SCHEMA = (
    "只輸出一個 JSON 物件：\n"
    '{"summary": "一句話整體結論", "items": [{"severity": "必須修|建議修|提醒", '
    '"category": "劇情邏輯|人物|情緒關係|身體資訊|轉場|章末|設定|資訊邊界|文字", '
    '"quote": "問題所在的正文原句（逐字複製，10～60 字）", "issue": "問題是什麼，依據是哪個設定或前文", '
    '"suggestion": "具體怎麼改"}]}\n'
    "規則：每條意見都要有依據；沒有問題就給空陣列，不要湊數；作者文風允許的寫法不算問題；"
    "quote 必須從正文原封不動複製，工作台會逐字比對；最多 15 條，依嚴重度排序。")


def _dir(book_dir, kind):
    d = os.path.join(book_dir, ".studio", kind)
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# 審查意見
# ---------------------------------------------------------------------------
def normalize_review(data, chapter_text):
    tn = re.sub(r"[\s　]", "", project.split_frontmatter(chapter_text)[1])
    items = []
    for i, it in enumerate((data or {}).get("items") or []):
        if not isinstance(it, dict) or not str(it.get("issue", "")).strip():
            continue
        sev = it.get("severity") if it.get("severity") in SEVERITIES else "建議修"
        q = str(it.get("quote") or "").strip()
        items.append({"id": "R%d" % (len(items) + 1), "severity": sev,
                      "category": str(it.get("category") or "").strip()[:10],
                      "quote": q, "located": goals.quote_found(q, tn) if q else False,
                      "issue": str(it["issue"]).strip(), "suggestion": str(it.get("suggestion") or "").strip()})
    items.sort(key=lambda x: SEVERITIES.index(x["severity"]))
    for i, it in enumerate(items):
        it["id"] = "R%d" % (i + 1)
    return {"summary": str((data or {}).get("summary") or "").strip(), "items": items}


# 本機檢查（check_text.py）中逐行、可定位的發現併進審查意見，讓自動勾選與修訂也會處理。
# 標點由程式自動修、AI 味統計交給審查本身判斷，所以不併入。
LOCAL_KINDS = ("簡體字", "疑似誤字", "禁用詞", "大陸用語", "工程詞", "章尾昇華")
LOCAL_CATEGORY = "本機檢查"
LOCAL_MAX = 20


def _quote_around(line, needle, width=60):
    line = line.strip()
    if len(line) <= width:
        return line
    i = line.find(needle) if needle else -1
    if i < 0:
        return line[:width]
    a = max(0, min(i - (width - len(needle)) // 2, len(line) - width))
    return line[a:a + width]


def merge_local_checks(review, book_dir, path, checker):
    """把本機檢查的發現加進審查結果（不呼叫 AI）。同一個詞出現多次合併成一條。失敗時原樣回傳。"""
    if not checker or not path:
        return review
    full = os.path.join(book_dir, path)
    try:
        res = checker.check_file(full, checker.load_whitelist(book_dir), checker.load_banned(book_dir))
        lines = project.read_text(full).split("\n")
    except Exception:
        return review
    items = list(review.get("items") or [])
    ai_quotes = [x.get("quote") or "" for x in items if x.get("quote")]

    def covered(src, needle):
        # AI 審查的引文和這個發現在同一行、位置重疊，就當作已經指出
        i = src.find(needle)
        for q in ai_quotes:
            if needle in q or q in needle:
                return True
            j = src.find(q)
            if i >= 0 and j >= 0 and i < j + len(q) and j < i + len(needle):
                return True
        return False

    groups = {}
    for f in res.get("問題") or []:
        if f["類型"] not in LOCAL_KINDS or f["等級"] not in ("必須修", "建議修") or not f.get("行"):
            continue
        snip = str(f["片段"])
        needle = snip[:1] if f["類型"] == "簡體字" else snip.split("（")[0]
        src = lines[f["行"] - 1] if 0 < f["行"] <= len(lines) else ""
        if f["類型"] != "章尾昇華" and needle and covered(src, needle):
            continue
        key = (f["類型"], snip if f["類型"] == "簡體字" else needle)
        g = groups.setdefault(key, {"f": f, "needle": needle, "lines": []})
        g["lines"].append(f["行"])
    tn = re.sub(r"[\s　]", "", project.split_frontmatter(project.read_text(full))[1])
    added = 0
    for (kind, snip), g in groups.items():
        if added >= LOCAL_MAX:
            break
        f, ln = g["f"], g["lines"]
        src = lines[ln[0] - 1] if 0 < ln[0] <= len(lines) else ""
        q = _quote_around(src, g["needle"]) if kind != "章尾昇華" else src.strip()[:60]
        if kind == "簡體字":
            issue = "簡體字：%s" % snip
        elif kind == "章尾昇華":
            issue = "章尾昇華：最後一段在寫感悟或預告"
        else:
            issue = "%s「%s」" % (kind, g["needle"])
        if len(ln) > 1:
            issue += "（本章共 %d 處，全部都要處理）" % len(ln)
        items.append({"id": "", "severity": f["等級"], "category": LOCAL_CATEGORY, "quote": q,
                      "located": goals.quote_found(q, tn) if q else False,
                      "issue": issue, "suggestion": f["建議"]})
        added += 1
    # 去 AI 味的保真檢查（只提醒，自動流程不會勾）
    m = re.search(r"第0*(\d+)章", os.path.basename(path))
    if m:
        from . import fidelity
        for x in fidelity.load(book_dir, int(m.group(1)), project.read_text(full)):
            items.append({"id": "", "severity": "提醒", "category": LOCAL_CATEGORY, "quote": "", "located": False,
                          "issue": "去 AI 味後%s：%s" % (x["kind"], x["text"]),
                          "suggestion": "確認是不是刻意的改動；名字、數字、對白原話被改掉的話改回原稿"})
            added += 1
    items.sort(key=lambda x: SEVERITIES.index(x["severity"]))
    for i, it in enumerate(items):
        it["id"] = "R%d" % (i + 1)
    return dict(review, items=items, local=added)


def save_review(book_dir, no, path, text, review, provider):
    rec = dict(review, chapter=no, path=path, hash=goals.text_hash(text), checked_at=time.time(), provider=provider)
    with open(os.path.join(_dir(book_dir, "審查"), "第%03d章.json" % no), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    return rec


def load_review(book_dir, no):
    p = os.path.join(book_dir, ".studio", "審查", "第%03d章.json" % no)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        rec = json.load(f)
    full = os.path.join(book_dir, rec.get("path") or "")
    rec["stale"] = not os.path.isfile(full) or goals.text_hash(project.read_text(full)) != rec.get("hash")
    return rec


def review_md(no, rec):
    items = rec["items"]
    cnt = {s: sum(1 for x in items if x["severity"] == s) for s in SEVERITIES}
    head = "**第%d章審查**：%s（必須修 %d、建議修 %d、提醒 %d）" % (
        no, rec.get("summary") or "", cnt["必須修"], cnt["建議修"], cnt["提醒"])
    lines = ["- 【%s】%s%s → %s" % (x["severity"], x["issue"], "" if x["located"] or not x["quote"] else "（引文對不上）",
                                     x["suggestion"]) for x in items]
    if rec.get("local"):
        head += "\n其中 %d 條來自本機檢查（禁用詞、簡體字、大陸用語等，不經 AI）。" % rec["local"]
    return head + ("\n" + "\n".join(lines) if lines else "\n沒有發現問題。") + "\n\n可以在章節頁勾選要處理的意見，按「依勾選意見修訂」。"


def notes_text(rec, ids, extra):
    chosen = [x for x in (rec or {}).get("items", []) if x["id"] in (ids or [])]
    lines = []
    for x in chosen:
        lines.append("- 【%s｜%s】%s%s\n  修法：%s" % (x["severity"], x["category"], x["issue"],
                                                  ("\n  位置：「%s」" % x["quote"]) if x["quote"] else "", x["suggestion"]))
    if (extra or "").strip():
        lines.append("- 【作者意見】" + extra.strip())
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 逐段對照
# ---------------------------------------------------------------------------
def paragraphs(text):
    body = project.split_frontmatter(text)[1].replace("\r\n", "\n")
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def _inline(a, b):
    """單段的字元層級差異：[[op, text], ...]，op 為 eq／del／ins。"""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append(["eq", a[i1:i2]])
        else:
            if i2 > i1:
                out.append(["del", a[i1:i2]])
            if j2 > j1:
                out.append(["ins", b[j1:j2]])
    return out


def diff_blocks(old_text, new_text):
    old, new = paragraphs(old_text), paragraphs(new_text)
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    blocks = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            blocks.append({"type": "same", "old": old[i1:i2]})
            continue
        b = {"type": "change", "op": tag, "old": old[i1:i2], "new": new[j1:j2], "index": len([x for x in blocks if x["type"] == "change"])}
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            b["inline"] = [_inline(o, n) for o, n in zip(old[i1:i2], new[j1:j2])]
        blocks.append(b)
    return blocks


CHANGE_TABLE_RULE = ("匯報裡用表格逐處列出改動，格式固定為：\n| 原句 | 為什麼改 | 改成什麼 |\n|---|---|---|\n"
                     "「原句」照原稿抄（太長就抄前 30 字，要能在原稿找到）；「為什麼改」寫類別，例如：罐頭反應、替讀者點題、"
                     "敘述者解釋、章尾昇華、萬用表情、萬用比喻、說明書式對白、短句轟炸、破折號太多、大陸用語、簡體字、標點；"
                     "「改成什麼」寫改後的句子，刪掉就寫「（刪除）」。最多 40 列，同類太多時最後一列寫「其他 N 處同類」。"
                     "表格之後再用一兩句說明刻意保留了什麼。")


def parse_change_table(report):
    """從匯報抓出「原句｜為什麼改｜改成什麼」表格。"""
    items = []
    for line in (report or "").split("\n"):
        s = line.strip()
        if not s.startswith("|") or re.match(r"^\|[\s:\-|]+\|$", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("原句", "原文") or not cells[0]:
            continue
        items.append({"old": cells[0], "why": cells[1], "new": "｜".join(cells[2:])})
    return items


def _norm(s):
    return re.sub(r"[\s「」『』，。、！？：；…—\-*_]", "", s or "")


def save_revision(book_dir, no, base_path, base_text, new_title, new_text, notes, report, provider, kind="revise", items=None):
    rec = {"chapter": no, "base_path": base_path, "base_hash": goals.text_hash(base_text), "base_text": base_text,
           "new_title": new_title, "new_text": new_text, "notes": notes, "report": report,
           "created": time.time(), "provider": provider, "kind": kind,
           "items": items if items is not None else (parse_change_table(report) if kind == "deslop" else [])}
    with open(os.path.join(_dir(book_dir, "修訂"), "第%03d章.json" % no), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    return rec


def load_revision(book_dir, no):
    p = os.path.join(book_dir, ".studio", "修訂", "第%03d章.json" % no)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        rec = json.load(f)
    full = os.path.join(book_dir, rec["base_path"])
    rec["stale"] = not os.path.isfile(full) or goals.text_hash(project.read_text(full)) != rec["base_hash"]
    rec["blocks"] = diff_blocks(rec["base_text"], rec["new_text"])
    rec["changes"] = sum(1 for b in rec["blocks"] if b["type"] == "change")
    # 去 AI 味：把逐處清單對到段落上（用原句在原文段落裡找），對照畫面每段旁邊顯示修改原因
    items = rec.get("items") or []
    if items:
        used = set()
        for b in rec["blocks"]:
            if b["type"] != "change":
                continue
            olds = _norm("".join(b["old"]))
            news = _norm("".join(b["new"]))
            rs = []
            for i, it in enumerate(items):
                k = _norm(it["old"])[:30]
                if i not in used and k and (k in olds or (not olds and _norm(it["new"])[:20] in news)):
                    rs.append(it)
                    used.add(i)
            b["reasons"] = rs
        rec["unmatched"] = [it for i, it in enumerate(items) if i not in used]
    return rec


def discard_revision(book_dir, no):
    p = os.path.join(book_dir, ".studio", "修訂", "第%03d章.json" % no)
    if os.path.isfile(p):
        os.replace(p, os.path.join(_dir(book_dir, "備份"), "修訂_第%03d章.%d.json" % (no, int(time.time()))))


def apply_revision(book_dir, no, choices, checker):
    """choices: {變更編號(字串): "new"|"old"}，沒列到的採用修訂。結果寫成候選稿。"""
    rec = load_revision(book_dir, no)
    if not rec:
        raise project.ProjectError("第%d章沒有待確認的修訂" % no)
    if rec["stale"]:
        raise project.ProjectError("原稿在修訂之後被改過了，這份修訂已經對不上。請捨棄後重新修訂。")
    out, used_new, kept_old = [], 0, 0
    for b in rec["blocks"]:
        if b["type"] == "same":
            out += b["old"]
        elif choices.get(str(b["index"]), "new") == "old":
            out += b["old"]
            kept_old += 1
        else:
            out += b["new"]
            used_new += 1
    text = "\n\n".join(out).strip() + "\n"
    if checker:
        text, _ = checker.fix_punct(text)
    if rec.get("kind") == "deslop":
        # 去 AI 味不改劇情事實：寫回原本那份（正文或候選稿），原檔先備份；正文不用重跑回寫追蹤
        full = os.path.join(book_dir, rec["base_path"])
        bak = tracking.backup(book_dir, full, "去AI味前")
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        discard_revision(book_dir, no)
        from . import fidelity
        fid = fidelity.run(book_dir, no, rec["base_path"], rec["base_text"], text)
        return {"path": rec["base_path"], "used_new": used_new, "kept_old": kept_old, "from_text": rec["base_path"].startswith("正文"),
                "kind": "deslop", "backup": os.path.relpath(bak, book_dir).replace("\\", "/"), "fidelity": fid.strip()}
    # 寫成候選稿（原本是候選稿就覆蓋，原本是正文就另存候選，採用時再回寫追蹤）
    cand_dir = os.path.join(book_dir, "候選")
    os.makedirs(cand_dir, exist_ok=True)
    old = project._scan_dir(cand_dir).get(no)
    if old:
        tracking.backup(book_dir, os.path.join(cand_dir, old), "候選")
        os.remove(os.path.join(cand_dir, old))
    title = re.sub(r'[\\/:*?"<>|]', "", rec.get("new_title") or "") or \
        project.chapter_title_from_filename(os.path.basename(rec["base_path"])) or "未命名"
    name = "第%03d章_%s.md" % (no, title)
    with open(os.path.join(cand_dir, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    discard_revision(book_dir, no)
    return {"path": "候選/" + name, "used_new": used_new, "kept_old": kept_old,
            "from_text": rec["base_path"].startswith("正文")}
