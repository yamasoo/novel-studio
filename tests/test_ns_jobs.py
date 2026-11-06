# -*- coding: utf-8 -*-
"""ns_jobs.View 的最小測試（轉移計畫 §7.1.5）。只測轉換，不啟動 FastAPI。"""
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ns_jobs import COLLAPSE, View


class FakeJob:
    def __init__(self, events, status="running"):
        self.id = "j1"
        self.book_id = "b1"
        self.title = "測試"
        self.prompt = ""
        self.status = status
        self.events = list(events)
        self.started = 1.0
        self.ended = None
        self.result = ""
        self.cost = None
        self.meta = {"action": "write"}
        self.session_id = None
        self.provider = {"id": "p1", "name": "P"}
        self.lock = threading.Lock()


class ViewTest(unittest.TestCase):
    def test_stream_mapping_and_collapse(self):
        job = FakeJob([
            {"kind": "stream_start", "text": "草稿"},
            {"kind": "stream", "text": "第一段"},
            {"kind": "thinking", "text": "想"},
            {"kind": "stream", "text": "第二段"},
            {"kind": "stream_end"},
            {"kind": "tool", "name": "Read", "text": "讀取"},
            {"kind": "log", "text": "完成"},
        ])
        view = View(job)
        data = view.patch(0)
        self.assertEqual(data["status"], "running")          # 還沒 end
        self.assertEqual(data["stream"][0]["type"], "begin")
        self.assertTrue(data["stream"][1]["text"].startswith(COLLAPSE))
        self.assertEqual(data["stream"][2]["type"], "thinking")
        self.assertEqual(data["stream"][4]["type"], "end")
        self.assertEqual(data["stream"][5]["label"], "工具：Read")
        self.assertEqual(data["log"][0]["text"], "完成")

    def test_end_sets_status_and_ask(self):
        job = FakeJob([
            {"kind": "result", "text": "報告"},
            {"kind": "end", "status": "done"},
        ], status="done")
        view = View(job)
        data = view.patch(0)
        self.assertEqual(data["status"], "done")
        self.assertEqual(data["ask"]["id"], "reply")
        self.assertEqual(data["result"]["text"], "報告")

    def test_since_and_summary(self):
        job = FakeJob([{"kind": "log", "text": "a"}, {"kind": "log", "text": "b"}])
        view = View(job)
        first = view.patch(0)
        self.assertEqual([x["text"] for x in first["log"]], ["a", "b"])
        second = view.patch(first["seq"])
        self.assertEqual(second["log"], [])
        self.assertEqual(view.summary()["seq"], 0)           # resume 要從頭重播

    def test_text_not_collapsed(self):
        job = FakeJob([{"kind": "text", "text": "**全文**"}])
        view = View(job)
        data = view.patch(0)
        self.assertFalse(data["stream"][1]["text"].startswith(COLLAPSE))


if __name__ == "__main__":
    unittest.main()
