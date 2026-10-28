# -*- coding: utf-8 -*-
"""每本書的寫作語言。

存放位置（依序找，找到就用）：
  1. 設定/故事核心.md 開頭資料區的「語言: zh-TW | en | ja」
  2. .studio/lang（開書當下還沒有故事核心檔時先記在這裡；開書訪談時會被寫進故事核心）
  3. 都沒有 → zh-TW（舊書不用改任何東西）
"""
import os
import re

DEFAULT = "zh-TW"
SUPPORTED = ("zh-TW", "en", "ja")
LABELS = {"zh-TW": "繁體中文", "en": "English", "ja": "日本語"}

_ALIASES = {
    "zh-tw": "zh-TW", "zh_tw": "zh-TW", "zh": "zh-TW", "tw": "zh-TW", "zh-hant": "zh-TW",
    "繁體中文": "zh-TW", "繁体中文": "zh-TW", "中文": "zh-TW", "台灣繁體中文": "zh-TW",
    "en": "en", "en-us": "en", "en-gb": "en", "english": "en", "英文": "en", "英語": "en",
    "ja": "ja", "ja-jp": "ja", "jp": "ja", "japanese": "ja", "日本語": "ja", "日文": "ja", "日語": "ja",
}


# 字數單位：中文、日文算字（漢字＋假名），英文算詞
UNITS = {"zh-TW": "chars", "en": "words", "ja": "chars"}


def count_unit(lang):
    """"chars" 或 "words"。API 回傳字數時一併附上，前端才知道要顯示「字」還是「詞」。"""
    return UNITS.get(normalize(lang), "chars")


def normalize(value):
    """各種寫法 → zh-TW / en / ja；認不得的一律當 zh-TW。"""
    if not value:
        return DEFAULT
    return _ALIASES.get(str(value).strip().lower(), DEFAULT)


def _fm_lang(book_dir):
    p = os.path.join(book_dir, "設定", "故事核心.md")
    try:
        with open(p, encoding="utf-8") as f:
            head = f.read(2000)
    except OSError:
        return None
    if not head.startswith("---"):
        return None
    for line in head.split("\n")[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"\s*語言\s*[:：]\s*(.*?)\s*$", line)
        if m and m.group(1):
            return m.group(1)
    return None


def _file_lang(book_dir):
    try:
        with open(os.path.join(book_dir, ".studio", "lang"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def book_lang(book_dir):
    if not book_dir:
        return DEFAULT
    return normalize(_fm_lang(book_dir) or _file_lang(book_dir))


def book_unit(book_dir):
    return count_unit(book_lang(book_dir))


def set_book_lang(book_dir, value):
    """設定書的語言：寫 .studio/lang；故事核心檔已存在的話，也同步改裡面的「語言」。"""
    from . import shared
    lang = normalize(value)
    os.makedirs(os.path.join(book_dir, ".studio"), exist_ok=True)
    with open(os.path.join(book_dir, ".studio", "lang"), "w", encoding="utf-8", newline="\n") as f:
        f.write(lang + "\n")
    p = os.path.join(book_dir, "設定", "故事核心.md")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            text = f.read()
        if text.startswith("---"):
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(shared.set_fm(text, "語言", lang))
    return lang
