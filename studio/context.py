# -*- coding: utf-8 -*-
"""
為不能自己讀檔的模型組裝上下文：依「寫前必讀」挑檔案，並控制在模型的上下文長度內。
"""
import contextvars
import os
import re

from . import contract, project, prompts, recall, shared

CJK = re.compile(r"[　-鿿豈-￯]")


DEFAULT_CJK_RATIO = 1.2   # 不知道模型時用的保守值
# 每個任務在自己的執行緒裡設定（不同任務、不同供應商互不影響）
_RATIO = contextvars.ContextVar("cjk_token_ratio", default=DEFAULT_CJK_RATIO)
_LAST = contextvars.ContextVar("last_pack", default=None)


def set_ratio(ratio):
    try:
        r = float(ratio)
    except (TypeError, ValueError):
        r = DEFAULT_CJK_RATIO
    _RATIO.set(min(3.0, max(0.2, r)))


def ratio():
    return _RATIO.get()


def est_tokens(text):
    """粗估 token 數：中日韓字元依供應商設定的比例（預設 1.2，偏保守），其他字元約 0.3。"""
    n_cjk = len(CJK.findall(text))
    return int(n_cjk * _RATIO.get() + (len(text) - n_cjk) * 0.3) + 4


def last_breakdown(top=6):
    """最近一次組上下文時各段的大小，給任務紀錄看。"""
    info = _LAST.get()
    if not info:
        return ""
    parts = sorted(info["sizes"], key=lambda x: -x[1])
    shown = ["%s %s" % (t, _fmt(n)) for t, n in parts[:top] if n > 0]
    rest = sum(n for _, n in parts[top:])
    if rest:
        shown.append("其他 %s" % _fmt(rest))
    s = "上下文組成（約，每個中文字 %.2g token）：%s；預算 %s" % (_RATIO.get(), "、".join(shown), _fmt(info["budget"]))
    if info.get("notes"):
        s += "。" + "；".join(info["notes"])
    return s


def _fmt(n):
    return "%.1f 萬" % (n / 10000.0) if n >= 10000 else "%d" % n


def read(book_dir, rel):
    p = os.path.join(book_dir, rel)
    return project.read_text(p) if os.path.isfile(p) else ""


def strip_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def body(text):
    return strip_comments(project.split_frontmatter(text)[1]).strip()


def _shown_title(t, P):
    """段落標題：程式裡用中文當索引，給模型看時依目前語言翻譯。"""
    if t.endswith("（節錄）"):
        return prompts.label(t[:-4]) + P["excerpt"]
    return prompts.label(t)


class Pack:
    """依優先順序收集段落；超出預算時，低優先的先被截短或捨棄。"""

    def __init__(self, budget):
        self.budget = budget
        self.items = []  # (priority, title, text, keep)  keep: "head" / "tail"
        self.notes = []  # 給任務紀錄看的說明（例如時間線篩了幾條）

    def note(self, text):
        if text:
            self.notes.append(text)

    def add(self, priority, title, text, keep="head"):
        text = (text or "").strip()
        if text:
            self.items.append((priority, title, text, keep))

    def build(self):
        used = 0
        chosen, dropped = [], []
        for pr, title, text, keep in sorted(self.items, key=lambda x: x[0]):
            cost = est_tokens(text) + 10
            if used + cost <= self.budget:
                chosen.append((pr, title, text))
                used += cost
                continue
            room = self.budget - used - 30
            if room > 300:
                ratio = room / cost
                n = max(200, int(len(text) * ratio))
                P = prompts.cur()
                cut = text[:n] + P["cut_tail"] if keep == "head" else P["cut_head"] + text[-n:]
                chosen.append((pr, title + "（節錄）", cut))
                used += est_tokens(cut) + 10
            else:
                dropped.append(title)
        order = {t: i for i, (_, t, _, _) in enumerate(self.items)}
        chosen.sort(key=lambda x: order.get(x[1].replace("（節錄）", ""), 0))
        P = prompts.cur()
        out = "\n\n".join("%s%s%s\n%s" % (P["bk_l"], _shown_title(t, P), P["bk_r"], x) for _, t, x in chosen)
        _LAST.set({"budget": self.budget, "sizes": [(t, est_tokens(x) + 10) for _, t, x in chosen], "notes": list(self.notes)})
        return out, used, dropped


