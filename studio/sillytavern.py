# -*- coding: utf-8 -*-
"""
匯出至 SillyTavern（酒館）：
- World Info / Lorebook（.json）
- Character Card V2（.png，內嵌 base64 `chara` tEXt chunk）
- 世界觀 GM 跑團主持卡（.png）
- 一鍵整合包（.zip：世界書＋GM 卡＋角色卡＋使用說明）

只用 Python 標準函式庫（struct / zlib / base64 / zipfile），不需要 Pillow 或外部套件。
所有輸出檔案皆寫入書目錄的 export/，對設定集與原稿唯讀。
"""
import base64
import datetime
import json
import os
import re
import struct
import zipfile
import zlib

from . import export as export_mod, lang as lang_mod, layout, project

PNG_SIG = b"\x89PNG\r\n\x1a\n"
LORE_SECTIONS = ("core", "characters", "factions", "world", "glossary", "tracking")
MAX_ENTRY_CHARS = 2400

_GM_STR = {
    "zh-TW": {
        "gm_name": "{title} · GM 主持人",
        "gm_personality": "公平、重視世界觀一致性、善於描寫場景與 NPC 互動的 TRPG 遊戲主持人。",
        "gm_scenario": "玩家將作為一名初來乍到的旅人，進入《{title}》的世界展開自由探索與冒險。",
        "gm_first": (
            "歡迎來到《{title}》的世界。\n\n"
            "我是本場跑團的主持人（GM）。你可以先告訴我你的角色名字、身分與想出發的地點，"
            "或者直接輸入「開始」，讓我為你揭開故事的第一幕。"
        ),
        "char_first": "（{name} 抬頭看向你。）「……找我有事嗎？」",
        "char_scenario": "《{title}》的世界。你正與 {name} 面對面交談。",
        "readme": (
            "SillyTavern（酒館）匯入步驟：\n"
            "1. 角色卡 / GM 跑團卡（.png）：打開酒館 → 點上方「人物管理」→ 匯入 PNG 檔即可開始對話或跑團。\n"
            "2. 世界書（_lorebook.json）：點上方「世界書（World Info）」→ 匯入 JSON 檔並勾選啟用。\n"
            "   聊到角色、地名、勢力或專有名詞時，酒館會自動帶入對應設定。\n"
        ),
    },
    "en": {
        "gm_name": "{title} · Game Master",
        "gm_personality": "A fair, lore-faithful tabletop RPG Game Master skilled at vivid scenes and NPC roleplay.",
        "gm_scenario": "The player enters the world of \"{title}\" as a newcomer to explore and forge their own story.",
        "gm_first": (
            "Welcome to the world of \"{title}\".\n\n"
            "I am your Game Master. Tell me your character's name, background, and where you wish to begin, "
            "or simply say \"Start\" to open the first scene."
        ),
        "char_first": "*{name} looks up at you.* \"...Did you need something?\"",
        "char_scenario": "The world of \"{title}\". You are speaking face-to-face with {name}.",
        "readme": (
            "How to import into SillyTavern:\n"
            "1. Character / GM cards (.png): Open SillyTavern -> Character Management -> Import PNG.\n"
            "2. World Info (_lorebook.json): Open World Info -> Import JSON and enable it for your chat.\n"
        ),
    },
    "ja": {
        "gm_name": "{title} · GM（ゲームマスター）",
        "gm_personality": "世界観の一貫性を重視し、臨場感ある情景描写とNPC演出に長けたTRPGゲームマスター。",
        "gm_scenario": "プレイヤーは旅人として『{title}』の世界に足を踏み入れ、自由に冒険を繰り広げます。",
        "gm_first": (
            "『{title}』の世界へようこそ。\n\n"
            "私は本セッションのGMです。あなたのキャラクター名や立場、出発したい場所を教えてください。"
            "そのまま「開始」と入力すれば第一幕を始めます。"
        ),
        "char_first": "（{name}は顔を上げてこちらを見た。）「……何か用か？」",
        "char_scenario": "『{title}』の世界。あなたは{name}と向かい合って話している。",
        "readme": (
            "SillyTavern へのインポート手順：\n"
            "1. キャラクター／GMカード（.png）：キャラクター管理から PNG をインポートします。\n"
            "2. ワールド情報（_lorebook.json）：World Info から JSON をインポートして有効化してください。\n"
        ),
    },
}


