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
import unicodedata
import shutil
import zipfile

from . import bookmeta, context, fmkeys, layout, project, sections, trackjson, volume

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
        "卷綱": len(_volume_files(book_dir, L)),
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
    """要先轉換的舊書：還有 v2 的資料夾，或逐章資料夾裡還有舊檔名（第001章_…）。
    只看資料夾與檔名（書架每次都會問，不能讀檔）。"""
    return rename_enabled() and (any(os.path.isdir(os.path.join(book_dir, *d.split("/"))) for d in _V2_DIRS)
                                 or _old_chapter_files(book_dir) or _old_volume_files(book_dir) or _docs_needed(book_dir)
                                 or _fm_pending_quick(book_dir) or _sec_pending_quick(book_dir))
    # 沒有 JSON 不算舊格式：讀取時以 .md 為準，下次回寫（trackjson.sync）就會補上


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


# --- 第三步：逐章檔名換成 ch-0001 ---------------------------------------------------
_OLD_CH_FILE = re.compile(r"^第0*(\d+)章(_.*)?(\.[^.]+(?:\.[^.]+)?)$")       # 第001章_章名.md、第001章.json、第001章.draft.md
_OLD_CH_RANGE = re.compile(r"^第0*(\d+)-0*(\d+)章(.*)$")                   # 第001-003章.json、第001-010章_報告.md
_OLD_CH_DIR = re.compile(r"^第0*(\d+)章$")                                  # 插圖、流程快照的逐章資料夾
_CH_TEXT_DIRS = ("MANUSCRIPT", "CANDIDATES")                               # 章名可能只在檔名裡的資料夾
_CH_DIRS = ("MANUSCRIPT", "CANDIDATES", "CHAPTER_CARDS", "REVERSE_CARDS", "SUMMARIES")
_CH_SKIP = ("STUDIO_BACKUP",)                                              # 備份是歷史紀錄，不改名


def _ch_scope(rel):
    """這個檔案在不在逐章改名的範圍：各章資料夾（含反推草稿裡的）、.studio（備份、任務紀錄除外）、插圖的各章資料夾。"""
    v3 = v3_view()
    rel = map_rel(rel)          # 還沒改資料夾名稱的書（試跑時）：用改名後的位置判斷
    inner = rel[len(_REV_DRAFTS):] if rel.startswith(_REV_DRAFTS) else rel
    if any(os.path.dirname(inner) == v3[k] for k in _CH_DIRS):
        return True
    if rel.startswith(PATHS["ILLUST"][1] + "/" + NAMES["ILLUST_CHAPTERS"][1] + "/"):
        return True
    if rel.startswith(".studio/") and not rel.startswith(_REV_DRAFTS):
        return not any(rel.startswith(v3[k] + "/") for k in _CH_SKIP) and not rel.startswith((layout.MIGRATE_DIR + "/", ".studio/jobs/"))
    return False


def _ch_name(name, is_dir=False):
    """舊的逐章名稱 → 新名稱；不是逐章名稱回傳 None。"""
    if is_dir:
        m = _OLD_CH_DIR.match(name)
        return layout.chapter_stem(int(m.group(1))) if m else None
    m = _OLD_CH_RANGE.match(name)
    if m:
        return "ch-%04d-%04d%s" % (int(m.group(1)), int(m.group(2)), m.group(3))
    m = _OLD_CH_FILE.match(name)
    if m:
        return layout.chapter_stem(int(m.group(1))) + m.group(3)
    return None


