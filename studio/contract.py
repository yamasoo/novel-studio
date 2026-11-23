# -*- coding: utf-8 -*-
"""續寫合約：把「續寫時不能違背的事實」整理成一份檔案，注入每章上下文的最前面。

為什麼要這份
  寫第 30 章時，模型看得到章綱、狀態卡、部分伏筆，但「這本書已經定稿到第幾章」「誰已經死了」
  「哪些秘密讀者已經知道、哪些還不能說破」散在各個表裡。合約把它們集中成一頁，
  以 priority 0 注入（預算不夠時最後才被砍），所以它比任何單一資料表都可靠。

怎麼產生
  純本機、不呼叫模型：從 正文／設定／追蹤／大綱 的既有資料整理。
  作者可以直接改，但重新產生時只有 `## 作者補充` 之後的內容會原樣保留——
  自己加的規則請寫在那一節。

什麼時候更新
  ensure() 只在「檔案不存在」或「已定稿章數變了」時重寫，所以續寫一章之後會自動跟上。
"""
import os
import re
import time

from . import project, textguard, volume
from . import fmkeys, layout, sections
from . import enums, tables

REL = layout.CONTRACT
KEEP_MARK = "## 作者補充"
# 合約依書的語言寫；重新產生時三種語言的「作者補充」標記都認（書改過語言也不會弄丟作者寫的內容）
KEEP_MARKS = {"zh-TW": KEEP_MARK, "en": "## Author's additions", "ja": "## 作者の追記"}

