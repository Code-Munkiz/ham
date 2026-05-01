"""Server-side image generation adapters — never callable from browsers."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import struct
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from src.llm_client import (
    get_openrouter_base_url,
    normalized_openrouter_api_key,
    openrouter_api_key_is_plausible,
)

_ALLOWED_IMAGE_MIME = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})


@dataclass
class ImageGenerationResult:
    data: bytes
    mime: str
    width: int | None
    height: int | None


class ImageGenerationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def default_image_prompt_max_chars() -> int:
    raw = (os.environ.get("HAM_MEDIA_IMAGE_PROMPT_MAX_CHARS") or "").strip()
    if raw:
        try:
            return max(1, min(32_000, int(raw)))
        except ValueError:
            pass
    return 4_000


def default_image_output_max_bytes() -> int:
    raw = (os.environ.get("HAM_MEDIA_IMAGE_OUTPUT_MAX_BYTES") or "").strip()
    if raw:
        try:
            return max(10_000, min(30 * 1024 * 1024, int(raw)))
        except ValueError:
            pass
    return 12 * 1024 * 1024


def default_image_model_env() -> str:
    return (os.environ.get("HAM_MEDIA_IMAGE_DEFAULT_MODEL") or "").strip()


def image_generation_feature_enabled() -> bool:
    v = (os.environ.get("HAM_MEDIA_IMAGE_GENERATION_ENABLED") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def openrouter_api_key_configured() -> bool:
    key = normalized_openrouter_api_key()
    return bool(key and openrouter_api_key_is_plausible(key))


def prompt_digest_and_excerpt(prompt: str) -> tuple[str, str]:
    stripped = prompt.strip()
    digest = hashlib.sha256(stripped.encode("utf-8")).hexdigest()
    excerpt = stripped[:240] + ("…" if len(stripped) > 240 else "")
    return digest, excerpt


class ImageProviderAdapter(ABC):
    provider_slug: str

    @abstractmethod
    def generate_image(self, *, prompt: str, model_id: str | None) -> ImageGenerationResult: ...


class UnconfiguredImageProviderAdapter(ImageProviderAdapter):
    provider_slug = "none"

    def generate_image(self, *, prompt: str, model_id: str | None) -> ImageGenerationResult:
        _ = prompt, model_id
        raise ImageGenerationError(
            "IMAGE_GEN_NOT_CONFIGURED",
            "Image generation is not enabled or is not configured on this server.",
        )


class SyntheticTestOnlyImageAdapter(ImageProviderAdapter):
    """Returns a tiny PNG — injected in unit tests."""

    provider_slug = "test_synthetic"

    _TINY_PNG = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\x03\x1a\x00\x00\x00"
        b"\x00IEND\xaeB`\x82"
    )

    def generate_image(self, *, prompt: str, model_id: str | None) -> ImageGenerationResult:
        _ = prompt, model_id
        return ImageGenerationResult(data=self._TINY_PNG, mime="image/png", width=1, height=1)


def _parse_data_url(url: str) -> tuple[str, bytes] | None:
    if not isinstance(url, str):
        return None
    s = url.strip()
    if not s.startswith("data:"):
        return None
    m = re.match(r"data:([^;,]+)?(;base64)?,(.+)", s, re.DOTALL)
    if not m:
        return None
    mime = (m.group(1) or "application/octet-stream").strip().lower()
    payload = m.group(3) or ""
    if m.group(2):
        try:
            raw = base64.b64decode(payload, validate=False)
        except (binascii.Error, ValueError):
            return None
    else:
        raw = urllib.parse.unquote_to_bytes(payload.replace("+", "%2B"))
    return mime.split(";")[0], raw


def _png_dimensions_safe(data: bytes) -> tuple[int | None, int | None]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    try:
        w, h = struct.unpack(">II", data[16:24])
        if w <= 0 or h <= 0 or w > 32_767 or h > 32_767:
            return None, None
        return int(w), int(h)
    except (struct.error, TypeError, ValueError):
        return None, None


def _normalize_mime_image(mime: str) -> str | None:
    m = mime.strip().lower()
    if m == "image/jpg":
        m = "image/jpeg"
    return m if m in _ALLOW_IMAGE_MIME else None


def _maybe_append_data_url_parts(out: list[tuple[str, bytes]], urls: object) -> None:
    urls_list = urls if isinstance(urls, list) else []
    for item in urls_list:
        if not isinstance(item, dict):
            continue
        candidates: list[str] = []
        iu = item.get("image_url")
        if isinstance(iu, str):
            candidates.append(iu)
        elif isinstance(iu, dict):
            u = iu.get("url")
            if isinstance(u, str):
                candidates.append(u)
        for raw in candidates:
            if isinstance(raw, str) and raw.startswith("data:"):
                got = _parse_data_url(raw)
                if got:
                    mime, blob = got
                    nm = _normalize_mime_image(mime)
                    if nm and blob:
                        out.append((nm, blob))


def _extract_images_from_chat_response(body: dict[str, Any]) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return out
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return out

    imgs = msg.get("images")
    _maybe_append_data_url_parts(out, imgs)

    content = msg.get("content")
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "image_url" and isinstance(part.get("image_url"), dict):
                u = part["image_url"].get("url")
                if isinstance(u, str) and u.startswith("data:"):
                    got = _parse_data_url(u)
                    if got:
                        mime, blob = got
                        nm = _normalize_mime_image(mime)
                        if nm and blob:
                            out.append((nm, blob))

    seen: set[tuple[str, bytes]] = set()
    deduped: list[tuple[str, bytes]] = []
    for mime, blob in out:
        key = (mime, blob[:32])
        if key in seen:
            continue
        seen.add(key)
        deduped.append((mime, blob))
    return deduped


class OpenRouterImageProviderAdapter(ImageProviderAdapter):
    provider_slug = "openrouter"

    def __init__(self, *, api_url: str, api_key: str, timeout_sec: float = 120.0) -> None:
        self._url = api_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._timeout = timeout_sec

    def generate_image(self, *, prompt: str, model_id: str | None) -> ImageGenerationResult:
        mid = (model_id or default_image_model_env() or "").strip()
        if not mid:
            raise ImageGenerationError(
                "IMAGE_GEN_MODEL_MISSING",
                "No image generation model configured. "
                "Set HAM_MEDIA_IMAGE_DEFAULT_MODEL or pass model_id in the request.",
            )
        max_out = default_image_output_max_bytes()
        referer = (os.getenv("OPENROUTER_HTTP_REFERER") or "").strip()
        title_str = (os.getenv("OPENROUTER_APP_TITLE") or "").strip()
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }
        if referer:
            headers["HTTP-Referer"] = referer
        if title_str:
            headers["X-Title"] = title_str

        payload: dict[str, Any] = {
            "model": mid,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
            "max_tokens": 1024,
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                r = client.post(self._url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ImageGenerationError(
                "IMAGE_GEN_UPSTREAM_TIMEOUT",
                "Image generation timed out.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ImageGenerationError(
                "IMAGE_GEN_UPSTREAM_ERROR",
                "Could not reach the image generation service.",
            ) from exc

        if r.status_code >= 400:
            raise ImageGenerationError(
                "IMAGE_GEN_UPSTREAM_REJECTED",
                "Image generation failed. Adjust your prompt or try again.",
            )

        try:
            body = r.json()
        except json.JSONDecodeError as exc:
            raise ImageGenerationError(
                "IMAGE_GEN_INVALID_RESPONSE",
                "Image generation returned an unexpected response.",
            ) from exc

        blobs = _extract_images_from_chat_response(body if isinstance(body, dict) else {})
        if not blobs:
            raise ImageGenerationError(
                "IMAGE_GEN_NO_IMAGE",
                "The model returned no usable image.",
            )

        mime, blob = blobs[0]
        if len(blob) > max_out:
            raise ImageGenerationError(
                "IMAGE_GEN_OUTPUT_TOO_LARGE",
                "Generated image exceeds the maximum allowed size.",
            )

        w, h = (None, None)
        if mime == "image/png":
            w, h = _png_dimensions_safe(blob)

        return ImageGenerationResult(data=blob, mime=mime, width=w, height=h)


def build_default_image_adapter() -> ImageProviderAdapter:
    if not image_generation_feature_enabled():
        return UnconfiguredImageProviderAdapter()

    if not openrouter_api_key_configured():
        return UnconfiguredImageProviderAdapter()

    key_val = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key_val:
        return UnconfiguredImageProviderAdapter()

    api_base = get_openrouter_base_url().rstrip("/")
    return OpenRouterImageProviderAdapter(api_url=api_base, api_key=key_val)


_adapter_singleton: ImageProviderAdapter | None = None


def get_image_generation_adapter() -> ImageProviderAdapter:
    global _adapter_singleton
    if _adapter_singleton is None:
        _adapter_singleton = build_default_image_adapter()
    return _adapter_singleton


def set_image_generation_adapter_for_tests(adapter: ImageProviderAdapter | None) -> None:
    global _adapter_singleton
    _adapter_singleton = adapter


def rebuild_image_generation_adapter_singleton() -> None:
    """Call after monkeypatch env in tests."""
    global _adapter_singleton
    _adapter_singleton = build_default_image_adapter()
