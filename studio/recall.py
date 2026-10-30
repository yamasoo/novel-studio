# -*- coding: utf-8 -*-
"""檢索式長期記憶：從作者自己寫過的段落裡，找出跟這一章最像的幾段，注入寫稿上下文。

為什麼不用「名稱子字串比對」
  原本的上下文只會依「這章提到誰」把設定檔整份拉進來，找不到「相似的處境」。
  寫到第 30 章時，真正有用的是「作者自己寫過的類似場景」——那是文字層的相似，不是名字相同。

怎麼做（不呼叫模型、純本機）
  1. 把 正文/ 每一章切成段落當文件。
  2. 分詞：中日文用「字元 bigram」（不用斷詞），英文用單詞；查詢用同一套。
  3. BM25 排序，取前 k 段；去掉與已選段落幾乎重複的；依字數預算裁剪。
  4. 索引快取在 .studio/索引/recall.json，用檔案的 size＋mtime 當版本；檔案一動就重建。

怎麼用
  context.for_chapter 會呼叫 context_block()，以 priority 3 注入（預算不夠時可以被丟）。
  設定可關：config 的 recall=false；段數：recall_paragraphs（預設 6）。
"""
import hashlib
import json
import math
import os
import re

from . import project

CACHE_REL = ".studio/索引/recall.json"
K1, B = 1.2, 0.75
MIN_PARA = 40          # 太短的段落（一行對白）不當文件
MAX_CHARS = 1200       # 注入的字數上限（約 600 tokens 中文）
SCORE_FLOOR = 0.03     # 分數低於第一名的 3% → 當雜訊丟掉（BM25 的分數差距很大，這條只砍長尾）
CJK = re.compile(r"[\u3400-\u9fff\u3040-\u30ff]+")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")


def _tokens(text):
    """中日文→字元 bigram（單字成段就留單字）；英文→小寫單詞。"""
    out = []
    for run in CJK.findall(text or ""):
        if len(run) == 1:
            out.append(run)
        else:
            out.extend(run[i:i + 2] for i in range(len(run) - 1))
    out.extend(w.lower() for w in WORD.findall(text or "") if len(w) > 2)
    return out


def _cache_path(book_dir):
    return os.path.join(book_dir, *CACHE_REL.split("/"))


def _manifest(book_dir):
    """正文檔案的版本指紋：檔名＋大小＋mtime。檔案一改，指紋就變。"""
    items = []
    for rel in sorted(project._scan_dir(os.path.join(book_dir, "正文")).items()):
        no, fn = rel
        p = os.path.join(book_dir, "正文", fn)
        try:
            st = os.stat(p)
        except OSError:
            continue
        items.append([no, fn, st.st_size, int(st.st_mtime)])
    blob = json.dumps(items, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16], items


def paragraphs(book_dir):
    """[(章號, 段號, 文字)]：只收夠長的段落，frontmatter 與標題不算。"""
    out = []
    for no, fn in sorted(project._scan_dir(os.path.join(book_dir, "正文")).items()):
        text = project.read_text(os.path.join(book_dir, "正文", fn))
        body = project.split_frontmatter(text)[1] if text else ""
        for i, para in enumerate(body.split("\n\n")):
            p = para.strip()
            if len(p) < MIN_PARA or p.startswith(("#", "|", ">", "```")):
                continue
            out.append((no, i, p))
    return out


def build(book_dir):
    """建立（或重建）索引並寫快取；回傳 {manifest, paras}。"""
    digest, _items = _manifest(book_dir)
    paras = [[no, i, text] for no, i, text in paragraphs(book_dir)]
    data = {"version": 1, "manifest": digest, "paras": paras}
    p = _cache_path(book_dir)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass          # 快取寫不進去（書在唯讀位置）也能用，只是每次重算
    return data


_CACHE = {}
_TOKEN_CACHE = {}      # 指紋 → 與 paras 對齊的分詞結果（同一本書第二次查詢就不用重切）


def index(book_dir, force=False):
    """讀索引；檔案變了就重建。回傳 {manifest, paras}。"""
    key = os.path.abspath(book_dir)
    digest, _ = _manifest(book_dir)
    if not force:
        hit = _CACHE.get(key)
        if hit and hit.get("manifest") == digest:
            return hit
        try:
            with open(_cache_path(book_dir), encoding="utf-8") as f:
                data = json.load(f)
            if data.get("manifest") == digest:
                _CACHE[key] = data
                return data
        except (OSError, ValueError):
            pass
    data = build(book_dir)
    _CACHE[key] = data
    return data


def _bm25(docs, query_tokens, k):
    """docs：[{tokens, ...}]；回傳依分數排序的前 k 個（含分數）。"""
    n = len(docs)
    if not n or not query_tokens:
        return []
    df = {}
    for d in docs:
        for t in set(d["tokens"]):
            df[t] = df.get(t, 0) + 1
    avg = sum(len(d["tokens"]) for d in docs) / n
    q = set(query_tokens)
    scored = []
    for d in docs:
        tf = {}
        for t in d["tokens"]:
            if t in q:
                tf[t] = tf.get(t, 0) + 1
        if not tf:
            continue
        s = 0.0
        for t, f in tf.items():
            idf = math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
            s += idf * (f * (K1 + 1)) / (f + K1 * (1 - B + B * len(d["tokens"]) / max(avg, 1)))
        scored.append((s, d))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


def _tokens_for(data):
    """把整本書的分詞結果快取起來：12,000 段重切一次要 0.4 秒，同一本書之後都直接重用。"""
    key = data.get("manifest") or ""
    hit = _TOKEN_CACHE.get(key)
    if hit is not None and len(hit) == len(data.get("paras") or []):
        return hit
    toks = [_tokens(p[2]) for p in data.get("paras") or []]
    _TOKEN_CACHE.clear()
    _TOKEN_CACHE[key] = toks
    return toks


def search(book_dir, query, k=6, before=None, exclude=(), min_score=0.5):
    """找跟 query 最像的作者段落。before：只看這章之前（預設全部）；exclude：不要的章號。"""
    data = index(book_dir)
    toks = _tokens_for(data)
    docs = []
    for (no, i, text), tk in zip(data.get("paras") or [], toks):
        if before is not None and no >= before:
            continue
        if no in exclude:
            continue
        docs.append({"chapter": no, "i": i, "text": text, "tokens": tk})
    hits = []
    seen = []
    top = 0.0
    for score, d in _bm25(docs, _tokens(query), k * 3):
        if score < min_score:
            continue
        if not hits:
            top = score
        elif score < top * SCORE_FLOOR:      # 分數只有第一名的兩成 → 當成雜訊
            break
        toks = set(d["tokens"])
        # 幾乎重複的段落（同一段被切成兩段、或作者貼了兩次）只留一次
        if any(len(toks & s) / max(1, len(toks | s)) > 0.8 for s in seen):
            continue
        seen.append(toks)
        hits.append({"chapter": d["chapter"], "text": d["text"], "score": round(score, 2)})
        if len(hits) >= k:
            break
    return hits


def context_block(book_dir, no, query, k=6, limit_chars=MAX_CHARS):
    """給寫稿上下文用的段落（含出處）。沒有可用的就回傳空字串。"""
    try:
        hits = search(book_dir, query, k=k, before=no)
    except Exception:
        return ""
    if not hits:
        return ""
    lines, used = [], 0
    for h in hits:
        text = h["text"].strip()
        if used + len(text) > limit_chars and lines:
            break
        lines.append("（第%d章）%s" % (h["chapter"], text))
        used += len(text)
    return "\n\n".join(lines)
