# -*- coding: utf-8 -*-
"""文風保真閉環：量測候選稿偏離本書文風多少，偏太多就帶著「數字目標＋作者原句」重寫一次。

為什麼是「閉環」而不是「檢查」
  原本只有一個手動按鈕（檢查用語與 AI 味）會提文風偏差，生成流程裡沒有它。
  這裡把它接到寫稿與去 AI 味之後：先量、偏太多就重寫一次、還偏就在匯報標記。
  零件（shared.parse_metrics／analyze／compare 的 13 指標）都沿用，只是接線。

門檻怎麼定
  文學本來就會波動，門檻太緊會把好稿子改壞。實測 demo 三本書每一章對自己的文風目標：
  多半是 0「明顯」、1～3「稍有」，所以預設門檻是 明顯 3、稍有 7——
  真的走鐘（句子長度、對白比例、段落節奏整組跑掉）才會觸發。可用環境變數調整。
"""
import contextlib
import os

from . import lang as lang_mod, project, prompts, shared

# 超過就重寫（可用 NS_STYLE_OBVIOUS／NS_STYLE_SLIGHT 覆寫）
LIMIT = {"obvious": int(os.environ.get("NS_STYLE_OBVIOUS") or 3),
         "slight": int(os.environ.get("NS_STYLE_SLIGHT") or 7)}
SAMPLE_MIN, SAMPLE_MAX = 40, 160      # 作者原句的長度範圍


def _read(path):
    return project.read_text(path) if os.path.isfile(path) else ""


@contextlib.contextmanager
def _book_lang(book_dir):
    """量測要用「這本書的語言」的統計程式：plugin／plugin-en／plugin-ja 各一支。"""
    prev = prompts.cur_lang()
    prompts.set_lang(lang_mod.book_lang(book_dir))
    try:
        yield
    finally:
        prompts.set_lang(prev)


def target_metrics(book_dir):
    """回傳 (指標 dict, 來源說明)。優先 設定/文風.md，沒填就用作者自己的正文。"""
    with _book_lang(book_dir):
        m = shared.parse_metrics(_read(os.path.join(book_dir, "設定", "文風.md")))
        if m:
            return m, "文風檔"
        sample = shared.book_sample(book_dir)
        if sample.strip():
            try:
                return shared.analyze(sample, exclude=shared.book_names(book_dir)), "作者正文"
            except shared.SharedError:
                pass
    return {}, ""


def evaluate(book_dir, text):
    """量一段文字的文風偏差。verdict：ok／off／short（樣本太短）／skip（沒有目標）。"""
    target, basis = target_metrics(book_dir)
    out = {"rows": [], "obvious": 0, "slight": 0, "verdict": "skip", "basis": basis,
           "limit": dict(LIMIT)}
    if not target:
        return out
    if not (text or "").strip():
        out["verdict"] = "empty"
        return out
    with _book_lang(book_dir):
        try:
            actual = shared.analyze(text, exclude=shared.book_names(book_dir))
        except shared.SharedError:
            out["verdict"] = "short"
            return out
        rows = shared.compare(target, actual)
    out["rows"] = rows
    out["obvious"] = sum(1 for r in rows if r["偏離"] == "明顯")
    out["slight"] = sum(1 for r in rows if r["偏離"] == "稍有")
    out["verdict"] = "off" if (out["obvious"] > LIMIT["obvious"] or out["slight"] > LIMIT["slight"]) else "ok"
    return out


def deviating(ev):
    """只留偏離的指標（明顯優先，再來稍有）。"""
    if not ev.get("rows"):
        return []
    rows = [r for r in ev["rows"] if r["偏離"] == "明顯"] + [r for r in ev["rows"] if r["偏離"] == "稍有"]
    return rows


def table_md(ev):
    """給任務匯報看的 13 指標表（目標／實際／差距）。"""
    if not ev.get("rows"):
        return ""
    head = "| 指標 | 目標 | 實際 | 差距 | 偏離 |\n|---|---|---|---|---|"
    body = ["| %s | %s | %s | %s | %s |" % (r["指標"], r["目標"], r["實際"], r["差距"], r["偏離"] or "")
            for r in ev["rows"]]
    return head + "\n" + "\n".join(body)


def summary(ev):
    if ev.get("verdict") == "short":
        return "文風無法量測（樣本太短）"
    if ev.get("verdict") == "skip":
        return "沒有文風目標，跳過文風檢查"
    return "文風偏差：明顯 %d、稍有 %d（門檻 %d／%d）" % (
        ev.get("obvious", 0), ev.get("slight", 0), LIMIT["obvious"], LIMIT["slight"])


def samples(book_dir, n=2):
    """作者自己的句子：優先從不同章各取一段，讓重寫有語感可以對。"""
    out = []
    chapters = sorted(project._scan_dir(os.path.join(book_dir, "正文")).items())
    for _no, fn in chapters:
        text = _read(os.path.join(book_dir, "正文", fn))
        body = project.split_frontmatter(text)[1] if text else ""
        for para in body.split("\n\n"):
            p = para.strip()
            if SAMPLE_MIN <= len(p) <= SAMPLE_MAX and not p.startswith(("#", "|", ">", "-")):
                out.append(p)
                break
        if len(out) >= n:
            break
    return out[:n]


def feedback(book_dir, ev, n=0, lang=None):
    """重寫用的指示：偏差的指標（目標／實際）、作者原句、輸出要求。"""
    lang = lang or lang_mod.book_lang(book_dir)
    rows = deviating(ev)[:6]
    lines = [prompts.t(lang, "style_retry_head").strip(), ""]
    for r in rows:
        lines.append(prompts.t(lang, "style_retry_line", name=r["指標"], target=r["目標"],
                               actual=r["實際"], level=r["偏離"]))
    ss = samples(book_dir)
    if ss:
        lines += ["", prompts.t(lang, "style_retry_samples", s1=ss[0], s2=ss[1] if len(ss) > 1 else ss[0])]
    lines += ["", prompts.t(lang, "style_retry_tail", n=n)]
    return "\n".join(lines)


def findings(book_dir, text):
    """給「檢查用語與 AI 味」用：偏離明顯的指標轉成提醒（沿用既有格式）。"""
    ev = evaluate(book_dir, text)
    out = []
    for r in deviating(ev):
        if r["偏離"] != "明顯":
            continue
        out.append({"等級": "提醒", "類型": "文風偏差", "行": 0,
                    "訊息": "「%s」目標 %s、實際 %s（差 %s）" % (r["指標"], r["目標"], r["實際"], r["差距"])})
    return out
