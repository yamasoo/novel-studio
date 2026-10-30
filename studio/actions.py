# -*- coding: utf-8 -*-
"""工作台按鈕對應的 Claude Code 指令。每個動作回傳 (標題, 提示詞)。
標題一律用中文（介面靠 i18n 翻譯）；提示詞依書的語言取自 studio/prompts/。"""
from . import prompts


def _r(a, b):
    a, b = int(a), int(b or a)
    return (a, b) if a <= b else (b, a)


def _ch(n):
    return "第%03d章" % int(n)


ACTIONS = {
    # ---------------- 開書與專案 ----------------
    "setup_new": {
        "group": "專案", "label": "開書訪談",
        "fields": [{"key": "idea", "label": "初步構想（一句話、一段簡介或關鍵字）", "type": "textarea"}],
    },
    "setup_check": {"group": "專案", "label": "檢查專案結構", "fields": []},
    "style": {
        "group": "專案", "label": "分析／調整文風",
        "fields": [{"key": "text", "label": "貼上寫作樣本，或描述想要的文風", "type": "textarea"}],
    },
    "preference": {
        "group": "專案", "label": "記錄長期偏好",
        "fields": [{"key": "text", "label": "例如：以後對話都不用破折號", "type": "textarea"}],
    },
    # ---------------- 規劃 ----------------
    "concept": {
        "group": "規劃", "label": "故事核心診斷",
        "fields": [{"key": "note", "label": "補充想法（選填）", "type": "textarea"}],
    },
    "master_outline": {
        "group": "規劃", "label": "全書大綱",
        "fields": [{"key": "note", "label": "補充要求（選填）", "type": "textarea"}],
    },
    "volume_outline": {
        "group": "規劃", "label": "卷綱",
        "fields": [{"key": "volume", "label": "第幾卷", "type": "text", "default": "一"},
                   {"key": "note", "label": "補充要求（選填）", "type": "textarea"}],
    },
    "volume_draft": {
        "group": "規劃", "label": "卷綱草稿",
        "fields": [{"key": "volume", "label": "第幾卷", "type": "number"},
                   {"key": "from", "label": "這一卷從第幾章", "type": "number"},
                   {"key": "to", "label": "這一卷到第幾章", "type": "number"},
                   {"key": "note", "label": "補充要求（選填）", "type": "textarea"}],
    },
    "chapter_cards": {
        "group": "規劃", "label": "排章綱",
        "fields": [{"key": "from", "label": "從第幾章", "type": "number"},
                   {"key": "to", "label": "到第幾章", "type": "number"},
                   {"key": "note", "label": "補充要求（選填）", "type": "textarea"}],
    },
    # ---------------- 設定 ----------------
    "character": {
        "group": "設定", "label": "建立／補完角色",
        "fields": [{"key": "name", "label": "角色名", "type": "text"},
                   {"key": "note", "label": "已知資訊（選填）", "type": "textarea"}],
    },
    "gen_drafts": {
        "group": "設定", "label": "生成設定草稿",
        "fields": [{"key": "text", "label": "要生成什麼？例如：3 個第一卷的反派候選", "type": "textarea"}],
    },
    "bible_from_outline": {
        "group": "設定", "label": "從大綱長設定",
        "fields": [{"key": "roles", "label": "角色", "type": "checkbox", "default": True},
                   {"key": "factions", "label": "勢力", "type": "checkbox", "default": True},
                   {"key": "world", "label": "世界觀（地理、科技、戰術…）", "type": "checkbox", "default": True},
                   {"key": "refs", "label": "參考方向（選填）：例如「空中艦作戰參考二戰潛艇」", "type": "textarea"},
                   {"key": "urls", "label": "參考網址（選填，每行一個，會抓內文）", "type": "textarea"}],
    },
    "intake": {
        "group": "設定", "label": "整理內容入庫",
        "fields": [{"key": "text", "label": "貼上和其他 AI 或自己的討論內容", "type": "textarea"}],
    },
    "promote_drafts": {
        "group": "設定", "label": "草稿轉正式",
        "fields": [{"key": "text", "label": "勾選要定案的草稿（沒勾＝只列出）", "type": "drafts"}],
    },
    # ---------------- 寫作 ----------------
    "write": {
        "group": "寫作", "label": "寫章節（候選稿）",
        "fields": [{"key": "from", "label": "從第幾章", "type": "number"},
                   {"key": "to", "label": "到第幾章（最多三章）", "type": "number"},
                   {"key": "note", "label": "這次的特別要求（選填）", "type": "textarea"}],
    },
    "revise": {
        "group": "寫作", "label": "改稿",
        "fields": [{"key": "chapter", "label": "第幾章", "type": "number"},
                   {"key": "note", "label": "要怎麼改", "type": "textarea"}],
    },
    "sync_tracking": {"group": "寫作", "label": "補齊追蹤資料", "fields": []},
    # ---------------- 品質 ----------------
    "review": {
        "group": "品質", "label": "一致性審查",
        "fields": [{"key": "from", "label": "從第幾章", "type": "number"},
                   {"key": "to", "label": "到第幾章", "type": "number"}],
    },
    "review_all": {"group": "品質", "label": "伏筆與角色健康檢查", "fields": []},
    "review_notes": {
        "group": "品質", "label": "單章審查",
        "fields": [{"key": "chapter", "label": "第幾章", "type": "number"},
                   {"key": "candidate", "label": "審查候選稿（而不是正文）", "type": "checkbox"}],
    },
    "revise_notes": {"group": "品質", "label": "依意見修訂", "hidden": True, "fields": []},
    "recover_continue": {"group": "寫作", "label": "續寫恢復稿", "hidden": True, "fields": []},
    "illust_prompt": {"group": "插圖", "label": "產生插圖提示詞", "hidden": True, "fields": []},
    "visual_card": {"group": "插圖", "label": "產生視覺卡", "hidden": True, "fields": []},
    "style_design": {"group": "專案", "label": "設計文風", "hidden": True, "fields": []},
    "reader_init": {"group": "專案", "label": "從時間線建立讀者認知", "hidden": True, "fields": []},
    "reader_reconcile": {"group": "專案", "label": "比對讀者認知回收", "hidden": True, "fields": []},
    "reverse": {"group": "專案", "label": "從正文建立設定", "hidden": True, "fields": []},
    "glossary_org": {"group": "專案", "label": "整理名詞表進設定集", "hidden": True, "fields": []},
    "goal_check": {
        "group": "品質", "label": "章綱核對",
        "fields": [{"key": "chapter", "label": "第幾章", "type": "number"},
                   {"key": "candidate", "label": "核對候選稿（而不是正文）", "type": "checkbox"}],
    },
    "deslop": {
        "group": "品質", "label": "去 AI 味",
        "fields": [{"key": "chapter", "label": "第幾章", "type": "number"},
                   {"key": "candidate", "label": "處理候選稿（而不是正文）", "type": "checkbox"}],
    },
    # ---------------- 自由 ----------------
    "free": {
        "group": "自由", "label": "自由指令",
        "fields": [{"key": "text", "label": "想讓 Claude 做什麼", "type": "textarea"}],
    },
}


