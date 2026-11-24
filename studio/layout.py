# -*- coding: utf-8 -*-
"""書的資料夾結構：所有系統定義的資料夾與檔名都集中在這裡。

v3 結構英文化（見專案文件「15_v3結構英文化規格」）：
程式其他地方不寫 "bible/style.md" 這類字串，一律引用這裡的常數。
P3 第二批起，資料夾與系統檔名是英文（v2 的中文名稱對照在 studio/migrate.py，移轉工具靠它認舊書）。
範本檔名（TPL_*）第七批起也是英文。

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
BIBLE = "bible"
OUTLINE = "outline"
MANUSCRIPT = "manuscript"
CANDIDATES = "candidates"
TRACKING = "tracking"
SAMPLES = "samples"
TEMPLATES = "_templates"
STUDIO = ".studio"
BOOK_META = "book.json"          # 書的身分證（格式版本、書名、語言）；各版都放在書的根目錄
SCHEMA_VERSION = 3               # 這版程式寫出的書的格式（v3：資料夾、檔名、frontmatter、標題、追蹤表都換好了）

# 書架與檔案瀏覽看得到的資料夾（順序就是顯示順序）
BROWSABLE = (BIBLE, OUTLINE, MANUSCRIPT, TRACKING, CANDIDATES, SAMPLES, TEMPLATES)

# ---------------------------------------------------------------------------
# 設定集
# ---------------------------------------------------------------------------
CHARACTERS = BIBLE + "/characters"
FACTIONS = BIBLE + "/factions"
WORLD = BIBLE + "/world"
BIBLE_DRAFTS = BIBLE + "/drafts"
BIBLE_MERGED = BIBLE + "/_merged"
BIBLE_STRUCTURE = BIBLE + "/structure"
VISUAL_CARDS = BIBLE + "/visual-cards"

STORY_CORE = BIBLE + "/story-core.md"
STYLE = BIBLE + "/style.md"
GLOSSARY = BIBLE + "/glossary.md"
AUTHOR_PREFS = BIBLE + "/author-prefs.md"
BIBLE_INDEX = BIBLE + "/_index.md"
STYLE_FINGERPRINT = BIBLE + "/style-fingerprint.json"
STRUCTURE_DNA = BIBLE + "/structure-dna.json"
CONTRACT = BIBLE + "/continuation-contract.md"
BOOK_STRUCTURE = BIBLE_STRUCTURE + "/structure.md"

# ---------------------------------------------------------------------------
# 大綱
# ---------------------------------------------------------------------------
CHAPTER_CARDS = OUTLINE + "/chapters"
REVERSE_CARDS = CHAPTER_CARDS + "/_reverse"
VOLUME_DRAFTS = OUTLINE + "/drafts"
VOLUMES_SUBDIR = OUTLINE + "/volumes"          # 正式卷綱都放這層：vol-01.md（作者自己加的「幕」是 act-01.md）
BOOK_OUTLINE = OUTLINE + "/book.md"

# ---------------------------------------------------------------------------
# 追蹤
# ---------------------------------------------------------------------------
SUMMARIES = TRACKING + "/summaries"
CHARACTER_STATES = TRACKING + "/characters"
FORESHADOWING = TRACKING + "/foreshadowing.md"
TIMELINE = TRACKING + "/timeline.md"
STATE_CARD = TRACKING + "/state-card.md"
READER_KNOWLEDGE = TRACKING + "/reader-knowledge.md"
RELATIONS = TRACKING + "/relations.md"
READER_KNOWLEDGE_DRAFT = TRACKING + "/reader-knowledge.draft.md"
RELATIONS_DRAFT = TRACKING + "/relations.draft.md"

# ---------------------------------------------------------------------------
# 候選
# ---------------------------------------------------------------------------
SPINOFF_DRAFTS = CANDIDATES + "/spinoff"

# ---------------------------------------------------------------------------
# 範本
# ---------------------------------------------------------------------------
PROJECT_RULES = TEMPLATES + "/project-rules.md"

# ---------------------------------------------------------------------------
# .studio（工作台內部資料）
# ---------------------------------------------------------------------------
STUDIO_BACKUP = STUDIO + "/backup"
STUDIO_REVISIONS = STUDIO + "/revisions"
STUDIO_PIPELINE = STUDIO + "/pipeline"
STUDIO_PIPELINE_CURRENT = STUDIO_PIPELINE + "/current.json"
STUDIO_PIPELINE_SNAPSHOTS = STUDIO_PIPELINE + "/snapshots"
STUDIO_REVIEWS = STUDIO + "/reviews"
STUDIO_REVIEW = STUDIO + "/review"
STUDIO_CHECK = STUDIO + "/goal-check"
STUDIO_TRASH = STUDIO + "/trash"
STUDIO_RECALL_INDEX = STUDIO + "/index/recall.json"
STUDIO_REVERSE = STUDIO + "/reverse"
STUDIO_FIDELITY = STUDIO + "/fidelity"
STUDIO_WRITEBACK_CHECK = STUDIO + "/writeback-check"
STUDIO_RECOVERY = STUDIO + "/recovery"
STUDIO_EXPORT_PREFS = STUDIO + "/export-settings.json"
MIGRATE_DIR = STUDIO + "/migrate"              # 移轉工具的備份與報告（各版同名，移轉時不搬動）
MIGRATE_BACKUP_PREFIX = "pre-v3_"              # 移轉前的整本備份：.studio/migrate/pre-v3_YYYYMMDD-HHMMSS.zip
PIPELINE_CURRENT_FILE = "current.json"            # 流程狀態檔名（放在 STUDIO_PIPELINE 底下）
REVERSE_CUMULATIVE = "cumulative.json"               # 反推的累積結果（放在 STUDIO_REVERSE 底下）
REVERSE_DRAFTS = "drafts"                        # STUDIO_REVERSE 底下：反推出來、還沒採用的草稿
REVERSE_BATCHES = "batches"                       # STUDIO_REVERSE 底下：逐批抽取結果

# ---------------------------------------------------------------------------
# 書的第一層：插圖、匯出
# ---------------------------------------------------------------------------
ILLUST = "illust"
ILLUST_COVER = "cover"                         # ILLUST 底下：封面
ILLUST_CHAPTERS = "chapters"                   # ILLUST 底下：各章（裡面一章一個資料夾）
ILLUST_INDEX = "_illustrations.json"                    # ILLUST 底下
ART_STYLE = "art-style.json"                        # ILLUST 底下
EXPORT = "export"

# ---------------------------------------------------------------------------
# 範本檔名（plugin*/skills/novel-setup/templates/ 與書內 _範本/ 共用同一組檔名）
# ---------------------------------------------------------------------------
TEMPLATES_IN_SKILLS = "novel-setup/templates"   # 相對於 plugin*/skills/
TPL_STORY_CORE = "story-core.md"
TPL_STYLE = "style.md"
TPL_GLOSSARY = "glossary.md"
TPL_AUTHOR_PREFS = "author-prefs.md"
TPL_BOOK_OUTLINE = "book-outline.md"
TPL_VOLUME_OUTLINE = "volume-outline.md"
TPL_CHAPTER_CARD = "chapter-card.md"
TPL_STATE_CARD = "state-card.md"
TPL_FORESHADOWING = "foreshadowing.md"
TPL_TIMELINE = "timeline.md"
TPL_CHARACTER = "character.md"
TPL_FACTION = "faction.md"
TPL_WORLD = "world.md"
TPL_READER_KNOWLEDGE = "reader-knowledge.md"
TPL_RELATIONS = "relations.md"
TPL_CHAPTER_SUMMARY = "chapter-summary.md"
TPL_CHARACTER_STATE = "character-state.md"
TPL_PROJECT_RULES = "project-rules.md"     # 書內 _templates/ 才有（從 references/project-layout.md 複製）

# ---------------------------------------------------------------------------
# 書庫層級（_shared）
# ---------------------------------------------------------------------------
SHARED = "_shared"                # 書庫第一層的共用資料夾（不是書）
SHARED_TRASH = ".trash"          # _shared/ 底下刪除的項目
SHARED_BACKUP = ".backup"         # _shared/ 底下被覆蓋的舊版
SHARED_STYLES = "styles"          # _shared/ 底下的文風庫
SHARED_STRUCTURES = "structures"      # _shared/ 底下的章節結構庫
SHARED_PREFS = "author-prefs.md"    # _shared/ 底下的共用作者偏好


# ---------------------------------------------------------------------------
# 檔名規則（使用者內容的名稱由呼叫端給；這裡只管格式）
# ---------------------------------------------------------------------------
VOLUME_STEM = "vol-%02d"                      # 卷綱：vol-01（卷號 2 位數，100 卷以上自然變 3 位）
ACT_STEM = "act-%02d"                         # 「幕」：act-01（一卷裡再分的段落；卷末承諾以卷為準）
VOLUME_REVISION_SUFFIX = ".revision.md"       # 既有卷的修訂草稿：outline/drafts/vol-01.revision.md
VOLUME_UPDATE_PREFIX = "volume-update_"       # 卷末體檢的卷綱更新草稿：outline/drafts/volume-update_ch-0001-0060.md
OUTLINE_VOLUME_ONE = VOLUMES_SUBDIR + "/" + VOLUME_STEM % 1 + ".md"      # 第一卷（開新書、spawn、設定流程用）

# 建書時「活檔」的範本：目的地 → 範本檔名（v3 起兩邊的檔名不一樣，不能再用同名對應）
LIVE_TEMPLATES = {
    STORY_CORE: TPL_STORY_CORE, STYLE: TPL_STYLE, AUTHOR_PREFS: TPL_AUTHOR_PREFS, GLOSSARY: TPL_GLOSSARY,
    BOOK_OUTLINE: TPL_BOOK_OUTLINE, STATE_CARD: TPL_STATE_CARD, FORESHADOWING: TPL_FORESHADOWING, TIMELINE: TPL_TIMELINE,
    READER_KNOWLEDGE: TPL_READER_KNOWLEDGE, RELATIONS: TPL_RELATIONS, OUTLINE_VOLUME_ONE: TPL_VOLUME_OUTLINE,
}


CHAPTER_STEM = "ch-%04d"     # 逐章檔案的名稱：ch-0001（章號 4 位數；章名不放檔名，見 project.chapter_title）


def chapter_stem(no):
    """逐章資料夾的名稱（插圖、流程快照）：ch-0001"""
    return CHAPTER_STEM % int(no)


def chapter_md(no):
    """正文、候選、章綱、章節摘要的檔名：ch-0001.md"""
    return chapter_stem(no) + ".md"


def chapter_range_file(a, b, suffix):
    """跨章的報告檔：ch-0001-0010_<suffix>.md"""
    return "ch-%04d-%04d_%s.md" % (int(a), int(b), suffix)


def chapter_json(no):
    """.studio 底下逐章的紀錄檔：ch-0001.json"""
    return chapter_stem(no) + ".json"


def chapter_range_json(a, b):
    return "ch-%04d-%04d.json" % (int(a), int(b))


def revision_draft(no):
    """修訂稿：.studio/revisions/ch-0001.draft.md"""
    return STUDIO_REVISIONS + "/" + chapter_stem(no) + ".draft.md"


def revision_backup_file(no, stamp):
    return "revision_%s.%d.json" % (chapter_stem(no), int(stamp))


def volume_stem(no):
    return VOLUME_STEM % int(no)


def volume_file(no, base=VOLUMES_SUBDIR):
    """卷綱：outline/volumes/vol-01.md（base 可換成草稿資料夾：outline/drafts/vol-01.md）"""
    return "%s/%s.md" % (base, volume_stem(no))


def volume_revision_file(no, base=VOLUME_DRAFTS):
    """既有卷的修訂草稿：outline/drafts/vol-01.revision.md"""
    return "%s/%s%s" % (base, volume_stem(no), VOLUME_REVISION_SUFFIX)


def volume_update_draft(a, b):
    """卷末體檢的卷綱更新草稿：outline/drafts/volume-update_ch-0001-0060.md"""
    return VOLUME_DRAFTS + "/%sch-%04d-%04d.md" % (VOLUME_UPDATE_PREFIX, int(a), int(b))


def entry(folder, name):
    """設定集／追蹤裡以名稱命名的檔案：entry(CHARACTERS, "林晚") → 設定/角色/林晚.md"""
    return "%s/%s.md" % (folder, name)


def health_report_file(stamp):
    return "全書健康檢查_%s.md" % stamp


def backup_name(tag, stem, stamp, ext="md"):
    """.studio/backup 裡的備份檔名：<tag>_<原檔名>.<時間>.md"""
    return "%s_%s.%d.%s" % (tag, stem, int(stamp), ext)


def import_backup_file(stem, stamp):
    """匯入覆蓋前的備份：匯入前_<原檔名>.<時間>.md"""
    return "匯入前_%s.%d.md" % (stem, int(stamp))


def rerun_backup_file(sub, stem, stamp):
    """流程重跑前的紀錄備份：重跑前<子資料夾>_<原檔名>.<時間>.json"""
    return "重跑前%s_%s.%d.json" % (sub, stem, int(stamp))


SPINOFF_SKELETON_JSON = "skeleton.json"     # SPINOFF_DRAFTS 底下
SPINOFF_SKELETON_MD = "skeleton.md"


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
