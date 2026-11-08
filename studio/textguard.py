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


def _zh_module():
    """內建的繁體中文檢查腳本（plugin/…/check_text.py），沒有就回傳 None。"""
    if "zh" not in _LOADED:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "plugin", "skills", "novel-deslop", "scripts", "check_text.py")
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("check_text_zh", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _LOADED["zh"] = mod
        except Exception:
            _LOADED["zh"] = False
    return _LOADED["zh"] or None


def simp_count(text):
    """文字裡有幾個「簡體專用字」（Big5 沒有的字，不需要 OpenCC）。"""
    m = _zh_module()
    if not m or not text:
        return 0
    return sum(1 for ch in text if ch in m.SIMPLIFIED_ONLY)


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
    """回傳 (不符?, 可疑字串數, 檢查的字串數)。
    繁中書：長度 8 以上的字串中，含 2 個以上簡體專用字的超過 15%。
    英文書：長度 8 以上的字串中，含 3 個以上漢字的超過 10%。
    日文書：長度 20 以上、有漢字但完全沒有假名的字串超過 30%（日文的專有名詞常只有漢字，所以只看長句）。
    列舉值、第N章、F001 這類編號、資料夾路徑不算。"""
    if book_lang not in ("en", "ja", "zh-TW"):
        return False, 0, 0
    vals = [s for s in _strings(data, []) if s and not _CH_REF.search(s) and not _is_enum(s)]
    if book_lang == "zh-TW":
        pool = [s for s in vals if len(s) >= 8]
        bad = [s for s in pool if simp_count(s) >= 2]
        limit = 0.15
    elif book_lang == "en":
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


# ---------------------------------------------------------------------------
# 落檔前的繁體保護：少量簡體字逐字轉繁，整段偏簡體則原樣放行並回報
# ---------------------------------------------------------------------------
SIMP_MAX = 20          # 少於這數量的簡體字自動逐字轉繁；更多代表整段漂移，交給作者重跑

_PUA = "\ue000"


def s2t_map(chars):
    """簡體字 → 繁體字：OpenCC 逐字對照；一簡對多繁（長度不是 1）的字不轉。沒有 OpenCC 回傳 {}。"""
    if not chars:
        return {}
    try:
        from opencc import OpenCC
        cc = OpenCC("s2t")
    except Exception:
        return {}
    out = {}
    for ch in sorted(chars):
        try:
            t = cc.convert(ch)
        except Exception:
            continue
        if len(t) == 1 and t != ch:
            out[ch] = t
    return out


def _mask(text, terms):
    """白名單詞換成私用區佔位字，轉完再放回；佔位字不含中日韓字，標點規則不會動到它。"""
    table = {}
    for i, term in enumerate(t for t in terms if t):
        if term not in text:
            continue
        ph = "%s%d\ue001" % (_PUA, i)
        text = text.replace(term, ph)
        table[ph] = term
    return text, table


def _book_lang(book_dir):
    try:
        from . import lang as lang_mod
        return lang_mod.book_lang(book_dir)
    except Exception:
        return ""


def term_map(module):
    """從檢查腳本的大陸用語表挑「可以直接換」的：等級是建議修、建議值唯一（沒有／、（）。
    長的排前面，避免短的先吃掉長的（人工智能先於智能、公交車先於公交）。"""
    out = []
    for item in getattr(module, "MAINLAND_TERMS", []):
        bad, good = item[0], item[1]
        level = item[2] if len(item) > 2 else ""
        if level != "建議修" or not bad or not good:
            continue
        if "／" in good or "（" in good or "(" in good:
            continue
        out.append((bad, good))
    out.sort(key=lambda kv: -len(kv[0]))
    return out


def _split_fm_raw(text):
    """把開頭的 frontmatter 原文與後面的正文分開（不解析 YAML，壞掉也切得開）。"""
    if not text.startswith("---"):
        return "", text
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[:i + 1]) + "\n", "\n".join(lines[i + 1:])
    return "", text


def _guard_one(book_dir, text):
    """回傳 (文字, 計數)。計數是 {"simp": 轉繁處數, "term": 用語處數, "punct": 標點處數, "left": 沒轉的簡體字數}。

    frontmatter 不進這道：標點轉換會把「類型: 角色」的半形冒號改成全形，整份 frontmatter 就解析不了
    （名稱、定位、狀態全部讀不到）。跟 check_file 一樣，只處理正文。
    """
    zero = {"simp": 0, "term": 0, "punct": 0, "left": 0}
    if not text or not isinstance(text, str) or _book_lang(book_dir) != "zh-TW":
        return text, zero
    m = _zh_module()
    if not m:
        return text, zero
    head, text = _split_fm_raw(text)
    simp = simp_count(text)
    if simp > SIMP_MAX:        # 整段漂移：不硬轉，交給作者重跑
        return text, dict(zero, left=simp)
    masked, table = _mask(text, m.load_whitelist(book_dir))
    done = dict(zero)
    if simp:
        mapping = s2t_map({ch for ch in masked if ch in m.SIMPLIFIED_ONLY})
        for k, v in mapping.items():
            done["simp"] += masked.count(k)
            masked = masked.replace(k, v)
        done["left"] = simp_count(masked)
    for bad, good in term_map(m):
        n = masked.count(bad)
        if n:
            masked = masked.replace(bad, good)
            done["term"] += n
    if "```" not in masked:   # 程式碼區塊不動標點
        masked, done["punct"] = m.fix_punct(masked)
    for ph, term in table.items():
        masked = masked.replace(ph, term)
    return head + masked, done


def _note_of(done):
    """把計數寫成一句給作者看的話；沒動到內容就回傳空字串。"""
    parts = []
    if done.get("simp"):
        parts.append("簡體字已轉繁 %d 處" % done["simp"])
    if done.get("term"):
        parts.append("用語 %d 處" % done["term"])
    if done.get("punct"):
        parts.append("標點 %d 處" % done["punct"])
    if not parts and not done.get("left"):
        return ""
    note = "、".join(parts)
    if done.get("left"):
        if done["left"] > SIMP_MAX:
            why = "整段偏簡體"
        else:
            why = "沒有 OpenCC 可轉" if not parts else "白名單或對照表沒涵蓋"
        tail = "有 %d 個簡體字沒轉（%s），建議重跑這個步驟" % (done["left"], why)
        note = (note + "；" + tail) if note else tail
    return note


def guard_text(book_dir, text):
    """繁體書的產出在落檔前過一道（簡體轉繁、用語、標點），回傳 (文字, 說明)。"""
    out, done = _guard_one(book_dir, text)
    return out, _note_of(done)


def guard_data(book_dir, data):
    """把 dict／list 裡的字串值都過一次 guard_text；回傳 (新資料, 說明)。"""
    total = {"simp": 0, "term": 0, "punct": 0, "left": 0}

    def walk(v):
        if isinstance(v, dict):
            return {k: (val if str(k).startswith("_") else walk(val)) for k, val in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str) and v:
            out, done = _guard_one(book_dir, v)
            for k in total:
                total[k] += done.get(k, 0)
            return out
        return v

    out = walk(data)
    return out, _note_of(total)

def notify(note):
    """沒有回報通道的地方（例如續寫合約）把語言修正寫到後端視窗。"""
    if note:
        print("【語言】%s" % note, flush=True)
