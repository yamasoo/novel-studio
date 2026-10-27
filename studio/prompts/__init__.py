# -*- coding: utf-8 -*-
"""提示詞語言包。每個語言一個模組，內容是同一組鍵；缺的鍵退回繁體中文。
新增語言：複製 zh_TW.py、翻譯值、在 MODULES 加一行，再到 studio/lang.py 的 SUPPORTED 加上語言代碼。

兩種取用方式
- 有書的語言可用時（actions.build、Ctx 等）：pack(lang)／t(lang, key, **kw)
- 沒有任務物件可傳的模組（goals、tracking、revision、context 的 Pack）：用 set_lang() 設定「目前任務的語言」，
  再用 cur()／label() 取。設定在 Runner 執行緒開頭、launch_job、以及會組提示詞的 API 處理函式裡做。
"""
import contextvars
import re
from importlib import import_module

MODULES = {"zh-TW": "zh_TW", "en": "en", "ja": "ja"}
_cache = {}
_LANG = contextvars.ContextVar("prompt_lang", default="zh-TW")


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


# ---------------------------------------------------------------------------
# 目前任務的語言
# ---------------------------------------------------------------------------
def set_lang(lang):
    _LANG.set(lang if lang in MODULES else "zh-TW")


def cur_lang():
    return _LANG.get()


def cur():
    return pack(_LANG.get())


# ---------------------------------------------------------------------------
# 給模型看的「段落標題」翻譯：程式裡的標題維持中文當索引，依語言換成對應文字。
# 表在 labels.py：{語言: {中文: 譯文}}；中文裡可以用 {0} {1} 代表變數（例如「第{0}章章綱」）。找不到就原樣。
# ---------------------------------------------------------------------------
_lab = {}


def _compile(lang):
    from .labels import LABELS
    exact, pats = {}, []
    for k, v in (LABELS.get(lang) or {}).items():
        if re.search(r"\{\d+\}", k):
            rx = re.escape(k)
            rx = re.sub(r"\\\{(\d+)\\\}", r"(?P<g\1>.*?)", rx)
            pats.append((re.compile("^" + rx + "$", re.S), v))
        else:
            exact[k] = v
    pats.sort(key=lambda x: -len(x[0].pattern))
    _lab[lang] = (exact, pats)


def label(s, lang=None):
    lang = lang or _LANG.get()
    if lang == "zh-TW" or not s:
        return s
    if lang not in _lab:
        _compile(lang)
    exact, pats = _lab[lang]
    if s in exact:
        return exact[s]
    for rx, to in pats:
        m = rx.match(s)
        if m:
            return re.sub(r"\{(\d+)\}", lambda g: label(m.group("g" + g.group(1)), lang), to)
    return s
