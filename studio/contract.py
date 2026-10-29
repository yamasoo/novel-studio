# -*- coding: utf-8 -*-
"""續寫合約：把「續寫時不能違背的事實」整理成一份檔案，注入每章上下文的最前面。

為什麼要這份
  寫第 30 章時，模型看得到章綱、狀態卡、部分伏筆，但「這本書已經定稿到第幾章」「誰已經死了」
  「哪些秘密讀者已經知道、哪些還不能說破」散在各個表裡。合約把它們集中成一頁，
  以 priority 0 注入（預算不夠時最後才被砍），所以它比任何單一資料表都可靠。

怎麼產生
  純本機、不呼叫模型：從 正文／設定／追蹤／大綱 的既有資料整理。
  作者可以直接改，但重新產生時只有 `## 作者補充` 之後的內容會原樣保留——
  自己加的規則請寫在那一節。

什麼時候更新
  ensure() 只在「檔案不存在」或「已定稿章數變了」時重寫，所以續寫一章之後會自動跟上。
"""
import os
import re
import time

from . import project

REL = "設定/續寫合約.md"
KEEP_MARK = "## 作者補充"
STATUS_DONE = {"已回收", "已解", "回收"}


# ---------------------------------------------------------------------------
def _rows(text):
    """把 markdown 表格抓成 list[dict]，第一列當表頭。"""
    rows, head = [], None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if head:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if head is None:
            head = cells
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append({head[i]: cells[i] for i in range(min(len(head), len(cells)))})
    return rows


def _section(text, title):
    """取出 `## title` 到下一个 `## ` 之间的内文（不含标题行）。"""
    out, on = [], False
    for line in text.splitlines():
        if re.match(r"^##\s+", line):
            if on:
                break
            on = title in line
            continue
        if on:
            out.append(line)
    return "\n".join(out).strip()


def _read(path):
    return project.read_text(path) if os.path.isfile(path) else ""


def _body(book_dir, rel):
    text = _read(os.path.join(book_dir, *rel.split("/")))
    return project.split_frontmatter(text)[1] if text else ""


def _front(book_dir, rel):
    text = _read(os.path.join(book_dir, *rel.split("/")))
    return project.split_frontmatter(text)[0] if text else {}


def _clip(text, limit):
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "……"


def _strip_h1(text):
    """引用的檔案各自有 `# 標題`；放進合約的小節裡要拿掉，免得變成兩層大標。"""
    lines = (text or "").strip().splitlines()
    if lines and lines[0].lstrip().startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def last_chapter(book_dir):
    numbers = [n for n in project._scan_dir(os.path.join(book_dir, "正文"))]
    return max(numbers) if numbers else 0


def characters(book_dir):
    """[(名稱, 定位, 首次登場, 最後登場)]；資料來自 設定/角色/*.md 與 追蹤/角色狀態/。"""
    out = []
    for e in project.list_entries(book_dir, "設定/角色"):
        name = e.get("name") or ""
        fm = e.get("frontmatter") or _front(book_dir, e.get("file") or "")
        st = _front(book_dir, "追蹤/角色狀態/%s.md" % name)
        out.append((name, fm.get("定位") or "", fm.get("首次登場") or "", st.get("最後登場") or ""))
    return out


def threads(book_dir):
    """未回收的伏筆：[(編號, 內容, 埋設章, 預計回收, 狀態, 重要度)]，重要的排前面。"""
    rows = _rows(_body(book_dir, "追蹤/伏筆.md"))
    open_rows = []
    for r in rows:
        status = r.get("狀態") or ""
        if status in STATUS_DONE:
            continue
        open_rows.append((r.get("編號") or "", r.get("內容") or "", r.get("埋設章") or "",
                          r.get("預計回收") or "", status, r.get("重要度") or ""))
    order = {"高": 0, "中": 1, "低": 2}
    open_rows.sort(key=lambda x: (order.get(x[5], 3), x[0]))
    return open_rows


def secrets(book_dir):
    """時間線的兩堆：讀者已經知道的、還沒揭曉的。"""
    rows = _rows(_body(book_dir, "追蹤/時間線.md"))
    known, hidden = [], []
    for r in rows:
        revealed = (r.get("揭示章") or "").strip()
        item = (r.get("編號") or "", (r.get("實際發生（作者真相）") or "").strip(), revealed)
        if revealed and revealed not in ("未揭示", "未"):
            known.append(item)
        else:
            hidden.append(item)
    return known, hidden


def volume_outline(book_dir, no):
    """當前章節所在那一卷的卷綱（看 frontmatter 的「章節範圍」）；找不到就取第一份。"""
    d = os.path.join(book_dir, "大綱")
    files = sorted(f for f in os.listdir(d) if f.startswith("卷綱") and f.endswith(".md")) if os.path.isdir(d) else []
    best = None
    for f in files:
        body = _body(book_dir, "大綱/" + f)
        fm = _front(book_dir, "大綱/" + f)
        span = fm.get("章節範圍") or ""
        nums = [int(x) for x in re.findall(r"第0*(\d+)章", span)]
        if len(nums) >= 2 and nums[0] <= no <= nums[1]:
            return fm.get("卷名") or f, body
        if best is None:
            best = (fm.get("卷名") or f, body)
    return best or ("", "")


