from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

from app.config import get_settings


logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
RANK_HISTORY_SHEET = "📊 통합 순위기록"

RANK_HEADERS = [
    "기록ID",
    "수집일시",
    "키워드",
    "순위",
    "상품명",
    "판매처",
    "가격",
    "링크",
    "썸네일",
    "productType",
    "productId",
    "브랜드",
    "제조사",
    "카테고리1",
    "카테고리2",
    "카테고리3",
    "카테고리4",
]

_sheet_lock = threading.Lock()


def safe_sheet_value(value: Any) -> Any:
    if value is None:
        return ""

    if isinstance(value, (int, float, bool)):
        return value

    text = str(value)

    if text.startswith(("=", "+", "-", "@")):
        return "'" + text

    return text


@lru_cache(maxsize=1)
def get_spreadsheet():
    settings = get_settings()

    if (
        not settings.google_sheet_id
        or not settings.gcp_service_account_json
    ):
        raise RuntimeError(
            "Google Sheets 환경설정이 필요합니다."
        )

    service_account = json.loads(
        settings.gcp_service_account_json
    )

    credentials = Credentials.from_service_account_info(
        service_account,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )

    client = gspread.authorize(credentials)

    return client.open_by_key(
        settings.google_sheet_id
    )


def get_rank_worksheet():
    spreadsheet = get_spreadsheet()

    try:
        worksheet = spreadsheet.worksheet(
            RANK_HISTORY_SHEET
        )
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=RANK_HISTORY_SHEET,
            rows=2000,
            cols=len(RANK_HEADERS),
        )

    current_headers = worksheet.row_values(1)

    if not current_headers:
        worksheet.update(
            values=[RANK_HEADERS],
            range_name="A1",
        )
    elif current_headers[:len(RANK_HEADERS)] != RANK_HEADERS:
        raise RuntimeError(
            "통합 순위기록 시트의 헤더 구성이 "
            "기존 프로그램과 다릅니다."
        )

    return worksheet


def make_record_id(
    collected_at: str,
    keyword: str,
    rank: int,
    product_id: str,
) -> str:
    raw = (
        f"{collected_at}|{keyword}|"
        f"{rank}|{product_id}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:32]


def save_rank_search_result(
    search_result: dict[str, Any],
) -> int:
    results = search_result.get("results", [])

    if not results:
        return 0

    keyword = str(
        search_result.get("keyword") or ""
    )
    collected_at = datetime.now(KST).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    rows = []

    for item in results:
        categories = list(
            item.get("categories") or []
        )

        while len(categories) < 4:
            categories.append("")

        rank = int(item.get("rank") or 0)
        product_id = str(
            item.get("product_id") or ""
        )

        row = [
            make_record_id(
                collected_at,
                keyword,
                rank,
                product_id,
            ),
            collected_at,
            keyword,
            rank,
            item.get("title", ""),
            item.get("mall_name", ""),
            item.get("price", 0),
            item.get("link", ""),
            item.get("image", ""),
            item.get("product_type", 0),
            product_id,
            item.get("brand", ""),
            item.get("maker", ""),
            categories[0],
            categories[1],
            categories[2],
            categories[3],
        ]

        rows.append([
            safe_sheet_value(value)
            for value in row
        ])

    with _sheet_lock:
        worksheet = get_rank_worksheet()
        worksheet.append_rows(
            rows,
            value_input_option="RAW",
        )

    return len(rows)


def save_rank_search_result_safely(
    search_result: dict[str, Any],
) -> None:
    try:
        saved_count = save_rank_search_result(
            search_result
        )
        logger.info(
            "순위 검색 결과 %s건을 저장했습니다.",
            saved_count,
        )
    except Exception:
        logger.exception(
            "순위 검색 결과 저장에 실패했습니다."
        )
