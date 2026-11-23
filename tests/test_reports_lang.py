"""P5 第 2 批：工作台產生的報告依語言。

- 續寫合約、設定索引：寫進書裡的檔案，依**書的語言**（繁中逐字照舊）。
- 偏離報告：只在卷末體檢頁給作者看，依**介面語言**（API 的 lang 參數）。
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from studio import bible_index, contract, drift, layout, lang as lang_mod, project  # noqa: E402

DEMO = os.path.join(ROOT, "demo")
EN, JA, ZH = "en_TheLanternRoad", "ja_辺境の薬師と竜の約束", "退婚之後"


class ReportsLangTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for b in (EN, JA, ZH):
            shutil.copytree(os.path.join(DEMO, b), os.path.join(self.tmp, b))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def book(self, b):
        return os.path.join(self.tmp, b)

    def test_contract_by_book_language(self):
        en = contract.build(self.book(EN))
        self.assertIn("# Continuation contract", en)
        self.assertIn("## 3. Threads that must be carried", en)
        self.assertIn("planted Ch. 2", en)
        self.assertIn("status developing, priority high", en)
        self.assertIn("Wren Alder (protagonist, first appears Ch. 1", en)
        self.assertNotIn("續寫合約", en)
        ja = contract.build(self.book(JA))
        self.assertIn("# 続き書きの契約", ja)
        self.assertIn("（第1章で判明）", ja)
        zh = contract.build(self.book(ZH))
        self.assertIn("# 續寫合約", zh)
        self.assertIn("產生時間: ", zh)

    def test_contract_regenerates_when_language_changes(self):
        b = self.book(EN)
        lang_mod.set_book_lang(b, "zh-TW")
        contract.ensure(b, force=True)
        p = contract.path(b)
        text = project.read_text(p).replace("（沒有；作者自己加的規則寫在這裡）", "- 不要寫夢境")
        project.write_atomic(p, text)
        self.assertIsNone(contract.ensure(b), "章數、語言都沒變：不動作者改過的檔")
        lang_mod.set_book_lang(b, "en")
        self.assertTrue(contract.ensure(b), "書改成英文：重新產生")
        new = project.read_text(p)
        self.assertIn("## Author's additions", new)
        self.assertIn("- 不要寫夢境", new, "作者補充照留")
        self.assertNotIn("(None yet", new)

    def test_contract_section4_strip_for_new_volume(self):
        from studio import native_files

        class C:
            book = self.book(EN)
        t = native_files.contract_text(C(), drop_volume_promise=True)      # 卷綱草稿用：拿掉「卷末承諾」
        self.assertIn("## 3. Threads that must be carried", t)
        self.assertNotIn("End-of-volume promises", t)
        self.assertIn("## 5. Off limits", t)

    def test_drift_report_follows_ui_language(self):
        b = self.book(EN)
        info = drift.drift(b)
        zh = drift.report_md(b, info)
        en = drift.report_md(b, info, lang="en")
        ja = drift.report_md(b, info, lang="ja")
        self.assertTrue(zh.startswith("# 漂移報告"))
        self.assertTrue(en.startswith("# Drift report"))
        self.assertIn("one-sentence paragraphs", en)
        self.assertTrue(ja.startswith("# ずれのレポート"))
        self.assertIn("一文段落", ja)
        self.assertEqual(len(drift.findings(info)), len(drift.findings(info, "en")))

    def test_bible_index_by_book_language(self):
        bible_index.rebuild(self.book(EN))
        en = project.read_text(layout.path(self.book(EN), layout.BIBLE_INDEX))
        self.assertTrue(en.startswith("# Bible index"))
        self.assertIn("｜power-system｜canon｜", en)
        bible_index.rebuild(self.book(ZH))
        self.assertTrue(project.read_text(layout.path(self.book(ZH), layout.BIBLE_INDEX)).startswith("# 設定索引"))


if __name__ == "__main__":
    unittest.main()
