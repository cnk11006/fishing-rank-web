from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import gspread
import pandas as pd
import requests
import streamlit as st
from google.oauth2.service_account import Credentials
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# =========================================================
# 0. 로깅·시간대·공통 상수
# =========================================================

logger = logging.getLogger(__name__)

if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


KST = ZoneInfo("Asia/Seoul")

TARGET_STORE = "피싱템"

OUR_STORE_NAMES = {
    "피싱템",
    "피싱템 공식스토어",
    "피싱템스토어",
}

NAVER_SHOP_URL = "https://openapi.naver.com/v1/search/shop.json"
AD_BASE_URL = "https://api.searchad.naver.com"

RANK_HISTORY_SHEET = "📊 통합 순위기록"
MONITOR_SHEET_NAME = "📋 모니터링 목록"
AD_HISTORY_SHEET = "📢 광고진단 기록"
MIGRATION_LOG_SHEET = "⚙️ 마이그레이션 기록"

SYSTEM_SHEETS = {
    RANK_HISTORY_SHEET,
    MONITOR_SHEET_NAME,
    AD_HISTORY_SHEET,
    MIGRATION_LOG_SHEET,
}

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

MONITOR_HEADERS = [
    "항목ID",
    "키워드",
    "등록일",
    "메모",
    "productId",
    "상품명",
]

AD_HISTORY_HEADERS = [
    "기록ID",
    "수집일시",
    "광고ID",
    "캠페인",
    "광고그룹",
    "상품명",
    "ON/OFF",
    "입찰가",
    "품질지수",
    "노출수",
    "클릭수",
    "CTR",
    "평균순위",
    "광고비",
    "진단",
]

MIGRATION_HEADERS = [
    "실행일시",
    "원본시트",
    "이전건수",
    "상태",
    "메모",
]

DEFAULT_TIMEOUT = (5, 25)


# =========================================================
# 1. 시간·문자열·숫자 공통 함수
# =========================================================

def now_kst() -> datetime:
    return datetime.now(KST)


def now_text() -> str:
    return now_kst().strftime("%Y-%m-%d %H:%M:%S")


def today_text() -> str:
    return now_kst().strftime("%Y-%m-%d")


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def clean_naver_title(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"</?b>", "", text, flags=re.IGNORECASE)
    return html.unescape(text).strip()


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\s+", "", text)
    return text.strip()


def normalize_product_name(value: Any) -> str:
    text = clean_naver_title(value).upper()
    text = re.sub(r"[^0-9A-Z가-힣]", "", text)
    return text


def make_hash(*values: Any, length: int = 32) -> str:
    raw = "|||".join(str(v or "") for v in values)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def safe_sheet_value(value: Any) -> Any:
    """
    구글 시트에 RAW로 저장하더라도 외부 문자열이 수식처럼 보이지 않도록 방어한다.
    숫자 타입은 그대로 유지한다.
    """
    if value is None:
        return ""

    if isinstance(value, (int, float, bool)):
        return value

    text = str(value)

    if text.startswith(("=", "+", "-", "@")):
        return "'" + text

    return text


def safe_url(value: Any) -> str:
    """
    화면 링크에 사용할 URL을 http/https로 제한한다.
    """
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


