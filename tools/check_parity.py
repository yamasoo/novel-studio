#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三語結構對等檢查（push 前跑；不需要模型、不花錢）。

    python tools/check_parity.py                 # 檢查，有 FAIL 回傳 1
    python tools/check_parity.py --strict        # WARN 也算失敗（CI 用）
    python tools/check_parity.py --json out.json # 另存機器可讀結果
    python tools/check_parity.py --update-lock   # 更新翻譯基準（tools/i18n.lock.json）

檢查的不是「譯得好不好」，而是「三份有沒有走鐘」：

  1. 外掛檔案：plugin/、plugin-en/、plugin-ja/ 的檔案清單是否對等（允許清單以外的缺檔／多檔都算 FAIL）。
  2. SKILL.md 骨架：標題層級分佈、程式碼區塊數、表格列數、references/scripts 連結、frontmatter 鍵。
  3. 範本：frontmatter 鍵、標題層級分佈（範本檔名固定中文，不比對檔名）。
  4. README：標題層級分佈與互連檔案是否存在。
  5. 介面翻譯：tools/i18n_keys.json 的鍵是否有 en／ja 翻譯、有沒有失效的舊鍵、空值。
  6. 提示詞包：鍵與 {變數} 是否一致、英文包有沒有中文句子、長度比例離群（可能漏翻或整段改寫）。
  7. 翻譯新鮮度：tools/i18n.lock.json 記下每個檔案上次同步時的雜湊；繁中改了但 en／ja 沒動 → WARN「待更新翻譯」。

為什麼要這支：check_i18n.py 驗的是「已存在的鍵彼此一致」，管不到「原始碼新增的字串根本沒進語言檔」，
也管不到三份 Markdown 的章節結構走鐘。這支補那兩個洞。
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDITIONS = {"zh": "plugin", "en": "plugin-en", "ja": "plugin-ja"}
SKILLS = ["novel-bible", "novel-deslop", "novel-outline", "novel-review",
          "novel-setup", "novel-style", "novel-write"]
# 三語本來就不該一樣的檔案（各自的語言版本、繁中專用的台灣用語表）
ALLOW_ONLY = {
    "zh": {"skills/novel-deslop/references/tw-terms.md"},
    "en": set(),
    "ja": set(),
}
ALLOW_DIFF_NAMES = {"plugin.json", "THIRD_PARTY_NOTICES.md"}
HAN = re.compile(r"[\u3400-\u9fff]")
KANA = re.compile(r"[\u3040-\u30ff]")
VAR = re.compile(r"\{[A-Za-z_0-9]*\}")
LOCK = os.path.join(ROOT, "tools", "i18n.lock.json")

results = []   # (level, area, message)


def add(level, area, msg):
    results.append((level, area, msg))


def read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def sha(p):
    try:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


def walk(base):
    out = []
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d != ".git"]
        for fn in fns:
            out.append(os.path.relpath(os.path.join(dp, fn), base).replace("\\", "/"))
    return sorted(out)


def frontmatter_keys(text):
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end < 0:
        return []
    keys = []
    for line in text[3:end].splitlines():
        m = re.match(r"^([^\s:#][^:]*):", line)
        if m:
            keys.append(m.group(1).strip())
    return keys


def outline(text):
    """標題層級分佈：{1: n, 2: n, 3: n}；程式碼區塊裡的 # 不算。"""
    dist, fence = {}, False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = re.match(r"^(#{1,6})\s", line)
        if m:
            dist[len(m.group(1))] = dist.get(len(m.group(1)), 0) + 1
    return dist


def count_fences(text):
    return sum(1 for line in text.splitlines() if line.strip().startswith("```")) // 2


def count_table_rows(text):
    fence = False
    n = 0
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
            continue
        if not fence and re.match(r"^\s*\|.*\|\s*$", line):
            n += 1
    return n


def ref_links(text):
    return sorted(set(re.findall(r"(?:references|scripts)/[\w./-]+", text)))


def diff_summary(a, b):
    keys = sorted(set(a) | set(b))
    return ["%s %s≠%s" % (k, a.get(k, 0), b.get(k, 0)) for k in keys if a.get(k, 0) != b.get(k, 0)]


