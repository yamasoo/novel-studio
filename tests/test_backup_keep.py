# -*- coding: utf-8 -*-
"""tracking.backup 的備份上限測試：同一組只留最新 BACKUP_KEEP 份，其他檔案不動。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import tracking


class BackupKeepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.book = os.path.join(self.tmp.name, "書")
        self.d = os.path.join(self.book, ".studio", "備份")
        os.makedirs(self.d)
        self.src = os.path.join(self.book, "設定", "角色", "周叔.md")
        os.makedirs(os.path.dirname(self.src))
        with open(self.src, "w", encoding="utf-8", newline="\n") as f:
            f.write("新版內容\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, d, name, text):
        with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def test_keeps_latest_backup_keep_in_same_group_only(self):
        base = 1700000000          # 遠早於現在，新備份一定是最新的
        old = ["修改前_周叔.%d.md" % (base + i) for i in range(35)]
        for i, name in enumerate(old):
            self._write(self.d, name, "舊備份 %d\n" % i)
        # 不符合樣式的檔案與其他組、子目錄都不該被動到
        self._write(self.d, "筆記.md", "別動我\n")
        self._write(self.d, "修改前_周叔.草稿.md", "別動我\n")
        self._write(self.d, "追加前_周叔.%d.md" % (base + 500), "別組\n")
        sub = os.path.join(self.d, "_共用", ".備份")
        os.makedirs(sub)
        self._write(sub, "修改前_周叔.%d.md" % (base + 1), "子目錄\n")

        out = tracking.backup(self.book, self.src, "修改前")

        self.assertTrue(out and os.path.isfile(out))
        kept = sorted(f for f in os.listdir(self.d)
                      if f.startswith("修改前_周叔.") and f.endswith(".md") and f[len("修改前_周叔."):-3].isdigit())
        self.assertEqual(len(kept), tracking.BACKUP_KEEP)
        self.assertEqual(tracking.BACKUP_KEEP, 30)
        self.assertIn(os.path.basename(out), kept)                       # 最新的留著
        self.assertIn("修改前_周叔.%d.md" % (base + 34), kept)           # 舊的最新幾份留著
        self.assertIn("修改前_周叔.%d.md" % (base + 6), kept)           # 36 份取最新 30 份
        self.assertNotIn("修改前_周叔.%d.md" % (base + 5), kept)         # 最舊的被修剪
        self.assertNotIn(old[0], kept)
        self.assertTrue(os.path.isfile(os.path.join(self.d, "筆記.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.d, "修改前_周叔.草稿.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.d, "追加前_周叔.%d.md" % (base + 500))))
        self.assertTrue(os.path.isfile(os.path.join(sub, "修改前_周叔.%d.md" % (base + 1))))

    def test_missing_source_returns_none_and_trims_nothing(self):
        name = "修改前_周叔.%d.md" % 1700000000
        self._write(self.d, name, "舊備份\n")
        self.assertIsNone(tracking.backup(self.book, os.path.join(self.book, "沒有.md"), "修改前"))
        self.assertTrue(os.path.isfile(os.path.join(self.d, name)))


if __name__ == "__main__":
    unittest.main()
