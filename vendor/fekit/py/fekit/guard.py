"""本機保護（docs/02_API合約.md 第 2 節）：Host、Sec-Fetch-Site、Origin、X-FE-Token。

純 ASGI 中介層，只依賴 Starlette 的回應類別，FastAPI 與 Starlette 都能用。
"""
import hmac
from urllib.parse import urlsplit

from .errors import error_response

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
DEFAULT_HOSTS = ("127.0.0.1", "localhost", "[::1]")
TOKEN_HEADER = "x-fe-token"


def host_name(host_header):
    """從 Host 標頭取出主機名稱（去掉埠、轉小寫）。格式不對回傳 None。"""
    if not host_header:
        return None
    host = host_header.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        if end < 0:
            return None
        rest = host[end + 1:]
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            return None
        return host[:end + 1]
    if host.count(":") > 1:
        return None
    name, _, port = host.partition(":")
    if _ and not port.isdigit():
        return None
    return name or None


def _normalize_hosts(hosts):
    result = set()
    for item in hosts:
        name = host_name(item)
        if name:
            result.add(name)
    return result


class LocalGuard:
    def __init__(self, app, token, allowed_hosts=()):
        self.app = app
        self.token = token.encode("utf-8")
        self.hosts = _normalize_hosts(tuple(DEFAULT_HOSTS) + tuple(allowed_hosts))

    @staticmethod
    def _headers(scope):
        # 同名標頭只取第一個；ASGI 標頭是 latin-1 的 bytes。
        result = {}
        for key, value in scope.get("headers", ()):
            result.setdefault(key.decode("latin-1").lower(), value.decode("latin-1"))
        return result

    def _check_host(self, headers):
        return host_name(headers.get("host")) in self.hosts

    def _check_origin(self, headers):
        site = headers.get("sec-fetch-site")
        if site is not None and site.strip().lower() not in ("same-origin", "none"):
            return False
        origin = headers.get("origin")
        if origin is not None:
            try:
                netloc = urlsplit(origin).netloc.lower()
            except ValueError:
                return False
            if not netloc or netloc != (headers.get("host") or "").strip().lower():
                return False
        return True

    def _check_token(self, headers):
        given = headers.get(TOKEN_HEADER, "").encode("utf-8")
        return hmac.compare_digest(given, self.token)

    def verdict(self, scope):
        """通過回傳 None，否則回傳 (訊息, code)。"""
        headers = self._headers(scope)
        if not self._check_host(headers):
            return "這個網址不是本機位址，請改用 http://127.0.0.1 或 http://localhost 開啟。", "bad_host"
        mutating = scope["type"] == "websocket" or scope.get("method", "GET") not in SAFE_METHODS
        if not mutating:
            return None
        if not self._check_origin(headers):
            return "請求來源不正確，已被擋下。", "bad_origin"
        if scope["type"] == "http" and not self._check_token(headers):
            return "請求權杖不正確，請重新整理頁面再試一次（後端重新啟動後權杖會改變）。", "bad_token"
        return None

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        problem = self.verdict(scope)
        if problem is None:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        response = error_response(403, problem[0], problem[1])
        await response(scope, receive, send)
