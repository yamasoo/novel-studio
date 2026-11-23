# -*- coding: utf-8 -*-
"""建專案（P6 Step 5）：用風格指紋與結構 DNA 建出一本新書的骨架。

產出的是「可以馬上開始填」的書，不是成品：
  資料夾骨架、18 份 _範本、CLAUDE.md、bible/style.md（含文字指標）、
  bible/structure/structure.md、指紋與 DNA 的副本、前三章章綱的空白模板。

不呼叫模型、不改任何既有檔案；目標資料夾不是空的就拒絕。
"""
import json
import os
import shutil

from . import datakeys, fingerprint, project, sdna
from . import layout, sections

KEY_DIRS = (layout.MANUSCRIPT, layout.CANDIDATES, layout.CHAPTER_CARDS, layout.VOLUMES_SUBDIR, layout.SUMMARIES, layout.CHARACTER_STATES,
            layout.CHARACTERS, layout.FACTIONS, layout.WORLD, layout.BIBLE_STRUCTURE, layout.SAMPLES)
LIVE_FILES = (layout.STORY_CORE, layout.GLOSSARY, layout.AUTHOR_PREFS,
              layout.FORESHADOWING, layout.TIMELINE, layout.STATE_CARD,
              layout.READER_KNOWLEDGE, layout.RELATIONS,
              layout.BOOK_OUTLINE, layout.OUTLINE_VOLUME_ONE)
CARD_SECTIONS = """## 本章四問
1. 主角這章想做什麼：
2. 誰或什麼阻止他：
3. 這章結束後局面變成什麼：
4. 讀者為什麼還要往下看：

## 本章功能與目標情緒
- 功能：
- 讀者看完的主要感受：

## 情節點
1.
2.
3.

## 出場角色
-

## 篇章鉤子
- 停在："""


def template_dir():
    """範本從示範書拿（它被 check_parity 盯著，一定有 18 份）。"""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "demo", "退婚之後", layout.TEMPLATES)


def _write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def _lang_label(lang):
    return {"zh-TW": "台灣繁體中文（用語、標點依台灣習慣）",
            "en": "English (US spelling and punctuation)",
            "ja": "日本語（表記は日本語の慣例に従う）"}.get(lang, lang)


def style_md(title, fp, dna):
    fp = datakeys.to_en(fp or {}, datakeys.FINGERPRINT)
    dna = datakeys.to_en(dna or {}, datakeys.DNA)
    m = fp.get("metrics") or {}
    d = dna
    pov = (d.get("pov") or {}).get("person") or "（待填）"
    ratio = ((d.get("dialogue") or {}).get("ratio"))
    # 文風檔的「文字指標」表照舊用中文指標名稱（parse_metrics 讀的是這一套）
    rows = "\n".join("| %s | %s |" % (k, v) for k, v in datakeys.metrics_zh(m).items()) or "| （待量測） | |"
    return """---
type: style
status: draft
---

# 《%s》本書文風

> 由 P6「A 書→B 書」的骨架產生。數字是參考書的實測值，你可以改；改完按章節頁的「重新量測」就會更新。

## 基本設定
- 敘事視角：%s
- 語言地區：%s
- 標點：引號用「」，引號內再引用用『』；刪節號用「……」；破折號用「——」

## 句子與節奏
- 平均句長約 %s 字、短句比例 %s
- 平均段長約 %s 字、單句成段 %s

## 對白
- 對白比例約 %s
%s
## 情緒寫法
（待填：你想怎麼讓讀者感覺到情緒？例：不直接寫「他很難過」，用動作和物件。）

## 本書禁忌
（待填：例：不用網路流行語、不寫上帝視角預告、不在章尾寫感悟。）

## 允許的例外
-

## 範例段落
（貼兩三段你滿意的文字，並寫一句你喜歡它哪裡。）

## 文字指標（程式統計）
| 指標 | 數值 |
|---|---|
%s
""" % (title, pov, _lang_label(fp.get("lang") or "zh-TW"),
       (m.get("avg_sentence_length") or "—"), (m.get("short_sentence_ratio") or "—"),
       (m.get("avg_paragraph_length") or "—"), (m.get("single_sentence_paragraphs") or "—"),
       (("%.0f%%" % (ratio * 100)) if isinstance(ratio, (int, float)) else "—"),
       ("- 章與章之間的對白比例變異 %.2f\n" % (d.get("dialogue") or {}).get("chapter_cv", 0)
        if d.get("dialogue") else ""),
       rows)


