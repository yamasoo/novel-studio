# -*- coding: utf-8 -*-
"""book.json：每本書的身分證（v3 規格 3.7）。

{"schema_version": 2, "title": "退婚之後", "lang": "zh-TW", "created": "2026-11-20"}

- schema_version：這本書檔案的格式版本。沒有 book.json 的舊書當成 2。
  移轉工具（tools/migrate_v3.py）靠它判斷要不要轉換；工作台寫出的版本是 layout.SCHEMA_VERSION。
- lang：書的寫作語言，lang.book_lang 最先看這裡。沒有這個欄位時照舊看故事核心的「語言」與 .studio/lang。
- 其他欄位原樣保留（之後可以加 chapter_target_length 之類）。
"""
import datetime
import json
import os

from . import layout

ORDER = ("schema_version", "title", "lang", "created")


def path(book_dir):
    return os.path.join(book_dir, layout.BOOK_META)


def read(book_dir):
    """讀不到或格式壞掉都回傳 {}（不丟例外：開書、列書架不能因為這個檔壞掉而失敗）。"""
    try:
        with open(path(book_dir), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def exists(book_dir):
    return os.path.isfile(path(book_dir))


def version(book_dir):
    """這本書的格式版本；沒有 book.json 的舊書是 2。"""
    try:
        return int(read(book_dir).get("schema_version") or 2)
    except (TypeError, ValueError):
        return 2


def write(book_dir, **updates):
    """合併寫入（沒給的欄位保留）。第一次建立時補上 schema_version、title（資料夾名）、created（今天）。
    值是 None 的欄位會被拿掉。回傳寫入後的內容。"""
    d = read(book_dir)
    d.setdefault("schema_version", layout.SCHEMA_VERSION)
    d.setdefault("title", os.path.basename(os.path.normpath(book_dir)))
    d.setdefault("created", datetime.date.today().isoformat())
    for k, v in updates.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    out = {k: d[k] for k in ORDER if k in d}
    out.update({k: v for k, v in d.items() if k not in out})
    from . import project
    project.write_atomic(path(book_dir), json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    return out
