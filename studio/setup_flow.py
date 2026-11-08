# -*- coding: utf-8 -*-
"""開書前段的狀態判定：開書進度五步、下一步、以及「開書報告」的檔案檢查。

三個地方共用同一份判定，所以「報告卡的下一步」與「總覽的 primary」永遠是同一個動作：
- app.py 的 GET /api/books/{book}/overview（ov["setup"]／ov["steps"]／ov["next_step"]）
- app.py 的 GET /api/books/{book}/setup_report（面板的開書報告卡）
- studio/native_files.py 的 setup_new 收尾敘述

判定一律看實際檔案（存在、內容、frontmatter），不看模型自述。
"""
import json
import os

from . import project

CORE = "設定/故事核心.md"
STYLE = "設定/文風.md"
MASTER = "大綱/全書大綱.md"
VOLUME_FILES = ("大綱/卷綱_第1卷.md", "大綱/卷一卷綱.md", "大綱/卷綱_第一卷.md")
CARD_DIR = "大綱/章綱"

# 五步：id 給前端當 key，action／prefill 給 Panel.openForm 用
STEPS = [
    {"id": "setup", "label": "開書訪談", "action": "setup_new", "prefill": {},
     "desc": "三份核心檔案要先有內容：CLAUDE.md、故事核心、文風。"},
    {"id": "concept", "label": "故事核心", "action": "concept", "prefill": {},
     "desc": "一句話說清楚主角要什麼、被什麼擋住，大約 1 分鐘。"},
    {"id": "master", "label": "全書大綱", "action": "master_outline", "prefill": {},
     "desc": "全書分成幾個大段、主角怎麼被推到終局，大約 3–5 分鐘。"},
    {"id": "volume", "label": "第一卷卷綱", "action": "volume_draft",
     "prefill": {"volume": "一", "from": 1, "to": 10},
     "desc": "第一卷的對手、卷末變化與劇情單元。"},
    {"id": "cards", "label": "前 10 章章綱", "action": "chapter_cards", "prefill": {"from": 1, "to": 10},
     "desc": "排第 1–10 章的章綱，排完就能開始寫。"},
]

WRITE_STEP = {"id": "write", "label": "寫第 1 章", "action": "write", "prefill": {"from": 1, "to": 1},
              "desc": "前五步都完成了，可以開始寫正文。"}


def _read(book_dir, rel):
    p = os.path.join(book_dir, *rel.split("/"))
    if not os.path.isfile(p):
        return None
    try:
        return project.read_text(p) or ""
    except OSError:
        return None


def _filled(text, min_chars):
    """有內容、而且不是還沒填的範本（範本註解 <!-- … --> 還在就算沒填）。"""
    if text is None:
        return False
    _, body = project.split_frontmatter(text)
    if "<!--" in body:
        return False
    return project.count_chars(text) >= min_chars


def _volume_step_done(book_dir):
    for rel in VOLUME_FILES:
        text = _read(book_dir, rel)
        if text and project.count_chars(text) >= 120:
            return True
    return False


def _cards_step_done(book_dir):
    d = os.path.join(book_dir, *CARD_DIR.split("/"))
    if not os.path.isdir(d):
        return False
    return len([f for f in os.listdir(d) if f.endswith(".md")]) >= 10


def _step_done(book_dir, step_id):
    if step_id == "setup":
        return project.is_book(book_dir)
    if step_id == "concept":
        return _filled(_read(book_dir, CORE), 120)
    if step_id == "master":
        return _filled(_read(book_dir, MASTER), 500)
    if step_id == "volume":
        return _volume_step_done(book_dir)
    if step_id == "cards":
        return _cards_step_done(book_dir)
    return False


def steps(book_dir):
    """五步的完成狀態；current＝第一個還沒完成的步驟。"""
    out = []
    current = None
    for s in STEPS:
        done = _step_done(book_dir, s["id"])
        if not done and current is None:
            current = s["id"]
        out.append({"id": s["id"], "label": s["label"], "done": done})
    for row in out:
        row["current"] = row["id"] == current
    return out


