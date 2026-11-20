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
V2_DEMO = os.path.join(ROOT, "tests", "fixtures", "v2_demo")      # v2 格式的示範書（P3 第二批轉換前的樣子），測移轉用


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
            shutil.copytree(os.path.join(V2_DEMO, n), os.path.join(self.lib, n))
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
        self.assertEqual(["book_meta", "rename"], [s["key"] for s in r["steps"]])
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
            after = {k: v for k, v in _snapshot(b).items() if not k.startswith(layout.MIGRATE_DIR + "/")}
            rewritten = {"CLAUDE.md", layout.GLOSSARY, layout.BIBLE_INDEX}    # 內容裡有路徑的系統檔
            moved = {migrate.map_rel(k): v for k, v in before.items() if k != ".studio/lang"}
            self.assertEqual(set(moved) | {"book.json"}, set(after), "只多 book.json，其他都是搬到新位置")
            for k, v in moved.items():
                if k not in rewritten:
                    self.assertEqual(v, after[k], k)
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
        self.assertEqual({k: v for k, v in before.items()}, {k: v for k, v in after.items() if not k.startswith(layout.MIGRATE_DIR + "/")})

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
        after = {k: v for k, v in _snapshot(b).items() if not k.startswith(layout.MIGRATE_DIR + "/")}
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
        after = {k: v for k, v in _snapshot(b).items() if not k.startswith(layout.MIGRATE_DIR + "/")}
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


