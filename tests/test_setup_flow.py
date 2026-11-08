# -*- coding: utf-8 -*-
"""開書前段的判定與面板提問（開書流程改版 §5.1／§5.2）。"""
import os
import threading
import time

import pytest

from studio import project, setup_flow
from studio.runner import Job, JobStopped


def _book(tmp_path):
    d = str(tmp_path)
    os.makedirs(os.path.join(d, "設定"), exist_ok=True)
    os.makedirs(os.path.join(d, "大綱", "章綱"), exist_ok=True)
    return d


def _write(d, rel, text):
    p = os.path.join(d, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


CLAUDE_MD = """# 《測試書》寫作專案

一個維修工想活著下樓，卻被困在一座壞掉的太空電梯裡。

## 基本設定
- 題材：科幻　平台：網路連載　預計篇幅：中篇
- 視角：第三人稱跟著主角
- 每章字數：2500～3500 字
- 語言：台灣繁體中文。

## 資料在哪裡
- 設定（靜態）：設定／計畫（未發生）：大綱／事實（已發生）：追蹤
"""

CORE = """---
類型: 故事核心
語言: zh-TW
---

## 一句話

一個維修工想活著下樓。他被壞掉的電梯擋住，只能一層一層換配重，換到最後才發現電梯是被人鎖住的，鎖住他的人是他自己的工會。

## 主角

電梯維修工，手上有整座結構的維修權限，卻欠了工會一筆說不清的帳。

## 他想要什麼

活著到地面，把兒子接回來。

## 被什麼擋住

電梯只剩手動下降，每降一層就少一段配重；而那個逃犯身上帶著一張不該在他身上的通行證。

## 預設

這段是作者按「跳過，你決定」之後由模型決定的，等作者看過再定稿。
"""


def test_steps_and_next_follow_files(tmp_path):
    d = _book(tmp_path)
    assert [s["done"] for s in setup_flow.steps(d)] == [False] * 5
    assert setup_flow.next_step(d)["id"] == "setup"

    _write(d, "CLAUDE.md", CLAUDE_MD)
    assert setup_flow.next_step(d)["id"] == "concept"

    _write(d, "設定/故事核心.md", CORE)
    assert setup_flow.next_step(d)["id"] == "master"

    # 不到 500 字不算完成
    _write(d, "大綱/全書大綱.md", "短大綱")
    assert setup_flow.next_step(d)["id"] == "master"

    _write(d, "大綱/全書大綱.md", "---\n類型: 全書大綱\n---\n" + ("卷" * 600))
    assert setup_flow.next_step(d)["id"] == "volume"

    _write(d, "大綱/卷綱_第1卷.md", "---\n狀態: 已確認\n---\n" + ("章" * 200))
    assert setup_flow.next_step(d)["id"] == "cards"

    for n in range(1, 11):
        _write(d, "大綱/章綱/第%03d章.md" % n, "---\n狀態: 已確認\n---\n章綱")
    nxt = setup_flow.next_step(d)
    assert nxt["id"] == "write" and nxt["action"] == "write" and nxt["prefill"] == {"from": 1, "to": 1}


def test_unfilled_template_comments_are_not_done(tmp_path):
    d = _book(tmp_path)
    _write(d, "CLAUDE.md", "# 書\n")
    _write(d, "設定/故事核心.md", "---\n類型: 故事核心\n---\n<!-- 還沒填 -->\n" + ("字" * 400))
    assert setup_flow.steps(d)[1]["done"] is False


def test_report_marks_created_pending_and_defaults(tmp_path):
    d = _book(tmp_path)
    _write(d, "CLAUDE.md", CLAUDE_MD)
    _write(d, "設定/故事核心.md", CORE)
    meta = {"params": {"answers": {"genre": {"q": "題材？", "a": "", "default": True},
                                   "pov": {"q": "視角？", "a": "B. 第三人稱", "default": False}}}}
    rep = setup_flow.report(d, meta)
    assert "CLAUDE.md" in rep["created"] and "設定/故事核心.md" in rep["created"]
    assert rep["pending"] == ["文風"]
    assert [x["key"] for x in rep["defaults"]] == ["genre"]
    assert rep["next"]["id"] == "master"
    text = setup_flow.report_md(d, meta)
    assert "已建立" in text and "（預設）" in text


def test_interview_state_three_ways(tmp_path):
    d = _book(tmp_path)
    assert setup_flow.interview_state(d)["state"] == "none"

    _write(d, ".studio/jobs/20260101-000000-aaaaaa.json", '{"meta": {"action": "setup_new"}}')
    assert setup_flow.interview_state(d)["state"] == "interrupted"

    _write(d, "CLAUDE.md", "# 書\n")
    assert setup_flow.interview_state(d)["state"] == "none"


def _job(tmp_path):
    return Job("測試書", str(tmp_path), "開書訪談", "p", meta={"action": "setup_new", "params": {}})


def test_ask_is_delivered_into_the_running_job(tmp_path):
    job = _job(tmp_path)
    got = {}

    def worker():
        got["answer"] = job.ask("第 1/4 題：題材？", options=["A. 科幻", "跳過，你決定"])

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    for _ in range(50):
        time.sleep(0.05)
        pending = job.pending_ask()
        if pending:
            break
    assert pending and pending["allow_text"] is True
    assert [o["label"] for o in pending["options"]] == ["A. 科幻", "跳過，你決定"]

    assert job.deliver_reply("a999", "x") is None      # 不存在的提問
    assert job.deliver_reply(pending["id"], "A. 科幻") == "ok"
    th.join(5)
    assert got["answer"] == "A. 科幻"
    assert job.pending_ask() is None
    assert job.deliver_reply(pending["id"], "再送一次") is None   # 已回答過


def test_ask_stops_with_the_job(tmp_path):
    job = _job(tmp_path)

    def worker():
        with pytest.raises(JobStopped):
            job.ask("等一個永遠不會來的回覆")

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    for _ in range(50):
        time.sleep(0.05)
        if job.pending_ask():
            break
    job.status = "cancelled"
    th.join(5)
    assert not th.is_alive()


def test_running_job_has_no_fake_reply_ask(tmp_path):
    """執行中但有真提問時，View.ask 回的是真提問；沒有提問時回 None（不會冒出假的回覆框）。"""
    import ns_jobs
    job = _job(tmp_path)
    view = ns_jobs.View(job, saved=False)
    assert view.ask() is None            # 還在跑、沒有提問

    def worker():
        job.ask("題材？")

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    for _ in range(50):
        time.sleep(0.05)
        if job.pending_ask():
            break
    ask = view.ask()
    assert ask and ask["prompt"] == "題材？"
    job.deliver_reply(ask["id"], "A")
    th.join(5)
