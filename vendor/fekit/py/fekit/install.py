"""install(app)：一次裝好本機保護、錯誤格式、任務端點與檔案瀏覽。"""
import secrets

from . import fs as _fs
from . import pages
from .errors import install_handlers
from .guard import LocalGuard


class Fekit:
    """install() 的回傳值。"""

    def __init__(self, token, app_name):
        self.token = token
        self.app_name = app_name

    def meta_tags(self):
        return pages.meta_tags(self.token, self.app_name)

    def inject(self, html):
        """把權杖與專案代號寫進 HTML 字串。"""
        return pages.inject(html, self.token, self.app_name)

    def page(self, source):
        """回傳寫好權杖的 HTMLResponse。source 是 HTML 字串或 pathlib.Path。"""
        return pages.render(source, self.token, self.app_name)


def install(app, *, app_name="fe", jobs=None, jobs_base="/api/jobs", fs=True, fs_roots=None,
            allowed_hosts=(), token=None):
    """裝在 app 上，必須在 app 開始服務之前呼叫。

    app_name       專案代號 [a-z0-9_-]，前端 FE.store 的 key 前綴。
    jobs           JobRunner；或 {路徑前綴: JobRunner}（要多組任務端點時）。
    jobs_base      jobs 是單一 JobRunner 時的路徑前綴。
    fs             是否提供 /api/fs/list。fs_roots 可限制可瀏覽的資料夾。
    allowed_hosts  除了 127.0.0.1、localhost、[::1] 之外也接受的 Host 主機名稱。
    token          指定權杖（測試用）；預設每次啟動隨機產生 32 bytes。
    """
    if not pages.APP_NAME_RE.match(app_name):
        raise ValueError("app_name 只能用 a-z、0-9、底線與連字號：%r" % app_name)
    token = token or secrets.token_urlsafe(32)

    install_handlers(app)
    routes = []
    if jobs is not None:
        mapping = jobs if isinstance(jobs, dict) else {jobs_base: jobs}
        for base, runner in mapping.items():
            routes.extend(runner.routes(base))
    if fs:
        routes.extend(_fs.make_routes("/api/fs", fs_roots))
    app.router.routes[:0] = routes
    app.add_middleware(LocalGuard, token=token, allowed_hosts=tuple(allowed_hosts))
    return Fekit(token, app_name)
