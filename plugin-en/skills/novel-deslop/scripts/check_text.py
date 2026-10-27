#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fiction text checker (English).

Checks:
  1. Quote and punctuation consistency (mixed straight/curly quotes, "--", "...")  -> 必須修 (auto-fix with --fix-punct)
  2. Engineering words leaking into prose (chapter, foreshadowing, outline ...)    -> 建議修
  3. AI-tell density (stock phrases, structures, reflective chapter endings)       -> 提醒; piled up in one chapter -> 建議修
  4. Rhythm: burst of short sentences, uniform length, em-dash density, name cycling -> 提醒 / 建議修
  5. Word count

Same command line and result shape as the Chinese checker, so the workbench can swap them.
Level names (必須修/建議修/提醒) and JSON keys are fixed tokens shared by every language.

Usage:
  python3 check_text.py 正文/第001章_Title.md
  python3 check_text.py 正文/
  python3 check_text.py 正文/第001章_Title.md --fix-punct
  python3 check_text.py 正文/第001章_Title.md --json
  python3 check_text.py 正文/第001章_Title.md --count

Whitelist: `.去AI味白名單` in the book folder, one fragment per line, `#` for comments.
Lines containing a whitelisted fragment skip the wording and AI-tell checks (punctuation still checked).

Standard library only, Python 3.8+.
Exit code: 0 = nothing to fix, 1 = items marked 必須修, 2 = bad arguments or files.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# AI tells: (category, regex)  — matched case-insensitively
# ---------------------------------------------------------------------------
AI_SIGNALS = [
    ("negation flip", r"\b(?:it|this|that|he|she|they|i|we)\s+(?:wasn't|weren't|isn't|aren't|was\s+not|were\s+not|is\s+not|are\s+not)\s+[^.,;!?\n]{1,40}[,.;]\s*(?:but\s+|it\s+was|he\s+was|she\s+was|they\s+were|it's|he's|she's)"),
    ("negation flip", r"\b(?:wasn't|weren't|isn't|aren't|not)\s+[^.,;!?\n]{1,30}\bbut\s+(?:rather\s+)?"),
    ("negation flip", r"\bnot\s+(?:just|merely|only)\s+[^.,;!?\n]{1,40}\bbut\b"),
    ("stock expression", r"\b(?:a\s+)?(?:small|faint|slight|ghost\s+of\s+a|tiny)\s+smile\s+(?:tugged|played|touched|curved)|\bsmile\s+tugged\b|\btugged\s+at\s+the\s+corner"),
    ("stock expression", r"\bsomething\s+(?:flickered|flashed|shifted|passed)\s+(?:in|across|behind)\s+(?:his|her|their)\s+(?:eyes|face|expression)"),
    ("stock expression", r"\b(?:jaw|muscle)\s+(?:tightened|clenched|ticked|jumped|worked)|\bknuckles\s+(?:went\s+|turned\s+)?white|\beyes\s+(?:widened|narrowed)\s+(?:slightly|a\s+fraction)"),
    ("stock expression", r"\bbreath\s+(?:she|he|they|i)\s+(?:hadn't|had\s+not|didn't|did\s+not)\s+(?:known|realized|realised)"),
    ("stock expression", r"\bwith\s+a\s+(?:hint|flicker|ghost|trace|touch|note|edge)\s+of\b"),
    ("body cliche", r"\bshiver\s+(?:ran|went|crept|raced|danced)\s+(?:down|up|along)|\bsend(?:s|ing)?\s+shivers?\b|\bheart\s+(?:hammered|pounded|raced|thundered|skipped)|\bstomach\s+(?:dropped|lurched|churned|knotted|twisted)|\bair\s+(?:left|rushed\s+out\s+of)\s+(?:her|his|their)\s+lungs|\bice\s+(?:pooled|flooded|ran)\b"),
    ("telling emotion", r"\b(?:felt|feeling)\s+(?:a\s+)?(?:surge|wave|rush|pang|stab|flicker|twinge|swell|flood)\s+of\b|\b(?:wave|surge|rush|pang)\s+of\s+(?:relief|grief|guilt|fear|anger|sadness|despair|panic|longing)"),
    ("telling emotion", r"\b(?:he|she|i|they)\s+(?:realized|realised|understood|knew)\s*,?\s+(?:then|suddenly|now)?\s*,?\s*(?:that\s+)?(?:how|just\s+how|what|that)\b"),
    ("explaining subtext", r"\bwhich\s+was\s+(?:her|his|their|its)\s+way\s+of\b|\bthe\s+silence\s+(?:said|spoke|told)\b|\bsaid\s+(?:more|everything|volumes)\b|\bspoke\s+volumes\b"),
    ("aphorism", r"\bsome\s+(?:things|doors|wounds|journeys|battles|truths)\b[^.]{1,60}\b(?:never|always|only|cannot|can't)\b|\bgrief\s+is\s+(?:just\s+)?love\b|\bthe\s+only\s+way\s+(?:out|through)\s+is\b"),
    ("prophetic ending", r"\bwhatever\s+(?:came|lay|lies)\s+next\b|\blittle\s+did\s+(?:he|she|they|i)\s+know\b|\bit\s+was\s+only\s+the\s+beginning\b|\bthe\s+(?:real\s+)?(?:storm|trouble|battle|fight)\s+(?:was\s+)?(?:only\s+)?(?:just\s+)?(?:beginning|ahead)\b|\bnothing\s+would\s+(?:ever\s+)?be\s+the\s+same\b|\bfor\s+the\s+first\s+time\s+in\s+(?:years|a\s+long\s+time)\b"),
    ("significance inflation", r"\beverything\s+had\s+changed\b|\bthis\s+was\s+(?:the\s+moment|it)\b|\bit\s+was\s+more\s+than\s+(?:just\s+)?an?\s+\w+;?\s*it\s+was\b|\bthe\s+weight\s+of\s+(?:the|it|everything|what)\b"),
    ("filler adverb", r"\b(?:slowly|softly|quietly|gently|suddenly|simply|somehow|barely|almost|faintly|slightly)\b"),
    ("hedge", r"\b(?:seemed|appeared)\s+to\b|\ba\s+(?:little|bit)\b|\bsort\s+of\b|\bkind\s+of\b|\bsomething\s+like\b"),
    ("stock simile", r"\blike\s+a\s+(?:physical\s+)?(?:blow|punch|slap|ton\s+of\s+bricks)|\bthick\s+enough\s+to\s+cut\b|\ba\s+storm\s+(?:was\s+)?brewing\b|\btime\s+(?:seemed\s+to\s+)?(?:slow|stop|stand\s+still)|\ba\s+symphony\s+of\b|\bdance\s+of\b"),
    ("dialogue tag", r"\b(?:voice|tone)\s+(?:barely\s+above|little\s+more\s+than)\s+a\s+whisper|\bvoice\s+laced\s+with\b|\b(?:murmured|whispered|breathed)\s*[.,]?\s*(?=\W)"),
    ("canned reaction", r"\b(?:she|he|they|i)\s+(?:froze|stilled)\b|\bsilence\s+(?:stretched|hung|settled|fell)\b|\bfor\s+a\s+(?:long\s+)?(?:moment|beat|heartbeat),?\s+(?:neither|no\s+one|nobody)\b|\bthe\s+room\s+(?:went|fell|grew)\s+(?:still|silent|quiet)\b|\btension\s+(?:crackled|hung|filled)\b"),
    ("official register", r"\b(?:furthermore|moreover|in\s+essence|ultimately|a\s+testament\s+to|tapestry|delve|myriad|palpable|navigate\s+(?:the|her|his)\s+(?:grief|pain|loss|world))\b"),
    ("stock name", r"\b(?:Elara|Kael|Lyra|Thorne|Seraphina|Aria\s+Blackwood|Sarah\s+Chen|Marcus)\b"),
]

