from __future__ import annotations

import re
import time
from typing import Any

from app.services.google_sheets import (
    save_rank_search_result,
)
from app.services.monitoring_service import (
    read_monitor_items,
)
from app.services.rank_service import (
    NaverShoppingError,
    search_our_store_ranks,
)


def normalize_product_name(value: Any) -> str:
    return re.sub(
        r"[^0-9a-z가-힣]",
        "",
        str(value or "").casefold(),
    )


def match_monitor_results(
    monitor: dict[str, Any],
    search_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    product_id = str(
        monitor.get("product_id") or ""
    ).strip()

    product_name = normalize_product_name(
        monitor.get("product_name")
    )

    if product_id:
        return [
            result
            for result in search_results
            if str(
                result.get("product_id") or ""
            ).strip() == product_id
        ]

    if product_name:
        return [
            result
            for result in search_results
            if product_name
            in normalize_product_name(
                result.get("title")
            )
        ]

    return list(search_results)


def collect_monitoring_ranks() -> dict[str, Any]:
    started_at = time.perf_counter()
    monitors = read_monitor_items()

    if not monitors:
        return {
            "total_items": 0,
            "unique_keywords": 0,
            "exposed_count": 0,
            "not_exposed_count": 0,
            "error_count": 0,
            "saved_records": 0,
            "elapsed_seconds": 0,
            "results": [],
        }

    keywords = list(dict.fromkeys(
        str(
            monitor.get("keyword") or ""
        ).strip()
        for monitor in monitors
        if str(
            monitor.get("keyword") or ""
        ).strip()
    ))

    search_by_keyword: dict[
        str,
        dict[str, Any],
    ] = {}
    errors_by_keyword: dict[str, str] = {}
    saved_records = 0

    # 키워드는 차례로 처리하고 각 키워드 내부의
    # 100~400위 요청은 rank_service가 병렬 처리합니다.
    for keyword in keywords:
        try:
            search_result = search_our_store_ranks(
                keyword=keyword,
                limit=400,
            )
            search_by_keyword[keyword] = (
                search_result
            )

            saved_records += save_rank_search_result(
                search_result
            )
        except NaverShoppingError as error:
            errors_by_keyword[keyword] = str(error)
        except Exception as error:
            errors_by_keyword[keyword] = (
                f"{type(error).__name__}: {error}"
            )

    results: list[dict[str, Any]] = []
    exposed_count = 0
    not_exposed_count = 0
    error_count = 0

    for monitor in monitors:
        keyword = str(
            monitor.get("keyword") or ""
        ).strip()

        if keyword in errors_by_keyword:
            error_count += 1
            results.append({
                **monitor,
                "status": "error",
                "rank": None,
                "matched_count": 0,
                "message": (
                    errors_by_keyword[keyword]
                ),
            })
            continue

        search_result = search_by_keyword.get(
            keyword,
            {},
        )
        matched = match_monitor_results(
            monitor,
            search_result.get("results", []),
        )

        if matched:
            matched.sort(
                key=lambda item: int(
                    item.get("rank") or 999999
                )
            )
            best_rank = int(
                matched[0].get("rank") or 0
            )
            exposed_count += 1

            results.append({
                **monitor,
                "status": "exposed",
                "rank": best_rank,
                "matched_count": len(matched),
                "message": (
                    f"{best_rank}위 노출"
                ),
            })
        else:
            not_exposed_count += 1

            results.append({
                **monitor,
                "status": "not_exposed",
                "rank": None,
                "matched_count": 0,
                "message": "400위 이내 미노출",
            })

    return {
        "total_items": len(monitors),
        "unique_keywords": len(keywords),
        "exposed_count": exposed_count,
        "not_exposed_count": not_exposed_count,
        "error_count": error_count,
        "saved_records": saved_records,
        "elapsed_seconds": round(
            time.perf_counter() - started_at,
            3,
        ),
        "results": results,
    }
