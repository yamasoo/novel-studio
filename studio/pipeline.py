# -*- coding: utf-8 -*-
"""
整章自動流程：把一章從章綱到定稿的步驟依序串起來。

每一步都是原本工作台就有的單一動作（各自一次 AI 呼叫，只帶那一步需要的資料），
這裡只負責排順序、等它做完、檢查結果、在中間做不需要 AI 的事（自動勾選意見、套用修訂、搬正文）。

任一步失敗就停在那一步，狀態存在 .studio/流程/目前.json；修正後可以從那一步繼續。
"""
import json
import os
import threading
import time
import uuid

from . import context, goals, project, revision

STEPS = [
    ("card", "章綱"),
    ("write", "寫章節（候選稿）"),
    ("goal", "章綱核對"),
    ("deslop", "去 AI 味"),
    ("review", "審查意見"),
    ("tick", "自動勾選意見"),
    ("revise", "依勾選意見修訂"),
    ("apply", "全部套用修訂"),
    ("accept", "定稿並回寫追蹤"),
]
LABEL = dict(STEPS)
DEFAULT_SEVERITIES = ["必須修", "建議修"]
AUTO_NOTE = ("這是整章自動流程的一步：不要停下來問作者，也不要等作者確認；"
             "不確定的地方採用最合理、和既有設定一致的寫法，並在匯報列出來。")


class PipelineError(Exception):
    pass


class StepFailed(Exception):
    pass


class Stopped(Exception):
    pass


def _state_path(book_dir):
    d = os.path.join(book_dir, ".studio", "流程")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "目前.json")


