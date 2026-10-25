# -*- coding: utf-8 -*-
"""
非 Claude 模型的「規劃與設定」類動作。
模型用檔案區塊輸出要建立或修改的檔案，由 Python 檢查路徑後寫入：

    <<<檔案 設定/角色/周叔.md>>>
    （完整內容）
    <<<結束>>>
    <<<刪除 設定/草稿/周叔.md>>>
"""
import os
import re
import shutil
import time

from . import context, project, shared, tracking

FILE_RE = re.compile(r"<<<\s*檔案\s+(.+?)\s*>>>[ \t]*\r?\n(.*?)\r?\n?[ \t]*<<<\s*結束\s*>>>", re.S)
DEL_RE = re.compile(r"<<<\s*刪除\s+(.+?)\s*>>>")
WRITE_PREFIXES = ("設定/", "大綱/", "範例/")
DELETE_PREFIXES = ("設定/草稿/",)

FILE_RULE = """【輸出規則】
需要建立或修改檔案時，用下面的格式輸出「完整檔案內容」（不是只給修改處），一個檔案一個區塊：
<<<檔案 相對路徑>>>
檔案的完整內容（含 YAML frontmatter）
<<<結束>>>
要刪除已轉正的草稿時，單獨一行寫：<<<刪除 設定/草稿/檔名.md>>>
- 只能寫入 CLAUDE.md，以及 設定/、大綱/、範例/ 底下的 .md 檔；路徑用 / 分隔，從書目錄算起。
- 檔名、內容一律台灣繁體中文；照提供的範本格式寫，frontmatter 欄位不要刪。
- 檔案區塊以外的文字是給作者看的白話匯報：做了什麼、哪些放草稿、需要作者決定什麼。
- 需要作者回答時，在匯報最後列出問題與編號選項（標出推薦），然後結束這一輪。"""

CONFIRM_RULE = ("【這一輪只提案】這個任務要先讓作者確認：這一輪只輸出提案與總覽，不要輸出任何檔案區塊。"
                "作者回覆確認（例如「好」「確認」「寫入」）後，下一輪再輸出完整檔案。")


# ---------------------------------------------------------------------------
# 專案骨架（不需要 AI）
# ---------------------------------------------------------------------------
SKELETON_DIRS = ["設定/世界觀", "設定/角色", "設定/勢力", "設定/草稿", "大綱/章綱", "正文", "候選",
                 "追蹤/角色狀態", "追蹤/章節摘要", "範例", "_範本"]
SKELETON_FILES = {  # 目的地: 範本
    "設定/故事核心.md": "故事核心.md", "設定/文風.md": "文風.md", "設定/作者偏好.md": "作者偏好.md",
    "設定/名詞表.md": "名詞表.md", "大綱/全書大綱.md": "全書大綱.md", "追蹤/狀態卡.md": "狀態卡.md",
    "追蹤/伏筆.md": "伏筆.md", "追蹤/時間線.md": "時間線.md",
}


def ensure_skeleton(book_dir, plugin_dir):
    """補齊資料夾、_範本 與空白檔案；不覆蓋既有內容。回傳新建項目清單。"""
    created = []
    tpl_dir = os.path.join(plugin_dir, "skills", "novel-setup", "templates")
    for d in SKELETON_DIRS:
        p = os.path.join(book_dir, d)
        if not os.path.isdir(p):
            os.makedirs(p)
            created.append(d + "/")
        if d not in ("_範本",) and not os.listdir(p):
            open(os.path.join(p, ".gitkeep"), "w").close()
    if os.path.isdir(tpl_dir):
        for f in os.listdir(tpl_dir):
            dst = os.path.join(book_dir, "_範本", f)
            if not os.path.exists(dst):
                shutil.copyfile(os.path.join(tpl_dir, f), dst)
                created.append("_範本/" + f)
        spec = os.path.join(plugin_dir, "skills", "novel-setup", "references", "project-layout.md")
        dst = os.path.join(book_dir, "_範本", "專案規範.md")
        if os.path.isfile(spec) and not os.path.exists(dst):
            shutil.copyfile(spec, dst)
            created.append("_範本/專案規範.md")
        for rel, tpl in SKELETON_FILES.items():
            dst = os.path.join(book_dir, rel)
            if not os.path.exists(dst) and os.path.isfile(os.path.join(tpl_dir, tpl)):
                shutil.copyfile(os.path.join(tpl_dir, tpl), dst)
                created.append(rel)
    return created


