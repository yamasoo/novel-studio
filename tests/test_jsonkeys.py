# -*- coding: utf-8 -*-
"""jsonkeys.to_keys：模型資料 → 程式內部的英文鍵（v3 P2）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import jsonkeys  # noqa: E402


class ToKeysTest(unittest.TestCase):
    def test_chinese_and_english_give_same_result(self):
        zh = {"foreshadow": [{"編號": "F001", "最後出現": "第003章"}], "characters": [{"名稱": "林晚", "關係變化": "x"}]}
        en = {"foreshadow": [{"id": "F001", "Last_Seen": "第003章"}], "characters": [{"name": "林晚", "relationship_changes": "x"}]}
        self.assertEqual(jsonkeys.to_keys(zh, values=False), jsonkeys.to_keys(en, values=False))
        self.assertEqual({"id": "F001", "last_seen": "第003章"}, jsonkeys.to_keys(zh, values=False)["foreshadow"][0])

    def test_two_english_words_pick_by_value_type(self):
        d = jsonkeys.to_keys({"名詞": [{"名詞": "暗格"}], "人物": [{"關係": ["主僕"]}], "relations": [{"關係": "師徒"}]}, values=False)
        self.assertEqual([{"term": "暗格"}], d["terms"])
        self.assertEqual([{"relationships": ["主僕"]}], d["people"])
        self.assertEqual([{"relationship": "師徒"}], d["relations"])

    def test_chinese_key_wins_when_both_given(self):
        self.assertEqual({"content": "中"}, jsonkeys.to_keys({"content": "英", "內容": "中"}, values=False))
        self.assertEqual({"content": "中"}, jsonkeys.to_keys({"內容": "中", "content": "英"}, values=False))

    def test_unknown_and_private_keys_kept(self):
        d = jsonkeys.to_keys({"自訂欄": "a", "_lang_mismatch": True, "report": "r"}, values=False)
        self.assertEqual({"自訂欄": "a", "_lang_mismatch": True, "report": "r"}, d)

    def test_enum_values_normalized_and_unknown_reported(self):
        unknown = []
        d = jsonkeys.to_keys({"foreshadow": [{"status": "planted", "priority": "very important"}]}, unknown, values=True)
        self.assertEqual("已埋", d["foreshadow"][0]["status"])
        self.assertEqual([("重要度", "very important")], unknown)

    def test_no_english_key_collides_with_native_keys(self):
        self.assertFalse(set(jsonkeys.ZH_TO_EN.values()) & jsonkeys.NATIVE)
        for pair in jsonkeys._PLURAL.values():
            self.assertFalse(set(pair) & jsonkeys.NATIVE)


if __name__ == "__main__":
    unittest.main()
