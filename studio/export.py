# -*- coding: utf-8 -*-
"""
匯出全文：純文字（TXT）與電子書（EPUB 3）。
只用 Python 標準函式庫，不需要額外套件。
匯出檔存在書目錄的 匯出/ 資料夾。
"""
import datetime
import html
import json
import os
import re
import uuid
import zipfile

from . import illust, project

OUT_DIR = "匯出"
PREFS = os.path.join(".studio", "匯出設定.json")

ITEMS = [
    ("text", "正文"),
    ("outline", "全書大綱與卷綱"),
    ("cards", "章綱"),
    ("bible", "設定集"),
    ("tracking", "追蹤資料"),
]
TITLE_STYLES = {
    "arabic": "第1章 章名",
    "chinese": "第一章 章名",
    "name": "只有章名",
    "original": "照稿子裡的標題",
}
PARA_STYLES = {
    "indent": "段首空兩格",
    "blank": "段落之間空一行",
    "both": "空兩格＋空一行",
}
ENCODINGS = {"utf-8": "UTF-8（建議）", "utf-8-sig": "UTF-8 含 BOM（舊版記事本、部分閱讀器）"}
COVER_NAMES = ("封面.jpg", "封面.jpeg", "封面.png", "cover.jpg", "cover.jpeg", "cover.png")

DEFAULTS = {"format": "epub", "items": ["text"], "from": None, "to": None, "title": "", "author": "",
            "title_style": "arabic", "para_style": "indent", "encoding": "utf-8",
            "vertical": False, "use_cover": True, "include_illust": True}


class ExportError(project.ProjectError):
    pass


# ---------------------------------------------------------------------------
# 共用
# ---------------------------------------------------------------------------
_DIGITS = "零一二三四五六七八九"


def chinese_number(n):
    """1→一、10→十、15→十五、105→一百零五、2024→二千零二十四。"""
    n = int(n)
    if n == 0:
        return "零"
    if n >= 100000:
        return str(n)
    out, zero = "", False
    for value, unit in ((10000, "萬"), (1000, "千"), (100, "百"), (10, "十"), (1, "")):
        d = n // value
        n %= value
        if d:
            if zero:
                out += "零"
                zero = False
            if not (value == 10 and d == 1 and not out):
                out += _DIGITS[d]
            out += unit
        elif out:
            zero = True
    return out


def book_title(book_dir):
    p = os.path.join(book_dir, "設定", "故事核心.md")
    if os.path.isfile(p):
        fm, _ = project.split_frontmatter(project.read_text(p))
        if fm.get("書名"):
            return str(fm["書名"]).strip()
    return os.path.basename(os.path.normpath(book_dir))


def find_cover(book_dir):
    """封面：先用「插圖／封面」的主圖，沒有再找書資料夾裡的 封面.jpg／封面.png。回傳相對路徑。"""
    main = illust.main_image(book_dir, "cover")
    if main:
        return os.path.relpath(main, book_dir).replace(os.sep, "/")
    for n in COVER_NAMES:
        if os.path.isfile(os.path.join(book_dir, n)):
            return n
    return None


def load_prefs(book_dir):
    p = os.path.join(book_dir, PREFS)
    prefs = dict(DEFAULTS)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                prefs.update(json.load(f))
        except Exception:
            pass
    return prefs


def save_prefs(book_dir, opts):
    keep = {k: opts.get(k) for k in DEFAULTS if k not in ("from", "to")}
    os.makedirs(os.path.join(book_dir, ".studio"), exist_ok=True)
    with open(os.path.join(book_dir, PREFS), "w", encoding="utf-8") as f:
        json.dump(keep, f, ensure_ascii=False, indent=1)


def _clean(text):
    """去掉 frontmatter 與 HTML 註解（範本裡的填寫提示）。"""
    body = project.split_frontmatter(text)[1].replace("\r\n", "\n")
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    return body.strip("\n")