# ---------------------------------------------------------------------------
# 純標準函式庫 PNG 產生與 V2 `chara` tEXt chunk 寫入
# ---------------------------------------------------------------------------

def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def make_placeholder_png(width: int = 256, height: int = 256, seed_text: str = "") -> bytes:
    """純標準庫建立暖紙書卷風漸層 PNG（無 Pillow 依賴）。"""
    h = zlib.crc32(seed_text.encode("utf-8")) & 0xFFFFFFFF
    # 基礎色：沿用 fekit 暖紙與朱紅／靛藍／松綠柔和邊框
    palettes = [
        ((138, 59, 46), (246, 242, 234)),   # 朱紅 / 紙白
        ((47, 90, 122), (240, 244, 247)),   # 靛藍 / 淡紙
        ((63, 107, 58), (242, 246, 240)),   # 松綠 / 淡紙
        ((138, 100, 16), (248, 244, 232)),  # 琥珀 / 暖紙
    ]
    accent, paper = palettes[h % len(palettes)]
    raw_rows = bytearray()
    border = 14
    for y in range(height):
        raw_rows.append(0)  # filter type 0
        t = y / max(1, height - 1)
        for x in range(width):
            in_border = x < border or x >= width - border or y < border or y >= height - border
            if in_border:
                r, g, b = accent
            else:
                # 柔紙漸層
                r = int(paper[0] * (1 - 0.14 * t) + accent[0] * (0.14 * t))
                g = int(paper[1] * (1 - 0.14 * t) + accent[1] * (0.14 * t))
                b = int(paper[2] * (1 - 0.14 * t) + accent[2] * (0.14 * t))
            raw_rows.extend((r, g, b))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw_rows), level=6)
    return PNG_SIG + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")


def embed_chara_chunk(png_bytes: bytes, card_dict: dict) -> bytes:
    """把 Character Card V2 JSON 以 base64 寫入 PNG 的 `chara` tEXt chunk（會先移除舊的 chara chunk）。"""
    if not png_bytes.startswith(PNG_SIG):
        raise export_mod.ExportError("圖片不是有效的 PNG 格式")
    payload = json.dumps(card_dict, ensure_ascii=False).encode("utf-8")
    b64 = base64.b64encode(payload)
    chara_chunk = _png_chunk(b"tEXt", b"chara\x00" + b64)

    out = bytearray(PNG_SIG)
    pos = len(PNG_SIG)
    n = len(png_bytes)
    inserted = False
    while pos + 8 <= n:
        length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        ctype = png_bytes[pos + 4:pos + 8]
        cdata = png_bytes[pos + 8:pos + 8 + length]
        end = pos + 12 + length
        if end > n:
            break
        # 略過舊的 chara tEXt chunk，避免重複
        if ctype == b"tEXt" and cdata.startswith(b"chara\x00"):
            pos = end
            continue
        if ctype == b"IEND" and not inserted:
            out.extend(chara_chunk)
            inserted = True
        out.extend(png_bytes[pos:end])
        pos = end
    if not inserted:
        out.extend(chara_chunk)
        out.extend(_png_chunk(b"IEND", b""))
    return bytes(out)


def read_chara_chunk(png_bytes: bytes) -> dict:
    """從 PNG 讀回 `chara` tEXt chunk（測試與驗證用）。"""
    if not png_bytes.startswith(PNG_SIG):
        return {}
    pos = len(PNG_SIG)
    n = len(png_bytes)
    while pos + 8 <= n:
        length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        ctype = png_bytes[pos + 4:pos + 8]
        cdata = png_bytes[pos + 8:pos + 8 + length]
        end = pos + 12 + length
        if end > n:
            break
        if ctype == b"tEXt" and cdata.startswith(b"chara\x00"):
            raw = base64.b64decode(cdata[6:])
            return json.loads(raw.decode("utf-8"))
        pos = end
    return {}