def blank_files(book_dir):
    """還是空白範本（沒填內容）的核心檔案。"""
    out = []
    for rel in ("設定/故事核心.md", "設定/文風.md", "大綱/全書大綱.md", "追蹤/狀態卡.md"):
        p = os.path.join(book_dir, rel)
        if os.path.isfile(p):
            b = context.body(project.read_text(p))
            filled = [l for l in b.split("\n") if l.strip() and not l.startswith("#") and not re.match(r"^\s*[-\d.]+\s*[^：:]*[：:]\s*$", l)]
            if len(filled) < 2:
                out.append(rel)
    return out


# ---------------------------------------------------------------------------
# 檔案區塊
# ---------------------------------------------------------------------------
def _norm(path):
    p = path.strip().strip("`'\"「」").replace("\\", "/").lstrip("./").lstrip("/")
    return p


def parse_blocks(text):
    t = text.strip()
    files = [(_norm(m.group(1)), m.group(2)) for m in FILE_RE.finditer(t)]
    dels = [_norm(m.group(1)) for m in DEL_RE.finditer(t)]
    report = DEL_RE.sub("", FILE_RE.sub("", t)).strip()
    report = re.sub(r"\n{3,}", "\n\n", report)
    return files, dels, report


def apply_blocks(book_dir, files, dels):
    done, skipped = [], []
    for rel, content in files:
        ok = (rel == "CLAUDE.md" or rel.startswith(WRITE_PREFIXES)) and rel.endswith(".md")
        try:
            full = project.safe_path(book_dir, rel) if ok else None
        except project.ProjectError:
            ok = False
        if not ok:
            skipped.append("%s（不允許寫入這個位置）" % rel)
            continue
        if os.path.isfile(full):
            tracking.backup(book_dir, full, "修改前")
            verb = "更新"
        else:
            verb = "新增"
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(content.strip() + "\n")
        done.append("%s %s" % (verb, rel))
    for rel in dels:
        try:
            full = project.safe_path(book_dir, rel)
        except project.ProjectError:
            skipped.append("刪除 %s（路徑不合法）" % rel)
            continue
        if not rel.startswith(DELETE_PREFIXES) or not os.path.isfile(full):
            skipped.append("刪除 %s（只能刪除設定/草稿/裡存在的檔案）" % rel)
            continue
        tracking.backup(book_dir, full, "刪除前")
        os.remove(full)
        done.append("刪除 %s（已備份）" % rel)
    return done, skipped


def result_text(report, done, skipped):
    out = report.strip() or "（模型沒有附匯報）"
    if done:
        out += "\n\n**已寫入：**\n" + "\n".join("- " + x for x in done)
    if skipped:
        out += "\n\n**略過：**\n" + "\n".join("- " + x for x in skipped)
    if done:
        out += "\n\n修改前的版本都備份在 .studio/備份/。"
    return out


# ---------------------------------------------------------------------------
# 上下文
# ---------------------------------------------------------------------------
def tpl(c, name):
    p = os.path.join(c.plugin_dir, "skills", "novel-setup", "templates", name)
    return project.read_text(p) if os.path.isfile(p) else ""


def ref(c, rel):
    return context.skill_ref(c.plugin_dir, rel)


def entity_index(book_dir):
    lines = []
    for sub, label in (("設定/角色", "角色"), ("設定/勢力", "勢力"), ("設定/世界觀", "世界觀"), ("設定/草稿", "草稿")):
        for e in project.list_entries(book_dir, sub):
            lines.append("- [%s] %s（%s）%s" % (label, e["name"], e["file"], ("：" + e["summary"]) if e.get("summary") else ""))
    return "\n".join(lines) or "（還沒有任何設定檔）"


