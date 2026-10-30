# -*- coding: utf-8 -*-
"""卷綱的唯一解析入口：找某章屬於哪一卷、哪幾章沒有卷綱、下一個卷號。

為什麼要集中：續寫合約與漂移工具原本各有一套（一個找不到退回第一卷、一個退回最後一卷），
兩邊都會靜默拿到錯的卷。這裡只認**正式卷綱**（`大綱/`、`大綱/卷綱/` 的 `卷綱*.md`）；
草稿放在 `大綱/草稿/`，不會被當成正式卷綱（見 `docs/卷先行.md`）。
"""
import difflib
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


def contract_bullets(text):
    """從卷綱抓「卷契約」那一段的項目（- 本卷賣點：…），用來帶進全書大綱。"""
    m = re.search(r"^##\s*卷契約\s*$(.*?)(?=^##\s|\Z)", text or "", re.S | re.M)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        s = line.strip()
        if s.startswith("- ") and "：" in s:
            out.append(s)
    return out


def _bullet_key(line):
    s = (line or "").strip().lstrip("-").strip()
    return s.split("：", 1)[0].strip() if "：" in s else s


def _sync_book_outline(book_dir, no, fm, bullets=None):
    """把這一卷補進 大綱/全書大綱.md 的「分卷」：缺的一節就追加，缺的卷契約就補上。

    只補不覆蓋：已有的句子不動，章節範圍對不上就只警告。
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
    rng = str(fm.get("章節範圍") or "")
    nums = [int(x) for x in re.findall(r"\d+", rng)]
    lo, hi = (nums[0], nums[-1]) if len(nums) >= 2 else (None, None)
    bullets = [b for b in (bullets or []) if b]
    name = str(fm.get("卷名") or ("第%d卷" % no))

    for i in range(start, end):
        if _heading_volume(lines[i]) != no:
            continue
        sec_end = next((j for j in range(i + 1, end) if lines[j].startswith(("### ", "## "))), end)
        span_line = next((x for x in lines[i:sec_end] if x.strip().startswith("- 篇幅")), "")
        other = [int(x) for x in re.findall(r"\d+", span_line)]
        if lo is not None and len(other) >= 2 and (other[0], other[1]) != (lo, hi):
            return ["全書大綱的第 %d 卷寫的是第 %d–%d 章，這次是第 %d–%d 章；已保留原本內容。"
                    % (no, other[0], other[1], lo, hi)]
        have = {_bullet_key(x) for x in lines[i:sec_end] if x.strip().startswith("- ")}
        add = [b for b in bullets if _bullet_key(b) not in have]
        if not add:
            return []
        # 插在「篇幅」那行後面（沒有就插在標題後面），卷綱連結留在最後
        at = next((j for j in range(i + 1, sec_end) if lines[j].strip().startswith("- 篇幅")), i + 1)
        new = lines[:at + 1] + add + lines[at + 1:]
        return _write_outline(book_dir, p, new)

    block = ["### 第 %d 卷：%s" % (no, name), "",
             "- 篇幅：第 %d 章～第 %d 章" % (lo or 0, hi or 0)] + bullets + \
            ["- 卷綱：`大綱/卷綱_第%d卷.md`（已確認）" % no, ""]
    return _write_outline(book_dir, p, lines[:end] + [""] + block + lines[end:])


def _write_outline(book_dir, p, lines):
    try:
        from . import tracking
        tracking.backup(book_dir, p, "全書大綱同步前")
    except Exception:
        pass
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    os.replace(tmp, p)
    return []


def sync_outline(book_dir, no):
    """把已採用的卷綱重新同步進全書大綱（補缺的卷契約；只補不覆蓋）。"""
    no = int(no)
    rel = "大綱/卷綱_第%d卷.md" % no
    p = project.safe_path(book_dir, rel)
    if not os.path.isfile(p):
        raise project.ProjectError("找不到正式的 %s，先採用卷綱再同步。" % rel)
    text = project.read_text(p)
    fm, _body = project.split_frontmatter(text)
    return _sync_book_outline(book_dir, no, fm or {}, contract_bullets(text))


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
    return {"rel": dst_rel,
            "warnings": _sync_book_outline(book_dir, no, fm, contract_bullets(text))}


REVISION_PREFIX = "卷綱修訂"


def revision_rel(no):
    return "%s/%s_第%d卷.md" % (DRAFT_DIR, REVISION_PREFIX, int(no))


def revisions(book_dir):
    """`大綱/草稿/` 裡的「既有卷修訂」草稿。每筆：rel/name/status/lo/hi/no。"""
    d = os.path.join(book_dir, *DRAFT_DIR.split("/"))
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not (f.endswith(".md") and f.startswith(REVISION_PREFIX)):
            continue
        try:
            fm = project.split_frontmatter(project.read_text(os.path.join(d, f)))[0] or {}
        except OSError:
            continue
        nums = [int(x) for x in re.findall(r"\d+", str(fm.get("章節範圍") or ""))]
        lo, hi = (nums[0], nums[-1]) if len(nums) >= 2 else (None, None)
        out.append({"rel": "%s/%s" % (DRAFT_DIR, f), "name": str(fm.get("卷名") or f),
                    "status": str(fm.get("狀態") or ""), "lo": lo, "hi": hi, "no": _num_from_name(f)})
    out.sort(key=lambda v: (v["no"] or 0, v["rel"]))
    return out


def official(book_dir, no):
    """第 N 卷的正式卷綱（只認 DIRS 底下的檔案，草稿不算）。"""
    try:
        no = int(no)
    except (TypeError, ValueError):
        return None
    return next((v for v in list_volumes(book_dir) if v["no"] == no and v["kind"] == "卷"), None)


def revision_info(book_dir, no):
    """修訂草稿與正式卷綱的差異；沒有草稿回 None。"""
    rev = revision_rel(no)
    p = project.safe_path(book_dir, rev)
    if not os.path.isfile(p):
        return None
    text = project.read_text(p)
    v = official(book_dir, no)
    rel = v["rel"] if v else ""
    old = project.read_text(project.safe_path(book_dir, rel)) if rel else ""
    diff = "\n".join(difflib.unified_diff(
        old.splitlines(), text.splitlines(),
        fromfile=rel or "（沒有正式卷綱）", tofile=rev, lineterm="", n=3))
    return {"rel": rev, "official": rel, "diff": diff, "text": text}


def apply_revision(book_dir, no):
    """把修訂草稿套回正式卷綱：備份正式檔、狀態改「已確認」、同步全書大綱，刪掉草稿。"""
    v = official(book_dir, no)
    if not v:
        raise project.ProjectError("找不到第 %s 卷的正式卷綱；新卷請用「開新卷 → 採用」。" % no)
    rel = revision_rel(no)
    src = project.safe_path(book_dir, rel)
    if not os.path.isfile(src):
        raise project.ProjectError("找不到第 %s 卷的修訂草稿（%s）。" % (no, rel))
    text = project.read_text(src)
    fm, _body = project.split_frontmatter(text)
    if not str(fm.get("章節範圍") or "").strip():
        raise project.ProjectError("修訂草稿沒有「章節範圍」，先補上第幾章到第幾章再套用。")
    dst = project.safe_path(book_dir, v["rel"])
    try:
        from . import tracking
        tracking.backup(book_dir, dst, "卷綱修訂前")
    except Exception:
        pass
    new_text = project.set_frontmatter_field(text, "狀態", "已確認")
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_text if new_text.endswith("\n") else new_text + "\n")
    os.replace(tmp, dst)
    try:
        os.remove(src)
    except OSError:
        pass
    return {"rel": v["rel"],
            "warnings": _sync_book_outline(book_dir, int(no), fm, contract_bullets(text))}


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
