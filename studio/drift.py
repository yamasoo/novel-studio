# -*- coding: utf-8 -*-
"""大綱漂移偵測：卷末（或每 10 章）回頭看「實際寫出來的」和「大綱說要寫的」差在哪。

四件事，全部不花錢、只看已經存在的檔案：
  1. 章綱沒寫到：每章章綱的罕見用詞有多少沒出現在正文（低覆蓋的章節 + 沒寫到的詞）
  2. 角色消失：設定裡的角色最後一次登場離現在多久（預設 20 章沒出現就列出）
  3. 伏筆欠帳：還沒回收的伏筆，埋設章離現在多久（預設 30 章）
  4. 文風漂移：每章偏離本書文風的幅度（偏離值），挑出超過門檻的章節與指標

可選的 LLM 輕量版（--provider）：只送章節摘要與卷綱（不送全文），請模型找
「情節點沒寫到／新增事件沒進大綱／角色消失」，並產出「更新卷綱」草稿。
"""
import os
import re

from . import contract, project, prompts, recall, shared, style_loop, volume

IDLE_CHARS = 20      # 幾章沒登場算「消失」
THREAD_AGE = 30      # 伏筆埋設後幾章還沒回收算「欠帳」
LOW_COVER = 0.20     # 章綱覆蓋率低於這個就列出
KEEP_ROLES = ("主角", "主要配角", "配角")     # 反派／怪物／一次性角色不算「消失」
# 章綱分段：情節點是「要寫到的內容」；出場角色與伏筆操作另外處理（一個查名字、一個是簿記）
PLOT_HEADS = ("情節點", "章末鉤子", "場景", "衝突", "轉折")
NAME_HEAD = "出場角色"
META_RX = re.compile(r"章|主角|讀者|目標|禁忌|注意|情緒|場景|資訊|邊界|伏筆|全書|本卷|情節|節奏")


def sections_of_card(card):
    """章綱 → {段落標題: 內容}。"""
    out, head = {}, None
    for line in (card or "").splitlines():
        if line.startswith("#"):
            head = line.lstrip("#").strip()
            out.setdefault(head, [])
            continue
        if head:
            out[head].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def content_of_card(card):
    """只取「要寫到的內容」：情節點、章末鉤子、場景…（不含出場角色名單與伏筆簿記）。"""
    sec = sections_of_card(card)
    parts = [v for k, v in sec.items() if any(h in k for h in PLOT_HEADS)]
    return "\n".join(parts).strip() or (card or "")


def card_names(card):
    """章綱「出場角色」段落點名的角色。"""
    sec = sections_of_card(card)
    for k, v in sec.items():
        if NAME_HEAD in k:
            return [ln.strip().lstrip("-* ").strip() for ln in v.splitlines() if ln.strip()]
    return []


def _card(book_dir, no):
    p = project._scan_dir(os.path.join(book_dir, "大綱", "章綱")).get(no)
    if not p:
        return ""
    return project.split_frontmatter(project.read_text(os.path.join(book_dir, "大綱", "章綱", p)))[1]


def _text(book_dir, no):
    p = project._scan_dir(os.path.join(book_dir, "正文")).get(no)
    if not p:
        return ""
    return project.split_frontmatter(project.read_text(os.path.join(book_dir, "正文", p)))[1]


def coverage(card, text):
    """章綱的罕見用詞有多少出現在正文裡；同時回傳「沒寫到的詞」（已濾掉樣板字）。"""
    card_t = recall._tokens(card)
    out_t = set(recall._tokens(text))
    if not card_t or not out_t:
        return 0.0, []
    freq = {}
    for t in card_t:
        freq[t] = freq.get(t, 0) + 1
    rare = [t for t in card_t if freq[t] <= 2 and not META_RX.search(t)]
    uniq = list(dict.fromkeys(rare))
    if not uniq:
        return 0.0, []
    missing = [t for t in uniq if t not in out_t]
    return round(1 - len(missing) / len(uniq), 3), missing


def threads(book_dir):
    """未回收伏筆：[(編號, 埋設章, 摘要, 重要度)]。已回收／廢棄的不算。"""
    text = project.read_text(project.safe_path(book_dir, "追蹤/伏筆.md"))
    out = []
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("|---") or "編號" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 7:
            continue
        fid, desc, born = cells[0], cells[1], cells[2]
        status = cells[5] if len(cells) > 5 else ""
        weight = cells[6] if len(cells) > 6 else ""
        m = re.search(r"第(\d+)章", born)
        if not m:
            continue
        if status in ("已回收", "廢棄", "捨棄"):
            continue
        out.append((fid, int(m.group(1)), desc, weight, status))
    return out


