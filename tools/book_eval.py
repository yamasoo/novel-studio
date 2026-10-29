#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""書的回歸測試（報告 P4）：改提示詞之後，用固定 fixture 得到「哪些指標退步」。

    python tools/book_eval.py                       # 假 provider：只驗管線（不花錢，可 nightly）
    python tools/book_eval.py --provider deepseek   # 真 provider：驗品質（會花錢）
    python tools/book_eval.py --tasks deslop --books zh-TW
    python tools/book_eval.py --baseline eval/results/2026-10-29-1200-fake.json   # 和基線比

三種任務，都跑在 demo 三本示範書的副本上（不動原書）：
  continue  遮住最後一章（正文、章節摘要、候選），用前面既有的資料寫這一章
  deslop    對最後一章跑去 AI 味（原稿不動，結果寫在 .studio/修訂/*.draft.md）
  review    對最後一章跑審查，看工作台實際存下來的審查紀錄

指標以「確定性」為主（自己算，沒有模型雜訊）：
  文風偏差數（明顯／稍有）、檢查腳本問題數（含必須修）、名字保留率、數字保留率、
  字數比、產出語言是否正確、審查 JSON 是否合法、審查引用是否逐字命中。
LLM 評分刻意沒做：先確立「同一批 fixture、同一組數字、逐次可比」，再談主觀分數。

結果存 eval/results/<時間>-<模式>.json；給 --baseline 就逐項比對，退步會標出來並回傳 1。
"""
import argparse
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from studio import context, native, project, prompts, providers, revision, runner, shared, textguard  # noqa: E402

PLUGIN_DIR = os.path.join(ROOT, "plugin")
FIXTURES = [("zh-TW", "退婚之後"), ("en", "en_TheLanternRoad"), ("ja", "ja_辺境の薬師と竜の約束")]
TASKS = ("continue", "deslop", "review")
RESULTS = os.path.join(ROOT, "eval", "results")
# 長篇 fixture：放在 eval/fixtures.local.json（不進版控，因為是本機路徑）。
# 格式見 eval/fixtures.example.json；每一筆：{"key": ..., "path": 書的資料夾, "lang": ..., "chapter": 要遮的章}
FIXTURES_LOCAL = os.path.join(ROOT, "eval", "fixtures.local.json")
FIXTURES_EXAMPLE = os.path.join(ROOT, "eval", "fixtures.example.json")

# LLM 評分的固定 rubric（以確定性指標為主，這個只是輔助；分數有噪音，退步要看趨勢）
RUBRIC = """你是資深小說編輯。請只看「這一章」給 1–5 分（5 最好），四個面向各自給分：
- card：有沒有照章綱寫（章綱列的情節點、場景、鉤子）
- style：和這本書的寫法像不像（敘述視角、句子長度、對白比例）
- continuity：和前文接不接得上（人際關係、已知事實、時間地點）
- readable：能不能直接給讀者看（錯字、視角混亂、語意不通）
只輸出一個 JSON 物件：{"card": n, "style": n, "continuity": n, "readable": n, "reason": "一句話理由"}
不要加說明或程式碼圍欄。"""

# 分數方向：True＝越大越好。沒列到的指標只記錄、不判退步。
HIGHER_BETTER = {
    "names_kept": True, "digits_kept": True, "lang_ok": True,
    "review_json_ok": True, "review_quote_hit": True,
    "card_coverage": True, "llm_ok": True,
    "card_coverage_vs_human": True, "names_kept_vs_human": True,
    "llm_card": True, "llm_style": True, "llm_continuity": True, "llm_readable": True,
    "style_obvious": False, "style_slight": False,
    "issues": False, "issues_must": False, "length_ratio_off": False,
}
# 容許浮動：在門檻內不算退步（避免每次跑都在跳噪音）
TOLERANCE = {"names_kept": 0.05, "digits_kept": 0.02, "review_quote_hit": 0.1,
             "length_ratio_off": 0.05, "style_slight": 1, "style_obvious": 0.5,
             "card_coverage": 0.05, "card_coverage_vs_human": 0.1, "names_kept_vs_human": 0.1,
             # LLM 評分是 1–5 分、有噪音：差 0.5 分以內不算退步
             "llm_card": 0.5, "llm_style": 0.5, "llm_continuity": 0.5, "llm_readable": 0.5}


# ---------------------------------------------------------------------------
def read(p):
    return project.read_text(p) if os.path.isfile(p) else ""


def load_checker():
    """各語言自己的檢查腳本（textguard 依書的語言挑 plugin-en／plugin-ja）。"""
    spec = importlib.util.spec_from_file_location(
        "check_text", os.path.join(PLUGIN_DIR, "skills", "novel-deslop", "scripts", "check_text.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return textguard.wrap(mod)


CHECKER = None


def checker():
    global CHECKER
    if CHECKER is None:
        CHECKER = load_checker()
    return CHECKER


def issues_of(book, text):
    """用該語言的檢查腳本掃一段文字；寫成暫存檔再掃，不改動書。"""
    if not text.strip():
        return []
    fd, p = tempfile.mkstemp(suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        res = checker().check_file(p, checker().load_whitelist(book))
        return res.get("問題") or []
    except Exception:
        return []
    finally:
        try:
            os.remove(p)
        except OSError:
            pass


def digit_runs(text):
    return re.findall(r"\d+(?:\.\d+)?", text)


def has_han_run(text, limit=8):
    return any(len(m.group(0)) >= limit for m in re.finditer(r"[\u4e00-\u9fff]+", text))


def kana_ratio(text):
    return len(re.findall(r"[\u3040-\u30ff]", text)) / max(1, len(text))


def lang_ok(lang, text):
    if not text.strip():
        return 0
    if lang == "en":
        return 0 if has_han_run(text) else 1
    if lang == "ja":
        return 1 if kana_ratio(text) > 0.03 else 0
    return 1 if not has_han_run(text, 40) else 0


# ---------------------------------------------------------------------------
# 指標
# ---------------------------------------------------------------------------
# 無法量測時用這個值（例如樣本太短、書裡沒有文風指標也沒有正文），比對時略過
UNMEASURED = -1


def style_metrics(book, text):
    """文風偏差：目標優先取 設定/文風.md 的指標；沒填就用「作者自己的正文」當基準。

    示範書與不少實際的書都沒有填文風指標，這時退回「用全部正文算一組指標」——
    仍然有意義（比的是「像不像作者已經寫過的東西」），而且不需要人工先填資料。
    樣本太短（shared 要求 300 字以上）就標成無法量測，不要用 0 假裝「完全吻合」。
    """
    target = shared.parse_metrics(read(os.path.join(book, "設定", "文風.md")))
    if not target:
        sample = shared.book_sample(book)
        if not sample.strip():
            return {"style_obvious": UNMEASURED, "style_slight": UNMEASURED, "style_basis": "none"}
        try:
            target = shared.analyze(sample, exclude=shared.book_names(book))
        except shared.SharedError:
            return {"style_obvious": UNMEASURED, "style_slight": UNMEASURED, "style_basis": "short"}
    if not text.strip():
        return {"style_obvious": UNMEASURED, "style_slight": UNMEASURED, "style_basis": "empty"}
    try:
        actual = shared.analyze(text, exclude=shared.book_names(book))
    except shared.SharedError:
        return {"style_obvious": UNMEASURED, "style_slight": UNMEASURED, "style_basis": "short"}
    rows = shared.compare(target, actual)
    return {"style_obvious": sum(1 for r in rows if r["偏離"] == "明顯"),
            "style_slight": sum(1 for r in rows if r["偏離"] == "稍有")}


def card_coverage(card, output):
    """章綱的內容字有多少出現在稿子裡（不要求逐字，只看用詞有沒有跟上）。

    用跟檢索一樣的 bigram／單詞切法；只比章綱裡「比較罕見」的詞（出現兩次以上的去掉），
    所以「他」「說」這種到處都有的字不會把分數撐高。
    """
    if not (card or "").strip() or not (output or "").strip():
        return 0.0
    from studio.recall import _tokens      # 與檢索同一套分詞，避免兩邊算法不一致
    card_t = _tokens(card)
    out_t = set(_tokens(output))
    if not card_t:
        return 0.0
    freq = {}
    for t in card_t:
        freq[t] = freq.get(t, 0) + 1
    rare = [t for t in card_t if freq[t] <= 2]
    if not rare:
        return 0.0
    hit = sum(1 for t in set(rare) if t in out_t)
    return round(hit / len(set(rare)), 3)


def judge(prov, lang, card, output):
    """LLM 評分（可選）：固定 rubric，1–5 分。回傳 llm_* 指標；解析失敗只記錄不中斷。"""
    if not (output or "").strip():
        return {"llm_ok": 0}
    user = "【章綱】\n%s\n\n【要評的這一章】\n%s" % ((card or "（沒有章綱）")[:2000], output[:8000])
    try:
        text, _ = providers.chat(ROOT, prov, [{"role": "system", "content": RUBRIC},
                                             {"role": "user", "content": user}],
                                 json_mode=True, max_tokens=600)
        data = providers.parse_json(text)
    except Exception as e:
        return {"llm_ok": 0, "llm_note": str(e)[:60]}
    if not isinstance(data, dict):
        return {"llm_ok": 0}
    out = {"llm_ok": 1, "llm_reason": str(data.get("reason") or "")[:80]}
    for k in ("card", "style", "continuity", "readable"):
        try:
            out["llm_" + k] = float(data.get(k))
        except (TypeError, ValueError):
            out["llm_ok"] = 0
    return out


def score_deslop(book, lang, source, output):
    iss = issues_of(book, output)
    src_digits, pool = digit_runs(source), list(digit_runs(output))
    kept = 0
    for d in src_digits:
        if d in pool:
            pool.remove(d)
            kept += 1
    names = {n for n in shared.book_names(book) if n}
    src_names = {n for n in names if n in source}
    m = {
        "issues": len(iss),
        "issues_must": sum(1 for i in iss if (i.get("等級") or "") == "必須修"),
        "digits_kept": (kept / len(src_digits)) if src_digits else 1.0,
        "names_kept": (len({n for n in src_names if n in output}) / len(src_names)) if src_names else 1.0,
        "length_ratio_off": abs(len(output) / max(1, len(source)) - 1.0),
        "lang_ok": lang_ok(lang, output),
    }
    m.update(style_metrics(book, output))
    return m


def score_continue(book, lang, card, output):
    iss = issues_of(book, output)
    want = {n for n in shared.book_names(book) if n and n in card}
    got = {n for n in want if n in output}
    m = {
        "issues": len(iss),
        "issues_must": sum(1 for i in iss if (i.get("等級") or "") == "必須修"),
        "names_kept": (len(got) / len(want)) if want else 1.0,
        "card_coverage": card_coverage(card, output),
        "lang_ok": lang_ok(lang, output),
    }
    m.update(style_metrics(book, output))
    return m


def score_review(chapter_text, rec):
    """審查紀錄（工作台實際存下來的那份）→ 指標。quote 逐字命中是硬指標。"""
    if not isinstance(rec, dict) or not rec:
        return {"review_json_ok": 0, "review_items": 0, "review_quote_hit": 0.0,
                "review_must": 0, "review_suggest": 0, "review_note": 0}
    items = [i for i in (rec.get("items") or []) if isinstance(i, dict)]
    quotes = [str(i.get("quote") or "").strip() for i in items]
    quotes = [q for q in quotes if q]
    hit = [q for q in quotes if q in chapter_text]
    sev = [str(i.get("severity") or "") for i in items]
    return {
        "review_json_ok": 1 if rec.get("summary") is not None and isinstance(rec.get("items"), list) else 0,
        "review_items": len(items),
        "review_quote_hit": (len(hit) / len(quotes)) if quotes else 1.0,
        "review_must": sum(1 for s in sev if "必須" in s or s.lower().startswith("must")),
        "review_suggest": sum(1 for s in sev if "建議" in s or s.lower().startswith("should")),
        "review_note": sum(1 for s in sev if "提醒" in s or s.lower().startswith("note")),
    }


# ---------------------------------------------------------------------------
# 假的 provider：只驗「流程與提示詞組裝」，數字不代表品質
# ---------------------------------------------------------------------------
class FakeChat:
    """看 label 決定回什麼：寫稿／改稿回正文，其他（結構化輸出）回合法 JSON。

    之前用「提示詞裡有沒有 novel-review」判斷，日文寫稿的提示詞剛好提到這個字串，
    於是把 JSON 當成正文交回來——那是假 provider 的判斷太粗糙，不是流程有問題。
    """

    def __init__(self, lang="zh-TW"):
        self.lang = lang
        self.calls = 0

    def _prose(self, n=1):
        if self.lang == "en":
            return "# Chapter %d Fake\n\nThe fake provider wrote this paragraph." % n
        if self.lang == "ja":
            return "# 第%d章 偽\n\n偽のプロバイダが書いた段落です。" % n
        return "# 第%d章 假標題\n\n這是假 provider 寫的段落。" % n

    def chat(self, home, prov, messages, **kw):
        self.calls += 1
        label = str(kw.get("label") or "")
        prose = any(k in label for k in ("寫第", "去 AI 味", "修訂", "續寫"))
        if kw.get("json_mode") and not prose:
            body = json.dumps({"summary": "（假 provider）", "items": []}, ensure_ascii=False)
        else:
            body = self._prose()
        return body, {"prompt_tokens": 0, "completion_tokens": 0, "finish_reason": "stop"}


def with_fake(fake, fn):
    real_chat, real_call = providers.chat, native.Ctx.call

    def call(self, messages, **kw):
        return real_call(self, messages, **kw)
    providers.chat = fake.chat
    native.Ctx.call = call
    try:
        return fn()
    finally:
        providers.chat, native.Ctx.call = real_chat, real_call


def real_provider(pid):
    cfg = json.loads(read(os.path.join(ROOT, "config.json")) or "{}")
    prov = providers.resolve(cfg.get("providers") or providers.DEFAULT_PROVIDERS,
                             pid or cfg.get("default_provider") or "claude_code")
    if not prov:
        raise SystemExit("找不到執行者：%s（可用的有 %s）"
                         % (pid, "、".join(c["id"] for c in providers.choices(cfg.get("providers") or []))))
    if prov.get("type") == "claude_code":
        raise SystemExit("Claude Code 不能跑回歸測試（要走 /chat/completions），請用 --provider 指定 API 執行者。")
    if not str(prov.get("model") or "").strip():
        raise SystemExit("執行者「%s」還沒選模型。先到工作台「設定 → AI 執行者」按「測試連線／抓模型清單」選一個，\n"
                         "或用 --provider %s/<模型 id> 指定。" % (prov.get("id"), prov.get("id")))
    if not providers.key_status(ROOT, prov):
        env = prov.get("key_env") or "DEEPSEEK_API_KEY"
        hint = ""
        if not providers._keyring():
            hint = ("\n這支 python 讀不到系統金鑰庫（多半是沒安裝 keyring、或不是工作台用的那個 venv）。"
                    "\n請用工作台同一個 venv 跑，例如：\n"
                    "  & 'C:\\Users\\你\\venvs\\novel-studio\\Scripts\\python.exe' tools/book_eval.py --provider %s"
                    % (prov.get("id"),))
        raise SystemExit("執行者「%s」還沒有 API 金鑰。三種放法（擇一）：\n"
                         "  1. 工作台「設定 → AI 執行者」貼上金鑰（存進系統金鑰庫，推薦；app 與工具都讀得到）\n"
                         "  2. 設環境變數 %s —— 只在「設定它的那個視窗」有效：\n"
                         "       這個視窗：$env:%s = 'sk-...'\n"
                         "       以後都有效：setx %s \"sk-...\" 然後「開一個新視窗」\n"
                         "  3. 工作台資料夾的 secrets.json（明文，不進 git）%s"
                         % (prov.get("id"), env, env, env, hint))
    return prov


# ---------------------------------------------------------------------------
def load_fixtures():
    """回傳 [{key, name, path, lang, chapter(可空)}]。

    內建三本示範書；另外可加 eval/fixtures.local.json（本機路徑，不進版控）跑長篇。
    例：
      [{"key": "long-273", "path": "E:/dev/novel1/某本書", "lang": "zh-TW", "chapter": 200}]
    chapter 沒給就用最後一章（示範書的行為）。
    """
    out = [{"key": lang, "name": name, "path": os.path.join(ROOT, "demo", name), "lang": lang, "chapter": None}
           for lang, name in FIXTURES]
    if not os.path.isfile(FIXTURES_LOCAL):
        return out
    try:
        with open(FIXTURES_LOCAL, encoding="utf-8") as f:
            extra = json.load(f)
    except ValueError as e:
        raise SystemExit("eval/fixtures.local.json 不是合法 JSON：%s" % e)
    for it in extra if isinstance(extra, list) else []:
        path = it.get("path") or ""
        lang = it.get("lang") or "zh-TW"
        if not os.path.isdir(path):
            print("  （跳過 fixture：資料夾不存在 %s）" % path, flush=True)
            continue
        out.append({"key": it.get("key") or os.path.basename(path), "name": os.path.basename(path),
                    "path": path, "lang": lang, "chapter": it.get("chapter")})
    return out


def copy_book(entry, tmp):
    dst = os.path.join(tmp, "book")
    shutil.copytree(entry["path"], dst)
    return dst


def mask_from(book, no):
    """把第 no 章以後的稿子全部遮起來（正文、章節摘要、候選），模擬「寫到這裡」的當下。"""
    removed = 0
    for sub in ("正文", "追蹤/章節摘要", "候選"):
        d = project._scan_dir(os.path.join(book, sub))
        for n, fn in list(d.items()):
            if n >= no:
                try:
                    os.remove(os.path.join(book, sub, fn))
                    removed += 1
                except OSError:
                    pass
    return removed


def run_action(book, lang, action, params, prov):
    prompts.set_lang(lang)
    job = runner.Job(os.path.basename(book), book, action, "", meta={"action": action, "params": params},
                     provider=prov)
    with contextlib.redirect_stdout(io.StringIO()):
        native.run(job, prov, ROOT, PLUGIN_DIR, checker(), {})
    if job.status != "done":
        err = next((e.get("text") for e in reversed(job.events) if e["kind"] == "error"), job.status)
        raise RuntimeError("%s 失敗：%s" % (action, err))
    return job


def eval_book(entry, tasks, prov, judge_on=False, chapter=None, texts=None):
    """texts：有給就順便把每個任務的產出文字存進去（寫在另一個檔，基線不會變大）。"""
    lang = entry["lang"]
    target = chapter or entry.get("chapter")
    tmp = tempfile.mkdtemp(prefix="ns_eval_")
    out = {}
    try:
        book = copy_book(entry, tmp)
        for task in tasks:
            t0 = time.time()
            ch = project._scan_dir(os.path.join(book, "正文"))
            if task == "review":
                no = target or (max(ch) if ch else 0)
                if no:
                    run_action(book, lang, "review_notes", {"chapter": no}, prov)
                    rec = revision.load_review(book, no) or {}
                    body = read(os.path.join(book, "正文", ch[no])) if no in ch else ""
                    out["review"] = score_review(body, rec)
                    if texts is not None:
                        texts["review"] = {"chapter": no, "text": body[:12000],
                                           "items": (rec.get("items") or [])[:40]}
            elif task == "deslop":
                no = target or (max(ch) if ch else 0)
                if no:
                    src = read(os.path.join(book, "正文", ch[no]))
                    run_action(book, lang, "deslop", {"chapter": no}, prov)
                    rec = revision.load_revision(book, no) or {}
                    # 去 AI 味的結果：還躺在修訂紀錄裡就取 new_text，已經套用就讀回正文
                    now_files = project._scan_dir(os.path.join(book, "正文"))
                    polished = rec.get("new_text") or (read(os.path.join(book, "正文", now_files[no]))
                                                       if no in now_files else "")
                    out["deslop"] = score_deslop(book, lang, src, polished or "")
                    if texts is not None:
                        texts["deslop"] = {"chapter": no, "before": src[:6000], "after": (polished or "")[:12000]}
            elif task == "continue":
                no = target or (max(ch) if ch else 0)
                if no:
                    # 先量「人類原作」當對照（同一張章綱、同一章），再遮掉它
                    human = read(os.path.join(book, "正文", ch[no])) if no in ch else ""
                    _, card = context.card_text(book, no)
                    if not card:
                        print("   %-6s continue  跳過：第%d章沒有章綱" % (lang, no), flush=True)
                        continue
                    ref = score_continue(book, lang, card, human) if human else {}
                    removed = mask_from(book, no)      # 遮住這一章以後的稿子
                    run_action(book, lang, "write", {"from": no, "to": no}, prov)
                    made = project._scan_dir(os.path.join(book, "候選")).get(no)
                    text = read(os.path.join(book, "候選", made)) if made else ""
                    m = score_continue(book, lang, card, text)
                    m["masked"] = removed
                    if ref:
                        for k, v in ref.items():
                            m["ref_" + k] = v
                        # 和人類原作的比例（1.0＝和作者自己寫的一樣；低於 1 就是輸給原作）
                        for k in ("card_coverage", "names_kept"):
                            m[k + "_vs_human"] = (round(m[k] / ref[k], 2) if ref.get(k) else 0)
                    out["continue"] = m
                    if judge_on:
                        m.update(judge(prov, lang, card, text))
                    if texts is not None:
                        # 問題的行號要對得上，所以存「模型產出」與「檢查結果」
                        texts["continue"] = {"chapter": no, "text": text[:12000],
                                             "card": card[:2000], "issues": issues_of(book, text)[:60]}
            print("   %-6s %-9s %5.1f 秒" % (lang, task, time.time() - t0), flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def evaluate(entries, tasks, pid, judge_on=False, texts=None):
    """回傳 ({key: {task: 指標}}, 假 provider 呼叫次數or None)。texts：收集產出文字。"""
    if pid:
        prov = real_provider(pid)
        return {e["key"]: eval_book(e, tasks, prov, judge_on, texts=(texts.setdefault(e["key"], {}) if texts is not None else None))
                for e in entries}, None
    prov = {"id": "eval-fake", "type": "openai", "name": "fake", "model": "fake",
            "context_tokens": 65536, "max_output": 4096}
    res = {}
    for e in entries:
        fake = FakeChat(e["lang"])
        t = texts.setdefault(e["key"], {}) if texts is not None else None
        res[e["key"]] = with_fake(fake, lambda e=e, t=t: eval_book(e, tasks, prov, judge_on, texts=t))
        res[e["key"]]["_calls"] = fake.calls
    return res, sum(v.pop("_calls", 0) for v in res.values())


# ---------------------------------------------------------------------------
def flatten(results):
    flat = {}
    for lang, tasks in results.items():
        for task, m in tasks.items():
            for k, v in m.items():
                flat["%s/%s/%s" % (lang, task, k)] = v
    return flat


def compare_with(base, now):
    regress, rows = [], []
    for k in sorted(set(base) | set(now)):
        b, n = base.get(k), now.get(k)
        if b == UNMEASURED or n == UNMEASURED:
            rows.append((k, b, n, "無法量測"))
            continue
        if b is None or n is None:
            rows.append((k, b, n, "新增" if b is None else "未跑"))
            continue
        if isinstance(b, (int, float)) and isinstance(n, (int, float)):
            diff, name = n - b, k.rsplit("/", 1)[-1]
            tol = TOLERANCE.get(name, 0.0)
            direction = HIGHER_BETTER.get(name)
            mark = ""
            if direction is not None and abs(diff) > tol:
                worse = (diff < 0) if direction else (diff > 0)
                mark = "退步" if worse else "進步"
                if worse:
                    regress.append((k, b, n))
            rows.append((k, b, n, mark))
        else:
            rows.append((k, b, n, "" if b == n else "不同"))
    return rows, regress


def shown(path):
    """顯示用路徑：專案內就用相對路徑，在別的磁碟（例如 --out 指到 C:）就用絕對路徑。"""
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


def probe(pid):
    """一則極短請求，確認金鑰、模型、endpoint 都通（成本幾乎是 0）。"""
    prov = real_provider(pid)
    t0 = time.time()
    try:
        text, usage = providers.chat(ROOT, prov, [{"role": "user", "content": "回覆兩個字：可以"}], max_tokens=8)
    except Exception as e:
        raise SystemExit("連線失敗：%s" % e)
    print("連線成功：%s（%s／%s），%.1f 秒，回覆 %r"
          % (prov.get("id"), prov.get("name"), prov.get("model"), time.time() - t0, (text or "").strip()[:30]))
    if usage:
        print("   usage：%s" % json.dumps(usage, ensure_ascii=False))
    print("   下一步：python tools/book_eval.py --provider %s" % (pid or prov.get("id")))
    return 0


def resolve_baseline(path):
    """先確認基線存在再開跑——不然跑完整套（真 provider 會花錢、要好幾分鐘）才發現檔名打錯。"""
    if os.path.isdir(path):
        cands = sorted(f for f in os.listdir(path) if f.endswith(".json"))
        if not cands:
            raise SystemExit("基線資料夾裡沒有 .json：%s" % path)
        path = os.path.join(path, cands[-1])
    if not os.path.isfile(path):
        raise SystemExit(
            "找不到基線檔：%s\n"
            "第一次要先跑一次真 provider，把結果存成基線：\n"
            "  python tools/book_eval.py --provider <執行者>                 # 跑一次\n"
            "  Copy-Item (Get-ChildItem eval\\results\\*-real.json | Sort-Object LastWriteTime | Select-Object -Last 1) eval\\baseline.json\n"
            "之後才用 --baseline eval\\baseline.json 比對。" % path)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--books", default="zh-TW,en,ja",
                    help="要跑哪些 fixture：示範書用語言（zh-TW／en／ja），長篇用 fixtures.local.json 裡的 key")
    ap.add_argument("--tasks", default=",".join(TASKS), help="continue、deslop、review")
    ap.add_argument("--provider", help="真 provider 的執行者 id；不給就用假 provider")
    ap.add_argument("--out", default=RESULTS, help="結果資料夾（預設 eval/results）")
    ap.add_argument("--baseline", help="跟這份比對（.json，或給資料夾取最新一份）")
    ap.add_argument("--probe", action="store_true", help="只測金鑰與模型通不通：送一則極短請求就結束")
    ap.add_argument("--judge", action="store_true", help="額外用 LLM 依固定 rubric 評分（多花錢、有噪音）")
    ap.add_argument("--chapter", type=int, help="指定要遮／要處理的章號（預設：fixture 設定的或最後一章）")
    a = ap.parse_args()

    base_path = resolve_baseline(a.baseline) if a.baseline else None
    if a.probe:
        return probe(a.provider)

    all_fx = load_fixtures()
    want = [x.strip() for x in a.books.split(",") if x.strip()]
    entries = [e for e in all_fx if e["key"] in want]
    if not entries:
        raise SystemExit("找不到 fixture：%s\n可用的有：%s" % ("、".join(want), "、".join(e["key"] for e in all_fx)))
    tasks = [x.strip() for x in a.tasks.split(",") if x.strip() in TASKS]
    if not tasks:
        raise SystemExit("--tasks 是空的（continue、deslop、review）")
    mode = "real" if a.provider else "fake"
    if a.judge and not a.provider:
        raise SystemExit("--judge 要搭配 --provider（假 provider 的評分沒有意義）")
    t0 = time.time()
    texts = {}
    results, calls = evaluate(entries, tasks, a.provider, a.judge, texts)

    stamp = time.strftime("%Y-%m-%d-%H%M")
    payload = {"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "mode": mode,
               "provider": a.provider or "fake", "tasks": tasks,
               "books": [e["key"] for e in entries], "judge": bool(a.judge),
               "fixtures": [{"key": e["key"], "path": shown(e["path"]), "lang": e["lang"], "chapter": e["chapter"]}
                            for e in entries],
               "seconds": round(time.time() - t0, 1), "results": results}
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "%s-%s.json" % (stamp, mode))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print("== %s（%s，%.1f 秒%s%s）" % ("、".join(e["key"] for e in entries), mode, payload["seconds"],
                                       "，假 provider 共 %d 次呼叫" % calls if calls is not None else "",
                                       "，含 LLM 評分" if a.judge else ""))
    for key, tasks_res in results.items():
        for task, m in tasks_res.items():
            print("   %-14s %-9s %s" % (key, task, json.dumps(m, ensure_ascii=False)))
    print("   結果：%s" % shown(path))
    texts = {k: v for k, v in (texts or {}).items() if v}
    if texts:
        tpath = path.replace(".json", "-texts.json")
        with open(tpath, "w", encoding="utf-8", newline="\n") as f:
            json.dump(texts, f, ensure_ascii=False, indent=1)
        print("   產出（含檢查結果，方便追問題）：%s" % shown(tpath))
    if calls is not None:
        print("\n   （假 provider 只驗流程與提示詞組裝；數字不代表品質，要比品質請用 --provider）")

    if base_path:
        rows, regress = compare_with(flatten(json.loads(read(base_path)).get("results") or {}),
                                     flatten(results))
        print("\n== 與基線 %s 比對" % os.path.basename(base_path))
        for k, b, n, mark in rows:
            if mark:
                print("   %-8s %-42s %s → %s" % (mark, k, b, n))
        print("   " + ("有 %d 項退步" % len(regress) if regress else "沒有退步的指標"))
        return 1 if regress else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
