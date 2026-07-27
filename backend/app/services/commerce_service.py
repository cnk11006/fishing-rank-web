from __future__ import annotations

import base64
import threading
import time
from typing import Any

import bcrypt
import requests

from app.config import get_settings


TOKEN_URL = (
    "https://api.commerce.naver.com"
    "/external/v1/oauth2/token"
)
CHANNEL_PRODUCT_URL = (
    "https://api.commerce.naver.com"
    "/external/v2/products/channel-products/{channel_product_no}"
)

_token_lock = threading.Lock()
_cached_token = ""
_cached_token_expires_at = 0.0


class CommerceApiError(Exception):
    pass


class CommerceApiConfigurationError(CommerceApiError):
    pass


def commerce_api_ready() -> bool:
    return get_settings().commerce_api_settings_ready


def generate_client_secret_sign(
    client_id: str,
    client_secret: str,
    timestamp: int,
) -> str:
    password = f"{client_id}_{timestamp}".encode("utf-8")

    try:
        hashed = bcrypt.hashpw(
            password,
            client_secret.encode("utf-8"),
        )
    except (ValueError, TypeError) as error:
        raise CommerceApiConfigurationError(
            "커머스 API 애플리케이션 시크릿 형식이 올바르지 않습니다."
        ) from error

    return base64.b64encode(hashed).decode("utf-8")


def _response_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""

    if not isinstance(payload, dict):
        return ""

    return str(
        payload.get("message")
        or payload.get("detail")
        or payload.get("code")
        or ""
    ).strip()


def issue_access_token() -> tuple[str, int]:
    settings = get_settings()

    if not settings.commerce_api_settings_ready:
        raise CommerceApiConfigurationError(
            "네이버 커머스 API 환경설정이 완료되지 않았습니다."
        )

    timestamp = int(time.time() * 1000)
    signature = generate_client_secret_sign(
        settings.naver_commerce_client_id,
        settings.naver_commerce_client_secret,
        timestamp,
    )

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": settings.naver_commerce_client_id,
                "timestamp": timestamp,
                "client_secret_sign": signature,
                "grant_type": "client_credentials",
                "type": "SELF",
            },
            headers={
                "Accept": "application/json",
                "Content-Type": (
                    "application/x-www-form-urlencoded"
                ),
            },
            timeout=(5, 20),
        )
    except requests.RequestException as error:
        raise CommerceApiError(
            "네이버 커머스 API 인증 서버에 연결하지 못했습니다."
        ) from error

    if response.status_code != 200:
        message = _response_message(response)
        suffix = f" ({message})" if message else ""

        raise CommerceApiError(
            "네이버 커머스 API 인증에 실패했습니다"
            f": HTTP {response.status_code}{suffix}"
        )

    try:
        payload = response.json()
    except ValueError as error:
        raise CommerceApiError(
            "커머스 API 인증 응답을 해석하지 못했습니다."
        ) from error

    token = str(payload.get("access_token") or "").strip()

    if not token:
        raise CommerceApiError(
            "커머스 API 인증 토큰이 응답에 없습니다."
        )

    try:
        expires_in = int(payload.get("expires_in") or 180)
    except (TypeError, ValueError):
        expires_in = 180

    return token, max(expires_in, 60)


def get_access_token(
    force_refresh: bool = False,
) -> str:
    global _cached_token
    global _cached_token_expires_at

    now = time.time()

    if (
        not force_refresh
        and _cached_token
        and now < _cached_token_expires_at
    ):
        return _cached_token

    with _token_lock:
        now = time.time()

        if (
            not force_refresh
            and _cached_token
            and now < _cached_token_expires_at
        ):
            return _cached_token

        token, expires_in = issue_access_token()
        _cached_token = token
        _cached_token_expires_at = (
            now + max(expires_in - 30, 30)
        )
        return token


def _request_channel_product(
    channel_product_no: str,
    token: str,
) -> requests.Response:
    try:
        return requests.get(
            CHANNEL_PRODUCT_URL.format(
                channel_product_no=channel_product_no
            ),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=(5, 20),
        )
    except requests.RequestException as error:
        raise CommerceApiError(
            "네이버 커머스 API 상품 조회 서버에 연결하지 못했습니다."
        ) from error


def extract_product_information(
    payload: dict[str, Any],
    channel_product_no: str,
) -> dict[str, str]:
    origin_product = payload.get("originProduct")

    if not isinstance(origin_product, dict):
        origin_product = {}

    smartstore_product = payload.get(
        "smartstoreChannelProduct"
    )

    if not isinstance(smartstore_product, dict):
        smartstore_product = {}

    channel_title = str(
        smartstore_product.get("channelProductName")
        or payload.get("channelProductName")
        or ""
    ).strip()

    origin_title = str(
        origin_product.get("name")
        or payload.get("name")
        or ""
    ).strip()

    title = channel_title or origin_title

    origin_product_no = str(
        payload.get("originProductNo")
        or origin_product.get("originProductNo")
        or ""
    ).strip()

    returned_channel_no = str(
        payload.get("channelProductNo")
        or smartstore_product.get("channelProductNo")
        or channel_product_no
    ).strip()

    return {
        "current_title": title,
        "channel_product_no": returned_channel_no,
        "origin_product_no": origin_product_no,
    }


def fetch_channel_product(
    channel_product_no: str,
) -> dict[str, str]:
    product_no = str(channel_product_no or "").strip()

    if not product_no.isdigit():
        raise CommerceApiError(
            "스마트스토어 채널상품번호가 올바르지 않습니다."
        )

    token = get_access_token()
    response = _request_channel_product(
        product_no,
        token,
    )

    if response.status_code == 401:
        token = get_access_token(force_refresh=True)
        response = _request_channel_product(
            product_no,
            token,
        )

    if response.status_code != 200:
        message = _response_message(response)
        suffix = f" ({message})" if message else ""

        raise CommerceApiError(
            "커머스 API에서 상품을 조회하지 못했습니다"
            f": HTTP {response.status_code}{suffix}"
        )

    try:
        payload = response.json()
    except ValueError as error:
        raise CommerceApiError(
            "커머스 API 상품 응답을 해석하지 못했습니다."
        ) from error

    if not isinstance(payload, dict):
        raise CommerceApiError(
            "커머스 API 상품 응답 형식이 올바르지 않습니다."
        )

    result = extract_product_information(
        payload,
        product_no,
    )

    if not result["current_title"]:
        raise CommerceApiError(
            "커머스 API 응답에서 상품명을 찾지 못했습니다."
        )

    return result
