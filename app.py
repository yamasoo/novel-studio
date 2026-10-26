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
import re
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
from studio import actions, comfy, context, export, forge, goals, illust, importer, native, native_files, project, providers, pipeline, recovery, revision, runner as runner_mod, shared, style_design  # noqa: E402

VERSION = "1.10.0"
PLUGIN_DIR = os.path.join(HERE, "plugin")
CONFIG_PATH = os.path.join(HERE, "config.json")
DEFAULT_CONFIG = {
    # 書庫：第一次使用時由使用者在書架頁選擇（不自動用任何既有資料夾）
    "library": "",
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
    "pipeline_severities": ["必須修", "建議修"],   # 整章自動流程：自動勾選哪些等級的審查意見
    "pipeline_mode": "stop",            # 整章自動流程：stop＝每章定稿後停下來；continue＝連續寫到最後一章
    "pipeline_providers": {},           # 整章自動流程：各步驟的執行者（空白＝跟流程的執行者）；面板按鈕也預設帶入
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
PIPES = pipeline.Manager()
CLAUDE_SPECIAL = {}   # 動作 → 建立 Claude Code 特殊任務的函式（各函式定義後登記）


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
            "key_status": {p["id"]: providers.key_status(HERE, p) for p in CONFIG.get("providers") or []},
            "key_store": providers.store_name(), "secrets_pending": providers.pending_secrets(HERE)}


@app.post("/api/config")
async def set_config(req: Request):
    body = await req.json()
    for k in ("library", "claude_cmd", "model", "permission_mode", "allowed_tools", "add_dirs",
              "stale_foreshadow", "stale_character", "default_provider",
              "reconcile_before_write", "goal_check_after_write", "pipeline_severities", "pipeline_mode"):
        if k in body:
            CONFIG[k] = body[k]
    if "pipeline_providers" in body:
        ids = {p.get("id") for p in CONFIG.get("providers") or []}
        CONFIG["pipeline_providers"] = pipeline.clean_step_providers(body.get("pipeline_providers"), ids)
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
        try:
            r_ = float(p.get("cjk_token_ratio") or 0)
        except (TypeError, ValueError):
            r_ = 0
        if r_ > 0:
            clean["cjk_token_ratio"] = round(min(3.0, max(0.2, r_)), 2)   # 0／空白＝自動
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


@app.post("/api/secrets/migrate")
def secrets_migrate():
    """把 secrets.json 的金鑰搬進系統金鑰庫（Windows 認證管理員等）。"""
    if not providers.store_name():
        raise HTTPException(400, "這台電腦沒有可用的系統金鑰庫（需要 keyring 套件），金鑰會繼續存在 secrets.json。")
    moved, left = providers.migrate_secrets(HERE)
    r = get_config()
    r["moved"], r["left"] = moved, left
    return r


@app.post("/api/providers/{pid}/models")
def provider_models(pid: str):
    prov = get_provider(pid)
    if prov.get("type") == "claude_code":
        return {"models": ["sonnet", "opus", "haiku"]}
    try:
        return {"models": providers.list_models(HERE, prov)}
    except providers.ProviderError as e:
        raise HTTPException(400, str(e))


@app.post("/api/providers/{pid}/calibrate")
def provider_calibrate(pid: str):
    """llama.cpp：用 /tokenize 算出每個中文字約幾 token（不呼叫模型生成）。"""
    prov = get_provider(pid)
    if prov.get("type") == "claude_code":
        raise HTTPException(400, "Claude Code 不需要設定")
    try:
        return {"ratio": providers.calibrate_cjk(HERE, prov)}
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
    _guard_pipeline(book_id)
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
              "不要修改任何檔案。\n%s%s\n最後一則回覆只輸出 JSON，不要加說明或程式碼圍欄。" % (
                  no, rel, ("作者這次的要求：" + params["note"].strip() + "\n") if (params.get("note") or "").strip() else "",
                  revision.REVIEW_SCHEMA))
    job = runner_mod.Job(book_id, d, "審查第%d章" % no, prompt, provider=prov, meta={"action": "review_notes", "params": params})

    def after(j):
        try:
            data = providers.parse_json(j.result or "")
        except providers.ProviderError as e:
            raise RuntimeError("無法解析 Claude 回傳的審查結果：%s" % e)
        text = project.read_text(os.path.join(d, rel))
        rv = revision.merge_local_checks(revision.normalize_review(data, text), d, rel, check_text)
        rec = revision.save_review(d, no, rel, text, rv, prov.get("id"))
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


# ---------------------------------------------------------------------------
# 共用庫（書庫/_共用/）：文風、章節結構、共用作者偏好
# ---------------------------------------------------------------------------
def library():
    lib = CONFIG.get("library")
    if not lib or not os.path.isdir(lib):
        raise HTTPException(400, "書庫資料夾不存在，請先在設定中指定。")
    return lib


def _book_list():
    return [b["id"] for b in project.list_books(CONFIG.get("library")) if b.get("is_book")]


def _sample_text(body):
    """文風分析的樣本：貼上的文字、上傳的檔案，或某本書的正文。"""
    src = body.get("source")
    if src == "book":
        d = book_dir(body.get("book") or "")
        a = int(body["from"]) if body.get("from") else None
        b = int(body["to"]) if body.get("to") else None
        text = shared.book_sample(d, a, b)
        if not text.strip():
            raise HTTPException(400, "這本書在這個範圍內沒有正文")
        return text, shared.book_names(d)
    if src in ("text", "files"):
        payload = {"text": body.get("text") or ""} if src == "text" else {"files": body.get("files") or []}
        parts = wrap(lambda: importer.load_sources(payload))
        return "\n\n".join(p[1] for p in parts), []
    return None, []


def _guard_book(book_id):
    if RUNNER.running_for(book_id):
        raise HTTPException(409, "這本書有任務在執行，請等它結束再套用。")


@app.get("/api/shared")
def shared_overview():
    lib = library()
    d = shared.shared_dir(lib)
    prefs = os.path.join(d, "作者偏好.md")
    banned = check_text.parse_banned(project.read_text(prefs)) if os.path.isfile(prefs) else []
    return {"dir": d, "exists": os.path.isdir(d), "styles": wrap(lambda: shared.list_styles(lib)),
            "structures": wrap(lambda: shared.list_structures(lib)),
            "prefs": {"exists": os.path.isfile(prefs), "banned": len(banned),
                      "active": bool(os.path.isfile(prefs) and shared._meaningful(project.read_text(prefs)))},
            "books": _book_list()}


