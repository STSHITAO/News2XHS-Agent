from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import Draft, JobRun, NewsItem, PublishTask
from app.schemas.common import HealthResponse, MessageResponse
from app.schemas.draft import DraftGenerateRequest, DraftGenerateResponse, DraftOut, DraftStatusUpdateRequest, DraftUpdateRequest
from app.schemas.image_gen import CoverGenerateRequest, CoverGenerateResponse
from app.schemas.news import HotFetchRequest, HotFetchResponse, NewsItemOut
from app.schemas.publish import PublishResponse, PublishTaskOut
from app.services.draft_service import DraftService
from app.services.image_generation_service import ImageGenerationService
from app.services.job_service import JobService
from app.services.news_service import NewsService
from app.services.publish_service import PublishService
from app.services.xhs_mcp_client import XhsMcpClient
from app.utils.text_sanitize import sanitize_topic


router = APIRouter(tags=["news_xiaohongshu"])
UPLOAD_DIR = Path("static/uploads/covers")
ALLOWED_IMAGE_SUFFIX = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


def _to_news_item_out(row: NewsItem) -> NewsItemOut:
    return NewsItemOut(
        id=row.id,
        title=row.title,
        url=row.url,
        summary=row.summary,
        source=row.source,
        published_at=row.published_at,
    )


