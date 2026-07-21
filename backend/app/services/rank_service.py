from __future__ import annotations

import html
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from app.config import get_settings


NAVER_SHOPPING_URL = (
    "https://openapi.naver.com/v1/search/shop.json"
)

OUR_STORE_NAMES = {
    "피싱템",
    "피싱템 공식스토어",
    "피싱템스토어",
}


class NaverShoppingError(Exception):
    pass


def normalize_store_name(value: Any) -> str:
    return re.sub(
        r"\s+",
        "",
        str(value or "").lower(),
    )


NORMALIZED_STORE_NAMES = {
    normalize_store_name(name)
    for name in OUR_STORE_NAMES
}


def clean_title(value: Any) -> str:
    text = re.sub(
        r"</?b>",
        "",
        str(value or ""),
        flags=re.IGNORECASE,
    )
    return html.unescape(text).strip()


def safe_integer(value: Any) -> int:
    try:
        return int(str(value or "0").replace(",", ""))
    except (TypeError, ValueError):
        return 0


def is_our_store(value: Any) -> bool:
    return (
        normalize_store_name(value)
        in NORMALIZED_STORE_NAMES
    )


def fetch_page(
    keyword: str,
    start: int,
    client_id: str,
    client_secret: str,
) -> tuple[int, list[dict[str, Any]], int]:
    try:
        response = requests.get(
            NAVER_SHOPPING_URL,
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": (
                    client_secret
                ),
                "User-Agent": (
                    "Fishingtem-Rank-Radar/2.0"
                ),
            },
            params={
                "query": keyword,
                "display": 100,
                "start": start,
                "sort": "sim",
            },
            timeout=(5, 25),
        )
    except requests.RequestException as error:
        raise NaverShoppingError(
            "네이버 쇼핑 API에 연결하지 못했습니다."
        ) from error

    if response.status_code != 200:
        try:
            data = response.json()
            message = (
                data.get("errorMessage")
                or data.get("message")
                or "알 수 없는 오류"
            )
        except Exception:
            message = response.text[:200]

        raise NaverShoppingError(
            f"네이버 쇼핑 API 오류 "
            f"{response.status_code}: {message}"
        )

    data = response.json()

    return (
        start,
        data.get("items", []),
        safe_integer(data.get("total")),
    )


def search_our_store_ranks(
    keyword: str,
    limit: int,
) -> dict[str, Any]:
    settings = get_settings()

    if (
        not settings.naver_client_id
        or not settings.naver_client_secret
    ):
        raise NaverShoppingError(
            "네이버 API 환경설정이 필요합니다."
        )

    started_at = time.perf_counter()
    starts = list(range(1, limit + 1, 100))

    with ThreadPoolExecutor(
        max_workers=min(4, len(starts))
    ) as executor:
        pages = list(
            executor.map(
                lambda start: fetch_page(
                    keyword,
                    start,
                    settings.naver_client_id,
                    settings.naver_client_secret,
                ),
                starts,
            )
        )

    pages.sort(key=lambda page: page[0])

    results: list[dict[str, Any]] = []
    fetched_count = 0
    total_results = 0

    for start, items, page_total in pages:
        total_results = max(
            total_results,
            page_total,
        )
        fetched_count += len(items)

        for index, item in enumerate(items):
            mall_name = str(
                item.get("mallName") or ""
            ).strip()

            if not is_our_store(mall_name):
                continue

            results.append({
                "rank": start + index,
                "title": clean_title(
                    item.get("title")
                ),
                "mall_name": mall_name,
                "price": safe_integer(
                    item.get("lprice")
                ),
                "link": str(
                    item.get("link") or ""
                ),
                "image": str(
                    item.get("image") or ""
                ),
                "product_type": safe_integer(
                    item.get("productType")
                ),
                "product_id": str(
                    item.get("productId") or ""
                ),
                "brand": str(
                    item.get("brand") or ""
                ),
                "maker": str(
                    item.get("maker") or ""
                ),
                "categories": [
                    str(
                        item.get(f"category{number}")
                        or ""
                    )
                    for number in range(1, 5)
                ],
            })

    results.sort(key=lambda item: item["rank"])

    return {
        "keyword": keyword,
        "limit": limit,
        "total_results": total_results,
        "fetched_count": fetched_count,
        "match_count": len(results),
        "best_rank": (
            results[0]["rank"]
            if results
            else None
        ),
        "elapsed_seconds": round(
            time.perf_counter() - started_at,
            3,
        ),
        "results": results,
    }
