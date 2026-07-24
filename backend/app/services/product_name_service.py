from __future__ import annotations

import html
import json
import re
from collections import Counter
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from app.services.keyword_service import (
    KeywordAnalysisError,
    analyze_keywords,
    fetch_keyword_statistics,
    parse_volume,
)
from app.services.rank_service import (
    NaverShoppingError,
    search_our_store_ranks,
)


ALLOWED_NAVER_HOSTS = {
    "naver.com",
    "naver.me",
}
MAX_PAGE_BYTES = 2_000_000
MAX_RECOMMENDED_LENGTH = 50

PROMOTION_WORDS = {
    "무료배송",
    "당일배송",
    "초특가",
    "최저가",
    "세일",
    "할인",
    "쿠폰",
    "사은품",
    "적립",
}

CLAIM_WORDS = {
    "최고",
    "최고급",
    "최상급",
    "1위",
    "국민",
    "완벽한",
    "무조건",
}


class ProductNameRecommendationError(Exception):
    pass


class ProductPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.og_title = ""
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ):
        attributes = {
            key.lower(): value or ""
            for key, value in attrs
        }

        if tag.lower() == "meta":
            property_name = (
                attributes.get("property")
                or attributes.get("name")
                or ""
            ).lower()

            if property_name in {
                "og:title",
                "twitter:title",
            }:
                self.og_title = (
                    attributes.get("content") or ""
                ).strip()

        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str):
        if self.in_title:
            self.title_parts.append(data)


def normalize_text(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        html.unescape(str(value or "")),
    ).strip()


def normalize_key(value: Any) -> str:
    return re.sub(
        r"[^0-9a-zA-Z가-힣]",
        "",
        str(value or ""),
    ).casefold()


def clean_product_title(value: Any) -> str:
    title = normalize_text(value)
    title = re.sub(
        r"\s*[:|\-]\s*(네이버\s*(쇼핑|스마트스토어)?).*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return title.strip(" |-")


def is_allowed_naver_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    hostname = (parsed.hostname or "").lower()

    return any(
        hostname == root
        or hostname.endswith("." + root)
        for root in ALLOWED_NAVER_HOSTS
    )


def extract_product_id(value: str) -> str:
    patterns = (
        r"/products/(\d+)",
        r"[?&](?:nvMid|productId)=(\d+)",
        r"/catalog/(\d+)",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            value,
            flags=re.IGNORECASE,
        )

        if match:
            return match.group(1)

    return ""


def fetch_public_product_title(
    product_url: str,
) -> tuple[str, str]:
    if not is_allowed_naver_url(product_url):
        raise ProductNameRecommendationError(
            "네이버 상품 링크만 입력할 수 있습니다."
        )

    current_url = product_url
    session = requests.Session()

    for _ in range(4):
        if not is_allowed_naver_url(current_url):
            raise ProductNameRecommendationError(
                "허용되지 않은 주소로 이동했습니다."
            )

        try:
            response = session.get(
                current_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(compatible; FishingtemSeo/1.0)"
                    ),
                    "Accept": "text/html",
                },
                timeout=(5, 20),
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException as error:
            return "", (
                "상품 페이지에 연결하지 못했습니다. "
                "현재 상품명을 직접 입력해 주세요."
            )

        if response.status_code in {
            301,
            302,
            303,
            307,
            308,
        }:
            location = response.headers.get(
                "location",
                "",
            )
            response.close()

            if not location:
                break

            current_url = urljoin(
                current_url,
                location,
            )
            continue

        if response.status_code != 200:
            response.close()
            return "", (
                "상품정보를 자동으로 불러오지 못했습니다. "
                "현재 상품명을 직접 입력해 주세요."
            )

        chunks: list[bytes] = []
        downloaded = 0

        try:
            for chunk in response.iter_content(
                chunk_size=65536,
            ):
                if not chunk:
                    continue

                downloaded += len(chunk)

                if downloaded > MAX_PAGE_BYTES:
                    break

                chunks.append(chunk)
        finally:
            response.close()

        encoding = (
            response.encoding
            or response.apparent_encoding
            or "utf-8"
        )
        page_text = b"".join(chunks).decode(
            encoding,
            errors="replace",
        )

        parser = ProductPageParser()
        parser.feed(page_text)

        title = clean_product_title(
            parser.og_title
            or " ".join(parser.title_parts)
        )

        if not title:
            match = re.search(
                r'"productName"\s*:\s*"((?:\\.|[^"])*)"',
                page_text,
            )

            if match:
                try:
                    title = clean_product_title(
                        json.loads(
                            f'"{match.group(1)}"'
                        )
                    )
                except Exception:
                    title = clean_product_title(
                        match.group(1)
                    )

        if title:
            return title, ""

        return "", (
            "상품명은 자동 확인하지 못했습니다. "
            "현재 상품명을 직접 입력해 주세요."
        )

    return "", (
        "상품 링크 이동을 완료하지 못했습니다. "
        "현재 상품명을 직접 입력해 주세요."
    )


