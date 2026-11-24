# -*- coding: utf-8 -*-
"""結構化角色視覺卡（相容漫畫改編 bible_check 規格與 VN 視覺小說分層需求）。

檔案位置：<書籍目錄>/bible/visual-cards/<id>.md
- 採用獨立檔案，不改動 bible/characters/<角色名>.md 既有的小說寫作 frontmatter。
- 欄位形狀相容漫畫卡範本（id / name / aliases / status / sections / outfits），
  並於 `vn` 區塊擴充視覺小說所需的頭像配件、立繪姿態與 7 種基礎表情（預設平靜）。
- 儲存或 AI 產生時，可透過 to_legacy_card() 同步摘要回原角色檔的「## 繪圖提示」。
"""
import hashlib
import os
import re
import yaml

from . import layout, project, tracking

SECTION_KEYS = ("head", "body", "upper", "lower", "accessory")
OUTFIT_PARTS = ("top", "bottom", "set")
VN_EXPRESSIONS = ("neutral", "happy", "angry", "sad", "serious", "worried", "surprised")
VN_EXPRESSION_LABELS = {
    "neutral": "平靜",
    "happy": "喜",
    "angry": "怒",
    "sad": "哀",
    "serious": "認真",
    "worried": "擔心",
    "surprised": "驚訝",
}
DEFAULT_VN_EXPRESSIONS = {
    "neutral": "calm look, neutral expression, closed mouth",
    "happy": "warm smile, gentle eyes",
    "angry": "furrowed brows, sharp glare, frowning",
    "sad": "downcast eyes, melancholic expression, slight frown",
    "serious": "focused eyes, stern expression, composed",
    "worried": "furrowed brow, worried eyes, slightly parted lips",
    "surprised": "wide eyes, raised eyebrows, slightly open mouth",
}
DEFAULT_SPRITE_POSE = "standing straight, relaxed posture, facing viewer"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# bible_check 規則比對用
_AGE_RE = re.compile(
    r"(?:\b\d{1,3}\s*-?\s*year\s*-?\s*old\b"
    r"|\b(?:early|mid|late)?\s*-?\s*(?:twenties|thirties|forties|fifties|sixties|seventies|eighties|teens)\b"
    r"|\b(?:young|middle-aged|elderly|older|aged|adult|mature|senior)\b)",
    re.I,
)
_GENDER_RE = re.compile(
    r"\b(?:man|woman|male|female|gentleman|lady|boy|girl|nonbinary|non-binary|person|youth)\b",
    re.I,
)
_CLOTHING_RE = re.compile(
    r"\b(?:t-shirt|shirt|blouse|jacket|coat|overcoat|trench\s*coat|cloak|robe|hanfu|kimono|dress|skirt"
    r"|trousers|pants|jeans|shorts|suit|uniform|vest|sweater|hoodie|cardigan|apron|boots|shoes|sneakers"
    r"|sandals|socks|stockings|gloves|cape|armor|armour|tunic|sleeves|collar|tie|necktie|scarf)\b",
    re.I,
)
_EMOTION_RE = re.compile(
    r"\b(?:smil(?:e|es|ing)|grin(?:s|ning)?|frown(?:s|ing)?|angry|furious|sad|cry(?:ing)?|tears|weeping"
    r"|happy|cheerful|laugh(?:s|ing)?|scowl(?:s|ing)?|smirk(?:s|ing)?|pout(?:s|ing)?|blush(?:es|ing)?"
    r"|shocked|surprised|worried|anxious|glar(?:e|es|ing)|nervous|terrified|expressionless"
    r"|neutral expression|calm look)\b",
    re.I,
)
_ACTION_RE = re.compile(
    r"\b(?:standing|sitting|running|walking|jumping|holding|fighting|pointing|kneeling|leaning"
    r"|crouching|lying down|looking back|arms crossed|hands on hips|waving|swinging|drawing a sword)\b",
    re.I,
)
_HEAD_ACCESSORY_RE = re.compile(
    r"\b(?:glasses|spectacles|monocle|earrings?|necklace|pendant|choker|hairpin|hairclip|headband|tiara|crown|hat|cap)\b",
    re.I,
)


