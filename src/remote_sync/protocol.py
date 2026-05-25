from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UploadOperation(StrEnum):
    BEGIN = "begin"
    MKDIR = "mkdir"
    FILE = "file"
    FINISH = "finish"


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: UploadOperation
    workspace: str = Field(min_length=1, max_length=255)
    session_id: str = Field(min_length=1, max_length=255)
    path: str | None = None
    content_b64: str | None = None

    @field_validator("path")
    @classmethod
    def validate_path_presence(cls, value: str | None, info) -> str | None:
        operation = info.data.get("operation")
        if operation in {UploadOperation.MKDIR, UploadOperation.FILE} and not value:
            raise ValueError("path is required for mkdir and file operations")
        return value

    @field_validator("content_b64")
    @classmethod
    def validate_content_presence(cls, value: str | None, info) -> str | None:
        operation = info.data.get("operation")
        if operation == UploadOperation.FILE and value is None:
            raise ValueError("content_b64 is required for file operations")
        return value


class UploadResponse(BaseModel):
    ok: bool = True
    detail: str


class HealthResponse(BaseModel):
    status: str = "ok"


class DownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace: str = Field(min_length=1, max_length=255)


class FileEntry(BaseModel):
    path: str
    content_b64: str


class DownloadResponse(BaseModel):
    workspace: str
    directories: list[str]
    files: list[FileEntry]
