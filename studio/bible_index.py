"""設定索引：只讀本機檔案，不呼叫 AI。

- build(book_dir)：掃描 設定/（世界觀、角色、勢力）與 設定/名詞表.md，找出疑似重複的名稱。
- rebuild(book_dir)：build 後寫入 設定/_索引.md（給 novel-bible skill 先讀）。
- merge(book_dir, canonical, duplicates)：把疑似重複的設定檔併入保留的那一份。
  不刪除任何內容：被併入的檔案移到 設定/_已合併/，內文併進保留檔的「併入」段落，
  名稱加進保留檔的「別名」，名詞表與其他設定裡指向舊檔的路徑改成保留檔。
"""

import datetime
import json
import os
import re
import shutil

from . import project

SETTING_SUBDIRS = ("世界觀", "角色", "勢力")
MERGE_FOLDERS = ("設定/角色/", "設定/勢力/", "設定/世界觀/")
INDEX_REL = "設定/_索引.md"
GLOSSARY_REL = "設定/名詞表.md"
MERGED_REL = "設定/_已合併"

# 「近似」比對時才去掉的層級後綴：只用來提醒「可能是同一個地方」，結果一律標成近似，不預設勾選。
# 刻意不包含「迴廊」「要塞」等會指不同地點的詞。
LOOSE_SUFFIXES = ("星系", "星域", "星區", "市", "家")
PUNCT_RE = re.compile(r"[\s・·•\-—－_()（）「」『』＝]")
ALIAS_SPLIT_RE = re.compile(r"[、,，/／]")


def _clean(s):
    """表格欄位不能含分隔符，否則索引會錯位。"""
    return str(s or "").replace("|", "/").replace("｜", "/").strip()


def _first_line(body, title):
    m = re.search(r"^##\s*" + re.escape(title) + r"\s*$\n(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    if not m:
        return ""
    for line in m.group(1).splitlines():
        s = line.strip()
        if s and not s.startswith(("#", ">", "<!--")):
            return s
    return ""


def strict_norm(name):
    """只去掉標點、空白與寫法差異（訊→信、英文大小寫），不改變詞義。"""
    return PUNCT_RE.sub("", str(name)).replace("訊", "信").lower()


def loose_norm(name):
    s = strict_norm(name)
    for suf in LOOSE_SUFFIXES:
        if s.endswith(suf) and len(s) > len(suf) + 1:
            return s[: -len(suf)]
    return s


def _setting_rows(book_dir):
    rows = []
    for sub in SETTING_SUBDIRS:
        folder = os.path.join(book_dir, "設定", sub)
        if not os.path.isdir(folder):
            continue
        for f in sorted(os.listdir(folder)):
            p = os.path.join(folder, f)
            if not (f.endswith(".md") and os.path.isfile(p)) or f.startswith("_"):
                continue
            fm, body = project.split_frontmatter(project.read_text(p))
            stem = os.path.splitext(f)[0]
            aliases = fm.get("別名") or []
            if isinstance(aliases, str):
                aliases = [a.strip() for a in ALIAS_SPLIT_RE.split(aliases) if a.strip()]
            rows.append({
                "name": str(fm.get("名稱") or stem),
                "aliases": [str(a) for a in aliases],
                "category": str(fm.get("分類") or "").strip(),
                "status": str(fm.get("狀態") or "").strip(),
                "summary": _first_line(body, "一句話")[:80],
                "file": project.rel_of(book_dir, p),
                "sub": sub,
            })
    return rows


def _glossary_rows(book_dir):
    p = os.path.join(book_dir, GLOSSARY_REL)
    if not os.path.isfile(p):
        return []
    rows = []
    for line in project.read_text(p).splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] == "名詞" or set(cells[0]) <= set("-: "):
            continue
        names = [n.strip() for n in cells[0].split("／") if n.strip()]
        if not names:
            continue
        note = cells[3] if len(cells) > 3 else ""
        ch = re.search(r"首次出現[：:]\s*第\s*(\d+)\s*章", note)
        ref = re.search(r"詳見\s*(\S+?\.md)", note)
        rows.append({
            "name": names[0],
            "aliases": names[1:],
            "category": cells[1],
            "chapter": int(ch.group(1)) if ch else None,
            "ref": ref.group(1) if ref else "",
        })
    return rows


