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
import secrets
import subprocess
import sys
import threading
import time
import traceback
import webbrowser

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from urllib.parse import quote, urlsplit
from fastapi.staticfiles import StaticFiles
import uvicorn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from studio import actions, bible_index, comfy, context, contract, drift, export, fidelity, fingerprint, forge, goals, illust, importer, jsonkeys, lang as lang_mod, native, native_files, project, prompts, providers, pipeline, reader_ledger, recovery, relations, reverse, revision, runner as runner_mod, sdna, search, shared, spawn, spinoff, style_design, textguard, tracking, upcheck, volume, wb_check  # noqa: E402

VERSION = "1.18.0"
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
    "pipeline_style_check": True,       # 整章自動流程：跑不跑「文風檢查」（本機計算，不花錢）
    "style_retry": True,                # 寫稿／去 AI 味後，文風偏離太多就帶數字重寫一次
    "recall": True,                     # 檢索式記憶：把作者寫過的相似段落注入寫稿上下文
    "recall_paragraphs": 6,             # 檢索注入幾個段落
    "autopilot_every": 0,               # 自動駕駛：每幾章停下來檢查一次（0＝不檢查）
    "autopilot_stop_must": 1,           # 檢查點：累計幾個「必須修」就停
    "autopilot_stop_style": 2.4,        # 檢查點：文風偏離幾倍就停（閘門 1.2 的兩倍）
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
    """寫設定檔：先寫 .tmp 再換掉，避免寫到一半斷電／被同步程式鎖住時留下半個 JSON。"""
    with _cfg_lock:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CONFIG_PATH)


def save_config_or_400(cfg):
    """存設定；失敗時回 400 加原因（而不是讓它變成 HTTP 500 的一頁 traceback）。"""
    try:
        save_config(cfg)
    except OSError as e:
        raise HTTPException(400, "設定存不起來（%s）：%s。請確認工作台資料夾可以寫入。"
                            % (CONFIG_PATH, getattr(e, "strerror", None) or e))


CONFIG = load_config()
# 檢查工具（內建 novel-deslop skill 的 check_text.py）
_spec = importlib.util.spec_from_file_location(
    "check_text", os.path.join(PLUGIN_DIR, "skills", "novel-deslop", "scripts", "check_text.py"))
check_text = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_text)
check_text = textguard.wrap(check_text)   # 英文、日文正文改用 plugin-en／plugin-ja 的檢查；繁中正文行為不變

RUNNER = runner_mod.Runner(lambda: CONFIG, HERE, PLUGIN_DIR, check_text)
PIPES = pipeline.Manager()
CLAUDE_SPECIAL = {}   # 動作 → 建立 Claude Code 特殊任務的函式（各函式定義後登記）


def get_provider(pid=None):
    """pid 可以是「執行者」或「執行者/模型」（例如 deepseek/deepseek-v4-pro）。"""
    pid = pid or CONFIG.get("default_provider") or "claude_code"
    p = providers.resolve(CONFIG.get("providers") or [], pid)
    if p:
        return p
    base = pid.partition("/")[0]
    if base != pid and providers.resolve(CONFIG.get("providers") or [], base):
        raise HTTPException(400, "執行者「%s」的模型清單裡沒有「%s」（可能已經從設定刪掉），請重新選擇。" % (base, pid.partition("/")[2]))
    raise HTTPException(400, "找不到執行者：%s" % pid)


def provider_ids():
    return {c["id"] for c in providers.choices(CONFIG.get("providers") or [])}

app = FastAPI(title="小說工作台")

# ---------------------------------------------------------------------------
# 變更端點的守門（報告 S2）
# 只綁 127.0.0.1 擋不住瀏覽器的 CSRF 與 DNS rebinding，所以：
#   1. 變更方法（POST／PUT／DELETE…）只接受「同來源」請求：Origin 的 host 要等於這次的 Host，
#      Sec-Fetch-Site 要是 same-origin／none。
#   2. 變更方法還要帶一次性權杖 X-NS-Token：每次啟動產生，由 index() 注入頁面，
#      前端在 index.html 載入時包一層 fetch 自動加上（見 TOKEN_JS）。
# 這兩道都不影響 GET／SSE；直接用 curl 打 API 的腳本要自己帶權杖（重新啟動就失效）。
# ---------------------------------------------------------------------------
MUTATE_TOKEN = secrets.token_urlsafe(32)
TOKEN_HEADER = "x-ns-token"
SAFE_METHODS = frozenset(["GET", "HEAD", "OPTIONS"])
TOKEN_JS = (
    "window.__NS_TOKEN__=%s;(function(){var f=window.fetch;window.fetch=function(u,o){"
    "o=o||{};var h=new Headers(o.headers||{});h.set('X-NS-Token',window.__NS_TOKEN__);"
    "o.headers=h;return f(u,o)};})();" % json.dumps(MUTATE_TOKEN)
)


def same_origin(request):
    """請求是不是同一個來源（擋跨站表單與 DNS rebinding）。"""
    site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if site and site not in ("same-origin", "none"):
        return False
    origin = request.headers.get("origin")
    if not origin:
        return True          # 老瀏覽器不送 Origin：還是要靠下面的權杖
    return urlsplit(origin).netloc.lower() == (request.headers.get("host") or "").lower()


@app.middleware("http")
async def guard_mutations(request: Request, call_next):
    if request.method not in SAFE_METHODS:
        if not same_origin(request):
            return JSONResponse({"error": "拒絕跨來源的變更請求（請從工作台頁面操作）"}, status_code=403)
        if not secrets.compare_digest(request.headers.get(TOKEN_HEADER, "") or "", MUTATE_TOKEN):
            return JSONResponse({"error": "請求權杖不正確，請重新整理頁面再試一次"}, status_code=403)
    return await call_next(request)



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
    except PermissionError as e:
        # 最常見的原因：用「放在工作區裡的 .venv」啟動，那個 python 寫不進書庫外的資料夾。
        # 直接給能動的解法，不要把 traceback 丟給作者。
        raise HTTPException(400, "沒有權限寫入這個檔案：%s\n\n"
                                 "如果是「用專案裡的 .venv 啟動、書庫在專案外」的情況，這個 python 會被限制在專案資料夾裡。"
                                 "請改用外部虛擬環境啟動：\n"
                                 "  set NS_VENV=C:\\Users\\你\\venvs\\novel-studio\n"
                                 "  start.bat\n"
                                 "（目前用的 python：%s）" % (getattr(e, "filename", "?"), sys.executable))


