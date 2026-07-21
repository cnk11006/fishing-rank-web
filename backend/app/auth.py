from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import get_settings


router = APIRouter(
    prefix="/api/auth",
    tags=["authentication"],
)

MAX_LOGIN_FAILURES = 5
LOGIN_LOCK_SECONDS = 60
SESSION_DURATION_SECONDS = 60 * 60 * 8
SESSION_COOKIE_NAME = "fishing_session"


@dataclass
class LoginAttempt:
    failures: int = 0
    locked_until: float = 0.0


class LoginRequest(BaseModel):
    password: str = Field(
        min_length=1,
        max_length=256,
    )


_attempts: dict[str, LoginAttempt] = {}
_attempts_lock = threading.Lock()


def encode_base64(value: bytes) -> str:
    return (
        base64.urlsafe_b64encode(value)
        .decode("ascii")
        .rstrip("=")
    )


def decode_base64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)

    return base64.urlsafe_b64decode(
        value + padding
    )


def get_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get(
        "x-forwarded-for",
        "",
    )

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    if request.client:
        return request.client.host

    return "unknown"


def create_session_token() -> str:
    settings = get_settings()
    now = int(time.time())

    payload = {
        "issued_at": now,
        "expires_at": now + SESSION_DURATION_SECONDS,
        "nonce": secrets.token_urlsafe(16),
    }

    payload_text = encode_base64(
        json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    signature = hmac.new(
        settings.session_secret.encode("utf-8"),
        payload_text.encode("ascii"),
        hashlib.sha256,
    ).digest()

    return (
        f"{payload_text}."
        f"{encode_base64(signature)}"
    )


def validate_session_token(token: str) -> bool:
    settings = get_settings()

    if not token or not settings.session_secret:
        return False

    try:
        payload_text, signature_text = token.split(".", 1)

        expected_signature = hmac.new(
            settings.session_secret.encode("utf-8"),
            payload_text.encode("ascii"),
            hashlib.sha256,
        ).digest()

        supplied_signature = decode_base64(
            signature_text
        )

        if not hmac.compare_digest(
            supplied_signature,
            expected_signature,
        ):
            return False

        payload = json.loads(
            decode_base64(payload_text)
            .decode("utf-8")
        )

        expires_at = int(
            payload.get("expires_at", 0)
        )

        return expires_at > int(time.time())

    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ):
        return False


def check_login_lock(
    client_identifier: str,
) -> int:
    current_time = time.time()

    with _attempts_lock:
        attempt = _attempts.get(
            client_identifier,
            LoginAttempt(),
        )

        if attempt.locked_until > current_time:
            return max(
                1,
                int(
                    attempt.locked_until
                    - current_time
                ) + 1,
            )

        if attempt.locked_until:
            _attempts.pop(
                client_identifier,
                None,
            )

    return 0


def register_login_failure(
    client_identifier: str,
) -> tuple[int, int]:
    current_time = time.time()

    with _attempts_lock:
        attempt = _attempts.get(
            client_identifier,
            LoginAttempt(),
        )

        attempt.failures += 1

        if attempt.failures >= MAX_LOGIN_FAILURES:
            attempt.locked_until = (
                current_time
                + LOGIN_LOCK_SECONDS
            )

        _attempts[client_identifier] = attempt

        remaining_attempts = max(
            0,
            MAX_LOGIN_FAILURES - attempt.failures,
        )

        lock_seconds = (
            LOGIN_LOCK_SECONDS
            if attempt.locked_until > current_time
            else 0
        )

    return remaining_attempts, lock_seconds


def clear_login_failures(
    client_identifier: str,
) -> None:
    with _attempts_lock:
        _attempts.pop(
            client_identifier,
            None,
        )


@router.post("/login")
def login(
    login_request: LoginRequest,
    request: Request,
) -> JSONResponse:
    settings = get_settings()

    if not settings.authentication_ready:
        raise HTTPException(
            status_code=503,
            detail=(
                "로그인 환경설정이 완료되지 않았습니다."
            ),
        )

    client_identifier = get_client_identifier(
        request
    )

    remaining_lock_seconds = check_login_lock(
        client_identifier
    )

    if remaining_lock_seconds > 0:
        raise HTTPException(
            status_code=429,
            detail={
                "message": (
                    "로그인 실패 횟수가 많습니다."
                ),
                "retry_after": (
                    remaining_lock_seconds
                ),
            },
        )

    password_matches = hmac.compare_digest(
        login_request.password.encode("utf-8"),
        settings.app_password.encode("utf-8"),
    )

    if not password_matches:
        (
            remaining_attempts,
            lock_seconds,
        ) = register_login_failure(
            client_identifier
        )

        if lock_seconds:
            raise HTTPException(
                status_code=429,
                detail={
                    "message": (
                        "로그인 실패 횟수가 많습니다."
                    ),
                    "retry_after": lock_seconds,
                },
            )

        raise HTTPException(
            status_code=401,
            detail={
                "message": (
                    "비밀번호가 올바르지 않습니다."
                ),
                "remaining_attempts": (
                    remaining_attempts
                ),
            },
        )

    clear_login_failures(client_identifier)

    token = create_session_token()

    response = JSONResponse(
        content={
            "authenticated": True,
            "message": "로그인되었습니다.",
        }
    )

    production_mode = (
        settings.app_environment.lower()
        == "production"
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_DURATION_SECONDS,
        httponly=True,
        secure=production_mode,
        samesite=(
            "none"
            if production_mode
            else "lax"
        ),
        path="/",
    )

    return response


@router.get("/status")
def authentication_status(
    fishing_session: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE_NAME,
    ),
) -> dict[str, bool]:
    return {
        "authenticated": validate_session_token(
            fishing_session or ""
        )
    }


@router.post("/logout")
def logout() -> JSONResponse:
    response = JSONResponse(
        content={
            "authenticated": False,
            "message": "로그아웃되었습니다.",
        }
    )

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )

    return response
