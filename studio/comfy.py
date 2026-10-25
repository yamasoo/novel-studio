# -*- coding: utf-8 -*-
"""
ComfyUI API 客戶端與 workflow 處理。

使用者提供 API 格式的 workflow（ComfyUI 選單「Export (API)」），或用專案附的範本（examples/comfy/）。
工作台只改：正向、負向、seed、寬高、張數、存檔節點；其他（取樣器、步數、CFG、模型）照 workflow。
要改的節點由程式從取樣節點往回追，不需要在 workflow 裡加任何標記。

只會在 workflow 裡新增 ComfyUI 內建節點（SaveImage／PreviewImage、Prompt Upsampler 用的 TextGenerate 等）。
"""
import copy
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(os.path.dirname(HERE), "examples", "comfy")

SAMPLERS = {"KSampler": "seed", "KSamplerAdvanced": "noise_seed"}
TEXT_ENCODERS_PASS = {"ConditioningZeroOut", "ConditioningSetTimestepRange", "ConditioningCombine", "ConditioningConcat"}
OUTPUT_NODES = {"SaveImage", "PreviewImage", "SaveAnimatedWEBP", "SaveAnimatedPNG", "PreviewAny", "SaveImageKJ",
                "Image Save", "SaveImageWebsocket"}

# 出圖設定的種類：決定範本、提示詞格式、Upsampler 系統提示
KINDS = {
    "anima": {"label": "Anima", "template": "anima.api.json",
              "guess": {"unet": ["anima"], "clip": ["qwen_3_06b", "qwen3_06b", "qwen_3_0.6b"], "vae": ["qwen_image_vae"]},
              "upsampler_clip": "qwen3.5_9b"},
    "moss": {"label": "MOSS-Image", "template": "moss.api.json",
             "guess": {"unet": ["moss_image", "moss"], "clip": ["qwen3.5_9b", "qwen3.5"], "vae": ["flux2-vae", "flux2"]},
             "upsampler_clip": ""},   # MOSS 直接用自己的文字編碼器改寫
}
MOSS_NEGATIVE = "nsfw, worst quality, bad anatomy, watermark, jpeg artifact"

UPSAMPLER_SYSTEM = {
    "anima": (
        "You rewrite a rough image prompt into one clean prompt for Anima, an anime-style text-to-image model whose text encoder "
        "understands Danbooru tags, natural English sentences, and a mix of both.\n\n"
        "Keep exactly as written: the leading quality, score, year and rating tags, in the same order; every @artist tag, "
        "character name and series name; every subject, count, clothing item, pose, action, object, setting and style the input "
        "mentions; weighted tags such as (tag:1.2).\n\n"
        "Improve: remove exact duplicates; when two details contradict, keep the more specific one; write Danbooru tags with spaces "
        "instead of underscores, except score_ tags; after the tags, write 2 to 4 natural English sentences that describe the "
        "finished image (who is in it, what they are doing, where, lighting, composition, art style). For more than one character, "
        "describe each one separately and say where each is in the frame.\n\n"
        "Do not add characters, objects, text, nudity or a different art style that the input does not imply. Do not change the "
        "rating tag. Do not explain, add a title, quotation marks, bullet points or labels.\n\n"
        "Output only the final prompt: one line of comma-separated tags, then the sentences, in English, under 180 words."),
    "moss": (
        "Rewrite the user's image prompt into one caption that describes the finished image, for a text-to-image model.\n"
        "Keep every subject, count, action, clothing, setting, style and mood the user gave; do not contradict or drop anything. "
        "Fill in what is left open with concrete visual choices: composition, viewpoint, lighting, colors, materials and medium. "
        "Describe only what can be seen. Give positions with words such as left, right, foreground and background.\n"
        "Write in English plain prose, 60 to 180 words, starting with the medium and the main subject. "
        "No quality keywords, no lists, no headings, no negative prompt. Reply with the caption only."),
}


