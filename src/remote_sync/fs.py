from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def sanitize_workspace_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValueError("workspace name cannot be empty")
    if any(sep in stripped for sep in ("/", "\\")):
        raise ValueError("workspace name cannot contain path separators")
    if stripped in {".", ".."}:
        raise ValueError("workspace name is invalid")
    return stripped


def sanitize_relative_path(value: str) -> PurePosixPath:
    candidate = PurePosixPath(value)
    if candidate.is_absolute():
        raise ValueError("path must be relative")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("path contains invalid segments")
    return candidate


def safe_join(root: Path, relative_path: str) -> Path:
    sanitized = sanitize_relative_path(relative_path)
    return root.joinpath(*sanitized.parts)


def replace_directory(source: Path, target: Path, backup: Path) -> None:
    if backup.exists():
        shutil.rmtree(backup)

    if target.exists():
        target.rename(backup)

    try:
        source.rename(target)
    except Exception:
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)
