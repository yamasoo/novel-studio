# -*- coding: utf-8 -*-
"""結構 DNA 的 CLI：python tools/sdna.py --book <書的資料夾> [--save] [--show] [--json]
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from studio import lang as lang_mod, prompts, sdna  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", required=True, help="書的資料夾（含 正文/）")
    ap.add_argument("--save", action="store_true", help="寫進 設定/結構DNA.json")
    ap.add_argument("--show", action="store_true", help="顯示現有的（不重算）")
    ap.add_argument("--json", action="store_true", help="直接印 JSON")
    a = ap.parse_args()

    book = os.path.abspath(a.book)
    if not os.path.isdir(book):
        raise SystemExit("找不到書的資料夾：%s" % book)
    prompts.set_lang(lang_mod.book_lang(book))

    if a.show and not a.save:
        data = sdna.load(book)
        if a.json:
            import json
            print(json.dumps(data, ensure_ascii=False, indent=1))
        else:
            print(sdna.show(data))
        return 0

    data = sdna.build(book)
    if a.save:
        rel = sdna.save(book)
        print("已寫入 %s" % rel)
    if a.json:
        import json
        print(json.dumps(data, ensure_ascii=False, indent=1))
    else:
        print(sdna.show(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
