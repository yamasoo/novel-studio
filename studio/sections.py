# -*- coding: utf-8 -*-
"""Markdown 段落標題的固定 ID 與三語顯示字（v3 規格第 8 節）。

檔案裡的 `## 標題` 依書的語言寫；程式用段落 ID 找段落，三種語言（以及 v2 的中文寫法、別名）都認得。
作者自己加的段落認不得就原樣保留，不參與解析。

  label(doc, sid, lang)   寫出用的標題（WRITE 控制寫出語言）
  id_of(doc, heading)     標題 → 段落 ID；doc=None 時查全部文件類型（只取不撞名的）
  find(body, doc, sid)    取出該段內文（不含標題行）；找不到回 ""
  head_rx(doc, sid)       比對標題文字的正規式片段（含編號前綴，例如「1. 」）

文件類型用 frontmatter `type` 的英文 ID（character、chapter-card…）。
"""
import re

# 寫出段落標題用哪個語言："book" 依書的語言；"zh-TW" 一律繁中（v3 P3 5b 起依書的語言）
WRITE = "book"

LANGS = ("zh-TW", "en", "ja")

# doc → [(sid, 繁中, English, 日本語, (其他別名…))]
DOCS = {
    "character": [
        ("one_line", "一句話", "One line", "ひとこと", ()),
        ("outer", "外在", "Outer", "外面", ()),
        ("inner", "內在", "Inner", "内面", ()),
        ("voice", "說話方式（聲音卡）", "Voice card", "話し方（ボイスカード）", ("說話方式", "聲音卡")),
        ("relationships", "關係", "Relationships", "関係", ("關係",)),
        ("arc", "角色弧線", "Character arc", "キャラクターアーク", ()),
        ("notes", "備註", "Notes", "備考", ()),
    ],
    "faction": [
        ("one_line", "一句話", "One line", "ひとこと", ()),
        ("basics", "基本資料", "Basics", "基本情報", ()),
        ("goals", "目標與利益", "Goals and interests", "目的と利害", ()),
        ("internal_rules", "內部規矩", "Internal rules", "内部の掟", ()),
        ("attitude_to_protagonist", "對主角的態度", "Attitude toward the protagonist", "主人公への態度", ()),
        ("aliases", "別名", "Aliases", "別名", ()),
        ("history", "沿革", "History", "沿革", ()),
        ("sub_units", "內部編組", "Internal units", "内部の編成", ()),
        ("author_check", "需要作者確認", "For the author to confirm", "作者の確認が必要", ()),
        ("notes", "備註", "Notes", "備考", ()),
    ],
    "world": [
        ("one_line", "一句話", "One line", "ひとこと", ()),
        ("rules", "規則", "Rules", "ルール", ()),
        ("costs_limits", "代價與限制", "Costs and limits", "代償と制約", ()),
        ("reader_learns_when", "讀者何時知道", "When the reader learns it", "読者が知る時期", ()),
        ("plot_relevance", "與劇情的關係", "Relevance to the plot", "物語との関わり", ()),
        ("rules_limits", "規則與限制", "Rules and limits", "ルールと制約", ()),
        ("traits", "特性", "Traits", "特性", ()),
        ("origin", "來歷", "Origin", "由来", ()),
        ("story_role", "在故事中的作用", "Role in the story", "物語での役割", ()),
        ("current_state", "目前狀態", "Current state", "現在の状態", ()),
        ("limits_costs", "限制與代價", "Limits and costs", "制約と代償", ()),
        ("notes", "備註", "Notes", "備考", ()),
    ],
    "story-core": [
        ("hook", "一句話鉤子", "One-line hook", "ひとことフック", ()),
        ("genre", "題材與定位", "Genre and positioning", "ジャンルと位置づけ", ()),
        ("selling_points", "賣點（讀者為什麼看）", "Selling points", "売り（読者が読む理由）", ("賣點",)),
        ("protagonist", "主角", "Protagonist", "主人公", ()),
        ("world", "世界觀", "World", "世界観", ()),
        ("story_engine", "故事引擎", "Story engine", "物語のエンジン", ()),
        ("core_conflict", "核心衝突", "Core conflict", "中心の対立", ()),
        ("reader_contract", "讀者契約", "Reader contract", "読者との約束", ()),
        ("endgame", "終局方向", "Endgame", "結末の方向", ()),
        ("escalation_steps", "升級台階", "Escalation steps", "エスカレーションの段階", ()),
        ("notes", "備註", "Notes", "備考", ()),
    ],
    "style": [
        ("positioning", "定位與參考", "Positioning and references", "位置づけと参考", ()),
        ("basics", "基本設定", "Basics", "基本設定", ()),
        ("diction", "用詞與語域", "Diction and register", "語彙と文体の格", ()),
        ("sentence_rhythm", "句子與節奏", "Sentences and rhythm", "文とリズム", ()),
        ("paragraph_layout", "段落與版面", "Paragraphs and layout", "段落と組版", ()),
        ("description", "描寫與感官", "Description and the senses", "描写と感覚", ()),
        ("imagery", "修辭與意象", "Figures and imagery", "修辞とイメージ", ()),
        ("dialogue", "對白", "Dialogue", "台詞", ()),
        ("emotion", "情緒寫法", "Writing emotion", "感情の書き方", ()),
        ("scene_transition", "場景與轉場", "Scenes and transitions", "場面と転換", ()),
        ("serial", "章節與連載", "Chapters and serialization", "章と連載", ()),
        ("do", "建議做法", "Do", "推奨", ()),
        ("dont", "本書禁忌", "Don't", "この本の禁止事項", ("禁忌",)),
        ("exceptions", "允許的例外", "Allowed exceptions", "許される例外", ()),
        ("sample", "範例段落", "Sample passage", "見本の段落", ()),
        ("metrics", "文字指標（程式統計）", "Text metrics (computed)", "文章の指標（プログラム集計）", ()),
    ],
    "chapter-card": [
        ("four_questions", "本章四問", "Four questions", "この章の四つの問い", ()),
        ("function_emotion", "本章功能與目標情緒", "Function and target emotion", "章の役割と狙う感情", ()),
        ("plot_points", "情節點", "Plot points", "プロットポイント", ()),
        ("cast", "出場角色", "Characters on stage", "登場人物", ()),
        ("foreshadowing_ops", "伏筆操作", "Foreshadowing moves", "伏線の操作", ()),
        ("donts", "禁止事項", "Don'ts", "禁止事項", ("禁止事项",)),
        ("ending_hook", "章末鉤子", "Ending hook", "章末の引き", ("篇章鉤子",)),
        ("notes", "備註", "Notes", "備考", ()),
    ],
    "volume-outline": [
        ("contract", "卷契約", "Volume contract", "巻の約束", ()),
        ("standing_rules", "本卷常駐規則", "Standing rules", "この巻の常設ルール", ()),
        ("summary", "本卷摘要", "Volume summary", "この巻の要約", ()),
        ("units", "劇情單元", "Plot units", "プロットユニット", ()),
        ("emotion_curve", "情緒曲線", "Emotional curve", "感情曲線", ()),
        ("character_arcs", "人物弧線", "Character arcs", "人物のアーク", ()),
        ("foreshadowing", "本卷伏筆", "Foreshadowing in this volume", "この巻の伏線", ()),
        ("notes", "備註", "Notes", "備考", ()),
    ],
    "book-outline": [
        ("overview", "總覽", "Overview", "全体像", ()),
        ("volumes", "分卷", "Volumes", "巻構成", ()),
        ("main_foreshadowing", "主線伏筆總規劃", "Main-line foreshadowing plan", "主筋の伏線計画", ()),
        ("subplots", "感情線／支線規劃", "Romance and subplot plan", "感情線・サブプロット計画", ()),
        ("notes", "備註", "Notes", "備考", ()),
    ],
    "chapter-summary": [
        ("what_happened", "發生了什麼", "What happened", "何が起きたか", ()),
        ("situation_change", "局面變化", "How the situation changed", "局面の変化", ()),
        ("new_elements", "新出現的人事物", "New people, places and things", "新たに登場したもの", ()),
        ("ends_on", "結尾停在", "Ends on", "終わり方", ()),
    ],
    "state-card": [
        ("current_position", "目前位置", "Where we are", "現在地", ()),
        ("main_progress", "主線進度", "Main-line progress", "主筋の進行", ()),
        ("present_characters", "在場角色", "Characters present", "場にいる人物", ()),
        ("next_chapter_promises", "下一章承諾", "Promises for the next chapter", "次章への約束", ()),
        ("long_term_constraints", "長期約束", "Long-term constraints", "長期の制約", ()),
        ("continuity_risks", "連續性風險", "Continuity risks", "連続性のリスク", ()),
        ("active_foreshadowing", "活躍伏筆", "Active foreshadowing", "進行中の伏線", ()),
    ],
    # 角色狀態是「- 欄位：值」列點，不是 ## 段落；欄位名稱一樣依語言
    "character-state": [
        ("identity", "身分", "Identity", "身分", ()),
        ("location", "位置", "Location", "居場所", ()),
        ("goal", "目標", "Goal", "目標", ()),
        ("physical_state", "身體狀態", "Physical state", "身体の状態", ()),
        ("emotional_state", "情緒狀態", "Emotional state", "心の状態", ()),
        ("abilities_resources", "能力與資源", "Abilities and resources", "能力と手持ち", ()),
        ("relationship_changes", "關係變化", "Relationship changes", "関係の変化", ("關係の変化",)),
        ("known_secrets", "知道的秘密", "Secrets known", "知っている秘密", ()),
        ("unfinished_business", "未了結的事", "Unfinished business", "未解決のこと", ()),
    ],
    # 不分文件類型、工作台自己加的段落
    "common": [
        ("illust_prompt", "繪圖提示", "Illustration prompt", "作画プロンプト", ()),
        ("rev_unmerged", "從正文反推（未併入，請核對）", "From the manuscript (not merged; please check)",
         "本文からの逆算（未統合・要確認）", ()),
    ],
}

