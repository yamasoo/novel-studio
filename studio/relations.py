# -*- coding: utf-8 -*-
"""角色關係表（誰對誰）：追蹤/關係.md

一個方向一列：「甲 → 乙」和「乙 → 甲」分開記，兩邊的看法可以不一樣。
關係改變時不覆蓋：舊的那列填上「結束章」，另開一列（起始章＝改變的那一章），所以歷史都留著。
結束章空白＝目前有效。

回寫追蹤時 AI 只報「有變的關係」，由這裡負責關舊列、開新列；舊書可以從角色檔的「## 關係」直接轉成草稿（不用模型）。
"""
import os
import re

from . import project, tracking

FILE = "追蹤/關係.md"
DRAFT = "追蹤/關係_草稿.md"
HEADERS = ["編號", "誰", "對誰", "關係", "態度", "起始章", "結束章", "變化原因"]
NEW_BOOK_CHAPTERS = 15   # 沒有關係表又已經寫超過這麼多章，視為舊書，不自動建立（等作者從角色檔轉換）

INTRO = ("> 誰「對」誰的關係，一個方向一列（A 對 B、B 對 A 分開記）。「關係」是身分或定位（師徒、盟友、債主），"
         "「態度」是這個人對另一個人的感受與溫度（信任、戒備、愛慕）。\n"
         "> 關係改變時舊的那列填「結束章」、另開一列，不要覆蓋；「結束章」空白＝目前有效。起始章空白＝從開頭就是這樣或不確定。\n\n")

_SKIP = re.compile(r"^[（(]?\s*(正文未明確|無|尚無|待補|未定|沒有|不明)\s*[）)]?[。.]?$")
_TRIVIAL = ("", "無", "（無）", "(無)", "沒有", "無變化", "無新增", "（正文未明確）", "正文未明確", "（無變化）")


def _norm(s):
    return re.sub(r"[\s，。、；：「」『』！？,.;:!?（）()]", "", str(s or ""))


def _cell(v):
    return str(v if v is not None else "").replace("|", "／").replace("\n", " ").strip()


def _ended(r):
    return bool(str(r.get("結束章") or "").strip())


def active(rows):
    return [r for r in rows if not _ended(r)]


# ---------------------------------------------------------------------------
# 角色名稱對照（別名 → 正式名稱）
# ---------------------------------------------------------------------------
def faction_merge_map(factions):
    """勢力檔有時會重複登記（「甲國」與「甲國（甲國政府）」）：名稱是另一個勢力名稱加括號的，併入那一個。"""
    names = [str(f["name"]).strip() for f in factions]
    out = {}
    for n in names:
        for base in names:
            if base != n and n.startswith(base) and n[len(base):len(base) + 1] in ("（", "("):
                out[n] = base
    return out


def alias_map(book_dir):
    """名稱／別名 → 正式名稱。角色與勢力都對得到；兩個人共用的別名不猜。"""
    entries = project.list_entries(book_dir, "設定/角色")
    factions = project.list_entries(book_dir, "設定/勢力")
    merge = faction_merge_map(factions)
    names = {str(e["name"]).strip() for e in entries} | {str(f["name"]).strip() for f in factions}
    owners = {}
    for e in entries + factions:
        canon_name = merge.get(str(e["name"]).strip(), str(e["name"]).strip())
        for a in [str(x).strip() for x in (e.get("aliases") or [])]:
            if a and a not in names:
                owners.setdefault(a, set()).add(canon_name)
    out = {n: merge.get(n, n) for n in names}
    out.update({a: next(iter(o)) for a, o in owners.items() if len(o) == 1})
    return out


def canon(name, amap):
    n = str(name or "").strip()
    if n in amap:
        return amap[n]
    n2 = re.sub(r"[（(].*?[）)]", "", n).strip()
    return amap.get(n2, n2 or n)


# ---------------------------------------------------------------------------
# 表格讀寫（保留表格前後的文字）
# ---------------------------------------------------------------------------
def _path(book_dir, rel):
    return os.path.join(book_dir, *rel.split("/"))