@app.post("/api/shared/init")
def shared_init():
    d = wrap(lambda: shared.shared_dir(library(), create=True))
    return {"dir": d}


@app.get("/api/shared/file")
def shared_file(path: str):
    lib = library()
    if path.startswith("preset:"):
        p = os.path.join(shared.PRESET_DIR, os.path.basename(path[7:]))
        readonly = True
    else:
        p = wrap(lambda: shared.safe_shared_path(lib, path))
        readonly = False
    if not os.path.isfile(p):
        raise HTTPException(404, "檔案不存在")
    text = project.read_text(p)
    return {"path": path, "text": text, "mtime": os.path.getmtime(p), "chars": project.count_chars(text),
            "readonly": readonly, "metrics": shared.parse_metrics(text)}


@app.put("/api/shared/file")
async def shared_file_put(req: Request):
    body = await req.json()
    path = body.get("path") or ""
    if path.startswith("preset:"):
        raise HTTPException(400, "內建結構不能直接修改，請先「複製到我的結構」")
    p = wrap(lambda: shared.safe_shared_path(library(), path))
    if not p.endswith(".md"):
        raise HTTPException(400, "只能編輯 .md 檔案")
    if os.path.isfile(p) and body.get("mtime") and abs(os.path.getmtime(p) - float(body["mtime"])) > 0.001:
        raise HTTPException(409, "檔案在你編輯期間被修改過了。請複製你的修改，重新載入後再存。")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(body.get("text", ""))
    return {"ok": True, "mtime": os.path.getmtime(p)}


@app.post("/api/shared/styles")
async def shared_style_new(req: Request):
    body = await req.json()
    lib = library()
    src = body.get("source") or "blank"
    if src == "copy_book":
        d = book_dir(body.get("book") or "")
        return wrap(lambda: shared.create_style(lib, body.get("name"), source=("book", d)))
    text, names = _sample_text(body)
    if text:
        wrap(lambda: shared.analyze(text, names))  # 樣本太短時先報錯
    return wrap(lambda: shared.create_style(lib, body.get("name"), sample_text=text, exclude=names))


@app.post("/api/shared/styles/{name}/restat")
async def shared_style_restat(name: str, req: Request):
    body = await req.json()
    text, names = _sample_text(body)
    if not text:
        raise HTTPException(400, "請提供樣本文字")
    p = os.path.join(shared.shared_dir(library()), "文風", name + ".md")
    if not os.path.isfile(p):
        raise HTTPException(404, "找不到這個文風")
    m = wrap(lambda: shared.analyze(text, names))
    t = shared.put_metrics(project.read_text(p), m)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    return {"metrics": m}


@app.post("/api/shared/styles/{name}/apply")
async def shared_style_apply(name: str, req: Request):
    body = await req.json()
    _guard_book(body.get("book"))
    return {"path": wrap(lambda: shared.apply_style(library(), name, book_dir(body.get("book") or "")))}


@app.post("/api/shared/styles/{name}/compare")
async def shared_style_compare(name: str, req: Request):
    body = await req.json()
    p = os.path.join(shared.shared_dir(library()), "文風", name + ".md")
    if not os.path.isfile(p):
        raise HTTPException(404, "找不到這個文風")
    target = shared.parse_metrics(project.read_text(p))
    if not target:
        raise HTTPException(400, "這個文風還沒有文字指標，請先「重新統計」")
    text, names = _sample_text(dict(body, source=body.get("source") or "book"))
    actual = wrap(lambda: shared.analyze(text, names))
    return {"rows": shared.compare(target, actual), "actual": actual}


@app.post("/api/shared/styles/design")
async def shared_style_design(req: Request):
    """請 AI 設計／調整／試寫共用文風（任務掛在 _共用 底下）。"""
    body = await req.json()
    lib = library()
    params = {k: body.get(k) for k in ("mode", "name", "genre", "feel", "refs", "pov", "readers", "avoid", "note", "overwrite")}
    text, names = _sample_text(body)
    params["sample"] = text or ""
    params["exclude"] = ",".join(names)
    shared.shared_dir(lib, create=True)
    d = book_dir(shared.SHARED)
    try:
        info = style_design.prepare(lib, params)
    except (style_design.DesignError, shared.SharedError) as e:
        raise HTTPException(400, str(e))
    prov = get_provider(body.get("provider"))
    title = actions.build("style_design", params, shared.SHARED)[0]
    try:
        if prov.get("type") == "claude_code":
            job = runner_mod.Job(shared.SHARED, d, title, style_design.claude_prompt(info, params, PLUGIN_DIR),
                                 provider=prov, meta={"action": "style_design", "params": {k: v for k, v in params.items() if k != "sample"}})

            def after(j):
                try:
                    j.result = style_design.finish(lib, info, j.result or "")
                except style_design.DesignError as e:
                    raise RuntimeError(str(e))
                j.emit("result", text=j.result)
            job.after = after
        else:
            job = runner_mod.Job(shared.SHARED, d, title, "（由工作台組裝）", provider=prov,
                                 meta={"action": "style_design", "params": params})
        job = RUNNER.start(job)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return job.to_dict()


@app.post("/api/shared/styles/save")
async def shared_style_save(req: Request):
    body = await req.json()
    return wrap(lambda: shared.save_style_from_book(library(), body.get("name"), book_dir(body.get("book") or ""),
                                                    bool(body.get("overwrite"))))


@app.delete("/api/shared/{kind}/{name}")
def shared_delete(kind: str, name: str):
    if kind not in ("styles", "structures"):
        raise HTTPException(404, "不支援")
    wrap(lambda: shared.delete_item(library(), "style" if kind == "styles" else "structure", name))
    return {"ok": True}


@app.post("/api/shared/structures")
async def shared_structure_new(req: Request):
    body = await req.json()
    if body.get("copy_preset"):
        return wrap(lambda: shared.copy_preset(library(), body["copy_preset"], body.get("name")))
    return wrap(lambda: shared.new_structure(library(), body.get("name")))


