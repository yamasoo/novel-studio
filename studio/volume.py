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
DRAFT_DIR = "大綱/草稿"      # 草稿放獨立資料夾：正式卷綱只認 DIRS 底下的 卷綱*.md
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


def next_start(book_dir):
    """下一卷建議從第幾章開始：現有卷綱的最大結束章 + 1。"""
    his = [v["hi"] for v in list_volumes(book_dir) if v["hi"]]
    return (max(his) + 1) if his else 1


def draft_rel(no):
    return "%s/卷綱_第%d卷.md" % (DRAFT_DIR, int(no))


def drafts(book_dir):
    """`大綱/草稿/` 裡的**新卷**卷綱草稿（卷綱更新草稿不算）。每筆：rel/name/status/lo/hi/no。"""
    d = os.path.join(book_dir, *DRAFT_DIR.split("/"))
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not (f.endswith(".md") and f.startswith("卷綱") and not f.startswith("卷綱更新")):
            continue
        try:
            fm = project.split_frontmatter(project.read_text(os.path.join(d, f)))[0] or {}
        except OSError:
            continue
        nums = [int(x) for x in re.findall(r"\d+", str(fm.get("章節範圍") or ""))]
        lo, hi = (nums[0], nums[-1]) if len(nums) >= 2 else (None, None)
        out.append({"rel": "%s/%s" % (DRAFT_DIR, f), "name": str(fm.get("卷名") or f),
                    "status": str(fm.get("狀態") or ""), "lo": lo, "hi": hi, "no": _num_from_name(f)})
    out.sort(key=lambda v: (v["lo"] if v["lo"] is not None else 10 ** 9, v["rel"]))
    return out


def plan_drafts(book_dir):
    """`大綱/草稿/` 裡的卷綱**更新**草稿（卷末體檢產生，不是新卷）。每筆：rel/name/lo/hi。"""
    d = os.path.join(book_dir, *DRAFT_DIR.split("/"))
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not (f.endswith(".md") and f.startswith("卷綱更新")):
            continue
        nums = [int(x) for x in re.findall(r"\d+", f)]
        lo, hi = (nums[0], nums[1]) if len(nums) >= 2 else (None, None)
        out.append({"rel": "%s/%s" % (DRAFT_DIR, f), "name": os.path.splitext(f)[0], "lo": lo, "hi": hi})
    return out


def _heading_volume(line):
    """讀 `### 第N卷：…` 這種標題的卷號；讀不到回 None。"""
    m = re.match(r"^###\s*第\s*([0-9〇零一二兩三四五六七八九十百]+)\s*卷", (line or "").strip())
    return _cn_int(m.group(1)) if m else None


def _sync_book_outline(book_dir, no, fm):
    """採用卷綱後，把這一卷補進 大綱/全書大綱.md 的「分卷」（只追加、不覆蓋），並回傳警告。

    全書大綱是作者寫的規劃；這裡只確保「已定案的卷」在裡面有一節，
    卷的內容好不好、預計卷數對不對，仍然由作者判斷。
    """
    rel = "大綱/全書大綱.md"
    p = os.path.join(book_dir, *rel.split("/"))
    if not os.path.isfile(p):
        return ["沒有 大綱/全書大綱.md，這次沒有同步全書大綱。"]
    text = project.read_text(p)
    lines = text.splitlines()
    head = "## 分卷"
    start = next((i for i, x in enumerate(lines) if x.strip() == head), None)
    if start is None:
        return ["全書大綱沒有「分卷」段，這次沒有同步（避免把內容塞錯地方）。"]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    same = None
    rng = str(fm.get("章節範圍") or "")
    nums = [int(x) for x in re.findall(r"\d+", rng)]
    lo, hi = (nums[0], nums[-1]) if len(nums) >= 2 else (None, None)
    for i in range(start, end):
        if _heading_volume(lines[i]) != no:
            continue
        same = i
        body = "\n".join(lines[i:i + 4])
        other = [int(x) for x in re.findall(r"\d+", body)]
        if lo is not None and len(other) >= 2 and (other[0], other[1]) != (lo, hi):
            return ["全書大綱的第 %d 卷寫的是第 %d–%d 章，這次採用的是第 %d–%d 章；已保留原本內容。"
                    % (no, other[0], other[1], lo, hi)]
        break
    if same is not None:
        return []
    name = str(fm.get("卷名") or ("第%d卷" % no))
    block = ["### 第 %d 卷：%s" % (no, name), "",
             "- 篇幅：第 %d 章～第 %d 章" % (lo or 0, hi or 0),
             "- 卷綱：`大綱/卷綱_第%d卷.md`（已確認）" % no, ""]
    new = lines[:end] + [""] + block + lines[end:]
    try:
        from . import tracking
        tracking.backup(book_dir, p, "全書大綱同步前")
    except Exception:
        pass
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(new).rstrip() + "\n")
    os.replace(tmp, p)
    return []


def adopt(book_dir, no):
    """把 `大綱/草稿/卷綱_第N卷.md` 變成正式卷綱（狀態改「已確認」），成功後刪掉草稿。

    採用前只檢查最基本的東西（有 frontmatter、有章節範圍、正式檔不存在）：
    章節範圍要不要和前一卷接得起來、內容好不好，是作者看過才算的事，不在這裡自動判斷。
    """
    no = int(no)
    src_rel = draft_rel(no)
    src = project.safe_path(book_dir, src_rel)
    if not os.path.isfile(src):
        raise project.ProjectError("找不到第 %d 卷的卷綱草稿（%s）。" % (no, src_rel))
    text = project.read_text(src)
    fm, _body = project.split_frontmatter(text)
    if not fm:
        raise project.ProjectError("草稿沒有 frontmatter（類型、卷名、章節範圍），不能採用。")
    if not str(fm.get("章節範圍") or "").strip():
        raise project.ProjectError("草稿沒有「章節範圍」，不能採用；先補上第幾章到第幾章。")
    dst_rel = "大綱/卷綱_第%d卷.md" % no
    dst = project.safe_path(book_dir, dst_rel)
    if os.path.isfile(dst):
        raise project.ProjectError("正式的 %s 已經存在，先確認是不是已經採用過。" % dst_rel)
    new_text = project.set_frontmatter_field(text, "狀態", "已確認")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_text if new_text.endswith("\n") else new_text + "\n")
    os.replace(tmp, dst)
    try:
        os.remove(src)
    except OSError:
        pass
    return {"rel": dst_rel, "warnings": _sync_book_outline(book_dir, no, fm)}


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