# ---------------------------------------------------------------------------
# 只適用於繁體中文的參考資料（台灣用語、中文 AI 味信號與改寫示範）：其他語言的書不帶，除非有該語言自己的版本
ZH_ONLY_REFS = {"novel-deslop/references/tw-terms.md", "novel-deslop/references/ai-signals.md",
                "novel-deslop/references/rewrite-examples.md"}
LANG_DIR = {"en": "plugin-en", "ja": "plugin-ja"}


def lang_plugin(plugin_dir, lang=None):
    """該語言自己的 plugin 資料夾（plugin-en／plugin-ja，與 plugin 同層）；沒有就回傳原本的 plugin_dir。繁體中文永遠是原本的。"""
    lang = lang or prompts.cur_lang()
    if lang != "zh-TW" and plugin_dir:
        d = os.path.join(os.path.dirname(os.path.normpath(plugin_dir)), LANG_DIR.get(lang, "plugin-" + lang))
        if os.path.isdir(os.path.join(d, "skills")):
            return d
    return plugin_dir


def skill_ref(plugin_dir, rel):
    lang = prompts.cur_lang()
    if lang != "zh-TW":
        # 該語言自己的 skills 資料夾（plugin-en／plugin-ja，與 plugin 同層）有就用
        own = os.path.join(os.path.dirname(os.path.normpath(plugin_dir)), LANG_DIR.get(lang, "plugin-" + lang), "skills", rel)
        if os.path.isfile(own):
            return body(project.read_text(own))
        if rel in ZH_ONLY_REFS:
            return ""
    p = os.path.join(plugin_dir, "skills", rel)
    return body(project.read_text(p)) if os.path.isfile(p) else ""


def chapter_files(book_dir, no):
    return {k: project._scan_dir(os.path.join(book_dir, *k.split("/"))).get(no)
            for k in ("大綱/章綱", "正文", "候選", "追蹤/章節摘要")}


def chapter_text(book_dir, no, prefer=("候選", "正文")):
    for d in prefer:
        f = project._scan_dir(os.path.join(book_dir, d)).get(no)
        if f:
            return d + "/" + f, project.read_text(os.path.join(book_dir, d, f))
    return None, ""


def card_text(book_dir, no):
    f = project._scan_dir(os.path.join(book_dir, "大綱", "章綱")).get(no)
    return ("大綱/章綱/" + f, project.read_text(os.path.join(book_dir, "大綱", "章綱", f))) if f else (None, "")


_LATIN = re.compile(r"[A-Za-z]")
_name_rx = {}


def name_in_text(name, text):
    """名稱有沒有出現在文字裡。含拉丁字母的名稱（英文書）：不分大小寫、要是完整單字，
    所以 jim 對得到 Jim Hawkins，Jimmy 不會被誤認成 Jim；中文、日文名稱照舊用子字串比對。"""
    if not name:
        return False
    if not _LATIN.search(name):
        return name in text
    rx = _name_rx.get(name)
    if rx is None:
        rx = _name_rx[name] = re.compile(r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])", re.I)
    return rx.search(text) is not None


def mentioned_entities(book_dir, text):
    """找出文字中提到的角色、勢力、世界觀檔案。"""
    hits = []
    for sub in ("設定/角色", "設定/勢力", "設定/世界觀"):
        for e in project.list_entries(book_dir, sub):
            names = [e["name"]] + [str(a) for a in (e.get("aliases") or [])]
            if any(name_in_text(n, text) for n in names):
                hits.append(e)
    return hits


FS_BEFORE, FS_AFTER = 3, 5   # 伏筆：預計回收章在第 N−3～N+5 章的整條帶
FS_RECENT = 3                # 伏筆：最近幾章有出現過的整條帶
FS_DONE = ("已回收", "廢棄")


