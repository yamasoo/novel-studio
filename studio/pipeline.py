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

from . import context, goals, lang as lang_mod, project, prompts, revision, style_loop, tracking, volume

STEPS = [
    ("card", "章綱"),
    ("write", "寫章節（候選稿）"),
    ("goal", "章綱核對"),
    ("deslop", "去 AI 味"),
    ("style", "文風檢查"),
    ("review", "審查意見"),
    ("tick", "自動勾選意見"),
    ("revise", "依勾選意見修訂"),
    ("apply", "全部套用修訂"),
    ("accept", "定稿並回寫追蹤"),
]
LABEL = dict(STEPS)
# 會呼叫 AI 的步驟（可以各自指定執行者），以及面板上對應的動作
AI_STEPS = ["card", "write", "goal", "deslop", "review", "revise", "accept"]
STEP_ACTION = {"card": "chapter_cards", "write": "write", "goal": "goal_check", "deslop": "deslop",
               "review": "review_notes", "revise": "revise_notes", "accept": "accept"}


NOTE_STEPS = ("card", "write", "deslop", "review", "revise")   # 重跑時可以補一句要求的步驟


def clean_step_providers(m, valid_ids):
    """{步驟: 執行者 id}；空白或不存在的執行者＝跟流程的執行者。"""
    out = {}
    for k, v in (m or {}).items():
        if k in AI_STEPS and v and v in valid_ids:
            out[k] = v
    return out
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


