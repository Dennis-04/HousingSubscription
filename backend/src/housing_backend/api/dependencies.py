from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request, status

from housing_backend.bootstrap import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def require_admin(request: Request, x_admin_token: str | None = Header(default=None)) -> None:
    expected = get_container(request).settings.admin_api_token
    if not expected or expected.startswith("replace_with_"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="관리 API가 비활성화되어 있습니다. ADMIN_API_TOKEN을 설정하세요.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")