# ---------------------------------------------------------------------------
# 讀取書庫設定集與圖片（全部唯讀）
# ---------------------------------------------------------------------------

def _str_list(val) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        parts = re.split(r"[,，、;/\n]+", val)
    elif isinstance(val, (list, tuple)):
        parts = [str(x) for x in val]
    else:
        parts = [str(val)]
    out, seen = [], set()
    for p in parts:
        s = p.strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def _trim(text: str, limit: int = MAX_ENTRY_CHARS) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit].rstrip() + "\n…"


def _clean_md_entry(path: str) -> tuple[dict, str, str]:
    """讀單一 Markdown 設定檔，回傳 (frontmatter, name, body)。"""
    fm, body = project.split_frontmatter(project.read_text(path))
    stem = os.path.splitext(os.path.basename(path))[0]
    name = str(fm.get("name") or fm.get("title") or stem).strip() or stem
    return fm, name, body.strip()


def list_characters(book_dir: str) -> list[dict]:
    """列出本書所有正式角色（不含草稿）。"""
    cdir = layout.path(book_dir, layout.CHARACTERS)
    if not os.path.isdir(cdir):
        return []
    out = []
    for f in sorted(os.listdir(cdir)):
        if not f.endswith(".md") or f.startswith("."):
            continue
        p = os.path.join(cdir, f)
        if not os.path.isfile(p):
            continue
        fm, name, body = _clean_md_entry(p)
        out.append({
            "file": f,
            "stem": os.path.splitext(f)[0],
            "name": name,
            "aliases": _str_list(fm.get("aliases")),
            "role": str(fm.get("role") or "").strip(),
            "faction": str(fm.get("faction") or "").strip(),
            "tags": _str_list(fm.get("tags")),
            "body": body,
            "fm": fm,
            "path": p,
        })
    return out


def _list_md_folder(book_dir: str, rel_folder: str) -> list[dict]:
    folder = layout.path(book_dir, rel_folder)
    if not os.path.isdir(folder):
        return []
    out = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".md") or f.startswith("."):
            continue
        p = os.path.join(folder, f)
        if not os.path.isfile(p):
            continue
        fm, name, body = _clean_md_entry(p)
        if not body:
            continue
        out.append({
            "file": f,
            "name": name,
            "aliases": _str_list(fm.get("aliases")),
            "body": body,
            "fm": fm,
        })
    return out


def _parse_glossary(book_dir: str) -> list[dict]:
    """解析 bible/glossary.md 的 Markdown 表格列成獨立名詞條目。"""
    p = layout.path(book_dir, layout.GLOSSARY)
    if not os.path.isfile(p):
        return []
    _, body = project.split_frontmatter(project.read_text(p))
    rows = []
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|") or not s.endswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if all(re.fullmatch(r"[-:\s]+", c or "-") for c in cells):
            continue
        term = cells[0]
        if not term or term in ("名詞", "術語", "名稱", "Term", "Name", "用語"):
            continue
        rest = [c for c in cells[1:] if c]
        if not rest:
            continue
        rows.append({"term": term, "desc": "｜".join(rest)})
    return rows


def _find_png_avatar(book_dir: str, char_stem: str = "") -> bytes | None:
    """嘗試尋找角色的 PNG 設定圖，或封面 PNG；找不到就回傳 None（由呼叫端用佔位 PNG）。"""
    illust_dir = layout.path(book_dir, layout.ILLUST)
    candidates = []
    if char_stem and os.path.isdir(illust_dir):
        for root, _, files in os.walk(illust_dir):
            for f in sorted(files):
                if f.lower().endswith(".png") and char_stem.lower() in f.lower():
                    candidates.append(os.path.join(root, f))
    for cname in ("封面.png", "cover.png"):
        cp = os.path.join(book_dir, cname)
        if os.path.isfile(cp):
            candidates.append(cp)
    for p in candidates:
        try:
            with open(p, "rb") as fp:
                data = fp.read()
            if data.startswith(PNG_SIG):
                return data
        except OSError:
            continue
    return None


def _safe_filename(name: str, fallback: str = "export") -> str:
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (name or "").strip()).strip(" .")
    return s or fallback