def ensure_steps(state):
    """舊的流程狀態可能沒有新加的步驟（例如後來的「文風檢查」）：補上去，不要讓它壞掉。"""
    steps = state.setdefault("steps", [])
    have = {s.get("key") for s in steps}
    order = [k for k, _ in STEPS]
    for k, label in STEPS:
        if k in have:
            continue
        steps.append({"key": k, "label": label, "status": "pending", "note": "", "job": None,
                      "started": None, "ended": None})
    steps.sort(key=lambda s: order.index(s["key"]) if s.get("key") in order else len(order))
    return state


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
    def create(cls, book_id, book_dir, hooks, start, end, mode, severities, provider, note="", step_providers=None):
        # 卷先行：有卷綱的書，只准寫在正式卷綱的章節範圍內。
        # 沒有卷綱的舊書不擋（不然整批書突然不能寫）；缺的是「使用者還沒建立卷綱」的情況。
        if volume.has_volumes(book_dir):
            missing = volume.cover(book_dir, start, end)
            if missing:
                raise PipelineError(
                    "%s不在任何卷綱的章節範圍內；先補對應的 大綱/卷綱_第N卷.md 再開流程"
                    "（見 docs/卷先行.md）。" % volume.brief(missing))
            # 卷先行（第二段）：章綱要先排好，不然還是一章一章臨場接
            no_card = [n for n in range(int(start), int(end) + 1) if not context.card_text(book_dir, n)[1]]
            if no_card:
                raise PipelineError(
                    "%s還沒有章綱；先到大綱頁按「排這一卷的章綱」把整卷排好，再開整章自動流程。"
                    % volume.brief(no_card))
        state = {"id": uuid.uuid4().hex[:10], "book": book_id, "from": int(start), "to": int(end),
                 "mode": mode if mode in ("stop", "continue") else "stop",
                 "severities": [s for s in (severities or DEFAULT_SEVERITIES) if s in revision.SEVERITIES],
                 "provider": provider, "note": (note or "").strip(),
                 "step_providers": dict(step_providers or {}),   # 開始時記下的分配，中途繼續也用同一套
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
        from . import autopilot
        prompts.set_lang(lang_mod.book_lang(self.d))   # 這條執行緒組的提示詞都用這本書的語言
        try:
            while True:
                no = self.s["chapter"]
                self._run_chapter(no)
                self.s["done_chapters"].append(no)
                # 自動駕駛的檢查點：每 K 章停下來驗一次必須修與文風，不及格就不往下寫
                every = int(self.h.get("autopilot_every") or 0)
                if every and self.s["mode"] != "stop" and len(self.s["done_chapters"]) % every == 0:
                    res = autopilot.checkpoint(self.d, no, every, checker=self.h.get("checker"))
                    self.s.setdefault("checkpoints", []).append(
                        {"upto": no, "ok": res["ok"], "stats": res["stats"], "reasons": res["reasons"],
                         "usage": dict(self.s.get("usage") or {})})
                    cost = autopilot.cost_line(self.s.get("usage"))
                    if not res["ok"]:
                        self.s["status"] = "paused"
                        self.s["message"] = (autopilot.summary(res)
                                             + ("\n" + cost if cost else "")
                                             + "\n\n（已寫到第%d章；處理完再按「繼續」就會接著寫。）" % no)
                        self.s["chapter"] = no + 1
                        self.s["steps"] = new_steps()
                        self.s.pop("accepted_path", None)
                        break
                if no >= self.s["to"]:
                    self.s["status"] = "done"
                    cost = autopilot.cost_line(self.s.get("usage"))
                    self.s["message"] = ("第%d章已定稿。" % no
                                         + ("全部章節都完成了。" if self.s["from"] != no else "")
                                         + (cost if cost else ""))
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
            self.cur = key
            self._snapshot(no, key)
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

    def provider_for(self, key):
        return (self.s.get("step_providers") or {}).get(key) or self.s["provider"]

    def _wait(self, action, params):
        if self.stop_flag:
            raise Stopped()
        cur = getattr(self, "cur", None)
        pid = self.provider_for(cur)
        if cur:
            with self.lock:
                self.step(cur)["provider"] = pid
        try:
            job = self.h["launch"](action, params, pid)
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
        self._add_usage(job)
        return job

    def _add_usage(self, job):
        """把這一輪任務的 token 與費用累加到流程狀態（檢查點與 UI 都用得到）。"""
        with self.lock:
            u = self.s.setdefault("usage", {"prompt_tokens": 0, "completion_tokens": 0,
                                            "cost": 0.0, "jobs": 0})
            u["jobs"] = int(u.get("jobs") or 0) + 1
            for e in reversed(job.events or []):
                if e.get("kind") == "result":
                    usage = e.get("usage") or {}
                    u["prompt_tokens"] = int(u.get("prompt_tokens") or 0) + int(usage.get("prompt_tokens") or 0)
                    u["completion_tokens"] = (int(u.get("completion_tokens") or 0)
                                              + int(usage.get("completion_tokens") or 0))
                    u["cost"] = round(float(u.get("cost") or 0) + float(e.get("cost") or 0), 4)
                    break

    # ------------------------------------------------------------------ 各步驟
    def _cand(self, no):
        return project._scan_dir(os.path.join(self.d, "候選")).get(no)

    def _rerun_note(self, key):
        r = self.s.get("rerun_note") or {}
        return r.get("text", "") if r.get("step") == key else ""

    def _note(self, key=None):
        n = AUTO_NOTE + (("\n作者對整個流程的要求：" + self.s["note"]) if self.s.get("note") else "")
        rr = self._rerun_note(key or getattr(self, "cur", None))
        return n + (("\n作者這次重跑的要求：" + rr) if rr else "")

    # ------------------------------------------------------------------ 快照與退回重跑
    def _snap_dir(self, no):
        return os.path.join(self.d, ".studio", "流程", "快照", "第%03d章" % no)

    def _snapshot(self, no, key):
        """這一步開始前的候選稿（與章綱是否存在），給「從這裡重跑」還原用。"""
        if key == "accept" and self.s.get("accepted_path"):
            return
        os.makedirs(self._snap_dir(no), exist_ok=True)
        name = self._cand(no)
        text = project.read_text(os.path.join(self.d, "候選", name)) if name else ""
        rec = {"step": key, "candidate": name or "", "text": text, "card": bool(context.card_text(self.d, no)[1]),
               "time": time.time()}
        with open(os.path.join(self._snap_dir(no), key + ".json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)

    def load_snapshot(self, no, key):
        p = os.path.join(self._snap_dir(no), key + ".json")
        if not os.path.isfile(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def _shelve(self, path, tag):
        """把檔案移到 .studio/備份/（不直接刪）。"""
        if path and os.path.isfile(path):
            tracking.backup(self.d, path, tag)
            os.remove(path)

    def can_rewind(self, key):
        """回傳 (可以嗎, 原因)。"""
        keys = [k for k, _ in STEPS]
        if key not in keys:
            return False, "沒有這個步驟"
        if self.s["status"] in ("done", "paused") or self.s.get("accepted_path") or self.step("accept")["status"] == "done":
            return False, "這一章已經定稿（追蹤也回寫了），不能退回；請用「寫章節（候選稿）」重寫"
        if self.s["status"] not in ("failed", "stopped"):
            return False, "流程要先停止（或停在失敗的步驟）才能退回"
        if key == "card":
            if self.step("card")["status"] == "skipped":
                return False, "章綱是原本就有的（不是流程寫的），要重寫請到章綱頁"
            return True, ""
        if key == "write":
            return True, ""
        st = self.step(key)
        if st["status"] == "pending" and not any(self.step(k)["status"] in ("done", "skipped", "failed")
                                                 for k in keys[keys.index(key):]):
            return False, "這一步還沒跑過，按「從這一步繼續」就好"
        if not self.load_snapshot(self.s["chapter"], key):
            return False, "沒有這一步開始前的快照（流程在這個功能加入前就開始了），只能從「章綱」或「寫章節」重跑"
        return True, ""

    def rewind(self, key, note=""):
        """退回到某一步開始前的狀態：候選稿還原、之後各步的紀錄先備份再清掉、步驟改回未執行。"""
        ok, why = self.can_rewind(key)
        if not ok:
            raise PipelineError(why)
        no = self.s["chapter"]
        keys = [k for k, _ in STEPS]
        idx = keys.index(key)
        later = set(keys[idx:])
        cand = self._cand(no)
        cand_path = os.path.join(self.d, "候選", cand) if cand else ""
        if key == "card":
            card_path, _ = context.card_text(self.d, no)
            self._shelve(os.path.join(self.d, card_path) if card_path else "", "重跑前章綱")
            self._shelve(cand_path, "重跑前候選")
        elif key == "write":
            self._shelve(cand_path, "重跑前候選")
        else:
            snap = self.load_snapshot(no, key)
            self._shelve(cand_path, "重跑前候選")
            if snap.get("candidate"):
                os.makedirs(os.path.join(self.d, "候選"), exist_ok=True)
                with open(os.path.join(self.d, "候選", snap["candidate"]), "w", encoding="utf-8", newline="\n") as f:
                    f.write(snap["text"])
        # 之後各步的紀錄
        recs = {"goal": ("核對", "第%03d章.json" % no), "review": ("審查", "第%03d章.json" % no)}
        for k, (sub, fn) in recs.items():
            if k in later:
                p = os.path.join(self.d, ".studio", sub, fn)
                if os.path.isfile(p):
                    bak = os.path.join(self.d, ".studio", "備份")
                    os.makedirs(bak, exist_ok=True)
                    os.replace(p, os.path.join(bak, "重跑前%s_%s.%d.json" % (sub, fn[:-5], int(time.time()))))
        if "revise" in later:
            revision.discard_revision(self.d, no)
        if "tick" in later:
            self.s.pop("ticked", None)
        with self.lock:
            for st in self.s["steps"]:
                if st["key"] in later:
                    st.update(status="pending", note="", job=None, started=None, ended=None)
                    st.pop("provider", None)
            self.s["error"] = ""
            self.s["rerun_note"] = {"step": key, "text": (note or "").strip()} if key in NOTE_STEPS and (note or "").strip() else {}
            self.s["message"] = "從「%s」重跑" % LABEL[key]
        self.save()

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
        revision.discard_revision(self.d, no)   # 去 AI 味會產生一份修訂，流程裡直接全部套用
        self._wait("deslop", {"chapter": no, "candidate": True, "note": self._rerun_note("deslop"), "auto_apply": True})
        if not self._cand(no):
            raise StepFailed("去 AI 味之後找不到候選稿")
        return "已處理"

    def _s_style(self, no):
        """文風檢查（本機計算，不呼叫模型；可在設定關掉）。寫稿／去 AI 味那一步已經做過一次
        「偏離就重寫」，這裡是把最終候選稿的 13 指標記錄下來，讓作者看得到數字。"""
        if not self.h.get("style_check", lambda: True)():
            return ("skip", "文風檢查已關閉")
        rel, text = context.chapter_text(self.d, no, ("候選", "正文"))
        if not text:
            return ("skip", "還沒有稿子")
        ev = style_loop.evaluate(self.d, text)
        if not ev.get("rows"):
            return ("skip", style_loop.summary(ev))
        line = style_loop.summary(ev)
        if ev["verdict"] == "off":
            line += "（超過門檻：可在章節頁看 13 指標的目標／實際）"
        return line

    def _s_review(self, no):
        self._wait("review_notes", {"chapter": no, "candidate": True, "note": self._rerun_note("review")})
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
        if not ids and not extra and not self._rerun_note("revise"):
            self.mark("revise", "skipped", "沒有要修的意見")
            self.mark("apply", "skipped", "沒有修訂")
            return ("skip", "勾選等級（%s）沒有任何意見" % "、".join(self.s["severities"]) if self.s["severities"] else "沒有設定自動勾選的等級")
        return "勾選 %d 條%s" % (len(ids), "，另補章綱沒寫到的情節點" if extra else "")

    def _s_revise(self, no):
        t = self.s.get("ticked") or {}
        if t.get("chapter") != no:
            raise StepFailed("找不到勾選結果，請從「自動勾選意見」重新開始")
        revision.discard_revision(self.d, no)
        extra = t.get("extra") or ""
        rr = self._rerun_note("revise")
        if rr and rr not in extra:
            extra = (extra + "\n" if extra else "") + "作者這次重跑的要求：" + rr
        self._wait("revise_notes", {"chapter": no, "ids": t.get("ids") or [], "extra": extra})
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
        p = Pipeline(book_id, book_dir, ensure_steps(st), hooks)
        self.pipes[book_id] = p
        return p
