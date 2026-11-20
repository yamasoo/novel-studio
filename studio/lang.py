# -*- coding: utf-8 -*-
"""每本書的寫作語言。

存放位置（依序找，找到就用）：
  1. book.json 的 lang（v3 起的唯一來源；工作台開書、改語言都寫這裡）
  2. bible/story-core.md 開頭資料區的「語言: zh-TW | en | ja」（舊書；Claude Code 技能目前也寫這裡，P4 改）
  3. .studio/lang（舊書）
  4. 都沒有 → zh-TW
"""
import os
import re

from . import project
from . import layout

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


def unit_zh(lang):
    """後端訊息裡的中文單位字：chars → 「字」、words → 「詞」。
    訊息原文是介面翻譯的 key，繁中／日文書維持「字」（顯示與以前完全一樣），英文書用「詞」。"""
    return "詞" if count_unit(lang) == "words" else "字"


def normalize(value):
    """各種寫法 → zh-TW / en / ja；認不得的一律當 zh-TW。"""
    if not value:
        return DEFAULT
    return _ALIASES.get(str(value).strip().lower(), DEFAULT)


def _fm_lang(book_dir, rel=None):
    """故事核心 frontmatter 的「語言」。rel：故事核心的相對路徑（移轉工具讀舊書時給 v2 的路徑）。"""
    p = layout.path(book_dir, rel or layout.STORY_CORE)
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
        with open(layout.path(book_dir, layout.STUDIO, "lang"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def book_lang(book_dir):
    if not book_dir:
        return DEFAULT
    from . import bookmeta
    return normalize(bookmeta.read(book_dir).get("lang") or _fm_lang(book_dir) or _file_lang(book_dir))


def book_unit(book_dir):
    return count_unit(book_lang(book_dir))


def set_book_lang(book_dir, value):
    """設定書的語言：寫 book.json。舊的 .studio/lang 拿掉（免得兩邊不一致）。
    故事核心檔已存在的話，也同步改裡面的「語言」（Claude Code 技能還會讀它；P4 改完技能再拿掉）。"""
    from . import bookmeta, shared
    lang = normalize(value)
    bookmeta.write(book_dir, lang=lang)
    old = layout.path(book_dir, layout.STUDIO, "lang")
    if os.path.isfile(old):
        os.remove(old)
    p = layout.path(book_dir, layout.STORY_CORE)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            text = f.read()
        if text.startswith("---"):
            project.write_atomic(p, shared.set_fm(text, "語言", lang))
    return lang
