# -*- coding: utf-8 -*-
"""
AI 供應商：OpenAI 相容的 Chat Completions（DeepSeek、llama.cpp 的 llama-server、
Ollama、LM Studio、OpenRouter……都適用）。只用標準函式庫。
"""
import json
import os
import sys
import socket
import urllib.error
import urllib.parse
import urllib.request

SECRETS_NAME = "secrets.json"

DEFAULT_PROVIDERS = [
    {"id": "claude_code", "type": "claude_code", "name": "Claude Code"},
    {"id": "deepseek", "type": "openai", "name": "DeepSeek",
     "base_url": "https://api.deepseek.com", "model": "", "key_env": "DEEPSEEK_API_KEY",
     "context_tokens": 128000, "max_output": 32768, "temperature": 1.0, "cjk_token_ratio": 0.6,
     "json_mode": True, "price_in": 0.0, "price_out": 0.0, "extra": {},
     "reasoning": {"adapter": "deepseek", "draft": "low", "plan": "high", "review": "high", "structured": "off"}},
    {"id": "llamacpp", "type": "openai", "name": "llama.cpp（本機）",
     "base_url": "http://127.0.0.1:8080/v1", "model": "", "key_env": "",
     "context_tokens": 32768, "max_output": 4096, "temperature": 0.8,
     "json_mode": True, "price_in": 0.0, "price_out": 0.0, "extra": {},
     "reasoning": {"adapter": "none", "draft": "off", "plan": "low", "review": "low", "structured": "off"}},
    {"id": "gemini", "type": "gemini", "name": "Google Gemini API",
     "base_url": "https://generativelanguage.googleapis.com/v1beta",
     "model": "gemini-3.8-flash", "key_env": "GEMINI_API_KEY",
     "context_tokens": 1000000, "max_output": 65536, "temperature": 0.9, "cjk_token_ratio": 0.8,
     "json_mode": True, "safety_relax": True, "price_in": 0.0, "price_out": 0.0, "extra": {},
     "reasoning": {"adapter": "gemini_thinking", "draft": "low", "plan": "medium", "review": "medium", "structured": "off"},
     "models": [
         {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash"},
         {"id": "gemini-4-neon", "name": "Gemini 4 Neon"},
     ]},
]

# ---------------------------------------------------------------------------
# 一個執行者底下的多個模型：選項的 id 寫成「執行者/模型」，例如 deepseek/deepseek-v4-pro
# ---------------------------------------------------------------------------
CLAUDE_MODELS = [("sonnet", "Sonnet"), ("opus", "Opus"), ("haiku", "Haiku")]
MODEL_FIELDS = (("context_tokens", int), ("max_output", int), ("price_in", float), ("price_out", float),
                ("cjk_token_ratio", float), ("temperature", float))


def _supports_models(p):
    """llama.cpp（本機）維持一個執行者一個模型。"""
    return p.get("type") in ("openai", "gemini") and p.get("id") != "llamacpp"


def choices(provs):
    """所有可以選的「執行者＋模型」，給下拉選單用。"""
    out = []
    for p in provs or []:
        base = {"base": p["id"], "group": p.get("name") or p["id"], "type": p.get("type"),
                "unset": p.get("type") != "claude_code" and not p.get("base_url")}
        if p.get("type") == "claude_code":
            out.append(dict(base, id=p["id"], label="預設", name=p.get("name") or p["id"]))
            out += [dict(base, id="%s/%s" % (p["id"], m), label=lbl, model=m, name="%s · %s" % (p.get("name"), lbl))
                    for m, lbl in CLAUDE_MODELS]
        elif _supports_models(p) and p.get("models"):
            dm = p.get("model") or ""
            out.append(dict(base, id=p["id"], label="%s（預設）" % (dm or "預設"), model=dm, is_default=True,
                            name="%s · %s" % (p.get("name"), dm) if dm else p.get("name")))
            for m in p["models"]:
                if m.get("id") and m["id"] != dm:
                    out.append(dict(base, id="%s/%s" % (p["id"], m["id"]), label=m.get("name") or m["id"], model=m["id"],
                                    name="%s · %s" % (p.get("name"), m.get("name") or m["id"])))
        else:
            out.append(dict(base, id=p["id"], label=p.get("model") or "預設", model=p.get("model") or "", name=p.get("name") or p["id"]))
    return out


def resolve(provs, pid):
    """把「執行者/模型」展開成一份完整的設定（執行者的設定＋這個模型覆寫的值）。找不到回傳 None。"""
    base_id, _, mid = str(pid or "").partition("/")
    base = next((p for p in provs or [] if p.get("id") == base_id), None)
    if not base:
        return None
    if not mid:
        return base
    if base.get("type") == "claude_code":
        if mid not in [m for m, _ in CLAUDE_MODELS]:
            return None
        lbl = dict(CLAUDE_MODELS)[mid]
        return dict(base, id=pid, key_id=base_id, base_id=base_id, model=mid, name="%s · %s" % (base.get("name"), lbl))
    m = next((x for x in base.get("models") or [] if x.get("id") == mid), None)
    if not m:
        return None
    out = dict(base, id=pid, key_id=base_id, base_id=base_id, model=mid, name="%s · %s" % (base.get("name"), m.get("name") or mid))
    out.pop("models", None)
    for k, _ in MODEL_FIELDS:
        if m.get(k) not in (None, "", 0):
            out[k] = m[k]
    if m.get("reasoning"):
        out["reasoning"] = dict(base.get("reasoning") or {}, **m["reasoning"])
    return out


def clean_models(models, stages, efforts):
    out, seen = [], set()
    for m in models or []:
        mid = str((m or {}).get("id") or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        c = {"id": mid}
        if str(m.get("name") or "").strip():
            c["name"] = str(m["name"]).strip()
        for k, f in MODEL_FIELDS:
            try:
                v = f(m.get(k)) if m.get(k) not in (None, "") else None
            except (TypeError, ValueError):
                v = None
            if v:
                c[k] = round(min(3.0, max(0.2, v)), 2) if k == "cjk_token_ratio" else v
        r = {st: v for st, v in (m.get("reasoning") or {}).items() if st in stages and v in efforts}
        if r:
            c["reasoning"] = r
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# 思考強度：依任務階段決定。思考過程也算在輸出 token 裡，整理 JSON 這類格式任務通常不需要思考。
# ---------------------------------------------------------------------------
STAGES = {"draft": "寫稿（寫章節、改稿、去 AI 味）", "plan": "規劃（大綱、章綱、設定、問答）",
          "review": "審查（一致性、章綱核對）", "structured": "結構化（回寫追蹤、對帳等 JSON）"}
EFFORTS = ["off", "low", "medium", "high", "max"]
ADAPTERS = {
    "none": "不控制（照模型預設）",
    "deepseek": "DeepSeek（thinking 開關＋reasoning_effort）",
    "openai_effort": "OpenAI 類（reasoning_effort）",
    "qwen_template": "llama.cpp／Qwen3 類（chat_template_kwargs.enable_thinking）",
    "gemini_thinking": "Google Gemini（thinkingConfig）",
}
DEFAULT_REASONING = {"adapter": "none", "draft": "low", "plan": "high", "review": "high", "structured": "off"}


def reasoning_for(prov, stage):
    r = dict(DEFAULT_REASONING)
    r.update(prov.get("reasoning") or {})
    return (r.get("adapter") or "none"), ((r.get(stage) or "off") if stage else None)


def apply_reasoning(body, prov, stage):
    """依階段把思考控制參數加進請求。回傳說明文字，沒有控制時回傳空字串。"""
    adapter, effort = reasoning_for(prov, stage)
    if adapter == "none" or not stage:
        return ""
    if adapter == "deepseek":
        if effort == "off":
            body["thinking"] = {"type": "disabled"}
        else:
            body["thinking"] = {"type": "enabled"}
            body["reasoning_effort"] = {"medium": "high"}.get(effort, effort)  # DeepSeek 只有 low／high／max
    elif adapter == "openai_effort":
        if effort != "off":
            body["reasoning_effort"] = {"max": "high"}.get(effort, effort)
    elif adapter == "qwen_template":
        body["chat_template_kwargs"] = {"enable_thinking": effort != "off"}
    return "思考：%s" % ("關閉" if effort == "off" else effort)


class ProviderError(Exception):
    pass


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------------------
# 金鑰：優先存在作業系統的金鑰庫（Windows 認證管理員／macOS 鑰匙圈／Linux Secret Service），
# 由作業系統加密、綁定登入帳號，專案資料夾裡不留金鑰。
# 沒有金鑰庫可用時才用 secrets.json（不進 git）。也可以用環境變數。
# 讀取順序：系統金鑰庫 → secrets.json → 環境變數。
# ---------------------------------------------------------------------------
KEYRING_SERVICE = "novel-studio"
_KR = None


def _keyring():
    """回傳可用的 keyring 模組；沒安裝或沒有可用的後端時回傳 None。"""
    global _KR
    if _KR is None:
        _KR = False
        try:
            import keyring
            from keyring.backends import fail
            kr = keyring.get_keyring()
            if not isinstance(kr, fail.Keyring) and getattr(kr, "priority", 1) > 0:
                _KR = keyring
        except Exception:
            _KR = False
    return _KR or None


def store_name():
    """系統金鑰庫的名稱（給介面顯示）；沒有就回傳空字串。"""
    if not _keyring():
        return ""
    if sys.platform.startswith("win"):
        return "Windows 認證管理員"
    if sys.platform == "darwin":
        return "macOS 鑰匙圈"
    return "系統金鑰庫"


def _kr_get(pid):
    kr = _keyring()
    if not kr:
        return ""
    try:
        return kr.get_password(KEYRING_SERVICE, pid) or ""
    except Exception:
        return ""


def _kr_set(pid, key):
    kr = _keyring()
    if not kr:
        return False
    try:
        if key:
            kr.set_password(KEYRING_SERVICE, pid, key)
            return kr.get_password(KEYRING_SERVICE, pid) == key
        try:
            kr.delete_password(KEYRING_SERVICE, pid)
        except Exception:
            pass
        return True
    except Exception:
        return False


def load_secrets(home):
    p = os.path.join(home, SECRETS_NAME)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _write_secrets(home, s):
    p = os.path.join(home, SECRETS_NAME)
    if not s:
        if os.path.isfile(p):
            os.remove(p)
        return
    with open(p, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def save_secret(home, pid, key):
    """存金鑰（空字串＝刪除）。有系統金鑰庫就存那裡，並移除 secrets.json 裡的舊值。回傳存放位置名稱。"""
    s = load_secrets(home)
    if _keyring() and _kr_set(pid, key):
        if pid in s:
            s.pop(pid)
            _write_secrets(home, s)
        return store_name() if key else ""
    if key:
        s[pid] = key
    else:
        s.pop(pid, None)
    _write_secrets(home, s)
    return SECRETS_NAME if key else ""


def migrate_secrets(home):
    """把 secrets.json 的金鑰搬進系統金鑰庫；全部搬完就刪掉 secrets.json。回傳 (搬了幾個, 剩幾個)。"""
    if not _keyring():
        return 0, len(load_secrets(home))
    s = load_secrets(home)
    moved = 0
    for pid in list(s):
        if s[pid] and _kr_set(pid, s[pid]):
            s.pop(pid)
            moved += 1
    _write_secrets(home, s)
    return moved, len(s)


def pending_secrets(home):
    """secrets.json 裡還有幾個金鑰可以搬進系統金鑰庫。"""
    return len([k for k, v in load_secrets(home).items() if v]) if _keyring() else 0


def _load_dotenv(home):
    """讀取專案根目錄的 .env（只用標準函式庫，支援 KEY=VALUE、引號、export 與 # 註解）。"""
    out = {}
    if not home:
        return out
    p = os.path.join(home, ".env")
    if not os.path.isfile(p):
        return out
    try:
        with open(p, encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if not k:
                    continue
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                elif " #" in v:
                    v = v.split(" #", 1)[0].strip()
                out[k] = v
    except OSError:
        return {}
    return out


def api_key(home, prov):
    kid = prov.get("key_id") or prov["id"]   # 同一個執行者底下的不同模型共用金鑰
    k = _kr_get(kid)
    if k:
        return k
    s = load_secrets(home)
    if s.get(kid):
        return s[kid]
    env = prov.get("key_env")
    if not env:
        return ""
    if os.environ.get(env):
        return os.environ.get(env, "")
    return _load_dotenv(home).get(env, "")


def _tail(k):
    return "（…%s）" % k[-4:] if len(k) > 8 else ""


def key_status(home, prov):
    kid = prov.get("key_id") or prov["id"]
    k = _kr_get(kid)
    if k:
        return store_name() + _tail(k)
    s = load_secrets(home)
    if s.get(kid):
        return "secrets.json" + _tail(s[kid])
    env = prov.get("key_env")
    if env and os.environ.get(env):
        return "環境變數 %s" % env
    if env:
        dv = _load_dotenv(home).get(env)
        if dv:
            return ".env (%s)%s" % (env, _tail(dv))
    return ""


def needs_key(prov):
    """本機服務（llama.cpp 等，網址是 127.0.0.1／localhost）不一定要金鑰；有設就照樣帶上。"""
    return not _is_local(prov.get("base_url") or "")


# ---------------------------------------------------------------------------
def _is_local(url):
    host = urllib.parse.urlparse(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local")


def _opener(url):
    # 本機服務不走代理
    if _is_local(url):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def _endpoint(prov, path):
    base = (prov.get("base_url") or "").rstrip("/")
    if not base:
        raise ProviderError("尚未設定 %s 的網址" % prov.get("name"))
    return base + path


def _headers(home, prov):
    h = {"Content-Type": "application/json", "Accept": "text/event-stream, application/json"}
    k = api_key(home, prov)
    if k:
        h["Authorization"] = "Bearer " + k
    return h


def _http_error(e):
    try:
        body = e.read().decode("utf-8", "replace")
        j = json.loads(body)
        msg = (j.get("error") or {}).get("message") if isinstance(j.get("error"), dict) else j.get("error")
        body = msg or body
    except Exception:
        body = str(e)
    hint = {401: "金鑰錯誤或未設定", 402: "帳戶餘額不足", 404: "網址或模型名稱錯誤", 429: "請求太頻繁或額度用完"}.get(e.code, "")
    return ProviderError("HTTP %s %s：%s" % (e.code, hint, str(body)[:400]))


def cjk_ratio(prov):
    """每個中文字約幾 token。沒有設定時：DeepSeek 用官方估計 0.6，其他用保守的 1.2。"""
    try:
        r = float(prov.get("cjk_token_ratio") or 0)
    except (TypeError, ValueError):
        r = 0
    if r > 0:
        return r
    return 0.6 if "deepseek" in (prov.get("base_url") or "").lower() else 1.2


CALIBRATE_TEXT = ("天還沒亮透阿母就在灶腳起火灶裡的柴是上禮拜颱風撿的還帶著濕氣煙順著煙囪爬不出去倒灌回來整間廚房霧濛濛"
                  "她把地瓜簽倒進鍋裡鏟子刮著鍋底一聲一聲我在門口站了一會兒她沒回頭只說鞋子穿好地上濕"
                  "客棧的燈油將盡夥計添了兩回見無人說話也就退到門邊打盹他坐在靠窗那張桌子刀橫在膝上鞘口缺了一角是去年在洛水邊留下的"
                  "窗外雨聲不大打著簷角一聲一聲像有人在數葬儀社的老闆說現在土葬不划算火葬比較環保樹葬更環保但樹葬要排隊排到明年春天"
                  "他問我們家屬有沒有偏好我媽說她偏好活著老闆點點頭在表格上寫了待確認我把車停在對街熄火雨刷停在半空像兩隻舉錯方向的手"
                  "目標在二樓窗簾沒拉緊留了一指寬的縫我看了十二分鐘他走過去三次每次都停在同一塊地板低頭像在確認什麼還在不在")


def calibrate_cjk(home, prov, timeout=15):
    """用 llama.cpp（llama-server）的 /tokenize 實際計算中文字的 token 比例。其他服務沒有這個端點。"""
    base = (prov.get("base_url") or "").rstrip("/")
    if not base:
        raise ProviderError("尚未設定 %s 的網址" % prov.get("name"))
    if "deepseek" in base.lower():
        raise ProviderError("DeepSeek 沒有 /tokenize；官方估計每個中文字約 0.6 token，欄位留空就會自動用這個值。")
    root = base[:-3] if base.endswith("/v1") else base
    body = json.dumps({"content": CALIBRATE_TEXT, "add_special": False}).encode("utf-8")
    req = urllib.request.Request(root + "/tokenize", data=body, headers=_headers(home, prov), method="POST")
    try:
        with _opener(req.full_url).open(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (404, 405):
            raise ProviderError("這個服務沒有 /tokenize（只有 llama.cpp 的 llama-server 有），請手動填比例。")
        raise _http_error(e)
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        raise ProviderError("連不上 %s：%s" % (req.full_url, getattr(e, "reason", e)))
    except ValueError:
        raise ProviderError("/tokenize 的回應不是 JSON，請手動填比例。")
    toks = data.get("tokens") if isinstance(data, dict) else None
    if not isinstance(toks, list) or not toks:
        raise ProviderError("/tokenize 沒有回傳 tokens，請手動填比例。")
    return round(len(toks) / float(len(CALIBRATE_TEXT)), 2)


GEMINI_SAFETY_OFF = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]
_GEMINI_THINK_BUDGET = {"off": 0, "low": 1024, "medium": 4096, "high": 8192, "max": 16384}


def _gemini_headers(home, prov):
    h = {"Content-Type": "application/json", "Accept": "text/event-stream, application/json"}
    k = api_key(home, prov)
    if k:
        h["x-goog-api-key"] = k
    return h


def _gemini_build_body(prov, messages, json_mode=False, max_tokens=None, stage=None):
    """將 OpenAI 格式 messages 轉為 Google Gemini 原生 generateContent 請求體。"""
    sys_parts, contents = [], []
    for m in messages or []:
        role = (m.get("role") or "user").lower()
        txt = m.get("content") or ""
        if not isinstance(txt, str):
            txt = json.dumps(txt, ensure_ascii=False)
        if role == "system":
            if txt.strip():
                sys_parts.append({"text": txt})
            continue
        g_role = "model" if role == "assistant" else "user"
        if contents and contents[-1]["role"] == g_role:
            contents[-1]["parts"].append({"text": txt})
        else:
            contents.append({"role": g_role, "parts": [{"text": txt}]})
    if not contents:
        contents = [{"role": "user", "parts": [{"text": ""}]}]

    gen_cfg = {"maxOutputTokens": int(max_tokens or prov.get("max_output") or 8192)}
    if prov.get("temperature") not in (None, ""):
        gen_cfg["temperature"] = float(prov["temperature"])
    if json_mode and prov.get("json_mode", True):
        gen_cfg["responseMimeType"] = "application/json"

    adapter, effort = reasoning_for(prov, stage)
    if adapter == "gemini_thinking" and stage:
        budget = _GEMINI_THINK_BUDGET.get(effort, 0)
        tcfg = {"thinkingBudget": budget}
        if budget > 0:
            tcfg["includeThoughts"] = True
        gen_cfg["thinkingConfig"] = tcfg

    body = {"contents": contents, "generationConfig": gen_cfg}
    if sys_parts:
        body["systemInstruction"] = {"parts": sys_parts}
    if prov.get("safety_relax", True):
        body["safetySettings"] = list(GEMINI_SAFETY_OFF)

    extra = prov.get("extra") or {}
    if isinstance(extra, dict):
        for ek, ev in extra.items():
            if ek == "generationConfig" and isinstance(ev, dict):
                body["generationConfig"].update(ev)
            else:
                body[ek] = ev
    return body


def _gemini_list_models(home, prov, timeout=15):
    req = urllib.request.Request(_endpoint(prov, "/models"), headers=_gemini_headers(home, prov))
    try:
        with _opener(req.full_url).open(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise _http_error(e)
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        raise ProviderError("連不上 %s：%s" % (req.full_url, getattr(e, "reason", e)))
    out = []
    for m in data.get("models") or []:
        methods = m.get("supportedGenerationMethods")
        if methods and "generateContent" not in methods:
            continue
        mid = str(m.get("name") or m.get("id") or "").strip()
        if mid.startswith("models/"):
            mid = mid[7:]
        if mid:
            out.append(mid)
    return out


def _gemini_usage(um):
    if not isinstance(um, dict):
        return {}
    out = {}
    if um.get("promptTokenCount") is not None:
        out["prompt_tokens"] = int(um["promptTokenCount"])
    if um.get("candidatesTokenCount") is not None:
        out["completion_tokens"] = int(um["candidatesTokenCount"])
    if um.get("totalTokenCount") is not None:
        out["total_tokens"] = int(um["totalTokenCount"])
    return out


def _gemini_chat(home, prov, messages, on_delta=None, on_thinking=None, json_mode=False,
                 max_tokens=None, should_stop=None, timeout=600, stage=None):
    """串流呼叫 Google Gemini 原生 streamGenerateContent?alt=sse。"""
    model = (prov.get("model") or "gemini-3.8-flash").strip()
    if model.startswith("models/"):
        model = model[7:]
    url = _endpoint(prov, "/models/%s:streamGenerateContent?alt=sse" % urllib.parse.quote(model, safe=""))
    body = _gemini_build_body(prov, messages, json_mode=json_mode, max_tokens=max_tokens, stage=stage)
    req = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=_gemini_headers(home, prov), method="POST",
    )
    text_parts, usage = [], {}
    finish = None

    def _consume(ev):
        nonlocal usage, finish
        if ev.get("error"):
            err = ev["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise ProviderError(str(msg)[:400])
        if ev.get("usageMetadata"):
            usage = _gemini_usage(ev["usageMetadata"])
        fb = ev.get("promptFeedback") or {}
        if fb.get("blockReason"):
            raise ProviderError("Gemini 安全過濾攔截了輸入（%s）" % fb["blockReason"])
        for cand in ev.get("candidates") or []:
            content = cand.get("content") or {}
            for part in content.get("parts") or []:
                txt = part.get("text")
                if not txt:
                    continue
                if part.get("thought"):
                    if on_thinking:
                        on_thinking(txt)
                else:
                    text_parts.append(txt)
                    if on_delta:
                        on_delta(txt)
            if cand.get("finishReason"):
                finish = cand["finishReason"]

    try:
        resp = _opener(req.full_url).open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise _http_error(e)
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        raise ProviderError("連不上 %s：%s" % (req.full_url, getattr(e, "reason", e)))
    try:
        ctype = resp.headers.get("Content-Type", "")
        if "text/event-stream" not in ctype:
            raw_json = json.loads(resp.read().decode("utf-8"))
            for ev in (raw_json if isinstance(raw_json, list) else [raw_json]):
                _consume(ev)
        else:
            try:
                lines = iter(resp)
            except Exception as e:
                raise ProviderError("讀取回應失敗：%s" % e)
            while True:
                try:
                    raw = next(lines)
                except StopIteration:
                    break
                except Exception as e:
                    raise ProviderError("串流中斷：%s" % e)
                if should_stop and should_stop():
                    raise Cancelled()
                line = raw.decode("utf-8", "replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    ev = json.loads(payload)
                except ValueError:
                    continue
                _consume(ev)
        if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII") and not text_parts:
            raise ProviderError("Gemini 安全過濾中止了輸出（finishReason: %s）" % finish)
        if not finish and not text_parts:
            raise ProviderError("串流中斷：Gemini 沒有回傳任何內容")
    finally:
        try:
            resp.close()
        except Exception:
            pass
    usage = dict(usage or {})
    if finish:
        usage["finish_reason"] = {"STOP": "stop", "MAX_TOKENS": "length"}.get(finish, str(finish).lower())
    return "".join(text_parts), usage


def list_models(home, prov, timeout=15):
    if prov.get("type") == "gemini":
        return _gemini_list_models(home, prov, timeout=timeout)
    req = urllib.request.Request(_endpoint(prov, "/models"), headers=_headers(home, prov))
    try:
        with _opener(req.full_url).open(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise _http_error(e)
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        raise ProviderError("連不上 %s：%s" % (req.full_url, getattr(e, "reason", e)))
    items = data.get("data") or data.get("models") or []
    out = []
    for m in items:
        mid = m.get("id") or m.get("name") or m.get("model")
        if mid:
            out.append(mid)
    return out


def chat(home, prov, messages, on_delta=None, on_thinking=None, json_mode=False,
         max_tokens=None, should_stop=None, timeout=600, stage=None):
    """
    串流呼叫 /chat/completions（或 Google Gemini 原生 streamGenerateContent）。回傳 (完整文字, usage dict)。
    on_delta(text)：正文片段；on_thinking(text)：推理過程片段（DeepSeek、llama.cpp、Gemini）。
    """
    if prov.get("type") == "gemini":
        return _gemini_chat(home, prov, messages, on_delta=on_delta, on_thinking=on_thinking,
                            json_mode=json_mode, max_tokens=max_tokens, should_stop=should_stop,
                            timeout=timeout, stage=stage)
    body = {
        "model": prov.get("model") or "default",
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": int(max_tokens or prov.get("max_output") or 4096),
    }
    if prov.get("temperature") not in (None, ""):
        body["temperature"] = float(prov["temperature"])
    if json_mode and prov.get("json_mode", True):
        body["response_format"] = {"type": "json_object"}
    apply_reasoning(body, prov, stage)
    extra = prov.get("extra") or {}
    if isinstance(extra, dict):
        body.update(extra)   # 使用者的額外參數優先

    req = urllib.request.Request(_endpoint(prov, "/chat/completions"),
                                 data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers=_headers(home, prov), method="POST")
    text_parts, usage = [], {}
    finish = None
    saw_done = False
    try:
        resp = _opener(req.full_url).open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise _http_error(e)
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        raise ProviderError("連不上 %s：%s" % (req.full_url, getattr(e, "reason", e)))
    try:
        ctype = resp.headers.get("Content-Type", "")
        if "text/event-stream" not in ctype:
            # 不支援串流的伺服器：一次回傳
            data = json.loads(resp.read().decode("utf-8"))
            msg = (data.get("choices") or [{}])[0].get("message") or {}
            if msg.get("reasoning_content") and on_thinking:
                on_thinking(msg["reasoning_content"])
            content = msg.get("content") or ""
            if on_delta:
                on_delta(content)
            return content, data.get("usage") or {}
        try:
            lines = iter(resp)
        except Exception as e:
            raise ProviderError("讀取回應失敗：%s" % e)
        while True:
            try:
                raw = next(lines)
            except StopIteration:
                break
            except Exception as e:  # 連線中途斷掉
                raise ProviderError("串流中斷：%s" % e)
            if should_stop and should_stop():
                raise Cancelled()
            line = raw.decode("utf-8", "replace").strip()
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                saw_done = True
                break
            try:
                ev = json.loads(payload)
            except ValueError:
                continue
            if ev.get("error"):
                raise ProviderError(str(ev["error"])[:400])
            if ev.get("usage"):
                usage = ev["usage"]
            for ch in ev.get("choices") or []:
                d = ch.get("delta") or {}
                r = d.get("reasoning_content") or d.get("reasoning")
                if r and on_thinking:
                    on_thinking(r)
                c = d.get("content")
                if c:
                    text_parts.append(c)
                    if on_delta:
                        on_delta(c)
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
        if not saw_done and not finish:
            raise ProviderError("串流中斷：伺服器在輸出完成前就斷線了")
    finally:
        try:
            resp.close()
        except Exception:
            pass
    usage = dict(usage or {})
    if finish:
        usage["finish_reason"] = finish
    return "".join(text_parts), usage


def cost_of(prov, usage):
    pi, po = float(prov.get("price_in") or 0), float(prov.get("price_out") or 0)
    if not (pi or po) or not usage:
        return None
    return (usage.get("prompt_tokens", 0) * pi + usage.get("completion_tokens", 0) * po) / 1_000_000


def parse_json(text):
    """容錯解析模型回傳的 JSON（去掉 ```json 圍欄、前後雜訊）。"""
    t = text.strip()
    t = t.replace("```json", "```")
    if t.startswith("```"):
        t = t.strip("`").strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(t[a:b + 1])
        except ValueError as e:
            raise ProviderError("模型回傳的 JSON 格式錯誤：%s" % e)
    raise ProviderError("模型沒有回傳 JSON")
