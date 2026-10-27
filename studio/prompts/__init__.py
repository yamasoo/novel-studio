# -*- coding: utf-8 -*-
"""提示詞語言包。每個語言一個模組，內容是同一組鍵；缺的鍵退回繁體中文。
新增語言：複製 zh_TW.py、翻譯值、在 MODULES 加一行，再到 studio/lang.py 的 SUPPORTED 加上語言代碼。"""
from importlib import import_module

MODULES = {"zh-TW": "zh_TW", "en": "en", "ja": "ja"}
_cache = {}


def pack(lang):
    """回傳該語言的提示詞字典（已用繁體中文補齊缺的鍵）。"""
    if lang not in MODULES:
        lang = "zh-TW"
    if lang not in _cache:
        base = import_module(__name__ + ".zh_TW").T
        d = dict(base)
        if lang != "zh-TW":
            d.update(import_module(__name__ + "." + MODULES[lang]).T)
        _cache[lang] = d
    return _cache[lang]


def t(lang, key, **kw):
    s = pack(lang)[key]
    return s.format(**kw) if kw else s
