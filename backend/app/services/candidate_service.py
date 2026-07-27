from __future__ import annotations

import math
import re
import time
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import get_settings
from app.services.keyword_service import (
    fetch_keyword_statistics,
    normalize_keyword,
    parse_volume,
)
from app.services.rank_service import (
    NaverShoppingError,
    clean_title,
    create_http_session,
    fetch_page,
    is_our_store,
    safe_integer,
)


EXCLUDED_CATEGORIES = {
    "패션의류",
    "패션잡화",
    "화장품/미용",
    "출산/육아",
    "식품",
    "디지털/가전",
}

PRODUCT_ID_COLUMNS = [
    "상품번호",
    "상품 번호",
    "상품ID",
    "스마트스토어 상품번호",
]
PRODUCT_NAME_COLUMNS = [
    "상품명",
    "상품 명",
    "제품명",
]
BRAND_COLUMNS = [
    "브랜드",
    "제조사",
    "제조 회사",
]

MAX_MASTER_SIZE = 20 * 1024 * 1024


class CandidateAnalysisError(Exception):
    pass


def find_column(
    columns: list[str],
    candidates: list[str],
) -> str | None:
    normalized = [
        str(column).strip()
        for column in columns
    ]

    for candidate in candidates:
        for column in normalized:
            if column == candidate:
                return column

    for candidate in candidates:
        for column in normalized:
            if candidate in column:
                return column

    return None


def clean_cell(value: Any) -> str:
    text = str(value or "").strip()

    if text.casefold() in {
        "nan",
        "none",
        "nat",
    }:
        return ""

    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]

    return text


def normalize_name(value: Any) -> str:
    return re.sub(
        r"[^0-9a-z가-힣]",
        "",
        clean_cell(value).casefold(),
    )


def normalize_brand(value: Any) -> str:
    return normalize_name(value)


def read_product_master(
    file_name: str,
    content: bytes,
) -> dict[str, Any]:
    if len(content) > MAX_MASTER_SIZE:
        raise CandidateAnalysisError(
            "상품 마스터 파일은 20MB 이하여야 합니다."
        )

    suffix = Path(file_name).suffix.casefold()

    if suffix not in {".xlsx", ".xls", ".csv"}:
        raise CandidateAnalysisError(
            "상품 마스터는 xlsx, xls 또는 csv 파일이어야 합니다."
        )

    try:
        if suffix == ".csv":
            frame = None
            last_encoding_error = None

            # 일반 UTF-8 CSV와 한글 Windows Excel CSV를 모두 지원합니다.
            for encoding in ("utf-8-sig", "cp949", "euc-kr"):
                try:
                    frame = pd.read_csv(
                        BytesIO(content),
                        dtype=str,
                        encoding=encoding,
                        keep_default_na=False,
                    ).fillna("")
                    break
                except UnicodeDecodeError as error:
                    last_encoding_error = error

            if frame is None:
                raise CandidateAnalysisError(
                    "CSV 파일의 문자 인코딩을 확인할 수 없습니다. "
                    "UTF-8 또는 CP949 형식으로 저장해 주세요."
                ) from last_encoding_error

        else:
            frame = pd.read_excel(
                BytesIO(content),
                dtype=str,
                engine=(
                    "openpyxl"
                    if suffix == ".xlsx"
                    else "xlrd"
                ),
            ).fillna("")

    except CandidateAnalysisError:
        raise
    except Exception as error:
        raise CandidateAnalysisError(
            f"상품 마스터를 읽지 못했습니다: {error}"
        ) from error

    if frame.empty:
        raise CandidateAnalysisError(
            "상품 마스터에 데이터가 없습니다."
        )

    frame.columns = [
        str(column).strip()
        for column in frame.columns
    ]
    columns = list(frame.columns)

    name_column = find_column(
        columns,
        PRODUCT_NAME_COLUMNS,
    )
    product_id_column = find_column(
        columns,
        PRODUCT_ID_COLUMNS,
    )
    brand_column = find_column(
        columns,
        BRAND_COLUMNS,
    )

    if not name_column:
        raise CandidateAnalysisError(
            "'상품명' 열을 찾지 못했습니다. 현재 열: "
            + ", ".join(columns)
        )

    product_ids: set[str] = set()
    normalized_names: set[str] = set()
    brands: set[str] = set()

    for record in frame.to_dict(orient="records"):
        product_name = clean_cell(
            record.get(name_column)
        )
        product_id = (
            clean_cell(
                record.get(product_id_column)
            )
            if product_id_column
            else ""
        )
        brand = (
            clean_cell(
                record.get(brand_column)
            )
            if brand_column
            else ""
        )

        if product_id:
            product_ids.add(product_id)

        normalized_product_name = normalize_name(
            product_name
        )

        if normalized_product_name:
            normalized_names.add(
                normalized_product_name
            )

        normalized_product_brand = normalize_brand(
            brand
        )

        if normalized_product_brand:
            brands.add(normalized_product_brand)

    return {
        "product_count": len(frame),
        "product_ids": product_ids,
        "normalized_names": normalized_names,
        "brands": brands,
        "product_id_column_found": bool(
            product_id_column
        ),
        "brand_column_found": bool(
            brand_column
        ),
    }


