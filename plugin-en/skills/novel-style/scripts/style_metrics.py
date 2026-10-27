# -*- coding: utf-8 -*-
"""
Style metrics for English prose (local statistics, no AI).

Usage:
  python style_metrics.py sample.md [more files...] [--exclude Ines,Callum]

Prints a Markdown table to paste under "## 文字指標（程式統計）" in the style note.
--exclude: words (character and place names) to leave out of "高頻詞組".
The workbench also loads this file to compute style metrics. Same API and the same
(Chinese) metric keys as the Chinese version, so the rest of the workbench needs no changes.
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


WORD = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
SENT_SPLIT = re.compile(r"(?<=[.!?])[\"'”’)]*\s+|…[\"'”’)]*\s+")
QUOTE = re.compile(r'"([^"]*)"|“([^”]*)”')
PUNCT_KEYS = [("逗號", ","), ("頓號", ";"), ("驚嘆號", "!"), ("問號", "?"), ("刪節號", "…"), ("破折號", "—")]
METRIC_NOTES = {
    "樣本字數": "words",
    "平均句長": "words; shorter = faster pace",
    "短句比例": "sentences of 6 words or fewer",
    "長句比例": "sentences of 25 words or more",
    "平均段長": "words",
    "單句成段": "share of paragraphs with a single sentence",
    "對白比例": "share of words inside quotation marks",
    "對白段比例": "share of paragraphs containing dialogue",
    "每千字逗號": "per 1,000 words: commas",
    "每千字頓號": "per 1,000 words: semicolons",
    "每千字驚嘆號": "per 1,000 words: exclamation marks",
    "每千字問號": "per 1,000 words: question marks",
    "每千字刪節號": "per 1,000 words: ellipses",
    "每千字破折號": "per 1,000 words: em dashes (also counts '--')",
    "每千字的": "per 1,000 words: -ly adverbs; higher = more modifiers",
    "每千字地": "per 1,000 words: 'seemed/appeared to' and 'a bit/a little' hedges",
    "每千字AI味信號": "common AI-tell phrases found by the checker",
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
    return [re.sub(r"\s+", " ", p) for p in paras]


def _ai_signals():
    """Borrow the AI-tell list from the sibling novel-deslop checker (skipped if it cannot be loaded)."""
    try:
        import importlib.util
        p = os.path.join(HERE, "..", "..", "novel-deslop", "scripts", "check_text.py")
        spec = importlib.util.spec_from_file_location("check_text_for_metrics_en", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return [pat for cat, pat in mod.AI_SIGNALS if cat not in ("filler adverb", "hedge")]
    except Exception:
        return []


_AI = None


def _wc(s):
    return len(WORD.findall(s))


def analyze(text, exclude=()):
    """Ordered dict of metrics. exclude: names to keep out of the frequent phrases."""
    global _AI
    if _AI is None:
        _AI = _ai_signals()
    body = _prose(text)
    paras = _paragraphs(body)
    joined = "\n".join(paras)
    total = _wc(joined)
    if total < 150:
        raise SampleTooShort("Sample too short (%d words). Use at least 150 words, ideally 1,500+, for the numbers to mean anything." % total)
    sents = []
    for p in paras:
        for s in SENT_SPLIT.split(p):
            if _wc(s):
                sents.append(s)
    slen = [_wc(s) for s in sents]
    plen = [_wc(p) for p in paras if _wc(p)]
    dlg = sum(_wc(a or b) for a, b in QUOTE.findall(joined))
    k = 1000.0 / total
    m = {"樣本字數": total,
         "平均句長": round(sum(slen) / len(slen), 1) if slen else 0,
         "短句比例": "%d%%" % round(100.0 * sum(1 for n in slen if n <= 6) / max(1, len(slen))),
         "長句比例": "%d%%" % round(100.0 * sum(1 for n in slen if n >= 25) / max(1, len(slen))),
         "平均段長": round(sum(plen) / len(plen), 1) if plen else 0,
         "單句成段": "%d%%" % round(100.0 * sum(1 for p in paras if len(SENT_SPLIT.split(p.strip())) <= 1) / max(1, len(paras))),
         "對白比例": "%d%%" % round(100.0 * dlg / total),
         "對白段比例": "%d%%" % round(100.0 * sum(1 for p in paras if '"' in p or "“" in p) / max(1, len(paras)))}
    for label, ch in PUNCT_KEYS:
        n = joined.count(ch)
        if ch == "…":
            n += len(re.findall(r"\.{3}", joined))
        if ch == "—":
            n += joined.count("--")
        m["每千字" + label] = round(n * k, 1)
    m["每千字的"] = round(len(re.findall(r"\b\w+ly\b", joined, re.I)) * k, 1)
    m["每千字地"] = round(len(re.findall(r"\b(?:seemed|appeared)\s+to\b|\ba\s+(?:little|bit)\b|\bsort\s+of\b|\bkind\s+of\b", joined, re.I)) * k, 1)
    m["每千字AI味信號"] = round(sum(len(re.findall(p, joined, re.I)) for p in _AI) * k, 1)
    m["高頻詞組"] = ", ".join(frequent_phrases(paras, exclude=exclude)) or "(no notably repeated phrases)"
    return m


STOP = set("the a an and or but of to in on at for with from by as is was were are be been it its he she they them his her their i you we me my your our this that these those there then than so not no do did does had has have would could should will can just very into out up down over under about after before again back too also only more most some any all one two".split())


def frequent_phrases(paras, top=12, exclude=()):
    """2-4 word phrases used 3+ times (those inside a longer phrase are dropped): shows tics and habits."""
    cnt = Counter()
    ex = [e.lower() for e in exclude if e]
    for p in paras:
        for sent in SENT_SPLIT.split(p):
            ws = [w.lower().replace("’", "'") for w in WORD.findall(sent)]
            for n in (2, 3, 4):
                for i in range(len(ws) - n + 1):
                    g = ws[i:i + n]
                    if g[0] in STOP or g[-1] in STOP:
                        continue
                    cnt[" ".join(g)] += 1
    cand = [(w, c) for w, c in cnt.items() if c >= 3 and not any(e in w for e in ex)]
    cand.sort(key=lambda x: (-x[1] * (len(x[0].split()) ** 1.3), x[0]))
    out = []
    for w, c in cand:
        if any(w in o for o, _ in out) or any(o in w and cnt[o] <= c + 1 for o, _ in out):
            continue
        out.append((w, c))
        if len(out) >= top:
            break
    return ["%s x%d" % (w, c) for w, c in out]


def metrics_md(m):
    rows = ["| 指標 | 數值 | 說明 |", "|---|---|---|"]
    for k, v in m.items():
        rows.append("| %s | %s | %s |" % (k, v, METRIC_NOTES.get(k, "")))
    return (METRICS_HEAD + "\n<!-- Computed by a program from the sample text; the drafting AI uses these numbers. Re-running overwrites this section. -->\n"
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