# ---------------------------------------------------------------------------
# Lorebook（World Info）組裝
# ---------------------------------------------------------------------------

def build_lorebook(book_dir: str, sections: list[str] | None = None) -> dict:
    """組裝 SillyTavern World Info / Lorebook JSON dict。"""
    wanted = set(sections or LORE_SECTIONS)
    title = export_mod.book_title(book_dir)
    entries = {}
    uid = 0

    def add_entry(comment: str, keys: list[str], content: str, *, constant: bool = False, order: int = 100):
        nonlocal uid
        body = _trim(content)
        if not body:
            return
        clean_keys = _str_list(keys)
        if not clean_keys and not constant:
            clean_keys = [comment]
        entries[str(uid)] = {
            "uid": uid,
            "key": clean_keys,
            "keysecondary": [],
            "comment": comment,
            "content": body,
            "constant": bool(constant),
            "vectorized": False,
            "selective": True,
            "selectiveLogic": 0,
            "addMemo": True,
            "order": order,
            "position": 0,
            "disable": False,
            "excludeRecursion": False,
            "preventRecursion": False,
            "delayUntilRecursion": False,
            "probability": 100,
            "useProbability": True,
            "depth": 4,
            "group": "",
            "groupOverride": False,
            "groupWeight": 100,
            "scanDepth": None,
            "caseSensitive": None,
            "matchWholeWords": None,
            "useGroupScoring": None,
            "automationId": "",
            "role": None,
            "sticky": 0,
            "cooldown": 0,
            "delay": 0,
        }
        uid += 1

    if "core" in wanted:
        core_path = layout.path(book_dir, layout.STORY_CORE)
        if os.path.isfile(core_path):
            _, body = project.split_frontmatter(project.read_text(core_path))
            if body.strip():
                add_entry(f"{title} · 故事核心", [title], body, constant=True, order=10)

    if "characters" in wanted:
        for ch in list_characters(book_dir):
            keys = [ch["name"]] + ch["aliases"]
            head = f"角色：{ch['name']}"
            if ch["role"]:
                head += f"（{ch['role']}）"
            if ch["faction"]:
                head += f"｜勢力：{ch['faction']}"
            add_entry(f"角色：{ch['name']}", keys, head + "\n\n" + ch["body"], order=50)

    if "factions" in wanted:
        for item in _list_md_folder(book_dir, layout.FACTIONS):
            add_entry(f"勢力：{item['name']}", [item["name"]] + item["aliases"], item["body"], order=60)

    if "world" in wanted:
        for item in _list_md_folder(book_dir, layout.WORLD):
            add_entry(f"世界觀：{item['name']}", [item["name"]] + item["aliases"], item["body"], order=70)

    if "glossary" in wanted:
        for row in _parse_glossary(book_dir):
            add_entry(f"名詞：{row['term']}", [row["term"]], f"{row['term']}：{row['desc']}", order=80)

    if "tracking" in wanted:
        for rel, label, order in (
            (layout.TIMELINE, "時間線", 90),
            (layout.RELATIONS, "角色關係", 92),
            (layout.STATE_CARD, "當前狀態卡", 95),
        ):
            p = layout.path(book_dir, rel)
            if os.path.isfile(p):
                _, body = project.split_frontmatter(project.read_text(p))
                if body.strip():
                    add_entry(f"{title} · {label}", [title, label], body, order=order)

    return {"entries": entries}


# ---------------------------------------------------------------------------
# Character Card V2（角色卡 / GM 跑團主持卡）
# ---------------------------------------------------------------------------

def _make_v2_card(*, name: str, description: str, personality: str, scenario: str,
                  first_mes: str, tags: list[str], creator_notes: str = "") -> dict:
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": name,
            "description": _trim(description, 6000),
            "personality": _trim(personality, 1500),
            "scenario": _trim(scenario, 2500),
            "first_mes": first_mes,
            "mes_example": "",
            "creator_notes": creator_notes or "Exported from Novel Studio",
            "system_prompt": "",
            "post_history_instructions": "",
            "alternate_greetings": [],
            "tags": _str_list(tags),
            "creator": "Novel Studio",
            "character_version": "1.0",
            "extensions": {},
        },
    }


