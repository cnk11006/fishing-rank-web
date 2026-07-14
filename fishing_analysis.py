from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from datetime import timedelta
from typing import Any, Iterable

import pandas as pd
import streamlit as st

from fishing_core import (
    AD_HISTORY_HEADERS,
    AD_HISTORY_SHEET,
    TARGET_STORE,
    ad_api_get,
    append_raw_rows,
    clean_naver_title,
    collect_rank_light,
    ensure_worksheet_headers,
    get_exact_keyword_volume,
    get_google_sheet,
    get_keyword_stats_list,
    get_or_create_worksheet,
    is_our_shop_item,
    make_hash,
    normalize_product_name,
    normalize_text,
    now_kst,
    now_text,
    safe_float,
    safe_int,
    safe_url,
    worksheet_records_safe,
)


logger = logging.getLogger(__name__)


# =========================================================
# 0. 공통 엑셀 열 탐색
# =========================================================

def find_column(
    columns: Iterable[Any],
    candidates: Iterable[str],
    exact_first: bool = True,
) -> str | None:
    """
    엑셀 열 이름에서 후보 문자열을 찾는다.

    1. 정확히 같은 열 이름 우선
    2. 후보 문자열이 포함된 열 이름 탐색
    """
    column_list = [str(column).strip() for column in columns]
    candidate_list = [str(x).strip() for x in candidates]

    if exact_first:
        for candidate in candidate_list:
            for column in column_list:
                if column == candidate:
                    return column

    for candidate in candidate_list:
        for column in column_list:
            if candidate in column:
                return column

    return None


def numeric_series(
    dataframe: pd.DataFrame,
    column: str | None,
    default: float = 0,
) -> pd.Series:
    """
    지정한 열이 없을 때도 데이터프레임 길이와 동일한 Series를 반환한다.
    """
    if column and column in dataframe.columns:
        return pd.to_numeric(
            dataframe[column],
            errors="coerce",
        ).fillna(default)

    return pd.Series(
        [default] * len(dataframe),
        index=dataframe.index,
        dtype="float64",
    )


