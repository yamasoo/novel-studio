"""把名詞表整理進設定集：細分類、依主題寫成世界觀檔、重要條目獨立成檔、合併勢力，名詞表留作索引。

- 名詞表每一條都保留（垃圾條目除外），一條一行，「注意」欄指到詳細內容在哪一份設定檔。寫稿時篩名詞表照常運作。
- 地點、物品、能力與技術、制度與習俗、生物依「主題」寫成 設定/世界觀/{主題}.md；出場 5 章以上的地點、物品、技術獨立成一份。
- 組織交給 AI 合併重複（例如縮寫與全名）、把不是勢力的移走、同一政權不同階段的名稱寫成沿革，拿不準的標「需要作者確認」。
- 事件留在名詞表，指到時間線；稱謂留在名詞表。
- 每個名詞從正文抓前後幾句當參考（本機搜尋，不重讀整本）。
結果寫成草稿，由「從正文建立設定」頁的「設定」組採用。

提示詞與寫出的說明文字跟著書的語言走（prompts 的語言包）；類別、欄位鍵名與 JSON 的列舉值維持中文，程式靠它們判斷。
"""
import os
import re

from . import context, enums, project, prompts, search

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
    for no, f in sorted(project._scan_dir(os.path.join(book_dir, "正文")).items()):
        t = context.body(project.read_text(os.path.join(book_dir, "正文", f)))
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
    tbl = project.read_table(book_dir, "設定/名詞表.md")
    key = tbl["headers"][0] if tbl["headers"] else "名詞"
    return [{"名詞": _clean(r.get(key)), "類別": _clean(r.get("類別")), "說明": _clean(r.get("說明")), "注意": _clean(r.get("注意"))}
            for r in tbl["rows"] if _clean(r.get(key))]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def organize(book_dir, rows, call, write, log=lambda t: None, step=None, existing_factions=None):
    """rows：[{名詞, 類別, 說明, 注意}]；call(label, text) → dict；write(rel, text) 寫草稿。
    step(key, label, text)：有快取時用（反推流程），沒有就直接 call。回傳匯報文字。"""
    step = step or (lambda key, label, text: call(label, text))
    texts = load_texts(book_dir)
    info = {}
    keep_rows = []
    junk = 0
    for r in rows:
        if JUNK.search(r["說明"] or "") and not r["類別"] == "人物":
            junk += 1
            continue
        chs, sn = stats(texts, r["名詞"].split("／")[0])
        info[r["名詞"]] = {"chapters": chs, "snips": sn}
        keep_rows.append(r)
    log("名詞 %d 條（刪掉說明空白的 %d 條），開始分類" % (len(keep_rows), junk))

    # 1. 分類（人物列不送）
    cls = {}
    todo = [r for r in keep_rows if r["類別"] != "人物"]
    for i in range(0, len(todo), CLASSIFY_BATCH):
        part = todo[i:i + CLASSIFY_BATCH]
        body = "\n".join(_p("gl_cls_line", name=r["名詞"], cat=enums.show("term_cat", r["類別"], prompts.cur_lang()) or _p("gl_none"),
                             n=len(info[r["名詞"]]["chapters"]), desc=r["說明"])
                         for r in part)
        d = step("org_cls_%d" % (i // CLASSIFY_BATCH), _p("gl_lbl_cls", i=i // CLASSIFY_BATCH + 1, total=(len(todo) + CLASSIFY_BATCH - 1) // CLASSIFY_BATCH),
                 _p("gl_classify_wrap", body=body, schema=_p("gl_classify_schema", topic_hint=_p("gl_topic_hint")))) or {}
        for x in d.get("名詞") or []:
            if isinstance(x, dict) and _clean(x.get("名詞")):
                cls[_clean(x.get("名詞"))] = x

    def big_of(r):
        x = cls.get(r["名詞"]) or {}
        b = _clean(x.get("大類"))
        return b if b in BIG else ("人物" if r["類別"] == "人物" else (r["類別"] if r["類別"] in BIG else "其他"))

    # 2. 勢力
    orgs = [r for r in keep_rows if big_of(r) == "組織" and _clean((cls.get(r["名詞"]) or {}).get("處理")) != "刪除"]
    where = {}          # 名詞 → 詳見哪份檔
    factions_out = 0
    moved = {}
    if orgs or existing_factions:
        ex = existing_factions if existing_factions is not None else [
            (e["name"], context.body(project.read_text(os.path.join(book_dir, e["file"])))[:700]) for e in project.list_entries(book_dir, "設定/勢力")]
        body = _p("gl_fac_head") + "\n" + "\n".join(_p("gl_fac_line", name=r["名詞"], n=len(info[r["名詞"]]["chapters"]), desc=r["說明"]) for r in orgs)
        if ex:
            body += "\n\n" + _p("gl_fac_ex") + "\n" + "\n\n".join("〔%s〕\n%s" % (n, t) for n, t in ex)
        d = step("org_fac", _p("gl_lbl_fac"), _p("gl_fac_wrap", body=body, schema=_p("gl_faction_schema", unknown=_u()))) or {}
        from .reverse import render_faction
        for f in d.get("勢力") or []:
            if not isinstance(f, dict) or not _clean(f.get("名稱")):
                continue
            name, text = render_faction(f)
            extra = ""
            if f.get("別名"):
                extra += "\n## 別名\n" + "、".join(_clean(a) for a in f["別名"] if _clean(a)) + "\n"
            if _clean(f.get("沿革")):
                extra += "\n## 沿革\n" + _clean(f.get("沿革")) + "\n"
            if f.get("內部編組"):
                extra += "\n## 內部編組\n" + "\n".join("- " + _clean(x) for x in f["內部編組"] if _clean(x)) + "\n"
            if _clean(f.get("需要作者確認")):
                extra += "\n## 需要作者確認\n- " + _clean(f.get("需要作者確認")) + "\n"
            text = text.replace("\n## 備註\n", extra + "\n## 備註\n", 1)
            rel = "設定/勢力/%s.md" % _fname(name)
            write(rel, text)
            factions_out += 1
            for n in [name] + list(f.get("別名") or []) + list(f.get("內部編組") or []):
                where[_clean(n)] = rel
        for x in d.get("不是勢力") or []:
            if isinstance(x, dict) and _clean(x.get("名詞")):
                moved[_clean(x.get("名詞"))] = _clean(x.get("改成")) or "其他"

    # 3. 主題檔與獨立檔
    topics, own = {}, []
    for r in keep_rows:
        x = cls.get(r["名詞"]) or {}
        b = big_of(r)
        if moved.get(r["名詞"]) == "人物" or _clean(x.get("處理")) in ("刪除", "人物") or b not in TOPIC_BIG:
            continue
        n_ch = len(info[r["名詞"]]["chapters"])
        if b in OWN_FILE_BIG and n_ch >= OWN_FILE_MIN:
            own.append(r)
        t = _clean(x.get("主題")) or _default_topic(b)
        topics.setdefault(t, []).append(r)
    for t, items in topics.items():
        merged = {"一句話": "", "分區": [], "規則與限制": [], "與劇情的關係": "", "flag": False}
        for j in range(0, len(items), TOPIC_BATCH):
            part = items[j:j + TOPIC_BATCH]
            body = "\n".join("- %s〔%s〕%s%s" % (
                r["名詞"], _clean((cls.get(r["名詞"]) or {}).get("小類")) or big_of(r), r["說明"],
                "".join("\n  " + _p("gl_snip", n=s[0], s=s[1]) for s in info[r["名詞"]]["snips"][:1])) for r in part)
            d = step("org_topic_%s_%d" % (t, j // TOPIC_BATCH), _p("gl_lbl_topic", topic=t),
                     _p("gl_topic_wrap", topic=t, body=body, schema=_p("gl_topic_schema", unknown=_u()))) or {}
            merged["一句話"] = merged["一句話"] or _clean(d.get("一句話"))
            merged["分區"] += [s for s in d.get("分區") or [] if isinstance(s, dict)]
            merged["規則與限制"] += [_clean(x) for x in d.get("規則與限制") or [] if _clean(x)]
            merged["與劇情的關係"] = merged["與劇情的關係"] or _clean(d.get("與劇情的關係"))
            merged["flag"] = merged["flag"] or bool(d.get("_lang_mismatch"))
        rel = "設定/世界觀/%s.md" % _fname(t)
        firsts = {r["名詞"]: (info[r["名詞"]]["chapters"] or [0])[0] for r in items}
        own_names = {r["名詞"] for r in own}
        shown = set()
        secs = []
        for s in merged["分區"]:
            lines = []
            for e in s.get("條目") or []:
                if not isinstance(e, dict) or not _clean(e.get("名詞")):
                    continue
                n = _clean(e.get("名詞"))
                shown.add(n)
                tail = []
                if firsts.get(n):
                    tail.append(_p("gl_first_seen", n="%03d" % firsts[n]))
                if n in own_names:
                    tail.append("詳見 設定/世界觀/%s.md" % _fname(n))
                lines.append("- **%s**：%s%s" % (n, _clean(e.get("說明")) or _u(), "（%s）" % "；".join(tail) if tail else ""))
            if lines:
                secs.append("## %s\n%s" % (_clean(s.get("標題")) or "其他", "\n".join(lines)))
        left = [r for r in items if r["名詞"] not in shown]
        if left:   # AI 漏掉的照原說明補上，不讓名詞消失
            secs.append("## 其他\n" + "\n".join("- **%s**：%s" % (r["名詞"], r["說明"] or _u()) for r in left))
        rules = "\n".join("- " + x for x in merged["規則與限制"]) or "- " + _u()
        write(rel, ("---\n類型: 世界觀\n名稱: %s\n狀態: 草稿\n來源: 從名詞表整理\n---\n\n# %s\n\n## 一句話\n%s\n\n%s\n\n## 規則與限制\n%s\n\n"
                    "## 與劇情的關係\n%s\n\n## 備註\n- %s\n") % (
            t, t, merged["一句話"] or _u(), "\n\n".join(secs), rules, merged["與劇情的關係"] or _u(),
            _p("gl_note_review") + (("\n- " + _p("lang_flag_note")) if merged["flag"] else "")))
        for r in items:
            where.setdefault(r["名詞"], rel)
    for j in range(0, len(own), OWN_BATCH):
        part = own[j:j + OWN_BATCH]
        body = "\n\n".join(_p("gl_own_line", name=r["名詞"], n=len(info[r["名詞"]]["chapters"]), a=info[r["名詞"]]["chapters"][0],
                              b=info[r["名詞"]]["chapters"][-1], desc=r["說明"],
                              snips="\n".join(_p("gl_snip", n=s[0], s=s[1]) for s in info[r["名詞"]]["snips"])) for r in part)
        d = step("org_own_%d" % (j // OWN_BATCH), _p("gl_lbl_own", i=j // OWN_BATCH + 1, total=(len(own) + OWN_BATCH - 1) // OWN_BATCH),
                 _p("gl_own_wrap", body=body, schema=_p("gl_own_schema", unknown=_u()))) or {}
        got = {_clean(e.get("名稱")): e for e in d.get("條目") or [] if isinstance(e, dict)}
        for r in part:
            e = got.get(r["名詞"]) or {"一句話": r["說明"]}
            rel = "設定/世界觀/%s.md" % _fname(r["名詞"])

            def lst(v):
                v = [_clean(x) for x in (v or []) if _clean(x)] if isinstance(v, list) else ([_clean(v)] if _clean(v) else [])
                return "\n".join("- " + x for x in v) or "- " + _u()
            write(rel, ("---\n類型: 世界觀\n名稱: %s\n狀態: 草稿\n來源: 從名詞表整理\n---\n\n# %s\n\n## 一句話\n%s\n\n## 特性\n%s\n\n## 來歷\n%s\n\n"
                        "## 在故事中的作用\n%s\n\n## 目前狀態\n%s\n\n## 限制與代價\n%s\n\n## 備註\n- %s\n") % (
                r["名詞"], r["名詞"], _clean(e.get("一句話")) or _u(), lst(e.get("特性")), _clean(e.get("來歷")) or _u(),
                _clean(e.get("在故事中的作用")) or _u(), _clean(e.get("目前狀態")) or _u(), lst(e.get("限制與代價")),
                _p("gl_own_note", n=len(info[r["名詞"]]["chapters"]), a="%03d" % info[r["名詞"]]["chapters"][0], b="%03d" % info[r["名詞"]]["chapters"][-1]) +
                (("\n- " + _p("lang_flag_note")) if e.get("_lang_mismatch") else "")))
            where[r["名詞"]] = rel

    # 4. 名詞表（索引）
    out_rows, n_del = [], 0
    for r in keep_rows:
        x = cls.get(r["名詞"]) or {}
        act = _clean(x.get("處理"))
        if act == "刪除":
            n_del += 1
            continue
        b = big_of(r)
        if act == "人物" or moved.get(r["名詞"]) == "人物":
            b = "人物"
        sub = _clean(x.get("小類"))
        note = [p for p in re.split(r"[；;]", r["注意"]) if p.strip() and not p.strip().startswith("詳見")]
        if where.get(r["名詞"]):
            note.append("詳見 " + where[r["名詞"]])
        elif b == "事件":
            note.append("見 追蹤/時間線.md")
        out_rows.append({"名詞": r["名詞"], "類別": b + ("／" + sub if sub and sub != b else ""), "說明": r["說明"], "注意": "；".join(note)})
    order = {b: i for i, b in enumerate(BIG)}
    out_rows.sort(key=lambda x: (order.get(x["類別"].split("／")[0], 99), x["類別"]))
    from . import tracking
    write("設定/名詞表.md", "---\n類型: 名詞表\n來源: 從名詞表整理\n---\n\n# 名詞表\n\n> " + _p("gl_table_note") + "\n\n" +
          tracking._render_table(["名詞", "類別", "說明", "注意"], out_rows) + "\n")
    cnt = {}
    for r in out_rows:
        cnt[r["類別"].split("／")[0]] = cnt.get(r["類別"].split("／")[0], 0) + 1
    return ("名詞表 %d 條（%s）；刪掉 %d 條沒有內容的；主題檔 %d 份（%s）；獨立條目 %d 份；勢力 %d 份。" % (
        len(out_rows), "、".join("%s %d" % (k, v) for k, v in cnt.items()), junk + n_del, len(topics), "、".join(topics),
        len(own), factions_out))
