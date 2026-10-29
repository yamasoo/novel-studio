# -*- coding: utf-8 -*-
"""建專案（P6 Step 5）：用風格指紋與結構 DNA 建出一本新書的骨架。

產出的是「可以馬上開始填」的書，不是成品：
  資料夾骨架、18 份 _範本、CLAUDE.md、設定/文風.md（含文字指標）、
  設定/章節結構/結構.md、指紋與 DNA 的副本、前三章章綱的空白模板。

不呼叫模型、不改任何既有檔案；目標資料夾不是空的就拒絕。
"""
import json
import os
import shutil

from . import fingerprint, project, sdna

KEY_DIRS = ("正文", "候選", "大綱/章綱", "大綱/卷綱", "追蹤/章節摘要", "追蹤/角色狀態",
            "設定/角色", "設定/勢力", "設定/世界觀", "設定/章節結構", "範例")
LIVE_FILES = ("設定/故事核心.md", "設定/名詞表.md", "設定/作者偏好.md",
              "追蹤/伏筆.md", "追蹤/時間線.md", "追蹤/狀態卡.md",
              "追蹤/讀者認知.md", "追蹤/關係.md",
              "大綱/全書大綱.md", "大綱/卷綱/卷綱_第一卷.md")
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
    return os.path.join(here, "demo", "退婚之後", "_範本")


def _write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def _lang_label(lang):
    return {"zh-TW": "台灣繁體中文（用語、標點依台灣習慣）",
            "en": "English (US spelling and punctuation)",
            "ja": "日本語（表記は日本語の慣例に従う）"}.get(lang, lang)


def style_md(title, fp, dna):
    m = (fp or {}).get("文字指標") or {}
    ch = (fp or {}).get("章節") or {}
    d = dna or {}
    pov = (d.get("視角") or {}).get("人稱") or "（待填）"
    ratio = ((d.get("對白") or {}).get("比例"))
    rows = "\n".join("| %s | %s |" % (k, v) for k, v in m.items()) or "| （待量測） | |"
    return """---
類型: 文風
狀態: 草稿
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
""" % (title, pov, _lang_label((fp or {}).get("語言") or "zh-TW"),
       (m.get("平均句長") or "—"), (m.get("短句比例") or "—"),
       (m.get("平均段長") or "—"), (m.get("單句成段") or "—"),
       (("%.0f%%" % (ratio * 100)) if isinstance(ratio, (int, float)) else "—"),
       ("- 章與章之間的對白比例變異 %.2f\n" % (d.get("對白") or {}).get("章間變異", 0)
        if d.get("對白") else ""),
       rows)


def structure_md(*, dna, fp, title):
    d = dna or {}
    ch = (d.get("章節") or {})
    curve = d.get("章長曲線") or []
    chs = (fp or {}).get("章節") or {}
    lines = ["# 《%s》章節結構（骨架）" % title, "",
             "> 這些數字是從參考書量出來的骨架，不是規定；寫作時拿來對照。", "",
             "## 視角", "- %s（%s）" % ((d.get("視角") or {}).get("人稱") or "—",
                                        (d.get("視角") or {}).get("依據") or "—"), "",
             "## 章長", "- 平均 %s 字、最短 %s、最長 %s、變異 %s"
             % (ch.get("平均") or chs.get("平均章長") or "—", ch.get("最短") or chs.get("最短章長") or "—",
                ch.get("最長") or chs.get("最長章長") or "—", ch.get("變異") or chs.get("章長變異") or "—"),
             "- 章長曲線（十段、1.0＝平均）：%s" % ("、".join("%.2f" % x for x in curve) or "—"), "",
             "## 對白節奏", "- 對白行比例 %s、章間變異 %s"
             % (("%.0f%%" % ((d.get("對白") or {}).get("比例", 0) * 100)) if d.get("對白") else "—",
                (d.get("對白") or {}).get("章間變異") or "—"), "",
             "## 段落", "- 平均段長 %s、單句成段 %s"
             % ((d.get("段落") or {}).get("平均段長") or "—", (d.get("段落") or {}).get("單句成段") or "—"), ""]
    return "\n".join(lines)


def card_md(title, no):
    return """---
類型: 章綱
章號: %d
章名: %s
所屬卷: 第一卷
狀態: 草稿
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

    # 18 份範本
    dst_tpl = os.path.join(target, "_範本")
    shutil.copytree(tpl, dst_tpl)
    created.append("_範本/（%d 份）" % len(os.listdir(dst_tpl)))

    # 空的「活檔」：從範本複製，狀態改成草稿（範本檔名不一定同名，這裡做對應）
    for rel in LIVE_FILES:
        src_name = "卷綱.md" if rel.endswith("卷綱_第一卷.md") else os.path.basename(rel)
        src = os.path.join(tpl, src_name)
        if not os.path.isfile(src):
            continue
        text = project.read_text(src)
        text = project.set_frontmatter_field(text, "狀態", "草稿") if "---" in text[:10] else text
        _write(os.path.join(target, *rel.split("/")), text)
        created.append(rel)

    lang = (fp or {}).get("語言") or (dna or {}).get("語言") or "zh-TW"
    _write(os.path.join(target, "設定", "文風.md"), style_md(title, fp, dna))
    created.append("設定/文風.md")
    _write(os.path.join(target, "設定", "章節結構", "結構.md"), structure_md(dna=dna, fp=fp, title=title))
    created.append("設定/章節結構/結構.md")
    if fp:
        _write(os.path.join(target, "設定", "風格指紋.json"), json.dumps(fp, ensure_ascii=False, indent=1))
        created.append("設定/風格指紋.json")
    if dna:
        _write(os.path.join(target, "設定", "結構DNA.json"), json.dumps(dna, ensure_ascii=False, indent=1))
        created.append("設定/結構DNA.json")

    _write(os.path.join(target, "CLAUDE.md"), claude_md(title, lang, fp, dna, source))
    created.append("CLAUDE.md")

    for i in range(1, max(1, int(cards)) + 1):
        rel = "大綱/章綱/第%03d章_待填.md" % i
        _write(os.path.join(target, *rel.split("/")), card_md("（待填）", i))
        created.append(rel)

    return {"target": target, "created": created, "lang": lang}


def claude_md(title, lang, fp, dna, source=""):
    ch = (fp or {}).get("章節") or {}
    pov = (dna.get("視角") or {}).get("人稱") if dna else "（待填）"
    return """# 《%s》

> 這本書的骨架由工作台產生%s。故事內容由你決定，這裡只放規則。

## 基本設定
- 語言：%s
- 敘事視角：%s
- 章長：平均約 %s 字（參考值，不是硬性規定）
- 對白比例：約 %s

## 資料夾
- 設定／正文／候選／大綱／追蹤／範例，完整說明見 `_範本/專案規範.md`
- `設定/文風.md` 有文字指標；寫稿時工作台會把這些數字放進上下文

## 寫作規則
- 續寫時以 `大綱/章綱/` 的章綱為唯一劇情藍圖
- 章尾停在具體畫面，不寫感悟或預告
- 每次改設定或追蹤，順手更新 `追蹤/`

## 這本書從哪裡來
- 骨架參考：%s（只取風格指紋與結構 DNA，沒有沿用任何名字或事件）
""" % (title, ("（參考：%s）" % source) if source else "", _lang_label(lang), pov,
       ch.get("平均章長") or "—",
       ("%.0f%%" % (((dna or {}).get("對白") or {}).get("比例", 0) * 100)) if dna and dna.get("對白") else "—",
       source or "—")
