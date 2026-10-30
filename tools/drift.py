# -*- coding: utf-8 -*-
"""漂移偵測的 CLI：python tools/drift.py --book <書的資料夾> [--from N --to M] [--provider id]"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from studio import drift, lang as lang_mod, prompts  # noqa: E402


def write_plan(path, book, d, res):
    """把「更新卷綱」草稿寫到指定檔案（預設放在候選/，不會蓋掉大綱）。"""
    a, b = d["range"]
    L = ["# 卷綱更新草稿（第%d–%d 章漂移報告）" % (a, b), "",
         "> 由 `tools/drift.py --provider` 產生，請自己看過再貼回卷綱。", ""]
    for key, label in (("missed", "卷綱有、實際沒寫到"), ("added", "實際有、卷綱沒安排"),
                       ("vanished", "卷綱有、章節沒出現的角色")):
        items = res.get(key) or []
        if items:
            L.append("## " + label)
            L += ["- " + str(x) for x in items]
            L.append("")
    if res.get("plan"):
        L.append("## 建議改卷綱")
        L += ["- " + str(x) for x in res["plan"]]
        L.append("")
    if res.get("note"):
        L += ["> " + str(res["note"]), ""]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    print("- 卷綱更新草稿：%s" % path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", required=True, help="書的資料夾（含 正文/、設定/、大綱/）")
    ap.add_argument("--from", dest="start", type=int, help="從第幾章開始（預設：最後 10 章）")
    ap.add_argument("--to", dest="end", type=int, help="到第幾章（預設：最後一章）")
    ap.add_argument("--idle", type=int, default=drift.IDLE_CHARS, help="幾章沒登場算消失")
    ap.add_argument("--thread-age", type=int, default=drift.THREAD_AGE, help="伏筆幾章沒處理算欠帳")
    ap.add_argument("--provider", help="用真 provider 做一次輕量版比對（只送摘要與卷綱）")
    ap.add_argument("--out", help="把報告寫成這個 .md")
    ap.add_argument("--plan-out", help="把 LLM 產生的「更新卷綱」草稿寫成這個 .md（要一起給 --provider）")
    a = ap.parse_args()

    book = os.path.abspath(a.book)
    if not os.path.isdir(book):
        raise SystemExit("找不到書的資料夾：%s" % book)
    prompts.set_lang(lang_mod.book_lang(book))

    d = drift.drift(book, a.start, a.end, a.idle, a.thread_age)
    print(drift.report_md(book, d))
    if a.provider:
        from studio import providers
        prov = providers.resolve(providers.DEFAULT_PROVIDERS, a.provider)
        if not prov:
            raise SystemExit("找不到執行者：%s" % a.provider)
        res = drift.llm_pass(prov, book, d)
        if res.get("error"):
            print("\n（LLM 比對失敗：%s）" % res["error"])
        else:
            print("\n## LLM 比對（只讀摘要與卷綱）")
            for k, label in (("missed", "卷綱有、摘要沒看到"), ("added", "摘要有、卷綱沒安排"),
                             ("vanished", "卷綱有、章節沒出現的角色")):
                for it in (res.get(k) or [])[:8]:
                    print("- [%s] %s" % (label, it))
            for it in (res.get("plan") or [])[:5]:
                print("- [建議改卷綱] %s" % it)
            if res.get("note"):
                print("- 備註：%s" % res["note"])
            if a.plan_out and (res.get("plan") or res.get("missed") or res.get("added")):
                write_plan(a.plan_out, book, d, res)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(drift.report_md(book, d))
        print("\n報告已寫到 %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
