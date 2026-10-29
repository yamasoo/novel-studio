#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""翻譯缺口 → 初翻 patch（報告 T4）。不會直接改正式語言檔。

    python tools/i18n_fill.py --list                 # 看缺哪些、有哪些待核可的初翻
    python tools/i18n_fill.py --fill                 # 呼叫模型產出初翻 → i18n/pending/<lang>.json
    python tools/i18n_fill.py --fill --provider deepseek/api
    python tools/i18n_fill.py --apply                # 人工核可後，把 pending 併進 static/locales/
    python tools/i18n_fill.py --apply --lang ja

流程：缺口 → 初翻（術語表＋上下文，只送差異片段）→ 寫進 i18n/pending/ → 人工核可 → --apply。
模型只會寫 i18n/pending/，正式語言檔只有 --apply 會動，而且會先印出要新增幾條。

路徑、檔名、語言名稱這類三語同形的字串不送模型，直接建議 "=="（執行期顯示原文）。
不會呼叫模型的部分（--list／--apply）不需要 API 金鑰，CI 也不會跑這支。
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from studio import providers  # noqa: E402

CONFIG_PATH = os.path.join(ROOT, "config.json")
LOCALES = os.path.join(ROOT, "static", "locales")
PENDING = os.path.join(ROOT, "i18n", "pending")
GLOSSARY = os.path.join(ROOT, "i18n", "glossary.tsv")
INDEX = os.path.join(ROOT, "tools", "i18n_keys.json")
SAME = "=="
LANGS = ("en", "ja")
LANG_NAME = {"en": "English", "ja": "日本語"}


# ---------------------------------------------------------------------------
def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    try:
        return json.loads(read(path))
    except ValueError:
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def index_keys():
    """介面字串索引：{中文原文: 出現次數}。"""
    d = load_json(INDEX, {})
    return {k: v for k, v in d.items() if not k.startswith("_")}


def locale_keys(lang):
    d = load_json(os.path.join(LOCALES, lang + ".json"), {})
    return {k: v for k, v in d.items() if not k.startswith("_")}


def is_same_form(key):
    """三語本來就同形（路徑、檔名、語言名稱、範例佔位字串）→ 建議填 "=="。"""
    k = key.strip()
    if "/" in k or "\\" in k or k.endswith(".md") or "&#10;" in k:
        return True
    return k in {"繁體中文", "日本語", "English"} or k.startswith("Language ")


def ignored(key):
    """抽取器雜訊（與 tools/check_parity.py 的 LOCALE_IGNORE 同步）。"""
    sys.path.insert(0, HERE)
    try:
        import check_parity
        return key in check_parity.LOCALE_IGNORE
    except Exception:
        return False


def gaps(lang):
    """回傳 (要初翻的鍵, 建議填 "==" 的鍵, 失效舊鍵)。"""
    inv = index_keys()
    have = locale_keys(lang)
    todo, same = [], []
    for k in sorted(inv):
        if k in have or ignored(k):
            continue
        (same if is_same_form(k) else todo).append(k)
    stale = sorted(k for k in have if k not in inv)
    return todo, same, stale


def glossary_pairs():
    """術語表 → [(zh, en, ja)]，當作初翻的用語錨點。"""
    rows = []
    if not os.path.isfile(GLOSSARY):
        return rows
    for line in read(GLOSSARY).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = line.split("\t")
        if len(cells) < 3 or (cells[0], cells[1]) == ("zh", "en"):
            continue
        rows.append((cells[0].strip(), cells[1].strip(), cells[2].strip()))
    return rows


# ---------------------------------------------------------------------------
def pending_path(lang):
    return os.path.join(PENDING, lang + ".json")


def load_pending(lang):
    return load_json(pending_path(lang), {"lang": lang, "created": "", "proposals": {}})


def dump_review(lang, proposals, todo):
    """給人看的核可清單：一條一行，附上中文原文。"""
    os.makedirs(PENDING, exist_ok=True)
    p = os.path.join(PENDING, lang + ".review.md")
    lines = ["# %s 初翻待核可（%s）" % (lang, time.strftime("%Y-%m-%d %H:%M")), "",
             "核可後：`python tools/i18n_fill.py --apply --lang %s`，再跑" % lang,
             "`python tools/check_i18n.py`、`python tools/check_parity.py --update-lock`。", "",
             "| 中文原文 | 建議譯文 |", "|---|---|"]
    for k in todo:
        if k in proposals:
            lines.append("| %s | %s |" % (k.replace("|", "\\|"), str(proposals[k]).replace("|", "\\|")))
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return p


# ---------------------------------------------------------------------------
def pick_provider(pid=None):
    cfg = load_json(CONFIG_PATH, {}) or {}
    provs = cfg.get("providers") or providers.DEFAULT_PROVIDERS
    pid = pid or cfg.get("default_provider") or "claude_code"
    prov = providers.resolve(provs, pid)
    if not prov:
        raise SystemExit("找不到執行者：%s（用 --provider 指定，例如 --provider deepseek）" % pid)
    if prov.get("type") == "claude_code":
        raise SystemExit("Claude Code 不能用來初翻（這支工具要 OpenAI 相容的 /chat/completions）；"
                         "請用 --provider 指定 DeepSeek、llama.cpp 等執行者。")
    return prov