def _to_draft_out(row: Draft) -> DraftOut:
    try:
        tags = json.loads(row.tags_json or "[]")
        if not isinstance(tags, list):
            tags = []
    except Exception:
        tags = []
    return DraftOut(
        id=row.id,
        topic=row.topic,
        title=row.title,
        content=row.content,
        tags=[str(tag) for tag in tags],
        cover_image_url=row.cover_image_url,
        status=row.status,
        editor_notes=row.editor_notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_publish_task_out(task: PublishTask) -> PublishTaskOut:
    return PublishTaskOut(
        id=task.id,
        draft_id=task.draft_id,
        status=task.status,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _build_auto_cover_prompt(draft: Draft) -> str:
    topic = sanitize_topic(draft.topic, max_len=20)
    title = (draft.title or "").strip()
    return (
        f"Generate a Xiaohongshu cover image, vertical composition, realistic style, clean layout, "
        f"no watermark, topic: {topic}, title: {title}"
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(success=True, service=settings.APP_NAME, env=settings.APP_ENV)


@router.get("/api/system/status")
def system_status(request: Request) -> dict:
    scheduler = getattr(request.app.state, "scheduler", None)
    publish_guard_enabled = bool(settings.PUBLISH_GUARD_TOKEN.strip())
    return {
        "success": True,
        "service": settings.APP_NAME,
        "scheduler_enabled": settings.SCHEDULER_ENABLED,
        "scheduler_started": bool(getattr(scheduler, "started", False)),
        "search_provider": settings.SEARCH_TOOL_TYPE,
        "image_provider": settings.IMAGE_GEN_PROVIDER,
        "publish_guard_enabled": publish_guard_enabled,
    }


@router.post("/api/news/hot/fetch", response_model=HotFetchResponse)
def fetch_hot_news(payload: HotFetchRequest, db: Session = Depends(get_db)) -> HotFetchResponse:
    clean_query = sanitize_topic(payload.query, max_len=24)
    service = NewsService(db)
    bundle = service.fetch_and_store_hot_news(
        query=clean_query,
        limit=payload.limit,
        period=payload.period,
    )
    items = service.list_hot_news(limit=payload.limit)
    return HotFetchResponse(
        success=True,
        query=clean_query,
        provider=bundle.provider,
        selected_tool=bundle.selected_tool,
        count=len(items),
        items=[_to_news_item_out(item) for item in items],
    )


@router.get("/api/news/hot", response_model=list[NewsItemOut])
def list_hot_news(limit: int = 50, db: Session = Depends(get_db)) -> list[NewsItemOut]:
    rows = NewsService(db).list_hot_news(limit=limit)
    return [_to_news_item_out(row) for row in rows]


@router.post("/api/drafts/generate", response_model=DraftGenerateResponse)
def generate_draft(payload: DraftGenerateRequest, db: Session = Depends(get_db)) -> DraftGenerateResponse:
    clean_topic = sanitize_topic(payload.topic, max_len=20)
    service = DraftService(db)
    try:
        row = service.generate_draft(topic=clean_topic, max_news_items=payload.max_news_items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    auto_cover_generated = False
    auto_cover_provider = ""
    auto_cover_error = ""
    if settings.AUTO_GENERATE_COVER_ON_DRAFT:
        try:
            cover_service = ImageGenerationService(db)
            cover_result = cover_service.generate_cover(
                prompt=_build_auto_cover_prompt(row),
                draft_id=row.id,
                overwrite_draft_cover=True,
            )
            auto_cover_generated = True
            auto_cover_provider = cover_result.provider
            db.refresh(row)
        except Exception as exc:
            auto_cover_provider = (settings.IMAGE_GEN_PROVIDER or "").strip()
            auto_cover_error = str(exc)
            if settings.AUTO_GENERATE_COVER_STRICT:
                raise HTTPException(status_code=502, detail=f"auto cover generation failed: {exc}") from exc

    return DraftGenerateResponse(
        success=True,
        draft=_to_draft_out(row),
        auto_cover_generated=auto_cover_generated,
        auto_cover_provider=auto_cover_provider,
        auto_cover_error=auto_cover_error,
    )


@router.get("/api/drafts", response_model=list[DraftOut])
def list_drafts(limit: int = 100, status: str | None = None, db: Session = Depends(get_db)) -> list[DraftOut]:
    rows = DraftService(db).list_drafts(limit=limit, status=status)
    return [_to_draft_out(row) for row in rows]


@router.get("/api/drafts/{draft_id}", response_model=DraftOut)
def get_draft(draft_id: int, db: Session = Depends(get_db)) -> DraftOut:
    service = DraftService(db)
    try:
        row = service.get_draft(draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_draft_out(row)


@router.put("/api/drafts/{draft_id}", response_model=DraftOut)
def update_draft(draft_id: int, payload: DraftUpdateRequest, db: Session = Depends(get_db)) -> DraftOut:
    service = DraftService(db)
    try:
        row = service.update_draft(
            draft_id=draft_id,
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
            cover_image_url=payload.cover_image_url,
            editor_notes=payload.editor_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_draft_out(row)


@router.post("/api/drafts/{draft_id}/approve", response_model=DraftOut)
def approve_draft(draft_id: int, payload: DraftStatusUpdateRequest, db: Session = Depends(get_db)) -> DraftOut:
    service = DraftService(db)
    try:
        row = service.approve_draft(draft_id=draft_id, notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_draft_out(row)


@router.post("/api/drafts/{draft_id}/reject", response_model=DraftOut)
def reject_draft(draft_id: int, payload: DraftStatusUpdateRequest, db: Session = Depends(get_db)) -> DraftOut:
    service = DraftService(db)
    try:
        row = service.reject_draft(draft_id=draft_id, notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_draft_out(row)


@router.post("/api/publish/{draft_id}", response_model=PublishResponse)
def publish_draft(draft_id: int, request: Request, db: Session = Depends(get_db)) -> PublishResponse:
    guard_token = settings.PUBLISH_GUARD_TOKEN.strip()
    if guard_token:
        header_token = request.headers.get("X-Publish-Token", "").strip()
        if not header_token or header_token != guard_token:
            raise HTTPException(status_code=403, detail="Invalid publish token.")

    service = PublishService(db)
    try:
        task = service.publish_draft(draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = None
    if task.response_payload:
        try:
            payload = json.loads(task.response_payload)
        except Exception:
            payload = {"raw": task.response_payload}
    message = task.error_message or "publish done"
    if task.status == "succeeded" and isinstance(payload, dict):
        raw_payload = payload.get("raw")
        if isinstance(raw_payload, dict):
            raw_message = raw_payload.get("message") or raw_payload.get("status")
            if raw_message:
                message = str(raw_message)
    return PublishResponse(
        success=task.status == "succeeded",
        task_id=task.id,
        status=task.status,
        message=message,
        response_payload=payload,
    )


@router.get("/api/publish/{draft_id}/status", response_model=PublishTaskOut)
def publish_status(draft_id: int, db: Session = Depends(get_db)) -> PublishTaskOut:
    service = PublishService(db)
    task = service.get_latest_task_for_draft(draft_id)
    if not task:
        raise HTTPException(status_code=404, detail="No publish task found for this draft.")
    return _to_publish_task_out(task)


@router.get("/api/jobs/history")
def jobs_history(limit: int = 100, db: Session = Depends(get_db)) -> dict:
    rows: list[JobRun] = JobService(db).list_runs(limit=limit)
    payload = [
        {
            "id": row.id,
            "job_name": row.job_name,
            "status": row.status,
            "message": row.message,
            "created_at": row.created_at,
            "finished_at": row.finished_at,
        }
        for row in rows
    ]
    return {"success": True, "items": payload}


@router.get("/api/xhs/login-status")
def xhs_login_status() -> dict:
    client = XhsMcpClient()
    try:
        return client.get_login_status()
    except Exception as exc:
        return {"success": False, "status": "error", "message": str(exc)}


@router.get("/api/xhs/login-qrcode")
def xhs_login_qrcode() -> dict:
    client = XhsMcpClient()
    try:
        return client.get_login_qrcode()
    except Exception as exc:
        return {"success": False, "status": "error", "message": str(exc)}


@router.post("/api/xhs/reset-login")
def xhs_reset_login() -> dict:
    client = XhsMcpClient()
    try:
        return client.reset_login()
    except Exception as exc:
        return {"success": False, "status": "error", "message": str(exc)}


@router.post("/api/xhs/ping", response_model=MessageResponse)
def xhs_ping() -> MessageResponse:
    return MessageResponse(success=True, message=f"xiaohongshu mcp base: {settings.XHS_MCP_BASE_URL}")


@router.post("/api/uploads/cover")
async def upload_cover_image(file: UploadFile = File(...)) -> dict:
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIX:
        raise HTTPException(status_code=400, detail="unsupported image format")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="file too large, max 10MB")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    out_name = f"{uuid4().hex}{suffix}"
    out_path = (UPLOAD_DIR / out_name).resolve()
    out_path.write_bytes(content)

    return {
        "success": True,
        "cover_image_url": str(out_path),
        "cover_preview_url": f"/static/uploads/covers/{out_name}",
        "filename": out_name,
    }


@router.get("/api/cover/provider")
def cover_provider_info() -> dict:
    provider = (settings.IMAGE_GEN_PROVIDER or "MockAPI").strip()
    base_url = (settings.IMAGE_GEN_BASE_URL or "").strip()
    model = (settings.IMAGE_GEN_MODEL or "").strip()
    configured = True
    if provider.lower() not in {"mock", "mockapi"}:
        configured = bool(base_url and model and settings.IMAGE_GEN_API_KEY)
    return {
        "success": True,
        "provider": provider,
        "model": model or "mock-image",
        "configured": configured,
    }


@router.post("/api/cover/generate", response_model=CoverGenerateResponse)
def generate_cover(payload: CoverGenerateRequest, db: Session = Depends(get_db)) -> CoverGenerateResponse:
    service = ImageGenerationService(db)
    try:
        result = service.generate_cover(
            prompt=payload.prompt,
            draft_id=payload.draft_id,
            size=payload.size,
            overwrite_draft_cover=payload.overwrite_draft_cover,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"cover generation failed: {exc}") from exc

    return CoverGenerateResponse(
        success=True,
        provider=result.provider,
        model=result.model,
        prompt=result.prompt,
        cover_image_url=result.cover_image_url,
        cover_preview_url=result.cover_preview_url,
        draft_id=result.draft_id,
        draft_updated=result.draft_updated,
    )
