# -*- coding: utf-8 -*-
"""書的格式移轉（v3 規格第 10 節）。工作台與 tools/migrate_v3.py 共用。

流程：偵測 → 備份（整本壓成 zip）→ 逐步轉換 → 轉換前後的統計比對 → 對不上就自動還原 → 寫報告。
- 每一步都能自己判斷「這本書還需不需要」（needed），所以可以重複執行；已經轉好的書直接跳過。
- P3 分批做：每一批加一步，最後一步把 book.json 的 schema_version 改成 3。
- 統計只比對「內容有沒有掉」：章數、正文總字數、章綱數、設定條目數、各追蹤表列數。
"""
import datetime
import os
import shutil
import zipfile

from . import bookmeta, context, layout, project

SKIP_DIRS = (".git",)                       # 不備份、不還原（作者自己的版本控制）


# ---------------------------------------------------------------------------
# 統計
# ---------------------------------------------------------------------------
def stats(book_dir):
    def n_entries(rel):
        return len(project.list_entries(book_dir, rel))

    def n_rows(rel):
        try:
            return len(project.read_table(book_dir, rel)["rows"])
        except project.ProjectError:
            return 0
    chs = project._scan_dir(layout.path(book_dir, layout.MANUSCRIPT))
    total = 0
    for f in chs.values():
        total += project.count_chars(context.body(project.read_text(layout.path(book_dir, layout.MANUSCRIPT, f))))
    return {
        "章數": len(chs),
        "正文總字數": total,
        "章綱": len(project._scan_dir(layout.path(book_dir, layout.CHAPTER_CARDS))),
        "章節摘要": len(project._scan_dir(layout.path(book_dir, layout.SUMMARIES))),
        "角色": n_entries(layout.CHARACTERS),
        "勢力": n_entries(layout.FACTIONS),
        "世界觀": n_entries(layout.WORLD),
        "伏筆": n_rows(layout.FORESHADOWING),
        "時間線": n_rows(layout.TIMELINE),
        "讀者認知": n_rows(layout.READER_KNOWLEDGE),
        "角色關係": n_rows(layout.RELATIONS),
        "名詞表": n_rows(layout.GLOSSARY),
    }


# ---------------------------------------------------------------------------
# 各步驟：needed(book_dir) → bool；apply(book_dir) → [說明]（只在不是 dry-run 時呼叫）；plan(book_dir) → [說明]
# ---------------------------------------------------------------------------
class Step:
    def __init__(self, key, title, needed, plan, apply):
        self.key, self.title, self.needed, self.plan, self.apply = key, title, needed, plan, apply


def _old_lang(book_dir):
    from . import lang
    return lang.normalize(bookmeta.read(book_dir).get("lang") or lang._fm_lang(book_dir) or lang._file_lang(book_dir))


def _meta_needed(book_dir):
    m = bookmeta.read(book_dir)
    return not m.get("lang") or "schema_version" not in m or os.path.isfile(layout.path(book_dir, layout.STUDIO, "lang"))


def _meta_plan(book_dir):
    out = []
    if not bookmeta.exists(book_dir):
        out.append("建立 %s（語言 %s）" % (layout.BOOK_META, _old_lang(book_dir)))
    elif not bookmeta.read(book_dir).get("lang"):
        out.append("%s 補上語言 %s" % (layout.BOOK_META, _old_lang(book_dir)))
    if os.path.isfile(layout.path(book_dir, layout.STUDIO, "lang")):
        out.append("移除 %s/lang（語言改記在 %s）" % (layout.STUDIO, layout.BOOK_META))
    return out or ["%s 補上格式版本" % layout.BOOK_META]


def _meta_apply(book_dir):
    out = _meta_plan(book_dir)
    bookmeta.write(book_dir, lang=_old_lang(book_dir))
    old = layout.path(book_dir, layout.STUDIO, "lang")
    if os.path.isfile(old):
        os.remove(old)
    return out


STEPS = [
    Step("book_meta", "書的身分證 book.json", _meta_needed, _meta_plan, _meta_apply),
]


# ---------------------------------------------------------------------------
# 備份與還原
# ---------------------------------------------------------------------------
def _backup_dir(book_dir):
    return layout.path(book_dir, layout.STUDIO_BACKUP)


def _walk_files(book_dir):
    skip_backup = os.path.normpath(_backup_dir(book_dir))
    for base, dirs, files in os.walk(book_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and os.path.normpath(os.path.join(base, d)) != skip_backup)
        for f in sorted(files):
            p = os.path.join(base, f)
            yield p, os.path.relpath(p, book_dir).replace(os.sep, "/")


