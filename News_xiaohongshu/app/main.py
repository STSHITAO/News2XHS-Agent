from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import sys

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router
from app.core.config import settings
from app.core.database import engine
from app.models import Base
from app.services.scheduler_service import SchedulerService


# Use uvicorn's logger so startup hints always appear in terminal output.
logger = logging.getLogger("uvicorn.error")


def _runtime_arg(name: str) -> str | None:
    flag = f"--{name}"
    for idx, token in enumerate(sys.argv):
        if token == flag and idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
        if token.startswith(f"{flag}="):
            return token.split("=", 1)[1]
    return None


def _runtime_host_port() -> tuple[str, int]:
    host = _runtime_arg("host") or settings.APP_HOST
    raw_port = _runtime_arg("port")
    try:
        port = int(raw_port) if raw_port else int(settings.APP_PORT)
    except Exception:
        port = int(settings.APP_PORT)
    return host, port


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    scheduler = SchedulerService()
    scheduler.start()
    app.state.scheduler = scheduler
    host, port = _runtime_host_port()
    logger.info("News_xiaohongshu started.")
    logger.info("Open Admin UI: http://127.0.0.1:%s/admin", port)
    logger.info("Open API Docs: http://127.0.0.1:%s/docs", port)
    logger.info("Runtime bind: host=%s port=%s", host, port)
    print(f"[News_xiaohongshu] Admin UI: http://127.0.0.1:{port}/admin", flush=True)
    print(f"[News_xiaohongshu] API Docs: http://127.0.0.1:{port}/docs", flush=True)
    yield
    scheduler.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.include_router(router)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/")
def index() -> RedirectResponse:
    return RedirectResponse(url="/admin", status_code=302)


@app.get("/admin")
def admin_page(request: Request):
    return templates.TemplateResponse(request, "admin.html", {"app_name": settings.APP_NAME})


@app.get("/admin/draft/{draft_id}")
def draft_editor_page(request: Request, draft_id: int):
    return templates.TemplateResponse(
        request,
        "draft_editor.html",
        {"app_name": settings.APP_NAME, "draft_id": draft_id},
    )
