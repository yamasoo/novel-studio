"""長時間任務（docs/02_API合約.md 第 4 節）：JobRunner、Job，以及輪詢與 SSE 端點。

用法：
    runner = JobRunner()

    def draft(job, chapter):                  # 一般函式在背景執行緒跑；async def 也可以（各自一個事件迴圈）
        job.set(phase="streaming", note="第 %d 章" % chapter)
        job.begin("c", "草稿")
        for piece in pieces:
            job.checkpoint()                  # 使用者按了停止就丟出 JobStopped，任務變成 stopped
            job.write("c", piece)
        job.end("c")
        return "完成"                          # 字串會變成 result = {"text": "完成"}

    @app.post("/api/drafts")                  # 建立任務的端點由專案自己寫
    def create(body: dict):
        return runner.start(draft, body["chapter"], kind="draft", title="產生草稿").summary()

    install(app, jobs=runner)                 # 掛上 /api/jobs 的端點

執行緒安全：Job 的方法可以從任何執行緒呼叫；端點在事件迴圈裡只做短暫的加鎖讀取。
"""
import asyncio
import bisect
import copy
import inspect
import json
import logging
import secrets
import threading
import time
from collections import deque

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from .errors import ApiError

log = logging.getLogger("fekit.jobs")

TERMINAL = ("done", "error", "stopped")
LEVELS = ("info", "warn", "error", "dim")
SETTABLE = ("title", "phase", "note", "progress", "items", "result")


class JobStopped(Exception):
    """使用者要求停止。在任務函式裡不要吞掉它，runner 會把任務標成 stopped。"""


class JobError(Exception):
    """任務失敗。訊息要是人看得懂的繁體中文，會直接顯示在面板上。"""


def _json_safe(value, name):
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise TypeError("%s 必須能轉成 JSON：%s" % (name, exc)) from None
    return copy.deepcopy(value)


def _clean_progress(value):
    if value is None:
        return None
    if isinstance(value, (tuple, list)) and len(value) == 2:
        value = {"done": value[0], "total": value[1]}
    if not isinstance(value, dict) or "done" not in value or "total" not in value:
        raise TypeError("progress 要是 {'done':, 'total':} 或 (done, total)")
    return {"done": value["done"], "total": value["total"]}


def _clean_options(options):
    result = []
    for option in options or ():
        if isinstance(option, dict):
            value = option["value"]
            label = option.get("label", value)
        elif isinstance(option, (tuple, list)):
            value, label = option
        else:
            value = label = option
        result.append({"value": str(value), "label": str(label)})
    return result