class ComfyError(Exception):
    pass


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _req(base, path, data=None, timeout=10, raw=False):
    url = base.rstrip("/") + path
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = r.read()
            if raw:
                return content
            return json.loads(content.decode("utf-8")) if content else {}
    except urllib.error.HTTPError as e:
        text = ""
        try:
            text = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        raise ComfyError(_explain_error(e.code, text))
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        raise ComfyError("連不到 ComfyUI（%s）：%s。請確認 ComfyUI 已啟動，網址正確。" % (base, getattr(e, "reason", e)))


def _explain_error(code, text):
    try:
        data = json.loads(text)
    except ValueError:
        return "ComfyUI 回應錯誤 %s：%s" % (code, text[:300])
    err = data.get("error") or {}
    msg = err.get("message") if isinstance(err, dict) else str(err)
    lines = [msg or ("ComfyUI 回應錯誤 %s" % code)]
    for nid, ne in (data.get("node_errors") or {}).items():
        for e in ne.get("errors") or []:
            lines.append("節點 %s（%s）：%s %s" % (nid, ne.get("class_type"), e.get("message") or "", e.get("details") or ""))
    return "\n".join(lines)


def system_stats(base):
    return _req(base, "/system_stats", timeout=6)


def object_info(base, cls=None):
    return _req(base, "/object_info" + ("/" + urllib.parse.quote(cls) if cls else ""), timeout=30)


def _choices(info, cls, field):
    try:
        spec = info[cls]["input"]["required"][field]
    except (KeyError, TypeError):
        return []
    if isinstance(spec, list) and spec:
        if isinstance(spec[0], list):
            return spec[0]
        if spec[0] == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
            return spec[1].get("options") or []
    return []


def model_lists(info):
    return {"unet": _choices(info, "UNETLoader", "unet_name"),
            "clip": _choices(info, "CLIPLoader", "clip_name"),
            "vae": _choices(info, "VAELoader", "vae_name")}


def guess_models(kind, lists):
    """依檔名猜這個種類該用哪個模型（只在使用者還沒選時用）。"""
    out = {}
    for key, words in KINDS.get(kind, KINDS["anima"])["guess"].items():
        hit = next((f for w in words for f in lists.get(key) or [] if w in f.lower()), "")
        out[key] = hit
    up = KINDS.get(kind, {}).get("upsampler_clip")
    out["upsampler_clip"] = next((f for f in lists.get("clip") or [] if up and up in f.lower()), "")
    return out


# ---------------------------------------------------------------------------
# workflow
# ---------------------------------------------------------------------------
def load_workflow(path):
    with open(path, encoding="utf-8") as f:
        try:
            wf = json.load(f)
        except ValueError as e:
            raise ComfyError("workflow 不是有效的 JSON：%s" % e)
    if isinstance(wf, dict) and "nodes" in wf and "links" in wf:
        raise ComfyError("這是一般存檔的 workflow。請在 ComfyUI 選單用「Export (API)」匯出 API 格式"
                         "（選單沒有這項的話，到設定開啟開發者模式）。")
    if isinstance(wf, dict) and "prompt" in wf and isinstance(wf["prompt"], dict):
        wf = wf["prompt"]
    if not isinstance(wf, dict) or not all(isinstance(v, dict) and "class_type" in v for v in wf.values()):
        raise ComfyError("看不懂這份 workflow，請確認是 ComfyUI 匯出的 API 格式 JSON。")
    return wf


def template_path(kind):
    return os.path.join(TEMPLATE_DIR, KINDS.get(kind, KINDS["anima"])["template"])


def _link(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)


def _ancestors(wf, nid, seen=None):
    seen = set() if seen is None else seen
    if nid in seen or nid not in wf:
        return seen
    seen.add(nid)
    for v in wf[nid].get("inputs", {}).values():
        if _link(v):
            _ancestors(wf, v[0], seen)
    return seen


def _trace_encoders(wf, link, out, depth=0):
    """從 conditioning 連線往回找有 text 輸入的文字編碼節點。"""
    if not _link(link) or depth > 12 or link[0] not in wf:
        return
    node = wf[link[0]]
    ins = node.get("inputs", {})
    if ("text" in ins or "prompt" in ins) and node["class_type"] != "TextGenerate":
        out.append(link[0])
        return
    for k, v in ins.items():
        if _link(v) and ("cond" in k or k in ("positive", "negative", "conditioning", "conditioning_1", "conditioning_2", "on_true", "on_false")):
            _trace_encoders(wf, v, out, depth + 1)


