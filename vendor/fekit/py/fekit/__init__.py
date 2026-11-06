"""fekit 的 Python 輔助套件。規格見 docs/02_API合約.md 第 1–5 節。

    from fekit import install, JobRunner
    app = FastAPI()
    runner = JobRunner()
    fe = install(app, app_name="my-app", jobs=runner)

    @app.get("/")
    def index():
        return fe.page(Path("web/index.html"))

只依賴 Starlette（FastAPI 是它的上層，兩者都能用）。需要 Python 3.10 以上。
"""
from .errors import ApiError
from .install import Fekit, install
from .jobs import Job, JobError, JobRunner, JobStopped
from .upload import SavedUpload, safe_filename, save_upload

__all__ = [
    "install", "Fekit", "ApiError", "JobRunner", "Job", "JobStopped", "JobError",
    "save_upload", "safe_filename", "SavedUpload",
]
