# -*- coding: utf-8 -*-
"""S4：任務與 View 的記憶體回收（執行中的永遠保留；已結束的只留最近 N 份）。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ns_jobs
from studio import runner


def make_view(job):
    """建一份 View 並先 sync（等同 view_of 在正式流程裡做的事）。"""
    view = ns_jobs.View(job)
    view.sync()
    return view


def make_job(book_dir, status="done", ended=1.0, title="t"):
    job = runner.Job("b1", book_dir, title, "prompt")
    job.status = status
    job.started = ended      # 讓排序可決定：真的跑起來時是 time.time()
    job.ended = ended
    if status != "running":
        job.emit("end", status=status)
    return job


class RunnerReclaimTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ns-reclaim-")
        self.r = runner.Runner(lambda: {})

    def test_只留最近N個已結束的(self):
        for i in range(35):
            j = make_job(self.tmp, ended=float(i))
            self.r.jobs[j.id] = j
        dropped = self.r.reclaim(30)
        self.assertEqual(len(dropped), 5)
        self.assertEqual(len(self.r.jobs), 30)
        for jid in dropped:                       # 被放掉的是最舊的 5 個
            self.assertNotIn(jid, self.r.jobs)

    def test_執行中的永遠保留(self):
        running = make_job(self.tmp, status="running", ended=None)
        self.r.jobs[running.id] = running
        for i in range(35):
            j = make_job(self.tmp, ended=float(i))
            self.r.jobs[j.id] = j
        self.r.reclaim(30)
        self.assertIn(running.id, self.r.jobs)
        self.assertEqual(len(self.r.jobs), 31)

    def test_沒超過就不動(self):
        for i in range(5):
            j = make_job(self.tmp, ended=float(i))
            self.r.jobs[j.id] = j
        self.assertEqual(self.r.reclaim(30), [])
        self.assertEqual(len(self.r.jobs), 5)

    def test_回收時通知外面(self):
        got = []
        r = runner.Runner(lambda: {}, on_forget=got.extend)
        for i in range(33):
            j = make_job(self.tmp, ended=float(i))
            r.jobs[j.id] = j
        dropped = r.reclaim(30)
        self.assertEqual(got, dropped)

    def test_任務結束一定會回收(self):
        r = runner.Runner(lambda: {})
        calls = []
        r._run_job = lambda job: calls.append("job")
        r.reclaim = lambda: calls.append("reclaim")
        r._run(object())
        self.assertEqual(calls, ["job", "reclaim"])

    def test_任務炸掉也會回收(self):
        r = runner.Runner(lambda: {})

        def boom(job):
            raise RuntimeError("炸了")

        calls = []
        r._run_job = boom
        r.reclaim = lambda: calls.append("reclaim")
        with self.assertRaises(RuntimeError):
            r._run(object())
        self.assertEqual(calls, ["reclaim"])


class ViewPruneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ns-view-")
        self._saved = dict(ns_jobs.VIEWS)
        ns_jobs.VIEWS.clear()

    def tearDown(self):
        ns_jobs.VIEWS.clear()
        ns_jobs.VIEWS.update(self._saved)

    def test_forget_放掉指定的View(self):
        j = make_job(self.tmp, ended=1.0)
        ns_jobs.VIEWS[j.id] = make_view(j)
        ns_jobs.forget([j.id])
        self.assertEqual(ns_jobs.VIEWS, {})

    def test_只留最近N份已結束的(self):
        jobs = []
        for i in range(35):
            j = make_job(self.tmp, ended=float(i))
            ns_jobs.VIEWS[j.id] = make_view(j)
            jobs.append(j)
        ns_jobs.prune_views(30)
        self.assertEqual(len(ns_jobs.VIEWS), 30)
        self.assertNotIn(jobs[0].id, ns_jobs.VIEWS)
        self.assertIn(jobs[-1].id, ns_jobs.VIEWS)

    def test_執行中的View不動(self):
        running = make_job(self.tmp, status="running", ended=None)
        ns_jobs.VIEWS[running.id] = make_view(running)
        for i in range(35):
            j = make_job(self.tmp, ended=float(i))
            ns_jobs.VIEWS[j.id] = make_view(j)
        ns_jobs.prune_views(30)
        self.assertIn(running.id, ns_jobs.VIEWS)
        self.assertEqual(len(ns_jobs.VIEWS), 31)


if __name__ == "__main__":
    unittest.main()
