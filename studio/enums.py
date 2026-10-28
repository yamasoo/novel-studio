# -*- coding: utf-8 -*-
"""列舉值容錯：模型寫的英文、日文（或中文的近似寫法）換回檔案裡用的中文固定詞。

norm(kind, value) → 中文固定詞；認不得回傳 None（呼叫端原樣使用，並在任務紀錄提醒一次）。
比對時不分大小寫，去掉空白、底線、連字號與引號。
display(kind, lang) → 給英文、日文提示詞用的選項文字（例如 "protagonist|main supporting|supporting|antagonist"）。
"""
import re

# kind → [(中文固定詞, [同義詞……])]；同義詞的第一個英文、第一個日文是提示詞裡顯示的寫法
TABLES = {
    "role": [
        ("主角", ["protagonist", "main character", "lead", "hero", "heroine", "主人公", "主役"]),
        ("主要配角", ["main supporting", "major supporting", "deuteragonist", "主要な脇役", "メイン", "準主役", "主要脇役"]),
        ("配角", ["supporting", "supporting character", "secondary", "脇役", "サブ"]),
        ("反派", ["antagonist", "villain", "敵役", "悪役", "敵"]),
        ("路人", ["minor", "extra", "background", "モブ", "端役", "通行人"]),
    ],
    "importance": [
        ("主要", ["major", "main", "主要", "メイン"]),
        ("次要", ["minor", "secondary", "サブ", "副次", "準"]),
        ("路人", ["extra", "background", "passerby", "モブ", "通行人"]),
    ],
    "fs_status": [
        ("已埋", ["planted", "set up", "仕込み済み", "仕込み", "埋め済み"]),
        ("推進中", ["developing", "in progress", "advancing", "ongoing", "進行中", "展開中"]),
        ("已回收", ["paid off", "resolved", "payoff", "closed", "回収済み", "回収"]),
        ("廢棄", ["dropped", "abandoned", "discarded", "破棄", "廃棄", "放棄"]),
    ],
    "level": [
        ("高", ["high", "高"]), ("中", ["medium", "mid", "middle", "中"]), ("低", ["low", "低"]),
    ],
    # 讀者認知的類型＋新登場的類型（回寫的 new_entities）：值不重疊，放同一張表
    "type": [
        ("已知", ["known", "既知"]),
        ("懸念", ["question", "suspense", "mystery", "open question", "謎", "懸念"]),
        ("誤認", ["misbelief", "misdirection", "misconception", "false belief", "誤認", "思い込み"]),
        ("角色", ["character", "person", "人物", "キャラクター", "キャラ"]),
        ("勢力", ["faction", "organization", "group", "組織"]),
        ("名詞", ["term", "glossary", "用語"]),
        ("地點", ["place", "location", "場所", "地名"]),
        ("物品", ["item", "object", "thing", "アイテム", "物"]),
        ("規則", ["rule", "ルール", "規則"]),
    ],
    # 伏筆的動作、讀者認知的動作、回收比對的動作
    "action": [
        ("埋", ["plant", "planted", "set up", "仕込み", "仕込む"]),
        ("推進", ["advance", "develop", "progress", "進展", "前進"]),
        ("回收", ["pay off", "payoff", "resolve", "resolved", "reveal", "回収"]),
        ("新", ["new", "新規", "新しい"]),
        ("部分", ["partial", "partly", "partially", "一部"]),
        ("合併", ["merge", "merged", "統合", "併合"]),
    ],
    "term_cat": [
        ("地點", ["place", "location", "場所", "地名"]),
        ("組織", ["organization", "organisation", "faction", "group", "組織", "団体"]),
        ("物品", ["item", "object", "thing", "物", "アイテム", "道具"]),
        ("能力與技術", ["ability and technology", "ability", "technology", "technique", "skill", "能力と技術", "能力", "技術"]),
        ("制度與習俗", ["institution and custom", "institution", "custom", "system", "制度と習俗", "制度", "習俗", "慣習"]),
        ("生物", ["creature", "species", "animal", "plant", "生き物", "生物"]),
        ("事件", ["event", "incident", "出来事", "事件"]),
        ("稱謂", ["title", "form of address", "honorific", "rank", "称号", "呼称", "敬称"]),
        ("人物", ["person", "character", "人物", "キャラクター"]),
        ("其他", ["other", "misc", "その他"]),
    ],
    "handling": [
        ("保留", ["keep", "retain", "残す", "保持"]),
        ("刪除", ["delete", "remove", "drop", "削除"]),
        ("人物", ["person", "character", "人物"]),
    ],
    "change_to": [
        ("人物", ["person", "character", "人物"]),
        ("物品", ["item", "object", "物", "アイテム"]),
        ("其他", ["other", "その他"]),
    ],
    "world_cat": [
        ("力量體系", ["power system", "magic system", "力の体系", "能力体系"]),
        ("地理與氣候", ["geography and climate", "geography", "climate", "地理と気候", "地理"]),
        ("歷史與年表", ["history and chronology", "history", "chronology", "timeline", "歴史と年表", "歴史"]),
        ("社會與政治", ["society and politics", "society", "politics", "社会と政治", "社会", "政治"]),
        ("經濟與物資", ["economy and resources", "economy", "goods", "経済と物資", "経済"]),
        ("宗教信仰", ["religion and beliefs", "religion", "faith", "宗教と信仰", "宗教"]),
        ("文化與風俗", ["culture and customs", "culture", "customs", "文化と風俗", "文化"]),
        ("科技原理", ["technology and science", "technology", "science", "科学技術", "技術原理"]),
        ("載具與兵器", ["vehicles and weapons", "vehicles", "weapons", "ships", "乗り物と兵器", "兵器"]),
        ("生態與資源", ["ecology and resources", "ecology", "natural resources", "生態と資源", "生態"]),
        ("其他", ["other", "その他"]),
    ],
    # 審查（review_schema）
    "severity": [
        ("必須修", ["must fix", "must", "critical", "必ず直す", "必修正", "要修正"]),
        ("建議修", ["should fix", "should", "suggested", "recommended", "直した方がよい", "直したほうがよい", "推奨"]),
        ("提醒", ["note", "notice", "reminder", "minor", "注意", "メモ"]),
    ],
    "review_cat": [
        ("劇情邏輯", ["plot logic", "plot", "logic", "筋の論理", "プロット"]),
        ("人物", ["character", "characters", "人物"]),
        ("情緒關係", ["emotion and relationships", "emotion", "relationships", "感情と関係", "感情"]),
        ("身體資訊", ["physical and information state", "physical state", "continuity", "身体と情報", "身体"]),
        ("轉場", ["transitions", "transition", "場面転換", "転換"]),
        ("章末", ["chapter ending", "ending", "章末", "章の終わり"]),
        ("設定", ["setting", "worldbuilding", "設定"]),
        ("資訊邊界", ["information boundary", "spoiler", "情報の境界"]),
        ("文字", ["prose", "wording", "style", "文章", "文体"]),
    ],
}

