from __future__ import annotations

import copy
import math
import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import gspread

from app.config import get_settings
from app.services import keyword_service, season_service
from app.services.google_sheets import (
    RANK_HEADERS,
    RANK_HISTORY_SHEET,
    get_rank_worksheet,
    get_spreadsheet,
    make_record_id,
    safe_sheet_value,
)
from app.services.monitoring_service import (
    MONITOR_SHEET_NAME,
    read_monitor_items,
)


KST = ZoneInfo("Asia/Seoul")
AD_DIAGNOSIS_SHEET = "📢 광고진단 기록"
MIGRATION_LOG_SHEET = "⚙️ 마이그레이션 기록"

SYSTEM_SHEETS = {
    RANK_HISTORY_SHEET,
    MONITOR_SHEET_NAME,
    AD_DIAGNOSIS_SHEET,
    MIGRATION_LOG_SHEET,
}

MIGRATION_HEADERS = [
    "실행일시",
    "원본시트",
    "이전건수",
    "상태",
    "메모",
]


OVERVIEW_CACHE_TTL_SECONDS = 300
OVERVIEW_QUOTA_COOLDOWN_SECONDS = 60

_overview_cache_lock = threading.Lock()
_overview_cache_value: dict[str, Any] | None = None
_overview_cache_expires_at = 0.0
_overview_quota_blocked_until = 0.0


class DataManagementError(Exception):
    pass


class DataManagementQuotaError(DataManagementError):
    def __init__(self, retry_after: int = 60):
        self.retry_after = max(1, int(retry_after))
        super().__init__(
            "Google Sheets 읽기 요청 한도를 초과했습니다."
        )


def _safe_int(value: Any) -> int:
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


def _get_value(
    row: list[str],
    indexes: dict[str, int],
    *names: str,
) -> str:
    for name in names:
        position = indexes.get(name)

        if position is not None and position < len(row):
            return str(row[position]).strip()

    return ""


def _get_migration_log_worksheet():
    spreadsheet = get_spreadsheet()

    try:
        worksheet = spreadsheet.worksheet(
            MIGRATION_LOG_SHEET
        )
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=MIGRATION_LOG_SHEET,
            rows=1000,
            cols=len(MIGRATION_HEADERS),
        )

    headers = worksheet.row_values(1)

    if not headers:
        worksheet.update(
            values=[MIGRATION_HEADERS],
            range_name="A1",
        )

    return worksheet


def _migrated_sheet_names() -> set[str]:
    worksheet = _get_migration_log_worksheet()
    values = worksheet.get_all_values()
    migrated: set[str] = set()

    for row in values[1:]:
        padded = row + [""] * 5

        if padded[3].strip() == "완료":
            migrated.add(padded[1].strip())

    return migrated



def _is_legacy_rank_worksheet(worksheet) -> bool:
    """순위기록 형식의 기존 워크시트인지 확인합니다."""
    try:
        headers = {
            str(value).strip()
            for value in worksheet.row_values(1)
            if str(value).strip()
        }
    except Exception:
        return False

    has_rank = bool(
        headers.intersection({"순위", "rank", "Rank"})
    )
    has_date = bool(
        headers.intersection(
            {"수집일시", "날짜", "수집일", "일시"}
        )
    )

    return has_rank and has_date


def _rank_content_key(
    row: list[Any],
) -> tuple[str, str, int, str, str]:
    padded = list(row) + [""] * len(RANK_HEADERS)

    return (
        str(padded[1]).strip(),
        str(padded[2]).strip().casefold(),
        _safe_int(padded[3]),
        str(padded[4]).strip().casefold(),
        str(padded[10]).strip(),
    )


