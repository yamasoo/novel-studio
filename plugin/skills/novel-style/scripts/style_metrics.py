# -*- coding: utf-8 -*-
"""
文風文字指標（本機統計，不用 AI）。

用法：
  python style_metrics.py 樣本.md [更多檔案…] [--exclude 林晚,沈既白]

輸出一張 Markdown 表格，可以直接貼進文風檔的「## 文字指標（程式統計）」一節。
--exclude：不列入「高頻詞組」的詞（本書的人名、地名），避免它們佔滿名單。
小說工作台也用這支程式統計文風（studio/shared.py 會載入它）。
"""
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
METRICS_HEAD = "## 文字指標（程式統計）"


class SampleTooShort(ValueError):
    pass


def strip_frontmatter(text):
    if text.startswith("---"):
        lines = text.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:])
    return text


CJK = re.compile(r"[㐀-鿿豈-﫿]")
SENT_END = re.compile(r"[。！？!?]+[」』]?|……+[」』]?")
PUNCT_KEYS = [("逗號", "，"), ("頓號", "、"), ("驚嘆號", "！"), ("問號", "？"), ("刪節號", "……"), ("破折號", "——")]
# 數值越大／越小代表什麼（給作者看的說明）
METRIC_NOTES = {
    "平均句長": "字；越短節奏越快",
    "短句比例": "8 字以下的句子",
    "長句比例": "30 字以上的句子",
    "平均段長": "字",
    "單句成段": "只有一句的段落比例",
    "對白比例": "引號內字數佔全部",
    "對白段比例": "含對白的段落比例",
    "每千字的": "「的」字密度，越高修飾越多",
    "每千字地": "「地」字密度，越高副詞越多",
    "每千字AI味信號": "程式偵測到的常見 AI 套語",
}


def _prose(text):
    body = strip_frontmatter(text.replace("\r\n", "\n"))
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"(?m)^\s*#.*$", "", body)
    body = re.sub(r"(?m)^\s*([-*_]){3,}\s*$", "", body)
    return body


def _paragraphs(body):
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if len(paras) <= 2 and body.count("\n") > 4:
        paras = [ln.strip() for ln in body.split("\n") if ln.strip()]
    return [re.sub(r"\s+", "", p.lstrip("　 ")) for p in paras]


