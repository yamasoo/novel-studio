# -*- coding: utf-8 -*-
"""
Forge Neo（A1111 系列）API 客戶端與出圖佇列。
Forge 要用 --api 啟動。參數用 infotext 格式（Steps: …, Sampler: …, Model: …, Module 1: …）送出，
由 Forge 自己切換模型、VAE／文字編碼器並套用 Shift 等設定；提示詞、種子、尺寸由工作台明確指定。
"""
import base64
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
import uuid

from . import comfy, illust


class ForgeError(Exception):
    pass


def _req(base, path, data=None, timeout=10):
    url = base.rstrip("/") + path
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail") or ""
        except Exception:
            pass
        if e.code == 404:
            raise ForgeError("Forge 沒有開放 API（%s 回應 404）。請在啟動參數加上 --api 後重開 Forge。" % path)
        raise ForgeError("Forge 回應錯誤 %s：%s" % (e.code, detail or e.reason))
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        raise ForgeError("連不到 Forge（%s）：%s。請確認 Forge 已啟動，網址正確。" % (base, getattr(e, "reason", e)))


def status(base):
    """回傳 Forge 目前狀態：模型、模組、取樣器、排程器。"""
    opts = _req(base, "/sdapi/v1/options", timeout=8)
    out = {"ok": True, "model": opts.get("sd_model_checkpoint"),
           "modules": [m.replace("\\", "/").rsplit("/", 1)[-1] for m in (opts.get("forge_additional_modules") or [])],
           "preset": opts.get("forge_preset")}
    for key, path in (("models", "/sdapi/v1/sd-models"), ("samplers", "/sdapi/v1/samplers"),
                      ("schedulers", "/sdapi/v1/schedulers"), ("all_modules", "/sdapi/v1/sd-modules")):
        try:
            items = _req(base, path, timeout=8)
            out[key] = [i.get("model_name") or i.get("title") or i.get("name") or i.get("label") for i in items]
        except ForgeError:
            out[key] = []
    return out


def loras(base):
    """Forge 的 LoRA 清單：[{name, alias, path}]（內建 Lora 擴充的 /sdapi/v1/loras）。"""
    items = _req(base, "/sdapi/v1/loras", timeout=15)
    out = []
    for x in items or []:
        if isinstance(x, dict) and x.get("name"):
            out.append({"name": str(x["name"]), "alias": str(x.get("alias") or ""), "path": str(x.get("path") or "")})
    return out


def _num(v):
    s = ("%.2f" % float(v)).rstrip("0").rstrip(".")
    return s or "0"


def with_loras(positive, loras_on):
    """在正向提示詞最後加上 <lora:名稱:強度> 與觸發詞；提示詞裡已經有同一個 LoRA 就不重複加。"""
    tags = ["<lora:%s:%s>" % (x["name"], _num(x["strength"])) for x in loras_on
            if "<lora:%s:" % x["name"] not in (positive or "")]
    p = comfy.with_triggers(positive, loras_on)
    return ", ".join([s for s in [(p or "").rstrip(" ,")] + tags if s])


def build_payload(positive, negative, params_line, seed, width, height, count=1, save_in_forge=False):
    infotext = positive + "\nNegative prompt: " + negative + ("\n" + params_line if params_line else "")
    return {"prompt": positive, "negative_prompt": negative, "seed": int(seed), "width": int(width), "height": int(height),
            "batch_size": max(1, min(4, int(count))), "n_iter": 1, "infotext": infotext,
            "save_images": bool(save_in_forge), "send_images": True,
            # Forge Neo 解析 infotext 時，styles 欄位會得到 gr.skip()，接著用 isinstance(…, list[str]) 檢查而出錯
            # （TypeError: isinstance() argument 2 cannot be a parameterized generic）。
            # 明確指定的欄位會跳過 infotext 解析，所以這幾個欄位自己給值。
            "styles": [], "enable_hr": False, "hr_additional_modules": None,
            "hr_sampler_name": None, "hr_scheduler": None}


def txt2img(base, payload, timeout=1800):
    r = _req(base, "/sdapi/v1/txt2img", payload, timeout=timeout)
    info = {}
    try:
        info = json.loads(r.get("info") or "{}")
    except Exception:
        pass
    return [base64.b64decode(i.split(",", 1)[-1]) for i in r.get("images") or []], info


def progress(base):
    try:
        return _req(base, "/sdapi/v1/progress?skip_current_image=true", timeout=5)
    except ForgeError:
        return {}


def interrupt(base):
    try:
        _req(base, "/sdapi/v1/interrupt", {}, timeout=5)
    except ForgeError:
        pass


