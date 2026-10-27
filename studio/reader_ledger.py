"""讀者認知帳本：從時間線轉換成草稿（舊書用）。

時間線記「事件」：作者真相＋讀者目前知道多少。讀者認知帳本記「讀者腦中的狀態」：
已知（讀者知道、但角色未必知道的關鍵資訊）、懸念（讀者在等答案的問題）、誤認（讀者誤以為的事）。
轉換結果一律先存成草稿，作者確認後才變成正式的帳本。
"""
import os
import re

from . import context, project, tracking

BATCH = 40   # 每次送給模型的時間線列數

SCHEMA = """請只輸出一個 JSON 物件，格式：
{"items": [
  {"類型": "已知|懸念|誤認", "內容": "讀者的認知（懸念寫成讀者在問的問題；誤認寫成讀者以為的事）",
   "作者真相": "答案或真相（時間線的實際發生有寫才填，沒有就留空，不要自己編）",
   "種下章": "第NNN章（讀者開始有這個認知的章；看不出來就留空）",
   "回收章": "已經揭曉或澄清的章；預計揭曉的章也可以填；還沒定就留空",
   "相關角色": "…", "來源": "時間線編號"}
]}"""

RULES = """轉換規則：
- 從每一列的「讀者目前知道」判斷讀者腦中的狀態，「實際發生（作者真相）」是答案。
- 讀者完全不知道這件事發生過的，不用登記（那是作者的底牌，時間線已經記了）；讀者察覺到異狀、在等答案的，登記成「懸念」。
- 讀者被引導相信了錯的版本，登記成「誤認」，內容寫讀者以為的版本，作者真相寫實際的版本。
- 讀者知道、但劇中某些角色還不知道的關鍵資訊（戲劇反諷），登記成「已知」，內容寫明「誰還不知道」。一般已揭曉的事件不用登記成已知。
- 已經在某章揭曉的懸念和誤認也要登記，回收章填那一章（帳本會記得它已經回收，寫稿時不會再帶）。
- 一列時間線可以產生零到多條；同一個問題跨好幾列的，合併成一條，來源寫多個編號。
- 內容要短（一句話），用讀者的角度寫，不要加評論。"""


def _rows_md(headers, rows):
    return context.table_md(headers, rows)


