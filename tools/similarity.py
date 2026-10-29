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

# 實測的自然重複（同作者、後面的章節對前面的章節）：
#   zh-TW containment 0.034、最長共同 0 字
#   ja    containment 0.081、最長共同 0 字
#   en    containment 0.347、最長共同 33 字
LIMITS = {
    "zh-TW": {"containment": 0.10, "lcs": 20},
    "ja": {"containment": 0.20, "lcs": 20},
    "en": {"containment": 0.50, "lcs": 60},
}


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
    fp_src, fp_new = similarity.fingerprint(src), similarity.fingerprint(new)
    r = similarity.compare_prints(fp_src, fp_new)
    lcs = similarity.longest_common(src, new)
    names = [c[0] for c in contract.characters(a.source)] if os.path.isdir(a.source) else []
    hit = similarity.names_in(new, names)
    lim = LIMITS[a.lang]

    print("來源 %d 字、新稿 %d 字" % (len(src), len(new)))
    print("  containment（新稿的 6-gram 有多少在來源）：%.4f（門檻 %.2f）" % (r["containment"], lim["containment"]))
    print("  jaccard：%.5f" % r["jaccard"])
    print("  最長共同片段：%d 字（門檻 %d）" % (lcs, lim["lcs"]))
    if names:
        print("  命中來源角色名：%s（任何一個都不行）" % ("、".join(hit) if hit else "沒有"))

    bad = []
    if r["containment"] >= lim["containment"]:
        bad.append("6-gram 重疊 %.2f%% 超過 %.0f%%" % (r["containment"] * 100, lim["containment"] * 100))
    if lcs >= lim["lcs"]:
        bad.append("最長共同片段 %d 字（門檻 %d）" % (lcs, lim["lcs"]))
    if hit:
        bad.append("沿用了來源角色名：%s" % "、".join(hit))
    if bad:
        print("\n結果：**太像了**——" + "；".join(bad))
        return 1
    print("\n結果：可以（沒有超過門檻）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