def add_book_core(pk, c, light=False):
    rd = lambda r: context.body(context.read(c.book, r))
    pk.add(0, "本書規則（CLAUDE.md）", context.book_rules(c.book))
    pk.add(1, "故事核心", rd("設定/故事核心.md"))
    pk.add(2, "本書文風", rd("設定/文風.md"))
    pk.add(2, "作者偏好", rd("設定/作者偏好.md"))
    pk.add(2, "共用作者偏好（所有書都適用；和本書衝突時以本書為準）", shared.prefs_for_context(c.book))
    sname, stext, _ = shared.structure_for(c.book)
    if sname and not light:
        pk.add(3, "本書預設章節結構：%s（排章綱時用來安排每章的節拍；章綱可在 frontmatter 用「結構: 名稱」改用 設定/章節結構/ 裡的其他結構）" % sname, stext)
    if not light:
        pk.add(3, "狀態卡（已寫章節的目前局勢）", rd("追蹤/狀態卡.md"))
        pk.add(4, "名詞表", rd("設定/名詞表.md"))
    pk.add(4, "已有的設定檔", entity_index(c.book))


def outline_files_text(c):
    return "\n\n".join("〈%s〉\n%s" % (f["file"], context.body(context.read(c.book, f["file"])))
                       for f in project.outline_files(c.book) if f["file"] != "大綱/全書大綱.md")


# ---------------------------------------------------------------------------
# 各動作：回傳 (標題, 任務說明, Pack, 是否先提案)
# ---------------------------------------------------------------------------
def spec_setup_new(c, p):
    created = ensure_skeleton(c.book, c.plugin_dir)
    if created:
        c.job.emit("log", text="已建立專案資料夾與範本（%d 項）" % len(created))
    pk = context.Pack(c.budget(int(c.prov.get("max_output") or 8192)))
    pk.add(0, "開書訪談流程", ref(c, "novel-setup/references/interview.md"))
    pk.add(0, "CLAUDE.md 範本", ref(c, "novel-setup/references/claude-md-template.md"))
    pk.add(1, "故事核心範本（設定/故事核心.md）", tpl(c, "故事核心.md"))
    pk.add(1, "文風範本（設定/文風.md）", tpl(c, "文風.md"))
    idea = (p.get("idea") or "").strip() or "（作者還沒給，請引導）"
    task = ("你正在為新書《%s》做開書訪談。資料夾與空白範本已經建好。\n作者的初步構想：%s\n"
            "照訪談流程一輪一輪問，每輪最多 4 題；作者已經回答的就跳過。現在先問第一輪。\n"
            "第二輪（必問）問完、作者也回答後，才輸出三個檔案：CLAUDE.md（照範本，把 {…} 換成訪談結果，範本開始／結束標記不要輸出）、"
            "設定/故事核心.md、設定/文風.md（照範本，已知的填進去，不知道的保留範本註解，不要自己編）。"
            "作者說「跳過」「你決定」時，提出 2～3 個選項或採用合理預設並標明。" % (c.job.book_id, idea))
    return "開書訪談", task, pk, False


def spec_style(c, p):
    text = p.get("text", "")
    m = None
    if len(shared.CJK.findall(text or "")) >= 300:   # 貼的是樣本：先用程式統計
        try:
            m = shared.analyze(text, shared.book_names(c.book))
        except shared.SharedError:
            m = None
    pk = context.Pack(c.budget(int(c.prov.get("max_output") or 8192)))
    pk.add(0, "目前的 設定/文風.md", context.read(c.book, "設定/文風.md") or tpl(c, "文風.md"))
    pk.add(0, "文風範本（缺的章節照這個補）", tpl(c, "文風.md"))
    pk.add(1, "文風的十三個面向", ref(c, "novel-style/references/style-dimensions.md"))
    pk.add(2, "類型線索表", ref(c, "novel-style/references/genre-cues.md"))
    if m:
        pk.add(0, "樣本的文字指標（程式統計）", shared.metrics_md(m))
    pk.add(2, "本書規則", context.book_rules(c.book))
    task = ("分析、設計或調整本書文風（設定/文風.md，輸出完整檔案，保留作者原本寫的內容）。作者提供的內容：\n%s\n\n"
            "判斷作者給的是什麼：寫作樣本 → 歸納特徵寫成規則，範例段落優先節錄樣本，附「我喜歡它哪裡」；"
            "類型或感覺的描述 → 依十三個面向與類型線索設計；修改意見 → 只改相關條目。\n"
            "原則：規則具體到能拿來檢查一段文字；給範圍不給死數字；只寫深與眾不同的五到八項；禁忌附替代做法；"
            "分清 建議做法／本書禁忌／允許的例外；參考作品只學特徵，不抄原文與專有名詞；範例段落至少三段有場景標籤；整份 1500～3000 字。"
            "不要自己寫「## 文字指標（程式統計）」一節（程式會補上）。不要提問，不確定的地方在匯報列出。匯報列出改了什麼。" % text)
    if m:
        c.after_files = lambda done: _style_metrics_after(c, m, done)
    return "分析文風", task, pk, False