# ---------------------------------------------------------------------------
# 佇列：一次只送一張到 Forge（Forge 本身也是一次一張），其他的排隊
# ---------------------------------------------------------------------------
class Queue:
    def __init__(self, get_cfg):
        self.get_cfg = get_cfg
        self.items = []
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.current = None
        threading.Thread(target=self._loop, daemon=True).start()

    def add(self, book_id, book_dir, target, label, positive, negative, params_line, seed, width, height, count, meta,
            backend="forge", profile=None):
        seed = int(seed) if str(seed).lstrip("-").isdigit() else -1
        if seed < 0:
            seed = random.randint(1, 2 ** 31 - 1)
        it = {"id": uuid.uuid4().hex[:10], "book_id": book_id, "book_dir": book_dir, "target": target, "label": label,
              "positive": positive, "negative": negative, "params": params_line, "seed": seed,
              "width": int(width), "height": int(height), "count": max(1, min(4, int(count or 1))), "meta": meta or {},
              "status": "queued", "progress": 0, "eta": None, "error": "", "files": [], "created": time.time(),
              "backend": backend, "profile": profile or {}, "elapsed": 0, "phase": ""}
        with self.lock:
            self.items.append(it)
            self.items = [x for x in self.items if x["status"] in ("queued", "running") or time.time() - x["created"] < 3600][-200:]
        self.wake.set()
        return it

    def list(self, book_id=None):
        with self.lock:
            return [self._pub(x) for x in self.items if book_id is None or x["book_id"] == book_id]

    @staticmethod
    def _pub(x):
        d = {k: x[k] for k in ("id", "book_id", "target", "label", "seed", "width", "height", "count", "status",
                               "progress", "eta", "error", "files", "created", "backend", "elapsed", "phase")}
        d["profile"] = (x.get("profile") or {}).get("name", "")
        return d

    def cancel(self, qid):
        with self.lock:
            for x in self.items:
                if x["id"] == qid:
                    if x["status"] == "queued":
                        x["status"] = "cancelled"
                    elif x["status"] == "running":
                        x["cancel"] = True
                        if x.get("backend") != "comfy":   # ComfyUI 由執行迴圈自己中斷
                            interrupt(self._base())
                    return True
        return False

    def _base(self):
        return (self.get_cfg().get("forge_url") or illust.DEFAULTS["forge_url"]).rstrip("/")

    def _loop(self):
        while True:
            self.wake.wait(2)
            self.wake.clear()
            while True:
                with self.lock:
                    it = next((x for x in self.items if x["status"] == "queued"), None)
                    if it:
                        it["status"] = "running"
                if not it:
                    break
                self._run(it)

    def _run(self, it):
        if it.get("backend") == "comfy":
            return self._run_comfy(it)
        cfg = self.get_cfg()
        base = self._base()
        result = {}

        def work():
            try:
                payload = build_payload(it["positive"], it["negative"], it["params"], it["seed"], it["width"], it["height"],
                                        it["count"], cfg.get("save_in_forge"))
                result["images"], result["info"] = txt2img(base, payload)
            except Exception as e:  # noqa: BLE001
                result["error"] = str(e)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        while t.is_alive():
            t.join(1.0)
            p = progress(base)
            if p:
                it["progress"] = round(float(p.get("progress") or 0), 3)
                it["eta"] = p.get("eta_relative")
        if it.get("cancel"):
            it["status"] = "cancelled"
            return
        if result.get("error"):
            it["status"] = "error"
            it["error"] = result["error"]
            return
        info = result.get("info") or {}
        seeds = info.get("all_seeds") or []
        infotexts = info.get("infotexts") or []
        files = []
        for i, data in enumerate(result.get("images") or []):
            seed = seeds[i] if i < len(seeds) else it["seed"] + i
            meta = dict(it["meta"], origin="forge", prompt=it["positive"], negative=it["negative"], params=it["params"],
                        seed=seed, width=it["width"], height=it["height"],
                        infotext=infotexts[i] if i < len(infotexts) else "", forge_url=base)
            try:
                files.append(illust.save_image(it["book_dir"], it["target"], data, meta))
            except Exception as e:  # noqa: BLE001
                it["error"] = str(e)
        it["files"] = files
        it["progress"] = 1
        it["status"] = "done" if files else "error"
        if not files and not it["error"]:
            it["error"] = "Forge 沒有回傳圖片"

    # ------------------------------------------------------------------ ComfyUI
    def _run_comfy(self, it):
        cfg = self.get_cfg()
        base = (cfg.get("comfy_url") or illust.DEFAULTS["comfy_url"]).rstrip("/")
        prof = it.get("profile") or {}
        try:
            path = prof.get("workflow") or comfy.template_path(prof.get("kind") or "anima")
            if not os.path.isfile(path):
                raise comfy.ComfyError("找不到 workflow 檔：%s" % path)
            wf, out_id = comfy.prepare(comfy.load_workflow(path), prof, it["positive"], it["negative"], it["seed"],
                                       it["width"], it["height"], it["count"], bool(cfg.get("comfy_keep_output")),
                                       "novel-studio/%s" % (prof.get("kind") or "image"))

            def tick(elapsed, state):
                it["elapsed"], it["phase"] = int(elapsed), state

            images, pid = comfy.run(base, wf, out_id, lambda: bool(it.get("cancel")), tick)
        except comfy.ComfyError as e:
            if it.get("cancel"):
                it["status"] = "cancelled"
                return
            it["status"], it["error"] = "error", str(e)
            return
        except Exception as e:  # noqa: BLE001
            it["status"], it["error"] = "error", "程式錯誤：%s" % e
            return
        files = []
        for i, data in enumerate(images):
            meta = dict(it["meta"], origin="comfy", prompt=it["positive"], negative=it["negative"], seed=it["seed"],
                        batch_index=i, width=it["width"], height=it["height"], comfy_profile=prof.get("name"),
                        comfy_kind=prof.get("kind"), upsampler=bool(prof.get("upsampler")), comfy_prompt_id=pid,
                        loras=[{"name": x["name"], "strength": x["strength"]} for x in comfy.active_loras(prof)])
            try:
                files.append(illust.save_image(it["book_dir"], it["target"], data, meta))
            except Exception as e:  # noqa: BLE001
                it["error"] = str(e)
        it["files"] = files
        it["progress"] = 1
        it["status"] = "done" if files else "error"
        if not files and not it["error"]:
            it["error"] = "ComfyUI 沒有回傳圖片"
