from __future__ import annotations

import hashlib
import html
import json
import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services.advertising_service import (
    AdvertisingApiError,
    search_ad_get,
)
from app.services.google_sheets import (
    get_spreadsheet,
    safe_sheet_value,
)


KST = ZoneInfo("Asia/Seoul")
AD_HISTORY_SHEET = "📢 광고 진단 기록"
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


def safe_int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def clean_title(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def now_text() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


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


def extract_ad_product_name(ad: dict[str, Any]) -> str:
    ad_info = ad.get("ad") or {}
    reference = ad.get("referenceData") or {}

    candidates = [
        ad_info.get("productName"),
        reference.get("productName"),
        ad_info.get("headline"),
        ad.get("name"),
    ]

    for candidate in candidates:
        text = clean_title(candidate)
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
            "💰 순위·CTR이 양호합니다. "
            f"{current:,}원 → 약 {suggested:,}원으로 "
            "소폭 낮춘 뒤 순위를 관찰할 수 있습니다."
        )

    return f"💰 현재 입찰가 {current:,}원 유지가 무난합니다."


def diagnose_ad(
    stat: dict[str, Any],
    bid_amount: Any = None,
    quality_grade: Any = None,
    is_active: bool = True,
) -> tuple[str, str, list[str], int]:
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
    advice: list[str] = []

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
        return "🟠", "노출순위·클릭 모두 개선 필요", advice, 80

    if low_rank:
        return "🟡", "노출은 되지만 순위가 낮음", advice, 60

    if low_ctr:
        return "🟡", "노출은 되지만 클릭이 낮음", advice, 55

    if quality and quality <= 3:
        return "🟡", "품질지수 개선 권장", advice, 50

    if impressions < 100:
        return "🟡", "데이터 추가 수집 필요", advice, 30

    return (
        "🟢",
        "양호",
        ["노출·클릭·순위가 비교적 안정적입니다."],
        0,
    )


def get_ads(adgroup_id: str) -> list[dict[str, Any]]:
    data = search_ad_get(
        "/ncc/ads",
        params={"nccAdgroupId": adgroup_id},
    )

    if not isinstance(data, list):
        raise AdvertisingApiError(
            "광고 소재 API 응답 형식이 올바르지 않습니다."
        )

    return [
        item for item in data
        if isinstance(item, dict)
    ]


