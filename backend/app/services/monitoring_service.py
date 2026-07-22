from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import gspread

from app.services.google_sheets import (
    get_spreadsheet,
    safe_sheet_value,
)


KST = ZoneInfo("Asia/Seoul")
MONITOR_SHEET_NAME = "📋 모니터링 목록"

MONITOR_HEADERS = [
    "항목ID",
    "키워드",
    "등록일",
    "메모",
    "productId",
    "상품명",
]

_monitor_lock = threading.Lock()


class DuplicateMonitorError(Exception):
    pass


class MonitorSheetError(Exception):
    pass


def get_monitor_worksheet():
    spreadsheet = get_spreadsheet()

    try:
        worksheet = spreadsheet.worksheet(
            MONITOR_SHEET_NAME
        )
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=MONITOR_SHEET_NAME,
            rows=1000,
            cols=len(MONITOR_HEADERS),
        )

    headers = worksheet.row_values(1)

    if not headers:
        worksheet.update(
            values=[MONITOR_HEADERS],
            range_name="A1",
        )
    elif headers[:len(MONITOR_HEADERS)] != MONITOR_HEADERS:
        raise MonitorSheetError(
            "모니터링 목록 시트의 헤더 구성이 "
            "기존 프로그램과 다릅니다."
        )

    return worksheet


def read_monitor_items() -> list[dict[str, Any]]:
    with _monitor_lock:
        worksheet = get_monitor_worksheet()
        values = worksheet.get_all_values()

    items: list[dict[str, Any]] = []

    for row_number, row in enumerate(
        values[1:],
        start=2,
    ):
        padded = row + [""] * (
            len(MONITOR_HEADERS) - len(row)
        )

        if not any(
            str(value).strip()
            for value in padded
        ):
            continue

        items.append({
            "item_id": padded[0].strip(),
            "keyword": padded[1].strip(),
            "registered_at": padded[2].strip(),
            "memo": padded[3].strip(),
            "product_id": padded[4].strip(),
            "product_name": padded[5].strip(),
            "row_number": row_number,
        })

    return items