def build_gm_card(book_dir: str) -> dict:
    """建立本書的 TRPG 世界觀 GM 跑團主持卡（V2）。"""
    title = export_mod.book_title(book_dir)
    lang = lang_mod.book_lang(book_dir)
    s = _GM_STR.get(lang, _GM_STR["zh-TW"])

    parts = []
    core_path = layout.path(book_dir, layout.STORY_CORE)
    if os.path.isfile(core_path):
        _, body = project.split_frontmatter(project.read_text(core_path))
        if body.strip():
            parts.append(body.strip())

    chars = list_characters(book_dir)
    if chars:
        names = "、".join(c["name"] for c in chars[:12])
        parts.append(f"主要登場角色：{names}")

    factions = _list_md_folder(book_dir, layout.FACTIONS)
    if factions:
        fnames = "、".join(f["name"] for f in factions[:10])
        parts.append(f"主要勢力：{fnames}")

    desc = "\n\n".join(parts) or f"《{title}》的世界觀與舞台。"
    return _make_v2_card(
        name=s["gm_name"].format(title=title),
        description=desc,
        personality=s["gm_personality"],
        scenario=s["gm_scenario"].format(title=title),
        first_mes=s["gm_first"].format(title=title),
        tags=["TRPG", "GM", "Novel Studio", title],
        creator_notes=f"World GM card for {title} (exported from Novel Studio). Pair with the Lorebook JSON.",
    )


def build_character_card(book_dir: str, char_stem: str) -> tuple[dict, dict]:
    """依角色檔名（不含 .md）建立 SillyTavern V2 角色卡，回傳 (card_dict, char_info)。"""
    chars = list_characters(book_dir)
    target = next((c for c in chars if c["stem"] == char_stem or c["name"] == char_stem), None)
    if target is None:
        raise export_mod.ExportError(f"找不到角色設定檔：{char_stem}")

    title = export_mod.book_title(book_dir)
    lang = lang_mod.book_lang(book_dir)
    s = _GM_STR.get(lang, _GM_STR["zh-TW"])

    # 故事核心簡摘作為 scenario 背景
    scenario = s["char_scenario"].format(title=title, name=target["name"])
    core_path = layout.path(book_dir, layout.STORY_CORE)
    if os.path.isfile(core_path):
        _, core_body = project.split_frontmatter(project.read_text(core_path))
        if core_body.strip():
            scenario += "\n\n" + _trim(core_body.strip(), 800)

    meta_lines = []
    if target["aliases"]:
        meta_lines.append("別名：" + "、".join(target["aliases"]))
    if target["role"]:
        meta_lines.append("定位：" + target["role"])
    if target["faction"]:
        meta_lines.append("所屬勢力：" + target["faction"])
    desc = ("\n".join(meta_lines) + "\n\n" if meta_lines else "") + target["body"]

    card = _make_v2_card(
        name=target["name"],
        description=desc,
        personality=", ".join(target["tags"]) if target["tags"] else target["role"],
        scenario=scenario,
        first_mes=s["char_first"].format(name=target["name"]),
        tags=["Novel Studio", title] + target["tags"],
        creator_notes=f"Character from {title} (exported from Novel Studio).",
    )
    return card, target


# ---------------------------------------------------------------------------
# 公開 API：資訊查詢與實際匯出寫檔
# ---------------------------------------------------------------------------

def meta(book_dir: str) -> dict:
    """回傳酒館匯出面板所需的角色清單與資料統計。"""
    chars = list_characters(book_dir)
    factions = _list_md_folder(book_dir, layout.FACTIONS)
    worlds = _list_md_folder(book_dir, layout.WORLD)
    glossary = _parse_glossary(book_dir)
    return {
        "book_title": export_mod.book_title(book_dir),
        "characters": [{"stem": c["stem"], "name": c["name"], "role": c["role"]} for c in chars],
        "counts": {
            "characters": len(chars),
            "factions": len(factions),
            "world": len(worlds),
            "glossary": len(glossary),
        },
    }


