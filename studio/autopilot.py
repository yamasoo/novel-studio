# -*- coding: utf-8 -*-
"""自動駕駛的檢查點：每 K 章停下來看一次，不及格就停在那一章等人。

為什麼要有它
  「連續寫到最後一章」原本的風險是：一路寫下去，到第 30 章才發現文風跑掉或設定衝突，
  前面 20 章都要重來。檢查點把「品質」變成流程的一部分，而不是事後補救。

看三件事（全部本機計算，不花錢）：
  1. 必須修：這幾章的正文有沒有「必須修」等級的錯（簡體字、標點、視角跳躍……）
  2. 文風：這幾章偏離本書文風的倍數有沒有超過上限（預設 2.4＝閘門 1.2 的兩倍）
  3. 漂移：用 P5 的偵測找「角色消失／伏筆欠帳／章綱沒寫到」

停下來只是「不繼續寫」，不會改任何檔案；按「繼續」就會再跑 K 章。
"""
import os

from . import drift, project, style_loop

EVERY = 10
STOP_MUST = 1        # 這幾章累計幾個「必須修」就停
STOP_STYLE = 2.4     # 偏離本書文風幾倍就停（閘門 1.2 的兩倍）


def default_checker(book_dir):
    """沒有傳 checker 時，載入 plugin（繁中）的檢查器；英文／日文書請由呼叫端傳入。"""
    import importlib.util

    from . import textguard
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(here, "plugin", "skills", "novel-deslop", "scripts", "check_text.py")
    if not os.path.isfile(p):
        return None
    spec = importlib.util.spec_from_file_location("check_text_auto", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return textguard.wrap(mod)


def checkpoint(book_dir, upto, every=EVERY, stop_must=STOP_MUST, stop_style=STOP_STYLE, checker=None):
    """回傳 {ok, reasons, stats, range, findings}。ok=False 時 reasons 是給作者看的原因。"""
    start = max(1, upto - max(1, every) + 1)
    d = drift.drift(book_dir, start, upto)
    reasons = []
    stats = {"must": 0, "style_max_rel": 0.0, "drift": 0}

    chk = checker or default_checker(book_dir)
    must_chapters = []
    if chk:
        for no, fn in sorted(project._scan_dir(os.path.join(book_dir, "正文")).items()):
            if not (start <= no <= upto):
                continue
            try:
                res = chk.check_file(os.path.join(book_dir, "正文", fn), chk.load_whitelist(book_dir))
            except Exception:
                continue
            n = sum(1 for f in res.get("問題") or [] if f["等級"] == "必須修")
            if n:
                stats["must"] += n
                must_chapters.append(no)
    if stats["must"] >= stop_must:
        reasons.append("第 %s 章有「必須修」的問題共 %d 項"
                       % ("、".join(str(x) for x in must_chapters[:5]), stats["must"]))

    worst = max((r["max_rel"] for r in d.get("style") or []), default=0)
    stats["style_max_rel"] = round(worst, 2)
    if worst >= stop_style:
        top = max(d["style"], key=lambda r: r["max_rel"]) if d.get("style") else {}
        reasons.append("文風偏離 %.2f 倍（門檻 %.1f；第%d章偏在「%s」）"
                       % (worst, stop_style, top.get("chapter", 0), top.get("worst") or "?"))

    fs = drift.findings(d)
    stats["drift"] = len(fs)
    # 漂移只是線索（全書累積的伏筆欠帳、久未登場的角色不是這幾章造成的），不當停下的條件；
    # 真正會擋的是「必須修」與「文風偏離超過閘門兩倍」——跟報告 P7 的預設一致。
    stats["drift_note"] = fs[0] if fs else ""

    return {"ok": not reasons, "reasons": reasons, "stats": stats, "range": [start, upto],
            "findings": fs[:8]}


def summary(res):
    if res["ok"]:
        s = "第%d–%d章檢查點通過（必須修 %d、文風最大偏離 %.2f 倍、漂移線索 %d 條）" % (
            res["range"][0], res["range"][1], res["stats"]["must"],
            res["stats"]["style_max_rel"], res["stats"]["drift"])
        if res["stats"].get("drift_note"):
            s += "\n留意：" + res["stats"]["drift_note"]
        return s
    return "檢查點沒過，先停在這裡：\n" + "\n".join("- " + r for r in res["reasons"])
