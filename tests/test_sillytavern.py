# -*- coding: utf-8 -*-
"""SillyTavern（酒館）匯出模組單元測試。"""
import json
import os
import tempfile
import unittest
import zipfile

from studio import export as export_mod, sillytavern


def _make_sample_book(root: str) -> str:
    bdir = os.path.join(root, "sample_book")
    for sub in ("bible/characters", "bible/factions", "bible/world", "tracking"):
        os.makedirs(os.path.join(bdir, sub), exist_ok=True)
    with open(os.path.join(bdir, "book.json"), "w", encoding="utf-8") as f:
        json.dump({"format_version": 3, "title": "範例奇幻錄", "lang": "zh-TW"}, f, ensure_ascii=False)
    with open(os.path.join(bdir, "bible", "story-core.md"), "w", encoding="utf-8") as f:
        f.write("---\ntitle: 範例奇幻錄\n---\n\n一座漂浮在雲海上的鍊金術港城，少年與師父追查失落星圖。\n")
    with open(os.path.join(bdir, "bible", "characters", "lin.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: 林青\naliases:\n  - 阿青\nrole: 主角\nfaction: 星港協會\ntags:\n  - 沉穩\n  - 鍊金師\n---\n\n出身港城下層的年輕鍊金師，隨身攜帶黃銅懷錶。\n")
    with open(os.path.join(bdir, "bible", "factions", "guild.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: 星港協會\naliases:\n  - 協會\n---\n\n掌管星圖與飛船航道的古老同業公會。\n")
    with open(os.path.join(bdir, "bible", "world", "skyport.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: 雲海星港\n---\n\n建於浮空礦脈之上的貿易港都。\n")
    with open(os.path.join(bdir, "bible", "glossary.md"), "w", encoding="utf-8") as f:
        f.write("# 名詞表\n\n| 名詞 | 說明 |\n|---|---|\n| 星塵結晶 | 驅動浮空船的核心能源 |\n")
    return bdir


class TestSillyTavernExport(unittest.TestCase):
    def test_png_chara_roundtrip(self):
        base = sillytavern.make_placeholder_png(64, 64, "test")
        card = {"spec": "chara_card_v2", "spec_version": "2.0", "data": {"name": "林青", "description": "測試"}}
        embedded = sillytavern.embed_chara_chunk(base, card)
        self.assertTrue(embedded.startswith(sillytavern.PNG_SIG))
        loaded = sillytavern.read_chara_chunk(embedded)
        self.assertEqual(loaded["spec"], "chara_card_v2")
        self.assertEqual(loaded["data"]["name"], "林青")

    def test_lorebook_and_cards_and_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            bdir = _make_sample_book(td)
            m = sillytavern.meta(bdir)
            self.assertEqual(m["counts"]["characters"], 1)
            self.assertEqual(m["counts"]["factions"], 1)
            self.assertEqual(m["counts"]["world"], 1)
            self.assertEqual(m["counts"]["glossary"], 1)

            # 1. Lorebook JSON
            r_lore = sillytavern.export_sillytavern(bdir, {"mode": "lorebook"})
            self.assertTrue(r_lore["file"].endswith(".json"))
            self.assertEqual(r_lore["entries"], 5)  # core + 1 char + 1 faction + 1 world + 1 glossary
            lore_path = export_mod.export_path(bdir, r_lore["file"])
            with open(lore_path, encoding="utf-8") as f:
                lore = json.load(f)
            entries = list(lore["entries"].values())
            self.assertTrue(any(e["constant"] for e in entries))
            self.assertTrue(any("阿青" in e["key"] for e in entries))
            self.assertTrue(any("星塵結晶" in e["key"] for e in entries))

            # 2. GM Card PNG
            r_gm = sillytavern.export_sillytavern(bdir, {"mode": "gm"})
            self.assertTrue(r_gm["file"].endswith(".png"))
            with open(export_mod.export_path(bdir, r_gm["file"]), "rb") as f:
                gm_card = sillytavern.read_chara_chunk(f.read())
            self.assertEqual(gm_card["spec"], "chara_card_v2")
            self.assertIn("範例奇幻錄", gm_card["data"]["name"])

            # 3. Character Card PNG
            r_ch = sillytavern.export_sillytavern(bdir, {"mode": "character", "character": "lin"})
            with open(export_mod.export_path(bdir, r_ch["file"]), "rb") as f:
                ch_card = sillytavern.read_chara_chunk(f.read())
            self.assertEqual(ch_card["data"]["name"], "林青")
            self.assertIn("黃銅懷錶", ch_card["data"]["description"])

            # 4. Bundle ZIP
            r_zip = sillytavern.export_sillytavern(bdir, {"mode": "bundle"})
            self.assertTrue(r_zip["file"].endswith(".zip"))
            self.assertEqual(r_zip["cards"], 2)
            with zipfile.ZipFile(export_mod.export_path(bdir, r_zip["file"]), "r") as zf:
                names = zf.namelist()
                self.assertIn("README.txt", names)
                self.assertTrue(any(n.endswith("_lorebook.json") for n in names))
                self.assertTrue(any(n.endswith("_GM.png") for n in names))
                self.assertTrue(any(n.endswith("林青.png") for n in names))

            # list_exports 需包含這 4 個新檔
            listed = [x["file"] for x in export_mod.list_exports(bdir)]
            for fn in (r_lore["file"], r_gm["file"], r_ch["file"], r_zip["file"]):
                self.assertIn(fn, listed)


if __name__ == "__main__":
    unittest.main()
