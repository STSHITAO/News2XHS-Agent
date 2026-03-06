from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Draft
from app.utils.text_sanitize import sanitize_topic


MOCK_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNgAAAAAgAB4iG8MwAAAABJRU5ErkJggg=="
)


@dataclass
class CoverImageResult:
    provider: str
    model: str
    prompt: str
    cover_image_url: str
    cover_preview_url: str
    draft_id: int | None
    draft_updated: bool


class ImageGenerationService:
    SIZE_RE = re.compile(r"^\d{2,4}x\d{2,4}$")

    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = (settings.IMAGE_GEN_PROVIDER or "MockAPI").strip()
        self.output_dir = Path(settings.IMAGE_GEN_OUTPUT_DIR).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_cover(
        self,
        *,
        prompt: str | None = None,
        draft_id: int | None = None,
        size: str | None = None,
        overwrite_draft_cover: bool = True,
    ) -> CoverImageResult:
        draft = None
        if draft_id is not None:
            draft = self.db.get(Draft, draft_id)
            if not draft:
                raise ValueError(f"Draft not found: {draft_id}")

        final_prompt = (prompt or "").strip()
        if not final_prompt and draft is not None:
            final_prompt = self._build_prompt_from_draft(draft)
        if not final_prompt:
            raise ValueError("prompt is required when draft_id is not provided")

        final_size = self._normalize_size(size or settings.IMAGE_GEN_DEFAULT_SIZE)
        image_bytes, extension = self._generate_image_bytes(final_prompt, final_size)
        cover_image_url, cover_preview_url = self._save_image(image_bytes, extension)

        draft_updated = False
        if draft is not None and overwrite_draft_cover:
            draft.cover_image_url = cover_image_url
            self.db.commit()
            draft_updated = True

        return CoverImageResult(
            provider=self.provider,
            model=(settings.IMAGE_GEN_MODEL or "mock-image"),
            prompt=final_prompt,
            cover_image_url=cover_image_url,
            cover_preview_url=cover_preview_url,
            draft_id=draft_id,
            draft_updated=draft_updated,
        )

    def _generate_image_bytes(self, prompt: str, size: str) -> tuple[bytes, str]:
        provider = self.provider.lower()
        if provider in {"mock", "mockapi"}:
            return MOCK_PNG_BYTES, ".png"
        if provider in {"openaicompatible", "openai-compatible", "openai_compatible", "qwen"}:
            return self._generate_openai_compatible(prompt, size)
        raise ValueError(f"Unsupported IMAGE_GEN_PROVIDER: {self.provider}")

    def _generate_openai_compatible(self, prompt: str, size: str) -> tuple[bytes, str]:
        api_key = (settings.IMAGE_GEN_API_KEY or "").strip()
        base_url = (settings.IMAGE_GEN_BASE_URL or "").strip()
        model = (settings.IMAGE_GEN_MODEL or "").strip()
        if not api_key:
            raise ValueError("IMAGE_GEN_API_KEY is required")
        if not base_url:
            raise ValueError("IMAGE_GEN_BASE_URL is required")
        if not model:
            raise ValueError("IMAGE_GEN_MODEL is required")

        endpoint = base_url.rstrip("/")
        if not endpoint.endswith("/images/generations"):
            endpoint = f"{endpoint}/images/generations"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": 1,
        }

        with httpx.Client(timeout=settings.IMAGE_GEN_TIMEOUT) as client:
            # ModelScope Qwen-Image requires async mode for image generation.
            if "modelscope.cn" in endpoint:
                return self._generate_modelscope_async(client, endpoint, headers, model, prompt, size)

            response = client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            rows = data.get("data") or []
            if not rows:
                raise ValueError("image provider returned empty data")
            first = rows[0] if isinstance(rows[0], dict) else {}

            b64_value = first.get("b64_json")
            if isinstance(b64_value, str) and b64_value.strip():
                return base64.b64decode(b64_value), ".png"

            image_url = str(first.get("url") or "").strip()
            if not image_url:
                raise ValueError("image provider response has neither b64_json nor url")
            img_resp = client.get(image_url)
            img_resp.raise_for_status()
            extension = self._infer_extension_from_headers(img_resp.headers)
            return img_resp.content, extension

    def _generate_modelscope_async(
        self,
        client: httpx.Client,
        endpoint: str,
        headers: dict[str, str],
        model: str,
        prompt: str,
        size: str,
    ) -> tuple[bytes, str]:
        submit_headers = {**headers, "X-ModelScope-Async-Mode": "true"}
        submit_payload = {"model": model, "prompt": prompt, "size": size}
        submit_resp = client.post(endpoint, headers=submit_headers, json=submit_payload)
        submit_resp.raise_for_status()
        submit = submit_resp.json()
        task_id = str(submit.get("task_id") or "").strip()
        if not task_id:
            raise ValueError(f"ModelScope async submission missing task_id: {submit}")

        base_url = endpoint.rsplit("/images/generations", 1)[0]
        poll_url = f"{base_url}/tasks/{task_id}"
        poll_headers = {**headers, "X-ModelScope-Task-Type": "image_generation"}
        deadline = time.time() + max(30, int(settings.IMAGE_GEN_TIMEOUT))

        last_payload: dict[str, Any] = {}
        while time.time() < deadline:
            poll_resp = client.get(poll_url, headers=poll_headers)
            poll_resp.raise_for_status()
            data = poll_resp.json() if poll_resp.content else {}
            if isinstance(data, dict):
                last_payload = data

            status = str((data or {}).get("task_status") or "").upper()
            if status == "SUCCEED":
                image_url = self._extract_modelscope_image_url(data)
                if not image_url:
                    raise ValueError(f"ModelScope async SUCCEED without image url: {data}")
                img_resp = client.get(image_url)
                img_resp.raise_for_status()
                extension = self._infer_extension_from_headers(img_resp.headers)
                return img_resp.content, extension
            if status == "FAILED":
                raise ValueError(f"ModelScope async task failed: {data}")
            time.sleep(2.5)

        raise TimeoutError(f"ModelScope async task timeout: {last_payload}")

    @staticmethod
    def _extract_modelscope_image_url(payload: dict[str, Any]) -> str:
        urls = payload.get("output_images")
        if isinstance(urls, list) and urls:
            first = str(urls[0]).strip()
            if first:
                return first
        outputs = payload.get("outputs")
        if isinstance(outputs, dict):
            for key in ("output_images", "images", "urls"):
                value = outputs.get(key)
                if isinstance(value, list) and value:
                    first = str(value[0]).strip()
                    if first:
                        return first
        return ""

    @staticmethod
    def _infer_extension_from_headers(headers: httpx.Headers) -> str:
        ctype = (headers.get("content-type") or "").lower()
        if "png" in ctype:
            return ".png"
        if "webp" in ctype:
            return ".webp"
        if "jpeg" in ctype or "jpg" in ctype:
            return ".jpg"
        return ".png"

    def _save_image(self, image_bytes: bytes, extension: str) -> tuple[str, str]:
        suffix = extension if extension.startswith(".") else f".{extension}"
        filename = f"ai_cover_{uuid4().hex}{suffix}"
        output = (self.output_dir / filename).resolve()
        output.write_bytes(image_bytes)

        root = Path("static/uploads/covers/generated").resolve()
        try:
            rel = output.relative_to(root)
            preview_url = f"/static/uploads/covers/generated/{rel.as_posix()}"
        except Exception:
            preview_url = f"/static/uploads/covers/generated/{filename}"
        return str(output), preview_url

    @classmethod
    def _normalize_size(cls, value: str) -> str:
        text = (value or "").strip().lower()
        if not cls.SIZE_RE.match(text):
            raise ValueError("size must be formatted like 1024x1024")
        return text

    @staticmethod
    def _build_prompt_from_draft(draft: Draft) -> str:
        topic = sanitize_topic(draft.topic, max_len=24)
        title = (draft.title or "").strip()
        return (
            f"为小红书图文笔记生成封面，主题:{topic}，标题:{title}。"
            "要求: 简洁、清晰、中文可读、无水印、适合手机封面。"
        )