# 文件的 `# 標題`（H1）。{name}、{title}、{n} 是變數。
TITLES = {
    "state-card": ("狀態卡", "State card", "状態カード"),
    "foreshadowing": ("伏筆總表", "Foreshadowing", "伏線一覧"),
    "timeline": ("時間線", "Timeline", "年表"),
    "reader-knowledge": ("讀者認知", "Reader knowledge", "読者の認識"),
    "relations": ("角色關係", "Character relations", "人物関係"),
    "glossary": ("名詞表", "Glossary", "用語集"),
    "author-prefs": ("作者偏好", "Author preferences", "作者の好み"),
    "book-outline": ("全書大綱", "Book outline", "全体プロット"),
    "story-core": ("故事核心", "Story core", "物語の核"),
    "style": ("本書文風", "Style of this book", "この本の文体"),
    "volume-outline": ("卷綱：{title}", "Volume outline: {title}", "巻プロット：{title}"),
    "character-state": ("{name}：目前狀態", "{name}: current state", "{name}：現在の状態"),
    "chapter": ("第{n}章 {title}", "Chapter {n}: {title}", "第{n}章 {title}"),
}

NONE = {"zh-TW": "（無）", "en": "(none)", "ja": "（なし）"}


def title(doc, lang=None, **kw):
    t = TITLES[doc][{"zh-TW": 0, "en": 1, "ja": 2}[write_lang(lang)]]
    return t.format(**kw) if kw else t


