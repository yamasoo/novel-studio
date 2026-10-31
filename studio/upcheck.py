# -*- coding: utf-8 -*-
"""設定 vs 內容的檢查：提前登場、久別重逢。

兩個地方共用同一套規則：
  - `tools/contract_audit.py`（正文寫完之後掃）
  - `tools/card_audit.py` 與整章自動流程的前置檢查（章綱排好、正文還沒寫時先掃）

「未登記角色」目前沒有實作（說明有寫，程式只比對 `設定/角色/` 已登記的角色），
所以這裡不會回報新名字。
"""
import os
import re

from . import context, contract, project

SPOILER_GAP = 15   # 「提前登場」：只是被提到很正常，差 15 章以上才算劇透風險
IDLE_GAP = 30      # 「久別重逢」：最後登場之後 30 章又出現（只看主角／配角）
KEEP_ROLES = ("主角", "主要配角", "配角")

# 章綱的「禁止事項」是給作者／模型的限制（例如「某角色不得登場」），
# 裡面的名字不是本章內容；掃章綱時要先整段拿掉，不然會把「不准提到」誤判成「提前提到」。
FORBIDDEN_SECTION = re.compile(
    r"^##\s*(?:[0-9一二三四五六七八九十]+[、.．]\s*)?禁止事[項项][^\n]*$.*?(?=^##\s|\Z)",
    re.M | re.S)


def _without_forbidden(text):
    return FORBIDDEN_SECTION.sub("", text or "")



def _num(v):
    m = re.search(r"\d+", str(v or ""))
    return int(m.group(0)) if m else None


def conflicts(book_dir, no, text, chars=None):
    """一段文字（一章）和角色設定對照，回傳 [{chapter, name, kind, detail}]。"""
    if chars is None:
        chars = contract.characters(book_dir)
    out = []
    for name, pos, first, last in chars:
        if not name or len(name) < 2 or name not in text:
            continue
        f, l = _num(first), _num(last)
        if f and no < f and f - no >= SPOILER_GAP:
            out.append({"chapter": no, "name": name, "kind": "提前登場",
                        "detail": "設定的首次登場是第%d章，但第%d章就提到（早了 %d 章）" % (f, no, f - no)})
        elif l and no > l + IDLE_GAP and any(k in str(pos or "") for k in KEEP_ROLES):
            out.append({"chapter": no, "name": name, "kind": "久別重逢",
                        "detail": "最後登場記在第%d章，第%d章又出現（差了 %d 章）" % (l, no, no - l)})
    return out


def findings(book_dir, start, end, cards=False):
    """掃一段章節的衝突。

    cards=True：掃 大綱/章綱（正文還沒寫也能先檢查）；False：掃 正文。
    回傳 [{chapter, name, kind, detail, source}]，source 是 章綱 或 正文。
    """
    start, end = int(start), int(end)
    chars = contract.characters(book_dir)
    out = []
    if cards:
        for no in range(start, end + 1):
            _rel, text = context.card_text(book_dir, no)
            if not (text or "").strip():
                continue
            for c in conflicts(book_dir, no, _without_forbidden(text), chars):
                c["source"] = "章綱"
                out.append(c)
        return out
    ch = project._scan_dir(os.path.join(book_dir, "正文"))
    for no in sorted(n for n in ch if start <= n <= end):
        text = project.split_frontmatter(project.read_text(os.path.join(book_dir, "正文", ch[no])))[1]
        for c in conflicts(book_dir, no, text, chars):
            c["source"] = "正文"
            out.append(c)
    return out


def summary(rows):
    """給訊息用的一句：第 12、13 章「某某」提前登場（共 2 處）。"""
    if not rows:
        return ""
    parts = ["第%d章「%s」%s" % (r["chapter"], r["name"], r["kind"]) for r in rows[:3]]
    more = "…" if len(rows) > 3 else ""
    return "、".join(parts) + more + "（共 %d 處）" % len(rows)