def _convert_legacy_rows(
    worksheet,
    existing_ids: set[str],
    existing_content_keys: (
        set[tuple[str, str, int, str, str]] | None
    ) = None,
) -> list[list[Any]]:
    values = worksheet.get_all_values()

    if len(values) < 2:
        return []

    if existing_content_keys is None:
        existing_content_keys = set()

    headers = [
        str(value).strip()
        for value in values[0]
    ]
    indexes = {
        name: index
        for index, name in enumerate(headers)
    }

    if not any(
        name in indexes
        for name in ("순위", "rank", "Rank")
    ):
        return []

    converted: list[list[Any]] = []

    for row in values[1:]:
        collected_at = _get_value(
            row,
            indexes,
            "수집일시",
            "날짜",
            "수집일",
            "일시",
        )
        rank = _safe_int(
            _get_value(
                row,
                indexes,
                "순위",
                "rank",
                "Rank",
            )
        )

        if not collected_at or rank <= 0:
            continue

        keyword = _get_value(
            row,
            indexes,
            "키워드",
            "검색어",
        ) or worksheet.title

        product_id = _get_value(
            row,
            indexes,
            "productId",
            "상품번호",
            "상품ID",
        )

        record_id = make_record_id(
            collected_at,
            keyword,
            rank,
            product_id,
        )

        output = [
            record_id,
            collected_at,
            keyword,
            rank,
            _get_value(row, indexes, "상품명", "제품명"),
            _get_value(row, indexes, "판매처", "쇼핑몰"),
            _safe_int(
                _get_value(
                    row,
                    indexes,
                    "가격",
                    "최저가",
                )
            ),
            _get_value(row, indexes, "링크", "상품링크"),
            _get_value(row, indexes, "썸네일", "이미지"),
            _safe_int(
                _get_value(
                    row,
                    indexes,
                    "productType",
                )
            ),
            product_id,
            _get_value(row, indexes, "브랜드"),
            _get_value(row, indexes, "제조사"),
            _get_value(row, indexes, "카테고리1"),
            _get_value(row, indexes, "카테고리2"),
            _get_value(row, indexes, "카테고리3"),
            _get_value(row, indexes, "카테고리4"),
        ]

        content_key = _rank_content_key(output)

        if (
            record_id in existing_ids
            or content_key in existing_content_keys
        ):
            continue

        existing_ids.add(record_id)
        existing_content_keys.add(content_key)

        converted.append([
            safe_sheet_value(value)
            for value in output
        ])

    return converted

def _load_data_overview() -> dict[str, Any]:
    try:
        spreadsheet = get_spreadsheet()
        worksheets = spreadsheet.worksheets()
        rank_worksheet = get_rank_worksheet()
        rank_values = rank_worksheet.get_all_values()
        monitor_items = read_monitor_items()

        rank_count = max(0, len(rank_values) - 1)
        latest_collected_at = ""

        if rank_values:
            headers = rank_values[0]

            if "수집일시" in headers:
                position = headers.index("수집일시")
                dates = [
                    row[position].strip()
                    for row in rank_values[1:]
                    if position < len(row)
                    and row[position].strip()
                ]

                if dates:
                    latest_collected_at = max(dates)

        legacy_sheets = [
            worksheet.title
            for worksheet in worksheets
            if (
                worksheet.title not in SYSTEM_SHEETS
                and _is_legacy_rank_worksheet(worksheet)
            )
        ]

        settings = get_settings()

        return {
            "summary": {
                "worksheet_count": len(worksheets),
                "rank_record_count": rank_count,
                "monitor_count": len(monitor_items),
                "legacy_sheet_count": len(legacy_sheets),
                "latest_collected_at": latest_collected_at,
            },
            "legacy_sheets": legacy_sheets,
            "worksheets": [
                {
                    "title": worksheet.title,
                    "is_system": (
                        worksheet.title in SYSTEM_SHEETS
                    ),
                }
                for worksheet in worksheets
            ],
            "system": {
                "naver_shopping_ready": bool(
                    settings.naver_client_id
                    and settings.naver_client_secret
                ),
                "naver_search_ad_ready": (
                    settings.keyword_api_settings_ready
                ),
                "google_sheets_ready": bool(
                    settings.google_sheet_id
                    and settings.gcp_service_account_json
                ),
                "authentication_ready": (
                    settings.authentication_ready
                ),
                "environment": settings.app_environment,
                "timezone": "Asia/Seoul",
            },
        }

    except gspread.exceptions.APIError as error:
        response = getattr(error, "response", None)

        if getattr(response, "status_code", None) == 429:
            raise DataManagementQuotaError(
                OVERVIEW_QUOTA_COOLDOWN_SECONDS
            ) from error

        raise DataManagementError(
            f"데이터 현황을 불러오지 못했습니다: {error}"
        ) from error
    except Exception as error:
        raise DataManagementError(
            f"데이터 현황을 불러오지 못했습니다: {error}"
        ) from error


