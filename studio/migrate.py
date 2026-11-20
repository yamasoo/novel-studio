# -*- coding: utf-8 -*-
"""書的格式移轉（v3 規格第 10 節）。工作台與 tools/migrate_v3.py 共用。

流程：偵測 → 備份（整本壓成 zip）→ 逐步轉換 → 轉換前後的統計比對 → 對不上就自動還原 → 寫報告。
- 每一步都能自己判斷「這本書還需不需要」（needed），所以可以重複執行；已經轉好的書直接跳過。
- P3 分批做：每一批加一步，最後一步把 book.json 的 schema_version 改成 3。
- 統計只比對「內容有沒有掉」：章數、正文總字數、章綱數、設定條目數、各追蹤表列數。
"""
import datetime
import os
import re
import shutil
import zipfile

from . import bookmeta, context, layout, project

SKIP_DIRS = (".git",)                       # 不備份、不還原（作者自己的版本控制）


# ---------------------------------------------------------------------------
# v2 → v3 的路徑對照（規格 3.1～3.5）。左邊是 layout 常數名稱；v2 欄是凍結的舊值（layout 換成 v3 之後也還認得舊書）。
# ---------------------------------------------------------------------------
PATHS = {
    #  常數名稱                    v2                          v3
    "BIBLE":                     ("設定",                     "bible"),
    "OUTLINE":                   ("大綱",                     "outline"),
    "MANUSCRIPT":                ("正文",                     "manuscript"),
    "CANDIDATES":                ("候選",                     "candidates"),
    "TRACKING":                  ("追蹤",                     "tracking"),
    "SAMPLES":                   ("範例",                     "samples"),
    "TEMPLATES":                 ("_範本",                    "_templates"),
    "ILLUST":                    ("插圖",                     "illust"),
    "EXPORT":                    ("匯出",                     "export"),
    "CHARACTERS":                ("設定/角色",                "bible/characters"),
    "FACTIONS":                  ("設定/勢力",                "bible/factions"),
    "WORLD":                     ("設定/世界觀",              "bible/world"),
    "BIBLE_DRAFTS":              ("設定/草稿",                "bible/drafts"),
    "BIBLE_MERGED":              ("設定/_已合併",             "bible/_merged"),
    "BIBLE_STRUCTURE":           ("設定/章節結構",            "bible/structure"),
    "STORY_CORE":                ("設定/故事核心.md",         "bible/story-core.md"),
    "STYLE":                     ("設定/文風.md",             "bible/style.md"),
    "GLOSSARY":                  ("設定/名詞表.md",           "bible/glossary.md"),
    "AUTHOR_PREFS":              ("設定/作者偏好.md",         "bible/author-prefs.md"),
    "BIBLE_INDEX":               ("設定/_索引.md",            "bible/_index.md"),
    "STYLE_FINGERPRINT":         ("設定/風格指紋.json",       "bible/style-fingerprint.json"),
    "STRUCTURE_DNA":             ("設定/結構DNA.json",        "bible/structure-dna.json"),
    "CONTRACT":                  ("設定/續寫合約.md",         "bible/continuation-contract.md"),
    "BOOK_STRUCTURE":            ("設定/章節結構/結構.md",    "bible/structure/structure.md"),
    "CHAPTER_CARDS":             ("大綱/章綱",                "outline/chapters"),
    "REVERSE_CARDS":             ("大綱/章綱/反推",           "outline/chapters/_reverse"),
    "VOLUME_DRAFTS":             ("大綱/草稿",                "outline/drafts"),
    "VOLUMES_SUBDIR":            ("大綱/卷綱",                "outline/volumes"),
    "BOOK_OUTLINE":              ("大綱/全書大綱.md",         "outline/book.md"),
    "SUMMARIES":                 ("追蹤/章節摘要",            "tracking/summaries"),
    "CHARACTER_STATES":          ("追蹤/角色狀態",            "tracking/characters"),
    "FORESHADOWING":             ("追蹤/伏筆.md",             "tracking/foreshadowing.md"),
    "TIMELINE":                  ("追蹤/時間線.md",           "tracking/timeline.md"),
    "STATE_CARD":                ("追蹤/狀態卡.md",           "tracking/state-card.md"),
    "READER_KNOWLEDGE":          ("追蹤/讀者認知.md",         "tracking/reader-knowledge.md"),
    "RELATIONS":                 ("追蹤/關係.md",             "tracking/relations.md"),
    "READER_KNOWLEDGE_DRAFT":    ("追蹤/讀者認知_草稿.md",    "tracking/reader-knowledge.draft.md"),
    "RELATIONS_DRAFT":           ("追蹤/關係_草稿.md",        "tracking/relations.draft.md"),
    "SPINOFF_DRAFTS":            ("候選/新書草稿",            "candidates/spinoff"),
    "STUDIO_BACKUP":             (".studio/備份",             ".studio/backup"),
    "STUDIO_REVISIONS":          (".studio/修訂",             ".studio/revisions"),
    "STUDIO_PIPELINE":           (".studio/流程",             ".studio/pipeline"),
    "STUDIO_PIPELINE_CURRENT":   (".studio/流程/目前.json",   ".studio/pipeline/current.json"),
    "STUDIO_PIPELINE_SNAPSHOTS": (".studio/流程/快照",        ".studio/pipeline/snapshots"),
    "STUDIO_REVIEWS":            (".studio/審查報告",         ".studio/reviews"),
    "STUDIO_REVIEW":             (".studio/審查",             ".studio/review"),
    "STUDIO_CHECK":              (".studio/核對",             ".studio/goal-check"),
    "STUDIO_TRASH":              (".studio/刪除",             ".studio/trash"),
    "STUDIO_RECALL_INDEX":       (".studio/索引/recall.json", ".studio/index/recall.json"),
    "STUDIO_REVERSE":            (".studio/反推",             ".studio/reverse"),
    "STUDIO_FIDELITY":           (".studio/保真",             ".studio/fidelity"),
    "STUDIO_WRITEBACK_CHECK":    (".studio/回寫檢查",         ".studio/writeback-check"),
    "STUDIO_RECOVERY":           (".studio/恢復稿",           ".studio/recovery"),
    "STUDIO_EXPORT_PREFS":       (".studio/匯出設定.json",    ".studio/export-settings.json"),
}
# 檔名常數（放在某個資料夾底下，常數本身不含資料夾）
NAMES = {
    "PIPELINE_CURRENT_FILE":     ("目前.json",   "current.json"),
    "REVERSE_CUMULATIVE":        ("累積.json",   "cumulative.json"),
    "REVERSE_DRAFTS":            ("草稿",        "drafts"),
    "REVERSE_BATCHES":           ("批次",        "batches"),
    "ILLUST_INDEX":              ("_插圖.json",  "_illustrations.json"),    # 插圖資料夾裡每一層都可能有
    "ILLUST_COVER":              ("封面",        "cover"),
    "ILLUST_CHAPTERS":           ("章節",        "chapters"),
    "ART_STYLE":                 ("畫風.json",   "art-style.json"),
    "SPINOFF_SKELETON_JSON":     ("骨架.json",   "skeleton.json"),
    "SPINOFF_SKELETON_MD":       ("骨架.md",     "skeleton.md"),
}
# 書庫層級的共用資料夾
SHARED_PATHS = {
    "SHARED":                    ("_共用",            "_shared"),
    "SHARED_STYLES":             ("_共用/文風",       "_shared/styles"),
    "SHARED_STRUCTURES":         ("_共用/結構",       "_shared/structures"),
    "SHARED_PREFS":              ("_共用/作者偏好.md", "_shared/author-prefs.md"),
    "SHARED_TRASH":              ("_共用/.刪除",      "_shared/.trash"),
    "SHARED_BACKUP":             ("_共用/.備份",      "_shared/.backup"),
}