def foreshadow_for(book_dir, scope, a, b=None, pk=None):
    """伏筆：近期的整條帶、其他還沒回收的只帶一行索引、已回收或廢棄的不帶（被點名的照帶）。
    整條帶：scope（章綱等）點名的編號、預計回收章在 [a−3, b+5]、最後出現在最近 3 章。"""
    b = b or a
    tbl = project.read_table(book_dir, "追蹤/伏筆.md")
    rows, hs = tbl["rows"], tbl["headers"]
    if not rows:
        return body(read(book_dir, "追蹤/伏筆.md"))
    ids = set(re.findall(r"\b[A-Z]{1,2}\d{2,}\b", scope or ""))
    full, index = [], []
    for r in rows:
        rid = str(r.get("編號") or "")
        done = str(r.get("狀態") or "").strip() in FS_DONE
        due = _nums(r.get("預計回收"))
        last = _nums(r.get("最後出現"))
        if rid in ids:
            full.append(r)
        elif done:
            continue
        elif any(a - FS_BEFORE <= n <= b + FS_AFTER for n in due) or any(a - FS_RECENT <= n <= b for n in last):
            full.append(r)
        else:
            index.append(r)
    if pk is not None:
        pk.note("伏筆整條帶 %d、索引 %d（已回收或廢棄的不帶）" % (len(full), len(index)))
    out = table_md(hs, full) if full else prompts.cur()["fs_none"]
    if index:
        def short(s, n=30):
            s = str(s or "").replace("|", "／").replace("\n", " ")
            return s if len(s) <= n else s[:n] + "…"
        out += (prompts.cur()["fs_index_head"] +
                "\n".join("| %s | %s | %s | %s |" % (r.get("編號", ""), short(r.get("內容")), r.get("預計回收", ""), r.get("重要度", ""))
                          for r in index))
    return out


# ---------------------------------------------------------------------------
# 會一直長大的表：只帶和這一章有關的列
# ---------------------------------------------------------------------------
FILTER_MIN_TOKENS = 3000   # 表格小於這個量就整份帶
RECENT_CHAPTERS = 10       # 時間線：最近幾章的事件一定帶
MAIN_SHARE = 0.3           # 出現在超過三成列的角色（主角）不拿來比對
_PARTIAL = (r"只知道|不知道|未知|尚未|還沒|以為|誤會|誤認|懷疑|不清楚|不確定|猜測|部分"
            r"|(?i:only knows|does not know|doesn't know|unaware|unknown|not yet|believes|mistakenly|suspects|unclear|unsure|guess|partial)"
            r"|知らない|まだ|誤解|疑って|不明|一部")
_UNREVEALED = ("未揭示", "未知", "不知道", "尚未", "還不知道", "無", "-", "—", "－", "？", "?",
               "unrevealed", "unknown", "not yet", "none", "n/a", "N/A", "未公開", "不明", "なし")


def _nums(s):
    return [int(x) for x in re.findall(r"\d+", str(s or ""))]


def _entity_names(book_dir, scope):
    names = []
    for e in mentioned_entities(book_dir, scope):
        names += [e["name"]] + [str(a) for a in (e.get("aliases") or [])]
    return [n for n in dict.fromkeys(names) if n and len(n) >= 2]


def _open_part(known):
    """從「讀者目前知道」取出讀者還不知道的那幾句。"""
    sents = [x for x in re.split(r"(?<=[。；;])|(?<=[.!?])\s+", known) if x and re.search(_PARTIAL, x)]
    return ("".join(sents).strip() or known[-60:]).replace("|", "／")


def timeline_for(book_dir, scope, a, b=None, pk=None):
    """時間線。表格小時整份帶；大時：
    - 整列帶：讀者完全不知道或還沒到揭示章的、最近幾章的、和本章出場人事有關的
    - 只列「讀者還不知道什麼」（不帶作者真相）：其他還有懸念的列
    - 不帶：其他已經揭曉、和本章無關的列"""
    b = b or a
    tl = project.read_table(book_dir, "追蹤/時間線.md")
    rows, hs = tl["rows"], tl["headers"]
    if not rows:
        return body(read(book_dir, "追蹤/時間線.md"))
    full = table_md(hs, rows)
    if est_tokens(full) <= FILTER_MIN_TOKENS:
        return full
    names = _entity_names(book_dir, scope)
    joined = ["|".join(str(v) for v in r.values()) for r in rows]
    names = [n for n in names if sum(1 for j in joined if n in j) <= max(3, len(rows) * MAIN_SHARE)]
    ids = set(re.findall(r"\b[A-Z]{1,2}\d{2,}\b", scope))
    ledger = has_reader_ledger(book_dir)   # 有帳本就由帳本負責未解疑問
    keep, opens = [], []
    for r, j in zip(rows, joined):
        rev = _nums(r.get("揭示章"))
        known = str(r.get("讀者目前知道") or "").strip()
        hidden = not known or known in _UNREVEALED or not rev or min(rev) >= a
        recent = any(a - RECENT_CHAPTERS <= n <= b for n in rev)
        related = str(r.get("編號") or "") in ids or any(n in j for n in names)
        if hidden or recent or related:
            keep.append(r)
        elif not ledger and re.search(_PARTIAL, known):   # 沒有讀者認知帳本時：從措辭猜讀者還不知道的部分
            opens.append(r)
    if pk is not None:
        pk.note("時間線 %d 條：整列帶 %d、只列未解疑問 %d" % (len(rows), len(keep), len(opens)))
    out = table_md(hs, keep)
    if opens:
        out += (prompts.cur()["tl_open_head"] +
                "\n".join("| %s | %s | %s |" % (r.get("編號", ""), r.get("揭示章", ""), _open_part(str(r.get("讀者目前知道") or "")))
                          for r in opens))
    return out