def backup(book_dir):
    """整本書壓成 zip（不含 .git 與備份資料夾本身），回傳 zip 路徑；失敗丟例外（呼叫端要中止）。"""
    d = _backup_dir(book_dir)
    os.makedirs(d, exist_ok=True)
    name = layout.MIGRATE_BACKUP_PREFIX + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip"
    p = os.path.join(d, name)
    n = 1
    while os.path.exists(p):
        n += 1
        p = os.path.join(d, name.replace(".zip", "_%d.zip" % n))
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        for full, rel in _walk_files(book_dir):
            z.write(full, rel)
    with zipfile.ZipFile(p) as z:          # 確認壓縮檔可以讀
        if z.testzip() is not None:
            raise project.ProjectError("備份檔損壞：%s" % p)
    return p


def backups(book_dir):
    d = _backup_dir(book_dir)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.startswith(layout.MIGRATE_BACKUP_PREFIX) and f.endswith(".zip"))


def rollback(book_dir, zip_path=None):
    """用移轉前的備份還原：先清掉書裡的檔案（.git 與備份資料夾不動），再解壓。回傳用了哪一份備份。"""
    zs = [zip_path] if zip_path else backups(book_dir)
    if not zs or not zs[-1] or not os.path.isfile(zs[-1]):
        raise project.ProjectError("找不到移轉前的備份")
    zp = zs[-1]
    with zipfile.ZipFile(zp) as z:
        bad = [n for n in z.namelist() if n.startswith("/") or ".." in n.split("/")]
        if bad:
            raise project.ProjectError("備份檔裡有不安全的路徑：%s" % bad[0])
        for full, _ in list(_walk_files(book_dir)):
            os.remove(full)
        for base, dirs, _ in os.walk(book_dir, topdown=False):      # 清掉空資料夾（.git、備份除外）
            for d in dirs:
                p = os.path.join(base, d)
                if d in SKIP_DIRS or os.path.normpath(p) == os.path.normpath(_backup_dir(book_dir)):
                    continue
                if os.path.isdir(p) and not os.listdir(p):
                    os.rmdir(p)
        z.extractall(book_dir)
    return zp


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def pending(book_dir):
    return [s for s in STEPS if s.needed(book_dir)]


def is_book(d):
    if not os.path.isdir(d) or os.path.basename(d).startswith((".", "_")):
        return False
    return bookmeta.exists(d) or any(os.path.isdir(layout.path(d, x)) for x in (layout.MANUSCRIPT, layout.BIBLE))


def books_in(path):
    """傳進來的是一本書就回傳 [它]；是書庫就回傳底下每一本書。"""
    if is_book(path):
        return [path]
    return [os.path.join(path, n) for n in sorted(os.listdir(path)) if is_book(os.path.join(path, n))]


def _report(book_dir, lines):
    d = layout.path(book_dir, layout.STUDIO_REPORTS)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "migrate-v3_%s.md" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    project.write_atomic(p, "\n".join(lines).rstrip() + "\n")
    return p


def migrate(book_dir, dry_run=False, now=None):
    """回傳 {"status": "skipped"|"dry_run"|"done"|"rolled_back", "steps": [...], "report": 路徑, ...}。"""
    title = os.path.basename(os.path.normpath(book_dir))
    todo = pending(book_dir)
    if not todo:
        return {"book": title, "status": "skipped", "steps": [], "message": "已經是最新格式"}
    steps = [{"key": s.key, "title": s.title, "changes": s.plan(book_dir)} for s in todo]
    if dry_run:
        return {"book": title, "status": "dry_run", "steps": steps, "stats": stats(book_dir)}
    before = stats(book_dir)
    zp = backup(book_dir)
    done = []
    try:
        for s in todo:
            done.append({"key": s.key, "title": s.title, "changes": s.apply(book_dir)})
        after = stats(book_dir)
    except Exception as e:      # 任何一步失敗：整本還原
        rollback(book_dir, zp)
        return {"book": title, "status": "rolled_back", "steps": done, "backup": zp, "message": "轉換失敗，已還原：%s" % e}
    diff = {k: (before[k], after.get(k)) for k in before if before[k] != after.get(k)}
    if diff:
        rollback(book_dir, zp)
        return {"book": title, "status": "rolled_back", "steps": done, "backup": zp, "diff": diff,
                "message": "轉換前後的統計對不上，已還原：" + "、".join("%s %s → %s" % (k, a, b) for k, (a, b) in diff.items())}
    lines = ["# 格式移轉報告：%s" % title, "", "- 備份：%s" % os.path.relpath(zp, book_dir).replace(os.sep, "/"), ""]
    for s in done:
        lines += ["## %s" % s["title"]] + ["- " + c for c in s["changes"]] + [""]
    lines += ["## 統計（轉換前後相同）"] + ["- %s：%s" % (k, v) for k, v in before.items()]
    rp = _report(book_dir, lines)
    return {"book": title, "status": "done", "steps": done, "backup": zp, "stats": before, "report": rp}