def candidate_rule(lang="zh-TW"):
    return prompts.pack(lang)["candidate_rule"]


def build(action, p, book_name, lang="zh-TW"):
    """回傳 (標題, 提示詞)。標題固定中文；提示詞用 lang 指定的語言（書的語言，見 studio/lang.py）。"""
    p = p or {}
    P = prompts.pack(lang)

    def tpl(key, **kw):
        return P[key].format(**kw)

    def rng_of(a, b):
        return tpl("ch_one", a=a) if a == b else tpl("ch_many", a=a, b=b)

    note = (p.get("note") or "").strip()
    extra = tpl("extra", note=note) if note else ""
    rule = P["candidate_rule"]

    if action == "setup_new":
        return ("開書訪談", tpl("setup_new", book=book_name, idea=(p.get("idea") or P["idea_none"]).strip()))
    if action == "setup_check":
        return ("檢查專案結構", tpl("setup_check"))
    if action == "style":
        return ("分析文風", tpl("style", text=p.get("text", "")))
    if action == "preference":
        return ("記錄偏好", tpl("preference", text=p.get("text", "")))

    if action == "concept":
        return ("故事核心診斷", tpl("concept") + extra)
    if action == "master_outline":
        return ("全書大綱", tpl("master_outline") + extra)
    if action == "volume_outline":
        v = (p.get("volume") or "一").strip()
        return ("第%s卷卷綱" % v, tpl("volume_outline", v=v, extra=extra))
    if action == "volume_draft":
        v = str(p.get("volume") or "一").strip()
        a, b = _r(p.get("from") or 1, p.get("to"))
        return ("第%s卷卷綱草稿" % v, tpl("volume_draft", v=v, a=a, b=b, extra=extra))
    if action == "chapter_cards":
        a, b = _r(p.get("from") or 1, p.get("to"))
        if p.get("auto"):   # 整章自動流程：不先給總覽，直接寫入
            rng = "第%d章" % a if a == b else "第%d～%d章" % (a, b)
            return ("寫%s章綱" % rng, tpl("cards_auto", rng=rng_of(a, b), extra=extra))
        return ("排章綱 %d～%d" % (a, b), tpl("cards", a=a, b=b, extra=extra))

    if action == "character":
        name = (p.get("name") or "").strip()
        return ("角色：%s" % name, tpl("character", name=name, extra=extra))
    if action == "gen_drafts":
        return ("生成設定草稿", tpl("gen_drafts", text=p.get("text", "")))
    if action == "bible_from_outline":
        parts = []
        if p.get("roles", True):
            parts.append("角色")
        if p.get("factions", True):
            parts.append("勢力")
        if p.get("world", True):
            parts.append("世界觀")
        return ("從大綱長設定", tpl("bible_from_outline", scope="、".join(parts) or "角色",
                                   refs=(p.get("refs") or "").strip(),
                                   urls=(p.get("urls") or "").strip()))
    if action == "intake":
        return ("整理入庫", tpl("intake", text=p.get("text", "")))
    if action == "promote_drafts":
        return ("草稿轉正式", tpl("promote", text=p.get("text", "")))

    if action == "write":
        a, b = _r(p.get("from"), p.get("to"))
        b = min(b, a + 2)
        rng = "第%d章" % a if a == b else "第%d～%d章" % (a, b)
        return ("寫%s" % rng, tpl("write", rng=rng_of(a, b), rule=rule, extra=extra))
    if action == "revise":
        n = int(p.get("chapter"))
        return ("改第%d章" % n, tpl("revise", n=n, ch=_ch(n), note=note or P["revise_note_none"]))
    if action == "sync_tracking":
        return ("補齊追蹤", tpl("sync_tracking"))

    if action == "review":
        a, b = _r(p.get("from") or 1, p.get("to"))
        rng = "第%d章" % a if a == b else "第%d～%d章" % (a, b)
        return ("審查%s" % rng, tpl("review", rng=rng_of(a, b)))
    if action == "review_all":
        return ("健康檢查", tpl("review_all"))
    if action == "deslop":
        n = int(p.get("chapter"))
        where = "候選/" if p.get("candidate") else "正文/"
        return ("去AI味 第%d章" % n, tpl("deslop", where=where, ch=_ch(n), n=n, extra=extra))

    if action == "free":
        return ("自由指令", p.get("text", ""))
    if action == "style_design":
        return ({"revise": "調整文風", "test": "試寫文風"}.get(p.get("mode"), "設計文風") + "：%s" % (p.get("name") or ""),
                "（由工作台組裝）")
    if action in ("illust_prompt", "visual_card"):
        return ("產生插圖提示詞" if action == "illust_prompt" else "產生視覺卡：%s" % (p.get("file") or "").rsplit("/", 1)[-1][:-3],
                "（由工作台組裝）")
    if action in ("review_notes", "revise_notes", "recover_continue"):
        return ({"review_notes": "審查第%s章", "revise_notes": "修訂第%s章", "recover_continue": "續寫恢復稿%s"}[action]
                % (p.get("chapter") or ""), "（由工作台組裝）")
    if action == "goal_check":
        return ("核對第%s章章綱" % p.get("chapter"), "（由工作台組裝）")
    if action == "reader_init":
        return ("從時間線建立讀者認知", "（由工作台組裝）")
    if action == "reader_reconcile":
        return ("比對讀者認知回收", "（由工作台組裝）")
    if action == "glossary_org":
        return ("整理名詞表進設定集", "（由工作台組裝）")
    if action == "reverse":
        return ("從正文建立設定%s" % ("（到第%s章）" % p["upto"] if p.get("upto") else ""), "（由工作台組裝）")

    # 內部動作
    if action == "accept":
        n = int(p.get("chapter"))
        return ("採用第%d章並回寫" % n, tpl("accept", n=n, path=p.get("path")))
    if action == "reject":
        n = int(p.get("chapter"))
        return ("重寫第%d章候選稿" % n, tpl("reject", n=n, ch=_ch(n), note=note or P["reject_note_none"], rule=rule))
    raise KeyError(action)


def catalog():
    return [{"id": k, "group": v["group"], "label": v["label"], "fields": v["fields"], "hidden": v.get("hidden", False)}
            for k, v in ACTIONS.items()]