def chapter_heading(no, name, original, style):
    name = (name or "").strip()
    if style == "original" and original:
        return original
    if style == "name" and name:
        return name
    num = "第%s章" % (chinese_number(no) if style == "chinese" else no)
    return ("%s %s" % (num, name)).strip()


def _split_chapter(text, no):
    """回傳 (原標題, 章名, 段落清單)。"""
    body = _clean(text)
    original, name = "", ""
    m = re.match(r"\s*#\s+(.+?)\s*(?:\n|$)", body)
    if m:
        original = m.group(1).strip()
        body = body[m.end():]
        name = re.sub(r"^第\s*[0-9一二三四五六七八九十百千零〇]+\s*章[\s:：、.．]*", "", original).strip()
    paras = [re.sub(r"[ \t]*\n[ \t]*", "", p).strip() for p in re.split(r"\n\s*\n", body)]
    # 一行一段的稿子（段落之間沒有空行）也要拆開
    if len(paras) <= 2 and body.count("\n") > 4:
        paras = [ln.strip() for ln in body.split("\n")]
    paras = [p.lstrip("　 ") for p in paras if p.strip() and not re.fullmatch(r"[-*_]{3,}", p.strip())]
    return original, name, paras


def _docs(book_dir, rels):
    out = []
    for rel in rels:
        p = os.path.join(book_dir, rel)
        if os.path.isfile(p):
            body = _clean(project.read_text(p))
            if not re.sub(r"[#\s\-|:]", "", body):
                continue
            fm = project.split_frontmatter(project.read_text(p))[0]
            title = str(fm.get("名稱") or fm.get("章名") or "")
            m = re.match(r"\s*#\s+(.+?)\s*(?:\n|$)", body)
            if m:
                title = title or m.group(1).strip()
                body = body[m.end():].strip("\n")
            out.append({"title": title or os.path.splitext(os.path.basename(rel))[0], "md": body, "src": rel})
    return out


def _md_files(book_dir, rel_dir):
    d = os.path.join(book_dir, rel_dir)
    if not os.path.isdir(d):
        return []
    return [rel_dir + "/" + f for f in sorted(os.listdir(d)) if f.endswith(".md")]


def gather(book_dir, opts):
    """依選項整理要匯出的內容。回傳 (章節清單, 附錄分組清單)。"""
    items = set(opts.get("items") or [])
    chapters, groups = [], []
    rows = [r for r in project.scan_chapters(book_dir) if r["text_file"]]
    lo = int(opts["from"]) if opts.get("from") else None
    hi = int(opts["to"]) if opts.get("to") else None
    if "text" in items:
        for r in rows:
            if (lo and r["no"] < lo) or (hi and r["no"] > hi):
                continue
            original, name, paras = _split_chapter(project.read_text(os.path.join(book_dir, r["text_file"])), r["no"])
            name = name or r["title"]
            img = illust.main_image(book_dir, "chapter:%d" % r["no"]) if opts.get("include_illust", True) else None
            chapters.append({"no": r["no"], "image": img, "title": chapter_heading(r["no"], name, original, opts.get("title_style")),
                             "paras": paras})
    if "outline" in items:
        rels = [x for x in _md_files(book_dir, "大綱") if os.path.basename(x).startswith("全書大綱")]
        rels += [x for x in _md_files(book_dir, "大綱") if x not in rels]
        groups.append(("全書大綱與卷綱", _docs(book_dir, rels)))
    if "cards" in items:
        docs = []
        for r in project.scan_chapters(book_dir):
            if r["card_file"] and not ((lo and r["no"] < lo) or (hi and r["no"] > hi)):
                for doc in _docs(book_dir, [r["card_file"]]):
                    style = opts.get("title_style") if opts.get("title_style") != "name" else "arabic"
                    doc["title"] = chapter_heading(r["no"], r["title"], "", style if style != "original" else "arabic")
                    docs.append(doc)
        groups.append(("章綱", docs))
    if "bible" in items:
        rels = ["設定/故事核心.md", "設定/文風.md", "設定/作者偏好.md", "設定/名詞表.md"]
        for sub in ("角色", "勢力", "世界觀"):
            rels += _md_files(book_dir, "設定/" + sub)
        groups.append(("設定集", _docs(book_dir, rels)))
    if "tracking" in items:
        rels = ["追蹤/狀態卡.md", "追蹤/伏筆.md", "追蹤/時間線.md"]
        rels += _md_files(book_dir, "追蹤/角色狀態")
        rels += _md_files(book_dir, "追蹤/章節摘要")
        groups.append(("追蹤資料", _docs(book_dir, rels)))
    groups = [(g, docs) for g, docs in groups if docs]
    return chapters, groups


