# -*- coding: utf-8 -*-
"""風格指紋的 CLI：python tools/fingerprint.py --book <書的資料夾> [--save] [--show]
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from studio import fingerprint, lang as lang_mod, prompts  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", required=True, help="書的資料夾（含 正文/、設定/）")
    ap.add_argument("--save", action="store_true", help="寫進 設定/風格指紋.json")
    ap.add_argument("--show", action="store_true", help="顯示現有的指紋（不重算）")
    ap.add_argument("--json", action="store_true", help="直接印 JSON（給程式用）")
    ap.add_argument("--samples", type=int, default=fingerprint.PICK, help="代表句幾句（預設 10）")
    a = ap.parse_args()

    book = os.path.abspath(a.book)
    if not os.path.isdir(book):
        raise SystemExit("找不到書的資料夾：%s" % book)
    prompts.set_lang(lang_mod.book_lang(book))

    if a.show and not a.save:
        data = fingerprint.load(book)
        if a.json:
            import json
            print(json.dumps(data, ensure_ascii=False, indent=1))
        else:
            print(fingerprint.show(data))
        return 0

    data = fingerprint.build(book, a.samples)
    if a.save:
        rel = fingerprint.save(book, a.samples)
        print("已寫入 %s（%d 句代表句）" % (rel, len(data["代表句"])))
    if a.json:
        import json
        print(json.dumps(data, ensure_ascii=False, indent=1))
    else:
        print(fingerprint.show(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