def structure_md(*, dna, fp, title):
    fp = datakeys.to_en(fp or {}, datakeys.FINGERPRINT)
    dna = datakeys.to_en(dna or {}, datakeys.DNA)
    d = dna
    ch = (d.get("chapters") or {})
    curve = d.get("length_curve") or []
    chs = fp.get("chapters") or {}
    lines = ["# 《%s》章節結構（骨架）" % title, "",
             "> 這些數字是從參考書量出來的骨架，不是規定；寫作時拿來對照。", "",
             "## 視角", "- %s（%s）" % ((d.get("pov") or {}).get("person") or "—",
                                        (d.get("pov") or {}).get("basis") or "—"), "",
             "## 章長", "- 平均 %s 字、最短 %s、最長 %s、變異 %s"
             % (ch.get("mean") or chs.get("mean") or "—", ch.get("min") or chs.get("min") or "—",
                ch.get("max") or chs.get("max") or "—", ch.get("cv") or chs.get("cv") or "—"),
             "- 章長曲線（十段、1.0＝平均）：%s" % ("、".join("%.2f" % x for x in curve) or "—"), "",
             "## 對白節奏", "- 對白行比例 %s、章間變異 %s"
             % (("%.0f%%" % ((d.get("dialogue") or {}).get("ratio", 0) * 100)) if d.get("dialogue") else "—",
                (d.get("dialogue") or {}).get("chapter_cv") or "—"), "",
             "## 段落", "- 平均段長 %s、單句成段 %s"
             % ((d.get("paragraphs") or {}).get("avg_paragraph_length") or "—",
                (d.get("paragraphs") or {}).get("single_sentence_paragraphs") or "—"), ""]
    return "\n".join(lines)


def card_md(title, no):
    return """---
type: chapter-card
chapter: %d
title: %s
volume: 1
status: draft
---

# 第%d章 %s

%s
""" % (no, title, no, title, CARD_SECTIONS)


def create(target, title, fp=None, dna=None, cards=3, source=""):
    """建一本新書。回傳 {created: [...相對路徑], skipped: [...]}。

    目標資料夾必須不存在或空；不會覆蓋任何東西。
    """
    target = os.path.abspath(target)
    if os.path.isdir(target) and os.listdir(target):
        raise project.ProjectError("資料夾不是空的，為了不覆蓋東西，請換一個路徑：%s" % target)
    tpl = template_dir()
    if not os.path.isdir(tpl):
        raise project.ProjectError("找不到範本資料夾（%s）" % tpl)

    created = []
    for sub in KEY_DIRS:
        os.makedirs(os.path.join(target, *sub.split("/")), exist_ok=True)

    fp = datakeys.to_en(fp, datakeys.FINGERPRINT) if fp else fp
    dna = datakeys.to_en(dna, datakeys.DNA) if dna else dna
    lang = (fp or {}).get("lang") or (dna or {}).get("lang") or "zh-TW"

    # 18 份範本（段落標題依書的語言）
    dst_tpl = layout.path(target, layout.TEMPLATES)
    shutil.copytree(tpl, dst_tpl)
    for f in os.listdir(dst_tpl):
        fp_ = os.path.join(dst_tpl, f)
        if f.endswith(".md"):
            t = project.read_text(fp_)
            t2 = sections.localize_doc(t, lang)
            if t2 != t:
                _write(fp_, t2)
    created.append("_templates/（%d 份）" % len(os.listdir(dst_tpl)))

    # 空的「活檔」：從範本複製，狀態改成草稿（目的地與範本檔名的對應在 layout.LIVE_TEMPLATES）
    for rel in LIVE_FILES:
        src_name = layout.LIVE_TEMPLATES[rel]
        src = os.path.join(tpl, src_name)
        if not os.path.isfile(src):
            continue
        text = project.read_text(src)
        text = project.set_frontmatter_field(text, "status", "draft") if "---" in text[:10] else text
        _write(os.path.join(target, *rel.split("/")), sections.localize_doc(text, lang))
        created.append(rel)

    _write(layout.path(target, layout.STYLE), sections.localize_doc(style_md(title, fp, dna), lang))
    created.append(layout.STYLE)
    _write(layout.path(target, layout.BOOK_STRUCTURE), structure_md(dna=dna, fp=fp, title=title))
    created.append(layout.BOOK_STRUCTURE)
    if fp:
        _write(layout.path(target, layout.STYLE_FINGERPRINT), json.dumps(fp, ensure_ascii=False, indent=1))
        created.append(layout.STYLE_FINGERPRINT)
    if dna:
        _write(layout.path(target, layout.STRUCTURE_DNA), json.dumps(dna, ensure_ascii=False, indent=1))
        created.append(layout.STRUCTURE_DNA)

    _write(os.path.join(target, "CLAUDE.md"), claude_md(title, lang, fp, dna, source))
    created.append("CLAUDE.md")
    from . import bookmeta
    bookmeta.write(target, title=title, lang=lang)    # 語言只記在 book.json（故事核心不再記）
    created.append(layout.BOOK_META)

    for i in range(1, max(1, int(cards)) + 1):
        rel = layout.CHAPTER_CARDS + "/" + layout.chapter_md(i)
        _write(os.path.join(target, *rel.split("/")), sections.localize_doc(card_md("（待填）", i), lang))
        created.append(rel)

    from . import trackjson
    trackjson.sync(target)          # 新建的追蹤表補上 JSON 正本
    return {"target": target, "created": created, "lang": lang}