def normalize_store_name(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


NORMALIZED_OUR_STORE_NAMES = {
    normalize_store_name(x) for x in OUR_STORE_NAMES
}


def is_our_store_name(mall_name: Any) -> bool:
    mall = normalize_store_name(mall_name)

    if not mall:
        return False

    if mall in NORMALIZED_OUR_STORE_NAMES:
        return True

    # 상호명 뒤에 공식몰 등의 표현이 붙는 경우 보조 판정
    return any(
        own_name and own_name in mall
        for own_name in NORMALIZED_OUR_STORE_NAMES
    )


def is_our_shop_item(item: dict[str, Any]) -> bool:
    """
    판매처명을 우선 사용한다.

    가격비교 상품은 mallName이 '네이버'로 올 수 있으므로,
    productType=1인 경우에만 상품명의 상호명을 보조 판정으로 사용한다.
    """
    mall_name = item.get("mallName") or item.get("판매처") or ""

    if is_our_store_name(mall_name):
        return True

    product_type = safe_int(
        item.get("productType", item.get("product_type", 0))
    )

    title = clean_naver_title(
        item.get("title") or item.get("상품명") or ""
    )

    if product_type == 1 and TARGET_STORE in title:
        return True

    return False


def get_catalog_badge(product_type: Any) -> str:
    pt = safe_int(product_type)

    mapping = {
        1: "🔗 가격비교 묶음",
        2: "🟡 독립(비매칭)",
        3: "✅ 독립(매칭)",
        4: "🔗 중고 가격비교",
        5: "🟡 중고 독립(비매칭)",
        6: "✅ 중고 독립(매칭)",
        7: "🔗 단종 가격비교",
        8: "🟡 단종 독립(비매칭)",
        9: "✅ 단종 독립(매칭)",
        10: "🔗 판매예정 가격비교",
        11: "🟡 판매예정 독립(비매칭)",
        12: "✅ 판매예정 독립(매칭)",
    }

    return mapping.get(pt, "")


# =========================================================
# 2. Streamlit Secrets
# =========================================================

def load_app_secrets() -> dict[str, str]:
    required = [
        "NAVER_CLIENT_ID",
        "NAVER_CLIENT_SECRET",
        "APP_PASSWORD",
        "GOOGLE_SHEET_ID",
        "NAVER_AD_CUSTOMER_ID",
        "NAVER_AD_ACCESS_LICENSE",
        "NAVER_AD_SECRET_KEY",
    ]

    missing = [key for key in required if key not in st.secrets]

    if "gcp_service_account" not in st.secrets:
        missing.append("gcp_service_account")

    if missing:
        st.error(
            "필수 Secrets 설정이 누락되었습니다: "
            + ", ".join(missing)
        )
        st.stop()

    return {
        "NAVER_CLIENT_ID": str(st.secrets["NAVER_CLIENT_ID"]),
        "NAVER_CLIENT_SECRET": str(st.secrets["NAVER_CLIENT_SECRET"]),
        "APP_PASSWORD": str(st.secrets["APP_PASSWORD"]),
        "GOOGLE_SHEET_ID": str(st.secrets["GOOGLE_SHEET_ID"]),
        "NAVER_AD_CUSTOMER_ID": str(
            st.secrets["NAVER_AD_CUSTOMER_ID"]
        ),
        "NAVER_AD_ACCESS_LICENSE": str(
            st.secrets["NAVER_AD_ACCESS_LICENSE"]
        ),
        "NAVER_AD_SECRET_KEY": str(
            st.secrets["NAVER_AD_SECRET_KEY"]
        ),
    }


# =========================================================
# 3. HTTP 세션·재시도
# =========================================================

@st.cache_resource
def get_http_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST", "PUT", "DELETE"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=10,
        pool_maxsize=20,
    )

    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update({
        "User-Agent": "Fishingtem-Rank-Radar/5.0",
        "Accept": "application/json",
    })

    return session


def response_error_message(
    response: requests.Response,
    prefix: str = "API 오류",
) -> str:
    body = ""

    try:
        data = response.json()
        body = (
            data.get("errorMessage")
            or data.get("detail")
            or data.get("title")
            or str(data)
        )
    except Exception:
        body = response.text[:300]

    return f"{prefix} {response.status_code}: {body}"


# =========================================================
# 4. 구글 시트 연결·공통 함수
# =========================================================

@st.cache_resource
def get_google_sheet():
    secrets = load_app_secrets()

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=scopes,
    )

    client = gspread.authorize(credentials)

    return client.open_by_key(secrets["GOOGLE_SHEET_ID"])


def get_or_create_worksheet(
    spreadsheet,
    title: str,
    rows: int = 1000,
    cols: int = 20,
):
    try:
        return spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(
            title=title,
            rows=rows,
            cols=cols,
        )


def ensure_worksheet_headers(
    worksheet,
    expected_headers: list[str],
) -> tuple[bool, str | None]:
    """
    빈 시트에는 헤더를 생성한다.

    기존 시트의 헤더가 다를 경우 데이터를 삭제하지 않고 오류만 반환한다.
    """
    values = worksheet.get_all_values()

    if not values:
        worksheet.append_row(
            expected_headers,
            value_input_option="RAW",
        )
        return True, None

    current = values[0]

    if current[:len(expected_headers)] != expected_headers:
        return (
            False,
            f"'{worksheet.title}' 시트 헤더가 예상 형식과 다릅니다. "
            f"현재: {current} / 필요: {expected_headers}",
        )

    return True, None


def worksheet_records_safe(
    worksheet,
    expected_headers: list[str],
) -> tuple[list[dict[str, Any]], str | None]:
    ok, error = ensure_worksheet_headers(
        worksheet,
        expected_headers,
    )

    if not ok:
        return [], error

    try:
        return worksheet.get_all_records(), None
    except Exception as exc:
        logger.exception("워크시트 읽기 실패: %s", worksheet.title)
        return [], str(exc)


def append_raw_rows(
    worksheet,
    rows: list[list[Any]],
) -> None:
    if not rows:
        return

    safe_rows = [
        [safe_sheet_value(cell) for cell in row]
        for row in rows
    ]

    worksheet.append_rows(
        safe_rows,
        value_input_option="RAW",
    )


# =========================================================
# 5. 통합 순위기록 시트
# =========================================================