def _style_metrics_after(c, m, done):
    if not any(x.endswith("設定/文風.md") for x in done):
        return
    fp = os.path.join(c.book, "設定", "文風.md")
    t = shared.put_metrics(project.read_text(fp), m)
    with open(fp, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)


def spec_preference(c, p):
    pk = context.Pack(c.budget(4000))
    pk.add(0, "目前的 設定/作者偏好.md", context.read(c.book, "設定/作者偏好.md") or tpl(c, "作者偏好.md"))
    task = ("把作者的長期偏好記進 設定/作者偏好.md（輸出完整檔案，表格新增一列，編號接續，記錄日期 %s）：\n%s\n"
            "規則：一條偏好一行，保留原話的限定與例外；一次性要求、劇情事實不要記；和舊偏好衝突時不要寫檔，先在匯報問作者要取代哪一條；"
            "作者說「忘掉」時整行刪除。" % (time.strftime("%Y-%m-%d"), p.get("text", "")))
    return "記錄偏好", task, pk, False


def spec_concept(c, p):
    pk = context.Pack(c.budget(int(c.prov.get("max_output") or 8192)))
    pk.add(0, "故事核心診斷方法", ref(c, "novel-outline/references/concept.md"))
    pk.add(1, "目前的 設定/故事核心.md", context.read(c.book, "設定/故事核心.md") or tpl(c, "故事核心.md"))
    add_book_core(pk, c, light=True)
    note = (p.get("note") or "").strip()
    task = ("做故事核心診斷，用方法第六節的格式在匯報裡給作者看（最小骨架、賣點、故事引擎、建議篇幅、缺口與建議）。%s\n"
            "同時更新 設定/故事核心.md（輸出完整檔案）：只寫作者已經說過或已確認的內容；你的提案寫在匯報裡，不要寫進檔案。"
            % (("作者補充：" + note) if note else ""))
    return "故事核心診斷", task, pk, False


def spec_master_outline(c, p):
    pk = context.Pack(c.budget(int(c.prov.get("max_output") or 8192)))
    pk.add(0, "長篇結構與節奏", ref(c, "novel-outline/references/structure.md"))
    pk.add(1, "全書大綱範本", tpl(c, "全書大綱.md"))
    pk.add(0, "目前的 大綱/全書大綱.md", context.body(context.read(c.book, "大綱/全書大綱.md")))
    add_book_core(pk, c)
    note = (p.get("note") or "").strip()
    task = ("規劃全書大綱。先給作者看分卷總覽（每卷：篇幅、目標、對手、卷末變化、大高潮），作者確認後再輸出 大綱/全書大綱.md 完整檔案。"
            "需要的角色或設定不存在時，列出來問作者，不要自己定案。%s" % (("\n作者補充：" + note) if note else ""))
    return "全書大綱", task, pk, True


def spec_volume_outline(c, p):
    v = (p.get("volume") or "一").strip()
    pk = context.Pack(c.budget(int(c.prov.get("max_output") or 8192)))
    pk.add(0, "長篇結構與節奏", ref(c, "novel-outline/references/structure.md"))
    pk.add(0, "全書大綱", context.body(context.read(c.book, "大綱/全書大綱.md")))
    pk.add(1, "卷綱範本", tpl(c, "卷綱.md"))
    pk.add(1, "目前的 大綱/卷綱_第%s卷.md" % v, context.body(context.read(c.book, "大綱/卷綱_第%s卷.md" % v)))
    pk.add(2, "其他卷綱", outline_files_text(c))
    pk.add(2, "伏筆總表", context.body(context.read(c.book, "追蹤/伏筆.md")))
    add_book_core(pk, c)
    note = (p.get("note") or "").strip()
    task = ("規劃第%s卷的卷綱。先給作者看卷契約和劇情單元總覽（一個單元一段），作者確認後再輸出 大綱/卷綱_第%s卷.md 完整檔案。"
            "已經寫成正文的部分要接得上狀態卡與伏筆。%s" % (v, v, ("\n作者補充：" + note) if note else ""))
    return "第%s卷卷綱" % v, task, pk, True


