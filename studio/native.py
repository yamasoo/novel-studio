# -*- coding: utf-8 -*-
"""
不靠 Claude Code 的寫作流程：工作台組裝上下文 → 模型只產出文字或 JSON → Python 寫檔。
適用於 DeepSeek、llama.cpp 等 OpenAI 相容的模型。
"""
import json
import os
import re
import time

from . import context, goals, native_files, project, providers, recovery, revision, shared, tracking

DELIM = "<<<匯報>>>"

SYSTEM = ("你是繁體中文長篇網路小說的寫作助手，與作者合作寫一本連載小說。"
          "一律使用台灣繁體中文與台灣用語；標點用「」『』、刪節號……、破折號——，全形標點。"
          "遵守提供的本書規則、文風與作者偏好；文風與通用技法衝突時以本書文風為準。"
          "章綱是唯一的劇情藍圖，不擅自改變章綱已定的結果；不提前揭露時間線中讀者還不知道的事。"
          "需要作者決定的事（新主線事件、大反轉、能力規則、揭開真相、改變章綱結果）不要自己寫進正文，列在匯報裡請作者決定。")

NATIVE_ACTIONS = {"write", "reject", "revise", "deslop", "accept", "sync_tracking", "review", "free", "reply",
                  "setup_check", "review_all", "goal_check", "review_notes", "revise_notes",
                  "recover_continue"} | set(native_files.SPECS)


class NativeError(Exception):
    pass


