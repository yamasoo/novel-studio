#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小説本文チェックツール（日本語）。

チェック項目：
  1. 約物の統一（半角の句読点・！？、西洋式の引用符、「…」の個数、ダッシュ、カギ括弧の対応）→ 必須修（--fix-punct で自動修正できるもの）
  2. 工房の言葉の漏れ（第N章・伏線・章綱……）→ 建議修
  3. AI 臭のシグナル（決まり文句、型、章末の昇華・予告、定型の反応）→ 提醒。同じ章に積み重なると 建議修
  4. 文末の重複、文頭の重複、短文の連続、文の長さの揃いすぎ、長すぎる文、ダッシュの密度、呼称の揺れ → 提醒／建議修
  5. 表記ゆれ、段落頭の字下げの混在、全角・半角の混在 → 提醒
  6. 文字数の統計（ルビ記法や空白・改行を除く）

使い方：
  python3 check_text.py 正文/第001章_題名.md
  python3 check_text.py 正文/
  python3 check_text.py 正文/第001章_題名.md --fix-punct
  python3 check_text.py 正文/第001章_題名.md --json
  python3 check_text.py 正文/第001章_題名.md --count

ホワイトリスト：
  書籍フォルダ（正文/ の一つ上）の `.去AI味白名單` に、原文の断片を一行ずつ書く。`#` で始まる行は注釈。
  断片を含む行は、語彙と AI 臭のチェックを飛ばす（約物は引き続きチェックする）。

標準ライブラリのみ、Python 3.8 以上。
終了コード：0 = 必ず直す項目なし、1 = 必ず直す項目あり、2 = 引数かファイルの誤り。
結果の形・JSON のキー・等級名（必須修／建議修／提醒）は、中国語版・英語版と同じです。
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

JP = r"[぀-ヿ㐀-䶿一-鿿豈-﫿ｦ-ﾟ]"
JP_RE = re.compile(JP)

# ---------------------------------------------------------------------------
# AI 臭のシグナル：(類別, 正規表現)
# ---------------------------------------------------------------------------
AI_SIGNALS = [
    ("否定の型", r"(?:は|が)?[^。、「」\n]{1,15}ではなく、[^。「」\n]{1,25}(?:だった|である|だ|のだった|のだ|であった)"),
    ("否定の型", r"単なる[^。、「」\n]{1,12}では(?:ない|なかった)"),
    ("心情の告知", r"(?:胸|心)(?:が|を)(?:締め付け|締めつけ|打た|揺さぶ|ざわつ)"),
    ("心情の告知", r"(?:不安|恐怖|怒り|悲しみ|喜び|寂しさ|切なさ)が(?:胸|心)に?(?:広が|込み上げ|押し寄せ|満ち)"),
    ("心情の告知", r"(?:感情|想い|思い)が(?:溢れ|あふれ|込み上げ)"),
    ("定型の表情", r"口元(?:が|を)(?:緩|歪|綻|引き結)|目(?:を|が)(?:見開|細め|伏せ)|眉(?:を|間に)(?:ひそめ|寄せ)|唇を噛|拳を(?:握り|握りしめ)|苦笑を(?:浮かべ|漏らし)|微笑(?:み|を)(?:を)?浮かべ|瞳(?:が|に)(?:揺れ|宿)|ごくりと"),
    ("定型の表情", r"(?:息|唾)を(?:呑|飲)(?:ん|み込ん)"),
    ("定型の身体反応", r"背筋(?:が|に)(?:凍|寒|ぞくり|冷た)|心臓が(?:跳ね|高鳴|早鐘|ドクン)|鼓動が(?:早|速)|全身(?:が|に)(?:震え|鳥肌)|血の気が引|冷や汗"),
    ("万能の副詞", r"ふと|思わず|どこか|わずかに|かすかに|ほのかに|ゆっくりと|そっと|ぼんやりと"),
    ("説明の結論", r"ようやく(?:理解|気づ|悟っ)|(?:ことを|のを)(?:理解|悟|痛感)した|それは[^。]{1,20}(?:ということ|という意味)|つまり|要するに"),
    ("予告・昇華", r"運命の(?:歯車|糸|悪戯)|まだ知らなかった|知る由もなかった|この時の[^。]{1,10}は|これが[^。]{1,10}の始まり|物語は(?:まだ)?始まったばかり|すべてが変わ(?:った|る)|新たな(?:一歩|物語|章)"),
    ("意義の膨張", r"かけがえのない|何物にも代えがたい|計り知れない|筆舌に尽くし|言葉にできない"),
    ("万能の比喩", r"まるで[^。]{1,25}(?:のようだった|のように|かのよう)|さながら|時が止まった|世界が(?:止まっ|色を失|静止)|時間が止まっ|嵐の前の静けさ"),
    ("定型の反応", r"言葉を失|絶句|目を丸く|唖然|呆然|固まっ|凍りつ|沈黙が(?:落ち|流れ|支配|場を)|静寂が(?:訪れ|包|満ち|落ち)|場が(?:静まり|凍り)|空気が(?:凍|張り詰|重く)|しばらく(?:の間)?(?:黙|沈黙)"),
    ("硬い説明調", r"という名の|と言えるだろう|と言えよう|ではないだろうか|に(?:他|ほか)ならない|において|に関して"),
    ("発話の修飾", r"(?:静かに|低い声で|冷たく|淡々と|ぽつりと)(?:言|告げ|呟|答え)"),
    ("説明の語尾", r"のだった|わけだった|のである"),
    ("定番の名前", r"リリア|セレナ|エリシア|アリシア|ルミナ|ノクス|ヴァルド|レイナ|ミリア"),
]

