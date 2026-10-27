"""回寫追蹤後的本機檢查：只看「有沒有寫到」，不判斷寫得對不對，不花 token。

結果存在 .studio/回寫檢查/第NNN章.json；總覽「需要注意」會列出還有問題的章。重跑回寫通過後就會消失。
"""
import json
import os
import re
import time

from . import context, project, tracking

MIN_MENTIONS = 3        # 正文提到幾次以上的角色，才要求角色狀態更新
STALE_SUSPENSE = 30     # 懸念、誤認種下超過幾章還沒回收就提醒
CHECK_DIR = os.path.join(".studio", "回寫檢查")
_DONE_FS = ("已回收", "廢棄")
_DONE_CARD = ("已寫", "定稿", "完成")


def _ids(text, prefix):
    return list(dict.fromkeys(re.findall(r"(?<![A-Za-z0-9])(%s\d{2,})(?!\d)" % prefix, text or "")))


def _ch(s):
    n = re.findall(r"\d+", str(s or ""))
    return int(n[0]) if n else 0


def _count(text, names):
    return max((text.count(n) for n in names if n and len(n) >= 2), default=0)


def check(book_dir, no, revision=False, data=None):
    """回傳問題清單（每項一句話）。data 是回寫用的 JSON（有的話多檢查新增物）。"""
    issues = []
    label = tracking.chapter_label(no)
    _, text = context.chapter_text(book_dir, no, ("正文",))
    text = context.body(text)
    _, card = context.card_text(book_dir, no)

    # 章節摘要
    sp = os.path.join(book_dir, "追蹤", "章節摘要", label + ".md")
    if not os.path.isfile(sp):
        issues.append("沒有產生章節摘要")
    else:
        blank = project.read_text(sp).count("（無）")
        if blank >= 2:
            issues.append("章節摘要有 %d 段空白" % blank)

    # 狀態卡
    if not revision and tracking.tracked_to(book_dir) < no:
        issues.append("狀態卡沒有更新到本章")

    # 角色狀態
    if not revision and text:
        miss = []
        for e in project.list_entries(book_dir, "設定/角色"):
            names = [e["name"]] + [str(a) for a in (e.get("aliases") or [])]
            n = _count(text, names)
            if n < MIN_MENTIONS:
                continue
            p = os.path.join(book_dir, "追蹤", "角色狀態", e["name"] + ".md")
            if not os.path.isfile(p):
                continue
            fm, _ = project.split_frontmatter(project.read_text(p))
            if _ch(fm.get("最後登場")) < no:
                miss.append("%s（出現 %d 次）" % (e["name"], n))
        if miss:
            issues.append("正文有出場、角色狀態沒更新：" + "、".join(miss))

    # 伏筆：章綱點名的
    fs = {r.get("編號"): r for r in project.read_table(book_dir, "追蹤/伏筆.md")["rows"]}
    for fid in _ids(card, "F"):
        r = fs.get(fid)
        if not r:
            issues.append("章綱提到 %s，伏筆表沒有這一條" % fid)
        elif r.get("狀態") not in _DONE_FS and _ch(r.get("最後出現")) < no:
            issues.append("章綱提到 %s，伏筆表的「最後出現」沒有推進到本章" % fid)

    # 時間線
    tl = project.read_table(book_dir, "追蹤/時間線.md")["rows"]
    if tl and not any(no in [int(x) for x in re.findall(r"\d+", str(r.get("揭示章") or ""))] for r in tl):
        issues.append("時間線沒有任何一列的揭示章是本章")

    # 讀者認知：章綱點名的
    rp = {r.get("編號"): r for r in project.read_table(book_dir, tracking.RP_FILE)["rows"]}
    if rp:
        for rid in _ids(card, "R"):
            r = rp.get(rid)
            if not r:
                issues.append("章綱提到 %s，讀者認知帳本沒有這一條" % rid)
            elif r.get("類型") != "已知" and not str(r.get("回收章") or "").strip():
                issues.append("章綱提到 %s，回收章還空著（如果本章要揭曉，回寫漏了）" % rid)

    # 章綱狀態
    if card:
        fm, _ = project.split_frontmatter(card)
        st = str(fm.get("狀態") or "")
        if not any(w in st for w in _DONE_CARD):
            issues.append("章綱狀態還是「%s」" % (st or "空白"))

    # 新增物：登記了但正文沒出現
    if data and text:
        ghost = []
        for it in data.get("new_entities") or []:
            name = str((it or {}).get("名稱") or (it or {}).get("名詞") or "").strip() if isinstance(it, dict) else str(it).strip()
            if name and len(name) >= 2 and name not in text:
                ghost.append(name)
        if ghost:
            issues.append("登記成新增物、但正文找不到：" + "、".join(ghost))
    return issues


def save(book_dir, no, issues):
    d = os.path.join(book_dir, CHECK_DIR)
    p = os.path.join(d, "%s.json" % tracking.chapter_label(no))
    if not issues:
        if os.path.isfile(p):
            os.remove(p)
        return
    os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"chapter": no, "time": time.time(), "issues": issues}, f, ensure_ascii=False, indent=1)


def run(book_dir, no, revision=False, data=None):
    """檢查、存檔，回傳附在任務結果後面的文字。"""
    try:
        issues = check(book_dir, no, revision, data)
    except Exception as e:   # 檢查失敗不能讓回寫跟著失敗
        return "\n\n回寫檢查沒有跑完：%s" % e
    save(book_dir, no, issues)
    if not issues:
        return "\n\n**回寫檢查**：全部正常。"
    return "\n\n**回寫檢查：第%d章有 %d 項可能沒寫到**\n%s\n\n可以到總覽按「重跑回寫」，或自己補。" % (
        no, len(issues), "\n".join("- " + x for x in issues))


def alerts(book_dir, latest):
    """總覽「需要注意」用。"""
    out = []
    d = os.path.join(book_dir, CHECK_DIR)
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    rec = json.load(fh)
            except (OSError, ValueError):
                continue
            no, iss = int(rec.get("chapter") or 0), rec.get("issues") or []
            if not no or not iss:
                continue
            path, _ = context.chapter_text(book_dir, no, ("正文",))
            out.append({"level": "warn", "kind": "回寫檢查", "action": "rewriteback", "chapter_no": no, "path": path,
                        "text": "第%d章回寫有 %d 項可能沒寫到：%s%s" % (no, len(iss), iss[0], "……" if len(iss) > 1 else ""),
                        "details": iss})
    rows = project.read_table(book_dir, tracking.RP_FILE)["rows"]
    stale = [r for r in rows if r.get("類型") != "已知" and not str(r.get("回收章") or "").strip()
             and _ch(r.get("種下章")) and latest - _ch(r.get("種下章")) > STALE_SUSPENSE]
    if stale:
        stale.sort(key=lambda r: _ch(r.get("種下章")))
        out.append({"level": "info", "kind": "懸念久未回收",
                    "text": "%d 條懸念或誤認種下超過 %d 章還沒回收（最久：%s 第%d章）。" % (
                        len(stale), STALE_SUSPENSE, stale[0].get("編號", ""), _ch(stale[0].get("種下章"))),
                    "details": ["%s（第%d章）%s" % (r.get("編號", ""), _ch(r.get("種下章")), r.get("內容", "")) for r in stale]})
    return out
