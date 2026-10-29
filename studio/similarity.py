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


def longest_common(a, b, floor=20):
    """最長共同片段（字元數）。兩邊先正規化；短於 floor 一律回 0（不值得報）。

    用 rolling hash 二分搜尋長度，找到候選再逐字驗證，避免雜湊碰撞誤報。
    """
    A, B = normalize(a), normalize(b)
    if len(A) < floor or len(B) < floor:
        return 0
    if len(A) > len(B):
        A, B = B, A

    powB = pow(BASE, 1, M61)
    # 預先算每個長度的「最高位權重」
    weights = {1: 1}
    for L in range(2, len(A) + 1):
        weights[L] = (weights[L - 1] * BASE) % M61

    def found(L):
        if L <= 0:
            return True, ""
        w = weights[L]
        seen = set()
        h = _hash(B, 0, L)
        seen.add(h)
        for i in range(1, len(B) - L + 1):
            h = ((h - ord(B[i - 1]) * w) * BASE + ord(B[i + L - 1])) % M61
            seen.add(h)
        h = _hash(A, 0, L)
        cand = [(h, 0)]
        for i in range(1, len(A) - L + 1):
            h = ((h - ord(A[i - 1]) * w) * BASE + ord(A[i + L - 1])) % M61
            cand.append((h, i))
        for h, i in cand:
            if h in seen:
                piece = A[i:i + L]
                if piece in B:            # 逐字驗證，排除碰撞
                    return True, piece
        return False, ""

    lo, hi, best = floor, len(A), (0, "")
    while lo <= hi:
        mid = (lo + hi) // 2
        ok, piece = found(mid)
        if ok:
            best = (mid, piece)
            lo = mid + 1
        else:
            hi = mid - 1
    return best[0]


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