def ensure_rank_history_sheet():
    spreadsheet = get_google_sheet()

    worksheet = get_or_create_worksheet(
        spreadsheet,
        RANK_HISTORY_SHEET,
        rows=10000,
        cols=len(RANK_HEADERS),
    )

    ok, error = ensure_worksheet_headers(
        worksheet,
        RANK_HEADERS,
    )

    if not ok:
        raise ValueError(error)

    return worksheet


def make_rank_record_id(
    collected_at: str,
    keyword: str,
    item: dict[str, Any],
) -> str:
    product_identity = (
        item.get("productId")
        or normalize_product_name(item.get("상품명", ""))
    )

    return make_hash(
        collected_at,
        keyword,
        item.get("순위", ""),
        product_identity,
        item.get("판매처", ""),
    )


def rank_item_to_row(
    keyword: str,
    item: dict[str, Any],
    collected_at: str,
) -> list[Any]:
    record_id = make_rank_record_id(
        collected_at,
        keyword,
        item,
    )

    return [
        record_id,
        collected_at,
        keyword,
        safe_int(item.get("순위")),
        item.get("상품명", ""),
        item.get("판매처", ""),
        safe_int(item.get("가격")),
        safe_url(item.get("링크", "")),
        safe_url(item.get("썸네일", "")),
        safe_int(item.get("productType")),
        str(item.get("productId", "")),
        item.get("브랜드", ""),
        item.get("제조사", ""),
        item.get("카테고리1", ""),
        item.get("카테고리2", ""),
        item.get("카테고리3", ""),
        item.get("카테고리4", ""),
    ]


def save_rank_records(
    keyword: str,
    found_items: list[dict[str, Any]],
    collected_at: str | None = None,
) -> tuple[bool, str]:
    if not keyword.strip():
        return False, "키워드가 비어 있습니다."

    if not found_items:
        return False, "저장할 상품이 없습니다."

    try:
        worksheet = ensure_rank_history_sheet()
        collected_at = collected_at or now_text()

        rows = [
            rank_item_to_row(
                keyword=keyword.strip(),
                item=item,
                collected_at=collected_at,
            )
            for item in found_items
        ]

        append_raw_rows(worksheet, rows)

        load_rank_history.clear()

        return True, f"{len(rows)}건 저장 완료"

    except Exception as exc:
        logger.exception("통합 순위기록 저장 실패")
        return False, f"구글 시트 저장 오류: {exc}"


@st.cache_data(ttl=300, max_entries=20)
def load_rank_history(
    keywords_tuple: tuple[str, ...] = (),
) -> dict[str, list[dict[str, Any]]]:
    """
    통합 순위기록 시트에서 지정된 키워드만 반환한다.

    keywords_tuple이 비어 있으면 전체 데이터를 반환한다.
    """
    try:
        worksheet = ensure_rank_history_sheet()
        records, error = worksheet_records_safe(
            worksheet,
            RANK_HEADERS,
        )

        if error:
            logger.error(error)
            return {}

        keyword_filter = {
            str(x).strip()
            for x in keywords_tuple
            if str(x).strip()
        }

        output: dict[str, list[dict[str, Any]]] = {}

        if keyword_filter:
            output = {keyword: [] for keyword in keyword_filter}

        for row in records:
            keyword = str(row.get("키워드", "")).strip()

            if not keyword:
                continue

            if keyword_filter and keyword not in keyword_filter:
                continue

            rank = safe_int(row.get("순위"))

            if rank <= 0:
                continue

            record = {
                "기록ID": str(row.get("기록ID", "")),
                "날짜": str(row.get("수집일시", "")),
                "키워드": keyword,
                "순위": rank,
                "상품명": str(row.get("상품명", "")),
                "판매처": str(row.get("판매처", "")),
                "가격": safe_int(row.get("가격")),
                "링크": safe_url(row.get("링크", "")),
                "썸네일": safe_url(row.get("썸네일", "")),
                "productType": safe_int(row.get("productType")),
                "productId": str(row.get("productId", "")),
                "브랜드": str(row.get("브랜드", "")),
                "제조사": str(row.get("제조사", "")),
                "카테고리1": str(row.get("카테고리1", "")),
                "카테고리2": str(row.get("카테고리2", "")),
                "카테고리3": str(row.get("카테고리3", "")),
                "카테고리4": str(row.get("카테고리4", "")),
            }

            output.setdefault(keyword, []).append(record)

        for keyword in output:
            output[keyword].sort(
                key=lambda x: (
                    str(x.get("날짜", "")),
                    safe_int(x.get("순위"), 9999),
                )
            )

        return output

    except Exception:
        logger.exception("통합 순위기록 불러오기 실패")
        return {}