# 同じ類別が一章にこの回数以上出たら「建議修」に上げる
CATEGORY_LIMIT = {
    "万能の副詞": 10, "定型の表情": 4, "定型の身体反応": 3, "心情の告知": 3, "否定の型": 3,
    "説明の結論": 3, "万能の比喩": 3, "意義の膨張": 2, "予告・昇華": 2, "定型の反応": 4,
    "硬い説明調": 3, "発話の修飾": 4, "説明の語尾": 6, "定番の名前": 1,
}
CATEGORY_HINT = {
    "否定の型": "結論を先に言い、具体的な理由を一つ添える",
    "心情の告知": "行動・物・避ける仕草で見せる",
    "定型の表情": "場面を動かす動作を一つだけ残す",
    "定型の身体反応": "この人物ならではの反応に置き換えるか、一度きりにする",
    "万能の副詞": "動詞がすでに言っているなら削る。曖昧さが狙いなら残す",
    "説明の結論": "読者に推測させる。分からなければ拍を直す",
    "予告・昇華": "具体的な像・行動・台詞で止める",
    "意義の膨張": "出来事に重みを運ばせる",
    "万能の比喩": "視点人物の暮らしから引いた比喩にするか、削る",
    "定型の反応": "削るか、言われたことへの人物の行動に置き換える",
    "硬い説明調": "地の文の硬さを文風に合わせ、平易な言い方にする",
    "発話の修飾": "「言った」にして、様子は仕草の一文に移す",
    "説明の語尾": "事実は言い切る。「〜のだった」を重ねない",
    "定番の名前": "この作品の世界に合った名前にする",
}

# 節奏と密度
BURST_LEN, BURST_RUN = 8, 4          # 8 字以下の文が 4 つ以上連続 → 短文の連続
UNIFORM_RUN, UNIFORM_SPREAD, UNIFORM_MIN = 6, 0.2, 18   # 6 文の長さの差が平均の 2 割未満（平均 18 字以上）
LONG_SENT = 120                      # 一文が 120 字を超えたら提醒
DASH_PER = 500                       # 地の文で 500 字あたり 1 回を超えたら建議修
ALIAS_FORMS = 4
PHRASE_REPEAT = 3
DIALOGUE = re.compile(r"「[^「」]*」|『[^『』]*』")