# 合約裡工作台自己寫的句子。繁中逐字照舊（P5 第 2 批前的輸出）；%s 的順序三種語言一致。
T = {
    "zh-TW": {
        "gen": "產生時間", "title": "# 續寫合約",
        "intro": "> 這份是「續寫時不能違背的事實」，程式從正文、設定、追蹤與大綱整理出來的，"
                 "以最高優先順序注入每章上下文。可以直接改；重新產生時只有 `%s` 之後的內容會原樣保留，"
                 "自己加的規則請寫在那一節。",
        "s1": "## 1. 不可變事實",
        "done": "- 本書已定稿到**第 %d 章**（正文 %d 章）；第 1～%d 章的內容不可改寫，續寫不得與之矛盾。",
        "none": "- 這本書還沒有定稿的正文章節（從第一章開始寫）。",
        "char": "%s（%s，首次登場 %s%s）", "char_last": "，最後登場 ", "unset": "未標", "sep": "、",
        "chars_more": "……另有 %d 位，見 `bible/characters/`", "chars": "- 角色（%d 位）：%s%s", "paren": "（%s）",
        "known": "- 讀者**已經知道**的事（不能再當成新資訊，也不能反過來推翻）：",
        "known_item": "  - %s（%s 揭示）：%s", "more_tl": "  - ……另有 %d 條，見 `tracking/timeline.md`",
        "hidden": "- **還沒揭曉**的事（本章不能提前說破）：",
        "words": "- 名詞表已登記 %d 條%s", "words_eg": "（例：%s）",
        "s2": "## 2. 聲線（每章都要維持）", "banned": "**本書禁忌（違反就是不合格）**",
        "no_style": "- 見 `bible/style.md`（沒有填就沿用共用文風）。",
        "s3": "## 3. 必須承接的懸念",
        "thread": "- %s %s（埋設 %s，預計回收 %s，狀態 %s，重要度 %s）",
        "more_fs": "- ……另有 %d 條還沒回收，見 `tracking/foreshadowing.md`",
        "no_threads": "- 目前沒有未回收的伏筆。",
        "s4": "## 4. 卷末承諾", "in_vol": "（第 %d 章屬於本卷：%s）",
        "out_vol": "- 第 %d 章不在任何卷綱的章節範圍內（現有卷綱只到第 %d 章）；"
                   "先補對應的 `outline/volumes/vol-NN.md`，續寫才對得上整卷走向（見 `docs/卷先行.md`）。",
        "no_vol": "- 還沒有卷綱；先寫 `outline/volumes/vol-NN.md`，續寫才對得上整卷走向。",
        "s5": "## 5. 禁區",
        "prefs": "- 作者的硬性偏好（`bible/author-prefs.md`）與本書規則（`CLAUDE.md`）優先於任何寫作技法；違反就重寫。",
        "keep_none": "（沒有；作者自己加的規則寫在這裡）",
    },
    "en": {
        "gen": "generated_at", "title": "# Continuation contract",
        "intro": "> These are the facts a continuation must not contradict. The studio builds this file from the text, "
                 "the bible, the tracking files and the outlines, and puts it first in every chapter's context. "
                 "You can edit it, but when it is rebuilt only what comes after `%s` is kept as is; "
                 "write your own rules in that section.",
        "s1": "## 1. Fixed facts",
        "done": "- The book is final through **chapter %d** (%d chapters of text); chapters 1–%d must not be rewritten "
                "or contradicted.",
        "none": "- The book has no final chapters yet (start from chapter 1).",
        "char": "%s (%s, first appears %s%s)", "char_last": ", last seen ", "unset": "not set", "sep": ", ",
        "chars_more": "…and %d more, see `bible/characters/`", "chars": "- Characters (%d): %s%s", "paren": " (%s)",
        "known": "- What the reader **already knows** (not new information any more, and must not be overturned):",
        "known_item": "  - %s (revealed in %s): %s", "more_tl": "  - …and %d more, see `tracking/timeline.md`",
        "hidden": "- What is **not revealed yet** (must not be given away early):",
        "words": "- The glossary has %d entries%s", "words_eg": " (e.g. %s)",
        "s2": "## 2. Voice (keep it in every chapter)", "banned": "**This book's don'ts (breaking one is a fail)**",
        "no_style": "- See `bible/style.md` (if empty, the shared style applies).",
        "s3": "## 3. Threads that must be carried",
        "thread": "- %s %s (planted %s, payoff planned %s, status %s, priority %s)",
        "more_fs": "- …and %d more open threads, see `tracking/foreshadowing.md`",
        "no_threads": "- No open threads right now.",
        "s4": "## 4. End-of-volume promises", "in_vol": "(Chapter %d belongs to this volume: %s)",
        "out_vol": "- Chapter %d is outside every volume outline's chapter range (the outlines only reach chapter %d); "
                   "add the matching `outline/volumes/vol-NN.md` first so the continuation follows the volume.",
        "no_vol": "- There is no volume outline yet; write `outline/volumes/vol-NN.md` first so the continuation "
                  "follows the volume.",
        "s5": "## 5. Off limits",
        "prefs": "- The author's hard preferences (`bible/author-prefs.md`) and this book's rules (`CLAUDE.md`) come "
                 "before any writing technique; if one is broken, rewrite.",
        "keep_none": "(None yet; add your own rules here)",
    },
    "ja": {
        "gen": "generated_at", "title": "# 続き書きの契約",
        "intro": "> 「続きを書くときに破ってはいけない事実」です。ワークベンチが本文・設定・追跡・あらすじから"
                 "まとめ、毎章のコンテキストの先頭に入れます。直接編集できますが、作り直すと `%s` 以降だけがそのまま"
                 "残ります。自分のルールはその節に書いてください。",
        "s1": "## 1. 変えられない事実",
        "done": "- この本は**第 %d 章**まで確定しています（本文 %d 章）。第 1～%d 章の内容は書き換えず、矛盾させないこと。",
        "none": "- この本にはまだ確定した章がありません（第 1 章から書きます）。",
        "char": "%s（%s、初登場 %s%s）", "char_last": "、最終登場 ", "unset": "未設定", "sep": "、",
        "chars_more": "……ほか %d 人、`bible/characters/` を参照", "chars": "- キャラクター（%d 人）：%s%s", "paren": "（%s）",
        "known": "- 読者が**すでに知っている**こと（新しい情報として扱わず、覆さないこと）：",
        "known_item": "  - %s（%sで判明）：%s", "more_tl": "  - ……ほか %d 件、`tracking/timeline.md` を参照",
        "hidden": "- **まだ明かしていない**こと（先に言ってしまわないこと）：",
        "words": "- 用語集の登録 %d 件%s", "words_eg": "（例：%s）",
        "s2": "## 2. 文体（毎章守ること）", "banned": "**この本の禁止事項（破ったら不合格）**",
        "no_style": "- `bible/style.md` を参照（空なら共有の文体を使います）。",
        "s3": "## 3. 引き継ぐ伏線",
        "thread": "- %s %s（仕込み %s、回収予定 %s、状態 %s、重要度 %s）",
        "more_fs": "- ……ほか未回収 %d 件、`tracking/foreshadowing.md` を参照",
        "no_threads": "- いま未回収の伏線はありません。",
        "s4": "## 4. 巻末の約束", "in_vol": "（第 %d 章はこの巻に属します：%s）",
        "out_vol": "- 第 %d 章はどの巻プロットの章の範囲にも入っていません（巻プロットは第 %d 章まで）。"
                   "先に対応する `outline/volumes/vol-NN.md` を書いてください。",
        "no_vol": "- まだ巻プロットがありません。先に `outline/volumes/vol-NN.md` を書いてください。",
        "s5": "## 5. 禁止領域",
        "prefs": "- 作者の譲れない好み（`bible/author-prefs.md`）とこの本のルール（`CLAUDE.md`）は、どんな書き方の"
                 "テクニックよりも優先します。破ったら書き直してください。",
        "keep_none": "（まだありません。自分のルールはここに書いてください）",
    },
}
STATUS_DONE = {"已回收", "已解", "回收"}