def _pairs():
    """（v2 相對路徑, v3 相對路徑），長的在前（最長前綴優先）。"""
    P = {k: v for k, v in PATHS.items()}
    out = list(P.values())
    out += [(P["STUDIO_REVERSE"][0] + "/" + NAMES[n][0], P["STUDIO_REVERSE"][1] + "/" + NAMES[n][1])
            for n in ("REVERSE_CUMULATIVE", "REVERSE_DRAFTS", "REVERSE_BATCHES")]
    out += [(P["ILLUST"][0] + "/" + NAMES[n][0], P["ILLUST"][1] + "/" + NAMES[n][1]) for n in ("ILLUST_INDEX", "ART_STYLE")]
    out += [(P["SPINOFF_DRAFTS"][0] + "/" + NAMES[n][0], P["SPINOFF_DRAFTS"][1] + "/" + NAMES[n][1])
            for n in ("SPINOFF_SKELETON_JSON", "SPINOFF_SKELETON_MD")]
    out.append((P["STUDIO_BACKUP"][0] + "/" + P["ILLUST"][0], P["STUDIO_BACKUP"][1] + "/" + P["ILLUST"][1]))   # 插圖的備份
    return sorted(set(out), key=lambda p: -len(p[0]))


PAIRS = _pairs()
TOP_V2 = tuple(PATHS[k][0] for k in ("BIBLE", "OUTLINE", "MANUSCRIPT", "CANDIDATES", "TRACKING", "SAMPLES", "TEMPLATES", "ILLUST", "EXPORT"))
_EXT = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_REV_DRAFTS = (PATHS["STUDIO_REVERSE"][1] + "/" + NAMES["REVERSE_DRAFTS"][1] + "/")