# 審查與修訂只處理書裡的這幾種稿子（報告 S1：不要把用戶端送來的路徑直接拼成檔案路徑）
REVIEWABLE_DIRS = ("正文", "候選", "設定")


def book_path(d, rel, must_exist=True):
    """用戶端送來的相對路徑 → 驗證過的書內相對路徑（限 正文／候選／設定）。"""
    if not isinstance(rel, str) or not rel.strip():
        raise HTTPException(400, "缺少要處理的檔案路徑")
    full = wrap(lambda: project.safe_path(d, rel.strip()))
    rel_norm = project.rel_of(d, full)
    if rel_norm.split("/")[0] not in REVIEWABLE_DIRS:
        raise HTTPException(400, "只能指定 %s 底下的檔案：%s" % ("、".join(x + "/" for x in REVIEWABLE_DIRS), rel))
    if must_exist and not os.path.isfile(full):
        raise HTTPException(404, "找不到檔案：%s" % rel)
    return rel_norm


@app.exception_handler(HTTPException)
async def http_err(request, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled(request, exc):
    """沒預期的例外：後端視窗印完整堆疊，前端拿到一句人話（而不是只有「HTTP 500」）。"""
    traceback.print_exc()
    print("↑ 上面是 %s %s 的完整堆疊" % (request.method, request.url.path), flush=True)
    # Python 3.11+ 會把同步端點的例外包成 ExceptionGroup，訊息要先剝到真正那一層才有用
    root, hops = exc, 0
    while hasattr(root, "exceptions") and getattr(root, "exceptions", None) and hops < 5:
        root, hops = root.exceptions[0], hops + 1
    return JSONResponse({"error": "工作台內部錯誤（%s：%s）。完整堆疊在後端視窗，請把它貼給開發者。"
                                 % (type(root).__name__, str(root)[:200])}, status_code=500)


# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
@app.get("/api/config")
def get_config():
    exe = runner_mod.find_claude(CONFIG.get("claude_cmd"))
    # choices：所有「執行者＋模型」的選項（前端下拉選單用；不寫回設定檔）
    return {"config": dict(CONFIG, choices=providers.choices(CONFIG.get("providers") or [])), "claude_found": exe, "version": VERSION,
            "port": int(CONFIG.get("port", 8765)), "running_port": RUNNING_PORT, "can_restart": SERVER is not None,
            "library_exists": os.path.isdir(CONFIG.get("library") or ""),
            "key_status": {p["id"]: providers.key_status(HERE, p) for p in CONFIG.get("providers") or []},
            "key_store": providers.store_name(), "secrets_pending": providers.pending_secrets(HERE)}


@app.post("/api/config")
async def set_config(req: Request):
    body = await req.json()
    for k in ("library", "claude_cmd", "model", "permission_mode", "allowed_tools", "add_dirs",
              "stale_foreshadow", "stale_character", "default_provider",
              "reconcile_before_write", "goal_check_after_write", "pipeline_severities", "pipeline_mode",
              "pipeline_style_check", "style_retry", "recall", "recall_paragraphs",
              "autopilot_every", "autopilot_stop_must", "autopilot_stop_style"):
        if k in body:
            CONFIG[k] = body[k]
    if "pipeline_providers" in body:
        CONFIG["pipeline_providers"] = pipeline.clean_step_providers(body.get("pipeline_providers"), provider_ids())
    if "port" in body:
        try:
            port = int(body["port"])
        except (TypeError, ValueError):
            raise HTTPException(400, "連接埠要是數字")
        if not 1024 <= port <= 65535:
            raise HTTPException(400, "連接埠要在 1024～65535 之間")
        CONFIG["port"] = port
    if body.get("create_library") and CONFIG.get("library"):
        lib = CONFIG["library"]
        try:
            os.makedirs(lib, exist_ok=True)
        except OSError as e:
            raise HTTPException(400, "書庫資料夾建不起來（%s）：%s。請確認這個路徑存在、而且是工作台有權寫入的位置。"
                                % (lib, getattr(e, "strerror", None) or e))
        if not os.path.isdir(lib):
            raise HTTPException(400, "書庫路徑不是資料夾：%s" % lib)
    save_config_or_400(CONFIG)
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
        if pid != "llamacpp":
            clean["models"] = providers.clean_models(p.get("models"), providers.STAGES, providers.EFFORTS)
        keep.append(clean)
        seen.add(pid)
    CONFIG["providers"] = keep
    for pid, key in (body.get("keys") or {}).items():
        if key is not None:
            try:
                providers.save_secret(HERE, pid, key.strip())
            except Exception as e:      # 金鑰庫不可用（憑證管理員被鎖、keyring 後端壞掉……）
                raise HTTPException(400, "金鑰存不起來（%s）：%s。可以改用環境變數 %s，或寫進 secrets.json。"
                                    % (pid, e, (providers.resolve(keep, pid) or {}).get("key_env") or "（見執行者設定）"))
    save_config_or_400(CONFIG)
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
    lang = lang_mod.book_lang(d)
    prompts.set_lang(lang)
    no = int(params.get("chapter"))
    _, card = context.card_text(d, no)
    gl = goals.freeze_goals(card)
    rel = context.chapter_text(d, no, ("候選",))[0] if params.get("candidate") else goals.target(d, no, True)[0]
    if not gl or not rel:
        raise HTTPException(400, "第%d章沒有章綱情節點或沒有正文，無法核對。" % no)
    prompt = (goals.build_prompt(no, gl, prompts.t(lang, "claude_read_only", rel=rel)) +
              "\n" + prompts.t(lang, "json_last_only"))
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
    prompts.set_lang(lang_mod.book_lang(d))     # 請求執行緒：後面組提示詞與檢查都要用這本書的語言
    no = int(params.get("chapter"))
    if params.get("path"):
        rel = book_path(d, params.get("path"))          # 用戶端指定稿子：一律驗證在 正文／候選／設定 底下
    else:
        rel = context.chapter_text(d, no, ("候選",))[0] if params.get("candidate") else goals.target(d, no, True)[0]
    if not rel:
        raise HTTPException(400, "第%d章沒有可以審查的稿子" % no)
    lang = lang_mod.book_lang(d)
    note = (params.get("note") or "").strip()
    prompt = prompts.t(lang, "claude_review_at", n=no, rel=rel,
                       note=(prompts.pack(lang)["author_req"] + note) if note else "")
    prompt += "\n" + revision.review_schema() + "\n" + prompts.t(lang, "json_last_only")
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
    prompts.set_lang(lang_mod.book_lang(d))     # 同上：修訂稿的提示詞與檢查都依這本書的語言
    no = int(params.get("chapter"))
    rv = revision.load_review(d, no)
    notes = revision.notes_text(rv, params.get("ids") or [], params.get("extra") or "")
    if not notes:
        raise HTTPException(400, "請至少勾選一條審查意見，或寫下你自己的修改意見。")
    rel = (rv or {}).get("path")
    rel = book_path(d, rel) if rel else goals.target(d, no, True)[0]
    if not rel:
        raise HTTPException(400, "第%d章沒有可以修訂的稿子" % no)
    draft = ".studio/修訂/第%03d章.draft.md" % no
    prompt = prompts.t(lang_mod.book_lang(d), "claude_revise_at", n=no, rel=rel, notes=notes, draft=draft)
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
    lang = lang_mod.book_lang(d)
    prompt = prompts.t(lang, "recover_continue", n=no, rid=rec["id"], ch="第%03d章" % no, rule=actions.candidate_rule(lang))
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
            "books": _book_list(),
            "book_langs": {b: lang_mod.book_lang(book_dir(b)) for b in _book_list()}}   # 套用時，語言不同的書要標出來


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
    # 語言：用某本書的正文當樣本就是那本書的語言，其他（貼上、上傳、空白範本）用選的語言
    lang = lang_mod.book_lang(book_dir(body.get("book") or "")) if src == "book" else lang_mod.normalize(body.get("lang"))
    prompts.set_lang(lang)      # 文字指標與範本都依這個語言挑
    text, names = _sample_text(body)
    if text:
        wrap(lambda: shared.analyze(text, names))  # 樣本太短時先報錯
    return wrap(lambda: shared.create_style(lib, body.get("name"), sample_text=text, exclude=names, lang=lang))


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
    lang = lang_mod.normalize(body.get("lang") or prompts.cur_lang())
    params["lang"] = lang          # 共用庫沒有「書的語言」：任務照介面選的語言組提示詞
    prompts.set_lang(lang)
    title = actions.build("style_design", params, shared.SHARED, lang=lang)[0]
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
    return wrap(lambda: shared.new_structure(library(), body.get("name"), lang=body.get("lang")))


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
        importer.set_import_lang(d, opts.get("lang"))   # 先記語言，骨架（_範本/文風.md 等）、CLAUDE.md 與之後的提示詞才會用對的語言
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
            "sheet_error": err, "providers": [{"id": c["id"], "name": c["name"], "type": c["type"]}
                                              for c in providers.choices(CONFIG.get("providers") or [])]}


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
    save_config_or_400(CONFIG)
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
                   negative=p.get("negative") or comfy.MOSS_NEGATIVE, allow_text=True)
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
        if prof.get("kind") == "moss" and illust.clean_texts(draft.get("texts")):
            meta["texts"] = illust.clean_texts(draft.get("texts"))
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
    lang = lang_mod.book_lang(d)
    prompts.set_lang(lang)
    try:
        kind, passage, chars, places = native.illust_inputs(d, params)
    except (native.NativeError, project.ProjectError) as e:
        raise HTTPException(400, str(e))
    system, user = illust.ai_scene_prompt(d, params.get("target"), passage, chars, places, kind)
    prompt = system + "\n\n" + user + "\n\n" + prompts.t(lang, "json_no_files_tail")
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
    lang = lang_mod.book_lang(d)
    prompts.set_lang(lang)
    f = params.get("file") or ""
    text = context.read(d, f)
    if not text:
        raise HTTPException(400, "找不到 %s" % f)
    system, user = illust.ai_card_prompt(text, os.path.splitext(os.path.basename(f))[0], f.split("/")[1])
    prompt = system + "\n\n" + user + "\n\n" + prompts.t(lang, "json_no_files_tail")
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


