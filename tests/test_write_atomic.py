# -*- coding: utf-8 -*-
"""project.write_atomic 的最小測試：成功覆寫，以及「寫入中途失敗時原檔不變」。"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import project


class WriteAtomicTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.path = os.path.join(self.dir, "稿.md")

    def tearDown(self):
        self._tmp.cleanup()

    def leftovers(self):
        return [f for f in os.listdir(self.dir) if f.endswith(".tmp")]

    def test_建立與覆寫(self):
        project.write_atomic(self.path, "第一版\n")
        self.assertEqual(project.read_text(self.path), "第一版\n")
        project.write_atomic(self.path, "第二版\n")
        self.assertEqual(project.read_text(self.path), "第二版\n")
        self.assertEqual(self.leftovers(), [])

    def test_自動建父目錄(self):
        p = os.path.join(self.dir, "正文", "第001章.md")
        project.write_atomic(p, "內容\n")
        self.assertEqual(project.read_text(p), "內容\n")

    def test_換檔失敗時原檔不變(self):
        project.write_atomic(self.path, "舊內容\n")
        with mock.patch("os.replace", side_effect=PermissionError("被鎖住")):
            with self.assertRaises(OSError):
                project.write_atomic(self.path, "新內容")
        self.assertEqual(project.read_text(self.path), "舊內容\n")
        self.assertEqual(self.leftovers(), [])

    def test_寫入中途失敗時原檔不變(self):
        project.write_atomic(self.path, "舊內容\n")
        with mock.patch("os.fsync", side_effect=OSError("磁碟滿")):
            with self.assertRaises(OSError):
                project.write_atomic(self.path, "新內容")
        self.assertEqual(project.read_text(self.path), "舊內容\n")
        self.assertEqual(self.leftovers(), [])

    def test_檔案不存在時失敗不留半個檔(self):
        with mock.patch("os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                project.write_atomic(self.path, "內容")
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual(self.leftovers(), [])

    def test_編碼與換行(self):
        text = "---\n類型: 正文\n---\n\n# 第1章 測試\n\n中文段落。\n"
        project.write_atomic(self.path, text)
        with open(self.path, "rb") as f:
            raw = f.read()
        self.assertEqual(raw, text.encode("utf-8"))
        self.assertNotIn(b"\r", raw)


if __name__ == "__main__":
    unittest.main()