# 插圖資料夾裡的第一層：封面、章節、各類設定（跟設定資料夾同名）
_ILLUST_INNER = dict([NAMES["ILLUST_COVER"], NAMES["ILLUST_CHAPTERS"]] +
                     [(PATHS[k][0].split("/")[-1], PATHS[k][1].split("/")[-1]) for k in ("CHARACTERS", "FACTIONS", "WORLD")])
_ILLUST_ROOTS = (PATHS["ILLUST"][1] + "/", PATHS["STUDIO_BACKUP"][1] + "/" + PATHS["ILLUST"][1] + "/")


def _map_illust(rel):
    for root in _ILLUST_ROOTS:
        if rel.startswith(root):
            parts = rel[len(root):].split("/")
            parts[0] = _ILLUST_INNER.get(parts[0], parts[0])
            parts = [NAMES["ILLUST_INDEX"][1] if p == NAMES["ILLUST_INDEX"][0] else p for p in parts]
            return root + "/".join(parts)
    return rel


def map_rel(rel):
    """v2 的相對路徑 → v3。認不得的原樣。反推草稿資料夾裡放的是整本書的結構，裡面那一段也換；
    插圖資料夾裡的分類資料夾與索引檔也換。"""
    for old, new in PAIRS:
        if rel == old or rel.startswith(old + "/"):
            rel = new + rel[len(old):]
            break
    rel = _map_illust(rel)
    if rel.startswith(_REV_DRAFTS):
        inner = rel[len(_REV_DRAFTS):]
        rel = _REV_DRAFTS + map_rel(inner) if not inner.startswith(".studio") else rel
    return rel


def map_ref(s):
    """文字或 JSON 裡出現的路徑：完整的已知路徑、已知資料夾底下的東西、或「第一層資料夾/…有副檔名的檔案」與「第一層資料夾/」才換。"""
    if not isinstance(s, str) or "/" not in s and s not in dict(PAIRS):
        return s
    if s.startswith("entity:"):          # 插圖的對象（entity:設定/角色/X.md）
        return "entity:" + map_ref(s[len("entity:"):])
    for old, _ in PAIRS:
        if (s == old or s.startswith(old + "/")) and old not in TOP_V2:
            return map_rel(s)
    for top in TOP_V2:
        if s.startswith(top + "/") and (s.endswith("/") or _EXT.search(s)):
            return map_rel(s.rstrip("/")) + ("/" if s.endswith("/") else "")
    return s


def v2_view():
    return {k: v[0] for k, v in PATHS.items()}


def v3_view():
    return {k: v[1] for k, v in PATHS.items()}


# ---------------------------------------------------------------------------
# 統計
# ---------------------------------------------------------------------------
def view_of(book_dir):
    """這本書目前用哪一版的資料夾名稱：有任何 v3 第一層資料夾就是 v3。"""
    v3 = v3_view()
    return v3 if any(os.path.isdir(os.path.join(book_dir, v3[k])) for k in ("BIBLE", "MANUSCRIPT", "OUTLINE", "TRACKING")) else v2_view()


