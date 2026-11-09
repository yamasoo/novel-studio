# -*- coding: utf-8 -*-
"""開書前段與卷層的狀態判定：開書進度六步、卷層進度、下一步、以及「開書報告」的檔案檢查。

三個地方共用同一份判定，所以「報告卡的下一步」與「總覽的 primary」永遠是同一個動作：
- app.py 的 GET /api/books/{book}/overview（ov["setup"]／ov["steps"]／ov["next_step"]）
- app.py 的 GET /api/books/{book}/setup_report（面板的開書報告卡）
- studio/native_files.py 的 setup_new 收尾敘述

判定一律看實際檔案（存在、內容、frontmatter），不看模型自述。

卷層（第二卷之後）：範圍一律以正式卷綱 frontmatter 的「章節範圍」為準（`volume.find`），
沒有卷綱就當單卷、開放到最後一章；「卷末體檢做過了嗎」只看卷綱檔尾的更新草稿或
`大綱/草稿/卷綱更新_第a-b章.md`，不另外存狀態檔。
"""
import json
import os

from . import project, volume

CORE = "設定/故事核心.md"
STYLE = "設定/文風.md"
MASTER = "大綱/全書大綱.md"
VOLUME_FILES = ("大綱/卷綱_第1卷.md", "大綱/卷一卷綱.md", "大綱/卷綱_第一卷.md")
CARD_DIR = "大綱/章綱"
CHAR_DIR = "設定/角色"
FACTION_DIR = "設定/勢力"
WORLD_DIR = "設定/世界觀"
BIBLE_DRAFT_DIR = "設定/草稿"
MIN_CHARACTERS = 3          # 初始設定過關的角色正式檔門檻

# 六步：id 給前端當 key，action／prefill 給 Panel.openForm 用（go 給換頁型步驟用）
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
    {"id": "settings", "label": "初始設定", "action": "bible_from_outline", "prefill": {},
     "desc": "角色至少 3 個正式檔、勢力或世界觀至少一個：先從大綱長設定草稿，再把草稿轉正式。"},
]

WRITE_STEP = {"id": "write", "label": "寫第 1 章", "action": "write", "prefill": {"from": 1, "to": 1},
              "desc": "前六步都完成了，可以開始寫正文。"}


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


def _entries(book_dir, rel):
    """資料夾裡的正式檔（.md）；資料夾不存在就回空清單。"""
    d = os.path.join(book_dir, *rel.split("/"))
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".md"))


def settings_state(book_dir):
    """初始設定：角色正式檔 ≥ 3，且勢力或世界觀至少一個非空檔。

    草稿（設定/草稿/）不算完成——要按「草稿轉正式」才會變成角色／勢力／世界觀；
    這裡同時回草稿數，讓下一步卡可以說「N 份草稿等你轉正式」。
    """
    chars = _entries(book_dir, CHAR_DIR)
    factions = _entries(book_dir, FACTION_DIR)
    worlds = _entries(book_dir, WORLD_DIR)
    return {
        "characters": len(chars),
        "factions": len(factions),
        "worlds": len(worlds),
        "drafts": len(_entries(book_dir, BIBLE_DRAFT_DIR)),
        "min_characters": MIN_CHARACTERS,
        "done": len(chars) >= MIN_CHARACTERS and bool(factions or worlds),
    }


def _volume_step_done(book_dir):
    for rel in VOLUME_FILES:
        text = _read(book_dir, rel)
        if text and project.count_chars(text) >= 120:
            return True
    return False


def _cards_step_done(book_dir):
    """前 10 章章綱：≥ 10 個章綱檔，或**第一卷的章節範圍已經排滿章綱**。

    第二個條件是給「第一卷不到 10 章」的書：不然 6 章一卷的書永遠過不了這一步，
    卡在「排第 1–10 章章綱」而寫不了第 1 章。
    """
    d = os.path.join(book_dir, *CARD_DIR.split("/"))
    have = {c["no"] for c in project.scan_chapters(book_dir) if c.get("card_file")}
    if os.path.isdir(d) and len([f for f in os.listdir(d) if f.endswith(".md")]) >= 10:
        return True
    if not have:
        return False
    vol = volume.find(book_dir, 1) or volume.find(book_dir, min(have))
    if vol and vol.get("lo") and vol.get("hi") and vol["lo"] <= 1 <= vol["hi"]:
        return all(n in have for n in range(vol["lo"], vol["hi"] + 1))
    return False


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
    if step_id == "settings":
        return settings_state(book_dir)["done"]
    return False


def steps(book_dir):
    """六步的完成狀態；current＝第一個還沒完成的步驟。"""
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


def _has_text(book_dir):
    """這本書有沒有正文了（有的話初始設定不擋寫作）。"""
    return any(c.get("text_file") for c in project.scan_chapters(book_dir))


