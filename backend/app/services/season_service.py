from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import date
from typing import Any

import requests

from app.config import get_settings
from app.services.keyword_service import (
    fetch_keyword_statistics,
    normalize_keyword,
    parse_volume,
)


DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"
CACHE_SECONDS = 60 * 60 * 6

_cache: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()

SEASONS = {
    12: "겨울",
    1: "겨울",
    2: "겨울",
    3: "봄",
    4: "봄",
    5: "봄",
    6: "여름",
    7: "여름",
    8: "여름",
    9: "가을",
    10: "가을",
    11: "가을",
}

MONTH_NAMES = {
    1: "1월",
    2: "2월",
    3: "3월",
    4: "4월",
    5: "5월",
    6: "6월",
    7: "7월",
    8: "8월",
    9: "9월",
    10: "10월",
    11: "11월",
    12: "12월",
}


class SeasonAnalysisError(Exception):
    pass


def shifted_month_start(
    target: date,
    offset: int,
) -> date:
    index = target.year * 12 + target.month - 1 + offset
    year, month_index = divmod(index, 12)
    return date(year, month_index + 1, 1)


def fetch_monthly_trend(
    keyword: str,
    months: int,
) -> list[dict[str, Any]]:
    settings = get_settings()

    if not settings.naver_client_id or not settings.naver_client_secret:
        raise SeasonAnalysisError(
            "네이버 데이터랩 API 설정이 필요합니다."
        )

    today = date.today()
    start_date = shifted_month_start(today, -(months - 1))

    try:
        response = requests.post(
            DATALAB_URL,
            headers={
                "X-Naver-Client-Id": settings.naver_client_id,
                "X-Naver-Client-Secret": settings.naver_client_secret,
                "Content-Type": "application/json",
            },
            json={
                "startDate": start_date.isoformat(),
                "endDate": today.isoformat(),
                "timeUnit": "month",
                "keywordGroups": [
                    {
                        "groupName": keyword,
                        "keywords": [keyword],
                    }
                ],
            },
            timeout=(5, 30),
        )
    except requests.RequestException as error:
        raise SeasonAnalysisError(
            "네이버 데이터랩 API에 연결하지 못했습니다."
        ) from error

    if response.status_code != 200:
        try:
            data = response.json()
            message = (
                data.get("errorMessage")
                or data.get("message")
                or str(data)
            )
        except Exception:
            message = response.text[:300]

        raise SeasonAnalysisError(
            f"네이버 데이터랩 API 오류 "
            f"{response.status_code}: {message}"
        )

    data = response.json()
    results = data.get("results", [])

    if not results:
        return []

    trend_rows = results[0].get("data", [])
    current_period = today.strftime("%Y-%m")

    rows: list[dict[str, Any]] = []

    for item in trend_rows:
        period = str(item.get("period") or "")
        ratio = round(float(item.get("ratio") or 0), 3)

        try:
            month = int(period[5:7])
        except (TypeError, ValueError):
            continue

        rows.append({
            "period": period,
            "month": month,
            "month_name": MONTH_NAMES[month],
            "season": SEASONS[month],
            "ratio": ratio,
            "is_partial": period.startswith(current_period),
        })

    rows.sort(key=lambda row: row["period"])
    return rows


def get_exact_keyword_volume(
    keyword: str,
) -> dict[str, Any]:
    statistics = fetch_keyword_statistics(keyword)
    normalized = normalize_keyword(keyword).casefold()

    selected: dict[str, Any] | None = None

    for item in statistics:
        related = normalize_keyword(
            item.get("relKeyword")
        ).casefold()

        if related == normalized:
            selected = item
            break

    if selected is None and statistics:
        selected = statistics[0]

    if selected is None:
        return {
            "pc_volume": 0,
            "mobile_volume": 0,
            "total_volume": 0,
        }

    pc_volume, _ = parse_volume(
        selected.get("monthlyPcQcCnt")
    )
    mobile_volume, _ = parse_volume(
        selected.get("monthlyMobileQcCnt")
    )

    return {
        "pc_volume": pc_volume,
        "mobile_volume": mobile_volume,
        "total_volume": pc_volume + mobile_volume,
    }


def analyze_season(
    keyword: str,
    months: int = 24,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    normalized = normalize_keyword(keyword)

    if not normalized:
        raise SeasonAnalysisError(
            "분석할 키워드를 입력해 주세요."
        )

    cache_key = (normalized.casefold(), months)
    current_time = time.time()

    with _cache_lock:
        cached = _cache.get(cache_key)

        if cached and current_time - cached[0] < CACHE_SECONDS:
            return {
                **cached[1],
                "cached": True,
                "elapsed_seconds": round(
                    time.perf_counter() - started_at,
                    3,
                ),
            }

    monthly = fetch_monthly_trend(normalized, months)

    if not monthly:
        raise SeasonAnalysisError(
            "데이터랩에서 월별 검색 추이를 찾지 못했습니다."
        )

    volume = get_exact_keyword_volume(normalized)

    complete_rows = [
        row for row in monthly
        if not row["is_partial"]
    ]
    comparison_rows = complete_rows or monthly

    peak_row = max(
        comparison_rows,
        key=lambda row: row["ratio"],
    )
    latest_row = comparison_rows[-1]
    previous_row = (
        comparison_rows[-2]
        if len(comparison_rows) >= 2
        else None
    )

    trend_change = (
        round(
            latest_row["ratio"]
            - previous_row["ratio"],
            3,
        )
        if previous_row
        else 0.0
    )

    if trend_change > 2:
        trend_status = "rising"
        trend_label = "상승"
    elif trend_change < -2:
        trend_status = "falling"
        trend_label = "하락"
    else:
        trend_status = "stable"
        trend_label = "보합"

    grouped: dict[str, list[float]] = defaultdict(list)

    for row in comparison_rows:
        grouped[row["season"]].append(row["ratio"])

    season_order = ["봄", "여름", "가을", "겨울"]
    season_scores = []

    for season in season_order:
        values = grouped.get(season, [])
        average = (
            round(sum(values) / len(values), 3)
            if values
            else 0.0
        )
        season_scores.append({
            "season": season,
            "average_ratio": average,
            "sample_count": len(values),
        })

    strongest_season = max(
        season_scores,
        key=lambda row: row["average_ratio"],
    )

    peak_month = int(peak_row["month"])
    preparation_month = 12 if peak_month == 1 else peak_month - 1

    current_row = monthly[-1]
    recommendation = (
        f"검색 수요 최고 시점은 {peak_month}월입니다. "
        f"광고와 상품 준비는 {preparation_month}월부터 "
        f"시작하는 것을 권장합니다."
    )

    result = {
        "keyword": normalized,
        "months": months,
        "cached": False,
        "summary": {
            **volume,
            "current_ratio": current_row["ratio"],
            "current_period": current_row["period"],
            "current_is_partial": current_row["is_partial"],
            "latest_complete_ratio": latest_row["ratio"],
            "latest_complete_period": latest_row["period"],
            "peak_ratio": peak_row["ratio"],
            "peak_period": peak_row["period"],
            "peak_month": peak_month,
            "strongest_season": strongest_season["season"],
            "trend_status": trend_status,
            "trend_label": trend_label,
            "trend_change": trend_change,
            "preparation_month": preparation_month,
            "recommendation": recommendation,
        },
        "season_scores": season_scores,
        "monthly": monthly,
        "elapsed_seconds": round(
            time.perf_counter() - started_at,
            3,
        ),
    }

    with _cache_lock:
        _cache[cache_key] = (current_time, result)

    return result
