# -*- coding: utf-8 -*-
"""S4：pipeline 等任務結束的逾時（總時長與閒置兩種），卡住時要取消任務並讓那一步失敗。"""
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import pipeline


class FakeJob:
    """只實作 _wait 會用到的東西：events / status / id。"""

    def __init__(self):
        self.id = "j1"
        self.status = "running"
        self.events = [{"kind": "start"}]
        self.cost = None
        self.lock = threading.Lock()

    def finish(self):
        self.events.append({"kind": "end", "status": "done"})
        self.status = "done"


def make_pipeline(tmp):
    state = {"chapter": 1, "status": "running", "provider": "p1", "step_providers": {},
             "steps": [{"key": "write", "label": "寫章節", "status": "running", "note": "",
                        "job": None, "started": None, "ended": None}],
             "usage": {}, "done_chapters": []}
    hooks = {"launch": lambda action, params, pid: FakeJob(), "cancel": lambda jid: None}
    p = pipeline.Pipeline("b1", tmp, state, hooks)
    p.cur = "write"
    return p


class WaitTimeoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ns-wait-")

    def test_閒置太久會取消並失敗(self):
        p = make_pipeline(self.tmp)
        cancelled = []
        p.h["cancel"] = cancelled.append
        with mock.patch.object(pipeline, "WAIT_TOTAL", 3600), mock.patch.object(pipeline, "WAIT_IDLE", 0.3):
            with self.assertRaises(pipeline.StepFailed) as ctx:
                p._wait("write", {})
        self.assertIn("閒置", str(ctx.exception))
        self.assertEqual(cancelled, ["j1"])

    def test_總時長超過會取消並失敗(self):
        p = make_pipeline(self.tmp)
        cancelled = []
        p.h["cancel"] = cancelled.append
        with mock.patch.object(pipeline, "WAIT_TOTAL", 0.3), mock.patch.object(pipeline, "WAIT_IDLE", 3600):
            with self.assertRaises(pipeline.StepFailed) as ctx:
                p._wait("write", {})
        self.assertIn("總共等了", str(ctx.exception))
        self.assertEqual(cancelled, ["j1"])

    def test_正常結束不會誤殺(self):
        p = make_pipeline(self.tmp)
        cancelled = []
        p.h["cancel"] = cancelled.append

        def launch(action, params, pid):
            job = FakeJob()
            threading.Timer(0.2, job.finish).start()
            return job

        p.h["launch"] = launch
        with mock.patch.object(pipeline, "WAIT_TOTAL", 30), mock.patch.object(pipeline, "WAIT_IDLE", 30):
            job = p._wait("write", {})
        self.assertEqual(job.status, "done")
        self.assertEqual(cancelled, [])

    def test_有輸出就不算閒置(self):
        p = make_pipeline(self.tmp)

        def launch(action, params, pid):
            job = FakeJob()

            def pump():
                for i in range(6):
                    time.sleep(0.15)
                    job.events.append({"kind": "log", "text": str(i)})
                job.finish()

            threading.Thread(target=pump, daemon=True).start()
            return job

        p.h["launch"] = launch
        with mock.patch.object(pipeline, "WAIT_TOTAL", 30), mock.patch.object(pipeline, "WAIT_IDLE", 0.4):
            job = p._wait("write", {})
        self.assertEqual(job.status, "done")

    def test_按停止不會卡住(self):
        p = make_pipeline(self.tmp)

        def launch(action, params, pid):
            job = FakeJob()

            def stop():
                time.sleep(0.2)
                p.stop_flag = True
                job.status = "cancelled"

            threading.Thread(target=stop, daemon=True).start()
            return job

        p.h["launch"] = launch
        with mock.patch.object(pipeline, "WAIT_TOTAL", 30), mock.patch.object(pipeline, "WAIT_IDLE", 0.5):
            with self.assertRaises(pipeline.Stopped):
                p._wait("write", {})


if __name__ == "__main__":
    unittest.main()