READER_FILE = "追蹤/讀者認知.md"


def has_reader_ledger(book_dir):
    return bool(project.read_table(book_dir, READER_FILE)["rows"])


def _reader_open(r, a):
    """還沒回收（回收章空白或在本章以後）的懸念／誤認。"""
    if str(r.get("類型") or "").strip() == "已知":
        return False
    rec = _nums(r.get("回收章"))
    return not rec or min(rec) >= a


def reader_for(book_dir, scope, a, b=None, pk=None):
    """讀者認知帳本。表格小時整份帶；大時：
    - 整列帶（含作者真相）：還沒回收而且和本章有關的（章綱點名、出場人事、預計本章回收、最近幾章才種下的）；和本章有關的「已知」
    - 只列內容（不帶作者真相）：其他還沒回收的懸念與誤認
    - 不帶：已回收的、無關的已知"""
    b = b or a
    tbl = project.read_table(book_dir, READER_FILE)
    rows, hs = tbl["rows"], tbl["headers"]
    if not rows:
        return ""
    full = table_md(hs, rows)
    if est_tokens(full) <= FILTER_MIN_TOKENS:
        return full
    names = _entity_names(book_dir, scope)
    joined = ["|".join(str(v) for v in r.values()) for r in rows]
    names = [n for n in names if sum(1 for j in joined if n in j) <= max(3, len(rows) * MAIN_SHARE)]
    ids = set(re.findall(r"\b[A-Z]{1,2}\d{2,}\b", scope))
    keep, idx = [], []
    for r, j in zip(rows, joined):
        rid = str(r.get("編號") or "")
        related = rid in ids or any(n in j for n in names)
        if _reader_open(r, a):
            due = any(a <= n <= b for n in _nums(r.get("回收章")))
            recent = any(a - RECENT_CHAPTERS <= n <= b for n in _nums(r.get("種下章")))
            (keep if related or due or recent else idx).append(r)
        elif str(r.get("類型") or "").strip() == "已知" and related:
            keep.append(r)
    if pk is not None:
        pk.note("讀者認知 %d 條：整列帶 %d、只列內容 %d（已回收的不帶）" % (len(rows), len(keep), len(idx)))
    out = table_md(hs, keep)
    if idx:
        out += (prompts.cur()["reader_open_head"] +
                "\n".join("| %s | %s | %s |" % (r.get("編號", ""), r.get("類型", ""), str(r.get("內容", "")).replace("|", "／"))
                          for r in idx))
    return out


def reader_for_writeback(book_dir):
    """回寫用：還沒回收的整列帶（要能用原編號回收）；已知只列編號和內容（避免重複登記）。"""
    tbl = project.read_table(book_dir, READER_FILE)
    rows, hs = tbl["rows"], tbl["headers"]
    if not rows:
        return ""
    opens = [r for r in rows if _reader_open(r, 0)]
    known = [r for r in rows if str(r.get("類型") or "").strip() == "已知"]
    out = table_md(hs, opens)
    if known:
        out += prompts.cur()["reader_known_head"] + "\n".join("- %s %s" % (r.get("編號", ""), r.get("內容", "")) for r in known)
    return out


READER_TITLE = "讀者認知（懸念與誤認不能提前揭曉；回收章在本章範圍內的才可以揭曉）"