def claude_reader_job(book_id, d, prov, params):
    if not project.read_table(d, "追蹤/時間線.md")["rows"]:
        raise HTTPException(400, "這本書還沒有時間線，沒有東西可以轉換")
    job = runner_mod.Job(book_id, d, "從時間線建立讀者認知", reader_ledger.claude_prompt(d), provider=prov,
                         meta={"action": "reader_init", "params": params})

    def after(j):
        try:
            data = providers.parse_json(j.result or "")
        except providers.ProviderError as e:
            raise RuntimeError("無法解析 Claude 回傳的結果：%s" % e)
        j.result = reader_ledger.save_draft(d, reader_ledger.merge([jsonkeys.to_zh(data)]))
        j.emit("result", text=j.result)
    job.after = after
    return job


def claude_reader_recon_job(book_id, d, prov, params):
    try:
        prompt = reader_ledger.recon_claude_prompt(d)
    except project.ProjectError as e:
        raise HTTPException(400, str(e))
    job = runner_mod.Job(book_id, d, "比對讀者認知回收", prompt, provider=prov, meta={"action": "reader_reconcile", "params": params})

    def after(j):
        try:
            data = providers.parse_json(j.result or "")
        except providers.ProviderError as e:
            raise RuntimeError("無法解析 Claude 回傳的結果：%s" % e)
        j.result = reader_ledger.apply_recon(d, [jsonkeys.to_zh(data)])
        j.emit("result", text=j.result)
    job.after = after
    return job


def claude_deslop_job(book_id, d, prov, params):
    """Claude Code 去 AI 味：不改原稿，改好的全文寫到暫存檔，工作台建立逐段對照（或流程裡直接全部套用）。"""
    no = int(params.get("chapter"))
    where = ("候選",) if params.get("candidate") else ("正文",)
    rel, base_text = context.chapter_text(d, no, where)
    if not base_text:
        raise HTTPException(400, "第%d章沒有%s" % (no, where[0] if where[0] == "正文" else "候選稿"))
    pending = revision.load_revision(d, no)
    if pending and not params.get("auto_apply"):
        raise HTTPException(409, "第%d章還有一份待確認的修訂。請先到章節頁的「修訂對照」套用或捨棄，再去 AI 味。" % no)
    draft = ".studio/修訂/第%03d章.draft.md" % no
    note = (params.get("note") or "").strip()
    lang = lang_mod.book_lang(d)
    prompts.set_lang(lang)
    prompt = prompts.t(lang, "claude_deslop_at", n=no, rel=rel, draft=draft,
                       note=(prompts.pack(lang)["author_req"] + note) if note else "",
                       table=prompts.t(lang, "change_table_rule"))
    job = runner_mod.Job(book_id, d, "去AI味 第%d章" % no, prompt, provider=prov, meta={"action": "deslop", "params": params})

    def after(j):
        p = os.path.join(d, draft)
        if not os.path.isfile(p):
            raise RuntimeError("Claude 沒有產生去 AI 味的稿子（%s）。" % draft)
        new_text = project.read_text(p)
        os.remove(p)
        if pending:
            revision.discard_revision(d, no)
        title = native._split_output(new_text, no, native._card_title(d, no))[0]
        fixed, _ = check_text.fix_punct(new_text)
        j.result = native.deslop_result(d, book_id, no, rel, base_text, title, fixed, j.result or "", prov.get("id"),
                                        auto_apply=bool(params.get("auto_apply")), checker=check_text)
        j.emit("result", text=j.result)
    job.after = after
    return job


