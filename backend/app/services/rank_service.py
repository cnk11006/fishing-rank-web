from __future__ import annotations

import html
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import get_settings


KST = ZoneInfo("Asia/Seoul")

NAVER_SHOPPING_URL = (
    "https://openapi.naver.com/v1/search/shop.json"
)

TARGET_STORE = "피싱템"

OUR_STORE_NAMES = {
    "피싱템",
    "피싱템 공식스토어",
    "피싱템스토어",
}

CATALOG_TYPES = {1, 4, 7, 10}


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
        return int(
            float(
                str(value or "0")
                .replace(",", "")
                .strip()
            )
        )
    except (TypeError, ValueError):
        return 0


def safe_url(value: Any) -> str:
    url = str(value or "").strip()

    if not url:
        return ""

    try:
        parsed = urlparse(url)

        if parsed.scheme in {"http", "https"}:
            return url
    except Exception:
        pass

    return ""


def is_our_store(value: Any) -> bool:
    mall = normalize_store_name(value)

    if not mall:
        return False

    if mall in NORMALIZED_STORE_NAMES:
        return True

    return any(
        own_name and own_name in mall
        for own_name in NORMALIZED_STORE_NAMES
    )


def is_our_shop_item(item: dict[str, Any]) -> bool:
    if is_our_store(item.get("mallName")):
        return True

    product_type = safe_integer(
        item.get("productType")
    )
    title = clean_title(item.get("title"))

    return (
        product_type == 1
        and TARGET_STORE in title
    )


def catalog_badge(product_type: Any) -> str:
    value = safe_integer(product_type)

    mapping = {
        1: "가격비교 묶음",
        2: "독립·비매칭",
        3: "독립·매칭",
        4: "중고 가격비교",
        5: "중고 독립",
        6: "중고 독립·매칭",
        7: "가격비교 등록",
        8: "독립 등록",
        9: "독립 등록·매칭",
        10: "가격비교 등록",
        11: "독립 등록",
        12: "독립 등록·매칭",
    }

    return mapping.get(
        value,
        "독립 노출",
    )


def parse_item(
    item: dict[str, Any],
    rank: int,
) -> dict[str, Any]:
    product_type = safe_integer(
        item.get("productType")
    )

    return {
        "rank": rank,
        "title": clean_title(
            item.get("title")
        ),
        "mall_name": str(
            item.get("mallName") or ""
        ).strip(),
        "price": safe_integer(
            item.get("lprice")
        ),
        "highest_price": safe_integer(
            item.get("hprice")
        ),
        "link": safe_url(
            item.get("link")
        ),
        "image": safe_url(
            item.get("image")
        ),
        "product_type": product_type,
        "product_id": str(
            item.get("productId") or ""
        ),
        "brand": str(
            item.get("brand") or ""
        ).strip(),
        "maker": str(
            item.get("maker") or ""
        ).strip(),
        "categories": [
            str(
                item.get(f"category{number}")
                or ""
            ).strip()
            for number in range(1, 5)
        ],
        "is_ours": is_our_shop_item(item),
        "is_catalog": (
            product_type in CATALOG_TYPES
        ),
        "catalog_badge": catalog_badge(
            product_type
        ),
    }


def create_http_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=[
            429,
            500,
            502,
            503,
            504,
        ],
        allowed_methods={"GET"},
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry
    )
    session = requests.Session()
    session.mount("https://", adapter)

    return session


def fetch_page(
    session: requests.Session,
    keyword: str,
    start: int,
    client_id: str,
    client_secret: str,
    exclude: str,
) -> tuple[list[dict[str, Any]], int, str | None]:
    try:
        response = session.get(
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
                **(
                    {"exclude": exclude}
                    if exclude
                    else {}
                ),
            },
            timeout=(5, 25),
        )
    except requests.Timeout:
        return (
            [],
            0,
            "네이버 쇼핑 API 응답 시간이 초과되었습니다.",
        )
    except requests.RequestException as error:
        return (
            [],
            0,
            f"네이버 쇼핑 API 연결 오류: {error}",
        )

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

        return (
            [],
            0,
            (
                "네이버 쇼핑 API 오류 "
                f"{response.status_code}: {message}"
            ),
        )

    try:
        data = response.json()
    except ValueError:
        return (
            [],
            0,
            "네이버 쇼핑 API 응답을 해석하지 못했습니다.",
        )

    items = data.get("items", [])

    if not isinstance(items, list):
        return (
            [],
            0,
            "네이버 쇼핑 API 응답 형식이 올바르지 않습니다.",
        )

    return (
        items,
        safe_integer(data.get("total")),
        None,
    )