RELATION_FILE = "追蹤/關係.md"
RELATION_TITLE = "角色關係（誰對誰目前的關係與態度；已經改變的不能無故倒退，要變就要在劇情裡有原因）"
RELATION_HISTORY_TITLE = "角色關係（含歷史：誰對誰什麼時候變過；結束章空白＝目前有效）"
_REL_NOW = ["誰", "對誰", "關係", "態度", "起始章"]
_REL_ALL = ["誰", "對誰", "關係", "態度", "起始章", "結束章", "變化原因"]


def _scene_chars(book_dir, scope):
    """文字裡提到的角色（正式名稱）。"""
    return {e["name"] for e in mentioned_entities(book_dir, scope)
            if str(e["file"]).replace("\\", "/").startswith(("設定/角色", "設定/勢力"))}


def relations_for(book_dir, scope, pk=None, history=False):
    """角色關係：只帶「在場角色之間」的。寫稿帶目前有效的；審查（history）連結束章與變化原因一起帶。"""
    rows = project.read_table(book_dir, RELATION_FILE)["rows"]
    if not rows:
        return ""
    chars = _scene_chars(book_dir, scope)
    pair = [r for r in rows if r.get("誰") in chars and r.get("對誰") in chars]
    now = [r for r in pair if not str(r.get("結束章") or "").strip()]
    if history:
        pair.sort(key=lambda r: (r.get("誰", ""), r.get("對誰", ""), _nums(r.get("起始章"))[:1] or [0]))
        out_rows, cols = pair, _REL_ALL
    else:
        out_rows, cols = now, _REL_NOW
    if pk is not None:
        pk.note("角色關係 %d 列（在場角色之間%s）" % (len(out_rows), "，含歷史" if history else "，目前有效"))
    return table_md(cols, out_rows)


def relations_for_writeback(book_dir, text):
    """回寫用：正文出場角色的、目前有效的關係。AI 只需要報有變的。"""
    rows = project.read_table(book_dir, RELATION_FILE)["rows"]
    if not rows:
        return ""
    chars = _scene_chars(book_dir, text)
    mine = [r for r in rows if (r.get("誰") in chars or r.get("對誰") in chars) and not str(r.get("結束章") or "").strip()]
    return table_md(_REL_NOW, mine)


def glossary_for(book_dir, scope, pk=None):
    """名詞表：只帶這一章範圍裡出現的名詞；稱謂類的，說明提到出場角色也帶。表格小時整份帶。"""
    text = read(book_dir, "設定/名詞表.md")
    tbl = project.read_table(book_dir, "設定/名詞表.md")
    rows, hs = tbl["rows"], tbl["headers"]
    if not rows or est_tokens(body(text)) <= FILTER_MIN_TOKENS:
        return body(text)
    key = hs[0] if hs else "名詞"
    names = _entity_names(book_dir, scope)
    keep = []
    for r in rows:
        term = str(r.get(key) or "").strip()
        terms = [t for t in re.split(r"[／/、,，]", term) if t.strip()]
        hit = any(t.strip() in scope for t in terms)
        if not hit and "稱謂" in str(r.get("類別") or ""):
            hit = any(n in "|".join(str(v) for v in r.values()) for n in names)
        if hit:
            keep.append(r)
    if pk is not None:
        pk.note("名詞表帶 %d／%d 條" % (len(keep), len(rows)))
    return table_md(hs, keep)


def table_md(headers, rows):
    if not rows:
        return ""
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(r.get(h, "") for h in headers) + " |" for r in rows]
    return "\n".join(out)


def recent_summaries(book_dir, before_no, n=3):
    sums = project._scan_dir(os.path.join(book_dir, "追蹤", "章節摘要"))
    nos = sorted(k for k in sums if k < before_no)[-n:]
    return "\n\n".join(body(read(book_dir, "追蹤/章節摘要/" + sums[k])) for k in nos)


def book_rules(book_dir):
    return body(read(book_dir, "CLAUDE.md"))