class Job:
    """任務物件。任務函式拿到的第一個參數就是它。"""

    def __init__(self, runner, job_id, kind, title):
        self._runner = runner
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._subs = []
        self._seq = 0
        self._rev = 0
        self._log = []        # [(seq, 內容)]
        self._stream = []
        self._dropped = 0     # 已丟棄的內容中最大的 seq
        self._ask_count = 0
        self._ask_waiting = False
        self._reply = None
        self.id = job_id
        self.kind = kind
        self.title = title
        self.status = "running"
        self.phase = "starting"
        self.note = ""
        self.progress = None
        self.stop_requested = False
        self.started_at = time.time()
        self.ended_at = None
        self.items = []
        self.ask_info = None
        self.error = None
        self.result = None

    # ── 狀態快照（端點用） ─────────────────────

    def _fields(self):
        return {
            "id": self.id, "kind": self.kind, "title": self.title, "status": self.status,
            "phase": self.phase, "note": self.note, "progress": self.progress,
            "stop_requested": self.stop_requested, "started_at": self.started_at,
            "ended_at": self.ended_at, "items": copy.deepcopy(self.items), "ask": copy.deepcopy(self.ask_info),
            "error": self.error, "result": copy.deepcopy(self.result),
        }

    def _snapshot(self, since, content=True):
        """合約 4.5 的增量。呼叫端要持有鎖。seq 一定等於這份內容實際涵蓋到的位置。"""
        data = self._fields()
        data["seq"] = self._seq
        if content:
            data["log"] = [item for _, item in self._log[bisect.bisect_right(self._log, since, key=lambda e: e[0]):]]
            data["stream"] = [item for _, item in self._stream[bisect.bisect_right(self._stream, since, key=lambda e: e[0]):]]
            if since < self._dropped:
                data["truncated"] = True
        return data

    def summary(self):
        """不含 log、stream 的任務物件。可以直接當建立任務的回應，也是 POST 的回應格式（合約 4.5 第 6 條）。"""
        with self._lock:
            data = self._fields()
            data["seq"] = self._seq
            return data

    def patch(self, since=0):
        """含內容的完整增量（輪詢的回應）。"""
        with self._lock:
            return self._snapshot(since)

    # ── 內部：通知 ─────────────────────────────

    def _touch(self):
        self._rev += 1
        self._cond.notify_all()
        for loop, event in list(self._subs):
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:  # 事件迴圈已關閉
                self._subs.remove((loop, event))

    def _subscribe(self, loop, event):
        with self._lock:
            self._subs.append((loop, event))

    def _unsubscribe(self, loop, event):
        with self._lock:
            if (loop, event) in self._subs:
                self._subs.remove((loop, event))

    def _trim(self, entries, limit):
        if limit and len(entries) > limit:
            self._dropped = max(self._dropped, entries[-limit - 1][0])
            del entries[:-limit]

    def _add(self, log=(), stream=()):
        with self._lock:
            for item in log:
                self._seq += 1
                self._log.append((self._seq, item))
            for item in stream:
                self._seq += 1
                self._stream.append((self._seq, item))
            self._trim(self._log, self._runner.log_limit)
            self._trim(self._stream, self._runner.stream_limit)
            self._touch()

    def _update(self, **fields):
        with self._lock:
            for key, value in fields.items():
                setattr(self, key, value)
            self._touch()

    # ── 任務函式用的介面 ───────────────────────

    def set(self, **fields):
        """更新 title、phase、note、progress、items、result。progress 可寫 (done, total)。"""
        unknown = set(fields) - set(SETTABLE)
        if unknown:
            raise TypeError("不能設定的欄位：%s" % "、".join(sorted(unknown)))
        clean = {}
        for key, value in fields.items():
            if key == "progress":
                value = _clean_progress(value)
            elif key == "items":
                value = _json_safe(list(value or ()), "items")
            elif key == "result":
                value = _json_safe(value, "result")
            else:
                value = "" if value is None else str(value)
            clean[key] = value
        self._update(**clean)

    def item(self, key, **fields):
        """改 items 裡 key 相符的那一項（state、note、label）；沒有就新增。"""
        with self._lock:
            items = copy.deepcopy(self.items)
            for entry in items:
                if entry.get("key") == key:
                    entry.update(fields)
                    break
            else:
                items.append(dict(fields, key=key))
            self._update(items=items)

    def say(self, text, level="info"):
        """寫一筆日誌。"""
        if level not in LEVELS:
            raise ValueError("level 要是 %s 其中之一" % "、".join(LEVELS))
        self._add(log=[{"level": level, "text": str(text)}])

    def begin(self, seg, label=None, format=None):
        event = {"seg": str(seg), "type": "begin"}
        if label is not None:
            event["label"] = str(label)
        if format is not None:
            if format not in ("text", "md", "json"):
                raise ValueError("format 要是 text、md、json 其中之一")
            event["format"] = format
        self._add(stream=[event])

    def write(self, seg, text):
        if text:
            self._add(stream=[{"seg": str(seg), "type": "text", "text": str(text)}])

    def think(self, seg, text):
        if text:
            self._add(stream=[{"seg": str(seg), "type": "thinking", "text": str(text)}])

    def end(self, seg, note=None):
        event = {"seg": str(seg), "type": "end"}
        if note:
            event["note"] = str(note)
        self._add(stream=[event])

    @property
    def stopping(self):
        return self._stop.is_set()

    def checkpoint(self):
        """在安全的地方呼叫。已要求停止就丟出 JobStopped。"""
        if self._stop.is_set():
            raise JobStopped()

    def sleep(self, seconds):
        """可以被停止打斷的 sleep。回傳 False 表示被要求停止。"""
        return not self._stop.wait(seconds)

    def ask(self, prompt, options=None, allow_text=True, wait=True):
        """向使用者提問（合約 4.7）。

        wait=True：任務暫停到有回覆，回傳回覆文字；等待中被要求停止會丟出 JobStopped。
        wait=False：只掛上提問，不等待（用在任務結束前，使用者回覆後由 JobRunner(followup=...) 接著做）。
        """
        with self._lock:
            self._ask_count += 1
            ask = {"id": "a%d" % self._ask_count, "prompt": str(prompt), "allow_text": bool(allow_text)}
            clean = _clean_options(options)
            if clean:
                ask["options"] = clean
            self._reply = None
            self._ask_waiting = bool(wait)
            self._update(ask_info=ask)
            if not wait:
                return ask["id"]
            while self._reply is None:
                if self._stop.is_set():
                    self._ask_waiting = False
                    self._update(ask_info=None)
                    raise JobStopped()
                self._cond.wait(0.5)
            reply, self._reply = self._reply, None
            self._ask_waiting = False
            return reply

    # ── runner 與端點用 ────────────────────────

    def request_stop(self):
        with self._lock:
            if self.status in TERMINAL:
                return
            self._stop.set()
            self._update(stop_requested=True)
        self._runner._wake()

    def _deliver_reply(self, ask_id, text):
        """回傳 'waiting'（任務會繼續）、'followup'（任務已結束，要接著做）；提問不符回傳 None。"""
        with self._lock:
            if self.ask_info is None or self.ask_info["id"] != ask_id:
                return None
            if self.status in TERMINAL:
                return "followup"
            if not self._ask_waiting:
                return None
            self._reply = text
            self.ask_info = None
            self._touch()
            return "waiting"

    def _clear_ask(self):
        with self._lock:
            self._update(ask_info=None)

    def _finish(self, status, error=None, result=None):
        with self._lock:
            self._update(status=status, phase="idle", note="", error=error, result=result, ended_at=time.time())


