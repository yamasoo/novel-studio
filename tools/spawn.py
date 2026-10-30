# -*- coding: utf-8 -*-
"""建專案的 CLI：python tools/spawn.py --from <參考書> --to <新書資料夾> --title <書名> [--cards 3]
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from studio import fingerprint, lang as lang_mod, project, prompts, sdna, spawn  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", required=True, help="參考書（要抽風格與結構的那本）")
    ap.add_argument("--to", dest="dst", required=True, help="新書的資料夾（必須不存在或空的）")
    ap.add_argument("--title", required=True, help="新書書名")
    ap.add_argument("--cards", type=int, default=3, help="先建幾張空白章綱（預設 3）")
    a = ap.parse_args()

    src = os.path.abspath(a.src)
    if not os.path.isdir(src):
        raise SystemExit("找不到參考書：%s" % src)
    prompts.set_lang(lang_mod.book_lang(src))
    fp = fingerprint.build(src)
    dna = sdna.build(src)
    try:
        res = spawn.create(a.dst, a.title, fp, dna, a.cards, source=os.path.basename(src))
    except project.ProjectError as e:
        raise SystemExit(str(e))

    print("已建立：%s（語言 %s）" % (res["target"], res["lang"]))
    for rel in res["created"]:
        print("  + " + rel)
    print("\n下一步：填 大綱/章綱/ 的章綱 → 在章節頁寫第一章。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
