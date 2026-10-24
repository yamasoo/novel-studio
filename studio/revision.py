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


def save_revision(book_dir, no, base_path, base_text, new_title, new_text, notes, report, provider):
    rec = {"chapter": no, "base_path": base_path, "base_hash": goals.text_hash(base_text), "base_text": base_text,
           "new_title": new_title, "new_text": new_text, "notes": notes, "report": report,
           "created": time.time(), "provider": provider}
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