def delete_rank_records_by_monitor(
    keyword: str,
    product_id: str = "",
    product_name: str = "",
) -> tuple[bool, str]:
    """
    모니터링 항목 삭제 시 기록까지 삭제하고 싶은 경우 사용할 수 있는 함수다.

    기본 UI에서는 모니터링 항목만 삭제하고 순위기록은 보존한다.
    """
    try:
        worksheet = ensure_rank_history_sheet()
        values = worksheet.get_all_values()

        if len(values) <= 1:
            return True, "삭제할 기록이 없습니다."

        headers = values[0]
        rows = values[1:]

        col_map = {
            name: index
            for index, name in enumerate(headers)
        }

        rows_to_delete: list[int] = []

        for sheet_row, row in enumerate(rows, start=2):
            def gv(name: str) -> str:
                index = col_map.get(name)
                if index is None or index >= len(row):
                    return ""
                return str(row[index])

            if gv("키워드").strip() != keyword.strip():
                continue

            if product_id:
                matched = gv("productId").strip() == product_id.strip()
            elif product_name:
                matched = (
                    normalize_product_name(gv("상품명"))
                    == normalize_product_name(product_name)
                )
            else:
                matched = True

            if matched:
                rows_to_delete.append(sheet_row)

        for row_number in reversed(rows_to_delete):
            worksheet.delete_rows(row_number)

        load_rank_history.clear()

        return True, f"{len(rows_to_delete)}건 삭제 완료"

    except Exception as exc:
        logger.exception("통합 순위기록 삭제 실패")
        return False, str(exc)


# =========================================================
# 6. 기존 키워드별 시트 → 통합 순위기록 마이그레이션
# =========================================================

def get_migration_log_sheet():
    spreadsheet = get_google_sheet()

    worksheet = get_or_create_worksheet(
        spreadsheet,
        MIGRATION_LOG_SHEET,
        rows=1000,
        cols=len(MIGRATION_HEADERS),
    )

    ok, error = ensure_worksheet_headers(
        worksheet,
        MIGRATION_HEADERS,
    )

    if not ok:
        raise ValueError(error)

    return worksheet


def get_migrated_sheet_names() -> set[str]:
    try:
        worksheet = get_migration_log_sheet()
        records, error = worksheet_records_safe(
            worksheet,
            MIGRATION_HEADERS,
        )

        if error:
            return set()

        return {
            str(row.get("원본시트", "")).strip()
            for row in records
            if str(row.get("상태", "")).strip() == "완료"
        }

    except Exception:
        logger.exception("마이그레이션 로그 읽기 실패")
        return set()


def detect_legacy_rank_header(
    first_row: list[str],
) -> tuple[list[str], bool]:
    known_headers = {
        "날짜",
        "순위",
        "상품명",
        "판매처",
        "가격",
        "링크",
        "썸네일",
        "productType",
        "productId",
    }

    has_header = any(
        str(cell).strip() in known_headers
        for cell in first_row
    )

    if has_header:
        return [str(x).strip() for x in first_row], True

    column_count = len(first_row)

    default = [
        "날짜",
        "순위",
        "상품명",
        "판매처",
        "가격",
        "링크",
    ]

    if column_count >= 7:
        default.append("썸네일")

    if column_count >= 8:
        default.append("productType")

    if column_count >= 9:
        default.append("productId")

    return default, False


def legacy_sheet_rows_to_rank_rows(
    worksheet,
) -> list[list[Any]]:
    values = worksheet.get_all_values()

    if not values:
        return []

    header, has_header = detect_legacy_rank_header(values[0])
    data_rows = values[1:] if has_header else values

    column_map = {
        name: index
        for index, name in enumerate(header)
    }

    def get_value(row: list[str], name: str) -> str:
        index = column_map.get(name)

        if index is None or index >= len(row):
            return ""

        return str(row[index]).strip()

    migrated_rows: list[list[Any]] = []
    keyword = worksheet.title

    for source_index, row in enumerate(data_rows, start=2):
        if not row or not any(str(cell).strip() for cell in row):
            continue

        collected_at = get_value(row, "날짜")
        rank = safe_int(get_value(row, "순위"))
        product_name = get_value(row, "상품명")

        if not collected_at or rank <= 0 or not product_name:
            continue

        item = {
            "순위": rank,
            "상품명": product_name,
            "판매처": get_value(row, "판매처"),
            "가격": safe_int(get_value(row, "가격")),
            "링크": get_value(row, "링크"),
            "썸네일": get_value(row, "썸네일"),
            "productType": safe_int(
                get_value(row, "productType")
            ),
            "productId": get_value(row, "productId"),
            "브랜드": "",
            "제조사": "",
            "카테고리1": "",
            "카테고리2": "",
            "카테고리3": "",
            "카테고리4": "",
        }

        new_row = rank_item_to_row(
            keyword=keyword,
            item=item,
            collected_at=collected_at,
        )

        # 과거 시트 내 같은 행이 재이전되지 않도록 원본 위치도 ID에 반영
        new_row[0] = make_hash(
            "legacy",
            worksheet.title,
            source_index,
            collected_at,
            rank,
            product_name,
            item["판매처"],
        )

        migrated_rows.append(new_row)

    return migrated_rows


