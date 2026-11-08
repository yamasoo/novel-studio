# -*- coding: utf-8 -*-
"""舊 novel-studio Job 事件 → fekit 任務增量（docs/02_API合約.md 第 4 節）。

只做三件事：
1. 把舊 `Job.events` 轉成合約增量（`View`）。
2. 提供 `/api/fe/books/{book}/jobs...` 的列表、明細、SSE、stop、reply。
3. 舊任務紀錄（`.studio/jobs/*.json`）用同一支轉接重播。
"""
import asyncio
import json
import threading
import time

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

TERMINAL = ("done", "error", "stopped")
STATUS_MAP = {"running": "running", "done": "done", "error": "error", "cancelled": "stopped"}
COLLAPSE = "\u200c"


class View:
    """把一個舊任務的 append-only 事件轉成合約增量；可重複查詢、不重複轉。"""

    def __init__(self, job, saved=False):
        self.job = job
        self.saved = saved
        self.lock = threading.Lock()
        self.i = 0                 # 已消化的舊事件數
        self.n = 0                 # 內容序號（seq）
        self.version = 0           # 任何事件都加一，SSE 用來判斷要不要送
        self.stream = []           # [(n, event)]
        self.log = []              # [(n, line)]
        self.seg_no = 0
        self.open_seg = None
        self.mark_next = False
        self.error = None
        self.result = None
        self.ended = bool(saved)
        if saved:
            self.sync()

    # ── 讀取舊任務 ──
    def _events(self):
        if isinstance(self.job, dict):
            return self.job.get("events") or []
        with self.job.lock:
            return list(self.job.events)

    def _status(self):
        return self.job.get("status") if isinstance(self.job, dict) else self.job.status

    def _get(self, name, default=None):
        if isinstance(self.job, dict):
            return self.job.get(name, default)
        return getattr(self.job, name, default)

    def sync(self):
        with self.lock:
            events = self._events()
            while self.i < len(events):
                self._one(events[self.i])
                self.i += 1
                self.version += 1

    # ── 轉換 ──
    def _push_stream(self, event):
        self.n += 1
        self.stream.append((self.n, event))

    def _push_log(self, level, text):
        self.n += 1
        self.log.append((self.n, {"level": level, "text": text}))

    def _begin(self, **fields):
        self.seg_no += 1
        seg = fields.pop("seg", "s%d" % self.seg_no)
        self._push_stream(dict({"seg": seg, "type": "begin"}, **fields))
        self.open_seg = seg
        return seg

    def _close(self):
        if self.open_seg:
            self._push_stream({"seg": self.open_seg, "type": "end"})
            self.open_seg = None

    def _ensure(self):
        if self.open_seg:
            return self.open_seg
        return self._begin(format="md")

    def _one(self, event):
        kind = event.get("kind")
        text = event.get("text") or ""
        if kind == "stream_start":
            self._begin(label=text or None, format="json" if event.get("json") else "md")
            self.mark_next = not event.get("json")
        elif kind == "stream":
            seg = self._ensure()
            if self.mark_next:
                text = COLLAPSE + text
                self.mark_next = False
            self._push_stream({"seg": seg, "type": "text", "text": text})
        elif kind == "thinking":
            self._push_stream({"seg": self._ensure(), "type": "thinking", "text": text})
        elif kind == "stream_end":
            self._close()
        elif kind == "text":
            self._close()
            seg = self._begin(format="md")
            self._push_stream({"seg": seg, "type": "text", "text": text})
            self._push_stream({"seg": seg, "type": "end"})
            self.open_seg = None
        elif kind == "tool":
            self._close()
            seg = self._begin(label="工具：%s" % (event.get("name") or ""), format="text")
            self._push_stream({"seg": seg, "type": "text", "text": text or event.get("name") or ""})
            self._push_stream({"seg": seg, "type": "end"})
            self.open_seg = None
        elif kind == "tool_error":
            self._close()
            seg = self._begin(label="工具錯誤", format="text")
            self._push_stream({"seg": seg, "type": "text", "text": text})
            self._push_stream({"seg": seg, "type": "end"})
            self.open_seg = None
        elif kind == "log":
            self._push_log("info", text)
        elif kind == "error":
            self.error = text or "任務失敗"
            self._push_log("error", self.error)
        elif kind == "cancelled":
            self._push_log("dim", text or "已停止")
        elif kind == "result":
            self.result = text
            bits = []
            if event.get("turns"):
                bits.append("%s 輪" % event["turns"])
            usage = event.get("usage") or {}
            if usage:
                bits.append("輸入 %s／輸出 %s tokens" % (
                    usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)))
            if event.get("cost") is not None:
                bits.append("$%.4f" % float(event["cost"]))
            if bits:
                self._push_log("dim", "・".join(bits))
        elif kind == "end":
            self.ended = True
        elif kind in ("init", "start"):
            pass
        else:
            self._push_log("dim", "[%s] %s" % (kind, text))

    # ── 對外 ──
    def terminal(self):
        return self.ended and STATUS_MAP.get(self._status(), self._status()) in TERMINAL

    def ask(self):
        # 執行中的任務有真的提問（開書訪談）：直接把那一題給面板畫成選項。
        job = self.job
        if not isinstance(job, dict) and not self.terminal():
            pending = getattr(job, "pending_ask", None)
            got = pending() if pending else None
            if got:
                return got
        if not self.terminal():
            return None
        # 任務結束後的「補充需求」框：不是正式流程的入口。
        title = self._get("title") or "這個任務"
        return {"id": "reply",
                "prompt": "補充需求…（對「%s」再補一句；正式步驟請用上面的「下一步」或面板的動作按鈕）" % title,
                "allow_text": True}

    def fields(self):
        raw = self._status()
        status = STATUS_MAP.get(raw, raw)
        # 看到 end 之前一律算 running：after 回呼還會補 result，不能讓面板提早結束。
        if not self.ended and status in TERMINAL:
            status = "running"
        return {
            "id": self._get("id"),
            "seq": self.n,
            "kind": (self._get("meta") or {}).get("action", ""),
            "title": self._get("title") or "",
            "status": status,
            "phase": "",
            "note": "",
            "progress": None,
            "stop_requested": bool(self._get("status") == "cancelled" and not self.ended),
            "started_at": self._get("started"),
            "ended_at": self._get("ended"),
            "items": [],
            "truncated": False,
            "ask": self.ask(),
            "error": self.error if status == "error" else None,
            "result": {"text": self.result} if self.result else None,
            # 舊前端還在用的欄位（面板與 finish 會讀）
            "book": self._get("book_id") or (self._get("book") if isinstance(self.job, dict) else None),
            "meta": self._get("meta") or {},
            "session_id": self._get("session_id"),
            "provider": (self._get("provider") or {}).get("id") if isinstance(self._get("provider"), dict) else self._get("provider"),
            "cost": self._get("cost"),
            "started": self._get("started"),
            "prompt": self._get("prompt") or "",
        }

    def patch(self, since=0):
        self.sync()
        data = self.fields()
        data["stream"] = [event for n, event in self.stream if n > since]
        data["log"] = [line for n, line in self.log if n > since]
        return data

    def summary(self):
        self.sync()
        data = self.fields()
        data.pop("stream", None)
        data.pop("log", None)
        # 列表只用來讓 FE.jobs.resume() attach；seq 一定要回 0。
        # 回最新 seq 的話，attach 會從最新的位置開始，之前的輸出全部看不到。
        data["seq"] = 0
        return data


