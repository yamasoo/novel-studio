# -*- coding: utf-8 -*-
"""文風保真閉環：量測候選稿偏離本書文風多少，偏太多就帶著「數字目標＋作者原句」重寫一次。

為什麼是「閉環」而不是「檢查」
  原本只有一個手動按鈕（檢查用語與 AI 味）會提文風偏差，生成流程裡沒有它。
  這裡把它接到寫稿與去 AI 味之後：先量、偏太多就重寫一次、還偏就在匯報標記。
  零件（shared.parse_metrics／analyze／compare 的 13 指標）都沿用，只是接線。

門檻怎麼定
  文學本來就會波動，門檻太緊會把好稿子改壞。但真書實測發現「明顯」這一級很乾淨：
    - 作者自己的章節：幾乎都是 0 項明顯（示範書 6 章、真書抽樣 36 章，最多 1 項）
    - 模型寫的章節：常見 2～3 項明顯（對白比例偏高、刪節號幾乎不用、段落偏碎）
  所以預設門檻是 明顯 2、稍有 7——作者自己不會被誤擋，模型的典型走鐘會被抓到。
  代價是約 17% 的章節會多重寫一次（示範書 12 章抽樣實測）。可用環境變數
  NS_STYLE_OBVIOUS／NS_STYLE_SLIGHT 調整。
"""
import contextlib
import os

from . import lang as lang_mod, project, prompts, shared

# 達到門檻就重寫（可用 NS_STYLE_REL／NS_STYLE_OBVIOUS／NS_STYLE_SLIGHT 覆寫）。
#
# 為什麼是「幅度」而不是「幾項偏離」：真書實測 24 章，作者自己的章節有 7 章出現 2 項以上「明顯」，
# 光看項數會誤擋 29% 的稿子。改看單一指標偏離了幾個「明顯」門檻（偏離值）：
#   作者自己：中位數 0.56、最大 1.18
#   模型寫的：1.32（對白比例 44% vs 目標 19%）
#   故意走鐘：22
# 所以門檻定 1.2（單一指標偏離達 1.2 倍），並用 obvious 4／slight 8 當「整組跑掉」的保險。
# 注意：這是 tripwire（抓明顯走鐘），不是品質閘門——1.18 與 1.32 的邊界很窄。
LIMIT = {"rel": float(os.environ.get("NS_STYLE_REL") or 1.2),
         "obvious": int(os.environ.get("NS_STYLE_OBVIOUS") or 4),
         "slight": int(os.environ.get("NS_STYLE_SLIGHT") or 8)}
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


_TARGET_CACHE = {}      # (book_dir, 版本指紋) → (指標, 來源)；避免每章都重量一次整本書


def _fingerprint(book_dir):
    """書的版本指紋：文風檔 + 正文檔的檔名/大小/mtime。內容沒變就重用上次算的目標。"""
    items = []
    p = os.path.join(book_dir, "設定", "文風.md")
    try:
        st = os.stat(p)
        items.append((st.st_size, int(st.st_mtime)))
    except OSError:
        items.append(0)
    ch = os.path.join(book_dir, "正文")
    try:
        names = sorted(os.listdir(ch))
    except OSError:
        names = []
    items.append((len(names), names[:1], names[-1:]))
    try:
        last = os.stat(os.path.join(ch, names[-1])).st_mtime if names else 0
        items.append(int(last))
    except OSError:
        pass
    return hash(tuple(str(x) for x in items))


def target_metrics(book_dir):
    """回傳 (指標 dict, 來源說明)。優先 設定/文風.md，沒填就用作者自己的正文。

    量整本書不便宜（百萬字的書要幾秒），而一次漂移掃描會對每一章都問一次同樣的目標，
    所以用「文風檔＋正文變動」當指紋快取：書沒改就重用。
    """
    key = (os.path.abspath(book_dir), _fingerprint(book_dir))
    hit = _TARGET_CACHE.get(key)
    if hit is not None:
        return hit
    with _book_lang(book_dir):
        m = shared.parse_metrics(_read(os.path.join(book_dir, "設定", "文風.md")))
        if m:
            _TARGET_CACHE.clear()
            _TARGET_CACHE[key] = (m, "文風檔")
            return _TARGET_CACHE[key]
        sample = shared.book_sample(book_dir)
        if sample.strip():
            try:
                got = (shared.analyze(sample, exclude=shared.book_names(book_dir)), "作者正文")
                _TARGET_CACHE.clear()
                _TARGET_CACHE[key] = got
                return got
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
    out["max_rel"] = max([r.get("偏離值") or 0 for r in rows] or [0])
    out["mean_rel"] = (sum(r.get("偏離值") or 0 for r in rows) / len(rows)) if rows else 0
    out["worst"] = prompts.label(max(rows, key=lambda r: r.get("偏離值") or 0)["指標"]) if rows else ""
    off = (out["max_rel"] >= LIMIT["rel"] or out["obvious"] >= LIMIT["obvious"]
           or out["slight"] >= LIMIT["slight"])
    out["verdict"] = "off" if off else "ok"
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
    body = ["| %s | %s | %s | %s | %s |" % (prompts.label(r["指標"]), r["目標"], r["實際"], r["差距"],
                                            prompts.label(r["偏離"]) if r["偏離"] else "")
            for r in ev["rows"]]
    return head + "\n" + "\n".join(body)


def summary(ev):
    if ev.get("verdict") == "short":
        return "文風無法量測（樣本太短）"
    if ev.get("verdict") == "skip":
        return "沒有文風目標，跳過文風檢查"
    tail = ""
    if ev.get("worst"):
        tail = "；偏最多：%s（%.2f 倍）" % (ev["worst"], ev.get("max_rel") or 0)
    return "文風偏差：明顯 %d、稍有 %d%s" % (ev.get("obvious", 0), ev.get("slight", 0), tail)


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
                               actual=r["實際"],
                               level="%s，偏離 %.2f 倍" % (r["偏離"], r.get("偏離值") or 0)))
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
