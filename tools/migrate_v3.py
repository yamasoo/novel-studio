# -*- coding: utf-8 -*-
"""書的格式移轉（v3）。

  python tools/migrate_v3.py <書資料夾或書庫資料夾> --dry-run   # 只列出要做什麼，不動檔案
  python tools/migrate_v3.py <書資料夾或書庫資料夾>             # 實際轉換（先整本備份成 zip）
  python tools/migrate_v3.py <書資料夾> --rollback               # 用最近一次移轉前的備份還原

可以重複執行：已經轉好的書直接跳過。轉換前後的統計（章數、字數、條目數、表格列數）對不上會自動還原。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import migrate, project  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="書的格式移轉（v3）")
    ap.add_argument("path", help="一本書的資料夾，或整個書庫")
    ap.add_argument("--dry-run", action="store_true", help="只列出要做什麼，不動檔案")
    ap.add_argument("--rollback", action="store_true", help="用最近一次移轉前的備份還原（只能指定一本書）")
    a = ap.parse_args(argv)
    path = os.path.abspath(a.path)
    if not os.path.isdir(path):
        print("找不到資料夾：%s" % a.path)
        return 2
    if a.rollback:
        if not migrate.is_book(path):
            print("還原只能指定一本書")
            return 2
        try:
            zp = migrate.rollback(path)
        except project.ProjectError as e:
            print(str(e))
            return 1
        print("已用 %s 還原" % os.path.basename(zp))
        return 0
    books = migrate.books_in(path)
    if not books:
        print("這個資料夾裡沒有書")
        return 2
    bad = 0
    if not migrate.is_book(path):          # 書庫：共用資料夾也要轉
        try:
            for line in migrate.migrate_library(path, dry_run=a.dry_run):
                print("== 書庫共用資料夾：%s" % line)
        except project.ProjectError as e:
            print("== 書庫共用資料夾：%s" % e)
            bad += 1
    for b in books:
        r = migrate.migrate(b, dry_run=a.dry_run)
        print("== %s：%s" % (r["book"], {"skipped": "已是最新格式", "dry_run": "要轉換（試跑，沒有動檔案）",
                                         "done": "轉換完成", "rolled_back": "失敗，已還原"}[r["status"]]))
        for s in r["steps"]:
            print("  [%s]" % s["title"])
            for c in s["changes"]:
                print("    - %s" % c)
        if r.get("message") and r["status"] != "skipped":
            print("  " + r["message"])
        if r.get("report"):
            print("  報告：%s" % os.path.relpath(r["report"], b))
        bad += r["status"] == "rolled_back"
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