def migrate_legacy_rank_sheets(
    include_already_migrated: bool = False,
) -> dict[str, Any]:
    """
    기존 키워드별 워크시트 데이터를 통합 순위기록으로 이전한다.

    원본 시트는 삭제하지 않는다.
    """
    spreadsheet = get_google_sheet()
    target = ensure_rank_history_sheet()
    log_sheet = get_migration_log_sheet()

    migrated_names = (
        set()
        if include_already_migrated
        else get_migrated_sheet_names()
    )

    results: list[dict[str, Any]] = []
    total_count = 0

    worksheets = spreadsheet.worksheets()

    for worksheet in worksheets:
        title = worksheet.title

        if title in SYSTEM_SHEETS:
            continue

        if title in migrated_names:
            results.append({
                "원본시트": title,
                "이전건수": 0,
                "상태": "건너뜀",
                "메모": "이미 이전 완료된 시트",
            })
            continue

        try:
            rows = legacy_sheet_rows_to_rank_rows(worksheet)

            if rows:
                append_raw_rows(target, rows)

            result = {
                "원본시트": title,
                "이전건수": len(rows),
                "상태": "완료",
                "메모": "원본 시트 보존",
            }

            append_raw_rows(
                log_sheet,
                [[
                    now_text(),
                    title,
                    len(rows),
                    "완료",
                    "원본 시트 보존",
                ]],
            )

            total_count += len(rows)
            results.append(result)

        except Exception as exc:
            logger.exception(
                "기존 시트 마이그레이션 실패: %s",
                title,
            )

            result = {
                "원본시트": title,
                "이전건수": 0,
                "상태": "오류",
                "메모": str(exc),
            }

            results.append(result)

            append_raw_rows(
                log_sheet,
                [[
                    now_text(),
                    title,
                    0,
                    "오류",
                    str(exc),
                ]],
            )

    load_rank_history.clear()

    return {
        "총이전건수": total_count,
        "결과": results,
    }


# =========================================================
# 7. 모니터링 목록
# =========================================================

def ensure_monitor_sheet():
    spreadsheet = get_google_sheet()

    worksheet = get_or_create_worksheet(
        spreadsheet,
        MONITOR_SHEET_NAME,
        rows=1000,
        cols=len(MONITOR_HEADERS),
    )

    values = worksheet.get_all_values()

    # 기존 3열 구조를 데이터 삭제 없이 6열 구조로 자동 확장
    if values and values[0][:3] == ["키워드", "등록일", "메모"]:
        old_rows = values[1:]

        worksheet.clear()

        append_raw_rows(
            worksheet,
            [MONITOR_HEADERS],
        )

        converted: list[list[Any]] = []

        for row in old_rows:
            keyword = row[0] if len(row) > 0 else ""
            registered_at = row[1] if len(row) > 1 else ""
            memo = row[2] if len(row) > 2 else ""

            if not str(keyword).strip():
                continue

            product_name = ""

            if str(memo).startswith("등록상품:"):
                product_name = str(memo).replace(
                    "등록상품:",
                    "",
                    1,
                ).strip()

            item_id = make_hash(
                keyword,
                memo,
                product_name,
            )

            converted.append([
                item_id,
                keyword,
                registered_at,
                memo,
                "",
                product_name,
            ])

        append_raw_rows(worksheet, converted)

        return worksheet

    ok, error = ensure_worksheet_headers(
        worksheet,
        MONITOR_HEADERS,
    )

    if not ok:
        raise ValueError(error)

    return worksheet


@st.cache_data(ttl=300, max_entries=5)
def load_monitor_keywords() -> list[dict[str, Any]]:
    try:
        worksheet = ensure_monitor_sheet()

        records, error = worksheet_records_safe(
            worksheet,
            MONITOR_HEADERS,
        )

        if error:
            logger.error(error)
            return []

        output = []

        for row in records:
            keyword = str(row.get("키워드", "")).strip()

            if not keyword:
                continue

            output.append({
                "항목ID": str(row.get("항목ID", "")).strip(),
                "키워드": keyword,
                "등록일": str(row.get("등록일", "")).strip(),
                "메모": str(row.get("메모", "")).strip(),
                "productId": str(
                    row.get("productId", "")
                ).strip(),
                "상품명": str(row.get("상품명", "")).strip(),
            })

        return output

    except Exception:
        logger.exception("모니터링 목록 불러오기 실패")
        return []


