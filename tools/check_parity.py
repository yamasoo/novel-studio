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
     三語本來就同形的字串（路徑、檔名、語言名稱）填 "=="，執行期直接顯示原文，不算漏翻。
  6. 提示詞包：鍵與 {變數} 是否一致、英文包有沒有中文句子、長度比例離群（可能漏翻或整段改寫）。
  7. 翻譯新鮮度：tools/i18n.lock.json 記下每個檔案上次同步時的雜湊；繁中改了但 en／ja 沒動 → WARN「待更新翻譯」。
  8. 示範書範本：demo/ 三語示範書的 `_範本/` 檔案集是否一致（新手照範本做，缺檔就是坑）。
  9. 術語表 i18n/glossary.tsv：語言檔與 README 有沒有用到「禁用譯法」，以及介面譯法是否與表一致。

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
# 同形標記：值填 "==" 表示三語相同（路徑、檔名、語言名稱）。執行期 static/i18n.js 會略過，
# 直接顯示中文原文；所以它讓覆蓋率能真的到 100%，而不是用假翻譯充數。
SAME = "=="
# 看起來就不需要翻譯的鍵（路徑、檔名、語言選單、範例佔位字串）
NEUTRAL_RX = re.compile(r"[/\\]|\.md\b|&#10;|^Language |^繁體中文$|^日本語$")
# 抽取器的已知雜訊：i18n_extract.py 把 JS 模板字串切壞了，真正的句子在原始碼裡（報告 §2.2 A1 註）。
# 修好抽取器之前先列在這裡，免得覆蓋率永遠被這幾條卡住。
LOCALE_IGNORE = {
    ').join("、")}；其他步驟用上面選的執行者。（設定 → 整章自動流程）',
    'title="這個動作目前只支援 Claude Code"',
    'badge ${/空章|重複|倒退|簡體/.test(f) ?',
    r"Panel.openForm('deslop',{chapter:${parseInt((f.path.match(/第0*(\d+)章/) || [])[1]) || 1},candidate:${f.path.startsWith(",
}
HAN = re.compile(r"[\u3400-\u9fff]")
KANA = re.compile(r"[\u3040-\u30ff]")
VAR = re.compile(r"\{[A-Za-z_0-9]*\}")
LOCK = os.path.join(ROOT, "tools", "i18n.lock.json")
DEMO_DIR = os.path.join(ROOT, "demo")
TEMPLATE_DIR = os.path.join("skills", "novel-setup", "templates")

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
            # 繁中專屬檔案（例：novel-deslop 的台灣用語表）不算漏引用
            miss = [x for x in miss if "skills/%s/%s" % (s, x) not in ALLOW_ONLY["zh"]]
            if miss:
                add("FAIL", "skill", "%s/%s 少了引用：%s" % (s, k, "、".join(miss)))
            extra = [x for x in r["refs"] if x not in base["refs"]]
            if extra:
                add("WARN", "skill", "%s/%s 多了引用：%s" % (s, k, "、".join(extra)))
            # 表格列數差太多通常代表整段漏翻
            if base["tables"] and abs(base["tables"] - r["tables"]) > max(2, base["tables"] * 0.25):
                add("WARN", "skill", "%s/%s 表格列數 %d≠%d（可能漏翻段落）" % (s, k, base["tables"], r["tables"]))


def templates():
    """範本檔名清單（繁中版為準；17 個 .md）。"""
    d = os.path.join(ROOT, "plugin", TEMPLATE_DIR)
    if not os.path.isdir(d):
        return []
    return sorted(fn for fn in os.listdir(d) if fn.endswith(".md"))


# ---------------------------------------------------------------------------
# 3. 範本骨架
# ---------------------------------------------------------------------------
def check_templates():
    base_dir = os.path.join(ROOT, "plugin", "skills", "novel-setup", "templates")
    if not os.path.isdir(base_dir):
        return
    for fn in templates():
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
    inv -= LOCALE_IGNORE                     # 抽取雜訊不列入覆蓋率
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
            add("WARN", "locale", "%s 有 %d 個路徑類字串沒翻（多半可以填 \"==\"）" % (fn, len(pathlike)))
        if stale:
            add("WARN", "locale", "%s 有 %d 個失效的舊鍵（原始碼已沒有這段字）" % (fn, len(stale)))
        for x in empty:
            add("FAIL", "locale", "%s 值是空的：%s" % (fn, x[:40]))
        # 同形標記只該用在「三語本來就一樣」的字串上；拿它蓋掉一句話是假覆蓋
        for x in sorted(set(d)):
            if d[x] != SAME or not HAN.search(x) or NEUTRAL_RX.search(x):
                continue
            add("WARN", "locale", "%s 用同形標記蓋掉含中文的句子（確認真的是路徑／專有名詞）：%s" % (fn, x[:40]))


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
def demo_books():
    """三語示範書：資料夾名 en_／ja_ 開頭的是譯本，其餘視為繁中示範書。"""
    if not os.path.isdir(DEMO_DIR):
        return {}
    found = {}
    for name in sorted(os.listdir(DEMO_DIR)):
        p = os.path.join(DEMO_DIR, name)
        if not os.path.isdir(p):
            continue
        if name.startswith("en_"):
            found.setdefault("en", p)
        elif name.startswith("ja_"):
            found.setdefault("ja", p)
        else:
            found.setdefault("zh", p)
    return found if len(found) == 3 else {}