def load_state(book_dir):
    p = os.path.join(book_dir, ".studio", "流程", "目前.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def new_steps():
    return [{"key": k, "label": v, "status": "pending", "note": "", "job": None, "started": None, "ended": None}
            for k, v in STEPS]


class Pipeline:
    """一個流程 = 一本書、一段章節範圍。hooks 由 app 提供：
    launch(action, params) -> 已啟動的 Job；cancel(job_id)；checker（check_text 模組）。"""

    def __init__(self, book_id, book_dir, state, hooks):
        self.book_id, self.d, self.s, self.h = book_id, book_dir, state, hooks
        self.lock = threading.Lock()
        self.stop_flag = False
        self.job = None
        self.thread = None

    # ------------------------------------------------------------------ 狀態
    @classmethod
    def create(cls, book_id, book_dir, hooks, start, end, mode, severities, provider, note=""):
        state = {"id": uuid.uuid4().hex[:10], "book": book_id, "from": int(start), "to": int(end),
                 "mode": mode if mode in ("stop", "continue") else "stop",
                 "severities": [s for s in (severities or DEFAULT_SEVERITIES) if s in revision.SEVERITIES],
                 "provider": provider, "note": (note or "").strip(),
                 "chapter": int(start), "status": "running", "error": "", "message": "",
                 "steps": new_steps(), "done_chapters": [], "created": time.time(), "updated": time.time()}
        return cls(book_id, book_dir, state, hooks)

    def save(self):
        self.s["updated"] = time.time()
        with open(_state_path(self.d), "w", encoding="utf-8") as f:
            json.dump(self.s, f, ensure_ascii=False, indent=1)

    def to_dict(self):
        with self.lock:
            d = json.loads(json.dumps(self.s, ensure_ascii=False))
        d["job"] = self.job.id if self.job and d["status"] == "running" else None   # 目前（或剛結束）這一步的任務
        return d

    def step(self, key):
        return next(x for x in self.s["steps"] if x["key"] == key)

    def mark(self, key, status, note=None):
        with self.lock:
            st = self.step(key)
            st["status"] = status
            if note is not None:
                st["note"] = note
            if status == "running":
                st["started"], st["ended"] = time.time(), None
            elif status in ("done", "skipped", "failed"):
                st["ended"] = time.time()
        self.save()

    # ------------------------------------------------------------------ 執行
    def start(self):
        self.stop_flag = False
        self.s["status"], self.s["error"] = "running", ""
        self.save()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag = True
        if self.job and self.job.status == "running":
            self.h["cancel"](self.job.id)

    def _run(self):
        try:
            while True:
                no = self.s["chapter"]
                self._run_chapter(no)
                self.s["done_chapters"].append(no)
                if no >= self.s["to"]:
                    self.s["status"] = "done"
                    self.s["message"] = "第%d章已定稿。" % no + ("全部章節都完成了。" if self.s["from"] != no else "")
                    break
                if self.s["mode"] == "stop":
                    self.s["status"] = "paused"
                    self.s["message"] = "第%d章已定稿。按「繼續下一章」寫第%d章。" % (no, no + 1)
                    self.s["chapter"] = no + 1
                    self.s["steps"] = new_steps()
                    self.s.pop("accepted_path", None)
                    break
                self.s["chapter"] = no + 1
                self.s["steps"] = new_steps()
                self.s.pop("accepted_path", None)
                self.save()
        except Stopped:
            self.s["status"] = "stopped"
            self.s["message"] = "已停止。可以從停下來的那一步繼續。"
        except StepFailed as e:
            self.s["status"] = "failed"
            self.s["error"] = str(e)
        except Exception as e:  # 程式錯誤也停在那一步，不讓執行緒默默死掉
            self.s["status"] = "failed"
            self.s["error"] = "程式錯誤：%s" % e
            for st in self.s["steps"]:
                if st["status"] == "running":
                    st["status"], st["note"] = "failed", str(e)
        self.job = None
        self.save()

    def _run_chapter(self, no):
        for key, _ in STEPS:
            st = self.step(key)
            if st["status"] in ("done", "skipped"):
                continue
            if self.stop_flag:
                raise Stopped()
            self.mark(key, "running", "")
            try:
                res = getattr(self, "_s_" + key)(no)
            except StepFailed as e:
                self.mark(key, "failed", str(e))
                raise StepFailed("第%d章「%s」失敗：%s" % (no, LABEL[key], e))
            except Stopped:
                self.mark(key, "pending", "已停止")
                raise
            if isinstance(res, tuple) and res and res[0] == "skip":
                self.mark(key, "skipped", res[1])
            else:
                self.mark(key, "done", res or "")

    def _wait(self, action, params):
        if self.stop_flag:
            raise Stopped()
        try:
            job = self.h["launch"](action, params)
        except Exception as e:
            raise StepFailed(getattr(e, "detail", None) or str(e))
        self.job = job
        with self.lock:
            for st in self.s["steps"]:
                if st["status"] == "running":
                    st["job"] = job.id
        self.save()
        while not (job.events and job.events[-1].get("kind") == "end"):
            time.sleep(0.4)
        if job.status == "cancelled" or self.stop_flag:
            raise Stopped()
        if job.status != "done":
            errs = [e.get("text") for e in job.events if e.get("kind") == "error" and e.get("text")]
            raise StepFailed(errs[-1] if errs else "任務沒有完成（%s）" % job.status)
        return job

    # ------------------------------------------------------------------ 各步驟
    def _cand(self, no):
        return project._scan_dir(os.path.join(self.d, "候選")).get(no)

    def _note(self):
        return AUTO_NOTE + (("\n作者對整個流程的要求：" + self.s["note"]) if self.s.get("note") else "")

    def _s_card(self, no):
        if context.card_text(self.d, no)[1]:
            return ("skip", "已有章綱")
        self._wait("chapter_cards", {"from": no, "to": no, "auto": True, "note": self._note()})
        if not context.card_text(self.d, no)[1]:
            raise StepFailed("AI 沒有寫出第%d章的章綱檔（大綱/章綱/第%03d章.md），請看面板上的回覆。" % (no, no))
        return "已寫好章綱"

    def _s_write(self, no):
        if self._cand(no):
            return ("skip", "已有候選稿，直接使用")
        self._wait("write", {"from": no, "to": no, "note": self._note()})
        if not self._cand(no):
            raise StepFailed("AI 沒有產生候選稿，請看面板上的回覆（可能在等你回答問題）。")
        return "候選稿：" + self._cand(no)

    def _s_goal(self, no):
        _, card = context.card_text(self.d, no)
        if not goals.freeze_goals(card):
            return ("skip", "章綱沒有可以核對的情節點")
        rec = goals.load(self.d, no)
        if rec and not rec.get("stale") and (rec.get("path") or "").startswith("候選"):
            return ("skip", "寫稿時已核對：%s" % _goal_brief(rec["items"]))
        self._wait("goal_check", {"chapter": no, "candidate": True})
        rec = goals.load(self.d, no)
        return _goal_brief(rec["items"]) if rec else "已核對"

    def _s_deslop(self, no):
        self._wait("deslop", {"chapter": no, "candidate": True})
        if not self._cand(no):
            raise StepFailed("去 AI 味之後找不到候選稿")
        return "已處理"

    def _s_review(self, no):
        self._wait("review_notes", {"chapter": no, "candidate": True})
        rv = revision.load_review(self.d, no)
        if not rv:
            raise StepFailed("沒有取得審查結果")
        cnt = {s: sum(1 for x in rv["items"] if x["severity"] == s) for s in revision.SEVERITIES}
        return "必須修 %d、建議修 %d、提醒 %d" % (cnt["必須修"], cnt["建議修"], cnt["提醒"])

    def _s_tick(self, no):
        rv = revision.load_review(self.d, no) or {"items": []}
        sev = set(self.s["severities"])
        ids = [x["id"] for x in rv["items"] if x["severity"] in sev]
        extra = ""
        rec = goals.load(self.d, no)
        if rec:
            unmet = [it for it in rec["items"] if it["status"] == "unmet"]
            if unmet:
                extra = "章綱核對發現這些情節點沒寫到，請補上：" + "；".join("%s %s" % (it["id"], it["text"]) for it in unmet)
        with self.lock:
            self.s["ticked"] = {"chapter": no, "ids": ids, "extra": extra}
        if not ids and not extra:
            self.mark("revise", "skipped", "沒有要修的意見")
            self.mark("apply", "skipped", "沒有修訂")
            return ("skip", "勾選等級（%s）沒有任何意見" % "、".join(self.s["severities"]) if self.s["severities"] else "沒有設定自動勾選的等級")
        return "勾選 %d 條%s" % (len(ids), "，另補章綱沒寫到的情節點" if extra else "")

    def _s_revise(self, no):
        t = self.s.get("ticked") or {}
        if t.get("chapter") != no:
            raise StepFailed("找不到勾選結果，請從「自動勾選意見」重新開始")
        revision.discard_revision(self.d, no)
        self._wait("revise_notes", {"chapter": no, "ids": t.get("ids") or [], "extra": t.get("extra") or ""})
        rec = revision.load_revision(self.d, no)
        if not rec:
            raise StepFailed("沒有產生修訂稿")
        return "%d 處段落變更" % rec["changes"]

    def _s_apply(self, no):
        try:
            r = revision.apply_revision(self.d, no, {}, self.h.get("checker"))
        except project.ProjectError as e:
            raise StepFailed(str(e))
        return "套用 %d 處" % r["used_new"]

    def _s_accept(self, no):
        if self._cand(no):
            if self.h["busy"]():
                raise StepFailed("還有其他任務在執行")
            try:
                path = project.accept_candidate(self.d, no)
            except project.ProjectError as e:
                raise StepFailed(str(e))
            with self.lock:
                self.s["accepted_path"] = path
            self.save()
        path = self.s.get("accepted_path") or context.chapter_text(self.d, no, ("正文",))[0]
        if not path:
            raise StepFailed("找不到第%d章的候選稿或正文" % no)
        self._wait("accept", {"chapter": no, "path": path})
        return "已移到 " + path + "，追蹤已回寫"


def _goal_brief(items):
    c = goals.summary(items)
    return "已寫到 %d、沒寫到 %d、無法判斷 %d" % (c["completed"], c["unmet"], c["unknown"] + c["unverified"])


# ---------------------------------------------------------------------------
# 管理（每本書最多一個流程）
# ---------------------------------------------------------------------------
class Manager:
    def __init__(self):
        self.pipes = {}
        self.lock = threading.Lock()

    def get(self, book_id):
        return self.pipes.get(book_id)

    def active(self, book_id):
        p = self.pipes.get(book_id)
        return bool(p and p.s["status"] == "running")

    def put(self, pipe):
        with self.lock:
            old = self.pipes.get(pipe.book_id)
            if old and old.s["status"] == "running":
                raise PipelineError("這本書已經有整章自動流程在執行")
            self.pipes[pipe.book_id] = pipe
        return pipe

    def restore(self, book_id, book_dir, hooks):
        """伺服器重開後，從 .studio/流程/目前.json 讀回（執行中的視為已停止）。"""
        p = self.pipes.get(book_id)
        if p:
            return p
        st = load_state(book_dir)
        if not st:
            return None
        if st.get("status") == "running":
            st["status"] = "stopped"
            st["message"] = "工作台重新啟動過，流程已停止。可以從停下來的那一步繼續。"
            for x in st["steps"]:
                if x["status"] == "running":
                    x["status"] = "pending"
        p = Pipeline(book_id, book_dir, st, hooks)
        self.pipes[book_id] = p
        return p