def none(lang=None):
    return NONE[write_lang(lang)]


# 帶編號的標題（### 第N卷：卷名、### 單元N：名稱（第a～b章））
VOLUME_HEAD = {"zh-TW": "第%s卷：%s", "en": "Volume %s: %s", "ja": "第%s巻：%s"}
UNIT_HEAD = {"zh-TW": "單元%s：%s（%s）", "en": "Unit %s: %s (%s)", "ja": "ユニット%s：%s（%s）"}
UNIT_RANGE = {"zh-TW": "第%d～%d章", "en": "ch. %d–%d", "ja": "第%d～%d章"}

_NUM = re.compile(r"^\s*(?:[0-9０-９]+|[一二三四五六七八九十]+)\s*[.．、:：)）]\s*")


def _norm(s):
    s = _NUM.sub("", str(s or "")).strip().strip("*").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def _rows(doc):
    return DOCS.get(doc) or []


def _labels(row):
    sid, zh, en, ja, extra = row
    return (zh, en, ja) + tuple(extra)


def write_lang(lang):
    """寫出段落標題、固定標籤要用的語言（WRITE 不是 "book" 時一律繁中）。"""
    lang = lang if WRITE == "book" else WRITE
    return lang if lang in LANGS else "zh-TW"


def label(doc, sid, lang=None):
    """寫出用的標題。WRITE 不是 "book" 時一律繁中。"""
    lang = write_lang(lang)
    for row in _rows(doc) + _rows("common"):
        if row[0] == sid:
            i = {"zh-TW": 1, "en": 2, "ja": 3}.get(lang, 1)
            return row[i]
    raise KeyError((doc, sid))