def add_monitor_keyword(
    keyword: str,
    memo: str = "",
    product_id: str = "",
    product_name: str = "",
) -> tuple[bool, str]:
    keyword = str(keyword).strip()
    memo = str(memo).strip()
    product_id = str(product_id).strip()
    product_name = str(product_name).strip()

    if not keyword:
        return False, "키워드가 비어 있습니다."

    try:
        worksheet = ensure_monitor_sheet()
        records = load_monitor_keywords()

        for row in records:
            same_keyword = row["키워드"] == keyword

            if product_id:
                same_product = (
                    row.get("productId", "") == product_id
                )
            elif product_name:
                same_product = (
                    normalize_product_name(
                        row.get("상품명", "")
                    )
                    == normalize_product_name(product_name)
                )
            else:
                same_product = row.get("메모", "") == memo

            if same_keyword and same_product:
                return False, "이미 등록된 모니터링 항목입니다."

        item_id = make_hash(
            keyword,
            product_id,
            normalize_product_name(product_name),
            memo,
        )

        append_raw_rows(
            worksheet,
            [[
                item_id,
                keyword,
                now_text(),
                memo,
                product_id,
                product_name,
            ]],
        )

        load_monitor_keywords.clear()

        return True, "등록 완료"

    except Exception as exc:
        logger.exception("모니터링 등록 실패")
        return False, f"등록 오류: {exc}"


def delete_monitor_items(
    item_ids: Iterable[str],
) -> tuple[bool, str]:
    target_ids = {
        str(item_id).strip()
        for item_id in item_ids
        if str(item_id).strip()
    }

    if not target_ids:
        return False, "삭제할 항목이 없습니다."

    try:
        worksheet = ensure_monitor_sheet()
        values = worksheet.get_all_values()

        if len(values) <= 1:
            return False, "삭제할 항목이 없습니다."

        header = values[0]

        try:
            id_index = header.index("항목ID")
        except ValueError:
            return False, "모니터링 시트에서 항목ID 열을 찾지 못했습니다."

        rows_to_delete: list[int] = []

        for row_number, row in enumerate(values[1:], start=2):
            item_id = (
                str(row[id_index]).strip()
                if id_index < len(row)
                else ""
            )

            if item_id in target_ids:
                rows_to_delete.append(row_number)

        for row_number in reversed(rows_to_delete):
            worksheet.delete_rows(row_number)

        load_monitor_keywords.clear()

        return True, f"{len(rows_to_delete)}개 삭제 완료"

    except Exception as exc:
        logger.exception("모니터링 삭제 실패")
        return False, f"삭제 오류: {exc}"


# =========================================================
# 8. 네이버 쇼핑 순위 수집
# =========================================================

def naver_shop_headers(
    client_id: str,
    client_secret: str,
) -> dict[str, str]:
    return {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }


def parse_naver_shop_item(
    item: dict[str, Any],
    rank: int,
) -> dict[str, Any]:
    product_type = safe_int(item.get("productType"))

    return {
        "순위": rank,
        "productId": str(item.get("productId", "")),
        "상품명": clean_naver_title(item.get("title", "")),
        "판매처": str(item.get("mallName", "")).strip(),
        "가격": safe_int(item.get("lprice")),
        "최고가": safe_int(item.get("hprice")),
        "링크": safe_url(item.get("link", "")),
        "썸네일": safe_url(item.get("image", "")),
        "productType": product_type,
        "묶음여부": product_type in {1, 4, 7, 10},
        "브랜드": str(item.get("brand", "")).strip(),
        "제조사": str(item.get("maker", "")).strip(),
        "카테고리1": str(item.get("category1", "")).strip(),
        "카테고리2": str(item.get("category2", "")).strip(),
        "카테고리3": str(item.get("category3", "")).strip(),
        "카테고리4": str(item.get("category4", "")).strip(),
    }


def fetch_naver_shop_page(
    keyword: str,
    client_id: str,
    client_secret: str,
    start: int = 1,
    display: int = 100,
    exclude: str = "",
) -> tuple[list[dict[str, Any]], str | None]:
    session = get_http_session()

    params = {
        "query": keyword,
        "display": min(max(display, 1), 100),
        "start": min(max(start, 1), 1000),
        "sort": "sim",
    }

    if exclude:
        params["exclude"] = exclude

    try:
        response = session.get(
            NAVER_SHOP_URL,
            headers=naver_shop_headers(
                client_id,
                client_secret,
            ),
            params=params,
            timeout=DEFAULT_TIMEOUT,
        )

        if response.status_code != 200:
            return [], response_error_message(
                response,
                "네이버 쇼핑 API 오류",
            )

        data = response.json()
        items = data.get("items", [])

        if not isinstance(items, list):
            return [], "네이버 쇼핑 API 응답 형식이 올바르지 않습니다."

        return items, None

    except requests.Timeout:
        return [], "네이버 쇼핑 API 응답 시간이 초과되었습니다."
    except requests.RequestException as exc:
        return [], f"네이버 쇼핑 API 연결 오류: {exc}"
    except Exception as exc:
        logger.exception("네이버 쇼핑 API 처리 오류")
        return [], f"네이버 쇼핑 API 처리 오류: {exc}"