def _load(book_dir, rel, label=""):
    p = _path(book_dir, rel)
    if os.path.isfile(p):
        before, headers, rows, after = tracking._split_table(project.read_text(p))
        headers = headers or list(HEADERS)
        headers = headers + [h for h in HEADERS if h not in headers]
        return before, headers, rows, after
    return "---\n類型: 關係\n更新至: %s\n---\n\n# 角色關係\n\n%s" % (label, INTRO), list(HEADERS), [], ""


def _save(book_dir, rel, before, headers, rows, after, label):
    before = tracking._bump_updated(before, label)
    sep = "" if before.endswith("\n\n") else ("\n" if before.endswith("\n") else "\n\n")
    tracking._write(_path(book_dir, rel), before + sep + tracking._render_table(headers, rows) + ("\n" + after if after.strip() else "\n"))


def read_rows(book_dir, rel=FILE):
    return project.read_table(book_dir, rel)["rows"]


def exists(book_dir):
    return os.path.isfile(_path(book_dir, FILE))


def _next_id(rows):
    nums = [int(m.group(1)) for r in rows for m in [re.match(r"L(\d+)", str(r.get("編號") or ""))] if m]
    return max(nums, default=0) + 1


# ---------------------------------------------------------------------------
# 回寫：套用「有變的關係」
# ---------------------------------------------------------------------------
def apply_changes(book_dir, no, items, revision=False):
    """回傳匯報文字（空字串＝沒有動）。修訂舊章不動關係表（目前的關係以最新章為準，不能倒退）。"""
    label = tracking.chapter_label(no)
    items = [x for x in (items or []) if isinstance(x, dict)]
    if revision or not items:
        return ""
    if not exists(book_dir) and no > NEW_BOOK_CHAPTERS:
        return "角色關係（還沒建立關係表，略過；可到「伏筆與時間線」的角色關係分頁從角色檔建立）"
    amap = alias_map(book_dir)
    before, headers, rows, after = _load(book_dir, FILE, label)
    added, changed, same = 0, 0, 0
    nxt = _next_id(rows)
    for it in items:
        who, to = canon(it.get("誰"), amap), canon(it.get("對誰"), amap)
        rel, att, why = _cell(it.get("關係")), _cell(it.get("態度")), _cell(it.get("原因") or it.get("變化原因"))
        if not who or not to or who == to or not (rel or att):
            continue
        cur = next((r for r in reversed(rows) if r.get("誰") == who and r.get("對誰") == to and not _ended(r)), None)
        if cur is None:
            rows.append({"編號": "L%03d" % nxt, "誰": who, "對誰": to, "關係": rel, "態度": att,
                         "起始章": label, "結束章": "", "變化原因": why})
            nxt += 1
            added += 1
            continue
        new_rel, new_att = rel or cur.get("關係", ""), att or cur.get("態度", "")
        if _norm(new_rel) == _norm(cur.get("關係")) and _norm(new_att) == _norm(cur.get("態度")):
            same += 1
            continue
        if tracking._chno(cur.get("起始章")) == no and str(cur.get("起始章") or "").strip():
            # 同一章重跑回寫：改原來那列，不留下一列長度為零的歷史
            cur["關係"], cur["態度"] = new_rel, new_att
            if why:
                cur["變化原因"] = why
        else:
            cur["結束章"] = label
            rows.append({"編號": "L%03d" % nxt, "誰": who, "對誰": to, "關係": new_rel, "態度": new_att,
                         "起始章": label, "結束章": "", "變化原因": why})
            nxt += 1
        changed += 1
    if not (added or changed):
        return ""
    _save(book_dir, FILE, before, headers, rows, after, label)
    return "角色關係（新增 %d、變更 %d）" % (added, changed)


# ---------------------------------------------------------------------------
# 舊書：從角色檔的「## 關係」轉成草稿（不用模型）
# ---------------------------------------------------------------------------
def _section(body):
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    m = re.search(r"(?m)^##\s*關係[^\n]*\n(.*?)(?=^##\s|\Z)", body, re.S)
    return m.group(1) if m else ""


