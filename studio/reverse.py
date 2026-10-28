"""從成稿反推設定（匯入完成的書用，不需要開書訪談）。

流程（做法參考 oh-story-claudecode 的 story-import／story-long-analyze，MIT；內容與格式依本工作台重寫）：
1. 逐章抽取：依執行者的上下文長度分批（每批 1～3 章），照章節順序。每批帶著「跨批狀態」
   （已知人物與別名、還沒收的伏筆與懸念、上一章結尾）往下跑；每批結果存檔，中斷了從斷的地方接。
2. 本機累積：人物、別名、名詞、事件、伏筆、讀者認知在本機合併編號，不重讀正文。
3. 整理：請 AI 根據累積資料寫角色檔、勢力、世界觀、故事核心、全書大綱與卷綱、狀態卡、主要角色的目前狀態。
4. 本機產生：名詞表、反向章綱、章節摘要、伏筆表、時間線、讀者認知帳本。

全部先存成草稿（.studio/反推/草稿/），分「設定／大綱／章綱／追蹤」四組讓作者採用或捨棄。
推不出來的欄位寫「（正文未明確）」或「待補」，不編造。
"""
import json
import os
import re
import shutil
import time

from . import context, enums, project, prompts, tracking

DIR = os.path.join(".studio", "反推")
GROUPS = ("設定", "大綱", "章綱", "追蹤")
MAX_PER_BATCH = 3
CORE_MIN_CHAPTERS = 3      # 出場 3 章以上才建角色檔；其他列進名詞表
MAX_CORE = 40
CHARS_PER_CALL = 5
ARC_CHAPTERS = 30          # 寫卷綱前，每 30 章先整理一段
FACTION_MIN = 2

# ---------------------------------------------------------------------------
# 規則與欄位的提示詞：由語言包（prompts）取得，依書的語言。JSON 鍵名與枚舉值維持中文（程式解析用）。
# ---------------------------------------------------------------------------
def _rv(key, **subs):
    s = prompts.cur()[key]
    for k, v in subs.items():
        s = s.replace("{%s}" % k, v)
    return s


def unknown():
    return prompts.cur()["rev_unknown"]


def _t(key, **kw):
    """語言包裡的一般文字（{名字} 用 str.format 帶入）。"""
    s = prompts.cur()[key]
    return s.format(**kw) if kw else s


def extract_schema():
    return _rv("rev_extract_schema")


def extract_rules():
    return _rv("rev_extract_rules", lang_rule=prompts.cur()["extract_lang_rule"])


def char_schema():
    return _rv("rev_char_schema", unknown=unknown())


def world_schema():
    lang = prompts.cur_lang()
    cats = "、".join(WORLD_CATS) if lang == "zh-TW" else enums.display("world_cat", lang, sep=prompts.cur()["list_sep"])
    return _rv("rev_world_schema", cats=cats, unknown=unknown())


def arc_schema():
    return _rv("rev_arc_schema", arc_len=prompts.cur()["arc_len"])


def book_schema():
    return _rv("rev_book_schema", unknown=unknown())


def state_schema():
    return _rv("rev_state_schema")





# ---------------------------------------------------------------------------
# 檔案與狀態
# ---------------------------------------------------------------------------
def _p(book_dir, *parts):
    return os.path.join(book_dir, DIR, *parts)


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def chapters(book_dir):
    out = []
    for no, f in sorted(project._scan_dir(os.path.join(book_dir, "正文")).items()):
        text = project.read_text(os.path.join(book_dir, "正文", f))
        out.append({"no": no, "title": project.chapter_title_from_filename(f), "file": "正文/" + f,
                    "chars": project.count_chars(context.body(text))})
    return out


def state(book_dir):
    st = _load(_p(book_dir, "state.json"), {})
    acc = _load(_p(book_dir, "累積.json"), {})
    st["processed"] = sorted(int(k) for k in (acc.get("summaries") or {}))
    st["drafts"] = draft_groups(book_dir)
    return st


def reset(book_dir):
    d = _p(book_dir)
    if os.path.isdir(d):
        bak = os.path.join(book_dir, ".studio", "備份", "反推_%d" % int(time.time()))
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        shutil.move(d, bak)


# ---------------------------------------------------------------------------
# 估算與分批
# ---------------------------------------------------------------------------
def plan_batches(book_dir, upto, budget, out_reserve, start=1):
    """依上下文預算把第 start～upto 章分批（每批最多 3 章）。"""
    room = max(1500, budget - out_reserve - 3500)   # 3500：規則、格式與跨批狀態
    batches, cur, used = [], [], 0
    for c in chapters(book_dir):
        if c["no"] > upto:
            break
        if c["no"] < start:
            continue
        t = context.est_tokens(context.body(project.read_text(os.path.join(book_dir, c["file"]))))
        if cur and (len(cur) >= MAX_PER_BATCH or used + t > room):
            batches.append(cur)
            cur, used = [], 0
        cur.append(c["no"])
        used += t
    if cur:
        batches.append(cur)
    return batches