def _str_list(val):
    """把字串或清單正規化成乾淨的字串清單。"""
    if val is None:
        return []
    if isinstance(val, str):
        items = [x.strip() for x in re.split(r"[\n;]+", val) if x.strip()]
    elif isinstance(val, (list, tuple)):
        items = [str(x).strip() for x in val if str(x).strip()]
    else:
        items = [str(val).strip()] if str(val).strip() else []
    out, seen = [], set()
    for s in items:
        low = s.lower()
        if low not in seen:
            seen.add(low)
            out.append(s)
    return out


def slugify_id(raw_id, fallback_name=""):
    """轉成符合 [a-z0-9_-] 的角色卡 ID。"""
    s = re.sub(r"[^a-z0-9_-]+", "_", str(raw_id or "").strip().lower()).strip("_-")
    if s and ID_RE.match(s):
        return s
    seed = str(fallback_name or raw_id or "char").strip()
    s2 = re.sub(r"[^a-z0-9_-]+", "_", seed.lower()).strip("_-")
    if s2 and ID_RE.match(s2):
        return s2
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    return "char_" + h


def normalize_card(data, *, name="", aliases=None, source="", body="", fill_vn_defaults=False):
    """將模型回傳或前端表單的 dict 正規化成標準視覺卡結構。"""
    d = dict(data or {})
    card_name = str(d.get("name") or name or "").strip()
    card_id = slugify_id(d.get("id") or "", fallback_name=card_name)
    raw_aliases = d.get("aliases") if d.get("aliases") is not None else (aliases or [])
    card_aliases = _str_list(raw_aliases)
    status = str(d.get("status") or "draft").strip().lower()
    if status not in ("draft", "confirmed"):
        status = "draft"

    raw_sec = d.get("sections") if isinstance(d.get("sections"), dict) else {}
    sections = {k: _str_list(raw_sec.get(k)) for k in SECTION_KEYS}

    raw_outfits = d.get("outfits") if isinstance(d.get("outfits"), dict) else {}
    outfits = {}
    for oid, oval in raw_outfits.items():
        if not isinstance(oval, dict):
            continue
        okey = slugify_id(oid, fallback_name="default")
        outfits[okey] = {
            "top": _str_list(oval.get("top")),
            "bottom": _str_list(oval.get("bottom")),
            "set": _str_list(oval.get("set")),
            "notes": str(oval.get("notes") or "").strip(),
        }
    if "default" not in outfits:
        outfits["default"] = {"top": [], "bottom": [], "set": [], "notes": "日常"}

    raw_vn = d.get("vn") if isinstance(d.get("vn"), dict) else {}
    avatar_acc = _str_list(raw_vn.get("avatar_accessories"))
    if not avatar_acc and fill_vn_defaults and sections["accessory"]:
        avatar_acc = [a for a in sections["accessory"] if _HEAD_ACCESSORY_RE.search(a)]
    sprite_pose = str(raw_vn.get("sprite_pose") or "").strip()
    if not sprite_pose and fill_vn_defaults:
        sprite_pose = DEFAULT_SPRITE_POSE
    raw_expr = raw_vn.get("expressions") if isinstance(raw_vn.get("expressions"), dict) else {}
    expressions = {}
    for k in VN_EXPRESSIONS:
        v = str(raw_expr.get(k) or "").strip()
        if not v and fill_vn_defaults:
            v = DEFAULT_VN_EXPRESSIONS[k]
        expressions[k] = v

    card_body = str(d.get("body") if d.get("body") is not None else body).strip()
    card_source = str(d.get("source") or source or "").strip().replace("\\", "/")

    return {
        "id": card_id,
        "name": card_name,
        "aliases": card_aliases,
        "status": status,
        "source": card_source,
        "sections": sections,
        "outfits": outfits,
        "vn": {
            "avatar_accessories": avatar_acc,
            "sprite_pose": sprite_pose,
            "expressions": expressions,
        },
        "body": card_body,
    }