CLAUDE_SPECIAL.update({"deslop": claude_deslop_job})
CLAUDE_SPECIAL.update({"reader_init": claude_reader_job, "reader_reconcile": claude_reader_recon_job})
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
    mode = str(body.get("mode") or "interview").strip()
    if mode not in ("interview", "skeleton"):
        raise HTTPException(400, "開書方式不對")
    ref = (body.get("ref") or "").strip()
    if mode == "skeleton" and not ref:
        raise HTTPException(400, "用參考書骨架直接開書，要先選一本參考書")
    prov = get_provider(body.get("provider"))
    if mode == "skeleton" and prov.get("type") == "claude_code":
        raise HTTPException(400, "用骨架直接開書要走 API 的執行者（Claude Code 不行），請先切換執行者。")
    os.makedirs(lib, exist_ok=True)
    d = wrap(lambda: project.create_book(lib, body.get("name", "")))
    name = os.path.basename(d)
    lang_mod.set_book_lang(d, body.get("lang"))   # 先記下這本書的語言，開書訪談的指令與之後的所有提示詞才會用對的語言
    if mode == "skeleton":            # 先把空白範本建好，之後套用骨架時才有檔案可備份、覆寫
        wrap(lambda: native_files.ensure_skeleton(d, PLUGIN_DIR))
    seeded = []
    if ref:                          # 參考書（P6）：把它的風格指標與章節結構補進新書，全程不呼叫模型
        try:
            ref_dir = book_dir(ref)
            prompts.set_lang(lang_mod.book_lang(ref_dir))
            fp = fingerprint.build(ref_dir)          # 指紋很貴（大書 10 秒以上）：只算一次，DNA 直接重用
            seeded = spawn.seed(d, name, fp, sdna.build(ref_dir, fp), source=ref)
        except Exception as e:       # 參考書讀不到不該讓「開新書」失敗
            print("（參考書 seed 失敗：%s）" % e, flush=True)
        finally:
            prompts.set_lang(lang_mod.book_lang(d))
    job = None
    if mode != "skeleton" and body.get("start_setup", True):
        params = {"idea": body.get("idea", "")}
        title, prompt = actions.build("setup_new", params, name, lang=lang_mod.book_lang(d))
        job = RUNNER.start(runner_mod.Job(name, d, title, prompt, meta={"action": "setup_new", "params": params},
                                          provider=prov))
    return {"id": name, "job": job.to_dict() if job else None, "seeded": seeded, "mode": mode}


SPINOFF_TASKS = {}
SPINOFF_LOCK = threading.Lock()
SPINOFF_KEEP = 20


def _spinoff_put(tid, state):
    with SPINOFF_LOCK:
        SPINOFF_TASKS[tid] = state
        while len(SPINOFF_TASKS) > SPINOFF_KEEP:
            SPINOFF_TASKS.pop(next(iter(SPINOFF_TASKS)))


def _spinoff_get(tid):
    with SPINOFF_LOCK:
        st = SPINOFF_TASKS.get(tid)
        return dict(st) if st else None


@app.post("/api/books/{book_id}/spinoff")
async def spinoff_start(book_id: str, req: Request):
    """開始用參考書產生故事骨架（背景執行；用 GET …/spinoff/{task} 看進度）。"""
    d = book_dir(book_id)
    body = await req.json()
    source = (body.get("source") or "").strip()
    if not source:
        raise HTTPException(400, "請先選一本參考書")
    src = book_dir(source)
    if os.path.normpath(src) == os.path.normpath(d):
        raise HTTPException(400, "參考書不能是同一本")
    prov = get_provider(body.get("provider"))
    if prov.get("type") == "claude_code":
        raise HTTPException(400, "產生骨架要走 API 的執行者（Claude Code 不行），請在右側面板上方切換。")
    note = (body.get("note") or "").strip()
    apply = bool(body.get("apply"))
    if apply:
        # 「用骨架直接開書」只給還沒有 CLAUDE.md 的新書；已經有專案的書不能整包覆蓋。
        p = os.path.join(d, "CLAUDE.md")
        if os.path.isfile(p):
            try:
                old = project.read_text(p)
            except OSError:
                old = ""
            if "用參考書骨架直接開書" not in old:
                raise HTTPException(409, "這本書已經是專案，不能用『直接開書』覆蓋。")
        wrap(lambda: native_files.ensure_skeleton(d, PLUGIN_DIR))
    tid = secrets.token_hex(8)
    state = {"id": tid, "book": book_id, "status": "running", "stage": "排隊中…",
             "error": "", "result": None, "started": time.time()}
    _spinoff_put(tid, state)

    def run():
        try:
            lang = lang_mod.book_lang(d)
            prompts.set_lang(lang)
            data = spinoff.generate(prov, src, note, lang=lang, progress=lambda msg: state.update(stage=msg))
            rel = spinoff.save(d, data)
            applied = (spinoff.apply_new(d, data, title=book_id, lang=lang, source=source)
                       if apply else None)
            state.update(status="done", stage="完成",
                         result={"draft": rel, "preview": spinoff.show(data),
                                 "guard": data.get("護欄") or {}, "applied": applied})
        except SystemExit as e:
            state.update(status="error", error=str(e))
        except providers.ProviderError as e:
            state.update(status="error", error="模型回覆有問題：%s" % e)
        except project.ProjectError as e:
            state.update(status="error", error="套用失敗：%s" % e)
        except Exception as e:      # 背景執行緒：不要讓例外默默消失
            state.update(status="error", error="產生失敗：%s" % e)
        finally:
            prompts.set_lang(lang_mod.book_lang(d))

    threading.Thread(target=run, daemon=True).start()
    return {"task": tid, "stage": state["stage"]}


@app.get("/api/books/{book_id}/spinoff/{task_id}")
def spinoff_status(book_id: str, task_id: str):
    st = _spinoff_get(task_id)
    if not st or st.get("book") != book_id:
        raise HTTPException(404, "找不到這個骨架任務")
    st["elapsed"] = round(time.time() - float(st.get("started") or time.time()), 1)
    st.pop("started", None)
    return st