def get_data_overview() -> dict[str, Any]:
    global _overview_cache_value
    global _overview_cache_expires_at
    global _overview_quota_blocked_until

    now = time.monotonic()

    with _overview_cache_lock:
        now = time.monotonic()

        if now < _overview_quota_blocked_until:
            retry_after = math.ceil(
                _overview_quota_blocked_until - now
            )
            raise DataManagementQuotaError(retry_after)

        if (
            _overview_cache_value is not None
            and now < _overview_cache_expires_at
        ):
            return copy.deepcopy(_overview_cache_value)

        try:
            overview = _load_data_overview()
        except DataManagementQuotaError:
            _overview_quota_blocked_until = (
                time.monotonic()
                + OVERVIEW_QUOTA_COOLDOWN_SECONDS
            )
            raise

        _overview_cache_value = copy.deepcopy(overview)
        _overview_cache_expires_at = (
            time.monotonic()
            + OVERVIEW_CACHE_TTL_SECONDS
        )

        return copy.deepcopy(overview)


def clear_data_overview_cache() -> None:
    global _overview_cache_value
    global _overview_cache_expires_at

    with _overview_cache_lock:
        _overview_cache_value = None
        _overview_cache_expires_at = 0.0


def migrate_legacy_rank_sheets() -> dict[str, Any]:
    try:
        spreadsheet = get_spreadsheet()
        target = get_rank_worksheet()
        log_sheet = _get_migration_log_worksheet()
        migrated_names = _migrated_sheet_names()

        target_values = target.get_all_values()
        existing_ids = {
            row[0].strip()
            for row in target_values[1:]
            if row and row[0].strip()
        }
        existing_content_keys = {
            _rank_content_key(row)
            for row in target_values[1:]
            if row
        }

        results: list[dict[str, Any]] = []
        total_count = 0

        for worksheet in spreadsheet.worksheets():
            title = worksheet.title

            if title in SYSTEM_SHEETS:
                continue

            if not _is_legacy_rank_worksheet(worksheet):
                continue

            if title in migrated_names:
                results.append({
                    "source_sheet": title,
                    "migrated_count": 0,
                    "status": "skipped",
                    "message": "이미 이전 완료된 시트",
                })
                continue

            try:
                rows = _convert_legacy_rows(
                    worksheet,
                    existing_ids,
                    existing_content_keys,
                )

                if rows:
                    target.append_rows(
                        rows,
                        value_input_option="RAW",
                    )

                log_sheet.append_row(
                    [
                        datetime.now(KST).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        title,
                        len(rows),
                        "완료",
                        "원본 시트 보존",
                    ],
                    value_input_option="RAW",
                )

                total_count += len(rows)
                results.append({
                    "source_sheet": title,
                    "migrated_count": len(rows),
                    "status": "completed",
                    "message": "원본 시트 보존",
                })

            except Exception as error:
                log_sheet.append_row(
                    [
                        datetime.now(KST).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        title,
                        0,
                        "오류",
                        str(error)[:500],
                    ],
                    value_input_option="RAW",
                )

                results.append({
                    "source_sheet": title,
                    "migrated_count": 0,
                    "status": "error",
                    "message": str(error),
                })

        clear_data_overview_cache()

        return {
            "total_migrated_count": total_count,
            "result_count": len(results),
            "results": results,
            "source_sheets_deleted": False,
        }

    except Exception as error:
        raise DataManagementError(
            f"순위기록 통합에 실패했습니다: {error}"
        ) from error


def clear_application_caches() -> dict[str, Any]:
    clear_data_overview_cache()

    category_count = 0
    season_count = 0

    with keyword_service._category_cache_lock:
        category_count = len(
            keyword_service._category_cache
        )
        keyword_service._category_cache.clear()

    with season_service._cache_lock:
        season_count = len(
            season_service._cache
        )
        season_service._cache.clear()

    get_spreadsheet.cache_clear()

    return {
        "message": (
            "백엔드 캐시를 초기화했습니다. "
            "Google Sheets의 실제 데이터는 삭제되지 않았습니다."
        ),
        "cleared": {
            "keyword_category_cache": category_count,
            "season_analysis_cache": season_count,
            "google_sheets_connection_cache": 1,
        },
    }
