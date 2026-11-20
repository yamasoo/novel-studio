# -*- coding: utf-8 -*-
"""v3 結構英文化：盯住程式裡還沒換成 studio.layout 常數的中文路徑字串。

找的是「看起來像書裡的路徑」的字串常數（docstring、註解不算）：
  - 含 "/" 且有中文的字串（"設定/文風.md"、"追蹤/角色狀態/%s.md"）
  - 有中文的 .md／.json 檔名（"文風.md"、"目前.json"）
  - 等於 layout 第一層資料夾名稱的字串（"正文"、"候選"…）——可能是路徑，也可能是顯示文字，一併列出待人工判斷
不檢查：studio/layout.py 與 studio/ids.py 本身、studio/prompts/（提示詞內文，P4 處理）、tests/、tools/。
行尾有「# literal-ok: 原因」的不算：人工判斷過不是路徑（API 鍵、顯示文字、列舉值），或要到之後的階段才換。

用法
  python tools/check_literals.py                 # 列出各檔數量
  python tools/check_literals.py -v              # 連同每一處的行號與字串
  python tools/check_literals.py --check         # 任何檔案比基準多就失敗（CI 用）
  python tools/check_literals.py --update-baseline  # 換掉一批後，把基準往下調

基準檔：tools/check_literals.baseline.json（只能往下調；數字變大代表有人新寫了中文路徑）
"""
import argparse
import ast
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from studio import layout  # noqa: E402

BASELINE = os.path.join(ROOT, "tools", "check_literals.baseline.json")
HAN = re.compile(r"[一-鿿]")
TOP = {v for k, v in layout.all_constants().items() if isinstance(v, str) and "/" not in v and k != "STUDIO"}


def targets():
    files = [os.path.join(ROOT, "app.py"), os.path.join(ROOT, "ns_jobs.py")]
    files += sorted(glob.glob(os.path.join(ROOT, "studio", "*.py")))
    # layout.py（路徑）與 ids.py（舊 ID 別名表）是唯一允許寫 v2 中文名稱的地方
    return [f for f in files if os.path.basename(f) not in ("layout.py", "ids.py")]


def _docstring_ids(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            b = n.body[0]
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant):
                out.add(id(b.value))
    return out


def kind_of(v):
    if not HAN.search(v):
        return None
    if len(v) > 60 or "\n" in v:
        return None                      # 長句、提示詞片段
    if re.fullmatch(r"[^\s，。：、（）「」]+(/[^\s，。：、（）「」]*)+", v):
        return "path"
    if re.fullmatch(r"[^\s/，。：]+\.(md|json|jsonl|txt)", v):
        return "file"
    if v in TOP:
        return "top"
    return None


def scan(path):
    src = open(path, encoding="utf-8").read()
    lines = src.split("\n")
    tree = ast.parse(src)
    docs = _docstring_ids(tree)
    hits = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            if "literal-ok" in lines[n.lineno - 1]:      # 人工判斷過不是路徑（或之後的階段才換），行尾註明原因
                continue
            k = kind_of(n.value)
            if k:
                hits.append((n.lineno, k, n.value))
    return sorted(hits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    a = ap.parse_args()

    counts, detail = {}, {}
    for f in targets():
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        h = scan(f)
        if h:
            counts[rel] = len(h)
            detail[rel] = h
    total = sum(counts.values())

    if a.update_baseline:
        with open(BASELINE, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"total": total, "files": dict(sorted(counts.items()))}, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print("基準已更新：合計 %d" % total)
        return 0

    if a.check:
        if not os.path.exists(BASELINE):
            print("沒有基準檔，先跑 --update-baseline")
            return 1
        base = json.load(open(BASELINE, encoding="utf-8"))["files"]
        bad = [(f, n, base.get(f, 0)) for f, n in sorted(counts.items()) if n > base.get(f, 0)]
        if bad:
            print("下列檔案的中文路徑字串比基準多（請改用 studio/layout.py 的常數）：")
            for f, n, b in bad:
                print("  %s：%d（基準 %d）" % (f, n, b))
                for ln, k, v in detail[f]:
                    print("    %d  [%s] %s" % (ln, k, v))
            return 1
        print("OK：合計 %d（基準 %d）" % (total, sum(base.values())))
        return 0

    for f, n in sorted(counts.items(), key=lambda x: -x[1]):
        print("%4d  %s" % (n, f))
        if a.verbose:
            for ln, k, v in detail[f]:
                print("        %5d  [%s] %s" % (ln, k, v))
    print("合計 %d" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