@app.get("/api/books/{book_id}/drift")
def drift_report(book_id: str, from_: int = Query(None, alias="from"), to: int = None):
    """卷末體檢：本機計算的漂移報告（不呼叫模型）。"""
    d = book_dir(book_id)
    prompts.set_lang(lang_mod.book_lang(d))
    info = drift.drift(d, from_, to)
    return {"report": drift.report_md(d, info), "findings": drift.findings(info),
            "range": info["range"], "count": len(drift.findings(info))}


@app.post("/api/books/{book_id}/drift/plan")
async def drift_plan(book_id: str, req: Request):
    """用模型產生「卷綱更新」草稿（只送摘要與卷綱，約 1 次呼叫）。"""
    d = book_dir(book_id)
    body = await req.json()
    a, b = int(body.get("from") or 1), int(body.get("to") or 1)
    prov = get_provider(body.get("provider"))
    if prov.get("type") == "claude_code":
        raise HTTPException(400, "產生卷綱草稿要走 API 的執行者（Claude Code 不行）。")
    prompts.set_lang(lang_mod.book_lang(d))
    info = await run_in_threadpool(drift.drift, d, a, b)
    res = await run_in_threadpool(drift.llm_pass, prov, d, info)
    if res.get("error"):        # 失敗不存草稿：不然「附加」會把失敗訊息寫進卷綱
        return {"plan_md": "", "draft": "", "volume_file": drift.volume_rel(d, b),
                "error": res["error"]}
    text = drift.plan_md(res, a, b)
    rel = drift.save_plan(d, a, b, text)
    return {"plan_md": text, "draft": rel, "volume_file": drift.volume_rel(d, b), "error": ""}


@app.post("/api/books/{book_id}/drift/apply")
async def drift_apply(book_id: str, req: Request):
    """把草稿附加到卷綱（原檔先備份；只附加、不覆蓋）。"""
    d = book_dir(book_id)
    body = await req.json()
    a, b = int(body.get("from") or 1), int(body.get("to") or 1)
    draft = (body.get("draft") or "").strip()
    if not draft:
        raise HTTPException(400, "沒有草稿可以附加")
    p = wrap(lambda: project.safe_path(d, draft))
    if not os.path.isfile(p) or not draft.startswith(("候選/", "大綱/草稿/")):
        raise HTTPException(400, "草稿路徑不對：%s" % draft)
    rel, bak = wrap(lambda: drift.apply_plan(d, b, project.read_text(p), a, b))
    return {"volume_file": rel, "backup": os.path.basename(bak or "")}


# ---------------------------------------------------------------------------
# 各語言的示範書：語言 → (demo/ 底下的資料夾, 放進書庫後的名稱)
DEMO_BOOKS = {
    "zh-TW": ("退婚之後", "退婚之後（示範）"),
    "en": ("en_TheLanternRoad", "The Lantern Road (Demo)"),
    "ja": ("ja_辺境の薬師と竜の約束", "辺境の薬師と竜の約束（サンプル）"),
}


@app.post("/api/demo")
async def add_demo(req: Request):
    import shutil
    try:
        body = await req.json()
    except Exception:
        body = {}          # 舊版前端不送內容：維持繁中示範書
    lang = lang_mod.normalize((body or {}).get("lang"))
    lib = CONFIG.get("library")
    if not lib:
        raise HTTPException(400, "請先設定書庫資料夾")
    try:
        os.makedirs(lib, exist_ok=True)
    except OSError as e:
        raise HTTPException(400, "書庫資料夾建不起來（%s）：%s。請確認這個路徑存在、而且工作台有寫入權限。"
                            % (lib, e.strerror or e))
    src_name, dst_name = DEMO_BOOKS[lang]
    src = os.path.join(HERE, "demo", src_name)
    dst = os.path.join(lib, dst_name)
    if os.path.exists(dst):
        raise HTTPException(400, "示範書已經在書架上了")
    try:
        shutil.copytree(src, dst)
    except OSError as e:
        # 複製到一半失敗就清掉，避免書架上留下半本書
        shutil.rmtree(dst, ignore_errors=True)
        raise HTTPException(400, "示範書複製失敗（%s → %s）：%s。常見原因是書庫資料夾的寫入權限。"
                            % (src, dst, e.strerror or e))
    return {"id": os.path.basename(dst)}


@app.get("/api/books/{book_id}/overview")
def book_overview(book_id: str):
    d = book_dir(book_id)
    ov = project.overview(d, int(CONFIG.get("stale_foreshadow", 10)), int(CONFIG.get("stale_character", 15)))
    ov["is_book"] = project.is_book(d)
    ov["lang"] = lang_mod.book_lang(d)
    ov["unit"] = lang_mod.count_unit(ov["lang"])      # chars＝字（中日文）、words＝詞（英文）
    wb = wb_check.alerts(d, ov.get("latest") or 0)   # 回寫檢查放在追蹤落後後面、其他提醒前面
    lag = 1 if ov["alerts"] and ov["alerts"][0]["kind"] == "追蹤落後" else 0
    ov["alerts"][lag:lag] = [a for a in wb if a["kind"] == "回寫檢查"]
    ov["alerts"] += [a for a in wb if a["kind"] != "回寫檢查"]
    rv_drafts = sum(len(v) for v in reverse.draft_groups(d).values())
    if rv_drafts and project.list_entries(d, "設定/角色"):
        ov["alerts"].insert(0, {"level": "info", "kind": "設定草稿等你核對", "action": "reverse",
                                "text": "「從正文建立設定」或「整理名詞表」產生了 %d 份草稿，還沒採用或捨棄。" % rv_drafts})
    elif ov.get("latest") and not project.list_entries(d, "設定/角色") and not project.read_table(d, "追蹤/伏筆.md")["rows"]:
        st = reverse.state(d)
        ov["alerts"].insert(0, {"level": "info", "kind": "從正文建立設定", "action": "reverse",
                                "text": ("正文有 %d 章，但還沒有角色與追蹤資料。可以讓 AI 從正文反推設定、大綱與追蹤（先存成草稿）。" % ov["latest"])
                                if not st.get("processed") else "已從正文抽取到第 %d 章%s。" % (
                                    max(st["processed"]), "，草稿等你核對" if any(st["drafts"].values()) else "，還沒跑完")})
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


@app.post("/api/books/{book_id}/lang")
async def set_book_language(book_id: str, req: Request):
    d = book_dir(book_id)
    _guard_book(book_id)
    body = await req.json()
    lang = lang_mod.set_book_lang(d, body.get("lang"))
    return {"lang": lang, "unit": lang_mod.count_unit(lang)}


