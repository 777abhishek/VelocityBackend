from __future__ import annotations

from typing import Optional

from fastapi import Request


def is_authorized(request: Request, api_key: Optional[str]) -> bool:
    if not api_key:
        return True
    auth = request.headers.get("Authorization")
    return auth == f"Bearer {api_key}" if auth else False
