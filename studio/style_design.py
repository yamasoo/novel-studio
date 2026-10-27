# -*- coding: utf-8 -*-
"""
共用庫「請 AI 設計文風」：設計／調整／試寫。

Claude Code 與 OpenAI 相容 API 共用同一份任務說明；模型把完整文風檔放在
<<<文風>>> … <<<結束>>> 區塊裡，由 Python 寫入 _共用/文風/<名稱>.md（舊檔先備份），
有樣本時用程式統計覆蓋「文字指標」一節。
"""
import os
import re
import time

from . import context, project, prompts, shared

MODES = {"design": "設計文風", "revise": "調整文風", "test": "試寫文風"}
BLOCK_RE = re.compile(r"<<<\s*文風\s*>>>[ \t]*\r?\n(.*?)\r?\n?[ \t]*<<<\s*結束\s*>>>", re.S)
SAMPLE_LIMIT = 6000   # 給模型看的樣本上限（字）；統計用全文


class DesignError(Exception):
    pass


def skill_file(plugin_dir, rel):
    return context.skill_ref(plugin_dir, "novel-style/" + rel)


def style_path(library, name):
    return os.path.join(shared.shared_dir(library, create=True), "文風", shared._name_ok(name) + ".md")


def prepare(library, params):
    """檢查參數、讀現有檔、統計樣本。回傳 dict（不呼叫 AI）。"""
    mode = params.get("mode") or "design"
    if mode not in MODES:
        raise DesignError("不認識的模式：%s" % mode)
    try:
        name = shared._name_ok(params.get("name") or "")
    except shared.SharedError as e:
        raise DesignError(str(e))
    p = style_path(library, name)
    current = project.read_text(p) if os.path.isfile(p) else ""
    if mode in ("revise", "test") and not current:
        raise DesignError("找不到文風「%s」" % name)
    if mode == "design" and current and not params.get("overwrite"):
        raise DesignError("已經有叫「%s」的文風了。要重新設計請勾選「覆蓋」，或改用「請 AI 調整」。" % name)
    if mode == "revise" and not (params.get("note") or "").strip():
        raise DesignError("請寫下要怎麼調整")
    sample = (params.get("sample") or "").strip()
    metrics = None
    if sample:
        try:
            metrics = shared.analyze(sample, [x.strip() for x in re.split(r"[,，、\s]+", params.get("exclude") or "") if x.strip()])
        except shared.SharedError:
            metrics = None   # 樣本太短就只當參考，不統計
    return {"mode": mode, "name": name, "path": p, "current": current, "sample": sample, "metrics": metrics}


def _brief(params):
    rows = [("類型", params.get("genre")), ("想要的感覺", params.get("feel")), ("參考作品或作者", params.get("refs")),
            ("敘事視角", params.get("pov")), ("讀者與平台", params.get("readers")), ("一定不要", params.get("avoid"))]
    return "\n".join("- %s：%s" % (k, v.strip()) for k, v in rows if (v or "").strip()) or "（作者沒有填，請依名稱推想）"


def task_text(info, params):
    """給模型的任務說明（不含參考資料）。"""
    mode, name = info["mode"], info["name"]
    common = ("【原則】規則要具體到能拿來檢查一段文字；給範圍與情境，不給死數字；只寫深這個文風與眾不同的五到八項，其他一句帶過；"
              "禁忌要附替代做法；分清楚 建議做法／本書禁忌／允許的例外；參考作品只學特徵，不抄原文、不用它的人名地名專有名詞與招牌台詞；"
              "範例段落一律原創，至少三段有場景標籤（【對白】【動作】【描寫】【情緒】【轉場】挑最能代表的），每段後面一句「我喜歡它哪裡」，可以加一段【反例】附「為什麼不行」；"
              "整份 %s（不含指標表）；%s。" % (prompts.cur()["style_len"], prompts.cur()["style_lang_rule"]))
    out_rule = ("【輸出格式】先輸出完整文風檔，放在區塊裡：\n<<<文風>>>\n（完整檔案，含 YAML frontmatter：類型: 文風、狀態: 草稿、名稱: %s；標題「# 文風：%s」）\n<<<結束>>>\n"
                "區塊之後是給作者看的白話匯報。照範本的章節順序；「## 範例段落」標題原樣保留；"
                "不要自己寫「## 文字指標（程式統計）」一節（程式會補上）。不要提問，不確定的地方直接做最合理的選擇，在匯報列出來請作者確認。" % (name, name))
    if mode == "design":
        t = "為書庫的共用文風「%s」寫一份完整的文風檔。\n作者的描述：\n%s\n" % (name, _brief(params))
        if (params.get("note") or "").strip():
            t += "作者補充：%s\n" % params["note"].strip()
        if info["sample"]:
            t += ("作者附了寫作樣本：從樣本歸納特徵寫成規則（作者的描述優先），範例段落優先節錄樣本裡最有代表性的段落，"
                  "缺的場景類型再依規則補寫並標「（補寫）」。%s\n" % ("程式統計的文字指標也附上了，可以轉成範圍描述寫進規則。" if info["metrics"] else ""))
        if info["current"]:
            t += "這個名稱已經有舊檔，作者選擇重新設計；舊檔附在參考資料裡，作者寫過的具體偏好要保留。\n"
        t += "匯報包括：核心一句話、你選了哪幾項當核心與理由、需要作者確認的地方。\n"
        return "\n".join([t, common, out_rule])
    if mode == "revise":
        t = ("依作者意見調整共用文風「%s」。作者的意見：\n%s\n\n只改和意見相關的條目，其他原樣保留；新意見和舊規則衝突時以新意見為準，舊規則刪掉或改寫；"
             "作者刻意要用、但會被去 AI 味規則擋的寫法，寫進「允許的例外」並附用途。舊檔缺少範本裡的重要章節時可以順手補上。"
             "匯報用「舊 → 新」逐條列出改動。\n" % (name, params["note"].strip()))
        return "\n".join([t, common, out_rule])
    scene = (params.get("note") or "").strip() or "自己挑一個最能考驗這個文風的情境（通常是對白加一點動作）"
    return ("照共用文風「%s」試寫一段 %s的場景。情境：%s\n人名地名用原創的。\n"
            "寫完另起一段「自評」：逐條列出這段示範了哪幾條規則，以及哪條規則很難遵守或規則之間打架（代表規則可能要改）。\n"
            "只輸出試寫和自評，不要輸出 <<<文風>>> 區塊，不要改文風檔。" % (name, prompts.cur()["trial_len"], scene))