CATEGORY_LIMIT = {
    "filler adverb": 12, "hedge": 8, "stock expression": 3, "body cliche": 2,
    "telling emotion": 2, "negation flip": 3, "explaining subtext": 2,
    "aphorism": 2, "prophetic ending": 1, "significance inflation": 2,
    "stock simile": 3, "dialogue tag": 4, "canned reaction": 3,
    "official register": 3, "stock name": 1,
}

CATEGORY_HINT = {
    "negation flip": "state the real thing; give one concrete reason",
    "stock expression": "keep one action that moves the scene",
    "body cliche": "use only if surprising for this character, once",
    "telling emotion": "show it through an action, object or avoidance",
    "explaining subtext": "let the reader infer; fix the beat if they can't",
    "aphorism": "cut, or make it this character's own speech",
    "prophetic ending": "end on an image, action or dialogue",
    "significance inflation": "let the events carry the weight",
    "filler adverb": "cut where the verb already says it",
    "hedge": "commit to the statement unless vagueness is the point",
    "stock simile": "use a comparison from this viewpoint character's own life",
    "dialogue tag": "use 'said' and put the manner in an action beat",
    "canned reaction": "cut, or replace with what the character does",
    "official register": "use the plain word a person in this scene would use",
    "stock name": "pick a name that belongs to this book's world",
}

