from fastapi import Cookie, HTTPException

from app.auth import (
    SESSION_COOKIE_NAME,
    validate_session_token,
)


def require_authenticated_session(
    fishing_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE_NAME,
    ),
) -> None:
    if not validate_session_token(
        fishing_session or ""
    ):
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
        )
