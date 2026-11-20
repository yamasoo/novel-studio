# -*- coding: utf-8 -*-
"""v3 P2：API 識別值改英文後，舊的中文 ID 仍然要能用（舊書籤、瀏覽器存的設定、外部腳本）。"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import ids, importer, layout, project, reverse, search


class NormTest(unittest.TestCase):
    def test_new_ids_pass_through(self):
        for kind, valid in ids.VALID.items():
            for v in valid:
                self.assertEqual(v, ids.norm(kind, v))

    def test_old_ids_and_folder_names(self):
        self.assertEqual("characters", ids.norm("bible_tab", "角色"))
        self.assertEqual("core", ids.norm("bible_tab", "核心"))
        self.assertEqual("structure", ids.norm("bible_tab", "章節結構"))
        self.assertEqual("cards", ids.norm("reverse_group", "章綱"))
        self.assertEqual("bible", ids.norm("reverse_group", layout.BIBLE))
        self.assertEqual("outline", ids.norm("search_scope", "章綱"))
        self.assertEqual("candidates", ids.norm("search_scope", "候選"))
        self.assertEqual("manuscript", ids.norm("import_target", "正文"))

    def test_unknown_passes_through(self):
        self.assertEqual("nope", ids.norm("bible_tab", "nope"))
        self.assertIsNone(ids.norm("bible_tab", None))

    def test_every_alias_targets_a_valid_id(self):
        for kind, table in ids.ALIASES.items():
            for old, new in table.items():
                self.assertIn(new, ids.VALID[kind], "%s：%s → %s" % (kind, old, new))


class ApiCompatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.book = os.path.join(self.tmp.name, "書")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), self.book)

    def tearDown(self):
        self.tmp.cleanup()

    def test_bible_keys_are_new_ids(self):
        b = project.bible(self.book)
        self.assertEqual({"characters", "factions", "world", "drafts", "core"}, set(b))
        self.assertTrue(b["characters"])

    def test_search_accepts_old_and_new_scopes(self):
        new = search.search(self.book, "玉珮", ["manuscript", "bible"])
        old = search.search(self.book, "玉珮", ["正文", "設定"])
        self.assertEqual(["manuscript", "bible"], new["scopes"])
        self.assertEqual(new["scopes"], old["scopes"])
        self.assertEqual(new["results"], old["results"])
        self.assertTrue({r["scope"] for r in new["results"]} <= set(ids.SEARCH_SCOPES))
        # 同一個範圍新舊寫法混用只算一次
        self.assertEqual(["manuscript"], search.search(self.book, "玉珮", ["正文", "manuscript"])["scopes"])

    def test_search_default_scope(self):
        self.assertEqual(["manuscript"], search.search(self.book, "玉珮")["scopes"])

    def test_reverse_groups_accept_old_ids(self):
        self.assertEqual(set(ids.REVERSE_GROUPS), set(reverse.draft_groups(self.book)))
        self.assertEqual(reverse.discard(self.book, "設定"), reverse.discard(self.book, "bible"))
        with self.assertRaises(project.ProjectError):
            reverse.discard(self.book, "不存在的分組")

    def test_import_target_old_and_new(self):
        payload = {"text": "第九十章 測試\n\n一段正文。\n"}
        for target, folder, rid in (("候選", layout.CANDIDATES, "candidates"), ("candidates", layout.CANDIDATES, "candidates"),
                                    ("正文", layout.MANUSCRIPT, "manuscript"), ("manuscript", layout.MANUSCRIPT, "manuscript")):
            res = importer.commit(self.book, payload, {"target": target, "conflict": "overwrite"})
            self.assertEqual(rid, res["target"], target)
            self.assertTrue(res["written"] and res["written"][0]["file"].startswith(folder + "/"), res["written"])

if __name__ == "__main__":
    unittest.main()