def labels(doc, sid):
    """這個段落所有認得的標題寫法。doc 是 None 或不認得的類型時，收集所有文件類型裡同一個 ID 的寫法。"""
    if doc in DOCS:
        for row in _rows(doc) + _rows("common"):
            if row[0] == sid:
                return _labels(row)
    out = []
    for rows in DOCS.values():
        for row in rows:
            if row[0] == sid:
                out += [x for x in _labels(row) if x not in out]
    if not out:
        raise KeyError((doc, sid))
    return tuple(out)


_GLOBAL = None


def _global():
    """標題 → ID（跨文件類型）；同一個寫法對到兩個不同 ID 的不收。"""
    global _GLOBAL
    if _GLOBAL is None:
        seen = {}
        for doc, rows in DOCS.items():
            for row in rows:
                for lab in _labels(row):
                    seen.setdefault(_norm(lab), set()).add(row[0])
        _GLOBAL = {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}
    return _GLOBAL


def id_of(doc, heading):
    key = _norm(heading)
    if not key:
        return None
    if doc is None:
        return _global().get(key)
    for row in _rows(doc) + _rows("common"):
        if key in {_norm(x) for x in _labels(row)}:
            return row[0]
    return None


def head_rx(doc, sid):
    """比對標題文字（不含 ## ）的正規式：可有編號前綴、尾端空白；英文不分大小寫由呼叫端加 (?i)。"""
    alts = sorted({re.escape(x) for x in labels(doc, sid)}, key=len, reverse=True)
    return r"(?:[0-9０-９一二三四五六七八九十]+\s*[.．、:：)）]\s*)?(?:%s)" % "|".join(alts)


def find(body, doc, sid, level=2):
    """取出 `## <該段標題>` 到下一個同層或更高層標題之間的內文；找不到回 ""。"""
    hashes = "#" * level
    rx = re.compile(r"(?mi)^%s[ \t]*%s[ \t]*$\n?(.*?)(?=^#{1,%d}[ \t]|\Z)" % (hashes, head_rx(doc, sid), level), re.S)
    m = rx.search(body or "")
    return m.group(1) if m else ""


def has(body, doc, sid, level=2):
    hashes = "#" * level
    return bool(re.search(r"(?mi)^%s[ \t]*%s[ \t]*$" % (hashes, head_rx(doc, sid)), body or ""))


def fields(doc, lang=None):
    """[(sid, 寫出用標籤)]，給角色狀態這種列點欄位用。"""
    return [(row[0], label(doc, row[0], lang)) for row in _rows(doc)]


def field_id(doc, name):
    return id_of(doc, name)


