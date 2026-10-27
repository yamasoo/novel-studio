# -*- coding: utf-8 -*-
"""工作台按鈕對應的 Claude Code 指令。每個動作回傳 (標題, 提示詞)。"""


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
    "intake": {
        "group": "設定", "label": "整理內容入庫",
        "fields": [{"key": "text", "label": "貼上和其他 AI 或自己的討論內容", "type": "textarea"}],
    },
    "promote_drafts": {
        "group": "設定", "label": "草稿轉正式",
        "fields": [{"key": "text", "label": "哪些草稿要定案（名稱）", "type": "text"}],
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

CANDIDATE_RULE = (
    "【寫稿前對帳】動筆前先把章綱的每個情節點和已定稿事實（狀態卡、角色狀態、時間線、上一章結尾）逐條比對，"
    "有衝突就採用與定稿一致的寫法，並在匯報列出衝突與你的處理方式。\n"
    "【候選稿模式】這次由作者在工作台審稿：依 novel-write 的「候選稿模式」執行——"
    "正文寫進 `候選/第NNN章_章名.md`（不是 正文/），做完自查與新增物申報後就停止並匯報，"
    "不要回寫追蹤、不要更新章綱狀態、不要 git 提交。作者在介面按「採用」後，會另外請你回寫。"
)


def build(action, p, book_name):
    p = p or {}
    note = (p.get("note") or "").strip()
    extra = ("\n作者補充：" + note) if note else ""

    if action == "setup_new":
        return ("開書訪談", "請使用 novel-setup skill，在目前資料夾為新書《%s》建立小說專案。"
                "目前資料夾就是書目錄，直接在這裡建，不要再建子資料夾。\n"
                "作者的初步構想：%s\n照訪談流程一輪一輪問我，先問第一輪。"
                % (book_name, (p.get("idea") or "（還沒有，請引導我）").strip()))
    if action == "setup_check":
        return ("檢查專案結構", "請使用 novel-setup skill 檢查目前這個小說專案：缺哪些資料夾或範本、哪些核心檔案還是空白。缺的範本補上，不要覆蓋既有內容。")
    if action == "style":
        return ("分析文風", "請使用 novel-style skill 分析、設計或調整本書文風（設定/文風.md）。"
                "作者貼的是寫作樣本就照「分析樣本」做；是描述就照「從描述設計」或「依意見修改」做。不要提問，不確定的地方在匯報列出。\n"
                "作者提供的內容：\n%s" % p.get("text", ""))
    if action == "preference":
        return ("記錄偏好", "請使用 novel-setup skill 記錄作者的長期偏好到 設定/作者偏好.md：\n%s" % p.get("text", ""))

    if action == "concept":
        return ("故事核心診斷", "請使用 novel-outline skill 做故事核心診斷，並更新 設定/故事核心.md。" + extra)
    if action == "master_outline":
        return ("全書大綱", "請使用 novel-outline skill 規劃全書大綱（大綱/全書大綱.md）。先給我看分卷總覽，確認後再寫入。" + extra)
    if action == "volume_outline":
        v = (p.get("volume") or "一").strip()
        return ("第%s卷卷綱" % v, "請使用 novel-outline skill 規劃第%s卷的卷綱。先給我看卷契約和劇情單元總覽，確認後再寫入。%s" % (v, extra))
    if action == "chapter_cards":
        a, b = _r(p.get("from") or 1, p.get("to"))
        if p.get("auto"):   # 整章自動流程：不先給總覽，直接寫入
            rng = "第%d章" % a if a == b else "第%d～%d章" % (a, b)
            return ("寫%s章綱" % rng, "請使用 novel-outline skill 寫%s的章綱，直接寫入 大綱/章綱/（照章綱範本，frontmatter 狀態填「已確認」），"
                    "不用先給我看總覽。依卷綱與前一章章綱接續；回收重要伏筆、新的大反轉或新角色時，選最保守、和既有設定一致的做法，在匯報列出。%s" % (rng, extra))
        return ("排章綱 %d～%d" % (a, b), "請使用 novel-outline skill 排第%d～%d章的章綱。先給我看單元總覽表（一章一行），我確認後再寫入各章檔案。%s" % (a, b, extra))

    if action == "character":
        name = (p.get("name") or "").strip()
        return ("角色：%s" % name, "請使用 novel-bible skill 建立或補完角色「%s」。%s" % (name, extra))
    if action == "gen_drafts":
        return ("生成設定草稿", "請使用 novel-bible skill 生成設定草稿，全部放 設定/草稿/：\n%s" % p.get("text", ""))
    if action == "intake":
        return ("整理入庫", "請使用 novel-bible skill，把下面的內容整理入庫（照從對話萃取的規則：已定案→正式，討論中→草稿）：\n\n%s" % p.get("text", ""))
    if action == "promote_drafts":
        return ("草稿轉正式", "請使用 novel-bible skill，把以下設定草稿轉為正式：%s" % p.get("text", ""))

    if action == "write":
        a, b = _r(p.get("from"), p.get("to"))
        b = min(b, a + 2)
        rng = "第%d章" % a if a == b else "第%d～%d章" % (a, b)
        return ("寫%s" % rng, "請使用 novel-write skill 寫%s。\n%s%s" % (rng, CANDIDATE_RULE, extra))
    if action == "revise":
        n = int(p.get("chapter"))
        return ("改第%d章" % n, "請使用 novel-write skill 的改稿流程修改第%d章（正文/%s_*.md）。\n作者的要求：%s" % (n, _ch(n), note or "（未說明，請先問我）"))
    if action == "sync_tracking":
        return ("補齊追蹤", "請使用 novel-write skill：檢查 追蹤/狀態卡.md 的「更新至」，對所有已在 正文/ 但追蹤還沒回寫的章節，依序執行第七步回寫追蹤，然後匯報。")

    if action == "review":
        a, b = _r(p.get("from") or 1, p.get("to"))
        rng = "第%d章" % a if a == b else "第%d～%d章" % (a, b)
        return ("審查%s" % rng, "請使用 novel-review skill 審查%s，輸出審查報告。不要直接修改正文。" % rng)
    if action == "review_all":
        return ("健康檢查", "請使用 novel-review skill 做全書檢查，重點是清單 B：設定一致性、追蹤是否跟上正文、伏筆健康度、角色久未登場、資訊揭露邊界、讀者契約與節奏。不要讀全部正文，以摘要與追蹤為主。")
    if action == "deslop":
        n = int(p.get("chapter"))
        where = "候選/" if p.get("candidate") else "正文/"
        return ("去AI味 第%d章" % n, "請使用 novel-deslop skill 處理 %s%s_*.md（第%d章）：先跑檢查腳本、修必須修的項目，再處理語意層的 AI 味。不要改動劇情事實。%s" % (where, _ch(n), n, extra))

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

    # 內部動作
    if action == "accept":
        n = int(p.get("chapter"))
        return ("採用第%d章並回寫" % n, "作者已在工作台採用第%d章，正文已移到 %s。請使用 novel-write skill，從第七步「回寫追蹤」開始執行（章節摘要、狀態卡、角色狀態、伏筆、時間線、設定登記、章綱狀態、git 提交），完成後簡短匯報。" % (n, p.get("path")))
    if action == "reject":
        n = int(p.get("chapter"))
        return ("重寫第%d章候選稿" % n, "作者退回了第%d章的候選稿（候選/%s_*.md）。\n作者的意見：%s\n請使用 novel-write skill 依意見改寫這份候選稿，仍然只寫在 候選/，不要回寫追蹤。改完匯報改了哪些地方。\n%s" % (n, _ch(n), note or "（未說明）", CANDIDATE_RULE))
    raise KeyError(action)


def catalog():
    return [{"id": k, "group": v["group"], "label": v["label"], "fields": v["fields"], "hidden": v.get("hidden", False)}
            for k, v in ACTIONS.items()]