def text_series(
    dataframe: pd.DataFrame,
    column: str | None,
) -> pd.Series:
    if column and column in dataframe.columns:
        return (
            dataframe[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    return pd.Series(
        [""] * len(dataframe),
        index=dataframe.index,
        dtype="object",
    )


def read_excel_safely(
    uploaded_file,
    dtype: Any = None,
) -> tuple[pd.DataFrame | None, str | None]:
    try:
        dataframe = pd.read_excel(
            uploaded_file,
            dtype=dtype,
            engine="openpyxl",
        )

        if dataframe is None or dataframe.empty:
            return None, "엑셀 파일에 분석할 데이터가 없습니다."

        dataframe.columns = [
            str(column).strip()
            for column in dataframe.columns
        ]

        return dataframe, None

    except Exception as exc:
        logger.exception("엑셀 파일 읽기 실패")
        return None, f"엑셀 파일 읽기 오류: {exc}"


# =========================================================
# 1. 광고 API — 캠페인·그룹·소재·성과
# =========================================================

@st.cache_data(ttl=300, max_entries=5)
def ad_get_campaigns() -> tuple[list[dict[str, Any]], str | None]:
    data, error = ad_api_get("/ncc/campaigns")

    if error:
        return [], error

    if not isinstance(data, list):
        return [], "캠페인 API 응답 형식이 올바르지 않습니다."

    return data, None


@st.cache_data(ttl=300, max_entries=100)
def ad_get_adgroups(
    campaign_id: str,
) -> tuple[list[dict[str, Any]], str | None]:
    data, error = ad_api_get(
        "/ncc/adgroups",
        params={"nccCampaignId": campaign_id},
    )

    if error:
        return [], error

    if not isinstance(data, list):
        return [], "광고그룹 API 응답 형식이 올바르지 않습니다."

    return data, None


@st.cache_data(ttl=300, max_entries=500)
def ad_get_ads(
    adgroup_id: str,
) -> tuple[list[dict[str, Any]], str | None]:
    data, error = ad_api_get(
        "/ncc/ads",
        params={"nccAdgroupId": adgroup_id},
    )

    if error:
        return [], error

    if not isinstance(data, list):
        return [], "광고 소재 API 응답 형식이 올바르지 않습니다."

    return data, None


@st.cache_data(ttl=300, max_entries=500)
def ad_get_stats(
    ids_tuple: tuple[str, ...],
    days: int = 7,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    ids = [
        str(item_id).strip()
        for item_id in ids_tuple
        if str(item_id).strip()
    ]

    if not ids:
        return {}, []

    days = max(1, min(safe_int(days, 7), 90))

    until = now_kst().strftime("%Y-%m-%d")
    since = (
        now_kst() - timedelta(days=days)
    ).strftime("%Y-%m-%d")

    fields = [
        "impCnt",
        "clkCnt",
        "ctr",
        "cpc",
        "salesAmt",
        "avgRnk",
        "ccnt",
    ]

    time_range = {
        "since": since,
        "until": until,
    }

    results: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for start_index in range(0, len(ids), 100):
        chunk = ids[start_index:start_index + 100]

        params = {
            "ids": chunk,
            "fields": json.dumps(
                fields,
                ensure_ascii=False,
            ),
            "timeRange": json.dumps(
                time_range,
                ensure_ascii=False,
            ),
        }

        data, error = ad_api_get(
            "/stats",
            params=params,
        )

        if error:
            errors.append(error)
            continue

        rows = (
            data.get("data", [])
            if isinstance(data, dict)
            else []
        )

        for row in rows:
            result_id = str(row.get("id", "")).strip()

            if not result_id:
                continue

            results[result_id] = {
                "impCnt": safe_int(row.get("impCnt")),
                "clkCnt": safe_int(row.get("clkCnt")),
                "ctr": safe_float(row.get("ctr")),
                "cpc": safe_float(row.get("cpc")),
                "salesAmt": safe_float(row.get("salesAmt")),
                "avgRnk": safe_float(row.get("avgRnk")),
                "ccnt": safe_int(row.get("ccnt")),
            }

        time.sleep(0.15)

    return results, errors


# =========================================================
# 2. 광고 진단
# =========================================================

def recommend_bid(
    impressions: float,
    ctr: float,
    average_rank: float,
    bid_amount: Any,
) -> str | None:
    current_bid = safe_int(bid_amount)

    if current_bid <= 0:
        return None

    if impressions <= 0:
        suggested = max(
            current_bid + 10,
            int(round(current_bid * 1.3, -1)),
        )

        return (
            "💰 노출이 없어 입찰가 상향 검토: "
            f"{current_bid:,}원 → 약 {suggested:,}원. "
            "일예산·비즈머니·소재 상태도 함께 확인하세요."
        )

    if average_rank >= 5:
        suggested = max(
            current_bid + 10,
            int(round(current_bid * 1.2, -1)),
        )

        return (
            "💰 평균 노출순위가 낮아 입찰가 상향 검토: "
            f"{current_bid:,}원 → 약 {suggested:,}원."
        )

    if (
        0 < average_rank < 3
        and ctr >= 1.0
        and impressions >= 100
    ):
        suggested = max(
            10,
            int(round(current_bid * 0.9, -1)),
        )

        return (
            "💰 순위와 클릭률이 양호합니다. "
            f"{current_bid:,}원 → 약 {suggested:,}원으로 "
            "소폭 낮춘 후 순위 변화를 관찰할 수 있습니다."
        )

    return (
        f"💰 현재 입찰가 {current_bid:,}원 수준 유지가 무난합니다."
    )


def diagnose_ad(
    stat: dict[str, Any],
    bid_amount: Any = None,
    quality_grade: Any = None,
    is_active: bool = True,
) -> tuple[str, str, list[str], int]:
    """
    반환:
    - 상태 아이콘
    - 진단 문구
    - 조언 목록
    - 우선순위 점수
    """
    if not is_active:
        return (
            "⚪",
            "꺼짐 (집행 안 됨)",
            ["캠페인·광고그룹·소재의 ON/OFF 상태를 확인하세요."],
            0,
        )

    impressions = safe_float(stat.get("impCnt"))
    clicks = safe_float(stat.get("clkCnt"))
    ctr = safe_float(stat.get("ctr"))
    average_rank = safe_float(stat.get("avgRnk"))
    quality = safe_int(quality_grade)

    advice: list[str] = []

    bid_tip = recommend_bid(
        impressions=impressions,
        ctr=ctr,
        average_rank=average_rank,
        bid_amount=bid_amount,
    )

    if bid_tip:
        advice.append(bid_tip)

    if quality > 0:
        if quality <= 3:
            advice.append(
                f"품질지수 {quality}/10으로 낮습니다. "
                "상품명·대표 이미지·가격·리뷰 경쟁력을 우선 개선하세요."
            )
        elif quality <= 6:
            advice.append(
                f"품질지수 {quality}/10으로 보통 수준입니다. "
                "클릭률을 개선하면 동일 입찰가에서도 노출 효율이 좋아질 수 있습니다."
            )

    if impressions <= 0:
        advice.extend([
            "입찰가 부족, 예산 소진, 비즈머니 부족, 검수 상태를 확인하세요.",
            "캠페인·광고그룹·소재가 모두 ON인지 확인하세요.",
        ])

        return (
            "🔴",
            "노출 안 됨",
            advice,
            100,
        )

    if average_rank >= 5:
        advice.append(
            f"평균 노출순위가 {average_rank:.1f}위입니다. "
            "입찰가 또는 품질지수 개선을 검토하세요."
        )

    if impressions >= 100 and ctr < 0.5:
        advice.append(
            f"CTR이 {ctr:.2f}%로 낮습니다. "
            "대표 이미지·상품명·가격 혜택을 점검하세요."
        )

    if 0 < impressions < 100:
        advice.append(
            "노출 데이터가 적어 판단 신뢰도가 낮습니다. "
            "며칠 더 운영한 후 다시 확인하세요."
        )

    low_rank = average_rank >= 5
    low_ctr = impressions >= 100 and ctr < 0.5

    if low_rank and low_ctr:
        return (
            "🟠",
            "노출순위·클릭 모두 개선 필요",
            advice,
            80,
        )

    if low_rank:
        return (
            "🟡",
            "노출은 되지만 순위가 낮음",
            advice,
            60,
        )

    if low_ctr:
        return (
            "🟡",
            "노출은 되지만 클릭이 낮음",
            advice,
            55,
        )

    if quality and quality <= 3:
        return (
            "🟡",
            "품질지수 개선 권장",
            advice,
            50,
        )

    if impressions < 100:
        return (
            "🟡",
            "데이터 추가 수집 필요",
            advice,
            30,
        )

    return (
        "🟢",
        "양호",
        ["노출·클릭·순위가 비교적 안정적입니다."],
        0,
    )


def determine_entity_active(
    entity: dict[str, Any],
    eligible_statuses: set[str] | None = None,
) -> bool:
    if entity.get("userLock") is True:
        return False

    status = str(entity.get("status", "")).upper()

    if status in {
        "PAUSED",
        "DELETED",
        "STOPPED",
        "DISABLED",
    }:
        return False

    if eligible_statuses and status:
        return status in eligible_statuses

    return True


def extract_ad_product_name(
    ad: dict[str, Any],
) -> str:
    ad_info = ad.get("ad") or {}
    reference = ad.get("referenceData") or {}

    candidates = [
        ad_info.get("productName"),
        reference.get("productName"),
        ad_info.get("headline"),
        ad.get("name"),
    ]

    for candidate in candidates:
        text = clean_naver_title(candidate)

        if text:
            return text

    return "(이름 없음)"


def extract_quality_grade(
    ad: dict[str, Any],
) -> int:
    qi_data = ad.get("nccQi") or {}

    if isinstance(qi_data, dict):
        return safe_int(qi_data.get("qiGrade"))

    return 0


def extract_bid_amount(
    ad: dict[str, Any],
    adgroup: dict[str, Any] | None = None,
) -> int:
    ad_attr = ad.get("adAttr") or {}
    bid = safe_int(ad_attr.get("bidAmt"))

    if bid > 0:
        return bid

    if adgroup:
        return safe_int(adgroup.get("bidAmt"))

    return 0


def run_ad_diagnosis(
    adgroups: list[dict[str, Any]],
    campaign_name: str,
    days: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for adgroup in adgroups:
        adgroup_id = str(
            adgroup.get("nccAdgroupId", "")
        ).strip()

        if not adgroup_id:
            continue

        adgroup_name = str(
            adgroup.get("name", "")
        ).strip()

        group_active = determine_entity_active(adgroup)

        ads, ads_error = ad_get_ads(adgroup_id)

        if ads_error:
            errors.append(
                f"{campaign_name}/{adgroup_name}: {ads_error}"
            )
            continue

        if not ads:
            continue

        ad_ids = tuple(
            str(ad.get("nccAdId", "")).strip()
            for ad in ads
            if str(ad.get("nccAdId", "")).strip()
        )

        stats, stat_errors = ad_get_stats(
            ad_ids,
            days=days,
        )

        errors.extend(stat_errors)

        for ad in ads:
            ad_id = str(
                ad.get("nccAdId", "")
            ).strip()

            if not ad_id:
                continue

            stat = stats.get(ad_id, {})
            quality = extract_quality_grade(ad)
            bid = extract_bid_amount(ad, adgroup)
            product_name = extract_ad_product_name(ad)

            ad_active = determine_entity_active(
                ad,
                eligible_statuses={
                    "ELIGIBLE",
                    "ACTIVE",
                    "ON",
                },
            )

            is_active = group_active and ad_active

            icon, verdict, advice, priority = diagnose_ad(
                stat=stat,
                bid_amount=bid,
                quality_grade=quality,
                is_active=is_active,
            )

            rows.append({
                "광고ID": ad_id,
                "상태": icon,
                "우선순위": priority,
                "캠페인": campaign_name,
                "광고그룹": adgroup_name,
                "상품명": product_name,
                "ON/OFF": "ON" if is_active else "OFF",
                "입찰가": bid,
                "품질지수": quality,
                "노출수": safe_int(stat.get("impCnt")),
                "클릭수": safe_int(stat.get("clkCnt")),
                "CTR(%)": round(
                    safe_float(stat.get("ctr")),
                    2,
                ),
                "평균순위": round(
                    safe_float(stat.get("avgRnk")),
                    1,
                ),
                "광고비": safe_int(stat.get("salesAmt")),
                "전환수": safe_int(stat.get("ccnt")),
                "진단": verdict,
                "_advice": " / ".join(advice),
            })

        time.sleep(0.1)

    rows.sort(
        key=lambda row: (
            -safe_int(row.get("우선순위")),
            -safe_int(row.get("광고비")),
        )
    )

    return rows, errors


# =========================================================
# 3. 광고 진단 기록
# =========================================================

def ensure_ad_history_sheet():
    spreadsheet = get_google_sheet()

    worksheet = get_or_create_worksheet(
        spreadsheet,
        AD_HISTORY_SHEET,
        rows=10000,
        cols=len(AD_HISTORY_HEADERS),
    )

    values = worksheet.get_all_values()

    # 예전 7열 광고진단 시트가 있으면 삭제하지 않고 백업 이름으로 변경
    if values and values[0][:3] == ["날짜", "상품명", "노출수"]:
        backup_title = (
            f"광고진단_구버전_{now_kst().strftime('%Y%m%d_%H%M%S')}"
        )

        worksheet.update_title(backup_title)

        worksheet = get_or_create_worksheet(
            spreadsheet,
            AD_HISTORY_SHEET,
            rows=10000,
            cols=len(AD_HISTORY_HEADERS),
        )

    ok, error = ensure_worksheet_headers(
        worksheet,
        AD_HISTORY_HEADERS,
    )

    if not ok:
        raise ValueError(error)

    return worksheet


def save_ad_diagnosis(
    rows: list[dict[str, Any]],
    collected_at: str | None = None,
) -> tuple[bool, str, str]:
    if not rows:
        return False, "저장할 광고 진단 결과가 없습니다.", ""

    try:
        worksheet = ensure_ad_history_sheet()
        collected_at = collected_at or now_text()

        sheet_rows: list[list[Any]] = []

        for row in rows:
            ad_id = str(row.get("광고ID", "")).strip()

            if not ad_id:
                continue

            record_id = make_hash(
                collected_at,
                ad_id,
                row.get("캠페인", ""),
                row.get("광고그룹", ""),
            )

            sheet_rows.append([
                record_id,
                collected_at,
                ad_id,
                row.get("캠페인", ""),
                row.get("광고그룹", ""),
                row.get("상품명", ""),
                row.get("ON/OFF", ""),
                safe_int(row.get("입찰가")),
                safe_int(row.get("품질지수")),
                safe_int(row.get("노출수")),
                safe_int(row.get("클릭수")),
                safe_float(row.get("CTR(%)")),
                safe_float(row.get("평균순위")),
                safe_int(row.get("광고비")),
                row.get("진단", ""),
            ])

        append_raw_rows(
            worksheet,
            sheet_rows,
        )

        load_ad_history.clear()

        return (
            True,
            f"광고 진단 {len(sheet_rows)}건 저장 완료",
            collected_at,
        )

    except Exception as exc:
        logger.exception("광고 진단 저장 실패")
        return False, f"광고 진단 저장 오류: {exc}", ""


@st.cache_data(ttl=300, max_entries=5)
def load_ad_history() -> list[dict[str, Any]]:
    try:
        worksheet = ensure_ad_history_sheet()

        records, error = worksheet_records_safe(
            worksheet,
            AD_HISTORY_HEADERS,
        )

        if error:
            logger.error(error)
            return []

        output: list[dict[str, Any]] = []

        for row in records:
            ad_id = str(row.get("광고ID", "")).strip()
            collected_at = str(
                row.get("수집일시", "")
            ).strip()

            if not ad_id or not collected_at:
                continue

            output.append({
                "기록ID": str(row.get("기록ID", "")),
                "수집일시": collected_at,
                "광고ID": ad_id,
                "캠페인": str(row.get("캠페인", "")),
                "광고그룹": str(row.get("광고그룹", "")),
                "상품명": str(row.get("상품명", "")),
                "ON/OFF": str(row.get("ON/OFF", "")),
                "입찰가": safe_int(row.get("입찰가")),
                "품질지수": safe_int(row.get("품질지수")),
                "노출수": safe_int(row.get("노출수")),
                "클릭수": safe_int(row.get("클릭수")),
                "CTR": safe_float(row.get("CTR")),
                "평균순위": safe_float(row.get("평균순위")),
                "광고비": safe_int(row.get("광고비")),
                "진단": str(row.get("진단", "")),
            })

        output.sort(
            key=lambda row: row["수집일시"]
        )

        return output

    except Exception:
        logger.exception("광고 진단 기록 불러오기 실패")
        return []


def load_previous_ad_snapshot(
    current_collected_at: str | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """
    가장 최근 실행 이전의 광고 스냅샷을 광고ID 기준으로 반환한다.
    """
    history = load_ad_history()

    if not history:
        return {}, None

    snapshot_times = sorted({
        row["수집일시"]
        for row in history
        if row.get("수집일시")
    })

    if current_collected_at:
        candidates = [
            timestamp
            for timestamp in snapshot_times
            if timestamp < current_collected_at
        ]
    else:
        candidates = snapshot_times[:-1]

    if not candidates:
        return {}, None

    previous_time = candidates[-1]

    previous_rows = [
        row
        for row in history
        if row["수집일시"] == previous_time
    ]

    previous_map = {
        row["광고ID"]: row
        for row in previous_rows
        if row.get("광고ID")
    }

    return previous_map, previous_time


def compare_ad_snapshots(
    current_rows: list[dict[str, Any]],
    previous_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []

    for current in current_rows:
        ad_id = str(current.get("광고ID", "")).strip()
        previous = previous_map.get(ad_id)

        if not previous:
            continue

        current_impressions = safe_int(
            current.get("노출수")
        )
        previous_impressions = safe_int(
            previous.get("노출수")
        )

        current_rank = safe_float(
            current.get("평균순위")
        )
        previous_rank = safe_float(
            previous.get("평균순위")
        )

        current_ctr = safe_float(
            current.get("CTR(%)")
        )
        previous_ctr = safe_float(
            previous.get("CTR")
        )

        reasons: list[str] = []
        severity = 0

        if (
            previous_impressions > 0
            and current_impressions
            < previous_impressions * 0.7
        ):
            drop_rate = round(
                (
                    1
                    - current_impressions
                    / previous_impressions
                )
                * 100
            )

            reasons.append(
                f"노출 {drop_rate}% 감소 "
                f"({previous_impressions:,} → {current_impressions:,})"
            )

            severity += drop_rate

        if (
            previous_rank > 0
            and current_rank > 0
            and current_rank - previous_rank >= 3
        ):
            reasons.append(
                f"평균순위 하락 "
                f"({previous_rank:.1f}위 → {current_rank:.1f}위)"
            )

            severity += int(
                (current_rank - previous_rank) * 10
            )

        if (
            previous_ctr >= 0.5
            and current_ctr < previous_ctr * 0.7
        ):
            reasons.append(
                f"CTR 감소 "
                f"({previous_ctr:.2f}% → {current_ctr:.2f}%)"
            )

            severity += 20

        if reasons:
            changes.append({
                "광고ID": ad_id,
                "상품명": current.get("상품명", ""),
                "캠페인": current.get("캠페인", ""),
                "변화": " / ".join(reasons),
                "심각도": severity,
            })

    changes.sort(
        key=lambda row: -safe_int(row.get("심각도"))
    )

    return changes


# =========================================================
# 4. SEO 분석
# =========================================================

SEO_SPECIAL_CHARACTERS = {
    "!",
    "@",
    "#",
    "$",
    "%",
    "^",
    "&",
    "*",
    "~",
    "+",
}


def generate_recommended_name(
    keyword: str,
    original_name: str,
    selected_related_keywords: list[str],
    max_length: int = 40,
) -> str:
    keyword = str(keyword).strip()
    original_name = clean_naver_title(original_name)

    base = original_name.replace(
        TARGET_STORE,
        "",
    ).strip()

    # 연속 공백 정리
    base = re.sub(r"\s+", " ", base)

    if (
        keyword
        and normalize_text(keyword)
        not in normalize_text(base)
    ):
        base = f"{keyword} {base}".strip()

    for related_keyword in selected_related_keywords:
        related_keyword = str(
            related_keyword
        ).strip()

        if not related_keyword:
            continue

        if (
            normalize_text(related_keyword)
            in normalize_text(base)
        ):
            continue

        candidate = f"{base} {related_keyword}".strip()

        if len(candidate) <= 35:
            base = candidate

    with_store_name = f"{base} {TARGET_STORE}".strip()

    if len(with_store_name) <= max_length:
        return with_store_name

    return base[:max_length].strip()


def analyze_seo(
    keyword: str,
    product_name: str,
    selected_related_keywords: list[str],
) -> dict[str, Any]:
    issues: list[tuple[str, str]] = []
    good_points: list[str] = []
    score = 100

    product_name = clean_naver_title(product_name)
    name_length = len(product_name)

    if name_length < 15:
        issues.append((
            "❌ 상품명이 너무 짧음",
            f"현재 {name_length}자입니다. "
            "상품 특성을 포함해 25~40자 수준을 검토하세요.",
        ))
        score -= 20

    elif name_length > 50:
        issues.append((
            "⚠️ 상품명이 너무 김",
            f"현재 {name_length}자입니다. "
            "핵심 키워드와 모델명 중심으로 정리하세요.",
        ))
        score -= 10

    else:
        good_points.append(
            f"✅ 상품명 길이가 적정 범위입니다 ({name_length}자)."
        )

    keyword_normalized = normalize_text(keyword)
    name_normalized = normalize_text(product_name)

    if keyword_normalized and keyword_normalized in name_normalized:
        good_points.append(
            f"✅ 핵심 키워드 '{keyword}'가 포함되어 있습니다."
        )
    else:
        issues.append((
            "❌ 핵심 키워드 미포함",
            f"상품과 실제로 관련 있다면 '{keyword}'를 상품명에 추가하세요.",
        ))
        score -= 30

    found_specials = [
        character
        for character in product_name
        if character in SEO_SPECIAL_CHARACTERS
    ]

    if len(found_specials) > 2:
        issues.append((
            "⚠️ 특수문자 과다",
            f"특수문자 {', '.join(sorted(set(found_specials)))}를 "
            "필요한 것만 남기세요.",
        ))
        score -= 10
    else:
        good_points.append(
            "✅ 특수문자 사용량이 많지 않습니다."
        )

    if product_name.startswith(TARGET_STORE):
        issues.append((
            "⚠️ 상호명이 상품명 맨 앞에 있음",
            "핵심 상품 키워드와 모델명을 먼저 배치하는 방안을 검토하세요.",
        ))
        score -= 10
    else:
        good_points.append(
            "✅ 상호명이 핵심 키워드보다 앞에 있지 않습니다."
        )

    words = [
        word.strip()
        for word in product_name.split()
        if len(word.strip()) > 1
    ]

    duplicates = sorted({
        word
        for word in words
        if words.count(word) > 1
    })

    if duplicates:
        issues.append((
            "⚠️ 중복 단어",
            f"{', '.join(duplicates)} 단어가 반복됩니다.",
        ))
        score -= 10
    else:
        good_points.append(
            "✅ 동일 단어가 과도하게 반복되지 않습니다."
        )

    included: list[str] = []
    missing: list[str] = []

    for related_keyword in selected_related_keywords:
        if (
            normalize_text(related_keyword)
            in name_normalized
        ):
            included.append(related_keyword)
        else:
            missing.append(related_keyword)

    if included:
        good_points.append(
            "✅ 포함된 연관 키워드: "
            + ", ".join(included)
        )

    if missing:
        issues.append((
            "💡 추가 검토 가능한 연관 키워드",
            ", ".join(missing)
            + " 중 상품과 직접 관련 있는 키워드만 사용하세요.",
        ))

    score = max(0, min(score, 100))

    return {
        "score": score,
        "issues": issues,
        "goods": good_points,
        "recommended_name": generate_recommended_name(
            keyword=keyword,
            original_name=product_name,
            selected_related_keywords=selected_related_keywords,
        ),
        "related_keywords": selected_related_keywords,
        "notice": (
            "SEO 점수는 내부 점검용 휴리스틱이며 "
            "네이버의 공식 검색순위 보장 기준이 아닙니다."
        ),
    }


# =========================================================
# 5. 채널·상품·검색어 엑셀 분석
# =========================================================

def analyze_channel_file(
    uploaded_file,
) -> tuple[pd.DataFrame | None, str | None]:
    dataframe, error = read_excel_safely(
        uploaded_file
    )

    if error:
        return None, error

    assert dataframe is not None

    channel_property = find_column(
        dataframe.columns,
        ["채널속성"],
    )
    channel_group = find_column(
        dataframe.columns,
        ["채널그룹"],
    )
    channel_name = find_column(
        dataframe.columns,
        ["채널명"],
    )
    visits = find_column(
        dataframe.columns,
        ["유입수"],
    )
    payment_count = find_column(
        dataframe.columns,
        [
            "결제수(마지막클릭)",
            "결제수",
        ],
    )
    payment_amount = find_column(
        dataframe.columns,
        [
            "결제금액(마지막클릭)",
            "결제금액",
        ],
    )

    if not visits:
        return None, (
            "'유입수' 열을 찾지 못했습니다. "
            f"현재 열: {list(dataframe.columns)}"
        )

    output = pd.DataFrame({
        "채널속성": text_series(
            dataframe,
            channel_property,
        ),
        "채널그룹": text_series(
            dataframe,
            channel_group,
        ),
        "채널명": text_series(
            dataframe,
            channel_name,
        ),
        "유입수": numeric_series(
            dataframe,
            visits,
        ),
        "결제수": numeric_series(
            dataframe,
            payment_count,
        ),
        "결제금액": numeric_series(
            dataframe,
            payment_amount,
        ),
    })

    denominator = output["유입수"].replace(
        0,
        pd.NA,
    )

    output["결제율(%)"] = (
        output["결제수"]
        .div(denominator)
        .mul(100)
        .fillna(0)
        .round(2)
    )

    output["객단가"] = (
        output["결제금액"]
        .div(output["결제수"].replace(0, pd.NA))
        .fillna(0)
        .round()
        .astype(int)
    )

    return output, None


def analyze_product_file(
    uploaded_file,
) -> tuple[pd.DataFrame | None, str | None]:
    dataframe, error = read_excel_safely(
        uploaded_file
    )

    if error:
        return None, error

    assert dataframe is not None

    name_column = find_column(
        dataframe.columns,
        ["상품명", "제품명"],
    )
    product_id_column = find_column(
        dataframe.columns,
        ["상품ID", "상품번호"],
    )
    views_column = find_column(
        dataframe.columns,
        ["상품상세조회수", "상세조회수"],
    )
    payment_amount_column = find_column(
        dataframe.columns,
        ["결제금액"],
    )
    payment_quantity_column = find_column(
        dataframe.columns,
        ["결제상품수량", "결제수량"],
    )
    conversion_column = find_column(
        dataframe.columns,
        [
            "상세조회대비결제율",
            "결제율",
            "전환율",
        ],
    )

    if not name_column:
        return None, (
            "'상품명' 열을 찾지 못했습니다. "
            f"현재 열: {list(dataframe.columns)}"
        )

    output = pd.DataFrame({
        "상품명": text_series(
            dataframe,
            name_column,
        ),
        "상품ID": text_series(
            dataframe,
            product_id_column,
        ),
        "조회수": numeric_series(
            dataframe,
            views_column,
        ),
        "결제금액": numeric_series(
            dataframe,
            payment_amount_column,
        ),
        "결제수량": numeric_series(
            dataframe,
            payment_quantity_column,
        ),
        "결제율": numeric_series(
            dataframe,
            conversion_column,
        ),
    })

    positive_views = output.loc[
        output["조회수"] > 0,
        "조회수",
    ]

    positive_rates = output.loc[
        output["결제율"] > 0,
        "결제율",
    ]

    view_median = (
        positive_views.median()
        if not positive_views.empty
        else 0
    )

    rate_median = (
        positive_rates.median()
        if not positive_rates.empty
        else 0
    )

    def classify(row: pd.Series) -> str:
        views = safe_float(row["조회수"])
        rate = safe_float(row["결제율"])

        if views <= 0:
            return "⚪ 데이터없음"

        high_view = (
            view_median > 0
            and views >= view_median
        )

        high_rate = (
            rate_median > 0
            and rate >= rate_median
        )

        if high_view and high_rate:
            return "🟢 효자상품"

        if high_view and not high_rate:
            return "🔴 개선필요"

        if not high_view and high_rate:
            return "🟡 숨은보석"

        return "⚪ 정리검토"

    output["분류"] = output.apply(
        classify,
        axis=1,
    )

    return output, None


def analyze_search_file(
    uploaded_file,
) -> tuple[
    pd.DataFrame | None,
    list[str],
    str | None,
]:
    dataframe, error = read_excel_safely(
        uploaded_file
    )

    if error:
        return None, [], error

    assert dataframe is not None

    columns = list(dataframe.columns)

    keyword_column = find_column(
        columns,
        ["키워드", "검색어"],
    )
    visits_column = find_column(
        columns,
        ["유입수"],
    )
    payment_count_column = find_column(
        columns,
        ["결제수"],
    )
    payment_amount_column = find_column(
        columns,
        ["결제금액"],
    )

    if not keyword_column:
        return (
            None,
            columns,
            "'키워드' 또는 '검색어' 열을 찾지 못했습니다.",
        )

    if not visits_column:
        return (
            None,
            columns,
            "'유입수' 열을 찾지 못했습니다.",
        )

    output = pd.DataFrame({
        "검색어": text_series(
            dataframe,
            keyword_column,
        ),
        "유입수": numeric_series(
            dataframe,
            visits_column,
        ),
        "결제수": numeric_series(
            dataframe,
            payment_count_column,
        ),
        "결제금액": numeric_series(
            dataframe,
            payment_amount_column,
        ),
    })

    output = output[
        ~output["검색어"].isin({
            "(검색어 없음)",
            "nan",
            "None",
            "",
        })
    ]

    output = (
        output
        .groupby("검색어", as_index=False)
        .agg({
            "유입수": "sum",
            "결제수": "sum",
            "결제금액": "sum",
        })
    )

    output["결제율(%)"] = (
        output["결제수"]
        .div(output["유입수"].replace(0, pd.NA))
        .mul(100)
        .fillna(0)
        .round(2)
    )

    output = output.sort_values(
        ["결제금액", "유입수"],
        ascending=[False, False],
    )

    return output, columns, None


# =========================================================
# 6. 교차구매 분석
# =========================================================

def read_multiple_excel_files(
    uploaded_files,
) -> tuple[pd.DataFrame | None, list[str], list[str]]:
    if not uploaded_files:
        return None, [], ["업로드된 파일이 없습니다."]

    if not isinstance(uploaded_files, (list, tuple)):
        uploaded_files = [uploaded_files]

    frames: list[pd.DataFrame] = []
    errors: list[str] = []

    for uploaded_file in uploaded_files:
        dataframe, error = read_excel_safely(
            uploaded_file,
            dtype=str,
        )

        if error:
            file_name = getattr(
                uploaded_file,
                "name",
                "파일",
            )
            errors.append(
                f"{file_name}: {error}"
            )
            continue

        assert dataframe is not None
        dataframe = dataframe.fillna("")
        frames.append(dataframe)

    if not frames:
        return None, [], errors

    combined = pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    ).fillna("")

    return combined, list(combined.columns), errors


def analyze_cross_purchase(
    uploaded_files,
    target_query: str,
    ours_ids: set[str] | None = None,
) -> tuple[
    list[dict[str, Any]] | None,
    list[str],
    int | None,
    list[str],
]:
    dataframe, columns, file_errors = read_multiple_excel_files(
        uploaded_files
    )

    if dataframe is None:
        return None, columns, None, file_errors

    order_column = find_column(
        columns,
        ["주문번호", "주문 번호", "구매번호"],
    )
    name_column = find_column(
        columns,
        ["상품명", "상품 명", "제품명"],
    )
    product_id_column = find_column(
        columns,
        ["상품번호", "상품 번호", "상품ID"],
    )

    if not order_column or not name_column:
        return None, columns, None, file_errors

    dataframe[order_column] = (
        dataframe[order_column]
        .astype(str)
        .str.strip()
    )

    dataframe[name_column] = (
        dataframe[name_column]
        .astype(str)
        .str.strip()
    )

    if product_id_column:
        dataframe[product_id_column] = (
            dataframe[product_id_column]
            .astype(str)
            .str.strip()
        )

    dataframe = dataframe[
        dataframe[order_column] != ""
    ].copy()

    query = str(target_query).strip()

    if not query:
        return [], columns, 0, file_errors

    target_mask = dataframe[name_column].str.contains(
        query,
        na=False,
        regex=False,
    )

    if product_id_column:
        target_mask = target_mask | (
            dataframe[product_id_column] == query
        )

    target_orders = set(
        dataframe.loc[
            target_mask,
            order_column,
        ].unique()
    )

    if not target_orders:
        return [], columns, 0, file_errors

    related = dataframe[
        dataframe[order_column].isin(target_orders)
    ].copy()

    related_target_mask = related[
        name_column
    ].str.contains(
        query,
        na=False,
        regex=False,
    )

    if product_id_column:
        related_target_mask = related_target_mask | (
            related[product_id_column] == query
        )

    others = related[
        ~related_target_mask
        & (related[name_column] != "")
    ].copy()

    if others.empty:
        return [], columns, len(target_orders), file_errors

    group_columns = [name_column]

    if product_id_column:
        group_columns.insert(0, product_id_column)

    # 같은 주문에 같은 상품이 여러 행이어도 1건으로 계산
    unique_order_products = (
        others[
            [order_column] + group_columns
        ]
        .drop_duplicates()
    )

    grouped = (
        unique_order_products
        .groupby(group_columns, dropna=False)[order_column]
        .nunique()
        .reset_index(name="함께 구매 주문수")
    )

    ours_ids = {
        str(product_id).strip()
        for product_id in (ours_ids or set())
        if str(product_id).strip()
    }

    rows: list[dict[str, Any]] = []
    total_orders = len(target_orders)

    for _, grouped_row in grouped.iterrows():
        product_name = str(
            grouped_row[name_column]
        ).strip()

        product_id = (
            str(grouped_row[product_id_column]).strip()
            if product_id_column
            else ""
        )

        together_orders = safe_int(
            grouped_row["함께 구매 주문수"]
        )

        is_ours = (
            product_id in ours_ids
            if product_id and ours_ids
            else TARGET_STORE in product_name
        )

        rows.append({
            "상품번호": product_id,
            "함께 산 상품": product_name,
            "함께 구매 주문수": together_orders,
            "동시구매율(%)": round(
                together_orders
                / total_orders
                * 100,
                1,
            ),
            "우리 제품": "✅" if is_ours else "",
        })

    rows.sort(
        key=lambda row: (
            -safe_int(row["함께 구매 주문수"]),
            str(row["함께 산 상품"]),
        )
    )

    return rows, columns, total_orders, file_errors


# =========================================================
# 7. 상품 마스터·자사 동반구매율
# =========================================================

def load_product_master(
    master_file,
    our_brand: str = TARGET_STORE,
) -> tuple[
    set[str] | None,
    dict[str, str],
    str | None,
]:
    dataframe, error = read_excel_safely(
        master_file,
        dtype=str,
    )

    if error:
        return None, {}, error

    assert dataframe is not None

    dataframe = dataframe.fillna("")
    columns = list(dataframe.columns)

    product_id_column = find_column(
        columns,
        ["상품번호", "상품 번호", "상품ID"],
    )
    division_column = find_column(
        columns,
        ["구분", "브랜드", "자사/타사"],
    )
    name_column = find_column(
        columns,
        ["상품명", "상품 명", "제품명"],
    )

    if not product_id_column or not division_column:
        return (
            None,
            {},
            "'상품번호' 또는 '구분/브랜드' 열을 찾지 못했습니다. "
            f"현재 열: {columns}",
        )

    dataframe[product_id_column] = (
        dataframe[product_id_column]
        .astype(str)
        .str.strip()
    )

    dataframe[division_column] = (
        dataframe[division_column]
        .astype(str)
        .str.strip()
    )

    if name_column:
        dataframe[name_column] = (
            dataframe[name_column]
            .astype(str)
            .str.strip()
        )

    brand_normalized = normalize_text(our_brand)

    ours_mask = dataframe[division_column].apply(
        lambda value: (
            brand_normalized in normalize_text(value)
        )
    )

    ours_ids = set(
        dataframe.loc[
            ours_mask,
            product_id_column,
        ]
    )

    ours_ids.discard("")

    product_names: dict[str, str] = {}

    for _, row in dataframe.iterrows():
        product_id = str(
            row[product_id_column]
        ).strip()

        if not product_id:
            continue

        product_name = (
            str(row[name_column]).strip()
            if name_column
            else ""
        )

        if product_id not in product_names:
            product_names[product_id] = product_name

    return ours_ids, product_names, None


def analyze_brand_contribution(
    uploaded_files,
    ours_ids: set[str],
    min_orders: int = 3,
) -> tuple[
    list[dict[str, Any]] | None,
    list[str],
    int,
    list[str],
]:
    dataframe, columns, file_errors = read_multiple_excel_files(
        uploaded_files
    )

    if dataframe is None:
        return None, columns, 0, file_errors

    order_column = find_column(
        columns,
        ["주문번호", "주문 번호", "구매번호"],
    )
    product_id_column = find_column(
        columns,
        ["상품번호", "상품 번호", "상품ID"],
    )
    name_column = find_column(
        columns,
        ["상품명", "상품 명", "제품명"],
    )

    if not order_column or not product_id_column:
        return None, columns, 0, file_errors

    dataframe[order_column] = (
        dataframe[order_column]
        .astype(str)
        .str.strip()
    )

    dataframe[product_id_column] = (
        dataframe[product_id_column]
        .astype(str)
        .str.strip()
    )

    if name_column:
        dataframe[name_column] = (
            dataframe[name_column]
            .astype(str)
            .str.strip()
        )

    dataframe = dataframe[
        (dataframe[order_column] != "")
        & (dataframe[product_id_column] != "")
    ].copy()

    ours_ids = {
        str(product_id).strip()
        for product_id in ours_ids
        if str(product_id).strip()
    }

    orders_with_ours = set(
        dataframe.loc[
            dataframe[product_id_column].isin(ours_ids),
            order_column,
        ].unique()
    )

    product_name_map: dict[str, str] = {}

    if name_column:
        for _, row in dataframe.iterrows():
            product_id = str(
                row[product_id_column]
            ).strip()
            product_name = str(
                row[name_column]
            ).strip()

            if (
                product_id
                and product_name
                and product_id not in product_name_map
            ):
                product_name_map[product_id] = product_name

    # 한 주문에서 동일 상품이 반복되어도 한 번만 집계
    order_product_pairs = dataframe[
        [order_column, product_id_column]
    ].drop_duplicates()

    competitor_pairs = order_product_pairs[
        ~order_product_pairs[
            product_id_column
        ].isin(ours_ids)
    ]

    min_orders = max(1, safe_int(min_orders, 3))

    rows: list[dict[str, Any]] = []
    all_competitor_orders: set[str] = set()

    for product_id, group in competitor_pairs.groupby(
        product_id_column
    ):
        order_ids = set(group[order_column])
        total_orders = len(order_ids)

        if total_orders < min_orders:
            continue

        with_ours = len(
            order_ids & orders_with_ours
        )

        rate = (
            round(
                with_ours
                / total_orders
                * 100,
                1,
            )
            if total_orders
            else 0
        )

        all_competitor_orders |= order_ids

        rows.append({
            "타사 상품번호": product_id,
            "타사 제품": product_name_map.get(
                product_id,
                "",
            ),
            "주문 건수": total_orders,
            "자사 동반 주문": with_ours,
            "자사 동반구매율(%)": rate,
        })

    rows.sort(
        key=lambda row: (
            -safe_float(row["자사 동반구매율(%)"]),
            -safe_int(row["주문 건수"]),
        )
    )

    return (
        rows,
        columns,
        len(all_competitor_orders),
        file_errors,
    )


# =========================================================
# 8. 사입 후보 — 태그 사전
# =========================================================

SPECIES_TAGS = {
    "갈치": [
        "갈치",
        "텐빈",
        "텐야",
        "사벨",
        "사벨피쉬",
    ],
    "주꾸미": [
        "주꾸미",
        "쭈꾸미",
        "갑오징어",
    ],
    "무늬오징어": [
        "무늬오징어",
        "에깅",
        "아오리",
    ],
    "참돔": [
        "참돔",
        "타이라바",
        "러버지깅",
    ],
    "볼락": [
        "볼락",
        "메바루",
        "볼락루어",
    ],
    "광어": [
        "광어",
        "대광어",
        "다운샷",
    ],
    "농어": [
        "농어",
        "시배스",
    ],
    "우럭": [
        "우럭",
        "조피볼락",
    ],
    "한치": [
        "한치",
        "이카메탈",
        "오모리그",
    ],
    "문어": [
        "문어",
        "피문어",
        "대왕문어",
        "돌문어",
    ],
    "고등어": [
        "고등어",
    ],
    "전갱이": [
        "전갱이",
        "아징",
    ],
    "감성돔": [
        "감성돔",
        "감시",
    ],
    "삼치": [
        "삼치",
    ],
    "대구": [
        "대구",
        "대구라바",
    ],
    "민물": [
        "민물",
        "붕어",
        "잉어",
    ],
}


GENRE_TAGS = {
    "로드": [
        "로드",
        "낚싯대",
        "낚시대",
        "선상대",
        "루어대",
    ],
    "릴": [
        "릴",
        "베이트릴",
        "스피닝릴",
        "전동릴",
        "장구통릴",
    ],
    "루어": [
        "루어",
        "웜",
        "지그",
        "메탈",
        "에기",
        "미노우",
        "스푼",
    ],
    "채비": [
        "채비",
        "봉돌",
        "바늘",
        "도래",
        "기둥줄",
        "스냅",
        "편대",
    ],
    "라인": [
        "라인",
        "원줄",
        "쇼크리더",
        "합사",
        "목줄",
        "카본줄",
        "나일론줄",
    ],
    "소품": [
        "케이스",
        "가방",
        "수납",
        "집게",
        "플라이어",
        "가위",
        "태클박스",
        "로드벨트",
    ],
    "의류": [
        "낚시복",
        "구명복",
        "구명조끼",
        "장갑",
        "모자",
    ],
}


BRAND_ALIAS = {
    "백경": [
        "백경",
        "bkc",
    ],
    "시마노": [
        "시마노",
        "shimano",
    ],
    "다이와": [
        "다이와",
        "daiwa",
    ],
    "아부가르시아": [
        "아부가르시아",
        "abugarcia",
        "abu",
    ],
}


def normalize_brand(raw_brand: Any) -> str:
    normalized = normalize_text(raw_brand)

    if not normalized:
        return ""

    for standard, aliases in BRAND_ALIAS.items():
        for alias in aliases:
            alias_normalized = normalize_text(alias)

            if (
                alias_normalized
                and (
                    normalized == alias_normalized
                    or alias_normalized in normalized
                )
            ):
                return normalize_text(standard)

    return normalized


def extract_tags(
    product_name: Any,
    tag_dictionary: dict[str, list[str]],
) -> list[str]:
    normalized_name = normalize_text(product_name)

    if not normalized_name:
        return []

    tags: list[str] = []

    for tag, keywords in tag_dictionary.items():
        if any(
            normalize_text(keyword) in normalized_name
            for keyword in keywords
            if normalize_text(keyword)
        ):
            tags.append(tag)

    return tags


def extract_model_codes(
    product_name: Any,
) -> list[str]:
    """
    영문과 숫자가 함께 들어간 모델 코드 후보를 추출한다.

    단순 숫자만 있는 규격은 모델 코드로 사용하지 않는다.
    """
    text = clean_naver_title(
        product_name
    ).upper()

    patterns = [
        r"\b[A-Z]{1,8}[-_/]?\d{2,6}[A-Z0-9-_/]*\b",
        r"\b[A-Z]{2,10}\s+\d{2,6}[A-Z0-9-_/]*\b",
        r"\b\d{2,6}[-_/][A-Z]{1,8}[A-Z0-9-_/]*\b",
    ]

    found: list[str] = []

    for pattern in patterns:
        for model in re.findall(pattern, text):
            normalized_model = re.sub(
                r"[\s\-_/]",
                "",
                model,
            )

            has_letter = bool(
                re.search(r"[A-Z]", normalized_model)
            )
            has_number = bool(
                re.search(r"\d", normalized_model)
            )

            if (
                has_letter
                and has_number
                and len(normalized_model) >= 4
            ):
                found.append(normalized_model)

    return sorted(
        set(found),
        key=lambda value: (-len(value), value),
    )


def make_product_fingerprint(
    product_name: Any,
    brand: Any = "",
) -> str:
    models = extract_model_codes(product_name)

    if models:
        return (
            f"{normalize_brand(brand)}|MODEL|{models[0]}"
        )

    normalized_name = normalize_product_name(
        product_name
    )

    return (
        f"{normalize_brand(brand)}|NAME|"
        f"{normalized_name[:40]}"
    )


def make_candidate_key(
    item: dict[str, Any],
    matched_brand: str,
) -> str:
    product_id = str(
        item.get("productId", "")
    ).strip()

    if product_id:
        return f"PID|{product_id}"

    return make_product_fingerprint(
        item.get("상품명", ""),
        matched_brand,
    )


# =========================================================
# 9. 사입 후보 — 자사 커버리지
# =========================================================

def build_store_coverage(
    store_dataframe: pd.DataFrame,
) -> tuple[dict[str, Any] | None, str | None]:
    if store_dataframe is None or store_dataframe.empty:
        return None, "자사 상품 파일에 데이터가 없습니다."

    dataframe = store_dataframe.fillna("").copy()

    dataframe.columns = [
        str(column).strip()
        for column in dataframe.columns
    ]

    columns = list(dataframe.columns)

    name_column = find_column(
        columns,
        ["상품명", "상품 명", "제품명"],
    )
    brand_column = find_column(
        columns,
        ["브랜드", "제조사", "제조 회사"],
    )
    product_id_column = find_column(
        columns,
        ["상품번호", "상품 번호", "상품ID"],
    )

    if not name_column:
        return (
            None,
            "'상품명' 열을 찾지 못했습니다. "
            f"현재 열: {columns}",
        )

    group_coverage: set[tuple[str, str, str]] = set()
    product_ids: set[str] = set()
    fingerprints: set[str] = set()
    model_codes: set[str] = set()
    normalized_names: set[str] = set()

    for _, row in dataframe.iterrows():
        product_name = str(
            row.get(name_column, "")
        ).strip()

        if not product_name:
            continue

        brand = (
            str(row.get(brand_column, "")).strip()
            if brand_column
            else ""
        )

        normalized_brand = normalize_brand(brand)

        product_id = (
            str(row.get(product_id_column, "")).strip()
            if product_id_column
            else ""
        )

        if product_id:
            product_ids.add(product_id)

        fingerprints.add(
            make_product_fingerprint(
                product_name,
                brand,
            )
        )

        models = extract_model_codes(product_name)
        model_codes.update(models)

        normalized_names.add(
            normalize_product_name(product_name)
        )

        species_tags = (
            extract_tags(
                product_name,
                SPECIES_TAGS,
            )
            or ["기타"]
        )

        genre_tags = (
            extract_tags(
                product_name,
                GENRE_TAGS,
            )
            or ["기타"]
        )

        for species in species_tags:
            for genre in genre_tags:
                group_coverage.add((
                    normalized_brand,
                    species,
                    genre,
                ))

    return {
        "group_coverage": group_coverage,
        "product_ids": product_ids,
        "fingerprints": fingerprints,
        "model_codes": model_codes,
        "normalized_names": normalized_names,
        "product_count": len(dataframe),
    }, None


def is_same_owned_product(
    item: dict[str, Any],
    matched_brand: str,
    coverage: dict[str, Any],
) -> tuple[bool, str]:
    product_id = str(
        item.get("productId", "")
    ).strip()

    if (
        product_id
        and product_id in coverage.get(
            "product_ids",
            set(),
        )
    ):
        return True, "productId 일치"

    fingerprint = make_product_fingerprint(
        item.get("상품명", ""),
        matched_brand,
    )

    if fingerprint in coverage.get(
        "fingerprints",
        set(),
    ):
        return True, "모델/상품명 지문 일치"

    candidate_models = set(
        extract_model_codes(
            item.get("상품명", "")
        )
    )

    common_models = (
        candidate_models
        & coverage.get("model_codes", set())
    )

    if common_models:
        return (
            True,
            "모델코드 일치: "
            + ", ".join(sorted(common_models)),
        )

    normalized_name = normalize_product_name(
        item.get("상품명", "")
    )

    if (
        normalized_name
        and normalized_name
        in coverage.get(
            "normalized_names",
            set(),
        )
    ):
        return True, "정규화 상품명 일치"

    return False, ""


# =========================================================
# 10. 사입 후보 — 검색 조합과 점수
# =========================================================

def build_keyword_specs(
    brands: list[str],
    seasons: list[str],
    genres: list[str],
) -> list[dict[str, str]]:
    source_brands = brands or [""]
    source_seasons = seasons or [""]
    source_genres = genres or [""]

    specs: list[dict[str, str]] = []
    seen: set[str] = set()

    for brand in source_brands:
        for season in source_seasons:
            for genre in source_genres:
                parts = [
                    str(part).strip()
                    for part in [
                        brand,
                        season,
                        genre,
                    ]
                    if str(part).strip()
                ]

                if not parts:
                    continue

                keyword = " ".join(parts)
                normalized_keyword = normalize_text(keyword)

                if normalized_keyword in seen:
                    continue

                seen.add(normalized_keyword)

                specs.append({
                    "keyword": keyword,
                    "brand": str(brand).strip(),
                    "season": str(season).strip(),
                    "genre": str(genre).strip(),
                })

    return specs


def build_keywords(
    brands: list[str],
    seasons: list[str],
    genres: list[str],
) -> list[str]:
    return [
        spec["keyword"]
        for spec in build_keyword_specs(
            brands,
            seasons,
            genres,
        )
    ]


def match_candidate_brand(
    item: dict[str, Any],
    requested_brand: str,
    all_brands: list[str],
) -> str:
    api_brand = str(
        item.get("브랜드", "")
    ).strip()

    maker = str(
        item.get("제조사", "")
    ).strip()

    product_name = str(
        item.get("상품명", "")
    ).strip()

    search_order = []

    if requested_brand:
        search_order.append(requested_brand)

    search_order.extend(
        brand
        for brand in all_brands
        if brand not in search_order
    )

    combined_normalized = normalize_text(
        f"{api_brand} {maker} {product_name}"
    )

    for brand in search_order:
        standard = normalize_brand(brand)

        aliases = BRAND_ALIAS.get(
            brand,
            [brand],
        )

        alias_values = {
            normalize_text(brand),
            normalize_text(standard),
            *[
                normalize_text(alias)
                for alias in aliases
            ],
        }

        if any(
            alias
            and alias in combined_normalized
            for alias in alias_values
        ):
            return brand

    if api_brand:
        return api_brand

    return requested_brand


def determine_candidate_tags(
    product_name: str,
    spec: dict[str, str],
) -> tuple[list[str], list[str]]:
    species = extract_tags(
        product_name,
        SPECIES_TAGS,
    )

    genres = extract_tags(
        product_name,
        GENRE_TAGS,
    )

    # 상품명에 태그가 없으면 검색에 사용한 시즌/장르를 상속
    if not species and spec.get("season"):
        species = [spec["season"]]

    if not genres and spec.get("genre"):
        genres = [spec["genre"]]

    return (
        species or ["기타"],
        genres or ["기타"],
    )


def candidate_volume_query(
    species: list[str],
    genres: list[str],
    spec: dict[str, str],
) -> str:
    species_value = (
        species[0]
        if species and species[0] != "기타"
        else spec.get("season", "")
    )

    genre_value = (
        genres[0]
        if genres and genres[0] != "기타"
        else spec.get("genre", "")
    )

    parts = [
        value
        for value in [
            species_value,
            genre_value,
        ]
        if value and value != "기타"
    ]

    if parts:
        return " ".join(parts)

    # 둘 다 기타인 경우 전체 검색어를 기준으로 사용
    return spec.get("keyword", "")


def get_candidate_search_volume(
    query: str,
    local_cache: dict[str, int],
) -> int:
    normalized_query = normalize_text(query)

    if not normalized_query:
        return 0

    if normalized_query in local_cache:
        return local_cache[normalized_query]

    exact_volume = get_exact_keyword_volume(
        query,
        local_cache=None,
    )

    if exact_volume > 0:
        local_cache[normalized_query] = exact_volume
        return exact_volume

    # 정확한 키워드가 없으면 반환된 연관 키워드 중
    # 가장 가까운 키워드를 선택
    results = get_keyword_stats_list(
        [normalized_query]
    )

    query_tokens = {
        token
        for token in re.split(
            r"\s+",
            str(query).strip(),
        )
        if token
    }

    best_volume = 0
    best_score = -1

    for row in results:
        result_keyword = str(
            row.get("키워드", "")
        ).strip()

        result_normalized = normalize_text(
            result_keyword
        )

        if not result_normalized:
            continue

        overlap_score = sum(
            1
            for token in query_tokens
            if normalize_text(token) in result_normalized
        )

        if (
            overlap_score > best_score
            or (
                overlap_score == best_score
                and safe_int(row.get("총 검색량"))
                > best_volume
            )
        ):
            best_score = overlap_score
            best_volume = safe_int(
                row.get("총 검색량")
            )

    # 관련 토큰이 하나도 없으면 연관 키워드를 임의로 사용하지 않음
    if best_score <= 0:
        best_volume = 0

    local_cache[normalized_query] = best_volume

    return best_volume


def calculate_candidate_score(
    search_volume: int,
    best_rank: int,
    observed_seller_count: int = 1,
) -> int:
    if best_rank <= 0:
        return 0

    rank_score = search_volume / best_rank

    # 여러 판매처에서 관측되면 시장 검증 보너스.
    # 지나치게 큰 영향을 주지 않도록 최대 20%로 제한.
    seller_bonus = min(
        max(observed_seller_count - 1, 0) * 0.03,
        0.20,
    )

    return int(
        rank_score * (1 + seller_bonus)
    )


# =========================================================
# 11. 사입 후보 발굴
# =========================================================

def find_candidates(
    brands: list[str],
    seasons: list[str],
    genres: list[str],
    client_id: str,
    client_secret: str,
    coverage: dict[str, Any] | None,
    max_rank: int = 50,
    exclude_used_rental_overseas: bool = True,
    show_progress: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    specs = build_keyword_specs(
        brands,
        seasons,
        genres,
    )

    if not specs:
        return [], ["검색 조합이 없습니다."]

    coverage = coverage or {
        "group_coverage": set(),
        "product_ids": set(),
        "fingerprints": set(),
        "model_codes": set(),
        "normalized_names": set(),
    }

    max_rank = min(
        max(safe_int(max_rank, 50), 1),
        100,
    )

    volume_cache: dict[str, int] = {}
    candidates: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    progress = (
        st.progress(
            0,
            text="사입 후보 수집 준비 중...",
        )
        if show_progress
        else None
    )

    for spec_index, spec in enumerate(specs):
        keyword = spec["keyword"]

        if progress is not None:
            progress.progress(
                spec_index / max(len(specs), 1),
                text=(
                    f"🔍 [{spec_index + 1}/{len(specs)}] "
                    f"{keyword}"
                ),
            )

        items, error = collect_rank_light(
            keyword=keyword,
            client_id=client_id,
            client_secret=client_secret,
            limit=max_rank,
            exclude_used_rental_overseas=(
                exclude_used_rental_overseas
            ),
        )

        if error:
            errors.append(
                f"{keyword}: {error}"
            )
            continue

        for item in items:
            if is_our_shop_item({
                "mallName": item.get("판매처", ""),
                "title": item.get("상품명", ""),
                "productType": item.get("productType", 0),
            }):
                continue

            rank = safe_int(item.get("순위"))
            product_name = str(
                item.get("상품명", "")
            ).strip()
            mall_name = str(
                item.get("판매처", "")
            ).strip()

            matched_brand = match_candidate_brand(
                item=item,
                requested_brand=spec.get("brand", ""),
                all_brands=brands,
            )

            # 브랜드를 명시했는데 실제 상품에서 전혀 확인되지 않는 경우 제외
            if spec.get("brand"):
                requested_standard = normalize_brand(
                    spec["brand"]
                )
                matched_standard = normalize_brand(
                    matched_brand
                )

                if (
                    not matched_brand
                    or requested_standard
                    != matched_standard
                ):
                    continue

            brand_key = normalize_brand(
                matched_brand
            )

            species, item_genres = determine_candidate_tags(
                product_name=product_name,
                spec=spec,
            )

            group_owned = any(
                (
                    brand_key,
                    species_value,
                    genre_value,
                )
                in coverage.get(
                    "group_coverage",
                    set(),
                )
                for species_value in species
                for genre_value in item_genres
            )

            same_product, match_reason = is_same_owned_product(
                item=item,
                matched_brand=matched_brand,
                coverage=coverage,
            )

            volume_query = candidate_volume_query(
                species=species,
                genres=item_genres,
                spec=spec,
            )

            search_volume = get_candidate_search_volume(
                query=volume_query,
                local_cache=volume_cache,
            )

            candidate_key = make_candidate_key(
                item=item,
                matched_brand=matched_brand,
            )

            price = safe_int(item.get("가격"))

            if candidate_key not in candidates:
                candidates[candidate_key] = {
                    "productId": str(
                        item.get("productId", "")
                    ),
                    "검색키워드": keyword,
                    "검색키워드목록": {keyword},
                    "브랜드": matched_brand,
                    "API브랜드": item.get("브랜드", ""),
                    "제조사": item.get("제조사", ""),
                    "타사 상품명": product_name,
                    "대표판매처": mall_name,
                    "최고순위": rank,
                    "대표가격": price,
                    "어종": ", ".join(species),
                    "장르": ", ".join(item_genres),
                    "검색량기준": volume_query,
                    "키워드검색량": search_volume,
                    "제품군 취급여부": (
                        "이미 취급군"
                        if group_owned
                        else "🆕 미취급군"
                    ),
                    "동일제품 취급여부": (
                        "동일제품 있음"
                        if same_product
                        else "🆕 동일제품 없음"
                    ),
                    "동일판정근거": match_reason,
                    "카테고리1": item.get("카테고리1", ""),
                    "카테고리2": item.get("카테고리2", ""),
                    "카테고리3": item.get("카테고리3", ""),
                    "카테고리4": item.get("카테고리4", ""),
                    "productType": safe_int(
                        item.get("productType")
                    ),
                    "링크": safe_url(
                        item.get("링크", "")
                    ),

from __future__ import annotations

import json
import logging
import re
import time
from datetime import timedelta
from typing import Any, Iterable

import pandas as pd
import streamlit as st

from fishing_core import (
    AD_HISTORY_HEADERS,
    AD_HISTORY_SHEET,
    TARGET_STORE,
    ad_api_get,
    append_raw_rows,
    clean_naver_title,
    collect_rank_light,
    ensure_worksheet_headers,
    get_exact_keyword_volume,
    get_google_sheet,
    get_keyword_stats_list,
    get_or_create_worksheet,
    is_our_shop_item,
    make_hash,
    normalize_product_name,
    normalize_text,
    now_kst,
    now_text,
    safe_float,
    safe_int,
    safe_url,
    worksheet_records_safe,
)

logger = logging.getLogger(__name__)


# =========================================================
# 0. 엑셀 공통 함수
# =========================================================

def find_column(
    columns: Iterable[Any],
    candidates: Iterable[str],
) -> str | None:
    columns = [str(c).strip() for c in columns]
    candidates = [str(c).strip() for c in candidates]

    # 정확히 일치하는 열 우선
    for candidate in candidates:
        for column in columns:
            if column == candidate:
                return column

    # 일부 문자열 포함
    for candidate in candidates:
        for column in columns:
            if candidate in column:
                return column

    return None


def numeric_series(
    df: pd.DataFrame,
    column: str | None,
    default: float = 0,
) -> pd.Series:
    if column and column in df.columns:
        return pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(default)

    return pd.Series(
        [default] * len(df),
        index=df.index,
        dtype="float64",
    )


def text_series(
    df: pd.DataFrame,
    column: str | None,
) -> pd.Series:
    if column and column in df.columns:
        return (
            df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    return pd.Series(
        [""] * len(df),
        index=df.index,
        dtype="object",
    )


def read_excel_safely(
    uploaded_file,
    dtype: Any = None,
) -> tuple[pd.DataFrame | None, str | None]:
    try:
        df = pd.read_excel(
            uploaded_file,
            dtype=dtype,
            engine="openpyxl",
        )

        if df is None or df.empty:
            return None, "엑셀 파일에 데이터가 없습니다."

        df.columns = [
            str(column).strip()
            for column in df.columns
        ]

        return df, None

    except Exception as exc:
        logger.exception("엑셀 파일 읽기 실패")
        return None, f"엑셀 파일 읽기 오류: {exc}"


# =========================================================
# 1. 광고 API
# =========================================================

@st.cache_data(ttl=300, max_entries=5)
def ad_get_campaigns():
    data, error = ad_api_get("/ncc/campaigns")

    if error:
        return [], error

    if not isinstance(data, list):
        return [], "캠페인 API 응답 형식이 올바르지 않습니다."

    return data, None


@st.cache_data(ttl=300, max_entries=100)
def ad_get_adgroups(campaign_id: str):
    data, error = ad_api_get(
        "/ncc/adgroups",
        params={"nccCampaignId": campaign_id},
    )

    if error:
        return [], error

    if not isinstance(data, list):
        return [], "광고그룹 API 응답 형식이 올바르지 않습니다."

    return data, None


@st.cache_data(ttl=300, max_entries=500)
def ad_get_ads(adgroup_id: str):
    data, error = ad_api_get(
        "/ncc/ads",
        params={"nccAdgroupId": adgroup_id},
    )

    if error:
        return [], error

    if not isinstance(data, list):
        return [], "광고 소재 API 응답 형식이 올바르지 않습니다."

    return data, None


@st.cache_data(ttl=300, max_entries=500)
def ad_get_stats(
    ids_tuple: tuple[str, ...],
    days: int = 7,
):
    ids = [
        str(item_id).strip()
        for item_id in ids_tuple
        if str(item_id).strip()
    ]

    if not ids:
        return {}, []

    days = max(1, min(safe_int(days, 7), 90))

    until = now_kst().strftime("%Y-%m-%d")
    since = (
        now_kst() - timedelta(days=days)
    ).strftime("%Y-%m-%d")

    fields = [
        "impCnt",
        "clkCnt",
        "ctr",
        "cpc",
        "salesAmt",
        "avgRnk",
        "ccnt",
    ]

    time_range = {
        "since": since,
        "until": until,
    }

    results = {}
    errors = []

    for start_index in range(0, len(ids), 100):
        chunk = ids[start_index:start_index + 100]

        params = {
            "ids": chunk,
            "fields": json.dumps(fields),
            "timeRange": json.dumps(time_range),
        }

        data, error = ad_api_get(
            "/stats",
            params=params,
        )

        if error:
            errors.append(error)
            continue

        rows = (
            data.get("data", [])
            if isinstance(data, dict)
            else []
        )

        for row in rows:
            result_id = str(row.get("id", "")).strip()

            if not result_id:
                continue

            results[result_id] = {
                "impCnt": safe_int(row.get("impCnt")),
                "clkCnt": safe_int(row.get("clkCnt")),
                "ctr": safe_float(row.get("ctr")),
                "cpc": safe_float(row.get("cpc")),
                "salesAmt": safe_float(row.get("salesAmt")),
                "avgRnk": safe_float(row.get("avgRnk")),
                "ccnt": safe_int(row.get("ccnt")),
            }

        time.sleep(0.15)

    return results, errors


# =========================================================
# 2. 광고 진단 로직
# =========================================================

def recommend_bid(
    impressions: float,
    ctr: float,
    average_rank: float,
    bid_amount: Any,
) -> str | None:
    current = safe_int(bid_amount)

    if current <= 0:
        return None

    if impressions <= 0:
        suggested = max(
            current + 10,
            int(round(current * 1.3, -1)),
        )

        return (
            f"💰 노출이 없어 입찰가 상향 검토: "
            f"{current:,}원 → 약 {suggested:,}원. "
            "예산·비즈머니·소재 상태도 함께 확인하세요."
        )

    if average_rank >= 5:
        suggested = max(
            current + 10,
            int(round(current * 1.2, -1)),
        )

        return (
            f"💰 평균순위가 낮아 입찰가 상향 검토: "
            f"{current:,}원 → 약 {suggested:,}원."
        )

    if (
        0 < average_rank < 3
        and ctr >= 1.0
        and impressions >= 100
    ):
        suggested = max(
            10,
            int(round(current * 0.9, -1)),
        )

        return (
            f"💰 순위·CTR이 양호합니다. "
            f"{current:,}원 → 약 {suggested:,}원으로 "
            "소폭 낮춘 뒤 순위를 관찰할 수 있습니다."
        )

    return f"💰 현재 입찰가 {current:,}원 유지가 무난합니다."


def diagnose_ad(
    stat: dict[str, Any],
    bid_amount: Any = None,
    quality_grade: Any = None,
    is_active: bool = True,
):
    if not is_active:
        return (
            "⚪",
            "꺼짐 (집행 안 됨)",
            ["캠페인·광고그룹·소재의 ON/OFF를 확인하세요."],
            0,
        )

    impressions = safe_float(stat.get("impCnt"))
    ctr = safe_float(stat.get("ctr"))
    average_rank = safe_float(stat.get("avgRnk"))
    quality = safe_int(quality_grade)

    advice = []

    bid_tip = recommend_bid(
        impressions,
        ctr,
        average_rank,
        bid_amount,
    )

    if bid_tip:
        advice.append(bid_tip)

    if quality > 0:
        if quality <= 3:
            advice.append(
                f"품질지수 {quality}/10으로 낮습니다. "
                "상품명·대표 이미지·가격·리뷰를 우선 개선하세요."
            )
        elif quality <= 6:
            advice.append(
                f"품질지수 {quality}/10으로 보통입니다. "
                "CTR을 개선하면 노출 효율이 좋아질 수 있습니다."
            )

    if impressions <= 0:
        advice.extend([
            "입찰가 부족, 예산 소진, 비즈머니 부족 여부를 확인하세요.",
            "캠페인·그룹·소재가 모두 ON인지 확인하세요.",
        ])

        return "🔴", "노출 안 됨", advice, 100

    low_rank = average_rank >= 5
    low_ctr = impressions >= 100 and ctr < 0.5

    if low_rank:
        advice.append(
            f"평균 노출순위가 {average_rank:.1f}위입니다. "
            "입찰가 또는 품질지수 개선을 검토하세요."
        )

    if low_ctr:
        advice.append(
            f"CTR이 {ctr:.2f}%로 낮습니다. "
            "대표 이미지·상품명·가격을 점검하세요."
        )

    if 0 < impressions < 100:
        advice.append(
            "노출 데이터가 적습니다. 며칠 더 운영한 뒤 재진단하세요."
        )

    if low_rank and low_ctr:
        return (
            "🟠",
            "노출순위·클릭 모두 개선 필요",
            advice,
            80,
        )

    if low_rank:
        return (
            "🟡",
            "노출은 되지만 순위가 낮음",
            advice,
            60,
        )

    if low_ctr:
        return (
            "🟡",
            "노출은 되지만 클릭이 낮음",
            advice,
            55,
        )

    if quality and quality <= 3:
        return (
            "🟡",
            "품질지수 개선 권장",
            advice,
            50,
        )

    if impressions < 100:
        return (
            "🟡",
            "데이터 추가 수집 필요",
            advice,
            30,
        )

    return (
        "🟢",
        "양호",
        ["노출·클릭·순위가 비교적 안정적입니다."],
        0,
    )


def entity_is_active(
    entity: dict[str, Any],
    eligible_statuses: set[str] | None = None,
) -> bool:
    if entity.get("userLock") is True:
        return False

    status = str(entity.get("status", "")).upper()

    if status in {
        "PAUSED",
        "DELETED",
        "STOPPED",
        "DISABLED",
    }:
        return False

    if eligible_statuses and status:
        return status in eligible_statuses

    return True


def extract_ad_product_name(
    ad: dict[str, Any],
) -> str:
    ad_info = ad.get("ad") or {}
    reference = ad.get("referenceData") or {}

    candidates = [
        ad_info.get("productName"),
        reference.get("productName"),
        ad_info.get("headline"),
        ad.get("name"),
    ]

    for candidate in candidates:
        text = clean_naver_title(candidate)

        if text:
            return text

    return "(이름 없음)"


def extract_quality_grade(ad: dict[str, Any]) -> int:
    quality = ad.get("nccQi") or {}

    if isinstance(quality, dict):
        return safe_int(quality.get("qiGrade"))

    return 0


def extract_bid_amount(
    ad: dict[str, Any],
    adgroup: dict[str, Any],
) -> int:
    ad_attr = ad.get("adAttr") or {}
    bid = safe_int(ad_attr.get("bidAmt"))

    if bid > 0:
        return bid

    return safe_int(adgroup.get("bidAmt"))


def run_ad_diagnosis(
    adgroups: list[dict[str, Any]],
    campaign_name: str,
    days: int,
):
    rows = []
    errors = []

    for adgroup in adgroups:
        adgroup_id = str(
            adgroup.get("nccAdgroupId", "")
        ).strip()

        if not adgroup_id:
            continue

        adgroup_name = str(
            adgroup.get("name", "")
        ).strip()

        group_active = entity_is_active(adgroup)

        ads, ads_error = ad_get_ads(adgroup_id)

        if ads_error:
            errors.append(
                f"{campaign_name}/{adgroup_name}: {ads_error}"
            )
            continue

        ad_ids = tuple(
            str(ad.get("nccAdId", "")).strip()
            for ad in ads
            if str(ad.get("nccAdId", "")).strip()
        )

        stats, stat_errors = ad_get_stats(
            ad_ids,
            days,
        )

        errors.extend(stat_errors)

        for ad in ads:
            ad_id = str(
                ad.get("nccAdId", "")
            ).strip()

            if not ad_id:
                continue

            stat = stats.get(ad_id, {})
            quality = extract_quality_grade(ad)
            bid = extract_bid_amount(ad, adgroup)
            product_name = extract_ad_product_name(ad)

            ad_active = entity_is_active(
                ad,
                {"ELIGIBLE", "ACTIVE", "ON"},
            )

            is_active = group_active and ad_active

            icon, verdict, advice, priority = diagnose_ad(
                stat,
                bid,
                quality,
                is_active,
            )

            rows.append({
                "광고ID": ad_id,
                "상태": icon,
                "우선순위": priority,
                "캠페인": campaign_name,
                "광고그룹": adgroup_name,
                "상품명": product_name,
                "ON/OFF": "ON" if is_active else "OFF",
                "입찰가": bid,
                "품질지수": quality,
                "노출수": safe_int(stat.get("impCnt")),
                "클릭수": safe_int(stat.get("clkCnt")),
                "CTR(%)": round(
                    safe_float(stat.get("ctr")),
                    2,
                ),
                "평균순위": round(
                    safe_float(stat.get("avgRnk")),
                    1,
                ),
                "광고비": safe_int(stat.get("salesAmt")),
                "전환수": safe_int(stat.get("ccnt")),
                "진단": verdict,
                "_advice": " / ".join(advice),
            })

        time.sleep(0.1)

    rows.sort(
        key=lambda row: (
            -safe_int(row.get("우선순위")),
            -safe_int(row.get("광고비")),
        )
    )

    return rows, errors


# =========================================================
# 3. 광고 진단 기록
# =========================================================

def ensure_ad_history_sheet():
    spreadsheet = get_google_sheet()

    worksheet = get_or_create_worksheet(
        spreadsheet,
        AD_HISTORY_SHEET,
        rows=10000,
        cols=len(AD_HISTORY_HEADERS),
    )

    values = worksheet.get_all_values()

    # 구버전 광고진단 시트는 삭제하지 않고 이름을 변경해 보존
    if (
        values
        and values[0][:3]
        == ["날짜", "상품명", "노출수"]
    ):
        backup_name = (
            "광고진단_구버전_"
            + now_kst().strftime("%Y%m%d_%H%M%S")
        )

        worksheet.update_title(backup_name)

        worksheet = get_or_create_worksheet(
            spreadsheet,
            AD_HISTORY_SHEET,
            rows=10000,
            cols=len(AD_HISTORY_HEADERS),
        )

    ok, error = ensure_worksheet_headers(
        worksheet,
        AD_HISTORY_HEADERS,
    )

    if not ok:
        raise ValueError(error)

    return worksheet


def save_ad_diagnosis(
    rows: list[dict[str, Any]],
    collected_at: str | None = None,
):
    if not rows:
        return False, "저장할 광고 진단 결과가 없습니다.", ""

    try:
        worksheet = ensure_ad_history_sheet()
        collected_at = collected_at or now_text()
        sheet_rows = []

        for row in rows:
            ad_id = str(row.get("광고ID", "")).strip()

            if not ad_id:
                continue

            record_id = make_hash(
                collected_at,
                ad_id,
                row.get("캠페인", ""),
                row.get("광고그룹", ""),
            )

            sheet_rows.append([
                record_id,
                collected_at,
                ad_id,
                row.get("캠페인", ""),
                row.get("광고그룹", ""),
                row.get("상품명", ""),
                row.get("ON/OFF", ""),
                safe_int(row.get("입찰가")),
                safe_int(row.get("품질지수")),
                safe_int(row.get("노출수")),
                safe_int(row.get("클릭수")),
                safe_float(row.get("CTR(%)")),
                safe_float(row.get("평균순위")),
                safe_int(row.get("광고비")),
                row.get("진단", ""),
            ])

        append_raw_rows(
            worksheet,
            sheet_rows,
        )

        load_ad_history.clear()

        return (
            True,
            f"광고 진단 {len(sheet_rows)}건 저장 완료",
            collected_at,
        )

    except Exception as exc:
        logger.exception("광고 진단 저장 실패")
        return False, f"광고 진단 저장 오류: {exc}", ""


@st.cache_data(ttl=300, max_entries=5)
def load_ad_history():
    try:
        worksheet = ensure_ad_history_sheet()

        records, error = worksheet_records_safe(
            worksheet,
            AD_HISTORY_HEADERS,
        )

        if error:
            return []

        output = []

        for row in records:
            ad_id = str(row.get("광고ID", "")).strip()
            collected_at = str(
                row.get("수집일시", "")
            ).strip()

            if not ad_id or not collected_at:
                continue

            output.append({
                "기록ID": str(row.get("기록ID", "")),
                "수집일시": collected_at,
                "광고ID": ad_id,
                "캠페인": str(row.get("캠페인", "")),
                "광고그룹": str(row.get("광고그룹", "")),
                "상품명": str(row.get("상품명", "")),
                "ON/OFF": str(row.get("ON/OFF", "")),
                "입찰가": safe_int(row.get("입찰가")),
                "품질지수": safe_int(row.get("품질지수")),
                "노출수": safe_int(row.get("노출수")),
                "클릭수": safe_int(row.get("클릭수")),
                "CTR": safe_float(row.get("CTR")),
                "평균순위": safe_float(row.get("평균순위")),
                "광고비": safe_int(row.get("광고비")),
                "진단": str(row.get("진단", "")),
            })

        output.sort(
            key=lambda row: row["수집일시"]
        )

        return output

    except Exception:
        logger.exception("광고 기록 읽기 실패")
        return []


def load_previous_ad_snapshot(
    current_collected_at: str | None = None,
):
    history = load_ad_history()

    if not history:
        return {}, None

    snapshot_times = sorted({
        row["수집일시"]
        for row in history
        if row.get("수집일시")
    })

    if current_collected_at:
        candidates = [
            timestamp
            for timestamp in snapshot_times
            if timestamp < current_collected_at
        ]
    else:
        candidates = snapshot_times[:-1]

    if not candidates:
        return {}, None

    previous_time = candidates[-1]

    previous_map = {
        row["광고ID"]: row
        for row in history
        if (
            row["수집일시"] == previous_time
            and row.get("광고ID")
        )
    }

    return previous_map, previous_time


def compare_ad_snapshots(
    current_rows: list[dict[str, Any]],
    previous_map: dict[str, dict[str, Any]],
):
    changes = []

    for current in current_rows:
        ad_id = str(current.get("광고ID", "")).strip()
        previous = previous_map.get(ad_id)

        if not previous:
            continue

        current_imp = safe_int(current.get("노출수"))
        previous_imp = safe_int(previous.get("노출수"))

        current_rank = safe_float(
            current.get("평균순위")
        )
        previous_rank = safe_float(
            previous.get("평균순위")
        )

        current_ctr = safe_float(
            current.get("CTR(%)")
        )
        previous_ctr = safe_float(
            previous.get("CTR")
        )

        reasons = []
        severity = 0

        if (
            previous_imp > 0
            and current_imp < previous_imp * 0.7
        ):
            drop_rate = round(
                (1 - current_imp / previous_imp) * 100
            )

            reasons.append(
                f"노출 {drop_rate}% 감소 "
                f"({previous_imp:,} → {current_imp:,})"
            )

            severity += drop_rate

        if (
            previous_rank > 0
            and current_rank > 0
            and current_rank - previous_rank >= 3
        ):
            reasons.append(
                f"순위 하락 "
                f"({previous_rank:.1f}위 → {current_rank:.1f}위)"
            )

            severity += int(
                (current_rank - previous_rank) * 10
            )

        if (
            previous_ctr >= 0.5
            and current_ctr < previous_ctr * 0.7
        ):
            reasons.append(
                f"CTR 감소 "
                f"({previous_ctr:.2f}% → {current_ctr:.2f}%)"
            )

            severity += 20

        if reasons:
            changes.append({
                "광고ID": ad_id,
                "상품명": current.get("상품명", ""),
                "캠페인": current.get("캠페인", ""),
                "변화": " / ".join(reasons),
                "심각도": severity,
            })

    changes.sort(
        key=lambda row: -safe_int(row.get("심각도"))
    )

    return changes
# =========================================================
# 4. SEO 분석
# =========================================================

SEO_SPECIAL_CHARACTERS = {
    "!", "@", "#", "$", "%", "^", "&", "*", "~", "+"
}


def generate_recommended_name(
    keyword: str,
    original_name: str,
    selected_related_keywords: list[str],
    max_length: int = 40,
) -> str:
    keyword = str(keyword).strip()
    original_name = clean_naver_title(original_name)

    base = original_name.replace(
        TARGET_STORE,
        "",
    ).strip()

    base = re.sub(r"\s+", " ", base)

    if (
        keyword
        and normalize_text(keyword)
        not in normalize_text(base)
    ):
        base = f"{keyword} {base}".strip()

    for related_keyword in selected_related_keywords:
        related_keyword = str(
            related_keyword
        ).strip()

        if not related_keyword:
            continue

        if (
            normalize_text(related_keyword)
            in normalize_text(base)
        ):
            continue

        candidate = f"{base} {related_keyword}".strip()

        if len(candidate) <= 35:
            base = candidate

    with_store = f"{base} {TARGET_STORE}".strip()

    if len(with_store) <= max_length:
        return with_store

    return base[:max_length].strip()


def analyze_seo(
    keyword: str,
    product_name: str,
    selected_related_keywords: list[str],
) -> dict[str, Any]:
    issues = []
    good_points = []
    score = 100

    product_name = clean_naver_title(product_name)
    name_length = len(product_name)

    if name_length < 15:
        issues.append((
            "❌ 상품명이 너무 짧음",
            f"현재 {name_length}자입니다. "
            "상품 특성을 포함해 25~40자 수준을 검토하세요.",
        ))
        score -= 20

    elif name_length > 50:
        issues.append((
            "⚠️ 상품명이 너무 김",
            f"현재 {name_length}자입니다. "
            "핵심 키워드와 모델명 중심으로 정리하세요.",
        ))
        score -= 10

    else:
        good_points.append(
            f"✅ 상품명 길이가 적정합니다 ({name_length}자)."
        )

    normalized_keyword = normalize_text(keyword)
    normalized_name = normalize_text(product_name)

    if (
        normalized_keyword
        and normalized_keyword in normalized_name
    ):
        good_points.append(
            f"✅ 핵심 키워드 '{keyword}'가 포함되어 있습니다."
        )
    else:
        issues.append((
            "❌ 핵심 키워드 미포함",
            f"상품과 관련 있다면 '{keyword}'를 추가하세요.",
        ))
        score -= 30

    found_specials = [
        character
        for character in product_name
        if character in SEO_SPECIAL_CHARACTERS
    ]

    if len(found_specials) > 2:
        issues.append((
            "⚠️ 특수문자 과다",
            "특수문자는 필요한 것만 남기는 것을 권장합니다.",
        ))
        score -= 10
    else:
        good_points.append(
            "✅ 특수문자 사용량이 많지 않습니다."
        )

    if product_name.startswith(TARGET_STORE):
        issues.append((
            "⚠️ 상호명이 상품명 맨 앞에 있음",
            "핵심 상품 키워드와 모델명을 먼저 배치해 보세요.",
        ))
        score -= 10
    else:
        good_points.append(
            "✅ 핵심 상품 정보가 상호명보다 앞에 있습니다."
        )

    words = [
        word.strip()
        for word in product_name.split()
        if len(word.strip()) > 1
    ]

    duplicate_words = sorted({
        word
        for word in words
        if words.count(word) > 1
    })

    if duplicate_words:
        issues.append((
            "⚠️ 중복 단어",
            f"{', '.join(duplicate_words)} 단어가 반복됩니다.",
        ))
        score -= 10
    else:
        good_points.append(
            "✅ 동일 단어가 과도하게 반복되지 않습니다."
        )

    included = []
    not_included = []

    for related_keyword in selected_related_keywords:
        if (
            normalize_text(related_keyword)
            in normalized_name
        ):
            included.append(related_keyword)
        else:
            not_included.append(related_keyword)

    if included:
        good_points.append(
            "✅ 포함된 연관 키워드: "
            + ", ".join(included)
        )

    if not_included:
        issues.append((
            "💡 추가 검토 가능한 연관 키워드",
            ", ".join(not_included)
            + " 중 상품과 직접 관련 있는 키워드만 사용하세요.",
        ))

    score = max(0, min(score, 100))

    return {
        "score": score,
        "issues": issues,
        "goods": good_points,
        "recommended_name": generate_recommended_name(
            keyword,
            product_name,
            selected_related_keywords,
        ),
        "related_keywords": selected_related_keywords,
        "notice": (
            "SEO 점수는 내부 점검용 기준이며, "
            "네이버 검색순위를 보장하는 공식 기준이 아닙니다."
        ),
    }


# =========================================================
# 5. 채널 분석
# =========================================================

def analyze_channel_file(uploaded_file):
    df, error = read_excel_safely(uploaded_file)

    if error:
        return None, error

    channel_property = find_column(
        df.columns,
        ["채널속성"],
    )
    channel_group = find_column(
        df.columns,
        ["채널그룹"],
    )
    channel_name = find_column(
        df.columns,
        ["채널명"],
    )
    visits = find_column(
        df.columns,
        ["유입수"],
    )
    payment_count = find_column(
        df.columns,
        ["결제수(마지막클릭)", "결제수"],
    )
    payment_amount = find_column(
        df.columns,
        ["결제금액(마지막클릭)", "결제금액"],
    )

    if not visits:
        return (
            None,
            "'유입수' 열을 찾지 못했습니다. "
            f"현재 열: {list(df.columns)}",
        )

    output = pd.DataFrame({
        "채널속성": text_series(
            df,
            channel_property,
        ),
        "채널그룹": text_series(
            df,
            channel_group,
        ),
        "채널명": text_series(
            df,
            channel_name,
        ),
        "유입수": numeric_series(
            df,
            visits,
        ),
        "결제수": numeric_series(
            df,
            payment_count,
        ),
        "결제금액": numeric_series(
            df,
            payment_amount,
        ),
    })

    output["결제율(%)"] = (
        output["결제수"]
        .div(output["유입수"].replace(0, pd.NA))
        .mul(100)
        .fillna(0)
        .round(2)
    )

    output["객단가"] = (
        output["결제금액"]
        .div(output["결제수"].replace(0, pd.NA))
        .fillna(0)
        .round()
        .astype(int)
    )

    return output, None


# =========================================================
# 6. 상품 분석
# =========================================================

def analyze_product_file(uploaded_file):
    df, error = read_excel_safely(uploaded_file)

    if error:
        return None, error

    name_column = find_column(
        df.columns,
        ["상품명", "제품명"],
    )
    product_id_column = find_column(
        df.columns,
        ["상품ID", "상품번호"],
    )
    views_column = find_column(
        df.columns,
        ["상품상세조회수", "상세조회수"],
    )
    payment_amount_column = find_column(
        df.columns,
        ["결제금액"],
    )
    payment_quantity_column = find_column(
        df.columns,
        ["결제상품수량", "결제수량"],
    )
    conversion_column = find_column(
        df.columns,
        [
            "상세조회대비결제율",
            "결제율",
            "전환율",
        ],
    )

    if not name_column:
        return (
            None,
            "'상품명' 열을 찾지 못했습니다. "
            f"현재 열: {list(df.columns)}",
        )

    output = pd.DataFrame({
        "상품명": text_series(
            df,
            name_column,
        ),
        "상품ID": text_series(
            df,
            product_id_column,
        ),
        "조회수": numeric_series(
            df,
            views_column,
        ),
        "결제금액": numeric_series(
            df,
            payment_amount_column,
        ),
        "결제수량": numeric_series(
            df,
            payment_quantity_column,
        ),
        "결제율": numeric_series(
            df,
            conversion_column,
        ),
    })

    positive_views = output.loc[
        output["조회수"] > 0,
        "조회수",
    ]

    positive_rates = output.loc[
        output["결제율"] > 0,
        "결제율",
    ]

    view_median = (
        positive_views.median()
        if not positive_views.empty
        else 0
    )

    rate_median = (
        positive_rates.median()
        if not positive_rates.empty
        else 0
    )

    def classify(row):
        views = safe_float(row["조회수"])
        rate = safe_float(row["결제율"])

        if views <= 0:
            return "⚪ 데이터없음"

        high_view = (
            view_median > 0
            and views >= view_median
        )

        high_rate = (
            rate_median > 0
            and rate >= rate_median
        )

        if high_view and high_rate:
            return "🟢 효자상품"

        if high_view and not high_rate:
            return "🔴 개선필요"

        if not high_view and high_rate:
            return "🟡 숨은보석"

        return "⚪ 정리검토"

    output["분류"] = output.apply(
        classify,
        axis=1,
    )

    return output, None


# =========================================================
# 7. 검색어 분석
# =========================================================

def analyze_search_file(uploaded_file):
    df, error = read_excel_safely(uploaded_file)

    if error:
        return None, [], error

    columns = list(df.columns)

    keyword_column = find_column(
        columns,
        ["키워드", "검색어"],
    )
    visits_column = find_column(
        columns,
        ["유입수"],
    )
    payment_count_column = find_column(
        columns,
        ["결제수"],
    )
    payment_amount_column = find_column(
        columns,
        ["결제금액"],
    )

    if not keyword_column:
        return (
            None,
            columns,
            "'키워드' 또는 '검색어' 열을 찾지 못했습니다.",
        )

    if not visits_column:
        return (
            None,
            columns,
            "'유입수' 열을 찾지 못했습니다.",
        )

    output = pd.DataFrame({
        "검색어": text_series(
            df,
            keyword_column,
        ),
        "유입수": numeric_series(
            df,
            visits_column,
        ),
        "결제수": numeric_series(
            df,
            payment_count_column,
        ),
        "결제금액": numeric_series(
            df,
            payment_amount_column,
        ),
    })

    output = output[
        ~output["검색어"].isin({
            "(검색어 없음)",
            "nan",
            "None",
            "",
        })
    ]

    output = (
        output
        .groupby("검색어", as_index=False)
        .agg({
            "유입수": "sum",
            "결제수": "sum",
            "결제금액": "sum",
        })
    )

    output["결제율(%)"] = (
        output["결제수"]
        .div(output["유입수"].replace(0, pd.NA))
        .mul(100)
        .fillna(0)
        .round(2)
    )

    output = output.sort_values(
        ["결제금액", "유입수"],
        ascending=[False, False],
    )

    return output, columns, None


# =========================================================
# 8. 여러 주문 엑셀 통합
# =========================================================

def read_multiple_excel_files(uploaded_files):
    if not uploaded_files:
        return None, [], ["업로드된 파일이 없습니다."]

    if not isinstance(uploaded_files, (list, tuple)):
        uploaded_files = [uploaded_files]

    frames = []
    errors = []

    for uploaded_file in uploaded_files:
        df, error = read_excel_safely(
            uploaded_file,
            dtype=str,
        )

        if error:
            file_name = getattr(
                uploaded_file,
                "name",
                "파일",
            )

            errors.append(
                f"{file_name}: {error}"
            )
            continue

        frames.append(df.fillna(""))

    if not frames:
        return None, [], errors

    combined = pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    ).fillna("")

    return combined, list(combined.columns), errors


# =========================================================
# 9. 특정 상품의 교차구매 분석
# =========================================================

def analyze_cross_purchase(
    uploaded_files,
    target_query: str,
    ours_ids: set[str] | None = None,
):
    df, columns, file_errors = read_multiple_excel_files(
        uploaded_files
    )

    if df is None:
        return None, columns, None, file_errors

    order_column = find_column(
        columns,
        ["주문번호", "주문 번호", "구매번호"],
    )
    name_column = find_column(
        columns,
        ["상품명", "상품 명", "제품명"],
    )
    product_id_column = find_column(
        columns,
        ["상품번호", "상품 번호", "상품ID"],
    )

    if not order_column or not name_column:
        return None, columns, None, file_errors

    df[order_column] = (
        df[order_column]
        .astype(str)
        .str.strip()
    )

    df[name_column] = (
        df[name_column]
        .astype(str)
        .str.strip()
    )

    if product_id_column:
        df[product_id_column] = (
            df[product_id_column]
            .astype(str)
            .str.strip()
        )

    df = df[
        df[order_column] != ""
    ].copy()

    query = str(target_query).strip()

    if not query:
        return [], columns, 0, file_errors

    target_mask = df[name_column].str.contains(
        query,
        na=False,
        regex=False,
    )

    if product_id_column:
        target_mask = target_mask | (
            df[product_id_column] == query
        )

    target_orders = set(
        df.loc[
            target_mask,
            order_column,
        ].unique()
    )

    if not target_orders:
        return [], columns, 0, file_errors

    related = df[
        df[order_column].isin(target_orders)
    ].copy()

    related_target_mask = (
        related[name_column]
        .str.contains(
            query,
            na=False,
            regex=False,
        )
    )

    if product_id_column:
        related_target_mask = related_target_mask | (
            related[product_id_column] == query
        )

    others = related[
        ~related_target_mask
        & (related[name_column] != "")
    ].copy()

    if others.empty:
        return [], columns, len(target_orders), file_errors

    group_columns = [name_column]

    if product_id_column:
        group_columns.insert(
            0,
            product_id_column,
        )

    # 동일 주문에서 같은 상품이 여러 줄이어도 1건으로 계산
    unique_order_products = (
        others[
            [order_column] + group_columns
        ]
        .drop_duplicates()
    )

    grouped = (
        unique_order_products
        .groupby(
            group_columns,
            dropna=False,
        )[order_column]
        .nunique()
        .reset_index(name="함께 구매 주문수")
    )

    ours_ids = {
        str(product_id).strip()
        for product_id in (ours_ids or set())
        if str(product_id).strip()
    }

    total_orders = len(target_orders)
    rows = []

    for _, row in grouped.iterrows():
        product_name = str(
            row[name_column]
        ).strip()

        product_id = (
            str(row[product_id_column]).strip()
            if product_id_column
            else ""
        )

        together_orders = safe_int(
            row["함께 구매 주문수"]
        )

        if product_id and ours_ids:
            is_ours = product_id in ours_ids
        else:
            is_ours = TARGET_STORE in product_name

        rows.append({
            "상품번호": product_id,
            "함께 산 상품": product_name,
            "함께 구매 주문수": together_orders,
            "동시구매율(%)": round(
                together_orders / total_orders * 100,
                1,
            ),
            "우리 제품": "✅" if is_ours else "",
        })

    rows.sort(
        key=lambda row: (
            -safe_int(row["함께 구매 주문수"]),
            str(row["함께 산 상품"]),
        )
    )

    return rows, columns, total_orders, file_errors


# =========================================================
# 10. 상품 마스터 읽기
# =========================================================

def load_product_master(
    master_file,
    our_brand: str = TARGET_STORE,
):
    df, error = read_excel_safely(
        master_file,
        dtype=str,
    )

    if error:
        return None, {}, error

    df = df.fillna("")
    columns = list(df.columns)

    product_id_column = find_column(
        columns,
        ["상품번호", "상품 번호", "상품ID"],
    )
    division_column = find_column(
        columns,
        ["구분", "브랜드", "자사/타사"],
    )
    name_column = find_column(
        columns,
        ["상품명", "상품 명", "제품명"],
    )

    if not product_id_column or not division_column:
        return (
            None,
            {},
            "'상품번호' 또는 '구분/브랜드' 열을 찾지 못했습니다. "
            f"현재 열: {columns}",
        )

    df[product_id_column] = (
        df[product_id_column]
        .astype(str)
        .str.strip()
    )

    df[division_column] = (
        df[division_column]
        .astype(str)
        .str.strip()
    )

    if name_column:
        df[name_column] = (
            df[name_column]
            .astype(str)
            .str.strip()
        )

    normalized_our_brand = normalize_text(
        our_brand
    )

    ours_mask = df[division_column].apply(
        lambda value: (
            normalized_our_brand
            in normalize_text(value)
        )
    )

    ours_ids = set(
        df.loc[
            ours_mask,
            product_id_column,
        ]
    )

    ours_ids.discard("")

    product_names = {}

    for _, row in df.iterrows():
        product_id = str(
            row[product_id_column]
        ).strip()

        if not product_id:
            continue

        product_name = (
            str(row[name_column]).strip()
            if name_column
            else ""
        )

        if product_id not in product_names:
            product_names[product_id] = product_name

    return ours_ids, product_names, None


# =========================================================
# 11. 타사 상품별 자사 동반구매율
# =========================================================

def analyze_brand_contribution(
    uploaded_files,
    ours_ids: set[str],
    min_orders: int = 3,
):
    df, columns, file_errors = read_multiple_excel_files(
        uploaded_files
    )

    if df is None:
        return None, columns, 0, file_errors

    order_column = find_column(
        columns,
        ["주문번호", "주문 번호", "구매번호"],
    )
    product_id_column = find_column(
        columns,
        ["상품번호", "상품 번호", "상품ID"],
    )
    name_column = find_column(
        columns,
        ["상품명", "상품 명", "제품명"],
    )

    if not order_column or not product_id_column:
        return None, columns, 0, file_errors

    df[order_column] = (
        df[order_column]
        .astype(str)
        .str.strip()
    )

    df[product_id_column] = (
        df[product_id_column]
        .astype(str)
        .str.strip()
    )

    if name_column:
        df[name_column] = (
            df[name_column]
            .astype(str)
            .str.strip()
        )

    df = df[
        (df[order_column] != "")
        & (df[product_id_column] != "")
    ].copy()

    ours_ids = {
        str(product_id).strip()
        for product_id in ours_ids
        if str(product_id).strip()
    }

    orders_with_ours = set(
        df.loc[
            df[product_id_column].isin(ours_ids),
            order_column,
        ].unique()
    )

    product_name_map = {}

    if name_column:
        for _, row in df.iterrows():
            product_id = str(
                row[product_id_column]
            ).strip()

            product_name = str(
                row[name_column]
            ).strip()

            if (
                product_id
                and product_name
                and product_id not in product_name_map
            ):
                product_name_map[product_id] = product_name

    # 한 주문에서 같은 상품이 여러 줄이어도 1건
    order_product_pairs = df[
        [order_column, product_id_column]
    ].drop_duplicates()

    competitor_pairs = order_product_pairs[
        ~order_product_pairs[
            product_id_column
        ].isin(ours_ids)
    ]

    min_orders = max(
        1,
        safe_int(min_orders, 3),
    )

    rows = []
    all_competitor_orders = set()

    for product_id, group in competitor_pairs.groupby(
        product_id_column
    ):
        order_ids = set(group[order_column])
        total_orders = len(order_ids)

        if total_orders < min_orders:
            continue

        with_ours = len(
            order_ids & orders_with_ours
        )

        rate = (
            round(
                with_ours / total_orders * 100,
                1,
            )
            if total_orders
            else 0
        )

        all_competitor_orders |= order_ids

        rows.append({
            "타사 상품번호": product_id,
            "타사 제품": product_name_map.get(
                product_id,
                "",
            ),
            "주문 건수": total_orders,
            "자사 동반 주문": with_ours,
            "자사 동반구매율(%)": rate,
        })

    rows.sort(
        key=lambda row: (
            -safe_float(row["자사 동반구매율(%)"]),
            -safe_int(row["주문 건수"]),
        )
    )

    return (
        rows,
        columns,
        len(all_competitor_orders),
        file_errors,
    )
# =========================================================
# 12. 사입 후보 분석용 태그 사전
# =========================================================

SPECIES_TAGS = {
    "갈치": [
        "갈치",
        "텐빈",
        "텐야",
        "사벨",
        "사벨피쉬",
    ],
    "주꾸미": [
        "주꾸미",
        "쭈꾸미",
        "갑오징어",
    ],
    "무늬오징어": [
        "무늬오징어",
        "에깅",
        "아오리",
    ],
    "참돔": [
        "참돔",
        "타이라바",
        "러버지깅",
    ],
    "볼락": [
        "볼락",
        "메바루",
        "볼락루어",
    ],
    "광어": [
        "광어",
        "대광어",
        "다운샷",
    ],
    "농어": [
        "농어",
        "시배스",
    ],
    "우럭": [
        "우럭",
        "조피볼락",
    ],
    "한치": [
        "한치",
        "이카메탈",
        "오모리그",
    ],
    "문어": [
        "문어",
        "피문어",
        "대왕문어",
        "돌문어",
    ],
    "고등어": [
        "고등어",
    ],
    "전갱이": [
        "전갱이",
        "아징",
    ],
    "감성돔": [
        "감성돔",
        "감시",
    ],
    "삼치": [
        "삼치",
    ],
    "대구": [
        "대구",
        "대구라바",
    ],
    "민물": [
        "민물",
        "붕어",
        "잉어",
    ],
}


GENRE_TAGS = {
    "로드": [
        "로드",
        "낚싯대",
        "낚시대",
        "선상대",
        "루어대",
    ],
    "릴": [
        "릴",
        "베이트릴",
        "스피닝릴",
        "전동릴",
        "장구통릴",
    ],
    "루어": [
        "루어",
        "웜",
        "지그",
        "메탈",
        "에기",
        "미노우",
        "스푼",
    ],
    "채비": [
        "채비",
        "봉돌",
        "바늘",
        "도래",
        "기둥줄",
        "스냅",
        "편대",
    ],
    "라인": [
        "라인",
        "원줄",
        "쇼크리더",
        "합사",
        "목줄",
        "카본줄",
        "나일론줄",
    ],
    "소품": [
        "케이스",
        "가방",
        "수납",
        "집게",
        "플라이어",
        "가위",
        "태클박스",
        "로드벨트",
    ],
    "의류": [
        "낚시복",
        "구명복",
        "구명조끼",
        "장갑",
        "모자",
    ],
}


BRAND_ALIAS = {
    "백경": [
        "백경",
        "bkc",
    ],
    "시마노": [
        "시마노",
        "shimano",
    ],
    "다이와": [
        "다이와",
        "daiwa",
    ],
    "아부가르시아": [
        "아부가르시아",
        "abugarcia",
        "abu garcia",
    ],
    "메이호": [
        "메이호",
        "meiho",
    ],
    "하야부사": [
        "하야부사",
        "hayabusa",
    ],
    "오너": [
        "오너",
        "owner",
    ],
}


# =========================================================
# 13. 브랜드·태그·모델명 정규화
# =========================================================

def normalize_brand(raw_brand: Any) -> str:
    normalized = normalize_text(raw_brand)

    if not normalized:
        return ""

    for standard_brand, aliases in BRAND_ALIAS.items():
        alias_values = [
            standard_brand,
            *aliases,
        ]

        for alias in alias_values:
            normalized_alias = normalize_text(alias)

            if not normalized_alias:
                continue

            if (
                normalized == normalized_alias
                or normalized_alias in normalized
            ):
                return normalize_text(standard_brand)

    return normalized


def get_brand_aliases(raw_brand: Any) -> set[str]:
    """
    입력된 브랜드와 연결되는 한글·영문 별칭을 반환한다.
    """
    normalized_input = normalize_brand(raw_brand)
    aliases = {
        normalize_text(raw_brand),
        normalized_input,
    }

    for standard_brand, registered_aliases in BRAND_ALIAS.items():
        if normalize_brand(standard_brand) != normalized_input:
            continue

        aliases.add(normalize_text(standard_brand))

        for alias in registered_aliases:
            aliases.add(normalize_text(alias))

    aliases.discard("")

    return aliases


def extract_tags(
    product_name: Any,
    tag_dictionary: dict[str, list[str]],
) -> list[str]:
    normalized_name = normalize_text(product_name)

    if not normalized_name:
        return []

    found_tags = []

    for tag, keywords in tag_dictionary.items():
        matched = any(
            normalize_text(keyword) in normalized_name
            for keyword in keywords
            if normalize_text(keyword)
        )

        if matched:
            found_tags.append(tag)

    return found_tags


def extract_model_codes(
    product_name: Any,
) -> list[str]:
    """
    영문+숫자가 함께 포함된 모델 코드 후보를 추출한다.

    단순 규격 숫자만 있는 값은 모델 코드로 사용하지 않는다.
    """
    text = clean_naver_title(
        product_name
    ).upper()

    patterns = [
        r"\b[A-Z]{1,8}[-_/]?\d{2,6}[A-Z0-9\-_/]*\b",
        r"\b[A-Z]{2,10}\s+\d{2,6}[A-Z0-9\-_/]*\b",
        r"\b\d{2,6}[-_/][A-Z]{1,8}[A-Z0-9\-_/]*\b",
    ]

    found_models = []

    for pattern in patterns:
        matches = re.findall(pattern, text)

        for model in matches:
            normalized_model = re.sub(
                r"[\s\-_/]",
                "",
                model,
            )

            has_letter = bool(
                re.search(r"[A-Z]", normalized_model)
            )

            has_number = bool(
                re.search(r"\d", normalized_model)
            )

            if (
                has_letter
                and has_number
                and len(normalized_model) >= 4
            ):
                found_models.append(normalized_model)

    return sorted(
        set(found_models),
        key=lambda value: (
            -len(value),
            value,
        ),
    )


def make_product_fingerprint(
    product_name: Any,
    brand: Any = "",
) -> str:
    normalized_brand = normalize_brand(brand)
    models = extract_model_codes(product_name)

    if models:
        return (
            f"{normalized_brand}|MODEL|{models[0]}"
        )

    normalized_name = normalize_product_name(
        product_name
    )

    return (
        f"{normalized_brand}|NAME|"
        f"{normalized_name[:50]}"
    )


def make_candidate_key(
    item: dict[str, Any],
    matched_brand: str,
) -> str:
    """
    동일 모델을 여러 판매처가 판매하는 경우 하나로 묶기 위해
    모델코드를 productId보다 우선 사용한다.
    """
    models = extract_model_codes(
        item.get("상품명", "")
    )

    if models:
        return (
            f"MODEL|{normalize_brand(matched_brand)}|"
            f"{models[0]}"
        )

    product_id = str(
        item.get("productId", "")
    ).strip()

    if product_id:
        return f"PID|{product_id}"

    return make_product_fingerprint(
        item.get("상품명", ""),
        matched_brand,
    )


# =========================================================
# 14. 자사 상품 커버리지 구성
# =========================================================

def build_store_coverage(
    store_dataframe: pd.DataFrame,
):
    if (
        store_dataframe is None
        or store_dataframe.empty
    ):
        return None, "자사 상품 파일에 데이터가 없습니다."

    df = store_dataframe.fillna("").copy()

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    columns = list(df.columns)

    name_column = find_column(
        columns,
        ["상품명", "상품 명", "제품명"],
    )

    brand_column = find_column(
        columns,
        ["브랜드", "제조사", "제조 회사"],
    )

    product_id_column = find_column(
        columns,
        [
            "상품번호",
            "상품 번호",
            "상품ID",
            "스마트스토어 상품번호",
        ],
    )

    if not name_column:
        return (
            None,
            "'상품명' 열을 찾지 못했습니다. "
            f"현재 열: {columns}",
        )

    group_coverage = set()
    product_ids = set()
    fingerprints = set()
    model_codes = set()
    normalized_names = set()

    valid_product_count = 0

    for _, row in df.iterrows():
        product_name = str(
            row.get(name_column, "")
        ).strip()

        if not product_name:
            continue

        valid_product_count += 1

        brand = (
            str(row.get(brand_column, "")).strip()
            if brand_column
            else ""
        )

        normalized_brand = normalize_brand(brand)

        product_id = (
            str(row.get(product_id_column, "")).strip()
            if product_id_column
            else ""
        )

        if product_id:
            product_ids.add(product_id)

        fingerprint = make_product_fingerprint(
            product_name,
            brand,
        )

        fingerprints.add(fingerprint)

        models = extract_model_codes(
            product_name
        )

        model_codes.update(models)

        normalized_names.add(
            normalize_product_name(product_name)
        )

        species = (
            extract_tags(
                product_name,
                SPECIES_TAGS,
            )
            or ["기타"]
        )

        genres = (
            extract_tags(
                product_name,
                GENRE_TAGS,
            )
            or ["기타"]
        )

        for species_value in species:
            for genre_value in genres:
                group_coverage.add((
                    normalized_brand,
                    species_value,
                    genre_value,
                ))

    return {
        "group_coverage": group_coverage,
        "product_ids": product_ids,
        "fingerprints": fingerprints,
        "model_codes": model_codes,
        "normalized_names": normalized_names,
        "product_count": valid_product_count,
        "brand_column_found": bool(brand_column),
        "product_id_column_found": bool(
            product_id_column
        ),
    }, None


def is_owned_product_group(
    brand_key: str,
    species: list[str],
    genres: list[str],
    coverage: dict[str, Any],
) -> bool:
    group_coverage = coverage.get(
        "group_coverage",
        set(),
    )

    for species_value in species:
        for genre_value in genres:
            # 브랜드까지 일치
            if (
                brand_key,
                species_value,
                genre_value,
            ) in group_coverage:
                return True

            # 자사 파일에 브랜드 열이 없는 경우의 보조 판정
            if (
                "",
                species_value,
                genre_value,
            ) in group_coverage:
                return True

    return False


def is_same_owned_product(
    item: dict[str, Any],
    matched_brand: str,
    coverage: dict[str, Any],
):
    product_id = str(
        item.get("productId", "")
    ).strip()

    if (
        product_id
        and product_id
        in coverage.get("product_ids", set())
    ):
        return True, "productId 일치"

    fingerprint = make_product_fingerprint(
        item.get("상품명", ""),
        matched_brand,
    )

    if (
        fingerprint
        in coverage.get("fingerprints", set())
    ):
        return True, "모델/상품명 지문 일치"

    candidate_models = set(
        extract_model_codes(
            item.get("상품명", "")
        )
    )

    common_models = (
        candidate_models
        & coverage.get("model_codes", set())
    )

    if common_models:
        return (
            True,
            "모델코드 일치: "
            + ", ".join(sorted(common_models)),
        )

    normalized_name = normalize_product_name(
        item.get("상품명", "")
    )

    if (
        normalized_name
        and normalized_name
        in coverage.get("normalized_names", set())
    ):
        return True, "정규화 상품명 일치"

    return False, ""


# =========================================================
# 15. 검색 조합 생성
# =========================================================

def build_keyword_specs(
    brands: list[str],
    seasons: list[str],
    genres: list[str],
):
    source_brands = brands or [""]
    source_seasons = seasons or [""]
    source_genres = genres or [""]

    specs = []
    seen = set()

    for brand in source_brands:
        for season in source_seasons:
            for genre in source_genres:
                parts = [
                    str(part).strip()
                    for part in [
                        brand,
                        season,
                        genre,
                    ]
                    if str(part).strip()
                ]

                if not parts:
                    continue

                keyword = " ".join(parts)
                normalized_keyword = normalize_text(
                    keyword
                )

                if normalized_keyword in seen:
                    continue

                seen.add(normalized_keyword)

                specs.append({
                    "keyword": keyword,
                    "brand": str(brand).strip(),
                    "season": str(season).strip(),
                    "genre": str(genre).strip(),
                })

    return specs


def build_keywords(
    brands: list[str],
    seasons: list[str],
    genres: list[str],
):
    return [
        spec["keyword"]
        for spec in build_keyword_specs(
            brands,
            seasons,
            genres,
        )
    ]


# =========================================================
# 16. 후보 브랜드·태그 판정
# =========================================================

def match_candidate_brand(
    item: dict[str, Any],
    requested_brand: str,
    all_brands: list[str],
) -> str:
    api_brand = str(
        item.get("브랜드", "")
    ).strip()

    maker = str(
        item.get("제조사", "")
    ).strip()

    product_name = str(
        item.get("상품명", "")
    ).strip()

    combined = normalize_text(
        f"{api_brand} {maker} {product_name}"
    )

    search_brands = []

    if requested_brand:
        search_brands.append(requested_brand)

    for brand in all_brands:
        if brand not in search_brands:
            search_brands.append(brand)

    for brand in search_brands:
        aliases = get_brand_aliases(brand)

        if any(
            alias and alias in combined
            for alias in aliases
        ):
            return brand

    # API가 브랜드 값을 명확하게 반환하면 보조 사용
    if api_brand:
        return api_brand

    return ""


def requested_brand_matches(
    requested_brand: str,
    matched_brand: str,
) -> bool:
    if not requested_brand:
        return True

    if not matched_brand:
        return False

    return (
        normalize_brand(requested_brand)
        == normalize_brand(matched_brand)
    )


def determine_candidate_tags(
    product_name: str,
    spec: dict[str, str],
):
    species = extract_tags(
        product_name,
        SPECIES_TAGS,
    )

    genres = extract_tags(
        product_name,
        GENRE_TAGS,
    )

    # 상품명에 태그가 없으면 검색에 사용한 조건을 상속
    if not species and spec.get("season"):
        species = [spec["season"]]

    if not genres and spec.get("genre"):
        genres = [spec["genre"]]

    return (
        species or ["기타"],
        genres or ["기타"],
    )


# =========================================================
# 17. 검색량·잠재력 점수
# =========================================================

def make_volume_query(
    species: list[str],
    genres: list[str],
    spec: dict[str, str],
) -> str:
    species_value = (
        species[0]
        if species and species[0] != "기타"
        else spec.get("season", "")
    )

    genre_value = (
        genres[0]
        if genres and genres[0] != "기타"
        else spec.get("genre", "")
    )

    parts = [
        value
        for value in [
            species_value,
            genre_value,
        ]
        if value and value != "기타"
    ]

    if parts:
        return " ".join(parts)

    return spec.get("keyword", "")


def get_candidate_search_volume(
    query: str,
    volume_cache: dict[str, int],
) -> int:
    normalized_query = normalize_text(query)

    if not normalized_query:
        return 0

    if normalized_query in volume_cache:
        return volume_cache[normalized_query]

    exact_volume = get_exact_keyword_volume(
        query,
        local_cache=None,
    )

    if exact_volume > 0:
        volume_cache[normalized_query] = exact_volume
        return exact_volume

    # 정확히 일치하는 검색량이 없으면 연관키워드 중
    # 검색어 구성요소가 가장 많이 겹치는 결과를 선택
    results = get_keyword_stats_list(
        [normalized_query]
    )

    query_tokens = {
        token
        for token in re.split(
            r"\s+",
            str(query).strip(),
        )
        if token
    }

    best_volume = 0
    best_overlap = 0

    for result in results:
        result_keyword = str(
            result.get("키워드", "")
        ).strip()

        normalized_result = normalize_text(
            result_keyword
        )

        if not normalized_result:
            continue

        overlap = sum(
            1
            for token in query_tokens
            if normalize_text(token) in normalized_result
        )

        result_volume = safe_int(
            result.get("총 검색량")
        )

        if (
            overlap > best_overlap
            or (
                overlap == best_overlap
                and overlap > 0
                and result_volume > best_volume
            )
        ):
            best_overlap = overlap
            best_volume = result_volume

    if best_overlap <= 0:
        best_volume = 0

    volume_cache[normalized_query] = best_volume

    return best_volume


def calculate_candidate_score(
    search_volume: int,
    best_rank: int,
    observed_seller_count: int,
) -> int:
    if best_rank <= 0:
        return 0

    rank_score = search_volume / best_rank

    # 여러 판매처에서 관측된 경우 최대 20% 보너스
    seller_bonus = min(
        max(observed_seller_count - 1, 0) * 0.03,
        0.20,
    )

    return int(
        rank_score * (1 + seller_bonus)
    )


# =========================================================
# 18. 사입 후보 발굴
# =========================================================

def find_candidates(
    brands: list[str],
    seasons: list[str],
    genres: list[str],
    client_id: str,
    client_secret: str,
    coverage: dict[str, Any] | None,
    max_rank: int = 50,
    exclude_used_rental_overseas: bool = True,
    show_progress: bool = True,
):
    specs = build_keyword_specs(
        brands,
        seasons,
        genres,
    )

    if not specs:
        return [], ["검색 조합이 없습니다."]

    coverage = coverage or {
        "group_coverage": set(),
        "product_ids": set(),
        "fingerprints": set(),
        "model_codes": set(),
        "normalized_names": set(),
    }

    max_rank = min(
        max(safe_int(max_rank, 50), 1),
        100,
    )

    volume_cache = {}
    candidates = {}
    errors = []

    progress = None

    if show_progress:
        progress = st.progress(
            0,
            text="사입 후보 수집 준비 중...",
        )

    for spec_index, spec in enumerate(specs):
        keyword = spec["keyword"]

        if progress is not None:
            progress.progress(
                spec_index / max(len(specs), 1),
                text=(
                    f"🔍 [{spec_index + 1}/{len(specs)}] "
                    f"{keyword}"
                ),
            )

        items, error = collect_rank_light(
            keyword=keyword,
            client_id=client_id,
            client_secret=client_secret,
            limit=max_rank,
            exclude_used_rental_overseas=(
                exclude_used_rental_overseas
            ),
        )

        if error:
            errors.append(
                f"{keyword}: {error}"
            )
            continue

        for item in items:
            # 자사 스토어 상품 제외
            if is_our_shop_item({
                "mallName": item.get("판매처", ""),
                "title": item.get("상품명", ""),
                "productType": item.get(
                    "productType",
                    0,
                ),
            }):
                continue

            rank = safe_int(
                item.get("순위")
            )

            if rank <= 0:
                continue

            product_name = str(
                item.get("상품명", "")
            ).strip()

            mall_name = str(
                item.get("판매처", "")
            ).strip()

            matched_brand = match_candidate_brand(
                item=item,
                requested_brand=spec.get("brand", ""),
                all_brands=brands,
            )

            # 특정 브랜드 검색인데 상품과 브랜드가 맞지 않으면 제외
            if not requested_brand_matches(
                spec.get("brand", ""),
                matched_brand,
            ):
                continue

            brand_key = normalize_brand(
                matched_brand
            )

            species, candidate_genres = (
                determine_candidate_tags(
                    product_name,
                    spec,
                )
            )

            group_owned = is_owned_product_group(
                brand_key=brand_key,
                species=species,
                genres=candidate_genres,
                coverage=coverage,
            )

            same_product, match_reason = (
                is_same_owned_product(
                    item=item,
                    matched_brand=matched_brand,
                    coverage=coverage,
                )
            )

            volume_query = make_volume_query(
                species=species,
                genres=candidate_genres,
                spec=spec,
            )

            search_volume = (
                get_candidate_search_volume(
                    volume_query,
                    volume_cache,
                )
            )

            candidate_key = make_candidate_key(
                item,
                matched_brand,
            )

            price = safe_int(
                item.get("가격")
            )

            if candidate_key not in candidates:
                candidates[candidate_key] = {
                    "productId": str(
                        item.get("productId", "")
                    ).strip(),
                    "검색키워드목록": {keyword},
                    "브랜드": matched_brand,
                    "API브랜드": str(
                        item.get("브랜드", "")
                    ),
                    "제조사": str(
                        item.get("제조사", "")
                    ),
                    "타사 상품명": product_name,
                    "대표판매처": mall_name,
                    "최고순위": rank,
                    "대표가격": price,
                    "어종목록": set(species),
                    "장르목록": set(
                        candidate_genres
                    ),
                    "검색량기준": volume_query,
                    "키워드검색량": search_volume,
                    "제품군취급": group_owned,
                    "동일제품취급": same_product,
                    "동일판정근거": match_reason,
                    "카테고리1": item.get(
                        "카테고리1",
                        "",
                    ),
                    "카테고리2": item.get(
                        "카테고리2",
                        "",
                    ),
                    "카테고리3": item.get(
                        "카테고리3",
                        "",
                    ),
                    "카테고리4": item.get(
                        "카테고리4",
                        "",
                    ),
                    "productType": safe_int(
                        item.get("productType")
                    ),
                    "대표링크": safe_url(
                        item.get("링크", "")
                    ),
                    "썸네일": safe_url(
                        item.get("썸네일", "")
                    ),
                    "판매처목록": {
                        mall_name
                    } if mall_name else set(),
                    "가격목록": (
                        [price]
                        if price > 0
                        else []
                    ),
                }
            )

            else:
                candidate = candidates[
                    candidate_key
                ]

                candidate[
                    "검색키워드목록"
                ].add(keyword)

                if mall_name:
                    candidate[
                        "판매처목록"
                    ].add(mall_name)

                if price > 0:
                    candidate[
                        "가격목록"
                    ].append(price)

                candidate[
                    "어종목록"
                ].update(species)

                candidate[
                    "장르목록"
                ].update(candidate_genres)

                if group_owned:
                    candidate["제품군취급"] = True

                if same_product:
                    candidate["동일제품취급"] = True

                    if not candidate.get(
                        "동일판정근거"
                    ):
                        candidate[
                            "동일판정근거"
                        ] = match_reason

                # 검색량이 더 큰 분류를 대표 검색량으로 사용
                if (
                    search_volume
                    > safe_int(
                        candidate.get(
                            "키워드검색량"
                        )
                    )
                ):
                    candidate[
                        "키워드검색량"
                    ] = search_volume

                    candidate[
                        "검색량기준"
                    ] = volume_query

                # 더 높은 순위가 발견되면 대표 상품 정보 갱신
                if rank < safe_int(
                    candidate.get("최고순위"),
                    9999,
                ):
                    candidate["최고순위"] = rank
                    candidate[
                        "대표판매처"
                    ] = mall_name

                    candidate[
                        "대표가격"
                    ] = price

                    candidate[
                        "타사 상품명"
                    ] = product_name

                    candidate[
                        "대표링크"
                    ] = safe_url(
                        item.get("링크", "")
                    )

                    candidate[
                        "썸네일"
                    ] = safe_url(
                        item.get("썸네일", "")
                    )

        time.sleep(0.08)

    if progress is not None:
        progress.progress(
            1.0,
            text="✅ 사입 후보 분석 완료",
        )

    result_rows = []

    for candidate in candidates.values():
        seller_names = candidate.pop(
            "판매처목록",
            set(),
        )

        prices = candidate.pop(
            "가격목록",
            [],
        )

        keyword_set = candidate.pop(
            "검색키워드목록",
            set(),
        )

        species_set = candidate.pop(
            "어종목록",
            set(),
        )

        genre_set = candidate.pop(
            "장르목록",
            set(),
        )

        prices = [
            safe_int(price)
            for price in prices
            if safe_int(price) > 0
        ]

        observed_seller_count = len(
            seller_names
        )

        best_rank = safe_int(
            candidate.get("최고순위")
        )

        search_volume = safe_int(
            candidate.get("키워드검색량")
        )

        candidate["검색키워드"] = ", ".join(
            sorted(keyword_set)
        )

        candidate["어종"] = ", ".join(
            sorted(species_set)
        )

        candidate["장르"] = ", ".join(
            sorted(genre_set)
        )

        # 실제 전체 판매처 수가 아니라 검색 결과에서 관측된 판매처 수
        candidate[
            "관측판매처수"
        ] = observed_seller_count

        candidate["최저관측가"] = (
            min(prices)
            if prices
            else 0
        )

        candidate["최고관측가"] = (
            max(prices)
            if prices
            else 0
        )

        candidate["평균관측가"] = (
            int(sum(prices) / len(prices))
            if prices
            else 0
        )

        candidate["제품군 취급여부"] = (
            "이미 취급군"
            if candidate.pop("제품군취급")
            else "🆕 미취급군"
        )

        candidate["동일제품 취급여부"] = (
            "동일제품 있음"
            if candidate.pop("동일제품취급")
            else "🆕 동일제품 없음"
        )

        candidate["잠재력점수"] = (
            calculate_candidate_score(
                search_volume=search_volume,
                best_rank=best_rank,
                observed_seller_count=(
                    observed_seller_count
                ),
            )
        )

        result_rows.append(candidate)

    # 동일제품이 없고 제품군도 미취급인 상품을 최우선 배치
    result_rows.sort(
        key=lambda row: (
            row["동일제품 취급여부"]
            != "🆕 동일제품 없음",
            row["제품군 취급여부"]
            != "🆕 미취급군",
            -safe_int(row["잠재력점수"]),
            safe_int(row["최고순위"], 9999),
        )
    )

    return result_rows, errors
