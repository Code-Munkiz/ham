from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote

_WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}
_WIN_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


@dataclass(frozen=True)
class ZipIntakeCaps:
    max_compressed_bytes: int = 20 * 1024 * 1024
    max_uncompressed_bytes: int = 100 * 1024 * 1024
    max_file_count: int = 2000
    max_entry_bytes: int = 10 * 1024 * 1024
    max_path_length: int = 240
    max_manifest_entries: int = 200


@dataclass(frozen=True)
class ZipEntrySummary:
    path: str
    size_bytes: int
    compressed_bytes: int
    is_dir: bool


@dataclass(frozen=True)
class ZipValidationResult:
    digest_sha256: str
    compressed_bytes: int
    uncompressed_bytes: int
    file_count: int
    dir_count: int
    entries: list[ZipEntrySummary]


class ZipSafetyError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_IFMT(mode) == stat.S_IFLNK


def _normalized_entry_name(raw: str) -> str:
    # ZIP names are slash-separated, but malformed archives sometimes include backslashes.
    name = unquote((raw or "").replace("\\", "/")).strip()
    while "//" in name:
        name = name.replace("//", "/")
    return name


def _is_absolute_path(name: str) -> bool:
    return name.startswith("/") or name.startswith("//") or bool(_WIN_ABS_RE.match(name))


def _is_path_traversal(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return any(part == ".." for part in parts)


def _has_unsafe_segment(name: str) -> bool:
    for segment in PurePosixPath(name).parts:
        if segment in (".", "..", "/"):
            continue
        if any(ord(ch) < 32 for ch in segment):
            return True
        candidate = segment.strip().rstrip(". ").split(".")[0].upper()
        if candidate in _WINDOWS_DEVICE_NAMES:
            return True
    return False


def validate_zip_upload(payload: bytes, caps: ZipIntakeCaps | None = None) -> ZipValidationResult:
    limits = caps or ZipIntakeCaps(
        max_compressed_bytes=_int_env("HAM_BUILDER_ZIP_MAX_COMPRESSED_BYTES", 20 * 1024 * 1024),
        max_uncompressed_bytes=_int_env(
            "HAM_BUILDER_ZIP_MAX_UNCOMPRESSED_BYTES",
            100 * 1024 * 1024,
        ),
        max_file_count=_int_env("HAM_BUILDER_ZIP_MAX_FILE_COUNT", 2000),
        max_entry_bytes=_int_env("HAM_BUILDER_ZIP_MAX_ENTRY_BYTES", 10 * 1024 * 1024),
        max_path_length=_int_env("HAM_BUILDER_ZIP_MAX_PATH_LENGTH", 240),
        max_manifest_entries=_int_env("HAM_BUILDER_ZIP_MAX_MANIFEST_ENTRIES", 200),
    )
    compressed_bytes = len(payload)
    if compressed_bytes <= 0:
        raise ZipSafetyError("ZIP_EMPTY", "ZIP payload is empty.")
    if compressed_bytes > limits.max_compressed_bytes:
        raise ZipSafetyError("ZIP_TOO_LARGE", "ZIP exceeds maximum compressed size.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ZipSafetyError("ZIP_INVALID", "Invalid ZIP archive.") from exc

    entries: list[ZipEntrySummary] = []
    file_count = 0
    dir_count = 0
    total_uncompressed = 0
    for info in zf.infolist():
        name = _normalized_entry_name(info.filename)
        if not name:
            continue
        if _is_absolute_path(name):
            raise ZipSafetyError("ZIP_ABSOLUTE_PATH", "ZIP contains absolute paths.")
        if _is_path_traversal(name):
            raise ZipSafetyError("ZIP_PATH_TRAVERSAL", "ZIP contains path traversal entries.")
        if len(name) > limits.max_path_length:
            raise ZipSafetyError("ZIP_INVALID", "ZIP contains a path that exceeds length limits.")
        if _has_unsafe_segment(name):
            raise ZipSafetyError("ZIP_INVALID", "ZIP contains unsafe entry names.")
        if _is_symlink(info):
            raise ZipSafetyError("ZIP_UNSAFE_SYMLINK", "ZIP contains symbolic link entries.")
        if info.is_dir():
            dir_count += 1
            if len(entries) < limits.max_manifest_entries:
                entries.append(
                    ZipEntrySummary(
                        path=name,
                        size_bytes=0,
                        compressed_bytes=0,
                        is_dir=True,
                    )
                )
            continue
        file_count += 1
        if file_count > limits.max_file_count:
            raise ZipSafetyError("ZIP_TOO_MANY_FILES", "ZIP contains too many files.")
        if info.file_size > limits.max_entry_bytes:
            raise ZipSafetyError("ZIP_ENTRY_TOO_LARGE", "ZIP contains an oversized file.")
        total_uncompressed += int(info.file_size)
        if total_uncompressed > limits.max_uncompressed_bytes:
            raise ZipSafetyError(
                "ZIP_UNCOMPRESSED_TOO_LARGE",
                "ZIP exceeds maximum uncompressed size.",
            )
        if len(entries) < limits.max_manifest_entries:
            entries.append(
                ZipEntrySummary(
                    path=name,
                    size_bytes=int(info.file_size),
                    compressed_bytes=int(info.compress_size),
                    is_dir=False,
                )
            )
    if file_count == 0:
        raise ZipSafetyError("ZIP_EMPTY", "ZIP must contain at least one file.")
    return ZipValidationResult(
        digest_sha256=hashlib.sha256(payload).hexdigest(),
        compressed_bytes=compressed_bytes,
        uncompressed_bytes=total_uncompressed,
        file_count=file_count,
        dir_count=dir_count,
        entries=entries,
    )
