# -*- coding: utf-8 -*-
"""風格指紋、結構 DNA、衍生新書骨架這三種 JSON 的鍵（v3：英文）。

程式內部與檔案一律英文鍵；舊檔（P4d 以前寫的）與模型偶爾回的中文鍵，
讀進來時經 to_en() 換成英文。每種檔一張表：同一個中文字在不同檔可能是不同意思
（例如「章數」在指紋裡是章節總數 count，在骨架的卷綱裡是那一卷的章數 chapter_count）。

文字指標（對白比例、平均句長…）在工作台其他地方仍是中文鍵（文風檔、style_loop），
所以只在這三種檔的邊界換：metrics_en() 寫出前換成英文 ID，metrics_zh() 交回文風那一套。
"""

# 文字指標：中文名稱 ↔ 英文 ID
METRICS = {
    "對白比例": "dialogue_ratio",
    "平均句長": "avg_sentence_length",
    "短句比例": "short_sentence_ratio",
    "長句比例": "long_sentence_ratio",
    "平均段長": "avg_paragraph_length",
    "單句成段": "single_sentence_paragraphs",
    "每千字逗號": "commas_per_1k",
    "每千字刪節號": "ellipses_per_1k",
    "每千字破折號": "dashes_per_1k",
    "每千字驚嘆號": "exclamations_per_1k",
    "每千字的": "de_per_1k",
    "每千字地": "di_per_1k",
    "每千字AI味信號": "ai_signals_per_1k",
}
METRICS_ZH = {v: k for k, v in METRICS.items()}

FINGERPRINT = {
    "版本": "version", "語言": "lang", "章節": "chapters", "文字指標": "metrics",
    "指標來源": "metrics_source", "代表句": "exemplars", "說明": "note",
    # chapters
    "章數": "count", "總字數": "total_length", "平均章長": "mean", "中位章長": "median",
    "最短章長": "min", "最長章長": "max", "章長變異": "cv",
}

DNA = {
    "版本": "version", "語言": "lang", "視角": "pov", "章節": "chapters", "對白": "dialogue",
    "段落": "paragraphs", "章長曲線": "length_curve", "排除": "excluded", "說明": "note",
    # pov
    "人稱": "person", "依據": "basis",
    # chapters
    "章數": "count", "平均": "mean", "最短": "min", "最長": "max", "變異": "cv",
    "最長/最短": "max_min_ratio",  # literal-ok: 舊檔的鍵（不是路徑）
    # dialogue
    "比例": "ratio", "章間變異": "chapter_cv",
}

SKELETON = {
    "書名建議": "title_suggestion", "一句話前提": "premise", "賣點": "selling_points",
    "主角": "protagonists", "名字": "name", "定位": "role", "動機": "motive", "弱點": "weakness",
    "世界觀要點": "world_points", "語感說明": "voice_note",
    "卷綱": "volumes", "卷": "volume", "名稱": "title", "章數": "chapter_count",
    "主線": "main_line", "卷末狀態": "end_state",
    "骨架來源": "source", "護欄": "guard", "撞到名字": "name_hits", "禁用名單數": "banned_count",
    "語言": "lang",
}

# 結構 DNA「排除」清單的值
EXCLUDED = {"人名": "names", "地名": "places", "專有名詞": "proper_nouns", "事件序列": "event_order"}

# 這些位置底下是文字指標，鍵要用 METRICS 換
_METRIC_PARENTS = {"文字指標", "metrics", "段落", "paragraphs"}


def _conv(obj, table, parent=None):
    if isinstance(obj, dict):
        out = {}
        metric = parent in _METRIC_PARENTS
        for k, v in obj.items():
            nk = METRICS.get(k, k) if metric else table.get(k, k)
            if nk in out:            # 同一欄英文、中文都寫了：先出現的為準
                continue
            out[nk] = _conv(v, table, k)
        return out
    if isinstance(obj, list):
        if parent in ("排除", "excluded"):
            return [EXCLUDED.get(x, x) if isinstance(x, str) else x for x in obj]
        return [_conv(x, table, parent) for x in obj]
    return obj


def to_en(obj, table):
    """舊檔或模型輸出 → 英文鍵（已經是英文的原樣）。"""
    return _conv(obj, table)


def has_cjk_key(obj):
    """還有中文鍵嗎（給移轉工具判斷要不要轉）。"""
    if isinstance(obj, dict):
        return any(any("぀" <= ch <= "鿿" for ch in str(k)) or has_cjk_key(v)
                   for k, v in obj.items())
    if isinstance(obj, list):
        return any(has_cjk_key(x) for x in obj)
    return False


def metrics_en(m):
    return {METRICS.get(k, k): v for k, v in (m or {}).items()}


def metrics_zh(m):
    return {METRICS_ZH.get(k, k): v for k, v in (m or {}).items()}


TABLES = {"fingerprint": FINGERPRINT, "dna": DNA, "skeleton": SKELETON}
