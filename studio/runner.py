# -*- coding: utf-8 -*-
"""在背景執行 Claude Code（非互動模式），把輸出整理成事件串流。"""
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

from . import lang as lang_mod, prompts

# 系統提示詞依書的語言取自 studio/prompts/（保持單行：Windows 的 claude.cmd 會把參數裡的換行切斷）


def studio_system(book_dir):
    return prompts.pack(lang_mod.book_lang(book_dir))["studio_system"]


IS_WIN = os.name == "nt"
KEEP_FINISHED = 30      # 記憶體裡保留最近幾個「已結束」的任務；執行中的永遠保留（磁碟另有完整紀錄）


def find_claude(cmd=None):
    cand = cmd or "claude"
    if os.path.isabs(cand) and os.path.isfile(cand):
        return cand
    found = shutil.which(cand)
    if found:
        return found
    if IS_WIN:
        for p in (os.path.expandvars(r"%USERPROFILE%\.local\bin\claude.exe"),
                  os.path.expandvars(r"%APPDATA%\npm\claude.cmd")):
            if os.path.isfile(p):
                return p
    return None


# 由工作台自己編排、每一步只要 Claude 回一段文字的動作（例如從正文建立設定）
NATIVE_WITH_CLAUDE = ("reverse", "glossary_org")


class ClaudeOnceError(Exception):
    pass


class JobStopped(Exception):
    """任務被停止時，還在等作者回覆的 native 流程要能乾淨地結束（不算錯誤）。"""


def claude_print(cfg, prompt, system="", cwd=None, should_stop=None, timeout=1800, model=None):
    """呼叫一次 claude -p（不用工具、不接續對話），回傳 (文字, usage)。
    用在工作台自己分批的長任務：每一批都是獨立的一次呼叫，不會把整本書塞進同一個對話。"""
    exe = find_claude(cfg.get("claude_cmd"))
    if not exe:
        raise ClaudeOnceError("找不到 claude 指令。請確認已安裝 Claude Code，或在設定中填入 claude 的完整路徑。")
    cmd = [exe, "-p", "--output-format", "json", "--max-turns", "1",
           "--disallowedTools", "Bash,Edit,Write,MultiEdit,NotebookEdit,Read,Glob,Grep,WebFetch,WebSearch,Task"]
    if system:
        cmd += ["--append-system-prompt", " ".join(system.split())]   # 保持單行（Windows 的 claude.cmd）
    if model or cfg.get("model"):
        cmd += ["--model", model or cfg["model"]]
    kw = {}
    if IS_WIN:
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if cmd[0].lower().endswith((".cmd", ".bat")):
            cmd = " ".join('"%s"' % a.replace('"', '""') for a in cmd)
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, **kw)
    out = {}

    def talk():
        out["o"], out["e"] = proc.communicate(prompt.encode("utf-8"))
    th = threading.Thread(target=talk, daemon=True)
    th.start()
    t0 = time.time()
    while th.is_alive():
        th.join(0.5)
        if (should_stop and should_stop()) or time.time() - t0 > timeout:
            proc.kill()
            th.join(5)
            raise ClaudeOnceError("已停止" if should_stop and should_stop() else "Claude Code 超過 %d 秒沒有回應" % timeout)
    raw = (out.get("o") or b"").decode("utf-8", "replace").strip()
    try:
        data = json.loads(raw.splitlines()[-1] if raw else "{}")
    except ValueError:
        data = {}
    if proc.returncode != 0 or data.get("is_error") or "result" not in data:
        err = (out.get("e") or b"").decode("utf-8", "replace").strip()
        raise ClaudeOnceError("Claude Code 執行失敗：%s" % ((data.get("result") or err or raw)[:300] or "結束代碼 %s" % proc.returncode))
    u = data.get("usage") or {}
    usage = {"prompt_tokens": int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0)
             + int(u.get("cache_creation_input_tokens") or 0),
             "completion_tokens": int(u.get("output_tokens") or 0), "cost_usd": data.get("total_cost_usd")}
    return data["result"], usage


def _short(path, cwd):
    if not path:
        return ""
    try:
        r = os.path.relpath(path, cwd)
        return path if r.startswith("..") else r.replace("\\", "/")
    except ValueError:
        return path


