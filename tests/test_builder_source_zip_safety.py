from __future__ import annotations

import asyncio
import io
import zipfile

import pytest

from src.ham.builder_zip_intake import (
    ZipIntakeCaps,
    ZipSafetyError,
    read_zip_upload_bytes,
    validate_zip_upload,
)


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, body in entries.items():
            zf.writestr(name, body)
    return buff.getvalue()


def test_validate_zip_upload_accepts_small_zip() -> None:
    payload = _zip_bytes({"src/main.py": b"print('ok')\n"})
    result = validate_zip_upload(payload, ZipIntakeCaps(max_manifest_entries=10))
    assert result.file_count == 1
    assert result.uncompressed_bytes > 0
    assert len(result.digest_sha256) == 64


def test_validate_zip_upload_rejects_path_traversal() -> None:
    payload = _zip_bytes({"../../evil.txt": b"x"})
    with pytest.raises(ZipSafetyError) as exc:
        validate_zip_upload(payload)
    assert exc.value.code == "ZIP_PATH_TRAVERSAL"


def test_validate_zip_upload_rejects_absolute_path() -> None:
    payload = _zip_bytes({"/etc/passwd": b"x"})
    with pytest.raises(ZipSafetyError) as exc:
        validate_zip_upload(payload)
    assert exc.value.code == "ZIP_ABSOLUTE_PATH"


def test_validate_zip_upload_rejects_too_many_files() -> None:
    payload = _zip_bytes({"a.txt": b"1", "b.txt": b"2"})
    with pytest.raises(ZipSafetyError) as exc:
        validate_zip_upload(payload, ZipIntakeCaps(max_file_count=1))
    assert exc.value.code == "ZIP_TOO_MANY_FILES"


def test_validate_zip_upload_rejects_oversized_entry() -> None:
    payload = _zip_bytes({"big.bin": b"x" * 32})
    with pytest.raises(ZipSafetyError) as exc:
        validate_zip_upload(payload, ZipIntakeCaps(max_entry_bytes=16))
    assert exc.value.code == "ZIP_ENTRY_TOO_LARGE"


class _ChunkedFakeUpload:
    """Minimal async ``read`` surface matching ``starlette.datastructures.UploadFile``."""

    def __init__(self, total_bytes: int) -> None:
        self._i = 0
        self._total = total_bytes

    async def read(self, n: int) -> bytes:
        if self._i >= self._total:
            return b""
        take = min(n, self._total - self._i)
        out = b"z" * take
        self._i += len(out)
        return out


def test_read_zip_upload_bytes_accepts_under_cap() -> None:
    caps = ZipIntakeCaps(max_compressed_bytes=64)
    got = asyncio.run(read_zip_upload_bytes(_ChunkedFakeUpload(50), caps=caps))
    assert len(got) == 50


def test_read_zip_upload_bytes_rejects_over_cap() -> None:
    caps = ZipIntakeCaps(max_compressed_bytes=32)
    with pytest.raises(ZipSafetyError) as exc:
        asyncio.run(read_zip_upload_bytes(_ChunkedFakeUpload(100), caps=caps))
    assert exc.value.code == "ZIP_TOO_LARGE"
