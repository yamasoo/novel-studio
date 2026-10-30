#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""章綱體檢：拿角色設定回頭對 大綱/章綱，正文還沒寫就先抓劇透與久別重逢。

用法：python tools/card_audit.py --book <書> [--from N --to M]

有衝突回傳 1。規則跟 tools/contract_audit.py 相同（共用 studio/upcheck.py）。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from studio import project, upcheck  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", required=True)
    ap.add_argument("--from", dest="start", type=int)
    ap.add_argument("--to", dest="end", type=int)
    a = ap.parse_args()
    book = os.path.abspath(a.book)
    if not os.path.isdir(book):
        raise SystemExit("找不到書：%s" % book)
    cards = project._scan_dir(os.path.join(book, "大綱", "章綱"))
    if not cards:
        print("這本書沒有章綱可以檢查。")
        return 0
    end = int(a.end or max(cards))
    rows = upcheck.findings(book, a.start or 1, end, cards=True)
    if not rows:
        print("章綱沒有發現衝突（第 %s–%s 章）。" % (a.start or 1, end))
        return 0
    print("發現 %d 處（第 %s–%s 章）：" % (len(rows), a.start or 1, end))
    for r in rows:
        print("  第%d章「%s」（%s）：%s" % (r["chapter"], r["name"], r["kind"], r["detail"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