def summarize_tool(name, inp, cwd):
    inp = inp or {}
    if name in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        verb = {"Read": "讀取", "Write": "寫入", "Edit": "修改", "MultiEdit": "修改"}.get(name, name)
        return "%s %s" % (verb, _short(inp.get("file_path") or inp.get("notebook_path"), cwd))
    if name == "Bash":
        return "執行指令：%s" % (inp.get("description") or inp.get("command", ""))[:120]
    if name in ("Glob", "Grep"):
        return "搜尋：%s" % (inp.get("pattern") or "")
    if name == "Skill":
        return "載入 skill：%s" % (inp.get("skill") or inp.get("command") or "")
    if name in ("Task", "Agent"):
        return "啟動子代理：%s" % (inp.get("description") or "")
    if name == "TodoWrite":
        return "更新待辦清單"
    if name == "WebSearch":
        return "網路搜尋：%s" % inp.get("query", "")
    return name


class Job:
    def __init__(self, book_id, book_dir, title, prompt, resume=None, meta=None, provider=None):
        self.id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.book_id = book_id
        self.book_dir = book_dir
        self.title = title
        self.prompt = prompt
        self.resume = resume
        self.meta = meta or {}
        self.events = []
        self.status = "running"     # running / done / error / cancelled
        self.session_id = resume
        self.started = time.time()
        self.ended = None
        self.result = ""
        self.cost = None
        self.proc = None
        self.lock = threading.Lock()
        self.after = None           # 完成後的回呼
        self.provider = provider or {"id": "claude_code", "type": "claude_code", "name": "Claude Code"}
        self.asks = {}              # 面板提問（開書訪談用）：id -> {id, prompt, options, allow_text, event, text, answered}
        self.ask_seq = 0

    # ------------------------------------------------------------------
    def emit(self, kind, **kw):
        ev = {"i": len(self.events), "t": time.time(), "kind": kind}
        ev.update(kw)
        with self.lock:
            self.events.append(ev)

    def to_dict(self, with_events=False):
        d = {"id": self.id, "book": self.book_id, "title": self.title, "prompt": self.prompt,
             "status": self.status, "session_id": self.session_id, "started": self.started,
             "ended": self.ended, "result": self.result, "cost": self.cost, "meta": self.meta,
             "resume": self.resume, "provider": self.provider.get("id"), "provider_name": self.provider.get("name")}
        if with_events:
            d["events"] = list(self.events)
        return d

    # ── 面板提問（ask）──────────────────────────────────────────────
    # 為什麼要自己實作：Claude Code 是 claude -p（非互動），但 API 執行者可以在任務中途
    # 停下來問作者問題，面板（vendor/fekit）已經會畫選項與輸入框，這裡只補「後端會等人」。
    def pending_ask(self):
        """目前等作者回答的那一題（沒有就 None）。只回傳給前端看的欄位。"""
        if self.status != "running":
            return None
        with self.lock:
            for ask in self.asks.values():
                if not ask["answered"]:
                    return {"id": ask["id"], "prompt": ask["prompt"],
                            "options": ask["options"], "allow_text": ask["allow_text"]}
        return None

    def ask(self, prompt, options=None, allow_text=True):
        """停下來問作者一題；他按選項或打字送出後回傳文字。任務被停止時丟 JobStopped。"""
        if self.status != "running":
            raise JobStopped()
        clean = []
        for o in options or []:
            if isinstance(o, dict):
                label = str(o.get("label") or "")
                clean.append({"label": label, "value": str(o.get("value", label))})
            else:
                clean.append({"label": str(o), "value": str(o)})
        with self.lock:
            self.ask_seq += 1
            ask_id = "a%d" % self.ask_seq
            ask = {"id": ask_id, "prompt": str(prompt), "options": clean,
                   "allow_text": bool(allow_text), "answered": False, "text": "", "event": threading.Event()}
            self.asks[ask_id] = ask
        self.emit("log", text="等待你的回覆：%s" % str(prompt).split("\n")[0][:80])
        try:
            self.save()      # 讓重新整理或換一台電腦打開時還看得到「在等什麼」
        except Exception:
            pass
        while not ask["event"].wait(0.5):
            if self.status != "running":
                with self.lock:
                    self.asks.pop(ask_id, None)
                raise JobStopped()
        if self.status != "running":
            raise JobStopped()
        return ask["text"]

    def deliver_reply(self, ask_id, text):
        """把面板的回覆送進等著的提問；提問不存在或已回答回傳 None（呼叫端轉 409）。"""
        with self.lock:
            ask = self.asks.get(ask_id)
            if not ask or ask["answered"]:
                return None
            ask["answered"] = True
            ask["text"] = str(text)
        ask["event"].set()
        self.emit("log", text="收到回覆：%s" % str(text)[:120])
        return "ok"

    def save(self):
        from . import project
        d = os.path.join(self.book_dir, ".studio", "jobs")
        os.makedirs(d, exist_ok=True)
        # 任務紀錄含完整事件，可能幾百 KB：用原子寫，中途斷掉才不會留下半個 json
        project.write_atomic(os.path.join(d, self.id + ".json"),
                             json.dumps(self.to_dict(True), ensure_ascii=False))