def next_step(book_dir):
    """下一步：第一個沒完成的步驟；五步都完成就是「寫第 1 章」。"""
    for s in STEPS:
        if not _step_done(book_dir, s["id"]):
            return dict(s)
    nxt = dict(WRITE_STEP)
    # 已經寫過章節的書：沿用原本的「下一章」寫法
    chs = project.scan_chapters(book_dir)
    written = [c["no"] for c in chs if c["text_file"]]
    if written:
        nxt["prefill"] = {"from": max(written) + 1, "to": max(written) + 1}
        nxt["label"] = "寫第 %d 章" % (max(written) + 1)
    return nxt


def _had_setup_job(book_dir):
    """這本書以前有沒有跑過開書訪談（.studio/jobs 裡有 setup_new 的紀錄）。"""
    d = os.path.join(book_dir, ".studio", "jobs")
    if not os.path.isdir(d):
        return False
    for f in os.listdir(d):
        if not f.endswith(".json") or f.endswith(".messages.json"):
            continue
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                meta = (json.load(fh) or {}).get("meta") or {}
        except (OSError, ValueError):
            continue
        if meta.get("action") == "setup_new":
            return True
    return False


def interview_state(book_dir, running_job=None):
    """開書訪談的狀態：interviewing（有任務在跑）／interrupted（沒有 CLAUDE.md 也沒在跑）／none。"""
    meta = {}
    params = {}
    if running_job is not None:
        meta = (running_job.meta or {}) if hasattr(running_job, "meta") else (running_job.get("meta") or {})
        params = meta.get("params") or {}
    answers = params.get("answers") or {}
    if running_job is not None and meta.get("action") == "setup_new":
        state = "interviewing"
    elif answers and not project.is_book(book_dir):
        state = "interrupted"
    elif not project.is_book(book_dir):
        # 開始過訪談（有答案或有任務紀錄）但沒有 CLAUDE.md → 中斷，不是「還沒開始」
        state = "interrupted" if (answers or _had_setup_job(book_dir)) else "none"
    else:
        state = "none"
    return {
        "state": state,
        "job_id": (getattr(running_job, "id", None) if running_job is not None else None),
        "provider_type": ((running_job.provider or {}).get("type")
                          if running_job is not None and hasattr(running_job, "provider") else ""),
        "answered": len([k for k, v in answers.items() if v]),
        "answers": answers,
    }


def _file_row(book_dir, rel, label):
    text = _read(book_dir, rel)
    if text is None:
        return {"path": rel, "label": label, "exists": False, "ok": False, "chars": 0, "note": "待補（檔案不存在）"}
    _, body = project.split_frontmatter(text)
    chars = project.count_chars(text)
    pending = "<!--" in body
    ok = bool(chars) and not pending
    note = ""
    if "<!--" in body:
        note = "待補（範本註解還沒填完）"
    elif not chars:
        note = "待補（只有標題，沒有內容）"
    return {"path": rel, "label": label, "exists": True, "ok": ok, "chars": chars, "note": note}


def report(book_dir, meta=None):
    """開書報告：程式檢查的三份檔案 ＋ 作者選擇「跳過，你決定」的題目 ＋ 下一步。"""
    params = (meta or {}).get("params") or {}
    answers = params.get("answers") or {}
    files = [_file_row(book_dir, "CLAUDE.md", "本書規則"),
             _file_row(book_dir, CORE, "故事核心"),
             _file_row(book_dir, STYLE, "文風")]
    defaults = [{"q": v.get("q") or k, "key": k} for k, v in answers.items() if isinstance(v, dict) and v.get("default")]
    pending = [f["label"] for f in files if not f["ok"]]
    return {
        "files": files,
        "created": [f["path"] for f in files if f["ok"]],
        "pending": pending,
        "defaults": defaults,
        "next": next_step(book_dir),
        "steps": steps(book_dir),
    }


def report_md(book_dir, meta=None):
    """同一份報告的文字版（放進任務結果，面板收合時也看得到）。"""
    r = report(book_dir, meta)
    lines = ["**開書報告（程式檢查檔案）**"]
    lines.append("已建立：" + ("、".join(p for p in r["created"]) if r["created"] else "（沒有）"))
    if r["pending"]:
        lines.append("待補：" + "、".join(r["pending"]))
    if r["defaults"]:
        lines.append("（預設）由模型決定：" + "、".join(d["q"] for d in r["defaults"]))
    nxt = r["next"]
    lines.append("下一步：%s%s" % (nxt["label"], ("——" + nxt["desc"]) if nxt.get("desc") else ""))
    return "\n".join(lines)