def duplicates(settings, glossary):
    """找疑似重複的名稱組。
    - 嚴格：去掉標點與寫法差異後相同（例如「艾爾特雷門多」「艾爾・特雷門多」）→ 可以預設建議保留。
    - 近似：只差「星系／星域／星區／市」等層級詞（例如「凱利姆」「凱利姆星域」）→ 標成近似，請作者確認是不是同一個地方。
    至少要有一個設定檔成員；只出現在名詞表的名稱只顯示、不能合併。"""
    items = []
    for r in settings:
        for raw in [r["name"]] + r["aliases"]:
            items.append({"name": raw, "file": r["file"], "source": "設定檔", "sub": r["sub"]})
    for r in glossary:
        for raw in [r["name"]] + r["aliases"]:
            items.append({"name": raw, "file": r["ref"], "source": "名詞表", "sub": ""})

    def group_by(fn):
        g = {}
        for it in items:
            g.setdefault(fn(it["name"]), []).append(it)
        return g

    def make(key, mems, loose):
        uniq, seen = [], set()
        for m in mems:
            k = (m["name"], m["file"], m["source"])
            if k not in seen:
                seen.add(k)
                uniq.append(m)
        if len({m["name"] for m in uniq}) < 2:
            return None
        if not any(m["source"] == "設定檔" for m in uniq):
            return None
        setting_members = [m for m in uniq if m["source"] == "設定檔"]
        keep = next((m for m in setting_members if strict_norm(m["name"]) == m["name"].lower()), setting_members[0])
        return {"key": key, "suggest": keep["file"], "loose": loose, "members": uniq}

    out = []
    for key, mems in group_by(strict_norm).items():
        g = make(key, mems, False)
        if g:
            out.append(g)
    for key, mems in group_by(loose_norm).items():
        # 只有「嚴格寫法不同」的成員被層級詞連在一起，才算近似組
        if len({strict_norm(m["name"]) for m in mems}) < 2:
            continue
        g = make(key, mems, True)
        if g:
            out.append(g)
    return sorted(out, key=lambda g: (g["loose"], g["key"]))


def build(book_dir):
    settings = _setting_rows(book_dir)
    glossary = _glossary_rows(book_dir)
    return {
        "settings": settings,
        "glossary": glossary,
        "duplicates": duplicates(settings, glossary),
        "counts": {"settings": len(settings), "glossary": len(glossary)},
        "today": datetime.date.today().isoformat(),
    }


def _index_markdown(data):
    today = data["today"]
    lines = [
        "# 設定索引",
        "",
        "> 由工作台產生於 %s。這是產生物，請勿手動編輯；在設定集按「重建索引」即可覆蓋。" % today,
        "> 查詢或衝突檢查時先讀這份索引，只打開命中的檔案。",
        "",
        "## 設定檔（%d）" % len(data["settings"]),
        "格式：名稱｜別名｜分類｜狀態｜一句話｜路徑",
        "",
    ]
    for r in data["settings"]:
        lines.append("- %s｜%s｜%s｜%s｜%s｜%s" % (
            _clean(r["name"]), _clean("、".join(r["aliases"])), _clean(r["category"]),
            _clean(r["status"]), _clean(r["summary"]), r["file"]))
    lines += ["", "## 名詞表（%d）" % len(data["glossary"]), "格式：名詞｜別名｜類別｜首次出現章｜詳見", ""]
    for r in data["glossary"]:
        lines.append("- %s｜%s｜%s｜%s｜%s" % (
            _clean(r["name"]), _clean("、".join(r["aliases"])), _clean(r["category"]),
            ("第%d章" % r["chapter"]) if r["chapter"] is not None else "",
            _clean(os.path.basename(r["ref"]))))
    lines += ["", "## 疑似重複（只列出，未自動合併）", ""]
    if data["duplicates"]:
        for g in data["duplicates"]:
            lines.append("- " + " ／ ".join(sorted({m["name"] for m in g["members"]})))
    else:
        lines.append("- （無）")
    lines.append("")
    return "\n".join(lines)


def rebuild(book_dir):
    data = build(book_dir)
    p = os.path.join(book_dir, INDEX_REL)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(_index_markdown(data))
    data["written"] = INDEX_REL
    return data


# ---------------------------------------------------------------------------
# 合併
# ---------------------------------------------------------------------------
def _check_setting_file(book_dir, rel):
    if not isinstance(rel, str) or not rel:
        raise project.ProjectError("檔案路徑格式錯誤")
    norm_rel = rel.replace("\\", "/").lstrip("/")
    if not norm_rel.startswith(MERGE_FOLDERS) or not norm_rel.endswith(".md"):
        raise project.ProjectError("只能合併 設定/角色、設定/勢力、設定/世界觀 裡的 .md 檔：" + rel)
    p = project.safe_path(book_dir, norm_rel)
    if not os.path.isfile(p):
        raise project.ProjectError("檔案不存在：" + rel)
    return norm_rel, p


def _aliases_of(fm):
    raw = fm.get("別名")
    if not raw:
        return []
    if isinstance(raw, str):
        return [a.strip() for a in ALIAS_SPLIT_RE.split(raw) if a.strip()]
    return [str(a).strip() for a in raw if str(a).strip()]