def missing_lines(card, text, limit=2):
    """哪幾句情節點沒寫到：逐句算「罕見詞沒出現的比例」，超過一半就列出來。

    bigram 清單（「飼與」「與貓」）作者看不懂，直接給句子的前 40 字才有用。
    """
    body = content_of_card(card)
    out_t = set(recall._tokens(text))
    hits = []
    for line in body.splitlines():
        s = line.strip().lstrip("-*0123456789.、 ").strip()
        if len(s) < 10:
            continue
        toks = [t for t in recall._tokens(s) if not META_RX.search(t)]
        if not toks:
            continue
        miss = [t for t in toks if t not in out_t]
        if len(miss) / len(toks) >= 0.5:
            hits.append((len(miss) / len(toks), s[:44]))
        if len(hits) >= limit * 2:
            break
    hits.sort(key=lambda x: -x[0])
    return [h[1] for h in hits[:limit]]


def _present(name, text):
    """名字有沒有出現在正文：全名、任一段（・或空白分隔）、或名字的最後兩三字。

    正文常常只寫名不寫姓（章綱寫全名、正文只寫名），或只寫姓氏
    （「厄內斯特・卡比」→「厄內斯特」），只比全名會誤報一整片。
    """
    if not name or name in text:
        return True
    for p in re.split(r"[・\s　]+", name):
        if len(p) >= 2 and p in text:
            return True
    core = re.split(r"[・\s　]+", name)[-1]
    return any(len(p) >= 2 and p in text for p in (core[:2], core[:3], core[-3:], core[-2:]))


def _looks_like_name(s):
    """章綱「出場角色」偶爾會寫描述（公安的女人、焦急的541），那不是名字。"""
    if not s or len(s) > 12:
        return False
    return not re.search(r"[的們等]|\d", s)


def drift(book_dir, start=None, end=None, idle=IDLE_CHARS, thread_age=THREAD_AGE):
    """回傳 dict：章節範圍、章綱覆蓋、角色、伏筆、文風。"""
    ch = project._scan_dir(os.path.join(book_dir, "正文"))
    if not ch:
        return {"error": "沒有正文"}
    last = max(ch)
    end = int(end or last)
    start = int(start or max(1, end - 9))
    nos = [n for n in sorted(ch) if start <= n <= end]

    low, cover_rows = [], []
    for no in nos:
        card, text = _card(book_dir, no), _text(book_dir, no)
        if not card or not text:
            continue
        cov, missing = coverage(content_of_card(card), text)
        absent = [n for n in card_names(card) if _looks_like_name(n) and not _present(n, text)]
        row = {"chapter": no, "coverage": cov, "missing": missing[:6],
               "lines": missing_lines(card, text), "absent": absent}
        cover_rows.append(row)
        if cov < LOW_COVER:
            low.append(row)

    idle_chars = []
    for name, pos, first, last_seen in contract.characters(book_dir):
        role = str(pos or "")
        if not any(k in role for k in KEEP_ROLES):
            continue                     # 反派／怪物／一次性角色不列入「消失」
        m = re.search(r"第(\d+)章", str(last_seen or ""))
        seen = int(m.group(1)) if m else (int(first) if str(first).isdigit() else None)
        if seen is None:
            continue
        if end - seen >= idle:
            idle_chars.append({"name": name, "role": role, "last": seen, "idle": end - seen})

    aged_all = [{"id": f, "chapter": born, "age": end - born, "weight": w, "status": st, "desc": d[:40]}
                for f, born, d, w, st in threads(book_dir) if end - born >= thread_age]
    # 先看重要度高的，再看舊的
    aged = sorted(aged_all, key=lambda r: (r["weight"] != "高", -r["age"]))[:8]

    style = []
    for no in nos:
        text = _text(book_dir, no)
        if not text.strip():
            continue
        try:
            ev = style_loop.evaluate(book_dir, text)
        except Exception:
            continue
        if ev.get("rows"):
            style.append({"chapter": no, "obvious": ev["obvious"], "slight": ev["slight"],
                          "max_rel": ev.get("max_rel") or 0, "worst": ev.get("worst") or ""})
    worst_style = sorted(style, key=lambda r: -r["max_rel"])[:5]
    all_threads = threads(book_dir)
    absent_all = [{"chapter": r["chapter"], "names": r["absent"]} for r in cover_rows if r.get("absent")]
    return {"range": [start, end], "chapters": len(nos), "low_cover": low, "cover_rows": cover_rows,
            "absent_names": absent_all,
            "idle_chars": sorted(idle_chars, key=lambda r: -r["idle"]), "aged_threads": aged,
            "thread_total": len(all_threads),
            "thread_oldest": (end - min(t[1] for t in all_threads)) if all_threads else 0,
            "style": style, "worst_style": worst_style}