def spec_chapter_cards(c, p):
    a = int(p.get("from") or 1)
    b = int(p.get("to") or a)
    a, b = min(a, b), max(a, b)
    pk = context.Pack(c.budget(int(c.prov.get("max_output") or 8192)))
    pk.add(0, "章綱寫法", ref(c, "novel-outline/references/chapter-card.md"))
    if a <= 3:
        pk.add(1, "開篇與黃金三章", ref(c, "novel-outline/references/opening.md"))
    pk.add(0, "章綱範本（大綱/章綱/第NNN章.md）", tpl(c, "章綱.md"))
    pk.add(0, "卷綱", outline_files_text(c))
    pk.add(2, "全書大綱", context.body(context.read(c.book, "大綱/全書大綱.md")))
    for n in range(a, b + 1):
        _, card = context.card_text(c.book, n)
        if card:
            pk.add(1, "既有的第%d章章綱" % n, context.body(card))
    _, prev = context.card_text(c.book, a - 1)
    pk.add(1, "前一章（第%d章）章綱" % (a - 1), context.body(prev))
    pk.add(2, "伏筆總表", context.body(context.read(c.book, "追蹤/伏筆.md")))
    add_book_core(pk, c)
    note = (p.get("note") or "").strip()
    task = ("排第%d～%d章的章綱。先給作者看單元總覽表（一章一行：章號、章名、一句話、功能、鉤子類型），作者確認後，"
            "再為每一章各輸出一個 大綱/章綱/第NNN章.md（章號補零到三位數，照範本，四問、情節點、伏筆操作、禁止事項、章末鉤子都要填；"
            "frontmatter 的狀態填「已確認」）。回收重要伏筆、新的大反轉或新角色要先問作者。%s" % (a, b, ("\n作者補充：" + note) if note else ""))
    return "排章綱 %d～%d" % (a, b), task, pk, True


def spec_character(c, p):
    name = (p.get("name") or "").strip()
    pk = context.Pack(c.budget(int(c.prov.get("max_output") or 8192)))
    pk.add(0, "角色設計方法", ref(c, "novel-bible/references/character-design.md"))
    pk.add(0, "入庫規則", ref(c, "novel-bible/references/intake-rules.md"))
    pk.add(1, "角色範本", tpl(c, "角色.md"))
    for rel in ("設定/角色/%s.md" % name, "設定/草稿/%s.md" % name):
        pk.add(0, "目前的 %s" % rel, context.read(c.book, rel))
    add_book_core(pk, c)
    note = (p.get("note") or "").strip()
    task = ("建立或補完角色「%s」。作者提供的資訊：%s\n"
            "作者給的、已確認的資訊寫進 設定/角色/%s.md（狀態：正式）；你自己補的部分放 設定/草稿/%s.md（狀態：草稿），等作者確認。"
            "已有檔案時保留原本內容，只補空欄。新名詞也更新 設定/名詞表.md（輸出完整檔案）。" % (name, note or "（無）", name, name))
    return "角色：%s" % name, task, pk, False


def spec_gen_drafts(c, p):
    pk = context.Pack(c.budget(int(c.prov.get("max_output") or 8192)))
    pk.add(0, "入庫規則", ref(c, "novel-bible/references/intake-rules.md"))
    pk.add(1, "角色設計方法", ref(c, "novel-bible/references/character-design.md"))
    pk.add(2, "世界觀設計方法", ref(c, "novel-bible/references/worldbuilding.md"))
    pk.add(1, "角色範本", tpl(c, "角色.md"))
    pk.add(2, "勢力範本", tpl(c, "勢力.md"))
    pk.add(2, "世界觀範本", tpl(c, "世界觀.md"))
    add_book_core(pk, c)
    task = ("生成設定草稿：%s\n全部寫在 設定/草稿/ 底下（一個項目一個檔，狀態：草稿），名字不要和既有設定撞名撞音，"
            "彼此拉開差異。批量生成配角時只寫一句話功能、想要、缺陷、聲音卡兩三條、和主角的關係。" % p.get("text", ""))
    return "生成設定草稿", task, pk, False


