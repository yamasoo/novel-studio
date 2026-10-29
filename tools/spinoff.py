# -*- coding: utf-8 -*-
"""產生新書骨架的 CLI：
python tools/spinoff.py --from <參考書> --provider <執行者> [--to <新書資料夾>] [--note "..."]
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from studio import lang as lang_mod, project, prompts, spinoff  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", required=True, help="參考書（提供風格與結構）")
    ap.add_argument("--provider", help="API 執行者 id（預設用設定裡的）")
    ap.add_argument("--to", dest="dst", help="要存進哪本書（會寫到 候選/新書草稿/）；不給就只印出來")
    ap.add_argument("--note", default="", help="給模型的補充（題材、想要的感覺…）")
    ap.add_argument("--json", action="store_true", help="印 JSON")
    a = ap.parse_args()

    src = os.path.abspath(a.src)
    if not os.path.isdir(src):
        raise SystemExit("找不到參考書：%s" % src)
    if a.dst and not os.path.isdir(a.dst):
        raise SystemExit("找不到要存進去的書：%s（先用 tools/spawn.py 建一本）" % a.dst)

    prompts.set_lang(lang_mod.book_lang(src))
    prov = spinoff.provider(a.provider)
    data = spinoff.generate(prov, src, a.note)

    if a.json:
        import json
        print(json.dumps(data, ensure_ascii=False, indent=1))
    else:
        print(spinoff.show(data))
    if a.dst:
        rel = spinoff.save(os.path.abspath(a.dst), data)
        print("已寫入 %s" % rel)
    return 0 if not (data.get("護欄") or {}).get("撞到名字") else 1


if __name__ == "__main__":
    sys.exit(main())
