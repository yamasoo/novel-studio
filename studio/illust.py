# -*- coding: utf-8 -*-
"""
插圖：每個章節、角色、勢力、世界觀項目、封面都可以有插圖（全部選用）。

書目錄/插圖/
├── .gitignore                 圖片預設不進 git
├── 封面/
├── 章節/第003章/
├── 角色/林晚/   勢力/沈家/   世界觀/玉珮/
每個資料夾：圖片 + 同名 .json（提示詞、seed、參數、來源片段）+ _插圖.json（主圖、提示詞草稿）

能在本機做的都在本機做：挑片段（打分）、中文→Danbooru 標籤查表、套用 StyleSelectorXL 樣式表、
組裝 Anima 提示詞。只有「把中文場景寫成英文描述」這一步需要 AI（另外的任務）。
"""
import base64
import json
import os
import random
import re
import shutil
import time
import zipfile
from xml.etree import ElementTree as ET

from . import project

ROOT = "插圖"
INDEX = "_插圖.json"
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
ENTITY_DIRS = ("角色", "勢力", "世界觀")
CARD_HEAD = "## 繪圖提示"

DEFAULTS = {
    "forge_url": "http://127.0.0.1:7860",
    "forge_dir": "",
    "style_sheet": "",
    "tag_csv": "",
    "tag_zh_csv": "",
    "params": "Steps: 30, Sampler: Euler a, CFG scale: 4.5",
    "width": 896, "height": 1152,
    "quality": "masterpiece, best quality, score_7",
    "safety": "safe",
    "negative": "worst quality, low quality, score_1, score_2, score_3, artist name",
    "format": "mixed",            # mixed：標籤＋自然語言；tags：只有標籤；natural：自然語言為主
    "style_source": "prompt",     # 樣式表用哪個欄位：prompt、naturl_prompt、both
    "show_nsfw_styles": False,
    "save_in_forge": False,       # 也存一份在 Forge 的 outputs 資料夾
    "provider": "",               # 產生提示詞用的 AI（空白＝面板目前的執行者）
}
SIZES = [("直式", 896, 1152), ("橫式", 1152, 896), ("方形", 1024, 1024), ("寬螢幕", 1344, 768), ("長直式", 768, 1344)]


class IllustError(project.ProjectError):
    pass


# ---------------------------------------------------------------------------
# 目標與路徑
# ---------------------------------------------------------------------------
def target_dir(book_dir, target):
    """target：cover、chapter:3、entity:設定/角色/林晚.md。回傳 (絕對路徑, 相對路徑, 說明)。"""
    if target == "cover":
        rel = ROOT + "/封面"
        label = "封面"
    elif target.startswith("chapter:"):
        no = int(target.split(":", 1)[1])
        rel = ROOT + "/章節/第%03d章" % no
        label = "第%d章" % no
    elif target.startswith("entity:"):
        f = target.split(":", 1)[1].replace("\\", "/")
        m = re.match(r"^設定/(角色|勢力|世界觀)/([^/]+)\.md$", f)
        if not m:
            raise IllustError("只有角色、勢力、世界觀的設定檔可以加插圖")
        rel = "%s/%s/%s" % (ROOT, m.group(1), m.group(2))
        label = m.group(2)
    else:
        raise IllustError("不認得的插圖目標：%s" % target)
    return os.path.join(book_dir, *rel.split("/")), rel, label


