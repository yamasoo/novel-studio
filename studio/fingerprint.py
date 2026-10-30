# -*- coding: utf-8 -*-
"""風格指紋：把一本書的「寫法」抽成可比較、可攜帶的資料。

P6（由 A 書產生 B 書）的第一份資產。只取**風格**，不取故事：
  1. 文字指標（13 項，跟文風閉環同一套）
  2. 章長分佈（平均／中位／最短／最長／變異）
  3. 對白比例與章節間波動
  4. 十段代表性短句（40–120 字）——**人名一律遮掉**，避免把來源的角色帶進新書

全部本機計算、沒有隨機性：同一本書跑兩次，輸出逐位元組相同（時間戳不寫進檔案）。
"""
import json
import os
import statistics

from . import contract, lang as lang_mod, project, prompts, shared

REL = "設定/風格指紋.json"
VER = 1
SENT_MIN, SENT_MAX = 40, 120      # 代表句的字數範圍
PICK = 10


def _sentences(text):
    """切句：句末標點（含後面的收引號／收括號）算一句；只有引號的碎片丟掉。"""
    import re
    out = []
    for m in re.finditer(r"[^。！？!?]*[。！？!?]+[」』）)]*", text or ""):
        s = m.group(0).strip()
        s = s.lstrip("「『（(")
        if SENT_MIN <= len(s) <= SENT_MAX and not re.fullmatch(r"[」』）)。！？\s]+", s):
            out.append(s)
    return out


def _mask(text, names):
    """把角色名換成「某」：句子長度不變、語感還在，但不會把來源的人名帶出去。"""
    for n in sorted((x for x in names if x and len(x) >= 2), key=len, reverse=True):
        text = text.replace(n, "某")
    return text


def _pick(sentences, k=PICK):
    """挑十句：先平均散在各章，再用 bigram 多樣性補。順序固定 → 結果可重現。"""
    from . import recall
    picked, used = [], set()
    step = max(1, len(sentences) // k)
    for i in range(0, len(sentences), step):
        if len(picked) >= k // 2:
            break
        s = sentences[i]
        if recall._tokens(s)[:8] and i not in used:
            picked.append(s)
            used.add(i)
    # 補到 k 句：每次挑「跟已選句子最不像」的那句
    while len(picked) < k:
        best, best_score = None, -1
        for i, s in enumerate(sentences):
            if i in used:
                continue
            ts = set(recall._tokens(s))
            if not ts:
                continue
            sim = max((len(ts & set(recall._tokens(p))) / max(1, len(ts | set(recall._tokens(p))))
                       for p in picked), default=0)
            score = 1 - sim
            if score > best_score:
                best, best_score = i, score
        if best is None:
            break
        picked.append(sentences[best])
        used.add(best)
    return picked


def _entity_names(book_dir):
    """要遮的名字：角色，加上勢力／世界觀的條目名（地名、組織名都是來源的內容）。"""
    names = [c[0] for c in contract.characters(book_dir)]
    for sub in ("設定/勢力", "設定/世界觀"):
        d = os.path.join(book_dir, *sub.split("/"))
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".md"):
                    names.append(os.path.splitext(f)[0])
    return [n for n in names if n and len(n) >= 2]


def build(book_dir, k=PICK):
    """回傳指紋 dict（不含時間戳，保證可重現）。"""
    lang = lang_mod.book_lang(book_dir)
    prev = prompts.cur_lang()
    try:
        prompts.set_lang(lang)
        metrics, basis = _target_metrics(book_dir)
        names = _entity_names(book_dir)
        ch = project._scan_dir(os.path.join(book_dir, "正文"))
        texts = [project.split_frontmatter(project.read_text(os.path.join(book_dir, "正文", ch[no])))[1]
                 for no in sorted(ch)]
    finally:
        prompts.set_lang(prev)

    lens = [project.count_chars(t) for t in texts if t.strip()]
    sents = []
    for t in texts:
        sents.extend(_sentences(t))
    picked = [_mask(s, names) for s in _pick(sents, k)]

    stats = {"章數": len(lens), "總字數": sum(lens)}
    if lens:
        stats.update({"平均章長": round(statistics.mean(lens)),
                      "中位章長": round(statistics.median(lens)),
                      "最短章長": min(lens), "最長章長": max(lens),
                      "章長變異": round(statistics.pstdev(lens) / max(1, statistics.mean(lens)), 2)})
    keep = ("對白比例", "平均句長", "短句比例", "平均段長", "單句成段", "每千字刪節號")
    metrics = {k: metrics[k] for k in keep if k in metrics}
    return {"版本": VER, "語言": lang, "章節": stats, "文字指標": metrics,
            "指標來源": basis, "代表句": picked,
            "說明": "代表句已把人名遮成「某」；只在生成新書時當語感範例，不要原句照抄。"}


def _target_metrics(book_dir):
    """跟文風閉環同一套：優先用文風檔，沒有就量作者自己的正文。"""
    from . import style_loop
    return style_loop.target_metrics(book_dir)


def save(book_dir, k=PICK):
    data = build(book_dir, k)
    p = project.safe_path(book_dir, REL)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = "%s.%d.tmp" % (p, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, p)
    return REL


def load(book_dir):
    p = project.safe_path(book_dir, REL)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def show(data):
    if not data:
        return "（還沒有風格指紋；先跑 tools/fingerprint.py --book <書> --save）"
    ch = data.get("章節") or {}
    L = ["語言 %s｜%d 章、%d 字（平均 %.0f 字/章，變異 %.2f）"
         % (data.get("語言"), ch.get("章數", 0), ch.get("總字數", 0),
            ch.get("平均章長", 0), ch.get("章長變異", 0)),
         "文字指標：" + "、".join("%s %s" % (k, v) for k, v in (data.get("文字指標") or {}).items()),
         "代表句（人名已遮）："]
    L += ["  %d. %s" % (i + 1, s) for i, s in enumerate(data.get("代表句") or [])]
    return "\n".join(L)