# ---------------------------------------------------------------------------
def for_chapter(book_dir, plugin_dir, no, budget, include_craft=True, prev_from_candidate=False,
                recall_on=True, recall_k=6):
    """寫第 no 章需要的上下文。"""
    pk = Pack(budget)
    card_path, card = card_text(book_dir, no)
    pk.add(0, "本書規則", book_rules(book_dir))
    # 續寫合約：這本書不能違背的事實（章數、角色、已揭示／未揭曉的秘密、未回收伏筆、卷末承諾、禁區）。
    # priority 0：預算不夠時最後才被砍，因為它比任何單一資料表都可靠。沒有合約就自動略過。
    pk.add(0, "續寫合約（不可變事實，不能違背）", body(contract.text(book_dir)))
    pk.add(0, "第%d章章綱（唯一劇情藍圖）" % no, body(card))
    pk.add(1, "本書文風（優先於一般寫作技法）", body(read(book_dir, "設定/文風.md")))
    pk.add(1, "作者偏好", body(read(book_dir, "設定/作者偏好.md")))
    pk.add(1, "共用作者偏好（所有書都適用；和本書衝突時以本書為準）", shared.prefs_for_context(book_dir))
    sname, stext, sfrom = shared.structure_for(book_dir, no)
    if sname:
        pk.add(1, prompts.cur()["chapter_structure_title"].format(name=sname, src=sfrom), stext)
    pk.add(2, "狀態卡（目前局勢）", body(read(book_dir, "追蹤/狀態卡.md")))
    # 上一章結尾
    prev_path, prev = chapter_text(book_dir, no - 1, ("候選", "正文") if prev_from_candidate else ("正文", "候選"))
    if prev:
        pk.add(2, "上一章結尾（%s）" % prev_path, body(prev)[-1200:], keep="tail")
    # 出場角色與相關設定
    scope = card + "\n" + body(read(book_dir, "追蹤/狀態卡.md"))
    for e in mentioned_entities(book_dir, scope):
        pk.add(3, "設定：%s" % e["name"], body(read(book_dir, e["file"])))
        st = read(book_dir, "追蹤/角色狀態/%s.md" % e["name"])
        if st:
            pk.add(3, "角色目前狀態：%s" % e["name"], body(st))
    fs = foreshadow_for(book_dir, card, no, pk=pk)
    pk.add(3, "相關伏筆", fs)
    near = card + "\n" + (body(prev)[-1200:] if prev else "")
    wide = scope + "\n" + near + "\n" + fs + "\n" + "\n".join(
        body(read(book_dir, e["file"])) for e in mentioned_entities(book_dir, scope))
    pk.add(3, READER_TITLE, reader_for(book_dir, card + "\n" + fs, no, pk=pk))
    pk.add(3, RELATION_TITLE, relations_for(book_dir, scope + "\n" + near, pk=pk))
    # 相似情境（P2 檢索式記憶）：從作者自己寫過的段落裡找最像的幾段。
    # 查詢＝本章章綱＋上一章結尾＋這章會出場的角色名字。priority 3：預算不夠時可以被丟。
    if recall_on:
        who = "、".join(e["name"] for e in mentioned_entities(book_dir, scope)[:8])
        query = card + "\n" + (body(prev)[-600:] if prev else "") + "\n" + who
        block = recall.context_block(book_dir, no, query, k=recall_k)
        if block:
            pk.add(3, "相似情境（作者自己寫過的段落；參考處境與寫法，不要照抄）", block)
    pk.add(4, "時間線（「讀者目前知道」是資訊邊界，不能提前說破）", timeline_for(book_dir, near, no, pk=pk))
    pk.add(4, "名詞表", glossary_for(book_dir, wide, pk=pk))
    pk.add(5, "前幾章摘要", recent_summaries(book_dir, no))
    if include_craft:
        pk.add(6, "寫作技法", skill_ref(plugin_dir, "novel-write/references/writing-craft.md"))
    return pk.build()


def for_writeback(book_dir, no, text, budget):
    """回寫追蹤需要的上下文。"""
    pk = Pack(budget)
    _, card = card_text(book_dir, no)
    pk.add(0, "第%d章正文（已採用）" % no, body(text))
    pk.add(1, "目前狀態卡（請在此基礎上更新）", body(read(book_dir, "追蹤/狀態卡.md")))
    pk.add(1, "伏筆總表", body(read(book_dir, "追蹤/伏筆.md")))
    pk.add(2, "時間線", body(read(book_dir, "追蹤/時間線.md")))
    pk.add(1, "讀者認知帳本（還沒回收的；本章揭曉了就用原編號填回收章）", reader_for_writeback(book_dir))
    for e in mentioned_entities(book_dir, text):
        st = read(book_dir, "追蹤/角色狀態/%s.md" % e["name"])
        if st:
            pk.add(2, "角色目前狀態：%s" % e["name"], body(st))
    pk.add(2, "角色關係（目前有效的；只有本章變了或第一次建立的才寫進 relations）", relations_for_writeback(book_dir, text))
    pk.add(3, "第%d章章綱" % no, body(card))
    pk.add(3, "名詞表（已登記的不用再列為新增物）", body(read(book_dir, "設定/名詞表.md")))
    names = [e["name"] for e in project.list_entries(book_dir, "設定/角色")]
    pk.add(3, "已建檔的角色", "、".join(names))
    return pk.build()