def spec_intake(c, p):
    pk = context.Pack(c.budget(int(c.prov.get("max_output") or 8192)))
    pk.add(0, "入庫規則", ref(c, "novel-bible/references/intake-rules.md"))
    pk.add(1, "角色範本", tpl(c, "角色.md"))
    pk.add(2, "勢力範本", tpl(c, "勢力.md"))
    pk.add(2, "世界觀範本", tpl(c, "世界觀.md"))
    add_book_core(pk, c)
    pk.add(0, "要整理的內容", p.get("text", ""))
    task = ("照入庫規則「從對話萃取」整理「要整理的內容」：已定案的寫進正式設定（設定/角色、設定/勢力、設定/世界觀），討論中的寫進 設定/草稿/，已否決的不寫。"
            "已有檔案時保留原本內容再補充；新名詞更新 設定/名詞表.md。匯報用表格列出：哪些進正式、哪些進草稿、哪些沒收。")
    return "整理入庫", task, pk, False


def spec_promote(c, p):
    pk = context.Pack(c.budget(int(c.prov.get("max_output") or 8192)))
    pk.add(0, "入庫規則", ref(c, "novel-bible/references/intake-rules.md"))
    for e in project.list_entries(c.book, "設定/草稿"):
        pk.add(0, "草稿：%s（%s）" % (e["name"], e["file"]), context.read(c.book, e["file"]))
    pk.add(1, "角色範本", tpl(c, "角色.md"))
    pk.add(2, "勢力範本", tpl(c, "勢力.md"))
    pk.add(2, "世界觀範本", tpl(c, "世界觀.md"))
    pk.add(1, "目前的名詞表（設定/名詞表.md）", context.read(c.book, "設定/名詞表.md"))
    add_book_core(pk, c)
    task = ("把這些草稿轉為正式：%s\n照入庫規則「草稿轉正式」：套用範本整理格式、狀態改為正式、寫到對應的正式資料夾，然後刪除原草稿檔；"
            "新名詞補進名詞表（輸出完整檔案）。和既有正式設定衝突時不要寫檔，先問作者。" % (p.get("text") or "（作者沒指定，先列出草稿請作者選）"))
    return "草稿轉正式", task, pk, False


SPECS = {"setup_new": spec_setup_new, "style": spec_style, "preference": spec_preference, "concept": spec_concept,
         "master_outline": spec_master_outline, "volume_outline": spec_volume_outline,
         "chapter_cards": spec_chapter_cards, "character": spec_character, "gen_drafts": spec_gen_drafts,
         "intake": spec_intake, "promote_drafts": spec_promote}


def run_spec(c, p, spec, system):
    label, task, pk, confirm = spec(c, p)
    ctx_text, used, dropped = pk.build()
    if dropped:
        c.job.emit("log", text="上下文超出長度，略過：%s" % "、".join(dropped))
    user = ctx_text + "\n\n【任務】" + task + "\n\n" + FILE_RULE + ("\n\n" + CONFIRM_RULE if confirm else "")
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    out = c.call(msgs, max_tokens=int(c.prov.get("max_output") or 8192), label=label, stage="plan")
    files, dels, report = parse_blocks(out)
    if c.truncated:
        report += "\n\n⚠ 這次輸出被截斷，最後一個檔案可能沒寫完（沒寫完的檔案不會寫入）。請調高「最大輸出」後再執行一次。"
    done, skipped = apply_blocks(c.book, files, dels) if (files or dels) else ([], [])
    hook = getattr(c, "after_files", None)
    if hook:
        c.after_files = None
        hook(done)
    msgs.append({"role": "assistant", "content": out})
    c.save_messages(msgs, {"kind": "files", "stage": "plan"})
    c.job.result = result_text(report, done, skipped)
    if confirm and not (files or dels):
        c.job.result += "\n\n確認沒問題的話，在下方回覆「確認」（或寫下要調整的地方），就會寫入檔案。"


