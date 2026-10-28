#!/usr/bin/env python3
"""既有書的檔名修復：舊版匯入、整理名詞表、從正文建立設定會把檔名裡的空白全部吃掉
（例如英文書的 `第001章_ATTHEADMIRALBENBOW.md`、`JimHawkins.md`）。這個工具依檔案內容重新產生檔名。

用法：
  python tools/fix_filenames.py <書目錄>            只列出「舊名 → 新名」，不改任何檔案
  python tools/fix_filenames.py <書目錄> --apply    真的改名

處理範圍
  正文／候選      依檔案第一行標題（去掉「# 第N章」）重新產生 第NNN章_<標題>.md
  設定/角色、勢力、世界觀、草稿，追蹤/角色狀態
                  依 frontmatter 的「名稱」重新產生 <名稱>.md（追蹤/角色狀態 是用角色名稱原樣找檔，所以也要一起修）
新名已經存在、或兩個檔案會變成同一個新名時，跳過並列出。

改名後：設定/名詞表.md 的「詳見」欄和 設定/_索引.md 引用的是舊路徑，請到設定集按「重建索引」。
追蹤資料（伏筆、時間線…）引用的是章號，不受影響。"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import importer, project  # noqa: E402

CH_FILE = re.compile(r"^第(\d+)章_.*\.md$")
# 標題行開頭的章號：「# 第1章 」「# 第一章　」「# Chapter 3: 」「# CHAPTER III. 」「# 第3話 」
HEAD_NO = re.compile(r"^#+\s*(?:第\s*[0-9一二三四五六七八九十百千零〇]+\s*[章話话回]|chapter\s+[0-9ivxlc]+)\s*[:：.、\-—–]*\s*", re.I)
NAME_DIRS = ["設定/角色", "設定/勢力", "設定/世界觀", "設定/草稿", "追蹤/角色狀態"]


def first_heading(path):
    """檔案第一個「#」開頭的行（略過 frontmatter）；沒有就回傳 None。"""
    _, body = project.split_frontmatter(project.read_text(path))
    for line in body.split("\n"):
        if line.lstrip().startswith("#"):
            return line.strip()
        if line.strip():          # 標題之前就有內文：不是標準格式，不猜
            return None
    return None


def plan_chapters(book, sub):
    d = os.path.join(book, sub)
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        m = CH_FILE.match(f)
        if not m or not os.path.isfile(os.path.join(d, f)):
            continue
        head = first_heading(os.path.join(d, f))
        if not head:
            out.append((sub, f, None, "沒有標題行，略過"))
            continue
        title = HEAD_NO.sub("", head, count=1).lstrip("#").strip()
        new = "第%03d章_%s.md" % (int(m.group(1)), project.safe_filename(title, importer.MAX_TITLE))
        out.append((sub, f, new, None))
    return out


def plan_names(book, sub):
    d = os.path.join(book, sub)
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if not (os.path.isfile(p) and f.endswith(".md")) or f.startswith("_") or f.startswith("."):
            continue
        fm, _ = project.split_frontmatter(project.read_text(p))
        name = str(fm.get("名稱") or "").strip()
        if not name:
            out.append((sub, f, None, "frontmatter 沒有「名稱」，略過"))
            continue
        out.append((sub, f, project.safe_filename(name, 40) + ".md", None))
    return out


def build_plan(book):
    items = []
    for sub in ("正文", "候選"):
        items += plan_chapters(book, sub)
    for sub in NAME_DIRS:
        items += plan_names(book, sub)
    # 決定每一項：改名／不用改／跳過
    taken = {}      # (資料夾, 小寫新名) → 舊名；同一資料夾內新名不能重複
    for sub, f, new, why in items:
        if new and new != f:
            taken.setdefault((sub, new.lower()), f)
    result = []
    for sub, f, new, why in items:
        if why:
            result.append((sub, f, None, why))
        elif new == f:
            continue
        else:
            d = os.path.join(book, sub)
            clash = os.path.exists(os.path.join(d, new)) and new.lower() != f.lower()
            if clash:
                result.append((sub, f, new, "新名已存在，跳過"))
            elif taken[(sub, new.lower())] != f:
                result.append((sub, f, new, "會和「%s」變成同一個新名，跳過" % taken[(sub, new.lower())]))
            else:
                result.append((sub, f, new, None))
    return result


def main():
    ap = argparse.ArgumentParser(description="依檔案內容重新產生檔名（預設只預覽）")
    ap.add_argument("book", help="書目錄")
    ap.add_argument("--apply", action="store_true", help="真的改名（沒加只列出清單）")
    a = ap.parse_args()
    book = os.path.abspath(a.book)
    if not os.path.isdir(book):
        print("找不到書目錄：%s" % book)
        return 2
    plan = build_plan(book)
    todo = [x for x in plan if x[2] and not x[3]]
    skipped = [x for x in plan if x[3]]
    if not plan:
        print("檔名都正確，不用修。")
        return 0
    for sub, f, new, why in plan:
        if not why:
            print("%s/%s  →  %s" % (sub, f, new))
    if skipped:
        print("\n跳過 %d 項：" % len(skipped))
        for sub, f, new, why in skipped:
            print("  %s/%s%s：%s" % (sub, f, "  →  " + new if new else "", why))
    print("\n可改名 %d 項。" % len(todo))
    if not a.apply:
        print("這是預覽，沒有改任何檔案。確認清單沒問題後，加 --apply 才會改名。")
        return 0
    done, failed = 0, 0
    for sub, f, new, _ in todo:
        try:
            os.rename(os.path.join(book, sub, f), os.path.join(book, sub, new))
            done += 1
        except OSError as e:
            failed += 1
            print("改名失敗：%s/%s → %s（%s）" % (sub, f, new, e))
    print("已改名 %d 項%s。" % (done, "，失敗 %d 項" % failed if failed else ""))
    if done:
        print("提醒：請到設定集按「重建索引」，更新 設定/名詞表.md 的「詳見」欄和 設定/_索引.md 引用的路徑。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
