# -*- coding: utf-8 -*-
"""book.json 與格式移轉工具（v3 P3 第一批）。"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import bookmeta, layout, migrate, project, sections, trackjson  # noqa: E402
from studio import lang as lang_mod  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "tools"))
import migrate_v3  # noqa: E402

DEMOS = ("退婚之後", "en_TheLanternRoad", "ja_辺境の薬師と竜の約束")
V2_DEMO = os.path.join(ROOT, "tests", "fixtures", "v2_demo")      # v2 格式的示範書（P3 第二批轉換前的樣子），測移轉用


def _fm(rel, data, lang="zh-TW"):
    """轉換後 .md 的 frontmatter 鍵會換成英文、英日文書的段落標題換成書的語言，其他內容不變。"""
    if not rel.endswith(".md") or rel.startswith((layout.STUDIO_BACKUP + "/", ".studio/jobs/")):
        return data
    text = migrate.fm_rewrite(data.decode("utf-8"))
    if lang in ("en", "ja") and text.startswith("---"):
        text = sections.localize_doc(text, lang)
    return text.encode("utf-8")


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
        self.assertNotIn("en", project.read_text(layout.path(d, layout.STORY_CORE)), "故事核心不再同步語言（技能改看 book.json）")
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
        self.assertEqual(["book_meta", "rename", "chapters", "volumes", "templates", "docs", "fmkeys", "sections", "tables",
                          "datakeys"],
                         [s["key"] for s in r["steps"]])
        self.assertEqual(["資料夾改名後一併處理"], r["steps"][-1]["changes"], "改名後才做的步驟也先列出來")
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
            rewritten = {"CLAUDE.md", layout.GLOSSARY, layout.BIBLE_INDEX, layout.BOOK_OUTLINE}    # 內容裡有路徑的系統檔（＋_templates 底下的範本）
            moved = {migrate.map_v3(k): v for k, v in before.items() if k != ".studio/lang"}
            jsons = {trackjson.json_rel(k) for k in moved if k in trackjson.CANON}
            self.assertEqual(set(moved) | {"book.json"} | jsons, set(after), "只多 book.json 與追蹤表的 JSON，其他都是搬到新位置")
            for j in jsons:
                self.assertEqual(trackjson.state(b, j[:-5] + ".md")[0], "same", j)
            for k, v in moved.items():
                if k not in rewritten and not k.startswith(layout.TEMPLATES + "/"):
                    want = _fm(k, v, lang)
                    if k == layout.STORY_CORE:          # 語言只記在 book.json：故事核心拿掉 lang 那一行
                        want = re.sub(rb"(?m)^lang: .*\n", b"", want)
                    self.assertEqual(want, after[k], k)
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
        w("設定/續寫合約.md", "# 續寫合約\n\n## 5. 禁區\n\n- 作者的硬性偏好（`設定/作者偏好.md`）優先。\n")
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
        rewritten = {"CLAUDE.md", "bible/glossary.md", "bible/continuation-contract.md", ".studio/revisions/ch-0001.json", ".studio/pipeline/current.json",
                     ".studio/reverse/drafts/bible/glossary.md", "illust/_illustrations.json"}
        for rel, data in self.before.items():
            new = migrate.map_v3(rel)
            if rel == ".studio/lang":
                continue
            self.assertIn(new, after, rel)
            if new not in rewritten and not new.startswith(layout.TEMPLATES + "/"):
                self.assertEqual(_fm(new, data), after[new], "內容不能變（frontmatter 的鍵換成英文除外）：%s" % rel)
        for top in migrate.TOP_V2:
            self.assertFalse(os.path.exists(os.path.join(self.book, top)), top)
        self.assertTrue(os.path.isdir(os.path.join(self.book, "export")), "空資料夾也要換名稱")
        self.assertEqual(r["stats"], migrate.stats(self.book))
        rd = lambda rel: after[rel].decode("utf-8")
        rec = json.loads(rd(".studio/revisions/ch-0001.json"))
        self.assertEqual("manuscript/ch-0001.md", rec["path"], "紀錄裡的路徑跟著檔名改")
        self.assertEqual("candidates/第003章_x.md", rec["base_path"], "不存在的檔不改（只換資料夾名稱）")
        self.assertEqual("設定/那個不是路徑", rec["note"], "不是路徑的字串不動")
        self.assertIn("詳見 bible/world/兵器.md；見 tracking/timeline.md", rd("bible/glossary.md"))
        self.assertIn("詳見 bible/world/兵器.md", rd(".studio/reverse/drafts/bible/glossary.md"))
        self.assertIn("`bible/characters/`，正文在 manuscript/。", rd("CLAUDE.md"))
        self.assertIn("`bible/author-prefs.md`", rd("bible/continuation-contract.md"), "續寫合約保留段的路徑也要換")
        self.assertIn("bible/characters/林晚.md", rd("illust/_illustrations.json"))
        self.assertIn("illust/林晚/1.png", rd("illust/_illustrations.json"))
        self.assertIn("設定/世界觀/兵器.md", rd("manuscript/ch-0003.md"), "正文一個字都不能改")
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
        skip = {"STUDIO", "BOOK_META", "PROJECT_RULES", "TEMPLATES_IN_SKILLS", "MIGRATE_DIR", "MIGRATE_BACKUP_PREFIX", "CHAPTER_STEM",
                "OUTLINE_VOLUME_ONE", "VOLUME_REVISION_SUFFIX", "VOLUME_UPDATE_PREFIX", "VOLUME_STEM", "ACT_STEM",
                "VISUAL_CARDS"}   # 範本檔名（第七批）、卷綱檔名規則（卷綱步驟）、v3 新增目錄
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


class ChapterStepTest(unittest.TestCase):
    """第三步：逐章檔名換成 ch-0001（v3 P3 第三批）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.book = os.path.join(self.tmp, "b")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), self.book)    # 已是 v3 資料夾

        def w(rel, text):
            p = os.path.join(self.book, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        self.w = w
        for f in os.listdir(layout.path(self.book, layout.MANUSCRIPT)):
            os.remove(layout.path(self.book, layout.MANUSCRIPT, f))
        w("manuscript/第001章_退婚當天.md", "# 第1章 退婚當天\n\n正文一。\n")
        w("manuscript/第002章_浮字.md", "正文二，沒有標題。\n")                       # 章名只在檔名裡
        w("candidates/第003章_甲稿.md", "# 第3章 甲稿\n\n甲\n")
        os.remove(layout.path(self.book, layout.CANDIDATES, "ch-0003.md"))
        w("candidates/第003章_乙稿.md", "# 第3章 乙稿\n\n乙\n")                      # 同一章兩份
        w(".studio/revisions/第001章.json", json.dumps({"path": "manuscript/第001章_退婚當天.md"}, ensure_ascii=False))
        w(".studio/revisions/第001章.draft.md", "草稿\n")
        w(".studio/reverse/batches/第001-002章.json", "{}")
        w(".studio/pipeline/snapshots/第001章/write.json", "{}")
        w(".studio/backup/修改前_第001章_退婚當天.1700000000.md", "舊\n")              # 備份不改名
        w("illust/chapters/第001章/a.png", "x")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_needs_migration_on_old_chapter_names(self):
        self.assertTrue(migrate.needs_migration(self.book), "v3 資料夾但還有舊章節檔名：要轉換")

    def test_migrate(self):
        before = migrate.stats(self.book)
        r = migrate.migrate(self.book)
        self.assertEqual("done", r["status"], r.get("message"))
        self.assertEqual(["chapters"], [s["key"] for s in r["steps"]])
        self.assertEqual(before, migrate.stats(self.book))
        L = sorted(os.listdir(layout.path(self.book, layout.MANUSCRIPT)))
        self.assertEqual(["ch-0001.md", "ch-0002.md"], L)
        self.assertEqual(["ch-0003.md", "ch-0003.v2.md"], sorted(os.listdir(layout.path(self.book, layout.CANDIDATES))))
        t2 = project.read_text(layout.path(self.book, layout.MANUSCRIPT, "ch-0002.md"))
        self.assertTrue(t2.startswith("# 第2章 浮字\n\n正文二"), "章名只在檔名裡：補一行標題")
        self.assertEqual("浮字", project.scan_chapters(self.book)[1]["title"] or "")
        self.assertEqual("# 第1章 退婚當天\n\n正文一。\n", project.read_text(layout.path(self.book, layout.MANUSCRIPT, "ch-0001.md")))
        rec = json.loads(project.read_text(layout.path(self.book, layout.STUDIO_REVISIONS, "ch-0001.json")))
        self.assertEqual("manuscript/ch-0001.md", rec["path"])
        for rel in (".studio/revisions/ch-0001.draft.md", ".studio/reverse/batches/ch-0001-0002.json",
                    ".studio/pipeline/snapshots/ch-0001/write.json", "illust/chapters/ch-0001/a.png",
                    ".studio/backup/修改前_第001章_退婚當天.1700000000.md"):
            self.assertTrue(os.path.isfile(os.path.join(self.book, *rel.split("/"))), rel)
        self.assertIn("補上標題", "".join(r["steps"][0]["changes"]))
        self.assertFalse(migrate.needs_migration(self.book))
        self.assertEqual("skipped", migrate.migrate(self.book)["status"])

    def test_workbench_reads_legacy_names(self):
        """技能或手動寫成舊檔名的檔，工作台照樣認得（章號、章名）。"""
        rows = {r["no"]: r for r in project.scan_chapters(self.book)}
        self.assertEqual("浮字", rows[2]["title"])
        self.assertEqual("manuscript/第002章_浮字.md", rows[2]["text_file"])


class DocsStepTest(unittest.TestCase):
    """第四步：系統文件（CLAUDE.md、_templates、名詞表、設定索引）裡的舊路徑。"""

    def test_rewrite_and_detect(self):
        tmp = tempfile.mkdtemp()
        try:
            b = os.path.join(tmp, "b")
            shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), b)
            self.assertFalse(migrate.needs_migration(b))
            p = os.path.join(b, "CLAUDE.md")
            text = project.read_text(p)
            with open(p, "a", encoding="utf-8", newline="\n") as f:
                f.write("\n- 正文：`正文/第NNN章_<title>.md`，章綱：outline/chapters/第NNN章.md。她說設定/那個不是路徑。\n")
            self.assertTrue(migrate.needs_migration(b), "系統文件還有舊路徑：要轉換")
            r = migrate.migrate(b)
            self.assertEqual(["docs"], [s["key"] for s in r["steps"]])
            new = project.read_text(p)
            self.assertTrue(new.startswith(text))
            self.assertIn("`manuscript/ch-NNNN.md`，章綱：outline/chapters/ch-NNNN.md。她說設定/那個不是路徑。", new)
            self.assertFalse(migrate.needs_migration(b))
        finally:
            shutil.rmtree(tmp)


