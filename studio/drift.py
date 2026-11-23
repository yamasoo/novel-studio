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

from . import contract, datakeys, enums, project, prompts, recall, shared, style_loop, textguard, volume
from . import layout, sections, tables

IDLE_CHARS = 20      # 幾章沒登場算「消失」
THREAD_AGE = 30      # 伏筆埋設後幾章還沒回收算「欠帳」
LOW_COVER = 0.20     # 章綱覆蓋率低於這個就列出
KEEP_ROLES = ("主角", "主要配角", "配角")     # 反派／怪物／一次性角色不算「消失」
# 章綱分段：情節點是「要寫到的內容」；出場角色與伏筆操作另外處理（一個查名字、一個是簿記）
PLOT_HEADS = ("情節點", "章末鉤子", "場景", "衝突", "轉折")
NAME_HEAD = "出場角色"
PLOT_IDS = ("plot_points", "ending_hook")      # 英文、日文標題靠段落 ID 認
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
    parts = [v for k, v in sec.items() if any(h in k for h in PLOT_HEADS) or sections.id_of("chapter-card", k) in PLOT_IDS]
    return "\n".join(parts).strip() or (card or "")


def card_names(card):
    """章綱「出場角色」段落點名的角色。"""
    sec = sections_of_card(card)
    for k, v in sec.items():
        if NAME_HEAD in k or sections.id_of("chapter-card", k) == "cast":
            return [ln.strip().lstrip("-* ").strip() for ln in v.splitlines() if ln.strip()]
    return []


def _card(book_dir, no):
    p = project._scan_dir(layout.path(book_dir, layout.CHAPTER_CARDS)).get(no)
    if not p:
        return ""
    return project.split_frontmatter(project.read_text(layout.path(book_dir, layout.CHAPTER_CARDS, p)))[1]


def _text(book_dir, no):
    p = project._scan_dir(layout.path(book_dir, layout.MANUSCRIPT)).get(no)
    if not p:
        return ""
    return project.split_frontmatter(project.read_text(layout.path(book_dir, layout.MANUSCRIPT, p)))[1]


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
    out = []
    # 經 tables.read：表頭與固定值不論書的語言，列都是英文鍵、內部值（已回收、第003章）
    for r in tables.read(book_dir, "foreshadow", layout.FORESHADOWING)["rows"]:
        fid, desc, born = r.get("id", ""), r.get("content", ""), r.get("planted_in", "")
        status, weight = r.get("status", ""), r.get("priority", "")
        if not fid:
            continue
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
    ch = project._scan_dir(layout.path(book_dir, layout.MANUSCRIPT))
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


# 偏離報告的句子。報告只在卷末體檢頁顯示給作者看，所以跟**介面語言**（API 的 lang 參數），
# 不是書的語言；繁中逐字照舊。章綱與正文的內容（情節點、名字）照原樣放進去。
T = {
    "zh-TW": {
        "no_text": "沒有正文，無法偵測",
        "low_lines": "第%d章章綱只寫到 %.0f%%：沒寫到的情節點像是「%s」", "q_join": "」「",
        "low_words": "第%d章章綱覆蓋只有 %.0f%%（沒寫到的詞：%s）", "sep": "、",
        "absent": "第%d章章綱點名「%s」但正文沒出現",
        "idle": "角色「%s」（%s）已經 %d 章沒登場（最後：第%d章）",
        "aged": "伏筆 %s（重要度%s）埋在第%d章、已經 %d 章沒處理（%s）",
        "threads": "未回收伏筆共 %d 條，最久的一條已經 %d 章",
        "style": "第%d章的文風偏離 %.2f 倍（%s，明顯 %d 項）",
        "title": "# 漂移報告（第%d–%d 章，共 %d 章）", "main": "## 主要偏離（%d 條）", "none": "（沒有明顯偏離）",
        "cover": "## 章綱覆蓋", "cover_head": "| 章 | 覆蓋 | 沒寫到的情節點 |", "no_show": "沒出場：",
        "trend": "## 文風趨勢", "avg": "平均偏離 %.2f 倍（門檻 %.1f）；最偏的幾章：", "worst": "- 第%d章 %.2f 倍（%s）",
    },
    "en": {
        "no_text": "No text yet, nothing to check",
        "low_lines": "Chapter %d covers only %.0f%% of its card: plot points not written include “%s”", "q_join": "”, “",
        "low_words": "Chapter %d covers only %.0f%% of its card (missing words: %s)", "sep": ", ",
        "absent": "The card for chapter %d names “%s”, but they don't appear in the text",
        "idle": "Character “%s” (%s) hasn't appeared for %d chapters (last: chapter %d)",
        "aged": "Thread %s (priority %s), planted in chapter %d, untouched for %d chapters (%s)",
        "threads": "%d open threads; the oldest has waited %d chapters",
        "style": "Chapter %d drifts %.2f× from the style (%s; %d clear deviations)",
        "title": "# Drift report (chapters %d–%d, %d chapters)", "main": "## Main deviations (%d)", "none": "(no clear deviations)",
        "cover": "## Chapter-card coverage", "cover_head": "| Ch. | Coverage | Plot points not written |", "no_show": "not on stage: ",
        "trend": "## Style trend", "avg": "Average deviation %.2f× (threshold %.1f); the chapters that drift most:",
        "worst": "- Chapter %d %.2f× (%s)",
    },
    "ja": {
        "no_text": "本文がないため、チェックできません",
        "low_lines": "第%d章は章カードの %.0f%% しか書けていません：書かれていないプロットポイント「%s」", "q_join": "」「",
        "low_words": "第%d章の章カードの反映は %.0f%% だけです（書かれていない語：%s）", "sep": "、",
        "absent": "第%d章の章カードに「%s」がありますが、本文に出てきません",
        "idle": "キャラクター「%s」（%s）が %d 章登場していません（最後：第%d章）",
        "aged": "伏線 %s（重要度 %s）は第%d章で仕込まれ、%d 章触れられていません（%s）",
        "threads": "未回収の伏線 %d 件、いちばん古いものは %d 章",
        "style": "第%d章の文体のずれ %.2f 倍（%s、明らかなもの %d 項目）",
        "title": "# ずれのレポート（第%d–%d章、全 %d 章）", "main": "## 主なずれ（%d 件）", "none": "（目立ったずれはありません）",
        "cover": "## 章カードの反映", "cover_head": "| 章 | 反映 | 書かれていないプロットポイント |", "no_show": "未登場：",
        "trend": "## 文体の傾向", "avg": "平均のずれ %.2f 倍（基準 %.1f）。ずれの大きい章：", "worst": "- 第%d章 %.2f 倍（%s）",
    },
}