def seed(book_dir, title, fp, dna, source=""):
    """把「從參考書量到的東西」補進一本**已經存在**的書（工作台開新書時用）。

    只寫這幾個檔，不動 CLAUDE.md 與其他內容：
      bible/style.md（原本是空範本才寫）、bible/structure/structure.md、
      bible/style-fingerprint.json、bible/structure-dna.json
    """
    fp = datakeys.to_en(fp, datakeys.FINGERPRINT) if fp else fp
    dna = datakeys.to_en(dna, datakeys.DNA) if dna else dna
    created = []
    p = layout.path(book_dir, layout.STYLE)
    text = project.read_text(p) if os.path.isfile(p) else ""
    from . import shared
    if not shared.parse_metrics(text):          # 已經有指標就不覆蓋（尊重作者手填的）
        from . import lang as lang_mod
        _write(p, sections.localize_doc(style_md(title, fp, dna), lang_mod.book_lang(book_dir)))
        created.append(layout.STYLE)
    _write(layout.path(book_dir, layout.BOOK_STRUCTURE), structure_md(dna=dna, fp=fp, title=title))
    created.append(layout.BOOK_STRUCTURE)
    if fp:
        _write(layout.path(book_dir, layout.STYLE_FINGERPRINT), json.dumps(fp, ensure_ascii=False, indent=1))
        created.append(layout.STYLE_FINGERPRINT)
    if dna:
        _write(layout.path(book_dir, layout.STRUCTURE_DNA), json.dumps(dna, ensure_ascii=False, indent=1))
        created.append(layout.STRUCTURE_DNA)
    return created


def claude_md(title, lang, fp, dna, source=""):
    fp = datakeys.to_en(fp or {}, datakeys.FINGERPRINT)
    dna = datakeys.to_en(dna or {}, datakeys.DNA)
    ch = fp.get("chapters") or {}
    pov = (dna.get("pov") or {}).get("person") if dna else "（待填）"
    return """# 《%s》

> 這本書的骨架由工作台產生%s。故事內容由你決定，這裡只放規則。

## 基本設定
- 語言：%s
- 敘事視角：%s
- 章長：平均約 %s 字（參考值，不是硬性規定）
- 對白比例：約 %s

## 資料夾
- bible／manuscript／candidates／outline／tracking／samples，完整說明見 `_templates/project-rules.md`
- `bible/style.md` 有文字指標；寫稿時工作台會把這些數字放進上下文

## 寫作規則
- 續寫時以 `outline/chapters/` 的章綱為唯一劇情藍圖
- 章尾停在具體畫面，不寫感悟或預告
- 每次改設定或追蹤，順手更新 `tracking/`

## 這本書從哪裡來
- 骨架參考：%s（只取風格指紋與結構 DNA，沒有沿用任何名字或事件）
""" % (title, ("（參考：%s）" % source) if source else "", _lang_label(lang), pov,
       ch.get("mean") or "—",
       ("%.0f%%" % ((dna.get("dialogue") or {}).get("ratio", 0) * 100)) if dna.get("dialogue") else "—",
       source or "—")