def parse_card(text):
    """讀取視覺卡 Markdown（YAML frontmatter + 本文）。"""
    if not text:
        return None
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n(.*))?$", text.lstrip("\ufeff"), flags=re.S)
    if not m:
        return None
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None
    body = (m.group(2) or "").strip()
    return normalize_card(meta, body=body, fill_vn_defaults=False)


def render_card(card, *, include_vn=True):
    """序列化成標準視覺卡 Markdown。include_vn=False 時輸出純漫畫卡（相容 t2c/bible.py）。"""
    c = normalize_card(card, fill_vn_defaults=False)
    meta = {
        "id": c["id"],
        "name": c["name"],
        "aliases": c["aliases"],
        "status": c["status"],
    }
    if include_vn and c.get("source"):
        meta["source"] = c["source"]
    meta["sections"] = {k: list(c["sections"].get(k) or []) for k in SECTION_KEYS}
    meta["outfits"] = {
        oid: {
            "top": list(oval.get("top") or []),
            "bottom": list(oval.get("bottom") or []),
            "set": list(oval.get("set") or []),
            "notes": oval.get("notes") or "",
        }
        for oid, oval in c["outfits"].items()
    }
    if include_vn:
        meta["vn"] = {
            "avatar_accessories": list(c["vn"].get("avatar_accessories") or []),
            "sprite_pose": c["vn"].get("sprite_pose") or "",
            "expressions": {k: (c["vn"].get("expressions") or {}).get(k, "") for k in VN_EXPRESSIONS},
        }
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=120).strip()
    body = (c.get("body") or "").strip()
    if body:
        return "---\n%s\n---\n\n%s\n" % (fm, body)
    return "---\n%s\n---\n" % fm