ENGINEERING_WORDS = r"第[一二三四五六七八九十百千零〇\d]+章|前の章|次の章|この章|伏線|章綱|大綱|細綱|読者"

# 表記ゆれ：同じ章で両方が使われたら提醒
VARIANT_PAIRS = [
    ("行う", "行なう"), ("明らか", "明かに"), ("終わる", "終る"), ("表れ", "現れ"),
    ("出来る", "できる"), ("一緒", "一諸"), ("分かる", "判る"), ("気付", "気づ"),
    ("いっぱい", "一杯"), ("ありがとう", "有難う"), ("だんだん", "段々"), ("たくさん", "沢山"),
    ("ください", "下さい"), ("ほとんど", "殆ど"), ("ちょっと", "一寸"), ("とても", "とっても"),
    ("おはよう", "お早う"), ("すごい", "凄い"),
]


def _jlen(s):
    return len(JP_RE.findall(s))


def load_whitelist(book_root):
    items = []
    if not book_root:
        return items
    path = os.path.join(book_root, ".去AI味白名單")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.strip() and not line.lstrip().startswith("#"):
                    items.append(line.strip())
    return items


def parse_banned(text, source=""):
    """「## 禁用詞」の節を読む。各行「- 語 → 提案」、/.../ は正規表現。[(regex, 表示, 提案)] を返す。"""
    out = []
    m = re.search(r"(?ms)^##+\s*禁用詞[^\n]*\n(.*?)(?=^##\s|\Z)", text or "")
    if not m:
        return out
    sec = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S)
    for line in sec.split("\n"):
        s = line.strip()
        if not s.startswith(("-", "*")):
            continue
        s = s[1:].strip()
        if not s:
            continue
        parts = re.split(r"\s*(?:→|->)\s*", s, maxsplit=1)
        word, hint = parts[0], (parts[1] if len(parts) > 1 else "")
        word = word.strip().strip("「」")
        if not word:
            continue
        if len(word) > 2 and word.startswith("/") and word.endswith("/"):
            try:
                rx = re.compile(word[1:-1])
            except re.error:
                continue
            show = word[1:-1]
        else:
            rx = re.compile(re.escape(word))
            show = word
        out.append((rx, show, (hint.strip() or "作者が禁用に指定した語") + ("（%s）" % source if source else "")))
    return out


def load_banned(book_root):
    items = []
    if not book_root:
        return items
    for path, src in ((os.path.join(book_root, "設定", "作者偏好.md"), "この本の作者偏好"),
                      (os.path.join(os.path.dirname(os.path.abspath(book_root)), "_共用", "作者偏好.md"), "共通の作者偏好")):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                items += parse_banned(f.read(), src)
    return items


def load_aliases(book_root):
    """設定/角色/*.md の名前と別名。{名前: [名前, 別名…]} を返す。"""
    out = {}
    d = os.path.join(book_root or "", "設定", "角色")
    if not book_root or not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not f.endswith(".md"):
            continue
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                text = fh.read(3000)
        except OSError:
            continue
        m = re.match(r"---\n(.*?)\n---", text, re.S)
        fm = m.group(1) if m else ""
        name = (re.search(r"(?m)^名稱:\s*(.+)$", fm) or [None, os.path.splitext(f)[0]])[1].strip()
        al = []
        am = re.search(r"(?m)^別名:\s*\[(.*)\]\s*$", fm)
        if am:
            al = [x.strip().strip("'\"") for x in am.group(1).split(",")]
        else:
            bm = re.search(r"(?ms)^別名:\s*\n((?:\s*-\s*.+\n?)+)", fm)
            if bm:
                al = [x.strip()[1:].strip().strip("'\"") for x in bm.group(1).strip().split("\n")]
        forms = [x for x in dict.fromkeys([name] + al) if x and len(x) >= 2]
        if len(forms) >= 2:
            out[name] = forms
    return out


