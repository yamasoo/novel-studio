# -*- coding: utf-8 -*-
"""
為不能自己讀檔的模型組裝上下文：依「寫前必讀」挑檔案，並控制在模型的上下文長度內。
"""
import os
import re

from . import project

CJK = re.compile(r"[　-鿿豈-￯]")


def est_tokens(text):
    """粗估 token 數：中日韓字元約 1.2，其他字元約 0.3（偏保守）。"""
    n_cjk = len(CJK.findall(text))
    return int(n_cjk * 1.2 + (len(text) - n_cjk) * 0.3) + 4


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


def foreshadow_rows(book_dir, text):
    tbl = project.read_table(book_dir, "追蹤/伏筆.md")
    ids = set(re.findall(r"F\d{3,}", text))
    keep = [r for r in tbl["rows"] if r.get("編號") in ids or
            (r.get("狀態") not in ("已回收", "廢棄") and r.get("重要度") in ("高", "中"))]
    return tbl["headers"], keep


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
    h, rows = foreshadow_rows(book_dir, card)
    pk.add(3, "相關伏筆", table_md(h, rows))
    tl = project.read_table(book_dir, "追蹤/時間線.md")
    pk.add(4, "時間線（「讀者目前知道」是資訊邊界，不能提前說破）", table_md(tl["headers"], tl["rows"]))
    pk.add(4, "名詞表", body(read(book_dir, "設定/名詞表.md")))
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
    pk.add(2, "伏筆總表", body(read(book_dir, "追蹤/伏筆.md")))
    pk.add(2, "時間線", body(read(book_dir, "追蹤/時間線.md")))
    for e in mentioned_entities(book_dir, joined):
        pk.add(3, "設定：%s" % e["name"], body(read(book_dir, e["file"])))
        st = read(book_dir, "追蹤/角色狀態/%s.md" % e["name"])
        if st:
            pk.add(3, "角色目前狀態：%s" % e["name"], body(st))
    pk.add(4, "名詞表", body(read(book_dir, "設定/名詞表.md")))
    pk.add(4, "故事核心（讀者契約）", body(read(book_dir, "設定/故事核心.md")))
    return pk.build()


def for_deslop(book_dir, plugin_dir, budget):
    pk = Pack(budget)
    pk.add(0, "本書文風（作者允許的寫法不要改）", body(read(book_dir, "設定/文風.md")))
    pk.add(0, "作者偏好", body(read(book_dir, "設定/作者偏好.md")))
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