@app.post("/api/shared/structures/{name}/apply")
async def shared_structure_apply(name: str, req: Request):
    body = await req.json()
    _guard_book(body.get("book"))
    d = book_dir(body.get("book") or "")
    return {"path": wrap(lambda: shared.apply_structure(library(), name, body.get("origin") or "mine", d,
                                                        bool(body.get("default"))))}


@app.get("/api/books/{book_id}/structures")
def book_structures(book_id: str, chapter: int = None):
    d = book_dir(book_id)
    out = {"list": shared.book_structures(d)}
    if chapter:
        name, _, src = shared.structure_for(d, chapter)
        _, card = context.card_text(d, chapter)
        fm = project.split_frontmatter(card)[0] if card else {}
        out["chapter"] = {"assigned": str(fm.get("結構") or ""), "effective": name, "from": src, "has_card": bool(card)}
    return out


@app.post("/api/books/{book_id}/structures/default")
async def book_structure_default(book_id: str, req: Request):
    body = await req.json()
    _guard_book(book_id)
    wrap(lambda: shared.set_book_default(book_dir(book_id), body.get("name") or None))
    return {"ok": True}


@app.post("/api/books/{book_id}/chapters/{no}/structure")
async def chapter_structure(book_id: str, no: int, req: Request):
    body = await req.json()
    _guard_book(book_id)
    wrap(lambda: shared.set_chapter_structure(book_dir(book_id), no, body.get("name") or None))
    return {"ok": True}


@app.post("/api/books/{book_id}/style-compare")
async def book_style_compare(book_id: str, req: Request):
    """本書的 設定/文風.md 文字指標 vs 正文實際統計。"""
    body = await req.json()
    d = book_dir(book_id)
    sp = os.path.join(d, "設定", "文風.md")
    target = shared.parse_metrics(project.read_text(sp)) if os.path.isfile(sp) else {}
    text, names = _sample_text(dict(body, source="book", book=book_id))
    actual = wrap(lambda: shared.analyze(text, names))
    return {"rows": shared.compare(target, actual) if target else [], "actual": actual, "has_target": bool(target)}


# ---------------------------------------------------------------------------
# 匯入舊稿
# ---------------------------------------------------------------------------
@app.get("/api/import/info")
def import_info():
    return {"has_opencc": importer.has_opencc(), "books": _book_list()}


@app.post("/api/import/preview")
async def import_preview(req: Request):
    body = await req.json()
    return wrap(lambda: importer.preview(body.get("payload") or {}, body.get("opts") or {}))


@app.post("/api/import/commit")
async def import_commit(req: Request):
    body = await req.json()
    lib = library()
    opts = body.get("opts") or {}
    if body.get("new_book"):
        name = (body.get("new_book") or "").strip()
        wrap(lambda: importer.plan(body.get("payload") or {}, opts))  # 先確認拆得出章節，再建書
        d = wrap(lambda: project.create_book(lib, name))
        native_files.ensure_skeleton(d, PLUGIN_DIR)
        importer.make_claude_md(d, PLUGIN_DIR, name)
        book_id = os.path.basename(d)
    else:
        book_id = body.get("book") or ""
        d = book_dir(book_id)
        _guard_book(book_id)
    r = wrap(lambda: importer.commit(d, body.get("payload") or {}, opts, check_text))
    r["book"] = book_id
    return r


# ---------------------------------------------------------------------------
# 插圖（Forge Neo 出圖、上傳、主圖、提示詞組裝）
# ---------------------------------------------------------------------------
def illust_cfg():
    cfg = dict(illust.DEFAULTS)
    cfg.update(CONFIG.get("illust") or {})
    return cfg


FORGE_QUEUE = forge.Queue(illust_cfg)


EXAMPLE_SHEET = os.path.join(HERE, "examples", "styles.example.json")


def _sheet_path(cfg):
    """樣式表：設定的路徑；沒填就用專案附的範例（examples/styles.example.json）。"""
    p = cfg.get("style_sheet") or EXAMPLE_SHEET
    return p if os.path.isfile(p) else ""


@app.get("/api/illust/config")
def illust_config():
    cfg = illust_cfg()
    t, z = illust.tag_dict_paths(cfg)
    sheet = _sheet_path(cfg)
    n = 0
    err = ""
    try:
        n = len(illust.load_sheet(cfg.get("style_sheet") or sheet)) if (cfg.get("style_sheet") or sheet) else 0
    except Exception as e:  # noqa: BLE001
        err = str(e)
    return {"config": cfg, "sizes": illust.SIZES, "tag_csv": t, "tag_zh_csv": z, "sheet": sheet, "sheet_count": n,
            "sheet_is_example": bool(sheet) and not cfg.get("style_sheet"),
            "sheet_error": err, "providers": [{"id": p["id"], "name": p.get("name"), "type": p.get("type")}
                                              for p in CONFIG.get("providers") or []]}