def estimate(book_dir, prov, upto=None):
    chs = chapters(book_dir)
    if not chs:
        return {"chapters": 0}
    upto = upto or chs[-1]["no"]
    sel = [c for c in chs if c["no"] <= upto]
    text_tok = sum(context.est_tokens(context.body(project.read_text(os.path.join(book_dir, c["file"])))) for c in sel)
    total = int(prov.get("context_tokens") or (180000 if prov.get("type") == "claude_code" else 32768))
    out_res = min(int(prov.get("max_output") or 8192), 16384)
    nb = len(plan_batches(book_dir, upto, total, out_res))
    tok_in = text_tok + nb * 4500 + len(sel) * 150          # 跨批狀態與整理步驟
    tok_out = len(sel) * 900 + 20000
    usage = {"prompt_tokens": tok_in, "completion_tokens": tok_out}
    from . import providers
    return {"chapters": len(sel), "upto": upto, "total_chapters": len(chs), "chars": sum(c["chars"] for c in sel),
            "batches": nb, "tokens_in": tok_in, "tokens_out": tok_out, "cost": providers.cost_of(prov, usage),
            "provider": prov.get("name")}


# ---------------------------------------------------------------------------
# 1. 逐章抽取
# ---------------------------------------------------------------------------
def _handoff(acc, first_no):
    P = prompts.cur()
    lines = []
    chars = sorted((acc.get("chars") or {}).items(), key=lambda kv: -len(kv[1]["chapters"]))[:80]
    if chars:
        lines.append(P["rev_h_known"] + "\n" + "\n".join(
            "- %s%s" % (k, (P["colon"] + P["list_sep"].join(v["aliases"])) if v["aliases"] else "") for k, v in chars))
    fs = [x for x in (acc.get("fs") or []) if x["狀態"] != "已回收"][-50:]
    if fs:
        lines.append(P["rev_h_open_fs"] + "\n" + "\n".join(_t("rev_fs_line", id=x["編號"], ch=x["埋設章"], text=x["內容"]) for x in fs))
    rp = [x for x in (acc.get("reader") or []) if x["類型"] != "已知" and not x.get("回收章")][-50:]
    if rp:
        lines.append(P["rev_h_open_rp"] + "\n" + "\n".join("- %s〔%s〕%s" % (x["編號"], enums.show("type", x["類型"], prompts.cur_lang()), x["內容"])
                                                          for x in rp))
    prev = (acc.get("summaries") or {}).get(str(first_no - 1))
    if prev:
        lines.append(_t("rev_h_prev_end", n=first_no - 1) + "\n" + prev.get("結尾停在", ""))
    return "\n\n".join(lines)


def extract_prompt(book_dir, nos, acc):
    parts = []
    for no in nos:
        path, text = context.chapter_text(book_dir, no, ("正文",))
        parts.append(_t("rev_ch_head", n=no, title=project.chapter_title_from_filename(os.path.basename(path or ""))) + "\n" +
                     context.body(text))
    hand = _handoff(acc, nos[0])
    return ((hand + "\n\n" if hand else "") + "\n\n".join(parts) + _t("task_mark") +
            _t("rev_extract_task", a=nos[0], b=nos[-1]) + "\n%s\n\n%s" % (extract_rules(), extract_schema()))


def _clean(s):
    return str(s or "").replace("|", "／").replace("\n", " ").strip()


def _canon(acc, names):
    idx = acc.setdefault("alias_index", {})
    for n in names:
        if n in idx:
            return idx[n]
    return None


