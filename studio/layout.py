# -*- coding: utf-8 -*-
"""書的資料夾結構：所有系統定義的資料夾與檔名都集中在這裡。

v3 結構英文化（見專案文件「15_v3結構英文化規格」）的第一步：
程式其他地方不再直接寫 "設定/文風.md" 這類字串，一律引用這裡的常數。
P1 階段「只搬位置、不改值」：常數的值仍是 v2 的中文名稱，行為完全不變；
P3 改成英文名稱時，只要改這一個檔（加上移轉工具）。

慣例
- 常數一律是書資料夾底下的相對路徑，用 "/" 分隔（跟 project.rel_of 回傳的格式一致）。
- 要組成實際路徑請用 path(book_dir, REL)，不要自己 os.path.join(book_dir, REL)：
  REL 裡的 "/" 在 Windows 要拆開，路徑才會跟以前完全一樣。
- 使用者內容（書名、角色名、章名）不在這裡；這裡只有系統名稱。
"""
import os

# ---------------------------------------------------------------------------
# 第一層資料夾
# ---------------------------------------------------------------------------
BIBLE = "設定"
OUTLINE = "大綱"
MANUSCRIPT = "正文"
CANDIDATES = "候選"
TRACKING = "追蹤"
SAMPLES = "範例"
TEMPLATES = "_範本"
STUDIO = ".studio"
BOOK_META = "book.json"          # 書的身分證（格式版本、書名、語言）；各版都放在書的根目錄
SCHEMA_VERSION = 2               # 這版程式寫出的書的格式。P3 把資料夾、檔名換成英文後改成 3

# 書架與檔案瀏覽看得到的資料夾（順序就是顯示順序）
BROWSABLE = (BIBLE, OUTLINE, MANUSCRIPT, TRACKING, CANDIDATES, SAMPLES, TEMPLATES)

# ---------------------------------------------------------------------------
# 設定集
# ---------------------------------------------------------------------------
CHARACTERS = BIBLE + "/角色"
FACTIONS = BIBLE + "/勢力"
WORLD = BIBLE + "/世界觀"
BIBLE_DRAFTS = BIBLE + "/草稿"
BIBLE_MERGED = BIBLE + "/_已合併"
BIBLE_STRUCTURE = BIBLE + "/章節結構"

STORY_CORE = BIBLE + "/故事核心.md"
STYLE = BIBLE + "/文風.md"
GLOSSARY = BIBLE + "/名詞表.md"
AUTHOR_PREFS = BIBLE + "/作者偏好.md"
BIBLE_INDEX = BIBLE + "/_索引.md"
STYLE_FINGERPRINT = BIBLE + "/風格指紋.json"
STRUCTURE_DNA = BIBLE + "/結構DNA.json"
CONTRACT = BIBLE + "/續寫合約.md"
BOOK_STRUCTURE = BIBLE_STRUCTURE + "/結構.md"

# ---------------------------------------------------------------------------
# 大綱
# ---------------------------------------------------------------------------
CHAPTER_CARDS = OUTLINE + "/章綱"
REVERSE_CARDS = CHAPTER_CARDS + "/反推"
VOLUME_DRAFTS = OUTLINE + "/草稿"
VOLUMES_SUBDIR = OUTLINE + "/卷綱"          # spawn 建書時卷綱放這層（v2 另一種寫法是直接放在 大綱/）
BOOK_OUTLINE = OUTLINE + "/全書大綱.md"

# ---------------------------------------------------------------------------
# 追蹤
# ---------------------------------------------------------------------------
SUMMARIES = TRACKING + "/章節摘要"
CHARACTER_STATES = TRACKING + "/角色狀態"
FORESHADOWING = TRACKING + "/伏筆.md"
TIMELINE = TRACKING + "/時間線.md"
STATE_CARD = TRACKING + "/狀態卡.md"
READER_KNOWLEDGE = TRACKING + "/讀者認知.md"
RELATIONS = TRACKING + "/關係.md"
READER_KNOWLEDGE_DRAFT = TRACKING + "/讀者認知_草稿.md"
RELATIONS_DRAFT = TRACKING + "/關係_草稿.md"