# ---------------------------------------------------------------------------
# 1. 外掛檔案對等
# ---------------------------------------------------------------------------
def check_plugin_files():
    tree = {k: set(walk(os.path.join(ROOT, v))) for k, v in EDITIONS.items()}
    for k in tree:
        others = set().union(*[s for j, s in tree.items() if j != k])
        for p in sorted(tree[k] - others - ALLOW_ONLY[k]):
            if os.path.basename(p) in ALLOW_DIFF_NAMES:
                add("WARN", "plugin", "%s 獨有：%s（若為語言專屬內容，請加進 ALLOW_ONLY）" % (k, p))
            else:
                add("FAIL", "plugin", "%s 獨有：%s" % (k, p))


# ---------------------------------------------------------------------------
# 2. SKILL.md 骨架
# ---------------------------------------------------------------------------
def check_skills():
    for s in SKILLS:
        rows = {}
        for k, ed in EDITIONS.items():
            p = os.path.join(ROOT, ed, "skills", s, "SKILL.md")
            text = read(p)
            if not text:
                add("FAIL", "skill", "%s 缺 %s/SKILL.md" % (k, ed))
                continue
            rows[k] = {
                "outline": outline(text),
                "fences": count_fences(text),
                "tables": count_table_rows(text),
                "refs": ref_links(text),
                "fm": frontmatter_keys(text),
            }
        if len(rows) < 2:
            continue
        base = rows["zh"]
        for k in ("en", "ja"):
            if k not in rows:
                continue
            r = rows[k]
            d = diff_summary(base["outline"], r["outline"])
            if d:
                add("FAIL", "skill", "%s/%s 標題層級分佈不同：%s" % (s, k, "、".join(d)))
            if base["fences"] != r["fences"]:
                add("WARN", "skill", "%s/%s 程式碼區塊 %d≠%d" % (s, k, base["fences"], r["fences"]))
            if base["fm"] != r["fm"]:
                add("FAIL", "skill", "%s/%s frontmatter 鍵不同：%s≠%s" % (s, k, base["fm"], r["fm"]))
            miss = [x for x in base["refs"] if x not in r["refs"]]
            if miss:
                add("FAIL", "skill", "%s/%s 少了引用：%s" % (s, k, "、".join(miss)))
            extra = [x for x in r["refs"] if x not in base["refs"]]
            if extra:
                add("WARN", "skill", "%s/%s 多了引用：%s" % (s, k, "、".join(extra)))
            # 表格列數差太多通常代表整段漏翻
            if base["tables"] and abs(base["tables"] - r["tables"]) > max(2, base["tables"] * 0.25):
                add("WARN", "skill", "%s/%s 表格列數 %d≠%d（可能漏翻段落）" % (s, k, base["tables"], r["tables"]))


# ---------------------------------------------------------------------------
# 3. 範本骨架
# ---------------------------------------------------------------------------
def check_templates():
    base_dir = os.path.join(ROOT, "plugin", "skills", "novel-setup", "templates")
    if not os.path.isdir(base_dir):
        return
    for fn in sorted(os.listdir(base_dir)):
        if not fn.endswith(".md"):
            continue
        z = read(os.path.join(base_dir, fn))
        for k, ed in (("en", "plugin-en"), ("ja", "plugin-ja")):
            p = os.path.join(ROOT, ed, "skills", "novel-setup", "templates", fn)
            if not os.path.isfile(p):
                add("FAIL", "template", "%s 缺範本 %s" % (k, fn))
                continue
            t = read(p)
            if z and not t.strip():
                add("FAIL", "template", "%s 的 %s 是空檔" % (k, fn))
                continue
            d = diff_summary(outline(z), outline(t))
            if d:
                add("WARN", "template", "%s/%s 標題層級分佈不同：%s" % (k, fn, "、".join(d)))
            if frontmatter_keys(z) != frontmatter_keys(t):
                add("FAIL", "template", "%s/%s frontmatter 鍵不同：%s≠%s" % (k, fn, frontmatter_keys(z), frontmatter_keys(t)))


