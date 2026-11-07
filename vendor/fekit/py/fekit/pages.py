"""把權杖與專案代號寫進 HTML（docs/02_API合約.md 第 2.1 節）。"""
import html as _html
import re
from pathlib import Path

from starlette.responses import HTMLResponse

APP_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
_HEAD_RE = re.compile(r"<head(\s[^>]*)?>", re.IGNORECASE)


def meta_tags(token, app_name):
    return '<meta name="fe-token" content="%s"><meta name="fe-app" content="%s">' % (
        _html.escape(token, quote=True),
        _html.escape(app_name, quote=True),
    )


def inject(text, token, app_name):
    """插在 <head> 後面（最前面），這樣即使頁面原本有同名 meta，前端讀到的也是這一組。"""
    tags = meta_tags(token, app_name)
    match = _HEAD_RE.search(text)
    if match:
        return text[:match.end()] + tags + text[match.end():]
    return tags + text


def render(source, token, app_name):
    """source 是 HTML 字串或檔案路徑。回應不可快取，因為權杖每次啟動都不同。"""
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8")
    else:
        text = source
    return HTMLResponse(inject(text, token, app_name), headers={"Cache-Control": "no-store"})
