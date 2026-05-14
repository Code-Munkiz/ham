"""Deterministic chat-triggered builder scaffold (no LLM codegen)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from src.ham.builder_chat_intent import classify_builder_chat_intent
from src.persistence.builder_source_store import (
    ImportJob,
    ProjectSource,
    SourceSnapshot,
    get_builder_source_store,
)

_MANIFEST_KIND_INLINE = "inline_text_bundle"
_MAX_TOTAL_TEXT = 200_000
_MAX_FILE_BYTES = 60_000
_MAX_FILES = 24


def _sanitize_title(user_plain: str) -> str:
    words = re.sub(r"[^\w\s-]", " ", user_plain, flags=re.UNICODE).split()
    title = " ".join(words[:12]).strip()
    if not title:
        return "HAM Builder App"
    return title[:120]


def _build_react_scaffold_files(user_plain: str) -> dict[str, str]:
    title = _sanitize_title(user_plain)
    safe_pkg = re.sub(r"[^a-z0-9-]", "-", title.lower())[:40].strip("-") or "ham-builder-app"
    return {
        "package.json": json.dumps(
            {
                "name": safe_pkg,
                "private": True,
                "version": "0.0.1",
                "type": "module",
                "scripts": {
                    "dev": "vite",
                    "build": "vite build",
                    "preview": "vite preview",
                },
                "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
                "devDependencies": {
                    "@vitejs/plugin-react": "^4.3.4",
                    "typescript": "^5.6.3",
                    "vite": "^5.4.11",
                },
            },
            indent=2,
        )
        + "\n",
        "index.html": (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "  <head>\n"
            '    <meta charset="UTF-8" />\n'
            f"    <title>{title}</title>\n"
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
            "  </head>\n"
            "  <body>\n"
            '    <div id="root"></div>\n'
            '    <script type="module" src="/src/main.tsx"></script>\n'
            "  </body>\n"
            "</html>\n"
        ),
        "src/main.tsx": (
            "import React from \"react\";\n"
            "import ReactDOM from \"react-dom/client\";\n"
            "import App from \"./App\";\n"
            "import \"./styles.css\";\n"
            "ReactDOM.createRoot(document.getElementById(\"root\")!).render(\n"
            "  <React.StrictMode>\n"
            "    <App />\n"
            "  </React.StrictMode>,\n"
            ");\n"
        ),
        "src/App.tsx": (
            "import React from \"react\";\n"
            "export default function App() {\n"
            f"  return (\n"
            f"    <main className=\"app-shell\">\n"
            f"      <h1>{title}</h1>\n"
            "      <p className=\"muted\">\n"
            "        Scaffold created from your chat request. HAM will attach a cloud preview when the preview\n"
            "        environment is ready. Use the Code tab to browse source files.\n"
            "      </p>\n"
            "      <p className=\"muted developer-hint\">\n"
            "        Developer: you may run <code>npm install</code> and <code>npm run dev</code> locally if needed.\n"
            "      </p>\n"
            "    </main>\n"
            "  );\n"
            "}\n"
        ),
        "src/styles.css": (
            ":root {\n"
            "  font-family: system-ui, sans-serif;\n"
            "  color: #e8eef8;\n"
            "  background: #040d14;\n"
            "}\n"
            ".app-shell {\n"
            "  max-width: 720px;\n"
            "  margin: 3rem auto;\n"
            "  padding: 0 1.5rem;\n"
            "}\n"
            ".muted {\n"
            "  color: rgba(232, 238, 248, 0.72);\n"
            "  line-height: 1.5;\n"
            "}\n"
        ),
        "README.md": (
            f"# {title}\n\n"
            "This is a small Vite + React scaffold produced by HAM chat.\n\n"
            "- **Preview:** HAM attaches a cloud preview when the preview environment is ready (see the Workbench Preview tab).\n"
            "- **Code:** Source files are listed under the Workbench Code tab.\n\n"
            "### Developer (optional)\n\n"
            "For local debugging you can run `npm install` and `npm run dev` on your machine.\n"
        ),
    }


def _bounded_files(user_plain: str) -> dict[str, str]:
    raw = _build_react_scaffold_files(user_plain)
    if len(raw) > _MAX_FILES:
        raise ValueError("too_many_files")
    out: dict[str, str] = {}
    total = 0
    for rel, text in raw.items():
        norm = rel.replace("\\", "/").lstrip("/")
        if not norm or ".." in norm.split("/"):
            continue
        body = text if isinstance(text, str) else str(text)
        if len(body.encode("utf-8")) > _MAX_FILE_BYTES:
            body = body.encode("utf-8")[:_MAX_FILE_BYTES].decode("utf-8", errors="ignore")
        total += len(body)
        if total > _MAX_TOTAL_TEXT:
            raise ValueError("bundle_too_large")
        out[norm] = body
    return out


def _fingerprint(session_id: str, user_plain: str) -> str:
    payload = f"{session_id}\n{user_plain.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def materialize_inline_files_as_zip_artifact(
    *,
    workspace_id: str,
    project_id: str,
    files: dict[str, str],
) -> tuple[str, int]:
    """Write a bounded ZIP to the builder artifact dir; return (builder-artifact:// URI, zip byte size)."""
    artifact_id = f"bzip_{uuid.uuid4().hex}"
    root = _artifact_root()
    target_dir = root / workspace_id / project_id
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / f"{artifact_id}.zip"
    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, text in sorted(files.items()):
            norm = rel.replace("\\", "/").lstrip("/")
            if not norm or ".." in norm.split("/"):
                continue
            zf.writestr(norm, text.encode("utf-8"))
    payload = buf.getvalue()
    max_zip = 50 * 1024 * 1024
    if len(payload) > max_zip:
        raise ValueError("artifact_zip_too_large")
    zip_path.write_bytes(payload)
    return f"builder-artifact://{artifact_id}", len(payload)


def _existing_fingerprint_snapshot_id(
    *,
    workspace_id: str,
    project_id: str,
    fingerprint: str,
) -> str | None:
    store = get_builder_source_store()
    for snap in store.list_source_snapshots(workspace_id=workspace_id, project_id=project_id):
        meta = snap.metadata or {}
        if str(meta.get("chat_scaffold_fingerprint") or "") == fingerprint:
            return snap.id
    return None


def maybe_chat_scaffold_for_turn(
    *,
    workspace_id: str | None,
    project_id: str | None,
    session_id: str,
    last_user_plain: str,
    created_by: str,
) -> dict[str, Any] | None:
    """If eligible, create ProjectSource + snapshot + import job; return summary dict."""
    ws = (workspace_id or "").strip()
    pid = (project_id or "").strip()
    if not ws or not pid:
        return None
    if classify_builder_chat_intent(last_user_plain) != "build_or_create":
        return None
    fp = _fingerprint(session_id, last_user_plain)
    existing_snapshot_id = _existing_fingerprint_snapshot_id(
        workspace_id=ws,
        project_id=pid,
        fingerprint=fp,
    )
    if existing_snapshot_id:
        return {
            "builder_intent": "build_or_create",
            "scaffolded": False,
            "deduplicated": True,
            "source_snapshot_id": existing_snapshot_id,
        }

    files = _bounded_files(last_user_plain)
    entries_manifest: list[dict[str, Any]] = []
    total_bytes = 0
    for path, text in sorted(files.items()):
        b = text.encode("utf-8")
        total_bytes += len(b)
        entries_manifest.append(
            {
                "path": path,
                "size_bytes": len(b),
                "text": text,
            }
        )

    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest()
    artifact_uri, zip_size = materialize_inline_files_as_zip_artifact(
        workspace_id=ws,
        project_id=pid,
        files=files,
    )
    store = get_builder_source_store()

    job = store.create_import_job(
        workspace_id=ws,
        project_id=pid,
        created_by=created_by,
        phase="received",
        status="queued",
        metadata={
            "activity_title": "Builder request received",
            "activity_message": "Chat requested a new builder scaffold.",
            "origin": "chat_scaffold",
        },
    )
    job = store.mark_import_job_running(import_job_id=job.id, phase="scaffolding")
    job = store.upsert_import_job(
        job.model_copy(
            update={
                "metadata": {
                    **(job.metadata or {}),
                    "activity_title": "Preparing your project source",
                    "activity_message": "Creating initial files from your chat prompt.",
                },
            },
        ),
    )

    source = ProjectSource(
        workspace_id=ws,
        project_id=pid,
        kind="chat_scaffold",
        status="ready",
        display_name="Chat scaffold",
        origin_ref="ham_chat",
        created_by=created_by,
        metadata={"chat_scaffold": "1", "import_job_id": job.id},
    )
    source = store.upsert_project_source(source)

    snapshot = SourceSnapshot(
        workspace_id=ws,
        project_id=pid,
        project_source_id=source.id,
        digest_sha256=digest,
        size_bytes=zip_size,
        artifact_uri=artifact_uri,
        manifest={
            "kind": _MANIFEST_KIND_INLINE,
            "file_count": len(entries_manifest),
            "entries": [{"path": e["path"], "size_bytes": e["size_bytes"]} for e in entries_manifest],
            "inline_files": files,
        },
        created_by=created_by,
        metadata={
            "chat_scaffold": "1",
            "chat_scaffold_fingerprint": fp,
            "import_job_id": job.id,
        },
    )
    snapshot = store.upsert_source_snapshot(snapshot)
    source.active_snapshot_id = snapshot.id
    source = store.upsert_project_source(source)

    job_done = store.mark_import_job_succeeded(
        import_job_id=job.id,
        phase="materialized",
        source_snapshot_id=snapshot.id,
        stats={"file_count": len(files), "inline_bytes": total_bytes, "artifact_zip_bytes": zip_size},
    )
    job_done = store.upsert_import_job(
        job_done.model_copy(
            update={
                "metadata": {
                    **(job_done.metadata or {}),
                    "activity_title": "Code files ready",
                    "activity_message": "Workbench Code tab can list this snapshot.",
                },
            },
        ),
    )

    return {
        "builder_intent": "build_or_create",
        "scaffolded": True,
        "project_source_id": source.id,
        "source_snapshot_id": snapshot.id,
        "import_job_id": job_done.id,
    }


def read_inline_snapshot_file(*, snapshot: SourceSnapshot, rel_path: str) -> tuple[str, int] | None:
    """Return (utf-8 text, byte length) for an inline scaffold file, or None."""
    manifest = snapshot.manifest or {}
    if manifest.get("kind") != _MANIFEST_KIND_INLINE:
        return None
    raw_files = manifest.get("inline_files")
    if not isinstance(raw_files, dict):
        return None
    norm = rel_path.replace("\\", "/").lstrip("/")
    if ".." in norm.split("/"):
        return None
    text = raw_files.get(norm)
    if not isinstance(text, str):
        return None
    b = text.encode("utf-8")
    if len(b) > _MAX_FILE_BYTES:
        return None
    return text, len(b)


def read_zip_snapshot_file_bytes(*, zip_bytes: bytes, rel_path: str, max_out: int) -> bytes | None:
    norm = rel_path.replace("\\", "/").lstrip("/")
    if ".." in norm.split("/"):
        return None
    try:
        buf = BytesIO(zip_bytes)
        with zipfile.ZipFile(buf) as zf:
            info = zf.getinfo(norm)
            if info.is_dir():
                return None
            if info.file_size > max_out:
                return None
            data = zf.read(info)
            if len(data) > max_out:
                return None
            return data
    except (KeyError, OSError, zipfile.BadZipFile, RuntimeError):
        return None


def _artifact_root() -> Path:
    raw = (os.environ.get("HAM_BUILDER_SOURCE_ARTIFACT_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".ham" / "builder-source-artifacts").resolve()


def load_zip_bytes_for_snapshot(
    *,
    workspace_id: str,
    project_id: str,
    artifact_id: str,
) -> bytes | None:
    root = _artifact_root() / workspace_id / project_id
    path = root / f"{artifact_id}.zip"
    try:
        if path.is_file() and path.stat().st_size <= 50 * 1024 * 1024:
            return path.read_bytes()
    except OSError:
        return None
    return None
