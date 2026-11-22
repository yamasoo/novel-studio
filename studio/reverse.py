"""從成稿反推設定（匯入完成的書用，不需要開書訪談）。

流程（做法參考 oh-story-claudecode 的 story-import／story-long-analyze，MIT；內容與格式依本工作台重寫）：
1. 逐章抽取：依執行者的上下文長度分批（每批 1～3 章），照章節順序。每批帶著「跨批狀態」
   （已知人物與別名、還沒收的伏筆與懸念、上一章結尾）往下跑；每批結果存檔，中斷了從斷的地方接。
2. 本機累積：人物、別名、名詞、事件、伏筆、讀者認知在本機合併編號，不重讀正文。
3. 整理：請 AI 根據累積資料寫角色檔、勢力、世界觀、故事核心、全書大綱與卷綱、狀態卡、主要角色的目前狀態。
4. 本機產生：名詞表、反向章綱、章節摘要、伏筆表、時間線、讀者認知帳本。

全部先存成草稿（.studio/reverse/drafts/），分「設定／大綱／章綱／追蹤」四組讓作者採用或捨棄。
推不出來的欄位寫「（正文未明確）」或「待補」，不編造。
"""
import difflib
import json
import os
import re
import shutil
import time

from . import context, enums, project, prompts, tracking
from . import fmkeys, layout
from . import tables
from . import jsonkeys
from . import ids

DIR = os.path.join(*layout.parts(layout.STUDIO_REVERSE))
GROUPS = ids.REVERSE_GROUPS
# 訊息裡顯示的分組名稱（介面文字；API 一律用 ids.REVERSE_GROUPS）
GROUP_LABEL = {"bible": "設定", "outline": "大綱", "cards": "章綱", "tracking": "追蹤"}  # literal-ok: 顯示標籤
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


# 累積資料（.studio/reverse/cumulative.json）的鍵：v3 起是英文鍵。舊版（中文鍵）的快取讀進來先換算，反推跑到一半升級的書可以續跑。
CARD_KEYS = (("protagonist_goal", "主角想做什麼"), ("obstacle", "阻礙"), ("new_situation", "局面變成"), ("why_read_on", "讀者為什麼往下看"),
             ("function", "功能"), ("emotion", "情緒"), ("ending_hook", "章末鉤子"))
_V2_CARD = dict([(zh, en) for en, zh in CARD_KEYS] + [("情節點", "plot_points"), ("出場", "on_stage"), ("伏筆操作", "foreshadow_ops")])
_V2_SUMMARY = {zh: en for en, zh in tracking.SUMMARY_KEYS}
_V2_TERM = {"類別": "kind", "小類": "subtype", "說明": "explanation"}


def _ren(d, m):
    return {m.get(k, k): v for k, v in d.items()} if isinstance(d, dict) else d


def upgrade_acc(acc):
    """舊版累積資料（中文鍵）→ 英文鍵；已經是英文鍵的原樣。"""
    for key, m in (("summaries", _V2_SUMMARY), ("cards", _V2_CARD), ("terms", _V2_TERM)):
        if key in acc:
            acc[key] = {k: _ren(v, m) for k, v in (acc[key] or {}).items()}
    if "events" in acc:
        acc["events"] = [tables.row_to_keys("timeline", x) for x in acc["events"] or []]
    if "fs" in acc:
        acc["fs"] = [_ren(tables.row_to_keys("foreshadow", x), {"回收章": "resolved_in"}) for x in acc["fs"] or []]
    if "reader" in acc:
        acc["reader"] = [tables.row_to_keys("reader", x) for x in acc["reader"] or []]
    return acc


def load_acc(book_dir):
    return upgrade_acc(_load(_p(book_dir, layout.REVERSE_CUMULATIVE), {}))


def chapters(book_dir):
    out = []
    for no, f in sorted(project._scan_dir(layout.path(book_dir, layout.MANUSCRIPT)).items()):
        text = project.read_text(layout.path(book_dir, layout.MANUSCRIPT, f))
        out.append({"no": no, "title": project.chapter_title(f, text), "file": layout.MANUSCRIPT + "/" + f,
                    "chars": project.count_chars(context.body(text))})
    return out


def state(book_dir):
    st = _load(_p(book_dir, "state.json"), {})
    acc = _load(_p(book_dir, layout.REVERSE_CUMULATIVE), {})
    st["processed"] = sorted(int(k) for k in (acc.get("summaries") or {}))
    drafts = draft_groups(book_dir)
    for g, items in drafts.items():
        plan = {x["rel"]: x for x in plan_group(book_dir, g)}
        for it in items:
            it.update(plan.get(it["rel"]) or {})
    st["drafts"] = drafts
    return st


def reset(book_dir):
    d = _p(book_dir)
    if os.path.isdir(d):
        bak = layout.path(book_dir, layout.STUDIO_BACKUP, "反推_%d" % int(time.time()))
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
    fs = [x for x in (acc.get("fs") or []) if x["status"] != "已回收"][-50:]
    if fs:
        lines.append(P["rev_h_open_fs"] + "\n" + "\n".join(_t("rev_fs_line", id=x["id"], ch=x["planted_in"], text=x["content"]) for x in fs))
    rp = [x for x in (acc.get("reader") or []) if x["type"] != "已知" and not x.get("resolved_in")][-50:]
    if rp:
        lines.append(P["rev_h_open_rp"] + "\n" + "\n".join("- %s〔%s〕%s" % (x["id"], enums.show("type", x["type"], prompts.cur_lang()), x["content"])
                                                          for x in rp))
    prev = (acc.get("summaries") or {}).get(str(first_no - 1))
    if prev:
        lines.append(_t("rev_h_prev_end", n=first_no - 1) + "\n" + prev.get("ends_on", ""))
    return "\n\n".join(lines)


