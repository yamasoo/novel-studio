# -*- coding: utf-8 -*-
"""續寫合約的零衝突掃描：只用既有檔案，不呼叫模型。

查三件事：
  1. 提前登場：某章提到某角色，但設定裡他「首次登場」在更後面（＝劇透）
  2. 已退場又出現：設定寫「最後登場」在某章，之後的章節又提到他
  3. 未登記角色：章節頁點名的人，在 設定/角色/ 裡沒有對應的檔案

用法：python tools/contract_audit.py --book <書> [--from N --to M]
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from studio import contract, project  # noqa: E402

# 「提前登場」：只是被提到（傳聞、對話）很正常，差 15 章以上才算真的劇透風險
SPOILER_GAP = 15
# 「久別重逢」：反派被打倒之後被回憶提起不算衝突，只看主角與配角
KEEP_ROLES = ("主角", "主要配角", "配角")
IDLE_GAP = 30


def _num(v):
    m = re.search(r"\d+", str(v or ""))
    return int(m.group(0)) if m else None


def audit(book_dir, start=None, end=None):
    ch = project._scan_dir(os.path.join(book_dir, "正文"))
    if not ch:
        return []
    end = int(end or max(ch))
    start = int(start or 1)
    chars = contract.characters(book_dir)
    out = []
    for no in sorted(n for n in ch if start <= n <= end):
        text = project.split_frontmatter(project.read_text(os.path.join(book_dir, "正文", ch[no])))[1]
        for name, pos, first, last in chars:
            if not name or len(name) < 2 or name not in text:
                continue
            f, l = _num(first), _num(last)
            if f and no < f and f - no >= SPOILER_GAP:
                out.append({"chapter": no, "name": name, "kind": "提前登場",
                            "detail": "設定的首次登場是第%d章，但第%d章就提到（早了 %d 章）"
                                      % (f, no, f - no)})
            elif (l and no > l + IDLE_GAP and any(k in str(pos or "") for k in KEEP_ROLES)):
                out.append({"chapter": no, "name": name, "kind": "久別重逢",
                            "detail": "最後登場記在第%d章，第%d章又出現（差了 %d 章）" % (l, no, no - l)})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", required=True)
    ap.add_argument("--from", dest="start", type=int)
    ap.add_argument("--to", dest="end", type=int)
    a = ap.parse_args()
    book = os.path.abspath(a.book)
    if not os.path.isdir(book):
        raise SystemExit("找不到書：%s" % book)

    rows = audit(book, a.start, a.end)
    if not rows:
        print("沒有發現衝突（第 %s–%s 章）" % (a.start or 1, a.end or "最後"))
        return 0
    print("發現 %d 處（第 %s–%s 章）：" % (len(rows), a.start or 1, a.end or "最後"))
    for r in rows:
        print("  第%d章「%s」（%s）：%s" % (r["chapter"], r["name"], r["kind"], r["detail"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