TABLES["term_big"] = TABLES["term_cat"]      # 名詞整理的「大類」和抽取的「類別」用同一組

_NEW_ID = ("新", "new", "新規", "新しい")


def _k(s):
    return re.sub(r"[\s_\-－「」『』\"'“”‘’]", "", str(s or "")).lower()


_INDEX = {}
for _kind, _rows in TABLES.items():
    _idx = {}
    for _zh, _syn in _rows:
        _idx.setdefault(_k(_zh), _zh)
    for _zh, _syn in _rows:          # 中文固定詞優先，同義詞在後（避免「人物」被別的列搶走）
        for s in _syn:
            _idx.setdefault(_k(s), _zh)
    _INDEX[_kind] = _idx


def norm(kind, value):
    """回傳中文固定詞；認不得回傳 None。kind="id"：只把「新」的各種寫法換成「新」，其他編號原樣。
    值裡有「|」（模型把選項整串抄回來）時取第一個認得的。"""
    if value is None:
        return None
    s = str(value)
    if kind == "id":
        return "新" if _k(s) in {_k(x) for x in _NEW_ID} else s
    idx = _INDEX.get(kind)
    if idx is None:
        return s
    if not s.strip():
        return s
    hit = idx.get(_k(s))
    if hit:
        return hit
    if "|" in s or "／" in s or "/" in s:
        for part in re.split(r"[|／/]", s):
            hit = idx.get(_k(part))
            if hit:
                return hit
    return None


def show(kind, value, lang):
    """把檔案裡的中文固定詞換成英文、日文的顯示寫法（給模型看的資料用）；繁中或認不得就原樣。"""
    if lang == "zh-TW":
        return value
    for zh, syn in TABLES.get(kind, []):
        if zh == value:
            if lang == "en":
                return next((s for s in syn if re.match(r"[A-Za-z]", s)), value)
            return next((s for s in syn if not re.match(r"[A-Za-z]", s)), value)
    return value


def display(kind, lang, sep="|"):
    """提示詞裡給模型挑的選項（英文用第一個英文同義詞、日文用第一個含假名或漢字的同義詞；繁中用中文固定詞）。"""
    out = []
    for zh, syn in TABLES[kind]:
        if lang == "en":
            pick = next((s for s in syn if re.match(r"[A-Za-z]", s)), zh)
        elif lang == "ja":
            pick = next((s for s in syn if not re.match(r"[A-Za-z]", s)), zh)
        else:
            pick = zh
        out.append(pick)
    return sep.join(out)
