"""檔案瀏覽 GET /api/fs/list（docs/02_API合約.md 第 5 節）。

這個端點會讓頁面看到本機的目錄結構，所以只有通過 LocalGuard 的請求才到得了這裡，
也不要替它加 CORS 標頭。roots 參數可以把可瀏覽的範圍限制在指定資料夾內。
"""
import os
import sys

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .errors import ApiError


def _windows_drives():
    import ctypes
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    return ["%s:\\" % chr(ord("A") + i) for i in range(26) if mask & (1 << i)]


def system_roots():
    if sys.platform == "win32":
        return _windows_drives()
    return ["/"]


def _norm(path):
    return os.path.normcase(os.path.normpath(path))


def _inside(path, roots):
    target = _norm(path)
    for root in roots:
        base = _norm(root)
        if target == base or target.startswith(base.rstrip(os.sep) + os.sep):
            return True
    return False


def _hidden(entry):
    if entry.name.startswith("."):
        return True
    try:
        attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & 0x2 or attrs & 0x4)  # FILE_ATTRIBUTE_HIDDEN、SYSTEM（只有 Windows 有）


def _parse_exts(text):
    exts = []
    for part in (text or "").split(","):
        part = part.strip().lower()
        if part:
            exts.append(part if part.startswith(".") else "." + part)
    return tuple(exts)


def _sort_key(name):
    return (name.casefold(), name)


def make_routes(prefix="/api/fs", roots=None):
    """roots 為 None 時是整台電腦（Windows 的磁碟機、其他系統的 /）。"""
    limit_roots = [os.path.abspath(r) for r in roots] if roots else None

    def top():
        return list(limit_roots) if limit_roots else system_roots()

    def parent_of(path, allowed):
        up = os.path.dirname(path)
        if up == path or not up:
            return None
        if limit_roots and not _inside(up, allowed):
            return None
        return up

    async def list_dir(request: Request):
        query = request.query_params
        mode = query.get("mode", "dir")
        if mode not in ("dir", "file"):
            raise ApiError(400, "mode 只能是 dir 或 file。", "bad_param")
        exts = _parse_exts(query.get("exts"))
        raw = query.get("path", "")
        available = top()
        empty = {"roots": available, "path": "", "parent": None, "sep": os.sep, "dirs": [], "files": []}
        if not raw.strip():
            return JSONResponse(empty)
        if "\0" in raw:
            raise ApiError(400, "路徑含有不合法的字元。", "bad_path")
        if not os.path.isabs(raw):
            raise ApiError(400, "請提供完整路徑（例如 E:\\dev）。", "bad_path")

        path = os.path.normpath(raw)
        # 不存在或是檔案：往上找第一個存在的資料夾
        while not os.path.isdir(path):
            up = os.path.dirname(path)
            if up == path or not up:
                return JSONResponse(empty)
            path = up
        if limit_roots and not _inside(path, limit_roots):
            return JSONResponse(empty)

        dirs, files = [], []
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if _hidden(entry):
                            continue
                        if entry.is_dir():
                            dirs.append(entry.name)
                        elif mode == "file" and (not exts or entry.name.lower().endswith(exts)):
                            files.append(entry.name)
                    except OSError:
                        continue  # 單一項目讀不到就略過
        except OSError as exc:
            raise ApiError(400, "讀不到這個資料夾：%s" % (exc.strerror or "沒有權限"), "unreadable") from None
        dirs.sort(key=_sort_key)
        files.sort(key=_sort_key)
        return JSONResponse({
            "roots": available, "path": path, "parent": parent_of(path, available),
            "sep": os.sep, "dirs": dirs, "files": files,
        })

    return [Route(prefix.rstrip("/") + "/list", list_dir, methods=["GET"])]