# ---------------------------------------------------------------------------
# 範本裡的列點欄位（- 想要：…）。三語範本逐行對齊抽出來的；冒號另外處理。
# ---------------------------------------------------------------------------
FIELDS = {
    "character": [
        ("年齡／身分", "Age / status", "年齢／身分"), ("外貌辨識點", "Distinguishing looks", "目立つ外見"),
        ("想要", "Wants", "望み"), ("害怕", "Fears", "恐れ"), ("缺陷", "Flaw", "欠点"),
        ("底線", "Bottom line", "譲れない線"), ("秘密", "Secret", "秘密"),
        ("慣用句式", "Habitual sentence patterns", "よく使う言い回し"), ("口頭禪", "Catchphrase", "口癖"),
        ("被逼急時的反應", "Reaction when pushed", "追い詰められたときの反応"),
        ("怎麼對上位者、平輩、下位者說話", "How they talk to superiors, equals and subordinates", "目上・同等・目下への話し方"),
    ],
    "faction": [
        ("規模與地盤", "Size and territory", "規模と勢力範囲"), ("首領", "Leader", "指導者"),
        ("主要成員", "Main members", "主な構成員"), ("資源與手段", "Resources and methods", "資源と手段"),
        ("想要什麼", "What it wants", "求めるもの"), ("和誰有衝突", "Who it is in conflict with", "対立する相手"),
        ("和誰有合作", "Who it cooperates with", "協力する相手"),
    ],
    "story-core": [
        ("題材", "Genre", "ジャンル"), ("目標讀者", "Target readers", "想定読者"),
        ("發表平台與更新節奏", "Platform and update rhythm", "掲載先と更新ペース"), ("預計篇幅", "Expected length", "想定の分量"),
        ("敘事視角", "Viewpoint", "視点"), ("想要什麼（外在目標）", "What they want (outer goal)", "外側の目標（何をしたいか）"),
        ("真正需要什麼（內在成長）", "What they really need (inner growth)", "内側の課題（本当に必要なもの）"),
        ("最大的缺陷或限制", "Biggest flaw or limit", "最大の欠点や限界"),
        ("金手指／特殊優勢（有的話）", "Special advantage (if any)", "特別な強み（あれば）"),
        ("主要對手", "Main opponent", "主な敵"), ("衝突根源", "Root of the conflict", "対立の根"),
    ],
    "book-outline": [
        ("預計卷數與字數", "Expected volumes and length", "想定する巻数と分量"), ("主線一句話", "Main line in one sentence", "本筋を一文で"),
        ("終局", "Ending", "結末"), ("篇幅", "Length", "分量"), ("本卷目標", "Volume goal", "この巻の目標"),
        ("主要對手", "Main opponent", "主な敵"), ("卷末變化", "Change by the end of the volume", "巻末までの変化"),
        ("卷末大高潮", "Big climax at the end", "巻末の大きな山場"),
        ("本卷埋下、留給後面的東西", "What is planted here for later", "後に向けて仕込むこと"),
        ("卷綱", "Volume outline", "巻プロット"),
    ],
    "volume-outline": [
        ("本卷賣點", "Selling point of this volume", "この巻の売り"), ("主角本卷目標", "The lead's goal this volume", "この巻での主人公の目標"),
        ("本卷對手", "Opponent this volume", "この巻の敵"), ("卷末兌現", "Payoff at the end", "巻末のカタルシス"),
        ("卷末新鉤子", "New hook at the end", "巻末の新しい引き"), ("起點局面", "Starting situation", "出発点の状況"),
        ("衝突", "Conflict", "葛藤"), ("小高潮", "Small climax", "小さな山場"), ("結果與代價", "Result and cost", "結果と代償"),
        ("埋下的伏筆", "Foreshadowing planted", "仕込む伏線"),
    ],
    "chapter-card": [
        ("主角這章想做什麼", "What the lead wants to do in this chapter", "主人公はこの章で何をしようとするか"),
        ("誰或什麼阻止他", "Who or what stops them", "それを妨げるのは誰か、何か"),
        ("這章結束後局面變成什麼", "What the situation is after this chapter", "この章の後、状況はどうなっているか"),
        ("讀者為什麼還要往下看", "Why the reader will keep reading", "読者が先を読みたくなる理由"),
        ("功能", "Function", "役割"), ("讀者看完的主要感受", "Main feeling for the reader", "読者に起こしたい主な感情"),
        ("類型", "Type", "種類"), ("停在", "Stops on", "止める場所"),
    ],
}
_LI = {"zh-TW": 0, "en": 1, "ja": 2}