def get_exact_volume(keyword: str) -> int:
    rows = fetch_keyword_statistics(keyword)
    normalized = normalize_keyword(
        keyword
    ).casefold()

    selected: dict[str, Any] | None = None

    for row in rows:
        related = normalize_keyword(
            row.get("relKeyword")
        ).casefold()

        if related == normalized:
            selected = row
            break

    if selected is None and rows:
        selected = rows[0]

    if selected is None:
        return 0

    pc_volume, _ = parse_volume(
        selected.get("monthlyPcQcCnt")
    )
    mobile_volume, _ = parse_volume(
        selected.get("monthlyMobileQcCnt")
    )

    return pc_volume + mobile_volume


def tokenize_product(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(
            r"[0-9a-z가-힣]+",
            clean_cell(value).casefold(),
        )
        if len(token) >= 2
    }


def calculate_relevance_score(
    keyword: str,
    title: str,
    brand: str,
    maker: str,
) -> int:
    normalized_keyword = normalize_name(keyword)
    normalized_title = normalize_name(title)
    normalized_brand = normalize_name(brand)
    normalized_maker = normalize_name(maker)

    if not normalized_keyword:
        return 0

    if normalized_keyword in normalized_title:
        return 100

    if normalized_keyword in {
        normalized_brand,
        normalized_maker,
    }:
        return 95

    keyword_tokens = tokenize_product(keyword)
    searchable_tokens = tokenize_product(
        " ".join([
            title,
            brand,
            maker,
        ])
    )

    if not keyword_tokens:
        return 0

    matched = len(
        keyword_tokens & searchable_tokens
    )

    return round(
        matched / len(keyword_tokens) * 90
    )


def calculate_category_score(
    category: str,
) -> int:
    normalized = normalize_name(category)

    if "낚시" in normalized:
        return 100

    if (
        "스포츠레저" in normalized
        or "캠핑" in normalized
    ):
        return 65

    if normalized:
        return 25

    return 10


def calculate_price_stability(
    prices: list[int],
) -> int:
    valid_prices = [
        price
        for price in prices
        if price > 0
    ]

    if len(valid_prices) < 2:
        return 50

    average = sum(valid_prices) / len(valid_prices)

    if average <= 0:
        return 0

    variance = sum(
        (price - average) ** 2
        for price in valid_prices
    ) / len(valid_prices)
    coefficient = math.sqrt(variance) / average

    return max(
        0,
        min(
            100,
            round(100 - coefficient * 100),
        ),
    )


