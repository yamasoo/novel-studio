"""錯誤格式（docs/02_API合約.md 第 1.1 節）。

所有錯誤回應都是 {"error": "繁體中文的一句話", "code": "英文代碼"}，不放 traceback。
"""
import logging
from http import HTTPStatus

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("fekit")

# 合約第 1.1 節的狀態碼用途；沒列的狀態碼用 DEFAULT_MESSAGE 以外的通用句子。
DEFAULT_MESSAGE = {
    400: "參數或內容不正確。",
    403: "這個請求被擋下了。",
    404: "找不到這個資源。",
    405: "這個網址不支援這個操作。",
    409: "目前的狀態無法執行這個操作。",
    413: "上傳的內容太大了。",
    422: "參數格式不正確。",
    500: "伺服器發生錯誤，請稍後再試一次。",
}
DEFAULT_CODE = {
    400: "bad_request",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "too_large",
    422: "invalid",
    500: "server_error",
}


class ApiError(Exception):
    """丟出這個例外，前端就會收到合約格式的錯誤。

    message 要是人看得懂的繁體中文，會直接顯示給使用者。
    extra 的欄位會原樣放進回應本體（前端放在 ApiError.data）。
    """

    def __init__(self, status, message, code=None, **extra):
        super().__init__(message)
        self.status = int(status)
        self.message = str(message)
        self.code = code or DEFAULT_CODE.get(self.status)
        self.extra = extra

    def body(self):
        data = {"error": self.message}
        if self.code:
            data["code"] = self.code
        data.update(self.extra)
        return data


def error_response(status, message, code=None, headers=None, **extra):
    return JSONResponse(ApiError(status, message, code, **extra).body(), status_code=status, headers=headers)


def _generic_message(status):
    if status in DEFAULT_MESSAGE:
        return DEFAULT_MESSAGE[status]
    return "請求失敗（HTTP %d）。" % status


async def handle_api_error(request: Request, exc: ApiError):
    return JSONResponse(exc.body(), status_code=exc.status)


async def handle_http_exception(request: Request, exc: HTTPException):
    """Starlette／FastAPI 的 HTTPException（包括找不到網址、方法不對）。

    自己寫的中文 detail 原樣使用；框架預設的英文（"Not Found"）換成中文。
    """
    detail = exc.detail
    try:
        phrase = HTTPStatus(exc.status_code).phrase
    except ValueError:
        phrase = ""
    if isinstance(detail, str) and detail and detail != phrase:
        message = detail
    else:
        message = _generic_message(exc.status_code)
    return JSONResponse(
        ApiError(exc.status_code, message).body(),
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


async def handle_validation_error(request: Request, exc):
    """FastAPI 的 RequestValidationError → 422 與合約格式。"""
    fields = []
    try:
        for item in exc.errors():
            fields.append({"loc": ".".join(str(part) for part in item.get("loc", ())), "type": str(item.get("type", ""))})
    except Exception:  # 不同版本的 errors() 格式不一定相同，拿不到就不附欄位
        fields = []
    names = "、".join(dict.fromkeys(item["loc"] for item in fields if item["loc"]))
    message = "參數格式不正確" + ("（%s）。" % names if names else "。")
    return JSONResponse(ApiError(422, message, "invalid", fields=fields).body(), status_code=422)


async def handle_unexpected(request: Request, exc: Exception):
    log.exception("未處理的例外：%s %s", request.method, request.url.path)
    return JSONResponse(ApiError(500, DEFAULT_MESSAGE[500]).body(), status_code=500)


def install_handlers(app):
    """把上面四個處理器掛到 app。FastAPI 的驗證例外只有裝了 FastAPI 才處理。"""
    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected)
    try:
        from fastapi.exceptions import RequestValidationError
    except ImportError:
        return
    app.add_exception_handler(RequestValidationError, handle_validation_error)
