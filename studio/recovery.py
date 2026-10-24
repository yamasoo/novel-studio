# -*- coding: utf-8 -*-
"""恢復稿：模型中途出錯、被停止或輸出被截斷時，保留已經寫出來的文字。"""
import json
import os
import re
import time

from . import project

DIR = ("恢復稿",)
TAIL = 1600
MIN_OVERLAP = 48


def _dir(book_dir):
    d = os.path.join(book_dir, ".studio", *DIR)
    os.makedirs(d, exist_ok=True)
    return d


def save(book_dir, job_id, label, text, reason, chapter=None, kind="text", provider=None):
    text = (text or "").strip()
    if len(text) < 20:
        return None
    rid = "%s-%d" % (job_id, int(time.time() * 1000) % 100000)
    rec = {"id": rid, "job": job_id, "label": label, "chapter": chapter, "kind": kind, "reason": reason,
           "chars": project.count_chars(text), "text": text, "created": time.time(), "provider": provider}
    with open(os.path.join(_dir(book_dir), rid + ".json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    return rec


def list_all(book_dir, with_text=False):
    d = os.path.join(book_dir, ".studio", *DIR)
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d), reverse=True):
        if f.endswith(".json"):
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    rec = json.load(fh)
            except Exception:
                continue
            if not with_text:
                rec["preview"] = rec.get("text", "")[-120:]
                rec.pop("text", None)
            out.append(rec)
    return out


def load(book_dir, rid):
    if not re.match(r"^[\w\-]+$", rid or ""):
        raise project.ProjectError("恢復稿編號不合法")
    p = os.path.join(book_dir, ".studio", *DIR, rid + ".json")
    if not os.path.isfile(p):
        raise project.ProjectError("找不到這份恢復稿")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def discard(book_dir, rid):
    load(book_dir, rid)
    p = os.path.join(book_dir, ".studio", *DIR, rid + ".json")
    bak = os.path.join(book_dir, ".studio", "備份")
    os.makedirs(bak, exist_ok=True)
    os.replace(p, os.path.join(bak, "恢復稿_" + rid + ".json"))


def compose(existing, addition):
    """把續寫接到原文後面；續寫開頭若重複了原文結尾，去掉重複的部分。"""
    a, b = existing.rstrip(), addition.strip()
    tail = re.sub(r"\s+", "", a[-TAIL:])
    head = re.sub(r"\s+", "", b[:TAIL])
    overlap = 0
    for n in range(min(len(tail), len(head)), MIN_OVERLAP - 1, -1):
        if tail[-n:] == head[:n]:
            overlap = n
            break
    if overlap:
        consumed, i = 0, 0
        while i < len(b) and consumed < overlap:
            if not b[i].isspace():
                consumed += 1
            i += 1
        b = b[i:].lstrip()
    if not overlap:
        # 短的重疊：續寫開頭重複了原文最後一句（或幾句）
        sents = re.findall(r"[^。！？…」]*[。！？…」]+", b[:400])
        while sents:
            s = re.sub(r"\s+", "", sents[0])
            if len(s) >= 6 and re.sub(r"\s+", "", a).endswith(s):
                b = b[len(sents[0]):].lstrip()
                sents.pop(0)
            else:
                break
    if not b:
        return a + "\n"
    # 續寫從段落中間接上時直接相連，否則空一行
    joiner = "" if a and not a.endswith(("。", "」", "』", "！", "？", "…", "—")) and not b.startswith(("「", "#")) else "\n\n"
    return a + joiner + b + "\n"
