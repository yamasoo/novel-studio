# -*- coding: utf-8 -*-
"""book.json 與格式移轉工具（v3 P3 第一批）。"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import bookmeta, layout, migrate, project  # noqa: E402
from studio import lang as lang_mod  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "tools"))
import migrate_v3  # noqa: E402

DEMOS = ("退婚之後", "en_TheLanternRoad", "ja_辺境の薬師と竜の約束")


def _snapshot(d):
    out = {}
    for base, dirs, files in os.walk(d):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(base, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, d).replace(os.sep, "/")] = fh.read()
    return out


class BookMetaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_create_book_writes_meta_without_lang(self):
        d = project.create_book(self.tmp, "新書")
        m = bookmeta.read(d)
        self.assertEqual(layout.SCHEMA_VERSION, m["schema_version"])
        self.assertEqual("新書", m["title"])
        self.assertNotIn("lang", m, "語言等作者選了再寫，沒寫時照舊看故事核心")
        self.assertEqual(["schema_version", "title", "created"], list(m))

    def test_lang_precedence(self):
        d = project.create_book(self.tmp, "b")
        os.makedirs(layout.path(d, layout.BIBLE))
        with open(layout.path(d, layout.STORY_CORE), "w", encoding="utf-8") as f:
            f.write("---\n類型: 故事核心\n語言: ja\n---\n\n# x\n")
        self.assertEqual("ja", lang_mod.book_lang(d), "book.json 沒有語言：看故事核心")
        lang_mod.set_book_lang(d, "en")
        self.assertEqual("en", bookmeta.read(d)["lang"])
        self.assertIn("語言: en", project.read_text(layout.path(d, layout.STORY_CORE)), "故事核心照舊同步（技能還會讀）")
        self.assertFalse(os.path.exists(layout.path(d, layout.STUDIO, "lang")))
        with open(layout.path(d, layout.STORY_CORE), "w", encoding="utf-8") as f:
            f.write("---\n語言: ja\n---\n")
        self.assertEqual("en", lang_mod.book_lang(d), "book.json 優先")

    def test_set_lang_removes_old_lang_file_and_keeps_other_fields(self):
        d = os.path.join(self.tmp, "old")
        os.makedirs(layout.path(d, layout.STUDIO))
        with open(layout.path(d, layout.STUDIO, "lang"), "w") as f:
            f.write("ja\n")
        self.assertEqual("ja", lang_mod.book_lang(d))
        bookmeta.write(d, chapter_target_length=2500)
        lang_mod.set_book_lang(d, "zh-TW")
        m = bookmeta.read(d)
        self.assertEqual("zh-TW", m["lang"])
        self.assertEqual(2500, m["chapter_target_length"])
        self.assertFalse(os.path.exists(layout.path(d, layout.STUDIO, "lang")))

    def test_broken_meta_falls_back(self):
        d = os.path.join(self.tmp, "x")
        os.makedirs(d)
        with open(bookmeta.path(d), "w") as f:
            f.write("{壞掉")
        self.assertEqual({}, bookmeta.read(d))
        self.assertEqual(2, bookmeta.version(d))
        self.assertEqual("zh-TW", lang_mod.book_lang(d))


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lib = os.path.join(self.tmp, "lib")
        os.makedirs(self.lib)
        for n in DEMOS:
            shutil.copytree(os.path.join(ROOT, "demo", n), os.path.join(self.lib, n))
        os.makedirs(os.path.join(self.lib, "_共用"))         # 共用庫不是書

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_library_mode_finds_books(self):
        self.assertEqual(sorted(DEMOS), sorted(os.path.basename(b) for b in migrate.books_in(self.lib)))
        b = os.path.join(self.lib, DEMOS[0])
        self.assertEqual([b], migrate.books_in(b))

    def test_dry_run_changes_nothing(self):
        b = os.path.join(self.lib, DEMOS[1])
        before = _snapshot(b)
        r = migrate.migrate(b, dry_run=True)
        self.assertEqual("dry_run", r["status"])
        self.assertEqual(["book_meta"], [s["key"] for s in r["steps"]])
        self.assertIn("建立 book.json（語言 en）", r["steps"][0]["changes"])
        self.assertEqual(before, _snapshot(b))

    def test_migrate_then_skip(self):
        for n, lang in zip(DEMOS, ("zh-TW", "en", "ja")):
            b = os.path.join(self.lib, n)
            before = _snapshot(b)
            r = migrate.migrate(b)
            self.assertEqual("done", r["status"], r)
            m = bookmeta.read(b)
            self.assertEqual(lang, m["lang"])
            self.assertEqual(n, m["title"])
            self.assertEqual(layout.SCHEMA_VERSION, m["schema_version"])
            self.assertEqual(lang, lang_mod.book_lang(b))
            after = _snapshot(b)
            changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
            self.assertTrue(all(k == "book.json" or k.startswith(layout.STUDIO + "/") for k in changed), changed)
            self.assertTrue(os.path.isfile(r["report"]))
            self.assertTrue(os.path.isfile(r["backup"]))
            self.assertEqual("skipped", migrate.migrate(b)["status"], "第二次直接跳過")

    def test_stats_mismatch_rolls_back(self):
        b = os.path.join(self.lib, DEMOS[0])
        before = _snapshot(b)
        real = migrate.stats
        calls = []

        def fake(d):
            s = real(d)
            calls.append(1)
            if len(calls) == 2:
                s["章數"] += 1
            return s
        with mock.patch.object(migrate, "stats", fake):
            r = migrate.migrate(b)
        self.assertEqual("rolled_back", r["status"])
        self.assertIn("章數", r["message"])
        after = _snapshot(b)
        self.assertEqual({k: v for k, v in before.items()}, {k: v for k, v in after.items() if not k.startswith(layout.STUDIO_BACKUP + "/")})

    def test_step_error_rolls_back(self):
        b = os.path.join(self.lib, DEMOS[2])
        before = _snapshot(b)

        def boom(d):
            with open(os.path.join(d, "半途.txt"), "w") as f:
                f.write("x")
            raise RuntimeError("壞掉")
        bad = migrate.Step("boom", "會失敗的步驟", lambda d: True, lambda d: ["x"], boom)
        with mock.patch.object(migrate, "STEPS", migrate.STEPS + [bad]):
            r = migrate.migrate(b)
        self.assertEqual("rolled_back", r["status"])
        self.assertIn("壞掉", r["message"])
        after = {k: v for k, v in _snapshot(b).items() if not k.startswith(layout.STUDIO_BACKUP + "/")}
        self.assertEqual(before, after)

    def test_rollback_restores_and_keeps_git(self):
        b = os.path.join(self.lib, DEMOS[0])
        os.makedirs(os.path.join(b, ".git"))
        with open(os.path.join(b, ".git", "HEAD"), "w") as f:
            f.write("ref: x\n")
        before = _snapshot(b)
        migrate.migrate(b)
        with open(layout.path(b, layout.MANUSCRIPT, "後來加的.md"), "w") as f:
            f.write("x")
        migrate.rollback(b)
        after = {k: v for k, v in _snapshot(b).items() if not k.startswith(layout.STUDIO_BACKUP + "/")}
        self.assertEqual(before, after)
        with zipfile_names(migrate.backups(b)[-1]) as names:
            self.assertFalse(any(n.startswith(".git/") for n in names), "備份不含 .git")

    def test_cli(self):
        b = os.path.join(self.lib, DEMOS[1])
        self.assertEqual(0, migrate_v3.main([self.lib, "--dry-run"]))
        self.assertFalse(bookmeta.exists(b))
        self.assertEqual(0, migrate_v3.main([self.lib]))
        self.assertTrue(bookmeta.exists(b))
        self.assertEqual(0, migrate_v3.main([self.lib]))
        self.assertEqual(0, migrate_v3.main([b, "--rollback"]))
        self.assertFalse(bookmeta.exists(b))
        self.assertEqual(2, migrate_v3.main([self.lib, "--rollback"]))
        self.assertEqual(2, migrate_v3.main([os.path.join(self.tmp, "沒有這個")]))


class zipfile_names:
    def __init__(self, p):
        import zipfile
        self.z = zipfile.ZipFile(p)

    def __enter__(self):
        return self.z.namelist()

    def __exit__(self, *a):
        self.z.close()


if __name__ == "__main__":
    unittest.main()
