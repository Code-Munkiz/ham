#!/usr/bin/env python3
"""Download and safely extract a preview source bundle from GCS."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path
from zipfile import ZipFile

from google.cloud import storage


def parse_gs_uri(uri: str) -> tuple[str, str]:
    value = uri.strip()
    if not value.startswith("gs://"):
        raise ValueError("PREVIEW_SOURCE_URI must start with gs://")
    no_scheme = value[5:]
    if "/" not in no_scheme:
        raise ValueError("PREVIEW_SOURCE_URI must include an object path")
    bucket, object_path = no_scheme.split("/", 1)
    if not bucket or not object_path:
        raise ValueError("PREVIEW_SOURCE_URI must include bucket and object path")
    return bucket, object_path


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    destination = destination.resolve()
    with ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target_path = (destination / member.filename).resolve()
            if os.path.commonpath([str(destination), str(target_path)]) != str(destination):
                raise ValueError(f"zip entry escapes destination: {member.filename}")
        archive.extractall(destination)


def download_and_extract(source_uri: str, destination: Path) -> None:
    bucket_name, object_path = parse_gs_uri(source_uri)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_path)

    with tempfile.NamedTemporaryFile(prefix="ham-preview-", suffix=".zip", delete=False) as handle:
        temp_zip = Path(handle.name)

    try:
        blob.download_to_filename(str(temp_zip))
        safe_extract_zip(temp_zip, destination)
    finally:
        temp_zip.unlink(missing_ok=True)


def clear_directory_contents(path: Path) -> None:
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and unpack preview source from GCS.")
    parser.add_argument("--source-uri", required=True, help="gs://bucket/path/preview-source.zip")
    parser.add_argument("--destination", default="/workspace")
    args = parser.parse_args()

    destination = Path(args.destination)
    destination.mkdir(parents=True, exist_ok=True)
    clear_directory_contents(destination)

    download_and_extract(args.source_uri, destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