def _latent_node(wf, link, depth=0):
    if not _link(link) or depth > 8 or link[0] not in wf:
        return None
    node = wf[link[0]]
    ins = node.get("inputs", {})
    if "width" in ins and "height" in ins:
        return link[0]
    for k in ("samples", "latent", "latent_image"):
        if _link(ins.get(k)):
            return _latent_node(wf, ins[k], depth + 1)
    return None


def analyze(wf):
    """找出取樣、正負文字編碼、空白 latent、輸出節點。回傳 dict；找不到必要節點時丟 ComfyError。"""
    samplers = [nid for nid, n in wf.items() if n["class_type"] in SAMPLERS]
    if not samplers:
        raise ComfyError("workflow 裡找不到 KSampler 或 KSamplerAdvanced。")
    pos, neg, latents = [], [], []
    for s in samplers:
        ins = wf[s]["inputs"]
        _trace_encoders(wf, ins.get("positive"), pos)
        _trace_encoders(wf, ins.get("negative"), neg)
        ln = _latent_node(wf, ins.get("latent_image"))
        if ln and ln not in latents:
            latents.append(ln)
    pos = list(dict.fromkeys(pos))
    neg = [x for x in dict.fromkeys(neg) if x not in pos]
    if not pos:
        raise ComfyError("找不到正向提示詞的文字編碼節點（KSampler 的 positive 往回找不到有 text 的節點）。")
    # 輸出：祖先裡有取樣節點的圖片輸出節點
    outs = []
    for nid, n in wf.items():
        if n["class_type"] in OUTPUT_NODES and "images" in n.get("inputs", {}):
            anc = _ancestors(wf, nid)
            if any(s in anc for s in samplers):
                outs.append(nid)
    decode = None
    if not outs:
        for nid, n in wf.items():
            if n["class_type"].startswith("VAEDecode") and any(s in _ancestors(wf, nid) for s in samplers):
                decode = nid
    if not outs and not decode:
        raise ComfyError("找不到輸出圖片的節點（SaveImage／PreviewImage 或 VAEDecode）。")
    return {"samplers": samplers, "positive": pos, "negative": neg, "latents": latents, "outputs": outs, "decode": decode}


def summary(wf, info=None):
    """給設定頁看的分析結果。info：/object_info 的結果，用來檢查節點有沒有安裝。"""
    a = analyze(wf)
    done, _ = prepare(wf, {"unet": "-", "clip": "-", "vae": "-"}, "", "", 1, 1024, 1024)
    classes = sorted({n["class_type"] for n in done.values()})
    missing = [c for c in classes if info is not None and c not in info]

    def label(nid):
        n = wf[nid]
        t = (n.get("_meta") or {}).get("title")
        return "%s %s%s" % (nid, n["class_type"], "（%s）" % t if t and t != n["class_type"] else "")
    removed = sorted({n["class_type"] for n in wf.values()} - set(classes) - OUTPUT_NODES)
    return {"samplers": [label(x) for x in a["samplers"]], "positive": [label(x) for x in a["positive"]],
            "negative": [label(x) for x in a["negative"]], "latent": [label(x) for x in a["latents"]],
            "output": [label(x) for x in a["outputs"]] or ["（沒有存檔節點，會自動加 SaveImage）"],
            "classes": classes, "missing": missing, "removed": removed}


def _models(wf, profile):
    """套用設定檔指定的模型（空白＝照 workflow）。只改 UNETLoader、CLIPLoader（文字編碼用的）、VAELoader。"""
    for n in wf.values():
        ins = n.get("inputs", {})
        if n["class_type"] == "UNETLoader" and profile.get("unet"):
            ins["unet_name"] = profile["unet"]
        elif n["class_type"] == "CLIPLoader" and profile.get("clip"):
            ins["clip_name"] = profile["clip"]
        elif n["class_type"] == "VAELoader" and profile.get("vae"):
            ins["vae_name"] = profile["vae"]