# ---------------------------------------------------------------------------
# 4. README
# ---------------------------------------------------------------------------
def check_readme():
    docs = {"zh": "README.md", "en": "README.en.md", "ja": "README.ja.md"}
    rows, texts = {}, {}
    for k, fn in docs.items():
        p = os.path.join(ROOT, fn)
        if not os.path.isfile(p):
            add("FAIL", "readme", "缺 %s" % fn)
            continue
        text = read(p)
        texts[k] = text
        rows[k] = {"outline": outline(text), "links": sorted(set(re.findall(r"\]\(([^)#]+)", text)))}
    if "zh" not in rows:
        return
    for k in ("en", "ja"):
        if k not in rows:
            continue
        d = diff_summary(rows["zh"]["outline"], rows[k]["outline"])
        if d:
            add("WARN", "readme", "%s 標題層級分佈與繁中不同：%s" % (docs[k], "、".join(d)))
        missing_targets = [x for x in rows[k]["links"] if x.startswith(("demo/", "tools/", "examples/", "plugin")) and not os.path.exists(os.path.join(ROOT, x.split("#")[0]))]
        for x in missing_targets:
            add("FAIL", "readme", "%s 連到不存在的路徑：%s" % (docs[k], x))
    # 互連
    for k in ("zh", "en", "ja"):
        if k in texts:
            others = [docs[j] for j in docs if j != k]
            for o in others:
                if o not in texts[k]:
                    add("WARN", "readme", "%s 沒有連到 %s" % (docs[k], o))


# ---------------------------------------------------------------------------
# 5. 介面翻譯覆蓋率
# ---------------------------------------------------------------------------
def check_locales():
    inv_path = os.path.join(ROOT, "tools", "i18n_keys.json")
    if not os.path.isfile(inv_path):
        add("WARN", "locale", "沒有 tools/i18n_keys.json，跳過覆蓋率檢查（先跑 tools/i18n_extract.py）")
        return
    inv = {k for k in json.loads(read(inv_path)) if not k.startswith("_")}
    for k, fn in (("en", "en.json"), ("ja", "ja.json")):
        p = os.path.join(ROOT, "static", "locales", fn)
        if not os.path.isfile(p):
            add("FAIL", "locale", "缺 static/locales/%s" % fn)
            continue
        d = json.loads(read(p))
        d = {x: y for x, y in d.items() if not x.startswith("_")}
        miss = sorted(inv - set(d))
        stale = sorted(set(d) - inv)
        empty = [x for x in inv & set(d) if isinstance(d[x], str) and not d[x].strip() and len(x.strip()) > 4]
        pathlike = [x for x in miss if "/" in x or x.endswith(".md")]
        real = [x for x in miss if x not in pathlike]
        if real:
            add("FAIL", "locale", "%s 有 %d 個介面字串沒翻（例：%s）" % (fn, len(real), "、".join(real[:3])))
        if pathlike:
            add("WARN", "locale", "%s 有 %d 個路徑類字串沒翻（多半可以原文照放）" % (fn, len(pathlike)))
        if stale:
            add("WARN", "locale", "%s 有 %d 個失效的舊鍵（原始碼已沒有這段字）" % (fn, len(stale)))
        for x in empty:
            add("FAIL", "locale", "%s 值是空的：%s" % (fn, x[:40]))


# ---------------------------------------------------------------------------
# 6. 提示詞包
# ---------------------------------------------------------------------------
def check_prompts():
    sys.path.insert(0, ROOT)
    try:
        import importlib
        packs = {n: importlib.import_module("studio.prompts." + n).T for n in ("zh_TW", "en", "ja")}
    except Exception as e:            # 匯入失敗（缺相依）就只警告
        add("WARN", "prompt", "無法載入提示詞包：%s" % e)
        return
    base = packs["zh_TW"]
    for n in ("en", "ja"):
        p = packs[n]
        for k in sorted(set(base) - set(p)):
            add("FAIL", "prompt", "%s 缺鍵：%s" % (n, k))
        for k in sorted(set(p) - set(base)):
            add("FAIL", "prompt", "%s 多出鍵：%s" % (n, k))
        for k in sorted(set(base) & set(p)):
            a, b = base[k], p[k]
            if not isinstance(a, str) or not isinstance(b, str):
                continue
            if a and sorted(set(VAR.findall(a))) != sorted(set(VAR.findall(b))):
                add("FAIL", "prompt", "%s 的 {變數} 不同：%s" % (n, k))
            if a and len(b) and k != "claude_out_lang":
                ratio = len(b) / len(a)
                if ratio < 0.35 or ratio > 4.5:
                    add("WARN", "prompt", "%s 的 %s 長度比例 %.2f（可能漏翻或整段改寫）" % (n, k, ratio))
        if n == "en":
            for k, v in p.items():
                if isinstance(v, str) and len(HAN.findall(v)) > 8:
                    add("WARN", "prompt", "英文包的 %s 還有中文句子" % k)