@app.post("/api/illust/config")
async def illust_config_save(req: Request):
    body = await req.json()
    cur = dict(CONFIG.get("illust") or {})
    for k in illust.DEFAULTS:
        if k in body:
            cur[k] = body[k]
    for k in ("width", "height"):
        if k in cur:
            try:
                cur[k] = max(256, min(4096, int(cur[k]) // 8 * 8))
            except (TypeError, ValueError):
                cur.pop(k)
    if "comfy_profiles" in body:
        cur["comfy_profiles"] = _clean_profiles(body["comfy_profiles"])
    if "forge_loras" in body:
        cur["forge_loras"] = _clean_loras(body["forge_loras"])
    cur["comfy_lora_dir"] = str(cur.get("comfy_lora_dir") or "").strip()
    if cur.get("backend") not in ("forge", "comfy"):
        cur["backend"] = "forge"
    CONFIG["illust"] = cur
    save_config(CONFIG)
    return illust_config()


PROFILE_KEYS = ("id", "name", "kind", "workflow", "unet", "clip", "vae", "upsampler", "upsampler_clip", "negative")


def _clean_profiles(items):
    out, seen = [], set()
    for i, p in enumerate(items or []):
        if not isinstance(p, dict):
            continue
        q = {k: p.get(k, "") for k in PROFILE_KEYS}
        q["kind"] = q["kind"] if q["kind"] in comfy.KINDS else "anima"
        q["upsampler"] = bool(p.get("upsampler"))
        q["name"] = str(q["name"] or comfy.KINDS[q["kind"]]["label"]).strip()[:40]
        pid = re.sub(r"[^\w-]", "", str(q["id"] or "")) or "p%d" % (i + 1)
        while pid in seen:
            pid += "_"
        seen.add(pid)
        q["id"] = pid
        for k in ("workflow", "unet", "clip", "vae", "upsampler_clip", "negative"):
            q[k] = str(q[k] or "").strip()
        q["loras"] = _clean_loras(p.get("loras"))
        out.append(q)
    return out or list(illust.DEFAULTS["comfy_profiles"])


def _clean_loras(items):
    """LoRA 清單：檔名、強度（-4～4）、是否使用、觸發詞；最多 8 個。檔名空白的也保留（設定頁還在選）。"""
    out = []
    for x in (items or [])[:8]:
        if not isinstance(x, dict):
            continue
        try:
            st = max(-4.0, min(4.0, round(float(x.get("strength", 1)), 2)))
        except (TypeError, ValueError):
            st = 1.0
        out.append({"name": str(x.get("name") or "").strip(), "strength": st, "on": bool(x.get("on", True)),
                    "trigger": str(x.get("trigger") or "").strip()[:200]})
    return out


def comfy_profile(cfg, pid=None):
    profs = cfg.get("comfy_profiles") or illust.DEFAULTS["comfy_profiles"]
    pid = pid or cfg.get("comfy_profile")
    return next((p for p in profs if p.get("id") == pid), profs[0])


@app.get("/api/illust/comfy/status")
def illust_comfy_status():
    """連線 ComfyUI：版本、可選的模型檔、各出圖設定的 workflow 檢查結果。"""
    cfg = illust_cfg()
    base = cfg.get("comfy_url") or illust.DEFAULTS["comfy_url"]
    try:
        stats = comfy.system_stats(base)
        info = comfy.object_info(base)
    except comfy.ComfyError as e:
        return {"ok": False, "error": str(e)}
    lists = comfy.model_lists(info)
    profs = []
    for p in cfg.get("comfy_profiles") or illust.DEFAULTS["comfy_profiles"]:
        r = {"id": p["id"], "guess": comfy.guess_models(p.get("kind"), lists)}
        try:
            path = p.get("workflow") or comfy.template_path(p.get("kind"))
            r["summary"] = comfy.summary(comfy.load_workflow(path), info, p)
            if p.get("upsampler") and "TextGenerate" not in info:
                r["summary"]["missing"].append("TextGenerate（Prompt Upsampler 需要較新的 ComfyUI）")
        except (comfy.ComfyError, OSError) as e:
            r["error"] = str(e)
        profs.append(r)
    sysinfo = stats.get("system") or {}
    devs = stats.get("devices") or []
    return {"ok": True, "version": sysinfo.get("comfyui_version") or "", "device": devs[0].get("name") if devs else "",
            "lists": lists, "profiles": profs}


@app.post("/api/illust/comfy/inspect")
async def illust_comfy_inspect(req: Request):
    """檢查一份 workflow（不需要連線 ComfyUI）。"""
    body = await req.json()
    path = (body.get("workflow") or "").strip() or comfy.template_path(body.get("kind") or "anima")
    if not os.path.isfile(path):
        raise HTTPException(400, "找不到檔案：%s" % path)
    try:
        return comfy.summary(comfy.load_workflow(path))
    except comfy.ComfyError as e:
        raise HTTPException(400, str(e))


FORGE_LORA_PATHS = {}   # 名稱 → 檔案路徑（測試連線時更新，讀同名 JSON 用）


def _forge_base():
    return illust_cfg().get("forge_url") or illust.DEFAULTS["forge_url"]


def _lora_folder(path, roots):
    p = path.replace("\\", "/")
    for r in roots:
        if r and p.lower().startswith(r.lower()):
            sub = os.path.dirname(p[len(r):].strip("/"))
            return sub
    return os.path.basename(os.path.dirname(p))


@app.get("/api/illust/forge/status")
def illust_forge_status():
    try:
        out = forge.status(_forge_base())
    except forge.ForgeError as e:
        return {"ok": False, "error": str(e)}
    try:
        items = forge.loras(_forge_base())
        dirs = [os.path.dirname(x["path"].replace("\\", "/")) for x in items if x["path"]]
        root = os.path.commonpath(dirs).replace("\\", "/") if dirs else ""
        FORGE_LORA_PATHS.clear()
        FORGE_LORA_PATHS.update({x["name"]: x["path"] for x in items})
        out["loras"] = [{"name": x["name"], "folder": _lora_folder(x["path"], [root])} for x in items]
    except (forge.ForgeError, ValueError) as e:
        out["loras"], out["lora_error"] = [], str(e)
    return out


def _comfy_lora_roots(cfg):
    if cfg.get("comfy_lora_dir"):
        return [cfg["comfy_lora_dir"]]
    try:
        fp = comfy._req(cfg.get("comfy_url") or illust.DEFAULTS["comfy_url"], "/internal/folder_paths", timeout=6)
    except comfy.ComfyError:
        return []
    v = (fp or {}).get("loras") or []
    if v and isinstance(v[0], list):   # 有些版本是 [[路徑…], [副檔名…]]
        v = v[0]
    return [str(x) for x in v if isinstance(x, str)]


@app.post("/api/illust/lora_hint")
async def illust_lora_hint(req: Request):
    """選 LoRA 時：讀同目錄同名 JSON，建議觸發詞（前 3 個詞）與強度；找不到就用檔名。"""
    body = await req.json()
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "沒有 LoRA 名稱")
    cfg = illust_cfg()
    path = ""
    if body.get("backend") == "comfy":
        rel = name.replace("\\", "/")
        for r in _comfy_lora_roots(cfg):
            cand = os.path.join(r, *rel.split("/"))
            if os.path.isfile(cand) or os.path.isfile(os.path.splitext(cand)[0] + ".json"):
                path = cand
                break
        path = path or rel
    else:
        path = FORGE_LORA_PATHS.get(name) or ""
        if not path:
            try:
                FORGE_LORA_PATHS.update({x["name"]: x["path"] for x in forge.loras(_forge_base())})
            except forge.ForgeError:
                pass
            path = FORGE_LORA_PATHS.get(name) or name
    return illust.lora_hint(path)


@app.post("/api/illust/forge/params")
async def illust_forge_params(req: Request):
    body = await req.json()
    d = body.get("forge_dir") or illust_cfg().get("forge_dir")
    line = wrap(lambda: illust.params_from_forge_dir(d))
    raw = open(os.path.join(d, "params.txt"), encoding="utf-8", errors="replace").read()
    w, h = illust.params_size(raw)
    return {"params": line, "width": w, "height": h}


@app.get("/api/illust/styles")
def illust_styles(nsfw: bool = False):
    cfg = illust_cfg()
    path = cfg.get("style_sheet") or _sheet_path(cfg)
    if not path:
        return {"styles": [], "categories": [], "total": 0, "missing": True}
    return wrap(lambda: illust.sheet_index(path, nsfw or bool(cfg.get("show_nsfw_styles"))))


@app.get("/api/illust/queue")
def illust_queue(book: str = None):
    return FORGE_QUEUE.list(book)


@app.post("/api/illust/queue/{qid}/cancel")
def illust_queue_cancel(qid: str):
    return {"ok": FORGE_QUEUE.cancel(qid)}


@app.get("/api/books/{book_id}/illust")
def book_illust(book_id: str, target: str):
    d = book_dir(book_id)
    info = wrap(lambda: illust.list_images(d, target))
    info["style"] = illust.load_book_style(d)
    return info


@app.get("/api/books/{book_id}/illust/overview")
def book_illust_overview(book_id: str):
    d = book_dir(book_id)
    return {"items": illust.overview(d), "style": illust.load_book_style(d),
            "chapters": [{"no": r["no"], "title": r["title"]} for r in project.scan_chapters(d) if r["text_file"] or r["candidate_file"]]}


@app.post("/api/books/{book_id}/illust/style")
async def book_illust_style(book_id: str, req: Request):
    return illust.save_book_style(book_dir(book_id), await req.json())


@app.get("/api/books/{book_id}/illust/image")
def book_illust_image(book_id: str, path: str):
    p = wrap(lambda: illust.image_path(book_dir(book_id), path))
    return FileResponse(p, headers={"Cache-Control": "max-age=86400"})


@app.post("/api/books/{book_id}/illust/upload")
async def book_illust_upload(book_id: str, req: Request):
    body = await req.json()
    return {"files": wrap(lambda: illust.upload(book_dir(book_id), body.get("target"), body.get("files")))}


@app.post("/api/books/{book_id}/illust/main")
async def book_illust_main(book_id: str, req: Request):
    body = await req.json()
    wrap(lambda: illust.set_main(book_dir(book_id), body.get("target"), body.get("file")))
    return {"ok": True}


@app.post("/api/books/{book_id}/illust/delete")
async def book_illust_delete(book_id: str, req: Request):
    body = await req.json()
    wrap(lambda: illust.delete_image(book_dir(book_id), body.get("target"), body.get("file")))
    return {"ok": True}


@app.post("/api/books/{book_id}/illust/draft")
async def book_illust_draft(book_id: str, req: Request):
    body = await req.json()
    wrap(lambda: illust.save_draft(book_dir(book_id), body.get("target"), body.get("draft") or {}))
    return {"ok": True}


@app.post("/api/books/{book_id}/illust/pick")
async def book_illust_pick(book_id: str, req: Request):
    """本機挑片段：依動作詞、畫面詞、章綱情節點打分，回傳前三段。"""
    body = await req.json()
    d = book_dir(book_id)
    no = int(body.get("chapter"))
    rel, text = context.chapter_text(d, no, ("正文", "候選"))
    if not text:
        raise HTTPException(400, "第%d章還沒有正文或候選稿" % no)
    _, card = context.card_text(d, no)
    return {"source": rel, "passages": illust.pick_passages(text, body.get("mode") or "highlight", card or "")}


@app.post("/api/books/{book_id}/illust/detect")
async def book_illust_detect(book_id: str, req: Request):
    """片段裡出現的角色、地點，以及本機中文→標籤查表的結果。"""
    body = await req.json()
    d = book_dir(book_id)
    text = body.get("text") or ""
    target = body.get("target") or ""
    ents = illust.mentioned(d, text) if text else []
    if target.startswith("entity:"):
        f = target.split(":", 1)[1]
        own = [e for e in illust.entity_cards(d) if e["file"] == f]
        ents = own + [e for e in ents if e["file"] != f]
    cfg = illust_cfg()
    t, z = illust.tag_dict_paths(cfg)
    return {"entities": ents, "all": [{"name": e["name"], "kind": e["kind"], "file": e["file"], "has_card": bool(e["card"])}
                                      for e in illust.entity_cards(d)],
            "zh_tags": illust.zh_lookup(text, z, t) if text and z else [], "has_dict": bool(z)}


def _backend_cfg(cfg, spec, backend=None, profile=None):
    """依出圖後端調整提示詞格式：MOSS-Image 用自然語言、不加品質與分級標籤、不用畫師標籤。"""
    cfg = dict(cfg)
    if (backend or cfg.get("backend")) != "comfy":
        return cfg
    p = comfy_profile(cfg, profile)
    if p.get("negative"):
        cfg["negative"] = p["negative"]
    if p.get("kind") == "moss":
        spec["format"] = "natural"
        spec["quality"], spec["safety"], spec["artist"] = "", "", ""
        cfg.update(format="natural", quality="", safety="", style_source="naturl_prompt",
                   negative=p.get("negative") or comfy.MOSS_NEGATIVE)
    return cfg


@app.post("/api/books/{book_id}/illust/assemble")
async def book_illust_assemble(book_id: str, req: Request):
    body = await req.json()
    d = book_dir(book_id)
    cfg = illust_cfg()
    spec = dict(body.get("draft") or {})
    bs = illust.load_book_style(d)
    if "styles" not in spec:
        spec["styles"] = bs.get("styles") or []
    if "artist" not in spec:
        spec["artist"] = bs.get("artist") or ""
    spec["extra"] = ", ".join(x for x in [spec.get("extra") or "", bs.get("extra") or ""] if x)
    spec["negative_extra"] = ", ".join(x for x in [spec.get("negative_extra") or "", bs.get("negative_extra") or ""] if x)
    cfg = _backend_cfg(cfg, spec, body.get("backend"), body.get("profile"))
    r = wrap(lambda: illust.assemble(spec, cfg, _sheet_path(cfg)))
    t, _ = illust.tag_dict_paths(cfg)
    notes = []
    if t:
        tag_part = ", ".join(x for x in [spec.get("action_tags", ""), spec.get("scene_tags", ""), spec.get("composition", "")]
                             + [c.get("action", "") for c in spec.get("chars") or []] if x)
        _, notes = illust.check_tags(tag_part, t)
    r["notes"] = notes
    return r


@app.post("/api/books/{book_id}/illust/generate")
async def book_illust_generate(book_id: str, req: Request):
    body = await req.json()
    d = book_dir(book_id)
    cfg = illust_cfg()
    target = body.get("target")
    _, _, label = wrap(lambda: illust.target_dir(d, target))
    if not (body.get("positive") or "").strip():
        raise HTTPException(400, "提示詞是空的")
    bs = illust.load_book_style(d)
    w = body.get("width") or (bs.get("cover_width") if target == "cover" else bs.get("width")) or cfg.get("width")
    h = body.get("height") or (bs.get("cover_height") if target == "cover" else bs.get("height")) or cfg.get("height")
    draft = body.get("draft") or {}
    if draft:
        illust.save_draft(d, target, draft)
    meta = {"styles": draft.get("styles"), "passage": (draft.get("passage") or "")[:600], "target": target}
    backend = body.get("backend") or cfg.get("backend") or "forge"
    prof = comfy_profile(cfg, body.get("profile")) if backend == "comfy" else None
    if prof:
        w, h = int(w) // 16 * 16, int(h) // 16 * 16   # MOSS／Flux2 系的 latent 要 16 的倍數
    positive = body["positive"]
    if backend != "comfy":
        on = comfy.active_loras({"loras": cfg.get("forge_loras") or []})
        if on:
            added = [x for x in on if "<lora:%s:" % x["name"] not in positive]   # 提示詞裡自己寫的以提示詞為準
            positive = forge.with_loras(positive, on)
            if added:
                meta["loras"] = [{"name": x["name"], "strength": x["strength"]} for x in added]
    it = FORGE_QUEUE.add(book_id, d, target, label, positive, body.get("negative") or "",
                         body.get("params") if body.get("params") is not None else cfg.get("params") or "",
                         body.get("seed", -1), w, h, body.get("count") or 1, meta, backend=backend, profile=prof)
    return FORGE_QUEUE._pub(it)


@app.post("/api/books/{book_id}/cards")
async def book_card_save(book_id: str, req: Request):
    """手動編輯視覺卡（寫進設定檔的「## 繪圖提示」一節）。"""
    body = await req.json()
    d = book_dir(book_id)
    _guard_book(book_id)
    f = body.get("file") or ""
    if not f.startswith(("設定/角色/", "設定/勢力/", "設定/世界觀/")):
        raise HTTPException(400, "只有角色、勢力、世界觀的設定檔可以加視覺卡")
    p = wrap(lambda: project.safe_path(d, f))
    text = project.read_text(p)
    native.tracking.backup(d, p, "視覺卡")
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(illust.write_card(text, {"tags": body.get("tags") or "", "description": body.get("description") or ""}))
    return {"card": illust.read_card(project.read_text(p))}


@app.post("/api/illust/zh")
async def illust_zh(req: Request):
    """中文→Danbooru 標籤查表（本機）。"""
    body = await req.json()
    t, z = illust.tag_dict_paths(illust_cfg())
    if not z:
        return {"tags": [], "has_dict": False}
    return {"tags": illust.zh_lookup(body.get("text") or "", z, t, limit=60), "has_dict": True}


def claude_illust_job(book_id, d, prov, params):
    try:
        kind, passage, chars, places = native.illust_inputs(d, params)
    except (native.NativeError, project.ProjectError) as e:
        raise HTTPException(400, str(e))
    system, user = illust.ai_scene_prompt(d, params.get("target"), passage, chars, places, kind)
    prompt = system + "\n\n" + user + "\n\n不需要讀寫任何檔案。最後一則回覆只輸出 JSON，不要加說明或程式碼圍欄。"
    job = runner_mod.Job(book_id, d, "產生插圖提示詞", prompt, provider=prov, meta={"action": "illust_prompt", "params": params})

    def after(j):
        try:
            data = providers.parse_json(j.result or "")
        except providers.ProviderError as e:
            raise RuntimeError("無法解析 Claude 回傳的結果：%s" % e)
        j.result = native.save_illust_result(d, params, data, prov.get("id"))
        j.emit("result", text=j.result)
    job.after = after
    return job


def claude_card_job(book_id, d, prov, params):
    f = params.get("file") or ""
    text = context.read(d, f)
    if not text:
        raise HTTPException(400, "找不到 %s" % f)
    system, user = illust.ai_card_prompt(text, os.path.splitext(os.path.basename(f))[0], f.split("/")[1])
    prompt = system + "\n\n" + user + "\n\n不需要讀寫任何檔案。最後一則回覆只輸出 JSON，不要加說明或程式碼圍欄。"
    job = runner_mod.Job(book_id, d, "產生視覺卡", prompt, provider=prov, meta={"action": "visual_card", "params": params})

    def after(j):
        try:
            data = providers.parse_json(j.result or "")
        except providers.ProviderError as e:
            raise RuntimeError("無法解析 Claude 回傳的結果：%s" % e)
        j.result = native.save_card_result(d, params, data)
        j.emit("result", text=j.result)
    job.after = after
    return job


CLAUDE_SPECIAL.update({"goal_check": claude_goal_job, "review_notes": claude_review_job,
                       "revise_notes": claude_revise_job, "recover_continue": claude_recover_job,
                       "illust_prompt": claude_illust_job, "visual_card": claude_card_job})


@app.get("/api/actions")
def get_actions():
    cat = actions.catalog()
    for a in cat:
        a["native"] = a["id"] in native.NATIVE_ACTIONS
    return cat


# ---------------------------------------------------------------------------
# 書架
# ---------------------------------------------------------------------------
SUGGESTED_LIBRARY = os.path.join(os.path.expanduser("~"), "Documents", "小說")


@app.get("/api/books")
def books():
    lib = CONFIG.get("library")
    return {"library": lib, "exists": os.path.isdir(lib or ""), "books": project.list_books(lib),
            "suggested": SUGGESTED_LIBRARY, "suggested_exists": os.path.isdir(SUGGESTED_LIBRARY)}


# ---------------------------------------------------------------------------
# 選資料夾／檔案（只列名稱，不讀檔案內容；服務只開在本機）
# ---------------------------------------------------------------------------
def _fs_roots():
    home = os.path.expanduser("~")
    roots = [("使用者資料夾", home)]
    for name, sub in (("文件", "Documents"), ("桌面", "Desktop"), ("下載", "Downloads")):
        p = os.path.join(home, sub)
        if os.path.isdir(p):
            roots.append((name, p))
    roots.append(("工作台資料夾", HERE))
    if os.name == "nt":
        import string
        for L in string.ascii_uppercase:
            d = L + ":\\"
            if os.path.exists(d):
                roots.append((L + ":", d))
    else:
        roots.append(("/", "/"))
    return [{"name": n, "path": p} for n, p in roots]


@app.get("/api/fs/list")
def fs_list(path: str = "", mode: str = "dir", exts: str = ""):
    want = [e.lower() if e.startswith(".") else "." + e.lower() for e in exts.split(",") if e.strip()]
    out = {"roots": _fs_roots(), "path": "", "parent": None, "dirs": [], "files": []}
    if not path:
        return out
    p = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
    # 檔案就看它所在的資料夾；不存在的路徑往上找到第一個存在的資料夾
    while p and not os.path.isdir(p):
        up = os.path.dirname(p)
        if up == p:
            return out
        p = up
    if not p:
        return out
    try:
        names = os.listdir(p)
    except OSError as e:
        raise HTTPException(400, "無法讀取這個資料夾：%s" % e)
    for n in sorted(names, key=str.lower):
        if n.startswith((".", "$")) or n in ("__pycache__", "System Volume Information"):
            continue
        full = os.path.join(p, n)
        if os.path.isdir(full):
            out["dirs"].append(n)
        elif mode == "file" and (not want or os.path.splitext(n)[1].lower() in want):
            out["files"].append(n)
    parent = os.path.dirname(p)
    out.update(path=p, parent=parent if parent and parent != p else None, sep=os.sep)
    return out


@app.post("/api/fs/mkdir")
async def fs_mkdir(req: Request):
    body = await req.json()
    base = os.path.abspath(os.path.expanduser(body.get("path") or ""))
    name = (body.get("name") or "").strip()
    if not os.path.isdir(base) or not name or re.search(r'[\\/:*?"<>|]', name):
        raise HTTPException(400, "資料夾名稱不合法")
    d = os.path.join(base, name)
    os.makedirs(d, exist_ok=True)
    return {"path": d}


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
    res = check_text.check_file(p, wl)
    rel = project.rel_of(d, p)
    if rel.startswith(("正文", "候選")):
        res["問題"] += shared.style_deviation_findings(d, project.read_text(p))
    return res


# ---------------------------------------------------------------------------
# 候選稿
# ---------------------------------------------------------------------------
@app.post("/api/books/{book_id}/candidate/{no}/accept")
def accept(book_id: str, no: int, provider: str = None):
    d = book_dir(book_id)
    _guard_pipeline(book_id)
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
    _guard_pipeline(book_id)
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
def launch_job(book_id, d, action, params, prov, resume=None, text=None):
    """建立並啟動一個任務（面板按鈕和整章自動流程共用）。失敗時丟 HTTPException。"""
    try:
        if action == "reply":
            title, prompt = "回覆", text or ""
        else:
            title, prompt = actions.build(action, params or {}, book_id)
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(400, "參數不完整：%s" % e)
    if not prompt.strip():
        raise HTTPException(400, "指令是空的")
    try:
        if action in CLAUDE_SPECIAL and prov.get("type") == "claude_code":
            return RUNNER.start(CLAUDE_SPECIAL[action](book_id, d, prov, params or {}))
        return RUNNER.start(runner_mod.Job(book_id, d, title, prompt, resume=resume, provider=prov,
                                           meta={"action": action, "params": params or {}}))
    except RuntimeError as e:
        raise HTTPException(409, str(e))


def _guard_pipeline(book_id):
    if PIPES.active(book_id):
        raise HTTPException(409, "這本書正在跑整章自動流程，請等它結束或先停止流程。")


@app.post("/api/books/{book_id}/jobs")
async def start_job(book_id: str, req: Request):
    d = book_dir(book_id)
    _guard_pipeline(book_id)
    body = await req.json()
    action = body.get("action", "free")
    resume = body.get("resume")
    prov = get_provider(body.get("provider"))
    if resume and body.get("resume_provider") and body["resume_provider"] != prov["id"]:
        prov = get_provider(body["resume_provider"])   # 接續對話一定用原本的執行者
    params = body.get("params") or {}
    return launch_job(book_id, d, action, params, prov, resume=resume, text=params.get("text", "")).to_dict()


# ---------------------------------------------------------------------------
# 整章自動流程
# ---------------------------------------------------------------------------
def _pipe_hooks(book_id, d, prov_id):
    def launch(action, params, pid=None):
        return launch_job(book_id, d, action, params, get_provider(pid or prov_id))
    return {"launch": launch, "cancel": RUNNER.cancel, "checker": check_text,
            "busy": lambda: RUNNER.running_for(book_id) is not None}


def _pipe_view(book_id, d):
    p = PIPES.get(book_id) or PIPES.restore(book_id, d, _pipe_hooks(book_id, d, CONFIG.get("default_provider")))
    return p.to_dict() if p else None


@app.get("/api/books/{book_id}/pipeline")
def pipeline_get(book_id: str):
    d = book_dir(book_id)
    return {"pipeline": _pipe_view(book_id, d), "steps": [{"key": k, "label": v} for k, v in pipeline.STEPS],
            "severities": revision.SEVERITIES,
            "defaults": {"severities": CONFIG.get("pipeline_severities") or pipeline.DEFAULT_SEVERITIES,
                         "mode": CONFIG.get("pipeline_mode") or "stop",
                         "step_providers": CONFIG.get("pipeline_providers") or {}},
            "ai_steps": pipeline.AI_STEPS}


@app.post("/api/books/{book_id}/pipeline")
async def pipeline_start(book_id: str, req: Request):
    d = book_dir(book_id)
    body = await req.json()
    if PIPES.active(book_id):
        raise HTTPException(409, "這本書已經有整章自動流程在執行")
    if RUNNER.running_for(book_id):
        raise HTTPException(409, "還有任務在執行，請等它結束再開始。")
    try:
        a = int(body.get("from"))
        b = int(body.get("to") or a)
    except (TypeError, ValueError):
        raise HTTPException(400, "請輸入章號")
    a, b = min(a, b), max(a, b)
    if a < 1:
        raise HTTPException(400, "章號要從 1 開始")
    if b - a >= 50:
        raise HTTPException(400, "一次最多 50 章")
    texts = project._scan_dir(os.path.join(d, "正文"))
    cands = project._scan_dir(os.path.join(d, "候選"))
    done = [n for n in range(a, b + 1) if n in texts and n not in cands]
    if done:
        raise HTTPException(400, "這些章節已經定稿了：%s。整章自動流程只處理還沒定稿的章節（已有候選稿的會從核對開始）。"
                            % "、".join("第%d章" % n for n in done))
    prov = get_provider(body.get("provider"))
    mode = body.get("mode") or CONFIG.get("pipeline_mode") or "stop"
    sev = body.get("severities")
    if sev is None:
        sev = CONFIG.get("pipeline_severities") or pipeline.DEFAULT_SEVERITIES
    ids = {x.get("id") for x in CONFIG.get("providers") or []}
    sp = body.get("step_providers")
    if sp is None:
        sp = CONFIG.get("pipeline_providers") or {}
    missing = [v for v in (sp or {}).values() if v and v not in ids]
    if missing:
        raise HTTPException(400, "步驟指定的執行者不存在：%s，請到設定修改。" % "、".join(missing))
    p = pipeline.Pipeline.create(book_id, d, _pipe_hooks(book_id, d, prov["id"]), a, b, mode, sev, prov["id"], body.get("note"),
                                 pipeline.clean_step_providers(sp, ids))
    try:
        PIPES.put(p)
    except pipeline.PipelineError as e:
        raise HTTPException(409, str(e))
    p.start()
    return {"pipeline": p.to_dict()}


@app.post("/api/books/{book_id}/pipeline/rewind")
async def pipeline_rewind(book_id: str, req: Request):
    """從某一步重跑：還原到那一步開始前的候選稿，之後的紀錄先備份再清掉，然後開始跑。"""
    d = book_dir(book_id)
    body = await req.json()
    _pipe_view(book_id, d)
    p = PIPES.get(book_id)
    if not p:
        raise HTTPException(404, "沒有流程")
    if RUNNER.running_for(book_id):
        raise HTTPException(409, "還有任務在執行，請等它結束再重跑。")
    try:
        p.rewind(str(body.get("step") or ""), body.get("note") or "")
    except pipeline.PipelineError as e:
        raise HTTPException(400, str(e))
    if body.get("provider"):
        p.s["provider"] = get_provider(body["provider"])["id"]
    p.h = _pipe_hooks(book_id, d, p.s["provider"])
    p.start()
    return {"pipeline": p.to_dict()}


@app.get("/api/books/{book_id}/pipeline/rewind_check")
def pipeline_rewind_check(book_id: str):
    """每一步能不能退回（給流程頁決定要不要顯示按鈕）。"""
    d = book_dir(book_id)
    _pipe_view(book_id, d)
    p = PIPES.get(book_id)
    if not p:
        return {"steps": {}}
    return {"steps": {k: dict(zip(("ok", "why"), p.can_rewind(k))) for k, _ in pipeline.STEPS},
            "note_steps": list(pipeline.NOTE_STEPS)}


@app.post("/api/books/{book_id}/pipeline/resume")
async def pipeline_resume(book_id: str, req: Request):
    """從停下來（失敗、停止）的那一步繼續；暫停（每章停）時開始下一章。"""
    d = book_dir(book_id)
    body = await req.json()
    _pipe_view(book_id, d)
    p = PIPES.get(book_id)
    if not p:
        raise HTTPException(404, "沒有可以繼續的流程")
    if p.s["status"] == "running":
        raise HTTPException(409, "流程正在執行")
    if p.s["status"] == "done":
        raise HTTPException(400, "流程已經全部完成")
    if RUNNER.running_for(book_id):
        raise HTTPException(409, "還有任務在執行，請等它結束再繼續。")
    if body.get("provider"):
        p.s["provider"] = get_provider(body["provider"])["id"]
    if body.get("mode") in ("stop", "continue"):
        p.s["mode"] = body["mode"]
    if p.s["status"] == "paused" and p.s["chapter"] > p.s["to"]:
        p.s["to"] = p.s["chapter"]
    p.h = _pipe_hooks(book_id, d, p.s["provider"])
    p.start()
    return {"pipeline": p.to_dict()}


@app.post("/api/books/{book_id}/pipeline/stop")
def pipeline_stop(book_id: str):
    book_dir(book_id)
    p = PIPES.get(book_id)
    if not p or p.s["status"] != "running":
        raise HTTPException(400, "沒有執行中的流程")
    p.stop()
    return {"ok": True}


@app.post("/api/books/{book_id}/pipeline/clear")
def pipeline_clear(book_id: str):
    d = book_dir(book_id)
    p = PIPES.get(book_id)
    if p and p.s["status"] == "running":
        raise HTTPException(409, "流程正在執行，請先停止")
    PIPES.pipes.pop(book_id, None)
    sp = os.path.join(d, ".studio", "流程", "目前.json")
    if os.path.isfile(sp):
        os.remove(sp)
    return {"ok": True}


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
