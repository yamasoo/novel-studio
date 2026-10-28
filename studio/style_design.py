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


def _t(key, **kw):
    s = prompts.cur()[key]
    return s.format(**kw) if kw else s


def _brief(params):
    names = _t("sd_brief_labels").split("|")
    rows = list(zip(names, [params.get(k) for k in ("genre", "feel", "refs", "pov", "readers", "avoid")]))
    return "\n".join(_t("sd_brief_line", k=k, v=v.strip()) for k, v in rows if (v or "").strip()) or _t("sd_brief_none")


def task_text(info, params):
    """給模型的任務說明（不含參考資料）。"""
    mode, name = info["mode"], info["name"]
    common = _t("sd_common", style_len=_t("style_len"), lang_rule=_t("style_lang_rule"))
    out_rule = _t("sd_out_rule", name=name)
    if mode == "design":
        t = _t("sd_design", name=name, brief=_brief(params))
        if (params.get("note") or "").strip():
            t += _t("sd_note", note=params["note"].strip())
        if info["sample"]:
            t += _t("sd_sample", metrics=_t("sd_sample_metrics") if info["metrics"] else "")
        if info["current"]:
            t += _t("sd_current")
        t += _t("sd_report")
        return "\n".join([t, common, out_rule])
    if mode == "revise":
        t = _t("sd_revise", name=name, note=params["note"].strip())
        return "\n".join([t, common, out_rule])
    scene = (params.get("note") or "").strip() or _t("sd_scene_default")
    return _t("sd_test", name=name, trial_len=_t("trial_len"), scene=scene)


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
        pk.add(1, "作者的寫作樣本", s if len(s) <= SAMPLE_LIMIT else s[:SAMPLE_LIMIT] + _t("cut_tail"))
    return pk


def claude_prompt(info, params, plugin_dir):
    """Claude Code：參考資料由 skill 自己讀，這裡只放作者的輸入。"""
    parts = [_t("sd_claude_use"), task_text(info, params)]
    if info["current"]:
        parts.append(_t("sd_claude_current") + info["current"])
    if info["metrics"]:
        parts.append(_t("sd_claude_metrics") + shared.metrics_md(info["metrics"]))
    if info["sample"]:
        s = info["sample"]
        parts.append(_t("sd_claude_sample") + (s if len(s) <= SAMPLE_LIMIT else s[:SAMPLE_LIMIT] + _t("cut_tail")))
    parts.append(_t("sd_claude_tail"))
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