class LegacyChapterNamesTest(unittest.TestCase):
    """v3 的書裡出現舊檔名（技能或手動寫的）：工作台照樣能用，寫出一律 ch-0001。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.book = os.path.join(self.tmp, "b")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), self.book)
        cand = layout.path(self.book, layout.CANDIDATES)
        for f in os.listdir(cand):
            os.remove(os.path.join(cand, f))
        with open(os.path.join(cand, "第003章_鋪子裡的帳.md"), "w", encoding="utf-8") as f:
            f.write("鋪子裡的帳。\n")          # 沒有標題：章名只在舊檔名裡

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_scan_and_accept(self):
        row = {r["no"]: r for r in project.scan_chapters(self.book)}[3]
        self.assertEqual("candidates/第003章_鋪子裡的帳.md", row["candidate_file"])
        rel = project.accept_candidate(self.book, 3)
        self.assertEqual(layout.MANUSCRIPT + "/ch-0003.md", rel, "採用後一律存成 ch-0003.md")

    def test_canonical_name_wins(self):
        man = layout.path(self.book, layout.MANUSCRIPT)
        for name in ("ch-0001.v2.md", "第001章_舊.md"):
            with open(os.path.join(man, name), "w", encoding="utf-8") as f:
                f.write("# 第1章 另一份\n")
        self.assertEqual("ch-0001.md", project._scan_dir(man)[1])


class VolumeStepTest(unittest.TestCase):
    """卷綱檔名換成 vol-01，正式卷綱一律放 outline/volumes/（v3 P3 第三批後半）。"""

    VOL = "---\n類型: 卷綱\n卷名: %s\n章節範圍: 第%d章～第%d章\n狀態: 已確認\n---\n\n# 卷綱：%s\n"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.book = os.path.join(self.tmp, "b")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), self.book)    # 已是 v3 資料夾、vol-01

        def w(rel, text):
            p = os.path.join(self.book, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        self.w = w
        shutil.rmtree(layout.path(self.book, layout.VOLUMES_SUBDIR))
        w("outline/卷綱_第一卷.md", self.VOL % ("舊帳", 1, 30, "舊帳"))
        w("outline/卷綱_第2卷.md", self.VOL % ("新帳", 31, 60, "新帳"))
        w("outline/卷綱_第三幕.md", self.VOL % ("幕", 61, 70, "幕"))
        w("outline/卷綱.md", self.VOL % ("沒卷號", 71, 80, "沒卷號"))                 # 認不出卷號：照原名搬
        w("outline/volumes/卷綱_第一卷.md", self.VOL % ("spawn 建的", 1, 10, "x"))    # 撞名 → vol-01.v2.md
        w("outline/drafts/卷綱_第3卷.md", self.VOL % ("新卷草稿", 61, 90, "新卷"))
        w("outline/drafts/卷綱修訂_第2卷.md", self.VOL % ("修訂", 31, 60, "修訂"))
        w("outline/drafts/卷綱更新_第1-30章.md", "# 卷綱更新草稿（第1–30 章體檢）\n")
        w(".studio/reverse/drafts/outline/卷綱_第1卷.md", "反推\n")
        w(".studio/pipeline/current.json", json.dumps({"volume": "outline/卷綱_第2卷.md", "dir": "outline"}, ensure_ascii=False))
        w(".studio/backup/卷綱_第1卷.1700000000.md", "舊\n")                         # 備份不改名
        book = project.read_text(layout.path(self.book, layout.BOOK_OUTLINE))
        w(layout.BOOK_OUTLINE, book + "\n- 卷綱：`outline/卷綱_第1卷.md`（已確認）\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_needs_migration_on_old_volume_names(self):
        self.assertTrue(migrate.needs_migration(self.book))

    def test_map(self):
        for old, new in (("大綱/卷綱_第1卷.md", "outline/volumes/vol-01.md"), ("大綱/卷一卷綱.md", "outline/volumes/vol-01.md"),
                         ("大綱/卷綱/卷綱_第一卷.md", "outline/volumes/vol-01.md"), ("outline/卷綱_第十二卷.md", "outline/volumes/vol-12.md"),
                         ("大綱/草稿/卷綱更新_第1-60章.md", "outline/drafts/volume-update_ch-0001-0060.md"),
                         ("outline/drafts/卷綱草稿.md", "outline/drafts/卷綱草稿.md"), ("outline/book.md", "outline/book.md")):
            self.assertEqual(new, migrate.map_v3(old), old)

    def test_migrate(self):
        from studio import volume
        before = migrate.stats(self.book)
        self.assertEqual(5, before["卷綱"])
        r = migrate.migrate(self.book)
        self.assertEqual("done", r["status"], r.get("message"))
        self.assertEqual(["volumes", "docs", "fmkeys"], [s["key"] for s in r["steps"]])
        self.assertEqual(before, migrate.stats(self.book))
        self.assertEqual(["act-03.md", "vol-01.md", "vol-01.v2.md", "vol-02.md", "卷綱.md"],
                         sorted(os.listdir(layout.path(self.book, layout.VOLUMES_SUBDIR))))
        self.assertEqual(["vol-02.revision.md", "vol-03.md", "volume-update_ch-0001-0030.md"],
                         sorted(os.listdir(layout.path(self.book, layout.VOLUME_DRAFTS))))
        self.assertTrue(os.path.isfile(os.path.join(self.book, ".studio", "reverse", "drafts", "outline", "volumes", "vol-01.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.book, ".studio", "backup", "卷綱_第1卷.1700000000.md")))
        with open(os.path.join(self.book, ".studio", "pipeline", "current.json"), encoding="utf-8") as f:
            self.assertEqual({"volume": "outline/volumes/vol-02.md", "dir": "outline"}, json.load(f), "只換檔案路徑，不換資料夾")
        self.assertIn("`outline/volumes/vol-01.md`", project.read_text(layout.path(self.book, layout.BOOK_OUTLINE)))
        # 工作台讀得到：卷號、範圍、幕、草稿、修訂、更新草稿
        vols = {v["rel"]: (v["no"], v["lo"], v["hi"], v["kind"]) for v in volume.list_volumes(self.book)}
        self.assertEqual((1, 1, 30, "卷"), vols["outline/volumes/vol-01.md"])
        self.assertEqual((3, 61, 70, "幕"), vols["outline/volumes/act-03.md"])
        self.assertEqual((None, 71, 80, "卷"), vols["outline/volumes/卷綱.md"])
        self.assertEqual(31, volume.find(self.book, 45)["lo"])
        self.assertEqual([3], [d["no"] for d in volume.drafts(self.book)])
        self.assertEqual([2], [d["no"] for d in volume.revisions(self.book)])
        self.assertEqual([(1, 30)], [(p["lo"], p["hi"]) for p in volume.plan_drafts(self.book)])
        self.assertFalse(migrate.needs_migration(self.book))
        self.assertEqual("skipped", migrate.migrate(self.book)["status"])

    def test_dry_run_from_v2(self):
        """v2 的書試跑：資料夾還沒改名就看得出卷綱要改。"""
        b = os.path.join(self.tmp, "v2")
        shutil.copytree(os.path.join(V2_DEMO, "ja_辺境の薬師と竜の約束"), b)
        r = migrate.migrate(b, dry_run=True)
        vol = next(s for s in r["steps"] if s["key"] == "volumes")
        self.assertEqual(["outline/卷綱_第一卷.md → outline/volumes/vol-01.md"], vol["changes"])
        self.assertEqual("done", migrate.migrate(b)["status"])
        self.assertTrue(os.path.isfile(os.path.join(b, "outline", "volumes", "vol-01.md")))


class VolumeFilesTest(unittest.TestCase):
    """工作台寫出的卷綱檔名（開新卷、採用、修訂、卷末體檢）。"""

    def test_names(self):
        self.assertEqual("outline/volumes/vol-01.md", layout.volume_file(1))
        self.assertEqual("outline/drafts/vol-12.md", layout.volume_file(12, base=layout.VOLUME_DRAFTS))
        self.assertEqual("outline/drafts/vol-02.revision.md", layout.volume_revision_file(2))
        self.assertEqual("outline/drafts/volume-update_ch-0001-0060.md", layout.volume_update_draft(1, 60))
        from studio import volume
        for raw, no in (("3", 3), ("三", 3), ("第十二卷", 12), ("vol-04", 4), ("", None)):
            self.assertEqual(no, volume.no_of(raw), raw)


class FmNumberTest(unittest.TestCase):
    """章號、章節範圍、所屬卷換成數字（v3 P3 第四批之三）。"""

    def test_numbers(self):
        t = ("---\ntype: chapter-card\nvolume: 第一卷\nupdated_through: 第012章\nfirst_appearance: 1\n"
             "last_appearance: 第3章前後\nchapter_range: 第001章～第030章\n---\n\n第001章～第002章 正文不動\n")
        out = migrate.fm_rewrite(t)
        self.assertIn("volume: 1\n", out)
        self.assertIn("updated_through: 12\n", out)
        self.assertIn("first_appearance: 1\n", out)
        self.assertIn("last_appearance: 第3章前後\n", out)             # 讀不出單一章號：原樣
        self.assertIn("chapter_range: [1, 30]\n", out)
        self.assertIn("第001章～第002章 正文不動", out)
        self.assertEqual(out, migrate.fm_rewrite(out))                   # 再跑一次不變

    def test_comment_example(self):
        out = migrate.fm_rewrite("---\nchapter_range:       # 例：第001章～第060章\n---\n")
        self.assertIn("# 例：[1, 60]", out)


class FmKeysStepTest(unittest.TestCase):
    """frontmatter 的鍵換成英文（v3 P3 第四批之二）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.book = os.path.join(self.tmp, "b")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), self.book)    # 已是英文鍵

        def w(rel, text):
            p = os.path.join(self.book, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        self.w = w
        w("bible/story-core.md", "---\n類型: 故事核心\n書名: 退婚之後\n狀態：草稿\n語言: zh-TW\n---\n\n# 故事核心\n\n狀態: 這行是正文\n")
        w("bible/characters/甲.md", "---\n類型: 角色\n名稱: 甲\n別名:\n  - 小甲\n定位: 主角\n自訂欄: 留著\n---\n\n# 甲\n")
        w("outline/chapters/ch-0001.md", "---\n類型: 章綱\n章號: 1\n章名: 退婚當天\nstatus: 已確認\n狀態: 草稿\n---\n\n# 第1章\n")
        w(".studio/backup/故事核心.1.md", "---\n類型: 故事核心\n---\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_quick_probe(self):
        self.assertTrue(migrate.needs_migration(self.book), "故事核心還是中文鍵：書架要提示轉換")

    def test_migrate(self):
        before = migrate.stats(self.book)
        r = migrate.migrate(self.book)
        self.assertEqual("done", r["status"], r.get("message"))
        self.assertEqual(["fmkeys", "datakeys"], [s["key"] for s in r["steps"]])
        self.assertEqual(before, migrate.stats(self.book))
        read = lambda rel: project.read_text(os.path.join(self.book, *rel.split("/")))
        self.assertEqual("---\ntype: story-core\ntitle: 退婚之後\nstatus: draft\n---\n\n# 故事核心\n\n狀態: 這行是正文\n",
                         read("bible/story-core.md"), "全形冒號補空格；固定詞換成英文 ID；正文不動；語言只記在 book.json")
        self.assertEqual("---\ntype: character\nname: 甲\naliases:\n  - 小甲\nrole: protagonist\n自訂欄: 留著\n---\n\n# 甲\n", read("bible/characters/甲.md"))
        self.assertIn("status: approved\n狀態: 草稿\n", read("outline/chapters/ch-0001.md"), "已經有英文鍵的那一欄不重複（重複的中文行原樣）")
        self.assertEqual("---\n類型: 故事核心\n---\n", read(".studio/backup/故事核心.1.md"), "備份不動")
        fm, _ = project.split_frontmatter(read("bible/characters/甲.md"))
        self.assertEqual(["小甲"], fm["aliases"])
        self.assertFalse(migrate.needs_migration(self.book))
        self.assertEqual("skipped", migrate.migrate(self.book)["status"])

    def test_values(self):
        text = "---\ntype: 角色\nrole: 主角          # 主角 / 配角\nstatus: \"已確認\"\ncategory: 自創類\nname: 主角\n---\n\nrole: 主角\n"
        self.assertEqual("---\ntype: character\nrole: protagonist          # protagonist / supporting\nstatus: \"approved\"\n"
                         "category: 自創類\nname: 主角\n---\n\nrole: 主角\n", migrate.fm_rewrite(text),
                         "固定詞與註解裡的選項換成 ID；作者自己的值、名稱、正文不動")

    def test_fenced_examples(self):
        text = "說明\n\n```yaml\n---\n類型: 角色\n名稱: 林晚   # 註解\n---\n```\n\n類型: 正文\n"
        self.assertEqual("說明\n\n```yaml\n---\ntype: character\nname: 林晚   # 註解\n---\n```\n\n類型: 正文\n",
                         migrate.fm_rewrite(text, fenced=True))
        self.assertEqual(text, migrate.fm_rewrite(text), "預設只換開頭的 frontmatter")


class TemplateStepTest(unittest.TestCase):
    """第七批：範本檔名換成英文、book.json 的格式版本 3。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.book = os.path.join(self.tmp, "b")
        shutil.copytree(os.path.join(ROOT, "demo", "退婚之後"), self.book)
        self.tpl = layout.path(self.book, layout.TEMPLATES)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_rename_and_collision(self):
        os.rename(os.path.join(self.tpl, "character.md"), os.path.join(self.tpl, "角色.md"))
        with open(os.path.join(self.tpl, "文風.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("作者改過的舊範本\n")                                # 新舊都在：舊的收進 _old/
        with open(os.path.join(self.book, "CLAUDE.md"), "a", encoding="utf-8", newline="\n") as f:
            f.write("\n- 路徑格式見 `_templates/專案規範.md`，角色用 `_templates/角色.md`。\n")
        self.assertTrue(migrate.needs_migration(self.book))
        r = migrate.migrate(self.book)
        self.assertEqual("done", r["status"], r.get("message"))
        self.assertEqual(["templates", "docs"], [s["key"] for s in r["steps"]])
        self.assertTrue(os.path.isfile(os.path.join(self.tpl, "character.md")))
        self.assertFalse(os.path.exists(os.path.join(self.tpl, "角色.md")))
        self.assertEqual("作者改過的舊範本\n", project.read_text(os.path.join(self.tpl, "_old", "文風.md")))
        claude = project.read_text(os.path.join(self.book, "CLAUDE.md"))
        self.assertIn("`_templates/project-rules.md`", claude)
        self.assertIn("`_templates/character.md`", claude)
        self.assertFalse(migrate.needs_migration(self.book))

    def test_schema_version(self):
        self.assertEqual(3, layout.SCHEMA_VERSION)
        bookmeta.write(self.book, schema_version=2)
        self.assertTrue(migrate.needs_migration(self.book))
        r = migrate.migrate(self.book)
        self.assertEqual(["book_meta"], [s["key"] for s in r["steps"]])
        self.assertIn("格式版本 2 → 3", r["steps"][0]["changes"])
        self.assertEqual(3, bookmeta.read(self.book)["schema_version"])

    def test_no_book_json_is_not_old(self):
        os.remove(layout.path(self.book, layout.BOOK_META))          # 例如技能建的書還沒有 book.json
        self.assertFalse(migrate.needs_migration(self.book))

    def test_presets_by_display_name(self):
        from studio import shared
        names = [s["name"] for s in shared.list_structures(self.tmp) if s["origin"] == "preset"]
        self.assertEqual(sorted(["三幕式", "起承轉合", "懸疑揭露", "壓抑爆發", "日常感情"]), names)
        self.assertTrue(shared.structure_path(self.tmp, "三幕式", "preset").endswith("three-act.md"))
        self.assertTrue(shared.structure_path(self.tmp, "three-act", "preset").endswith("three-act.md"))
        rel = shared.apply_structure(self.tmp, "三幕式", "preset", self.book)
        self.assertTrue(rel.endswith("三幕式.md"))
