# -*- coding: utf-8 -*-
"""前後端共用的識別值（API 參數、回應的鍵、網址參數）。

v3 結構英文化 P2：這些識別值原本是中文（「設定」「章綱」「正文」…），而且常常直接拿資料夾名稱
來當 ID。現在一律改成英文，並和資料夾名稱脫鉤：
- 路徑看 studio/layout.py；這裡只管「叫什麼」，不管「放在哪」。
- 舊的中文 ID（以及 v2 的資料夾名稱）都登記成別名，進來時用 norm() 換成新 ID，
  所以舊書籤、瀏覽器存的設定、外部腳本照樣能用。
- 介面顯示的文字不在這裡：前端用自己的標籤表，再交給 i18n 翻譯。
"""
from . import layout

# ---------------------------------------------------------------------------
# 設定集分頁（/api/books/<id>/bible 的鍵、網址 bible?t=）
# 名稱刻意跟 v3 的資料夾名稱一致（bible/characters …），前端從路徑推分頁時不必另外對照。
# ---------------------------------------------------------------------------
BIBLE_TABS = ("characters", "factions", "world", "core", "structure", "drafts")
BIBLE_ENTITY_TABS = ("characters", "factions", "world")

# ---------------------------------------------------------------------------
# 反推草稿的分組（/reverse 系列 API 的 group 參數與回應的鍵）
# ---------------------------------------------------------------------------
REVERSE_GROUPS = ("bible", "outline", "cards", "tracking")

# ---------------------------------------------------------------------------
# 全文搜尋範圍（/search 的 scopes 參數、結果的 scope）
# ---------------------------------------------------------------------------
SEARCH_SCOPES = ("manuscript", "candidates", "outline", "bible", "tracking")

# ---------------------------------------------------------------------------
# 匯入目標（/import 的 target 參數與回應）
# ---------------------------------------------------------------------------
IMPORT_TARGETS = ("manuscript", "candidates")

# ---------------------------------------------------------------------------
# 共用庫分頁（網址 #/shared?t=）
# ---------------------------------------------------------------------------
SHARED_TABS = ("styles", "structures", "prefs")


def _leaf(rel):
    return layout.parts(rel)[-1]


# 舊 ID → 新 ID。舊 ID 包含 v2 的中文 ID，以及「拿資料夾名稱當 ID」時會出現的值。
ALIASES = {
    "bible_tab": {
        "角色": "characters", _leaf(layout.CHARACTERS): "characters",
        "勢力": "factions", _leaf(layout.FACTIONS): "factions",
        "世界觀": "world", _leaf(layout.WORLD): "world",
        "核心": "core",
        "章節結構": "structure", _leaf(layout.BIBLE_STRUCTURE): "structure",
        "草稿": "drafts", _leaf(layout.BIBLE_DRAFTS): "drafts",
    },
    "reverse_group": {
        "設定": "bible", layout.BIBLE: "bible",
        "大綱": "outline", layout.OUTLINE: "outline",
        "章綱": "cards",
        "追蹤": "tracking", layout.TRACKING: "tracking",
    },
    "search_scope": {
        "正文": "manuscript", layout.MANUSCRIPT: "manuscript",
        "候選": "candidates", layout.CANDIDATES: "candidates",
        "章綱": "outline",
        "設定": "bible", layout.BIBLE: "bible",
        "追蹤": "tracking", layout.TRACKING: "tracking",
    },
    "import_target": {
        "正文": "manuscript", layout.MANUSCRIPT: "manuscript",
        "候選": "candidates", layout.CANDIDATES: "candidates",
    },
    "shared_tab": {
        "文風": "styles", layout.SHARED_STYLES: "styles",
        "章節結構": "structures", layout.SHARED_STRUCTURES: "structures",
        "共用作者偏好": "prefs",
    },
}
VALID = {"bible_tab": BIBLE_TABS, "reverse_group": REVERSE_GROUPS,
         "search_scope": SEARCH_SCOPES, "import_target": IMPORT_TARGETS, "shared_tab": SHARED_TABS}


def norm(kind, value):
    """舊 ID／資料夾名稱 → 新 ID；已經是新 ID 就原樣回傳；認不得的也原樣回傳（交給呼叫端判斷）。"""
    if value is None:
        return None
    v = str(value).strip()
    if v in VALID[kind]:
        return v
    return ALIASES[kind].get(v, v)


def aliases_for_frontend():
    """給前端的別名表（舊網址、瀏覽器存的舊值換成新 ID 用）。"""
    return {k: dict(v) for k, v in ALIASES.items()}


# ---------------------------------------------------------------------------
# 和資料夾的對應（只在需要「由 ID 找資料夾」或反過來時用）
# ---------------------------------------------------------------------------
BIBLE_TAB_FOLDER = {"characters": layout.CHARACTERS, "factions": layout.FACTIONS,
                    "world": layout.WORLD, "drafts": layout.BIBLE_DRAFTS, "structure": layout.BIBLE_STRUCTURE}
REVERSE_GROUP_FOLDER = {"bible": layout.BIBLE, "outline": layout.OUTLINE, "tracking": layout.TRACKING}
IMPORT_TARGET_FOLDER = {"manuscript": layout.MANUSCRIPT, "candidates": layout.CANDIDATES}