def _write_binary_atomic(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def export_sillytavern(book_dir: str, opts: dict | None = None) -> dict:
    """執行酒館匯出並寫入 `<book>/export/`。

    opts:
      - mode: "lorebook" | "gm" | "character" | "bundle"（預設 "bundle"）
      - character: 當 mode == "character" 時的角色 stem
      - sections: list[str]，世界書要收錄的區塊（預設全部）
    """
    opts = opts or {}
    mode = str(opts.get("mode") or "bundle").strip().lower()
    if mode not in ("lorebook", "gm", "character", "bundle"):
        raise export_mod.ExportError(f"不支援的酒館匯出模式：{mode}")

    sections = opts.get("sections") or list(LORE_SECTIONS)
    title = export_mod.book_title(book_dir)
    safe_title = _safe_filename(title, "novel")
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    out_dir = os.path.join(book_dir, export_mod.OUT_DIR)
    os.makedirs(out_dir, exist_ok=True)

    if mode == "lorebook":
        lore = build_lorebook(book_dir, sections)
        fname = f"{safe_title}_lorebook_{stamp}.json"
        dest = os.path.join(out_dir, fname)
        raw = json.dumps(lore, ensure_ascii=False, indent=2)
        project.write_atomic(dest, raw)
        return {"file": fname, "size": os.path.getsize(dest), "mode": mode, "entries": len(lore["entries"])}

    if mode == "gm":
        card = build_gm_card(book_dir)
        base_png = _find_png_avatar(book_dir) or make_placeholder_png(seed_text=title + ":gm")
        png_bytes = embed_chara_chunk(base_png, card)
        fname = f"{safe_title}_GM_card_{stamp}.png"
        dest = os.path.join(out_dir, fname)
        _write_binary_atomic(dest, png_bytes)
        return {"file": fname, "size": os.path.getsize(dest), "mode": mode, "cards": 1}

    if mode == "character":
        char_stem = str(opts.get("character") or "").strip()
        if not char_stem:
            raise export_mod.ExportError("請選擇要匯出的角色")
        card, info = build_character_card(book_dir, char_stem)
        base_png = _find_png_avatar(book_dir, info["stem"]) or make_placeholder_png(seed_text=info["name"])
        png_bytes = embed_chara_chunk(base_png, card)
        fname = f"{_safe_filename(info['name'], info['stem'])}_st_card_{stamp}.png"
        dest = os.path.join(out_dir, fname)
        _write_binary_atomic(dest, png_bytes)
        return {"file": fname, "size": os.path.getsize(dest), "mode": mode, "cards": 1}

    # bundle：一鍵整合包（世界書 + GM 卡 + 全部正式角色卡 + 使用說明）
    lore = build_lorebook(book_dir, sections)
    gm_card = build_gm_card(book_dir)
    gm_png = embed_chara_chunk(_find_png_avatar(book_dir) or make_placeholder_png(seed_text=title + ":gm"), gm_card)
    chars = list_characters(book_dir)
    lang = lang_mod.book_lang(book_dir)
    readme = _GM_STR.get(lang, _GM_STR["zh-TW"])["readme"]

    fname = f"{safe_title}_sillytavern_{stamp}.zip"
    dest = os.path.join(out_dir, fname)
    tmp = dest + ".tmp"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme.encode("utf-8"))
        zf.writestr(f"{safe_title}_lorebook.json", json.dumps(lore, ensure_ascii=False, indent=2).encode("utf-8"))
        zf.writestr(f"cards/{safe_title}_GM.png", gm_png)
        for ch in chars:
            card, info = build_character_card(book_dir, ch["stem"])
            base_png = _find_png_avatar(book_dir, info["stem"]) or make_placeholder_png(seed_text=info["name"])
            zf.writestr(
                f"cards/{_safe_filename(info['name'], info['stem'])}.png",
                embed_chara_chunk(base_png, card),
            )
    os.replace(tmp, dest)
    return {
        "file": fname,
        "size": os.path.getsize(dest),
        "mode": mode,
        "entries": len(lore["entries"]),
        "cards": 1 + len(chars),
    }