@app.get("/api/books/{book_id}/chapters")
def book_chapters(book_id: str):
    return project.scan_chapters(book_dir(book_id))


@app.get("/api/books/{book_id}/bible")
def book_bible(book_id: str):
    return project.bible(book_dir(book_id))


@app.post("/api/books/{book_id}/bible/delete")
async def book_bible_delete(book_id: str, req: Request):
    """刪除設定集的一個檔案：不永久刪除，移到 .studio/刪除/，再重建索引。"""
    d = book_dir(book_id)
    body = await req.json()
    rel = str(body.get("path") or "").strip().replace("\\", "/")
    allowed = ("設定/角色/", "設定/勢力/", "設定/世界觀/", "設定/草稿/")
    if not rel or ".." in rel.split("/") or not any(rel.startswith(p) for p in allowed):
        raise HTTPException(400, "只能刪除設定集裡的角色、勢力、世界觀或草稿。")
    p = wrap(lambda: project.safe_path(d, rel))
    if not os.path.isfile(p):
        raise HTTPException(404, "找不到這個設定檔")
    trash = os.path.join(d, ".studio", "刪除")
    os.makedirs(trash, exist_ok=True)
    cat = rel.split("/")[1] if len(rel.split("/")) > 2 else "設定"
    base = "%s_%s_%s" % (time.strftime("%Y%m%d-%H%M%S"), cat, os.path.basename(p))
    dst = os.path.join(trash, base)
    i = 2
    while os.path.exists(dst):
        dst = os.path.join(trash, "%s_%d.md" % (os.path.splitext(base)[0], i))
        i += 1
    try:
        os.replace(p, dst)
    except OSError as e:
        raise HTTPException(400, "刪除失敗：%s" % e)
    warn = ""
    try:
        bible_index.rebuild(d)
    except Exception as e:  # 索引是產生物，重建失敗不影響刪除
        warn = "索引重建失敗：%s" % e
    return {"deleted": rel, "moved_to": project.rel_of(d, dst), "warning": warn}


@app.get("/api/books/{book_id}/outline")
def book_outline(book_id: str):
    return project.outline_files(book_dir(book_id))


@app.get("/api/books/{book_id}/volumes")
def book_volumes(book_id: str):
    """卷先行的狀態：正式卷綱、草稿、下一個卷號與建議起始章。"""
    d = book_dir(book_id)
    data = {"volumes": volume.list_volumes(d), "drafts": volume.drafts(d),
            "plans": volume.plan_drafts(d), "revisions": volume.revisions(d),
            "next": volume.next_no(d), "from": volume.next_start(d)}
    # 草稿一產生就要看得到：不要讓瀏覽器拿舊的卷況
    return JSONResponse(data, headers={"Cache-Control": "no-store"})


@app.post("/api/books/{book_id}/volumes/adopt")
async def book_volume_adopt(book_id: str, req: Request):
    """採用卷綱草稿：搬到正式卷綱、狀態改「已確認」。"""
    d = book_dir(book_id)
    body = await req.json()
    try:
        no = int(body.get("volume"))
    except (TypeError, ValueError):
        raise HTTPException(400, "缺少卷號")
    res = wrap(lambda: volume.adopt(d, no))
    return {"rel": res["rel"], "warnings": res["warnings"],
            "volumes": volume.list_volumes(d), "drafts": volume.drafts(d)}


@app.get("/api/books/{book_id}/volumes/revision/{no}")
def book_volume_revision(book_id: str, no: int):
    """修訂草稿與正式卷綱的 diff（給作者看過再套用）。"""
    d = book_dir(book_id)
    info = wrap(lambda: volume.revision_info(d, no))
    if not info:
        raise HTTPException(404, "找不到這一卷的修訂草稿")
    return info


@app.post("/api/books/{book_id}/volumes/revision/apply")
async def book_volume_revision_apply(book_id: str, req: Request):
    """套用修訂草稿：備份正式卷綱、狀態改「已確認」、同步全書大綱，刪掉草稿。"""
    d = book_dir(book_id)
    body = await req.json()
    try:
        no = int(body.get("volume"))
    except (TypeError, ValueError):
        raise HTTPException(400, "缺少卷號")
    res = wrap(lambda: volume.apply_revision(d, no))
    return {"rel": res["rel"], "warnings": res["warnings"],
            "volumes": volume.list_volumes(d), "revisions": volume.revisions(d)}


@app.post("/api/books/{book_id}/volumes/outline-sync")
async def book_volume_outline_sync(book_id: str, req: Request):
    """把已採用的卷綱重新同步進全書大綱（補卷契約；只補不覆蓋）。"""
    d = book_dir(book_id)
    body = await req.json()
    try:
        no = int(body.get("volume"))
    except (TypeError, ValueError):
        raise HTTPException(400, "缺少卷號")
    warnings = wrap(lambda: volume.sync_outline(d, no))
    return {"warnings": warnings, "volumes": volume.list_volumes(d)}


@app.get("/api/books/{book_id}/card-check")
def book_card_check(book_id: str, from_: int = Query(None, alias="from"), to: int = None):
    """章綱體檢：拿角色設定回頭對章綱（正文還沒寫就先抓劇透）。"""
    d = book_dir(book_id)
    a, b = int(from_ or 1), int(to or from_ or 1)
    a, b = min(a, b), max(a, b)
    rows = wrap(lambda: upcheck.findings(d, a, b, cards=True))
    return {"range": [a, b], "findings": rows, "count": len(rows)}


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
        "reader": project.read_table(d, tracking.RP_FILE),
        "reader_draft": project.read_table(d, tracking.RP_DRAFT),
        "relations": project.read_table(d, relations.FILE),
        "relations_draft": project.read_table(d, relations.DRAFT),
        "relations_graph": relations.graph_data(d),
        "characters": chars,
        "latest": ov["latest"],
        "stale_foreshadow": int(CONFIG.get("stale_foreshadow", 10)),
    }


@app.get("/api/books/{book_id}/reverse")
def reverse_info(book_id: str, provider: str = None, upto: int = 0):
    """從正文建立設定：目前進度、草稿、費用估算。"""
    d = book_dir(book_id)
    prov = get_provider(provider)
    st = reverse.state(d)
    return {"state": st, "estimate": reverse.estimate(d, prov, upto or None),
            "has_settings": bool(project.list_entries(d, "設定/角色")) or bool(project.read_table(d, "追蹤/伏筆.md")["rows"])}


