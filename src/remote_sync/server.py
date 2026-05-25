from __future__ import annotations

import base64
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException

from remote_sync.auth import RequireAuth
from remote_sync.fs import ensure_directory, replace_directory, safe_join, sanitize_workspace_name
from remote_sync.protocol import (
    DownloadRequest,
    DownloadResponse,
    FileEntry,
    HealthResponse,
    UploadOperation,
    UploadRequest,
    UploadResponse,
)

logger = logging.getLogger("remote_sync.server")


@dataclass(slots=True)
class ServerStorage:
    root: Path

    @property
    def workspaces_dir(self) -> Path:
        return self.root / "workspaces"

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"

    def prepare(self) -> None:
        ensure_directory(self.workspaces_dir)
        ensure_directory(self.sessions_dir)

    def session_root(self, workspace: str, session_id: str) -> Path:
        return self.sessions_dir / sanitize_workspace_name(workspace) / session_id

    def session_payload_dir(self, workspace: str, session_id: str) -> Path:
        return self.session_root(workspace, session_id) / "payload"

    def workspace_dir(self, workspace: str) -> Path:
        return self.workspaces_dir / sanitize_workspace_name(workspace)


def create_app(storage_root: str | Path) -> FastAPI:
    storage = ServerStorage(Path(storage_root).resolve())
    storage.prepare()
    app = FastAPI(title="remote-sync", version="0.1.0")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/upload", response_model=UploadResponse)
    def upload(request: UploadRequest, _auth: RequireAuth) -> UploadResponse:
        try:
            workspace = sanitize_workspace_name(request.workspace)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            match request.operation:
                case UploadOperation.BEGIN:
                    return _handle_begin(storage, workspace, request.session_id)
                case UploadOperation.MKDIR:
                    assert request.path is not None
                    return _handle_mkdir(storage, workspace, request.session_id, request.path)
                case UploadOperation.FILE:
                    assert request.path is not None
                    assert request.content_b64 is not None
                    return _handle_file(
                        storage,
                        workspace,
                        request.session_id,
                        request.path,
                        request.content_b64,
                    )
                case UploadOperation.FINISH:
                    return _handle_finish(storage, workspace, request.session_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/download", response_model=DownloadResponse)
    def download(request: DownloadRequest, _auth: RequireAuth) -> DownloadResponse:
        try:
            workspace = sanitize_workspace_name(request.workspace)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        workspace_dir = storage.workspace_dir(workspace)
        if not workspace_dir.exists():
            raise HTTPException(status_code=404, detail=f"workspace not found: {workspace}")

        files: list[FileEntry] = []
        directories: list[str] = []

        for path in sorted(workspace_dir.rglob("*")):
            relative = path.relative_to(workspace_dir).as_posix()
            if path.is_dir():
                directories.append(relative)
            elif path.is_file():
                content_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
                files.append(FileEntry(path=relative, content_b64=content_b64))

        return DownloadResponse(
            workspace=workspace,
            directories=directories,
            files=files,
        )

    return app


def _handle_begin(storage: ServerStorage, workspace: str, session_id: str) -> UploadResponse:
    logger.info("sync begin workspace=%s session=%s", workspace, session_id)
    session_root = storage.session_root(workspace, session_id)
    if session_root.exists():
        shutil.rmtree(session_root)

    payload_dir = storage.session_payload_dir(workspace, session_id)
    ensure_directory(payload_dir)
    metadata_path = session_root / "metadata.json"
    metadata_path.write_text(json.dumps({"workspace": workspace, "session_id": session_id}), encoding="utf-8")
    return UploadResponse(detail="session initialized")


def _require_session_payload(storage: ServerStorage, workspace: str, session_id: str) -> Path:
    payload_dir = storage.session_payload_dir(workspace, session_id)
    if not payload_dir.exists():
        raise FileNotFoundError("sync session was not initialized")
    return payload_dir


def _handle_mkdir(storage: ServerStorage, workspace: str, session_id: str, relative_path: str) -> UploadResponse:
    logger.info("sync mkdir workspace=%s session=%s path=%s", workspace, session_id, relative_path)
    payload_dir = _require_session_payload(storage, workspace, session_id)
    target_dir = safe_join(payload_dir, relative_path)
    ensure_directory(target_dir)
    return UploadResponse(detail=f"directory created: {relative_path}")


def _handle_file(
    storage: ServerStorage,
    workspace: str,
    session_id: str,
    relative_path: str,
    content_b64: str,
) -> UploadResponse:
    logger.info("sync file workspace=%s session=%s path=%s", workspace, session_id, relative_path)
    payload_dir = _require_session_payload(storage, workspace, session_id)
    target_file = safe_join(payload_dir, relative_path)
    ensure_directory(target_file.parent)
    try:
        content = base64.b64decode(content_b64.encode("ascii"), validate=True)
    except ValueError as exc:
        raise ValueError("content_b64 is not valid base64") from exc
    target_file.write_bytes(content)
    return UploadResponse(detail=f"file stored: {relative_path}")


def _handle_finish(storage: ServerStorage, workspace: str, session_id: str) -> UploadResponse:
    logger.info("sync finish workspace=%s session=%s", workspace, session_id)
    payload_dir = _require_session_payload(storage, workspace, session_id)
    workspace_dir = storage.workspace_dir(workspace)
    ensure_directory(workspace_dir.parent)
    backup_dir = storage.root / "_backups" / workspace / session_id
    ensure_directory(backup_dir.parent)
    replace_directory(payload_dir, workspace_dir, backup_dir)
    shutil.rmtree(storage.session_root(workspace, session_id), ignore_errors=True)
    return UploadResponse(detail=f"workspace synchronized: {workspace}")