def findings(d):
    """把 drift() 的結果寫成人看的條列（≥3 條就符合報告的驗收）。"""
    if d.get("error"):
        return ["沒有正文，無法偵測"]
    out = []
    for r in d["low_cover"][:6]:
        if r.get("lines"):
            out.append("第%d章章綱只寫到 %.0f%%：沒寫到的情節點像是「%s」"
                       % (r["chapter"], r["coverage"] * 100, "」「".join(r["lines"])))
        else:
            out.append("第%d章章綱覆蓋只有 %.0f%%（沒寫到的詞：%s）"
                       % (r["chapter"], r["coverage"] * 100, "、".join(r["missing"][:4])))
    for r in d.get("absent_names") or []:
        out.append("第%d章章綱點名「%s」但正文沒出現" % (r["chapter"], "、".join(r["names"][:3])))
    for r in d["idle_chars"][:6]:
        out.append("角色「%s」（%s）已經 %d 章沒登場（最後：第%d章）"
                   % (r["name"], r["role"], r["idle"], r["last"]))
    for r in d["aged_threads"][:6]:
        out.append("伏筆 %s（重要度%s）埋在第%d章、已經 %d 章沒處理（%s）"
                   % (r["id"], r.get("weight") or "?", r["chapter"], r["age"], r["desc"]))
    if d.get("thread_total"):
        out.append("未回收伏筆共 %d 條，最久的一條已經 %d 章" % (d["thread_total"], d["thread_oldest"]))
    for r in d["worst_style"]:
        if r["max_rel"] >= style_loop.LIMIT["rel"]:
            out.append("第%d章的文風偏離 %.2f 倍（%s，明顯 %d 項）"
                       % (r["chapter"], r["max_rel"], r["worst"], r["obvious"]))
    return out


def report_md(book_dir, d=None, title=None):
    d = d or drift(book_dir)
    a, b = d["range"]
    L = ["# 漂移報告（第%d–%d 章，共 %d 章）" % (a, b, d["chapters"]), ""]
    fs = findings(d)
    L.append("## 主要偏離（%d 條）" % len(fs))
    L += ["- " + f for f in fs] or ["（沒有明顯偏離）"]
    L += ["", "## 章綱覆蓋", "| 章 | 覆蓋 | 沒寫到的情節點 |", "|---|---|---|"]
    for r in sorted(d["cover_rows"], key=lambda r: r["coverage"])[:12]:
        what = "」「".join(r.get("lines") or []) or "、".join(r["missing"])
        if r.get("absent"):
            what = (what + "｜" if what else "") + "沒出場：" + "、".join(r["absent"][:3])
        L.append("| %d | %.0f%% | %s |" % (r["chapter"], r["coverage"] * 100, what))
    if d["style"]:
        avg = sum(r["max_rel"] for r in d["style"]) / len(d["style"])
        L += ["", "## 文風趨勢", "平均偏離 %.2f 倍（門檻 %.1f）；最偏的幾章：" % (avg, style_loop.LIMIT["rel"])]
        L += ["- 第%d章 %.2f 倍（%s）" % (r["chapter"], r["max_rel"], r["worst"]) for r in d["worst_style"][:5]]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 可選：LLM 輕量版（只送摘要與卷綱，不送全文）
DRIFT_RULE = """你是這本小說的責編。下面給你「卷綱」「這些章節的摘要」。請只根據這些資料找偏離：
1. 卷綱要求但摘要裡沒看到的情節點
2. 摘要裡有、但卷綱沒安排的事件（新增事件）
3. 卷綱有、但這些章節裡完全沒出現的角色
只輸出 JSON：{"missed": ["..."], "added": ["..."], "vanished": ["..."], "plan": ["..."], "note": "一句話"}
plan 是「卷綱該怎麼改」的具體條目（最多 5 條），沒有就給空陣列。不要寫程式碼圍欄。"""


