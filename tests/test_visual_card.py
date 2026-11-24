# -*- coding: utf-8 -*-
"""結構化角色視覺卡（漫畫規格 ＋ VN 頭像／立繪／7 表情）單元測試。"""
import os
import tempfile
import unittest

from studio import illust, layout, native, project, prompts, visual_card


def _sample_card():
    return {
        "id": "example_char",
        "name": "示例角色",
        "aliases": ["示例", "小例"],
        "status": "confirmed",
        "source": "bible/characters/示例角色.md",
        "sections": {
            "head": [
                "a 34-year-old woman",
                "short black hair",
                "grey eyes",
                "a thin scar through the left eyebrow",
            ],
            "body": ["average build"],
            "upper": ["a ship-and-anchor tattoo on the right forearm"],
            "lower": ["a long scar along the left calf"],
            "accessory": [
                "wire-rimmed glasses",
                "a silver ring on the right thumb",
            ],
        },
        "outfits": {
            "default": {
                "top": ["a plain grey shirt"],
                "bottom": ["dark trousers", "work boots"],
                "set": [],
                "notes": "日常外出",
            },
            "harbour_work": {
                "top": ["rolled-up sleeves"],
                "bottom": ["rubber boots"],
                "set": ["a canvas apron"],
                "notes": "碼頭幹活",
            },
        },
        "vn": {
            "avatar_accessories": ["wire-rimmed glasses"],
            "sprite_pose": "standing relaxed, hands at sides, facing viewer",
            "expressions": dict(visual_card.DEFAULT_VN_EXPRESSIONS),
        },
        "body": "卡的本文是給人看的，程式不讀。",
    }


class VisualCardTests(unittest.TestCase):
    def test_template_roundtrip_and_check_ok(self):
        raw = _sample_card()
        md = visual_card.render_card(raw, include_vn=True)
        parsed = visual_card.parse_card(md)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["id"], "example_char")
        self.assertEqual(parsed["name"], "示例角色")
        self.assertEqual(parsed["sections"]["head"], raw["sections"]["head"])
        self.assertIn("harbour_work", parsed["outfits"])
        chk = visual_card.check_card(parsed)
        self.assertTrue(chk["ok"], chk["errors"])
        self.assertEqual(chk["errors"], [])
        self.assertEqual(chk["warnings"], [])

    def test_comic_export_strips_vn_and_source(self):
        md = visual_card.render_card(_sample_card(), include_vn=False)
        self.assertNotIn("\nvn:", md)
        self.assertNotIn("\nsource:", md)
        self.assertIn("id: example_char", md)
        self.assertIn("sections:", md)
        self.assertIn("outfits:", md)

    def test_check_card_catches_violations(self):
        bad = visual_card.normalize_card({
            "id": "bad_char",
            "name": "違規角色",
            "sections": {
                "head": ["short black hair", "a plain grey shirt", "smiling", "wire-rimmed glasses"],
                "body": ["standing"],
                "upper": [],
                "lower": [],
                "accessory": [],
            },
            "outfits": {
                "default": {"top": ["angry jacket"], "bottom": [], "set": [], "notes": ""},
            },
        }, fill_vn_defaults=False)
        chk = visual_card.check_card(bad)
        self.assertFalse(chk["ok"])
        joined_err = "\n".join(chk["errors"])
        self.assertIn("年齡", joined_err)
        self.assertIn("性別", joined_err)
        self.assertIn("服裝詞", joined_err)
        self.assertIn("表情詞", joined_err)
        self.assertIn("動作詞", joined_err)
        joined_warn = "\n".join(chk["warnings"])
        self.assertIn("sections.accessory", joined_warn)
        self.assertIn("VN 表情尚未填齊", joined_warn)

    def test_vn_prompt_composition(self):
        vn = visual_card.compose_vn_prompts(_sample_card(), outfit="harbour_work")
        self.assertEqual(vn["outfit"], "harbour_work")
        self.assertIn("a 34-year-old woman", vn["avatar_base"])
        self.assertIn("wire-rimmed glasses", vn["avatar_base"])
        self.assertNotIn("calm look", vn["avatar_base"])
        self.assertIn("calm look", vn["avatar_default"])
        self.assertEqual(len(vn["expressions"]), 7)
        for k in visual_card.VN_EXPRESSIONS:
            self.assertIn(k, vn["avatar_by_expression"])
            self.assertIn(k, vn["sprite_by_expression"])
        self.assertIn("a canvas apron", vn["sprite_body"])
        self.assertIn("standing relaxed", vn["sprite_body"])

    def test_v3_kind_characters_routing_and_save_sync(self):
        prompts.set_lang("zh-TW")
        sys_p, usr_p = illust.ai_card_prompt("---\ntype: character\nname: 示例角色\n---\n\n黑短髮灰眼。", "示例角色", "characters")
        self.assertIn("sections", usr_p)
        self.assertIn("expressions", usr_p)
        self.assertNotIn("no humans", usr_p)

        with tempfile.TemporaryDirectory() as tmp:
            char_rel = layout.CHARACTERS + "/示例角色.md"
            char_path = project.safe_path(tmp, char_rel)
            project.write_atomic(char_path, "---\ntype: character\nname: 示例角色\naliases: [小例]\n---\n\n# 示例角色\n")
            res = native.save_card_result(tmp, {"file": char_rel}, _sample_card())
            self.assertIn("bible/visual-cards/example_char.md", res)
            vc_path = project.safe_path(tmp, "bible/visual-cards/example_char.md")
            self.assertTrue(os.path.isfile(vc_path))
            # 原角色檔同步寫入「## 繪圖提示」，且不會被誤加 no humans
            char_text = project.read_text(char_path)
            legacy = illust.read_card(char_text)
            self.assertIsNotNone(legacy)
            self.assertIn("1girl", legacy["tags"])
            self.assertNotIn("no humans", legacy["tags"].lower())


if __name__ == "__main__":
    unittest.main()
