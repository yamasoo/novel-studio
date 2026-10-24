# -*- coding: utf-8 -*-
"""
章綱目標逐項核對：把章綱的情節點凍結成清單，請模型逐項回報是否寫到，並附正文原句；
Python 再確認每句引文真的在正文裡，引文對不上的「完成」一律降為「待確認」。
"""
import hashlib
import json
import os
import re
import time

from . import context, project

STATUS_LABEL = {"completed": "已寫到", "unmet": "沒寫到", "unknown": "無法判斷", "unverified": "引文對不上"}


def freeze_goals(card_text):
    """從章綱取出情節點與章末鉤子，回傳 [{"id","text"}]。"""
    _, body = project.split_frontmatter(card_text or "")
    body = context.strip_comments(body)
    goals = []
    m = re.search(r"##\s*情節點\s*\n(.*?)(?=\n##\s|\Z)", body, re.S)
    if m:
        for line in m.group(1).split("\n"):
            mm = re.match(r"\s*(?:\d+[.、．)]|[-*])\s*(.+)", line)
            if mm and mm.group(1).strip() and "待補" not in mm.group(1):
                goals.append(mm.group(1).strip())
    m = re.search(r"##\s*章末鉤子\s*\n(.*?)(?=\n##\s|\Z)", body, re.S)
    if m:
        mm = re.search(r"停在[：:]\s*(.+)", m.group(1))
        if mm and mm.group(1).strip() and "待定" not in mm.group(1):
            goals.append("章末停在：" + mm.group(1).strip())
    return [{"id": "G%d" % (i + 1), "text": t} for i, t in enumerate(goals)]


def _norm(s):
    return re.sub(r"[\s　]", "", s or "")


def quote_found(quote, text_norm):
    q = _norm(quote).strip("「」『』\"'“”‘’")
    if len(q) < 4:
        return False
    if q in text_norm:
        return True
    # 引文中用刪節號省略中間的部分：各段依序都要找得到
    parts = [p for p in re.split(r"……|…|\.\.\.", q) if len(p) >= 4]
    if len(parts) >= 2:
        pos = 0
        for p in parts:
            i = text_norm.find(p, pos)
            if i < 0:
                return False
            pos = i + len(p)
        return True
    return False


def text_hash(text):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


def build_prompt(no, goals, chapter_body):
    lines = "\n".join("%s：%s" % (g["id"], g["text"]) for g in goals)
    return ("【第%d章章綱目標清單（由工作台從章綱擷取）】\n%s\n\n【正文】\n%s\n\n"
            "【任務】逐項核對正文有沒有寫到每個目標。只輸出一個 JSON 物件：\n"
            '{"goals": [{"id": "G1", "status": "completed|unmet|unknown", '
            '"evidence": ["從正文逐字複製的原句"], "note": "一句說明：怎麼寫到的，或缺了什麼"}]}\n'
            "規則：\n- 清單裡每個 id 都要有一筆，不可增減。\n"
            "- completed 至少附一句引文；引文必須從正文原封不動複製（10～60 字），不可改寫、不可拼湊，工作台會逐字比對。\n"
            "- 只寫到一部分、或結果和目標不同，算 unmet，並在 note 說明差在哪裡。\n"
            "- 不確定時用 unknown，不要猜。" % (no, lines, chapter_body))


def verify(goals, data, chapter_text):
    tn = _norm(project.split_frontmatter(chapter_text)[1])
    got = {}
    for it in (data or {}).get("goals") or []:
        if isinstance(it, dict) and it.get("id"):
            got[str(it["id"]).strip()] = it
    items = []
    for g in goals:
        it = got.get(g["id"], {})
        status = it.get("status") if it.get("status") in ("completed", "unmet", "unknown") else "unknown"
        ev = it.get("evidence") or []
        if isinstance(ev, str):
            ev = [ev]
        checked = [{"quote": str(q), "found": quote_found(str(q), tn)} for q in ev if str(q).strip()]
        if status == "completed" and not any(c["found"] for c in checked):
            status = "unverified"
        items.append({"id": g["id"], "text": g["text"], "status": status,
                      "evidence": checked, "note": str(it.get("note") or "").strip()})
    return items


def summary(items):
    cnt = {k: 0 for k in STATUS_LABEL}
    for it in items:
        cnt[it["status"]] = cnt.get(it["status"], 0) + 1
    return cnt