def calculate_candidate_score(
    search_volume: int,
    best_rank: int,
    observed_seller_count: int,
    relevance_score: int,
    category_score: int,
    price_stability_score: int,
) -> tuple[int, dict[str, int]]:
    demand_score = min(
        100,
        round(
            math.log10(
                max(search_volume, 0) + 1
            )
            / 5
            * 100
        ),
    )
    exposure_score = max(
        0,
        min(
            100,
            round((401 - best_rank) / 4),
        ),
    )
    seller_score = min(
        100,
        max(observed_seller_count, 1) * 20,
    )

    total = round(
        demand_score * 0.24
        + exposure_score * 0.21
        + relevance_score * 0.24
        + category_score * 0.13
        + seller_score * 0.10
        + price_stability_score * 0.08
    )

    return total, {
        "demand": demand_score,
        "exposure": exposure_score,
        "relevance": relevance_score,
        "category": category_score,
        "seller_diversity": seller_score,
        "price_stability": price_stability_score,
    }


def build_candidate_reasons(
    score_detail: dict[str, int],
    best_rank: int,
    seller_count: int,
) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []

    if score_detail["demand"] >= 60:
        reasons.append(
            "검색 수요가 충분한 키워드입니다."
        )

    if best_rank <= 20:
        reasons.append(
            "네이버 쇼핑 상위 20위 안에 노출됩니다."
        )
    elif best_rank <= 100:
        reasons.append(
            "네이버 쇼핑 상위 100위 안에 노출됩니다."
        )

    if score_detail["relevance"] >= 90:
        reasons.append(
            "검색어와 상품의 관련성이 높습니다."
        )

    if score_detail["category"] >= 100:
        reasons.append(
            "낚시 관련 카테고리와 일치합니다."
        )

    if seller_count >= 3:
        reasons.append(
            "여러 판매처에서 유통되는 상품입니다."
        )
    else:
        warnings.append(
            "관측된 판매처가 적어 공급 가능성을 "
            "별도로 확인해야 합니다."
        )

    if score_detail["price_stability"] < 50:
        warnings.append(
            "판매 가격 편차가 커서 원가와 마진을 "
            "확인해야 합니다."
        )

    if score_detail["relevance"] < 60:
        warnings.append(
            "검색어와의 관련성이 낮을 수 있습니다."
        )

    return reasons, warnings



def should_exclude_item(
    title: str,
    product_type: int,
    exclude_used: bool,
    exclude_rental: bool,
    exclude_overseas: bool,
) -> bool:
    normalized = normalize_name(title)

    if exclude_used and (
        product_type == 2
        or "중고" in normalized
    ):
        return True

    if exclude_rental and (
        "렌탈" in normalized
        or "대여" in normalized
    ):
        return True

    if exclude_overseas and (
        "해외직구" in normalized
        or "해외배송" in normalized
    ):
        return True

    return False


