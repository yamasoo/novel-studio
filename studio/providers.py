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
     "context_tokens": 128000, "max_output": 32768, "temperature": 1.0,
     "json_mode": True, "price_in": 0.0, "price_out": 0.0, "extra": {},
     "reasoning": {"adapter": "deepseek", "draft": "low", "plan": "high", "review": "high", "structured": "off"}},
    {"id": "llamacpp", "type": "openai", "name": "llama.cpp（本機）",
     "base_url": "http://127.0.0.1:8080/v1", "model": "", "key_env": "",
     "context_tokens": 32768, "max_output": 4096, "temperature": 0.8,
     "json_mode": True, "price_in": 0.0, "price_out": 0.0, "extra": {},
     "reasoning": {"adapter": "none", "draft": "off", "plan": "low", "review": "low", "structured": "off"}},
]

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


def api_key(home, prov):
    k = _kr_get(prov["id"])
    if k:
        return k
    s = load_secrets(home)
    if s.get(prov["id"]):
        return s[prov["id"]]
    env = prov.get("key_env")
    return os.environ.get(env, "") if env else ""


def _tail(k):
    return "（…%s）" % k[-4:] if len(k) > 8 else ""


def key_status(home, prov):
    k = _kr_get(prov["id"])
    if k:
        return store_name() + _tail(k)
    s = load_secrets(home)
    if s.get(prov["id"]):
        return "secrets.json" + _tail(s[prov["id"]])
    env = prov.get("key_env")
    if env and os.environ.get(env):
        return "環境變數 %s" % env
    return ""


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


def list_models(home, prov, timeout=15):
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
    串流呼叫 /chat/completions。回傳 (完整文字, usage dict)。
    on_delta(text)：正文片段；on_thinking(text)：推理過程片段（DeepSeek、llama.cpp 的 reasoning_content）。
    """
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