# Rhythm and density
BURST_LEN, BURST_RUN = 4, 4          # 4+ sentences in a row, each at most 4 words
UNIFORM_RUN, UNIFORM_SPREAD, UNIFORM_MIN = 6, 0.2, 8   # 6 sentences within 20% of the mean (mean >= 8 words)
DASH_PER = 200                       # more than one em dash per 200 words of narration
ALIAS_FORMS = 4
PHRASE_REPEAT = 3
DIALOGUE = re.compile(r'"[^"]*"|“[^”]*”')

ENGINEERING_WORDS = r"\b(?:Chapter\s+\d+|previous\s+chapter|next\s+chapter|this\s+chapter|foreshadowing|chapter\s+outline|story\s+outline|the\s+reader\s+(?:will|should))\b"

WORD = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
SENT_SPLIT = re.compile(r"(?<=[.!?])[\"'”’)]*\s+|…\s+")
STOP_ALIAS = set()


def _wlen(s):
    return len(WORD.findall(s))


def load_whitelist(book_root):
    items = []
    if not book_root:
        return items
    path = os.path.join(book_root, ".去AI味白名單")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.strip() and not line.lstrip().startswith("#"):
                    items.append(line.strip())
    return items


def parse_banned(text, source=""):
    """Read the '## 禁用詞' section: lines '- word -> hint'; /.../ is a regex. Returns [(regex, shown, hint)]."""
    out = []
    m = re.search(r"(?ms)^##+\s*禁用詞[^\n]*\n(.*?)(?=^##\s|\Z)", text or "")
    if not m:
        return out
    sec = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S)
    for line in sec.split("\n"):
        s = line.strip()
        if not s.startswith(("-", "*")):
            continue
        s = s[1:].strip()
        if not s:
            continue
        parts = re.split(r"\s*(?:→|->)\s*", s, maxsplit=1)
        word, hint = parts[0], (parts[1] if len(parts) > 1 else "")
        word = word.strip().strip("「」\"'")
        if not word:
            continue
        if len(word) > 2 and word.startswith("/") and word.endswith("/"):
            try:
                rx = re.compile(word[1:-1], re.I)
            except re.error:
                continue
            show = word[1:-1]
        else:
            rx = re.compile(r"\b" + re.escape(word) + r"\b", re.I)
            show = word
        out.append((rx, show, (hint.strip() or "banned by the author") + (" (%s)" % source if source else "")))
    return out


def load_banned(book_root):
    items = []
    if not book_root:
        return items
    for path, src in ((os.path.join(book_root, "設定", "作者偏好.md"), "book preferences"),
                      (os.path.join(os.path.dirname(os.path.abspath(book_root)), "_共用", "作者偏好.md"), "shared preferences")):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                items += parse_banned(f.read(), src)
    return items


def load_aliases(book_root):
    """Names and aliases from 設定/角色/*.md frontmatter. Returns {name: [name, aliases...]}."""
    out = {}
    d = os.path.join(book_root or "", "設定", "角色")
    if not book_root or not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not f.endswith(".md"):
            continue
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                text = fh.read(3000)
        except OSError:
            continue
        m = re.match(r"---\n(.*?)\n---", text, re.S)
        fm = m.group(1) if m else ""
        name = (re.search(r"(?m)^名稱:\s*(.+)$", fm) or [None, os.path.splitext(f)[0]])[1].strip()
        al = []
        am = re.search(r"(?m)^別名:\s*\[(.*)\]\s*$", fm)
        if am:
            al = [x.strip().strip("'\"") for x in am.group(1).split(",")]
        else:
            bm = re.search(r"(?ms)^別名:\s*\n((?:\s*-\s*.+\n?)+)", fm)
            if bm:
                al = [x.strip()[1:].strip().strip("'\"") for x in bm.group(1).strip().split("\n")]
        forms = [x for x in dict.fromkeys([name] + al) if x and len(x) >= 2]
        if len(forms) >= 2:
            out[name] = forms
    return out


