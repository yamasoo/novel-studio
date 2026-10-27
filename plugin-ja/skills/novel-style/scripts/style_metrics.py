# -*- coding: utf-8 -*-
"""
日本語文章の文体指標（ローカル統計、AI は使わない）。

使い方：
  python style_metrics.py sample.md [他のファイル…] [--exclude 澪,蒼真]

出力された Markdown の表を、文風ノートの「## 文字指標（程式統計）」の下に貼る。
--exclude：「高頻詞組」から除きたい語（人名・地名）。
工房もこのファイルを読み込んで文体指標を計算する。API と指標のキー（中国語）は中国語版・英語版と同じで、
ほかの部分を変える必要はない。
"""
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
METRICS_HEAD = "## 文字指標（程式統計）"
JP = r"[぀-ヿ㐀-䶿一-鿿豈-﫿]"
JP_RE = re.compile(JP)
SHORT, LONG = 15, 45


class SampleTooShort(ValueError):
    pass


def strip_frontmatter(text):
    if text.startswith("---"):
        lines = text.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:])
    return text


SENT_SPLIT = re.compile(r"(?<=[。！？!?])[」』）]*|(?<=……)[」』）]*")
QUOTE = re.compile(r"「([^「」]*)」|『([^『』]*)』")
PUNCT_KEYS = [("逗號", "、"), ("頓號", "・"), ("驚嘆號", "！"), ("問號", "？"), ("刪節號", "…"), ("破折號", "―")]
METRIC_NOTES = {
    "樣本字數": "文字数（ルビ記法・空白・見出しを除く）",
    "平均句長": "文字数。短いほどテンポが速い",
    "短句比例": "%d 字以下の文の割合" % SHORT,
    "長句比例": "%d 字以上の文の割合" % LONG,
    "平均段長": "文字数",
    "單句成段": "一文だけの段落の割合",
    "對白比例": "「」『』の中の文字の割合",
    "對白段比例": "会話を含む段落の割合",
    "每千字逗號": "千字あたりの読点「、」",
    "每千字頓號": "千字あたりの中黒「・」",
    "每千字驚嘆號": "千字あたりの「！」（半角も含む）",
    "每千字問號": "千字あたりの「？」（半角も含む）",
    "每千字刪節號": "千字あたりの三点リーダー（「……」を一回と数える）",
    "每千字破折號": "千字あたりのダッシュ（「――」を一回と数える）",
    "每千字的": "千字あたりの副詞的な修飾（〜に・〜と・〜く 型の「ゆっくりと」など）。多いほど修飾が多い",
    "每千字地": "千字あたりの曖昧表現（ようだ・みたい・らしい・かもしれない等）",
    "每千字AI味信號": "検査ツールが見つけた AI 臭の決まり文句の千字あたり件数",
}


def _prose(text):
    body = strip_frontmatter(text.replace("\r\n", "\n"))
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"(?m)^\s*#.*$", "", body)
    body = re.sub(r"(?m)^\s*([-*_]|―|＊){3,}\s*$", "", body)
    body = re.sub(r"[|｜]", "", body)
    body = re.sub(r"《[^》\n]*》", "", body)
    return body


def _paragraphs(body):
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if len(paras) <= 2 and body.count("\n") > 4:
        paras = [ln.strip() for ln in body.split("\n") if ln.strip()]
    return [re.sub(r"[ \t]+", " ", p).replace("\n", "") for p in paras]