# ---------------------------------------------------------------------------
# Markdown → 純文字／XHTML（只處理設定檔會用到的語法）
# ---------------------------------------------------------------------------
def _inline_plain(s):
    s = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)
    return s.replace("`", "")


def _table_rows(lines):
    rows = []
    for ln in lines:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows


def _blocks(md):
    """把 Markdown 切成 (類型, 內容) 區塊。"""
    lines = md.split("\n")
    i, out = 0, []
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            i += 1
            continue
        m = re.match(r"(#{1,6})\s+(.*)", s)
        if m:
            out.append(("h", (len(m.group(1)), m.group(2).strip())))
            i += 1
        elif re.fullmatch(r"[-*_]{3,}", s):
            out.append(("hr", None))
            i += 1
        elif s.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(("table", _table_rows(block)))
        elif s.startswith(">"):
            block = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                block.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(("quote", "\n".join(block)))
        elif re.match(r"([-*+]|\d+[.)])\s+", s):
            ordered = bool(re.match(r"\d", s))
            items = []
            while i < len(lines) and lines[i].strip():
                t = lines[i].strip()
                mm = re.match(r"([-*+]|\d+[.)])\s+(.*)", t)
                if mm:
                    depth = (len(lines[i]) - len(lines[i].lstrip())) // 2
                    items.append([depth, re.sub(r"^\[[ xX]\]\s*", "", mm.group(2))])
                elif items:
                    items[-1][1] += t
                else:
                    break
                i += 1
            out.append(("ol" if ordered else "ul", items))
        else:
            block = []
            while i < len(lines) and lines[i].strip() and not re.match(r"(#{1,6}\s|\||>|([-*+]|\d+[.)])\s+)", lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            out.append(("p", "".join(block) if re.search(r"[一-鿿]$", block[0]) else " ".join(block)))
    return out


def md_to_plain(md):
    out = []
    for kind, val in _blocks(md):
        if kind == "h":
            out.append("【%s】" % _inline_plain(val[1]) if val[0] <= 2 else "■ " + _inline_plain(val[1]))
        elif kind == "hr":
            out.append("　　＊　＊　＊")
        elif kind == "table":
            out.extend("｜".join(_inline_plain(c) for c in r) for r in val)
        elif kind == "quote":
            out.append("　" + _inline_plain(val))
        elif kind in ("ul", "ol"):
            for n, (depth, t) in enumerate(val, 1):
                out.append("　" * depth + ("%d. " % n if kind == "ol" else "・") + _inline_plain(t))
        else:
            out.append(_inline_plain(val))
    return out


def _inline_html(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"(\*\*|__)(.+?)\1", r"<strong>\2</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def md_to_xhtml(md):
    out = []
    for kind, val in _blocks(md):
        if kind == "h":
            lv = min(6, val[0] + 1)
            out.append("<h%d>%s</h%d>" % (lv, _inline_html(val[1]), lv))
        elif kind == "hr":
            out.append('<p class="sep">＊　＊　＊</p>')
        elif kind == "table":
            if not val:
                continue
            head, rest = val[0], val[1:]
            out.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
                "".join("<th>%s</th>" % _inline_html(c) for c in head),
                "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % _inline_html(c) for c in r) for r in rest)))
        elif kind == "quote":
            out.append("<blockquote><p>%s</p></blockquote>" % _inline_html(val).replace("\n", "<br/>"))
        elif kind in ("ul", "ol"):
            tag = kind
            out.append("<%s>%s</%s>" % (tag, "".join(
                '<li%s>%s</li>' % (' class="d%d"' % min(d, 3) if d else "", _inline_html(t)) for d, t in val), tag))
        else:
            out.append("<p>%s</p>" % _inline_html(val))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------
def build_txt(title, author, chapters, groups, para_style):
    indent = "　　" if para_style in ("indent", "both") else ""
    gap = para_style in ("blank", "both")
    lines = [title]
    if author:
        lines.append("作者：" + author)
    lines.append("")
    for ch in chapters:
        lines += ["", ch["title"], ""]
        for p in ch["paras"]:
            lines.append(indent + p)
            if gap:
                lines.append("")
        if not gap:
            lines.append("")
    for gname, docs in groups:
        lines += ["", "", "＝＝＝＝＝　%s　＝＝＝＝＝" % gname, ""]
        for d in docs:
            lines += ["", "◆ " + d["title"], ""]
            lines += md_to_plain(d["md"])
            lines.append("")
    text = "\n".join(lines)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"
    return text.replace("\n", "\r\n")


# ---------------------------------------------------------------------------
# EPUB 3（附 toc.ncx，舊閱讀器也能看到目錄）
# ---------------------------------------------------------------------------
CSS = """@charset "utf-8";
html { %(wm)s }
body { margin: 0 5%%; line-height: 1.8; font-family: serif; text-align: justify; }
h1.chapter { font-size: 1.4em; font-weight: bold; margin: 2em 0 1.5em; text-align: %(h_align)s; }
h1.group { font-size: 1.6em; margin: 3em 0 2em; text-align: center; }
h2.doc { font-size: 1.25em; margin: 1.5em 0 1em; }
h3, h4, h5, h6 { font-size: 1.05em; margin: 1.2em 0 0.5em; }
p { margin: 0; text-indent: 0; }
.ch p { text-indent: %(indent)s; margin: %(pmargin)s; }
p.sep { text-align: center; margin: 1em 0; text-indent: 0; }
.doc-body p { margin: 0.4em 0; }
ul, ol { margin: 0.4em 0; padding-%(start)s: 1.5em; }
li.d1 { margin-%(start)s: 1.5em; } li.d2 { margin-%(start)s: 3em; } li.d3 { margin-%(start)s: 4.5em; }
table { border-collapse: collapse; margin: 0.8em 0; font-size: 0.9em; }
th, td { border: 1px solid #999; padding: 0.2em 0.4em; vertical-align: top; }
th { background: #eee; }
blockquote { margin: 0.8em 1.5em; color: #555; }
.title-page { text-align: center; margin-top: 30%%; }
.title-page h1 { font-size: 2em; margin-bottom: 1em; }
.title-page .author { font-size: 1.1em; }
.cover { text-align: center; margin: 0; padding: 0; }
.illust { text-align: center; margin: 1em 0; text-indent: 0; }
.illust img { max-width: 100%%; max-height: 90vh; }
.cover img { max-width: 100%%; max-height: 100%%; }
"""


def _xhtml(title, body, lang="zh-TW", body_class=""):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="%s" xml:lang="%s">\n'
            '<head><meta charset="utf-8"/><title>%s</title><link rel="stylesheet" type="text/css" href="../style.css"/></head>\n'
            '<body%s>\n%s\n</body>\n</html>\n') % (lang, lang, html.escape(title), ' class="%s"' % body_class if body_class else "", body)


IMG_MT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def build_epub(path, book_id_seed, title, author, chapters, groups, para_style, vertical, cover_path):
    uid = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "novel-studio:" + book_id_seed))
    modified = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    indent = "2em" if para_style in ("indent", "both") else "0"
    pmargin = "0 0 1em 0" if para_style in ("blank", "both") else "0"
    if vertical:
        pmargin = "0 0 0 1em" if para_style in ("blank", "both") else "0"
    css = CSS % {"wm": "writing-mode: vertical-rl; -epub-writing-mode: vertical-rl; -webkit-writing-mode: vertical-rl;" if vertical else "",
                 "indent": indent, "pmargin": pmargin, "h_align": "start" if vertical else "center",
                 "start": "top" if vertical else "left"}

    manifest, spine, nav_items, ncx_points = [], [], [], []
    files = {}

    cover_item = None
    if cover_path:
        ext = os.path.splitext(cover_path)[1].lower()
        mt = IMG_MT.get(ext, "image/jpeg")
        cname = "images/cover" + (ext if ext in IMG_MT else ".jpg")
        with open(cover_path, "rb") as f:
            files["OEBPS/" + cname] = f.read()
        manifest.append('<item id="cover-image" href="%s" media-type="%s" properties="cover-image"/>' % (cname, mt))
        files["OEBPS/text/cover.xhtml"] = _xhtml(title, '<div class="cover"><img src="../%s" alt="%s"/></div>'
                                                 % (cname, html.escape(title)))
        manifest.append('<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('<itemref idref="cover" linear="yes"/>')
        cover_item = "text/cover.xhtml"

    tp = '<div class="title-page"><h1>%s</h1>%s</div>' % (
        html.escape(title), '<p class="author">%s</p>' % html.escape(author) if author else "")
    files["OEBPS/text/title.xhtml"] = _xhtml(title, tp)
    manifest.append('<item id="titlepage" href="text/title.xhtml" media-type="application/xhtml+xml"/>')
    spine.append('<itemref idref="titlepage"/>')
    spine.append('<itemref idref="nav"/>')

    order = [0]

    def add_page(fid, fname, page_title, body, body_class=""):
        files["OEBPS/text/" + fname] = _xhtml(page_title, body, body_class=body_class)
        manifest.append('<item id="%s" href="text/%s" media-type="application/xhtml+xml"/>' % (fid, fname))
        spine.append('<itemref idref="%s"/>' % fid)

    def point(label, href, children=None):
        order[0] += 1
        n = order[0]
        inner = "".join(children or [])
        return ('<navPoint id="np%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/>%s</navPoint>'
                % (n, n, html.escape(label), href, inner))

    ch_nav, ch_ncx = [], []
    for i, ch in enumerate(chapters, 1):
        fname = "c%04d.xhtml" % i
        pic = ""
        if ch.get("image") and os.path.isfile(ch["image"]):
            ext = os.path.splitext(ch["image"])[1].lower()
            iname = "images/c%04d%s" % (i, ext if ext in IMG_MT else ".jpg")
            with open(ch["image"], "rb") as f:
                files["OEBPS/" + iname] = f.read()
            manifest.append('<item id="img%04d" href="%s" media-type="%s"/>' % (i, iname, IMG_MT.get(ext, "image/jpeg")))
            pic = '<div class="illust"><img src="../%s" alt="%s"/></div>\n' % (iname, html.escape(ch["title"]))
        body = '<h1 class="chapter">%s</h1>\n%s%s' % (html.escape(ch["title"]), pic,
                                                      "\n".join("<p>%s</p>" % html.escape(p) for p in ch["paras"]))
        add_page("c%04d" % i, fname, ch["title"], body, "ch")
        ch_nav.append('<li><a href="text/%s">%s</a></li>' % (fname, html.escape(ch["title"])))
        ch_ncx.append(point(ch["title"], "text/" + fname))
    nav_items += ch_nav
    ncx_points += ch_ncx

    for gi, (gname, docs) in enumerate(groups, 1):
        gfile = "g%02d.xhtml" % gi
        add_page("g%02d" % gi, gfile, gname, '<h1 class="group">%s</h1>' % html.escape(gname))
        sub_nav, sub_ncx = [], []
        order_before = order[0]
        order[0] += 1  # 分組本身的 playOrder
        for di, d in enumerate(docs, 1):
            fname = "g%02d_%03d.xhtml" % (gi, di)
            body = '<h2 class="doc">%s</h2>\n<div class="doc-body">\n%s\n</div>' % (html.escape(d["title"]), md_to_xhtml(d["md"]))
            add_page("g%02d_%03d" % (gi, di), fname, d["title"], body)
            sub_nav.append('<li><a href="text/%s">%s</a></li>' % (fname, html.escape(d["title"])))
            sub_ncx.append(point(d["title"], "text/" + fname))
        nav_items.append('<li><a href="text/%s">%s</a><ol>%s</ol></li>' % (gfile, html.escape(gname), "".join(sub_nav)))
        gn = order_before + 1
        ncx_points.append('<navPoint id="np%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="text/%s"/>%s</navPoint>'
                          % (gn, gn, html.escape(gname), gfile, "".join(sub_ncx)))

    if not nav_items:
        raise ExportError("沒有可以匯出的內容")

    landmarks = ['<li><a epub:type="toc" href="nav.xhtml">目錄</a></li>']
    if cover_item:
        landmarks.insert(0, '<li><a epub:type="cover" href="%s">封面</a></li>' % cover_item)
    if chapters:
        landmarks.append('<li><a epub:type="bodymatter" href="text/c0001.xhtml">正文</a></li>')
    nav = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
           '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-TW" xml:lang="zh-TW">\n'
           '<head><meta charset="utf-8"/><title>目錄</title><link rel="stylesheet" type="text/css" href="style.css"/></head>\n<body>\n'
           '<nav epub:type="toc" id="toc"><h1 class="group">目錄</h1><ol>%s</ol></nav>\n'
           '<nav epub:type="landmarks" hidden="hidden"><ol>%s</ol></nav>\n</body>\n</html>\n') % ("".join(nav_items), "".join(landmarks))
    files["OEBPS/nav.xhtml"] = nav
    files["OEBPS/style.css"] = css
    files["OEBPS/toc.ncx"] = ('<?xml version="1.0" encoding="utf-8"?>\n'
                              '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="zh-TW">\n'
                              '<head><meta name="dtb:uid" content="%s"/></head>\n<docTitle><text>%s</text></docTitle>\n'
                              '<navMap>%s</navMap>\n</ncx>\n') % (uid, html.escape(title), "".join(ncx_points))

    opf = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="zh-TW">\n'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
           '<dc:identifier id="bookid">%s</dc:identifier>\n<dc:title>%s</dc:title>\n%s<dc:language>zh-TW</dc:language>\n'
           '<meta property="dcterms:modified">%s</meta>\n%s</metadata>\n'
           '<manifest>\n<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
           '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
           '<item id="css" href="style.css" media-type="text/css"/>\n%s\n</manifest>\n'
           '<spine toc="ncx"%s>\n%s\n</spine>\n</package>\n') % (
        uid, html.escape(title), "<dc:creator>%s</dc:creator>\n" % html.escape(author) if author else "", modified,
        '<meta name="cover" content="cover-image"/>\n' if cover_item else "",
        "\n".join(manifest), ' page-progression-direction="rtl"' if vertical else "", "\n".join(spine))
    files["OEBPS/content.opf"] = opf
    files["META-INF/container.xml"] = ('<?xml version="1.0" encoding="utf-8"?>\n'
                                       '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                                       '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n'
                                       '</container>\n')

    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            z.writestr(name, data.encode("utf-8") if isinstance(data, str) else data, compress_type=zipfile.ZIP_DEFLATED)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def _safe_name(s):
    return re.sub(r'[\\/:*?"<>|\r\n\t]', "", s).strip() or "未命名"