class JobRunner:
    """管理任務、執行緒與端點。

    max_running  同時最多幾個任務在跑（預設 1）。
    queue        True：超過時排隊（status 是 queued）；False：直接回 409。
    log_limit、stream_limit  每個任務各留最近幾筆；超過的丟掉，增量會帶 truncated: true。
    followup     fn(job, text) -> Job | None。任務結束後使用者回覆提問時呼叫，回傳新任務就接著追蹤（合約 4.7）。
    ping_seconds SSE 閒置多久送一次 ': ping'。
    """

    def __init__(self, *, max_running=1, queue=False, log_limit=2000, stream_limit=20000, followup=None, ping_seconds=15):
        if max_running < 1:
            raise ValueError("max_running 至少是 1")
        self.max_running = max_running
        self.queue = queue
        self.log_limit = log_limit
        self.stream_limit = stream_limit
        self.followup = followup
        self.ping_seconds = ping_seconds
        self._cond = threading.Condition()
        self._jobs = {}        # 依建立順序
        self._waiting = deque()
        self._running = 0
        self._counter = 0

    # ── 建立與查詢 ─────────────────────────────

    def start(self, fn, *args, kind="job", title=None, queue=None, **kwargs):
        """開始一個任務，回傳 Job。已滿且不排隊時丟出 ApiError(409)。fn(job, *args, **kwargs)。"""
        allow_queue = self.queue if queue is None else queue
        with self._cond:
            immediate = self._running + len(self._waiting) < self.max_running
            if not immediate and not allow_queue:
                raise ApiError(409, "已經有任務在執行，請等它結束再試一次。", "busy")
            self._counter += 1
            job_id = "j_%s_%04d_%s" % (time.strftime("%Y%m%d"), self._counter, secrets.token_hex(2))
            job = Job(self, job_id, str(kind), str(title if title is not None else kind))
            self._jobs[job_id] = job
            if immediate:
                self._running += 1
            else:
                job.status = "queued"
                job.phase = "waiting"
                job.note = "前面還有任務，排隊中"
                self._waiting.append(job)
        threading.Thread(target=self._work, args=(job, fn, args, kwargs, immediate), name="fekit-" + job_id, daemon=True).start()
        return job

    def get(self, job_id):
        return self._jobs.get(job_id)

    def require(self, job_id):
        job = self._jobs.get(job_id)
        if job is None:
            raise ApiError(404, "找不到這個任務（後端可能重新啟動過）。", "not_found")
        return job

    def jobs(self):
        """新的在前。"""
        return list(reversed(list(self._jobs.values())))

    def stop_all(self):
        for job in self.jobs():
            job.request_stop()

    def _wake(self):
        with self._cond:
            self._cond.notify_all()

    # ── 執行 ───────────────────────────────────

    def _acquire(self, job):
        """排隊等位子。等到回傳 True；排隊中被要求停止回傳 False。"""
        with self._cond:
            while True:
                if job._stop.is_set():
                    if job in self._waiting:
                        self._waiting.remove(job)
                    self._cond.notify_all()
                    return False
                if self._waiting and self._waiting[0] is job and self._running < self.max_running:
                    self._waiting.popleft()
                    self._running += 1
                    return True
                self._cond.wait(0.5)

    def _work(self, job, fn, args, kwargs, immediate):
        held = immediate  # 是否占著一個執行位子
        try:
            if not immediate:
                if not self._acquire(job):
                    job._finish("stopped")
                    return
                held = True
                job._update(status="running", phase="starting", note="")
            job._update(started_at=time.time())
            self._run(job, fn, args, kwargs)
        finally:
            with self._cond:
                if held:
                    self._running -= 1
                self._cond.notify_all()

    def _run(self, job, fn, args, kwargs):
        try:
            if inspect.iscoroutinefunction(fn):
                value = asyncio.run(fn(job, *args, **kwargs))
            else:
                value = fn(job, *args, **kwargs)
            result = {"text": value} if isinstance(value, str) else _json_safe(value, "任務的回傳值")
            job._finish("done", result=result)
        except JobStopped:
            job.say("已依要求停止", "warn")
            job._finish("stopped")
        except (JobError, ApiError) as exc:
            message = exc.message if isinstance(exc, ApiError) else str(exc)
            job.say(message, "error")
            job._finish("error", error=message)
        except Exception as exc:
            log.exception("任務 %s 發生未預期的錯誤", job.id)
            job.say("發生未預期的錯誤（%s），詳細內容請看後端主控台。" % type(exc).__name__, "error")
            job._finish("error", error="任務發生未預期的錯誤，詳細內容請看後端主控台。")

    # ── 端點 ───────────────────────────────────

    def routes(self, base="/api/jobs"):
        base = base.rstrip("/")
        return [
            Route(base, self._list, methods=["GET"]),
            Route(base + "/{job_id}", self._poll, methods=["GET"]),
            Route(base + "/{job_id}/events", self._events, methods=["GET"]),
            Route(base + "/{job_id}/stop", self._stop_job, methods=["POST"]),
            Route(base + "/{job_id}/reply", self._reply_job, methods=["POST"]),
        ]

    @staticmethod
    def _int(value, name, default, minimum=0, maximum=None):
        if value in (None, ""):
            return default
        try:
            number = int(value)
        except ValueError:
            raise ApiError(400, "參數 %s 必須是整數。" % name, "bad_param") from None
        if number < minimum or (maximum is not None and number > maximum):
            raise ApiError(400, "參數 %s 超出範圍。" % name, "bad_param")
        return number

    async def _list(self, request: Request):
        wanted = {part for part in request.query_params.get("status", "").split(",") if part}
        limit = self._int(request.query_params.get("limit"), "limit", 20, 1, 200)
        rows = [job.summary() for job in self.jobs() if not wanted or job.status in wanted]
        return JSONResponse({"jobs": rows[:limit]})

    async def _poll(self, request: Request):
        job = self.require(request.path_params["job_id"])
        since = self._int(request.query_params.get("since"), "since", 0)
        return JSONResponse(job.patch(since))

    async def _body(self, request):
        raw = await request.body()
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except ValueError:
            raise ApiError(400, "請求本體不是正確的 JSON。", "bad_json") from None
        if not isinstance(data, dict):
            raise ApiError(400, "請求本體要是 JSON 物件。", "bad_json")
        return data

    async def _stop_job(self, request: Request):
        job = self.require(request.path_params["job_id"])
        await self._body(request)
        job.request_stop()
        return JSONResponse(job.summary())

    async def _reply_job(self, request: Request):
        job = self.require(request.path_params["job_id"])
        body = await self._body(request)
        ask_id, text = body.get("ask_id"), body.get("text", "")
        if not isinstance(ask_id, str) or not isinstance(text, str):
            raise ApiError(400, "回覆需要 ask_id 與 text（字串）。", "bad_param")
        outcome = job._deliver_reply(ask_id, text)
        if outcome is None:
            raise ApiError(409, "這個提問已經過期，請重新整理後再回覆。", "stale_ask")
        if outcome == "waiting":
            return JSONResponse(job.summary())
        if self.followup is None:
            raise ApiError(409, "這個任務已經結束，無法接著做。", "no_followup")
        new_job = self.followup(job, text)
        if inspect.isawaitable(new_job):
            new_job = await new_job
        if not isinstance(new_job, Job):
            raise ApiError(409, "無法接著做這個任務。", "no_followup")
        job._clear_ask()
        return JSONResponse(new_job.summary())

    async def _events(self, request: Request):
        job = self.require(request.path_params["job_id"])
        header = request.headers.get("last-event-id")
        try:
            start = int(header) if header not in (None, "") else self._int(request.query_params.get("since"), "since", 0)
        except ValueError:
            start = 0
        return StreamingResponse(
            self._event_stream(job, max(start, 0)),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def _event_stream(self, job, start):
        """第一則帶齊所有欄位與 start 之後的內容（合約 4.8 的第一種寫法），之後只在有變化時送。"""
        loop = asyncio.get_running_loop()
        event = asyncio.Event()
        job._subscribe(loop, event)
        cursor, seen = start, None
        try:
            while True:
                event.clear()
                with job._lock:
                    if seen is None or job._rev != seen:
                        patch = job._snapshot(cursor)
                        seen, cursor = job._rev, patch["seq"]
                    else:
                        patch = None
                if patch is not None:
                    yield "id: %d\ndata: %s\n\n" % (patch["seq"], json.dumps(patch, ensure_ascii=False, separators=(",", ":")))
                    if patch["status"] in TERMINAL:
                        yield "event: close\ndata: {}\n\n"
                        return
                    continue
                try:
                    await asyncio.wait_for(event.wait(), self.ping_seconds)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            job._unsubscribe(loop, event)