def rhythm_findings(body_lines, aliases):
    """body_lines: [(line_no, text)] without headings and comments. Returns [(level, kind, line, snippet, hint)]."""
    out = []
    sents = []          # (line_no, narration sentence); dialogue-only lines are (line_no, None) = interruption
    narr_text = []
    for ln, line in body_lines:
        s = line.strip()
        narr = DIALOGUE.sub("", s)
        narr_text.append(narr)
        if s[:1] in ('"', "“") and _wlen(narr) < 3:
            sents.append((ln, None))
            continue
        for x in SENT_SPLIT.split(narr):
            if _wlen(x):
                sents.append((ln, x))
    run, bursts = [], []
    for ln, x in sents + [(0, None)]:
        if x is not None and _wlen(x) <= BURST_LEN:
            run.append((ln, x))
            continue
        if len(run) >= BURST_RUN:
            bursts.append(run)
        run = []
    if bursts:
        out.append(("提醒", "rhythm: burst of fragments", bursts[0][0][0],
                    "%d place(s), lines %s (e.g. %s)" % (len(bursts), ", ".join(str(b[0][0]) for b in bursts[:8]),
                                                       " ".join(x.strip() for _, x in bursts[0][:5])[:50]),
                    "fragments in a row fake tension; keep the strongest one or two and fold the rest into full sentences (ignore if the style allows it)"))
    ns = [(ln, _wlen(x)) for ln, x in sents if x is not None]
    i, hits = 0, []
    while i + UNIFORM_RUN <= len(ns):
        w = [n for _, n in ns[i:i + UNIFORM_RUN]]
        mean = sum(w) / len(w)
        if mean >= UNIFORM_MIN and (max(w) - min(w)) <= mean * UNIFORM_SPREAD:
            hits.append(ns[i][0])
            i += UNIFORM_RUN
        else:
            i += 1
    if hits:
        out.append(("提醒", "rhythm: uniform sentence length", hits[0], "%d place(s), lines %s" % (len(hits), ", ".join(str(x) for x in hits[:8])),
                    "several sentences of near-equal length read as machine-made; mix long and short"))
    narr_all = "\n".join(narr_text)
    n_words = _wlen(narr_all)
    dashes = len(re.findall("—|--", narr_all))
    if n_words >= 600 and dashes > n_words / DASH_PER:
        out.append(("建議修", "rhythm: too many em dashes", 0, "%d in narration (about one per %d words)" % (dashes, n_words // max(dashes, 1)),
                    "at most about one em dash per %d words of narration; most can be commas, periods or a split sentence" % DASH_PER))
    full = "\n".join(l for _, l in body_lines)
    for name, forms in (aliases or {}).items():
        used = []
        rest = full
        for f in sorted(forms, key=len, reverse=True):
            c = len(re.findall(r"\b" + re.escape(f) + r"\b", rest))
            if c:
                rest = re.sub(r"\b" + re.escape(f) + r"\b", "\0", rest)
            if c >= 2:
                used.append("%s x%d" % (f, c))
        if len(used) >= ALIAS_FORMS:
            out.append(("提醒", "rhythm: too many labels for one character", 0, "%s: %s" % (name, ", ".join(used)),
                        "too many labels make readers wonder if it is the same person; settle on one or two and use pronouns"))
    return out


def guess_book_root(path):
    p = os.path.abspath(path)
    d = p if os.path.isdir(p) else os.path.dirname(p)
    while True:
        if os.path.basename(d) == "正文":
            return os.path.dirname(d)
        if os.path.isfile(os.path.join(d, "CLAUDE.md")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def strip_frontmatter(lines):
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return i + 1
    return 0


def count_chars(text):
    """Returns (words, characters without whitespace). The first slot keeps its old name's position."""
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    words = len(re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", body))
    no_space = len(re.sub(r"\s", "", body))
    return words, no_space


def fix_punct(text):
    n = 0

    def sub(pattern, repl, s, flags=0):
        nonlocal n
        s2, k = re.subn(pattern, repl, s, flags=flags)
        n += k
        return s2

    text = sub(r"(?<=\w)\s?--\s?(?=\w)", "—", text)
    text = sub(r"\.{3,}", "…", text)
    # mixed quote styles: if curly double quotes are present, turn straight ones into curly pairs
    if "“" in text or "”" in text:
        out = []
        for line in text.split("\n"):
            if '"' in line:
                parts = line.split('"')
                rebuilt = parts[0]
                for k, p in enumerate(parts[1:]):
                    rebuilt += ("“" if k % 2 == 0 else "”") + p
                    n += 1
                line = rebuilt
            out.append(line)
        text = "\n".join(out)
    if "’" in text:
        text = sub(r"(?<=[A-Za-z])'(?=[A-Za-z])", "’", text)
    return text, n


def punct_findings(lines, start):
    """Mixed quote styles, stray '--', '...'. Returns [(line_no, snippet, hint)]."""
    body = "\n".join(lines[start:])
    out = []
    has_curly = "“" in body or "”" in body
    has_straight = '"' in body
    if has_curly and has_straight:
        for i in range(start, len(lines)):
            if '"' in lines[i]:
                out.append((i + 1, lines[i].strip()[:40], "mixed straight and curly quotes; pick one (--fix-punct converts to curly)"))
                break
    for i in range(start, len(lines)):
        m = re.search(r"(?<=\w)\s?--\s?(?=\w)", lines[i])
        if m:
            out.append((i + 1, lines[i].strip()[:40], "use an em dash instead of '--'"))
            break
    for i in range(start, len(lines)):
        if re.search(r"\.{3,}", lines[i]) and "…" in body:
            out.append((i + 1, lines[i].strip()[:40], "'...' and the ellipsis character are mixed; pick one"))
            break
    return out


def check_file(path, whitelist, banned=None, aliases=None):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if banned is None:
        banned = load_banned(guess_book_root(path))
    if aliases is None:
        aliases = load_aliases(guess_book_root(path))
    lines = text.split("\n")
    start = strip_frontmatter(lines)
    findings = []
    cat_counter = Counter()
    cat_lines = defaultdict(list)
    phrase_counter = Counter()

    def add(level, kind, lineno, snippet, hint):
        findings.append({"等級": level, "類型": kind, "行": lineno, "片段": snippet, "建議": hint})

    for ln, snip, hint in punct_findings(lines, start):
        add("必須修", "punctuation", ln, snip, hint)

    for idx in range(start, len(lines)):
        line = lines[idx]
        lineno = idx + 1
        if not line.strip():
            continue
        whitelisted = any(w.lower() in line.lower() for w in whitelist)
        if whitelisted:
            continue
        for m in re.finditer(ENGINEERING_WORDS, line, re.I):
            add("建議修", "engineering word", lineno, m.group(0),
                "prose should not contain writing-process words; ignore if it exists inside the story")
        for rx, show, hint in banned:
            for m in rx.finditer(line):
                add("建議修", "banned word", lineno, m.group(0), hint)
        if line.lstrip().startswith("#"):
            continue
        for cat, pat in AI_SIGNALS:
            for m in re.finditer(pat, line, re.I):
                cat_counter[cat] += 1
                cat_lines[cat].append(lineno)
                if cat not in ("filler adverb", "hedge"):
                    phrase_counter[m.group(0).lower().strip()] += 1

    for cat, cnt in cat_counter.items():
        limit = CATEGORY_LIMIT.get(cat, 3)
        level = "建議修" if cnt >= limit else "提醒"
        add(level, "AI tell: " + cat, cat_lines[cat][0],
            "%d time(s), at lines %s" % (cnt, ", ".join(str(x) for x in cat_lines[cat][:10])),
            CATEGORY_HINT.get(cat, "judge in context; when they pile up, use a concrete action or cut (see ai-signals.md)"))
    for phrase, cnt in phrase_counter.items():
        if cnt >= PHRASE_REPEAT and len(phrase) >= 4:
            add("建議修", "repeated phrase", 0, "\"%s\" x%d" % (phrase, cnt), "repeated too often in one chapter; keep the strongest")

    body_lines = [(i + 1, l) for i, l in enumerate(lines[start:], start=start)
                  if l.strip() and not l.lstrip().startswith("#") and not l.strip().startswith("<!--")]
    if body_lines:
        last_no, last = body_lines[-1]
        if re.search(r"whatever\s+(?:came|lay)\s+next|little\s+did|only\s+the\s+beginning|nothing\s+would\s+(?:ever\s+)?be\s+the\s+same|for\s+the\s+first\s+time\s+in\s+(?:years|a\s+long\s+time)|she\s+(?:knew|realized)\s+(?:that\s+)?(?:she|this)|he\s+(?:knew|realized)\s+(?:that\s+)?(?:he|this)|new\s+chapter", last, re.I) \
                and not any(w.lower() in last.lower() for w in whitelist):
            add("建議修", "reflective ending", last_no, last.strip()[:50],
                "end on a concrete image, action or dialogue, not a lesson or a forecast")
        wl_free = [(n, l) for n, l in body_lines if not any(w.lower() in l.lower() for w in whitelist)]
        for level, kind, ln, snip, hint in rhythm_findings(wl_free, aliases):
            add(level, kind, ln, snip, hint)

    words, no_space = count_chars("\n".join(lines[start:]))
    order = {"必須修": 0, "建議修": 1, "提醒": 2}
    findings.sort(key=lambda x: (order[x["等級"]], x["行"]))
    return {"檔案": path, "中文字數": words, "總字數（不含空白）": no_space, "問題": findings}


def collect(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if name.endswith((".md", ".txt")):
                    files.append(os.path.join(p, name))
        elif os.path.isfile(p):
            files.append(p)
        else:
            print("not found: %s" % p, file=sys.stderr)
            sys.exit(2)
    return files


def print_report(res):
    print("=" * 60)
    print("%s" % res["檔案"])
    print("Words: %d   Characters (no whitespace): %d" % (res["中文字數"], res["總字數（不含空白）"]))
    if not res["問題"]:
        print("No problems found.")
        return
    groups = defaultdict(list)
    for f in res["問題"]:
        groups[f["等級"]].append(f)
    for level in ("必須修", "建議修", "提醒"):
        if not groups[level]:
            continue
        print("\n[%s] %d item(s)" % (level, len(groups[level])))
        for f in groups[level]:
            where = ("line %d" % f["行"]) if f["行"] else "whole chapter"
            print("  - %s | %s | %s -> %s" % (where, f["類型"], f["片段"], f["建議"]))


def main():
    ap = argparse.ArgumentParser(description="Fiction text checker (English)")
    ap.add_argument("paths", nargs="+", help="chapter files or folders")
    ap.add_argument("--fix-punct", action="store_true", help="fix punctuation in place")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--count", action="store_true", help="word count only")
    ap.add_argument("--book-root", help="book folder (default: the parent of 正文/)")
    args = ap.parse_args()

    files = collect(args.paths)
    if not files:
        print("no .md or .txt files to check", file=sys.stderr)
        sys.exit(2)

    if args.count:
        for p in files:
            with open(p, encoding="utf-8") as f:
                lines = f.read().split("\n")
            w, ns = count_chars("\n".join(lines[strip_frontmatter(lines):]))
            print("%s\twords %d\tcharacters %d" % (p, w, ns))
        return

    if args.fix_punct:
        for p in files:
            with open(p, encoding="utf-8") as f:
                text = f.read()
            new, n = fix_punct(text)
            if n:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(new)
            print("%s: fixed %d punctuation spot(s)" % (p, n))

    book_root = args.book_root or guess_book_root(files[0])
    whitelist = load_whitelist(book_root)
    results = [check_file(p, whitelist) for p in files]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print_report(r)
        must = sum(1 for r in results for f in r["問題"] if f["等級"] == "必須修")
        print("\n" + "=" * 60)
        print("Total: %d item(s) to fix.%s" % (must, " Fix those first." if must else ""))

    if any(f["等級"] == "必須修" for r in results for f in r["問題"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