# ---------------------------------------------------------------------------
UNREVEALED = {"not yet", "not revealed", "unrevealed", "未開示", "未公開"}


def _rows(text):
    """把 markdown 表格抓成 list[dict]，第一列當表頭。"""
    rows, head = [], None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if head:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if head is None:
            head = cells
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append({head[i]: cells[i] for i in range(min(len(head), len(cells)))})
    return rows


def _section(text, sid, doc="style"):
    """取出文風某一段（`## 標題` 到下一個 `## `，不含標題行）。標題三語都認；繁中照舊允許前後有別的字。"""
    out, on = [], False
    zh = [x for x in sections.labels(doc, sid) if re.search(r"[\u4e00-\u9fff]", x)]
    for line in text.splitlines():
        if re.match(r"^##\s+", line):
            if on:
                break
            on = any(x in line for x in zh) or sections.id_of(doc, line.lstrip("#")) == sid
            continue
        if on:
            out.append(line)
    return "\n".join(out).strip()


def _read(path):
    return project.read_text(path) if os.path.isfile(path) else ""


def _body(book_dir, rel):
    text = _read(os.path.join(book_dir, *rel.split("/")))
    return project.split_frontmatter(text)[1] if text else ""


def _front(book_dir, rel):
    text = _read(os.path.join(book_dir, *rel.split("/")))
    return project.split_frontmatter(text)[0] if text else {}


def _clip(text, limit):
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "……"


def _strip_h1(text):
    """引用的檔案各自有 `# 標題`；放進合約的小節裡要拿掉，免得變成兩層大標。"""
    lines = (text or "").strip().splitlines()
    if lines and lines[0].lstrip().startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def last_chapter(book_dir):
    numbers = [n for n in project._scan_dir(layout.path(book_dir, layout.MANUSCRIPT))]
    return max(numbers) if numbers else 0


def _lang(book_dir):
    from . import lang as lang_mod
    lg = lang_mod.book_lang(book_dir)
    return lg if lg in T else "zh-TW"


def _ch(v, lang):
    """內部章號（第003章）→ 書的語言（繁中原樣，英文 Ch. 3，日文 第3章）。"""
    return tables.display("foreshadow", "planted_in", v, lang) if v else v


def characters(book_dir):
    """[(名稱, 定位, 首次登場, 最後登場)]；資料來自 bible/characters/*.md 與 tracking/characters/。"""
    out = []
    for e in project.list_entries(book_dir, layout.CHARACTERS):
        name = e.get("name") or ""
        fm = e.get("frontmatter") or _front(book_dir, e.get("file") or "")
        st = _front(book_dir, layout.entry(layout.CHARACTER_STATES, name))
        out.append((name, fmkeys.disp("role", fm.get("role")) or "", fmkeys.ch_disp(fm.get("first_appearance")) or "", fmkeys.ch_disp(st.get("last_appearance")) or ""))
    return out


