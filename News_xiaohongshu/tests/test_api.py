import os
import sys
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DB_PATH = ROOT / f"test_news_xhs_{uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["DB_DIALECT"] = "sqlite"
os.environ["SCHEDULER_ENABLED"] = "False"
os.environ["SEARCH_TOOL_TYPE"] = "MockAPI"
os.environ["PUBLISH_GUARD_TOKEN"] = "unit-test-token"
os.environ["IMAGE_GEN_PROVIDER"] = "MockAPI"

from app.main import app  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.models import Base  # noqa: E402

client = TestClient(app)
Base.metadata.create_all(bind=engine)


def _create_approved_draft() -> int:
    fetch_resp = client.post(
        "/api/news/hot/fetch",
        json={"query": "test hot topic", "limit": 5, "period": "24h"},
    )
    assert fetch_resp.status_code == 200

    draft_resp = client.post(
        "/api/drafts/generate",
        json={"topic": "test hot topic", "max_news_items": 3},
    )
    assert draft_resp.status_code == 200
    draft_id = draft_resp.json()["draft"]["id"]

    approve_resp = client.post(
        f"/api/drafts/{draft_id}/approve",
        json={"notes": "ok"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"
    return draft_id


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_admin_pages() -> None:
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert "Draft" in resp.text or "草稿" in resp.text


def test_news_to_draft_edit_approve_flow() -> None:
    fetch_resp = client.post(
        "/api/news/hot/fetch",
        json={"query": "test hot topic", "limit": 5, "period": "24h"},
    )
    assert fetch_resp.status_code == 200
    assert fetch_resp.json()["count"] >= 1

    draft_resp = client.post(
        "/api/drafts/generate",
        json={"topic": "test hot topic", "max_news_items": 3},
    )
    assert draft_resp.status_code == 200
    assert isinstance(draft_resp.json().get("auto_cover_generated"), bool)
    draft = draft_resp.json()["draft"]
    draft_id = draft["id"]

    detail_resp = client.get(f"/api/drafts/{draft_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == draft_id

    update_resp = client.put(
        f"/api/drafts/{draft_id}",
        json={
            "title": "manual title update",
            "content": "manual body\nsecond paragraph",
            "tags": ["test", "half-auto"],
            "cover_image_url": "https://example.com/image.jpg",
            "editor_notes": "manual edit",
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "manual title update"
    assert "test" in update_resp.json()["tags"]

    editor_resp = client.get(f"/admin/draft/{draft_id}")
    assert editor_resp.status_code == 200
    assert str(draft_id) in editor_resp.text

    approve_resp = client.post(
        f"/api/drafts/{draft_id}/approve",
        json={"notes": "ok"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"


def test_publish_guard_requires_token() -> None:
    draft_id = _create_approved_draft()
    resp = client.post(f"/api/publish/{draft_id}")
    assert resp.status_code == 403
    assert "Invalid publish token" in resp.text


def test_upload_cover_image() -> None:
    payload = BytesIO(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01\xe2!\xbc3"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    resp = client.post(
        "/api/uploads/cover",
        files={"file": ("cover.png", payload, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["cover_image_url"]
    assert body["cover_preview_url"].startswith("/static/uploads/covers/")


def test_generate_cover_with_draft_updates_cover_path() -> None:
    draft_id = _create_approved_draft()
    resp = client.post(
        "/api/cover/generate",
        json={"draft_id": draft_id, "overwrite_draft_cover": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["provider"] in {"MockAPI", "mock", "mockapi"}
    assert body["cover_image_url"]
    assert body["cover_preview_url"].startswith("/static/uploads/covers/generated/")

    detail = client.get(f"/api/drafts/{draft_id}")
    assert detail.status_code == 200
    assert detail.json()["cover_image_url"] == body["cover_image_url"]