@app.post("/api/books/{book_id}/reverse/{op}")
async def reverse_op(book_id: str, op: str, req: Request):
    d = book_dir(book_id)
    body = await req.json() if (req.headers.get("content-type") or "").startswith("application/json") else {}
    if RUNNER.running_for(book_id):
        raise HTTPException(409, "還有任務在執行，請等它結束。")
    if op == "adopt":
        r = wrap(lambda: reverse.adopt(d, body.get("group")))
        wrap(lambda: contract.ensure(d))      # 拆書採用之後就有資料可以立續寫合約了（已存在且章數沒變就不動）
        return r
    if op == "discard":
        return wrap(lambda: reverse.discard(d, body.get("group")))
    if op == "reset":
        reverse.reset(d)
        return {"ok": True}
    raise HTTPException(404, "不支援的操作")


@app.get("/api/books/{book_id}/contract")
def contract_get(book_id: str):
    """續寫合約：這本書不能違背的事實（唯讀；要重產生用 POST）。"""
    d = book_dir(book_id)
    return {"path": contract.REL, "exists": os.path.isfile(contract.path(d)), "text": contract.text(d)}


@app.post("/api/books/{book_id}/contract")
async def contract_build(book_id: str, req: Request):
    d = book_dir(book_id)
    try:
        body = await req.json() if (req.headers.get("content-type") or "").startswith("application/json") else {}
    except ValueError:
        body = {}
    rel = wrap(lambda: contract.ensure(d, force=bool((body or {}).get("force"))))
    return {"path": contract.REL, "changed": bool(rel), "text": contract.text(d)}


@app.get("/api/books/{book_id}/search")
def book_search(book_id: str, q: str = "", scopes: str = ""):
    """前文全文搜尋（本機，不用模型）。scopes：正文,候選,章綱,設定,追蹤。"""
    return search.search(book_dir(book_id), q, [s for s in scopes.split(",") if s] or None)


@app.post("/api/books/{book_id}/tracking/reader/{op}")
def reader_draft_op(book_id: str, op: str):
    d = book_dir(book_id)
    if op == "adopt":
        rel = wrap(lambda: tracking.adopt_reader_draft(d))
        tracking.git_commit(d, "採用讀者認知帳本")
        return {"ok": True, "file": rel}
    if op == "discard":
        tracking.discard_reader_draft(d)
        return {"ok": True}
    raise HTTPException(404, "不支援的操作")


@app.post("/api/books/{book_id}/tracking/relations/{op}")
def relations_op(book_id: str, op: str):
    """角色關係表：build＝從角色檔的「## 關係」轉成草稿（不用模型）；adopt／discard＝採用或捨棄草稿。"""
    d = book_dir(book_id)
    if RUNNER.running_for(book_id):
        raise HTTPException(409, "還有任務在執行，請等它結束。")
    if op == "build":
        return {"ok": True, "message": wrap(lambda: relations.build_draft(d))}
    if op == "adopt":
        rel = wrap(lambda: relations.adopt_draft(d))
        tracking.git_commit(d, "採用角色關係表")
        return {"ok": True, "file": rel}
    if op == "discard":
        relations.discard_draft(d)
        return {"ok": True}
    raise HTTPException(404, "不支援的操作")


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


@app.get("/api/books/{book_id}/bible/index")
def bible_index_view(book_id: str):
    """設定索引（即時掃描，不寫檔）：設定檔、名詞表、疑似重複。"""
    return bible_index.build(book_dir(book_id))


@app.post("/api/books/{book_id}/bible/index/rebuild")
def bible_index_rebuild(book_id: str):
    """重新產生 設定/_索引.md（給 novel-bible skill 先讀）。"""
    d = book_dir(book_id)
    return bible_index.rebuild(d)


@app.post("/api/books/{book_id}/bible/merge")
async def bible_merge(book_id: str, req: Request):
    """把勾選的疑似重複併入保留的那一份。舊檔移到 設定/_已合併/，不刪除。"""
    d = book_dir(book_id)
    body = await req.json()
    if RUNNER.running_for(book_id):
        raise HTTPException(409, "Claude 正在處理這本書，請等任務結束再合併設定。")
    report = wrap(lambda: bible_index.merge(d, body.get("canonical"), body.get("duplicates") or []))
    bible_index.rebuild(d)
    return report


@app.post("/api/books/{book_id}/bible/category")
async def bible_set_category(book_id: str, req: Request):
    """批次把世界觀檔的「分類」改成固定清單中的一項。先全部檢查，通過才寫入。"""
    d = book_dir(book_id)
    body = await req.json()
    cat = body.get("category")
    status = body.get("status")
    files = body.get("files") or []
    if cat is None and status is None:
        raise HTTPException(400, "沒有要改的內容")
    if cat is not None and cat not in project.WORLD_CATS:
        raise HTTPException(400, "分類不在固定清單內")
    if status is not None and status not in ("正式", "草稿"):
        raise HTTPException(400, "狀態只能是 正式 或 草稿")
    if not isinstance(files, list) or not files:
        raise HTTPException(400, "沒有選取項目")
    if RUNNER.running_for(book_id):
        raise HTTPException(409, "Claude 正在處理這本書，請等任務結束再改分類。")
    targets = []
    for rel in files:
        if not isinstance(rel, str):
            raise HTTPException(400, "檔案路徑格式錯誤")
        norm = rel.replace("\\", "/").lstrip("/")
        p = wrap(lambda: project.safe_path(d, norm))
        allowed = ("設定/角色/", "設定/勢力/", "設定/世界觀/")
        if not norm.startswith(allowed) or not p.endswith(".md") or not os.path.isfile(p):
            raise HTTPException(400, "只能改 設定/角色、設定/勢力、設定/世界觀 裡的 .md 檔：" + rel)
        if cat is not None and not norm.startswith("設定/世界觀/"):
            raise HTTPException(400, "只有世界觀可以改分類：" + rel)
        targets.append(p)
    for p in targets:
        text = project.read_text(p)
        if cat is not None:
            text = project.set_frontmatter_field(text, "分類", cat)
        if status is not None:
            text = project.set_frontmatter_field(text, "狀態", status)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return {"ok": True, "updated": len(targets)}


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
    title, prompt = actions.build("accept", params, book_id, lang=lang_mod.book_lang(d))
    job = RUNNER.start(attach_wb_check(runner_mod.Job(book_id, d, title, prompt, meta={"action": "accept", "params": params},
                                                      provider=prov), d, "accept", params, prov))
    return {"path": path, "job": job.to_dict()}


