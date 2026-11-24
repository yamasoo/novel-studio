# -*- coding: utf-8 -*-
"""設定集手動合併（角色別名、備份、角色狀態檔連動、關係表更名去重、視覺卡轉指、日文書在地化）測試。"""
import os
import tempfile
import unittest

from studio import bible_index, bookmeta, layout, migrate, project, relations, visual_card


def _w(book, rel, text):
    p = project.safe_path(book, rel)
    project.write_atomic(p, text)
    return p


class BibleMergeCascadeTest(unittest.TestCase):
    def test_character_merge_cascades_state_relations_visual_card_and_backup(self):
        with tempfile.TemporaryDirectory(prefix="ns-bmerge-") as book:
            bookmeta.write(book, lang="ja", title="ja_demo")
            c1 = layout.CHARACTERS + "/ルゥ.md"
            c2 = layout.CHARACTERS + "/灰色の竜.md"
            _w(book, c1, "---\ntype: character\nname: ルゥ\naliases: []\nrole: supporting\nstatus: canon\n---\n\n# ルゥ\n\n## 一行まとめ\n犬ほどの大きさの竜。\n")
            _w(book, c2, "---\ntype: character\nname: 灰色の竜\naliases: [灰竜]\nrole: supporting\nstatus: draft\n---\n\n# 灰色の竜\n\n## 一行まとめ\n毒を受けた竜。\n")
            # 兩個角色狀態檔
            _w(book, layout.CHARACTER_STATES + "/ルゥ.md", "---\ntype: character-state\nname: ルゥ\n---\n\n# ルゥ\n\n- 場所：灰谷村\n")
            _w(book, layout.CHARACTER_STATES + "/灰色の竜.md", "---\ntype: character-state\nname: 灰色の竜\n---\n\n# 灰色の竜\n\n- 傷：毒\n")
            # 關係表：同時有 主角→ルゥ、主角→灰色の竜、ルゥ→灰色の竜（合併後變自指應刪除）
            from studio import tables
            rel_md = "---\ntype: relations\nupdated_through: 2\n---\n\n# 関係\n\n" + tables.render("relations", tables.keys("relations"), [
                {"id": "L001", "who": "エルマ", "toward": "ルゥ", "relationship": "契約者", "attitude": "信頼", "start_chapter": "1", "end_chapter": "", "reason": "竜約"},
                {"id": "L002", "who": "エルマ", "toward": "灰色の竜", "relationship": "契約者", "attitude": "信頼", "start_chapter": "1", "end_chapter": "", "reason": "竜約"},
                {"id": "L003", "who": "ルゥ", "toward": "灰色の竜", "relationship": "同一", "attitude": "無", "start_chapter": "1", "end_chapter": "", "reason": "誤登記"},
                {"id": "L004", "who": "灰色の竜", "toward": "ボルグ", "relationship": "知り合い", "attitude": "警戒", "start_chapter": "2", "end_chapter": "", "reason": "村で会った"},
            ], "ja") + "\n"
            _w(book, layout.RELATIONS, rel_md)
            # 只有舊檔有結構化視覺卡
            vc = visual_card.normalize_card({
                "id": "grey_dragon", "name": "灰色の竜", "source": c2,
                "sections": {"head": ["a 100-year-old male dragon"], "body": ["small build"], "upper": [], "lower": [], "accessory": []},
                "outfits": {"default": {"top": [], "bottom": [], "set": ["grey scales"], "notes": "原形"}},
            }, fill_vn_defaults=True)
            visual_card.save_card(book, vc)

            rep = bible_index.merge(book, c1, [c2])
            self.assertEqual(rep["canonical"], c1)
            self.assertIn("灰色の竜", rep["aliases"])
            self.assertIn("灰竜", rep["aliases"])
            self.assertEqual(rep["state_merged"], ["灰色の竜"])
            self.assertGreaterEqual(rep["relations_updated"], 2)
            self.assertTrue(rep["visual_cards_note"])

            # 主檔包含日文併入標題（不觸發 v3 轉換）與備份
            c1_txt = project.read_text(project.safe_path(book, c1))
            self.assertIn("## 統合：灰色の竜", c1_txt)
            self.assertNotIn("## 併入：", c1_txt)
            self.assertFalse(os.path.isfile(project.safe_path(book, c2)))
            bak_dir = layout.path(book, layout.STUDIO_BACKUP)
            self.assertTrue(os.path.isdir(bak_dir) and any("合併前" in f for f in os.listdir(bak_dir)))

            # 角色狀態檔已併入且舊檔搬移
            st_txt = project.read_text(project.safe_path(book, layout.CHARACTER_STATES + "/ルゥ.md"))
            self.assertIn("毒", st_txt)
            self.assertFalse(os.path.isfile(project.safe_path(book, layout.CHARACTER_STATES + "/灰色の竜.md")))

            # 關係表：L002 去重、L003 自指移除、L004 改指向 ルゥ
            rows = relations.read_rows(book)
            pairs = [(r["who"], r["toward"]) for r in rows]
            self.assertEqual(pairs, [("エルマ", "ルゥ"), ("ルゥ", "ボルグ")])

            # 視覺卡轉指向 ルゥ
            found_vc = visual_card.find_by_source(book, c1, char_name="ルゥ")
            self.assertIsNotNone(found_vc)
            self.assertEqual(found_vc["card"]["name"], "ルゥ")
            self.assertFalse(migrate.needs_migration(book))


if __name__ == "__main__":
    unittest.main()
