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

# 分數方向：True＝越大越好。沒列到的指標只記錄、不判退步。
HIGHER_BETTER = {
    "names_kept": True, "digits_kept": True, "lang_ok": True,
    "review_json_ok": True, "review_quote_hit": True,
    "style_obvious": False, "style_slight": False,
    "issues": False, "issues_must": False, "length_ratio_off": False,
}
# 容許浮動：在門檻內不算退步（避免每次跑都在跳噪音）
TOLERANCE = {"names_kept": 0.05, "digits_kept": 0.02, "review_quote_hit": 0.1,
             "length_ratio_off": 0.05, "style_slight": 1, "style_obvious": 0.5}


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
    def __init__(self, lang="zh-TW"):
        self.lang = lang
        self.calls = 0

    def chat(self, home, prov, messages, **kw):
        self.calls += 1
        text = "\n".join(str(m.get("content") or "") for m in messages)
        if kw.get("json_mode") or "novel-review" in text:
            body = json.dumps({"summary": "（假 provider）", "items": []}, ensure_ascii=False)
        elif self.lang == "en":
            body = "# Chapter 1 Fake\n\nThe fake provider wrote this paragraph."
        elif self.lang == "ja":
            body = "# 第1章 偽\n\n偽のプロバイダが書いた段落です。"
        else:
            body = "# 第1章 假標題\n\n這是假 provider 寫的段落。"
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
        raise SystemExit("執行者「%s」還沒有 API 金鑰。三種放法（擇一）：\n"
                         "  1. 工作台「設定 → AI 執行者」貼上金鑰（存進系統金鑰庫，推薦）\n"
                         "  2. 設環境變數 %s（在跑這支指令的同一個 shell 裡）\n"
                         "  3. 工作台資料夾的 secrets.json（明文，不進 git）"
                         % (prov.get("id"), prov.get("key_env") or "API 金鑰"))
    return prov


# ---------------------------------------------------------------------------
def copy_book(name, tmp):
    dst = os.path.join(tmp, "book")
    shutil.copytree(os.path.join(ROOT, "demo", name), dst)
    return dst


def hide_last_chapter(book):
    ch = project._scan_dir(os.path.join(book, "正文"))
    if not ch:
        return 0
    no = max(ch)
    os.remove(os.path.join(book, "正文", ch[no]))
    for sub in ("追蹤/章節摘要", "候選"):
        d = project._scan_dir(os.path.join(book, sub))
        if no in d:
            os.remove(os.path.join(book, sub, d[no]))
    return no


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


def eval_book(lang, name, tasks, prov):
    tmp = tempfile.mkdtemp(prefix="ns_eval_")
    out = {}
    try:
        book = copy_book(name, tmp)
        if "review" in tasks:
            ch = project._scan_dir(os.path.join(book, "正文"))
            no = max(ch) if ch else 0
            if no:
                run_action(book, lang, "review_notes", {"chapter": no}, prov)
                out["review"] = score_review(read(os.path.join(book, "正文", ch[no])),
                                             revision.load_review(book, no) or {})
        if "deslop" in tasks:
            ch = project._scan_dir(os.path.join(book, "正文"))
            no = max(ch) if ch else 0
            if no:
                src = read(os.path.join(book, "正文", ch[no]))
                run_action(book, lang, "deslop", {"chapter": no}, prov)
                rec = revision.load_revision(book, no) or {}
                # 去 AI 味的結果：還躺在修訂紀錄裡就取 new_text，已經套用就讀回正文
                now_files = project._scan_dir(os.path.join(book, "正文"))
                polished = rec.get("new_text") or (read(os.path.join(book, "正文", now_files[no]))
                                                  if no in now_files else "")
                out["deslop"] = score_deslop(book, lang, src, polished or "")
        if "continue" in tasks:
            no = hide_last_chapter(book)
            if no:
                _, card = context.card_text(book, no)
                run_action(book, lang, "write", {"from": no, "to": no}, prov)
                made = project._scan_dir(os.path.join(book, "候選")).get(no)
                out["continue"] = score_continue(book, lang, card,
                                                 read(os.path.join(book, "候選", made)) if made else "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def evaluate(langs, tasks, pid):
    """回傳 ({lang: {task: 指標}}, 假 provider 呼叫次數or None)。"""
    if pid:
        prov = real_provider(pid)
        return {lang: eval_book(lang, dict(FIXTURES)[lang], tasks, prov) for lang in langs}, None
    prov = {"id": "eval-fake", "type": "openai", "name": "fake", "model": "fake",
            "context_tokens": 65536, "max_output": 4096}
    res = {}
    for lang in langs:
        fake = FakeChat(lang)
        res[lang] = with_fake(fake, lambda: eval_book(lang, dict(FIXTURES)[lang], tasks, prov))
        res[lang]["_calls"] = fake.calls
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--books", default="zh-TW,en,ja", help="zh-TW、en、ja，可用逗號分隔")
    ap.add_argument("--tasks", default=",".join(TASKS), help="continue、deslop、review")
    ap.add_argument("--provider", help="真 provider 的執行者 id；不給就用假 provider")
    ap.add_argument("--out", default=RESULTS, help="結果資料夾（預設 eval/results）")
    ap.add_argument("--baseline", help="跟這份比對（.json，或給資料夾取最新一份）")
    a = ap.parse_args()

    langs = [x.strip() for x in a.books.split(",") if x.strip() in dict(FIXTURES)]
    tasks = [x.strip() for x in a.tasks.split(",") if x.strip() in TASKS]
    if not langs or not tasks:
        raise SystemExit("--books 或 --tasks 是空的（books：zh-TW,en,ja；tasks：continue,deslop,review）")
    mode = "real" if a.provider else "fake"
    t0 = time.time()
    results, calls = evaluate(langs, tasks, a.provider)

    stamp = time.strftime("%Y-%m-%d-%H%M")
    payload = {"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "mode": mode,
               "provider": a.provider or "fake", "tasks": tasks, "books": langs,
               "seconds": round(time.time() - t0, 1), "results": results}
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "%s-%s.json" % (stamp, mode))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print("== %s（%s，%.1f 秒%s）" % (",".join(langs), mode, payload["seconds"],
                                     "，假 provider 共 %d 次呼叫" % calls if calls is not None else ""))
    for lang, tasks_res in results.items():
        for task, m in tasks_res.items():
            print("   %-6s %-9s %s" % (lang, task, json.dumps(m, ensure_ascii=False)))
    print("   結果：%s" % shown(path))
    if calls is not None:
        print("\n   （假 provider 只驗流程與提示詞組裝；數字不代表品質，要比品質請用 --provider）")

    if a.baseline:
        base_path = a.baseline
        if os.path.isdir(base_path):
            cands = sorted(f for f in os.listdir(base_path) if f.endswith(".json"))
            if not cands:
                raise SystemExit("基線資料夾裡沒有 .json：%s" % base_path)
            base_path = os.path.join(base_path, cands[-1])
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