def extract_prompt(book_dir, nos, acc):
    parts = []
    for no in nos:
        path, text = context.chapter_text(book_dir, no, (layout.MANUSCRIPT,))
        parts.append(_t("rev_ch_head", n=no, title=project.chapter_title(path or "", text)) + "\n" +
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
    """把一批的抽取結果（英文鍵，jsonkeys.to_keys 換過）併進累積資料（本機，不呼叫 AI）。"""
    got = {}
    for ch in (data or {}).get("chapters") or []:
        try:
            got[int(ch.get("no"))] = ch
        except (TypeError, ValueError):
            continue
    if len(got) < len(nos) and len((data or {}).get("chapters") or []) == len(nos):
        got = {n: ch for n, ch in zip(nos, data["chapters"])}   # 章號寫錯但數量對：照順序對應
    for no in nos:
        ch = got.get(no) or {}
        acc.setdefault("summaries", {})[str(no)] = {k: _clean((ch.get("chapter_summary") or {}).get(k)) for k, _ in tracking.SUMMARY_KEYS}
        card = ch.get("chapter_card") or {}
        acc.setdefault("cards", {})[str(no)] = {
            "title": titles.get(no, ""),
            **{k: _clean(card.get(k)) for k, _ in CARD_KEYS},
            "plot_points": [_clean(x) for x in (card.get("plot_points") or []) if _clean(x)],
            "on_stage": [], "foreshadow_ops": []}
        if ch.get("_lang_mismatch"):
            acc["cards"][str(no)]["lang_flag"] = True
        cd = acc["cards"][str(no)]
        # 人物
        chars = acc.setdefault("chars", {})
        idx = acc.setdefault("alias_index", {})
        for p in ch.get("people") or []:
            if not isinstance(p, dict):
                continue
            name = _clean(p.get("name"))
            if len(name) < 2:
                continue
            al = [_clean(a) for a in (p.get("aliases") or []) if len(_clean(a)) >= 2 and _clean(a) != name]
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
            note = "；".join(x for x in (_clean(p.get("identity")), _clean(p.get("this_chapter"))) if x)
            if note:
                c["notes"].append([no, note])
            imp = _clean(p.get("importance")) or "次要"
            c["votes"][imp] = c["votes"].get(imp, 0) + 1
            if canon not in cd["on_stage"]:
                cd["on_stage"].append(canon)
        # 名詞
        terms = acc.setdefault("terms", {})
        for t in ch.get("terms") or []:
            if not isinstance(t, dict):
                continue
            n = _clean(t.get("term"))
            if len(n) < 2 or n in idx:
                continue
            e = terms.setdefault(n, {"kind": _clean(t.get("kind")) or "其他", "subtype": _clean(t.get("subtype")), "explanation": "", "chapters": []})
            d = _clean(t.get("explanation"))
            if d and len(d) > len(e["explanation"]):
                e["explanation"] = d[:120]
            if no not in e["chapters"]:
                e["chapters"].append(no)
        # 事件
        evs = acc.setdefault("events", [])
        for ev in ch.get("plot_events") or []:
            if isinstance(ev, dict) and _clean(ev.get("actual_event")):
                evs.append({"id": "E%03d" % (len(evs) + 1), "story_time": _clean(ev.get("story_time")),
                            "what_really_happened": _clean(ev.get("actual_event")), "reader_knows_now": _clean(ev.get("reader_knows")),
                            "revealed_in": tracking.chapter_label(no), "related_characters": _clean(ev.get("related_characters"))})
        # 伏筆
        fs = acc.setdefault("fs", [])
        by = {x["id"]: x for x in fs}
        for f in ch.get("foreshadowing") or []:
            if not isinstance(f, dict):
                continue
            fid, act = _clean(f.get("id")), _clean(f.get("action"))
            if fid in by:
                x = by[fid]
                x["last_seen"] = tracking.chapter_label(no)
                if act == "回收":
                    x["status"], x["resolved_in"] = "已回收", tracking.chapter_label(no)
                elif x["status"] != "已回收":
                    x["status"] = "推進中"
                cd["foreshadow_ops"].append(_t("rev_fs_op_pay" if act == "回收" else "rev_fs_op_adv", id=fid, text=x["content"][:20]))
            elif _clean(f.get("content")) and act != "回收":
                x = {"id": "F%03d" % (len(fs) + 1), "content": _clean(f.get("content")), "planted_in": tracking.chapter_label(no),
                     "planned_payoff": "", "last_seen": tracking.chapter_label(no), "status": "已埋",
                     "priority": _clean(f.get("priority")) if _clean(f.get("priority")) in ("高", "中", "低") else "中"}
                fs.append(x)
                by[x["id"]] = x
                cd["foreshadow_ops"].append(_t("rev_fs_op_new", id=x["id"], text=x["content"][:20]))
        # 讀者認知
        rp = acc.setdefault("reader", [])
        rby = {x["id"]: x for x in rp}
        for r in ch.get("reader_knowledge") or []:
            if not isinstance(r, dict):
                continue
            rid = _clean(r.get("id"))
            if rid in rby:
                if _clean(r.get("action")) == "回收" or _clean(r.get("author_truth")):
                    rby[rid]["resolved_in"] = tracking.chapter_label(no)
                    if _clean(r.get("author_truth")):
                        rby[rid]["author_truth"] = _clean(r.get("author_truth"))
            elif _clean(r.get("content")) and _clean(r.get("action")) != "回收":
                x = {"id": "R%03d" % (len(rp) + 1), "type": _clean(r.get("type")) if _clean(r.get("type")) in tracking.RP_TYPES else "懸念",
                     "content": _clean(r.get("content")), "author_truth": _clean(r.get("author_truth")),
                     "planted_chapter": tracking.chapter_label(no), "resolved_in": "", "related_characters": ""}
                rp.append(x)
                rby[x["id"]] = x
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
    lines = [_t("rev_h_top_terms")] + ["- %s〔%s〕%s" % (k, enums.show("term_cat", v["kind"], prompts.cur_lang()), v["explanation"]) for k, v in other]
    sums = acc.get("summaries") or {}
    keys = sorted(sums, key=int)
    pick = keys[::max(1, len(keys) // 12)][:12]
    lines += ["", _t("rev_h_some_sums")] + [_t("rev_note_line", n=k, text=sums[k]["what_happened"]) for k in pick]
    return "\n".join(lines) + "\n\n" + world_schema(), []




def arc_prompts(acc):
    sums = acc.get("summaries") or {}
    keys = sorted((int(k) for k in sums))
    out = []
    for i in range(0, len(keys), ARC_CHAPTERS):
        part = keys[i:i + ARC_CHAPTERS]
        body = "\n".join(_t("rev_arc_line", n=k, title=(acc["cards"].get(str(k)) or {}).get("title", ""),
                             what=sums[str(k)]["what_happened"], change=sums[str(k)]["situation_change"]) for k in part)
        out.append(("整理第%d～%d章的劇情段落" % (part[0], part[-1]), part[0], part[-1],
                    _t("rev_arc_intro", a=part[0], b=part[-1]) + "\n\n%s\n\n%s" % (body, arc_schema())))
    return out




def book_prompt(acc, arcs, title):
    lines = [_t("rev_book_title", title=title), "", _t("rev_h_arcs")]
    for a in arcs:
        lines.append(_t("rev_arc_seg_line", a=a["start"], b=a["end"], text=a.get("segment_summary", "")))
        for u in a.get("units") or []:
            lines.append(_t("rev_unit_line", name=u.get("name", ""), range=u.get("chapter_range", ""), conflict=u.get("conflict", ""),
                            result=u.get("outcome_cost", "")))
    core = core_characters(acc)[:8]
    lines += ["", _t("rev_h_main_chars") + _t("list_sep").join(core)]
    return "\n".join(lines) + "\n\n" + book_schema()




def state_prompt(acc, last_no):
    sums = acc.get("summaries") or {}
    keys = sorted(int(k) for k in sums)[-5:]
    lines = [_t("rev_h_recent")] + [_t("rev_state_line", n=k, what=sums[str(k)]["what_happened"], change=sums[str(k)]["situation_change"],
                                     end=sums[str(k)]["ends_on"]) for k in keys]
    fs = [x for x in acc.get("fs") or [] if x["status"] != "已回收"][-20:]
    lines += ["", _t("rev_h_open_fs")] + ["- %s %s" % (x["id"], x["content"]) for x in fs]
    rp = [x for x in acc.get("reader") or [] if x["type"] != "已知" and not x.get("resolved_in")][-15:]
    lines += ["", _t("rev_h_waiting")] + ["- %s %s" % (x["id"], x["content"]) for x in rp]
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
    path = _p(book_dir, layout.REVERSE_DRAFTS, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.rstrip("\n") + "\n")


def _fname(s):
    return project.safe_filename(s, 40)


def render_character(ch, acc, last_label):
    name = _clean(ch.get("name"))
    info = (acc.get("chars") or {}).get(name) or {}
    al = list(dict.fromkeys([a for a in (ch.get("aliases") or []) if a] + info.get("aliases", [])))
    first = min(info.get("chapters") or [0]) or ""
    rels = ch.get("relationships") if "relationships" in ch else ch.get("relationship")   # 清單（正常）或單一字串
    rel = "".join("\n- %s" % r for r in (rels or [])) or "\n- " + unknown()
    text = ("---\ntype: character\nname: %s\naliases: [%s]\nrole: %s\nfirst_appearance: %s\nstatus: draft\nsource: 從正文反推\n---\n\n# %s\n\n"
            "## 一句話\n%s\n\n## 外在\n- 年齡／身分：%s\n- 外貌辨識點：%s\n\n## 內在\n- 想要：%s\n- 害怕：%s\n- 缺陷：%s\n- 底線：%s\n- 秘密：%s\n\n"
            "## 說話方式（聲音卡）\n- %s\n\n## 關係%s\n\n## 角色弧線\n%s\n\n## 備註\n%s\n") % (
        name, ", ".join(al), fmkeys.write_value("role", _clean(ch.get("role")) or "配角"), first, name, _v(ch.get("one_line")), _v(ch.get("age_identity")),
        _v(ch.get("looks")), _v(ch.get("wants")), _v(ch.get("fears")), _v(ch.get("flaw")), _v(ch.get("bottom_line")), _v(ch.get("secret")),
        _v(ch.get("voice")), rel, _v(ch.get("arc")),
        _t("rev_note_char", count=len(info.get("chapters") or []), a=first, b=max(info.get("chapters") or [0]) or "") + _flag(ch))
    st = ch.get("current_state") or {}
    last = max(info.get("chapters") or [0]) or 0
    stext = "---\ntype: character-state\nname: %s\nupdated_through: %s\nlast_appearance: %s\n---\n\n# %s：目前狀態\n\n%s\n\n" % (
        name, fmkeys.ch_value(last_label), fmkeys.ch_value(last) if last else "", name, _t("rev_state_note"))
    stext += "\n".join("- %s：%s" % (label, _v(st.get(k))) for k, label in tracking.CHAR_KEYS)
    return name, text, stext


def render_faction(f):
    name = _clean(f.get("name"))
    return name, ("---\ntype: faction\nname: %s\nstatus: draft\nrelated_characters: [%s]\nsource: 從正文反推\n---\n\n# %s\n\n## 一句話\n%s\n\n## 基本資料\n"
                  "- 規模與地盤：%s\n- 首領：%s\n- 主要成員：%s\n- 資源與手段：%s\n\n## 目標與利益\n- 想要什麼：%s\n- 和誰有衝突：%s\n- 和誰有合作：%s\n\n"
                  "## 內部規矩\n%s\n\n## 對主角的態度\n%s\n\n## 備註\n%s\n") % (
        name, ", ".join(f.get("related_characters") or []), name, _v(f.get("one_line")), _v(f.get("scale_territory")), _v(f.get("leader")),
        _v(f.get("key_members")), _v(f.get("resources_means")), _v(f.get("faction_wants")), _v(f.get("conflicts_with")),
        _v(f.get("cooperates_with")), _v(f.get("internal_rules")), _v(f.get("attitude_to_protagonist")), _t("rev_note_review") + _flag(f))


def render_world(w):
    name = _clean(w.get("name")) or _t("rev_bg_name")
    cat = _clean(w.get("world_category"))
    cat = fmkeys.write_value("category", cat if cat in WORLD_CATS else "其他")
    tags = [_clean(t) for t in (w.get("labels") or []) if _clean(t)] if isinstance(w.get("labels"), list) else []
    rules = "\n".join("- " + _clean(r) for r in (w.get("rules") or []) if _clean(r)) or "- " + unknown()
    cost = "\n".join("- " + _clean(r) for r in (w.get("costs_limits") or []) if _clean(r)) or "- " + unknown()
    return name, ("---\ntype: world\ncategory: %s\ntags: [%s]\nname: %s\nstatus: draft\nsource: 從正文反推\n---\n\n# %s\n\n## 一句話\n%s\n\n## 規則\n%s\n\n## 代價與限制\n%s\n\n"
                  "## 讀者何時知道\n%s\n\n## 與劇情的關係\n%s\n\n## 備註\n%s\n") % (
        cat, ", ".join(tags), name, name, _v(w.get("one_line")), rules, cost, _t("rev_world_when"), _v(w.get("plot_relevance")),
        _t("rev_note_review") + _flag(w))


def render_core(c, title):
    def lst(x):
        items = [i for i in (x or []) if str(i).strip()] if isinstance(x, list) else [x]
        return "\n".join("%d. %s" % (i + 1, _v(v)) for i, v in enumerate(items)) or "1. " + unknown()
    return ("---\ntype: story-core\ntitle: %s\nstatus: draft\nsource: 從正文反推\n---\n\n# 故事核心\n\n## 一句話鉤子\n%s\n\n## 題材與定位\n- 題材：%s\n- 目標讀者：%s\n"
            "- 發表平台與更新節奏：%s\n- 預計篇幅：%s\n- 敘事視角：%s\n\n## 賣點（讀者為什麼看）\n%s\n\n## 主角\n- 想要什麼（外在目標）：%s\n"
            "- 真正需要什麼（內在成長）：%s\n- 最大的缺陷或限制：%s\n- 金手指／特殊優勢（有的話）：%s\n\n## 故事引擎\n%s\n\n## 核心衝突\n- 主要對手：%s\n- 衝突根源：%s\n\n"
            "## 讀者契約\n%s\n\n## 終局方向\n%s\n\n## 升級台階\n%s\n") % (
        _clean(c.get("title")) or title, _v(c.get("hook")), _v(c.get("genre")), _v(c.get("target_readers")), _t("rev_fill"), _t("rev_fill"),
        _v(c.get("pov")),
        lst(c.get("selling_points")), _v(c.get("protagonist_wants")), _v(c.get("protagonist_needs")), _v(c.get("protagonist_flaw")),
        _v(c.get("special_edge")), _v(c.get("story_engine")), _v(c.get("main_opponent")), _v(c.get("conflict_root")),
        "\n".join("- " + _v(x) for x in (c.get("reader_contract") or [])) or "- " + unknown(), _v(c.get("endgame")),
        lst(c.get("escalation_steps"))) + (
        "\n## 備註%s\n" % _flag(c) if _flag(c) else "")


CN_VOL = "一二三四五六七八九十"


def _vol_name(i):
    return "第%s卷" % (CN_VOL[i] if i < 10 else str(i + 1))


def render_outline(book, vols, arcs):
    lines = ["---\ntype: book-outline\nstatus: draft\nsource: 從正文反推\n---\n\n# 全書大綱\n\n## 總覽",
             "- 預計卷數與字數：" + _t("rev_vols_written", n=len(vols)),
             "- 主線一句話：%s" % _v((book.get("whole_book") or {}).get("main_line")),
             "- 終局：%s" % _v((book.get("whole_book") or {}).get("ending")), "", "## 分卷"]
    files = []
    for i, v in enumerate(vols):
        vn = _vol_name(i)
        nm = _clean(v.get("volume_name")) or vn
        a, b = int(v.get("start") or 0), int(v.get("end") or 0)
        lines += ["", "### %s：%s" % (vn, nm), "- 篇幅：第%d～%d章" % (a, b), "- 本卷目標：%s" % _v(v.get("volume_goal")),
                  "- 主要對手：%s" % _v(v.get("main_opponent")), "- 卷末變化：%s" % _v(v.get("volume_end_change")),
                  "- 卷末大高潮：%s" % _v(v.get("volume_climax")), "- 本卷埋下、留給後面的東西：" + _t("rev_see_fs")]
        units = []
        for ar in arcs:
            for u in ar.get("units") or []:
                m = re.findall(r"\d+", str(u.get("chapter_range") or ""))
                if m and a <= int(m[0]) <= b:
                    units.append(u)
        ut = "\n\n".join("### 單元%s：%s（%s）\n- 起點局面：%s\n- 衝突：%s\n- 小高潮：%s\n- 結果與代價：%s" % (
            j + 1, _v(u.get("name")), _clean(u.get("chapter_range")), _v(u.get("starting_situation")), _v(u.get("conflict")),
            _v(u.get("mini_climax")), _v(u.get("outcome_cost"))) for j, u in enumerate(units)) or unknown()
        arcs_in = [x for x in arcs if x["start"] <= b and x["end"] >= a]
        vt = ("---\ntype: volume-outline\ntitle: %s\nchapter_range: %s\nstatus: draft\nsource: 從正文反推\n---\n\n# 卷綱：%s\n\n## 卷契約\n- 本卷賣點：%s\n"
              "- 主角本卷目標：%s\n- 本卷對手：%s\n- 卷末兌現：%s\n- 卷末新鉤子：%s\n\n## 本卷摘要\n%s\n\n## 劇情單元\n\n%s\n\n## 人物弧線\n%s\n") % (
            nm, fmkeys.range_value(a, b), nm, unknown(), _v(v.get("volume_goal")), _v(v.get("main_opponent")), _v(v.get("volume_climax")),
            _v(v.get("volume_new_hook")), "\n\n".join(x.get("segment_summary", "") for x in arcs_in) or unknown(), ut,
            "\n".join("- " + _v(x) for x in (v.get("character_arcs") or [])) or "- " + unknown())
        files.append((layout.volume_file(i + 1), vt))
    if _flag(book):
        lines += ["", "## 備註" + _flag(book)]
    return "\n".join(lines) + "\n", files


def _vol_of(vols, no):
    for i, v in enumerate(vols):
        if int(v.get("start") or 0) <= no <= int(v.get("end") or 0):
            return (i + 1) if fmkeys.WRITE_VALUES == "en" else _vol_name(i)      # v3：所屬卷存整數
    return ""


def render_card(no, card, vols, chars_by_no):
    title = card.get("title") or ""
    todo = _t("rev_todo")
    pts = "\n".join("%d. %s" % (i + 1, p) for i, p in enumerate(card.get("plot_points") or [])) or "1. " + todo
    fs = "\n".join("- " + x for x in card.get("foreshadow_ops") or []) or "- " + _t("rev_none")
    who = "\n".join("- " + x for x in card.get("on_stage") or chars_by_no) or "- " + todo
    return ("---\ntype: chapter-card\nchapter: %d\ntitle: %s\nvolume: %s\nunit:\ntarget_length:\nstatus: written\nsource: 從正文反推\n---\n\n# 第%d章 %s\n\n## 本章四問\n"
            "1. 主角這章想做什麼：%s\n2. 誰或什麼阻止他：%s\n3. 這章結束後局面變成什麼：%s\n4. 讀者為什麼還要往下看：%s\n\n## 本章功能與目標情緒\n"
            "- 功能：%s\n- 讀者看完的主要感受：%s\n\n## 情節點\n%s\n\n## 出場角色\n%s\n\n## 伏筆操作\n%s\n\n## 禁止事項\n%s\n\n"
            "## 章末鉤子\n- 停在：%s\n\n## 備註\n%s\n") % (
        no, title, _vol_of(vols, no), no, title, card.get("protagonist_goal") or todo, card.get("obstacle") or todo,
        card.get("new_situation") or todo, card.get("why_read_on") or todo, card.get("function") or todo,
        card.get("emotion") or todo, pts, who, fs, _t("rev_card_forbid"), card.get("ending_hook") or todo,
        _t("rev_note_card") + ("\n- " + _t("lang_flag_note") if card.get("lang_flag") else ""))


def render_summary(no, title, chars, s):
    return ("---\ntype: chapter-summary\nchapter: %d\ntitle: %s\nlength: %d\n---\n\n# 第%d章 %s\n" % (no, title, chars, no, title) +
            "".join("\n## %s\n%s\n" % (head, s.get(k) or prompts.cur()["info_none"]) for k, head in tracking.SUMMARY_KEYS))


def render_tables(acc, last_label, core):
    fs = ("---\ntype: foreshadowing\nupdated_through: %s\n---\n\n# 伏筆總表\n\n" % fmkeys.ch_value(last_label) +
          tracking._render_table(tracking.FS_HEADERS, tables.rows_to_headers("foreshadow", acc.get("fs") or [])) + "\n")
    tl = ("---\ntype: timeline\nupdated_through: %s\n---\n\n# 時間線\n\n%s\n\n" % (fmkeys.ch_value(last_label), _t("rev_tl_note")) +
          tracking._render_table(tracking.TL_HEADERS, tables.rows_to_headers("timeline", acc.get("events") or [])) + "\n")
    rows = []
    terms = acc.get("terms") or {}
    for k, v in sorted(terms.items(), key=lambda kv: (min(kv[1]["chapters"]), kv[0])):
        rows.append({"term": k, "kind": v["kind"], "explanation": v["explanation"], "note": "首次出現：第%03d章" % min(v["chapters"])})
    for k, c in sorted((acc.get("chars") or {}).items(), key=lambda kv: min(kv[1]["chapters"])):
        if k in core:
            continue
        note = c["notes"][0][1] if c["notes"] else ""
        rows.append({"term": "／".join([k] + c["aliases"]), "kind": "人物", "explanation": note[:80],
                     "note": "首次出現：第%03d章；出場 %d 章" % (min(c["chapters"]), len(c["chapters"]))})
    return fs, tl, rows


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run(book_dir, call, log, upto=None, should_stop=lambda: False, budget=32768, out_reserve=8192, title=""):
    """call(label, user_text) → 解析後的 dict（英文鍵；失敗丟例外）；log(text) 寫任務紀錄。"""
    chs = chapters(book_dir)
    if not chs:
        raise project.ProjectError("這本書的正文是空的，請先匯入舊稿")
    upto = min(upto or chs[-1]["no"], chs[-1]["no"])
    titles = {c["no"]: c["title"] for c in chs}
    st = _load(_p(book_dir, "state.json"), {})
    acc = load_acc(book_dir)
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
        _save(_p(book_dir, layout.REVERSE_BATCHES, layout.chapter_range_json(nos[0], nos[-1])), data)
        _save(_p(book_dir, layout.REVERSE_CUMULATIVE), acc)
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
        d = syn[key]   # 舊版的快取是中文鍵：一律換成英文鍵
        return jsonkeys.to_keys(d, values=False) if d else d

    try:
        chars_out = []
        for j, (lb, pr) in enumerate(char_prompts(acc)):
            chars_out += (step("chars_%d" % j, lb, pr) or {}).get("cast") or []
        wp, _fac = world_prompt(acc)
        world = step("world", "整理背景設定", wp)
        arcs = []
        for j, (lb, a, b, pr) in enumerate(arc_prompts(acc)):
            d = step("arc_%d" % j, lb, pr) or {}
            arcs.append(dict(d, start=a, end=b))
        book = step("book", "整理故事核心、全書大綱與卷綱", book_prompt(acc, arcs, title))
        sc = step("state", "整理狀態卡", state_prompt(acc, last))
    except StopIteration:
        return None

    # 產生草稿
    d = _p(book_dir, layout.REVERSE_DRAFTS)
    if os.path.isdir(d):
        shutil.rmtree(d)
    core = []
    for ch in chars_out:
        if not isinstance(ch, dict) or not _clean(ch.get("name")):
            continue
        name, text, stext = render_character(ch, acc, label)
        core.append(name)
        _write_draft(book_dir, layout.entry(layout.CHARACTERS, _fname(name)), text)
        _write_draft(book_dir, layout.entry(layout.CHARACTER_STATES, _fname(name)), stext)
    for w in (world or {}).get("world") or []:
        if isinstance(w, dict):
            n, t = render_world(w)
            _write_draft(book_dir, layout.entry(layout.WORLD, _fname(n)), t)
    _write_draft(book_dir, layout.STORY_CORE, render_core((book or {}).get("story_core") or {}, title))
    vols = [v for v in (book or {}).get("volumes") or [] if isinstance(v, dict)]
    if not vols:
        vols = [{"volume_name": "第一卷", "start": 1, "end": last}]
    outline, vfiles = render_outline(book or {}, vols, arcs)
    _write_draft(book_dir, layout.BOOK_OUTLINE, outline)
    for rel, t in vfiles:
        _write_draft(book_dir, rel, t)
    chinfo = {c["no"]: c for c in chs}
    for k, card in (acc.get("cards") or {}).items():
        no = int(k)
        _write_draft(book_dir, layout.CHAPTER_CARDS + "/" + layout.chapter_md(no), render_card(no, card, vols, []))
        _write_draft(book_dir, layout.SUMMARIES + "/" + layout.chapter_md(no),
                     render_summary(no, card.get("title", ""), chinfo.get(no, {}).get("chars", 0), acc["summaries"][k]))
    fs, tl, rows = render_tables(acc, label, set(core))
    _write_draft(book_dir, layout.FORESHADOWING, fs)
    _write_draft(book_dir, layout.TIMELINE, tl)
    # 名詞：細分類、主題檔、重要條目獨立、勢力合併，名詞表留作索引
    from . import glossary_org
    try:
        org = glossary_org.organize(book_dir, rows, call, lambda rel, t: _write_draft(book_dir, rel, t), log=log, step=step)
    except StopIteration:
        return None
    tracking.write_reader_table(_p(book_dir, layout.REVERSE_DRAFTS, *layout.parts(layout.READER_KNOWLEDGE)), acc.get("reader") or [], label, keep_ids=True)
    stc = "---\ntype: state-card\nupdated_through: %s\n---\n\n# 狀態卡\n" % fmkeys.ch_value(label)
    for i, (k, head) in enumerate(tracking.STATE_KEYS, 1):
        items = (sc or {}).get(k) or []
        items = items if isinstance(items, list) else [items]
        stc += "\n## %d. %s\n%s\n" % (i, head, "\n".join("- " + _clean(x) for x in items if _clean(x)) or "- " + unknown())
    _write_draft(book_dir, layout.STATE_CARD, stc)
    st["done"] = time.time()
    _save(_p(book_dir, "state.json"), st)
    g = draft_groups(book_dir)
    return ("**從正文建立設定完成**（第1～%d章）\n\n草稿：設定 %d 份、大綱 %d 份、章綱 %d 份、追蹤 %d 份。\n"
            "人物 %d 位（建角色檔 %d 位，其餘列進名詞表）、名詞 %d 個、伏筆 %d 條、時間線 %d 條、讀者認知 %d 條。\n%s\n\n"
            "請到這一頁（設定集右上角「從正文建立設定」）逐組核對後按「採用」。推不出來的欄位標成「（正文未明確）」或「待補」。" % (
                last, len(g["bible"]), len(g["outline"]), len(g["cards"]), len(g["tracking"]), len(acc.get("chars") or {}), len(core),
                len(acc.get("terms") or {}), len(acc.get("fs") or []), len(acc.get("events") or []), len(acc.get("reader") or []), org))


# ---------------------------------------------------------------------------
# 草稿採用
# ---------------------------------------------------------------------------
_FOLDER_GROUP = {folder: g for g, folder in ids.REVERSE_GROUP_FOLDER.items()}


def _group_of(rel):
    """草稿的相對路徑 → 分組 ID（章綱另成一組；其他看第一層資料夾）。"""
    if rel.startswith(layout.CHAPTER_CARDS + "/"):
        return "cards"
    return _FOLDER_GROUP.get(rel.split("/", 1)[0])


def _group(group):
    """API 傳進來的分組：新 ID、舊的中文 ID 都接受；認不得就報錯。"""
    g = ids.norm("reverse_group", group)
    if g not in GROUPS:
        raise project.ProjectError("不認得的分組：%s" % group)
    return g


def draft_groups(book_dir):
    root = _p(book_dir, layout.REVERSE_DRAFTS)
    out = {g: [] for g in GROUPS}
    if not os.path.isdir(root):
        return out
    for dp, _, fns in os.walk(root):
        for f in sorted(fns):
            if f.endswith(".md"):
                rel = os.path.relpath(os.path.join(dp, f), root).replace("\\", "/")
                g = _group_of(rel)
                if g:
                    out[g].append({"rel": rel, "draft": (DIR + "/" + layout.REVERSE_DRAFTS + "/" + rel).replace("\\", "/"),
                                   "exists": os.path.isfile(os.path.join(book_dir, *rel.split("/")))})
    for g in out:
        out[g].sort(key=lambda x: x["rel"])
    return out


DEFAULT_MODE = {"bible": "merge", "outline": "keep", "cards": "copy", "tracking": "keep"}
ALLOWED_MODES = {"bible": ("merge", "replace", "keep"), "outline": ("merge", "replace", "keep"),
                 "cards": ("copy",), "tracking": ("replace", "keep")}
# 表格類設定檔：沒有「## 段落」，merge_entry 併不進任何一列（整份反推內容會被丟掉），
# 所以當機器快照處理——預設／被要求 merge 時一律整份取代，一樣先備份；「保留現有」照舊可用。
SNAPSHOT_RELS = (layout.GLOSSARY,)


def _mode_for(group, rel, mode=None):
    """這一組／這一份草稿實際要用的模式（表格類只允許 replace／keep）。"""
    m = mode or DEFAULT_MODE[group]
    if _canon_rel(group, rel) in SNAPSHOT_RELS:
        m = "keep" if m == "keep" else "replace"
    if m not in ALLOWED_MODES[group]:
        raise project.ProjectError("「%s」不支援「%s」模式" % (GROUP_LABEL.get(group, group), m))
    return m
CHAPTER_DRAFT_DIR = layout.REVERSE_CARDS


def _canon_rel(group, rel):
    """草稿要落到哪個正式路徑：章綱一律落 outline/chapters/_reverse/；卷綱草稿本來就用正式檔名（vol-01.md）。"""
    if group == "cards":
        return "%s/%s" % (CHAPTER_DRAFT_DIR, os.path.basename(rel))
    return rel


def _existing_rel(book_dir, group, rel):
    """這份草稿和哪個正式檔比對。章綱看章號對應的正式章綱，其餘看落點本身。"""
    if group != "cards":
        return _canon_rel(group, rel)
    no = project.chapter_no(os.path.basename(rel))
    if no is None:
        return None
    f = project._scan_dir(layout.path(book_dir, layout.CHAPTER_CARDS)).get(no)
    return layout.CHAPTER_CARDS + "/" + f if f else None


def _read_rel(book_dir, rel):
    if not rel:
        return ""
    p = os.path.join(book_dir, *rel.split("/"))
    return project.read_text(p) if os.path.isfile(p) else ""


def chapter_cards(book_dir):
    """已採用的反推章綱（outline/chapters/_reverse/），給大綱頁的唯讀對照清單。"""
    root = os.path.join(book_dir, *CHAPTER_DRAFT_DIR.split("/"))
    out = []
    if os.path.isdir(root):
        for f in sorted(os.listdir(root)):
            if not f.endswith(".md"):
                continue
            no = project.chapter_no(f)
            fm = project.split_frontmatter(project.read_text(os.path.join(root, f)))[0]
            out.append({"rel": "%s/%s" % (CHAPTER_DRAFT_DIR, f), "no": no or 0,
                        "name": str(fm.get("title") or "") or project.chapter_title_from_filename(f) or os.path.splitext(f)[0]})
    out.sort(key=lambda x: (x["no"] or 10 ** 9, x["rel"]))
    return out


def plan_group(book_dir, group):
    """每份草稿的採用決策資料（給前端畫新舊對照；相似度只在後端算）。"""
    group = _group(group)
    out = []
    for it in draft_groups(book_dir)[group]:
        rel = it["rel"]
        new = project.read_text(_p(book_dir, layout.REVERSE_DRAFTS, *rel.split("/")))
        old_rel = _existing_rel(book_dir, group, rel)
        old = _read_rel(book_dir, old_rel)
        out.append({
            "rel": rel,
            "target": _canon_rel(group, rel),
            "exists": bool(old_rel and os.path.isfile(os.path.join(book_dir, *old_rel.split("/")))),
            "chars_new": len(new),
            "chars_old": len(old),
            "lines_new": len(new.splitlines()),
            "lines_old": len(old.splitlines()),
            "similarity": round(difflib.SequenceMatcher(None, old.splitlines(), new.splitlines()).ratio(), 3) if old else 0.0,
            "default_mode": _mode_for(group, rel),
        })
    return out


def diff_group(book_dir, group, rel):
    """一份草稿和它會動到的正式檔的逐段差異（給對照視窗）。"""
    group = _group(group)
    if not any(x["rel"] == rel for x in draft_groups(book_dir)[group]):
        raise project.ProjectError("「%s」沒有這份草稿：%s" % (GROUP_LABEL.get(group, group), rel))
    old_rel = _existing_rel(book_dir, group, rel)
    new = project.read_text(_p(book_dir, layout.REVERSE_DRAFTS, *rel.split("/")))
    old = _read_rel(book_dir, old_rel)
    from . import revision
    return {"group": group, "rel": rel, "target": _canon_rel(group, rel), "old_rel": old_rel or "",
            "chars_new": len(new), "chars_old": len(old),
            "blocks": revision.diff_blocks(old, new)}


def adopt(book_dir, group, mode=None, files=None):
    """採用這組草稿。

    mode：keep（保留現有，什麼都不動）／replace（先備份再整份取代）／merge（先備份再併入，
    只補空白與缺的段落）／copy（章綱專用：寫進 outline/chapters/_reverse/，正式章綱不動）。
    mode 省略時用各組預設（設定 merge、大綱／追蹤 keep、章綱 copy）。
    例外：名詞表是表格、沒有「## 段落」，merge 併不進去，一律當快照整份取代（除非選 keep）。
    files：只處理這幾個相對路徑（None＝全部）。舊呼叫 adopt(book_dir, group) 仍可用。

    回傳 adopted（實際寫入份數）、merged、kept、backed_up、conflicts、backups（備份檔名）、targets。
    """
    group = _group(group)
    items = draft_groups(book_dir)[group]
    if not items:
        raise project.ProjectError("「%s」沒有草稿" % group)
    if files is not None:
        if isinstance(files, str):
            files = [files]
        if not isinstance(files, (list, tuple)):
            raise project.ProjectError("files 要是檔名清單")
        wanted = {str(f).replace("\\", "/") for f in files}
        items = [it for it in items if it["rel"] in wanted]
        if not items:
            raise project.ProjectError("選的檔案不在「%s」的草稿裡" % group)
    mode = mode or DEFAULT_MODE[group]
    if mode not in ALLOWED_MODES[group]:
        raise project.ProjectError("「%s」不支援「%s」模式" % (group, mode))
    n_adopted = n_merged = n_kept = n_bak = n_conf = 0
    backups, targets = [], []
    for it in items:
        rel = it["rel"]
        m = _mode_for(group, rel, mode)
        src = _p(book_dir, layout.REVERSE_DRAFTS, *rel.split("/"))
        dst_rel = _canon_rel(group, rel)
        dst = os.path.join(book_dir, *dst_rel.split("/"))
        targets.append({"rel": rel, "mode": m, "dst": dst_rel})
        if m == "keep":
            n_kept += 1
            continue
        new_text = project.read_text(src)
        has_old = os.path.isfile(dst)
        old_text = project.read_text(dst) if has_old else ""
        if has_old:
            bak = tracking.backup(book_dir, dst, "反推前")
            if bak:
                backups.append(os.path.basename(bak))
                n_bak += 1
        if m == "merge" and has_old:
            merged, conflicts = project.merge_entry(old_text, new_text)
            project.write_atomic(dst, merged)
            n_conf += len(conflicts)
            n_merged += 1
        else:
            project.write_atomic(dst, new_text)
        os.remove(src)
        n_adopted += 1
    tracking.git_commit(book_dir, "從正文建立設定：採用%s" % group)
    return {"adopted": n_adopted, "merged": n_merged, "kept": n_kept, "backed_up": n_bak,
            "conflicts": n_conf, "backups": backups, "targets": targets}


def discard(book_dir, group):
    group = _group(group)
    for it in draft_groups(book_dir)[group]:
        os.remove(_p(book_dir, layout.REVERSE_DRAFTS, *it["rel"].split("/")))
    return {"ok": True}