def _ai_signals():
    """借用 novel-deslop 的 AI 套語清單（找不到就略過這一項）。"""
    try:
        import importlib.util
        p = os.path.join(HERE, "..", "..", "novel-deslop", "scripts", "check_text.py")
        spec = importlib.util.spec_from_file_location("check_text_for_metrics", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return [pat for _, pat in mod.AI_SIGNALS]
    except Exception:
        return []


_AI = None


def analyze(text, exclude=()):
    """回傳有順序的指標 dict。exclude：不列入高頻詞組的詞（例如本書的人名、地名）。"""
    global _AI
    if _AI is None:
        _AI = _ai_signals()
    body = _prose(text)
    paras = _paragraphs(body)
    joined = "".join(paras)
    total = len(CJK.findall(joined))
    if total < 300:
        raise SampleTooShort("樣本太短了（中文 %d 字）。至少要 300 字，建議 3000 字以上，統計才有參考價值。" % total)
    sents = []
    for p in paras:
        start = 0
        for m in SENT_END.finditer(p):
            sents.append(p[start:m.end()])
            start = m.end()
        if p[start:].strip():
            sents.append(p[start:])
    slen = [len(CJK.findall(s)) for s in sents]
    slen = [n for n in slen if n > 0]
    plen = [len(CJK.findall(p)) for p in paras if CJK.search(p)]
    dlg = sum(len(CJK.findall(m)) for m in re.findall(r"「([^「」]*)」", joined))
    k = 1000.0 / total
    m = {"樣本字數": total,
         "平均句長": round(sum(slen) / len(slen), 1) if slen else 0,
         "短句比例": "%d%%" % round(100.0 * sum(1 for n in slen if n <= 8) / max(1, len(slen))),
         "長句比例": "%d%%" % round(100.0 * sum(1 for n in slen if n >= 30) / max(1, len(slen))),
         "平均段長": round(sum(plen) / len(plen), 1) if plen else 0,
         "單句成段": "%d%%" % round(100.0 * sum(1 for p in paras if len(SENT_END.findall(p)) <= 1) / max(1, len(paras))),
         "對白比例": "%d%%" % round(100.0 * dlg / total),
         "對白段比例": "%d%%" % round(100.0 * sum(1 for p in paras if "「" in p) / max(1, len(paras)))}
    for label, ch in PUNCT_KEYS:
        m["每千字" + label] = round(joined.count(ch) * k, 1)
    m["每千字的"] = round(joined.count("的") * k, 1)
    m["每千字地"] = round(len(re.findall(r"(?<=[一-鿿])地(?=[一-鿿])", joined)) * k, 1)
    m["每千字AI味信號"] = round(sum(len(re.findall(p, joined)) for p in _AI) * k, 1)
    m["高頻詞組"] = "、".join(frequent_phrases(paras, exclude=exclude)) or "（沒有特別重複的詞組）"
    return m


EDGE_HEAD = set("了的著過是在和與就也都又還把被給讓從向對而且")
EDGE_TAIL = set("了的著一是在把被給和與從向對而且就也都又還個")


def frequent_phrases(paras, top=12, exclude=()):
    """出現 3 次以上的 2～4 字詞組（去掉被更長詞組涵蓋的），可以看出口頭禪與慣用語。"""
    cnt = Counter()
    for p in paras:
        for chunk in re.findall(r"[一-鿿]+", p):
            for n in (2, 3, 4):
                for i in range(len(chunk) - n + 1):
                    cnt[chunk[i:i + n]] += 1
    stop = set("一個 不是 什麼 沒有 自己 知道 他們 我們 你們 她們 這個 那個 這樣 那樣 已經 還是 就是 一下 起來 出來 過來 下來 時候 一樣 可以 因為 所以 如果 但是 然後".split())
    ex = [e for e in exclude if e]
    cand = [(w, c) for w, c in cnt.items() if c >= 3 and w not in stop and not re.fullmatch(r"(.)\1+", w)
            and w[0] not in EDGE_HEAD and w[-1] not in EDGE_TAIL
            and not any(e in w or w in e for e in ex)]
    cand.sort(key=lambda x: (-x[1] * (len(x[0]) ** 1.3), x[0]))
    out = []
    for w, c in cand:
        if any(w in o for o, _ in out) or any(o in w and cnt[o] <= c + 1 for o, _ in out):
            continue
        out.append((w, c))
        if len(out) >= top:
            break
    return ["%s×%d" % (w, c) for w, c in out]


def metrics_md(m):
    rows = ["| 指標 | 數值 | 說明 |", "|---|---|---|"]
    for k, v in m.items():
        note = METRIC_NOTES.get(k, "")
        if k.startswith("每千字") and not note:
            note = "每一千個中文字出現幾次"
        rows.append("| %s | %s | %s |" % (k, v, note))
    return (METRICS_HEAD + "\n<!-- 由程式從範例文字統計，AI 寫稿時會參考這些數字。重新統計會覆蓋這一節。 -->\n"
            + "\n".join(rows) + "\n")


def main(argv):
    exclude, files = [], []
    it = iter(argv)
    for a in it:
        if a == "--exclude":
            exclude = [x.strip() for x in next(it, "").split(",") if x.strip()]
        else:
            files.append(a)
    if not files:
        print(__doc__)
        return 1
    text = "\n\n".join(open(f, encoding="utf-8").read() for f in files)
    try:
        print(metrics_md(analyze(text, exclude)))
    except SampleTooShort as e:
        print(str(e))
        return 2
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
