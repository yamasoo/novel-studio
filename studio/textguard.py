"""檢查工具的語言保護層。

內建的 check_text.py 是為繁體中文寫的（全形標點修正、簡繁用語、中文 AI 味詞表）。
英文、日文的書如果直接丟進去，標點修正會把半形標點換成全形、把引號改成「」，
等於把稿子改壞。這一層包住它：偵測到正文不是中文時，標點修正原樣放行，
check_file 回傳不帶中文規則的中性結果（各語言專屬規則之後另補）。
中文正文的行為與原本完全相同。
"""
import re

from . import project

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
        if detect(text) != "zh-TW":
            return text, 0
        return self._m.fix_punct(text)

    def check_file(self, path, whitelist, banned=None, aliases=None):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        lang = detect(project.split_frontmatter(text)[1])
        if lang == "zh-TW":
            return self._m.check_file(path, whitelist, banned, aliases)
        n = project.count_chars(text)
        return {"檔案": path, "中文字數": n, "總字數（不含空白）": len(re.sub(r"\s", "", text)),
                "問題": [], "語言": lang}


def wrap(module):
    return Checker(module)