def translate(prov, lang, keys, counts):
    """一次送一批鍵，回傳 {中文原文: 譯文}。"""
    pairs = glossary_pairs()
    gl = "\n".join("%s\t%s\t%s" % row for row in pairs) if pairs else "（沒有術語表）"
    listed = "\n".join("%s\t（介面出現 %d 次）" % (k, counts.get(k, 1)) for k in keys)
    system = ("你是 Novel Studio 的介面翻譯。把繁體中文介面字串翻成 %s。\n"
              "規則：\n"
              "1. {0}、{1} 這類變數原樣保留，順序可以依語序調整，但不能增刪。\n"
              "2. 資料夾／檔名（例如 設定/故事核心.md、第NNN章）原樣保留，不要翻譯。\n"
              "3. 術語一律照下面的術語表，不要自己換說法。\n"
              "4. 只輸出 JSON 物件：key 是中文原文，value 是 %s 譯文；不要加說明或程式碼圍欄。\n\n"
              "術語表（中文\\t英文\\t日文）：\n%s" % (LANG_NAME[lang], LANG_NAME[lang], gl))
    user = "請翻譯下面這些介面字串（一行一條，Tab 後面是它在介面出現的次數，僅供判斷語氣）：\n\n" + listed
    text, _ = providers.chat(ROOT, prov, [{"role": "system", "content": system},
                                          {"role": "user", "content": user}],
                             json_mode=True, max_tokens=max(1024, 120 * len(keys)))
    data = providers.parse_json(text)
    out = {}
    for k, v in (data or {}).items():
        if k in keys and isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


# ---------------------------------------------------------------------------
def cmd_list(langs):
    for lang in langs:
        todo, same, stale = gaps(lang)
        pend = load_pending(lang).get("proposals", {})
        print("== %s：要初翻 %d 條、建議同形 %d 條、失效舊鍵 %d 條、待核可 %d 條"
              % (lang, len(todo), len(same), len(stale), len(pend)))
        for k in todo[:10]:
            print("   待翻：%s" % k[:50])
        if len(todo) > 10:
            print("   ……還有 %d 條" % (len(todo) - 10))
        for k in same[:5]:
            print("   同形：%s → \"==\"" % k[:50])
        if pend:
            print("   待核可：python tools/i18n_fill.py --apply --lang %s（清單見 i18n/pending/%s.review.md）"
                  % (lang, lang))


def cmd_fill(langs, pid):
    prov = pick_provider(pid)
    print("用執行者：%s（%s／%s）" % (prov.get("id"), prov.get("name"), prov.get("model") or "default"))
    counts = index_keys()
    for lang in langs:
        todo, same, stale = gaps(lang)
        pend = load_pending(lang)
        proposals = dict(pend.get("proposals") or {})
        for k in same:                      # 同形不用模型，直接標
            proposals.setdefault(k, SAME)
        if todo:
            print("== %s：送出 %d 條給模型初翻（分 %d 批）" % (lang, len(todo), (len(todo) + 39) // 40))
            for i in range(0, len(todo), 40):
                batch = todo[i:i + 40]
                got = translate(prov, lang, batch, counts)
                proposals.update(got)
                print("   第 %d 批：%d/%d 條有譯文" % (i // 40 + 1, len(got), len(batch)))
        else:
            print("== %s：沒有缺口（同形 %d 條、待核可 %d 條）" % (lang, len(same), len(proposals)))
        write_json(pending_path(lang), {"lang": lang, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                        "proposals": proposals})
        review = dump_review(lang, proposals, sorted(proposals))
        print("   待核可清單：%s" % os.path.relpath(review, ROOT))
        print("   核可後：python tools/i18n_fill.py --apply --lang %s" % lang)


def cmd_apply(langs):
    for lang in langs:
        pend = load_pending(lang)
        proposals = pend.get("proposals") or {}
        if not proposals:
            print("== %s：沒有待核可的初翻（先跑 --fill）" % lang)
            continue
        path = os.path.join(LOCALES, lang + ".json")
        data = json.loads(read(path))
        added = {k: v for k, v in proposals.items() if k not in data}
        if not added:
            print("== %s：待核可的 %d 條都已經在語言檔裡了" % (lang, len(proposals)))
            continue
        print("== %s：新增 %d 條（%s）" % (lang, len(added), "、".join(k[:16] for k in list(added)[:3])))
        data.update(added)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")
        rest = {k: v for k, v in proposals.items() if k not in data}
        write_json(pending_path(lang), {"lang": lang, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                        "proposals": rest})
        print("   下一步：python tools/check_i18n.py && python tools/check_parity.py --update-lock")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", default="en,ja", help="en、ja，可用逗號分隔；預設 en,ja")
    ap.add_argument("--provider", help="要用哪個執行者初翻（預設 config.json 的 default_provider）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--list", action="store_true", help="只列出缺口與待核可（預設）")
    g.add_argument("--fill", action="store_true", help="呼叫模型產出初翻，寫到 i18n/pending/")
    g.add_argument("--apply", action="store_true", help="把 pending 併進 static/locales/（人工核可後才跑）")
    a = ap.parse_args()
    langs = [x.strip() for x in a.lang.split(",") if x.strip() in LANGS]
    if not langs:
        raise SystemExit("--lang 只接受 en、ja")
    if a.fill:
        cmd_fill(langs, a.provider)
    elif a.apply:
        cmd_apply(langs)
    else:
        cmd_list(langs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