def build_draft(book_dir):
    entries = project.list_entries(book_dir, "設定/角色")
    if not entries:
        raise project.ProjectError("這本書還沒有角色檔，沒有東西可以轉換")
    amap = alias_map(book_dir)
    known = {e["name"] for e in entries} | set(amap.values())
    to = tracking.tracked_to(book_dir) or 0
    label = tracking.chapter_label(to) if to else ""
    before, headers, rows, after = _load(book_dir, FILE, label)
    had = len(rows)
    have = {(r.get("誰"), r.get("對誰")) for r in rows}
    nxt = _next_id(rows)
    added, unfiled, per_char = [], set(), 0
    for e in entries:
        text = project.read_text(_path(book_dir, e["file"]))
        got = 0
        for line in _section(project.split_frontmatter(text)[1]).split("\n"):
            m = re.match(r"^\s*[-*]\s*(.+?)\s*[：:]\s*(.+?)\s*$", line)
            if not m:
                continue
            obj, desc = m.group(1).strip(), m.group(2).strip()
            if not desc or _SKIP.match(desc):
                continue
            target = canon(obj, amap)
            if target == e["name"] or (e["name"], target) in have:
                continue
            note = ""
            if target not in known:
                unfiled.add(target)
                note = "對象沒有角色檔或勢力檔"
            rows.append({"編號": "L%03d" % nxt, "誰": e["name"], "對誰": target, "關係": desc.rstrip("。.").strip(), "態度": "",
                         "起始章": "", "結束章": "", "變化原因": note})
            have.add((e["name"], target))
            nxt += 1
            added.append((e["name"], target))
            got += 1
        per_char += 1 if got else 0
    if not added:
        raise project.ProjectError("角色檔的「## 關係」裡沒有可以轉換的內容（或都已經在關係表裡）")
    one_way = sorted({(a, b) for a, b in have if b in known and (b, a) not in have})
    p = _path(book_dir, DRAFT)
    head = "---\n類型: 關係\n更新至: %s\n狀態: 草稿\n---\n\n# 角色關係（草稿：確認後按「採用」）\n\n%s" % (label, INTRO)
    tracking._write(p, head + tracking._render_table(headers, rows) + "\n")
    msg = ("**角色關係草稿已建立**（%s）：從 %d 份角色檔轉出 %d 列%s。\n\n"
           % (DRAFT, per_char, len(added), "（原有關係表的 %d 列保留）" % had if had else ""))
    msg += ("這是從角色檔的「## 關係」直接整理的，沒有用模型：起始章先空著，之後回寫時會慢慢補；"
            "「關係」是角色檔那句描述原文，「態度」留空，可以自己填。\n")
    if unfiled:
        msg += "\n對象沒有角色檔或勢力檔的（%d 個）：%s\n" % (len(unfiled), "、".join(sorted(unfiled)[:15]))
    if one_way:
        msg += "\n只有單方向的 %d 組（例如 %s → %s，缺反方向）；不是每組都需要補，有需要才寫。\n" % (len(one_way), one_way[0][0], one_way[0][1])
    msg += "\n請到「伏筆與時間線 → 角色關係」核對，確認後按「採用草稿」；採用前不會影響寫稿。"
    return msg


def adopt_draft(book_dir):
    src, dst = _path(book_dir, DRAFT), _path(book_dir, FILE)
    if not os.path.isfile(src):
        raise project.ProjectError("沒有角色關係草稿")
    if os.path.isfile(dst):
        tracking.backup(book_dir, dst, "關係")
    text = project.read_text(src)
    text = re.sub(r"(?m)^狀態: 草稿\n", "", text, count=1).replace("# 角色關係（草稿：確認後按「採用」）", "# 角色關係", 1)
    tracking._write(dst, text)
    os.remove(src)
    return FILE