def reference_pack(info, plugin_dir, budget):
    pk = context.Pack(budget)
    if info["current"]:
        pk.add(0, "目前的文風檔", info["current"])
    if info["mode"] != "test":
        pk.add(0, "文風範本（章節順序照這個）", context.skill_ref(plugin_dir, "novel-setup/templates/文風.md"))
        pk.add(1, "文風的十三個面向", skill_file(plugin_dir, "references/style-dimensions.md"))
        if info["mode"] == "design":
            pk.add(2, "類型線索表", skill_file(plugin_dir, "references/genre-cues.md"))
    if info["metrics"]:
        pk.add(0, "樣本的文字指標（程式統計）", shared.metrics_md(info["metrics"]))
    if info["sample"]:
        s = info["sample"]
        pk.add(1, "作者的寫作樣本", s if len(s) <= SAMPLE_LIMIT else s[:SAMPLE_LIMIT] + "\n……（以下省略）")
    return pk


def claude_prompt(info, params, plugin_dir):
    """Claude Code：參考資料由 skill 自己讀，這裡只放作者的輸入。"""
    parts = ["請使用 novel-style skill。", task_text(info, params)]
    if info["current"]:
        parts.append("【目前的文風檔】\n" + info["current"])
    if info["metrics"]:
        parts.append("【樣本的文字指標（程式已統計，不用再跑）】\n" + shared.metrics_md(info["metrics"]))
    if info["sample"]:
        s = info["sample"]
        parts.append("【作者的寫作樣本】\n" + (s if len(s) <= SAMPLE_LIMIT else s[:SAMPLE_LIMIT] + "\n……（以下省略）"))
    parts.append("不要讀寫書庫裡的任何檔案；最後一則回覆照【輸出格式】輸出。")
    return "\n\n".join(parts)


def finish(library, info, out, truncated=False):
    """解析模型輸出、寫檔，回傳給作者看的結果文字。"""
    if info["mode"] == "test":
        return (out or "").strip()
    m = BLOCK_RE.search(out or "")
    report = BLOCK_RE.sub("", out or "").strip()
    if not m:
        msg = "模型沒有輸出完整的文風檔（找不到 <<<文風>>> 區塊），沒有寫入。"
        if truncated:
            msg += "輸出被截斷了，請調高「最大輸出」後再試一次。"
        raise DesignError(msg + ("\n\n模型的回覆：\n" + report[:1500] if report else ""))
    text = m.group(1).strip() + "\n"
    if "## 範例段落" not in text:
        text = text.rstrip() + "\n\n## 範例段落\n"
    text = shared.set_fm(shared.set_fm(text, "名稱", info["name"]), "類型", "文風")
    if re.search(r"(?m)^# ", text):
        text = re.sub(r"(?m)^# .*$", lambda _m: "# 文風：%s" % info["name"], text, count=1)
    else:
        text = re.sub(r"(?s)^(---.*?---\s*\n)", lambda _m: _m.group(1) + "\n# 文風：%s\n" % info["name"], text, count=1)
    if info["metrics"]:
        text = shared.put_metrics(text, info["metrics"])
    elif info["current"]:   # 保留舊檔的文字指標
        old = re.search(r"(?ms)^" + re.escape(shared.METRICS_HEAD) + r".*?(?=^## |\Z)", info["current"])
        if old and shared.METRICS_HEAD not in text:
            anchor = re.search(r"(?m)^## 範例段落", text)
            text = text[:anchor.start()] + old.group(0).rstrip() + "\n\n" + text[anchor.start():]
    p = info["path"]
    backup = ""
    if os.path.isfile(p):
        bdir = os.path.join(os.path.dirname(os.path.dirname(p)), ".備份")
        os.makedirs(bdir, exist_ok=True)
        bname = "文風_%s_%s.md" % (info["name"], time.strftime("%Y%m%d-%H%M%S"))
        with open(os.path.join(bdir, bname), "w", encoding="utf-8", newline="\n") as f:
            f.write(info["current"])
        backup = "（舊版備份在 _共用/.備份/%s）" % bname
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    head = "已寫入共用文風「%s」%s。" % (info["name"], backup)
    if truncated:
        head += "\n⚠ 輸出可能被截斷，請檢查檔案結尾。"
    return head + ("\n\n" + report if report else "")