def llm_pass(prov, book_dir, d, max_chars=4000):
    """把卷綱與章節摘要送給模型找偏離；回傳 dict（失敗時只帶 error）。

    推理模型的「思考」也算在 max_tokens 裡：上限給太小，正文會是空的（實測 deepseek-flash
    給 1200 就可能全被思考吃掉，回來只有空白）。所以這裡給 4000，失敗再重試一次（輸入更短、
    要求更嚴），並把回覆片段放進錯誤訊息，方便判斷是「空回覆」還是「回傳了散文」。
    """
    from . import providers
    a, b = d["range"]
    volume = contract.volume_outline(book_dir, a) or ""
    sums = []
    for no in range(a, b + 1):
        p = project._scan_dir(os.path.join(book_dir, "追蹤", "章節摘要")).get(no)
        if p:
            sums.append("第%d章：%s" % (no, project.split_frontmatter(
                project.read_text(os.path.join(book_dir, "追蹤", "章節摘要", p)))[1].strip()[:400]))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    last = ""
    for attempt, (limit, tail) in enumerate(((4000, ""), (4000, "\n\n只輸出一個 JSON 物件，不要任何說明文字。"))):
        user = ("【卷綱】\n%s\n\n【章節摘要】\n%s%s"
                % (volume[:2000], "\n".join(sums), tail))[:max_chars if attempt == 0 else max(1500, max_chars // 2)]
        try:
            text, usage = providers.chat(root, prov,
                                         [{"role": "system", "content": DRIFT_RULE},
                                          {"role": "user", "content": user}],
                                         json_mode=True, max_tokens=limit)
        except Exception as e:
            last = "呼叫失敗：%s" % str(e)[:100]
            continue
        if not (text or "").strip():
            last = "回覆是空的（%s）" % ("finish_reason=length，思考可能吃掉了額度"
                                       if (usage or {}).get("finish_reason") == "length" else "模型沒有輸出內容")
            continue
        try:
            data = providers.parse_json(text)
        except Exception:
            last = "模型回覆不是 JSON（前 60 字：%s）" % text.strip()[:60]
            continue
        if isinstance(data, dict):
            return data
        last = "模型回傳的不是物件（%s）" % type(data).__name__
    return {"error": last or "未知錯誤"}


# ---------------------------------------------------------------------------
# 卷綱更新草稿：寫成檔案、附加回卷綱（都不覆蓋原本內容）
def volume_rel(book_dir, no):
    """這一章屬於哪一份正式卷綱；不在任何範圍就回空字串。

    不在任何範圍時**不要退回任何一卷**：退回第一卷／最後一卷都會把更新寫進錯的卷綱
    （2026-10-29 實測：第 51～60 章被標成第一卷）。
    """
    v = volume.find(book_dir, no)
    return v["rel"] if v else ""


def plan_md(res, a, b):
    """把 LLM 的偏離結果寫成「卷綱更新」草稿（markdown）。"""
    if res.get("error"):
        return "（產生失敗：%s）" % res["error"]
    L = ["# 卷綱更新草稿（第%d–%d 章體檢）" % (a, b), "",
         "> 由卷末體檢產生。看過再決定要不要附加到卷綱；不喜歡就直接丟掉。", ""]
    for key, label in (("missed", "卷綱有、實際沒寫到"), ("added", "實際有、卷綱沒安排"),
                       ("vanished", "卷綱有、章節沒出現的角色")):
        items = res.get(key) or []
        if items:
            L.append("## " + label)
            L += ["- " + str(x) for x in items]
            L.append("")
    if res.get("plan"):
        L.append("## 建議改卷綱")
        L += ["- " + str(x) for x in res["plan"]]
        L.append("")
    if res.get("note"):
        L += ["> " + str(res["note"]), ""]
    return "\n".join(L)


def save_plan(book_dir, a, b, text):
    """把草稿寫到 候選/卷綱更新_第a-b章.md（不進大綱，避免模型直接改你的規劃）。"""
    rel = "候選/卷綱更新_第%d-%d章.md" % (a, b)
    p = project.safe_path(book_dir, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    return rel


def apply_plan(book_dir, no, text, a=None, b=None):
    """把草稿「附加」到卷綱檔尾（原檔先備份），回傳 (卷綱相對路徑, 備份路徑)。"""
    from . import tracking
    rel = volume_rel(book_dir, no)
    if not rel:
        raise project.ProjectError(
            "第 %d 章不在任何卷綱的章節範圍內，不知道要附加到哪一份卷綱；先補卷綱再試。" % no)
    p = project.safe_path(book_dir, rel)
    bak = tracking.backup(book_dir, p, "卷綱更新前")
    old = project.read_text(p) if os.path.isfile(p) else ("---\n類型: 卷綱\n---\n\n# 卷綱\n")
    head = "\n\n---\n\n## 卷綱更新（第%s–%s章體檢）\n\n" % (a or "?", b or "?")
    body = text.strip()
    # 草稿裡的第一個 # 標題會和卷綱標題打架，去掉它
    if body.startswith("# "):
        body = body.split("\n", 1)[1].lstrip()
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(old.rstrip() + head + body + "\n")
    return rel, bak
