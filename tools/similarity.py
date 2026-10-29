# -*- coding: utf-8 -*-
"""相似度比對：python tools/similarity.py --source <書> --new <稿子或章節> [--lang zh-TW]

用來看「這份新稿和來源書有多像」。門檻依語言不同（見 docs/P6-相似度基準.md）。
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from studio import contract, project, similarity  # noqa: E402

LIMITS = similarity.LIMITS


def book_text(d):
    ch = project._scan_dir(os.path.join(d, "正文"))
    return "\n".join(project.split_frontmatter(project.read_text(os.path.join(d, "正文", ch[no])))[1]
                     for no in sorted(ch))


def read_new(p):
    if os.path.isdir(p):
        return book_text(p)
    if not os.path.isfile(p):
        raise SystemExit("找不到要比對的檔案或資料夾：%s" % p)
    return project.read_text(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="來源書的資料夾（或一份 .md）")
    ap.add_argument("--new", required=True, help="要比對的新稿：資料夾或 .md 檔")
    ap.add_argument("--lang", default="zh-TW", choices=sorted(LIMITS), help="門檻要用的語言")
    a = ap.parse_args()

    src = book_text(a.source) if os.path.isdir(a.source) else project.read_text(a.source)
    new = read_new(a.new)
    names = [c[0] for c in contract.characters(a.source)] if os.path.isdir(a.source) else []
    r = similarity.check(new, src, a.lang, names)
    m, sp = r["metrics"], r["span"]

    print("來源 %d 字、新稿 %d 字" % (len(src), len(new)))
    print("  containment：%.2f%%（門檻 %.0f%%）" % (m["containment"] * 100, m["limit_containment"] * 100))
    print("  jaccard：%.5f" % m["jaccard"])
    print("  最長共同片段：%d 字（門檻 %d）" % (sp["length"], m["limit_lcs"]))
    if sp["text"]:
        print("    片段：%s" % sp["text"][:60])
    if names:
        print("  命中來源角色名：%s" % ("、".join(r["names"]) if r["names"] else "沒有"))
    for p in r["paragraphs"][:5]:
        print("  第 %d 段有 %.0f%% 來自來源：%s…" % (p["paragraph"], p["containment"] * 100, p["preview"][:40]))

    if r["ok"]:
        print("\n結果：可以（沒有超過門檻）")
        return 0
    print("\n結果：**太像了**")
    for why in r["reasons"]:
        print("  - " + why)
    return 1


if __name__ == "__main__":
    sys.exit(main())
