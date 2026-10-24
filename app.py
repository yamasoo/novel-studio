# -*- coding: utf-8 -*-
"""
小說工作台 Novel Studio
本機網頁介面：管理小說專案，並透過 Claude Code 呼叫 novel-* skills。

啟動：python app.py   （或雙擊 start.bat）
預設網址：http://127.0.0.1:8765
"""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from urllib.parse import quote
from fastapi.staticfiles import StaticFiles
import uvicorn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from studio import actions, context, export, goals, native, project, providers, recovery, revision, runner as runner_mod  # noqa: E402

VERSION = "1.1.0"
PLUGIN_DIR = os.path.join(HERE, "plugin")
CONFIG_PATH = os.path.join(HERE, "config.json")
DEFAULT_CONFIG = {
    "library": os.path.join(os.path.expanduser("~"), "Documents", "小說"),
    "claude_cmd": "",
    "model": "",
    "permission_mode": "acceptEdits",
    "allowed_tools": ["Skill", "Bash(python:*)", "Bash(python3:*)", "Bash(py:*)", "Bash(git:*)"],
    # 額外允許 Claude Code 讀取的資料夾（內建 skills 會自動加入，不用填）
    "add_dirs": [],
    "providers": providers.DEFAULT_PROVIDERS,
    "default_provider": "claude_code",
    "reconcile_before_write": True,     # 非 Claude 模型寫稿前先做定稿對帳
    "goal_check_after_write": True,     # 非 Claude 模型寫完候選稿後自動核對章綱
    "stale_foreshadow": 10,
    "stale_character": 15,
    "host": "127.0.0.1",
    "port": 8765,
}

_cfg_lock = threading.Lock()


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    # 舊版設定：移除指向 ~/.claude/skills 的額外資料夾（skills 已內建在工作台）
    cfg["add_dirs"] = [d for d in cfg.get("add_dirs") or [] if not os.path.normpath(d).endswith(os.path.join(".claude", "skills"))]
    for p in cfg.get("providers") or []:
        # 舊版預設 8192 對推理模型太小（思考過程也算輸出）
        if p.get("id") == "deepseek" and int(p.get("max_output") or 0) == 8192:
            p["max_output"] = 32768
        if p.get("type") == "openai" and not p.get("reasoning"):
            p["reasoning"] = dict(providers.DEFAULT_REASONING, adapter="deepseek" if p.get("id") == "deepseek" else "none")
    have = {p.get("id") for p in cfg.get("providers") or []}
    cfg["providers"] = list(cfg.get("providers") or []) + [dict(p) for p in providers.DEFAULT_PROVIDERS if p["id"] not in have]
    return cfg


def save_config(cfg):
    with _cfg_lock:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)


CONFIG = load_config()
# 檢查工具（內建 novel-deslop skill 的 check_text.py）
_spec = importlib.util.spec_from_file_location(
    "check_text", os.path.join(PLUGIN_DIR, "skills", "novel-deslop", "scripts", "check_text.py"))
check_text = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_text)

RUNNER = runner_mod.Runner(lambda: CONFIG, HERE, PLUGIN_DIR, check_text)


def get_provider(pid=None):
    pid = pid or CONFIG.get("default_provider") or "claude_code"
    for p in CONFIG.get("providers") or []:
        if p.get("id") == pid:
            return p
    raise HTTPException(400, "找不到執行者：%s" % pid)

app = FastAPI(title="小說工作台")


# ---------------------------------------------------------------------------
# 共用
# ---------------------------------------------------------------------------
def book_dir(book_id):
    lib = CONFIG.get("library")
    if not lib or not os.path.isdir(lib):
        raise HTTPException(400, "書庫資料夾不存在，請先在設定中指定。")
    d = os.path.normpath(os.path.join(lib, book_id))
    if os.path.dirname(d) != os.path.normpath(lib) or not os.path.isdir(d):
        raise HTTPException(404, "找不到這本書")
    return d


def wrap(fn):
    try:
        return fn()
    except project.ProjectError as e:
        raise HTTPException(400, str(e))