class RenameStepTest(unittest.TestCase):
    """第二步：資料夾與系統檔名換成英文（工作台換成 v3 名稱後啟用）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lib = os.path.join(self.tmp, "lib")
        os.makedirs(self.lib)
        self.book = os.path.join(self.lib, "退婚之後")
        shutil.copytree(os.path.join(V2_DEMO, "退婚之後"), self.book)
        b = self.book

        def w(rel, text):
            p = os.path.join(b, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        # 各種會被搬動或改寫的東西
        w(".studio/修訂/第001章.json", json.dumps({"path": "正文/第001章_退婚當天.md", "base_path": "候選/第003章_x.md",
                                                  "note": "設定/那個不是路徑", "n": 3}, ensure_ascii=False))
        w(".studio/反推/累積.json", "{}")
        w(".studio/反推/state.json", "{}")
        w(".studio/反推/草稿/設定/角色/甲.md", "# 甲\n")
        w(".studio/反推/草稿/設定/名詞表.md", "| 名詞 | 類別 | 說明 | 注意 |\n|---|---|---|---|\n| a | 物品 | b | 詳見 設定/世界觀/兵器.md |\n")
        w(".studio/流程/目前.json", json.dumps({"wait": {"path": "候選/第003章_x.md"}}, ensure_ascii=False))
        w(".studio/備份/插圖/舊.png", "x")
        w(".studio/jobs/1.json", json.dumps({"prompt": "請寫到 設定/故事核心.md"}, ensure_ascii=False))
        w("插圖/_插圖.json", json.dumps({"設定/角色/林晚.md": {"main": "插圖/林晚/1.png"}}, ensure_ascii=False))
        w("插圖/畫風.json", "{}")
        w("設定/自訂資料夾/筆記.md", "作者自己的資料夾\n")
        w("候選/新書草稿/骨架.json", "{}")
        gl = project.read_text(layout.path(b, migrate.v2_view()["GLOSSARY"])).rstrip("\n") + "\n| 青雲劍 | 物品 | 佩劍 | 詳見 設定/世界觀/兵器.md；見 追蹤/時間線.md |\n"
        w("設定/名詞表.md", gl)
        w("正文/第003章_路徑字樣.md", "# 第三章\n\n她在設定/世界觀/兵器.md 這幾個字前停住，又看了看正文/第001章.md。\n")
        os.makedirs(os.path.join(b, "匯出"), exist_ok=True)       # 空資料夾
        claude = project.read_text(os.path.join(b, "CLAUDE.md"))
        w("CLAUDE.md", claude + "\n- 角色檔放在 `設定/角色/`，正文在 正文/。\n")
        self.before = _snapshot(b)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_plan(self):
        r = migrate.migrate(self.book, dry_run=True)
        steps = {s["key"]: s["changes"] for s in r["steps"]}
        self.assertIn("rename", steps)
        self.assertTrue(any(c.startswith("設定/ → bible/") for c in steps["rename"]), steps["rename"])
        self.assertIn("匯出/ → export/（空資料夾）", steps["rename"])
        self.assertEqual(self.before, _snapshot(self.book))

    def test_migrate(self):
        r = migrate.migrate(self.book)
        self.assertEqual("done", r["status"], r.get("message"))
        after = _snapshot(self.book)
        rewritten = {"CLAUDE.md", "bible/glossary.md", ".studio/revisions/第001章.json", ".studio/pipeline/current.json",
                     ".studio/reverse/drafts/bible/glossary.md", "illust/_illustrations.json"}
        for rel, data in self.before.items():
            new = migrate.map_rel(rel)
            if rel == ".studio/lang":
                continue
            self.assertIn(new, after, rel)
            if new not in rewritten:
                self.assertEqual(data, after[new], "內容不能變：%s" % rel)
        for top in migrate.TOP_V2:
            self.assertFalse(os.path.exists(os.path.join(self.book, top)), top)
        self.assertTrue(os.path.isdir(os.path.join(self.book, "export")), "空資料夾也要換名稱")
        self.assertEqual(r["stats"], migrate.stats(self.book))
        rd = lambda rel: after[rel].decode("utf-8")
        rec = json.loads(rd(".studio/revisions/第001章.json"))
        self.assertEqual("manuscript/第001章_退婚當天.md", rec["path"])
        self.assertEqual("candidates/第003章_x.md", rec["base_path"])
        self.assertEqual("設定/那個不是路徑", rec["note"], "不是路徑的字串不動")
        self.assertIn("詳見 bible/world/兵器.md；見 tracking/timeline.md", rd("bible/glossary.md"))
        self.assertIn("詳見 bible/world/兵器.md", rd(".studio/reverse/drafts/bible/glossary.md"))
        self.assertIn("`bible/characters/`，正文在 manuscript/。", rd("CLAUDE.md"))
        self.assertIn("bible/characters/林晚.md", rd("illust/_illustrations.json"))
        self.assertIn("illust/林晚/1.png", rd("illust/_illustrations.json"))
        self.assertIn("設定/世界觀/兵器.md", rd("manuscript/第003章_路徑字樣.md"), "正文一個字都不能改")
        self.assertIn("設定/故事核心.md", rd(".studio/jobs/1.json"), "長字串裡的路徑不動（任務紀錄是歷史）")
        self.assertIn("bible/自訂資料夾/筆記.md", after)
        self.assertIn(".studio/backup/illust/舊.png", after)
        self.assertIn(".studio/reverse/drafts/bible/characters/甲.md", after)
        self.assertIn("candidates/spinoff/skeleton.json", after)
        self.assertEqual("skipped", migrate.migrate(self.book)["status"])
        migrate.rollback(self.book)
        restored = {k: v for k, v in _snapshot(self.book).items() if not k.startswith(layout.MIGRATE_DIR + "/")}
        self.assertEqual(self.before, restored)
        self.assertTrue(os.path.isdir(os.path.join(self.book, "匯出")), "空資料夾也要還原")

    def test_collision_rolls_back(self):
        os.makedirs(os.path.join(self.book, "bible"))
        with open(os.path.join(self.book, "bible", "style.md"), "w", encoding="utf-8") as f:
            f.write("另一份\n")
        before = _snapshot(self.book)
        r = migrate.migrate(self.book)
        self.assertEqual("rolled_back", r["status"])
        self.assertIn("新位置已經有檔案：bible/style.md", r["message"])
        self.assertEqual(before, {k: v for k, v in _snapshot(self.book).items() if not k.startswith(layout.MIGRATE_DIR + "/")})

    def test_library_shared(self):
        sh = os.path.join(self.lib, "_共用")
        for rel in ("文風/冷硬派.md", "結構/三幕式.md", "作者偏好.md", ".備份/x.md", ".刪除/y.md"):
            os.makedirs(os.path.dirname(os.path.join(sh, rel)), exist_ok=True)
            with open(os.path.join(sh, rel), "w", encoding="utf-8") as f:
                f.write(rel)
        self.assertEqual(["_共用/ → _shared/（5 個檔）"], migrate.migrate_library(self.lib, dry_run=True))
        self.assertTrue(os.path.isdir(sh))
        self.assertEqual(0, migrate_v3.main([self.lib]))
        self.assertFalse(os.path.exists(sh))
        for rel in ("styles/冷硬派.md", "structures/三幕式.md", "author-prefs.md", ".backup/x.md", ".trash/y.md"):
            self.assertTrue(os.path.isfile(os.path.join(self.lib, "_shared", *rel.split("/"))), rel)
        self.assertTrue(os.path.isdir(os.path.join(self.book, "bible")))
        self.assertEqual([], migrate.migrate_library(self.lib))

    def test_enabled_only_when_workbench_uses_v3_names(self):
        self.assertTrue(migrate.rename_enabled(), "工作台已經換成 v3 名稱")
        with mock.patch.object(migrate, "rename_enabled", lambda: False):
            self.assertEqual(["book_meta"], [s.key for s in migrate.pending(self.book)])
            self.assertEqual([], migrate.migrate_library(self.lib))


class PathTableTest(unittest.TestCase):
    def test_table_covers_every_layout_path(self):
        """layout 裡每一個 v2 路徑常數都要在對照表裡（漏了就會留在舊名稱）。"""
        skip = {"STUDIO", "BOOK_META", "PROJECT_RULES", "TEMPLATES_IN_SKILLS", "MIGRATE_DIR", "MIGRATE_BACKUP_PREFIX",
                "SPAWN_VOLUME_ONE", "VOLUME_PREFIX", "VOLUME_REVISION_PREFIX"}   # 範本檔名、卷綱檔名規則：之後的批次
        names = set(migrate.PATHS) | set(migrate.NAMES) | set(migrate.SHARED_PATHS)
        for k, v in layout.all_constants().items():
            if not isinstance(v, str) or k in skip or k.startswith("TPL_"):
                continue
            self.assertIn(k, names, "%s = %s 沒有在 migrate 的對照表裡" % (k, v))

    def test_v3_column_matches_current_layout(self):
        """對照表的 v3 欄要跟目前的 layout 一樣（v2 欄是凍結的舊值）。"""
        col = 1
        for table in (migrate.PATHS, migrate.NAMES, migrate.SHARED_PATHS):
            for k, v in table.items():
                cur = getattr(layout, k)
                if table is migrate.SHARED_PATHS and k != "SHARED":
                    cur = layout.SHARED + "/" + cur
                self.assertEqual(v[col], cur, k)


class WorkbenchGateTest(unittest.TestCase):
    """工作台遇到舊格式的書：書架標「需要轉換」、API 拒絕、轉換端點（v3 P3 第二批）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lib = os.path.join(self.tmp, "lib")
        os.makedirs(os.path.join(self.lib, "_共用", "文風"))
        with open(os.path.join(self.lib, "_共用", "文風", "x.md"), "w", encoding="utf-8") as f:
            f.write("# x\n")
        shutil.copytree(os.path.join(V2_DEMO, "退婚之後"), os.path.join(self.lib, "舊書"))
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), os.path.join(self.lib, "新書"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_detection_and_shelf(self):
        self.assertTrue(migrate.needs_migration(os.path.join(self.lib, "舊書")))
        self.assertFalse(migrate.needs_migration(os.path.join(self.lib, "新書")))
        self.assertTrue(migrate.library_needs_migration(self.lib))
        books = {b["id"]: b for b in project.list_books(self.lib)}
        self.assertTrue(books["舊書"].get("needs_migration"))
        self.assertNotIn("chapters_written", books["舊書"], "舊書不算統計")
        self.assertNotIn("needs_migration", books["新書"])
        self.assertEqual(2, books["新書"]["chapters_written"])

    def test_api(self):
        try:
            from fastapi.testclient import TestClient
        except (ImportError, RuntimeError):
            self.skipTest("TestClient 需要 httpx")
        import app as app_mod
        with mock.patch.dict(app_mod.CONFIG, {"library": self.lib}):
            c = TestClient(app_mod.app, base_url="http://127.0.0.1:8765")
            h = {"x-fe-token": app_mod.fe.token}
            r = c.get("/api/books")
            self.assertTrue(r.json()["shared_needs_migration"])
            r = c.get("/api/books/" + "舊書" + "/chapters")
            self.assertEqual(409, r.status_code)
            self.assertIn("舊格式", r.json()["error"])
            r = c.post("/api/books/舊書/migrate", json={"dry_run": True}, headers=h)
            self.assertEqual("dry_run", r.json()["status"])
            self.assertTrue(os.path.isdir(os.path.join(self.lib, "舊書", migrate.PATHS["BIBLE"][0])), "試跑不動檔案")
            r = c.post("/api/books/舊書/migrate", json={}, headers=h).json()
            self.assertEqual("done", r["status"], r)
            self.assertTrue(r["backup"].startswith(layout.MIGRATE_DIR + "/"), "回傳書內相對路徑")
            self.assertEqual(["_共用/ → _shared/（1 個檔）"], r["library"], "轉書時順便轉共用資料夾")
            self.assertEqual(200, c.get("/api/books/舊書/chapters").status_code)
            self.assertFalse(c.get("/api/books").json()["shared_needs_migration"])