def _sentences(narr):
    return [x for x in re.split(r"[。！？!?]+[」』）]?|……+[」』）]?", narr) if _jlen(x)]


def _ending(s):
    """文末の型を返す。"""
    s = s.strip().rstrip("」』）)…―　 ")
    if not s:
        return ""
    if s.endswith("た"):
        return "た"
    return s[-2:] if len(s) >= 2 else s


def rhythm_findings(body_lines, aliases):
    """節奏と密度。body_lines：[(行番号, 文)]（見出しと注釈は除く）。[(等級, 類型, 行, 断片, 提案)] を返す。"""
    out = []
    sents = []          # (行番号, 地の文の一文)。会話だけの行は (行番号, None) で区切りになる
    narr_text = []
    for ln, line in body_lines:
        s = line.strip()
        narr = DIALOGUE.sub("", s)
        narr_text.append(narr)
        if s.startswith(("「", "『")) and _jlen(narr) < 4:
            sents.append((ln, None))
            continue
        for x in _sentences(narr):
            sents.append((ln, x))
    # 短文の連続
    run, bursts = [], []
    for ln, x in sents + [(0, None)]:
        if x is not None and _jlen(x) <= BURST_LEN:
            run.append((ln, x))
            continue
        if len(run) >= BURST_RUN:
            bursts.append(run)
        run = []
    if bursts:
        out.append(("提醒", "節奏：短文の連続", bursts[0][0][0],
                    "%d か所、%s 行目（例：%s）" % (len(bursts), "、".join(str(b[0][0]) for b in bursts[:8]),
                                                 "。".join(x for _, x in bursts[0][:5])[:40]),
                    "極端に短い文を並べて勢いを作っている。最も効く一、二文を残し、あとは完全な文に戻す（文風が許すなら無視してよい）"))
    # 文の長さの揃いすぎ
    ns = [(ln, _jlen(x)) for ln, x in sents if x is not None]
    i, hits = 0, []
    while i + UNIFORM_RUN <= len(ns):
        w = [n for _, n in ns[i:i + UNIFORM_RUN]]
        mean = sum(w) / len(w)
        if mean >= UNIFORM_MIN and (max(w) - min(w)) <= mean * UNIFORM_SPREAD:
            hits.append(ns[i][0])
            i += UNIFORM_RUN
        else:
            i += 1
    if hits:
        out.append(("提醒", "節奏：文の長さが揃いすぎ", hits[0], "%d か所、%s 行目" % (len(hits), "、".join(str(x) for x in hits[:8])),
                    "長さの近い文が続くと機械が並べたように読める。長短を散らす"))
    # 長すぎる文
    longs = [(ln, x) for ln, x in sents if x is not None and _jlen(x) > LONG_SENT]
    if longs:
        out.append(("提醒", "節奏：一文が長い", longs[0][0], "%d か所、%s 行目（%d 字超）" % (len(longs), "、".join(str(l[0]) for l in longs[:8]), LONG_SENT),
                    "読点でつないだ長い文は、意味の切れ目で二文に分けると読みやすい（文風が長文を求めるなら無視）"))
    # 文末の重複
    ends = [(ln, _ending(x)) for ln, x in sents if x is not None]
    run, eruns = [], []
    for ln, e in ends + [(0, None)]:
        if run and e is not None and ((e == "た" and run[0][1] == "た") or (e != "た" and e == run[0][1])):
            run.append((ln, e))
            continue
        need = 6 if run and run[0][1] == "た" else 3
        if len(run) >= need:
            eruns.append(run)
        run = [(ln, e)] if e is not None else []
    if eruns:
        out.append(("提醒", "節奏：文末が同じ型で続く", eruns[0][0][0],
                    "%d か所、%s 行目（「…%s。」が%d文連続）" % (len(eruns), "、".join(str(r[0][0]) for r in eruns[:8]), eruns[0][0][1], len(eruns[0])),
                    "体言止め・倒置・会話・現在形の挿入などで文末を変える（変化のためだけに文を崩さない）"))
    if len(ends) >= 15:
        ta = sum(1 for _, e in ends if e == "た")
        if ta / len(ends) >= 0.85:
            out.append(("提醒", "節奏：文末がほぼ「〜た。」", 0, "%d 文中 %d 文（%d%%）" % (len(ends), ta, 100 * ta // len(ends)),
                        "過去形の羅列は単調になりやすい。状況を述べる文や体言止めを混ぜる"))
    # 文頭の重複
    heads = [(ln, x.strip()[:2]) for ln, x in sents if x is not None and len(x.strip()) >= 2]
    run, hruns = [], []
    for ln, h in heads + [(0, None)]:
        if run and h == run[0][1]:
            run.append((ln, h))
            continue
        if len(run) >= 4 and re.match(JP, run[0][1] or ""):
            hruns.append(run)
        run = [(ln, h)] if h else []
    if hruns:
        out.append(("提醒", "節奏：文頭が同じで続く", hruns[0][0][0],
                    "%d か所、%s 行目（「%s…」が%d文連続）" % (len(hruns), "、".join(str(r[0][0]) for r in hruns[:8]), hruns[0][0][1], len(hruns[0])),
                    "主語を省く、語順を変える、動作から始めるなどで文頭を散らす"))
    # ダッシュの密度（地の文のみ）
    narr_all = "\n".join(narr_text)
    n_jp = _jlen(narr_all)
    dashes = len(re.findall(r"――|——|―", narr_all))
    if n_jp >= 1000 and dashes > n_jp / DASH_PER:
        out.append(("建議修", "節奏：ダッシュが多い", 0, "地の文に %d 回（約 %d 字に一回）" % (dashes, n_jp // max(dashes, 1)),
                    "地の文のダッシュは %d 字に一回までが目安。多くは読点・句点・文の分割で置き換えられる" % DASH_PER))
    # 呼称の揺れ
    full = "\n".join(l for _, l in body_lines)
    for name, forms in (aliases or {}).items():
        used = []
        rest = full
        for f in sorted(forms, key=len, reverse=True):
            c = rest.count(f)
            if c:
                rest = rest.replace(f, "\0")
            if c >= 2:
                used.append("%s×%d" % (f, c))
        if len(used) >= ALIAS_FORMS:
            out.append(("提醒", "節奏：呼称が多すぎる", 0, "%s：%s" % (name, "、".join(used)),
                        "同じ人物を何通りにも呼ぶと、同一人物か迷う。一、二通りに固定し、あとは代名詞や省略で"))
    return out


def guess_book_root(path):
    p = os.path.abspath(path)
    d = p if os.path.isdir(p) else os.path.dirname(p)
    while True:
        if os.path.basename(d) == "正文":
            return os.path.dirname(d)
        if os.path.isfile(os.path.join(d, "CLAUDE.md")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def strip_frontmatter(lines):
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return i + 1
    return 0


def _plain(text):
    """見出し、注釈、ルビ記法を除いた本文。"""
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"[|｜]", "", body)                 # ルビの開始記号
    body = re.sub(r"《[^》\n]*》", "", body)             # ルビ本体（《かな》）
    body = re.sub(r"《《([^》\n]*)》》", r"\1", body)    # 傍点記法は本文として数える
    return body


def count_chars(text):
    """(文字数, 空白・改行を除く総文字数)。ルビ記法・見出し・注釈は数えない。"""
    body = _plain(text)
    return _jlen(body) + len(re.findall(r"[A-Za-z0-9０-９Ａ-Ｚａ-ｚ]", body)) + len(re.findall(r"[、。！？「」『』（）…―ー・]", body)), len(re.sub(r"\s", "", body))


def fix_punct(text):
    n = 0

    def sub(pattern, repl, s, flags=0):
        nonlocal n
        s2, k = re.subn(pattern, repl, s, flags=flags)
        n += k
        return s2

    # 引用符 → 「」『』
    text = sub("“", "「", text)
    text = sub("”", "」", text)
    text = sub("‘", "『", text)
    text = sub("’(?=[^A-Za-z])", "』", text)
    out_lines = []
    for line in text.split("\n"):
        if '"' in line and JP_RE.search(line):
            parts = line.split('"')
            rebuilt = parts[0]
            for k, p in enumerate(parts[1:]):
                rebuilt += ("「" if k % 2 == 0 else "」") + p
                n += 1
            line = rebuilt
        out_lines.append(line)
    text = "\n".join(out_lines)
    # 三点リーダー：「…」は偶数個の「……」に
    text = sub(r"(?<!…)…(?!…)", "……", text)
    text = sub(r"(?<!…)…{3}(?!…)", "……", text)
    text = sub(r"\.{3,}|・{3,}|。{3,}", "……", text)
    # ダッシュ：「―」「—」の連なりを「――」に
    text = sub(r"(?<=" + JP + r")[—―]{1,3}(?=" + JP + r"|「|」|『|』)", "――", text)
    text = sub(r"(?<=" + JP + r")--(?=" + JP + r")", "――", text)
    # 半角の句読点・記号が日本語に隣接
    for h, fwd in {",": "、", "!": "！", "?": "？"}.items():
        text = sub(r"(?<=" + JP + r")" + re.escape(h), fwd, text)
        text = sub(re.escape(h) + r"(?=" + JP + r")", fwd, text)
    text = sub(r"(?<=" + JP + r")\.(?=\s|$|" + JP + r"|」)", "。", text, flags=re.M)
    return text, n


def punct_findings(lines, start):
    """約物の誤り。[(行番号, 断片, 提案)] を返す。"""
    out = []
    seen = set()

    def add(ln, snip, hint):
        if hint not in seen:
            seen.add(hint)
            out.append((ln, snip.strip()[:40], hint))

    for i in range(start, len(lines)):
        line = lines[i]
        ln = i + 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.search("[“”‘’]", line) or ('"' in line and JP_RE.search(line)):
            add(ln, line, "西洋式の引用符は「」『』に統一する（--fix-punct で自動修正）")
        if re.search(r"(?<=" + JP + r")[,!?]|[,!?](?=" + JP + r")", line):
            add(ln, line, "半角の「,」「!」「?」が日本語に隣接している（--fix-punct で自動修正）")
        if re.search(r"(?<!…)…(?!…)|\.{3,}|・{3,}|(?<!…)…{3}(?!…)", line):
            add(ln, line, "三点リーダーは「……」（偶数個）にそろえる（--fix-punct で自動修正）")
        if re.search(r"(?<!―)―(?!―)|—|--", line):
            add(ln, line, "ダッシュは「――」（二つ）にそろえる（--fix-punct で自動修正）")
        if re.search(r"[ｦ-ﾟ]", line):
            add(ln, line, "半角カタカナが混じっている。全角に直す")
        for o, c, label in (("「", "」", "「」"), ("『", "』", "『』"), ("（", "）", "（）")):
            if line.count(o) != line.count(c):
                add(ln, line, "%s の対応が合っていない（開き %d、閉じ %d）" % (label, line.count(o), line.count(c)))
    return out


def style_findings(lines, start):
    """表記ゆれ、字下げの混在、全角・半角の混在。[(等級, 類型, 行, 断片, 提案)] を返す。"""
    out = []
    body = "\n".join(lines[start:])
    for a, b in VARIANT_PAIRS:
        if a in body and b in body:
            out.append(("提醒", "表記ゆれ", 0, "「%s」と「%s」が混在" % (a, b), "どちらかに統一し、名詞表にも書く"))
    paras = [(i + 1, l) for i, l in enumerate(lines[start:], start=start)
             if l.strip() and not l.lstrip().startswith(("#", "<!--"))
             and not l.lstrip(" 　").startswith(("「", "『", "（", "―", "…", "＊", "*", "◇", "---"))]
    ind = [n for n, l in paras if l.startswith("　")]
    noind = [n for n, l in paras if not l.startswith("　")]
    if ind and noind and min(len(ind), len(noind)) >= 2:
        out.append(("提醒", "段落頭の字下げが混在", (ind + noind)[0],
                    "字下げあり %d 段落、なし %d 段落" % (len(ind), len(noind)), "文風に合わせて、地の文の段落頭を一字下げするかしないかに統一する"))
    prose = _plain(body)
    if re.search(r"[Ａ-Ｚａ-ｚ０-９]", prose) and re.search(r"[A-Za-z0-9]", prose):
        out.append(("提醒", "全角・半角の英数字が混在", 0, "全角と半角の英数字が両方ある", "どちらかに統一する（既定は半角）"))
    return out


def check_file(path, whitelist, banned=None, aliases=None):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if banned is None:
        banned = load_banned(guess_book_root(path))
    if aliases is None:
        aliases = load_aliases(guess_book_root(path))
    lines = text.split("\n")
    start = strip_frontmatter(lines)
    findings = []
    cat_counter = Counter()
    cat_lines = defaultdict(list)
    phrase_counter = Counter()

    def add(level, kind, lineno, snippet, hint):
        findings.append({"等級": level, "類型": kind, "行": lineno, "片段": snippet, "建議": hint})

    for ln, snip, hint in punct_findings(lines, start):
        add("必須修", "約物", ln, snip, hint)

    for idx in range(start, len(lines)):
        line = lines[idx]
        lineno = idx + 1
        if not line.strip():
            continue
        if any(w in line for w in whitelist):
            continue
        for m in re.finditer(ENGINEERING_WORDS, line):
            add("建議修", "工房の言葉", lineno, m.group(0), "本文に執筆用の語が出ている。作中に実在するもの（人物が本を読んでいる等）なら無視してよい")
        for rx, show, hint in banned:
            for m in rx.finditer(line):
                add("建議修", "禁用語", lineno, m.group(0), hint)
        if line.lstrip().startswith("#"):
            continue
        if re.search(r"\*\*[^*\n]+\*\*|^\s*[-*]\s+\S|^\s*\d+\.\s+\S|^\s*>\s", line):
            add("建議修", "Markdown 記号の残り", lineno, line.strip()[:30], "本文に箇条書きや強調の記号が残っている。文章に直す")
        for cat, pat in AI_SIGNALS:
            for m in re.finditer(pat, line):
                cat_counter[cat] += 1
                cat_lines[cat].append(lineno)
                if cat not in ("万能の副詞", "説明の語尾"):
                    phrase_counter[m.group(0)] += 1

    for cat, cnt in cat_counter.items():
        limit = CATEGORY_LIMIT.get(cat, 3)
        level = "建議修" if cnt >= limit else "提醒"
        add(level, "AI 臭：" + cat, cat_lines[cat][0],
            "計 %d 回、%s 行目" % (cnt, "、".join(str(x) for x in cat_lines[cat][:10])),
            CATEGORY_HINT.get(cat, "文脈で判断する。重なるときは具体的な動作や物に置き換えるか削る（ai-signals.md を参照）"))
    for phrase, cnt in phrase_counter.items():
        if cnt >= PHRASE_REPEAT and len(phrase) >= 3:
            add("建議修", "決まり文句の反復", 0, "「%s」×%d" % (phrase, cnt), "同じ章で繰り返しすぎ。最も効く一か所を残す")

    for level, kind, ln, snip, hint in style_findings(lines, start):
        add(level, kind, ln, snip, hint)

    body_lines = [(i + 1, l) for i, l in enumerate(lines[start:], start=start)
                  if l.strip() and not l.lstrip().startswith("#") and not l.strip().startswith("<!--")]
    if body_lines:
        last_no, last = body_lines[-1]
        if re.search(r"運命|これから|新たな|始まり|まだ知らなかった|知る由もなかった|決意(?:した|を)|誓っ|胸に刻|未来へ|明日へ|歩き出し|一歩を踏み出", last) \
                and not any(w in last for w in whitelist):
            add("建議修", "章末の昇華", last_no, last.strip()[:40], "具体的な像・行動・台詞で止める。感想や予告で終えない")
        wl_free = [(n, l) for n, l in body_lines if not any(w in l for w in whitelist)]
        for level, kind, ln, snip, hint in rhythm_findings(wl_free, aliases):
            add(level, kind, ln, snip, hint)

    chars, no_space = count_chars("\n".join(lines[start:]))
    order = {"必須修": 0, "建議修": 1, "提醒": 2}
    findings.sort(key=lambda x: (order[x["等級"]], x["行"]))
    return {"檔案": path, "中文字數": chars, "總字數（不含空白）": no_space, "問題": findings}


def collect(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if name.endswith((".md", ".txt")):
                    files.append(os.path.join(p, name))
        elif os.path.isfile(p):
            files.append(p)
        else:
            print("見つかりません：%s" % p, file=sys.stderr)
            sys.exit(2)
    return files


def print_report(res):
    print("=" * 60)
    print("%s" % res["檔案"])
    print("文字数：%d　総文字数（空白・改行を除く）：%d" % (res["中文字數"], res["總字數（不含空白）"]))
    if not res["問題"]:
        print("問題は見つかりませんでした。")
        return
    groups = defaultdict(list)
    for f in res["問題"]:
        groups[f["等級"]].append(f)
    for level in ("必須修", "建議修", "提醒"):
        if not groups[level]:
            continue
        print("\n【%s】%d 件" % (level, len(groups[level])))
        for f in groups[level]:
            where = ("%d 行目" % f["行"]) if f["行"] else "章全体"
            print("  - %s｜%s｜%s → %s" % (where, f["類型"], f["片段"], f["建議"]))


def main():
    ap = argparse.ArgumentParser(description="小説本文チェック（日本語）")
    ap.add_argument("paths", nargs="+", help="章のファイルまたはフォルダ")
    ap.add_argument("--fix-punct", action="store_true", help="約物を自動修正（ファイルを直接書き換える）")
    ap.add_argument("--json", action="store_true", help="JSON で出力")
    ap.add_argument("--count", action="store_true", help="文字数だけを出力")
    ap.add_argument("--book-root", help="書籍フォルダ（既定は 正文/ の一つ上を探す）")
    args = ap.parse_args()

    files = collect(args.paths)
    if not files:
        print("チェックできる .md か .txt がありません", file=sys.stderr)
        sys.exit(2)

    if args.count:
        for p in files:
            with open(p, encoding="utf-8") as f:
                lines = f.read().split("\n")
            body = "\n".join(lines[strip_frontmatter(lines):])
            c, ns = count_chars(body)
            dlg = sum(_jlen(m) for m in re.findall(r"「([^「」]*)」", _plain(body)))
            print("%s\t文字数 %d\t総文字数 %d\t会話の割合 %d%%" % (p, c, ns, round(100.0 * dlg / max(1, _jlen(_plain(body))))))
        return

    if args.fix_punct:
        for p in files:
            with open(p, encoding="utf-8") as f:
                text = f.read()
            new, n = fix_punct(text)
            if n:
                with open(p, "w", encoding="utf-8", newline="\n") as f:
                    f.write(new)
            print("%s：約物を %d 件修正" % (p, n))

    book_root = args.book_root or guess_book_root(files[0])
    whitelist = load_whitelist(book_root)
    results = [check_file(p, whitelist) for p in files]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print_report(r)
        must = sum(1 for r in results for f in r["問題"] if f["等級"] == "必須修")
        print("\n" + "=" * 60)
        print("合計：必須修 %d 件。%s" % (must, "先に必須修を直してください。" if must else ""))

    if any(f["等級"] == "必須修" for r in results for f in r["問題"]):
        sys.exit(1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
