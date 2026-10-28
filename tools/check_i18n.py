#!/usr/bin/env python3
"""三語檢查（push 前跑）：python tools/check_i18n.py

檢查項目
  1. 提示詞包 studio/prompts/zh_TW.py、en.py、ja.py：鍵一致、{變數} 一致。
  2. 英文包的值不能有漢字句子（JSON 鍵名、中文列舉值、檔案路徑、第NNN章 這類「資料格式」允許）。
  3. 介面翻譯 static/locales/en.json、ja.json：{0} 變數與原文一致、en／ja 彼此一致；不能有空值
     （原文 4 字以內的片段，如「章」「張」，某語言不需要時允許留空）；英文值不能有假名。
  4. 介面翻譯的資料夾路徑與 .md 檔名：key（中文原文）裡出現的路徑，值裡必須原樣出現（實際資料夾是中文名，不能翻譯）。
有問題時列出鍵名並回傳 1，全過回傳 0。"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

HAN = re.compile(r"[㐀-鿿豈-﫿]")
KANA = re.compile("[" + chr(0x3040) + "-" + chr(0x30fa) + chr(0x30fc) + "-" + chr(0x30ff) + "]")   # 平假名＋片假名；中點「・」(U+30FB) 不算
VAR = re.compile(r"\{[A-Za-z_0-9]*\}")

# ---- 英文包允許出現的中文：先把這些樣式從字串拿掉，再看還有沒有漢字 ----
_PATH_HEAD = r"(?:設定|大綱|追蹤|正文|候選|範例|_範本|\.studio)"
ALLOW = [
    re.compile(r"[^\s\"'`(\[]*" + _PATH_HEAD + r"/[^\s\"'`)\],;:]*"),   # 設定/故事核心.md、候選/{ch}_*.md、.studio/恢復稿/{rid}.json
    re.compile(r"第\s*(?:N+|\{[A-Za-z_0-9]*\}|\d+)\s*章"),               # 第NNN章、第{n}章、第12章
    re.compile(r"\"[^\"\n]*[㐀-鿿][^\"\n]*\""),                  # "名稱"、"主角|主要配角"（JSON 鍵名與中文列舉值）
    re.compile(r"\\\"[^\"\n]*[㐀-鿿][^\"\n]*\\\""),              # \"知道的秘密\"
    re.compile(r"[「『][^」』\n]{1,12}[」』]"),                            # 「別名」「已知」：指到資料裡的欄位名／選項
    re.compile(r"\|[^\n]*\|"),                                          # 表頭列「| 編號 | 內容 |」：檔案裡的欄位名
    re.compile(r"<<<[^>\n]*>>>|<<<[^>\n]*"),                            # <<<結束>>>、<<<追加 設定/名詞表.md>>>
]
# 剝掉後仍留下的漢字：連續超過這個長度就當成「中文句子」（欄位名、表頭、列舉值都不會這麼長）
MAX_BARE_RUN = 5


def han_sentences(value):
    s = value
    for rx in ALLOW:
        s = rx.sub(" ", s)
    return [m.group(0) for m in re.finditer(r"[㐀-鿿豈-﫿][㐀-鿿豈-﫿，。、；：！？（）]*", s)
            if len(HAN.findall(m.group(0))) > MAX_BARE_RUN]


def var_set(value):
    return sorted(set(VAR.findall(value))) if isinstance(value, str) else []


def load_pack(name):
    import importlib
    return importlib.import_module("studio.prompts." + name).T


def check_prompts(errors):
    packs = {n: load_pack(n) for n in ("zh_TW", "en", "ja")}
    base = packs["zh_TW"]
    for n in ("en", "ja"):
        p = packs[n]
        for k in sorted(set(base) - set(p)):
            errors.append("提示詞包 %s 缺鍵：%s" % (n, k))
        for k in sorted(set(p) - set(base)):
            errors.append("提示詞包 %s 多出鍵（繁中沒有）：%s" % (n, k))
        for k in sorted(set(base) & set(p)):
            if not base[k]:      # 繁中本來就空（例如 review_report_format、claude_out_lang）：沒有可比的變數
                continue
            if var_set(base[k]) != var_set(p[k]):
                errors.append("提示詞包 %s 的 {變數} 與繁中不同：%s（繁中 %s／%s %s）" % (n, k, var_set(base[k]), n, var_set(p[k])))
    for k, v in packs["en"].items():
        if isinstance(v, str):
            bad = han_sentences(v)
            if k.endswith("_len") and HAN.search(v):      # arc_len、style_len、trial_len 這類篇幅設定：完全不該有漢字
                bad.append(v)
            if bad:
                errors.append("英文提示詞包的值有中文句子：%s → %s" % (k, "｜".join(b[:20] for b in bad[:3])))


def check_locales(errors):
    loc = {}
    for n in ("en", "ja"):
        with open(os.path.join(ROOT, "static", "locales", n + ".json"), encoding="utf-8") as f:
            loc[n] = json.load(f)
    for n, d in loc.items():
        for k, v in d.items():
            if k.startswith("_"):      # _comment 這類說明鍵，執行時不載入
                continue
            # 空字串在執行時是有效翻譯（i18n.js 只擋 null）；「章」「張」「看到第」這類短片段，某個語言不需要就留空。
            # 所以只有原文超過 4 個字還是空的，才算漏翻。
            if not isinstance(v, str) or (not v.strip() and len(k.strip()) > 4):
                errors.append("%s.json 值是空的：%s" % (n, k))
    for k, v in loc["en"].items():
        if isinstance(v, str) and KANA.search(v):
            errors.append("en.json 的值有假名：%s → %s" % (k, v[:40]))
    for k in sorted(set(loc["en"]) & set(loc["ja"])):
        if k.startswith("_"):
            continue
        a, b = loc["en"][k], loc["ja"][k]
        if isinstance(a, str) and isinstance(b, str):
            va, vb = sorted(re.findall(r"\{\d+\}", a)), sorted(re.findall(r"\{\d+\}", b))
            if va != vb:
                errors.append("en.json 與 ja.json 的 {0} 變數不同：%s（en %s／ja %s）" % (k[:40], va, vb))
    for n, d in loc.items():
        for k, v in d.items():
            if isinstance(v, str) and not k.startswith("_"):
                ks = sorted(re.findall(r"\{\d+\}", k))
                vs = sorted(re.findall(r"\{\d+\}", v))
                if ks != vs:
                    errors.append("%s.json 的 {0} 變數與原文不同：%s（原文 %s／譯文 %s）" % (n, k[:40], ks, vs))
    check_paths(loc, errors)


# 介面文字裡的資料夾路徑與檔名：實際資料夾叫中文名，翻譯時不能跟著翻
PATH_RX = re.compile(r"(?:設定|大綱|追蹤|正文|候選|範例|_範本|_共用|\.studio)(?:/[^\s\"'`()\[\]{}<>,;:、。，；：！？（）「」『』→＋+*]+)+")
MD_RX = re.compile(r"[^\s/\"'`()\[\]{}<>,;:、。，；：！？（）「」『』→＋+*]+\.md\b")


def ui_paths(key):
    found = set(PATH_RX.findall(key)) | set(MD_RX.findall(key))
    found = {p.rstrip("/.") for p in found}
    # 被更長的路徑包含的短路徑不用另外比（例如 .studio/備份 已包含在 .studio/備份/插圖 裡）
    return sorted(p for p in found if not any(p != q and p in q for q in found))


def check_paths(loc, errors):
    for n, d in loc.items():
        for k, v in d.items():
            if k.startswith("_") or not isinstance(v, str):
                continue
            for p in ui_paths(k):
                if p not in v:
                    errors.append("%s.json 的路徑被翻譯或改掉：%s（原文要有「%s」）→ %s" % (n, k[:30], p, v[:50]))


def main():
    errors = []
    check_prompts(errors)
    check_locales(errors)
    if errors:
        print("check_i18n：發現 %d 個問題" % len(errors))
        for e in errors:
            print(" - " + e)
        return 1
    print("check_i18n：全部通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