def get_stats(
    ad_ids: list[str],
    days: int,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    results: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    if not ad_ids:
        return results, errors

    today = datetime.now(KST)
    since = today.fromtimestamp(
        today.timestamp() - days * 86400,
        tz=KST,
    )

    fields = [
        "impCnt",
        "clkCnt",
        "ctr",
        "cpc",
        "salesAmt",
        "avgRnk",
        "ccnt",
    ]

    for start in range(0, len(ad_ids), 100):
        chunk = ad_ids[start:start + 100]

        try:
            data = search_ad_get(
                "/stats",
                params={
                    "ids": chunk,
                    "fields": json.dumps(fields),
                    "timeRange": json.dumps({
                        "since": since.strftime("%Y-%m-%d"),
                        "until": today.strftime("%Y-%m-%d"),
                    }),
                },
            )
        except AdvertisingApiError as error:
            errors.append(str(error))
            continue

        rows = (
            data.get("data", [])
            if isinstance(data, dict)
            else []
        )

        for row in rows:
            if not isinstance(row, dict):
                continue

            ad_id = str(row.get("id", "")).strip()
            if not ad_id:
                continue

            results[ad_id] = {
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


def get_history_worksheet():
    spreadsheet = get_spreadsheet()

    try:
        worksheet = spreadsheet.worksheet(AD_HISTORY_SHEET)
    except Exception:
        worksheet = spreadsheet.add_worksheet(
            title=AD_HISTORY_SHEET,
            rows=10000,
            cols=len(AD_HISTORY_HEADERS),
        )

    headers = worksheet.row_values(1)

    if not headers:
        worksheet.update(
            values=[AD_HISTORY_HEADERS],
            range_name="A1",
        )
    elif headers[:len(AD_HISTORY_HEADERS)] != AD_HISTORY_HEADERS:
        raise RuntimeError(
            "광고 진단 기록 시트의 헤더 구성이 기존 프로그램과 다릅니다."
        )

    return worksheet


def load_history() -> list[dict[str, Any]]:
    worksheet = get_history_worksheet()
    values = worksheet.get_all_values()
    output: list[dict[str, Any]] = []

    for row in values[1:]:
        padded = row + [""] * (
            len(AD_HISTORY_HEADERS) - len(row)
        )
        item = dict(zip(AD_HISTORY_HEADERS, padded))

        if item["광고ID"] and item["수집일시"]:
            output.append(item)

    return output


def previous_snapshot(
    history: list[dict[str, Any]],
    collected_at: str,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    times = sorted({
        str(row.get("수집일시", ""))
        for row in history
        if row.get("수집일시")
        and str(row.get("수집일시")) < collected_at
    })

    if not times:
        return {}, None

    previous_time = times[-1]

    return (
        {
            str(row.get("광고ID", "")): row
            for row in history
            if row.get("수집일시") == previous_time
        },
        previous_time,
    )


def compare_rows(
    rows: list[dict[str, Any]],
    previous: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []

    for current in rows:
        old = previous.get(current["ad_id"])
        if not old:
            continue

        current_imp = safe_int(current["impressions"])
        previous_imp = safe_int(old.get("노출수"))
        current_rank = safe_float(current["average_rank"])
        previous_rank = safe_float(old.get("평균순위"))
        current_ctr = safe_float(current["ctr"])
        previous_ctr = safe_float(old.get("CTR"))

        reasons: list[str] = []
        severity = 0

        if previous_imp > 0 and current_imp < previous_imp * 0.7:
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
                "ad_id": current["ad_id"],
                "product_name": current["product_name"],
                "campaign_name": current["campaign_name"],
                "change": " / ".join(reasons),
                "severity": severity,
            })

    changes.sort(
        key=lambda item: -safe_int(item["severity"])
    )
    return changes


def save_rows(
    rows: list[dict[str, Any]],
    collected_at: str,
) -> int:
    if not rows:
        return 0

    worksheet = get_history_worksheet()
    values = []

    for row in rows:
        raw_id = (
            f"{collected_at}|{row['ad_id']}|"
            f"{row['campaign_name']}|{row['adgroup_name']}"
        )
        record_id = hashlib.sha256(
            raw_id.encode("utf-8")
        ).hexdigest()[:32]

        values.append([
            record_id,
            collected_at,
            row["ad_id"],
            row["campaign_name"],
            row["adgroup_name"],
            row["product_name"],
            "ON" if row["active"] else "OFF",
            row["bid_amount"],
            row["quality_grade"],
            row["impressions"],
            row["clicks"],
            row["ctr"],
            row["average_rank"],
            row["cost"],
            row["verdict"],
        ])

    worksheet.append_rows(
        [
            [safe_sheet_value(value) for value in row]
            for row in values
        ],
        value_input_option="RAW",
    )

    return len(values)


def run_advertising_diagnosis(
    mode: str,
    targets: list[dict[str, Any]],
    days: int,
    exclude_off_campaigns: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    campaigns_data = search_ad_get("/ncc/campaigns")

    if not isinstance(campaigns_data, list):
        raise AdvertisingApiError(
            "캠페인 API 응답 형식이 올바르지 않습니다."
        )

    campaigns = [
        campaign
        for campaign in campaigns_data
        if isinstance(campaign, dict)
        and "SHOPPING" in str(
            campaign.get("campaignTp", "")
        ).upper()
    ]

    target_map = {
        str(target.get("campaign_id", "")): {
            str(group_id)
            for group_id in target.get("adgroup_ids", [])
            if str(group_id)
        }
        for target in targets
        if target.get("campaign_id")
    }

    if mode == "selected":
        campaigns = [
            campaign
            for campaign in campaigns
            if str(
                campaign.get("nccCampaignId", "")
            ) in target_map
        ]
    elif exclude_off_campaigns:
        campaigns = [
            campaign
            for campaign in campaigns
            if entity_is_active(campaign)
        ]

    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for campaign in campaigns:
        campaign_id = str(
            campaign.get("nccCampaignId", "")
        )
        campaign_name = str(
            campaign.get("name", campaign_id)
        )

        try:
            groups_data = search_ad_get(
                "/ncc/adgroups",
                params={"nccCampaignId": campaign_id},
            )
        except AdvertisingApiError as error:
            errors.append(f"{campaign_name}: {error}")
            continue

        groups = [
            group for group in groups_data
            if isinstance(group, dict)
        ] if isinstance(groups_data, list) else []

        selected_group_ids = target_map.get(
            campaign_id,
            set(),
        )

        if mode == "selected" and selected_group_ids:
            groups = [
                group
                for group in groups
                if str(
                    group.get("nccAdgroupId", "")
                ) in selected_group_ids
            ]

        for group in groups:
            group_id = str(
                group.get("nccAdgroupId", "")
            )
            group_name = str(
                group.get("name", group_id)
            )

            try:
                ads = get_ads(group_id)
            except AdvertisingApiError as error:
                errors.append(
                    f"{campaign_name}/{group_name}: {error}"
                )
                continue

            ad_ids = [
                str(ad.get("nccAdId", ""))
                for ad in ads
                if ad.get("nccAdId")
            ]
            stats, stat_errors = get_stats(ad_ids, days)
            errors.extend(stat_errors)

            for ad in ads:
                ad_id = str(ad.get("nccAdId", ""))
                if not ad_id:
                    continue

                stat = stats.get(ad_id, {})
                quality = extract_quality_grade(ad)
                bid = extract_bid_amount(ad, group)
                active = (
                    entity_is_active(campaign)
                    and entity_is_active(group)
                    and entity_is_active(
                        ad,
                        {"ELIGIBLE", "ACTIVE", "ON"},
                    )
                )

                icon, verdict, advice, priority = diagnose_ad(
                    stat,
                    bid,
                    quality,
                    active,
                )

                rows.append({
                    "ad_id": ad_id,
                    "status_icon": icon,
                    "priority": priority,
                    "campaign_name": campaign_name,
                    "adgroup_name": group_name,
                    "product_name": extract_ad_product_name(ad),
                    "active": active,
                    "bid_amount": bid,
                    "quality_grade": quality,
                    "impressions": safe_int(
                        stat.get("impCnt")
                    ),
                    "clicks": safe_int(
                        stat.get("clkCnt")
                    ),
                    "ctr": round(
                        safe_float(stat.get("ctr")),
                        2,
                    ),
                    "average_rank": round(
                        safe_float(stat.get("avgRnk")),
                        1,
                    ),
                    "cost": safe_int(
                        stat.get("salesAmt")
                    ),
                    "conversions": safe_int(
                        stat.get("ccnt")
                    ),
                    "verdict": verdict,
                    "advice": " / ".join(advice),
                })

            time.sleep(0.1)

    rows.sort(
        key=lambda item: (
            -safe_int(item["priority"]),
            -safe_int(item["cost"]),
        )
    )

    collected_at = now_text()
    history = load_history()
    previous, previous_time = previous_snapshot(
        history,
        collected_at,
    )
    changes = compare_rows(rows, previous)

    saved_count = 0
    save_message = ""

    try:
        saved_count = save_rows(rows, collected_at)
        save_message = f"광고 진단 {saved_count}건 저장 완료"
    except Exception as error:
        save_message = f"광고 진단 저장 오류: {error}"
        errors.append(save_message)

    return {
        "collected_at": collected_at,
        "previous_collected_at": previous_time,
        "days": days,
        "total_ads": len(rows),
        "total_impressions": sum(
            item["impressions"] for item in rows
        ),
        "total_clicks": sum(
            item["clicks"] for item in rows
        ),
        "total_cost": sum(
            item["cost"] for item in rows
        ),
        "urgent_count": sum(
            item["status_icon"] in {"🔴", "🟠"}
            for item in rows
        ),
        "saved_count": saved_count,
        "save_message": save_message,
        "errors": errors,
        "changes": changes,
        "rows": rows,
        "elapsed_seconds": round(
            time.perf_counter() - started,
            2,
        ),
    }
