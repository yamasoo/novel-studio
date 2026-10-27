# -*- coding: utf-8 -*-
"""
為不能自己讀檔的模型組裝上下文：依「寫前必讀」挑檔案，並控制在模型的上下文長度內。
"""
import contextvars
import os
import re

from . import project, shared

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
                cut = text[:n] + "\n……（以下省略）" if keep == "head" else "……（前略）\n" + text[-n:]
                chosen.append((pr, title + "（節錄）", cut))
                used += est_tokens(cut) + 10
            else:
                dropped.append(title)
        order = {t: i for i, (_, t, _, _) in enumerate(self.items)}
        chosen.sort(key=lambda x: order.get(x[1].replace("（節錄）", ""), 0))
        out = "\n\n".join("【%s】\n%s" % (t, x) for _, t, x in chosen)
        _LAST.set({"budget": self.budget, "sizes": [(t, est_tokens(x) + 10) for _, t, x in chosen], "notes": list(self.notes)})
        return out, used, dropped


# ---------------------------------------------------------------------------
def skill_ref(plugin_dir, rel):
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


def mentioned_entities(book_dir, text):
    """找出文字中提到的角色、勢力、世界觀檔案。"""
    hits = []
    for sub in ("設定/角色", "設定/勢力", "設定/世界觀"):
        for e in project.list_entries(book_dir, sub):
            names = [e["name"]] + [str(a) for a in (e.get("aliases") or [])]
            if any(n and n in text for n in names):
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
    out = table_md(hs, full) if full else "（近期沒有要處理的伏筆）"
    if index:
        def short(s, n=30):
            s = str(s or "").replace("|", "／").replace("\n", " ")
            return s if len(s) <= n else s[:n] + "…"
        out += ("\n\n其他還沒回收的伏筆（只列索引，不要在本章擅自回收；章綱要求的以章綱為準）\n"
                "| 編號 | 內容 | 預計回收 | 重要度 |\n|---|---|---|---|\n" +
                "\n".join("| %s | %s | %s | %s |" % (r.get("編號", ""), short(r.get("內容")), r.get("預計回收", ""), r.get("重要度", ""))
                          for r in index))
    return out


# ---------------------------------------------------------------------------
# 會一直長大的表：只帶和這一章有關的列
# ---------------------------------------------------------------------------
FILTER_MIN_TOKENS = 3000   # 表格小於這個量就整份帶
RECENT_CHAPTERS = 10       # 時間線：最近幾章的事件一定帶
MAIN_SHARE = 0.3           # 出現在超過三成列的角色（主角）不拿來比對
_PARTIAL = r"只知道|不知道|未知|尚未|還沒|以為|誤會|誤認|懷疑|不清楚|不確定|猜測|部分"
_UNREVEALED = ("未揭示", "未知", "不知道", "尚未", "還不知道", "無", "-", "—", "－", "？", "?")


def _nums(s):
    return [int(x) for x in re.findall(r"\d+", str(s or ""))]


def _entity_names(book_dir, scope):
    names = []
    for e in mentioned_entities(book_dir, scope):
        names += [e["name"]] + [str(a) for a in (e.get("aliases") or [])]
    return [n for n in dict.fromkeys(names) if n and len(n) >= 2]


def _open_part(known):
    """從「讀者目前知道」取出讀者還不知道的那幾句。"""
    sents = [x for x in re.split(r"(?<=[。；;])", known) if re.search(_PARTIAL, x)]
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
        out += ("\n\n還沒揭曉的事（和本章沒有直接關係，只列讀者還不知道的部分；不要在本章說破。章綱要揭曉的事，以章綱為準）\n"
                "| 編號 | 揭示章 | 讀者還不知道 |\n|---|---|---|\n" +
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
        out += ("\n\n其他還沒揭曉的懸念與誤認（和本章沒有直接關係，只列讀者目前的認知；不要在本章說破。章綱要揭曉的，以章綱為準）\n"
                "| 編號 | 類型 | 內容 |\n|---|---|---|\n" +
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
        out += "\n\n已登記的已知（不用重複登記）\n" + "\n".join("- %s %s" % (r.get("編號", ""), r.get("內容", "")) for r in known)
    return out


READER_TITLE = "讀者認知（懸念與誤認不能提前揭曉；回收章在本章範圍內的才可以揭曉）"


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
def for_chapter(book_dir, plugin_dir, no, budget, include_craft=True, prev_from_candidate=False):
    """寫第 no 章需要的上下文。"""
    pk = Pack(budget)
    card_path, card = card_text(book_dir, no)
    pk.add(0, "本書規則", book_rules(book_dir))
    pk.add(0, "第%d章章綱（唯一劇情藍圖）" % no, body(card))
    pk.add(1, "本書文風（優先於一般寫作技法）", body(read(book_dir, "設定/文風.md")))
    pk.add(1, "作者偏好", body(read(book_dir, "設定/作者偏好.md")))
    pk.add(1, "共用作者偏好（所有書都適用；和本書衝突時以本書為準）", shared.prefs_for_context(book_dir))
    sname, stext, sfrom = shared.structure_for(book_dir, no)
    if sname:
        pk.add(1, "本章結構：%s（%s；節拍參考，章綱的情節點與章末停點優先，篇幅比例不必精確）" % (sname, sfrom), stext)
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
