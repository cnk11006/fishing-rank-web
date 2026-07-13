"""
auto_collect.py

GitHub Actions에서 매일 자동 실행되는 순위 수집 스크립트.

B안 통합 저장 방식:
- 모니터링 목록: 📋 모니터링 목록
- 순위 기록: 📊 통합 순위기록

주의:
- Streamlit Secrets가 아닌 GitHub Actions Secrets를 사용한다.
- 기존 키워드별 워크시트에는 더 이상 저장하지 않는다.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import gspread
import requests
from google.oauth2.service_account import Credentials
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# =========================================================
# 0. 환경변수·상수
# =========================================================

KST = ZoneInfo("Asia/Seoul")

TARGET_STORE = "피싱템"

OUR_STORE_NAMES = {
    "피싱템",
    "피싱템 공식스토어",
    "피싱템스토어",
}

NAVER_SHOP_URL = (
    "https://openapi.naver.com/v1/search/shop.json"
)

MONITOR_SHEET_NAME = "📋 모니터링 목록"
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

DEFAULT_TIMEOUT = (5, 25)


# =========================================================
# 1. 환경변수 확인
# =========================================================

def require_environment_variable(name: str) -> str:
    value = os.environ.get(name, "").strip()

    if not value:
        print(f"❌ 필수 환경변수가 없습니다: {name}")
        sys.exit(1)

    return value


CLIENT_ID = require_environment_variable(
    "NAVER_CLIENT_ID"
)

CLIENT_SECRET = require_environment_variable(
    "NAVER_CLIENT_SECRET"
)

SHEET_ID = require_environment_variable(
    "GOOGLE_SHEET_ID"
)

GCP_JSON_TEXT = require_environment_variable(
    "GCP_SERVICE_ACCOUNT_JSON"
)

try:
    GCP_JSON = json.loads(GCP_JSON_TEXT)
except json.JSONDecodeError as exc:
    print(
        "❌ GCP_SERVICE_ACCOUNT_JSON 형식이 올바르지 않습니다."
    )
    print(str(exc))
    sys.exit(1)


# =========================================================
# 2. 공통 함수
# =========================================================

def now_kst() -> datetime:
    return datetime.now(KST)


def now_text() -> str:
    return now_kst().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        if value is None or value == "":
            return default

        return int(
            float(
                str(value)
                .replace(",", "")
                .strip()
            )
        )

    except (TypeError, ValueError):
        return default


def clean_naver_title(value: Any) -> str:
    text = str(value or "")

    text = re.sub(
        r"</?b>",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return html.unescape(text).strip()


def normalize_store_name(value: Any) -> str:
    return re.sub(
        r"\s+",
        "",
        str(value or ""),
    ).lower()


NORMALIZED_OUR_STORE_NAMES = {
    normalize_store_name(name)
    for name in OUR_STORE_NAMES
}


def safe_url(value: Any) -> str:
    url = str(value or "").strip()

    if not url:
        return ""

    try:
        parsed = urlparse(url)

        if parsed.scheme in {
            "http",
            "https",
        }:
            return url

    except Exception:
        pass

    return ""


def safe_sheet_value(value: Any) -> Any:
    """
    외부 문자열이 구글 시트 수식으로 처리되지 않도록 방어한다.
    """
    if value is None:
        return ""

    if isinstance(
        value,
        (int, float, bool),
    ):
        return value

    text = str(value)

    if text.startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + text

    return text


def make_hash(
    *values: Any,
    length: int = 32,
) -> str:
    raw = "|||".join(
        str(value or "")
        for value in values
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:length]


def is_our_store_name(
    mall_name: Any,
) -> bool:
    normalized_mall = normalize_store_name(
        mall_name
    )

    if not normalized_mall:
        return False

    if (
        normalized_mall
        in NORMALIZED_OUR_STORE_NAMES
    ):
        return True

    return any(
        own_name
        and own_name in normalized_mall
        for own_name
        in NORMALIZED_OUR_STORE_NAMES
    )


def is_our_item(
    raw_item: dict[str, Any],
) -> bool:
    mall_name = str(
        raw_item.get("mallName", "")
    ).strip()

    if is_our_store_name(mall_name):
        return True

    product_type = safe_int(
        raw_item.get("productType")
    )

    product_name = clean_naver_title(
        raw_item.get("title", "")
    )

    # 가격비교 상품은 mallName이 네이버로 표시될 수 있어
    # 상품명의 상호명을 보조 판정으로 사용
    if (
        product_type == 1
        and TARGET_STORE in product_name
    ):
        return True

    return False


# =========================================================
# 3. HTTP 세션
# =========================================================

def create_http_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.7,
        status_forcelist=(
            429,
            500,
            502,
            503,
            504,
        ),
        allowed_methods=frozenset({
            "GET",
        }),
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=5,
        pool_maxsize=10,
    )

    session = requests.Session()

    session.mount(
        "https://",
        adapter,
    )

    session.mount(
        "http://",
        adapter,
    )

    session.headers.update({
        "User-Agent": (
            "Fishingtem-Rank-Auto-Collector/5.0"
        ),
        "Accept": "application/json",
    })

    return session


HTTP_SESSION = create_http_session()


# =========================================================
# 4. 구글 시트
# =========================================================

def get_spreadsheet():
    scopes = [
        (
            "https://www.googleapis.com/"
            "auth/spreadsheets"
        ),
        (
            "https://www.googleapis.com/"
            "auth/drive"
        ),
    ]

    credentials = (
        Credentials.from_service_account_info(
            GCP_JSON,
            scopes=scopes,
        )
    )

    client = gspread.authorize(
        credentials
    )

    return client.open_by_key(
        SHEET_ID
    )


def get_or_create_worksheet(
    spreadsheet,
    title: str,
    rows: int = 1000,
    cols: int = 20,
):
    try:
        return spreadsheet.worksheet(
            title
        )

    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(
            title=title,
            rows=rows,
            cols=cols,
        )


def ensure_headers(
    worksheet,
    expected_headers: list[str],
) -> None:
    values = worksheet.get_all_values()

    if not values:
        worksheet.append_row(
            expected_headers,
            value_input_option="RAW",
        )

        return

    current_headers = values[0]

    if (
        current_headers[
            :len(expected_headers)
        ]
        != expected_headers
    ):
        raise ValueError(
            f"'{worksheet.title}' 시트 헤더가 "
            "예상 형식과 다릅니다.\n"
            f"현재: {current_headers}\n"
            f"필요: {expected_headers}"
        )


def append_raw_rows(
    worksheet,
    rows: list[list[Any]],
) -> None:
    if not rows:
        return

    safe_rows = [
        [
            safe_sheet_value(cell)
            for cell in row
        ]
        for row in rows
    ]

    worksheet.append_rows(
        safe_rows,
        value_input_option="RAW",
    )


def get_rank_history_worksheet(
    spreadsheet,
):
    worksheet = get_or_create_worksheet(
        spreadsheet,
        RANK_HISTORY_SHEET,
        rows=10000,
        cols=len(RANK_HEADERS),
    )

    ensure_headers(
        worksheet,
        RANK_HEADERS,
    )

    return worksheet


# =========================================================
# 5. 모니터링 키워드 읽기
# =========================================================

def load_monitor_keywords(
    spreadsheet,
) -> list[str]:
    try:
        worksheet = spreadsheet.worksheet(
            MONITOR_SHEET_NAME
        )

    except gspread.exceptions.WorksheetNotFound:
        print(
            f"⚠️ '{MONITOR_SHEET_NAME}' 시트가 없습니다."
        )

        return []

    values = worksheet.get_all_values()

    if not values:
        print(
            "⚠️ 모니터링 목록 시트가 비어 있습니다."
        )

        return []

    headers = [
        str(value).strip()
        for value in values[0]
    ]

    try:
        keyword_index = headers.index(
            "키워드"
        )

    except ValueError:
        print(
            "❌ 모니터링 목록에서 "
            "'키워드' 열을 찾지 못했습니다."
        )

        print(
            f"현재 헤더: {headers}"
        )

        return []

    keywords = []
    seen = set()

    for row in values[1:]:
        if keyword_index >= len(row):
            continue

        keyword = str(
            row[keyword_index]
        ).strip()

        if not keyword:
            continue

        normalized = re.sub(
            r"\s+",
            " ",
            keyword,
        ).strip()

        if normalized in seen:
            continue

        seen.add(normalized)
        keywords.append(normalized)

    return keywords


# =========================================================
# 6. 네이버 쇼핑 API
# =========================================================

def request_shop_page(
    keyword: str,
    start: int,
) -> tuple[list[dict[str, Any]], str | None]:
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET,
    }

    params = {
        "query": keyword,
        "display": 100,
        "start": start,
        "sort": "sim",
        # 중고·렌탈·해외직구 제외
        "exclude": "used:rental:cbshop",
    }

    try:
        response = HTTP_SESSION.get(
            NAVER_SHOP_URL,
            headers=headers,
            params=params,
            timeout=DEFAULT_TIMEOUT,
        )

    except requests.Timeout:
        return (
            [],
            "네이버 쇼핑 API 응답 시간 초과",
        )

    except requests.RequestException as exc:
        return (
            [],
            f"네이버 쇼핑 API 연결 오류: {exc}",
        )

    if response.status_code != 200:
        try:
            response_data = response.json()

            message = (
                response_data.get("errorMessage")
                or response_data.get("detail")
                or str(response_data)
            )

        except Exception:
            message = response.text[:300]

        return (
            [],
            f"HTTP {response.status_code}: {message}",
        )

    try:
        data = response.json()
        items = data.get("items", [])

        if not isinstance(items, list):
            return (
                [],
                "네이버 API items 형식 오류",
            )

        return items, None

    except Exception as exc:
        return (
            [],
            f"네이버 API 응답 해석 오류: {exc}",
        )


def parse_shop_item(
    raw_item: dict[str, Any],
    rank: int,
) -> dict[str, Any]:
    return {
        "순위": rank,
        "상품명": clean_naver_title(
            raw_item.get("title", "")
        ),
        "판매처": str(
            raw_item.get("mallName", "")
        ).strip(),
        "가격": safe_int(
            raw_item.get("lprice")
        ),
        "링크": safe_url(
            raw_item.get("link", "")
        ),
        "썸네일": safe_url(
            raw_item.get("image", "")
        ),
        "productType": safe_int(
            raw_item.get("productType")
        ),
        "productId": str(
            raw_item.get("productId", "")
        ).strip(),
        "브랜드": str(
            raw_item.get("brand", "")
        ).strip(),
        "제조사": str(
            raw_item.get("maker", "")
        ).strip(),
        "카테고리1": str(
            raw_item.get("category1", "")
        ).strip(),
        "카테고리2": str(
            raw_item.get("category2", "")
        ).strip(),
        "카테고리3": str(
            raw_item.get("category3", "")
        ).strip(),
        "카테고리4": str(
            raw_item.get("category4", "")
        ).strip(),
    }


def collect_keyword_rank(
    keyword: str,
    max_rank: int = 400,
) -> tuple[
    list[dict[str, Any]],
    list[str],
]:
    found_items = []
    errors = []

    max_rank = max(
        1,
        min(max_rank, 1000),
    )

    page_count = (
        max_rank + 99
    ) // 100

    for page_index in range(page_count):
        start = page_index * 100 + 1

        raw_items, error = request_shop_page(
            keyword,
            start,
        )

        if error:
            errors.append(
                f"{start}위 구간: {error}"
            )
            break

        if not raw_items:
            break

        for item_index, raw_item in enumerate(
            raw_items
        ):
            rank = start + item_index

            if rank > max_rank:
                break

            if not is_our_item(raw_item):
                continue

            found_items.append(
                parse_shop_item(
                    raw_item,
                    rank,
                )
            )

        time.sleep(0.1)

    return found_items, errors


# =========================================================
# 7. 통합 순위기록 저장
# =========================================================

def make_record_id(
    collected_at: str,
    keyword: str,
    item: dict[str, Any],
) -> str:
    product_identity = (
        item.get("productId")
        or normalize_store_name(
            item.get("상품명", "")
        )
    )

    return make_hash(
        collected_at,
        keyword,
        item.get("순위", ""),
        product_identity,
        item.get("판매처", ""),
    )


def item_to_sheet_row(
    collected_at: str,
    keyword: str,
    item: dict[str, Any],
) -> list[Any]:
    return [
        make_record_id(
            collected_at,
            keyword,
            item,
        ),
        collected_at,
        keyword,
        safe_int(item.get("순위")),
        item.get("상품명", ""),
        item.get("판매처", ""),
        safe_int(item.get("가격")),
        item.get("링크", ""),
        item.get("썸네일", ""),
        safe_int(item.get("productType")),
        item.get("productId", ""),
        item.get("브랜드", ""),
        item.get("제조사", ""),
        item.get("카테고리1", ""),
        item.get("카테고리2", ""),
        item.get("카테고리3", ""),
        item.get("카테고리4", ""),
    ]


def save_rank_items(
    rank_worksheet,
    collected_at: str,
    keyword: str,
    found_items: list[dict[str, Any]],
) -> int:
    rows = [
        item_to_sheet_row(
            collected_at,
            keyword,
            item,
        )
        for item in found_items
    ]

    append_raw_rows(
        rank_worksheet,
        rows,
    )

    return len(rows)


# =========================================================
# 8. 실행
# =========================================================

def main() -> int:
    started_at = now_kst()
    collected_at = started_at.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print("=" * 60)
    print("🎣 피싱템 자동 순위 수집")
    print(f"🚀 시작: {collected_at}")
    print(f"📊 저장 시트: {RANK_HISTORY_SHEET}")
    print("=" * 60)

    try:
        spreadsheet = get_spreadsheet()

    except Exception as exc:
        print(
            f"❌ 구글 시트 연결 실패: {exc}"
        )

        return 1

    try:
        rank_worksheet = (
            get_rank_history_worksheet(
                spreadsheet
            )
        )

    except Exception as exc:
        print(
            f"❌ 통합 순위기록 시트 준비 실패: {exc}"
        )

        return 1

    keywords = load_monitor_keywords(
        spreadsheet
    )

    if not keywords:
        print(
            "⚠️ 등록된 모니터링 키워드가 없습니다."
        )

        return 0

    print(
        f"📋 수집 대상 키워드: {len(keywords)}개"
    )

    total_saved = 0
    success_keywords = 0
    not_found_keywords = 0
    failed_keywords = 0
    summaries = []

    for keyword_index, keyword in enumerate(
        keywords,
        start=1,
    ):
        print()
        print(
            f"🔍 [{keyword_index}/{len(keywords)}] "
            f"{keyword}"
        )

        found_items, errors = (
            collect_keyword_rank(
                keyword,
                max_rank=400,
            )
        )

        if errors:
            for error in errors:
                print(f"  ⚠️ {error}")

        if found_items:
            try:
                saved_count = save_rank_items(
                    rank_worksheet,
                    collected_at,
                    keyword,
                    found_items,
                )

                best_rank = min(
                    item["순위"]
                    for item in found_items
                )

                catalog_count = sum(
                    1
                    for item in found_items
                    if safe_int(
                        item.get("productType")
                    )
                    in {
                        1,
                        4,
                        7,
                        10,
                    }
                )

                total_saved += saved_count
                success_keywords += 1

                message = (
                    f"✅ {saved_count}개 저장 "
                    f"(최고 {best_rank}위"
                )

                if catalog_count:
                    message += (
                        f", 가격비교 {catalog_count}개"
                    )

                message += ")"

                print(f"  {message}")

                summaries.append({
                    "키워드": keyword,
                    "상태": "성공",
                    "저장건수": saved_count,
                    "최고순위": best_rank,
                    "메모": (
                        f"가격비교 {catalog_count}개"
                    ),
                })

            except Exception as exc:
                failed_keywords += 1

                print(
                    f"  ❌ 구글 시트 저장 실패: {exc}"
                )

                summaries.append({
                    "키워드": keyword,
                    "상태": "저장 오류",
                    "저장건수": 0,
                    "최고순위": "",
                    "메모": str(exc),
                })

        else:
            if errors:
                failed_keywords += 1
                status = "API 오류"
            else:
                not_found_keywords += 1
                status = "400위 내 미노출"

            print(f"  ⚠️ {status}")

            summaries.append({
                "키워드": keyword,
                "상태": status,
                "저장건수": 0,
                "최고순위": "",
                "메모": " / ".join(errors),
            })

        # API 과호출 방지
        time.sleep(1.0)

    finished_at = now_kst()
    duration = (
        finished_at - started_at
    ).total_seconds()

    print()
    print("=" * 60)
    print("✅ 자동 순위 수집 완료")
    print(
        "🕐 완료: "
        + finished_at.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )
    print(f"⏱️ 소요시간: {duration:.1f}초")
    print(f"📊 총 저장건수: {total_saved}건")
    print(
        f"✅ 노출 키워드: {success_keywords}개"
    )
    print(
        f"⚠️ 미노출 키워드: {not_found_keywords}개"
    )
    print(
        f"❌ 오류 키워드: {failed_keywords}개"
    )
    print("=" * 60)

    print()
    print("📋 키워드별 결과")

    for summary in summaries:
        print(
            f"- {summary['키워드']}: "
            f"{summary['상태']} "
            f"/ 저장 {summary['저장건수']}건 "
            f"/ 최고순위 {summary['최고순위']} "
            f"/ {summary['메모']}"
        )

    # 일부 키워드 실패가 있어도 전체 자동화 자체는 완료 처리한다.
    # 구글 시트 연결 또는 헤더 오류는 앞에서 exit code 1로 종료한다.
    return 0


if __name__ == "__main__":
    sys.exit(main())