def apply_batch(acc, data, nos, titles):
    """把一批的抽取結果併進累積資料（本機，不呼叫 AI）。"""
    got = {}
    for ch in (data or {}).get("chapters") or []:
        try:
            got[int(ch.get("章"))] = ch
        except (TypeError, ValueError):
            continue
    if len(got) < len(nos) and len((data or {}).get("chapters") or []) == len(nos):
        got = {n: ch for n, ch in zip(nos, data["chapters"])}   # 章號寫錯但數量對：照順序對應
    for no in nos:
        ch = got.get(no) or {}
        acc.setdefault("summaries", {})[str(no)] = {k: _clean((ch.get("摘要") or {}).get(k)) for k in
                                                    ("發生了什麼", "局面變化", "新出現的人事物", "結尾停在")}
        card = ch.get("章綱") or {}
        acc.setdefault("cards", {})[str(no)] = {
            "title": titles.get(no, ""),
            **{k: _clean(card.get(k)) for k in ("主角想做什麼", "阻礙", "局面變成", "讀者為什麼往下看", "功能", "情緒", "章末鉤子")},
            "情節點": [_clean(x) for x in (card.get("情節點") or []) if _clean(x)],
            "出場": [], "伏筆操作": []}
        if ch.get("_lang_mismatch"):
            acc["cards"][str(no)]["lang_flag"] = True
        cd = acc["cards"][str(no)]
        # 人物
        chars = acc.setdefault("chars", {})
        idx = acc.setdefault("alias_index", {})
        for p in ch.get("人物") or []:
            if not isinstance(p, dict):
                continue
            name = _clean(p.get("名稱"))
            if len(name) < 2:
                continue
            al = [_clean(a) for a in (p.get("別名") or []) if len(_clean(a)) >= 2 and _clean(a) != name]
            canon = _canon(acc, [name] + al)
            if not canon:
                canon = name
                chars[canon] = {"aliases": [], "chapters": [], "notes": [], "votes": {}}
                idx[canon] = canon
            c = chars[canon]
            for a in ([name] if name != canon else []) + al:
                if a not in c["aliases"] and a != canon and a not in idx:
                    c["aliases"].append(a)
                    idx[a] = canon
            if no not in c["chapters"]:
                c["chapters"].append(no)
            note = "；".join(x for x in (_clean(p.get("身分")), _clean(p.get("本章"))) if x)
            if note:
                c["notes"].append([no, note])
            imp = _clean(p.get("重要")) or "次要"
            c["votes"][imp] = c["votes"].get(imp, 0) + 1
            if canon not in cd["出場"]:
                cd["出場"].append(canon)
        # 名詞
        terms = acc.setdefault("terms", {})
        for t in ch.get("名詞") or []:
            if not isinstance(t, dict):
                continue
            n = _clean(t.get("名詞"))
            if len(n) < 2 or n in idx:
                continue
            e = terms.setdefault(n, {"類別": _clean(t.get("類別")) or "其他", "小類": _clean(t.get("小類")), "說明": "", "chapters": []})
            d = _clean(t.get("說明"))
            if d and len(d) > len(e["說明"]):
                e["說明"] = d[:120]
            if no not in e["chapters"]:
                e["chapters"].append(no)
        # 事件
        evs = acc.setdefault("events", [])
        for ev in ch.get("事件") or []:
            if isinstance(ev, dict) and _clean(ev.get("實際發生")):
                evs.append({"編號": "E%03d" % (len(evs) + 1), "故事時間": _clean(ev.get("故事時間")),
                            "實際發生（作者真相）": _clean(ev.get("實際發生")), "讀者目前知道": _clean(ev.get("讀者知道")),
                            "揭示章": tracking.chapter_label(no), "相關角色": _clean(ev.get("相關角色"))})
        # 伏筆
        fs = acc.setdefault("fs", [])
        by = {x["編號"]: x for x in fs}
        for f in ch.get("伏筆") or []:
            if not isinstance(f, dict):
                continue
            fid, act = _clean(f.get("編號")), _clean(f.get("動作"))
            if fid in by:
                x = by[fid]
                x["最後出現"] = tracking.chapter_label(no)
                if act == "回收":
                    x["狀態"], x["回收章"] = "已回收", tracking.chapter_label(no)
                elif x["狀態"] != "已回收":
                    x["狀態"] = "推進中"
                cd["伏筆操作"].append(_t("rev_fs_op_pay" if act == "回收" else "rev_fs_op_adv", id=fid, text=x["內容"][:20]))
            elif _clean(f.get("內容")) and act != "回收":
                x = {"編號": "F%03d" % (len(fs) + 1), "內容": _clean(f.get("內容")), "埋設章": tracking.chapter_label(no),
                     "預計回收": "", "最後出現": tracking.chapter_label(no), "狀態": "已埋",
                     "重要度": _clean(f.get("重要度")) if _clean(f.get("重要度")) in ("高", "中", "低") else "中"}
                fs.append(x)
                by[x["編號"]] = x
                cd["伏筆操作"].append(_t("rev_fs_op_new", id=x["編號"], text=x["內容"][:20]))
        # 讀者認知
        rp = acc.setdefault("reader", [])
        rby = {x["編號"]: x for x in rp}
        for r in ch.get("讀者") or []:
            if not isinstance(r, dict):
                continue
            rid = _clean(r.get("編號"))
            if rid in rby:
                if _clean(r.get("動作")) == "回收" or _clean(r.get("作者真相")):
                    rby[rid]["回收章"] = tracking.chapter_label(no)
                    if _clean(r.get("作者真相")):
                        rby[rid]["作者真相"] = _clean(r.get("作者真相"))
            elif _clean(r.get("內容")) and _clean(r.get("動作")) != "回收":
                x = {"編號": "R%03d" % (len(rp) + 1), "類型": _clean(r.get("類型")) if _clean(r.get("類型")) in tracking.RP_TYPES else "懸念",
                     "內容": _clean(r.get("內容")), "作者真相": _clean(r.get("作者真相")),
                     "種下章": tracking.chapter_label(no), "回收章": "", "相關角色": ""}
                rp.append(x)
                rby[x["編號"]] = x
    return acc


# ---------------------------------------------------------------------------
# 3. 整理（AI）
# ---------------------------------------------------------------------------
def core_characters(acc):
    out = []
    for name, c in (acc.get("chars") or {}).items():
        n = len(c["chapters"])
        main = c["votes"].get("主要", 0)
        if n >= CORE_MIN_CHAPTERS or main >= 2:
            out.append((n + main, name))
    out.sort(reverse=True)
    return [n for _, n in out[:MAX_CORE]]


def _sample(notes, k=24):
    if len(notes) <= k:
        return notes
    step = len(notes) / k
    return [notes[int(i * step)] for i in range(k - 1)] + [notes[-1]]