def collect_rank_data(
    keyword: str,
    client_id: str,
    client_secret: str,
    max_rank: int = 400,
    exclude_used_rental_overseas: bool = True,
) -> tuple[
    list[dict[str, Any]],
    list[int],
    list[dict[str, Any]],
    str | None,
]:
    """
    최대 400위까지 수집한다.

    반환:
    - 자사 상품
    - TOP10 가격
    - TOP100 상품
    - 오류 메시지
    """
    keyword = str(keyword).strip()

    if not keyword:
        return [], [], [], "검색 키워드가 비어 있습니다."

    max_rank = min(max(max_rank, 1), 1000)
    page_count = (max_rank + 99) // 100

    found_items: list[dict[str, Any]] = []
    top10_prices: list[int] = []
    top100_items: list[dict[str, Any]] = []

    exclude = (
        "used:rental:cbshop"
        if exclude_used_rental_overseas
        else ""
    )

    errors: list[str] = []

    for page_index in range(page_count):
        start = page_index * 100 + 1

        raw_items, error = fetch_naver_shop_page(
            keyword=keyword,
            client_id=client_id,
            client_secret=client_secret,
            start=start,
            display=100,
            exclude=exclude,
        )

        if error:
            errors.append(
                f"{start}위 구간: {error}"
            )
            break

        if not raw_items:
            break

        for item_index, raw_item in enumerate(raw_items):
            rank = start + item_index

            if rank > max_rank:
                break

            item = parse_naver_shop_item(
                raw_item,
                rank,
            )

            price = item["가격"]

            if rank <= 10 and price > 0:
                top10_prices.append(price)

            if rank <= 100 and price > 0:
                top100_items.append(item)

            if is_our_shop_item(raw_item):
                found_items.append(item)

        time.sleep(0.08)

    error_message = " / ".join(errors) if errors else None

    return (
        found_items,
        top10_prices,
        top100_items,
        error_message,
    )


def collect_rank_light(
    keyword: str,
    client_id: str,
    client_secret: str,
    limit: int = 50,
    exclude_used_rental_overseas: bool = True,
) -> tuple[list[dict[str, Any]], str | None]:
    limit = min(max(safe_int(limit, 50), 1), 100)

    exclude = (
        "used:rental:cbshop"
        if exclude_used_rental_overseas
        else ""
    )

    raw_items, error = fetch_naver_shop_page(
        keyword=keyword,
        client_id=client_id,
        client_secret=client_secret,
        start=1,
        display=100,
        exclude=exclude,
    )

    if error:
        return [], error

    parsed = [
        parse_naver_shop_item(item, index + 1)
        for index, item in enumerate(raw_items[:limit])
    ]

    return parsed, None


# =========================================================
# 9. 검색광고 API 인증
# =========================================================

def get_ad_api_header(
    method: str,
    uri: str,
    access_license: str,
    customer_id: str,
    secret_key: str,
) -> dict[str, str]:
    timestamp = str(int(time.time() * 1000))
    signature_source = f"{timestamp}.{method.upper()}.{uri}"

    digest = hmac.new(
        secret_key.encode("utf-8"),
        signature_source.encode("utf-8"),
        hashlib.sha256,
    )

    signature = base64.b64encode(
        digest.digest()
    ).decode("utf-8")

    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": access_license,
        "X-Customer": str(customer_id),
        "X-Signature": signature,
    }


def ad_api_get(
    uri: str,
    params: dict[str, Any] | None = None,
) -> tuple[Any, str | None]:
    secrets = load_app_secrets()
    session = get_http_session()

    headers = get_ad_api_header(
        method="GET",
        uri=uri,
        access_license=secrets["NAVER_AD_ACCESS_LICENSE"],
        customer_id=secrets["NAVER_AD_CUSTOMER_ID"],
        secret_key=secrets["NAVER_AD_SECRET_KEY"],
    )

    try:
        response = session.get(
            AD_BASE_URL + uri,
            params=params,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )

        if response.status_code != 200:
            return None, response_error_message(
                response,
                "검색광고 API 오류",
            )

        return response.json(), None

    except requests.Timeout:
        return None, "검색광고 API 응답 시간이 초과되었습니다."
    except requests.RequestException as exc:
        return None, f"검색광고 API 연결 오류: {exc}"
    except Exception as exc:
        logger.exception("검색광고 API 처리 오류")
        return None, f"검색광고 API 처리 오류: {exc}"


