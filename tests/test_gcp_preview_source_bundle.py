from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from src.ham.builder_sandbox_provider import SandboxSourceFile
from src.ham.gcp_preview_source_bundle import (
    PlanningSourceBundleUploader,
    build_bundle_object_name,
    package_source_files_to_zip,
)


def test_package_source_files_to_zip_builds_bundle() -> None:
    pkg = package_source_files_to_zip(
        files=[
            SandboxSourceFile(path="src/main.tsx", data=b"console.log('ok')"),
            SandboxSourceFile(path="package.json", data=b'{"name":"demo"}'),
        ],
        workspace_id="ws_demo",
        project_id="proj_demo",
        runtime_job_id="crjb_1234",
    )
    assert pkg.object_name.endswith("/preview-source.zip")
    assert pkg.file_count == 2
    with zipfile.ZipFile(BytesIO(pkg.payload)) as zf:
        assert sorted(zf.namelist()) == ["package.json", "src/main.tsx"]


def test_package_source_files_to_zip_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        package_source_files_to_zip(
            files=[SandboxSourceFile(path="../escape.txt", data=b"bad")],
            workspace_id="ws_demo",
            project_id="proj_demo",
            runtime_job_id="crjb_1234",
        )


def test_build_bundle_object_name_is_stable() -> None:
    assert (
        build_bundle_object_name(
            workspace_id="ws_demo",
            project_id="proj_demo",
            runtime_job_id="crjb_1234",
        )
        == "builder-preview-runtime/ws_demo/proj_demo/crjb_1234/preview-source.zip"
    )


def test_planning_uploader_returns_uri_without_upload() -> None:
    uploader = PlanningSourceBundleUploader()
    out = uploader.upload_bundle(
        bucket="ham-preview-bucket",
        object_name="builder-preview-runtime/ws/proj/job/preview-source.zip",
        payload=b"hello",
    )
    assert out.uri == "gs://ham-preview-bucket/builder-preview-runtime/ws/proj/job/preview-source.zip"
    assert out.uploaded is False
    assert out.byte_size == 5


def test_package_source_files_to_zip_includes_package_json_at_root_after_bootstrap() -> None:
    from src.ham.builder_preview_bootstrap import ensure_preview_bootstrap_files

    files = ensure_preview_bootstrap_files(
        {
            "src/App.tsx": "export default function App() { return null; }\n",
            "src/main.tsx": "import App from './App';\n",
        },
        project_name="demo app",
    )
    sandbox_files = [
        SandboxSourceFile(path=path, data=text.encode("utf-8"))
        for path, text in sorted(files.items())
    ]
    pkg = package_source_files_to_zip(
        files=sandbox_files,
        workspace_id="ws_demo",
        project_id="proj_demo",
        runtime_job_id="crjb_5678",
    )
    with zipfile.ZipFile(BytesIO(pkg.payload)) as zf:
        names = zf.namelist()
        assert "package.json" in names
        assert all("/" not in name or name.startswith("src/") for name in names)
        assert not any(name.startswith("src/package.json") for name in names)