def prompts(book_dir):
    """回傳 [(標籤, 使用者訊息)]，每批一則。"""
    tl = project.read_table(book_dir, "追蹤/時間線.md")
    rows, hs = tl["rows"], tl["headers"]
    if not rows:
        raise project.ProjectError("這本書還沒有時間線，沒有東西可以轉換")
    to = tracking.tracked_to(book_dir) or 0
    head = "這本書目前寫到第%d章。以下是時間線的一部分，請轉換成讀者認知帳本的條目。\n%s\n\n%s" % (to, RULES, SCHEMA)
    out = []
    for i in range(0, len(rows), BATCH):
        part = rows[i:i + BATCH]
        label = "轉換讀者認知 %d／%d" % (i // BATCH + 1, (len(rows) + BATCH - 1) // BATCH)
        out.append((label, head + "\n\n【時間線】\n" + _rows_md(hs, part)))
    return out


def claude_prompt(book_dir):
    to = tracking.tracked_to(book_dir) or 0
    return ("請讀取 追蹤/時間線.md（用 Read），把它轉換成讀者認知帳本的條目。這本書目前寫到第%d章。\n%s\n\n%s\n\n"
            "不要修改任何檔案。最後一則回覆只輸出 JSON，不要加說明或程式碼圍欄。" % (to, RULES, SCHEMA))


def _norm(s):
    return re.sub(r"[\s，。、；：「」『』！？,.;:!?]", "", str(s or ""))


def merge(results):
    """把各批結果合併、去重。results 是 parse 後的 dict 清單。"""
    items, seen = [], set()
    for data in results:
        for it in (data or {}).get("items") or []:
            if not isinstance(it, dict) or not str(it.get("內容") or "").strip():
                continue
            k = _norm(it.get("內容"))
            if k in seen:
                continue
            seen.add(k)
            src = str(it.get("來源") or "").strip()
            if src and src not in str(it["內容"]):
                # 來源編號附在內容後面，作者核對時好找回時間線
                it = dict(it, 內容="%s（%s）" % (str(it["內容"]).strip(), src))
            items.append(it)
    order = {"懸念": 0, "誤認": 1, "已知": 2}
    items.sort(key=lambda x: (order.get(x.get("類型"), 0), _first(x.get("種下章"))))
    return items


def _first(s):
    n = [int(x) for x in re.findall(r"\d+", str(s or ""))]
    return n[0] if n else 99999


def save_draft(book_dir, items):
    if not items:
        raise project.ProjectError("模型沒有轉換出任何條目")
    path = os.path.join(book_dir, *tracking.RP_DRAFT.split("/"))
    to = tracking.tracked_to(book_dir) or 0
    n = tracking.write_reader_table(path, items, tracking.chapter_label(to) if to else "", draft=True)
    cnt = {t: sum(1 for x in items if x.get("類型") == t) for t in tracking.RP_TYPES}
    opened = sum(1 for x in items if x.get("類型") != "已知" and not str(x.get("回收章") or "").strip())
    return ("**讀者認知草稿已建立**（%s，共 %d 條：懸念 %d、誤認 %d、已知 %d；還沒回收的 %d 條）\n\n"
            "請到「追蹤」的「讀者認知」分頁核對：AI 可能把作者的底牌寫成懸念，或漏掉你埋的誤導。"
            "確認後按「採用草稿」才會生效；採用前不會影響寫稿。" % (tracking.RP_DRAFT, n, cnt["懸念"], cnt["誤認"], cnt["已知"], opened))


# ---------------------------------------------------------------------------
# 回收比對：轉換只看得到「當時讀者不知道」，看不到後面哪一章揭曉。這一步拿後面的時間線與章節摘要逐條比對。
RECON_BATCH = 30

RECON_SCHEMA = """請只輸出一個 JSON 物件，格式（沒有變化的條目不用列）：
{"changes": [
  {"編號": "R005", "動作": "回收|部分|合併",
   "回收章": "動作是回收時：讀者知道答案的那一章（第NNN章）",
   "內容": "動作是部分時：改寫成讀者剩下還不知道的部分",
   "合併到": "動作是合併時：要併入的條目編號",
   "理由": "一句話，寫出根據（時間線編號或第幾章摘要）"}
]}"""

RECON_RULES = """判斷規則：
- 「回收」：後面的時間線或章節摘要寫明讀者已經知道答案（不是角色知道，是讀者讀到了）。回收章填讀者知道的那一章，不能晚於目前寫到的章。
- 「部分」：只回答了一部分，把內容改寫成剩下的問題（例如「是誰陷害了林父？」→「沈老爺之外，還有誰參與陷害林父？」）；回收章留空。
- 「合併」：和另一條是同一個問題，併入那一條（留下種下章比較早、寫得比較清楚的那條）。
- 只根據提供的資料判斷，看不出來就不要列；寧可漏判，不要把還沒揭曉的寫成回收。
- 已知類型不用判斷。"""


def ledger_source(book_dir):
    """回收比對的來源：有草稿就比對草稿，沒有就比對正式帳本。"""
    for rel in (tracking.RP_DRAFT, tracking.RP_FILE):
        t = project.read_table(book_dir, rel)
        if t["rows"]:
            return rel, t["rows"]
    raise project.ProjectError("還沒有讀者認知帳本或草稿，請先「從時間線建立」")


def _open_rows(rows):
    return [r for r in rows if r.get("類型") != "已知" and not str(r.get("回收章") or "").strip()]


def _index(rows):
    return "\n".join("- %s〔%s〕%s" % (r.get("編號", ""), r.get("類型", ""), r.get("內容", "")) for r in rows)


def _timeline_after(book_dir, start):
    tl = project.read_table(book_dir, "追蹤/時間線.md")
    keep = [r for r in tl["rows"] if _first(r.get("揭示章")) >= start]
    return "\n".join("- %s（%s）讀者知道：%s" % (r.get("編號", ""), r.get("揭示章", ""), r.get("讀者目前知道", "")) for r in keep)


def _summaries_after(book_dir, start):
    sums = project._scan_dir(os.path.join(book_dir, "追蹤", "章節摘要"))
    return "\n\n".join("第%d章：%s" % (k, context.body(context.read(book_dir, "追蹤/章節摘要/" + sums[k])).strip())
                       for k in sorted(sums) if k >= start)


def recon_packs(book_dir, budget):
    """回傳 [(標籤, 使用者訊息, 被略過的段落)]。"""
    rel, rows = ledger_source(book_dir)
    opens = _open_rows(rows)
    if not opens:
        raise project.ProjectError("沒有還沒回收的懸念或誤認")
    to = tracking.tracked_to(book_dir) or 0
    out = []
    n = (len(opens) + RECON_BATCH - 1) // RECON_BATCH
    for i in range(0, len(opens), RECON_BATCH):
        part = opens[i:i + RECON_BATCH]
        start = min(_first(r.get("種下章")) for r in part)
        start = 1 if start == 99999 else start
        pk = context.Pack(budget)
        pk.add(0, "要判斷的條目（還沒回收）", context.table_md(tracking.RP_HEADERS, part))
        pk.add(1, "帳本全部條目（合併時用）", _index(rows))
        pk.add(2, "時間線：各章讀者知道了什麼（第%d章以後）" % start, _timeline_after(book_dir, start))
        pk.add(3, "章節摘要（第%d章以後）" % start, _summaries_after(book_dir, start), keep="tail")
        text, used, dropped = pk.build()
        task = ("這本書目前寫到第%d章。讀者認知帳本是從時間線轉換的，只記了「當時讀者不知道」，沒記後面哪一章揭曉。"
                "請逐條判斷上面「要判斷的條目」到第%d章為止是否已經揭曉。\n%s\n\n%s" % (to, to, RECON_RULES, RECON_SCHEMA))
        out.append(("比對讀者認知回收 %d／%d" % (i // RECON_BATCH + 1, n), text + "\n\n【任務】" + task, dropped))
    return out


def recon_claude_prompt(book_dir):
    rel, rows = ledger_source(book_dir)
    if not _open_rows(rows):
        raise project.ProjectError("沒有還沒回收的懸念或誤認")
    to = tracking.tracked_to(book_dir) or 0
    return ("請讀取 %s、追蹤/時間線.md、追蹤/章節摘要/ 裡的各章摘要（用 Read；摘要很多時，從每條懸念的種下章往後讀）。"
            "這本書目前寫到第%d章。讀者認知帳本是從時間線轉換的，只記了「當時讀者不知道」，沒記後面哪一章揭曉。"
            "請逐條判斷「回收章」空白的懸念與誤認，到第%d章為止是否已經揭曉。\n%s\n\n%s\n\n"
            "不要修改任何檔案。最後一則回覆只輸出 JSON，不要加說明或程式碼圍欄。" % (rel, to, to, RECON_RULES, RECON_SCHEMA))


def apply_recon(book_dir, results):
    """套用比對結果，存成草稿（保留原編號），回傳匯報文字。"""
    rel, rows = ledger_source(book_dir)
    to = tracking.tracked_to(book_dir) or 99999
    rows = [dict(r) for r in rows]
    by_id = {r.get("編號"): r for r in rows}
    open_ids = {r.get("編號") for r in _open_rows(rows)}
    done, part, merged, skipped, lines = 0, 0, 0, 0, []
    remove = set()
    for data in results:
        for ch in (data or {}).get("changes") or []:
            if not isinstance(ch, dict):
                continue
            rid, act, why = str(ch.get("編號") or "").strip(), str(ch.get("動作") or "").strip(), str(ch.get("理由") or "").strip()
            r = by_id.get(rid)
            if not r or rid not in open_ids or rid in remove:
                skipped += 1
                continue
            if act == "回收":
                no = _first(ch.get("回收章"))
                if no == 99999 or no > to:
                    skipped += 1
                    continue
                r["回收章"] = tracking.chapter_label(no)
                done += 1
                lines.append("- %s 回收（%s）：%s　理由：%s" % (rid, r["回收章"], r.get("內容", ""), why))
            elif act == "部分" and str(ch.get("內容") or "").strip():
                old = r.get("內容", "")
                src = re.findall(r"（([A-Z]\d+(?:[、,][A-Z]?\d+)*)）\s*$", old)
                r["內容"] = str(ch["內容"]).strip() + ("（%s）" % src[0] if src and src[0] not in ch["內容"] else "")
                part += 1
                lines.append("- %s 部分揭曉：「%s」→「%s」　理由：%s" % (rid, old, r["內容"], why))
            elif act == "合併":
                to_id = str(ch.get("合併到") or "").strip()
                if to_id == rid or to_id not in by_id or to_id in remove:
                    skipped += 1
                    continue
                remove.add(rid)
                merged += 1
                lines.append("- %s 併入 %s：%s　理由：%s" % (rid, to_id, r.get("內容", ""), why))
            else:
                skipped += 1
    if not lines:
        return "**比對完成，沒有找到可以回收、部分揭曉或合併的條目**（%s 沒有變動）" % rel
    if rel == tracking.RP_DRAFT:
        tracking.backup(book_dir, os.path.join(book_dir, *rel.split("/")), "讀者認知草稿")
    kept = [r for r in rows if r.get("編號") not in remove]
    path = os.path.join(book_dir, *tracking.RP_DRAFT.split("/"))
    tracking.write_reader_table(path, kept, tracking.chapter_label(to) if to != 99999 else "", draft=True,
                                keep_ids=True, note="\n".join(lines))
    return ("**讀者認知回收比對完成**（比對 %s，結果存成草稿 %s）\n\n回收 %d 條、部分揭曉 %d 條、合併 %d 條%s。\n\n%s\n\n"
            "請到「伏筆與時間線 → 讀者認知」核對，確認後按「採用草稿」。"
            % (rel, tracking.RP_DRAFT, done, part, merged, "；%d 條判斷不合格式或不合理，已略過" % skipped if skipped else "", "\n".join(lines)))
