# -*- coding: utf-8 -*-
"""v3 結構改版的安全網：三本示範書「讀進來的樣子」要跟快照一樣。

涵蓋：唯讀 API（書架、總覽、章節、設定集、大綱、卷、追蹤、反推、合約、搜尋…）
以及寫章／回寫／審查／去 AI 味／聊天的上下文組裝結果。

- 快照檔：tests/snapshots/demo_snapshot.json
- 程式只搬位置、不改行為的重構（v3 計畫 P1、P2），跑完這份必須全綠。
- 真的要改行為時，用 UPDATE_SNAPSHOT=1 重產快照，並在 commit 說明為什麼變。

  UPDATE_SNAPSHOT=1 python -m pytest tests/test_demo_snapshot.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from fastapi.testclient import TestClient
except (ImportError, RuntimeError):   # 沒有 httpx 就整份跳過（和其他 API 測試一致）
    raise unittest.SkipTest("TestClient 需要 httpx／httpx2，這個環境沒有")

import app as app_mod
from studio import context, prompts

DEMO = os.path.join(ROOT, "demo")
SNAP = os.path.join(ROOT, "tests", "snapshots", "demo_snapshot.json")
UPDATE = os.environ.get("UPDATE_SNAPSHOT") == "1"

# 每本書要看的唯讀 API（相對於 /api/books/<id>）
BOOK_GETS = [
    "/overview", "/chapters", "/bible", "/outline", "/volumes", "/card-check", "/tracking",
    "/reverse", "/contract", "/structures", "/setup_report", "/drift", "/export",
    "/recoveries", "/pipeline", "/bible/index",
]
# 不分書的唯讀 API
GLOBAL_GETS = ["/api/books", "/api/actions", "/api/shared", "/api/import/info", "/api/reasoning"]
SEARCH_WORDS = {"zh-TW": "玉珮", "en": "lantern", "ja": "竜"}

# 會隨時間、機器變動的欄位：一律換成固定字
VOLATILE_KEYS = {"mtime", "mtime_ms", "mtimeMs", "updated", "updated_at", "created", "created_at",
                 "time", "ts", "token", "pid", "elapsed", "age", "modified"}


def _plugin_dir():
    return os.path.join(ROOT, "plugin")


class DemoSnapshotTest(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.lib = cls.tmp.name
        cls.books = sorted(n for n in os.listdir(DEMO) if os.path.isdir(os.path.join(DEMO, n)))
        # 書庫沒有 _共用 時 /api/shared 的回應也要固定
        for n in cls.books:
            shutil.copytree(os.path.join(DEMO, n), os.path.join(cls.lib, n))
        cls.patch = mock.patch.dict(app_mod.CONFIG, {"library": cls.lib})
        cls.patch.start()
        cls.client = TestClient(app_mod.app, base_url="http://127.0.0.1:8765")

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.patch.stop()
        cls.tmp.cleanup()

    # ---------- 正規化 ----------
    def _norm(self, v):
        if isinstance(v, dict):
            return {k: ("<volatile>" if k in VOLATILE_KEYS else self._norm(x)) for k, x in sorted(v.items())}
        if isinstance(v, list):
            return [self._norm(x) for x in v]
        if isinstance(v, str):
            s = v.replace(self.lib, "<LIB>").replace(self.lib.replace("\\", "/"), "<LIB>")
            s = s.replace(ROOT, "<ROOT>").replace(ROOT.replace("\\", "/"), "<ROOT>")
            s = re.sub(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?", "<datetime>", s)
            return s
        return v

    def _get(self, url):
        r = self.client.get(url)
        try:
            body = r.json()
        except ValueError:
            body = r.text
        return {"status": r.status_code, "body": self._norm(body)}

    # ---------- 收集 ----------
    def collect(self):
        out = {"books": self._get("/api/books"),
               "global": {g: self._get(g) for g in GLOBAL_GETS}}
        for b in self.books:
            base = "/api/books/" + quote(b)
            per = {}
            for g in BOOK_GETS:
                per[g] = self._get(base + g)
            ov = per["/overview"]["body"]
            lang = ov.get("lang", "zh-TW") if isinstance(ov, dict) else "zh-TW"
            per["/search"] = self._get(base + "/search?q=" + quote(SEARCH_WORDS.get(lang, "玉珮")))
            per["context"] = self._contexts(os.path.join(self.lib, b), lang)
            out[b] = per
        return out

    def _contexts(self, d, lang):
        prompts.set_lang(lang)            # skill_ref 等依「目前語言」挑 plugin-en／plugin-ja
        pd = _plugin_dir()
        res = {}
        calls = {
            "for_chapter_3": lambda: context.for_chapter(d, pd, 3, 60000),
            "for_writeback_2": lambda: context.for_writeback(d, 2, context.chapter_text(d, 2)[1] or "", 60000),
            "for_review_1_2": lambda: context.for_review(d, pd, 1, 2, 60000),
            "for_deslop": lambda: context.for_deslop(d, pd, 60000),
            "for_chat": lambda: context.for_chat(d, 60000),
        }
        for k, fn in calls.items():
            try:
                res[k] = self._norm(fn())
            except Exception as e:      # 記下例外型別，重構後例外也要一樣
                res[k] = "<error %s>" % type(e).__name__
        prompts.set_lang("zh-TW")
        return res

    # ---------- 測試 ----------
    def test_index_has_layout(self):
        """首頁內嵌 window.LAYOUT，值要跟 studio/layout.py 完全一樣（前端只從這裡拿路徑）。"""
        from studio import layout
        html = self.client.get("/").text
        m = re.search(r"window\.LAYOUT = Object\.freeze\((\{.*?\})\);", html)
        self.assertIsNotNone(m, "首頁沒有 window.LAYOUT")
        got = json.loads(m.group(1))
        want = {k: v for k, v in layout.all_constants().items() if isinstance(v, str)}
        self.assertEqual(want, got)
        self.assertLess(html.index("window.LAYOUT"), html.index('<script src="/static/'), "LAYOUT 要比 /static 腳本先載入")

    def test_demo_books_match_snapshot(self):
        got = json.loads(json.dumps(self.collect(), ensure_ascii=False, default=str))
        if UPDATE or not os.path.exists(SNAP):
            os.makedirs(os.path.dirname(SNAP), exist_ok=True)
            with open(SNAP, "w", encoding="utf-8", newline="\n") as f:
                json.dump(got, f, ensure_ascii=False, indent=1, sort_keys=True)
                f.write("\n")
            if not UPDATE:
                self.skipTest("第一次執行：已產生快照，請確認後提交")
            return
        with open(SNAP, encoding="utf-8") as f:
            want = json.load(f)
        self.assertEqual(sorted(want), sorted(got), "快照的項目不同（書的清單或 global）")
        for k in sorted(want):
            if k == "books":
                self.assertEqual(want[k], got[k], "書架 /api/books")
                continue
            if k == "global":
                for g in sorted(set(want[k]) | set(got[k])):
                    with self.subTest(api=g):
                        self.assertEqual(want[k].get(g), got[k].get(g))
                continue
            for part in sorted(set(want[k]) | set(got[k])):
                with self.subTest(book=k, part=part):
                    self.assertEqual(want[k].get(part), got[k].get(part))


if __name__ == "__main__":
    unittest.main()