def _field_rows(doc):
    if doc == "character-state":
        return [(r[1], r[2], r[3]) + tuple(r[4]) for r in DOCS["character-state"]]
    return FIELDS.get(doc) or []


def _field_label(doc, lab, lang):
    for row in _field_rows(doc):
        if lab in row or lab.lower() in {x.lower() for x in row}:
            return row[_LI[lang]]
    return None


_VOL_ZH = re.compile(r"^第\s*([0-9〇零一二兩三四五六七八九十百]+)\s*[卷巻]\s*[：:]\s*(.*)$")
_VOL_EN = re.compile(r"^Volume\s+([0-9]+)\s*:\s*(.*)$", re.I)
_UNIT_ZH = re.compile(r"^單元\s*([0-9一二三四五六七八九十百]+)\s*[：:]\s*(.*?)\s*（(.*)）\s*$")
_UNIT_JA = re.compile(r"^ユニット\s*([0-9一二三四五六七八九十百]+)\s*[：:]\s*(.*?)\s*（(.*)）\s*$")
_UNIT_EN = re.compile(r"^Unit\s+([0-9]+)\s*:\s*(.*?)\s*\((.*)\)\s*$", re.I)
_RANGE_ZH = re.compile(r"^第\s*0*([0-9]+)\s*[～~\-－–—]\s*(?:第\s*)?0*([0-9]+)\s*章$")
_RANGE_EN = re.compile(r"^ch(?:apters?|s?\.)?\s*0*([0-9]+)\s*[–\-~]\s*0*([0-9]+)$", re.I)
_CN = "零一二三四五六七八九"


def _int(s):
    s = str(s).strip()
    if s.isdigit():
        return int(s)
    from . import fmkeys
    return fmkeys.volume_int("第%s卷" % s)


def _range(s, lang):
    m = _RANGE_ZH.match(s.strip()) or _RANGE_EN.match(s.strip())
    if not m:
        return s
    a, b = int(m.group(1)), int(m.group(2))
    if lang == "en":
        return "ch. %d–%d" % (a, b)
    return "第%03d～%03d章" % (a, b) if re.search(r"第0\d", s) else "第%d～%d章" % (a, b)


def _num(src, n, lang):
    """卷號、單元號：中文、日文保留原本的寫法（一／1），英文一律阿拉伯數字。"""
    if lang == "en":
        return str(n) if n is not None else src
    return src if not src.isdigit() or n is None else src


def _h3(text, lang):
    """### 卷、單元標題換語言；已經是目標語言的寫法就不動（範圍、編號照作者寫的）。"""
    own = {"zh-TW": (lambda t: bool(_UNIT_ZH.match(t)) or bool(re.match(r"^第[^：:]*卷", t))),
           "ja": (lambda t: bool(_UNIT_JA.match(t)) or bool(re.match(r"^第[^：:]*巻", t))),
           "en": (lambda t: bool(_UNIT_EN.match(t) or _VOL_EN.match(t)))}[lang]
    if own(text):
        return None
    m = _VOL_ZH.match(text) or _VOL_EN.match(text)
    if m:
        src, rest = m.group(1), m.group(2)
        n = _int(src)
        if n is None:
            return None
        num = _num(src, n, lang)
        return {"zh-TW": "第%s卷：%s", "en": "Volume %s: %s", "ja": "第%s巻：%s"}[lang] % (num, rest)
    m = _UNIT_ZH.match(text) or _UNIT_JA.match(text) or _UNIT_EN.match(text)
    if m:
        src, name, rng = m.group(1), m.group(2), m.group(3)
        n = _int(src)
        num = _num(src, n, lang)
        return UNIT_HEAD[lang] % (num, name, _range(rng, lang))
    return None