# ---------------------------------------------------------------------------
def build(book_dir, keep=""):
    """產生合約全文。keep：作者補充（原樣接在最後）。"""
    no = last_chapter(book_dir)
    chars = characters(book_dir)
    open_rows = threads(book_dir)
    known, hidden = secrets(book_dir)
    vol_name, vol_body = volume_outline(book_dir, no + 1)
    style = _body(book_dir, "設定/文風.md")
    banned = _section(style, "本書禁忌") or _section(style, "禁忌")
    style_base = _section(style, "基本設定")
    prefs = _body(book_dir, "設定/作者偏好.md")
    words = _rows(_body(book_dir, "設定/名詞表.md"))

    L = ["---", "類型: 續寫合約", "更新至: 第%03d章" % no,
         "產生時間: %s" % time.strftime("%Y-%m-%d %H:%M"), "---", "",
         "# 續寫合約", "",
         "> 這份是「續寫時不能違背的事實」，程式從正文、設定、追蹤與大綱整理出來的，"
         "以最高優先順序注入每章上下文。可以直接改；重新產生時只有 `%s` 之後的內容會原樣保留，"
         "自己加的規則請寫在那一節。" % KEEP_MARK, "",
         "## 1. 不可變事實", ""]
    if no:
        L.append("- 本書已定稿到**第 %d 章**（正文 %d 章）；第 1～%d 章的內容不可改寫，續寫不得與之矛盾。" % (no, no, no))
    else:
        L.append("- 這本書還沒有定稿的正文章節（從第一章開始寫）。")
    if chars:
        L.append("- 角色（%d 位）：%s" % (len(chars), "、".join(
            "%s（%s，首次登場 %s%s）" % (n, pos or "未標", first or "未標",
                                       "，最後登場 " + last if last else "")
            for n, pos, first, last in chars)))
    if known:
        L.append("- 讀者**已經知道**的事（不能再當成新資訊，也不能反過來推翻）：")
        for code, fact, at in known[:12]:
            L.append("  - %s（%s 揭示）：%s" % (code, at, fact))
        if len(known) > 12:
            L.append("  - ……另有 %d 條，見 `追蹤/時間線.md`" % (len(known) - 12))
    if hidden:
        L.append("- **還沒揭曉**的事（本章不能提前說破）：")
        for code, fact, _at in hidden[:12]:
            L.append("  - %s：%s" % (code, fact))
        if len(hidden) > 12:
            L.append("  - ……另有 %d 條，見 `追蹤/時間線.md`" % (len(hidden) - 12))
    if words:
        names = [r.get("名詞") or r.get("名稱") or r.get("詞") or "" for r in words][:20]
        L.append("- 名詞表已登記 %d 條%s" % (len(words), ("（例：%s）" % "、".join(n for n in names if n)) if any(names) else ""))
    L += ["", "## 2. 聲線（每章都要維持）", ""]
    if style_base:
        L += [_clip(style_base, 600), ""]
    if banned:
        L += ["**本書禁忌（違反就是不合格）**", "", _clip(banned, 800), ""]
    if not (style_base or banned):
        L += ["- 見 `設定/文風.md`（沒有填就沿用共用文風）。", ""]
    L += ["## 3. 必須承接的懸念", ""]
    if open_rows:
        for code, fact, plant, due, status, weight in open_rows[:20]:
            L.append("- %s %s（埋設 %s，預計回收 %s，狀態 %s，重要度 %s）"
                     % (code, fact, plant or "未標", due or "未標", status or "未標", weight or "未標"))
        if len(open_rows) > 20:
            L.append("- ……另有 %d 條還沒回收，見 `追蹤/伏筆.md`" % (len(open_rows) - 20))
    else:
        L.append("- 目前沒有未回收的伏筆。")
    L += ["", "## 4. 卷末承諾", ""]
    if vol_body:
        if vol_name:
            L.append("（第 %d 章屬於本卷：%s）" % (no + 1, vol_name))
            L.append("")
        L.append(_clip(_strip_h1(vol_body), 900))
    else:
        L.append("- 還沒有卷綱；先寫 `大綱/卷綱_第N卷.md`，續寫才對得上整卷走向。")
    L += ["", "## 5. 禁區", ""]
    L.append("- 作者的硬性偏好（`設定/作者偏好.md`）與本書規則（`CLAUDE.md`）優先於任何寫作技法；違反就重寫。")
    if prefs:
        L += ["", _clip(_strip_h1(prefs), 500)]
    L += ["", KEEP_MARK, "", keep.strip() if keep.strip() else "（沒有；作者自己加的規則寫在這裡）", ""]
    return "\n".join(L)


def path(book_dir):
    return os.path.join(book_dir, *REL.split("/"))


def text(book_dir):
    """目前檔案內容；沒有就回傳空字串。"""
    return _read(path(book_dir))


def keep_of(existing):
    """舊檔裡 `## 作者補充` 之後的內容。"""
    if KEEP_MARK not in existing:
        return ""
    return existing.split(KEEP_MARK, 1)[1].strip()


def ensure(book_dir, force=False):
    """需要時產生／更新合約；回傳寫入的相對路徑，沒動就回傳 None。"""
    p = path(book_dir)
    existing = _read(p)
    no = last_chapter(book_dir)
    if existing and not force:
        fm = project.split_frontmatter(existing)[0]
        if (fm.get("更新至") or "").strip() == "第%03d章" % no:
            return None                     # 章數沒變：作者可能改過，不動它
    content = build(book_dir, keep_of(existing))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, p)
    return REL