def threads(book_dir):
    """未回收的伏筆：[(編號, 內容, 埋設章, 預計回收, 狀態, 重要度)]，重要的排前面。"""
    rows = tables.rows_to_keys("foreshadow", _rows(_body(book_dir, layout.FORESHADOWING)))
    open_rows = []
    for r in rows:
        status = r.get("status") or ""
        if status in STATUS_DONE:
            continue
        open_rows.append((r.get("id") or "", r.get("content") or "", r.get("planted_in") or "",
                          r.get("planned_payoff") or "", status, r.get("priority") or ""))
    order = {"高": 0, "中": 1, "低": 2}
    open_rows.sort(key=lambda x: (order.get(x[5], 3), x[0]))
    return open_rows


def secrets(book_dir):
    """時間線的兩堆：讀者已經知道的、還沒揭曉的。"""
    rows = tables.rows_to_keys("timeline", _rows(_body(book_dir, layout.TIMELINE)))
    known, hidden = [], []
    for r in rows:
        revealed = (r.get("revealed_in") or "").strip()
        item = (r.get("id") or "", (r.get("what_really_happened") or "").strip(), revealed)
        if revealed and revealed not in ("未揭示", "未") and revealed.lower() not in UNREVEALED:     # 英文、日文書的「not yet」「未開示」
            known.append(item)
        else:
            hidden.append(item)
    return known, hidden


def volume_outline(book_dir, no):
    """當前章節所在那一卷的卷綱（看 frontmatter 的「章節範圍」）。

    找不到就回空——不要退回第一卷：退回會讓「第 51 章」拿到第一卷的卷末承諾（2026-10-29 實測）。
    """
    v = volume.find(book_dir, no)
    if not v:
        return "", ""
    return v["name"], _body(book_dir, v["rel"])


