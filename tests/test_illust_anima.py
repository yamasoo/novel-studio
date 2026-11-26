# -*- coding: utf-8 -*-
"""Anima 插圖提示詞優化測試：服裝模式（default/custom/nude）、多人去重與 _strip_count、單張分級覆寫。"""
import unittest

from studio import illust


class AnimaAssembleTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(illust.DEFAULTS)
        self.char_a = {
            "name": "甲",
            "tags": "1girl, a 24-year-old woman, long black hair, red eyes, slim build, white blouse, black pencil skirt",
            "description": "a 24-year-old woman, long black hair, red eyes, slim build, white blouse, black pencil skirt",
            "body_tags": "a 24-year-old woman, long black hair, red eyes, slim build",
            "outfit_tags": "white blouse, black pencil skirt",
            "position": "left",
            "action": "blushing, lying on bed",
        }
        self.char_b = {
            "name": "乙",
            "tags": "1boy, a 28-year-old man, short silver hair, sharp blue eyes, tall athletic build, dark suit, necktie",
            "description": "a 28-year-old man, short silver hair, sharp blue eyes, tall athletic build, dark suit, necktie",
            "body_tags": "a 28-year-old man, short silver hair, sharp blue eyes, tall athletic build",
            "outfit_tags": "dark suit, necktie",
            "position": "right",
            "action": "leaning close",
        }

    def test_nude_mode_omits_default_outfit_and_adds_nude(self):
        c = dict(self.char_a, outfit_mode="nude")
        r = illust.assemble({"chars": [c], "safety": "explicit", "scene_tags": "dimly lit bedroom"}, self.cfg)
        pos = r["positive"]
        self.assertIn("explicit", pos)
        self.assertNotIn("safe", pos)
        self.assertIn("long black hair", pos)
        self.assertIn("nude", pos)
        self.assertNotIn("white blouse", pos)
        self.assertNotIn("black pencil skirt", pos)

    def test_custom_mode_omits_default_outfit_even_for_legacy_card(self):
        legacy = {
            "name": "舊卡角",
            "tags": "1girl, short blonde hair, green eyes, white shirt, pleated skirt",
            "description": "a young girl with short blonde hair wearing a white shirt and pleated skirt",
            "outfit_mode": "custom",
            "action": "wearing silk bathrobe, disheveled",
        }
        r = illust.assemble({"chars": [legacy], "safety": "sensitive"}, self.cfg)
        pos = r["positive"]
        self.assertIn("sensitive", pos)
        self.assertIn("short blonde hair", pos)
        self.assertIn("wearing silk bathrobe", pos)
        self.assertNotIn("white shirt", pos)
        self.assertNotIn("pleated skirt", pos)

    def test_multi_character_strips_individual_count_and_avoids_duplication(self):
        a = dict(self.char_a, outfit_mode="default")
        b = dict(self.char_b, outfit_mode="default")
        r = illust.assemble({"chars": [a, b], "safety": "none"}, self.cfg)
        pos = r["positive"]
        lines = pos.split("\n")
        # 頂部有 1girl, 1boy，不含 safe（因為 safety='none'）
        self.assertIn("1girl, 1boy", lines[0])
        self.assertNotIn("safe", lines[0])
        # 多人行不重複塞 1girl / 1boy，且有明確左右區分與 wearing
        left_line = next(l for l in lines if l.startswith("On the left:"))
        right_line = next(l for l in lines if l.startswith("On the right:"))
        self.assertNotIn("1girl", left_line)
        self.assertNotIn("1boy", right_line)
        self.assertIn("wearing white blouse, black pencil skirt", left_line)
        self.assertIn("wearing dark suit, necktie", right_line)
        # 不重複貼兩遍相同外觀
        self.assertEqual(left_line.count("long black hair"), 1)
        self.assertEqual(right_line.count("short silver hair"), 1)

    def test_merge_scene_keeps_outfit_mode_and_safety(self):
        entries = [{"name": "甲", "file": "bible/characters/甲.md", "card": {
            "tags": self.char_a["tags"], "description": self.char_a["description"],
            "body_tags": self.char_a["body_tags"], "outfit_tags": self.char_a["outfit_tags"],
        }}]
        draft = illust.merge_scene({}, {
            "characters": [{"name": "甲", "position": "left", "outfit_mode": "nude", "action": "lying on bed"}],
            "safety": "explicit",
            "scene_tags": "bedroom",
        }, entries)
        self.assertEqual(draft["safety"], "explicit")
        self.assertEqual(draft["chars"][0]["outfit_mode"], "nude")
        self.assertEqual(draft["chars"][0]["body_tags"], self.char_a["body_tags"])


if __name__ == "__main__":
    unittest.main()
