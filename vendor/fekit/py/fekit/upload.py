"""接收 FE.upload 的請求（docs/02_API合約.md 第 3 節）：本體就是檔案內容，檔名在 X-Filename。

    @app.post("/api/files")
    async def receive(request: Request):
        saved = await save_upload(request, UPLOAD_DIR, max_bytes=50 * 1024 * 1024)
        return {"name": saved.name, "size": saved.size}
"""
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from starlette.requests import Request

from .errors import ApiError

_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul", *("com%d" % i for i in range(1, 10)), *("lpt%d" % i for i in range(1, 10))}
MAX_NAME = 200


@dataclass
class SavedUpload:
    path: Path
    name: str
    size: int
    content_type: str


def safe_filename(raw):
    """URL 解碼後只取檔名部分。路徑、`..`、Windows 不能用的名稱都拒絕（400）。"""
    try:
        decoded = unquote(raw or "", errors="strict")
    except UnicodeDecodeError:
        raise ApiError(400, "檔名編碼不正確。", "bad_filename") from None
    parts = decoded.replace("\\", "/").split("/")
    if ".." in parts:
        raise ApiError(400, "檔名不可以含有 ..。", "bad_filename")
    name = parts[-1].strip()
    stem = name.split(".")[0].strip().lower()
    if (not name or name == "." or _BAD_CHARS.search(name) or name.endswith(".")
            or stem in _RESERVED or len(name) > MAX_NAME):
        raise ApiError(400, "檔名不能使用。", "bad_filename")
    return name


def _free_name(directory, name):
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    else:
        ext = "." + ext
    candidate, index = name, 0
    while (directory / candidate).exists():
        index += 1
        candidate = "%s (%d)%s" % (stem, index, ext)
    return candidate


async def save_upload(request: Request, directory, *, max_bytes=100 * 1024 * 1024, exts=None, on_conflict="rename"):
    """把請求本體寫成 directory 底下的檔案。

    on_conflict：rename（加 (1)）、overwrite、error（409）。
    exts：允許的副檔名（含點，不分大小寫）；None 表示不限。
    先寫到暫存檔，成功才改名，所以中途失敗不會留下半個檔案。
    """
    if on_conflict not in ("rename", "overwrite", "error"):
        raise ValueError("on_conflict 要是 rename、overwrite、error 其中之一")
    name = safe_filename(request.headers.get("x-filename"))
    if exts is not None and not name.lower().endswith(tuple(e.lower() for e in exts)):
        raise ApiError(400, "不支援這種檔案類型（可用：%s）。" % "、".join(exts), "bad_ext")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise ApiError(413, "檔案太大了（上限 %d MB）。" % (max_bytes // (1024 * 1024)), "too_large")

    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / (".upload-%s.part" % secrets.token_hex(6))
    size = 0
    try:
        with open(temp, "wb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > max_bytes:
                    raise ApiError(413, "檔案太大了（上限 %d MB）。" % (max_bytes // (1024 * 1024)), "too_large")
                handle.write(chunk)
        if on_conflict == "rename":
            name = _free_name(directory, name)
        elif on_conflict == "error" and (directory / name).exists():
            raise ApiError(409, "已經有同名的檔案：%s" % name, "exists")
        target = directory / name
        if target.resolve().parent != directory:  # 多一道保險，safe_filename 已經擋過
            raise ApiError(400, "檔名不能使用。", "bad_filename")
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return SavedUpload(target, name, size, request.headers.get("content-type") or "application/octet-stream")