@app.exception_handler(HTTPException)
async def http_err(request, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
@app.get("/api/config")
def get_config():
    exe = runner_mod.find_claude(CONFIG.get("claude_cmd"))
    return {"config": CONFIG, "claude_found": exe, "version": VERSION,
            "port": int(CONFIG.get("port", 8765)), "running_port": RUNNING_PORT, "can_restart": SERVER is not None,
            "library_exists": os.path.isdir(CONFIG.get("library") or ""),
            "key_status": {p["id"]: providers.key_status(HERE, p) for p in CONFIG.get("providers") or []}}


@app.post("/api/config")
async def set_config(req: Request):
    body = await req.json()
    for k in ("library", "claude_cmd", "model", "permission_mode", "allowed_tools", "add_dirs",
              "stale_foreshadow", "stale_character", "default_provider",
              "reconcile_before_write", "goal_check_after_write"):
        if k in body:
            CONFIG[k] = body[k]
    if "port" in body:
        try:
            port = int(body["port"])
        except (TypeError, ValueError):
            raise HTTPException(400, "連接埠要是數字")
        if not 1024 <= port <= 65535:
            raise HTTPException(400, "連接埠要在 1024～65535 之間")
        CONFIG["port"] = port
    if body.get("create_library") and CONFIG.get("library"):
        os.makedirs(CONFIG["library"], exist_ok=True)
    save_config(CONFIG)
    return get_config()


@app.post("/api/providers")
async def set_providers(req: Request):
    body = await req.json()
    keep = [p for p in CONFIG.get("providers") or [] if p.get("type") == "claude_code"]
    seen = {p["id"] for p in keep}
    for p in body.get("providers") or []:
        pid = str(p.get("id") or "").strip()
        if not pid or pid in seen or p.get("type") == "claude_code":
            continue
        clean = {"id": pid, "type": "openai", "name": str(p.get("name") or pid),
                 "base_url": str(p.get("base_url") or "").strip(), "model": str(p.get("model") or "").strip(),
                 "key_env": str(p.get("key_env") or "").strip()}
        for k, f, d in (("context_tokens", int, 32768), ("max_output", int, 4096), ("temperature", float, 0.8),
                        ("price_in", float, 0.0), ("price_out", float, 0.0)):
            try:
                clean[k] = f(p.get(k)) if p.get(k) not in (None, "") else d
            except (TypeError, ValueError):
                clean[k] = d
        clean["json_mode"] = bool(p.get("json_mode", True))
        ex = p.get("extra") or {}
        if isinstance(ex, str):
            try:
                ex = json.loads(ex) if ex.strip() else {}
            except ValueError:
                raise HTTPException(400, "%s 的「額外參數」不是合法 JSON" % clean["name"])
        clean["extra"] = ex if isinstance(ex, dict) else {}
        r = p.get("reasoning") or {}
        clean["reasoning"] = {"adapter": r.get("adapter") if r.get("adapter") in providers.ADAPTERS else "none"}
        for st in providers.STAGES:
            v = r.get(st)
            clean["reasoning"][st] = v if v in providers.EFFORTS else providers.DEFAULT_REASONING[st]
        keep.append(clean)
        seen.add(pid)
    CONFIG["providers"] = keep
    for pid, key in (body.get("keys") or {}).items():
        if key is not None:
            providers.save_secret(HERE, pid, key.strip())
    save_config(CONFIG)
    return get_config()


@app.post("/api/providers/{pid}/models")
def provider_models(pid: str):
    prov = get_provider(pid)
    if prov.get("type") == "claude_code":
        return {"models": ["sonnet", "opus", "haiku"]}
    try:
        return {"models": providers.list_models(HERE, prov)}
    except providers.ProviderError as e:
        raise HTTPException(400, str(e))


@app.get("/api/reasoning")
def reasoning_meta():
    return {"stages": providers.STAGES, "efforts": providers.EFFORTS, "adapters": providers.ADAPTERS}


@app.get("/api/books/{book_id}/goals/{no}")
def goal_result(book_id: str, no: int):
    d = book_dir(book_id)
    _, card = context.card_text(d, no)
    return {"goals": goals.freeze_goals(card), "result": goals.load(d, no)}


def claude_goal_job(book_id, d, prov, params):
    """用 Claude Code 核對章綱：Claude 只讀檔並回傳 JSON，驗證與存檔由工作台做。"""
    no = int(params.get("chapter"))
    _, card = context.card_text(d, no)
    gl = goals.freeze_goals(card)
    rel = context.chapter_text(d, no, ("候選",))[0] if params.get("candidate") else goals.target(d, no, True)[0]
    if not gl or not rel:
        raise HTTPException(400, "第%d章沒有章綱情節點或沒有正文，無法核對。" % no)
    prompt = (goals.build_prompt(no, gl, "（請用 Read 讀取 %s，不要修改任何檔案）" % rel) +
              "\n最後一則回覆只輸出 JSON，不要加說明或程式碼圍欄。")
    job = runner_mod.Job(book_id, d, "核對第%d章章綱" % no, prompt, provider=prov,
                         meta={"action": "goal_check", "params": params})

    def after(j):
        try:
            data = providers.parse_json(j.result or "")
        except providers.ProviderError as e:
            raise RuntimeError("無法解析 Claude 回傳的核對結果：%s" % e)
        text = project.read_text(os.path.join(d, rel))
        items = goals.verify(gl, data, text)
        goals.save(d, no, rel, text, items, prov.get("id"))
        j.result = goals.report_md(no, items)
        j.emit("result", text=j.result)
    job.after = after
    return job


@app.get("/api/books/{book_id}/review/{no}")
def review_result(book_id: str, no: int):
    return {"review": revision.load_review(book_dir(book_id), no)}


@app.get("/api/books/{book_id}/revision/{no}")
def revision_result(book_id: str, no: int):
    rec = revision.load_revision(book_dir(book_id), no)
    if rec:
        rec.pop("base_text", None)
        rec.pop("new_text", None)
    return {"revision": rec}


@app.post("/api/books/{book_id}/revision/{no}/apply")
async def revision_apply(book_id: str, no: int, req: Request):
    d = book_dir(book_id)
    if RUNNER.running_for(book_id):
        raise HTTPException(409, "還有任務在執行，請稍後再套用。")
    body = await req.json()
    return wrap(lambda: revision.apply_revision(d, no, body.get("choices") or {}, check_text))


@app.post("/api/books/{book_id}/revision/{no}/discard")
def revision_discard(book_id: str, no: int):
    revision.discard_revision(book_dir(book_id), no)
    return {"ok": True}


@app.get("/api/books/{book_id}/recoveries")
def recoveries(book_id: str):
    return recovery.list_all(book_dir(book_id))


@app.get("/api/books/{book_id}/recoveries/{rid}")
def recovery_get(book_id: str, rid: str):
    return wrap(lambda: recovery.load(book_dir(book_id), rid))


@app.post("/api/books/{book_id}/recoveries/{rid}/discard")
def recovery_discard(book_id: str, rid: str):
    wrap(lambda: recovery.discard(book_dir(book_id), rid))
    return {"ok": True}


@app.post("/api/books/{book_id}/recoveries/{rid}/candidate")
def recovery_to_candidate(book_id: str, rid: str):
    """直接把恢復稿存成候選稿（不續寫）。"""
    d = book_dir(book_id)
    rec = wrap(lambda: recovery.load(d, rid))
    if not rec.get("chapter"):
        raise HTTPException(400, "這份恢復稿不屬於任何章節")
    no = int(rec["chapter"])
    title, text, _ = native._split_output(rec["text"], no, native._card_title(d, no))
    cand = os.path.join(d, "候選")
    os.makedirs(cand, exist_ok=True)
    old = project._scan_dir(cand).get(no)
    if old:
        native.tracking.backup(d, os.path.join(cand, old), "候選")
        os.remove(os.path.join(cand, old))
    name = "第%03d章_%s.md" % (no, title)
    fixed, _ = check_text.fix_punct(text)
    with open(os.path.join(cand, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(fixed)
    recovery.discard(d, rid)
    return {"path": "候選/" + name, "chapter": no}


def claude_review_job(book_id, d, prov, params):
    no = int(params.get("chapter"))
    rel = params.get("path") or (context.chapter_text(d, no, ("候選",))[0] if params.get("candidate") else goals.target(d, no, True)[0])
    if not rel:
        raise HTTPException(400, "第%d章沒有可以審查的稿子" % no)
    prompt = ("請使用 novel-review skill 審查第%d章，稿子在 %s（用 Read 讀取，也讀相關的章綱、狀態卡、角色狀態、時間線）。"
              "不要修改任何檔案。\n%s\n最後一則回覆只輸出 JSON，不要加說明或程式碼圍欄。" % (no, rel, revision.REVIEW_SCHEMA))
    job = runner_mod.Job(book_id, d, "審查第%d章" % no, prompt, provider=prov, meta={"action": "review_notes", "params": params})

    def after(j):
        try:
            data = providers.parse_json(j.result or "")
        except providers.ProviderError as e:
            raise RuntimeError("無法解析 Claude 回傳的審查結果：%s" % e)
        text = project.read_text(os.path.join(d, rel))
        rec = revision.save_review(d, no, rel, text, revision.normalize_review(data, text), prov.get("id"))
        j.result = revision.review_md(no, rec)
        j.emit("result", text=j.result)
    job.after = after
    return job


def claude_revise_job(book_id, d, prov, params):
    no = int(params.get("chapter"))
    rv = revision.load_review(d, no)
    notes = revision.notes_text(rv, params.get("ids") or [], params.get("extra") or "")
    if not notes:
        raise HTTPException(400, "請至少勾選一條審查意見，或寫下你自己的修改意見。")
    rel = (rv or {}).get("path") or goals.target(d, no, True)[0]
    if not rel:
        raise HTTPException(400, "第%d章沒有可以修訂的稿子" % no)
    draft = ".studio/修訂/第%03d章.draft.md" % no
    prompt = ("請依下面的修改意見修訂第%d章（原稿在 %s，用 Read 讀取）。\n【要處理的修改意見】\n%s\n\n"
              "規則：只修改這些意見涉及的地方，其他段落一字不改，維持原本的空行分段（作者會逐段比對新舊版本）。"
              "**不要修改原稿**；把修訂後的完整章節（含「# 第%d章 章名」標題）寫到 %s。最後用白話逐條說明每個意見怎麼處理。"
              % (no, rel, notes, no, draft))
    job = runner_mod.Job(book_id, d, "修訂第%d章" % no, prompt, provider=prov, meta={"action": "revise_notes", "params": params})
    base_text = project.read_text(os.path.join(d, rel))

    def after(j):
        p = os.path.join(d, draft)
        if not os.path.isfile(p):
            raise RuntimeError("Claude 沒有產生修訂稿（%s）。" % draft)
        new_text = project.read_text(p)
        os.remove(p)
        title = native._split_output(new_text, no, native._card_title(d, no))[0]
        revision.save_revision(d, no, rel, base_text, title, new_text, notes, j.result, prov.get("id"))
        n = sum(1 for b in revision.diff_blocks(base_text, new_text) if b["type"] == "change")
        j.result = "**第%d章修訂好了**：共 %d 處段落變更，原稿沒有被改動。請到章節頁逐段確認。\n\n%s" % (no, n, j.result or "")
        j.emit("result", text=j.result)
    job.after = after
    return job


def claude_recover_job(book_id, d, prov, params):
    rec = wrap(lambda: recovery.load(d, params.get("id")))
    if not rec.get("chapter"):
        raise HTTPException(400, "這份恢復稿不屬於任何章節")
    no = int(rec["chapter"])
    prompt = ("第%d章之前寫到一半中斷了，已寫內容在 .studio/恢復稿/%s.json 的 text 欄位（用 Read 讀取）。"
              "請使用 novel-write skill，從中斷處接著寫完，不要重複已寫內容；把完整章節（已寫部分＋續寫）寫進 候選/第%03d章_章名.md。\n%s"
              % (no, rec["id"], no, actions.CANDIDATE_RULE))
    job = runner_mod.Job(book_id, d, "續寫第%d章" % no, prompt, provider=prov, meta={"action": "recover_continue", "params": params})
    job.after = lambda j: recovery.discard(d, rec["id"]) if project._scan_dir(os.path.join(d, "候選")).get(no) else None
    return job


@app.get("/api/books/{book_id}/export")
def export_meta(book_id: str):
    return export.meta(book_dir(book_id))


@app.post("/api/books/{book_id}/export")
async def export_run(book_id: str, req: Request):
    d = book_dir(book_id)
    opts = await req.json()
    return wrap(lambda: export.export(d, opts))


@app.get("/api/books/{book_id}/exports/{name}")
def export_download(book_id: str, name: str):
    p = wrap(lambda: export.export_path(book_dir(book_id), name))
    mt = "application/epub+zip" if name.endswith(".epub") else "text/plain; charset=utf-8"
    return FileResponse(p, media_type=mt,
                        headers={"Content-Disposition": "attachment; filename=\"novel%s\"; filename*=UTF-8''%s"
                                 % (os.path.splitext(name)[1], quote(name))})


@app.delete("/api/books/{book_id}/exports/{name}")
def export_delete(book_id: str, name: str):
    wrap(lambda: export.delete_export(book_dir(book_id), name))
    return {"ok": True}


# ---------------------------------------------------------------------------
# 重新啟動
# ---------------------------------------------------------------------------
SERVER = None          # 由 serve() 設定的 uvicorn.Server
RUNNING_PORT = None
RESTART_CODE = 75
_restart = {"requested": False}


@app.post("/api/restart")
def restart_server():
    if SERVER is None:
        raise HTTPException(400, "這個執行方式無法自動重新啟動，請手動關閉後再開。")
    running = [j for j in RUNNER.jobs.values() if j.status == "running"]
    if running:
        raise HTTPException(409, "還有 %d 個任務在執行（%s），請等它結束或先停止。" % (
            len(running), "、".join(j.title for j in running[:3])))
    _restart["requested"] = True

    def stop():
        time.sleep(0.4)
        SERVER.should_exit = True
        time.sleep(6)
        SERVER.force_exit = True   # 有連線遲遲不關時強制結束
    threading.Thread(target=stop, daemon=True).start()
    host = CONFIG.get("host", "127.0.0.1")
    port = int(CONFIG.get("port", 8765))
    return {"ok": True, "url": "http://%s:%d/" % ("127.0.0.1" if host in ("0.0.0.0", "") else host, port)}


@app.get("/api/actions")
def get_actions():
    cat = actions.catalog()
    for a in cat:
        a["native"] = a["id"] in native.NATIVE_ACTIONS
    return cat


# ---------------------------------------------------------------------------
# 書架
# ---------------------------------------------------------------------------
@app.get("/api/books")
def books():
    lib = CONFIG.get("library")
    return {"library": lib, "exists": os.path.isdir(lib or ""), "books": project.list_books(lib)}


@app.post("/api/books")
async def new_book(req: Request):
    body = await req.json()
    lib = CONFIG.get("library")
    if not lib:
        raise HTTPException(400, "請先設定書庫資料夾")
    os.makedirs(lib, exist_ok=True)
    d = wrap(lambda: project.create_book(lib, body.get("name", "")))
    name = os.path.basename(d)
    job = None
    if body.get("start_setup", True):
        params = {"idea": body.get("idea", "")}
        title, prompt = actions.build("setup_new", params, name)
        job = RUNNER.start(runner_mod.Job(name, d, title, prompt, meta={"action": "setup_new", "params": params},
                                          provider=get_provider(body.get("provider"))))
    return {"id": name, "job": job.to_dict() if job else None}


@app.post("/api/demo")
def add_demo():
    import shutil
    lib = CONFIG.get("library")
    if not lib:
        raise HTTPException(400, "請先設定書庫資料夾")
    os.makedirs(lib, exist_ok=True)
    src = os.path.join(HERE, "demo", "退婚之後")
    dst = os.path.join(lib, "退婚之後（示範）")
    if os.path.exists(dst):
        raise HTTPException(400, "示範書已經在書架上了")
    shutil.copytree(src, dst)
    return {"id": os.path.basename(dst)}


@app.get("/api/books/{book_id}/overview")
def book_overview(book_id: str):
    d = book_dir(book_id)
    ov = project.overview(d, int(CONFIG.get("stale_foreshadow", 10)), int(CONFIG.get("stale_character", 15)))
    ov["is_book"] = project.is_book(d)
    recs = recovery.list_all(d)
    if recs:
        ov["alerts"].insert(0, {"level": "warn", "kind": "恢復稿",
                                "text": "有 %d 份中斷的輸出被保留下來，可以接著寫或捨棄。" % len(recs), "action": "recoveries"})
    rdir = os.path.join(d, ".studio", "修訂")
    if os.path.isdir(rdir):
        for f in sorted(os.listdir(rdir)):
            m = __import__("re").match(r"第0*(\d+)章\.json$", f)
            if m:
                ov["alerts"].insert(0, {"level": "info", "kind": "待確認修訂",
                                        "text": "第%s章有修訂等你逐段確認。" % m.group(1), "chapter": int(m.group(1)), "tab": "revision"})
    run = RUNNER.running_for(book_id)
    ov["running"] = run.to_dict() if run else None
    return ov


@app.get("/api/books/{book_id}/chapters")
def book_chapters(book_id: str):
    return project.scan_chapters(book_dir(book_id))


@app.get("/api/books/{book_id}/bible")
def book_bible(book_id: str):
    return project.bible(book_dir(book_id))


@app.get("/api/books/{book_id}/outline")
def book_outline(book_id: str):
    return project.outline_files(book_dir(book_id))


@app.get("/api/books/{book_id}/tracking")
def book_tracking(book_id: str):
    d = book_dir(book_id)
    cs_dir = os.path.join(d, "追蹤", "角色狀態")
    chars = project.list_entries(d, "追蹤/角色狀態") if os.path.isdir(cs_dir) else []
    for c in chars:
        fm, _ = project.split_frontmatter(project.read_text(os.path.join(d, c["file"])))
        c["last"] = fm.get("最後登場")
        c["updated_to"] = fm.get("更新至")
    ov = project.overview(d)
    return {
        "foreshadow": project.read_table(d, "追蹤/伏筆.md"),
        "timeline": project.read_table(d, "追蹤/時間線.md"),
        "glossary": project.read_table(d, "設定/名詞表.md"),
        "characters": chars,
        "latest": ov["latest"],
        "stale_foreshadow": int(CONFIG.get("stale_foreshadow", 10)),
    }


# ---------------------------------------------------------------------------
# 檔案
# ---------------------------------------------------------------------------
@app.get("/api/books/{book_id}/file")
def read_file(book_id: str, path: str):
    d = book_dir(book_id)
    p = wrap(lambda: project.safe_path(d, path))
    if not os.path.isfile(p):
        raise HTTPException(404, "檔案不存在")
    text = project.read_text(p)
    fm, body = project.split_frontmatter(text)
    return {"path": project.rel_of(d, p), "text": text, "frontmatter": fm,
            "mtime": os.path.getmtime(p), "chars": project.count_chars(text)}


@app.put("/api/books/{book_id}/file")
async def write_file(book_id: str, req: Request):
    d = book_dir(book_id)
    body = await req.json()
    p = wrap(lambda: project.safe_path(d, body.get("path")))
    if not p.endswith(".md"):
        raise HTTPException(400, "只能編輯 .md 檔案")
    if RUNNER.running_for(book_id):
        raise HTTPException(409, "Claude 正在處理這本書，請等任務結束再存檔，避免互相覆蓋。")
    if os.path.isfile(p) and body.get("mtime") and abs(os.path.getmtime(p) - float(body["mtime"])) > 0.001:
        raise HTTPException(409, "檔案在你編輯期間被修改過了。請複製你的修改，重新載入後再存。")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(body.get("text", ""))
    return {"ok": True, "mtime": os.path.getmtime(p)}


@app.post("/api/books/{book_id}/check")
async def check_file(book_id: str, req: Request):
    d = book_dir(book_id)
    body = await req.json()
    p = wrap(lambda: project.safe_path(d, body.get("path")))
    if not os.path.isfile(p):
        raise HTTPException(404, "檔案不存在")
    wl = check_text.load_whitelist(d)
    return check_text.check_file(p, wl)


# ---------------------------------------------------------------------------
# 候選稿
# ---------------------------------------------------------------------------
@app.post("/api/books/{book_id}/candidate/{no}/accept")
def accept(book_id: str, no: int, provider: str = None):
    d = book_dir(book_id)
    prov = get_provider(provider)
    if RUNNER.running_for(book_id):
        raise HTTPException(409, "還有任務在執行，請稍後再採用。")
    path = wrap(lambda: project.accept_candidate(d, no))
    params = {"chapter": no, "path": path}
    title, prompt = actions.build("accept", params, book_id)
    job = RUNNER.start(runner_mod.Job(book_id, d, title, prompt, meta={"action": "accept", "params": params},
                                      provider=prov))
    return {"path": path, "job": job.to_dict()}


@app.post("/api/books/{book_id}/candidate/{no}/reject")
async def reject(book_id: str, no: int, req: Request):
    d = book_dir(book_id)
    body = await req.json()
    params = {"chapter": no, "note": body.get("note", "")}
    title, prompt = actions.build("reject", params, book_id)
    try:
        job = RUNNER.start(runner_mod.Job(book_id, d, title, prompt, meta={"action": "reject", "params": params},
                                          provider=get_provider(body.get("provider"))))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"job": job.to_dict()}


@app.post("/api/books/{book_id}/candidate/{no}/discard")
def discard(book_id: str, no: int):
    d = book_dir(book_id)
    wrap(lambda: project.discard_candidate(d, no))
    return {"ok": True}


# ---------------------------------------------------------------------------
# 任務
# ---------------------------------------------------------------------------
@app.post("/api/books/{book_id}/jobs")
async def start_job(book_id: str, req: Request):
    d = book_dir(book_id)
    body = await req.json()
    action = body.get("action", "free")
    resume = body.get("resume")
    try:
        if action == "reply":
            title, prompt = "回覆", body.get("params", {}).get("text", "")
        else:
            title, prompt = actions.build(action, body.get("params") or {}, book_id)
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(400, "參數不完整：%s" % e)
    if not prompt.strip():
        raise HTTPException(400, "指令是空的")
    try:
        prov = get_provider(body.get("provider"))
        if resume and body.get("resume_provider") and body["resume_provider"] != prov["id"]:
            prov = get_provider(body["resume_provider"])   # 接續對話一定用原本的執行者
        special = {"goal_check": claude_goal_job, "review_notes": claude_review_job,
                   "revise_notes": claude_revise_job, "recover_continue": claude_recover_job}
        if action in special and prov.get("type") == "claude_code":
            job = RUNNER.start(special[action](book_id, d, prov, body.get("params") or {}))
        else:
            job = RUNNER.start(runner_mod.Job(book_id, d, title, prompt, resume=resume, provider=prov,
                                              meta={"action": action, "params": body.get("params") or {}}))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return job.to_dict()


@app.get("/api/books/{book_id}/jobs")
def job_history(book_id: str):
    d = book_dir(book_id)
    hist = runner_mod.load_history(d)
    run = RUNNER.running_for(book_id)
    if run:
        hist = [run.to_dict()] + [h for h in hist if h["id"] != run.id]
    return hist


@app.get("/api/books/{book_id}/jobs/{job_id}")
def job_detail(book_id: str, job_id: str):
    j = RUNNER.get(job_id)
    if j:
        return j.to_dict(True)
    data = runner_mod.load_job_file(book_dir(book_id), job_id)
    if not data:
        raise HTTPException(404, "找不到任務")
    return data


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    return {"ok": RUNNER.cancel(job_id)}


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request, since: int = 0):
    job = RUNNER.get(job_id)
    if not job:
        raise HTTPException(404, "任務不在執行中")

    async def gen():
        i = since
        idle = 0
        while True:
            if await request.is_disconnected():
                break
            evs = job.events[i:]
            for ev in evs:
                yield "data: %s\n\n" % json.dumps(ev, ensure_ascii=False)
            i += len(evs)
            if job.status != "running" and i >= len(job.events) and job.ended:
                yield "event: close\ndata: {}\n\n"
                break
            if not evs:
                idle += 1
                if idle % 75 == 0:
                    yield ": ping\n\n"
            else:
                idle = 0
            await asyncio.sleep(0.2)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# 靜態頁面
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"),
                        headers={"Cache-Control": "no-cache"})


