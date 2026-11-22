"""把名詞表整理進設定集：細分類、依主題寫成世界觀檔、重要條目獨立成檔、合併勢力，名詞表留作索引。

- 名詞表每一條都保留（垃圾條目除外），一條一行，「注意」欄指到詳細內容在哪一份設定檔。寫稿時篩名詞表照常運作。
- 地點、物品、能力與技術、制度與習俗、生物依「主題」寫成 bible/world/{主題}.md；出場 5 章以上的地點、物品、技術獨立成一份。
- 組織交給 AI 合併重複（例如縮寫與全名）、把不是勢力的移走、同一政權不同階段的名稱寫成沿革，拿不準的標「需要作者確認」。
- 事件留在名詞表，指到時間線；稱謂留在名詞表。
- 每個名詞從正文抓前後幾句當參考（本機搜尋，不重讀整本）。
結果寫成草稿，由「從正文建立設定」頁的「設定」組採用。

提示詞與寫出的說明文字跟著書的語言走（prompts 的語言包）；類別、欄位鍵名與 JSON 的列舉值維持中文，程式靠它們判斷。
"""
import os
import re

from . import context, enums, project, prompts, search
from . import layout
from . import jsonkeys
from . import tables

BIG = ("地點", "組織", "物品", "能力與技術", "制度與習俗", "生物", "事件", "稱謂", "人物", "其他")
TOPIC_BIG = ("地點", "物品", "能力與技術", "制度與習俗", "生物", "其他")
OWN_FILE_MIN = 5          # 出場 5 章以上的地點、物品、技術獨立成檔
OWN_FILE_BIG = ("地點", "物品", "能力與技術")
CLASSIFY_BATCH = 60
TOPIC_BATCH = 40
OWN_BATCH = 4
JUNK = re.compile(r"未提及|正文(?:無|沒有)此?資訊|正文未明確|無相關資訊|not stated in the text|not mentioned in the text|本文に明記なし|言及なし|^\s*$")


def _p(key, **kw):
    """取出目前語言的提示詞／文字，替換 {名字} 的變數。只換有給的名字，JSON 的花括號不動。"""
    return re.sub(r"\{(\w+)\}", lambda m: str(kw[m.group(1)]) if m.group(1) in kw else m.group(0), prompts.cur()[key])


def _default_topic(big):
    """AI 沒給主題時的預設主題檔名（依書的語言）。語言包 gl_default_topics：「大類=主題|…|*=其他」。"""
    table = dict(x.split("=", 1) for x in prompts.cur()["gl_default_topics"].split("|"))
    return table.get(big) or table["*"]


def _u():
    return prompts.cur()["gl_unknown"]


def _clean(s):
    return str(s or "").replace("|", "／").replace("\n", " ").strip()


def _fname(s):
    return project.safe_filename(s, 40)


# ---------------------------------------------------------------------------
# 正文統計：出場章數、首次出現、前後文片段（本機）
# ---------------------------------------------------------------------------
def load_texts(book_dir):
    out = []
    for no, f in sorted(project._scan_dir(layout.path(book_dir, layout.MANUSCRIPT)).items()):
        t = context.body(project.read_text(layout.path(book_dir, layout.MANUSCRIPT, f)))
        out.append((no, t, search.norm(t)))
    return out


def stats(texts, term, snips=2, width=60):
    nt = search.norm(term)
    chs, out = [], []
    for no, t, n in texts:
        i = n.find(nt)
        if i < 0:
            continue
        chs.append(no)
        if len(out) < snips and (not out or out[-1][0] != no):
            s = re.sub(r"\s+", " ", t[max(0, i - width): i + len(term) + width])
            out.append((no, s))
    return chs, out