# ── 端點 ──
VIEWS = {}                      # 執行中的任務＋最近幾份已結束的（要回收，不然每個 View 都釘住一個 Job）
VIEWS_LOCK = threading.Lock()
VIEW_KEEP = 30                  # 已結束的任務保留幾份 View


def forget(job_ids):
    """任務被 Runner 回收時，把它的 View 一起放掉（不然 Job 會被 View 釘住回收不掉）。"""
    with VIEWS_LOCK:
        for jid in job_ids:
            VIEWS.pop(jid, None)


def prune_views(keep=None):
    """只留最近 keep 份「已結束」的 View；執行中的不動。"""
    keep = VIEW_KEEP if keep is None else int(keep)
    with VIEWS_LOCK:
        done = sorted((view._get("started") or 0, jid)
                      for jid, view in VIEWS.items() if view.terminal())
        for _, jid in done[:max(0, len(done) - keep)]:
            VIEWS.pop(jid, None)


def job_id_of(job):
    return job.get("id") if isinstance(job, dict) else job.id


def status_of(job):
    """不建 View 也算得出來的狀態；列表用它先篩，歷史任務才不會被白建一份。"""
    raw = job.get("status") if isinstance(job, dict) else job.status
    return STATUS_MAP.get(raw, raw)


def view_of(job):
    """執行中的任務共用一份 View；歷史任務每次給一份新的，不進快取。"""
    if isinstance(job, dict):
        return View(job, saved=True)      # 歷史任務：事件不會再變，但不該被 pin 住
    key = job_id_of(job)
    with VIEWS_LOCK:
        view = VIEWS.get(key)
        created = view is None
        if created:
            view = VIEWS[key] = View(job, saved=False)
    if created:
        prune_views()       # 順手回收舊的：注意要在放掉 VIEWS_LOCK 之後呼叫
    view.sync()
    return view