def suggest_main_keyword(title: str) -> str:
    if not title:
        return ""

    try:
        statistics = fetch_keyword_statistics(
            title
        )
    except KeywordAnalysisError:
        return ""

    normalized_title = normalize_key(title)
    candidates: list[tuple[int, int, str]] = []

    for item in statistics:
        keyword = normalize_text(
            item.get("relKeyword")
        )
        keyword_key = normalize_key(keyword)

        if (
            len(keyword_key) < 2
            or len(keyword_key) > 20
        ):
            continue

        pc_volume, _ = parse_volume(
            item.get("monthlyPcQcCnt")
        )
        mobile_volume, _ = parse_volume(
            item.get("monthlyMobileQcCnt")
        )
        total_volume = pc_volume + mobile_volume

        related = (
            keyword_key in normalized_title
            or normalized_title in keyword_key
        )

        candidates.append((
            1 if related else 0,
            total_volume,
            keyword,
        ))

    if not candidates:
        return ""

    candidates.sort(
        key=lambda row: (
            -row[0],
            -row[1],
            len(row[2]),
        )
    )
    return candidates[0][2]


def resolve_existing_product(
    product_url: str,
) -> dict[str, Any]:
    product_url = product_url.strip()

    if not product_url:
        raise ProductNameRecommendationError(
            "네이버 상품 링크를 입력해 주세요."
        )

    title, message = fetch_public_product_title(
        product_url
    )

    return {
        "resolved": bool(title),
        "product_url": product_url,
        "product_id": extract_product_id(
            product_url
        ),
        "current_title": title,
        "suggested_main_keyword": (
            suggest_main_keyword(title)
            if title
            else ""
        ),
        "message": (
            "상품정보를 불러왔습니다."
            if title
            else message
        ),
    }