def _t(lang):
    return T.get(lang) or T["zh-TW"]


def findings(d, lang="zh-TW"):
    """把 drift() 的結果寫成人看的條列（≥3 條就符合報告的驗收）。lang：介面語言。"""
    t = _t(lang)
    if d.get("error"):
        return [t["no_text"]]
    role = (lambda v: v) if lang == "zh-TW" else (lambda v: enums.show("role", v, lang))
    prio = lambda v: tables.display("foreshadow", "priority", v, lang) if v else "?"     # noqa: E731
    out = []
    for r in d["low_cover"][:6]:
        if r.get("lines"):
            out.append(t["low_lines"] % (r["chapter"], r["coverage"] * 100, t["q_join"].join(r["lines"])))
        else:
            out.append(t["low_words"] % (r["chapter"], r["coverage"] * 100, t["sep"].join(r["missing"][:4])))
    for r in d.get("absent_names") or []:
        out.append(t["absent"] % (r["chapter"], t["sep"].join(r["names"][:3])))
    for r in d["idle_chars"][:6]:
        out.append(t["idle"] % (r["name"], role(r["role"]), r["idle"], r["last"]))
    for r in d["aged_threads"][:6]:
        out.append(t["aged"] % (r["id"], prio(r.get("weight")), r["chapter"], r["age"], r["desc"]))
    if d.get("thread_total"):
        out.append(t["threads"] % (d["thread_total"], d["thread_oldest"]))
    for r in d["worst_style"]:
        if r["max_rel"] >= style_loop.LIMIT["rel"]:
            out.append(t["style"] % (r["chapter"], r["max_rel"], datakeys.metric_label(r["worst"], lang), r["obvious"]))
    return out


def report_md(book_dir, d=None, title=None, lang="zh-TW"):
    d = d or drift(book_dir)
    t = _t(lang)
    a, b = d["range"]
    L = [t["title"] % (a, b, d["chapters"]), ""]
    fs = findings(d, lang)
    L.append(t["main"] % len(fs))
    L += ["- " + f for f in fs] or [t["none"]]
    L += ["", t["cover"], t["cover_head"], "|---|---|---|"]
    for r in sorted(d["cover_rows"], key=lambda r: r["coverage"])[:12]:
        what = t["q_join"].join(r.get("lines") or []) or t["sep"].join(r["missing"])
        if r.get("absent"):
            what = (what + "｜" if what else "") + t["no_show"] + t["sep"].join(r["absent"][:3])
        L.append("| %d | %.0f%% | %s |" % (r["chapter"], r["coverage"] * 100, what))
    if d["style"]:
        avg = sum(r["max_rel"] for r in d["style"]) / len(d["style"])
        L += ["", t["trend"], t["avg"] % (avg, style_loop.LIMIT["rel"])]
        L += [t["worst"] % (r["chapter"], r["max_rel"], datakeys.metric_label(r["worst"], lang)) for r in d["worst_style"][:5]]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 可選：LLM 輕量版（只送摘要與卷綱，不送全文）