_TITLE_PAT = None


def _h1(doc, text, lang):
    for key, row in TITLES.items():
        for i, t in enumerate(row):
            if "{" not in t:
                if text == t:
                    return row[_LI[lang]]
                continue
            rx = "^" + re.escape(t).replace(r"\{title\}", "(?P<title>.*)").replace(r"\{name\}", "(?P<name>.*?)") \
                .replace(r"\{n\}", "(?P<n>[0-9]+|\\{N\\})") + "$"
            m = re.match(rx, text)
            if m:
                return row[_LI[lang]].format(**m.groupdict())
    return None


def localize(text, doc, lang):
    """把範本認得的段落標題、列點欄位、文件標題換成 lang 的寫法；其他內容（作者寫的、值、註解）不動。

    給兩個地方用：程式自己組的文件寫出前（照 WRITE 決定語言），以及移轉工具轉換英文、日文書。
    """
    lang = write_lang(lang)
    if not text:
        return text
    m = re.match(r"(?s)^---\n.*?\n---[ \t]*\n", text)
    head, body = (text[:m.end()], text[m.end():]) if m else ("", text)
    out, fence = [], False
    for line in body.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
            out.append(line)
            continue
        if fence:
            out.append(line)
            continue
        out.append(_loc_line(line, doc, lang))
    return head + "\n".join(out)


_NUM_PREFIX = re.compile(r"^((?:[0-9０-９]+|[一二三四五六七八九十]+)\s*[.．、]\s*)?(.*?)\s*$")


def _loc_line(line, doc, lang):
    m = re.match(r"^(#{1,3})[ \t]+(.*?)[ \t]*$", line)
    if m:
        level, text = len(m.group(1)), m.group(2)
        if level == 1:
            new = _h1(doc, text, lang)
            return "# " + new if new is not None else line
        if level == 2:
            nm = _NUM_PREFIX.match(text)
            pre, core = nm.group(1) or "", nm.group(2)
            sid = id_of(doc, core)
            if sid is None or _already(doc, sid, core, lang):
                return line
            return "## " + pre + _label_in(doc, sid, lang)
        new = _h3(text, lang)
        return "### " + new if new is not None else line
    m = re.match(r"^(\s*(?:[-*]|\d+\.)\s*)([^：:\n<]{1,60}?)\s*(：|:)([ \t]*)(.*)$", line)
    if m and _field_rows(doc):
        pre, lab, sep, sp, rest = m.groups()
        new = _field_label(doc, lab.strip(), lang)
        if new is None or new == lab.strip():
            return line
        if lang == "en":
            sp = sp or (" " if rest else "")
            sep = ":"
        else:
            if sep == ":" and sp == " ":
                sp = ""             # 英文的「: 」換成全形冒號時拿掉那一格
            sep = "："
        return pre + new + sep + sp + rest
    return line


def _already(doc, sid, core, lang):
    """標題已經是目標語言的寫法（繁中含別名）就不動，免得改到作者的用字。"""
    for row in _rows(doc) + _rows("common"):
        if row[0] == sid:
            if core == row[_LI[lang] + 1]:
                return True
            return lang == "zh-TW" and core in row[4]
    return False


def _label_in(doc, sid, lang):
    for row in _rows(doc) + _rows("common"):
        if row[0] == sid:
            return row[_LI[lang] + 1]
    return sid


def localize_doc(text, lang):
    """依 frontmatter 的 type 決定文件類型再 localize；沒有 type 的原樣。"""
    m = re.match(r"(?s)^---\n(.*?)\n---", text or "")
    if not m:
        return text
    t = re.search(r"(?m)^(?:type|類型)\s*[:：]\s*(\S+)", m.group(1))
    if not t:
        return text
    from . import fmkeys
    doc = fmkeys.value_en("type", t.group(1))
    if doc not in DOCS and doc not in FIELDS and doc not in TITLES:
        return text
    return localize(text, doc, lang)