def _ensure_root(book_dir):
    d = os.path.join(book_dir, ROOT)
    os.makedirs(d, exist_ok=True)
    gi = os.path.join(d, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8", newline="\n") as f:
            f.write("# 插圖檔案很大，預設不進 git。想一起版本控制就刪掉這個檔案。\n*\n!.gitignore\n")


def _read_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def load_index(book_dir, target):
    d, _, _ = target_dir(book_dir, target)
    return _read_json(os.path.join(d, INDEX), {})


def save_index(book_dir, target, idx):
    d, _, _ = target_dir(book_dir, target)
    _ensure_root(book_dir)
    _write_json(os.path.join(d, INDEX), idx)


def list_images(book_dir, target):
    d, rel, label = target_dir(book_dir, target)
    idx = _read_json(os.path.join(d, INDEX), {})
    out = []
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.lower().endswith(IMG_EXT):
                p = os.path.join(d, f)
                meta = _read_json(os.path.splitext(p)[0] + ".json", {})
                out.append({"file": f, "path": rel + "/" + f, "mtime": os.path.getmtime(p), "size": os.path.getsize(p),
                            "seed": meta.get("seed"), "origin": meta.get("origin", "upload"),
                            "width": meta.get("width"), "height": meta.get("height"),
                            "prompt": meta.get("prompt", ""), "negative": meta.get("negative", ""),
                            "main": f == idx.get("main")})
    out.sort(key=lambda x: -x["mtime"])
    if out and not any(x["main"] for x in out) and idx.get("main") is None:
        pass
    return {"target": target, "label": label, "dir": rel, "images": out, "main": idx.get("main"),
            "draft": idx.get("draft") or {}}


def main_image(book_dir, target):
    """主圖的絕對路徑；沒有指定主圖就用最新一張；都沒有回傳 None。"""
    try:
        d, _, _ = target_dir(book_dir, target)
    except IllustError:
        return None
    if not os.path.isdir(d):
        return None
    idx = _read_json(os.path.join(d, INDEX), {})
    if idx.get("main") and os.path.isfile(os.path.join(d, idx["main"])):
        return os.path.join(d, idx["main"])
    return None


def set_main(book_dir, target, name):
    d, _, _ = target_dir(book_dir, target)
    if name and not os.path.isfile(os.path.join(d, os.path.basename(name))):
        raise IllustError("找不到這張圖")
    idx = load_index(book_dir, target)
    idx["main"] = os.path.basename(name) if name else None
    save_index(book_dir, target, idx)


def save_draft(book_dir, target, draft):
    idx = load_index(book_dir, target)
    idx["draft"] = draft
    save_index(book_dir, target, idx)


def _new_name(d, seed=None, ext=".png"):
    base = time.strftime("%Y%m%d-%H%M%S") + ("-%s" % seed if seed not in (None, "", -1) else "")
    name, n = base + ext, 2
    while os.path.exists(os.path.join(d, name)):
        name = "%s-%d%s" % (base, n, ext)
        n += 1
    return name


def _sniff_ext(data):
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _image_size(data):
    try:
        if data.startswith(b"\x89PNG"):
            return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        if data[:3] == b"\xff\xd8\xff":
            i = 2
            while i < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
                i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    except Exception:
        pass
    return None, None


def save_image(book_dir, target, data, meta):
    """存一張圖（bytes），回傳檔名。meta 寫進同名 .json。"""
    ext = _sniff_ext(data)
    if not ext:
        raise IllustError("只能存 PNG、JPG、WEBP 圖片")
    d, rel, _ = target_dir(book_dir, target)
    _ensure_root(book_dir)
    os.makedirs(d, exist_ok=True)
    name = _new_name(d, meta.get("seed"), ext)
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)
    w, h = _image_size(data)
    meta = dict(meta, created=time.time(), width=meta.get("width") or w, height=meta.get("height") or h)
    _write_json(os.path.join(d, os.path.splitext(name)[0] + ".json"), meta)
    idx = load_index(book_dir, target)
    if not idx.get("main"):
        idx["main"] = name
        save_index(book_dir, target, idx)
    return name


def upload(book_dir, target, files):
    names = []
    for f in files or []:
        try:
            data = base64.b64decode(f.get("data") or "")
        except Exception:
            raise IllustError("圖片「%s」讀取失敗" % f.get("name"))
        if len(data) > 30 * 1024 * 1024:
            raise IllustError("圖片「%s」超過 30MB" % f.get("name"))
        names.append(save_image(book_dir, target, data, {"origin": "upload", "source_name": f.get("name")}))
    if not names:
        raise IllustError("請選擇圖片")
    return names


def delete_image(book_dir, target, name):
    d, _, _ = target_dir(book_dir, target)
    name = os.path.basename(name or "")
    p = os.path.join(d, name)
    if not name.lower().endswith(IMG_EXT) or not os.path.isfile(p):
        raise IllustError("找不到這張圖")
    bak = os.path.join(book_dir, ".studio", "備份", "插圖")
    os.makedirs(bak, exist_ok=True)
    stamp = int(time.time())
    shutil.move(p, os.path.join(bak, "%d_%s" % (stamp, name)))
    side = os.path.splitext(p)[0] + ".json"
    if os.path.isfile(side):
        shutil.move(side, os.path.join(bak, "%d_%s" % (stamp, os.path.basename(side))))
    idx = load_index(book_dir, target)
    if idx.get("main") == name:
        rest = [x for x in os.listdir(d) if x.lower().endswith(IMG_EXT)]
        idx["main"] = sorted(rest)[-1] if rest else None
        save_index(book_dir, target, idx)


def image_path(book_dir, rel):
    p = project.safe_path(book_dir, rel)
    if not rel.replace("\\", "/").startswith(ROOT + "/") or not p.lower().endswith(IMG_EXT) or not os.path.isfile(p):
        raise IllustError("找不到這張圖")
    return p


def overview(book_dir):
    """全書插圖總覽：封面、各章、各設定項目的張數與主圖。"""
    out = []
    root = os.path.join(book_dir, ROOT)

    def add(target):
        try:
            info = list_images(book_dir, target)
        except IllustError:
            return
        if info["images"]:
            out.append({"target": target, "label": info["label"], "count": len(info["images"]),
                        "main": (info["dir"] + "/" + info["main"]) if info["main"] else info["dir"] + "/" + info["images"][0]["file"]})
    add("cover")
    for r in project.scan_chapters(book_dir):
        add("chapter:%d" % r["no"])
    for sub in ENTITY_DIRS:
        d = os.path.join(root, sub)
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                add("entity:設定/%s/%s.md" % (sub, name))
    return out


