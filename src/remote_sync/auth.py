from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request


def _get_required_token() -> str | None:
    return os.environ.get("REMOTE_SYNC_TOKEN") or None


def verify_token(request: Request) -> None:
    required_token = _get_required_token()
    if required_token is None:
        return
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth_header[7:]
    if token != required_token:
        raise HTTPException(status_code=401, detail="invalid token")


RequireAuth = Annotated[None, Depends(verify_token)]
