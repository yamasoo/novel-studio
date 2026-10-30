# -*- coding: utf-8 -*-
"""卷綱狀態轉正：把「正式路徑」裡狀態還是草稿的卷綱，備份後標成已確認。

背景：舊的「卷綱」直寫入口會把 AI 產出的卷綱直接寫進 大綱/卷綱_第N卷.md，
但範本預設 `狀態: 草稿`。這些檔案一直被閘門與續寫合約當成正式（因為不看狀態），
只是標籤說謊；新流程（開新卷→採用／修訂→套用）一律會寫「已確認」。

用法（不花錢、不呼叫模型）：

    python tools/volume_status.py                 # 只列出，不寫檔
    python tools/volume_status.py --apply         # 備份後把狀態改成已確認
    python tools/volume_status.py --book 某本書   # 只處理一本
    python tools/volume_status.py --no-acts       # 不處理「幕」，只處理「卷」

書庫預設讀 config.json 的 library；也可以用 --library 指定。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from studio import project, tracking, volume  # noqa: E402


def config_library():
    p = os.path.join(ROOT, "config.json")
    try:
        with open(p, encoding="utf-8") as f:
            return (json.load(f).get("library") or "").strip()
    except (OSError, ValueError):
        return ""


def findings(library, book=None, acts=True):
    """回傳 [(書名, 書資料夾, 卷綱 dict)]，只收正式路徑且狀態是草稿的。"""
    out = []
    if not library or not os.path.isdir(library):
        return out
    for name in sorted(os.listdir(library)):
        d = os.path.join(library, name)
        if not os.path.isdir(d) or name.startswith(".") or name == "_共用":
            continue
        if book and name != book:
            continue
        if not project.is_book(d):
            continue
        for v in volume.list_volumes(d):
            if str(v.get("status") or "").strip() != "草稿":
                continue
            if v.get("kind") == "幕" and not acts:
                continue
            out.append((name, d, v))
    return out


def show(rows):
    if not rows:
        print("沒有「正式路徑＋狀態草稿」的卷綱。")
        return
    print("共 %d 份（正式路徑、狀態草稿）：" % len(rows))
    now = None
    for name, _d, v in rows:
        if name != now:
            print("\n== %s" % name)
            now = name
        print("   %-24s %s  第%s–%s章" % (v["rel"], v["kind"], v["lo"], v["hi"]))


def apply(rows, dry=False):
    """備份後把狀態改成已確認；回傳 (成功數, 失敗清單)。"""
    done, fails = 0, []
    for name, d, v in rows:
        p = project.safe_path(d, v["rel"])
        try:
            tracking.backup(d, p, "卷綱狀態轉正前")
            text = project.read_text(p)
            new = project.set_frontmatter_field(text, "狀態", "已確認")
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(new if new.endswith("\n") else new + "\n")
            os.replace(tmp, p)
            done += 1
            print("   已轉正：%s / %s" % (name, v["rel"]))
        except Exception as e:
            fails.append("%s / %s：%s" % (name, v["rel"], e))
            print("   失敗：%s / %s（%s）" % (name, v["rel"], e))
    return done, fails


def main(argv=None):
    ap = argparse.ArgumentParser(description="把正式路徑裡狀態草稿的卷綱轉成已確認（會先備份）")
    ap.add_argument("--library", help="書庫路徑；預設讀 config.json 的 library")
    ap.add_argument("--book", help="只處理這一本書（資料夾名稱）")
    ap.add_argument("--no-acts", action="store_true", help="不處理「幕」，只處理「卷」")
    ap.add_argument("--apply", action="store_true", help="真的寫檔（預設只列出）")
    args = ap.parse_args(argv)

    library = os.path.abspath(args.library) if args.library else config_library()
    if not library:
        print("找不到書庫：請用 --library 指定，或在設定頁設定書庫。")
        return 2
    rows = findings(library, args.book, acts=not args.no_acts)
    show(rows)
    if not args.apply:
        print("\n（只列出，沒有寫檔；要真的改狀態請加 --apply）")
        return 0
    if not rows:
        return 0
    print("\n開始轉正（每份都會先備份到該書的 .studio/備份/）…")
    done, fails = apply(rows)
    print("\n完成：轉正 %d 份，失敗 %d 份。" % (done, len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