def install(app, runner, book_dir, load_history, load_job_file, launch_reply):
    runner.on_forget = forget      # Runner 回收任務時，View 跟著放掉
    @app.get("/api/fe/books/{book_id}/jobs")
    def fe_list(book_id: str, status: str = "", limit: int = 20):
        book_dir(book_id)
        jobs = list(load_history(book_dir(book_id)) or [])
        run = runner.running_for(book_id)
        if run:
            jobs = [run] + [j for j in jobs if j.get("id") != run.id]
        wanted = [s.strip() for s in status.split(",") if s.strip()]
        cap = max(1, min(int(limit or 20), 100))
        out = []
        for job in jobs:
            # 歷史任務先用便宜的方式篩掉，被 ?status= 排除的那幾筆不要建 View。
            if wanted and isinstance(job, dict) and status_of(job) not in wanted:
                continue
            row = view_of(job).summary()
            if wanted and row["status"] not in wanted:
                continue          # 執行中的任務還沒看到 end 時狀態會降級，再篩一次
            out.append(row)
            if len(out) >= cap:
                break
        return {"jobs": out}

    @app.get("/api/fe/books/{book_id}/jobs/{job_id}")
    def fe_detail(book_id: str, job_id: str, since: int = 0):
        book_dir(book_id)
        job = runner.get(job_id) or load_job_file(book_dir(book_id), job_id)
        if not job:
            raise HTTPException(404, "找不到任務")
        return view_of(job).patch(since)

    @app.get("/api/fe/books/{book_id}/jobs/{job_id}/events")
    async def fe_events(book_id: str, job_id: str, request: Request, since: int = 0):
        book_dir(book_id)
        job = runner.get(job_id) or load_job_file(book_dir(book_id), job_id)
        if not job:
            raise HTTPException(404, "找不到任務")
        header = request.headers.get("last-event-id")
        if header and header.isdigit():
            since = int(header)
        view = view_of(job)

        async def gen():
            last_version = -1
            last_seq = since
            idle = 0
            while True:
                if await request.is_disconnected():
                    break
                view.sync()
                if view.version != last_version:
                    data = view.patch(last_seq)
                    last_seq = data["seq"]
                    last_version = view.version
                    yield "id: %d\ndata: %s\n\n" % (
                        data["seq"], json.dumps(data, ensure_ascii=False))
                    idle = 0
                else:
                    idle += 1
                    if idle % 75 == 0:
                        yield ": ping\n\n"
                if view.terminal() and view.i >= len(view._events()):
                    yield "event: close\ndata: {}\n\n"
                    break
                await asyncio.sleep(0.2)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/fe/books/{book_id}/jobs/{job_id}/stop")
    def fe_stop(book_id: str, job_id: str):
        book_dir(book_id)
        job = runner.get(job_id)
        if not job:
            raise HTTPException(404, "任務不在執行中")
        runner.cancel(job_id)
        view = view_of(job)
        data = view.fields()          # POST 不回 log/stream
        data.pop("stream", None)
        data.pop("log", None)
        return data

    @app.post("/api/fe/books/{book_id}/jobs/{job_id}/reply")
    async def fe_reply(book_id: str, job_id: str, request: Request):
        book_dir(book_id)
        body = await request.json()
        text = (body.get("text") or "").strip()
        ask_id = body.get("ask_id") or ""
        if not text:
            raise HTTPException(400, "請先輸入回覆")
        live = runner.get(job_id)          # 執行中的任務物件（有真的提問時用它）
        if live is not None and ask_id and ask_id not in ("reply", job_id):
            deliver = getattr(live, "deliver_reply", None)
            if deliver is not None and not isinstance(live, dict):
                if deliver(ask_id, text) != "ok":
                    raise HTTPException(409, "這個提問已經失效，請重新整理後再回覆。")
                # 回的是同一個任務：面板會把 ask 收起來，繼續顯示串流
                data = view_of(live).fields()
                data.pop("stream", None)
                data.pop("log", None)
                return data
        job = live or load_job_file(book_dir(book_id), job_id)
        if not job:
            raise HTTPException(404, "找不到任務")
        status = job.get("status") if isinstance(job, dict) else job.status
        if status == "running":
            # 這一輪沒有提問在等（有提問的話上面就送進去了）
            raise HTTPException(409, "任務還在執行，但目前沒有提問在等回覆。")
        if ask_id not in ("reply", job_id) and ask_id != (job.get("id") if isinstance(job, dict) else job.id):
            raise HTTPException(409, "這個提問已經失效")
        new_job = launch_reply(book_id, job, text)
        data = view_of(new_job).fields()
        data.pop("stream", None)
        data.pop("log", None)
        return data