def serve():
    """實際執行伺服器。要求重新啟動時以 RESTART_CODE 結束，由外層再啟動一次。"""
    global SERVER, RUNNING_PORT
    host = CONFIG.get("host", "127.0.0.1")
    port = int(CONFIG.get("port", 8765))
    url = "http://%s:%d" % ("127.0.0.1" if host in ("0.0.0.0", "") else host, port)
    if "--open-browser" in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print("小說工作台 %s 已啟動：%s（按 Ctrl+C 結束）" % (VERSION, url), flush=True)
    SERVER = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning",
                                           timeout_graceful_shutdown=3))
    RUNNING_PORT = port
    try:
        SERVER.run()
    except KeyboardInterrupt:
        return
    if _restart["requested"]:
        print("重新啟動中……", flush=True)
        sys.exit(RESTART_CODE)


def main():
    if "--serve" in sys.argv:
        return serve()
    # 外層：啟動伺服器子程序；子程序以 RESTART_CODE 結束時再啟動一次
    args = [sys.executable, os.path.abspath(__file__), "--serve"]
    first = "--no-browser" not in sys.argv
    while True:
        proc = subprocess.Popen(args + (["--open-browser"] if first else []))
        first = False
        try:
            code = proc.wait()
        except KeyboardInterrupt:
            try:
                code = proc.wait(timeout=10)
            except (KeyboardInterrupt, subprocess.TimeoutExpired):
                proc.kill()
            code = 0
            break
        if code != RESTART_CODE:
            break
    sys.exit(code if code not in (None, RESTART_CODE) else 0)


if __name__ == "__main__":
    main()