def report_md(no, items):
    cnt = summary(items)
    head = "**第%d章章綱核對**：已寫到 %d、沒寫到 %d、引文對不上 %d、無法判斷 %d（共 %d 項）" % (
        no, cnt["completed"], cnt["unmet"], cnt["unverified"], cnt["unknown"], len(items))
    lines = []
    for it in items:
        mark = {"completed": "✓", "unmet": "✗", "unverified": "？", "unknown": "－"}[it["status"]]
        line = "- %s %s %s" % (mark, it["id"], it["text"])
        if it["status"] != "completed" and it["note"]:
            line += "　→ " + it["note"]
        lines.append(line)
    return head + "\n" + "\n".join(lines)


def save(book_dir, no, path, text, items, provider):
    d = os.path.join(book_dir, ".studio", "核對")
    os.makedirs(d, exist_ok=True)
    rec = {"chapter": no, "path": path, "hash": text_hash(text), "checked_at": time.time(),
           "provider": provider, "items": items, "summary": summary(items)}
    with open(os.path.join(d, "第%03d章.json" % no), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    return rec


def load(book_dir, no):
    p = os.path.join(book_dir, ".studio", "核對", "第%03d章.json" % no)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        rec = json.load(f)
    full = os.path.join(book_dir, rec.get("path") or "")
    rec["stale"] = not os.path.isfile(full) or text_hash(project.read_text(full)) != rec.get("hash")
    return rec


def target(book_dir, no, prefer_candidate=False):
    order = ("候選", "正文") if prefer_candidate else ("正文", "候選")
    return context.chapter_text(book_dir, no, order)


# ---------------------------------------------------------------------------
# 定稿對帳（寫稿前）
# ---------------------------------------------------------------------------
RECONCILE_SCHEMA = (
    "只輸出一個 JSON 物件：\n"
    '{"final_state": ["和本章有關、已經定稿的事實，一句一條，最多 8 條"], '
    '"events": [{"event": "章綱要求的事件（照清單）", "conflict": true 或 false, '
    '"realization": "與定稿事實一致的寫法；沒有衝突就寫一句落實重點"}]}\n'
    "規則：只根據提供的資料；衝突指章綱要求和已定稿事實（狀態卡、角色狀態、時間線、前文摘要、上一章結尾）互相矛盾，"
    "例如角色不在場、物品不在手上、讀者還不該知道、時間對不上。沒有衝突就 conflict 填 false。")


def parse_reconcile(data):
    if not isinstance(data, dict):
        return None
    fs = data.get("final_state") or []
    if isinstance(fs, dict):
        fs = ["%s：%s" % (k, v) for k, v in fs.items()]
    evs = data.get("events") or []
    if not isinstance(fs, list) or not isinstance(evs, list):
        return None
    fs = [str(x).strip()[:300] for x in fs if str(x).strip()][:8]
    out = []
    for e in evs[:12]:
        if isinstance(e, dict) and str(e.get("event", "")).strip():
            out.append({"event": str(e["event"]).strip()[:200], "conflict": bool(e.get("conflict")),
                        "realization": str(e.get("realization") or "").strip()[:400]})
    if not fs and not out:
        return None
    return {"final_state": fs, "events": out}


def reconcile_block(rec):
    lines = ["【定稿對帳（寫稿前比對結果，必須遵守）】", "已定稿的相關事實："]
    lines += ["- " + x for x in rec["final_state"]] or ["- （無）"]
    lines.append("章綱事件的落實方式：")
    for e in rec["events"]:
        lines.append("- %s%s → %s" % ("【衝突】" if e["conflict"] else "", e["event"], e["realization"]))
    lines.append("有【衝突】的事件，照上面的落實方式寫，並在匯報裡告訴作者這個衝突。")
    return "\n".join(lines)


def reconcile_md(rec):
    conf = [e for e in rec["events"] if e["conflict"]]
    if not conf:
        return "寫稿前對帳：章綱和已定稿事實沒有發現衝突。"
    return "寫稿前對帳發現 %d 個衝突，已照與定稿一致的方式寫：\n%s" % (
        len(conf), "\n".join("- %s → %s" % (e["event"], e["realization"]) for e in conf))