def stats(book_dir, view=None):
    """內容統計（轉換前後要一樣）。view：用哪一版的路徑（預設依書目前的資料夾判斷）。"""
    L = view or view_of(book_dir)

    def p(key, *more):
        return os.path.join(book_dir, *L[key].split("/"), *more)

    def n_entries(key):
        return len(project.list_entries(book_dir, L[key]))

    def n_rows(key):
        try:
            return len(project.read_table(book_dir, L[key])["rows"])
        except project.ProjectError:
            return 0
    chs = project._scan_dir(p("MANUSCRIPT"))
    total = 0
    for f in chs.values():
        total += project.count_chars(context.body(project.read_text(p("MANUSCRIPT", f))))
    return {
        "章數": len(chs),
        "正文總字數": total,
        "章綱": len(project._scan_dir(p("CHAPTER_CARDS"))),
        "章節摘要": len(project._scan_dir(p("SUMMARIES"))),
        "角色": n_entries("CHARACTERS"),
        "勢力": n_entries("FACTIONS"),
        "世界觀": n_entries("WORLD"),
        "伏筆": n_rows("FORESHADOWING"),
        "時間線": n_rows("TIMELINE"),
        "讀者認知": n_rows("READER_KNOWLEDGE"),
        "角色關係": n_rows("RELATIONS"),
        "名詞表": n_rows("GLOSSARY"),
    }


# ---------------------------------------------------------------------------
# 各步驟：needed(book_dir) → bool；apply(book_dir) → [說明]（只在不是 dry-run 時呼叫）；plan(book_dir) → [說明]
# ---------------------------------------------------------------------------
class Step:
    def __init__(self, key, title, needed, plan, apply):
        self.key, self.title, self.needed, self.plan, self.apply = key, title, needed, plan, apply


def _old_lang(book_dir):
    """依舊規則取得語言。故事核心要用書目前的路徑去讀（這一步在改名之前，書還是 v2 的資料夾）。"""
    from . import lang
    return lang.normalize(bookmeta.read(book_dir).get("lang") or lang._fm_lang(book_dir, view_of(book_dir)["STORY_CORE"])
                          or lang._file_lang(book_dir))


def _meta_needed(book_dir):
    m = bookmeta.read(book_dir)
    return not m.get("lang") or "schema_version" not in m or os.path.isfile(layout.path(book_dir, layout.STUDIO, "lang"))


def _meta_plan(book_dir):
    out = []
    if not bookmeta.exists(book_dir):
        out.append("建立 %s（語言 %s）" % (layout.BOOK_META, _old_lang(book_dir)))
    elif not bookmeta.read(book_dir).get("lang"):
        out.append("%s 補上語言 %s" % (layout.BOOK_META, _old_lang(book_dir)))
    if os.path.isfile(layout.path(book_dir, layout.STUDIO, "lang")):
        out.append("移除 %s/lang（語言改記在 %s）" % (layout.STUDIO, layout.BOOK_META))
    return out or ["%s 補上格式版本" % layout.BOOK_META]


def _meta_apply(book_dir):
    out = _meta_plan(book_dir)
    bookmeta.write(book_dir, lang=_old_lang(book_dir))
    old = layout.path(book_dir, layout.STUDIO, "lang")
    if os.path.isfile(old):
        os.remove(old)
    return out


# --- 第二步：資料夾與系統檔名換成英文 -------------------------------------------------
_TOKEN = re.compile(r"[^\s|，、。；：（）()「」『』\[\]<>\"'`*,]+")
_MD_WITH_PATHS = ("GLOSSARY", "BIBLE_INDEX")       # 內容裡有路徑（名詞表的「詳見」、設定索引）的系統檔，加上書裡的 CLAUDE.md


def rename_enabled():
    """工作台本身換成 v3 的資料夾名稱之後才啟用（否則轉好的書工作台反而開不了）。"""
    return layout.BIBLE == PATHS["BIBLE"][1]


def _book_files(book_dir):
    for full, rel in _walk_files(book_dir):
        yield full, rel