# 送給模型的指令、使用者訊息的格式在三語提示詞（drift_rule、drift_user…），依書的語言


def llm_pass(prov, book_dir, d, max_chars=4000):
    """把卷綱與章節摘要送給模型找偏離；回傳 dict（失敗時只帶 error）。

    推理模型的「思考」也算在 max_tokens 裡：上限給太小，正文會是空的（實測 deepseek-flash
    給 1200 就可能全被思考吃掉，回來只有空白）。所以這裡給 4000，失敗再重試一次（輸入更短、
    要求更嚴），並把回覆片段放進錯誤訊息，方便判斷是「空回覆」還是「回傳了散文」。
    """
    from . import providers
    a, b = d["range"]
    P = prompts.cur()          # 呼叫端已經 set_lang(書的語言)
    volume = contract.volume_outline(book_dir, a) or ""
    sums = []
    for no in range(a, b + 1):
        p = project._scan_dir(layout.path(book_dir, layout.SUMMARIES)).get(no)
        if p:
            sums.append(P["drift_sum_line"].format(n=no, text=project.split_frontmatter(
                project.read_text(layout.path(book_dir, layout.SUMMARIES, p)))[1].strip()[:400]))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    last = ""
    for attempt, (limit, tail) in enumerate(((4000, ""), (4000, P["drift_retry_tail"]))):
        user = P["drift_user"].format(vol=volume[:2000], sums="\n".join(sums), tail=tail)[
            :max_chars if attempt == 0 else max(1500, max_chars // 2)]
        try:
            text, usage = providers.chat(root, prov,
                                         [{"role": "system", "content": P["drift_rule"]},
                                          {"role": "user", "content": user}],
                                         json_mode=True, max_tokens=limit, stage="structured")
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
    """把 LLM 的偏離結果寫成「卷綱更新」草稿（markdown）。依目前任務的語言（書的語言）寫。"""
    if res.get("error"):
        return "（產生失敗：%s）" % res["error"]
    P = prompts.cur()
    L = [P["drift_plan_title"].format(a=a, b=b), "", P["drift_plan_note"], ""]
    for key in ("missed", "added", "vanished"):
        items = res.get(key) or []
        if items:
            L.append("## " + P["drift_" + key])
            L += ["- " + str(x) for x in items]
            L.append("")
    if res.get("plan"):
        L.append(P["drift_plan_head"])
        L += ["- " + str(x) for x in res["plan"]]
        L.append("")
    if res.get("note"):
        L += ["> " + str(res["note"]), ""]
    return "\n".join(L)


def save_plan(book_dir, a, b, text, notes=None):
    """把草稿寫到 outline/drafts/volume-update_ch-aaaa-bbbb.md（跟新卷草稿同一個資料夾，但不會被當成新卷）。"""
    rel = layout.volume_update_draft(a, b)
    p = project.safe_path(book_dir, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    text, note = textguard.guard_text(book_dir, text if text.endswith("\n") else text + "\n")
    if note and notes is not None:
        notes.append(note)
    project.write_atomic(p, text)
    return rel


def apply_plan(book_dir, no, text, a=None, b=None, notes=None):
    """把草稿「附加」到卷綱檔尾（原檔先備份），回傳 (卷綱相對路徑, 備份路徑)。"""
    from . import tracking
    text, note = textguard.guard_text(book_dir, text)
    if note and notes is not None:
        notes.append(note)
    rel = volume_rel(book_dir, no)
    if not rel:
        raise project.ProjectError(
            "第 %d 章不在任何卷綱的章節範圍內，不知道要附加到哪一份卷綱；先補卷綱再試。" % no)
    p = project.safe_path(book_dir, rel)
    bak = tracking.backup(book_dir, p, "卷綱更新前")
    old = project.read_text(p) if os.path.isfile(p) else ("---\ntype: volume-outline\n---\n\n# 卷綱\n")
    from . import lang as lang_mod
    head = "\n\n---\n\n" + prompts.t(lang_mod.book_lang(book_dir), "drift_append_head", a=a or "?", b=b or "?") + "\n\n"
    body = text.strip()
    # 草稿裡的第一個 # 標題會和卷綱標題打架，去掉它
    if body.startswith("# "):
        body = body.split("\n", 1)[1].lstrip()
    project.write_atomic(p, old.rstrip() + head + body + "\n")
    return rel, bak