def discard_draft(book_dir):
    src = _path(book_dir, DRAFT)
    if os.path.isfile(src):
        tracking.backup(book_dir, src, "關係草稿")
        os.remove(src)


# ---------------------------------------------------------------------------
# 檢查用
# ---------------------------------------------------------------------------
def has_relation_change(characters):
    """回寫資料裡，有沒有角色填了「關係變化」。"""
    for c in characters or []:
        if isinstance(c, dict) and str(c.get("關係變化") or "").strip() not in _TRIVIAL:
            return True
    return False


# ---------------------------------------------------------------------------
# 關係圖：節點與勢力分組（資料來自設定集，不用模型）
# ---------------------------------------------------------------------------
MAIN_ROLES = ("主角", "主要配角")
_SPLIT = re.compile(r"[、，,；;／/]")


def _names_in(text, amap):
    out = []
    for part in _SPLIT.split(text or ""):
        part = re.sub(r"[（(].*?[）)]", "", part).strip()
        n = amap.get(part)
        if n and n not in out:
            out.append(n)
    return out


def faction_members(book_dir, amap=None):
    """各勢力的成員：{勢力: {角色: 優先序}}，優先序 0＝首領、1＝主要成員、2＝只列在「相關角色」。
    來源是勢力檔本身（frontmatter 的相關角色、「首領」「主要成員」兩行），重複登記的勢力併在一起。"""
    amap = amap or alias_map(book_dir)
    entries = project.list_entries(book_dir, "設定/勢力")
    merge = faction_merge_map(entries)
    chars = {e["name"] for e in project.list_entries(book_dir, "設定/角色")}
    out = {}
    for e in entries:
        fname = merge.get(str(e["name"]).strip(), str(e["name"]).strip())
        mem = out.setdefault(fname, {})
        fm, body = project.split_frontmatter(project.read_text(_path(book_dir, e["file"])))
        rel = fm.get("相關角色")
        cand = [(2, n) for n in _names_in("、".join(str(x) for x in rel) if isinstance(rel, list) else str(rel or ""), amap)]
        for line in body.split("\n"):
            m = re.match(r"^\s*[-*]\s*(首領|領袖|主要成員|成員)\s*[：:]\s*(.+?)\s*$", line)
            if m:
                cand += [(0 if m.group(1) in ("首領", "領袖") else 1, n) for n in _names_in(m.group(2), amap)]
        for pri, n in cand:
            if n in chars and pri < mem.get(n, 9):
                mem[n] = pri
    return out


def graph_data(book_dir):
    """關係圖用的資料：節點（角色、勢力）、勢力成員、全部關係列。前端依章數與篩選條件畫圖。"""
    chars = project.list_entries(book_dir, "設定/角色")
    factions = project.list_entries(book_dir, "設定/勢力")
    merge = faction_merge_map(factions)
    members = faction_members(book_dir)
    belongs = {}   # 角色 → 勢力（首領 > 主要成員 > 相關角色；同級取第一個）；也列出其他所屬
    for f, mem in members.items():
        for c, pri in mem.items():
            belongs.setdefault(c, []).append((pri, f))
    nodes = []
    for e in chars:
        fl = sorted(belongs.get(e["name"], []), key=lambda x: x[0])
        nodes.append({"name": e["name"], "kind": "角色", "role": e.get("role") or "",
                      "faction": fl[0][1] if fl else "", "also": [f for _, f in fl[1:]]})
    for f in factions:
        if str(f["name"]).strip() in merge:
            continue
        nodes.append({"name": f["name"], "kind": "勢力", "role": "", "members": sorted(members.get(f["name"], {}), key=lambda c: members[f["name"]][c])})
    amap = alias_map(book_dir)   # 表格裡寫別名或重複登記的勢力名時，圖上也要對到同一個點
    rows = [dict(r, 誰=canon(r.get("誰"), amap), 對誰=canon(r.get("對誰"), amap)) for r in read_rows(book_dir)]
    return {"nodes": nodes, "rows": rows, "latest": tracking.tracked_to(book_dir) or 0}