# ---------------------------------------------------------------------------
# 候選
# ---------------------------------------------------------------------------
SPINOFF_DRAFTS = CANDIDATES + "/新書草稿"

# ---------------------------------------------------------------------------
# 範本
# ---------------------------------------------------------------------------
PROJECT_RULES = TEMPLATES + "/專案規範.md"

# ---------------------------------------------------------------------------
# .studio（工作台內部資料）
# ---------------------------------------------------------------------------
STUDIO_BACKUP = STUDIO + "/備份"
STUDIO_REVISIONS = STUDIO + "/修訂"
STUDIO_PIPELINE = STUDIO + "/流程"
STUDIO_PIPELINE_CURRENT = STUDIO_PIPELINE + "/目前.json"
STUDIO_PIPELINE_SNAPSHOTS = STUDIO_PIPELINE + "/快照"
STUDIO_REVIEWS = STUDIO + "/審查報告"
STUDIO_REVIEW = STUDIO + "/審查"
STUDIO_CHECK = STUDIO + "/核對"
STUDIO_TRASH = STUDIO + "/刪除"
STUDIO_RECALL_INDEX = STUDIO + "/索引/recall.json"
STUDIO_REVERSE = STUDIO + "/反推"
STUDIO_FIDELITY = STUDIO + "/保真"
STUDIO_WRITEBACK_CHECK = STUDIO + "/回寫檢查"
STUDIO_RECOVERY = STUDIO + "/恢復稿"
STUDIO_EXPORT_PREFS = STUDIO + "/匯出設定.json"
MIGRATE_DIR = STUDIO + "/migrate"              # 移轉工具的備份與報告（各版同名，移轉時不搬動）
MIGRATE_BACKUP_PREFIX = "pre-v3_"              # 移轉前的整本備份：.studio/migrate/pre-v3_YYYYMMDD-HHMMSS.zip
PIPELINE_CURRENT_FILE = "目前.json"            # 流程狀態檔名（放在 STUDIO_PIPELINE 底下）
REVERSE_CUMULATIVE = "累積.json"               # 反推的累積結果（放在 STUDIO_REVERSE 底下）
REVERSE_DRAFTS = "草稿"                        # STUDIO_REVERSE 底下：反推出來、還沒採用的草稿
REVERSE_BATCHES = "批次"                       # STUDIO_REVERSE 底下：逐批抽取結果

# ---------------------------------------------------------------------------
# 書的第一層：插圖、匯出
# ---------------------------------------------------------------------------
ILLUST = "插圖"
ILLUST_INDEX = "_插圖.json"                    # ILLUST 底下
ART_STYLE = "畫風.json"                        # ILLUST 底下
EXPORT = "匯出"

# ---------------------------------------------------------------------------
# 範本檔名（plugin*/skills/novel-setup/templates/ 與書內 _範本/ 共用同一組檔名）
# ---------------------------------------------------------------------------
TEMPLATES_IN_SKILLS = "novel-setup/templates"   # 相對於 plugin*/skills/
TPL_STORY_CORE = "故事核心.md"
TPL_STYLE = "文風.md"
TPL_GLOSSARY = "名詞表.md"
TPL_AUTHOR_PREFS = "作者偏好.md"
TPL_BOOK_OUTLINE = "全書大綱.md"
TPL_VOLUME_OUTLINE = "卷綱.md"
TPL_CHAPTER_CARD = "章綱.md"
TPL_STATE_CARD = "狀態卡.md"
TPL_FORESHADOWING = "伏筆.md"
TPL_TIMELINE = "時間線.md"
TPL_CHARACTER = "角色.md"
TPL_FACTION = "勢力.md"
TPL_WORLD = "世界觀.md"

# ---------------------------------------------------------------------------
# 書庫層級（_共用）
# ---------------------------------------------------------------------------
SHARED = "_共用"                # 書庫第一層的共用資料夾（不是書）
SHARED_TRASH = ".刪除"          # _共用/ 底下刪除的項目
SHARED_BACKUP = ".備份"         # _共用/ 底下被覆蓋的舊版
SHARED_STYLES = "文風"          # _共用/ 底下的文風庫
SHARED_STRUCTURES = "結構"      # _共用/ 底下的章節結構庫
SHARED_PREFS = "作者偏好.md"    # _共用/ 底下的共用作者偏好