# ---------------------------------------------------------------------------
# 視覺卡：設定檔裡的「## 繪圖提示」一節
# ---------------------------------------------------------------------------
def read_card(text):
    m = re.search(r"(?ms)^" + re.escape(CARD_HEAD) + r"[^\n]*\n(.*?)(?=^## |\Z)", text or "")
    if not m:
        return None
    sec = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S)
    card = {"tags": "", "description": "", "position": ""}
    for line in sec.split("\n"):
        s = line.strip().lstrip("-").strip()
        for key, label in (("tags", "標籤"), ("description", "描述"), ("position", "預設位置")):
            mm = re.match(r"^%s\s*[:：]\s*(.*)$" % label, s)
            if mm:
                card[key] = mm.group(1).strip()
    return card if (card["tags"] or card["description"]) else None


def write_card(text, card):
    lines = [CARD_HEAD,
             "<!-- 給繪圖用的外觀描述。標籤用英文 Danbooru 標籤（用空格不用底線），描述用英文句子。工作台出圖時會自動帶入。 -->",
             "- 標籤：%s" % normalize_tags(card.get("tags", "")),
             "- 描述：%s" % (card.get("description") or "").strip()]
    sec = "\n".join(lines) + "\n"
    pat = re.compile(r"(?ms)^" + re.escape(CARD_HEAD) + r"[^\n]*\n.*?(?=^## |\Z)")
    if pat.search(text):
        return pat.sub(sec + "\n", text, count=1).rstrip() + "\n"
    return text.rstrip() + "\n\n" + sec


def entity_cards(book_dir):
    """所有角色、勢力、世界觀項目的名稱、別名與視覺卡。"""
    out = []
    for sub in ENTITY_DIRS:
        for e in project.list_entries(book_dir, "設定/" + sub):
            text = project.read_text(os.path.join(book_dir, e["file"]))
            out.append({"kind": sub, "name": e["name"], "file": e["file"],
                        "aliases": [str(a) for a in (e.get("aliases") or [])],
                        "card": read_card(text), "appearance": _appearance(text)})
    return out


def _appearance(text):
    """設定檔裡描述外觀的段落（給 AI 產生視覺卡用）。"""
    body = project.split_frontmatter(text)[1]
    parts = []
    for m in re.finditer(r"(?ms)^##+\s*([^\n]*)\n(.*?)(?=^## |\Z)", body):
        if re.search(r"外貌|外觀|長相|形象|樣貌|外表|服裝|特徵|描述|一句話|簡介|概述", m.group(1)):
            t = re.sub(r"<!--.*?-->", "", m.group(2), flags=re.S).strip()
            if t:
                parts.append("【%s】%s" % (m.group(1).strip(), t))
    return "\n".join(parts)[:1500]


def mentioned(book_dir, text):
    """片段裡提到的角色、地點（依第一次出現的位置排序）。"""
    found = []
    for e in entity_cards(book_dir):
        pos = [text.find(n) for n in [e["name"]] + e["aliases"] if n and len(n) >= 2 and n in text]
        if pos:
            found.append((min(pos), e))
    found.sort(key=lambda x: x[0])
    return [e for _, e in found]


# ---------------------------------------------------------------------------
# 挑片段（本機打分）
# ---------------------------------------------------------------------------
ACTION = list("揮砍刺劈斬躍跳衝撲抓推拉踢擋拔射閃翻摔撞奔跑扯甩握舉扔丟砸擲踹按壓拽搶追逃攔撕咬抱扶接拋踏蹬滾爬撐揪掐扣抽捅戳攥拎")
ACTION += ["轉身", "抬手", "伸手", "站起", "跪下", "倒下", "跌", "撲倒", "擋住", "拔出", "推開", "衝進", "跳下", "翻身", "揮手"]
VISUAL = ["紅", "白", "黑", "青", "金", "銀", "紫", "綠", "藍", "黃", "光", "火", "燈", "燭", "月", "日", "雨", "雪", "霧", "血", "煙", "風",
          "雲", "影", "夜", "晨", "黃昏", "窗", "門", "簾", "花", "樹", "水", "河", "橋", "街", "屋簷", "衣", "袖", "髮", "劍", "刀",
          "玉", "紙", "燈籠", "火光", "陽光", "月光", "雨水", "雪花"]
INNER = ["想", "覺得", "心裡", "明白", "知道", "記得", "以為", "彷彿", "似乎", "也許", "或許", "思索", "回憶"]


def _paras(text):
    body = project.split_frontmatter(text)[1]
    body = re.sub(r"(?m)^\s*#.*$", "", body)
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip() and not re.fullmatch(r"[-*_＊\s]{3,}", p.strip())]


