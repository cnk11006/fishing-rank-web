from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.google_sheets import (
    get_rank_worksheet,
)
from app.services.monitoring_collect_service import (
    match_monitor_results,
)
from app.services.monitoring_service import (
    read_monitor_items,
)


class RankHistoryError(Exception):
    pass


def safe_integer(value: Any) -> int | None:
    try:
        number = int(
            str(value or "").replace(",", "")
        )
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def load_rank_history_rows() -> list[dict[str, Any]]:
    worksheet = get_rank_worksheet()
    values = worksheet.get_all_values()

    if not values:
        return []

    headers = values[0]
    indexes = {
        name: position
        for position, name in enumerate(headers)
    }

    required = [
        "수집일시",
        "키워드",
        "순위",
        "상품명",
        "productId",
    ]

    missing = [
        name
        for name in required
        if name not in indexes
    ]

    if missing:
        raise RankHistoryError(
            "순위 기록 시트에 필요한 열이 없습니다: "
            + ", ".join(missing)
        )

    def get_value(
        row: list[str],
        name: str,
    ) -> str:
        position = indexes[name]

        if position >= len(row):
            return ""

        return str(row[position]).strip()

    records: list[dict[str, Any]] = []

    for row in values[1:]:
        collected_at = get_value(
            row,
            "수집일시",
        )
        keyword = get_value(row, "키워드")
        rank = safe_integer(
            get_value(row, "순위")
        )

        if not collected_at or not keyword or not rank:
            continue

        records.append({
            "collected_at": collected_at,
            "keyword": keyword,
            "rank": rank,
            "title": get_value(
                row,
                "상품명",
            ),
            "product_id": get_value(
                row,
                "productId",
            ),
        })

    return records


def calculate_monitoring_history() -> dict[str, Any]:
    monitors = read_monitor_items()
    records = load_rank_history_rows()

    records_by_keyword: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for record in records:
        key = str(
            record.get("keyword") or ""
        ).strip().casefold()

        records_by_keyword[key].append(record)

    results: list[dict[str, Any]] = []

    for monitor in monitors:
        keyword = str(
            monitor.get("keyword") or ""
        ).strip()

        keyword_records = records_by_keyword.get(
            keyword.casefold(),
            [],
        )

        snapshots: dict[
            str,
            list[dict[str, Any]],
        ] = defaultdict(list)

        for record in keyword_records:
            snapshots[
                str(record["collected_at"])
            ].append(record)

        snapshot_times = sorted(
            snapshots.keys()
        )

        latest_time = (
            snapshot_times[-1]
            if snapshot_times
            else None
        )
        previous_time = (
            snapshot_times[-2]
            if len(snapshot_times) >= 2
            else None
        )

        latest_matches = (
            match_monitor_results(
                monitor,
                snapshots.get(
                    latest_time,
                    [],
                ),
            )
            if latest_time
            else []
        )

        previous_matches = (
            match_monitor_results(
                monitor,
                snapshots.get(
                    previous_time,
                    [],
                ),
            )
            if previous_time
            else []
        )

        latest_rank = (
            min(
                int(item["rank"])
                for item in latest_matches
            )
            if latest_matches
            else None
        )

        previous_rank = (
            min(
                int(item["rank"])
                for item in previous_matches
            )
            if previous_matches
            else None
        )

        rank_change = (
            previous_rank - latest_rank
            if latest_rank is not None
            and previous_rank is not None
            else None
        )

        if not latest_time:
            status = "no_history"
            message = "수집 기록 없음"
        elif latest_rank is None:
            status = "not_exposed"
            message = "최근 수집에서 미노출"
        elif previous_rank is None:
            status = "first"
            message = f"{latest_rank}위 · 첫 기록"
        elif rank_change > 0:
            status = "up"
            message = (
                f"{latest_rank}위 · "
                f"{rank_change}계단 상승"
            )
        elif rank_change < 0:
            status = "down"
            message = (
                f"{latest_rank}위 · "
                f"{abs(rank_change)}계단 하락"
            )
        else:
            status = "same"
            message = f"{latest_rank}위 · 변동 없음"

        results.append({
            **monitor,
            "latest_rank": latest_rank,
            "previous_rank": previous_rank,
            "rank_change": rank_change,
            "latest_collected_at": latest_time,
            "previous_collected_at": previous_time,
            "status": status,
            "message": message,
        })

    return {
        "count": len(results),
        "history_row_count": len(records),
        "items": results,
    }
