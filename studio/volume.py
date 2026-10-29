# -*- coding: utf-8 -*-
"""卷綱的唯一解析入口：找某章屬於哪一卷、哪幾章沒有卷綱、下一個卷號。

為什麼要集中：續寫合約與漂移工具原本各有一套（一個找不到退回第一卷、一個退回最後一卷），
兩邊都會靜默拿到錯的卷。這裡只認**正式卷綱**（`大綱/`、`大綱/卷綱/` 的 `卷綱*.md`）；
草稿放在 `大綱/草稿/`，不會被當成正式卷綱（見 `docs/卷先行.md`）。
"""
import os
import re

from . import project

DIRS = ("大綱", "大綱/卷綱")
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_int(s):
    """把『一』『十二』『二十一』『兩』這類卷號轉成整數；認不出就回 None。"""
    s = (s or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    total = 0
    for ch in s:
        v = CN_NUM.get(ch)
        if v is None:
            return None
        total = total * 10 + v if total < 10 else total + v
    return total or None


def _num_from_name(name):
    m = re.search(r"第([〇零一二兩三四五六七八九十百\d]+)[卷幕]", name)
    if not m:
        return None
    raw = m.group(1)
    if raw.isdigit():
        return int(raw)
    if "百" in raw:      # 百位以上的寫法很少見，只支援「一百」「一百二十」這種
        head, _, tail = raw.partition("百")
        base = (_cn_int(head) or 1) * 100
        return base + (_cn_int(tail) or 0) if tail else base
    return _cn_int(raw)


def list_volumes(book_dir):
    """正式卷綱清單（依章節範圍起點排序）。每筆：rel/name/status/lo/hi/no。"""
    out = []
    for sub in DIRS:
        d = os.path.join(book_dir, *sub.split("/"))
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not (f.endswith(".md") and f.startswith("卷綱")):
                continue
            rel = "%s/%s" % (sub, f)
            try:
                fm = project.split_frontmatter(project.read_text(os.path.join(d, f)))[0] or {}
            except OSError:
                continue
            nums = [int(x) for x in re.findall(r"\d+", str(fm.get("章節範圍") or ""))]
            lo, hi = (nums[0], nums[-1]) if len(nums) >= 2 else (None, None)
            out.append({"rel": rel, "name": str(fm.get("卷名") or f), "status": str(fm.get("狀態") or ""),
                        "lo": lo, "hi": hi, "no": _num_from_name(f),
                        "kind": "幕" if "幕" in f else "卷"})
    # 同一章同時被「卷」和「幕」覆蓋時，卷優先（卷末承諾要的是卷，不是幕）
    out.sort(key=lambda v: (v["kind"] != "卷", v["lo"] if v["lo"] is not None else 10 ** 9, v["rel"]))
    return out


def find(book_dir, chapter):
    """這一章屬於哪一份正式卷綱；不在任何範圍就回 None（不再退回任何一卷）。"""
    for v in list_volumes(book_dir):
        if v["lo"] is not None and v["hi"] is not None and v["lo"] <= int(chapter) <= v["hi"]:
            return v
    return None


def cover(book_dir, start, end):
    """[start, end] 裡哪些章沒有正式卷綱。回傳章號清單（空＝都有卷綱）。"""
    out = []
    for no in range(int(start), int(end) + 1):
        if find(book_dir, no) is None:
            out.append(no)
    return out


def has_volumes(book_dir):
    return bool(list_volumes(book_dir))


def next_no(book_dir):
    """下一個卷號：檔名／卷名裡最大的卷號 + 1；都沒有就 1（只數「卷」，不數「幕」）。"""
    nums = [v["no"] for v in list_volumes(book_dir) if v["no"] and v["kind"] == "卷"]
    return (max(nums) + 1) if nums else 1


def brief(missing, limit=3):
    """把缺卷綱的章號縮成一句：第 51～60 章（共 10 章）。"""
    missing = list(missing)
    if not missing:
        return ""
    if len(missing) == 1:
        return "第 %d 章" % missing[0]
    # 只取連續段
    runs, cur = [], [missing[0]]
    for n in missing[1:]:
        if n == cur[-1] + 1:
            cur.append(n)
        else:
            runs.append(cur)
            cur = [n]
    runs.append(cur)
    parts = ["第 %d～%d 章" % (r[0], r[-1]) if len(r) > 1 else "第 %d 章" % r[0] for r in runs[:limit]]
    more = "…" if len(runs) > limit else ""
    return "%s（共 %d 章）%s" % ("、".join(parts), len(missing), more)