def for_review(book_dir, plugin_dir, a, b, budget):
    pk = Pack(budget)
    pk.add(0, "審查清單", skill_ref(plugin_dir, "novel-review/references/checklist.md"))
    pk.add(0, "本書規則", book_rules(book_dir))
    pk.add(1, "共用作者偏好（所有書都適用；和本書衝突時以本書為準）", shared.prefs_for_context(book_dir))
    joined = ""
    for n in range(a, b + 1):
        path, t = chapter_text(book_dir, n, ("正文", "候選"))
        if t:
            pk.add(1, "第%d章正文（%s）" % (n, path), body(t))
            joined += t
        _, card = card_text(book_dir, n)
        pk.add(3, "第%d章章綱" % n, body(card))
    prev_path, prev = chapter_text(book_dir, a - 1, ("正文",))
    if prev:
        pk.add(2, "前一章結尾", body(prev)[-1000:], keep="tail")
    pk.add(2, "狀態卡", body(read(book_dir, "追蹤/狀態卡.md")))
    cards = "\n".join(card_text(book_dir, n)[1] for n in range(a, b + 1))
    pk.add(2, "伏筆", foreshadow_for(book_dir, joined + "\n" + cards, a, b, pk=pk))
    pk.add(2, READER_TITLE, reader_for(book_dir, joined + "\n" + cards, a, b, pk=pk))
    pk.add(2, RELATION_HISTORY_TITLE, relations_for(book_dir, joined + "\n" + cards, pk=pk, history=True))
    pk.add(2, "時間線", timeline_for(book_dir, joined + "\n" + cards, a, b, pk=pk))
    for e in mentioned_entities(book_dir, joined):
        pk.add(3, "設定：%s" % e["name"], body(read(book_dir, e["file"])))
        st = read(book_dir, "追蹤/角色狀態/%s.md" % e["name"])
        if st:
            pk.add(3, "角色目前狀態：%s" % e["name"], body(st))
    pk.add(4, "名詞表", glossary_for(book_dir, joined + "\n" + cards, pk=pk))
    pk.add(4, "故事核心（讀者契約）", body(read(book_dir, "設定/故事核心.md")))
    return pk.build()


def for_deslop(book_dir, plugin_dir, budget):
    pk = Pack(budget)
    pk.add(0, "本書文風（作者允許的寫法不要改）", body(read(book_dir, "設定/文風.md")))
    pk.add(0, "作者偏好", body(read(book_dir, "設定/作者偏好.md")))
    pk.add(0, "共用作者偏好（所有書都適用；和本書衝突時以本書為準）", shared.prefs_for_context(book_dir))
    pk.add(1, "AI 味信號", skill_ref(plugin_dir, "novel-deslop/references/ai-signals.md"))
    pk.add(2, "改寫示範", skill_ref(plugin_dir, "novel-deslop/references/rewrite-examples.md"))
    pk.add(3, "兩岸用語與標點", skill_ref(plugin_dir, "novel-deslop/references/tw-terms.md"))
    return pk.build()


def for_chat(book_dir, budget):
    pk = Pack(budget)
    pk.add(0, "本書規則", book_rules(book_dir))
    pk.add(1, "故事核心", body(read(book_dir, "設定/故事核心.md")))
    pk.add(1, "狀態卡", body(read(book_dir, "追蹤/狀態卡.md")))
    pk.add(2, "全書大綱", body(read(book_dir, "大綱/全書大綱.md")))
    pk.add(2, "伏筆總表", body(read(book_dir, "追蹤/伏筆.md")))
    pk.add(3, "名詞表", body(read(book_dir, "設定/名詞表.md")))
    chs = project.scan_chapters(book_dir)
    pk.add(3, "章節列表", "\n".join("第%d章 %s（%s）" % (c["no"], c["title"], "已寫" if c["text_file"] else (c["card_status"] or "")) for c in chs))
    return pk.build()
