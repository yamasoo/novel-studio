# -*- coding: utf-8 -*-
"""textguard 的繁體保護：簡體偵測（不靠 OpenCC）與其他語言的行為不變。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import textguard

try:
    import opencc  # noqa: F401
    HAS_OPENCC = True
except Exception:
    HAS_OPENCC = False


def make_book(lang=None):
    """造一個只有 .studio/lang 的假書目錄（沒有就代表預設的繁體中文）。"""
    import tempfile
    d = tempfile.mkdtemp(prefix="ns-lang-")
    if lang:
        os.makedirs(os.path.join(d, ".studio"), exist_ok=True)
        with open(os.path.join(d, ".studio", "lang"), "w", encoding="utf-8", newline="\n") as f:
            f.write(lang + "\n")
    return d


class SimpCountTest(unittest.TestCase):
    def test_簡體字算得出來(self):
        self.assertGreaterEqual(textguard.simp_count("这是简体的一段文字"), 2)

    def test_繁體字不算(self):
        self.assertEqual(textguard.simp_count("這是繁體的一段文字，皇后與公里都正常。"), 0)

    def test_空字串與None(self):
        self.assertEqual(textguard.simp_count(""), 0)
        self.assertEqual(textguard.simp_count(None), 0)


class LangMismatchZhtwTest(unittest.TestCase):
    def test_整批簡體要重寫(self):
        data = {"角色": [{"一句話": "这是个很长的简体中文句子可以用来测试。"},
                        {"一句話": "他还说了另外一句话也是简体的。"}],
                "世界觀": "整个世界观都是用简体中文写成的长句子。"}
        bad, n, total = textguard.lang_mismatch(data, "zh-TW")
        self.assertTrue(bad)
        self.assertEqual(n, total)

    def test_繁體不觸發(self):
        data = {"角色": [{"一句話": "這是個很長的繁體中文句子，可以用來測試。"}],
                "世界觀": "整個世界觀都是用繁體中文寫成的長句子。"}
        self.assertEqual(textguard.lang_mismatch(data, "zh-TW"), (False, 0, 2))

    def test_單一個簡體字不觸發(self):
        data = {"一句話": "這是一段很長的繁體中文內容，只有一个字是簡體。"}
        self.assertFalse(textguard.lang_mismatch(data, "zh-TW")[0])

    def test_短字串不算(self):
        self.assertEqual(textguard.lang_mismatch({"名": "这个"}, "zh-TW"), (False, 0, 0))

    def test_編號與路徑不算(self):
        data = {"第1章": "这是简体", "路徑": "設定/角色/这是简体.md"}
        self.assertEqual(textguard.lang_mismatch(data, "zh-TW"), (False, 0, 0))

    def test_英文書行為不變(self):
        # 英文書寫成中文 → 要觸發；寫成英文 → 不觸發
        self.assertTrue(textguard.lang_mismatch({"a": "這是一段很長的中文內容"}, "en")[0])
        self.assertFalse(textguard.lang_mismatch({"a": "This is a long English sentence."}, "en")[0])

    def test_日文書行為不變(self):
        cn = "這是一段很長很長的中文內容而且完全沒有用到任何假名總共超過二十個字"
        self.assertTrue(textguard.lang_mismatch({"a": cn}, "ja")[0])
        self.assertFalse(textguard.lang_mismatch({"a": "これは長い日本語の文章です、ちゃんと仮名があります"}, "ja")[0])


class GuardTextTest(unittest.TestCase):
    def test_少量簡體轉成繁體(self):
        if not HAS_OPENCC:
            self.skipTest("沒有 OpenCC")
        d = make_book()
        out, note = textguard.guard_text(d, "他这时走了过来。")
        self.assertEqual(out, "他這時走了過來。")
        self.assertIn("已轉繁 4 處", note)   # 这、时、过、来

    def test_繁體不動(self):
        d = make_book()
        text = "這是繁體，皇后與公里都正常。"
        self.assertEqual(textguard.guard_text(d, text), (text, ""))

    def test_英文書不動(self):
        if not HAS_OPENCC:
            self.skipTest("沒有 OpenCC")
        d = make_book("en")
        text = "他这时走了过来。"
        self.assertEqual(textguard.guard_text(d, text), (text, ""))

    def test_整段偏簡體只回報不轉(self):
        d = make_book()
        text = "这" * (textguard.SIMP_MAX + 5)
        out, note = textguard.guard_text(d, text)
        self.assertEqual(out, text)
        self.assertIn("沒轉", note)
        self.assertIn("整段偏簡體", note)

    def test_沒有OpenCC只回報(self):
        import sys
        from unittest import mock
        d = make_book()
        text = "他这时走了过来。"
        with mock.patch.dict(sys.modules, {"opencc": None}):
            out, note = textguard.guard_text(d, text)
        self.assertEqual(out, text)
        self.assertIn("沒有 OpenCC", note)

    def test_白名單裡的專有名詞不動(self):
        if not HAS_OPENCC:
            self.skipTest("沒有 OpenCC")
        d = make_book()
        with open(os.path.join(d, ".去AI味白名單"), "w", encoding="utf-8", newline="\n") as f:
            f.write("这明\n")
        out, note = textguard.guard_text(d, "这明这时来了。")
        self.assertIn("这明", out)          # 名字原樣
        self.assertIn("這時", out)          # 其他照轉
        self.assertIn("已轉繁 3 處", note)   # 第二個「这」、时、来

    def test_不是字串就原樣回傳(self):
        d = make_book()
        self.assertEqual(textguard.guard_text(d, ""), ("", ""))
        self.assertEqual(textguard.guard_text(d, None), (None, ""))


class GuardDataTest(unittest.TestCase):
    def test_逐層處理字串值(self):
        if not HAS_OPENCC:
            self.skipTest("沒有 OpenCC")
        d = make_book()
        data = {"角色": [{"一句話": "他这时来了。"}], "數量": 3, "_note": "这"}
        out, note = textguard.guard_data(d, data)
        self.assertEqual(out["角色"][0]["一句話"], "他這時來了。")
        self.assertEqual(out["數量"], 3)
        self.assertEqual(out["_note"], "这")     # 底線開頭不動
        self.assertIn("已轉繁", note)

    def test_沒問題時說明為空(self):
        d = make_book()
        data = {"a": "這是繁體"}
        self.assertEqual(textguard.guard_data(d, data), (data, ""))


if __name__ == "__main__":
    unittest.main()