def check_card(card):
    """依範本規則（bible_check）與 VN 規格檢查視覺卡。回傳 {ok, errors, warnings}。"""
    errors, warnings = [], []
    if not isinstance(card, dict):
        return {"ok": False, "errors": ["視覺卡資料格式錯誤"], "warnings": []}

    cid = str(card.get("id") or "").strip()
    if not cid or not ID_RE.match(cid):
        errors.append("id 必須為英文小寫、數字、底線或連字號（[a-z0-9_-]）")
    if not str(card.get("name") or "").strip():
        errors.append("缺少必填欄位：name")

    secs = card.get("sections") if isinstance(card.get("sections"), dict) else {}
    head = _str_list(secs.get("head"))
    if not head:
        errors.append("sections.head 不可為空（需含年齡、性別、髮型髮色、眼型眼色等）")
    else:
        head_joined = ", ".join(head)
        if not _AGE_RE.search(head_joined):
            errors.append("sections.head 必須包含年齡描述（例如 a 34-year-old woman 或 young adult）")
        if not _GENDER_RE.search(head_joined):
            errors.append("sections.head 必須包含性別描述（例如 woman / man）")
        for item in head:
            if _HEAD_ACCESSORY_RE.search(item):
                warnings.append("sections.head 出現配件詞「%s」，建議移到 sections.accessory" % item)

    for sec_key in ("head", "body", "upper", "lower"):
        for item in _str_list(secs.get(sec_key)):
            m_cl = _CLOTHING_RE.search(item)
            if m_cl:
                errors.append("sections.%s 不可包含服裝詞「%s」（應放進 outfits）" % (sec_key, m_cl.group(0)))
            m_em = _EMOTION_RE.search(item)
            if m_em:
                errors.append("sections.%s 不可包含表情詞「%s」（頭像不含表情）" % (sec_key, m_em.group(0)))
            m_ac = _ACTION_RE.search(item)
            if m_ac:
                errors.append("sections.%s 不可包含動作詞「%s」" % (sec_key, m_ac.group(0)))

    outfits = card.get("outfits") if isinstance(card.get("outfits"), dict) else {}
    if "default" not in outfits:
        errors.append("缺少必填服裝：outfits.default")
    for oid, oval in outfits.items():
        if not isinstance(oval, dict):
            errors.append("outfits.%s 格式錯誤" % oid)
            continue
        all_items = _str_list(oval.get("top")) + _str_list(oval.get("bottom")) + _str_list(oval.get("set"))
        if not all_items:
            errors.append("outfits.%s 至少需填寫一項（top / bottom / set）" % oid)
        for item in all_items:
            m_em = _EMOTION_RE.search(item)
            if m_em:
                errors.append("outfits.%s 不可包含表情詞「%s」" % (oid, m_em.group(0)))
            m_ac = _ACTION_RE.search(item)
            if m_ac:
                errors.append("outfits.%s 不可包含動作詞「%s」" % (oid, m_ac.group(0)))

    vn = card.get("vn") if isinstance(card.get("vn"), dict) else {}
    exprs = vn.get("expressions") if isinstance(vn.get("expressions"), dict) else {}
    missing_expr = [k for k in VN_EXPRESSIONS if not str(exprs.get(k) or "").strip()]
    if missing_expr:
        warnings.append("VN 表情尚未填齊：%s" % "、".join(VN_EXPRESSION_LABELS.get(k, k) for k in missing_expr))
    if not str(vn.get("sprite_pose") or "").strip():
        warnings.append("VN 立繪預設動作（vn.sprite_pose）尚未填寫")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def look_en(card, outfit="default"):
    """將 sections 五段與指定服裝串接成完整英文外觀描述。"""
    c = normalize_card(card, fill_vn_defaults=False)
    parts = []
    for k in SECTION_KEYS:
        parts.extend(c["sections"].get(k) or [])
    ov = c["outfits"].get(outfit) or c["outfits"].get("default") or {}
    for pk in OUTFIT_PARTS:
        parts.extend(ov.get(pk) or [])
    return ", ".join(p for p in parts if p)


def to_legacy_card(card):
    """轉成舊版「## 繪圖提示」相容的 {tags, description}，讓現有章節插圖自動同步。"""
    c = normalize_card(card, fill_vn_defaults=False)
    tags_parts = []
    head_joined = " ".join(c["sections"].get("head") or []).lower()
    if re.search(r"\b(?:woman|female|girl|lady)\b", head_joined):
        tags_parts.append("1girl")
    elif re.search(r"\b(?:man|male|boy|gentleman)\b", head_joined):
        tags_parts.append("1boy")
    for k in ("head", "body", "accessory"):
        tags_parts.extend(c["sections"].get(k) or [])
    ov = c["outfits"].get("default") or {}
    for pk in OUTFIT_PARTS:
        tags_parts.extend(ov.get(pk) or [])
    desc = look_en(c, outfit="default")
    return {"tags": ", ".join(tags_parts), "description": desc}