def demo_units():
    """demo 三本示範書裡「相對路徑相同」的檔案才成組（正文檔名各語言不同，不成組）。"""
    books = demo_books()
    if not books:
        return []
    sets = {k: set(walk(v)) for k, v in books.items()}
    out = []
    for rel in sorted(set.intersection(*sets.values())):
        out.append(tuple(os.path.join(books[k], rel.replace("/", os.sep)) for k in ("zh", "en", "ja")))
    return out


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
    # 17 個範本：檔名固定中文，三邊同名同路徑，是最該被新鮮度鎖住的一群
    for fn in templates():
        rel = "skills/novel-setup/templates/%s" % fn
        out.append((os.path.join(ROOT, "plugin", rel), os.path.join(ROOT, "plugin-en", rel),
                    os.path.join(ROOT, "plugin-ja", rel)))
    # 示範書：新手照著抄的檔案，走鐘了也要看得見
    out.extend(demo_units())
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
# 8. 示範書的範本檔案集
# ---------------------------------------------------------------------------
def check_demo():
    books = demo_books()
    if not books:
        add("WARN", "demo", "找不到 demo/ 的三語示範書（資料夾名 en_／ja_ 開頭），跳過範本檔案集比較")
        return
    sets = {k: {p for p in walk(v) if p.startswith("_範本/")} for k, v in books.items()}
    base = sets["zh"]
    for k in ("en", "ja"):
        for p in sorted(base - sets[k]):
            add("WARN", "demo", "繁中示範書有 %s，%s 示範書沒有（新手照範本做會缺檔）" % (p, k))
        for p in sorted(sets[k] - base):
            add("WARN", "demo", "%s 示範書有 %s，繁中示範書沒有" % (k, p))


# ---------------------------------------------------------------------------
# 9. 術語表
# ---------------------------------------------------------------------------
def load_glossary():
    """i18n/glossary.tsv → [(zh, en, ja, {"en": [禁用…], "ja": [...]})]。"""
    p = os.path.join(ROOT, "i18n", "glossary.tsv")
    if not os.path.isfile(p):
        return []
    rows = []
    for line in read(p).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = line.split("\t")
        if len(cells) < 3:
            add("WARN", "glossary", "術語表有一行欄位不足（要 zh／en／ja 三欄）：%s" % line[:40])
            continue
        zh, en, ja = cells[0].strip(), cells[1].strip(), cells[2].strip()
        if (zh, en) == ("zh", "en"):          # 表頭
            continue
        banned = {"en": [], "ja": []}
        if len(cells) > 3 and cells[3].strip():
            for part in cells[3].split(";"):
                lang, _, terms = part.strip().partition(":")
                lang = lang.strip()
                if lang in banned:
                    banned[lang] = [t.strip() for t in terms.split("|") if t.strip()]
        rows.append((zh, en, ja, banned))
    return rows


def check_glossary():
    rows = load_glossary()
    if not rows:
        add("WARN", "glossary", "沒有 i18n/glossary.tsv，跳過術語檢查")
        return
    loc = {}
    for lang, fn in (("en", "en.json"), ("ja", "ja.json")):
        p = os.path.join(ROOT, "static", "locales", fn)
        if os.path.isfile(p):
            loc[lang] = json.loads(read(p))
    docs = {"en": "README.en.md", "ja": "README.ja.md"}
    texts = {lang: read(os.path.join(ROOT, fn)) for lang, fn in docs.items()}
    hits = []
    for zh, en, ja, banned in rows:
        canon = {"en": en, "ja": ja}
        for lang in ("en", "ja"):
            for term in banned[lang]:
                where = []
                keys = [k for k, v in loc.get(lang, {}).items() if isinstance(v, str) and term in v]
                if keys:
                    where.append("語言檔 %d 條（例：%s）" % (len(keys), keys[0][:24]))
                if term in texts.get(lang, ""):
                    where.append(docs[lang])
                if where:
                    hits.append((lang, term, zh, canon[lang], "、".join(where)))
    for lang, term, zh, want, where in hits[:10]:
        add("WARN", "glossary", "%s 用了禁用譯法「%s」，「%s」該用「%s」：%s" % (lang, term, zh, want, where))
    if len(hits) > 10:
        add("WARN", "glossary", "另有 %d 條禁用譯法命中（先修上面 10 條）" % (len(hits) - 10))
    # 表與實作不能各說各話：介面有這個 key，值就該跟表一樣
    for lang in ("en", "ja"):
        for zh, _, ja, _banned in rows:
            want = ja if lang == "ja" else _
            have = loc.get(lang, {}).get(zh)
            if isinstance(have, str) and have != want and have != SAME:
                add("WARN", "glossary", "%s.json 的「%s」是「%s」，術語表定的是「%s」" % (lang, zh, have, want))


# ---------------------------------------------------------------------------
def main():
    global ROOT, LOCK, DEMO_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", metavar="DIR", help="專案根目錄（預設：這支腳本的上一層）")
    ap.add_argument("--strict", action="store_true", help="WARN 也回傳 1")
    ap.add_argument("--json", metavar="PATH", help="另存 JSON 結果")
    ap.add_argument("--update-lock", action="store_true", help="更新 tools/i18n.lock.json")
    args = ap.parse_args()
    if args.root:
        ROOT = os.path.abspath(args.root)
        LOCK = os.path.join(ROOT, "tools", "i18n.lock.json")
        DEMO_DIR = os.path.join(ROOT, "demo")
    if args.update_lock:
        update_lock()
        return 0
    for fn in (check_plugin_files, check_skills, check_templates, check_readme,
               check_locales, check_prompts, check_freshness, check_demo, check_glossary):
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