@app.post("/api/books/{book_id}/candidate/{no}/reject")
async def reject(book_id: str, no: int, req: Request):
    d = book_dir(book_id)
    _guard_pipeline(book_id)
    body = await req.json()
    params = {"chapter": no, "note": body.get("note", "")}
    title, prompt = actions.build("reject", params, book_id, lang=lang_mod.book_lang(d))
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
def _attach_fidelity(job, d, params):
    """Claude Code 去 AI 味：先記下原稿，結束後做保真檢查（API 模型在 native.act_deslop 裡做）。"""
    try:
        no = int(params.get("chapter"))
    except (TypeError, ValueError):
        return job
    where = ("候選",) if params.get("candidate") else ("正文",)
    _, before = context.chapter_text(d, no, where)
    if not before:
        return job

    def after(j):
        rel, now = context.chapter_text(d, no, where)
        if now and now != before:
            j.result = (j.result or "") + fidelity.run(d, no, rel, before, now)
            j.emit("result", text=j.result)
    prev = job.after
    job.after = (lambda j: (prev(j), after(j))) if prev else after
    return job


def attach_wb_check(job, d, action, params, prov):
    """Claude Code 回寫追蹤（採用、補齊）結束後，跑本機的回寫檢查，結果接在任務結果後面。
    API 模型在 native._writeback 裡自己跑。"""
    if prov.get("type") != "claude_code" or action not in ("accept", "sync_tracking"):
        return job
    before = tracking.tracked_to(d)

    def after(j):
        if action == "accept":
            nos = [int(params.get("chapter"))]
        else:
            nos = [n for n in sorted(project._scan_dir(os.path.join(d, "正文"))) if before < n <= tracking.tracked_to(d)]
        add = "".join(wb_check.run(d, n, revision=bool(before and n < before)) for n in nos)
        if add:
            j.result = (j.result or "") + add
            j.emit("result", text=j.result)
    prev = job.after
    job.after = (lambda j: (prev(j), after(j))) if prev else after
    return job


def launch_job(book_id, d, action, params, prov, resume=None, text=None):
    """建立並啟動一個任務（面板按鈕和整章自動流程共用）。失敗時丟 HTTPException。"""
    try:
        if action == "reply":
            title, prompt = "回覆", text or ""
        else:
            title, prompt = actions.build(action, params or {}, book_id, lang=lang_mod.book_lang(d))
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(400, "參數不完整：%s" % e)
    if not prompt.strip():
        raise HTTPException(400, "指令是空的")
    try:
        if action in CLAUDE_SPECIAL and prov.get("type") == "claude_code":
            return RUNNER.start(CLAUDE_SPECIAL[action](book_id, d, prov, params or {}))
        return RUNNER.start(attach_wb_check(runner_mod.Job(book_id, d, title, prompt, resume=resume, provider=prov,
                                                           meta={"action": action, "params": params or {}}),
                                            d, action, params or {}, prov))
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
    if action in ("write", "chapter_cards") and not str(params.get("from") or "").strip():
        raise HTTPException(400, "請先填「從第幾章」；不要用空白送出，免得寫到第 1 章。")
    return launch_job(book_id, d, action, params, prov, resume=resume, text=params.get("text", "")).to_dict()


# ---------------------------------------------------------------------------
# 整章自動流程
# ---------------------------------------------------------------------------
def _pipe_hooks(book_id, d, prov_id):
    def launch(action, params, pid=None):
        return launch_job(book_id, d, action, params, get_provider(pid or prov_id))
    return {"launch": launch, "cancel": RUNNER.cancel, "checker": check_text,
            "busy": lambda: RUNNER.running_for(book_id) is not None,
            "style_check": lambda: bool(CONFIG.get("pipeline_style_check", True)),
            # 自動駕駛：每 K 章停下來驗「必須修」與「文風」（K=0 表示不檢查）
            "autopilot_every": int(CONFIG.get("autopilot_every") or 0)}


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
    wrap(lambda: contract.ensure(d))     # 開始整章自動流程前，先把續寫合約補到最新章數
    if sev is None:
        sev = CONFIG.get("pipeline_severities") or pipeline.DEFAULT_SEVERITIES
    ids = provider_ids()
    sp = body.get("step_providers")
    if sp is None:
        sp = CONFIG.get("pipeline_providers") or {}
    missing = [v for v in (sp or {}).values() if v and v not in ids]
    if missing:
        raise HTTPException(400, "步驟指定的執行者不存在：%s，請到設定修改。" % "、".join(missing))
    try:
        p = pipeline.Pipeline.create(book_id, d, _pipe_hooks(book_id, d, prov["id"]), a, b, mode, sev, prov["id"], body.get("note"),
                                     pipeline.clean_step_providers(sp, ids))
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
    # 程式更新後瀏覽器常拿舊的 app.js：網址加上檔案修改時間，檔案一改就會重新下載
    st = os.path.join(HERE, "static")
    html = project.read_text(os.path.join(st, "index.html"))
    for name in ("app.js", "style.css"):
        try:
            v = int(os.path.getmtime(os.path.join(st, name)))
        except OSError:
            continue
        html = html.replace('/static/%s"' % name, '/static/%s?v=%d"' % (name, v))
    # 一次性權杖：只注入給這個頁面，變更端點會驗它（前端 fetch 由 TOKEN_JS 自動帶上）
    html = html.replace("</head>", "<script>%s</script>\n</head>" % TOKEN_JS, 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


def serve():
    """實際執行伺服器。要求重新啟動時以 RESTART_CODE 結束，由外層再啟動一次。"""
    global SERVER, RUNNING_PORT
    host = CONFIG.get("host", "127.0.0.1")
    port = int(CONFIG.get("port", 8765))
    url = "http://%s:%d" % ("127.0.0.1" if host in ("0.0.0.0", "") else host, port)
    if "--open-browser" in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    preflight()
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


def preflight():
    """啟動時的自我檢查：書庫寫不寫得進去。寫不進去時給能動的解法，而不是等按下快照才炸。"""
    lib = CONFIG.get("library") or ""
    try:
        os.makedirs(lib, exist_ok=True)
        probe = os.path.join(lib, ".ns-write-test-%d" % os.getpid())
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError as e:
        print("\n" + "=" * 70)
        print("警告：這個 python 寫不進書庫，寫稿／存設定會失敗。")
        print("  書庫：%s" % lib)
        print("  原因：%s" % e)
        print("  目前用的 python：%s" % sys.executable)
        print("  最常見的原因：用「專案資料夾裡的 .venv」啟動，而書庫在專案外。")
        print("  解法：改用外部虛擬環境啟動——")
        print("    set NS_VENV=C:\\Users\\你\\venvs\\novel-studio")
        print("    start.bat")
        print("=" * 70 + "\n")
        return False


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
