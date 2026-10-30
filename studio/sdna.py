# -*- coding: utf-8 -*-
"""結構 DNA：把一本書的「骨架」抽成數字，給「由 A 書產生 B 書」用。

刻意只取抽象特徵——視角、章長分佈、對白節奏、段落節奏、章長曲線形狀。
**不取**人名、地名、專有名詞、事件序列：那些是來源書的內容，帶進新書就是抄。

全本機計算、沒有隨機性：同一本書跑兩次逐位元組相同。
"""
import json
import os
import re
import statistics

from . import lang as lang_mod, project, prompts

REL = "設定/結構DNA.json"
VER = 1
DIALOGUE_RX = re.compile(r"「[^」]*」|『[^』]*』|\"[^\"]*\"|[“”][^“”]*[“”]|“[^”]*”")
PRONOUNS = {
    "zh-TW": (re.compile(r"我|俺|咱"), re.compile(r"他|她|祂")),
    "ja": (re.compile(r"私|僕|俺|わたし|ぼく|おれ|あたし"), re.compile(r"彼|彼女|かれ|かのじょ")),
    "en": (re.compile(r"\bI\b|\bmy\b|\bme\b|\bI'm\b|\bI've\b"),
           re.compile(r"\bhe\b|\bshe\b|\bhis\b|\bher\b|\bhim\b", re.I)),
}


def _body(book_dir):
    ch = project._scan_dir(os.path.join(book_dir, "正文"))
    return [project.split_frontmatter(project.read_text(os.path.join(book_dir, "正文", ch[no])))[1]
            for no in sorted(ch)]


def pov(texts, lang="zh-TW"):
    """人稱：把對白拿掉，只看敘述句裡第一人稱與第三人稱代詞的比例。"""
    narration = "\n".join(DIALOGUE_RX.sub("", t) for t in texts)
    rx1, rx3 = PRONOUNS.get(lang, PRONOUNS["zh-TW"])
    f, t = len(rx1.findall(narration)), len(rx3.findall(narration))
    if f + t == 0:
        return {"人稱": "無法判斷", "依據": "沒有敘述句"}
    if f >= t * 2:
        who = "第一人稱"
    elif t >= f * 2:
        who = "第三人稱"
    else:
        who = "混合（限制視角）"
    return {"人稱": who, "依據": "敘述句裡第一人稱 %d 次、第三人稱 %d 次" % (f, t)}


def dialogue_ratio(texts):
    """對白比例：對白行數 ÷ 總行數（跟文風指標的算法不同，這裡看的是「章節結構」）。"""
    lines = [ln.strip() for t in texts for ln in t.splitlines() if ln.strip()]
    if not lines:
        return 0.0
    return sum(1 for ln in lines if ln.startswith(("「", "『", "\""))) / len(lines)


def shape(lens, buckets=10):
    """章長曲線：把章節分成十段，各段平均章長 ÷ 全書平均（1.0＝平均）。"""
    if not lens:
        return []
    mean = statistics.mean(lens)
    step = max(1, len(lens) // buckets)
    out = []
    for i in range(0, len(lens), step):
        chunk = lens[i:i + step]
        out.append(round(statistics.mean(chunk) / max(1, mean), 2))
    return out[:buckets]


def build(book_dir):
    lang = lang_mod.book_lang(book_dir)
    texts = _body(book_dir)
    lens = [project.count_chars(t) for t in texts if t.strip()]

    ch = {}
    if lens:
        ch = {"章數": len(lens), "平均": round(statistics.mean(lens)),
              "最短": min(lens), "最長": max(lens),
              "變異": round(statistics.pstdev(lens) / max(1, statistics.mean(lens)), 2),
              "最長/最短": round(max(lens) / max(1, min(lens)), 1)}
    ratio = dialogue_ratio(texts)
    per_chapter = []
    for t in texts:
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        if lines:
            per_chapter.append(sum(1 for ln in lines if ln.startswith(("「", "『", "\""))) / len(lines))
    var = round(statistics.pstdev(per_chapter) / max(1e-9, statistics.mean(per_chapter)), 2) \
        if per_chapter else 0

    prev = prompts.cur_lang()
    try:
        prompts.set_lang(lang)
        from . import fingerprint
        fp = fingerprint.build(book_dir)
    finally:
        prompts.set_lang(prev)

    return {"版本": VER, "語言": lang, "視角": pov(texts, lang), "章節": ch,
            "對白": {"比例": round(ratio, 2), "章間變異": var},
            "段落": {k: v for k, v in (fp.get("文字指標") or {}).items()
                     if k in ("平均段長", "單句成段")},
            "章長曲線": shape(lens),
            "排除": ["人名", "地名", "專有名詞", "事件序列"],
            "說明": "這是骨架，不會出現來源書的任何名字；要寫新書時和風格指紋一起用。"}


def save(book_dir):
    data = build(book_dir)
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
        return "（還沒有結構 DNA；先跑 tools/sdna.py --book <書> --save）"
    ch = data.get("章節") or {}
    d = data.get("對白") or {}
    L = ["語言 %s｜%s（%s）" % (data.get("語言"), (data.get("視角") or {}).get("人稱"),
                               (data.get("視角") or {}).get("依據")),
         "章長：平均 %d、最短 %d、最長 %d、變異 %.2f、最長/最短 %.1f"
         % (ch.get("平均", 0), ch.get("最短", 0), ch.get("最長", 0), ch.get("變異", 0), ch.get("最長/最短", 0)),
         "對白：比例 %.0f%%、章間變異 %.2f" % ((d.get("比例") or 0) * 100, d.get("章間變異") or 0),
         "章長曲線：" + "、".join("%.2f" % x for x in (data.get("章長曲線") or []))]
    return "\n".join(L)