def _moves(book_dir):
    return [(rel, map_rel(rel)) for _, rel in _book_files(book_dir) if map_rel(rel) != rel]


def _empty_dirs(book_dir):
    """還在舊名稱底下、裡面沒有檔案的資料夾（例如還沒寫的「正文/」），也要換成新名稱。"""
    out = []
    for base, dirs, files in os.walk(book_dir):
        rel = os.path.relpath(base, book_dir).replace(os.sep, "/")
        if rel == "." or rel.split("/")[0] in SKIP_DIRS or (rel + "/").startswith(layout.MIGRATE_DIR + "/"):
            continue
        if not files and not dirs and map_rel(rel) != rel:
            out.append(rel)
    return out


_V2_DIRS = tuple(TOP_V2) + tuple(v[0] for k, v in PATHS.items() if k.startswith("STUDIO_") and not v[0].endswith(".json"))


def needs_migration(book_dir):
    """工作台開不了、要先轉換的舊書：還有 v2 的資料夾。只看資料夾在不在（書架每次都會問，不能逐檔掃描）。"""
    return rename_enabled() and any(os.path.isdir(os.path.join(book_dir, *d.split("/"))) for d in _V2_DIRS)


def library_needs_migration(library):
    return rename_enabled() and bool(library) and os.path.isdir(os.path.join(library, SHARED_PATHS["SHARED"][0]))


def _rename_needed(book_dir):
    return rename_enabled() and bool(_moves(book_dir) or _empty_dirs(book_dir))


def _rename_plan(book_dir):
    moves = _moves(book_dir)
    by_top = {}
    for old, new in moves:
        k = (old.split("/")[0] if not old.startswith(".studio/") else "/".join(old.split("/")[:2]),
             new.split("/")[0] if not new.startswith(".studio/") else "/".join(new.split("/")[:2]))
        by_top[k] = by_top.get(k, 0) + 1
    out = ["%s/ → %s/（%d 個檔）" % (a, b, n) for (a, b), n in sorted(by_top.items())]
    out += ["%s/ → %s/（空資料夾）" % (d, map_rel(d)) for d in _empty_dirs(book_dir)]
    return out or ["沒有要搬的檔案"]


