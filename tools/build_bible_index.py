#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令列版：重新產生 設定/_索引.md。
和設定集的「重建索引」按鈕用同一套程式（studio/bible_index.py），結果一致，不呼叫 AI。

用法（在工作台資料夾執行，建議用 .venv 的 Python）：
    python tools/build_bible_index.py "C:\\路徑\\某本書的資料夾"
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from studio import bible_index  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print('用法：python tools/build_bible_index.py "書的資料夾"')
        return 1
    book = os.path.abspath(sys.argv[1])
    if not os.path.isdir(os.path.join(book, "設定")):
        print("找不到「設定」資料夾：%s" % book)
        return 1
    data = bible_index.rebuild(book)
    print("已寫入：%s" % os.path.join(book, bible_index.INDEX_REL))
    print("設定檔 %d 筆，名詞表 %d 筆，疑似重複 %d 組" % (
        data["counts"]["settings"], data["counts"]["glossary"], len(data["duplicates"])))
    for g in data["duplicates"][:20]:
        print("  - " + " ／ ".join(sorted({m["name"] for m in g["members"]})))
    if len(data["duplicates"]) > 20:
        print("  ……另有 %d 組，見索引檔" % (len(data["duplicates"]) - 20))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main())