def search_our_store_ranks(
    keyword: str,
    limit: int,
    include_special_products: bool = False,
) -> dict[str, Any]:
    settings = get_settings()

    if (
        not settings.naver_client_id
        or not settings.naver_client_secret
    ):
        raise NaverShoppingError(
            "네이버 API 환경설정이 필요합니다."
        )

    keyword = str(keyword).strip()

    if not keyword:
        raise NaverShoppingError(
            "검색 키워드를 입력해 주세요."
        )

    limit = min(max(int(limit), 1), 400)
    started_at = time.perf_counter()
    searched_at = datetime.now(KST).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    exclude = (
        ""
        if include_special_products
        else "used:rental:cbshop"
    )

    session = create_http_session()

    results: list[dict[str, Any]] = []
    top10_prices: list[int] = []
    market_top10: list[dict[str, Any]] = []
    warnings: list[str] = []

    fetched_count = 0
    total_results = 0

    try:
        for start in range(1, limit + 1, 100):
            items, page_total, error = fetch_page(
                session=session,
                keyword=keyword,
                start=start,
                client_id=settings.naver_client_id,
                client_secret=(
                    settings.naver_client_secret
                ),
                exclude=exclude,
            )

            if error:
                warnings.append(
                    f"{start}위 구간: {error}"
                )
                break

            if not items:
                break

            total_results = max(
                total_results,
                page_total,
            )
            fetched_count += len(items)

            for index, raw_item in enumerate(items):
                rank = start + index

                if rank > limit:
                    break

                item = parse_item(
                    raw_item,
                    rank,
                )
                price = item["price"]

                if rank <= 10 and price > 0:
                    top10_prices.append(price)

                if (
                    rank <= 100
                    and price > 0
                    and len(market_top10) < 10
                ):
                    market_top10.append(item)

                if is_our_shop_item(raw_item):
                    results.append(item)

            time.sleep(0.08)

    finally:
        session.close()

    results.sort(
        key=lambda item: item["rank"]
    )

    our_prices = [
        item["price"]
        for item in results
        if item["price"] > 0
    ]

    top10_average = (
        int(
            sum(top10_prices)
            / len(top10_prices)
        )
        if top10_prices
        else 0
    )

    our_average = (
        int(
            sum(our_prices)
            / len(our_prices)
        )
        if our_prices
        else 0
    )

    price_difference_percent = (
        round(
            (
                our_average
                - top10_average
            )
            / top10_average
            * 100
        )
        if our_average
        and top10_average
        else None
    )

    return {
        "keyword": keyword,
        "limit": limit,
        "include_special_products": (
            include_special_products
        ),
        "searched_at": searched_at,
        "total_results": total_results,
        "fetched_count": fetched_count,
        "match_count": len(results),
        "best_rank": (
            results[0]["rank"]
            if results
            else None
        ),
        "top10_price_summary": {
            "count": len(top10_prices),
            "lowest": (
                min(top10_prices)
                if top10_prices
                else 0
            ),
            "average": top10_average,
            "highest": (
                max(top10_prices)
                if top10_prices
                else 0
            ),
            "our_average": our_average,
            "difference_percent": (
                price_difference_percent
            ),
        },
        "market_top10": market_top10,
        "warnings": warnings,
        "partial_success": bool(
            warnings and fetched_count > 0
        ),
        "elapsed_seconds": round(
            time.perf_counter() - started_at,
            3,
        ),
        "results": results,
    }