def _set_aliases(text, aliases):
    """改寫 frontmatter 的「別名」。會連同原本多行的 YAML 清單一起換掉，避免留下殘行。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return "---\n別名: %s\n---\n\n%s" % (json.dumps(aliases, ensure_ascii=False), text)
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise project.ProjectError("frontmatter 格式錯誤，無法寫入別名")
    new_line = "別名: %s" % json.dumps(aliases, ensure_ascii=False)
    out, i, done = [], 1, False
    out.append(lines[0])
    while i < end:
        line = lines[i]
        if line.startswith("別名:") or line.startswith("別名："):
            if not done:
                out.append(new_line)
                done = True
            i += 1
            # 跳過原本的續行（縮排或以 - 開頭的 YAML 清單項目）
            while i < end and (lines[i].startswith((" ", "\t", "-")) and not lines[i].startswith("---")):
                i += 1
            continue
        out.append(line)
        i += 1
    if not done:
        pos = next((k + 1 for k, l in enumerate(out) if l.startswith("類型:")), 1)
        out.insert(pos, new_line)
    out.extend(lines[end:])
    return "\n".join(out)


def merge(book_dir, canonical, duplicates_rel):
    canon_rel, canon_path = _check_setting_file(book_dir, canonical)
    if not isinstance(duplicates_rel, list) or not duplicates_rel:
        raise project.ProjectError("沒有勾選要併入的項目")
    folder = os.path.dirname(canon_rel)
    dups = []
    for rel in duplicates_rel:
        r, p = _check_setting_file(book_dir, rel)
        if r == canon_rel:
            raise project.ProjectError("保留的檔案不能同時勾選為併入")
        if os.path.dirname(r) != folder:
            raise project.ProjectError("只能合併同一類的設定（例如都是世界觀）：" + rel)
        if r in [d[0] for d in dups]:
            continue
        dups.append((r, p))

    today = datetime.date.today().isoformat()
    canon_text = project.read_text(canon_path)
    cfm, _ = project.split_frontmatter(canon_text)
    cname = str(cfm.get("名稱") or os.path.splitext(os.path.basename(canon_rel))[0])
    aliases = _aliases_of(cfm)

    sections = []
    for r, p in dups:
        fm, body = project.split_frontmatter(project.read_text(p))
        dname = str(fm.get("名稱") or os.path.splitext(os.path.basename(r))[0])
        for a in [dname] + _aliases_of(fm):
            if a and a != cname and a not in aliases:
                aliases.append(a)
        body_lines = body.strip("\n").split("\n")
        if body_lines and body_lines[0].startswith("# "):
            body_lines = body_lines[1:]
        # 併入的內容標題降一級，避免和保留檔的「一句話」等標題重複
        body_lines = [("#" + l) if l.startswith("## ") else l for l in body_lines]
        sections.append("\n\n## 併入：%s（%s，待核對）\n\n%s" % (dname, today, "\n".join(body_lines).strip()))

    # 1) 保留檔：加別名、附上併入內容
    new_text = _set_aliases(canon_text, aliases) if aliases else canon_text
    new_text = new_text.rstrip("\n") + "".join(sections) + "\n"
    with open(canon_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_text)

    # 2) 把指向舊檔的路徑改成保留檔（名詞表、其他設定檔）
    replacements = {r: canon_rel for r, _ in dups}
    refs_changed = []
    merged_abs = os.path.normpath(os.path.join(book_dir, MERGED_REL))
    targets = [os.path.join(book_dir, GLOSSARY_REL)]
    for root, _, files in os.walk(os.path.join(book_dir, "設定")):
        if os.path.normpath(root).startswith(merged_abs):
            continue
        targets += [os.path.join(root, f) for f in files if f.endswith(".md") and f != "_索引.md"]
    for tp in set(targets):
        if not os.path.isfile(tp):
            continue
        t = project.read_text(tp)
        new = t
        for old, newp in replacements.items():
            new = new.replace(old, newp)
        if new != t:
            with open(tp, "w", encoding="utf-8", newline="\n") as f:
                f.write(new)
            refs_changed.append(os.path.relpath(tp, book_dir).replace("\\", "/"))

    # 3) 舊檔移到 設定/_已合併/（不刪除）
    dest_dir = os.path.join(book_dir, MERGED_REL)
    os.makedirs(dest_dir, exist_ok=True)
    moved = []
    for r, p in dups:
        dest = os.path.join(dest_dir, os.path.basename(p))
        if os.path.exists(dest):
            stem, ext = os.path.splitext(os.path.basename(p))
            dest = os.path.join(dest_dir, "%s_%s%s" % (stem, datetime.datetime.now().strftime("%H%M%S"), ext))
        shutil.move(p, dest)
        moved.append({"from": r, "to": os.path.relpath(dest, book_dir).replace("\\", "/")})

    return {"canonical": canon_rel, "merged": moved, "aliases": aliases, "refs_changed": refs_changed}