def analyze_candidates(
    master_file_name: str,
    master_content: bytes,
    keywords: list[str],
    max_results: int = 100,
    result_limit: int = 100,
    min_volume: int = 10,
    exclude_owned: bool = True,
    exclude_group: bool = False,
    exclude_used: bool = True,
    exclude_rental: bool = True,
    exclude_overseas: bool = True,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    settings = get_settings()

    if (
        not settings.naver_client_id
        or not settings.naver_client_secret
    ):
        raise CandidateAnalysisError(
            "네이버 쇼핑 API 설정이 필요합니다."
        )

    normalized_keywords = list(dict.fromkeys(
        keyword.strip()
        for keyword in keywords
        if keyword.strip()
    ))

    if not normalized_keywords:
        raise CandidateAnalysisError(
            "기준 검색어를 한 개 이상 입력해 주세요."
        )

    if len(normalized_keywords) > 40:
        raise CandidateAnalysisError(
            "기준 검색어는 최대 40개까지 가능합니다."
        )

    if max_results not in {
        100,
        200,
        300,
        400,
    }:
        raise CandidateAnalysisError(
            "검색어별 수집 수는 100·200·300·400 중 "
            "하나여야 합니다."
        )

    if result_limit < 10 or result_limit > 500:
        raise CandidateAnalysisError(
            "최종 후보 수는 10~500 사이여야 합니다."
        )

    coverage = read_product_master(
        master_file_name,
        master_content,
    )

    candidates: dict[
        str,
        dict[str, Any],
    ] = {}
    errors: list[dict[str, str]] = []

    for keyword in normalized_keywords:
        try:
            search_volume = get_exact_volume(
                keyword
            )

            if search_volume < min_volume:
                continue

            starts = list(
                range(1, max_results + 1, 100)
            )

            exclude_options: list[str] = []

            if exclude_used:
                exclude_options.append("used")

            if exclude_rental:
                exclude_options.append("rental")

            if exclude_overseas:
                exclude_options.append("cbshop")

            exclude = ":".join(exclude_options)
            pages: list[
                tuple[int, list[dict[str, Any]], int]
            ] = []
            session = create_http_session()

            try:
                for start in starts:
                    items, page_total, page_error = (
                        fetch_page(
                            session=session,
                            keyword=keyword,
                            start=start,
                            client_id=(
                                settings.naver_client_id
                            ),
                            client_secret=(
                                settings.naver_client_secret
                            ),
                            exclude=exclude,
                        )
                    )

                    if page_error:
                        raise NaverShoppingError(
                            f"{start}위 구간: {page_error}"
                        )

                    pages.append((
                        start,
                        items,
                        page_total,
                    ))

                    if not items:
                        break

                    time.sleep(0.08)
            finally:
                session.close()

            pages.sort(key=lambda page: page[0])

            for start, items, _ in pages:
                for index, item in enumerate(items):
                    title = clean_title(
                        item.get("title")
                    )
                    mall_name = clean_cell(
                        item.get("mallName")
                    )
                    product_id = clean_cell(
                        item.get("productId")
                    )
                    brand = clean_cell(
                        item.get("brand")
                    )
                    maker = clean_cell(
                        item.get("maker")
                    )
                    product_type = safe_integer(
                        item.get("productType")
                    )
                    category1 = clean_cell(
                        item.get("category1")
                    )

                    if is_our_store(mall_name):
                        continue

                    if category1 in EXCLUDED_CATEGORIES:
                        continue

                    if should_exclude_item(
                        title,
                        product_type,
                        exclude_used,
                        exclude_rental,
                        exclude_overseas,
                    ):
                        continue

                    normalized_title = normalize_name(
                        title
                    )
                    normalized_item_brand = (
                        normalize_brand(
                            brand or maker
                        )
                    )

                    same_product = (
                        bool(product_id)
                        and product_id
                        in coverage["product_ids"]
                    ) or (
                        bool(normalized_title)
                        and normalized_title
                        in coverage[
                            "normalized_names"
                        ]
                    )

                    group_owned = (
                        bool(normalized_item_brand)
                        and normalized_item_brand
                        in coverage["brands"]
                    )

                    if exclude_owned and same_product:
                        continue

                    if exclude_group and group_owned:
                        continue

                    candidate_key = (
                        normalized_title
                        + ":"
                        + normalized_item_brand
                        if normalized_title
                        else product_id
                    )

                    if not candidate_key:
                        continue

                    rank = start + index
                    price = safe_integer(
                        item.get("lprice")
                    )

                    if candidate_key not in candidates:
                        candidates[candidate_key] = {
                            "product_id": product_id,
                            "product_name": title,
                            "brand": brand,
                            "maker": maker,
                            "representative_seller": (
                                mall_name
                            ),
                            "best_rank": rank,
                            "representative_price": (
                                price
                            ),
                            "category": " > ".join(
                                filter(
                                    None,
                                    [
                                        clean_cell(
                                            item.get(
                                                f"category{number}"
                                            )
                                        )
                                        for number in range(
                                            1,
                                            5,
                                        )
                                    ],
                                )
                            ),
                            "link": clean_cell(
                                item.get("link")
                            ),
                            "image": clean_cell(
                                item.get("image")
                            ),
                            "search_volume": (
                                search_volume
                            ),
                            "volume_keyword": keyword,
                            "same_product_owned": (
                                same_product
                            ),
                            "product_group_owned": (
                                group_owned
                            ),
                            "keywords": {keyword},
                            "sellers": (
                                {mall_name}
                                if mall_name
                                else set()
                            ),
                            "prices": (
                                [price]
                                if price > 0
                                else []
                            ),
                        }
                    else:
                        candidate = candidates[
                            candidate_key
                        ]
                        candidate["keywords"].add(
                            keyword
                        )

                        if mall_name:
                            candidate["sellers"].add(
                                mall_name
                            )

                        if price > 0:
                            candidate["prices"].append(
                                price
                            )

                        if search_volume > candidate[
                            "search_volume"
                        ]:
                            candidate[
                                "search_volume"
                            ] = search_volume
                            candidate[
                                "volume_keyword"
                            ] = keyword

                        if rank < candidate["best_rank"]:
                            candidate["best_rank"] = rank
                            candidate[
                                "representative_seller"
                            ] = mall_name
                            candidate[
                                "representative_price"
                            ] = price
                            candidate["link"] = clean_cell(
                                item.get("link")
                            )
                            candidate["image"] = clean_cell(
                                item.get("image")
                            )

        except Exception as error:
            errors.append({
                "keyword": keyword,
                "message": str(error),
            })

    results: list[dict[str, Any]] = []

    for candidate in candidates.values():
        prices = candidate.pop("prices")
        sellers = candidate.pop("sellers")
        keyword_set = candidate.pop(
            "keywords"
        )

        seller_count = len(sellers)

        candidate["keywords"] = sorted(
            keyword_set
        )
        candidate["observed_seller_count"] = (
            seller_count
        )
        candidate["lowest_price"] = (
            min(prices)
            if prices
            else 0
        )
        candidate["highest_price"] = (
            max(prices)
            if prices
            else 0
        )
        candidate["average_price"] = (
            int(sum(prices) / len(prices))
            if prices
            else 0
        )
        relevance_score = (
            calculate_relevance_score(
                candidate["volume_keyword"],
                candidate["product_name"],
                candidate["brand"],
                candidate["maker"],
            )
        )
        category_score = (
            calculate_category_score(
                candidate["category"]
            )
        )
        price_stability_score = (
            calculate_price_stability(
                prices
            )
        )

        # 네이버 검색 결과에 포함됐더라도 검색어와 상품이
        # 거의 관련 없으면 사입 후보에서 제외합니다.
        if relevance_score < 25:
            continue

        potential_score, score_detail = (
            calculate_candidate_score(
                candidate["search_volume"],
                candidate["best_rank"],
                seller_count,
                relevance_score,
                category_score,
                price_stability_score,
            )
        )
        reasons, warnings = (
            build_candidate_reasons(
                score_detail,
                candidate["best_rank"],
                seller_count,
            )
        )

        candidate["potential_score"] = (
            potential_score
        )
        candidate["score_detail"] = score_detail
        candidate["recommendation_reasons"] = (
            reasons
        )
        candidate["warnings"] = warnings
        candidate["recommendation_grade"] = (
            "매우 높음"
            if potential_score >= 80
            else "높음"
            if potential_score >= 65
            else "보통"
            if potential_score >= 50
            else "검토 필요"
        )
        results.append(candidate)

    results.sort(
        key=lambda row: (
            row["same_product_owned"],
            row["product_group_owned"],
            -row["potential_score"],
            row["best_rank"],
        )
    )

    results = results[:result_limit]

    return {
        "summary": {
            "keyword_count": len(
                normalized_keywords
            ),
            "master_product_count": coverage[
                "product_count"
            ],
            "candidate_count": len(results),
            "error_count": len(errors),
            "max_results": max_results,
            "result_limit": result_limit,
            "min_volume": min_volume,
        },
        "keywords": normalized_keywords,
        "results": results,
        "errors": errors,
        "elapsed_seconds": round(
            time.perf_counter() - started_at,
            3,
        ),
    }