def compose_vn_prompts(card, outfit="default"):
    """依 VN 規格組裝頭像（頸部以上、預設平靜）、立繪（頸部以下＋動作）與 7 種表情提示詞。"""
    c = normalize_card(card, fill_vn_defaults=True)
    if outfit not in c["outfits"]:
        outfit = "default"
    ov = c["outfits"].get(outfit) or {}
    exprs = c["vn"]["expressions"]

    # 頭像（頸部以上：髮型髮色、眼型眼色、頭飾、耳環、項鍊、特殊特徵；不含表情）
    avatar_parts = list(c["sections"]["head"])
    for acc in c["vn"]["avatar_accessories"]:
        if acc.lower() not in {p.lower() for p in avatar_parts}:
            avatar_parts.append(acc)
    avatar_base = ", ".join(avatar_parts + ["portrait, head and neck only, facing viewer, simple background"])

    avatar_by_expr = {}
    for k in VN_EXPRESSIONS:
        ex = exprs.get(k) or DEFAULT_VN_EXPRESSIONS[k]
        avatar_by_expr[k] = ", ".join(avatar_parts + [ex, "portrait, head and neck only, facing viewer, simple background"])

    # 立繪（頸部以下：身體、永久特徵、衣服、動作）
    body_parts = (
        list(c["sections"]["body"])
        + list(c["sections"]["upper"])
        + list(c["sections"]["lower"])
        + list(ov.get("top") or [])
        + list(ov.get("bottom") or [])
        + list(ov.get("set") or [])
    )
    pose = c["vn"]["sprite_pose"] or DEFAULT_SPRITE_POSE
    sprite_body = ", ".join(body_parts + [pose])

    # 完整立繪（頭部＋配件＋頸部以下＋動作＋各表情）
    full_base = list(c["sections"]["head"]) + list(c["sections"]["accessory"]) + body_parts + [pose]
    # 去重（保序）
    dedup, seen = [], set()
    for p in full_base:
        low = p.lower()
        if low not in seen:
            seen.add(low)
            dedup.append(p)
    sprite_by_expr = {}
    for k in VN_EXPRESSIONS:
        ex = exprs.get(k) or DEFAULT_VN_EXPRESSIONS[k]
        sprite_by_expr[k] = ", ".join(dedup + [ex, "visual novel character sprite, simple background"])

    return {
        "outfit": outfit,
        "outfits": [{"id": oid, "notes": (val.get("notes") or "")} for oid, val in c["outfits"].items()],
        "avatar_base": avatar_base,
        "avatar_default": avatar_by_expr["neutral"],
        "avatar_by_expression": avatar_by_expr,
        "sprite_body": sprite_body,
        "sprite_by_expression": sprite_by_expr,
        "expressions": [
            {"key": k, "label": VN_EXPRESSION_LABELS[k], "prompt": exprs.get(k) or "", "default": k == "neutral"}
            for k in VN_EXPRESSIONS
        ],
    }


def card_rel(card_id):
    return "%s/%s.md" % (layout.VISUAL_CARDS, slugify_id(card_id))


def list_cards(book_dir):
    """列出本書所有結構化視覺卡。"""
    root = layout.path(book_dir, layout.VISUAL_CARDS)
    if not os.path.isdir(root):
        return []
    out = []
    for fn in sorted(os.listdir(root)):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(root, fn)
        if not os.path.isfile(p):
            continue
        card = parse_card(project.read_text(p))
        if not card:
            continue
        out.append({
            "file": layout.VISUAL_CARDS + "/" + fn,
            "card": card,
            "check": check_card(card),
        })
    return out


def find_by_source(book_dir, char_rel, char_name=""):
    """依角色檔相對路徑（或角色名稱）找到對應的結構化視覺卡。"""
    norm_rel = (char_rel or "").replace("\\", "/")
    cards = list_cards(book_dir)
    for item in cards:
        if item["card"].get("source") == norm_rel:
            return item
    if char_name:
        for item in cards:
            if item["card"].get("name") == char_name:
                return item
    return None


def save_card(book_dir, card, *, backup_tag="視覺卡"):
    """原子寫入 bible/visual-cards/<id>.md（覆蓋前先備份）。回傳 (rel, card, check)。"""
    c = normalize_card(card, fill_vn_defaults=False)
    rel = card_rel(c["id"])
    path = project.safe_path(book_dir, rel)
    if os.path.isfile(path):
        tracking.backup(book_dir, path, backup_tag)
    project.write_atomic(path, render_card(c, include_vn=True))
    return rel, c, check_card(c)