def add_monitor_item(
    keyword: str,
    memo: str = "",
    product_id: str = "",
    product_name: str = "",
) -> dict[str, Any]:
    keyword = keyword.strip()
    memo = memo.strip()
    product_id = product_id.strip()
    product_name = product_name.strip()

    if not keyword:
        raise ValueError(
            "키워드를 입력해 주세요."
        )

    with _monitor_lock:
        worksheet = get_monitor_worksheet()
        values = worksheet.get_all_values()

        for row in values[1:]:
            padded = row + [""] * (
                len(MONITOR_HEADERS) - len(row)
            )

            existing_keyword = (
                padded[1].strip().casefold()
            )
            existing_product_id = (
                padded[4].strip()
            )

            if (
                existing_keyword
                == keyword.casefold()
                and existing_product_id
                == product_id
            ):
                raise DuplicateMonitorError(
                    "이미 등록된 키워드와 상품입니다."
                )

        item = {
            "item_id": uuid.uuid4().hex,
            "keyword": keyword,
            "registered_at": datetime.now(
                KST
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "memo": memo,
            "product_id": product_id,
            "product_name": product_name,
        }

        worksheet.append_row(
            [
                safe_sheet_value(
                    item["item_id"]
                ),
                safe_sheet_value(
                    item["keyword"]
                ),
                safe_sheet_value(
                    item["registered_at"]
                ),
                safe_sheet_value(
                    item["memo"]
                ),
                safe_sheet_value(
                    item["product_id"]
                ),
                safe_sheet_value(
                    item["product_name"]
                ),
            ],
            value_input_option="RAW",
        )

    return item


def delete_monitor_items(
    item_ids: list[str],
) -> int:
    normalized_ids = {
        item_id.strip()
        for item_id in item_ids
        if item_id.strip()
    }

    if not normalized_ids:
        raise ValueError(
            "삭제할 항목을 선택해 주세요."
        )

    with _monitor_lock:
        worksheet = get_monitor_worksheet()
        values = worksheet.get_all_values()
        row_numbers: list[int] = []

        for row_number, row in enumerate(
            values[1:],
            start=2,
        ):
            item_id = (
                row[0].strip()
                if row
                else ""
            )

            if item_id in normalized_ids:
                row_numbers.append(row_number)

        for row_number in sorted(
            row_numbers,
            reverse=True,
        ):
            worksheet.delete_rows(row_number)

    return len(row_numbers)


def update_monitor_item(
    item_id: str,
    keyword: str,
    memo: str = "",
    product_id: str = "",
    product_name: str = "",
) -> dict[str, Any]:
    item_id = item_id.strip()
    keyword = keyword.strip()
    memo = memo.strip()
    product_id = product_id.strip()
    product_name = product_name.strip()

    if not item_id:
        raise ValueError(
            "수정할 항목 ID가 없습니다."
        )

    if not keyword:
        raise ValueError(
            "키워드를 입력해 주세요."
        )

    with _monitor_lock:
        worksheet = get_monitor_worksheet()
        values = worksheet.get_all_values()

        target_row_number: int | None = None
        registered_at = ""

        for row_number, row in enumerate(
            values[1:],
            start=2,
        ):
            padded = row + [""] * (
                len(MONITOR_HEADERS) - len(row)
            )
            existing_item_id = padded[0].strip()

            if existing_item_id == item_id:
                target_row_number = row_number
                registered_at = padded[2].strip()
                continue

            if (
                padded[1].strip().casefold()
                == keyword.casefold()
                and padded[4].strip()
                == product_id
            ):
                raise DuplicateMonitorError(
                    "이미 등록된 키워드와 상품입니다."
                )

        if target_row_number is None:
            raise ValueError(
                "수정할 모니터링 항목을 찾지 못했습니다."
            )

        updated_item = {
            "item_id": item_id,
            "keyword": keyword,
            "registered_at": registered_at,
            "memo": memo,
            "product_id": product_id,
            "product_name": product_name,
        }

        worksheet.update(
            values=[[
                safe_sheet_value(item_id),
                safe_sheet_value(keyword),
                safe_sheet_value(registered_at),
                safe_sheet_value(memo),
                safe_sheet_value(product_id),
                safe_sheet_value(product_name),
            ]],
            range_name=(
                f"A{target_row_number}:"
                f"F{target_row_number}"
            ),
        )

    return updated_item


def add_monitor_items_bulk(
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    if not items:
        return {
            "added_items": [],
            "added_count": 0,
            "duplicate_count": 0,
        }

    with _monitor_lock:
        worksheet = get_monitor_worksheet()
        values = worksheet.get_all_values()

        existing_keys: set[tuple[str, str]] = set()

        for row in values[1:]:
            padded = row + [""] * len(
                MONITOR_HEADERS
            )

            existing_keys.add((
                padded[1].strip().casefold(),
                padded[4].strip(),
            ))

        added_items: list[dict[str, Any]] = []
        rows: list[list[Any]] = []
        duplicate_count = 0
        incoming_keys: set[tuple[str, str]] = set()

        registered_at = datetime.now(
            KST
        ).strftime("%Y-%m-%d %H:%M:%S")

        for raw_item in items:
            keyword = str(
                raw_item.get("keyword") or ""
            ).strip()
            product_id = str(
                raw_item.get("product_id") or ""
            ).strip()
            product_name = str(
                raw_item.get("product_name") or ""
            ).strip()
            memo = str(
                raw_item.get("memo") or ""
            ).strip()

            if not keyword:
                continue

            key = (
                keyword.casefold(),
                product_id,
            )

            if (
                key in existing_keys
                or key in incoming_keys
            ):
                duplicate_count += 1
                continue

            incoming_keys.add(key)

            item = {
                "item_id": uuid.uuid4().hex,
                "keyword": keyword,
                "registered_at": registered_at,
                "memo": memo,
                "product_id": product_id,
                "product_name": product_name,
            }

            added_items.append(item)

            rows.append([
                safe_sheet_value(item["item_id"]),
                safe_sheet_value(item["keyword"]),
                safe_sheet_value(
                    item["registered_at"]
                ),
                safe_sheet_value(item["memo"]),
                safe_sheet_value(
                    item["product_id"]
                ),
                safe_sheet_value(
                    item["product_name"]
                ),
            ])

        if rows:
            worksheet.append_rows(
                rows,
                value_input_option="RAW",
            )

    return {
        "added_items": added_items,
        "added_count": len(added_items),
        "duplicate_count": duplicate_count,
    }