def char_prompts(acc):
    names = core_characters(acc)
    out = []
    for i in range(0, len(names), CHARS_PER_CALL):
        part = names[i:i + CHARS_PER_CALL]
        blocks = []
        for n in part:
            c = acc["chars"][n]
            blocks.append(_t("rev_char_block", name=n, aliases=_t("list_sep").join(c["aliases"]) or _t("rev_none"),
                             count=len(c["chapters"]), a=min(c["chapters"]), b=max(c["chapters"])) + "\n" +
                          "\n".join(_t("rev_note_line", n=no, text=t) for no, t in _sample(c["notes"])))
        out.append(("整理角色 %d／%d" % (i // CHARS_PER_CALL + 1, (len(names) + CHARS_PER_CALL - 1) // CHARS_PER_CALL),
                    _t("rev_char_intro") + "\n\n" + "\n\n".join(blocks) + "\n\n" + char_schema()))
    return out


WORLD_CATS = ["力量體系", "地理與氣候", "歷史與年表", "社會與政治", "經濟與物資", "宗教信仰",
              "文化與風俗", "科技原理", "載具與兵器", "生態與資源", "其他"]



def world_prompt(acc):
    terms = acc.get("terms") or {}
    other = sorted(terms.items(), key=lambda kv: -len(kv[1]["chapters"]))[:60]
    lines = [_t("rev_h_top_terms")] + ["- %s〔%s〕%s" % (k, enums.show("term_cat", v["類別"], prompts.cur_lang()), v["說明"]) for k, v in other]
    sums = acc.get("summaries") or {}
    keys = sorted(sums, key=int)
    pick = keys[::max(1, len(keys) // 12)][:12]
    lines += ["", _t("rev_h_some_sums")] + [_t("rev_note_line", n=k, text=sums[k]["發生了什麼"]) for k in pick]
    return "\n".join(lines) + "\n\n" + world_schema(), []




def arc_prompts(acc):
    sums = acc.get("summaries") or {}
    keys = sorted((int(k) for k in sums))
    out = []
    for i in range(0, len(keys), ARC_CHAPTERS):
        part = keys[i:i + ARC_CHAPTERS]
        body = "\n".join(_t("rev_arc_line", n=k, title=(acc["cards"].get(str(k)) or {}).get("title", ""),
                             what=sums[str(k)]["發生了什麼"], change=sums[str(k)]["局面變化"]) for k in part)
        out.append(("整理第%d～%d章的劇情段落" % (part[0], part[-1]), part[0], part[-1],
                    _t("rev_arc_intro", a=part[0], b=part[-1]) + "\n\n%s\n\n%s" % (body, arc_schema())))
    return out




def book_prompt(acc, arcs, title):
    lines = [_t("rev_book_title", title=title), "", _t("rev_h_arcs")]
    for a in arcs:
        lines.append(_t("rev_arc_seg_line", a=a["起"], b=a["訖"], text=a.get("段落摘要", "")))
        for u in a.get("單元") or []:
            lines.append(_t("rev_unit_line", name=u.get("名稱", ""), range=u.get("起訖", ""), conflict=u.get("衝突", ""),
                            result=u.get("結果與代價", "")))
    core = core_characters(acc)[:8]
    lines += ["", _t("rev_h_main_chars") + _t("list_sep").join(core)]
    return "\n".join(lines) + "\n\n" + book_schema()




def state_prompt(acc, last_no):
    sums = acc.get("summaries") or {}
    keys = sorted(int(k) for k in sums)[-5:]
    lines = [_t("rev_h_recent")] + [_t("rev_state_line", n=k, what=sums[str(k)]["發生了什麼"], change=sums[str(k)]["局面變化"],
                                     end=sums[str(k)]["結尾停在"]) for k in keys]
    fs = [x for x in acc.get("fs") or [] if x["狀態"] != "已回收"][-20:]
    lines += ["", _t("rev_h_open_fs")] + ["- %s %s" % (x["編號"], x["內容"]) for x in fs]
    rp = [x for x in acc.get("reader") or [] if x["類型"] != "已知" and not x.get("回收章")][-15:]
    lines += ["", _t("rev_h_waiting")] + ["- %s %s" % (x["編號"], x["內容"]) for x in rp]
    return _t("rev_state_head", n=last_no) + "\n".join(lines) + "\n\n" + state_schema()


# ---------------------------------------------------------------------------
# 4. 產生草稿（本機）
# ---------------------------------------------------------------------------
def _flag(d):
    """語言重試後仍不符的資料：備註加一行待核對（只有英文、日文書會有這個標記）。"""
    return ("\n- " + _t("lang_flag_note")) if isinstance(d, dict) and d.get("_lang_mismatch") else ""


def _v(x):
    s = x if isinstance(x, str) else ("、".join(str(i) for i in x) if isinstance(x, list) else str(x or ""))
    return s.strip() or unknown()


def _write_draft(book_dir, rel, text):
    path = _p(book_dir, "草稿", *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.rstrip("\n") + "\n")


def _fname(s):
    return project.safe_filename(s, 40)


def render_character(ch, acc, last_label):
    name = _clean(ch.get("名稱"))
    info = (acc.get("chars") or {}).get(name) or {}
    al = list(dict.fromkeys([a for a in (ch.get("別名") or []) if a] + info.get("aliases", [])))
    first = min(info.get("chapters") or [0]) or ""
    rel = "".join("\n- %s" % r for r in (ch.get("關係") or [])) or "\n- " + unknown()
    text = ("---\n類型: 角色\n名稱: %s\n別名: [%s]\n定位: %s\n首次登場: %s\n狀態: 草稿\n來源: 從正文反推\n---\n\n# %s\n\n"
            "## 一句話\n%s\n\n## 外在\n- 年齡／身分：%s\n- 外貌辨識點：%s\n\n## 內在\n- 想要：%s\n- 害怕：%s\n- 缺陷：%s\n- 底線：%s\n- 秘密：%s\n\n"
            "## 說話方式（聲音卡）\n- %s\n\n## 關係%s\n\n## 角色弧線\n%s\n\n## 備註\n%s\n") % (
        name, ", ".join(al), _clean(ch.get("定位")) or "配角", first, name, _v(ch.get("一句話")), _v(ch.get("年齡身分")),
        _v(ch.get("外貌")), _v(ch.get("想要")), _v(ch.get("害怕")), _v(ch.get("缺陷")), _v(ch.get("底線")), _v(ch.get("秘密")),
        _v(ch.get("說話方式")), rel, _v(ch.get("角色弧線")),
        _t("rev_note_char", count=len(info.get("chapters") or []), a=first, b=max(info.get("chapters") or [0]) or "") + _flag(ch))
    st = ch.get("目前狀態") or {}
    last = max(info.get("chapters") or [0]) or 0
    stext = "---\n類型: 角色狀態\n名稱: %s\n更新至: %s\n最後登場: %s\n---\n\n# %s：目前狀態\n\n%s\n\n" % (
        name, last_label, tracking.chapter_label(last) if last else "", name, _t("rev_state_note"))
    stext += "\n".join("- %s：%s" % (k, _v(st.get(k))) for k in tracking.CHAR_FIELDS)
    return name, text, stext


def render_faction(f):
    name = _clean(f.get("名稱"))
    return name, ("---\n類型: 勢力\n名稱: %s\n狀態: 草稿\n相關角色: [%s]\n來源: 從正文反推\n---\n\n# %s\n\n## 一句話\n%s\n\n## 基本資料\n"
                  "- 規模與地盤：%s\n- 首領：%s\n- 主要成員：%s\n- 資源與手段：%s\n\n## 目標與利益\n- 想要什麼：%s\n- 和誰有衝突：%s\n- 和誰有合作：%s\n\n"
                  "## 內部規矩\n%s\n\n## 對主角的態度\n%s\n\n## 備註\n%s\n") % (
        name, ", ".join(f.get("相關角色") or []), name, _v(f.get("一句話")), _v(f.get("規模與地盤")), _v(f.get("首領")),
        _v(f.get("主要成員")), _v(f.get("資源與手段")), _v(f.get("想要什麼")), _v(f.get("和誰有衝突")), _v(f.get("和誰有合作")),
        _v(f.get("內部規矩")), _v(f.get("對主角的態度")), _t("rev_note_review") + _flag(f))


def render_world(w):
    name = _clean(w.get("名稱")) or _t("rev_bg_name")
    cat = _clean(w.get("分類"))
    cat = cat if cat in WORLD_CATS else "其他"
    tags = [_clean(t) for t in (w.get("標籤") or []) if _clean(t)] if isinstance(w.get("標籤"), list) else []
    rules = "\n".join("- " + _clean(r) for r in (w.get("規則") or []) if _clean(r)) or "- " + unknown()
    cost = "\n".join("- " + _clean(r) for r in (w.get("代價與限制") or []) if _clean(r)) or "- " + unknown()
    return name, ("---\n類型: 世界觀\n分類: %s\n標籤: [%s]\n名稱: %s\n狀態: 草稿\n來源: 從正文反推\n---\n\n# %s\n\n## 一句話\n%s\n\n## 規則\n%s\n\n## 代價與限制\n%s\n\n"
                  "## 讀者何時知道\n%s\n\n## 與劇情的關係\n%s\n\n## 備註\n%s\n") % (
        cat, ", ".join(tags), name, name, _v(w.get("一句話")), rules, cost, _t("rev_world_when"), _v(w.get("與劇情的關係")),
        _t("rev_note_review") + _flag(w))


def render_core(c, title):
    def lst(x):
        items = [i for i in (x or []) if str(i).strip()] if isinstance(x, list) else [x]
        return "\n".join("%d. %s" % (i + 1, _v(v)) for i, v in enumerate(items)) or "1. " + unknown()
    return ("---\n類型: 故事核心\n書名: %s\n狀態: 草稿\n來源: 從正文反推\n---\n\n# 故事核心\n\n## 一句話鉤子\n%s\n\n## 題材與定位\n- 題材：%s\n- 目標讀者：%s\n"
            "- 發表平台與更新節奏：%s\n- 預計篇幅：%s\n- 敘事視角：%s\n\n## 賣點（讀者為什麼看）\n%s\n\n## 主角\n- 想要什麼（外在目標）：%s\n"
            "- 真正需要什麼（內在成長）：%s\n- 最大的缺陷或限制：%s\n- 金手指／特殊優勢（有的話）：%s\n\n## 故事引擎\n%s\n\n## 核心衝突\n- 主要對手：%s\n- 衝突根源：%s\n\n"
            "## 讀者契約\n%s\n\n## 終局方向\n%s\n\n## 升級台階\n%s\n") % (
        _clean(c.get("書名")) or title, _v(c.get("一句話鉤子")), _v(c.get("題材")), _v(c.get("目標讀者")), _t("rev_fill"), _t("rev_fill"),
        _v(c.get("敘事視角")),
        lst(c.get("賣點")), _v(c.get("主角想要")), _v(c.get("主角需要")), _v(c.get("主角缺陷")), _v(c.get("金手指")),
        _v(c.get("故事引擎")), _v(c.get("主要對手")), _v(c.get("衝突根源")),
        "\n".join("- " + _v(x) for x in (c.get("讀者契約") or [])) or "- " + unknown(), _v(c.get("終局方向")), lst(c.get("升級台階"))) + (
        "\n## 備註%s\n" % _flag(c) if _flag(c) else "")


CN_VOL = "一二三四五六七八九十"


def _vol_name(i):
    return "第%s卷" % (CN_VOL[i] if i < 10 else str(i + 1))


def render_outline(book, vols, arcs):
    lines = ["---\n類型: 全書大綱\n狀態: 草稿\n來源: 從正文反推\n---\n\n# 全書大綱\n\n## 總覽",
             "- 預計卷數與字數：" + _t("rev_vols_written", n=len(vols)),
             "- 主線一句話：%s" % _v((book.get("全書") or {}).get("主線一句話")),
             "- 終局：%s" % _v((book.get("全書") or {}).get("終局")), "", "## 分卷"]
    files = []
    for i, v in enumerate(vols):
        vn = _vol_name(i)
        nm = _clean(v.get("卷名")) or vn
        a, b = int(v.get("起") or 0), int(v.get("訖") or 0)
        lines += ["", "### %s：%s" % (vn, nm), "- 篇幅：第%d～%d章" % (a, b), "- 本卷目標：%s" % _v(v.get("本卷目標")),
                  "- 主要對手：%s" % _v(v.get("主要對手")), "- 卷末變化：%s" % _v(v.get("卷末變化")),
                  "- 卷末大高潮：%s" % _v(v.get("卷末大高潮")), "- 本卷埋下、留給後面的東西：" + _t("rev_see_fs")]
        units = []
        for ar in arcs:
            for u in ar.get("單元") or []:
                m = re.findall(r"\d+", str(u.get("起訖") or ""))
                if m and a <= int(m[0]) <= b:
                    units.append(u)
        ut = "\n\n".join("### 單元%s：%s（%s）\n- 起點局面：%s\n- 衝突：%s\n- 小高潮：%s\n- 結果與代價：%s" % (
            j + 1, _v(u.get("名稱")), _clean(u.get("起訖")), _v(u.get("起點局面")), _v(u.get("衝突")), _v(u.get("小高潮")),
            _v(u.get("結果與代價"))) for j, u in enumerate(units)) or unknown()
        arcs_in = [x for x in arcs if x["起"] <= b and x["訖"] >= a]
        vt = ("---\n類型: 卷綱\n卷名: %s\n章節範圍: 第%03d章～第%03d章\n狀態: 草稿\n來源: 從正文反推\n---\n\n# 卷綱：%s\n\n## 卷契約\n- 本卷賣點：%s\n"
              "- 主角本卷目標：%s\n- 本卷對手：%s\n- 卷末兌現：%s\n- 卷末新鉤子：%s\n\n## 本卷摘要\n%s\n\n## 劇情單元\n\n%s\n\n## 人物弧線\n%s\n") % (
            nm, a, b, nm, unknown(), _v(v.get("本卷目標")), _v(v.get("主要對手")), _v(v.get("卷末大高潮")), _v(v.get("卷末新鉤子")),
            "\n\n".join(x.get("段落摘要", "") for x in arcs_in) or unknown(), ut,
            "\n".join("- " + _v(x) for x in (v.get("人物弧線") or [])) or "- " + unknown())
        files.append(("大綱/卷綱_%s.md" % vn, vt))
    if _flag(book):
        lines += ["", "## 備註" + _flag(book)]
    return "\n".join(lines) + "\n", files


def _vol_of(vols, no):
    for i, v in enumerate(vols):
        if int(v.get("起") or 0) <= no <= int(v.get("訖") or 0):
            return _vol_name(i)
    return ""


def render_card(no, card, vols, chars_by_no):
    title = card.get("title") or ""
    todo = _t("rev_todo")
    pts = "\n".join("%d. %s" % (i + 1, p) for i, p in enumerate(card.get("情節點") or [])) or "1. " + todo
    fs = "\n".join("- " + x for x in card.get("伏筆操作") or []) or "- " + _t("rev_none")
    who = "\n".join("- " + x for x in card.get("出場") or chars_by_no) or "- " + todo
    return ("---\n類型: 章綱\n章號: %d\n章名: %s\n所屬卷: %s\n所屬單元:\n字數目標:\n狀態: 已寫\n來源: 從正文反推\n---\n\n# 第%d章 %s\n\n## 本章四問\n"
            "1. 主角這章想做什麼：%s\n2. 誰或什麼阻止他：%s\n3. 這章結束後局面變成什麼：%s\n4. 讀者為什麼還要往下看：%s\n\n## 本章功能與目標情緒\n"
            "- 功能：%s\n- 讀者看完的主要感受：%s\n\n## 情節點\n%s\n\n## 出場角色\n%s\n\n## 伏筆操作\n%s\n\n## 禁止事項\n%s\n\n"
            "## 章末鉤子\n- 停在：%s\n\n## 備註\n%s\n") % (
        no, title, _vol_of(vols, no), no, title, card.get("主角想做什麼") or todo, card.get("阻礙") or todo,
        card.get("局面變成") or todo, card.get("讀者為什麼往下看") or todo, card.get("功能") or todo,
        card.get("情緒") or todo, pts, who, fs, _t("rev_card_forbid"), card.get("章末鉤子") or todo,
        _t("rev_note_card") + ("\n- " + _t("lang_flag_note") if card.get("lang_flag") else ""))


def render_summary(no, title, chars, s):
    return ("---\n類型: 章節摘要\n章號: %d\n章名: %s\n字數: %d\n---\n\n# 第%d章 %s\n" % (no, title, chars, no, title) +
            "".join("\n## %s\n%s\n" % (k, s.get(k) or prompts.cur()["info_none"]) for k in ("發生了什麼", "局面變化", "新出現的人事物", "結尾停在")))


def render_tables(acc, last_label, core):
    fs = "---\n類型: 伏筆\n更新至: %s\n---\n\n# 伏筆總表\n\n" % last_label + tracking._render_table(tracking.FS_HEADERS, acc.get("fs") or []) + "\n"
    tl = ("---\n類型: 時間線\n更新至: %s\n---\n\n# 時間線\n\n%s\n\n" % (last_label, _t("rev_tl_note")) +
          tracking._render_table(tracking.TL_HEADERS, acc.get("events") or []) + "\n")
    rows = []
    terms = acc.get("terms") or {}
    for k, v in sorted(terms.items(), key=lambda kv: (min(kv[1]["chapters"]), kv[0])):
        rows.append({"名詞": k, "類別": v["類別"], "說明": v["說明"], "注意": "首次出現：第%03d章" % min(v["chapters"])})
    for k, c in sorted((acc.get("chars") or {}).items(), key=lambda kv: min(kv[1]["chapters"])):
        if k in core:
            continue
        note = c["notes"][0][1] if c["notes"] else ""
        rows.append({"名詞": "／".join([k] + c["aliases"]), "類別": "人物", "說明": note[:80],
                     "注意": "首次出現：第%03d章；出場 %d 章" % (min(c["chapters"]), len(c["chapters"]))})
    return fs, tl, rows


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run(book_dir, call, log, upto=None, should_stop=lambda: False, budget=32768, out_reserve=8192, title=""):
    """call(label, user_text) → 解析後的 dict（失敗丟例外）；log(text) 寫任務紀錄。"""
    chs = chapters(book_dir)
    if not chs:
        raise project.ProjectError("這本書的正文是空的，請先匯入舊稿")
    upto = min(upto or chs[-1]["no"], chs[-1]["no"])
    titles = {c["no"]: c["title"] for c in chs}
    st = _load(_p(book_dir, "state.json"), {})
    acc = _load(_p(book_dir, "累積.json"), {})
    done = {int(k) for k in (acc.get("summaries") or {})}
    batches = plan_batches(book_dir, upto, budget, out_reserve, start=(max(done) + 1) if done else 1)
    if batches:
        st["synth"] = {}   # 有新章節，整理要重做
    log("逐章抽取：第1～%d章，還有 %d 批要跑（已完成 %d 章）" % (upto, len(batches), len(done)))
    for i, nos in enumerate(batches, 1):
        if should_stop():
            return None
        data = call("逐章抽取 %d／%d：第%d～%d章" % (i, len(batches), nos[0], nos[-1]), extract_prompt(book_dir, nos, acc))
        apply_batch(acc, data, nos, titles)
        _save(_p(book_dir, "批次", "第%03d-%03d章.json" % (nos[0], nos[-1])), data)
        _save(_p(book_dir, "累積.json"), acc)
    last = max(int(k) for k in acc["summaries"])
    label = tracking.chapter_label(last)
    st.update({"upto": last, "updated": time.time()})
    syn = st.setdefault("synth", {})

    def step(key, label_, prompt):
        if key not in syn:
            if should_stop():
                raise StopIteration
            syn[key] = call(label_, prompt)
            _save(_p(book_dir, "state.json"), st)
        return syn[key]

    try:
        chars_out = []
        for j, (lb, pr) in enumerate(char_prompts(acc)):
            chars_out += (step("chars_%d" % j, lb, pr) or {}).get("角色") or []
        wp, _fac = world_prompt(acc)
        world = step("world", "整理背景設定", wp)
        arcs = []
        for j, (lb, a, b, pr) in enumerate(arc_prompts(acc)):
            d = step("arc_%d" % j, lb, pr) or {}
            arcs.append(dict(d, 起=a, 訖=b))
        book = step("book", "整理故事核心、全書大綱與卷綱", book_prompt(acc, arcs, title))
        sc = step("state", "整理狀態卡", state_prompt(acc, last))
    except StopIteration:
        return None

    # 產生草稿
    d = _p(book_dir, "草稿")
    if os.path.isdir(d):
        shutil.rmtree(d)
    core = []
    for ch in chars_out:
        if not isinstance(ch, dict) or not _clean(ch.get("名稱")):
            continue
        name, text, stext = render_character(ch, acc, label)
        core.append(name)
        _write_draft(book_dir, "設定/角色/%s.md" % _fname(name), text)
        _write_draft(book_dir, "追蹤/角色狀態/%s.md" % _fname(name), stext)
    for w in (world or {}).get("世界觀") or []:
        if isinstance(w, dict):
            n, t = render_world(w)
            _write_draft(book_dir, "設定/世界觀/%s.md" % _fname(n), t)
    _write_draft(book_dir, "設定/故事核心.md", render_core((book or {}).get("故事核心") or {}, title))
    vols = [v for v in (book or {}).get("卷") or [] if isinstance(v, dict)]
    if not vols:
        vols = [{"卷名": "第一卷", "起": 1, "訖": last}]
    outline, vfiles = render_outline(book or {}, vols, arcs)
    _write_draft(book_dir, "大綱/全書大綱.md", outline)
    for rel, t in vfiles:
        _write_draft(book_dir, rel, t)
    chinfo = {c["no"]: c for c in chs}
    for k, card in (acc.get("cards") or {}).items():
        no = int(k)
        _write_draft(book_dir, "大綱/章綱/第%03d章_%s.md" % (no, _fname(card.get("title"))), render_card(no, card, vols, []))
        _write_draft(book_dir, "追蹤/章節摘要/%s.md" % tracking.chapter_label(no),
                     render_summary(no, card.get("title", ""), chinfo.get(no, {}).get("chars", 0), acc["summaries"][k]))
    fs, tl, rows = render_tables(acc, label, set(core))
    _write_draft(book_dir, "追蹤/伏筆.md", fs)
    _write_draft(book_dir, "追蹤/時間線.md", tl)
    # 名詞：細分類、主題檔、重要條目獨立、勢力合併，名詞表留作索引
    from . import glossary_org
    try:
        org = glossary_org.organize(book_dir, rows, call, lambda rel, t: _write_draft(book_dir, rel, t), log=log, step=step)
    except StopIteration:
        return None
    tracking.write_reader_table(_p(book_dir, "草稿", "追蹤", "讀者認知.md"), acc.get("reader") or [], label, keep_ids=True)
    stc = "---\n類型: 狀態卡\n更新至: %s\n---\n\n# 狀態卡\n" % label
    for i, k in enumerate(tracking.STATE_SECTIONS, 1):
        items = (sc or {}).get(k) or []
        items = items if isinstance(items, list) else [items]
        stc += "\n## %d. %s\n%s\n" % (i, k, "\n".join("- " + _clean(x) for x in items if _clean(x)) or "- " + unknown())
    _write_draft(book_dir, "追蹤/狀態卡.md", stc)
    st["done"] = time.time()
    _save(_p(book_dir, "state.json"), st)
    g = draft_groups(book_dir)
    return ("**從正文建立設定完成**（第1～%d章）\n\n草稿：設定 %d 份、大綱 %d 份、章綱 %d 份、追蹤 %d 份。\n"
            "人物 %d 位（建角色檔 %d 位，其餘列進名詞表）、名詞 %d 個、伏筆 %d 條、時間線 %d 條、讀者認知 %d 條。\n%s\n\n"
            "請到這一頁（設定集右上角「從正文建立設定」）逐組核對後按「採用」。推不出來的欄位標成「（正文未明確）」或「待補」。" % (
                last, len(g["設定"]), len(g["大綱"]), len(g["章綱"]), len(g["追蹤"]), len(acc.get("chars") or {}), len(core),
                len(acc.get("terms") or {}), len(acc.get("fs") or []), len(acc.get("events") or []), len(acc.get("reader") or []), org))


# ---------------------------------------------------------------------------
# 草稿採用
# ---------------------------------------------------------------------------
def _group_of(rel):
    if rel.startswith("大綱/章綱/"):
        return "章綱"
    return rel.split("/", 1)[0] if rel.split("/", 1)[0] in GROUPS else None


def draft_groups(book_dir):
    root = _p(book_dir, "草稿")
    out = {g: [] for g in GROUPS}
    if not os.path.isdir(root):
        return out
    for dp, _, fns in os.walk(root):
        for f in sorted(fns):
            if f.endswith(".md"):
                rel = os.path.relpath(os.path.join(dp, f), root).replace("\\", "/")
                g = _group_of(rel)
                if g:
                    out[g].append({"rel": rel, "draft": (DIR + "/草稿/" + rel).replace("\\", "/"),
                                   "exists": os.path.isfile(os.path.join(book_dir, *rel.split("/")))})
    for g in out:
        out[g].sort(key=lambda x: x["rel"])
    return out


def adopt(book_dir, group):
    if group not in GROUPS:
        raise project.ProjectError("不認得的分組：%s" % group)
    items = draft_groups(book_dir)[group]
    if not items:
        raise project.ProjectError("「%s」沒有草稿" % group)
    n_bak = 0
    for it in items:
        dst = os.path.join(book_dir, *it["rel"].split("/"))
        if os.path.isfile(dst):
            tracking.backup(book_dir, dst, "反推前")
            n_bak += 1
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(_p(book_dir, "草稿", *it["rel"].split("/")), dst)
    tracking.git_commit(book_dir, "從正文建立設定：採用%s" % group)
    return {"adopted": len(items), "backed_up": n_bak}


def discard(book_dir, group):
    if group not in GROUPS:
        raise project.ProjectError("不認得的分組：%s" % group)
    for it in draft_groups(book_dir)[group]:
        os.remove(_p(book_dir, "草稿", *it["rel"].split("/")))
    return {"ok": True}
