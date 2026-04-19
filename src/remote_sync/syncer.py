from __future__ import annotations

import base64
from contextlib import nullcontext
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from remote_sync.fs import sanitize_workspace_name
from remote_sync.protocol import UploadOperation


@dataclass(slots=True)
class SyncSummary:
    workspace: str
    session_id: str
    directories_sent: int
    files_sent: int


class SyncClient:
    def __init__(self, server_url: str, timeout: float = 30.0, http_client: Any | None = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.http_client = http_client

    def sync_directory(self, workspace: str, source_dir: str | Path) -> SyncSummary:
        workspace = sanitize_workspace_name(workspace)
        source_root = Path(source_dir).expanduser().resolve()
        if not source_root.exists():
            raise FileNotFoundError(f"source directory does not exist: {source_root}")
        if not source_root.is_dir():
            raise NotADirectoryError(f"source path is not a directory: {source_root}")

        session_id = uuid.uuid4().hex
        directories_sent = 0
        files_sent = 0

        client_context = (
            nullcontext(self.http_client)
            if self.http_client is not None
            else httpx.Client(timeout=self.timeout)
        )
        with client_context as client:
            self._post(client, workspace, session_id, UploadOperation.BEGIN)

            for directory in sorted(_iter_directories(source_root)):
                relative = directory.relative_to(source_root).as_posix()
                self._post(
                    client,
                    workspace,
                    session_id,
                    UploadOperation.MKDIR,
                    path=relative,
                )
                directories_sent += 1

            for file_path in sorted(_iter_files(source_root)):
                relative = file_path.relative_to(source_root).as_posix()
                content_b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
                self._post(
                    client,
                    workspace,
                    session_id,
                    UploadOperation.FILE,
                    path=relative,
                    content_b64=content_b64,
                )
                files_sent += 1

            self._post(client, workspace, session_id, UploadOperation.FINISH)

        return SyncSummary(
            workspace=workspace,
            session_id=session_id,
            directories_sent=directories_sent,
            files_sent=files_sent,
        )

    def _post(
        self,
        client: Any,
        workspace: str,
        session_id: str,
        operation: UploadOperation,
        *,
        path: str | None = None,
        content_b64: str | None = None,
    ) -> None:
        payload = {
            "workspace": workspace,
            "session_id": session_id,
            "operation": operation.value,
        }
        if path is not None:
            payload["path"] = path
        if content_b64 is not None:
            payload["content_b64"] = content_b64

        response = client.post(f"{self.server_url}/upload", json=payload)
        response.raise_for_status()


def _iter_directories(source_root: Path) -> list[Path]:
    return [path for path in source_root.rglob("*") if path.is_dir()]


def _iter_files(source_root: Path) -> list[Path]:
    return [path for path in source_root.rglob("*") if path.is_file()]
