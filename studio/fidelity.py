"""去 AI 味後的保真檢查：比對改前與改後，列出名字、數字、對白、字數的變化。純本機，不花 token。

只列出來給作者看（審查裡是「提醒」，整章自動流程不會自動修回）：去 AI 味有時會合理地把重複的名字改成代稱。
結果存在 .studio/保真/第NNN章.json，記下改後稿的雜湊；稿子之後又被改過就不再帶進審查。
"""
import json
import os
import re
from collections import Counter

from . import context, goals, project

DIR = os.path.join(".studio", "保真")
NAME_DROP = 0.3       # 名字少了三成以上（而且至少少 3 次）才列
LENGTH_CHANGE = 0.15  # 字數增減超過 15% 才列
MAX_LIST = 12

_NUM = re.compile(r"\d+(?:[.,]\d+)*(?:%|％)?|[零〇一二兩三四五六七八九十百千萬]+(?=分鐘|秒|小時|天|週|年|個月|月|次|章|人|名|塊|元|萬|公里|公尺|米|歲|艘|條|張|頁|根|點|號|層|排|列|份|輛|架|發)")
_DIALOGUE = re.compile(r"「([^「」]{2,})」")


def _names(book_dir):
    names = []
    for sub in ("設定/角色", "設定/勢力", "設定/世界觀"):
        for e in project.list_entries(book_dir, sub):
            names += [e["name"]] + [str(a) for a in (e.get("aliases") or [])]
    gl = project.read_table(book_dir, "設定/名詞表.md")
    key = gl["headers"][0] if gl["headers"] else "名詞"
    for r in gl["rows"]:
        names += [t.strip() for t in re.split(r"[／/、,，]", str(r.get(key) or "")) if t.strip()]
    return [n for n in dict.fromkeys(names) if len(n) >= 2]


def _count_names(text, names):
    """長的先算、算過就挖掉，避免「林遠」重算「林遠之」。"""
    out, rest = {}, text
    for n in sorted(names, key=len, reverse=True):
        c = rest.count(n)
        if c:
            out[n] = c
            rest = rest.replace(n, "\0")
    return out


def compare(book_dir, before, after):
    """回傳 [{"kind", "text"}]。"""
    b, a = context.body(before), context.body(after)
    out = []
    names = _names(book_dir)
    cb, ca = _count_names(b, names), _count_names(a, names)
    gone = [n for n, c in cb.items() if not ca.get(n)]
    less = [(n, c, ca.get(n, 0)) for n, c in cb.items()
            if ca.get(n) and c - ca[n] >= 3 and (c - ca[n]) / c >= NAME_DROP]
    if gone:
        out.append({"kind": "名字不見了", "text": "、".join("%s（原本 %d 次）" % (n, cb[n]) for n in gone[:MAX_LIST])})
    if less:
        out.append({"kind": "名字少很多", "text": "、".join("%s %d→%d" % x for x in less[:MAX_LIST])})
    nb, na = Counter(_NUM.findall(b)), Counter(_NUM.findall(a))
    lost = list((nb - na).elements())
    if lost:
        out.append({"kind": "數字不見了或改了", "text": "、".join(dict.fromkeys(lost[:MAX_LIST * 2]).keys())})
    db = _DIALOGUE.findall(b)
    ad = "".join(_DIALOGUE.findall(a))
    changed = [d for d in db if d not in ad]
    if changed:
        ex = "；".join("「%s」" % (d if len(d) <= 30 else d[:30] + "……") for d in changed[:5])
        out.append({"kind": "對白被改寫或刪掉", "text": "%d／%d 句：%s%s" % (len(changed), len(db), ex, "……" if len(changed) > 5 else "")})
    lb, la = project.count_chars(b), project.count_chars(a)
    if lb and abs(la - lb) / lb > LENGTH_CHANGE:
        out.append({"kind": "字數變化大", "text": "%d → %d 字（%+d%%）" % (lb, la, round((la - lb) * 100 / lb))})
    return out


def save(book_dir, no, path, after, items):
    d = os.path.join(book_dir, DIR)
    p = os.path.join(d, "第%03d章.json" % no)
    if not items:
        if os.path.isfile(p):
            os.remove(p)
        return
    os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"chapter": no, "path": path, "hash": goals.text_hash(after), "items": items}, f, ensure_ascii=False, indent=1)


def load(book_dir, no, text):
    """稿子沒再被改過才回傳（雜湊相同）。"""
    p = os.path.join(book_dir, DIR, "第%03d章.json" % no)
    if not os.path.isfile(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return []
    return rec.get("items") or [] if rec.get("hash") == goals.text_hash(text) else []


def run(book_dir, no, path, before, after):
    """比對、存檔，回傳附在去 AI 味匯報後面的文字。"""
    try:
        items = compare(book_dir, before, after)
    except Exception as e:   # 檢查失敗不影響去 AI 味
        return "\n\n保真檢查沒有跑完：%s" % e
    save(book_dir, no, path, after, items)
    if not items:
        return "\n\n**保真檢查**：名字、數字、對白、字數都沒有明顯變化。"
    return "\n\n**保真檢查**（只列出來給你看，請自己判斷要不要改回）\n" + "\n".join("- %s：%s" % (x["kind"], x["text"]) for x in items)
