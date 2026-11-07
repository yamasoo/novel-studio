# -*- coding: utf-8 -*-
"""textguard 的繁體保護：簡體偵測（不靠 OpenCC）與其他語言的行為不變。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import textguard


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


if __name__ == "__main__":
    unittest.main()
