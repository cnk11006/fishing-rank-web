from __future__ import annotations

import base64
import hashlib
import hmac
import threading
import time
from typing import Any

import requests

from app.config import get_settings


SEARCH_AD_BASE_URL = (
    "https://api.searchad.naver.com"
)

REQUEST_INTERVAL = 0.15
_request_lock = threading.Lock()
_last_request_at = 0.0


class AdvertisingApiError(Exception):
    pass


def wait_for_request_slot() -> None:
    global _last_request_at

    with _request_lock:
        current_time = time.monotonic()
        elapsed = (
            current_time - _last_request_at
        )
        wait_seconds = max(
            0.0,
            REQUEST_INTERVAL - elapsed,
        )

        if wait_seconds:
            time.sleep(wait_seconds)

        _last_request_at = time.monotonic()


def create_signature(
    timestamp: str,
    method: str,
    uri: str,
    secret_key: str,
) -> str:
    message = f"{timestamp}.{method}.{uri}"

    return base64.b64encode(
        hmac.new(
            secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("ascii")


def search_ad_get(
    uri: str,
    params: dict[str, Any] | None = None,
) -> Any:
    settings = get_settings()

    if not settings.keyword_api_settings_ready:
        raise AdvertisingApiError(
            "네이버 검색광고 API 설정이 필요합니다."
        )

    last_response = None

    for attempt in range(4):
        wait_for_request_slot()

        timestamp = str(
            int(time.time() * 1000)
        )
        signature = create_signature(
            timestamp=timestamp,
            method="GET",
            uri=uri,
            secret_key=(
                settings.naver_ad_secret_key
            ),
        )

        try:
            response = requests.get(
                f"{SEARCH_AD_BASE_URL}{uri}",
                headers={
                    "X-Timestamp": timestamp,
                    "X-API-KEY": (
                        settings
                        .naver_ad_access_license
                    ),
                    "X-Customer": (
                        settings
                        .naver_ad_customer_id
                    ),
                    "X-Signature": signature,
                    "Content-Type": (
                        "application/json"
                    ),
                },
                params=params,
                timeout=(5, 30),
            )
        except requests.RequestException as error:
            if attempt < 3:
                time.sleep(1 + attempt)
                continue

            raise AdvertisingApiError(
                "검색광고 API에 연결하지 못했습니다."
            ) from error

        last_response = response

        if response.status_code == 200:
            return response.json()

        if (
            response.status_code == 429
            and attempt < 3
        ):
            time.sleep(1.5 * (attempt + 1))
            continue

        try:
            data = response.json()
            message = (
                data.get("title")
                or data.get("detail")
                or str(data)
            )
        except Exception:
            message = response.text[:300]

        raise AdvertisingApiError(
            f"검색광고 API 오류 "
            f"{response.status_code}: {message}"
        )

    status_code = (
        last_response.status_code
        if last_response is not None
        else "응답 없음"
    )

    raise AdvertisingApiError(
        f"검색광고 API 오류: {status_code}"
    )


def normalize_campaign(
    campaign: dict[str, Any],
) -> dict[str, Any]:
    user_locked = bool(
        campaign.get("userLock")
    )

    return {
        "campaign_id": str(
            campaign.get("nccCampaignId")
            or ""
        ),
        "name": str(
            campaign.get("name") or ""
        ),
        "campaign_type": str(
            campaign.get("campaignTp")
            or ""
        ),
        "daily_budget": int(
            campaign.get("dailyBudget")
            or 0
        ),
        "uses_daily_budget": bool(
            campaign.get("useDailyBudget")
        ),
        "user_locked": user_locked,
        "status": (
            "paused"
            if user_locked
            else "active"
        ),
        "registered_at": str(
            campaign.get("regTm") or ""
        ),
        "edited_at": str(
            campaign.get("editTm") or ""
        ),
    }


def normalize_adgroup(
    adgroup: dict[str, Any],
    campaign_name: str,
) -> dict[str, Any]:
    user_locked = bool(
        adgroup.get("userLock")
    )
    api_status = str(
        adgroup.get("status") or ""
    )

    active = (
        not user_locked
        and api_status.upper()
        not in {
            "PAUSED",
            "STOP",
            "DELETED",
        }
    )

    return {
        "adgroup_id": str(
            adgroup.get("nccAdgroupId")
            or ""
        ),
        "campaign_id": str(
            adgroup.get("nccCampaignId")
            or ""
        ),
        "campaign_name": campaign_name,
        "name": str(
            adgroup.get("name") or ""
        ),
        "bid_amount": int(
            adgroup.get("bidAmt") or 0
        ),
        "daily_budget": int(
            adgroup.get("dailyBudget")
            or 0
        ),
        "uses_daily_budget": bool(
            adgroup.get("useDailyBudget")
        ),
        "user_locked": user_locked,
        "api_status": api_status,
        "status_reason": str(
            adgroup.get("statusReason")
            or ""
        ),
        "status": (
            "active"
            if active
            else "paused"
        ),
    }


def get_advertising_overview() -> dict[str, Any]:
    started_at = time.perf_counter()

    campaign_data = search_ad_get(
        "/ncc/campaigns"
    )

    if not isinstance(campaign_data, list):
        raise AdvertisingApiError(
            "캠페인 응답 형식이 올바르지 않습니다."
        )

    campaigns = [
        normalize_campaign(campaign)
        for campaign in campaign_data
        if isinstance(campaign, dict)
    ]

    campaign_names = {
        campaign["campaign_id"]: (
            campaign["name"]
        )
        for campaign in campaigns
    }

    adgroups: list[dict[str, Any]] = []
    adgroup_errors: list[dict[str, str]] = []

    for campaign in campaigns:
        campaign_id = campaign[
            "campaign_id"
        ]

        if not campaign_id:
            continue

        try:
            data = search_ad_get(
                "/ncc/adgroups",
                params={
                    "nccCampaignId": campaign_id
                },
            )

            if not isinstance(data, list):
                raise AdvertisingApiError(
                    "광고그룹 응답 형식이 "
                    "올바르지 않습니다."
                )

            adgroups.extend(
                normalize_adgroup(
                    adgroup,
                    campaign_names.get(
                        campaign_id,
                        "",
                    ),
                )
                for adgroup in data
                if isinstance(adgroup, dict)
            )
        except AdvertisingApiError as error:
            adgroup_errors.append({
                "campaign_id": campaign_id,
                "campaign_name": (
                    campaign["name"]
                ),
                "message": str(error),
            })

    active_campaigns = sum(
        1
        for campaign in campaigns
        if campaign["status"] == "active"
    )
    active_adgroups = sum(
        1
        for adgroup in adgroups
        if adgroup["status"] == "active"
    )

    return {
        "summary": {
            "campaign_count": len(campaigns),
            "active_campaign_count": (
                active_campaigns
            ),
            "paused_campaign_count": (
                len(campaigns)
                - active_campaigns
            ),
            "adgroup_count": len(adgroups),
            "active_adgroup_count": (
                active_adgroups
            ),
            "paused_adgroup_count": (
                len(adgroups)
                - active_adgroups
            ),
            "error_count": len(
                adgroup_errors
            ),
        },
        "campaigns": campaigns,
        "adgroups": adgroups,
        "errors": adgroup_errors,
        "elapsed_seconds": round(
            time.perf_counter() - started_at,
            3,
        ),
    }