def split_features(
    values: list[str],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for raw_value in values:
        for value in re.split(
            r"[,/\n]+",
            str(raw_value or ""),
        ):
            cleaned = normalize_text(value)
            key = normalize_key(cleaned)

            if (
                not cleaned
                or not key
                or key in seen
            ):
                continue

            seen.add(key)
            result.append(cleaned)

    return result[:12]


def policy_warnings(title: str) -> list[str]:
    warnings: list[str] = []

    for word in sorted(PROMOTION_WORDS):
        if word in title:
            warnings.append(
                f"판매조건·프로모션 표현 ‘{word}’ 제외 권장"
            )

    for word in sorted(CLAIM_WORDS):
        if word in title:
            warnings.append(
                f"객관적 근거가 필요한 표현 ‘{word}’ 확인 필요"
            )

    if re.search(r"[!★☆♥♡]{2,}", title):
        warnings.append(
            "과도하게 반복된 특수문자 제외 권장"
        )

    tokens = [
        normalize_key(token)
        for token in title.split()
        if normalize_key(token)
    ]
    duplicated = [
        token
        for token, count in Counter(tokens).items()
        if count > 1
    ]

    if duplicated:
        warnings.append(
            "동일·유사 키워드 반복 확인 필요"
        )

    if len(title) > 100:
        warnings.append(
            "상품명이 100자를 초과합니다."
        )
    elif len(title) > MAX_RECOMMENDED_LENGTH:
        warnings.append(
            "가독성을 위해 약 50자 이내 사용을 권장합니다."
        )

    return warnings


def build_title(
    components: list[str],
    max_length: int = MAX_RECOMMENDED_LENGTH,
) -> str:
    result: list[str] = []
    current_key = ""

    for component in components:
        value = normalize_text(component)
        key = normalize_key(value)

        if not value or not key:
            continue

        if key in current_key:
            continue

        candidate = " ".join(
            [*result, value]
        ).strip()

        if len(candidate) > max_length:
            continue

        result.append(value)
        current_key = normalize_key(
            " ".join(result)
        )

    return " ".join(result)


def candidate_score(
    title: str,
    main_keyword: str,
    brand: str,
    features: list[str],
) -> int:
    title_key = normalize_key(title)
    score = 45

    if normalize_key(main_keyword) in title_key:
        score += 25

    if brand and normalize_key(brand) in title_key:
        score += 5

    matched_features = sum(
        1
        for feature in features
        if normalize_key(feature) in title_key
    )
    score += min(matched_features * 4, 12)

    if 15 <= len(title) <= 50:
        score += 8

    score += max(
        0,
        5 - len(policy_warnings(title)) * 3,
    )

    return min(max(score, 0), 100)


def compare_titles(
    current_title: str,
    recommended_title: str,
) -> dict[str, list[str]]:
    current_tokens = current_title.split()
    recommended_tokens = (
        recommended_title.split()
    )

    current_keys = {
        normalize_key(token)
        for token in current_tokens
    }
    recommended_keys = {
        normalize_key(token)
        for token in recommended_tokens
    }

    return {
        "kept": [
            token
            for token in recommended_tokens
            if normalize_key(token)
            in current_keys
        ],
        "added": [
            token
            for token in recommended_tokens
            if normalize_key(token)
            not in current_keys
        ],
        "removed": [
            token
            for token in current_tokens
            if normalize_key(token)
            not in recommended_keys
        ],
    }


def recommend_product_names(
    *,
    mode: str,
    main_keyword: str,
    product_type: str = "",
    brand: str = "피싱템",
    model_name: str = "",
    features: list[str] | None = None,
    required_words: list[str] | None = None,
    excluded_words: list[str] | None = None,
    current_title: str = "",
    product_url: str = "",
) -> dict[str, Any]:
    if mode not in {"new", "existing"}:
        raise ProductNameRecommendationError(
            "작업 방식을 확인해 주세요."
        )

    current_title = clean_product_title(
        current_title
    )
    product_url = product_url.strip()

    if (
        mode == "existing"
        and product_url
        and not current_title
    ):
        resolved = resolve_existing_product(
            product_url
        )
        current_title = resolved[
            "current_title"
        ]

        if not main_keyword:
            main_keyword = resolved[
                "suggested_main_keyword"
            ]

    main_keyword = normalize_text(main_keyword)
    product_type = normalize_text(product_type)
    brand = normalize_text(brand) or "피싱템"
    model_name = normalize_text(model_name)

    if not main_keyword:
        raise ProductNameRecommendationError(
            "메인 키워드를 입력해 주세요."
        )

    if (
        mode == "new"
        and not product_type
    ):
        product_type = main_keyword

    feature_values = split_features(
        features or []
    )
    required_values = split_features(
        required_words or []
    )
    excluded_keys = {
        normalize_key(value)
        for value in split_features(
            excluded_words or []
        )
    }

    started_warnings: list[str] = []

    try:
        keyword_result = analyze_keywords(
            main_keyword,
            related_limit=20,
        )
    except KeywordAnalysisError as error:
        raise ProductNameRecommendationError(
            str(error)
        ) from error

    try:
        rank_result = search_our_store_ranks(
            keyword=main_keyword,
            limit=100,
            include_special_products=False,
        )
        market_top10 = rank_result.get(
            "market_top10",
            [],
        )
    except NaverShoppingError as error:
        market_top10 = []
        started_warnings.append(str(error))

    related_rows = sorted(
        keyword_result.get("keywords", []),
        key=lambda row: int(
            row.get("total_volume") or 0
        ),
        reverse=True,
    )

    main_key = normalize_key(main_keyword)
    related_keywords: list[str] = []

    for row in related_rows:
        keyword = normalize_text(
            row.get("keyword")
        )
        key = normalize_key(keyword)

        if (
            not key
            or key == main_key
            or key in excluded_keys
        ):
            continue

        if (
            main_key in key
            or key in main_key
        ):
            related_keywords.append(keyword)

        if len(related_keywords) >= 3:
            break

    concise_components = [
        brand,
        product_type or main_keyword,
        *feature_values[:2],
        model_name,
        *required_values,
    ]
    balanced_components = [
        brand,
        product_type or main_keyword,
        *feature_values[:4],
        *related_keywords[:1],
        model_name,
        *required_values,
    ]
    expanded_components = [
        brand,
        product_type or main_keyword,
        *feature_values[:6],
        *related_keywords[:2],
        model_name,
        *required_values,
    ]

    raw_candidates = [
        (
            "간결형",
            "핵심 상품정보를 짧고 명확하게 구성했습니다.",
            concise_components,
        ),
        (
            "균형형",
            "검색 키워드와 제품 특징을 균형 있게 구성했습니다.",
            balanced_components,
        ),
        (
            "확장형",
            "관련 검색어와 제품 특징을 넓게 반영했습니다.",
            expanded_components,
        ),
    ]

    candidates: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for style, reason, components in raw_candidates:
        title = build_title(components)

        if not title:
            continue

        if title in seen_titles:
            title = build_title(
                [
                    *components,
                    *related_keywords,
                ],
                max_length=55,
            )

        if title in seen_titles:
            continue

        seen_titles.add(title)

        used_keywords = [
            keyword
            for keyword in [
                main_keyword,
                *feature_values,
                *related_keywords,
                *required_values,
            ]
            if (
                normalize_key(keyword)
                in normalize_key(title)
            )
        ]

        candidates.append({
            "style": style,
            "title": title,
            "score": candidate_score(
                title,
                main_keyword,
                brand,
                feature_values,
            ),
            "length": len(title),
            "reason": reason,
            "used_keywords": list(
                dict.fromkeys(
                    used_keywords
                )
            ),
            "warnings": policy_warnings(
                title
            ),
            "changes": compare_titles(
                current_title,
                title,
            ) if current_title else {
                "kept": [],
                "added": [],
                "removed": [],
            },
        })

    candidates.sort(
        key=lambda item: (
            0 if item["style"] == "균형형" else 1,
            -item["score"],
        )
    )

    keyword_suggestions = [
        {
            "keyword": row.get(
                "keyword",
                "",
            ),
            "total_volume": int(
                row.get(
                    "total_volume",
                    0,
                )
            ),
            "competition": row.get(
                "competition",
                "",
            ),
            "representative_category": (
                row.get(
                    "representative_category",
                    "",
                )
            ),
        }
        for row in related_rows[:10]
    ]

    competitor_titles = [
        {
            "rank": item.get("rank"),
            "title": item.get("title", ""),
            "mall_name": item.get(
                "mall_name",
                "",
            ),
        }
        for item in market_top10
    ]

    return {
        "mode": mode,
        "main_keyword": main_keyword,
        "product_type": product_type,
        "brand": brand,
        "model_name": model_name,
        "current_title": current_title,
        "product_url": product_url,
        "representative_category": (
            keyword_result.get(
                "summary",
                {},
            ).get(
                "representative_category",
                "",
            )
        ),
        "current_title_warnings": (
            policy_warnings(current_title)
            if current_title
            else []
        ),
        "keyword_suggestions": (
            keyword_suggestions
        ),
        "competitor_titles": competitor_titles,
        "candidates": candidates,
        "warnings": started_warnings,
    }