# ---------------------------------------------------------------------------
# 7. 翻譯新鮮度（lock 檔）
# ---------------------------------------------------------------------------
def units():
    """(繁中路徑, en 路徑, ja 路徑) 的清單：只收三邊都存在的檔案。"""
    out = []
    for s in SKILLS:
        for sub in ("", "references/", "scripts/"):
            z = "plugin/skills/%s/%s" % (s, sub)
            d = os.path.join(ROOT, z)
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if not os.path.isfile(os.path.join(d, fn)) or fn in ALLOW_ONLY["zh"]:
                    continue
                rel = "skills/%s/%s%s" % (s, sub, fn)
                zp = os.path.join(ROOT, "plugin", rel)
                ep = os.path.join(ROOT, "plugin-en", rel)
                jp = os.path.join(ROOT, "plugin-ja", rel)
                if os.path.isfile(ep) and os.path.isfile(jp):
                    out.append((zp, ep, jp))
    for fn in ("README.md",):
        out.append((os.path.join(ROOT, fn), os.path.join(ROOT, "README.en.md"), os.path.join(ROOT, "README.ja.md")))
    return out


def load_lock():
    if not os.path.isfile(LOCK):
        return None
    try:
        return json.loads(read(LOCK))
    except ValueError:
        return None


def update_lock():
    data = {"version": 1, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "units": {}}
    for zp, ep, jp in units():
        key = os.path.relpath(zp, ROOT).replace("\\", "/")
        data["units"][key] = {"zh": sha(zp), "en": sha(ep), "ja": sha(jp)}
    with open(LOCK, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print("已更新 %s（%d 組）" % (os.path.relpath(LOCK, ROOT), len(data["units"])))


def check_freshness():
    lock = load_lock()
    if not lock:
        add("WARN", "fresh", "沒有 tools/i18n.lock.json，跳過新鮮度檢查（第一次請跑 --update-lock）")
        return
    for zp, ep, jp in units():
        key = os.path.relpath(zp, ROOT).replace("\\", "/")
        rec = lock["units"].get(key)
        if not rec:
            add("WARN", "fresh", "新增檔案尚未登記翻譯基準：%s" % key)
            continue
        zh_moved = sha(zp) != rec["zh"]
        en_same = sha(ep) == rec["en"]
        ja_same = sha(jp) == rec["ja"]
        if zh_moved and (en_same or ja_same):
            need = [n for n, same in (("en", en_same), ("ja", ja_same)) if same]
            add("WARN", "fresh", "繁中改了、%s 沒動（待更新翻譯）：%s" % ("／".join(need), key))


# ---------------------------------------------------------------------------
def main():
    global ROOT, LOCK
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", metavar="DIR", help="專案根目錄（預設：這支腳本的上一層）")
    ap.add_argument("--strict", action="store_true", help="WARN 也回傳 1")
    ap.add_argument("--json", metavar="PATH", help="另存 JSON 結果")
    ap.add_argument("--update-lock", action="store_true", help="更新 tools/i18n.lock.json")
    args = ap.parse_args()
    if args.root:
        ROOT = os.path.abspath(args.root)
        LOCK = os.path.join(ROOT, "tools", "i18n.lock.json")
    if args.update_lock:
        update_lock()
        return 0
    for fn in (check_plugin_files, check_skills, check_templates, check_readme,
               check_locales, check_prompts, check_freshness):
        fn()
    order = {"FAIL": 0, "WARN": 1}
    results.sort(key=lambda r: (order.get(r[0], 2), r[1]))
    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    for level, area, msg in results:
        print("[%s] %-8s %s" % (level, area, msg))
    print("\n檢查完成：FAIL %d、WARN %d" % (len(fails), len(warns)))
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump([{"level": a, "area": b, "message": c} for a, b, c in results], f, ensure_ascii=False, indent=1)
        print("結果已寫入 %s" % args.json)
    if fails or (args.strict and warns):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