# ---------------------------------------------------------------------------
# 檔名規則（使用者內容的名稱由呼叫端給；這裡只管格式）
# ---------------------------------------------------------------------------
VOLUME_PREFIX = "卷綱_第"                     # 正式卷綱檔名的開頭（掃描、比對用）
VOLUME_ONE_ALIASES = (OUTLINE + "/卷綱_第1卷.md", OUTLINE + "/卷一卷綱.md", OUTLINE + "/卷綱_第一卷.md")
SPAWN_VOLUME_ONE = VOLUMES_SUBDIR + "/卷綱_第一卷.md"
VOLUME_REVISION_PREFIX = "卷綱修訂"


def chapter_file(no, title):
    """正文／候選／反推章綱的檔名：第001章_標題.md"""
    return "第%03d章_%s.md" % (int(no), title)


def chapter_stub_file(no):
    """spawn 建書時的空白章綱：第001章_待填.md"""
    return "第%03d章_待填.md" % int(no)


def chapter_range_file(a, b, suffix):
    """跨章的報告檔：第001-010章_<suffix>.md"""
    return "第%03d-%03d章_%s.md" % (int(a), int(b), suffix)


def chapter_json(no):
    """.studio 底下逐章的紀錄檔：第001章.json"""
    return "第%03d章.json" % int(no)


def chapter_range_json(a, b):
    return "第%03d-%03d章.json" % (int(a), int(b))


def revision_draft(no):
    """修訂稿：.studio/修訂/第001章.draft.md"""
    return STUDIO_REVISIONS + "/第%03d章.draft.md" % int(no)


def revision_backup_file(no, stamp):
    return "修訂_第%03d章.%d.json" % (int(no), int(stamp))


def volume_file(no, base=OUTLINE):
    """卷綱：大綱/卷綱_第1卷.md（base 可換成草稿資料夾）"""
    return "%s/%s%s卷.md" % (base, VOLUME_PREFIX, no)


def volume_revision_file(no, base=VOLUME_DRAFTS):
    return "%s/%s_第%d卷.md" % (base, VOLUME_REVISION_PREFIX, int(no))


def volume_update_draft(a, b):
    """卷綱更新草稿：大綱/草稿/卷綱更新_第1-60章.md"""
    return VOLUME_DRAFTS + "/卷綱更新_第%d-%d章.md" % (int(a), int(b))


def entry(folder, name):
    """設定集／追蹤裡以名稱命名的檔案：entry(CHARACTERS, "林晚") → 設定/角色/林晚.md"""
    return "%s/%s.md" % (folder, name)


def health_report_file(stamp):
    return "全書健康檢查_%s.md" % stamp


def backup_name(tag, stem, stamp, ext="md"):
    """.studio/備份 裡的備份檔名：<tag>_<原檔名>.<時間>.md"""
    return "%s_%s.%d.%s" % (tag, stem, int(stamp), ext)


def import_backup_file(stem, stamp):
    """匯入覆蓋前的備份：匯入前_<原檔名>.<時間>.md"""
    return "匯入前_%s.%d.md" % (stem, int(stamp))


def rerun_backup_file(sub, stem, stamp):
    """流程重跑前的紀錄備份：重跑前<子資料夾>_<原檔名>.<時間>.json"""
    return "重跑前%s_%s.%d.json" % (sub, stem, int(stamp))


SPINOFF_SKELETON_JSON = "骨架.json"     # SPINOFF_DRAFTS 底下
SPINOFF_SKELETON_MD = "骨架.md"


def shared_style_file(name, stamp):
    return "文風_%s_%s.md" % (name, stamp)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def parts(rel):
    """相對路徑拆成各段（給 os.path.join(*parts(...)) 用）。"""
    return [p for p in rel.split("/") if p]


def path(book_dir, rel, *more):
    """書資料夾 + 相對路徑（+ 更多段）→ 實際路徑。和以前的 os.path.join(book_dir, "設定", "文風.md") 結果相同。"""
    return os.path.join(book_dir, *parts(rel), *more)


def all_constants():
    """{常數名: 值}；給檢查工具和移轉工具用。"""
    return {k: v for k, v in globals().items() if k.isupper() and isinstance(v, (str, tuple))}