def reply_files(c, out):
    files, dels, report = parse_blocks(out)
    done, skipped = apply_blocks(c.book, files, dels) if (files or dels) else ([], [])
    return result_text(report, done, skipped)


# ---------------------------------------------------------------------------
def act_setup_check(c, p):
    created = ensure_skeleton(c.book, c.plugin_dir)
    blanks = blank_files(c.book)
    lines = []
    lines.append("補上了 %d 個缺少的資料夾或範本：%s" % (len(created), "、".join(created)) if created else "資料夾與範本都齊全。")
    if not os.path.isfile(os.path.join(c.book, "CLAUDE.md")):
        lines.append("還沒有 CLAUDE.md（本書規則），建議先做「開書訪談」。")
    if blanks:
        lines.append("這些檔案還是空白範本：%s。" % "、".join(blanks))
    ents = {k: len(project.list_entries(c.book, "設定/" + k)) for k in ("角色", "勢力", "世界觀", "草稿")}
    lines.append("目前設定：角色 %d、勢力 %d、世界觀 %d、草稿 %d。" % (ents["角色"], ents["勢力"], ents["世界觀"], ents["草稿"]))
    chs = project.scan_chapters(c.book)
    lines.append("章綱 %d 章、已寫正文 %d 章。" % (sum(1 for x in chs if x["card_file"]), sum(1 for x in chs if x["text_file"])))
    if not os.path.isdir(os.path.join(c.book, ".git")):
        lines.append("這本書還沒有 git 版本控制；需要的話在書目錄執行 `git init`，之後每採用一章會自動提交。")
    c.job.result = "\n\n".join(lines)


def act_review_all(c, p, system):
    pk = context.Pack(c.budget(int(c.prov.get("max_output") or 8192)))
    pk.add(0, "審查清單", ref(c, "novel-review/references/checklist.md"))
    ov = project.overview(c.book)
    pk.add(0, "工作台偵測到的警示", "\n".join("- %s：%s" % (a["kind"], a["text"]) for a in ov["alerts"]) or "（無）")
    pk.add(1, "伏筆總表", context.body(context.read(c.book, "追蹤/伏筆.md")))
    pk.add(1, "時間線", context.body(context.read(c.book, "追蹤/時間線.md")))
    pk.add(1, "狀態卡", context.body(context.read(c.book, "追蹤/狀態卡.md")))
    sums = project._scan_dir(os.path.join(c.book, "追蹤", "章節摘要"))
    pk.add(2, "全部章節摘要", "\n\n".join(context.body(context.read(c.book, "追蹤/章節摘要/" + sums[k])) for k in sorted(sums)), keep="tail")
    roles = []
    for e in project.list_entries(c.book, "追蹤/角色狀態"):
        fm, _ = project.split_frontmatter(context.read(c.book, e["file"]))
        roles.append("- %s：最後登場 %s" % (e["name"], fm.get("最後登場") or "—"))
    pk.add(2, "角色最後登場", "\n".join(roles))
    add_book_core(pk, c)
    fmt = ref(c, "novel-review/references/fix-routing.md")
    m = re.search(r"## 四、報告格式(.*)", fmt, re.S)
    user = (pk.build()[0] + "\n\n【任務】做全書健康檢查（目前寫到第%d章），重點是清單 B：設定一致性、追蹤是否跟上正文、伏筆健康度、角色久未登場、資訊揭露邊界、讀者契約與節奏。"
            "每個問題要有依據與建議；沒有問題就說通過。用以下格式輸出 Markdown 報告：\n%s" % (ov["latest"], m.group(1) if m else ""))
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    out = c.call(msgs, max_tokens=int(c.prov.get("max_output") or 8192), label="全書健康檢查", stage="review")
    d = os.path.join(c.book, ".studio", "審查報告")
    os.makedirs(d, exist_ok=True)
    fn = "全書健康檢查_%s.md" % time.strftime("%Y%m%d-%H%M")
    with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
        f.write(out)
    c.save_messages(msgs + [{"role": "assistant", "content": out}], {"kind": "chat"})
    c.job.result = out + "\n\n（報告已存到 .studio/審查報告/%s）" % fn
