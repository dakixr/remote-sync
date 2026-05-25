from __future__ import annotations

import base64
from contextlib import nullcontext
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pathspec

from remote_sync.fs import ensure_directory, sanitize_workspace_name
from remote_sync.protocol import UploadOperation


@dataclass(slots=True)
class SyncSummary:
    workspace: str
    session_id: str
    directories_sent: int
    files_sent: int


@dataclass(slots=True)
class PullSummary:
    workspace: str
    directories_written: int
    files_written: int


class SyncClient:
    def __init__(self, server_url: str, timeout: float = 30.0, token: str | None = None, http_client: Any | None = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.token = token
        self.http_client = http_client

    def _headers(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    def sync_directory(self, workspace: str, source_dir: str | Path) -> SyncSummary:
        workspace = sanitize_workspace_name(workspace)
        source_root = Path(source_dir).expanduser().resolve()
        if not source_root.exists():
            raise FileNotFoundError(f"source directory does not exist: {source_root}")
        if not source_root.is_dir():
            raise NotADirectoryError(f"source path is not a directory: {source_root}")

        spec = _load_gitignore(source_root)
        session_id = uuid.uuid4().hex
        directories_sent = 0
        files_sent = 0

        client_context = (
            nullcontext(self.http_client)
            if self.http_client is not None
            else httpx.Client(timeout=self.timeout, verify=False)
        )
        with client_context as client:
            self._post(client, workspace, session_id, UploadOperation.BEGIN)

            for directory in sorted(_iter_directories(source_root, spec)):
                relative = directory.relative_to(source_root).as_posix()
                self._post(
                    client,
                    workspace,
                    session_id,
                    UploadOperation.MKDIR,
                    path=relative,
                )
                directories_sent += 1

            for file_path in sorted(_iter_files(source_root, spec)):
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

    def pull_workspace(self, workspace: str, dest_dir: str | Path) -> PullSummary:
        workspace = sanitize_workspace_name(workspace)
        dest_root = Path(dest_dir).expanduser().resolve()

        client_context = (
            nullcontext(self.http_client)
            if self.http_client is not None
            else httpx.Client(timeout=self.timeout, verify=False)
        )
        with client_context as client:
            response = client.post(
                f"{self.server_url}/download",
                json={"workspace": workspace},
                headers=self._headers(),
            )
            response.raise_for_status()
            data = response.json()

        directories_written = 0
        files_written = 0

        for dir_path in data["directories"]:
            target = dest_root / dir_path
            ensure_directory(target)
            directories_written += 1

        for file_entry in data["files"]:
            target = dest_root / file_entry["path"]
            ensure_directory(target.parent)
            target.write_bytes(base64.b64decode(file_entry["content_b64"]))
            files_written += 1

        return PullSummary(
            workspace=workspace,
            directories_written=directories_written,
            files_written=files_written,
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

        response = client.post(f"{self.server_url}/upload", json=payload, headers=self._headers())
        response.raise_for_status()


def _load_gitignore(source_root: Path) -> pathspec.PathSpec | None:
    gitignore_path = source_root / ".gitignore"
    if not gitignore_path.is_file():
        return None
    patterns = gitignore_path.read_text(encoding="utf-8").splitlines()
    patterns.append(".git")
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def _is_ignored(path: Path, source_root: Path, spec: pathspec.PathSpec | None) -> bool:
    if spec is None:
        return path.name == ".git"
    relative = path.relative_to(source_root).as_posix()
    if path.is_dir():
        relative += "/"
    return spec.match_file(relative)


def _iter_directories(source_root: Path, spec: pathspec.PathSpec | None) -> list[Path]:
    results: list[Path] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_dir():
            continue
        if _is_ignored(path, source_root, spec):
            continue
        if any(_is_ignored(parent, source_root, spec) for parent in path.relative_to(source_root).parents if parent != Path(".")):
            continue
        results.append(path)
    return results


def _iter_files(source_root: Path, spec: pathspec.PathSpec | None) -> list[Path]:
    results: list[Path] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        if _is_ignored(path, source_root, spec):
            continue
        if any(_is_ignored(source_root / parent, source_root, spec) for parent in path.relative_to(source_root).parents if parent != Path(".")):
            continue
        results.append(path)
    return results
