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

# ---------------------------------------------------------------------------
# 寫檔前的閘門（大綱／卷綱／章綱／故事核心：按確認才落地）
# ---------------------------------------------------------------------------
from studio import native_files, prompts  # noqa: E402

FILE_BLOCK = "<<<檔案 大綱/全書大綱.md>>>\n---\n類型: 全書大綱\n---\n" + ("卷" * 600) + "\n<<<結束>>>"


class _Pack:
    def add(self, *a, **k):
        pass

    def build(self):
        return "ctx", 0, []


def _spec(c, p):
    return "測試動作", "任務說明", _Pack(), True


class _Job:
    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = []
        self.status = "running"
        self.result = ""

    def ask(self, prompt, options=None, allow_text=True):
        self.asked.append({"prompt": prompt, "options": [o["label"] for o in options or []], "allow_text": allow_text})
        return self.answers.pop(0)

    def emit(self, *a, **k):
        pass

    def save(self):
        pass


class _Ctx:
    def __init__(self, job, book, outputs, prov_type="openai"):
        self.job, self.book = job, book
        self.prov = {"type": prov_type, "max_output": 4096}
        self.truncated = False
        self.outputs = list(outputs)
        self.calls = 0
        self.meta = None

    def budget(self, n):
        return 8000

    def call(self, msgs, **kw):
        self.calls += 1
        self.last_msgs = msgs
        return self.outputs.pop(0)

    def save_messages(self, msgs, extra=None):
        pass


def test_gate_confirm_writes_the_files(tmp_path):
    d = _book(tmp_path)
    job = _Job(["確認，寫進檔案"])
    ctx = _Ctx(job, d, ["提案：分三卷", FILE_BLOCK])
    native_files.run_spec(ctx, {}, _spec, "sys")
    assert job.asked and job.asked[0]["options"][0] == prompts.pack("zh-TW")["gate_option_confirm"]
    assert os.path.isfile(os.path.join(d, "大綱", "全書大綱.md"))
    assert "已建立" in ctx.job.result or "全書大綱" in ctx.job.result
    assert ctx.calls == 2          # 先提案，確認後才輸出檔案


def test_gate_skip_writes_nothing(tmp_path):
    d = _book(tmp_path)
    job = _Job([prompts.pack("zh-TW")["gate_option_skip"]])
    ctx = _Ctx(job, d, ["提案：分三卷", FILE_BLOCK])
    native_files.run_spec(ctx, {}, _spec, "sys")
    assert ctx.calls == 1
    assert not os.path.isfile(os.path.join(d, "大綱", "全書大綱.md"))
    assert prompts.pack("zh-TW")["gate_skipped"] in ctx.job.result


def test_gate_edit_round_then_confirm(tmp_path):
    d = _book(tmp_path)
    P = prompts.pack("zh-TW")
    # 作者第一次直接打字（＝我要改），第二次按確認
    job = _Job(["第二卷的對手要換人", P["gate_option_confirm"]])
    ctx = _Ctx(job, d, ["提案一", "提案二", FILE_BLOCK])
    native_files.run_spec(ctx, {}, _spec, "sys")
    assert len(job.asked) == 2
    assert ctx.calls == 3          # 提案 → 依意見重產 → 確認後輸出檔案
    assert any("第二卷的對手要換人" in m["content"] for m in ctx.last_msgs)
    assert os.path.isfile(os.path.join(d, "大綱", "全書大綱.md"))


def test_gate_confirm_without_files_is_reported(tmp_path):
    d = _book(tmp_path)
    job = _Job([prompts.pack("zh-TW")["gate_option_confirm"]])
    ctx = _Ctx(job, d, ["只有提案", "還是只有提案"])
    native_files.run_spec(ctx, {}, _spec, "sys")
    assert prompts.pack("zh-TW")["gate_no_files"] in ctx.job.result
    assert not os.path.isfile(os.path.join(d, "大綱", "全書大綱.md"))


def test_gate_is_text_only_for_claude_code(tmp_path):
    """Claude Code 沒有 ask：不問，結果尾巴給原本的文字說明。"""
    d = _book(tmp_path)
    job = _Job([])
    ctx = _Ctx(job, d, ["提案：分三卷"], prov_type="claude_code")
    native_files.run_spec(ctx, {}, _spec, "sys")
    assert job.asked == []
    assert prompts.pack("zh-TW")["gate_text_hint"] in ctx.job.result


def test_plain_text_answer_is_treated_as_edit(tmp_path):
    P = prompts.pack("zh-TW")
    assert native_files._gate_verdict(P["gate_option_confirm"], P) == "ok"
    assert native_files._gate_verdict(P["gate_option_skip"], P) == "skip"
    assert native_files._gate_verdict(P["gate_option_edit"], P) == "edit"
    assert native_files._gate_verdict("確認", P) == "ok"
    assert native_files._gate_verdict("跳過", P) == "skip"
    assert native_files._gate_verdict("第三卷太短，拉長一點", P) == "edit"