def volume_state(book_dir):
    """這一卷的範圍與進度：範圍來自正式卷綱的「章節範圍」，沒有卷綱就是單卷。

    回傳 lo/hi（章節範圍）、total（這一卷幾章）、written（已寫幾章）、planned（有章綱幾章）、
    missing_cards（還缺幾章章綱）、full（寫滿了沒）、no/name/rel（卷號、卷名、卷綱相對路徑）。
    單卷模式 no=0、rel=""、name=""，full 一律 False（沒有界線就沒有「寫滿」）。
    """
    chs = project.scan_chapters(book_dir)
    written = sorted(c["no"] for c in chs if c.get("text_file"))
    planned = sorted(c["no"] for c in chs if c.get("card_file"))
    next_no = (written[-1] + 1) if written else ((planned[-1] + 1) if planned else 1)
    # 先看下一個要寫的章（它可能已經屬於下一卷），再退回來看最後一章／最後一張章綱，
    # 這樣「章綱排到第 12 章、還沒開始寫」的書也會落在第一卷，而不是掉進單卷模式。
    vol = None
    for probe in (next_no, next_no - 1, written[-1] if written else None, planned[-1] if planned else None):
        if probe:
            vol = volume.find(book_dir, probe)
            if vol:
                break
    if vol and vol.get("lo") and vol.get("hi"):
        lo, hi = int(vol["lo"]), int(vol["hi"])
        no, name, rel, mode = int(vol.get("no") or 0), str(vol.get("name") or ""), str(vol["rel"]), "卷綱"
    else:
        lo = min(planned) if planned else next_no
        hi = max(planned) if planned else next_no
        no, name, rel, mode = 0, "", "", "單卷"
    total = hi - lo + 1
    w = len([n for n in written if lo <= n <= hi])
    p = len([n for n in planned if lo <= n <= hi])
    return {
        "mode": mode, "no": no, "name": name, "rel": rel, "lo": lo, "hi": hi,
        "total": total, "written": w, "planned": p,
        "missing_cards": max(0, total - p),
        "full": bool(mode == "卷綱" and total > 0 and w >= total),
        "next_no": next_no,
    }


def _volume_checked(book_dir, vol):
    """這一卷做過卷末體檢了嗎：卷綱檔尾已有更新草稿，或 大綱/草稿/ 裡有對應的更新草稿。"""
    text = _read(book_dir, vol["rel"]) if vol.get("rel") else None
    if text and "卷綱更新草稿" in text:
        return True
    return _read(book_dir, "大綱/草稿/卷綱更新_第%d-%d章.md" % (vol["lo"], vol["hi"])) is not None


def _plain_write_next(book_dir):
    """舊書（已經有正文）而且沒有正式卷綱：沿用原本的「寫第 N 章」，不要冒出章綱或卷層步驟。"""
    nxt = dict(WRITE_STEP)
    chs = project.scan_chapters(book_dir)
    written = [c["no"] for c in chs if c.get("text_file")]
    if written:
        nxt["prefill"] = {"from": max(written) + 1, "to": max(written) + 1}
        nxt["label"] = "寫第 %d 章" % (max(written) + 1)
    return nxt


def _volume_next(book_dir):
    """六步之後的下一步：卷末體檢 → 下一卷卷綱 → 排章綱 → 寫第 N 章（依序）。"""
    vol = volume_state(book_dir)
    if vol["mode"] != "卷綱" and _has_text(book_dir):
        return _plain_write_next(book_dir)
    if vol["full"] and not _volume_checked(book_dir, vol):
        return {"id": "volume_end", "label": "卷末體檢（第%d–%d章）" % (vol["lo"], vol["hi"]),
                "action": None, "go": "/drift?from=%d&to=%d" % (vol["lo"], vol["hi"]),
                "prefill": {}, "cta": "開始卷末體檢",
                "desc": "這一卷寫滿了。先看漂移與伏筆，需要時再用更新草稿改卷綱。"}
    if vol["full"]:
        no, start = (vol["no"] or 0) + 1, vol["hi"] + 1
        cn = volume.cn_no(no)
        return {"id": "volume_next", "label": "第%s卷卷綱" % cn,
                "action": "volume_draft", "prefill": {"volume": cn, "from": start, "to": start + 9},
                "desc": "上一卷寫滿了。先把第%s卷的卷綱定下來（第%d 章起），再排這一卷的章綱。" % (cn, start)}
    chs = project.scan_chapters(book_dir)
    have = {c["no"] for c in chs if c.get("card_file") or c.get("text_file")}
    written = {c["no"] for c in chs if c.get("text_file")}
    gap = [n for n in range(vol["lo"], vol["hi"] + 1) if n not in have]
    if gap:
        a = gap[0]
        b = min(vol["hi"], a + 9)
        return {"id": "cards", "label": "排第%d–%d章的章綱" % (a, b),
                "action": "chapter_cards", "prefill": {"from": a, "to": b},
                "desc": "這一卷（第%d–%d章）還有 %d 章沒有章綱。" % (vol["lo"], vol["hi"], len(gap))}
    # 下一個要寫的章：這一卷裡第一張沒寫的（不是「最後一章 + 1」，中間跳章也不會跳過）
    need = [n for n in range(vol["lo"], vol["hi"] + 1) if n not in written]
    no = need[0] if need else max(vol["hi"] + 1, vol["next_no"])
    nxt = dict(WRITE_STEP)
    nxt["label"] = "寫第 %d 章" % no
    nxt["prefill"] = {"from": no, "to": no}
    return nxt


def next_step(book_dir):
    """下一步：第一個沒完成的步驟；六步都完成就交給卷層（體檢／下一卷／章綱／寫文）。

    已經有正文的書（舊書）不讓「初始設定」擋路：那一步只在還沒開始寫的書上排隊。
    """
    writing = _has_text(book_dir)
    for s in STEPS:
        if s["id"] == "settings" and writing:
            continue
        if not _step_done(book_dir, s["id"]):
            return dict(s)
    return _volume_next(book_dir)


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