def _ch_moves(book_dir):
    """[(舊相對路徑, 新相對路徑, 舊檔名裡的章名)]；目錄層的「第001章/」也一起換。撞名的加 .v2、.v3……"""
    moves, taken = [], set()
    for _, rel in _walk_files(book_dir):
        if not _ch_scope(rel):
            continue
        parts = rel.split("/")
        new_parts = [(_ch_name(p, is_dir=True) or p) for p in parts[:-1]]
        leaf = _ch_name(parts[-1]) or parts[-1]
        title = ""
        m = _OLD_CH_FILE.match(parts[-1])
        if m and m.group(2):
            title = m.group(2)[1:]
        new = "/".join(new_parts + [leaf])
        if new == rel:
            continue
        stem, ext = (new.rsplit(".", 1) + [""])[:2] if "." in leaf else (new, "")
        k = 2
        while new in taken or (os.path.exists(os.path.join(book_dir, *new.split("/"))) and new != rel):
            new = "%s.v%d.%s" % (stem, k, ext) if ext else "%s.v%d" % (stem, k)
            k += 1
        taken.add(new)
        moves.append((rel, new, title))
    return moves


def map_v3(rel):
    """v2 路徑 → 完整的 v3 路徑（資料夾名稱＋逐章檔名＋卷綱檔名）。給測試與快照比對用；實際搬檔時撞名會另加 .v2。"""
    rel = map_rel(rel)
    vol = _vol_target(rel)
    if vol:
        return vol
    if not _ch_scope(rel):
        return rel
    parts = rel.split("/")
    return "/".join([(_ch_name(p, is_dir=True) or p) for p in parts[:-1]] + [_ch_name(parts[-1]) or parts[-1]])


def _old_chapter_files(book_dir):
    """工作台會用到的四個逐章資料夾裡，還有舊檔名的檔（書架偵測用，只列資料夾、不讀檔）。"""
    v3 = v3_view()
    for k in _CH_DIRS:
        d = os.path.join(book_dir, *v3[k].split("/"))
        if os.path.isdir(d) and any(_OLD_CH_FILE.match(f) for f in os.listdir(d)):
            return True
    return False


def _chapters_needed(book_dir):
    return rename_enabled() and bool(_ch_moves(book_dir))


def _chapters_plan(book_dir):
    moves = _ch_moves(book_dir)
    by_dir = {}
    for old, new, _ in moves:
        d = os.path.dirname(old) or "."
        by_dir[d] = by_dir.get(d, 0) + 1
    out = ["%s/：%d 個檔改成 ch-0001 格式" % (d, n) for d, n in sorted(by_dir.items())]
    dup = [new for _, new, _ in moves if ".v" in os.path.basename(new)]
    if dup:
        out.append("同一章有多份（加上 .v2 等）：%s" % "、".join(dup))
    return out or ["沒有要改名的檔案"]


def _chapters_apply(book_dir):
    import json
    out = _chapters_plan(book_dir)
    moves = _ch_moves(book_dir)
    v3 = v3_view()
    headed = []
    for old, new, title in moves:
        src = os.path.join(book_dir, *old.split("/"))
        # 章名只在舊檔名裡（正文沒有一級標題）：補一行標題，章名才不會因為改名而不見
        if title and os.path.dirname(old) in tuple(v3[k] for k in _CH_TEXT_DIRS) and old.endswith(".md"):
            text = project.read_text(src)
            if not project.heading_title(text):
                no = int(_OLD_CH_FILE.match(os.path.basename(old)).group(1))
                project.write_atomic(src, "# 第%d章 %s\n\n%s" % (no, title, text.lstrip("\n")))   # literal-ok: 正文標題的固定寫法
                headed.append(new)
        os.renames(src, os.path.join(book_dir, *new.split("/")))
    if headed:
        out.append("章名原本只在檔名裡，已在正文第一行補上標題：%s" % "、".join(headed))
    fixed = _fix_json_refs(book_dir, [(old, new) for old, new, _ in moves])
    if fixed:
        out.append("改寫紀錄檔裡的路徑：%d 個檔" % fixed)
    return out


