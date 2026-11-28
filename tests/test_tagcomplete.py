# -*- coding: utf-8 -*-
"""TagComplete 即時標籤補全與 tagcomplete-neo 路徑偵測單元測試。"""
import os
import tempfile
import unittest

from studio import illust


class TagCompleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        tags_dir = os.path.join(self.d, "extensions", "sd-webui-tagcomplete-neo", "tags")
        os.makedirs(tags_dir, exist_ok=True)
        self.tag_csv = os.path.join(tags_dir, "danbooru.csv")
        self.zh_csv = os.path.join(tags_dir, "danbooru-0-zh.csv")
        with open(self.tag_csv, "w", encoding="utf-8") as f:
            f.write(
                'long_hair,0,4500000,"longhair,flowing_hair"\n'
                'long_sleeves,0,1200000,""\n'
                'silver_hair,0,900000,"grey_hair_alt"\n'
                'ask_(askzy),1,52000,""\n'
                'wlop,1,88000,""\n'
            )
        with open(self.zh_csv, "w", encoding="utf-8") as f:
            f.write(
                "long_hair,0,長髮|长发\n"
                "silver_hair,0,銀髮|银发\n"
                "wlop,1,王凌|鬼刀畫師\n"
            )

    def tearDown(self):
        self.tmp.cleanup()

    def test_detects_tagcomplete_neo_directory(self):
        t, z = illust.tag_dict_paths({"forge_dir": self.d})
        self.assertEqual(t, self.tag_csv)
        self.assertEqual(z, self.zh_csv)

    def test_english_prefix_and_zh_gloss(self):
        res = illust.suggest_tags("long", self.tag_csv, self.zh_csv, limit=10)
        self.assertTrue(res["has_dict"])
        tags = [x["tag"] for x in res["items"]]
        self.assertEqual(tags[:2], ["long hair", "long sleeves"])
        self.assertEqual(res["items"][0]["zh"], "長髮")

    def test_alias_match(self):
        res = illust.suggest_tags("flowing", self.tag_csv, self.zh_csv, limit=10)
        self.assertEqual(res["items"][0]["tag"], "long hair")
        self.assertEqual(res["items"][0]["alias"], "flowing hair")

    def test_chinese_lookup_suggests_english_tag(self):
        res = illust.suggest_tags("銀髮", self.tag_csv, self.zh_csv, limit=10)
        self.assertEqual(res["items"][0]["tag"], "silver hair")
        self.assertEqual(res["items"][0]["zh"], "銀髮")

    def test_artist_mode_and_at_prefix(self):
        res = illust.suggest_tags("@wl", self.tag_csv, self.zh_csv, limit=10)
        self.assertEqual(len(res["items"]), 1)
        self.assertEqual(res["items"][0]["tag"], "wlop")
        self.assertEqual(res["items"][0]["insert"], "@wlop")
        self.assertEqual(res["items"][0]["cat"], "1")

    def test_chinese_artist_lookup_and_stacking(self):
        res = illust.suggest_tags("王凌", self.tag_csv, self.zh_csv, limit=10)
        self.assertEqual(res["items"][0]["tag"], "wlop")
        self.assertEqual(res["items"][0]["insert"], "@wlop")
        self.assertEqual(res["items"][0]["cat"], "1")

        res_at = illust.suggest_tags("@鬼刀", self.tag_csv, self.zh_csv, limit=10)
        self.assertEqual(res_at["items"][0]["insert"], "@wlop")

        res_mode = illust.suggest_tags("鬼刀", self.tag_csv, self.zh_csv, limit=10, mode="artist")
        self.assertEqual(res_mode["items"][0]["insert"], "@wlop")

        # 確認多畫師與權重疊加不會多加 @
        asm = illust.assemble({"artist": "wlop, @ask (askzy), (@wlop:1.2)", "scene_tags": "sky"}, dict(illust.DEFAULTS))
        self.assertIn("@wlop, @ask (askzy), (@wlop:1.2)", asm["positive"])


if __name__ == "__main__":
    unittest.main()