# =========================================================
# 10. 키워드 검색량
# =========================================================

def parse_keyword_volume(
    value: Any,
) -> tuple[int, bool]:
    """
    '< 10'은 계산용 중앙 추정치 5로 변환하고 추정 여부를 반환한다.
    """
    text = str(value or "").strip()

    if text.replace(" ", "") in {"<10", "10미만"}:
        return 5, True

    try:
        return int(float(text.replace(",", ""))), False
    except (TypeError, ValueError):
        return 0, False


@st.cache_data(ttl=600, max_entries=200)
def get_keyword_stats(
    keywords_tuple: tuple[str, ...],
) -> list[dict[str, Any]]:
    keywords = [
        normalize_text(keyword)
        for keyword in keywords_tuple
        if normalize_text(keyword)
    ]

    if not keywords:
        return []

    competition_map = {
        "low": "🟢 낮음",
        "mid": "🟡 중간",
        "high": "🔴 높음",
        "Low": "🟢 낮음",
        "Mid": "🟡 중간",
        "High": "🔴 높음",
        "LOW": "🟢 낮음",
        "MID": "🟡 중간",
        "HIGH": "🔴 높음",
        "낮음": "🟢 낮음",
        "중간": "🟡 중간",
        "높음": "🔴 높음",
    }

    all_results: list[dict[str, Any]] = []
    seen: set[str] = set()

    # hintKeywords는 공백 제거 후 쉼표로 전달
    for start_index in range(0, len(keywords), 5):
        chunk = keywords[start_index:start_index + 5]

        params = {
            "hintKeywords": ",".join(chunk),
            "showDetail": "1",
        }

        data, error = ad_api_get(
            "/keywordstool",
            params=params,
        )

        if error:
            logger.warning(
                "키워드 도구 오류: %s",
                error,
            )
            continue

        for item in (data or {}).get("keywordList", []):
            keyword = str(
                item.get("relKeyword", "")
            ).strip()

            normalized_keyword = normalize_text(keyword)

            if not normalized_keyword:
                continue

            # 여러 힌트 키워드에서 같은 연관키워드가 반복될 수 있음
            if normalized_keyword in seen:
                continue

            seen.add(normalized_keyword)

            pc_volume, pc_estimated = parse_keyword_volume(
                item.get("monthlyPcQcCnt", 0)
            )

            mobile_volume, mobile_estimated = parse_keyword_volume(
                item.get("monthlyMobileQcCnt", 0)
            )

            competition = item.get("compIdx", "")

            all_results.append({
                "키워드": keyword,
                "PC 검색량": pc_volume,
                "모바일 검색량": mobile_volume,
                "총 검색량": pc_volume + mobile_volume,
                "경쟁강도": competition_map.get(
                    competition,
                    str(competition),
                ),
                "PC 평균클릭수": safe_float(
                    item.get("monthlyAvePcClkCnt", 0)
                ),
                "모바일 평균클릭수": safe_float(
                    item.get("monthlyAveMobileClkCnt", 0)
                ),
                "PC 평균클릭률": safe_float(
                    item.get("monthlyAvePcCtr", 0)
                ),
                "모바일 평균클릭률": safe_float(
                    item.get("monthlyAveMobileCtr", 0)
                ),
                "검색량 추정": (
                    "일부 <10 추정"
                    if pc_estimated or mobile_estimated
                    else ""
                ),
            })

        time.sleep(0.15)

    return all_results


def get_keyword_stats_list(
    keywords: list[str],
) -> list[dict[str, Any]]:
    """
    화면 코드에서 리스트로 편하게 호출하기 위한 래퍼.
    캐시 키를 안정적으로 만들기 위해 내부에서는 tuple을 사용한다.
    """
    normalized = tuple(
        normalize_text(keyword)
        for keyword in keywords
        if normalize_text(keyword)
    )

    return get_keyword_stats(normalized)


def get_exact_keyword_volume(
    query: str,
    local_cache: dict[str, int] | None = None,
) -> int:
    normalized_query = normalize_text(query)

    if not normalized_query:
        return 0

    if (
        local_cache is not None
        and normalized_query in local_cache
    ):
        return local_cache[normalized_query]

    results = get_keyword_stats_list(
        [normalized_query]
    )

    volume = 0

    for row in results:
        if normalize_text(row.get("키워드")) == normalized_query:
            volume = safe_int(row.get("총 검색량"))
            break

    if volume == 0 and results:
        # API가 정확 키워드 대신 연관 키워드만 반환하는 경우,
        # 첫 결과를 무조건 사용하지 않고 동일 문자열이 없으면 0 유지
        volume = 0

    if local_cache is not None:
        local_cache[normalized_query] = volume

    return volume