def _fix_json_refs(book_dir, moves, dirs=True):
    """搬過的檔：紀錄檔（.json）裡指向舊位置的路徑改成新位置。回傳改了幾個檔。
    dirs：資料夾本身也改了名（逐章資料夾），底下其他路徑跟著換；只搬檔案時不要開。"""
    import json
    rel_map = dict(moves)
    dir_map = {}
    for old, new in moves:
        od, nd = os.path.dirname(old), os.path.dirname(new)
        if dirs and od != nd:
            dir_map[od] = nd

    def fix(v):
        if isinstance(v, dict):
            return {fix(k): fix(x) for k, x in v.items()}
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, str):
            if v in rel_map:
                return rel_map[v]
            for od, nd in dir_map.items():
                if v == od or v.startswith(od + "/"):
                    return nd + v[len(od):]
        return v
    fixed = 0
    for full, rel in _book_files(book_dir):
        if rel.endswith(".json") and not rel.startswith(".studio/jobs/"):
            try:
                with open(full, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            new = fix(data)
            if new != data:
                project.write_atomic(full, json.dumps(new, ensure_ascii=False, indent=1) + "\n")
                fixed += 1
    return fixed


# --- 卷綱檔名換成 vol-01（正式卷綱一律放 outline/volumes/） ---------------------------
_VOL_NUM = r"([〇零一二兩三四五六七八九十百\d]+)"
_OLD_VOL = re.compile(r"^卷綱_第" + _VOL_NUM + r"([卷幕])(.*)\.md$")           # 卷綱_第1卷.md、卷綱_第一卷.md、卷綱_第二幕.md
_OLD_VOL_ALT = re.compile(r"^卷" + _VOL_NUM + r"卷綱\.md$")                     # 卷一卷綱.md（早期的寫法）
_OLD_VOL_REV = re.compile(r"^卷綱修訂_第" + _VOL_NUM + r"卷\.md$")              # 修訂草稿
_OLD_VOL_UPD = re.compile(r"^卷綱更新_第0*(\d+)-0*(\d+)章\.md$")               # 卷末體檢的卷綱更新草稿


def _is_old_volume(name):
    return name.endswith(".md") and (name.startswith("卷綱") or bool(_OLD_VOL_ALT.match(name)))


def _volume_files(book_dir, view):
    """正式卷綱的檔：outline/ 第一層的舊式卷綱，加上 outline/volumes/ 裡全部（統計用，哪一版的資料夾都能數）。"""
    out = []
    for sub, every in ((view["OUTLINE"], False), (view["VOLUMES_SUBDIR"], True)):
        d = os.path.join(book_dir, *sub.split("/"))
        if os.path.isdir(d):
            out += [sub + "/" + f for f in sorted(os.listdir(d))
                    if os.path.isfile(os.path.join(d, f)) and (f.endswith(".md") if every else _is_old_volume(f))]
    return out


def _vol_name(name, draft=False):
    """舊卷綱檔名 → 新檔名；認不出卷號的回 None（照原名搬）。"""
    m = _OLD_VOL_UPD.match(name)
    if m and draft:
        return layout.VOLUME_UPDATE_PREFIX + "ch-%04d-%04d.md" % (int(m.group(1)), int(m.group(2)))
    m = _OLD_VOL_REV.match(name)
    if m and draft:
        no = volume.no_of("第%s卷" % m.group(1))       # literal-ok: 舊檔名的卷號寫法
        return layout.volume_stem(no) + layout.VOLUME_REVISION_SUFFIX if no else None
    m = _OLD_VOL.match(name)
    if m:
        no = volume.no_of("第%s卷" % m.group(1))       # literal-ok: 舊檔名的卷號寫法
        stem = (layout.ACT_STEM if m.group(2) == "幕" else layout.VOLUME_STEM) % no if no else None
        return stem + m.group(3) + ".md" if stem else None
    m = _OLD_VOL_ALT.match(name)
    if m:
        no = volume.no_of(m.group(1))
        return layout.volume_stem(no) + ".md" if no else None
    return None


def _vol_target(rel):
    """這個檔要搬去哪；不是舊卷綱回 None。反推草稿資料夾裡的大綱也一樣處理。"""
    v3 = v3_view()
    rel = map_rel(rel)
    pre = _REV_DRAFTS if rel.startswith(_REV_DRAFTS) else ""
    inner = rel[len(pre):]
    d, name = os.path.dirname(inner), os.path.basename(inner)
    if d in (v3["OUTLINE"], v3["VOLUMES_SUBDIR"]) and _is_old_volume(name):
        return pre + v3["VOLUMES_SUBDIR"] + "/" + (_vol_name(name) or name)
    if d == v3["VOLUME_DRAFTS"] and name.startswith("卷綱") and name.endswith(".md"):
        new = _vol_name(name, draft=True)
        return pre + d + "/" + new if new else None
    return None


def map_volume(rel):
    """v2（或還沒改卷綱檔名的 v3）路徑 → 新的卷綱路徑；不是卷綱就原樣。"""
    return _vol_target(rel) or rel


def _vol_moves(book_dir):
    moves, taken = [], set()
    for _, rel in _walk_files(book_dir):
        if rel.startswith((PATHS["STUDIO_BACKUP"][1] + "/", layout.MIGRATE_DIR + "/", ".studio/jobs/")):
            continue
        new = _vol_target(rel)
        if not new or new == rel:
            continue
        stem, ext = new[:-3], ".md"
        k = 2
        while new in taken or os.path.exists(os.path.join(book_dir, *new.split("/"))):
            new = "%s.v%d%s" % (stem, k, ext)
            k += 1
        taken.add(new)
        moves.append((rel, new))
    return moves


def _old_volume_files(book_dir):
    """書架偵測用：outline/、outline/volumes/、outline/drafts/ 裡還有舊式卷綱檔名（只列資料夾、不讀檔）。"""
    v3 = v3_view()
    checks = (("OUTLINE", _is_old_volume), ("VOLUMES_SUBDIR", _vol_name),
              ("VOLUME_DRAFTS", lambda f: f.startswith("卷綱") and _vol_name(f, draft=True)))
    for k, old in checks:
        d = os.path.join(book_dir, *v3[k].split("/"))
        if os.path.isdir(d) and any(old(f) for f in os.listdir(d)):
            return True
    return False


def _volumes_needed(book_dir):
    return rename_enabled() and bool(_vol_moves(book_dir))


def _volumes_plan(book_dir):
    out = ["%s → %s" % (map_rel(old), new) for old, new in _vol_moves(book_dir)]
    return out or ["沒有要改名的卷綱"]


def _volumes_apply(book_dir):
    out = _volumes_plan(book_dir)
    moves = _vol_moves(book_dir)
    for old, new in moves:
        os.renames(os.path.join(book_dir, *old.split("/")), os.path.join(book_dir, *new.split("/")))
    fixed = _fix_json_refs(book_dir, moves, dirs=False)
    if fixed:
        out.append("改寫紀錄檔裡的路徑：%d 個檔" % fixed)
    return out


# --- frontmatter 的鍵換成英文（類型 → type、狀態 → status……；值不動） ---------------------
_FM_LINE = re.compile(r"^(%s)[ \t]*[:：]" % "|".join(sorted(map(re.escape, fmkeys.ZH2EN), key=len, reverse=True)))


_FM_VALUE = re.compile(r"^([A-Za-z_]+):([ \t]*)([^#\n]*?)([ \t]*(?:#.*)?)$")


def _fm_value_line(l):
    """type、status、role、category、default 那一行：值換成英文 ID；註解裡列出的固定詞也換。作者自己寫的值不動。"""
    m = _FM_VALUE.match(l)
    if not m:
        return l
    if m.group(1) in fmkeys.CHAPTER_KEYS + ("chapter_range", "volume"):
        return _fm_number_line(*m.groups())
    if m.group(1) not in fmkeys.VALUES:
        return l
    key, sp, val, comment = m.groups()
    q = val[:1] if val[:1] in "\"'" and val[-1:] == val[:1] and len(val) > 1 else ""
    raw = val[1:-1] if q else val
    new = fmkeys.value_en(key, raw) if raw else raw
    if comment:
        for e, zh in sorted(fmkeys.VALUES[key], key=lambda p: -len(p[1])):
            comment = re.sub(r"(?<![\w\u4e00-\u9fff])%s(?![\w\u4e00-\u9fff])" % re.escape(zh), e, comment)
    return "%s:%s%s%s%s%s" % (key, sp, q, new if isinstance(new, str) else raw, q, comment)


_RANGE_EXAMPLE = re.compile(r"第0*(\d+)章\s*[～~\-－–—至到]\s*第0*(\d+)章")     # literal-ok: v2 的章節範圍寫法


def _fm_number_line(key, sp, val, comment):
    """章號、章節範圍、所屬卷：第012章 → 12、第001章～第060章 → [1, 60]、第一卷 → 1。讀不出數字的原樣。"""
    raw = val.strip().strip("\"'")
    new = val
    if raw:
        if key == "chapter_range":
            nums = re.findall(r"\d+", raw)
            if len(nums) >= 2 and not raw.startswith("["):
                new = "[%d, %d]" % (int(nums[0]), int(nums[-1]))
        elif key == "volume":
            n = fmkeys.volume_int(raw)
            new = str(n) if n is not None else val
        else:
            n = fmkeys.ch_int(raw)
            new = str(n) if n is not None and re.fullmatch(r"(?:第\s*0*\d+\s*章|0*\d+|ch-?0*\d+)", raw, re.I) else val
    if comment:
        comment = _RANGE_EXAMPLE.sub(lambda mm: "[%d, %d]" % (int(mm.group(1)), int(mm.group(2))), comment)
    return "%s:%s%s%s" % (key, sp, new, comment)


def _fm_block(lines):
    """frontmatter 那幾行的鍵換成英文、固定詞的值換成英文 ID。
    鍵換了之後跟既有的鍵重複（同一欄寫了中英兩次）就保留原樣，不弄壞 YAML。"""
    have = {l.split(":", 1)[0].strip() for l in lines if ":" in l and not l.startswith((" ", "\t", "-", "#"))}
    out = []
    for l in lines:
        m = _FM_LINE.match(l)
        if m:
            new = fmkeys.en(m.group(1))
            if new not in have:
                rest = l[m.end():]
                l = new + ":" + (rest if not rest or rest[0] in " \t" else " " + rest)     # 全形冒號「狀態：草稿」後面沒空格
                have.add(new)
        out.append(_fm_value_line(l))
    return out


def fm_rewrite(text, fenced=False):
    """開頭 frontmatter 的中文鍵換成英文；正文不動。fenced=True 時連 ``` 區塊裡的 frontmatter 範例一起換（技能說明用）。"""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is not None:
            lines[1:end] = _fm_block(lines[1:end])
    if fenced:
        i = 0
        while i < len(lines):
            if lines[i].startswith("```") and i + 1 < len(lines) and lines[i + 1].strip() == "---":
                end = next((j for j in range(i + 2, len(lines)) if lines[j].strip() == "---"), None)
                if end is None:
                    break
                lines[i + 2:end] = _fm_block(lines[i + 2:end])
                i = end
            i += 1
    return "\n".join(lines)


_FM_SKIP = (PATHS["STUDIO_BACKUP"][1] + "/", ".studio/jobs/")


def _fm_files(book_dir):
    """frontmatter 裡還有中文鍵的 .md（備份、任務紀錄、移轉資料夾除外）。"""
    out = []
    for full, rel in _walk_files(book_dir):
        if not rel.endswith(".md") or rel.startswith(_FM_SKIP + (layout.MIGRATE_DIR + "/",)):
            continue
        try:
            text = project.read_text(full)
        except (OSError, UnicodeDecodeError):
            continue
        if text.startswith("---") and fm_rewrite(text) != text:
            out.append(rel)
    return out


_FM_PROBE = ("STORY_CORE", "BOOK_OUTLINE", "STATE_CARD", "STYLE")


def _fm_pending_quick(book_dir):
    """書架偵測用：只看幾份一定有 frontmatter 的系統檔，不掃整本書。"""
    v3 = v3_view()
    for k in _FM_PROBE:
        p = os.path.join(book_dir, *v3[k].split("/"))
        if os.path.isfile(p):
            text = project.read_text(p)
            if fm_rewrite(text) != text:
                return True
    return False


def _has_v2_dirs(book_dir):
    return any(os.path.isdir(os.path.join(book_dir, d)) for d in TOP_V2)


_AFTER_RENAME = "資料夾改名後一併處理"


def _fmkeys_needed(book_dir):
    # v2 的書一定還是中文鍵：試跑時先列出來（實際在資料夾改名之後才做）
    return rename_enabled() and (_has_v2_dirs(book_dir) or bool(_fm_files(book_dir)))


def _fmkeys_plan(book_dir):
    if _has_v2_dirs(book_dir):
        return [_AFTER_RENAME]
    files = _fm_files(book_dir)
    by_dir = {}
    for r in files:
        d = os.path.dirname(r) or "."
        by_dir[d] = by_dir.get(d, 0) + 1
    return ["%s/：%d 個檔" % (d, n) for d, n in sorted(by_dir.items())] or ["沒有要改的"]


def _fmkeys_apply(book_dir):
    out = _fmkeys_plan(book_dir)
    for rel in _fm_files(book_dir):
        p = os.path.join(book_dir, *rel.split("/"))
        project.write_atomic(p, fm_rewrite(project.read_text(p)))
    return out


# --- 第四步：系統文件裡的路徑（CLAUDE.md、_templates、名詞表、設定索引） ------------------
# Claude Code 照 CLAUDE.md 與範本找檔、寫檔，裡面的路徑沒換，技能就會寫回舊位置。
_CH_PATTERN = re.compile(r"第NNN章(?:_(?:<[^<>\s]{1,20}>|章名|章題|題名|title|\*))?\.md")     # literal-ok: 舊檔名樣板
_DOC_TOKEN = re.compile(r"[^\s|，、。；：（）()「」『』【】\[\]<>\"'`*,{}・;:]+")


# 資料夾樹狀圖裡是相對的名稱（「│   ├── 故事核心.md」），上面的路徑規則認不出來，另外處理
_TREE_NAMES = [("故事核心.md", "story-core.md"), ("文風.md", "style.md"), ("作者偏好.md", "author-prefs.md"), ("名詞表.md", "glossary.md"),
         ("世界觀/", "world/"), ("角色狀態/", "characters/"), ("角色/", "characters/"), ("勢力/", "factions/"), ("草稿/", "drafts/"),
         ("全書大綱.md", "book.md"), ("章綱/第001章.md", "chapters/ch-0001.md"), ("狀態卡.md", "state-card.md"),
         ("伏筆.md", "foreshadowing.md"), ("時間線.md", "timeline.md"), ("讀者認知.md", "reader-knowledge.md"), ("關係.md", "relations.md"),
         ("章節摘要/第001章.md", "summaries/ch-0001.md"),
         ("卷綱_第一卷.md", "volumes/vol-01.md")]
_DOC_VOL = [(re.compile(r"(?<![\w/])outline/drafts/卷綱修訂_第[NX{][^/`\s]*?卷\.md"), "outline/drafts/vol-NN.revision.md"),   # literal-ok: 舊檔名樣板
             (re.compile(r"(?<![\w/])outline/drafts/卷綱_第[NX{][^/`\s]*?卷\.md"), "outline/drafts/vol-NN.md"),
             (re.compile(r"(?<![\w/])outline/卷綱_第[NX{][^/`\s]*?卷\.md"), "outline/volumes/vol-NN.md")]
_TREE_CH_TEXT = re.compile(r"第001章_(?:<[^>]+>|章名)\.md")
_TREE_COL = 31


def _width(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _fix_tree(text):
    """資料夾樹狀圖（```區塊裡的 ├── 行）：系統檔名換成英文、註解欄重新對齊。"""
    out, inside = [], False
    for line in text.split("\n"):
        if line.startswith("```"):
            inside = not inside
            out.append(line)
            continue
        m = re.match(r"^([│ ]*[├└]── )(\S+)(\s{2,}(.*))?$", line) if inside else None
        if not m:
            out.append(line)
            continue
        pre, name, comment = m.group(1), m.group(2), m.group(4)
        for old, new in _TREE_NAMES:
            if name.startswith(old):
                name = new + name[len(old):]
                break
        name = _TREE_CH_TEXT.sub("ch-0001.md", name)
        if comment:
            pad = max(2, _TREE_COL - _width(pre + name))
            out.append(pre + name + " " * pad + comment)
        else:
            out.append(pre + name)
    return "\n".join(out)  # literal-ok: v2 名稱對照


def _doc_rewrite(text):
    def tok(m):
        t, tail = m.group(0), ""
        while len(t) > 1 and t[-1] in ".!?":
            t, tail = t[:-1], t[-1] + tail
        new = map_ref(t)
        if "/" in new and re.search(r"第\d+章", new):         # 具體的章節檔：outline/chapters/第001章.md → ch-0001.md
            new = map_v3(new)
        if "/" in new and "卷綱" in new:                       # 具體的卷綱：outline/卷綱_第1卷.md → outline/volumes/vol-01.md
            new = map_volume(new)
        nxt = text[m.end():m.end() + 1]
        if new == t and t.startswith(tuple(x + "/" for x in TOP_V2)) and nxt and nxt in "<{*%":
            new = map_rel(t.rstrip("/")) + ("/" if t.endswith("/") else "")      # 第一層資料夾＋檔名樣板
        return new + tail
    for pat, new in _DOC_VOL:
        text = pat.sub(new, text)
    return _fix_tree(_CH_PATTERN.sub("ch-NNNN.md", _DOC_TOKEN.sub(tok, text)))


def _doc_files(book_dir):
    v3 = v3_view()
    out = ["CLAUDE.md", v3["GLOSSARY"], v3["BIBLE_INDEX"], v3["BOOK_OUTLINE"]]     # 全書大綱「分卷」裡有卷綱的連結
    d = os.path.join(book_dir, *v3["TEMPLATES"].split("/"))
    if os.path.isdir(d):
        out += [v3["TEMPLATES"] + "/" + f for f in sorted(os.listdir(d)) if f.endswith(".md")]
    return [r for r in out if os.path.isfile(os.path.join(book_dir, *r.split("/")))]


def _docs_pending(book_dir):
    out = []
    for rel in _doc_files(book_dir):
        text = project.read_text(os.path.join(book_dir, *rel.split("/")))
        if _doc_rewrite(text) != text:
            out.append(rel)
    return out


def _docs_needed(book_dir):
    return rename_enabled() and (_has_v2_dirs(book_dir) or bool(_docs_pending(book_dir)))


def _docs_plan(book_dir):
    if _has_v2_dirs(book_dir):
        return [_AFTER_RENAME]
    files = _docs_pending(book_dir)
    return ["改寫檔案裡的舊路徑：%s" % "、".join(files)] if files else ["沒有要改的"]


def _docs_apply(book_dir):
    out = _docs_plan(book_dir)
    for rel in _docs_pending(book_dir):
        p = os.path.join(book_dir, *rel.split("/"))
        project.write_atomic(p, _doc_rewrite(project.read_text(p)))
    return out


# --- 段落標題依書的語言（英文、日文書；繁中書不變） ------------------------------------
def _sec_lang(book_dir):
    from . import lang as lang_mod
    return lang_mod.book_lang(book_dir)


def _sec_files(book_dir):
    """段落標題、範本欄位、文件標題還不是書的語言的 .md（備份、任務紀錄、移轉資料夾除外）。"""
    lang = _sec_lang(book_dir)
    if lang not in ("en", "ja"):
        return []
    out = []
    for full, rel in _walk_files(book_dir):
        if not rel.endswith(".md") or rel.startswith(_FM_SKIP + (layout.MIGRATE_DIR + "/",)):
            continue
        try:
            text = project.read_text(full)
        except (OSError, UnicodeDecodeError):
            continue
        if text.startswith("---") and sections.localize_doc(text, lang) != text:
            out.append(rel)
    return out


def _sec_pending_quick(book_dir):
    lang = _sec_lang(book_dir)
    if lang not in ("en", "ja"):
        return False
    v3 = v3_view()
    for k in _FM_PROBE + ("FORESHADOWING",):       # 伏筆表：第六批起表頭與固定值也依書的語言
        p = os.path.join(book_dir, *v3[k].split("/"))
        if os.path.isfile(p):
            text = project.read_text(p)
            if sections.localize_doc(text, lang) != text:
                return True
    return False


def _sections_needed(book_dir):
    if not rename_enabled():
        return False
    if _has_v2_dirs(book_dir):
        return _old_lang(book_dir) in ("en", "ja")
    return bool(_sec_files(book_dir))


def _sections_plan(book_dir):
    if _has_v2_dirs(book_dir):
        return [_AFTER_RENAME]
    by_dir = {}
    for r in _sec_files(book_dir):
        d = os.path.dirname(r) or "."
        by_dir[d] = by_dir.get(d, 0) + 1
    return ["%s/：%d 個檔" % (d, n) for d, n in sorted(by_dir.items())] or ["沒有要改的"]


def _sections_apply(book_dir):
    out = _sections_plan(book_dir)
    lang = _sec_lang(book_dir)
    for rel in _sec_files(book_dir):
        p = os.path.join(book_dir, *rel.split("/"))
        project.write_atomic(p, sections.localize_doc(project.read_text(p), lang))
    return out


# --- 追蹤表的 JSON 正本 -------------------------------------------------------------
def _tables_needed(book_dir):
    # 只在轉換舊書時順便補；不會單獨讓一本書被判成「要轉換」（見 needs_migration）
    if not rename_enabled():
        return False
    return _has_v2_dirs(book_dir) or bool(trackjson.pending(book_dir))


def _tables_plan(book_dir):
    if _has_v2_dirs(book_dir):
        return [_AFTER_RENAME]
    return ["%s → %s" % (rel, trackjson.json_rel(rel)) for rel in trackjson.pending(book_dir)] or ["沒有要改的"]


def _tables_apply(book_dir):
    out = _tables_plan(book_dir)
    trackjson.sync(book_dir)
    return out


STEPS = [
    Step("book_meta", "書的身分證 book.json", _meta_needed, _meta_plan, _meta_apply),
    Step("rename", "資料夾與系統檔名換成英文", _rename_needed, _rename_plan, _rename_apply),
    Step("chapters", "逐章檔名換成 ch-0001", _chapters_needed, _chapters_plan, _chapters_apply),
    Step("volumes", "卷綱檔名換成 vol-01", _volumes_needed, _volumes_plan, _volumes_apply),
    Step("docs", "系統文件裡的路徑", _docs_needed, _docs_plan, _docs_apply),
    Step("fmkeys", "frontmatter 的鍵與固定詞換成英文", _fmkeys_needed, _fmkeys_plan, _fmkeys_apply),
    Step("sections", "段落標題換成書的語言", _sections_needed, _sections_plan, _sections_apply),
    Step("tables", "追蹤表加上 JSON 正本", _tables_needed, _tables_plan, _tables_apply),
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
            if not s.needed(book_dir):       # 前面的步驟可能已經處理掉（各步驟會互相影響，套用前再確認一次）
                continue
            done.append({"key": s.key, "title": s.title, "changes": s.apply(book_dir)})
        for s in STEPS:                      # 前面的步驟（例如改資料夾名稱）做完才看得出來的
            if s.key not in {d["key"] for d in done} and s.needed(book_dir):
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