def _check_models(wf):
    for n in wf.values():
        for k in ("unet_name", "clip_name", "vae_name"):
            if k in n.get("inputs", {}) and not n["inputs"][k]:
                raise ComfyError("還沒有選%s。請到「設定 → 插畫」的 ComfyUI 出圖設定按「測試連線」後選擇模型檔。"
                                 % {"unet_name": "模型", "clip_name": "文字編碼器", "vae_name": "VAE"}[k])


def _new_id(wf, base=900):
    i = base
    while str(i) in wf:
        i += 1
    return str(i)


def prepare(wf, profile, positive, negative, seed, width, height, count=1, keep_output=False, prefix="novel-studio"):
    """回傳 (修改後的 workflow, 輸出節點 id)。不改動傳入的 wf。"""
    wf = copy.deepcopy(wf)
    _models(wf, profile)
    a = analyze(wf)
    for nid in a["positive"]:
        ins = wf[nid]["inputs"]
        ins["text" if "text" in ins else "prompt"] = positive
    for nid in a["negative"]:
        ins = wf[nid]["inputs"]
        ins["text" if "text" in ins else "prompt"] = negative
    for i, s in enumerate(a["samplers"]):
        wf[s]["inputs"][SAMPLERS[wf[s]["class_type"]]] = int(seed)   # 多段取樣（放大）共用同一個 seed
    for nid in a["latents"]:
        ins = wf[nid]["inputs"]
        ins["width"], ins["height"] = int(width), int(height)
        if "batch_size" in ins:
            ins["batch_size"] = max(1, min(4, int(count or 1)))
    # 輸出：只留一個，換成內建的 SaveImage（留在 ComfyUI 輸出資料夾）或 PreviewImage（暫存）
    if a["outputs"]:
        src = wf[a["outputs"][0]]["inputs"]["images"]
    else:
        src = [a["decode"], 0]
    for nid in [n for n, v in wf.items() if v["class_type"] in OUTPUT_NODES]:
        del wf[nid]
    out_id = _new_id(wf, 990)
    wf[out_id] = ({"class_type": "SaveImage", "inputs": {"images": src, "filename_prefix": prefix}}
                  if keep_output else {"class_type": "PreviewImage", "inputs": {"images": src}})
    if profile.get("upsampler"):
        _add_upsampler(wf, a["positive"], profile, positive)
    # 只留輸出節點需要的節點（組提示詞用的自訂節點、預覽節點都會被拿掉）
    keep = _ancestors(wf, out_id)
    for nid in [n for n in wf if n not in keep]:
        del wf[nid]
    _check_models(wf)
    return wf, out_id


def _add_upsampler(wf, pos_nodes, profile, positive):
    """在正向文字編碼前插入內建的 TextGenerate，用 LLM 改寫提示詞。"""
    kind = profile.get("kind") or "anima"
    first = wf[pos_nodes[0]]["inputs"]
    if kind == "moss" and _link(first.get("clip")):
        clip = first["clip"]
    else:
        name = profile.get("upsampler_clip") or ""
        if not name:
            raise ComfyError("開啟 Prompt Upsampler 需要選擇改寫用的文字編碼器（例如 MOSS 的 Qwen3.5 9B）。")
        cid = _new_id(wf, 950)
        wf[cid] = {"class_type": "CLIPLoader", "_meta": {"title": "Upsampler 用 LLM"},
                   "inputs": {"clip_name": name, "type": "moss_image", "device": "default"}}
        clip = [cid, 0]
    sid = _new_id(wf, 951)
    wf[sid] = {"class_type": "PrimitiveStringMultiline", "_meta": {"title": "Upsampler 系統提示"},
               "inputs": {"value": profile.get("upsampler_system") or UPSAMPLER_SYSTEM.get(kind, UPSAMPLER_SYSTEM["anima"])}}
    gid = _new_id(wf, 952)
    wf[gid] = {"class_type": "TextGenerate", "_meta": {"title": "Prompt Upsampler"},
               "inputs": {"clip": clip, "system_prompt": [sid, 0], "prompt": positive,
                          "max_length": 1024 if kind == "anima" else 2048, "sampling_mode": "on",
                          "sampling_mode.temperature": 0.7, "sampling_mode.top_k": 64, "sampling_mode.top_p": 0.95,
                          "sampling_mode.min_p": 0.05, "sampling_mode.repetition_penalty": 1.05, "sampling_mode.seed": 0,
                          "sampling_mode.presence_penalty": 0, "thinking": False, "use_default_template": True, "mtp": "auto"}}
    for nid in pos_nodes:
        ins = wf[nid]["inputs"]
        ins["text" if "text" in ins else "prompt"] = [gid, 0]
    return gid


