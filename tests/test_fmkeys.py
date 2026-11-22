# -*- coding: utf-8 -*-
"""frontmatter 的鍵：程式內部英文，檔案裡中文、英文寫法都認（v3 P3 第四批）。"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import fmkeys, project, shared  # noqa: E402

ZH = "---\n類型: 章綱\n章號: 3\n章名: 鋪子裡的帳\n狀態: 草稿\n自訂: x\n---\n\n# 第3章\n"
EN = "---\ntype: 章綱\nchapter: 3\ntitle: 鋪子裡的帳\nstatus: 草稿\n自訂: x\n---\n\n# 第3章\n"


class FmKeysTest(unittest.TestCase):
    def test_read_both_spellings(self):
        for text in (ZH, EN):
            fm, body = project.split_frontmatter(text)
            self.assertEqual({"type": "章綱", "chapter": 3, "title": "鋪子裡的帳", "status": "草稿", "自訂": "x"}, fm)
            self.assertEqual("\n# 第3章\n", body)
        self.assertEqual("類型", list(project.split_frontmatter_raw(ZH)[0])[0], "raw 照檔案裡的寫法")

    def test_first_spelling_wins(self):
        fm, _ = project.split_frontmatter("---\n狀態: 草稿\nstatus: approved\n---\n")
        self.assertEqual("草稿", fm["status"])

    def test_set_keeps_file_spelling(self):
        self.assertIn("\n狀態: approved\n", project.set_frontmatter_field(ZH, "status", "已確認"), "鍵照原寫法，值寫英文 ID")
        self.assertIn("\nstatus: approved\n", project.set_frontmatter_field(EN, "status", "approved"))
        self.assertIn("\n狀態: approved\n", project.set_frontmatter_field(ZH, "狀態", "已確認"), "中文鍵也收")

    def test_new_line_follows_write_setting(self):
        self.assertEqual("en", fmkeys.WRITE, "v3 寫英文鍵")
        self.assertEqual("---\ntype: 卷綱\ntitle: 舊帳\n---\n", project.set_frontmatter_field("---\ntype: 卷綱\n---\n", "title", "舊帳"))
        self.assertEqual("---\n類型: 卷綱\ntitle: 舊帳\n---\n", project.set_frontmatter_field("---\n類型: 卷綱\n---\n", "title", "舊帳"),
                         "插在中文的類型後面")
        old = fmkeys.WRITE
        try:
            fmkeys.WRITE = "zh"
            out = project.set_frontmatter_field("---\n類型: 卷綱\n---\n", "title", "舊帳")
            self.assertEqual("---\n類型: 卷綱\n卷名: 舊帳\n---\n", out, "title 依文件類型寫成卷名")
            self.assertIn("書名: 書", project.set_frontmatter_field("---\n類型: 故事核心\n---\n", "title", "書"))
        finally:
            fmkeys.WRITE = old

    def test_shared_set_fm_removes_both_spellings(self):
        text = "---\n名稱: 甲\nname: 乙\n語言: ja\n---\n本文\n"
        self.assertEqual("---\n語言: ja\n---\n本文\n", shared.set_fm(text, "name", None))
        self.assertEqual("---\n名稱: 甲\nname: 乙\nlang: en\n---\n本文\n", shared.set_fm(text, "lang", "en"))

    def test_every_zh_key_maps(self):
        for zh, en in fmkeys.ZH2EN.items():
            self.assertRegex(en, r"^[a-z_]+$", zh)
            self.assertIn(zh, fmkeys.file_keys(en))


if __name__ == "__main__":
    unittest.main()


class FmValuesTest(unittest.TestCase):
    """frontmatter 的值：檔案寫中文或英文 ID，交給介面的都一樣（v3 P3 第四批 4c-1）。"""

    def test_value_maps(self):
        self.assertEqual("approved", fmkeys.value_en("status", "已確認"))
        self.assertEqual("approved", fmkeys.value_en("狀態", "approved"))
        self.assertEqual("已確認", fmkeys.disp("status", "approved"))
        self.assertEqual("伏筆", fmkeys.disp("type", "伏筆"), "中文的同義寫法照原樣")
        self.assertEqual("怪物", fmkeys.disp("role", "怪物"), "作者自己寫的值照原樣")
        self.assertEqual("true", fmkeys.value_en("default", True))
        for key, pairs in fmkeys.VALUES.items():
            for e, zh in pairs:
                self.assertRegex(e, r"^[a-z][a-z-]*$")
                self.assertEqual(e, fmkeys.value_en(key, zh))

    def test_write_value(self):
        text = "---\ntype: 角色\nrole: 主角\n---\n"
        self.assertEqual("en", fmkeys.WRITE_VALUES, "v3 寫英文 ID")
        self.assertIn("role: antagonist", project.set_frontmatter_field(text, "role", "反派"))
        self.assertIn("default: true", shared.set_fm("---\nname: x\n---\n", "default", "是"))
        old = fmkeys.WRITE_VALUES
        try:
            fmkeys.WRITE_VALUES = "zh"
            self.assertIn("role: 反派", project.set_frontmatter_field(text, "role", "antagonist"))
        finally:
            fmkeys.WRITE_VALUES = old

    def test_demo_books_read_the_same_with_chinese_values(self):
        """示範書（英文 ID）的值全部換回中文：設定集、章節、卷綱、總覽、設定索引的結果都跟原本一樣（還沒轉換的舊書照樣能讀）。"""
        import re
        import shutil
        import tempfile
        from studio import bible_index, volume
        tmp = tempfile.mkdtemp()
        try:
            for name in ("退婚之後", "en_TheLanternRoad", "ja_辺境の薬師と竜の約束"):
                src = os.path.join(ROOT, "demo", name)
                dst = os.path.join(tmp, name)
                shutil.copytree(src, dst)
                n = 0
                for base, _, files in os.walk(dst):
                    for f in files:
                        if not f.endswith(".md"):
                            continue
                        p = os.path.join(base, f)
                        t = project.read_text(p)
                        if not t.startswith("---"):
                            continue
                        head, sep, rest = t[3:].partition("\n---")
                        new = re.sub(r"(?m)^(type|status|role|category): *([^#\n]+?)( *#.*)?$",
                                     lambda m: "%s: %s" % (m.group(1), fmkeys.disp(m.group(1), m.group(2))), head)
                        if new != head:
                            n += 1
                            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                                fh.write("---" + new + sep + rest)
                self.assertGreater(n, 10, name)

                def view(d):
                    return {"bible": project.bible(d), "chapters": project.scan_chapters(d),
                            "volumes": volume.list_volumes(d), "overview": project.overview(d)["status_count"],
                            "index": bible_index._index_markdown(bible_index.build(d))}
                a, b = view(src), view(dst)
                for k in a:
                    self.assertEqual(json_norm(a[k], src), json_norm(b[k], dst), "%s %s" % (name, k))
        finally:
            shutil.rmtree(tmp)


def json_norm(v, root):
    """去掉會變的欄位（修改時間、書的路徑）再比。"""
    import json
    if isinstance(v, dict):
        return {k: json_norm(x, root) for k, x in v.items() if k not in ("mtime", "mtime_ms")}
    if isinstance(v, list):
        return [json_norm(x, root) for x in v]
    return v.replace(root, "<ROOT>") if isinstance(v, str) else v


class ChapterNumberTest(unittest.TestCase):
    """v3：章號存整數、章節範圍存 [lo, hi]、所屬卷存整數；兩種舊寫法都讀得懂。"""

    def test_ch_int(self):
        for v in (12, "12", "第012章", "第12章", "ch-0012", " 第 12 章 "):
            self.assertEqual(12, fmkeys.ch_int(v), v)
        for v in (None, "", "未知", "第三章前後x"):
            self.assertIsNone(fmkeys.ch_int(v), v)

    def test_disp_and_value(self):
        self.assertEqual("第012章", fmkeys.ch_disp(12))
        self.assertEqual("第012章", fmkeys.ch_disp("第012章"))
        self.assertEqual(12, fmkeys.ch_value("第012章"))
        self.assertEqual("[1, 60]", fmkeys.range_value(1, 60))

    def test_volume_int(self):
        self.assertEqual(1, fmkeys.volume_int("第一卷"))
        self.assertEqual(12, fmkeys.volume_int("第十二卷"))
        self.assertEqual(20, fmkeys.volume_int("第二十卷"))
        self.assertEqual(3, fmkeys.volume_int("3"))
        self.assertIsNone(fmkeys.volume_int("序卷"))

    def test_read_after_write(self):
        text = "---\ntype: character\nfirst_appearance: 3\n---\n"
        fm, _ = project.split_frontmatter(text)
        self.assertEqual("第003章", fmkeys.ch_disp(fm["first_appearance"]))