def parse_rows(book_dir):
    """名詞表的列（英文鍵：term、kind、explanation、note）。名詞取第一欄（不論表頭寫什麼）。"""
    tbl = tables.read(book_dir, "glossary", layout.GLOSSARY)
    key = tables.file_keys(tbl)[0] if tbl["headers"] else "term"
    return [{"term": _clean(r.get(key)), "kind": _clean(r.get("kind")), "explanation": _clean(r.get("explanation")), "note": _clean(r.get("note"))}
            for r in tbl["rows"] if _clean(r.get(key))]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def organize(book_dir, rows, call, write, log=lambda t: None, step=None, existing_factions=None):
    """rows：名詞表的列（parse_rows 的英文鍵；反推傳來的中文鍵也收，一進來就換成英文鍵）；
    call(label, text) → dict；write(rel, text) 寫草稿。
    step(key, label, text)：有快取時用（反推流程），沒有就直接 call。回傳匯報文字。"""
    raw_step = step or (lambda key, label, text: call(label, text))

    def step(key, label, text):
        # 模型資料一律換成英文鍵：名詞整理自己呼叫的已經是英文鍵；反推的呼叫與 .studio/reverse 的快取可能還是中文鍵
        d = raw_step(key, label, text)
        return jsonkeys.to_keys(d, values=False) if d else d
    rows = [tables.row_to_keys("glossary", r) for r in rows]
    texts = load_texts(book_dir)
    info = {}
    keep_rows = []
    junk = 0
    for r in rows:
        if JUNK.search(r["explanation"] or "") and not r["kind"] == "人物":
            junk += 1
            continue
        chs, sn = stats(texts, r["term"].split("／")[0])
        info[r["term"]] = {"chapters": chs, "snips": sn}
        keep_rows.append(r)
    log("名詞 %d 條（刪掉說明空白的 %d 條），開始分類" % (len(keep_rows), junk))

    # 1. 分類（人物列不送）
    cls = {}
    todo = [r for r in keep_rows if r["kind"] != "人物"]
    for i in range(0, len(todo), CLASSIFY_BATCH):
        part = todo[i:i + CLASSIFY_BATCH]
        body = "\n".join(_p("gl_cls_line", name=r["term"], cat=enums.show("term_cat", r["kind"], prompts.cur_lang()) or _p("gl_none"),
                             n=len(info[r["term"]]["chapters"]), desc=r["explanation"])
                         for r in part)
        d = step("org_cls_%d" % (i // CLASSIFY_BATCH), _p("gl_lbl_cls", i=i // CLASSIFY_BATCH + 1, total=(len(todo) + CLASSIFY_BATCH - 1) // CLASSIFY_BATCH),
                 _p("gl_classify_wrap", body=body, schema=_p("gl_classify_schema", topic_hint=_p("gl_topic_hint")))) or {}
        for x in d.get("terms") or []:
            if isinstance(x, dict) and _clean(x.get("term")):
                cls[_clean(x.get("term"))] = x

    def big_of(r):
        x = cls.get(r["term"]) or {}
        b = _clean(x.get("main_class"))
        return b if b in BIG else ("人物" if r["kind"] == "人物" else (r["kind"] if r["kind"] in BIG else "其他"))

    # 2. 勢力
    orgs = [r for r in keep_rows if big_of(r) == "組織" and _clean((cls.get(r["term"]) or {}).get("handling")) != "刪除"]
    where = {}          # 名詞 → 詳見哪份檔
    factions_out = 0
    moved = {}
    if orgs or existing_factions:
        ex = existing_factions if existing_factions is not None else [
            (e["name"], context.body(project.read_text(os.path.join(book_dir, e["file"])))[:700]) for e in project.list_entries(book_dir, layout.FACTIONS)]
        body = _p("gl_fac_head") + "\n" + "\n".join(_p("gl_fac_line", name=r["term"], n=len(info[r["term"]]["chapters"]), desc=r["explanation"]) for r in orgs)
        if ex:
            body += "\n\n" + _p("gl_fac_ex") + "\n" + "\n\n".join("〔%s〕\n%s" % (n, t) for n, t in ex)
        d = step("org_fac", _p("gl_lbl_fac"), _p("gl_fac_wrap", body=body, schema=_p("gl_faction_schema", unknown=_u()))) or {}
        from .reverse import render_faction
        for f in d.get("factions") or []:
            if not isinstance(f, dict) or not _clean(f.get("name")):
                continue
            name, text = render_faction(f)
            extra = ""
            if f.get("aliases"):
                extra += "\n## 別名\n" + "、".join(_clean(a) for a in f["aliases"] if _clean(a)) + "\n"
            if _clean(f.get("history")):
                extra += "\n## 沿革\n" + _clean(f.get("history")) + "\n"
            if f.get("sub_units"):
                extra += "\n## 內部編組\n" + "\n".join("- " + _clean(x) for x in f["sub_units"] if _clean(x)) + "\n"
            if _clean(f.get("author_check")):
                extra += "\n## 需要作者確認\n- " + _clean(f.get("author_check")) + "\n"
            text = text.replace("\n## 備註\n", extra + "\n## 備註\n", 1)
            rel = layout.entry(layout.FACTIONS, _fname(name))
            write(rel, text)
            factions_out += 1
            for n in [name] + list(f.get("aliases") or []) + list(f.get("sub_units") or []):
                where[_clean(n)] = rel
        for x in d.get("not_factions") or []:
            if isinstance(x, dict) and _clean(x.get("term")):
                moved[_clean(x.get("term"))] = _clean(x.get("change_to")) or "其他"

    # 3. 主題檔與獨立檔
    topics, own = {}, []
    for r in keep_rows:
        x = cls.get(r["term"]) or {}
        b = big_of(r)
        if moved.get(r["term"]) == "人物" or _clean(x.get("handling")) in ("刪除", "人物") or b not in TOPIC_BIG:
            continue
        n_ch = len(info[r["term"]]["chapters"])
        if b in OWN_FILE_BIG and n_ch >= OWN_FILE_MIN:
            own.append(r)
        t = _clean(x.get("topic")) or _default_topic(b)
        topics.setdefault(t, []).append(r)
    for t, items in topics.items():
        merged = {"one_line": "", "sections": [], "rules_limits": [], "plot_relevance": "", "flag": False}
        for j in range(0, len(items), TOPIC_BATCH):
            part = items[j:j + TOPIC_BATCH]
            body = "\n".join("- %s〔%s〕%s%s" % (
                r["term"], _clean((cls.get(r["term"]) or {}).get("subtype")) or big_of(r), r["explanation"],
                "".join("\n  " + _p("gl_snip", n=s[0], s=s[1]) for s in info[r["term"]]["snips"][:1])) for r in part)
            d = step("org_topic_%s_%d" % (t, j // TOPIC_BATCH), _p("gl_lbl_topic", topic=t),
                     _p("gl_topic_wrap", topic=t, body=body, schema=_p("gl_topic_schema", unknown=_u()))) or {}
            merged["one_line"] = merged["one_line"] or _clean(d.get("one_line"))
            merged["sections"] += [s for s in d.get("sections") or [] if isinstance(s, dict)]
            merged["rules_limits"] += [_clean(x) for x in d.get("rules_limits") or [] if _clean(x)]
            merged["plot_relevance"] = merged["plot_relevance"] or _clean(d.get("plot_relevance"))
            merged["flag"] = merged["flag"] or bool(d.get("_lang_mismatch"))
        rel = layout.entry(layout.WORLD, _fname(t))
        firsts = {r["term"]: (info[r["term"]]["chapters"] or [0])[0] for r in items}
        own_names = {r["term"] for r in own}
        shown = set()
        secs = []
        for s in merged["sections"]:
            lines = []
            for e in s.get("entries") or []:
                if not isinstance(e, dict) or not _clean(e.get("term")):
                    continue
                n = _clean(e.get("term"))
                shown.add(n)
                tail = []
                if firsts.get(n):
                    tail.append(_p("gl_first_seen", n="%03d" % firsts[n]))
                if n in own_names:
                    tail.append("詳見 bible/world/%s.md" % _fname(n))
                lines.append("- **%s**：%s%s" % (n, _clean(e.get("explanation")) or _u(), "（%s）" % "；".join(tail) if tail else ""))
            if lines:
                secs.append("## %s\n%s" % (_clean(s.get("heading")) or "其他", "\n".join(lines)))
        left = [r for r in items if r["term"] not in shown]
        if left:   # AI 漏掉的照原說明補上，不讓名詞消失
            secs.append("## 其他\n" + "\n".join("- **%s**：%s" % (r["term"], r["explanation"] or _u()) for r in left))
        rules = "\n".join("- " + x for x in merged["rules_limits"]) or "- " + _u()
        write(rel, ("---\ntype: 世界觀\nname: %s\nstatus: 草稿\nsource: 從名詞表整理\n---\n\n# %s\n\n## 一句話\n%s\n\n%s\n\n## 規則與限制\n%s\n\n"
                    "## 與劇情的關係\n%s\n\n## 備註\n- %s\n") % (
            t, t, merged["one_line"] or _u(), "\n\n".join(secs), rules, merged["plot_relevance"] or _u(),
            _p("gl_note_review") + (("\n- " + _p("lang_flag_note")) if merged["flag"] else "")))
        for r in items:
            where.setdefault(r["term"], rel)
    for j in range(0, len(own), OWN_BATCH):
        part = own[j:j + OWN_BATCH]
        body = "\n\n".join(_p("gl_own_line", name=r["term"], n=len(info[r["term"]]["chapters"]), a=info[r["term"]]["chapters"][0],
                              b=info[r["term"]]["chapters"][-1], desc=r["explanation"],
                              snips="\n".join(_p("gl_snip", n=s[0], s=s[1]) for s in info[r["term"]]["snips"])) for r in part)
        d = step("org_own_%d" % (j // OWN_BATCH), _p("gl_lbl_own", i=j // OWN_BATCH + 1, total=(len(own) + OWN_BATCH - 1) // OWN_BATCH),
                 _p("gl_own_wrap", body=body, schema=_p("gl_own_schema", unknown=_u()))) or {}
        got = {_clean(e.get("name")): e for e in d.get("entries") or [] if isinstance(e, dict)}
        for r in part:
            e = got.get(r["term"]) or {"one_line": r["explanation"]}
            rel = layout.entry(layout.WORLD, _fname(r["term"]))

            def lst(v):
                v = [_clean(x) for x in (v or []) if _clean(x)] if isinstance(v, list) else ([_clean(v)] if _clean(v) else [])
                return "\n".join("- " + x for x in v) or "- " + _u()
            write(rel, ("---\ntype: 世界觀\nname: %s\nstatus: 草稿\nsource: 從名詞表整理\n---\n\n# %s\n\n## 一句話\n%s\n\n## 特性\n%s\n\n## 來歷\n%s\n\n"
                        "## 在故事中的作用\n%s\n\n## 目前狀態\n%s\n\n## 限制與代價\n%s\n\n## 備註\n- %s\n") % (
                r["term"], r["term"], _clean(e.get("one_line")) or _u(), lst(e.get("traits")), _clean(e.get("origin")) or _u(),
                _clean(e.get("story_role")) or _u(), _clean(e.get("current_state")) or _u(), lst(e.get("limits_costs")),
                _p("gl_own_note", n=len(info[r["term"]]["chapters"]), a="%03d" % info[r["term"]]["chapters"][0], b="%03d" % info[r["term"]]["chapters"][-1]) +
                (("\n- " + _p("lang_flag_note")) if e.get("_lang_mismatch") else "")))
            where[r["term"]] = rel

    # 4. 名詞表（索引）
    out_rows, n_del = [], 0
    for r in keep_rows:
        x = cls.get(r["term"]) or {}
        act = _clean(x.get("handling"))
        if act == "刪除":
            n_del += 1
            continue
        b = big_of(r)
        if act == "人物" or moved.get(r["term"]) == "人物":
            b = "人物"
        sub = _clean(x.get("subtype"))
        note = [p for p in re.split(r"[；;]", r["note"]) if p.strip() and not p.strip().startswith("詳見")]
        if where.get(r["term"]):
            note.append("詳見 " + where[r["term"]])
        elif b == "事件":
            note.append("見 tracking/timeline.md")
        out_rows.append({"term": r["term"], "kind": b + ("／" + sub if sub and sub != b else ""), "explanation": r["explanation"], "note": "；".join(note)})
    order = {b: i for i, b in enumerate(BIG)}
    out_rows.sort(key=lambda x: (order.get(x["kind"].split("／")[0], 99), x["kind"]))
    from . import tracking
    write(layout.GLOSSARY, "---\ntype: 名詞表\nsource: 從名詞表整理\n---\n\n# 名詞表\n\n> " + _p("gl_table_note") + "\n\n" +
          tracking._render_table(tables.headers("glossary"), tables.rows_to_headers("glossary", out_rows)) + "\n")
    cnt = {}
    for r in out_rows:
        cnt[r["kind"].split("／")[0]] = cnt.get(r["kind"].split("／")[0], 0) + 1
    return ("名詞表 %d 條（%s）；刪掉 %d 條沒有內容的；主題檔 %d 份（%s）；獨立條目 %d 份；勢力 %d 份。" % (
        len(out_rows), "、".join("%s %d" % (k, v) for k, v in cnt.items()), junk + n_del, len(topics), "、".join(topics),
        len(own), factions_out))