def pick_passages(text, mode="highlight", hints="", top=3, window=(120, 420)):
    """把段落組成 120～420 字的片段打分，回傳前 top 名。mode：highlight（精華）、action（動作）。"""
    paras = _paras(text)
    cands = []
    for i in range(len(paras)):
        buf, n = [], 0
        for j in range(i, len(paras)):
            buf.append(paras[j])
            n += len(paras[j])
            if n >= window[0]:
                break
        if n < 40:
            continue
        seg = "\n\n".join(buf)
        if len(seg) > window[1] * 1.5:
            seg = seg[:int(window[1] * 1.5)]
        cands.append((i, i + len(buf) - 1, seg))
    hint_grams = set()
    for h in re.findall(r"[一-鿿]{2,}", hints or ""):
        hint_grams |= {h[k:k + 2] for k in range(len(h) - 1)}
    scored = []
    for a, b, seg in cands:
        chars = max(1, len(re.findall(r"[一-鿿]", seg)))
        act = sum(seg.count(w) for w in ACTION)
        vis = sum(seg.count(w) for w in VISUAL)
        inner = sum(seg.count(w) for w in INNER)
        dlg = sum(len(x) for x in re.findall(r"「([^」]*)」", seg)) / chars
        sents = [s for s in re.split(r"[。！？…]+", seg) if s.strip()]
        short = sum(1 for s in sents if len(s) <= 10) / max(1, len(sents))
        excl = seg.count("！")
        hint = sum(1 for g in hint_grams if g in seg) if hint_grams else 0
        k = 100.0 / chars
        if mode == "action":
            score = act * k * 3 + short * 4 + excl * 0.8 + vis * k * 1 - dlg * 6 - inner * k * 2 + hint * 0.6
        else:
            score = vis * k * 2.2 + act * k * 1.5 + hint * 1.2 + short * 1.5 - dlg * 4 - inner * k * 1.5
        reasons = []
        if act:
            reasons.append("動作詞 %d" % act)
        if vis:
            reasons.append("畫面詞 %d" % vis)
        if hint:
            reasons.append("對上章綱 %d" % hint)
        if dlg > 0.4:
            reasons.append("對白多")
        scored.append({"start": a, "end": b, "text": seg, "score": round(score, 2), "reasons": "、".join(reasons)})
    scored.sort(key=lambda x: -x["score"])
    out = []
    for s in scored:
        if any(not (s["end"] < o["start"] or s["start"] > o["end"]) for o in out):
            continue
        out.append(s)
        if len(out) >= top:
            break
    return out


# ---------------------------------------------------------------------------
# Danbooru 標籤：正規化、驗證、中文查表（用 tagcomplete 附的 csv）
# ---------------------------------------------------------------------------
_TAGS = {"path": None, "mtime": None, "tags": {}, "alias": {}}
_ZH = {"path": None, "mtime": None, "pairs": []}
COUNT_TAGS = re.compile(r"^(\d+|6\+)(girls?|boys?|others?)$|^(solo|multiple girls|multiple boys)$")


def normalize_tag(t):
    t = t.strip().strip(",").strip()
    if not t:
        return ""
    if re.match(r"^score_\d", t):          # score 標籤保留底線
        return t
    if t.startswith("@") or t.startswith("("):
        return t.replace("_", " ") if not t.startswith("(") else t
    return re.sub(r"\s+", " ", t.replace("_", " "))


def normalize_tags(s):
    seen, out = set(), []
    for t in re.split(r"[,，、\n]+", s or ""):
        n = normalize_tag(t)
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return ", ".join(out)