# ---------------------------------------------------------------------------
# 執行
# ---------------------------------------------------------------------------
def submit(base, wf):
    cid = uuid.uuid4().hex
    r = _req(base, "/prompt", {"prompt": wf, "client_id": cid}, timeout=30)
    if r.get("node_errors"):
        raise ComfyError(_explain_error(400, json.dumps(r)))
    pid = r.get("prompt_id")
    if not pid:
        raise ComfyError("ComfyUI 沒有回傳任務編號：%s" % json.dumps(r, ensure_ascii=False)[:300])
    return pid


def queue_state(base, pid):
    """回傳 running / pending / gone。"""
    try:
        q = _req(base, "/queue", timeout=5)
    except ComfyError:
        return "unknown"
    for k, st in (("queue_running", "running"), ("queue_pending", "pending")):
        for item in q.get(k) or []:
            if len(item) > 1 and item[1] == pid:
                return st
    return "gone"


def history(base, pid):
    try:
        return _req(base, "/history/" + urllib.parse.quote(pid), timeout=10).get(pid)
    except ComfyError:
        return None


def fetch_images(base, entry, out_id):
    outs = (entry or {}).get("outputs") or {}
    imgs = (outs.get(out_id) or {}).get("images") or []
    if not imgs:   # 保險：拿任何一個輸出節點的圖
        for v in outs.values():
            imgs = v.get("images") or []
            if imgs:
                break
    data = []
    for im in imgs:
        q = urllib.parse.urlencode({"filename": im.get("filename", ""), "subfolder": im.get("subfolder", ""),
                                    "type": im.get("type", "output")})
        data.append(_req(base, "/view?" + q, timeout=60, raw=True))
    return data


def status_error(entry):
    st = (entry or {}).get("status") or {}
    if st.get("status_str") == "error":
        for m in st.get("messages") or []:
            if m and m[0] == "execution_error":
                d = m[1] or {}
                return "節點 %s（%s）出錯：%s" % (d.get("node_id"), d.get("node_type"), d.get("exception_message") or "")
        return "ComfyUI 執行失敗"
    return ""


def interrupt(base, pid):
    try:
        if queue_state(base, pid) == "pending":
            _req(base, "/queue", {"delete": [pid]}, timeout=5)
        else:
            _req(base, "/interrupt", {"prompt_id": pid}, timeout=5)
    except ComfyError:
        pass


def run(base, wf, out_id, should_stop, on_tick=None, timeout=3600):
    """送出並等待完成，回傳圖片 bytes 清單。should_stop()：使用者按停止。"""
    pid = submit(base, wf)
    start = time.time()
    while True:
        if should_stop():
            interrupt(base, pid)
            raise ComfyError("已停止")
        entry = history(base, pid)
        if entry:
            err = status_error(entry)
            if err:
                raise ComfyError(err)
            st = entry.get("status") or {}
            if st.get("completed") or entry.get("outputs"):
                imgs = fetch_images(base, entry, out_id)
                if not imgs:
                    raise ComfyError("ComfyUI 完成了，但沒有輸出圖片")
                return imgs, pid
            if st.get("completed") is False:
                raise ComfyError("ComfyUI 沒有完成這個任務（可能被中斷）")
        if on_tick:
            on_tick(time.time() - start, queue_state(base, pid))
        if time.time() - start > timeout:
            interrupt(base, pid)
            raise ComfyError("等太久了（超過 %d 分鐘）" % (timeout // 60))
        time.sleep(1.0)