class Runner:
    def __init__(self, get_config, home=None, plugin_dir=None, checker=None, on_forget=None):
        self.get_config = get_config
        self.home, self.plugin_dir, self.checker = home, plugin_dir, checker
        self.jobs = {}
        self.lock = threading.Lock()
        self.on_forget = on_forget     # 被回收的任務 id：讓 ns_jobs 一起放掉它的 View

    def running_for(self, book_id):
        with self.lock:
            for j in self.jobs.values():
                if j.book_id == book_id and j.status == "running":
                    return j
        return None

    def start(self, job):
        if self.running_for(job.book_id):
            raise RuntimeError("這本書已經有任務在執行，請等它結束或先停止它。")
        with self.lock:
            self.jobs[job.id] = job
        t = threading.Thread(target=self._run, args=(job,), daemon=True)
        t.start()
        return job

    def get(self, job_id):
        return self.jobs.get(job_id)

    def reclaim(self, keep=None):
        """只留最近 keep 個已結束的任務，回傳被放掉的 id。
        任務結束時已經寫進 .studio/jobs/，之後要看清單或明細會改讀檔案，不會掉資料。"""
        keep = KEEP_FINISHED if keep is None else int(keep)
        with self.lock:
            done = sorted((j.ended or j.started or 0, jid)
                          for jid, j in self.jobs.items() if j.status != "running")
            drop = [jid for _, jid in done[:max(0, len(done) - keep)]]
            for jid in drop:
                self.jobs.pop(jid, None)
        if drop and self.on_forget:
            try:
                self.on_forget(drop)
            except Exception:
                pass
        return drop

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if not job or job.status != "running":
            return False
        job.status = "cancelled"
        if not job.proc:      # 原生流程：串流迴圈會檢查狀態後停下
            return True
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(job.proc.pid)],
                               capture_output=True)
            else:
                os.killpg(os.getpgid(job.proc.pid), signal.SIGTERM)
        except Exception:
            try:
                job.proc.kill()
            except Exception:
                pass
        return True

    # ------------------------------------------------------------------
    def build_cmd(self, job):
        cfg = self.get_config()
        exe = find_claude(cfg.get("claude_cmd"))
        if not exe:
            raise FileNotFoundError("找不到 claude 指令。請確認已安裝 Claude Code，或在設定中填入 claude 的完整路徑。")
        from . import shared
        cmd = [exe, "-p", "--output-format", "stream-json", "--verbose",
               "--append-system-prompt", studio_system(job.book_dir) + shared.claude_note(job.book_dir)]
        mode = cfg.get("permission_mode") or "acceptEdits"
        cmd += ["--permission-mode", mode]
        tools = cfg.get("allowed_tools") or []
        if tools:
            cmd += ["--allowedTools"] + list(tools)
        if self.plugin_dir and os.path.isdir(self.plugin_dir):
            # 工作台內建的 novel-* skills（不依賴 ~/.claude/skills）；非中文的書改用該語言的 plugin-<語言>/
            from . import context, lang as lang_mod
            pdir = context.lang_plugin(self.plugin_dir, lang_mod.book_lang(job.book_dir))
            cmd += ["--plugin-dir", pdir, "--add-dir", pdir]
        sd = shared.shared_of_book(job.book_dir)
        if os.path.isdir(sd):
            # 書庫的 _共用/（共用作者偏好），讓 Claude 讀得到
            cmd += ["--add-dir", sd]
        for d in cfg.get("add_dirs") or []:
            d = os.path.expandvars(os.path.expanduser(d))
            if os.path.isdir(d):
                cmd += ["--add-dir", d]
        model = (job.provider or {}).get("model") or cfg.get("model")   # 選了「Claude Code · Opus」這類時用選的模型
        if model:
            cmd += ["--model", model]
        if job.resume:
            cmd += ["--resume", job.resume]
        return cmd

    def _run(self, job):
        try:
            self._run_job(job)
        finally:
            self.reclaim()      # 任務結束就回收舊任務，長時間開著才不會單調成長

    def _run_job(self, job):
        try:
            from . import prompts, lang as _lang
            prompts.set_lang(_lang.book_lang(job.book_dir))
        except Exception:
            pass
        if job.provider.get("type") != "claude_code" or (job.meta or {}).get("action") in NATIVE_WITH_CLAUDE:
            from . import native
            native.run(job, job.provider, self.home, self.plugin_dir, self.checker, self.get_config())
            if job.status == "running":
                job.status = "done"
            job.ended = time.time()
            job.emit("end", status=job.status)
            job.save()
            return
        try:
            cmd = self.build_cmd(job)
        except Exception as e:
            job.emit("error", text=str(e))
            job.status = "error"
            job.ended = time.time()
            job.emit("end", status=job.status)
            job.save()
            return
        job.emit("start", text="開始執行" + ("（接續上一輪對話）" if job.resume else ""))
        kw = {}
        if IS_WIN:
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kw["start_new_session"] = True
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        if IS_WIN and cmd[0].lower().endswith((".cmd", ".bat")):
            # 透過 cmd.exe 執行的批次檔：每個參數都加引號，避免 ( ) * 等字元被誤解
            cmd = " ".join('"%s"' % a.replace('"', '""') for a in cmd)
        try:
            job.proc = subprocess.Popen(cmd, cwd=job.book_dir, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, **kw)
        except Exception as e:
            job.emit("error", text="無法啟動 Claude Code：%s" % e)
            job.status = "error"
            job.ended = time.time()
            job.emit("end", status=job.status)
            job.save()
            return

        def feed():
            try:
                job.proc.stdin.write(job.prompt.encode("utf-8"))
                job.proc.stdin.close()
            except Exception:
                pass

        def read_err():
            for raw in job.proc.stderr:
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    job.emit("log", text=line)

        threading.Thread(target=feed, daemon=True).start()
        threading.Thread(target=read_err, daemon=True).start()

        got_result = False
        for raw in job.proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                job.emit("log", text=line)
                continue
            got_result = self._handle(job, msg) or got_result
        job.proc.wait()

        if job.status == "cancelled":
            job.emit("cancelled", text="已停止")
        elif job.proc.returncode != 0 and not got_result:
            job.status = "error"
            job.emit("error", text="Claude Code 結束代碼 %s" % job.proc.returncode)
        elif job.status == "running":
            job.status = "done"
        job.ended = time.time()
        if job.after and job.status == "done":
            try:
                job.after(job)
            except Exception as e:
                job.status = "error"
                job.emit("error", text=str(e))
        job.emit("end", status=job.status)
        job.save()

    def _handle(self, job, msg):
        t = msg.get("type")
        if msg.get("session_id"):
            job.session_id = msg["session_id"]
        if t == "system" and msg.get("subtype") == "init":
            job.emit("init", session_id=msg.get("session_id"), model=msg.get("model"))
        elif t == "assistant":
            for block in (msg.get("message") or {}).get("content") or []:
                bt = block.get("type")
                if bt == "text" and block.get("text", "").strip():
                    job.emit("text", text=block["text"])
                elif bt == "tool_use":
                    job.emit("tool", name=block.get("name"),
                             text=summarize_tool(block.get("name"), block.get("input"), job.book_dir))
        elif t == "user":
            for block in (msg.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                    c = block.get("content")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    job.emit("tool_error", text=str(c)[:300])
        elif t == "result":
            job.result = msg.get("result") or ""
            job.cost = msg.get("total_cost_usd")
            if msg.get("is_error"):
                job.status = "error"
                job.emit("error", text=job.result or msg.get("subtype", "執行失敗"))
            job.emit("result", text=job.result, cost=job.cost, turns=msg.get("num_turns"))
            return True
        return False


def load_history(book_dir, limit=30):
    d = os.path.join(book_dir, ".studio", "jobs")
    out = []
    if not os.path.isdir(d):
        return out
    names = [f for f in os.listdir(d) if f.endswith(".json") and not f.endswith(".messages.json")]
    for f in sorted(names, reverse=True)[:limit]:
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                j = json.load(fh)
            j.pop("events", None)
            out.append(j)
        except Exception:
            pass
    return out


def load_job_file(book_dir, job_id):
    p = os.path.join(book_dir, ".studio", "jobs", job_id + ".json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)
