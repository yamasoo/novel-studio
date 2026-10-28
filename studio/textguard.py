"""檢查工具的語言保護層。

內建的 check_text.py 是為繁體中文寫的（全形標點修正、簡繁用語、中文 AI 味詞表）。
英文、日文的書如果直接丟進去，標點修正會把半形標點換成全形、把引號改成「」，
等於把稿子改壞。這一層包住它：偵測到正文不是中文時，標點修正原樣放行，
英文、日文有各自的檢查腳本（plugin-en、plugin-ja）；找不到時回傳不帶中文規則的中性結果。
中文正文的行為與原本完全相同。
"""
import os
import re

from . import project

_LOADED = {}


def _lang_checker(lang):
    """plugin-<語言> 裡的檢查腳本（沒有就回傳 None，退回中性結果）。"""
    if lang not in _LOADED:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "plugin-" + lang, "skills", "novel-deslop", "scripts", "check_text.py")
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("check_text_" + lang, p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _LOADED[lang] = mod
        except Exception:
            _LOADED[lang] = False
    return _LOADED[lang] or None


def _en_checker():
    return _lang_checker("en")


_HAN = re.compile(r"[㐀-鿿豈-﫿]")
_KANA = re.compile(r"[぀-ヿ]")
_LATIN = re.compile(r"[A-Za-z]")


def detect(text):
    """回傳 'zh-TW' | 'ja' | 'en'。沒有任何文字時當作中文（維持原行為）。"""
    han = len(_HAN.findall(text))
    kana = len(_KANA.findall(text))
    latin = len(_LATIN.findall(text))
    if kana and kana >= 0.05 * (han + kana):
        return "ja"
    if han == 0 and latin == 0:
        return "zh-TW"
    if han >= 0.3 * (han + latin):
        return "zh-TW"
    return "en"


class Checker:
    """包住 check_text 模組；沒覆寫的屬性一律轉給原模組。"""

    def __init__(self, module):
        self._m = module

    def __getattr__(self, name):
        return getattr(self._m, name)

    def fix_punct(self, text):
        lang = detect(text)
        if lang in ("en", "ja") and _lang_checker(lang):
            return _lang_checker(lang).fix_punct(text)
        if lang != "zh-TW":
            return text, 0
        return self._m.fix_punct(text)

    def check_file(self, path, whitelist, banned=None, aliases=None):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        lang = detect(project.split_frontmatter(text)[1])
        if lang == "zh-TW":
            return self._m.check_file(path, whitelist, banned, aliases)
        if lang in ("en", "ja") and _lang_checker(lang):
            r = _lang_checker(lang).check_file(path, whitelist, None, None)
            r["語言"] = lang
            return r
        n = project.count_chars(text)
        return {"檔案": path, "中文字數": n, "總字數（不含空白）": len(re.sub(r"\s", "", text)),
                "問題": [], "語言": lang}


def wrap(module):
    return Checker(module)


# ---------------------------------------------------------------------------
# 產出語言檢查（英文、日文書）：模型回傳的 JSON 自由文字是不是寫成了中文
# ---------------------------------------------------------------------------
_CH_REF = re.compile(r"^第\s*\d+\s*[章卷]$|^[A-Z]\d{2,4}$|^(?:設定|大綱|追蹤|正文|候選|範例|_範本|\.studio)/")


def _strings(data, out):
    if isinstance(data, dict):
        for k, v in data.items():
            if str(k).startswith("_"):
                continue
            _strings(v, out)
    elif isinstance(data, list):
        for v in data:
            _strings(v, out)
    elif isinstance(data, str):
        out.append(data.strip())
    return out


def _is_enum(s):
    from . import enums
    return any(enums.norm(kind, s) is not None for kind in enums.TABLES)


def lang_mismatch(data, book_lang):
    """回傳 (不符?, 可疑字串數, 檢查的字串數)。繁中書不檢查。
    英文書：長度 8 以上的字串中，含 3 個以上漢字的超過 10%。
    日文書：長度 20 以上、有漢字但完全沒有假名的字串超過 30%（日文的專有名詞常只有漢字，所以只看長句）。
    列舉值、第N章、F001 這類編號、資料夾路徑不算。"""
    if book_lang not in ("en", "ja"):
        return False, 0, 0
    vals = [s for s in _strings(data, []) if s and not _CH_REF.search(s) and not _is_enum(s)]
    if book_lang == "en":
        pool = [s for s in vals if len(s) >= 8]
        bad = [s for s in pool if len(_HAN.findall(s)) >= 3]
        limit = 0.10
    else:
        pool = [s for s in vals if len(s) >= 20]
        bad = [s for s in pool if _HAN.search(s) and not _KANA.search(s)]
        limit = 0.30
    if not pool:
        return False, 0, 0
    return len(bad) / len(pool) > limit, len(bad), len(pool)


def flag_mismatch(data):
    """兩次都不符：在資料（與清單裡的每一筆）加上 _lang_mismatch，寫檔時會在「備註」加一行待核對。"""
    if isinstance(data, dict):
        data["_lang_mismatch"] = True
        for v in data.values():
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        flag_mismatch(x)
            elif isinstance(v, dict):
                flag_mismatch(v)
    return data
