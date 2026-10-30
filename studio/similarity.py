# -*- coding: utf-8 -*-
"""相似度：判斷「這段新寫的東西」和「來源書」有多像。

用在兩件事：
  1. P6 的護欄：由 A 書生 B 書時，B 的稿子不能和 A 撞太多（字元 6-gram、最長共同片段、角色名）。
  2. 量基準：先知道「兩本無關的書」之間本來有多像，門檻才不是憑感覺定的。

全部本機計算，不呼叫模型。
"""
import hashlib
import re

CJK = re.compile(r"[\u3400-\u9fff\u3040-\u30ff]")
WORD = re.compile(r"[A-Za-z]+")
# 正規化時只留「文字」：標點、空白、數字都不算，避免排版差異影響比對
KEEP = re.compile(r"[\u3400-\u9fff\u3040-\u30ffA-Za-z]")

M61 = (1 << 61) - 1
BASE = 1000003


def normalize(text):
    """只留中英日文字，其餘（標點、空白、數字）去掉；英文轉小寫。"""
    return "".join(KEEP.findall((text or "").lower()))


def ngrams(text, n=6):
    s = normalize(text)
    return {s[i:i + n] for i in range(len(s) - n + 1)} if len(s) >= n else set()


def jaccard(a, b, n=6):
    """字元 n-gram 的 Jaccard（0＝完全不同，1＝完全一樣）。"""
    A, B = ngrams(a, n), ngrams(b, n)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def _hash(s, lo, L):
    h = 0
    for i in range(lo, lo + L):
        h = (h * BASE + ord(s[i])) % M61
    return h


def _found(A, B, L, weights):
    """B（長字串）裡有沒有長度 L 的片段也出現在 A（要檢查的稿子）裡；有就回傳位置。"""
    if L <= 0:
        return True, "", 0
    w = weights[L]
    seen = {}
    h = _hash(B, 0, L)
    seen[h] = 0
    for i in range(1, len(B) - L + 1):
        h = ((h - ord(B[i - 1]) * w) * BASE + ord(B[i + L - 1])) % M61
        seen.setdefault(h, i)
    h = _hash(A, 0, L)
    for i in range(0, max(1, len(A) - L + 1)):
        if i:
            h = ((h - ord(A[i - 1]) * w) * BASE + ord(A[i + L - 1])) % M61
        j = seen.get(h)
        if j is not None:
            piece = A[i:i + L]
            if B[j:j + L] == piece:        # 逐字驗證，排除雜湊碰撞
                return True, piece, i
    return False, "", 0


def common_span(a, b, floor=20):
    """最長共同片段：回傳 (長度, 片段, 在 b 裡的起點)。

    b 是「要檢查的稿子」、a 是「來源」。沒有超過 floor 就回 (0, "", -1)。
    """
    A, B = normalize(a), normalize(b)
    if len(A) < floor or len(B) < floor:
        return 0, "", -1
    weights = {1: 1}
    for L in range(2, min(len(A), len(B)) + 1):
        weights[L] = (weights[L - 1] * BASE) % M61
    lo, hi, best = floor, min(len(A), len(B)), (0, "", -1)
    while lo <= hi:
        mid = (lo + hi) // 2
        ok, piece, idx = _found(A, B, mid, weights)
        if ok:
            best = (mid, piece, idx)
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def longest_common(a, b, floor=20):
    """最長共同片段（字元數）。"""
    return common_span(a, b, floor)[0]


def fingerprint(text, n=6):
    """給定一段文字，回傳可比較的指紋（供集合運算；大量比較時比逐次算快）。"""
    s = normalize(text)
    grams = {s[i:i + n] for i in range(len(s) - n + 1)} if len(s) >= n else set()
    return {"len": len(s), "grams": grams,
            "digest": hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]}


def compare_prints(p, q):
    if not p["grams"] or not q["grams"]:
        return {"jaccard": 0.0, "containment": 0.0, "chars": q["len"]}
    inter = len(p["grams"] & q["grams"])
    return {"jaccard": inter / len(p["grams"] | q["grams"]),
            "containment": inter / len(q["grams"]),      # q 有多少比例在 p 裡
            "chars": q["len"]}


def names_in(text, names):
    """文字裡出現了哪些名字（來源書的角色／地名）。"""
    return sorted({n for n in names if n and n in text})


# ---------------------------------------------------------------------------
# 護欄：檢查一份新稿和來源書有多像，並指出「哪一段」
# ---------------------------------------------------------------------------
# 實測的自然重複（同作者、後半對前半）：zh 0.034／0 字、ja 0.081／0 字、en 0.347／33 字
LIMITS = {
    "zh-TW": {"containment": 0.10, "lcs": 20},
    "ja": {"containment": 0.20, "lcs": 20},
    "en": {"containment": 0.50, "lcs": 60},
}
PARA_HIT = 0.50      # 單一段落有這麼高的比例來自來源 → 標記那一段


def paragraph_hits(new_text, fp_source, threshold=PARA_HIT):
    """逐段比對：哪幾段幾乎全來自來源（比整篇的總分更好定位）。"""
    out = []
    for i, para in enumerate([p.strip() for p in new_text.split("\n") if p.strip()], 1):
        if len(normalize(para)) < 40:
            continue
        r = compare_prints(fp_source, fingerprint(para))
        if r["containment"] >= threshold:
            out.append({"paragraph": i, "containment": round(r["containment"], 3),
                        "preview": para[:60]})
    return out


def raw_span(raw_text, piece):
    """把正規化後的共同片段對回原文（含標點空白），給人看得懂。"""
    if not piece:
        return ""
    idx, pos = [], []
    for i, ch in enumerate(raw_text):
        if KEEP.match(ch):
            idx.append(i)
            pos.append(ch.lower())
    norm = "".join(pos)
    at = norm.find(piece.lower())
    if at < 0:
        return piece
    return raw_text[idx[at]: idx[min(at + len(piece) - 1, len(idx) - 1)] + 1]


def check(new_text, source_text, lang="zh-TW", names=(), limits=None):
    """回傳 {ok, reasons, metrics, span, paragraphs}。ok=False 代表太像了。"""
    lim = (limits or LIMITS).get(lang, LIMITS["zh-TW"])
    fp_source = fingerprint(source_text)
    fp_new = fingerprint(new_text)
    r = compare_prints(fp_source, fp_new)
    length, piece, idx = common_span(source_text, new_text, floor=lim["lcs"])
    hits = paragraph_hits(new_text, fp_source)
    hit_names = names_in(new_text, list(names or []))

    reasons = []
    if r["containment"] >= lim["containment"]:
        reasons.append("6-gram 重疊 %.1f%%（門檻 %.0f%%）" % (r["containment"] * 100, lim["containment"] * 100))
    if length >= lim["lcs"]:
        reasons.append("最長共同片段 %d 字（門檻 %d）" % (length, lim["lcs"]))
    if hit_names:
        reasons.append("沿用了來源的名字：%s" % "、".join(hit_names[:5]))
    if hits:
        reasons.append("%d 段幾乎全來自來源（第 %s 段）" % (len(hits), "、".join(str(h["paragraph"]) for h in hits[:5])))

    return {"ok": not reasons, "reasons": reasons,
            "metrics": {"containment": round(r["containment"], 4), "jaccard": round(r["jaccard"], 5),
                        "chars": fp_new["len"], "limit_containment": lim["containment"],
                        "limit_lcs": lim["lcs"]},
            "span": {"length": length, "text": raw_span(new_text, piece), "at": idx},
            "paragraphs": hits, "names": hit_names}