def _ai_signals():
    """隣の novel-deslop の検査ツールから AI 臭のリストを借りる（読み込めなければ使わない）。"""
    try:
        import importlib.util
        p = os.path.join(HERE, "..", "..", "novel-deslop", "scripts", "check_text.py")
        spec = importlib.util.spec_from_file_location("check_text_for_metrics_ja", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return [pat for cat, pat in mod.AI_SIGNALS if cat not in ("万能の副詞", "説明の語尾")]
    except Exception:
        return []


_AI = None


def _jl(s):
    return len(JP_RE.findall(s)) + len(re.findall(r"[A-Za-z0-9０-９Ａ-Ｚａ-ｚ]", s))


def analyze(text, exclude=()):
    """指標の順序つき dict を返す。exclude：高頻詞組から除く語。"""
    global _AI
    if _AI is None:
        _AI = _ai_signals()
    body = _prose(text)
    paras = _paragraphs(body)
    joined = "\n".join(paras)
    total = _jl(joined)
    if total < 600:
        raise SampleTooShort("サンプルが短すぎます（%d 字）。数値に意味を持たせるには 600 字以上、できれば 3000 字以上必要です。" % total)
    sents = []
    for p in paras:
        for s in SENT_SPLIT.split(p):
            if s and _jl(s):
                sents.append(s)
    slen = [_jl(s) for s in sents]
    plen = [_jl(p) for p in paras if _jl(p)]
    dlg = sum(_jl(a or b) for a, b in QUOTE.findall(joined))
    k = 1000.0 / total
    m = {"樣本字數": total,
         "平均句長": round(sum(slen) / len(slen), 1) if slen else 0,
         "短句比例": "%d%%" % round(100.0 * sum(1 for n in slen if n <= SHORT) / max(1, len(slen))),
         "長句比例": "%d%%" % round(100.0 * sum(1 for n in slen if n >= LONG) / max(1, len(slen))),
         "平均段長": round(sum(plen) / len(plen), 1) if plen else 0,
         "單句成段": "%d%%" % round(100.0 * sum(1 for p in paras if len([x for x in SENT_SPLIT.split(p) if x and _jl(x)]) <= 1) / max(1, len(paras))),
         "對白比例": "%d%%" % round(100.0 * dlg / total),
         "對白段比例": "%d%%" % round(100.0 * sum(1 for p in paras if "「" in p or "『" in p) / max(1, len(paras)))}
    for label, ch in PUNCT_KEYS:
        if ch == "、":
            n = joined.count("、") + joined.count("，")
        elif ch == "！":
            n = joined.count("！") + joined.count("!")
        elif ch == "？":
            n = joined.count("？") + joined.count("?")
        elif ch == "…":
            n = len(re.findall(r"…+", joined)) + len(re.findall(r"\.{3}", joined))
        elif ch == "―":
            n = len(re.findall(r"[―—]+", joined)) + joined.count("--")
        else:
            n = joined.count(ch)
        m["每千字" + label] = round(n * k, 1)
    m["每千字的"] = round(len(re.findall(r"[ぁ-ん]{2,}(?:と|に)(?=[ぁ-んァ-ヶ一-龥])|[ぁ-ん一-龥]{1,3}く(?=[、]|[動歩言笑振見])", joined)) * k, 1)
    m["每千字地"] = round(len(re.findall(r"ようだ|ような|ように|みたい|らしい|かもしれ|だろう|気がした|ような気", joined)) * k, 1)
    m["每千字AI味信號"] = round(sum(len(re.findall(p, joined)) for p in _AI) * k, 1)
    m["高頻詞組"] = "、".join(frequent_phrases(paras, exclude=exclude)) or "（目立って繰り返される語句なし）"
    return m


def frequent_phrases(paras, top=12, exclude=()):
    """3〜6 字の連続を 3 回以上使っている語句（長い語句に含まれるものは除く）。癖と口調を示す。"""
    cnt = Counter()
    ex = [e for e in exclude if e]
    for p in paras:
        for chunk in re.split(r"[、。！？!?「」『』（）…―\s・]+", p):
            if len(chunk) < 3:
                continue
            for n in (3, 4, 5, 6):
                for i in range(len(chunk) - n + 1):
                    g = chunk[i:i + n]
                    # かな・漢字だけ。助詞だけの断片は除く
                    if not re.fullmatch(JP + "+", g):
                        continue
                    if re.fullmatch(r"[ぁ-ん]+", g):
                        continue
                    if g[0] in "ぁぃぅぇぉっゃゅょんをがにのはもでとへ" or g[-1] in "ぁぃぅぇぉっゃゅょ":
                        continue
                    cnt[g] += 1
    cand = [(w, c) for w, c in cnt.items() if c >= 3 and not any(e in w for e in ex)]
    cand.sort(key=lambda x: (-x[1] * (len(x[0]) ** 1.3), x[0]))
    out = []
    for w, c in cand:
        if any(w in o for o, _ in out) or any(o in w and cnt[o] <= c + 1 for o, _ in out):
            continue
        out.append((w, c))
        if len(out) >= top:
            break
    return ["%s×%d" % (w, c) for w, c in out]


def metrics_md(m):
    rows = ["| 指標 | 數值 | 說明 |", "|---|---|---|"]
    for k, v in m.items():
        rows.append("| %s | %s | %s |" % (k, v, METRIC_NOTES.get(k, "")))
    return (METRICS_HEAD + "\n<!-- サンプル本文からプログラムが計算した数値。執筆する AI はこの数字を参照する。再実行するとこの節は上書きされる。 -->\n"
            + "\n".join(rows) + "\n")


def main(argv):
    exclude, files = [], []
    it = iter(argv)
    for a in it:
        if a == "--exclude":
            exclude = [x.strip() for x in next(it, "").split(",") if x.strip()]
        else:
            files.append(a)
    if not files:
        print(__doc__)
        return 1
    text = "\n\n".join(open(f, encoding="utf-8").read() for f in files)
    try:
        print(metrics_md(analyze(text, exclude)))
    except SampleTooShort as e:
        print(str(e))
        return 2
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
