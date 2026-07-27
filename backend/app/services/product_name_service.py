from __future__ import annotations

import html
import re
from collections import Counter
from typing import Any


from app.services.keyword_service import (
    KeywordAnalysisError,
    analyze_keywords,
)
from app.services.rank_service import (
    NaverShoppingError,
    search_our_store_ranks,
)


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


def contains_excluded(
    value: str,
    excluded_keys: set[str],
) -> bool:
    value_key = normalize_key(value)

    return any(
        excluded_key
        and (
            excluded_key in value_key
            or value_key in excluded_key
        )
        for excluded_key in excluded_keys
    )


def extract_competitor_terms(
    market_top10: list[dict[str, Any]],
    known_terms: list[str],
    brand: str,
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    display_names: dict[str, str] = {}

    blocked_keys = {
        normalize_key(word)
        for word in (
            PROMOTION_WORDS
            | CLAIM_WORDS
            | {
                "네이버",
                "스마트스토어",
                "공식",
                "정품",
                "국내",
                "상품",
                "제품",
            }
        )
    }

    entity_keys = {
        normalize_key(value)
        for item in market_top10
        for value in (
            item.get("mall_name", ""),
            item.get("brand", ""),
            item.get("maker", ""),
        )
        if normalize_key(value)
    }
    entity_keys.add(normalize_key(brand))

    cleaned_known_terms = [
        normalize_text(term)
        for term in known_terms
        if 2 <= len(normalize_key(term)) <= 20
    ]

    for item in market_top10:
        title = clean_product_title(
            item.get("title", "")
        )
        title_key = normalize_key(title)
        found: dict[str, str] = {}

        for term in cleaned_known_terms:
            key = normalize_key(term)

            if key and key in title_key:
                found[key] = term

        for token in re.findall(
            r"[0-9A-Za-z가-힣]+",
            title,
        ):
            token = normalize_text(token)
            key = normalize_key(token)

            if (
                len(key) < 2
                or len(key) > 20
                or key.isdigit()
                or key in blocked_keys
            ):
                continue

            if any(
                key == entity_key
                or key in entity_key
                for entity_key in entity_keys
            ):
                continue

            found.setdefault(key, token)

        for key, term in found.items():
            counts[key] += 1
            display_names.setdefault(key, term)

    terms: list[dict[str, Any]] = []

    for key, product_count in counts.items():
        if product_count < 2:
            continue

        if product_count >= 6:
            recommendation = "적극 추천"
        elif product_count >= 4:
            recommendation = "추천"
        else:
            recommendation = "참고"

        terms.append({
            "term": display_names[key],
            "product_count": product_count,
            "frequency": round(
                product_count
                / max(len(market_top10), 1)
                * 100,
                1,
            ),
            "recommendation": recommendation,
        })

    terms.sort(
        key=lambda item: (
            -item["product_count"],
            len(item["term"]),
            item["term"],
        )
    )
    return terms[:15]


def score_candidate(
    *,
    title: str,
    main_keyword: str,
    product_type: str,
    brand: str,
    features: list[str],
    required_words: list[str],
    keyword_rows: list[dict[str, Any]],
    competitor_terms: list[dict[str, Any]],
    representative_category: str,
) -> tuple[int, dict[str, int]]:
    title_key = normalize_key(title)
    main_key = normalize_key(main_keyword)
    product_key = normalize_key(product_type)
    brand_key = normalize_key(brand)

    main_position = title_key.find(main_key)

    if main_position < 0:
        main_score = 0
    elif main_position <= len(brand_key) + 4:
        main_score = 25
    else:
        main_score = 21

    relevance_score = 0

    if product_key and product_key in title_key:
        relevance_score += 8
    elif main_key in title_key:
        relevance_score += 5

    matched_features = sum(
        1
        for feature in features
        if normalize_key(feature) in title_key
    )
    relevance_score += min(
        matched_features * 2,
        8,
    )

    matched_required = sum(
        1
        for word in required_words
        if normalize_key(word) in title_key
    )

    if required_words:
        relevance_score += round(
            4
            * matched_required
            / len(required_words)
        )
    else:
        relevance_score += 4

    relevance_score = min(relevance_score, 20)

    volume_map = {
        normalize_key(row.get("keyword", "")): int(
            row.get("total_volume") or 0
        )
        for row in keyword_rows
    }
    max_volume = max(
        volume_map.values(),
        default=0,
    )

    demand_score = (
        8 if main_key in title_key else 0
    )
    used_related_volume = max(
        (
            volume
            for key, volume in volume_map.items()
            if (
                key
                and key != main_key
                and key in title_key
            )
        ),
        default=0,
    )

    if max_volume > 0:
        demand_score += round(
            7
            * used_related_volume
            / max_volume
        )

    demand_score = min(demand_score, 15)

    matched_market_counts = [
        int(item["product_count"])
        for item in competitor_terms
        if normalize_key(item["term"]) in title_key
    ]
    market_denominator = sum(
        int(item["product_count"])
        for item in competitor_terms[:3]
    )

    if matched_market_counts and market_denominator:
        competitor_score = min(
            15,
            round(
                15
                * sum(matched_market_counts)
                / market_denominator
            ),
        )
    else:
        competitor_score = 0

    category_score = 0

    if representative_category:
        category_score += 8

    if product_key and (
        product_key in title_key
        or main_key in title_key
    ):
        category_score += 2

    tokens = [
        normalize_key(token)
        for token in title.split()
        if normalize_key(token)
    ]
    duplicate_count = sum(
        count - 1
        for count in Counter(tokens).values()
        if count > 1
    )

    if 15 <= len(title) <= 50:
        readability_score = 10
    elif 10 <= len(title) <= 60:
        readability_score = 7
    elif len(title) <= 100:
        readability_score = 4
    else:
        readability_score = 0

    readability_score = max(
        0,
        readability_score - duplicate_count * 2,
    )

    policy_issue_count = sum(
        1
        for word in PROMOTION_WORDS | CLAIM_WORDS
        if word in title
    )

    if re.search(r"[!★☆♥♡]{2,}", title):
        policy_issue_count += 1

    policy_score = max(
        0,
        5 - policy_issue_count * 2,
    )

    breakdown = {
        "main_keyword": main_score,
        "product_relevance": relevance_score,
        "search_demand": demand_score,
        "competitor_usage": competitor_score,
        "category_fit": min(category_score, 10),
        "readability": readability_score,
        "policy_compliance": policy_score,
    }

    return sum(breakdown.values()), breakdown


def diagnose_current_title(
    *,
    current_title: str,
    main_keyword: str,
    brand: str,
    features: list[str],
    excluded_keys: set[str],
    competitor_terms: list[dict[str, Any]],
) -> dict[str, list[str]]:
    if not current_title:
        return {
            "keep": [],
            "remove": [],
            "consider": [],
        }

    tokens = [
        token
        for token in current_title.split()
        if normalize_key(token)
    ]
    token_counts = Counter(
        normalize_key(token)
        for token in tokens
    )

    important_keys = {
        normalize_key(value)
        for value in [
            main_keyword,
            brand,
            *features,
        ]
        if normalize_key(value)
    }

    keep: list[str] = []
    remove: list[str] = []

    for token in tokens:
        key = normalize_key(token)

        should_remove = (
            contains_excluded(token, excluded_keys)
            or any(
                word in token
                for word in (
                    PROMOTION_WORDS
                    | CLAIM_WORDS
                )
            )
            or token_counts[key] > 1
        )

        if should_remove:
            if token not in remove:
                remove.append(token)
            continue

        if any(
            key in important_key
            or important_key in key
            for important_key in important_keys
        ):
            if token not in keep:
                keep.append(token)

    current_key = normalize_key(current_title)
    consider = [
        item["term"]
        for item in competitor_terms
        if (
            normalize_key(item["term"])
            not in current_key
            and not contains_excluded(
                item["term"],
                excluded_keys,
            )
        )
    ][:5]

    return {
        "keep": keep,
        "remove": remove,
        "consider": consider,
    }

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


    main_keyword = normalize_text(main_keyword)
    product_type = normalize_text(product_type)
    brand = normalize_text(brand) or "피싱템"
    model_name = normalize_text(model_name)

    if not main_keyword:
        raise ProductNameRecommendationError(
            "메인 키워드를 입력해 주세요."
        )

    if mode == "new" and not product_type:
        product_type = main_keyword

    feature_values = split_features(
        features or []
    )
    required_values = split_features(
        required_words or []
    )
    excluded_values = split_features(
        excluded_words or []
    )
    excluded_keys = {
        normalize_key(value)
        for value in excluded_values
        if normalize_key(value)
    }

    main_key = normalize_key(main_keyword)

    if contains_excluded(
        main_keyword,
        excluded_keys,
    ):
        raise ProductNameRecommendationError(
            "메인 키워드와 제외 단어가 충돌합니다."
        )

    conflicting_required = [
        word
        for word in required_values
        if contains_excluded(
            word,
            excluded_keys,
        )
    ]

    if conflicting_required:
        raise ProductNameRecommendationError(
            "필수 단어와 제외 단어가 충돌합니다: "
            + ", ".join(conflicting_required)
        )

    def allowed(value: str) -> bool:
        return (
            bool(normalize_key(value))
            and not contains_excluded(
                value,
                excluded_keys,
            )
        )

    product_type = (
        product_type
        if allowed(product_type)
        else main_keyword
    )
    brand = brand if allowed(brand) else ""
    model_name = (
        model_name
        if allowed(model_name)
        else ""
    )
    feature_values = [
        value
        for value in feature_values
        if allowed(value)
    ]

    warnings: list[str] = []

    try:
        keyword_result = analyze_keywords(
            main_keyword,
            related_limit=50,
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
        warnings.append(str(error))

    related_rows = sorted(
        keyword_result.get("keywords", []),
        key=lambda row: int(
            row.get("total_volume") or 0
        ),
        reverse=True,
    )
    representative_category = (
        keyword_result.get("summary", {}).get(
            "representative_category",
            "",
        )
    )

    related_keywords: list[str] = []
    related_seen: set[str] = set()

    for row in related_rows:
        keyword = normalize_text(
            row.get("keyword")
        )
        key = normalize_key(keyword)
        category = normalize_text(
            row.get("representative_category")
        )

        if (
            not key
            or key == main_key
            or key in related_seen
            or not allowed(keyword)
        ):
            continue

        directly_related = (
            main_key in key
            or key in main_key
        )
        same_category = (
            representative_category
            and category
            and category == representative_category
        )

        if directly_related or same_category:
            related_keywords.append(keyword)
            related_seen.add(key)

        if len(related_keywords) >= 8:
            break

    competitor_terms = [
        item
        for item in extract_competitor_terms(
            market_top10=market_top10,
            known_terms=[
                main_keyword,
                product_type,
                *feature_values,
                *required_values,
                *related_keywords,
            ],
            brand=brand,
        )
        if allowed(item["term"])
    ]

    market_terms: list[str] = []

    for item in competitor_terms:
        term = item["term"]
        key = normalize_key(term)

        if (
            not allowed(term)
            or key in main_key
            or main_key in key
            or key in normalize_key(product_type)
        ):
            continue

        market_terms.append(term)

        if len(market_terms) >= 5:
            break

    def make_title(
        components: list[str],
        max_length: int = MAX_RECOMMENDED_LENGTH,
    ) -> tuple[str, list[str]]:
        filtered = [
            value
            for value in components
            if allowed(value)
        ]
        title = build_title(
            filtered,
            max_length=max_length,
        )

        missing = [
            word
            for word in required_values
            if normalize_key(word)
            not in normalize_key(title)
        ]

        for word in missing:
            candidate = normalize_text(
                f"{title} {word}"
            )

            if len(candidate) <= 100:
                title = candidate

        final_missing = [
            word
            for word in required_values
            if normalize_key(word)
            not in normalize_key(title)
        ]

        return title, final_missing

    raw_candidates = [
        (
            "간결형",
            [
                brand,
                product_type or main_keyword,
                *required_values,
                *feature_values[:2],
                model_name,
            ],
        ),
        (
            "균형형",
            [
                brand,
                product_type or main_keyword,
                *required_values,
                *feature_values[:3],
                *market_terms[:2],
                *related_keywords[:1],
                model_name,
            ],
        ),
        (
            "확장형",
            [
                brand,
                product_type or main_keyword,
                *required_values,
                *feature_values[:5],
                *market_terms[:3],
                *related_keywords[:2],
                model_name,
            ],
        ),
    ]

    candidates: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for style, components in raw_candidates:
        title, missing_required = make_title(
            components
        )

        if not title:
            continue

        if title in seen_titles:
            title, missing_required = make_title(
                [
                    *components,
                    *market_terms,
                    *related_keywords,
                ],
                max_length=55,
            )

        if title in seen_titles:
            continue

        if contains_excluded(
            title,
            excluded_keys,
        ):
            continue

        seen_titles.add(title)

        score, score_breakdown = score_candidate(
            title=title,
            main_keyword=main_keyword,
            product_type=product_type,
            brand=brand,
            features=feature_values,
            required_words=required_values,
            keyword_rows=related_rows,
            competitor_terms=competitor_terms,
            representative_category=(
                representative_category
            ),
        )

        used_keywords = [
            keyword
            for keyword in [
                main_keyword,
                *feature_values,
                *market_terms,
                *related_keywords,
                *required_values,
            ]
            if (
                normalize_key(keyword)
                in normalize_key(title)
            )
        ]

        candidate_warnings = policy_warnings(
            title
        )

        if missing_required:
            candidate_warnings.append(
                "필수 단어가 누락되었습니다: "
                + ", ".join(missing_required)
            )

        if style == "간결형":
            reason = (
                "메인 키워드와 핵심 제품정보를 "
                "짧고 명확하게 구성했습니다."
            )
        elif style == "균형형":
            reason = (
                "검색량과 TOP 10 반복 단어, "
                "제품 특징을 균형 있게 반영했습니다."
            )
        else:
            reason = (
                "실제 제품정보 범위에서 연관 검색어와 "
                "경쟁 핵심 단어를 폭넓게 반영했습니다."
            )

        candidates.append({
            "style": style,
            "title": title,
            "score": score,
            "score_breakdown": score_breakdown,
            "length": len(title),
            "reason": reason,
            "used_keywords": list(
                dict.fromkeys(used_keywords)
            ),
            "warnings": candidate_warnings,
            "missing_required_words": (
                missing_required
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

    style_priority = {
        "균형형": 0,
        "간결형": 1,
        "확장형": 2,
    }
    candidates.sort(
        key=lambda item: (
            style_priority.get(
                item["style"],
                9,
            ),
            -item["score"],
        )
    )

    keyword_suggestions = [
        {
            "keyword": row.get("keyword", ""),
            "total_volume": int(
                row.get("total_volume", 0)
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
        for row in related_rows
        if allowed(
            normalize_text(
                row.get("keyword", "")
            )
        )
    ][:15]

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

    current_title_diagnosis = (
        diagnose_current_title(
            current_title=current_title,
            main_keyword=main_keyword,
            brand=brand,
            features=feature_values,
            excluded_keys=excluded_keys,
            competitor_terms=competitor_terms,
        )
    )

    return {
        "mode": mode,
        "main_keyword": main_keyword,
        "product_type": product_type,
        "brand": brand,
        "model_name": model_name,
        "current_title": current_title,
        "product_url": product_url,
        "representative_category": (
            representative_category
        ),
        "current_title_warnings": (
            policy_warnings(current_title)
            if current_title
            else []
        ),
        "current_title_diagnosis": (
            current_title_diagnosis
        ),
        "keyword_suggestions": (
            keyword_suggestions
        ),
        "competitor_terms": competitor_terms,
        "competitor_titles": competitor_titles,
        "candidates": candidates,
        "warnings": warnings,
    }