def _rewrite_json(v):
    if isinstance(v, dict):
        return {map_ref(k): _rewrite_json(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_rewrite_json(x) for x in v]
    return map_ref(v)


def _rewrite_text(text):
    return _TOKEN.sub(lambda m: map_ref(m.group(0)), text)


def _rename_apply(book_dir):
    import json
    out = _rename_plan(book_dir)
    moves = _moves(book_dir)
    targets = {}
    existing = {rel for _, rel in _book_files(book_dir)}
    for old, new in moves:
        if new in targets:
            raise project.ProjectError("兩個檔案會搬到同一個位置：%s、%s → %s" % (targets[new], old, new))
        if new in existing and new not in dict(moves):
            raise project.ProjectError("新位置已經有檔案：%s（舊的 %s 沒有搬）" % (new, old))
        targets[new] = old
    for old, new in moves:
        os.renames(os.path.join(book_dir, *old.split("/")), os.path.join(book_dir, *new.split("/")))
    for d in sorted(_empty_dirs(book_dir), key=len, reverse=True):
        os.makedirs(os.path.join(book_dir, *map_rel(d).split("/")), exist_ok=True)
        os.removedirs(os.path.join(book_dir, *d.split("/")))
    # 檔案內容裡的路徑：.json 的字串值與鍵、幾個系統 Markdown
    v3 = v3_view()
    md = {"CLAUDE.md"} | {v3[k] for k in _MD_WITH_PATHS} | {_REV_DRAFTS + v3[k] for k in _MD_WITH_PATHS}
    fixed = 0
    for full, rel in _book_files(book_dir):
        if rel.endswith(".json"):
            try:
                with open(full, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            new = _rewrite_json(data)
            if new != data:
                project.write_atomic(full, json.dumps(new, ensure_ascii=False, indent=1) + "\n")
                fixed += 1
        elif rel in md:
            text = project.read_text(full)
            new = _rewrite_text(text)
            if new != text:
                project.write_atomic(full, new)
                fixed += 1
    if fixed:
        out.append("改寫檔案裡的路徑：%d 個檔" % fixed)
    return out


# --- 書庫層級：_共用 ------------------------------------------------------------------
def map_shared(rel):
    for old, new in sorted(SHARED_PATHS.values(), key=lambda p: -len(p[0])):
        if rel == old or rel.startswith(old + "/"):
            return new + rel[len(old):]
    return rel


def migrate_library(library, dry_run=False):
    """書庫的共用資料夾（_共用 → _shared）。回傳說明清單；不需要就回傳 []。"""
    src = os.path.join(library, SHARED_PATHS["SHARED"][0])
    if not rename_enabled() or not os.path.isdir(src):
        return []
    if os.path.exists(os.path.join(library, SHARED_PATHS["SHARED"][1])):
        raise project.ProjectError("%s 和 %s 同時存在，請先手動合併" % (SHARED_PATHS["SHARED"][0], SHARED_PATHS["SHARED"][1]))
    moves = []
    for base, dirs, files in os.walk(src):
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), library).replace(os.sep, "/")
            moves.append((rel, map_shared(rel)))
    if dry_run:
        return ["%s/ → %s/（%d 個檔）" % (SHARED_PATHS["SHARED"][0], SHARED_PATHS["SHARED"][1], len(moves))]
    for old, new in moves:
        os.renames(os.path.join(library, *old.split("/")), os.path.join(library, *new.split("/")))
    if os.path.isdir(src) and not any(files for _, _, files in os.walk(src)):    # 搬完只剩空資料夾（os.renames 可能已經清掉）
        shutil.rmtree(src)
    os.makedirs(os.path.join(library, SHARED_PATHS["SHARED"][1]), exist_ok=True)
    return ["%s/ → %s/（%d 個檔）" % (SHARED_PATHS["SHARED"][0], SHARED_PATHS["SHARED"][1], len(moves))]


STEPS = [
    Step("book_meta", "書的身分證 book.json", _meta_needed, _meta_plan, _meta_apply),
    Step("rename", "資料夾與系統檔名換成英文", _rename_needed, _rename_plan, _rename_apply),
]


# ---------------------------------------------------------------------------
# 備份與還原
# ---------------------------------------------------------------------------
def _backup_dir(book_dir):
    return layout.path(book_dir, layout.MIGRATE_DIR)


def _walk_files(book_dir):
    skip_backup = os.path.normpath(_backup_dir(book_dir))
    for base, dirs, files in os.walk(book_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and os.path.normpath(os.path.join(base, d)) != skip_backup)
        for f in sorted(files):
            p = os.path.join(base, f)
            yield p, os.path.relpath(p, book_dir).replace(os.sep, "/")


def _empty_dir_rels(book_dir):
    skip_backup = os.path.normpath(_backup_dir(book_dir))
    for base, dirs, files in os.walk(book_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and os.path.normpath(os.path.join(base, d)) != skip_backup)
        if base != book_dir and not dirs and not files:
            yield os.path.relpath(base, book_dir).replace(os.sep, "/")


def backup(book_dir):
    """整本書壓成 zip（不含 .git 與備份資料夾本身），回傳 zip 路徑；失敗丟例外（呼叫端要中止）。"""
    d = _backup_dir(book_dir)
    os.makedirs(d, exist_ok=True)
    name = layout.MIGRATE_BACKUP_PREFIX + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip"
    p = os.path.join(d, name)
    n = 1
    while os.path.exists(p):
        n += 1
        p = os.path.join(d, name.replace(".zip", "_%d.zip" % n))
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        for full, rel in _walk_files(book_dir):
            z.write(full, rel)
        for rel in _empty_dir_rels(book_dir):     # 空資料夾也記下來，還原時才會回來
            z.writestr(rel + "/", "")
    with zipfile.ZipFile(p) as z:          # 確認壓縮檔可以讀
        if z.testzip() is not None:
            raise project.ProjectError("備份檔損壞：%s" % p)
    return p


def backups(book_dir):
    d = _backup_dir(book_dir)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.startswith(layout.MIGRATE_BACKUP_PREFIX) and f.endswith(".zip"))