# ---------------------------------------------------------------------------
class Ctx:
    def __init__(self, job, prov, home, plugin_dir, checker, opts=None):
        self.job, self.prov, self.home, self.plugin_dir, self.checker = job, prov, home, plugin_dir, checker
        self.opts = opts or {}
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self.truncated = False

    @property
    def book(self):
        return self.job.book_dir

    def budget(self, reserve_output):
        total = int(self.prov.get("context_tokens") or 32768)
        return max(2000, total - int(reserve_output) - 1500)

    def call(self, messages, json_mode=False, max_tokens=None, label="", stage=None, recover=None):
        """recover={"chapter": N, "kind": "chapter", "prefix": 已有文字}：失敗或截斷時把已輸出的文字存成恢復稿。"""
        job = self.job
        buf = {"s": "", "t": "", "last": time.time(), "all": []}

        def flush(force=False):
            if force or time.time() - buf["last"] > 0.25:
                if buf["t"]:
                    job.emit("thinking", text=buf["t"])
                    buf["t"] = ""
                if buf["s"]:
                    job.emit("stream", text=buf["s"])
                    buf["s"] = ""
                buf["last"] = time.time()

        def on_delta(t):
            buf["s"] += t
            buf["all"].append(t)
            flush()

        def on_think(t):
            buf["t"] += t
            flush()

        adapter, effort = providers.reasoning_for(self.prov, stage)
        tag = "" if adapter == "none" or not stage else "（思考：%s）" % ("關閉" if effort == "off" else effort)
        job.emit("stream_start", text=label + tag, json=json_mode)
        try:
            text, usage = providers.chat(self.home, self.prov, messages, on_delta=on_delta, on_thinking=on_think,
                                         json_mode=json_mode, max_tokens=max_tokens, stage=stage,
                                         should_stop=lambda: job.status == "cancelled")
        except Exception as e:
            flush(True)
            job.emit("stream_end")
            if recover is not None:
                reason = "已停止" if isinstance(e, providers.Cancelled) else str(e)[:200]
                self._keep("".join(buf["all"]), label, reason, recover)
            raise
        flush(True)
        job.emit("stream_end")
        if recover is not None and usage.get("finish_reason") == "length":
            self._keep(text, label, "輸出達到長度上限被截斷", recover)
        for k in ("prompt_tokens", "completion_tokens"):
            self.usage[k] += int(usage.get(k) or 0)
        self.truncated = usage.get("finish_reason") == "length"
        if self.truncated:
            job.emit("log", text="提醒：輸出達到「最大輸出」%s tokens 的上限被截斷。推理模型的思考過程也算在輸出裡，"
                                 "請到設定把這個執行者的「最大輸出」調高（DeepSeek 建議 32768 以上）。" % (max_tokens or self.prov.get("max_output")))
        return text

    def _keep(self, text, label, reason, recover):
        text = (text or "").split(DELIM)[0]
        if recover.get("prefix"):
            text = recovery.compose(recover["prefix"], text)
        rec = recovery.save(self.book, self.job.id, label, text, reason, chapter=recover.get("chapter"),
                            kind=recover.get("kind", "text"), provider=self.prov.get("id"))
        if rec:
            self.job.emit("log", text="已把中斷前寫出的 %d 字存成恢復稿，可以在章節頁或任務紀錄接著寫。" % rec["chars"])

    def save_messages(self, messages, extra=None):
        d = os.path.join(self.book, ".studio", "jobs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, self.job.id + ".messages.json"), "w", encoding="utf-8") as f:
            json.dump({"messages": messages, "extra": extra or {}}, f, ensure_ascii=False)


def load_messages(book_dir, job_id):
    p = os.path.join(book_dir, ".studio", "jobs", job_id + ".messages.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
def _target_chars(book_dir, no):
    _, card = context.card_text(book_dir, no)
    fm, _ = project.split_frontmatter(card)
    try:
        if fm.get("字數目標"):
            return int(fm["字數目標"])
    except (TypeError, ValueError):
        pass
    m = re.search(r"每章字數[：:]\s*(\d+)\s*[～~\-－到至]\s*(\d+)", context.read(book_dir, "CLAUDE.md"))
    if m:
        return (int(m.group(1)) + int(m.group(2))) // 2
    return 3000


def _card_title(book_dir, no):
    _, card = context.card_text(book_dir, no)
    fm, _ = project.split_frontmatter(card)
    return str(fm.get("章名") or "").strip()


def _split_output(text, no, fallback_title):
    """把「正文＋<<<匯報>>>＋匯報」拆開，回傳 (章名, 正文 markdown, 匯報)。"""
    t = text.strip()
    t = re.sub(r"^```(?:markdown|md)?\s*", "", t)
    report = ""
    if DELIM in t:
        t, report = t.split(DELIM, 1)
    t = t.strip().rstrip("`").strip()
    m = re.match(r"#\s*第\s*0*\d+\s*章\s*(.*)", t)
    title = (m.group(1).strip() if m else "") or fallback_title or "未命名"
    if not m:
        t = "# 第%d章 %s\n\n%s" % (no, title, t)
    title = re.sub(r'[\\/:*?"<>|]', "", title)
    return title, t.strip() + "\n", report.strip()


def _save_candidate(c, no, title, text):
    d = os.path.join(c.book, "候選")
    os.makedirs(d, exist_ok=True)
    old = project._scan_dir(d).get(no)
    if old:
        tracking.backup(c.book, os.path.join(d, old), "候選")
        os.remove(os.path.join(d, old))
    fixed, n = c.checker.fix_punct(text)
    name = "第%03d章_%s.md" % (no, title)
    with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(fixed)
    return "候選/" + name, n


def _check_summary(c, rel):
    res = c.checker.check_file(os.path.join(c.book, rel), c.checker.load_whitelist(c.book))
    must = [f for f in res["問題"] if f["等級"] == "必須修"]
    sug = [f for f in res["問題"] if f["等級"] == "建議修"]
    return res, "中文字數約 %d；用語檢查：必須修 %d 項、建議修 %d 項。" % (res["中文字數"], len(must), len(sug))


def _out_tokens(c, chars=None):
    # 只是上限，實際用多少算多少；推理模型的思考也算在輸出裡，所以不要壓低
    return int(c.prov.get("max_output") or 8192)


FORMAT_RULE = ("輸出格式：第一行是「# 第{n}章 章名」，接著是正文；正文結束後另起一行寫「" + DELIM +
               "」，再寫給作者的匯報。匯報包含：這章兩三句摘要、停在哪個鉤子；"
               "新出現的具名人物、地點、規則、伏筆（寫了要報）；需要作者決定、所以沒寫的事；自查結論一句話。"
               "不要輸出其他說明。")


# ---------------------------------------------------------------------------
def act_write(c, p):
    a = int(p.get("from") or 0)
    b = int(p.get("to") or a)
    if not a:
        raise NativeError("請指定要寫第幾章")
    a, b = min(a, b), max(a, b)
    b = min(b, a + 2)
    note = (p.get("note") or "").strip()
    reports = []
    for n in range(a, b + 1):
        if c.job.status == "cancelled":
            return
        if not context.card_text(c.book, n)[1]:
            raise NativeError("第%d章還沒有章綱，請先排章綱。" % n)
        target = _target_chars(c.book, n)
        out_tok = _out_tokens(c, target)
        ctx_text, used, dropped = context.for_chapter(c.book, c.plugin_dir, n, c.budget(out_tok),
                                                      prev_from_candidate=(n > a))
        if dropped:
            c.job.emit("log", text="上下文超出長度，略過：%s" % "、".join(dropped))
        c.job.emit("log", text="第%d章：上下文約 %d tokens，目標 %d 字" % (n, used, target))
        rec = _reconcile(c, n, prev_from_candidate=(n > a)) if c.opts.get("reconcile_before_write", True) else None
        if rec:
            ctx_text += "\n\n" + goals.reconcile_block(rec)
        user = (ctx_text + "\n\n【任務】依第%d章章綱寫出完整正文，約 %d 字（中文字）。"
                "照情節點順序展開成場景，每個情節點都要寫到；遵守禁止事項與資訊邊界；"
                "情緒用動作、物件、對白呈現，不替讀者點題，章尾停在具體畫面，不寫感悟或預告。%s\n%s"
                % (n, target, ("\n作者這次的要求：" + note) if note else "", FORMAT_RULE.format(n=n)))
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        out = c.call(msgs, max_tokens=out_tok, label="寫第%d章" % n, stage="draft",
                     recover={"chapter": n, "kind": "chapter"})
        title, text, report = _split_output(out, n, _card_title(c.book, n))
        rel, fixed = _save_candidate(c, n, title, text)
        _, chk = _check_summary(c, rel)
        msgs.append({"role": "assistant", "content": out})
        c.save_messages(msgs, {"kind": "chapter", "chapter": n})
        parts = ["**第%d章《%s》候選稿已存到 %s**" % (n, title, rel), report or "（模型沒有附匯報）"]
        if rec:
            parts.append(goals.reconcile_md(rec))
        if c.opts.get("goal_check_after_write", True):
            g = _goal_check(c, n, rel)
            if g:
                parts.append(g)
        parts.append(chk + ("（已自動修正標點 %d 處）" % fixed if fixed else ""))
        reports.append("\n\n".join(parts))
    c.job.result = "\n\n---\n\n".join(reports) + "\n\n候選稿請在章節頁審閱，採用後會回寫追蹤資料。"


def _rewrite(c, no, src_text, instruction, label):
    target = max(project.count_chars(src_text), 500)
    out_tok = _out_tokens(c, target)
    ctx_text, used, dropped = context.for_chapter(c.book, c.plugin_dir, no, c.budget(out_tok + context.est_tokens(src_text)),
                                                  include_craft=False)
    user = (ctx_text + "\n\n【目前的稿子】\n" + context.body(src_text) + "\n\n【任務】" + instruction +
            "\n請輸出修改後的完整章節（不是只給修改處）。\n" + FORMAT_RULE.format(n=no))
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    out = c.call(msgs, max_tokens=out_tok, label=label, stage="draft", recover={"chapter": no, "kind": "chapter"})
    msgs.append({"role": "assistant", "content": out})
    c.save_messages(msgs, {"kind": "chapter", "chapter": no})
    return _split_output(out, no, _card_title(c.book, no))


def act_reject(c, p):
    no = int(p.get("chapter"))
    path, src = context.chapter_text(c.book, no, ("候選",))
    if not src:
        raise NativeError("第%d章沒有候選稿" % no)
    note = (p.get("note") or "").strip() or "請整體再修順。"
    title, text, report = _rewrite(c, no, src, "作者退回了這份候選稿，意見如下，請照意見改寫：\n" + note, "改寫第%d章候選稿" % no)
    rel, _ = _save_candidate(c, no, title, text)
    _, chk = _check_summary(c, rel)
    c.job.result = "**第%d章候選稿已改寫（%s）**\n\n%s\n\n%s" % (no, rel, report, chk)


def act_revise(c, p):
    no = int(p.get("chapter"))
    path, src = context.chapter_text(c.book, no, ("正文",))
    if not src:
        raise NativeError("第%d章還沒有正文" % no)
    note = (p.get("note") or "").strip()
    if not note:
        raise NativeError("請說明要怎麼改")
    title, text, report = _rewrite(c, no, src, "作者要修改這一章：\n" + note, "改第%d章" % no)
    rel, _ = _save_candidate(c, no, title, text)
    _, chk = _check_summary(c, rel)
    c.job.result = ("**改好的第%d章放在候選稿（%s）**，原本的正文沒有動。採用後會覆蓋正文並重新回寫追蹤。\n\n%s\n\n%s"
                    % (no, rel, report, chk))


def act_deslop(c, p):
    no = int(p.get("chapter"))
    where = "候選" if p.get("candidate") else "正文"
    path, src = context.chapter_text(c.book, no, (where,))
    if not src:
        raise NativeError("第%d章沒有%s" % (no, "候選稿" if where == "候選" else "正文"))
    res = c.checker.check_file(os.path.join(c.book, path), c.checker.load_whitelist(c.book))
    finds = "\n".join("- 第%s行｜%s｜%s｜%s → %s" % (f["行"] or "全章", f["等級"], f["類型"], f["片段"], f["建議"])
                      for f in res["問題"][:60]) or "（腳本沒有發現問題）"
    target = project.count_chars(src)
    out_tok = _out_tokens(c, target)
    ref, used, dropped = context.for_deslop(c.book, c.plugin_dir, c.budget(out_tok + context.est_tokens(src) + 2000))
    user = (ref + "\n\n【檢查腳本的發現】\n" + finds + "\n\n【原稿】\n" + context.body(src) +
            "\n\n【任務】去除 AI 味並校正台灣用語：先修必須修的項目，再處理語意層的 AI 味（替讀者點題、敘述者解釋、章尾昇華、萬用表情與比喻堆疊、說明書式對白）。"
            "能刪就刪，否則換成具體動作、物件、對白；不改變劇情事實、人物決定與資訊揭露程度；作者文風允許的寫法保留。"
            "輸出完整的修改後章節。匯報寫：改了幾處、主要是哪幾類、刻意保留了什麼。\n" + FORMAT_RULE.format(n=no))
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    out = c.call(msgs, max_tokens=out_tok, label="去 AI 味：第%d章" % no, stage="draft")
    title, text, report = _split_output(out, no, _card_title(c.book, no))
    full = os.path.join(c.book, path)
    if where == "候選":
        rel, _ = _save_candidate(c, no, title, text)
    else:
        bak = tracking.backup(c.book, full, "去AI味前")
        fixed, _ = c.checker.fix_punct(text)
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(fixed)
        rel = path
        report += "\n\n原稿已備份到 %s" % os.path.relpath(bak, c.book).replace("\\", "/")
    _, chk = _check_summary(c, rel)
    c.save_messages(msgs + [{"role": "assistant", "content": out}], {"kind": "deslop", "chapter": no, "path": rel})
    c.job.result = "**第%d章已去 AI 味（%s）**\n\n%s\n\n%s" % (no, rel, report, chk)


def _writeback(c, no):
    path, text = context.chapter_text(c.book, no, ("正文",))
    if not text:
        raise NativeError("第%d章沒有正文" % no)
    title = project.chapter_title_from_filename(os.path.basename(path)) or _card_title(c.book, no)
    out_tok = _out_tokens(c)
    tracked = tracking.tracked_to(c.book)
    revision = bool(tracked and no < tracked)
    ctx_text, used, dropped = context.for_writeback(c.book, no, text, c.budget(out_tok))
    task = "第%d章已定稿。請整理這章對追蹤資料的影響。" % no
    if revision:
        task += tracking.REVISION_NOTE % (tracked, no)
    user = ctx_text + "\n\n【任務】" + task + "\n" + tracking.WRITEBACK_SCHEMA
    msgs = [{"role": "system", "content": SYSTEM + "這個任務請只輸出 JSON；思考保持簡短，把篇幅留給 JSON。"},
            {"role": "user", "content": user}]
    out = c.call(msgs, json_mode=True, max_tokens=out_tok, label="整理第%d章的追蹤資料" % no, stage="structured")
    try:
        data = providers.parse_json(out)
    except providers.ProviderError:
        if c.truncated:
            # 被截斷：不要把半截輸出接回去（模型會從頭再想一次），改成放寬上限重來
            more = min(out_tok * 2, 131072)
            c.job.emit("log", text="輸出被截斷，放寬上限到 %d tokens 重新產生……" % more)
            out = c.call(msgs, json_mode=True, max_tokens=more, label="重新產生 JSON", stage="structured")
        else:
            c.job.emit("log", text="JSON 格式有誤，請模型重新輸出一次……")
            msgs2 = msgs + [{"role": "assistant", "content": out},
                            {"role": "user", "content": "上面的輸出不是合法 JSON。請只輸出符合格式的 JSON 物件，不要任何說明或圍欄。"}]
            out = c.call(msgs2, json_mode=True, max_tokens=out_tok, label="重新輸出 JSON", stage="structured")
        try:
            data = providers.parse_json(out)
        except providers.ProviderError as e:
            raise NativeError("%s。%s" % (e, "輸出仍被截斷，請到設定調高「最大輸出」後再試。" if c.truncated else "可以再試一次，或改用其他模型。"))
    log = tracking.apply_writeback(c.book, no, title, project.count_chars(text), data, revision=revision)
    if revision:
        log.append("（修訂舊章：狀態卡與角色狀態保留第%d章的版本）" % tracked)
    committed = tracking.git_commit(c.book, "第%03d章 %s" % (no, title))
    return "**第%d章《%s》追蹤已回寫**：%s%s\n\n%s" % (
        no, title, "、".join(log), "；已 git 提交" if committed else "", str(data.get("report") or "").strip())


def act_accept(c, p):
    c.job.result = _writeback(c, int(p.get("chapter")))


def act_sync(c, p):
    fm, _ = project.split_frontmatter(context.read(c.book, "追蹤/狀態卡.md"))
    m = re.search(r"\d+", str(fm.get("更新至") or ""))
    done = int(m.group(0)) if m else 0
    todo = sorted(n for n in project._scan_dir(os.path.join(c.book, "正文")) if n > done)
    if not todo:
        c.job.result = "追蹤資料已經是最新的（更新至第%d章）。" % done
        return
    outs = []
    for n in todo:
        if c.job.status == "cancelled":
            return
        outs.append(_writeback(c, n))
    c.job.result = "\n\n".join(outs)


def act_review(c, p):
    a = int(p.get("from") or 1)
    b = int(p.get("to") or a)
    a, b = min(a, b), max(a, b)
    out_tok = _out_tokens(c)
    ctx_text, used, dropped = context.for_review(c.book, c.plugin_dir, a, b, c.budget(out_tok))
    if dropped:
        c.job.emit("log", text="上下文超出長度，略過：%s" % "、".join(dropped))
    fmt = context.skill_ref(c.plugin_dir, "novel-review/references/fix-routing.md")
    m = re.search(r"## 四、報告格式(.*)", fmt, re.S)
    user = (ctx_text + "\n\n【任務】依審查清單審查第%d～%d章，找出讀者會察覺的錯誤。每個問題要有依據（指出和哪裡矛盾）、位置與修法；沒有問題就說通過，不要為了湊數挑毛病。"
            "作者文風允許的寫法不算問題。用以下格式輸出 Markdown 報告：\n%s" % (a, b, m.group(1) if m else ""))
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    out = c.call(msgs, max_tokens=out_tok, label="審查第%d～%d章" % (a, b), stage="review")
    d = os.path.join(c.book, ".studio", "審查報告")
    os.makedirs(d, exist_ok=True)
    fn = "第%03d-%03d章_%s.md" % (a, b, time.strftime("%Y%m%d-%H%M"))
    with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
        f.write(out)
    c.save_messages(msgs + [{"role": "assistant", "content": out}], {"kind": "chat"})
    c.job.result = out + "\n\n（報告已存到 .studio/審查報告/%s）" % fn


def act_free(c, p):
    q = (p.get("text") or "").strip()
    if not q:
        raise NativeError("指令是空的")
    ctx_text, used, dropped = context.for_chat(c.book, c.budget(4000))
    msgs = [{"role": "system", "content": SYSTEM + "這是和作者的討論；除非作者要求，不要直接寫正文。"},
            {"role": "user", "content": ctx_text + "\n\n【作者】" + q}]
    out = c.call(msgs, max_tokens=_out_tokens(c), label="回答", stage="plan")
    c.save_messages(msgs + [{"role": "assistant", "content": out}], {"kind": "chat"})
    c.job.result = out


def act_reply(c, p):
    parent = c.job.resume
    data = load_messages(c.book, parent) if parent else None
    if not data:
        raise NativeError("找不到上一輪的對話紀錄，無法接續。")
    msgs = data["messages"]
    extra = data.get("extra") or {}
    msgs.append({"role": "user", "content": p.get("text", "")})
    out = c.call(msgs, max_tokens=_out_tokens(c), label="回覆", stage=extra.get("stage") or "plan")
    msgs.append({"role": "assistant", "content": out})
    c.save_messages(msgs, extra)
    if extra.get("kind") == "files":
        c.job.result = native_files.reply_files(c, out)
    elif extra.get("kind") == "chapter" and (DELIM in out or re.match(r"\s*#\s*第\s*\d+\s*章", out)):
        no = int(extra["chapter"])
        title, text, report = _split_output(out, no, _card_title(c.book, no))
        rel, _ = _save_candidate(c, no, title, text)
        _, chk = _check_summary(c, rel)
        c.job.result = "**第%d章候選稿已更新（%s）**\n\n%s\n\n%s" % (no, rel, report, chk)
    else:
        c.job.result = out


# ---------------------------------------------------------------------------
# 寫稿前定稿對帳
# ---------------------------------------------------------------------------
def _reconcile(c, no, prev_from_candidate=False):
    """比對章綱必須事件與已定稿事實。沒有任何已定稿資料（新書第一章）或解析失敗時回傳 None。"""
    has_facts = tracking.tracked_to(c.book) > 0 or bool(context.chapter_text(c.book, no - 1, ("正文", "候選"))[1])
    if not has_facts:
        return None
    _, card = context.card_text(c.book, no)
    gl = goals.freeze_goals(card)
    if not gl:
        return None
    pk = context.Pack(c.budget(_out_tokens(c)))
    pk.add(0, "第%d章章綱必須事件" % no, "\n".join("- " + g["text"] for g in gl))
    pk.add(0, "第%d章章綱全文" % no, context.body(card))
    pk.add(1, "狀態卡（已定稿）", context.body(context.read(c.book, "追蹤/狀態卡.md")))
    prev_path, prev = context.chapter_text(c.book, no - 1, ("候選", "正文") if prev_from_candidate else ("正文", "候選"))
    if prev:
        pk.add(1, "上一章結尾", context.body(prev)[-1500:], keep="tail")
    for e in context.mentioned_entities(c.book, card):
        st = context.read(c.book, "追蹤/角色狀態/%s.md" % e["name"])
        if st:
            pk.add(2, "角色目前狀態：%s" % e["name"], context.body(st))
    pk.add(2, "時間線（作者真相與讀者已知）", context.body(context.read(c.book, "追蹤/時間線.md")))
    h, rows = context.foreshadow_rows(c.book, card)
    pk.add(3, "相關伏筆", context.table_md(h, rows))
    pk.add(3, "前幾章摘要", context.recent_summaries(c.book, no))
    ctx_text, used, dropped = pk.build()
    msgs = [{"role": "system", "content": SYSTEM + "這個任務請只輸出 JSON。"},
            {"role": "user", "content": ctx_text + "\n\n【任務】寫第%d章之前，把章綱必須事件和已定稿事實逐條比對。\n%s" % (no, goals.RECONCILE_SCHEMA)}]
    try:
        out = c.call(msgs, json_mode=True, max_tokens=_out_tokens(c), label="寫第%d章前對帳" % no, stage="structured")
        rec = goals.parse_reconcile(providers.parse_json(out))
    except (providers.ProviderError, ValueError) as e:
        c.job.emit("log", text="對帳失敗，略過這一步：%s" % e)
        return None
    if not rec:
        c.job.emit("log", text="對帳結果格式不符，略過這一步。")
    return rec


# ---------------------------------------------------------------------------
# 章綱目標逐項核對
# ---------------------------------------------------------------------------
def _goal_check(c, no, rel=None):
    """核對一章（預設候選稿優先）。回傳匯報文字；沒有章綱目標時回傳空字串。"""
    _, card = context.card_text(c.book, no)
    gl = goals.freeze_goals(card)
    if not gl:
        return ""
    if rel:
        text = context.read(c.book, rel)
    else:
        rel, text = goals.target(c.book, no, prefer_candidate=True)
    if not text:
        return ""
    user = goals.build_prompt(no, gl, context.body(text))
    msgs = [{"role": "system", "content": SYSTEM + "這個任務請只輸出 JSON。"}, {"role": "user", "content": user}]
    try:
        out = c.call(msgs, json_mode=True, max_tokens=_out_tokens(c), label="核對第%d章章綱" % no, stage="review")
        data = providers.parse_json(out)
    except providers.ProviderError as e:
        c.job.emit("log", text="章綱核對失敗：%s" % e)
        return ""
    items = goals.verify(gl, data, text)
    goals.save(c.book, no, rel, text, items, c.prov.get("id"))
    return goals.report_md(no, items)


def act_goal_check(c, p):
    no = int(p.get("chapter"))
    rel = None
    if p.get("candidate"):
        rel = context.chapter_text(c.book, no, ("候選",))[0]
    r = _goal_check(c, no, rel)
    if not r:
        raise NativeError("第%d章沒有章綱情節點或沒有正文，無法核對。" % no)
    c.job.result = r


# ---------------------------------------------------------------------------
# 單章審查（逐條意見）→ 勾選 → 修訂（逐段對照）
# ---------------------------------------------------------------------------
def _review_target(c, no, p):
    if p.get("path"):
        return p["path"], context.read(c.book, p["path"])
    if p.get("candidate"):
        return context.chapter_text(c.book, no, ("候選",))
    return goals.target(c.book, no, prefer_candidate=True)


def act_review_notes(c, p):
    no = int(p.get("chapter"))
    rel, text = _review_target(c, no, p)
    if not text:
        raise NativeError("第%d章沒有可以審查的稿子" % no)
    pk = context.Pack(c.budget(_out_tokens(c) + context.est_tokens(text)))
    pk.add(0, "審查清單", context.skill_ref(c.plugin_dir, "novel-review/references/checklist.md"))
    pk.add(0, "本書規則", context.book_rules(c.book))
    pk.add(1, "本書文風（作者允許的寫法不算問題）", context.body(context.read(c.book, "設定/文風.md")))
    pk.add(1, "共用作者偏好（「常犯的毛病」要特別檢查）", shared.prefs_for_context(c.book))
    _, card = context.card_text(c.book, no)
    pk.add(1, "第%d章章綱" % no, context.body(card))
    prev_path, prev = context.chapter_text(c.book, no - 1, ("正文",))
    if prev:
        pk.add(1, "前一章結尾", context.body(prev)[-1200:], keep="tail")
    pk.add(2, "狀態卡", context.body(context.read(c.book, "追蹤/狀態卡.md")))
    for e in context.mentioned_entities(c.book, text):
        pk.add(2, "設定：%s" % e["name"], context.body(context.read(c.book, e["file"])))
        st = context.read(c.book, "追蹤/角色狀態/%s.md" % e["name"])
        if st:
            pk.add(2, "角色目前狀態：%s" % e["name"], context.body(st))
    pk.add(3, "時間線", context.body(context.read(c.book, "追蹤/時間線.md")))
    pk.add(3, "伏筆總表", context.body(context.read(c.book, "追蹤/伏筆.md")))
    ctx_text, used, dropped = pk.build()
    user = (ctx_text + "\n\n【要審查的稿子（%s）】\n" % rel + context.body(text) +
            "\n\n【任務】依審查清單審查這一章，列出讀者會察覺的問題。\n" + revision.REVIEW_SCHEMA)
    msgs = [{"role": "system", "content": SYSTEM + "這個任務請只輸出 JSON。"}, {"role": "user", "content": user}]
    out = c.call(msgs, json_mode=True, max_tokens=_out_tokens(c), label="審查第%d章" % no, stage="review")
    rec = revision.normalize_review(providers.parse_json(out), text)
    rec = revision.save_review(c.book, no, rel, text, rec, c.prov.get("id"))
    c.job.result = revision.review_md(no, rec)


def act_revise_notes(c, p):
    no = int(p.get("chapter"))
    rv = revision.load_review(c.book, no)
    ids = p.get("ids") or []
    extra = (p.get("extra") or "").strip()
    notes = revision.notes_text(rv, ids, extra)
    if not notes:
        raise NativeError("請至少勾選一條審查意見，或寫下你自己的修改意見。")
    rel = (rv or {}).get("path") or goals.target(c.book, no, prefer_candidate=True)[0]
    text = context.read(c.book, rel) if rel else ""
    if not text:
        raise NativeError("第%d章沒有可以修訂的稿子" % no)
    out_tok = _out_tokens(c)
    ctx_text, used, dropped = context.for_chapter(c.book, c.plugin_dir, no, c.budget(out_tok + context.est_tokens(text)),
                                                  include_craft=False)
    user = (ctx_text + "\n\n【目前的稿子（%s）】\n" % rel + context.body(text) +
            "\n\n【要處理的修改意見】\n" + notes +
            "\n\n【任務】只修改這些意見涉及的地方；其他段落一字不改，維持原本的空行分段（作者會逐段比對新舊版本）。"
            "不改變劇情事實與人物決定，除非意見明確要求。請輸出修改後的完整章節。匯報逐條說明每個意見怎麼處理。\n" + FORMAT_RULE.format(n=no))
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    out = c.call(msgs, max_tokens=out_tok, label="修訂第%d章" % no, stage="draft", recover={"chapter": no, "kind": "chapter"})
    title, new_text, report = _split_output(out, no, _card_title(c.book, no))
    rec = revision.save_revision(c.book, no, rel, text, title, new_text, notes, report, c.prov.get("id"))
    n = sum(1 for b in revision.diff_blocks(text, new_text) if b["type"] == "change")
    c.job.result = ("**第%d章修訂好了**：共 %d 處段落變更，原稿沒有被改動。請到章節頁逐段選擇要保留原文還是採用修訂，再按「套用」。\n\n%s"
                    % (no, n, report or ""))


def act_recover_continue(c, p):
    rec = recovery.load(c.book, p.get("id"))
    no = rec.get("chapter")
    if not no:
        raise NativeError("這份恢復稿不屬於任何章節，無法續寫；可以直接複製內容使用。")
    no = int(no)
    partial = rec["text"]
    out_tok = _out_tokens(c)
    ctx_text, used, dropped = context.for_chapter(c.book, c.plugin_dir, no, c.budget(out_tok + context.est_tokens(partial)),
                                                  include_craft=False, prev_from_candidate=True)
    target = _target_chars(c.book, no)
    user = (ctx_text + "\n\n【已經寫好的部分（中斷在最後一句）】\n" + partial +
            "\n\n【任務】從中斷處接著寫完第%d章（全章約 %d 字，已寫約 %d 字）。直接從斷點的下一句開始，"
            "不要重複已寫的內容，不要重寫標題。寫完後另起一行寫「%s」，再寫給作者的匯報。" % (no, target, rec.get("chars", 0), DELIM))
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    out = c.call(msgs, max_tokens=out_tok, label="續寫第%d章" % no, stage="draft",
                 recover={"chapter": no, "kind": "chapter", "prefix": partial})
    addition, report = (out.split(DELIM, 1) + [""])[:2]
    full = recovery.compose(partial, addition)
    title, text, _ = _split_output(full, no, _card_title(c.book, no))
    rel, fixed = _save_candidate(c, no, title, text)
    recovery.discard(c.book, rec["id"])
    _, chk = _check_summary(c, rel)
    c.save_messages(msgs + [{"role": "assistant", "content": out}], {"kind": "chapter", "chapter": no})
    c.job.result = "**第%d章已接著寫完，存成候選稿（%s）**\n\n%s\n\n%s" % (no, rel, report.strip(), chk)


HANDLERS = {"write": act_write, "reject": act_reject, "revise": act_revise, "deslop": act_deslop,
            "accept": act_accept, "sync_tracking": act_sync, "review": act_review, "free": act_free,
            "reply": act_reply, "setup_check": native_files.act_setup_check,
            "review_all": lambda c, p: native_files.act_review_all(c, p, SYSTEM),
            "goal_check": lambda c, p: act_goal_check(c, p),
            "review_notes": lambda c, p: act_review_notes(c, p),
            "revise_notes": lambda c, p: act_revise_notes(c, p),
            "recover_continue": lambda c, p: act_recover_continue(c, p)}
for _k, _spec in native_files.SPECS.items():
    HANDLERS[_k] = (lambda s: (lambda c, p: native_files.run_spec(c, p, s, SYSTEM)))(_spec)


def run(job, prov, home, plugin_dir, checker, opts=None):
    c = Ctx(job, prov, home, plugin_dir, checker, opts)
    action = job.meta.get("action")
    job.session_id = job.id  # 讓前端可以用 resume=job.id 接續
    job.emit("init", session_id=job.id, model="%s %s" % (prov.get("name"), prov.get("model") or ""))
    job.emit("start", text="開始執行（%s）" % prov.get("name"))
    try:
        h = HANDLERS.get(action)
        if not h:
            raise NativeError("「%s」目前只支援 Claude Code，請在面板上方把執行者切換成 Claude Code。" % (job.title))
        h(c, job.meta.get("params") or {})
        if job.status == "cancelled":
            job.emit("cancelled", text="已停止")
        else:
            job.status = "done"
            job.cost = providers.cost_of(prov, c.usage)
            job.emit("result", text=job.result, cost=job.cost,
                     usage=c.usage, turns=None)
    except providers.Cancelled:
        job.status = "cancelled"
        job.emit("cancelled", text="已停止")
    except (NativeError, providers.ProviderError, project.ProjectError) as e:
        job.status = "error"
        job.emit("error", text=str(e))
    except Exception as e:  # noqa
        job.status = "error"
        job.emit("error", text="%s：%s" % (type(e).__name__, e))