def export(book_dir, opts):
    opts = dict(DEFAULTS, **{k: v for k, v in (opts or {}).items() if v is not None})
    fmt = opts.get("format")
    if fmt not in ("txt", "epub"):
        raise ExportError("不支援的格式：%s" % fmt)
    if not opts.get("items"):
        raise ExportError("請至少勾選一項要匯出的內容")
    if opts.get("title_style") not in TITLE_STYLES:
        opts["title_style"] = "arabic"
    if opts.get("para_style") not in PARA_STYLES:
        opts["para_style"] = "indent"
    title = (opts.get("title") or "").strip() or book_title(book_dir)
    author = (opts.get("author") or "").strip()
    chapters, groups = gather(book_dir, opts)
    if not chapters and not groups:
        raise ExportError("勾選的項目裡沒有內容可以匯出（正文要先採用才會進正文資料夾）")

    out_dir = os.path.join(book_dir, OUT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    rng = ""
    if chapters and (opts.get("from") or opts.get("to")):
        a, b = chapters[0]["no"], chapters[-1]["no"]
        rng = "_第%d章" % a if a == b else "_第%d-%d章" % (a, b)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = "%s%s_%s.%s" % (_safe_name(title), rng, stamp, fmt)
    path = os.path.join(out_dir, name)
    n = 2
    while os.path.exists(path):
        name = "%s%s_%s-%d.%s" % (_safe_name(title), rng, stamp, n, fmt)
        path = os.path.join(out_dir, name)
        n += 1

    if fmt == "txt":
        text = build_txt(title, author, chapters, groups, opts["para_style"])
        enc = opts.get("encoding") if opts.get("encoding") in ENCODINGS else "utf-8"
        with open(path, "w", encoding=enc, newline="") as f:
            f.write(text)
    else:
        cover = find_cover(book_dir) if opts.get("use_cover") else None
        build_epub(path, os.path.basename(os.path.normpath(book_dir)), title, author, chapters, groups,
                   opts["para_style"], bool(opts.get("vertical")), os.path.join(book_dir, cover) if cover else None)
    save_prefs(book_dir, opts)
    chars = sum(len(project.CJK.findall("".join(c["paras"]))) for c in chapters)
    return {"file": name, "path": OUT_DIR + "/" + name, "size": os.path.getsize(path),
            "chapters": len(chapters), "chars": chars, "docs": sum(len(d) for _, d in groups)}


def list_exports(book_dir):
    d = os.path.join(book_dir, OUT_DIR)
    out = []
    if os.path.isdir(d):
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if os.path.isfile(p) and f.endswith((".txt", ".epub")):
                out.append({"file": f, "size": os.path.getsize(p), "mtime": os.path.getmtime(p)})
    out.sort(key=lambda x: -x["mtime"])
    return out


def export_path(book_dir, name):
    if not name or "/" in name or "\\" in name or name.startswith(".") or not name.endswith((".txt", ".epub")):
        raise ExportError("檔名不合法")
    p = os.path.join(book_dir, OUT_DIR, name)
    if not os.path.isfile(p):
        raise ExportError("找不到這個匯出檔")
    return p


def delete_export(book_dir, name):
    os.remove(export_path(book_dir, name))


def meta(book_dir):
    rows = [r for r in project.scan_chapters(book_dir) if r["text_file"]]
    return {"items": ITEMS, "title_styles": TITLE_STYLES, "para_styles": PARA_STYLES, "encodings": ENCODINGS,
            "prefs": load_prefs(book_dir), "book_title": book_title(book_dir), "cover": find_cover(book_dir),
            "illust_chapters": sum(1 for r in rows if illust.main_image(book_dir, "chapter:%d" % r["no"])),
            "chapters": [{"no": r["no"], "title": r["title"], "chars": r["chars"]} for r in rows],
            "exports": list_exports(book_dir)}