def rollback(book_dir, zip_path=None):
    """用移轉前的備份還原：先清掉書裡的檔案（.git 與備份資料夾不動），再解壓。回傳用了哪一份備份。"""
    zs = [zip_path] if zip_path else backups(book_dir)
    if not zs or not zs[-1] or not os.path.isfile(zs[-1]):
        raise project.ProjectError("找不到移轉前的備份")
    zp = zs[-1]
    with zipfile.ZipFile(zp) as z:
        bad = [n for n in z.namelist() if n.startswith("/") or ".." in n.split("/")]
        if bad:
            raise project.ProjectError("備份檔裡有不安全的路徑：%s" % bad[0])
        for full, _ in list(_walk_files(book_dir)):
            os.remove(full)
        for base, dirs, _ in os.walk(book_dir, topdown=False):      # 清掉空資料夾（.git、備份除外）
            for d in dirs:
                p = os.path.join(base, d)
                if d in SKIP_DIRS or os.path.normpath(p) == os.path.normpath(_backup_dir(book_dir)):
                    continue
                if os.path.isdir(p) and not os.listdir(p):
                    os.rmdir(p)
        z.extractall(book_dir)
    return zp


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def pending(book_dir):
    return [s for s in STEPS if s.needed(book_dir)]


def is_book(d):
    if not os.path.isdir(d) or os.path.basename(d).startswith((".", "_")):     # _共用／_shared 不是書
        return False
    return bookmeta.exists(d) or any(os.path.isdir(os.path.join(d, v[k])) for v in (v2_view(), v3_view()) for k in ("MANUSCRIPT", "BIBLE"))


def books_in(path):
    """傳進來的是一本書就回傳 [它]；是書庫就回傳底下每一本書。"""
    if is_book(path):
        return [path]
    return [os.path.join(path, n) for n in sorted(os.listdir(path)) if is_book(os.path.join(path, n))]


def _report(book_dir, lines):
    d = layout.path(book_dir, layout.MIGRATE_DIR)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "migrate-v3_%s.md" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    project.write_atomic(p, "\n".join(lines).rstrip() + "\n")
    return p


def migrate(book_dir, dry_run=False, now=None):
    """回傳 {"status": "skipped"|"dry_run"|"done"|"rolled_back", "steps": [...], "report": 路徑, ...}。"""
    title = os.path.basename(os.path.normpath(book_dir))
    todo = pending(book_dir)
    if not todo:
        return {"book": title, "status": "skipped", "steps": [], "message": "已經是最新格式"}
    steps = [{"key": s.key, "title": s.title, "changes": s.plan(book_dir)} for s in todo]
    if dry_run:
        return {"book": title, "status": "dry_run", "steps": steps, "stats": stats(book_dir)}
    before = stats(book_dir)
    zp = backup(book_dir)
    done = []
    try:
        for s in todo:
            done.append({"key": s.key, "title": s.title, "changes": s.apply(book_dir)})
        after = stats(book_dir)
    except Exception as e:      # 任何一步失敗：整本還原
        rollback(book_dir, zp)
        return {"book": title, "status": "rolled_back", "steps": done, "backup": zp, "message": "轉換失敗，已還原：%s" % e}
    diff = {k: (before[k], after.get(k)) for k in before if before[k] != after.get(k)}
    if diff:
        rollback(book_dir, zp)
        return {"book": title, "status": "rolled_back", "steps": done, "backup": zp, "diff": diff,
                "message": "轉換前後的統計對不上，已還原：" + "、".join("%s %s → %s" % (k, a, b) for k, (a, b) in diff.items())}
    lines = ["# 格式移轉報告：%s" % title, "", "- 備份：%s" % os.path.relpath(zp, book_dir).replace(os.sep, "/"), ""]
    for s in done:
        lines += ["## %s" % s["title"]] + ["- " + c for c in s["changes"]] + [""]
    lines += ["## 統計（轉換前後相同）"] + ["- %s：%s" % (k, v) for k, v in before.items()]
    rp = _report(book_dir, lines)
    return {"book": title, "status": "done", "steps": done, "backup": zp, "stats": before, "report": rp}