# ---------------------------------------------------------------------------
def build(book_dir, keep=""):
    """產生合約全文。keep：作者補充（原樣接在最後）。"""
    no = last_chapter(book_dir)
    chars = characters(book_dir)
    open_rows = threads(book_dir)
    known, hidden = secrets(book_dir)
    vol_name, vol_body = volume_outline(book_dir, no + 1)
    style = _body(book_dir, layout.STYLE)
    banned = _section(style, "dont")
    style_base = _section(style, "basics")
    prefs = _body(book_dir, layout.AUTHOR_PREFS)
    words = tables.rows_to_keys("glossary", _rows(_body(book_dir, layout.GLOSSARY)))

    lang = _lang(book_dir)
    t = T[lang]
    U = t["unset"]
    role = (lambda p: p) if lang == "zh-TW" else (lambda p: enums.show("role", p, lang))
    status_of = lambda v: tables.display("foreshadow", "status", v, lang)       # noqa: E731
    prio_of = lambda v: tables.display("foreshadow", "priority", v, lang)       # noqa: E731
    mark = KEEP_MARKS[lang]
    L = ["---", "type: continuation-contract", "updated_through: %s" % fmkeys.ch_value(no),
         "%s: %s" % (t["gen"], time.strftime("%Y-%m-%d %H:%M")), "---", "",
         t["title"], "",
         t["intro"] % mark, "",
         t["s1"], ""]
    if no:
        L.append(t["done"] % (no, no, no))
    else:
        L.append(t["none"])
    if chars:
        names = [t["char"] % (n, role(pos) if pos else U, _ch(first, lang) or U,
                              t["char_last"] + _ch(last, lang) if last else "")
                 for n, pos, first, last in chars[:20]]
        more = t["chars_more"] % (len(chars) - 20) if len(chars) > 20 else ""
        L.append(t["chars"] % (len(chars), t["sep"].join(names), (t["paren"] % more) if more else ""))
    if known:
        L.append(t["known"])
        for code, fact, at in known[:12]:
            L.append(t["known_item"] % (code, _ch(at, lang), fact))
        if len(known) > 12:
            L.append(t["more_tl"] % (len(known) - 12))
    if hidden:
        L.append(t["hidden"])
        for code, fact, _at in hidden[:12]:
            L.append("  - %s：%s" % (code, fact) if lang != "en" else "  - %s: %s" % (code, fact))
        if len(hidden) > 12:
            L.append(t["more_tl"] % (len(hidden) - 12))
    if words:
        names = [r.get("term") or r.get("名稱") or r.get("詞") or "" for r in words][:20]   # 名稱、詞：作者自己取的表頭
        L.append(t["words"] % (len(words), (t["words_eg"] % t["sep"].join(n for n in names if n)) if any(names) else ""))
    L += ["", t["s2"], ""]
    if style_base:
        L += [_clip(style_base, 600), ""]
    if banned:
        L += [t["banned"], "", _clip(banned, 800), ""]
    if not (style_base or banned):
        L += [t["no_style"], ""]
    L += [t["s3"], ""]
    if open_rows:
        for code, fact, plant, due, status, weight in open_rows[:20]:
            L.append(t["thread"] % (code, fact, _ch(plant, lang) or U, _ch(due, lang) or U,
                                    status_of(status) or U, prio_of(weight) or U))
        if len(open_rows) > 20:
            L.append(t["more_fs"] % (len(open_rows) - 20))
    else:
        L.append(t["no_threads"])
    L += ["", t["s4"], ""]
    if vol_body:
        if vol_name:
            L.append(t["in_vol"] % (no + 1, vol_name))
            L.append("")
        L.append(_clip(_strip_h1(vol_body), 900))
    else:
        if volume.has_volumes(book_dir):
            last = max([v["hi"] for v in volume.list_volumes(book_dir) if v["hi"]] or [0])
            L.append(t["out_vol"] % (no + 1, last))
        else:
            L.append(t["no_vol"])
    L += ["", t["s5"], ""]
    L.append(t["prefs"])
    if prefs:
        L += ["", _clip(_strip_h1(prefs), 500)]
    L += ["", mark, "", keep.strip() if keep.strip() else t["keep_none"], ""]
    return "\n".join(L)


def path(book_dir):
    return os.path.join(book_dir, *REL.split("/"))


def text(book_dir):
    """目前檔案內容；沒有就回傳空字串。"""
    return _read(path(book_dir))


def keep_of(existing):
    """舊檔裡「作者補充」之後的內容（三種語言的標記都認）；只有預設的「（沒有…）」就當成空的。"""
    for mark in KEEP_MARKS.values():
        if mark in existing:
            kept = existing.split(mark, 1)[1].strip()
            return "" if kept in {x["keep_none"] for x in T.values()} else kept
    return ""


def ensure(book_dir, force=False, notes=None):
    """需要時產生／更新合約；回傳寫入的相對路徑，沒動就回傳 None。"""
    p = path(book_dir)
    existing = _read(p)
    no = last_chapter(book_dir)
    if existing and not force:
        fm = project.split_frontmatter(existing)[0]
        same_lang = KEEP_MARKS[_lang(book_dir)] in existing      # 舊版（一律中文）或書改過語言：重新產生，作者補充照留
        if fmkeys.ch_int(fm.get("updated_through")) == no and same_lang:
            return None                     # 章數沒變：作者可能改過，不動它
    content = build(book_dir, keep_of(existing))
    content, note = textguard.guard_text(book_dir, content)
    if note:
        textguard.notify(note)
        if notes is not None:
            notes.append(note)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        # 暫存檔名帶 pid：上一次中斷留下的 .tmp 不會擋住這次（也避免兩個流程互踩）
        tmp = "%s.%d.tmp" % (p, os.getpid())
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(tmp, p)
    except OSError as e:
        raise project.ProjectError(
            "續寫合約存不起來（%s）：%s\n"
            "如果工作台是用「專案裡的 .venv」啟動、而書庫在專案資料夾外，那個 python 會被限制寫入，"
            "請改用外部虛擬環境：set NS_VENV=... 後再 start.bat。" % (getattr(e, "filename", REL), e))
    return REL