def _load_tags(path):
    if not path or not os.path.isfile(path):
        return None
    mt = os.path.getmtime(path)
    if _TAGS["path"] == path and _TAGS["mtime"] == mt:
        return _TAGS
    tags, alias = {}, {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split(",", 3)
            if len(parts) < 3:
                continue
            name = parts[0].replace("_", " ")
            try:
                cnt = int(parts[2])
            except ValueError:
                cnt = 0
            tags[name] = (parts[1], cnt)
            if len(parts) > 3:
                for a in parts[3].strip('"').split(","):
                    a = a.strip().replace("_", " ")
                    if a and not a.startswith("/"):
                        alias.setdefault(a, name)
    _TAGS.update(path=path, mtime=mt, tags=tags, alias=alias)
    return _TAGS


def check_tags(s, path):
    """回傳 (改正後的標籤字串, [說明])。不存在的標籤保留但提醒；別名換成正式名稱。"""
    db = _load_tags(path)
    tags = [t for t in normalize_tags(s).split(", ") if t]
    if not db:
        return ", ".join(tags), []
    out, notes = [], []
    for t in tags:
        low = t.lower()
        if low.startswith(("@", "score_", "(")) or low in ("safe", "sensitive", "nsfw", "explicit", "newest", "recent", "mid", "early", "old") \
                or re.match(r"^year \d{4}$", low) or low in ("masterpiece", "best quality", "good quality", "normal quality"):
            out.append(t)
            continue
        if low in db["tags"]:
            out.append(t)
        elif low in db["alias"]:
            out.append(db["alias"][low])
            notes.append("「%s」→「%s」" % (t, db["alias"][low]))
        else:
            out.append(t)
            notes.append("「%s」不是 Danbooru 標籤（Anima 也能讀自然語言，留著無妨）" % t)
    return ", ".join(out), notes


def _load_zh(path):
    if not path or not os.path.isfile(path):
        return None
    mt = os.path.getmtime(path)
    if _ZH["path"] == path and _ZH["mtime"] == mt:
        return _ZH
    pairs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split(",", 2)
            if len(parts) < 3 or parts[1] not in ("0",):   # 只用一般標籤
                continue
            tag = parts[0].replace("_", " ")
            for zh in parts[2].split("|"):
                zh = zh.strip()
                if len(zh) >= 2 and re.search(r"[一-鿿]", zh):
                    pairs.append((zh, tag))
    pairs.sort(key=lambda x: -len(x[0]))
    _ZH.update(path=path, mtime=mt, pairs=pairs)
    return _ZH


def zh_lookup(text, zh_path, tag_path=None, limit=40):
    """在中文文字裡找出對照表有的詞，轉成標籤（長詞優先，不重疊）。回傳 [{zh, tag, count}]。"""
    db = _load_zh(zh_path)
    if not db:
        return []
    pop = _load_tags(tag_path) if tag_path else None
    used = [False] * len(text)
    hits = {}
    for zh, tag in db["pairs"]:
        start = 0
        while True:
            i = text.find(zh, start)
            if i < 0:
                break
            if not any(used[i:i + len(zh)]):
                for k in range(i, i + len(zh)):
                    used[k] = True
                h = hits.setdefault(tag, {"zh": zh, "tag": tag, "count": 0})
                h["count"] += 1
            start = i + 1
    out = list(hits.values())
    # 對照表裡有些短詞對得很鬆（例如兩個字對到四個英文字的標籤），過濾掉
    out = [h for h in out if not (len(h["zh"]) <= 2 and len(h["tag"].split()) >= 3)]
    if pop:
        for h in out:
            h["popularity"] = pop["tags"].get(h["tag"], ("0", 0))[1]
        out = [h for h in out if h["popularity"] >= 50]
        out.sort(key=lambda h: (-h["count"], -h.get("popularity", 0)))
    else:
        out.sort(key=lambda h: -h["count"])
    return out[:limit]


def tag_dict_paths(cfg):
    """設定的路徑，沒填就從 Forge 資料夾找 tagcomplete 附的檔案。"""
    t, z = cfg.get("tag_csv") or "", cfg.get("tag_zh_csv") or ""
    fd = cfg.get("forge_dir") or ""
    base = os.path.join(fd, "extensions", "a1111-sd-webui-tagcomplete", "tags") if fd else ""
    if not t and base and os.path.isfile(os.path.join(base, "danbooru.csv")):
        t = os.path.join(base, "danbooru.csv")
    if not z and base:
        for n in ("danbooru-0-zh.csv", "zh_cn.csv", "danbooru-zh.csv"):
            if os.path.isfile(os.path.join(base, n)):
                z = os.path.join(base, n)
                break
    return t if os.path.isfile(t) else "", z if os.path.isfile(z) else ""


# ---------------------------------------------------------------------------
# StyleSelectorXL 樣式表（ALL.xlsx／ALL.json），規則和 Forge 擴充一致
# ---------------------------------------------------------------------------
_SHEET = {"path": None, "mtime": None, "styles": []}
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _read_xlsx(path):
    """只用標準函式庫讀第一個工作表（樣式表格式單純，不需要 openpyxl）。"""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        first = wb.find("m:sheets/m:sheet", NS)
        rid = first.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = next(r.get("Target") for r in rels if r.get("Id") == rid)
        sheet_path = "xl/" + target.lstrip("/").replace("xl/", "", 1) if not target.startswith("/xl/") else target.lstrip("/")
        root = ET.fromstring(z.read(sheet_path))
        rows = []
        for row in root.iter("{%s}row" % NS["m"]):
            cells = {}
            for c in row.findall("m:c", NS):
                ref = c.get("r") or ""
                col = 0
                for ch in re.match(r"[A-Z]+", ref).group(0):
                    col = col * 26 + (ord(ch) - 64)
                t = c.get("t")
                v = c.find("m:v", NS)
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
                else:
                    val = v.text if v is not None else ""
                cells[col - 1] = val or ""
            if cells:
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    if not rows:
        return []
    head = [str(h).strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        item = {head[i]: r[i] for i in range(min(len(head), len(r))) if head[i]}
        out.append(item)
    return out


def load_sheet(path):
    if not path:
        return []
    if not os.path.isfile(path):
        raise IllustError("找不到樣式表：%s" % path)
    mt = os.path.getmtime(path)
    if _SHEET["path"] == path and _SHEET["mtime"] == mt:
        return _SHEET["styles"]
    if path.lower().endswith(".xlsx"):
        raw = _read_xlsx(path)
    else:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    styles, seen = [], set()
    for it in raw:
        name = str(it.get("name") or "").strip()
        if not name or name in seen:     # 同名只取第一筆（和擴充一樣）
            continue
        seen.add(name)
        cats = [c.strip() for c in re.split(r"[,;，；]", str(it.get("category") or "")) if c.strip()]
        styles.append({"name": name, "prompt": str(it.get("prompt") or ""),
                       "natural": str(it.get("naturl_prompt") or it.get("natural_prompt") or ""),
                       "negative": str(it.get("negative_prompt") or ""),
                       "categories": cats, "zh": str(it.get("namezh") or ""), "en": str(it.get("nameen") or "")})
    _SHEET.update(path=path, mtime=mt, styles=styles)
    return styles


def _is_nsfw(st):
    return any(c.lower().startswith("nsfw") for c in st["categories"])


def sheet_index(path, show_nsfw=False):
    """給介面用：分類樹與每個樣式的簡短資訊。"""
    styles = load_sheet(path)
    out, cats = [], {}
    for st in styles:
        if not show_nsfw and _is_nsfw(st):
            continue
        out.append({"name": st["name"], "zh": st["zh"], "en": st["en"], "categories": st["categories"],
                    "prompt": st["prompt"][:160], "natural": st["natural"][:160]})
        for c in st["categories"]:
            cats[c] = cats.get(c, 0) + 1
    return {"styles": out, "categories": sorted(cats.items(), key=lambda x: x[0]), "total": len(styles)}


def resolve_dynamic(text, rng):
    """{A|B|C} 隨機選一個（可以巢狀）。"""
    pat = re.compile(r"\{([^{}]*\|[^{}]*)\}")
    for _ in range(20):
        m = pat.search(text)
        if not m:
            break
        text = text[:m.start()] + rng.choice(m.group(1).split("|")) + text[m.end():]
    return text


def apply_styles(core, natural_core, names, path, source="prompt", seed=0):
    """回傳 (正向, 負向片段, 實際用到的名稱)。規則同 StyleSelectorXL：{prompt} 換成原本的提示詞。"""
    if not names:
        return core, "", []
    by = {s["name"]: s for s in load_sheet(path)}
    rng = random.Random(seed)
    pos, negs, nats, used = core, [], [], []
    for n in names:
        st = by.get(n)
        if not st:
            continue
        used.append(n)
        if source in ("prompt", "both") or not st["natural"]:
            tpl = st["prompt"]
            if "{prompt}" in tpl:
                pos = tpl.replace("{prompt}", pos)
            elif tpl.strip():
                pos = (pos + ", " + tpl) if pos else tpl
        if source in ("naturl_prompt", "both") and st["natural"]:
            nats.append(st["natural"].replace("{prompt}", ""))
        if st["negative"].strip(" ,"):
            negs.append(st["negative"].strip(" ,"))
    pos = resolve_dynamic(pos, rng)
    nat = resolve_dynamic(" ".join(nats), rng)
    pos = re.sub(r"\s*,\s*(,\s*)+", ", ", pos).strip(" ,")
    pos = re.sub(r"\.\s*,\s*", ". ", pos)
    if nat.strip():
        pos = pos + ("\n" if pos else "") + re.sub(r"\s+", " ", nat).strip()
    return pos, resolve_dynamic(", ".join(negs), rng), used


# ---------------------------------------------------------------------------
# 組裝 Anima 提示詞
# ---------------------------------------------------------------------------
def _count_tags(chars):
    """依角色視覺卡裡的 1girl／1boy 算人數標籤。"""
    g = b = 0
    for c in chars:
        tl = [x.lower() for x in normalize_tags(c.get("tags", "")).split(", ")]
        if any(re.match(r"^\d*girls?$", x) for x in tl):
            g += 1
        elif any(re.match(r"^\d*boys?$", x) for x in tl):
            b += 1
    parts = []
    if g:
        parts.append("1girl" if g == 1 else "%dgirls" % g)
    if b:
        parts.append("1boy" if b == 1 else "%dboys" % b)
    if len(chars) == 1 and parts:
        parts.append("solo")
    return parts


def _strip_count(tags):
    return ", ".join(t for t in normalize_tags(tags).split(", ") if t and not COUNT_TAGS.match(t.lower()))


def _sentence(s):
    s = (s or "").strip()
    return s if not s or s[-1] in ".!?。" else s + "."


def assemble(spec, cfg, sheet_path=None):
    """spec：{format, quality, safety, artist, chars:[{name, tags, description, position, action}],
    scene_tags, action_tags, composition, sentences, extra, negative_extra, styles:[], style_source, seed}
    回傳 {positive, negative, styles_used}。"""
    fmt = spec.get("format") or cfg.get("format") or "mixed"
    quality = spec.get("quality", cfg.get("quality", ""))
    safety = spec.get("safety", cfg.get("safety", ""))
    artist = normalize_tags(spec.get("artist") or "")
    artist = ", ".join(a if a.startswith("@") else "@" + a for a in artist.split(", ") if a)
    chars = [c for c in spec.get("chars") or [] if (c.get("tags") or c.get("description") or c.get("action"))]
    head = normalize_tags(", ".join(x for x in [quality, safety] if x))
    count = _count_tags(chars)
    places = spec.get("places") or []
    scene = normalize_tags(", ".join(x for x in [spec.get("action_tags", ""), spec.get("scene_tags", "")]
                                     + [pl.get("tags", "") for pl in places]
                                     + [spec.get("composition", ""), spec.get("extra", "")] if x))
    place_desc = " ".join(_sentence(pl.get("description", "")) for pl in places if pl.get("description"))
    sentences = (spec.get("sentences") or "").strip()
    lines = []
    if fmt == "tags":
        tags = [head, ", ".join(count)]
        for c in chars:
            tags += [_strip_count(c.get("tags", "")), normalize_tags(c.get("action", ""))]
        tags += [artist, scene]
        lines.append(normalize_tags(", ".join(t for t in tags if t)))
    else:
        first = normalize_tags(", ".join(x for x in [head, ", ".join(count) if fmt == "mixed" else "", artist] if x))
        if first:
            lines.append(first + ".")
        if len(chars) >= 2:
            lines.append("The image depicts %d characters." % len(chars))
            pos_names = {"left": "Left side of the image", "right": "Right side of the image", "center": "Center of the image",
                         "back": "Background of the image"}
            auto = ["left", "right", "center", "back"]
            for i, c in enumerate(chars):
                p = (c.get("position") or "").lower() or auto[min(i, 3)]
                seg = pos_names.get(p, "Center of the image") + ": "
                bits = []
                if fmt == "mixed":
                    t = normalize_tags(", ".join(x for x in [c.get("tags", ""), c.get("action", "")] if x))
                    if t:
                        bits.append(t)
                desc = _sentence(c.get("description", ""))
                seg += ", ".join(bits) + ((". " if bits else "") + desc if desc else (". " if bits else ""))
                lines.append(seg.strip())
        elif chars:
            c = chars[0]
            if fmt == "mixed":
                t = normalize_tags(", ".join(x for x in [_strip_count(c.get("tags", "")), c.get("action", "")] if x))
                if t:
                    lines.append(t + ".")
            if c.get("description"):
                lines.append(_sentence(c["description"]))
        if fmt == "mixed" and scene:
            lines.append(scene + ".")
        if sentences:
            lines.append(sentences)
        if place_desc and fmt != "tags":
            lines.append(place_desc)
        elif fmt == "natural" and scene:
            lines.append("Scene elements: " + scene + ".")
    core = "\n".join(l for l in lines if l.strip())
    neg = normalize_tags(", ".join(x for x in [cfg.get("negative", ""), spec.get("negative_extra", "")] if x))
    styles = spec.get("styles") or []
    if styles and sheet_path:
        core, sneg, used = apply_styles(core, "", styles, sheet_path, spec.get("style_source") or cfg.get("style_source", "prompt"),
                                        int(spec.get("seed") or 0) if str(spec.get("seed") or "").lstrip("-").isdigit() else 0)
        if sneg:
            neg = normalize_tags(neg + ", " + sneg)
    else:
        used = []
    return {"positive": core, "negative": neg, "styles_used": used}


# ---------------------------------------------------------------------------
# 本書畫風設定（插圖/畫風.json）
# ---------------------------------------------------------------------------
BOOK_STYLE_DEFAULT = {"styles": [], "artist": "", "extra": "", "negative_extra": "", "width": None, "height": None,
                      "cover_width": 896, "cover_height": 1152}


def load_book_style(book_dir):
    d = dict(BOOK_STYLE_DEFAULT)
    d.update(_read_json(os.path.join(book_dir, ROOT, "畫風.json"), {}))
    return d


def save_book_style(book_dir, data):
    cur = load_book_style(book_dir)
    for k in BOOK_STYLE_DEFAULT:
        if k in data:
            cur[k] = data[k]
    _ensure_root(book_dir)
    _write_json(os.path.join(book_dir, ROOT, "畫風.json"), cur)
    return cur


# ---------------------------------------------------------------------------
# Forge 參數行（infotext 格式，例如從 PNG Info 複製的最後一行）
# ---------------------------------------------------------------------------
def params_from_forge_dir(forge_dir):
    p = os.path.join(forge_dir or "", "params.txt")
    if not os.path.isfile(p):
        raise IllustError("Forge 資料夾裡找不到 params.txt（要先在 Forge 生成過一張圖）")
    with open(p, encoding="utf-8", errors="replace") as f:
        lines = [l.strip() for l in f.read().split("\n") if l.strip()]
    line = next((l for l in reversed(lines) if re.match(r"^Steps:\s*\d+", l)), "")
    if not line:
        raise IllustError("params.txt 裡找不到參數行")
    return clean_params(line)


def clean_params(line):
    """去掉每次都不同或由工作台決定的欄位（Seed、Size、版本等）。"""
    keep = []
    for part in _split_params(line):
        key = part.split(":", 1)[0].strip()
        if key in ("Seed", "Size", "Version", "Model hash", "Variation seed", "Variation seed strength",
                   "Seed resize from", "Lora hashes", "TI hashes", "Emphasis"):
            continue
        keep.append(part.strip())
    return ", ".join(keep)


def _split_params(line):
    """依逗號切參數，但保留引號裡的逗號。"""
    out, buf, q = [], "", False
    for ch in line:
        if ch == '"':
            q = not q
        if ch == "," and not q:
            out.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf)
    return [x for x in out if x.strip()]


def params_size(line):
    m = re.search(r"Size:\s*(\d+)x(\d+)", line or "")
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


# ---------------------------------------------------------------------------
# 給 AI 的指示（產生場景描述、視覺卡）：只要一小段 JSON，其他由程式組裝
# ---------------------------------------------------------------------------
SCENE_SCHEMA = """只輸出一個 JSON 物件：
{"characters": [{"name": "角色名（照提供的名單）", "position": "left|right|center", "action": "這個角色的姿勢、表情、手上動作，英文 Danbooru 標籤，逗號分隔"}],
 "action_tags": "整體動作與互動的英文 Danbooru 標籤",
 "scene_tags": "地點、時間、天氣、光線、背景物件的英文 Danbooru 標籤",
 "composition": "構圖與鏡頭的英文 Danbooru 標籤，例如 cowboy shot, from side, dutch angle, close-up",
 "sentences": "兩到三句英文，描述畫面：誰、在做什麼、在哪裡、氣氛。角色用外觀稱呼（例如 the black-haired girl），不要用中文名字"}
規則：
- 標籤用空格不用底線，只寫畫面看得到的東西（不寫心理、不寫劇情因果）。
- 角色外觀（髮色、服裝等）已經在視覺卡裡，不要重複寫在 action 裡。
- 只畫一個瞬間；畫面裡最多三個角色，挑最重要的。
- 不要加品質標籤、畫師、safe 之類的分級標籤，工作台會自己加。"""

CARD_SCHEMA = """只輸出一個 JSON 物件：
{"tags": "外觀的英文 Danbooru 標籤，逗號分隔：人數（1girl／1boy）、髮型髮色、瞳色、體型、招牌服裝、配件；地點或物件則寫建築、材質、色調",
 "description": "一兩句英文，描述外觀與給人的感覺（不寫名字）"}
規則：標籤用空格不用底線；只寫固定不變的外觀，不寫動作、表情、場景；設定沒寫到的外觀可以合理補上，但不要和設定衝突。"""


def ai_scene_prompt(book_dir, target, passage, char_entries, place_entries, kind="chapter"):
    """回傳 (system, user)。char_entries/place_entries 是 entity_cards() 的項目。"""
    def card_line(e):
        c = e.get("card") or {}
        return "- %s（%s）：%s%s" % (e["name"], e["kind"], c.get("tags") or "（沒有視覺卡）",
                                   ("；" + c["description"]) if c.get("description") else "")
    parts = []
    if kind == "cover":
        core = project.read_text(os.path.join(book_dir, "設定", "故事核心.md")) if os.path.isfile(os.path.join(book_dir, "設定", "故事核心.md")) else ""
        parts.append("【任務】為這本小說的封面設計一個畫面：要能代表整本書的題材與氣氛，主角放在最顯眼的位置，不要放文字。")
        parts.append("【故事核心】\n" + project.split_frontmatter(core)[1][:2500])
    elif kind == "entity":
        parts.append("【任務】為這個設定項目畫一張設定圖（角色就是全身或半身立繪，地點或物件就是清楚的展示圖）。")
        if passage:
            parts.append("【設定內容】\n" + passage[:2500])
    else:
        parts.append("【任務】把下面這段小說片段畫成一張插畫。")
        parts.append("【片段】\n" + passage[:3000])
    if char_entries:
        parts.append("【出場角色與視覺卡】\n" + "\n".join(card_line(e) for e in char_entries))
    if place_entries:
        parts.append("【相關地點、物件】\n" + "\n".join(card_line(e) for e in place_entries))
    parts.append(SCENE_SCHEMA)
    system = "你是插畫分鏡師，把中文小說內容轉成給動畫風格繪圖模型（Anima，吃 Danbooru 標籤與英文自然語言）的畫面描述。只輸出 JSON。"
    return system, "\n\n".join(parts)


def ai_card_prompt(entry_text, name, kind):
    system = "你是角色設計師，把中文設定轉成給動畫風格繪圖模型用的固定外觀描述。只輸出 JSON。"
    user = "【%s：%s】\n%s\n\n%s" % (kind, name, project.split_frontmatter(entry_text)[1][:3000], CARD_SCHEMA)
    return system, user


def merge_scene(draft, data, char_entries):
    """把 AI 回傳的 JSON 併進草稿。"""
    draft = dict(draft or {})
    by = {e["name"]: e for e in char_entries}
    chars = []
    for c in (data or {}).get("characters") or []:
        e = by.get(str(c.get("name") or "").strip())
        if not e:
            continue
        card = e.get("card") or {}
        chars.append({"name": e["name"], "file": e["file"], "tags": card.get("tags", ""), "description": card.get("description", ""),
                      "position": str(c.get("position") or "").lower(), "action": normalize_tags(str(c.get("action") or ""))})
    if chars:
        draft["chars"] = chars
    for k in ("action_tags", "scene_tags", "composition"):
        if data.get(k):
            draft[k] = normalize_tags(str(data[k]))
    if data.get("sentences"):
        draft["sentences"] = str(data["sentences"]).strip()
    draft["updated"] = time.time()
    return draft
