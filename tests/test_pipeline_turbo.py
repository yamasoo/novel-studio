# -*- coding: utf-8 -*-
"""超速文本模式（profile='turbo'）單元測試。"""
import os
import tempfile
import time
import unittest

from studio import layout, pipeline


class _FakeJob:
    def __init__(self, jid, status="done"):
        self.id = jid
        self.status = status
        self.events = [{"kind": "result", "usage": {"prompt_tokens": 10, "completion_tokens": 20}, "cost": 0.001},
                       {"kind": "end"}]


class TurboPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        for sub in (layout.CHAPTER_CARDS, layout.MANUSCRIPT, layout.CANDIDATES, layout.STUDIO_PIPELINE):
            os.makedirs(layout.path(self.d, sub), exist_ok=True)
        with open(os.path.join(self.d, "book.json"), "w", encoding="utf-8") as f:
            f.write('{"format_version": 3, "title": "測試書", "lang": "zh-TW"}\n')

    def tearDown(self):
        self.tmp.cleanup()

    def _mk_card(self, no):
        p = layout.path(self.d, layout.CHAPTER_CARDS, layout.chapter_stem(no) + ".md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"---\ntype: chapter-card\nchapter: {no}\ntitle: 第{no}章測試\n---\n\n## 情節\n- 測試\n")

    def _mk_text(self, no):
        p = layout.path(self.d, layout.MANUSCRIPT, layout.chapter_stem(no) + ".md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# 第{no}章\n\n已定稿正文。\n")

    def _mk_cand(self, no):
        p = layout.path(self.d, layout.CANDIDATES, layout.chapter_stem(no) + ".md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# 第{no}章\n\n已有候選稿。\n")

    def test_turbo_only_writes_eligible_cards_to_candidates(self):
        # ch 1: 已有正文（略過）
        # ch 2: 有章綱、未寫（應寫）
        # ch 3: 無章綱（略過）
        # ch 4: 有章綱但已有候選稿（略過）
        # ch 5: 有章綱、未寫（應寫）
        self._mk_card(1)
        self._mk_text(1)
        self._mk_card(2)
        self._mk_card(4)
        self._mk_cand(4)
        self._mk_card(5)

        called = []

        def launch(action, params, pid):
            called.append((action, params.get("from"), params.get("to")))
            no = params["from"]
            self._mk_cand(no)
            return _FakeJob(f"job-{no}")

        hooks = {"launch": launch, "cancel": lambda jid: None, "checker": None}
        p = pipeline.Pipeline.create("book1", self.d, hooks, 1, 5, "stop", None, "fake", profile="turbo")
        self.assertEqual(p.s["profile"], "turbo")
        self.assertEqual(p.s["chapters"], [2, 5])
        self.assertEqual([s["key"] for s in p.s["steps"]], ["write"])

        p.start()
        for _ in range(50):
            if p.s["status"] != "running":
                break
            time.sleep(0.05)

        self.assertEqual(p.s["status"], "done")
        self.assertEqual(p.s["done_chapters"], [2, 5])
        self.assertEqual(called, [("write", 2, 2), ("write", 5, 5)])
        # 正文目錄絕不能被動到（只有原本的 ch 1）
        self.assertEqual(os.listdir(layout.path(self.d, layout.MANUSCRIPT)), [layout.chapter_stem(1) + ".md"])

    def test_turbo_raises_when_no_eligible_chapters(self):
        self._mk_card(1)
        self._mk_text(1)
        hooks = {"launch": lambda *a: _FakeJob("x"), "cancel": lambda jid: None, "checker": None}
        with self.assertRaises(pipeline.PipelineError):
            pipeline.Pipeline.create("book1", self.d, hooks, 1, 3, "continue", None, "fake", profile="turbo")


if __name__ == "__main__":
    unittest.main()
