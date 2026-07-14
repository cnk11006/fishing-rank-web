from __future__ import annotations

import base64
import hashlib
import hmac
import html
import os
import time
from typing import Any

import pandas as pd
import streamlit as st


# 반드시 커스텀 모듈 import보다 먼저 실행
st.set_page_config(
    page_title="피싱템 순위 레이더",
    layout="wide",
    page_icon="🎣",
)


from fishing_core import (
    MIGRATION_LOG_SHEET,
    MONITOR_SHEET_NAME,
    RANK_HISTORY_SHEET,
    TARGET_STORE,
    add_monitor_keyword,
    collect_rank_data,
    delete_monitor_items,
    get_catalog_badge,
    get_keyword_stats_list,
    is_our_store_name,
    load_app_secrets,
    load_monitor_keywords,
    load_rank_history,
    migrate_legacy_rank_sheets,
    now_kst,
    safe_float,
    safe_int,
    safe_url,
    save_rank_records,
)

from fishing_analysis import (
    ad_get_adgroups,
    ad_get_campaigns,
    analyze_brand_contribution,
    analyze_cross_purchase,
    analyze_seo,
    build_keyword_specs,
    build_store_coverage,
    compare_ad_snapshots,
    find_candidates,
    load_previous_ad_snapshot,
    load_product_master,
    run_ad_diagnosis,
    save_ad_diagnosis,
)


# =========================================================
# 0. Secrets
# =========================================================

SECRETS = load_app_secrets()

CLIENT_ID = SECRETS["NAVER_CLIENT_ID"]
CLIENT_SECRET = SECRETS["NAVER_CLIENT_SECRET"]
MASTER_PASSWORD = SECRETS["APP_PASSWORD"]
SHEET_ID = SECRETS["GOOGLE_SHEET_ID"]


# =========================================================
# 1. CSS
# =========================================================

st.markdown(
    """
    <style>
        .stApp {
            background-color: #F8F9FA;
        }

        footer {
            visibility: hidden;
        }

        #MainMenu {
            visibility: hidden;
        }

        [data-testid="stMetric"] {
            background-color: #ffffff;
            border-radius: 12px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.04);
            padding: 15px 20px;
            border-left: 5px solid #0A84FF;
        }

        [data-testid="stVerticalBlock"] > [style*="border"] {
            background-color: #ffffff !important;
            border-radius: 15px !important;
            border: 1px solid #eef0f5 !important;
            box-shadow: 0 4px 10px rgba(0,0,0,0.04) !important;
        }

        [data-testid="stForm"] {
            background-color: #ffffff;
            border-radius: 15px;
            border: 1px solid #eef0f5;
            box-shadow: 0 4px 10px rgba(0,0,0,0.03);
            padding: 10px;
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 4rem;
        }

        a {
            text-decoration: none;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 2. 로그인
# =========================================================

MAX_LOGIN_FAILURES = 5
LOGIN_LOCK_SECONDS = 60


def initialize_login_state() -> None:
    defaults = {
        "authenticated": False,
        "login_failures": 0,
        "login_locked_until": 0.0,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_login() -> None:
    initialize_login_state()

    if st.session_state["authenticated"]:
        return

    st.title("🔐 피싱템 보안 접속")
    st.caption(
        "허가된 사용자만 이용할 수 있습니다."
    )

    current_time = time.time()
    locked_until = safe_float(
        st.session_state.get(
            "login_locked_until",
            0,
        )
    )

    if locked_until > current_time:
        remaining = int(
            locked_until - current_time
        ) + 1

        st.error(
            f"로그인 실패 횟수가 많습니다. "
            f"{remaining}초 후 다시 시도하세요."
        )

        if st.button("🔄 잠금시간 다시 확인"):
            st.rerun()

        st.stop()

    with st.form("login_form"):
        password = st.text_input(
            "접속 비밀번호",
            type="password",
            autocomplete="current-password",
        )

        submitted = st.form_submit_button(
            "로그인",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        password_matches = hmac.compare_digest(
            str(password),
            str(MASTER_PASSWORD),
        )

        if password_matches:
            st.session_state["authenticated"] = True
            st.session_state["login_failures"] = 0
            st.session_state["login_locked_until"] = 0.0
            st.rerun()

        failures = safe_int(
            st.session_state.get(
                "login_failures",
                0,
            )
        ) + 1

        st.session_state["login_failures"] = failures

        if failures >= MAX_LOGIN_FAILURES:
            st.session_state[
                "login_locked_until"
            ] = (
                time.time()
                + LOGIN_LOCK_SECONDS
            )

            st.session_state["login_failures"] = 0

            st.error(
                "로그인 실패 횟수를 초과했습니다. "
                "60초 동안 로그인이 제한됩니다."
            )

        else:
            remaining_attempts = (
                MAX_LOGIN_FAILURES - failures
            )

            st.error(
                "비밀번호가 올바르지 않습니다. "
                f"남은 시도 횟수: {remaining_attempts}회"
            )

    st.stop()


render_login()


# =========================================================
# 3. 세션 상태
# =========================================================

SESSION_DEFAULTS = {
    "search_results": None,
    "search_keyword": "",
    "detail_item_id": None,
    "analysis_keyword": "",
    "analysis_results": None,
    "main_keyword_result": None,
    "ad_diag_rows": None,
    "ad_diag_collected_at": None,
    "ad_diag_errors": [],
    "candidate_rows": None,
    "candidate_errors": [],
    "migration_result": None,
    "cross_purchase_rows": None,
    "brand_contribution_rows": None,
}


for session_key, default_value in SESSION_DEFAULTS.items():
    if session_key not in st.session_state:
        st.session_state[session_key] = default_value


# =========================================================
# 4. 공통 표시 함수
# =========================================================

def make_widget_key(
    prefix: str,
    *values: Any,
) -> str:
    raw = "|||".join(
        str(value or "")
        for value in values
    )

    digest = hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:14]

    return f"{prefix}_{digest}"


def short_text(
    value: Any,
    max_length: int = 30,
) -> str:
    text = str(value or "")

    if len(text) <= max_length:
        return text

    return text[:max_length] + "…"


def product_matches_monitor(
    record: dict[str, Any],
    monitor: dict[str, Any],
) -> bool:
    monitor_product_id = str(
        monitor.get("productId", "")
    ).strip()

    record_product_id = str(
        record.get("productId", "")
    ).strip()

    if (
        monitor_product_id
        and record_product_id
    ):
        return (
            monitor_product_id
            == record_product_id
        )

    monitor_product_name = str(
        monitor.get("상품명", "")
    ).strip()

    if not monitor_product_name:
        memo = str(
            monitor.get("메모", "")
        )

        if memo.startswith("등록상품:"):
            monitor_product_name = memo.replace(
                "등록상품:",
                "",
                1,
            ).strip()

    record_product_name = str(
        record.get("상품명", "")
    ).strip()

    if not monitor_product_name:
        return True

    return (
        monitor_product_name
        == record_product_name
        or monitor_product_name
        in record_product_name
        or record_product_name
        in monitor_product_name
    )


def get_monitor_history(
    monitor: dict[str, Any],
    all_history: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    keyword = monitor["키워드"]

    records = all_history.get(
        keyword,
        [],
    )

    return [
        record
        for record in records
        if product_matches_monitor(
            record,
            monitor,
        )
    ]


def get_latest_snapshot(
    records: list[dict[str, Any]],
) -> tuple[
    str | None,
    list[dict[str, Any]],
]:
    if not records:
        return None, []

    latest_time = max(
        str(record.get("날짜", ""))
        for record in records
        if str(record.get("날짜", ""))
    )

    latest_rows = [
        record
        for record in records
        if str(record.get("날짜", ""))
        == latest_time
    ]

    return latest_time, latest_rows


def rank_status(rank: int | None) -> str:
    if not rank:
        return "⚪ 미노출"

    if rank <= 10:
        return "🟢 TOP 10"

    if rank <= 50:
        return "🟢 TOP 50"

    if rank <= 100:
        return "🟡 TOP 100"

    if rank <= 200:
        return "🟠 TOP 200"

    return "🔴 200위 밖"


def calculate_rank_change(
    records: list[dict[str, Any]],
) -> str:
    if not records:
        return "➖ 수집 기록 없음"

    snapshot_times = sorted({
        str(record.get("날짜", ""))
        for record in records
        if str(record.get("날짜", ""))
    })

    if len(snapshot_times) < 2:
        return "➖ 첫 수집"

    latest_time = snapshot_times[-1]
    previous_time = snapshot_times[-2]

    latest_ranks = [
        safe_int(record.get("순위"))
        for record in records
        if (
            str(record.get("날짜", ""))
            == latest_time
            and safe_int(
                record.get("순위")
            ) > 0
        )
    ]

    previous_ranks = [
        safe_int(record.get("순위"))
        for record in records
        if (
            str(record.get("날짜", ""))
            == previous_time
            and safe_int(
                record.get("순위")
            ) > 0
        )
    ]

    if not latest_ranks or not previous_ranks:
        return "➖ 비교 데이터 부족"

    latest_best = min(latest_ranks)
    previous_best = min(previous_ranks)

    change = previous_best - latest_best

    if change > 0:
        return f"🔺 {change}위 상승"

    if change < 0:
        return f"🔻 {abs(change)}위 하락"

    return "➡️ 변동 없음"


def render_product_cards(
    items: list[dict[str, Any]],
    columns_per_row: int = 5,
) -> None:
    if not items:
        return

    for row_start in range(
        0,
        len(items),
        columns_per_row,
    ):
        row_items = items[
            row_start:
            row_start + columns_per_row
        ]

        columns = st.columns(
            columns_per_row
        )

        for column, item in zip(
            columns,
            row_items,
        ):
            with column:
                with st.container(border=True):
                    image_url = safe_url(
                        item.get("썸네일", "")
                    )

                    link = safe_url(
                        item.get("링크", "")
                    )

                    product_name = str(
                        item.get("상품명", "")
                    )

                    rank = safe_int(
                        item.get("순위")
                    )

                    price = safe_int(
                        item.get("가격")
                    )

                    mall = str(
                        item.get("판매처", "")
                    )

                    if image_url:
                        st.image(
                            image_url,
                            use_container_width=True,
                        )

                    if link:
                        st.markdown(
                            f"**{rank}위 · "
                            f"[{short_text(product_name, 25)}]"
                            f"({link})**"
                        )
                    else:
                        st.markdown(
                            f"**{rank}위 · "
                            f"{short_text(product_name, 25)}**"
                        )

                    st.markdown(
                        f"💰 **{price:,}원**"
                        if price > 0
                        else "💰 가격정보 없음"
                    )

                    badge = get_catalog_badge(
                        item.get("productType")
                    )

                    st.caption(
                        f"{mall} {badge}"
                    )


# =========================================================
# 5. 상단 로고·메뉴
# =========================================================

header_left, header_right = st.columns(
    [5, 1]
)

with header_left:
    if os.path.exists("logo.png"):
        st.image(
            "logo.png",
            width=145,
        )
    else:
        st.markdown("# 🎣 피싱템 순위 레이더")

with header_right:
    if st.button(
        "🚪 로그아웃",
        use_container_width=True,
    ):
        st.session_state.clear()
        st.rerun()


sheet_url = (
    "https://docs.google.com/spreadsheets/d/"
    + SHEET_ID
)

st.link_button(
    "📊 구글 시트에서 전체 기록 보기",
    sheet_url,
)

st.caption(
    f"통합 기록 시트: {RANK_HISTORY_SHEET} · "
    f"현재 한국시간: "
    f"{now_kst().strftime('%Y-%m-%d %H:%M')}"
)

st.markdown("<br>", unsafe_allow_html=True)


TAB_LABELS = [
    "🔍 순위 검색",
    "📋 모니터링 관리",
    "📊 키워드 분석",
    "📢 광고 진단 & 시즌",
    "🛒 교차구매 분석",
    "🎯 사입 후보 발굴",
    "⚙️ 데이터 관리",
]


active_tab = st.radio(
    "메뉴",
    TAB_LABELS,
    horizontal=True,
    label_visibility="collapsed",
    key="main_menu",
)

menu = active_tab
selected_menu = active_tab

# =========================================================
# 6. 상세 분석 패널
# =========================================================

def render_detail_panel(
    keyword: str,
    target_product_name: str = "",
    target_product_id: str = "",
) -> None:
    st.markdown(
        f"## 🔍 '{keyword}' 상세 분석"
    )

    st.divider()

    st.markdown(
        "#### 🏆 현재 경쟁사 TOP 10 실시간 분석"
    )

    with st.spinner(
        "네이버쇼핑 경쟁사 데이터를 수집하고 있습니다..."
    ):
        (
            found_items,
            top10_prices,
            top100_items,
            error,
        ) = collect_rank_data(
            keyword=keyword,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            max_rank=400,
            exclude_used_rental_overseas=True,
        )

    if error:
        st.warning(error)

    average_price = (
        int(
            sum(top10_prices)
            / len(top10_prices)
        )
        if top10_prices
        else 0
    )

    our_prices = [
        safe_int(item.get("가격"))
        for item in found_items
        if safe_int(item.get("가격")) > 0
    ]

    our_average_price = (
        int(sum(our_prices) / len(our_prices))
        if our_prices
        else 0
    )

    our_best_rank = (
        min(
            safe_int(item.get("순위"))
            for item in found_items
            if safe_int(item.get("순위")) > 0
        )
        if found_items
        else None
    )

    metric1, metric2, metric3, metric4 = st.columns(4)

    metric1.metric(
        "피싱템 최고 순위",
        (
            f"{our_best_rank}위"
            if our_best_rank
            else "미노출"
        ),
    )

    metric2.metric(
        "피싱템 평균가",
        (
            f"{our_average_price:,}원"
            if our_average_price
            else "-"
        ),
    )

    metric3.metric(
        "TOP10 평균가",
        (
            f"{average_price:,}원"
            if average_price
            else "-"
        ),
    )

    if our_average_price and average_price:
        difference = round(
            (
                our_average_price
                - average_price
            )
            / average_price
            * 100
        )

        metric4.metric(
            "TOP10 대비 가격",
            (
                f"{abs(difference)}% "
                + (
                    "비쌈"
                    if difference > 0
                    else "저렴"
                )
            ),
            delta=difference,
            delta_color="inverse",
        )
    else:
        metric4.metric(
            "TOP10 대비 가격",
            "-",
        )

    if top100_items:
        st.markdown(
            "##### 상위 경쟁 상품"
        )

        render_product_cards(
            top100_items[:10],
            columns_per_row=5,
        )

    st.divider()
    st.markdown(
        "#### 🔍 SEO 진단 및 상품명 최적화"
    )

    if not found_items:
        st.warning(
            "피싱템 상품이 검색되지 않아 "
            "SEO 분석을 진행할 수 없습니다."
        )
        return

    selected_item = None

    if target_product_id:
        selected_item = next(
            (
                item
                for item in found_items
                if str(
                    item.get("productId", "")
                ).strip()
                == str(target_product_id).strip()
            ),
            None,
        )

    if (
        selected_item is None
        and target_product_name
    ):
        selected_item = next(
            (
                item
                for item in found_items
                if (
                    target_product_name
                    == item.get("상품명", "")
                    or target_product_name
                    in item.get("상품명", "")
                )
            ),
            None,
        )

    if selected_item is None:
        selected_item = min(
            found_items,
            key=lambda item: safe_int(
                item.get("순위"),
                9999,
            ),
        )

    st.markdown(
        "**분석 대상 상품:** "
        f"`{selected_item['상품명']}`"
    )

    st.markdown(
        f"**현재 순위:** "
        f"{safe_int(selected_item['순위'])}위 · "
        f"**판매가:** "
        f"{safe_int(selected_item['가격']):,}원"
    )

    product_type = safe_int(
        selected_item.get("productType")
    )

    if product_type in {1, 4, 7, 10}:
        st.warning(
            "🔗 가격비교 상품으로 노출되고 있습니다. "
            "독립 노출이 필요한 경우 카탈로그 매칭 상태와 "
            "상품명·옵션·가격 차별화를 점검하세요."
        )
    else:
        st.success(
            f"✅ 독립 상품 노출 형태입니다. "
            f"{get_catalog_badge(product_type)}"
        )

    with st.spinner(
        "연관 키워드를 분석하고 있습니다..."
    ):
        related_results = get_keyword_stats_list(
            [keyword]
        )

    related_results = sorted(
        related_results,
        key=lambda row: safe_int(
            row.get("총 검색량")
        ),
        reverse=True,
    )

    related_options = [
        row["키워드"]
        for row in related_results
        if (
            normalize_keyword_for_compare(
                row["키워드"]
            )
            != normalize_keyword_for_compare(
                keyword
            )
        )
    ][:10]

    selected_related = st.multiselect(
        "SEO 최적화에 반영할 연관 키워드",
        options=related_options,
        default=related_options[:3],
        max_selections=3,
        help=(
            "상품과 직접 관련 있는 키워드만 선택하세요."
        ),
        key=make_widget_key(
            "seo_related",
            keyword,
            selected_item.get(
                "productId",
                selected_item["상품명"],
            ),
        ),
    )

    seo_result = analyze_seo(
        keyword,
        selected_item["상품명"],
        selected_related,
    )

    score = safe_int(
        seo_result["score"]
    )

    score_icon = (
        "🟢"
        if score >= 80
        else "🟡"
        if score >= 60
        else "🔴"
    )

    st.markdown(
        f"### {score_icon} SEO 점수: "
        f"**{score}점** / 100점"
    )

    st.progress(score / 100)

    if seo_result["goods"]:
        st.markdown("##### ✅ 잘된 점")

        for good_point in seo_result["goods"]:
            st.markdown(f"- {good_point}")

    if seo_result["issues"]:
        st.markdown("##### ⚠️ 개선 검토")

        for title, description in seo_result["issues"]:
            st.markdown(
                f"- **{title}**: {description}"
            )

    st.markdown("##### ✏️ 추천 상품명")
    st.info(
        seo_result["recommended_name"]
    )

    st.caption(
        seo_result["notice"]
    )

    if related_results:
        related_df = pd.DataFrame(
            related_results[:10]
        )

        display_columns = [
            column
            for column in [
                "키워드",
                "PC 검색량",
                "모바일 검색량",
                "총 검색량",
                "경쟁강도",
                "검색량 추정",
            ]
            if column in related_df.columns
        ]

        st.dataframe(
            related_df[display_columns],
            use_container_width=True,
            hide_index=True,
        )


def normalize_keyword_for_compare(
    value: Any,
) -> str:
    return "".join(
        str(value or "").lower().split()
    )
# =========================================================
# 7. TAB 1 — 순위 검색
# =========================================================

if active_tab == "🔍 순위 검색":
    st.subheader("🔍 네이버쇼핑 순위 검색")

    search_column, option_column = st.columns(
        [4, 2]
    )

    with search_column:
        search_keyword = st.text_input(
            "검색할 키워드",
            placeholder="예: 타이라바 로드",
            key="rank_search_keyword_input",
        )

    with option_column:
        include_special_products = st.checkbox(
            "중고·렌탈·해외직구 포함",
            value=False,
            help=(
                "체크하지 않으면 중고·렌탈·해외직구를 "
                "가격 및 순위 분석에서 제외합니다."
            ),
            key="rank_include_special",
        )

    search_button = st.button(
        "🚀 400위까지 정밀 수색 시작",
        type="primary",
        use_container_width=True,
        key="rank_search_button",
    )

    if search_button:
        search_keyword = str(
            search_keyword
        ).strip()

        if not search_keyword:
            st.warning(
                "검색할 키워드를 입력하세요."
            )

        else:
            with st.spinner(
                "네이버쇼핑 400위까지 검색하고 있습니다..."
            ):
                (
                    found_items,
                    top10_prices,
                    top100_items,
                    search_error,
                ) = collect_rank_data(
                    keyword=search_keyword,
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    max_rank=400,
                    exclude_used_rental_overseas=(
                        not include_special_products
                    ),
                )

            st.session_state[
                "search_keyword"
            ] = search_keyword

            st.session_state[
                "search_results"
            ] = {
                "found_items": found_items,
                "top10_prices": top10_prices,
                "top100_items": top100_items,
                "error": search_error,
                "include_special": (
                    include_special_products
                ),
                "searched_at": now_kst().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }

    search_results = st.session_state.get(
        "search_results"
    )

    saved_keyword = st.session_state.get(
        "search_keyword",
        "",
    )

    if search_results:
        found_items = search_results.get(
            "found_items",
            [],
        )

        top10_prices = search_results.get(
            "top10_prices",
            [],
        )

        top100_items = search_results.get(
            "top100_items",
            [],
        )

        search_error = search_results.get(
            "error"
        )

        searched_at = search_results.get(
            "searched_at",
            "",
        )

        if search_error:
            st.warning(search_error)

        st.caption(
            f"검색 키워드: {saved_keyword} · "
            f"검색 시각: {searched_at}"
        )

        average_price = (
            int(
                sum(top10_prices)
                / len(top10_prices)
            )
            if top10_prices
            else 0
        )

        our_prices = [
            safe_int(item.get("가격"))
            for item in found_items
            if safe_int(item.get("가격")) > 0
        ]

        our_average_price = (
            int(
                sum(our_prices)
                / len(our_prices)
            )
            if our_prices
            else 0
        )

        if top10_prices:
            st.markdown(
                "### 💰 키워드 시장 가격 분석"
            )

            price_metric1, price_metric2, price_metric3, price_metric4 = (
                st.columns(4)
            )

            price_metric1.metric(
                "TOP10 최저가",
                f"{min(top10_prices):,}원",
            )

            price_metric2.metric(
                "TOP10 평균가",
                f"{average_price:,}원",
            )

            price_metric3.metric(
                "TOP10 최고가",
                f"{max(top10_prices):,}원",
            )

            price_metric4.metric(
                "피싱템 평균가",
                (
                    f"{our_average_price:,}원"
                    if our_average_price
                    else "-"
                ),
            )

        if top100_items:
            st.divider()

            st.markdown(
                "### 🏪 시장 경쟁 상품 TOP 10"
            )

            st.caption(
                "네이버쇼핑 정확도순 검색 결과입니다. "
                "썸네일 또는 상품명을 통해 상품 페이지를 확인할 수 있습니다."
            )

            render_product_cards(
                top100_items[:10],
                columns_per_row=5,
            )

        st.divider()

        if not found_items:
            st.error(
                f"현재 '{TARGET_STORE}' 상품이 "
                f"'{saved_keyword}' 검색결과 400위 내에 없습니다."
            )

        else:
            best_rank = min(
                safe_int(item.get("순위"))
                for item in found_items
                if safe_int(item.get("순위")) > 0
            )

            st.success(
                f"총 {len(found_items)}개의 자사 상품을 찾았습니다. "
                f"최고 순위는 {best_rank}위입니다."
            )

            if (
                our_average_price
                and average_price
            ):
                price_difference = round(
                    (
                        our_average_price
                        - average_price
                    )
                    / average_price
                    * 100
                )

                if price_difference > 0:
                    st.warning(
                        f"자사 평균가격이 TOP10 평균보다 "
                        f"{abs(price_difference)}% 높습니다."
                    )
                else:
                    st.info(
                        f"자사 평균가격이 TOP10 평균보다 "
                        f"{abs(price_difference)}% 낮습니다."
                    )

            st.markdown(
                "### 📌 저장 및 모니터링할 상품 선택"
            )

            st.caption(
                "검색만으로는 구글 시트에 저장되지 않습니다. "
                "아래에서 선택한 상품만 통합 순위기록에 저장됩니다."
            )

            with st.form("save_monitor_products_form"):
                selected_map = {}

                cards_per_row = 3

                for row_start in range(
                    0,
                    len(found_items),
                    cards_per_row,
                ):
                    row_items = found_items[
                        row_start:
                        row_start + cards_per_row
                    ]

                    columns = st.columns(
                        cards_per_row
                    )

                    for column, item in zip(
                        columns,
                        row_items,
                    ):
                        with column:
                            with st.container(border=True):
                                image_url = safe_url(
                                    item.get(
                                        "썸네일",
                                        "",
                                    )
                                )

                                if image_url:
                                    st.image(
                                        image_url,
                                        width=150,
                                    )

                                rank = safe_int(
                                    item.get("순위")
                                )

                                product_name = str(
                                    item.get(
                                        "상품명",
                                        "",
                                    )
                                )

                                product_id = str(
                                    item.get(
                                        "productId",
                                        "",
                                    )
                                )

                                link = safe_url(
                                    item.get(
                                        "링크",
                                        "",
                                    )
                                )

                                st.markdown(
                                    f"### 🏆 {rank}위"
                                )

                                product_type = safe_int(
                                    item.get(
                                        "productType"
                                    )
                                )

                                if product_type in {
                                    1,
                                    4,
                                    7,
                                    10,
                                }:
                                    st.warning(
                                        "🔗 가격비교 묶음"
                                    )
                                else:
                                    st.success(
                                        "✅ 독립 노출"
                                    )

                                if link:
                                    st.markdown(
                                        f"**[{product_name}]"
                                        f"({link})**"
                                    )
                                else:
                                    st.markdown(
                                        f"**{product_name}**"
                                    )

                                st.caption(
                                    f"🏪 "
                                    f"{item.get('판매처', '')}"
                                )

                                st.caption(
                                    f"💴 "
                                    f"{safe_int(item.get('가격')):,}원"
                                )

                                selection_key = (
                                    product_id
                                    or make_widget_key(
                                        "product",
                                        product_name,
                                        rank,
                                    )
                                )

                                selected_map[
                                    selection_key
                                ] = {
                                    "selected": st.checkbox(
                                        "저장 및 모니터링 등록",
                                        key=make_widget_key(
                                            "select_rank_product",
                                            saved_keyword,
                                            selection_key,
                                            rank,
                                        ),
                                    ),
                                    "item": item,
                                }

                save_button = st.form_submit_button(
                    "🚀 선택 상품 저장 및 모니터링 등록",
                    type="primary",
                    use_container_width=True,
                )

            if save_button:
                selected_items = [
                    value["item"]
                    for value in selected_map.values()
                    if value["selected"]
                ]

                if not selected_items:
                    st.warning(
                        "선택한 상품이 없습니다."
                    )

                else:
                    save_ok, save_message = (
                        save_rank_records(
                            keyword=saved_keyword,
                            found_items=selected_items,
                        )
                    )

                    monitor_success = 0
                    monitor_duplicates = 0
                    monitor_errors = []

                    for item in selected_items:
                        product_name = str(
                            item.get("상품명", "")
                        )

                        product_id = str(
                            item.get("productId", "")
                        )

                        monitor_ok, monitor_message = (
                            add_monitor_keyword(
                                keyword=saved_keyword,
                                memo=(
                                    f"등록상품:{product_name}"
                                ),
                                product_id=product_id,
                                product_name=product_name,
                            )
                        )

                        if monitor_ok:
                            monitor_success += 1
                        elif "이미 등록" in monitor_message:
                            monitor_duplicates += 1
                        else:
                            monitor_errors.append(
                                monitor_message
                            )

                    if save_ok:
                        st.success(
                            f"순위기록 {len(selected_items)}건 저장, "
                            f"모니터링 {monitor_success}건 등록 완료"
                        )
                    else:
                        st.error(save_message)

                    if monitor_duplicates:
                        st.info(
                            f"이미 등록된 모니터링 상품 "
                            f"{monitor_duplicates}건은 중복 등록하지 않았습니다."
                        )

                    for monitor_error in monitor_errors:
                        st.warning(monitor_error)


# =========================================================
# 8. TAB 2 — 모니터링 관리
# =========================================================

if active_tab == "📋 모니터링 관리":
    st.subheader("📋 모니터링 키워드 관리")

    with st.spinner(
        "모니터링 목록과 통합 순위기록을 불러오고 있습니다..."
    ):
        monitor_records = load_monitor_keywords()

        unique_keywords = tuple(sorted({
            record["키워드"]
            for record in monitor_records
            if record.get("키워드")
        }))

        all_history = (
            load_rank_history(
                unique_keywords
            )
            if unique_keywords
            else {}
        )

    if not monitor_records:
        st.info(
            "등록된 모니터링 항목이 없습니다. "
            "순위 검색 화면에서 상품을 등록하세요."
        )

    else:
        st.caption(
            f"총 {len(monitor_records)}개 상품을 모니터링하고 있습니다."
        )

        selected_for_deletion = []

        cards_per_row = 4

        for row_start in range(
            0,
            len(monitor_records),
            cards_per_row,
        ):
            row_records = monitor_records[
                row_start:
                row_start + cards_per_row
            ]

            columns = st.columns(
                cards_per_row
            )

            for column, monitor in zip(
                columns,
                row_records,
            ):
                with column:
                    monitor_id = monitor.get(
                        "항목ID",
                        "",
                    )

                    keyword = monitor.get(
                        "키워드",
                        "",
                    )

                    product_name = monitor.get(
                        "상품명",
                        "",
                    )

                    product_id = monitor.get(
                        "productId",
                        "",
                    )

                    history = get_monitor_history(
                        monitor,
                        all_history,
                    )

                    latest_time, latest_rows = (
                        get_latest_snapshot(
                            history
                        )
                    )

                    best_item = None

                    if latest_rows:
                        best_item = min(
                            latest_rows,
                            key=lambda row: safe_int(
                                row.get("순위"),
                                9999,
                            ),
                        )

                    thumbnail = ""
                    product_link = ""

                    if best_item:
                        thumbnail = safe_url(
                            best_item.get("썸네일")
                            or best_item.get("이미지")
                            or best_item.get("이미지URL")
                            or best_item.get("image")
                            or ""
                        )

                        product_link = safe_url(
                            best_item.get("링크")
                            or best_item.get("상품링크")
                            or best_item.get("link")
                            or ""
                        )

                    with st.container(border=True):
                        if thumbnail:
                            if product_link:
                                st.markdown(
                                    f"""
                                    <a href="{product_link}" target="_blank">
                                        <img src="{thumbnail}"
                                             style="width:100%; max-height:150px;
                                             object-fit:contain; cursor:pointer;">
                                    </a>
                                    """,
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.image(
                                    thumbnail,
                                    use_container_width=True,
                                )


                        st.markdown(
                            f"**🔑 {keyword}**"
                        )

                        displayed_name = (
                            product_name
                            or (
                                best_item.get(
                                    "상품명",
                                    "",
                                )
                                if best_item
                                else ""
                            )
                            or "상품 미지정"
                        )

                        st.caption(
                            "📦 "
                            + short_text(
                                displayed_name,
                                28,
                            )
                        )

                        if best_item:
                            current_rank = safe_int(
                                best_item.get(
                                    "순위"
                                )
                            )

                            st.markdown(
                                f"🏆 **{current_rank}위** · "
                                f"{rank_status(current_rank)}"
                            )

                            st.caption(
                                get_catalog_badge(
                                    best_item.get(
                                        "productType"
                                    )
                                )
                                or "ℹ️ 노출형태 미확인"
                            )

                            if product_link:
                                st.link_button(
                                    "🛍️ 상품 페이지 바로가기",
                                    product_link,
                                    use_container_width=True,
                                )

                        else:
                            st.markdown(
                                "🏆 **최근 수집 기록 없음**"
                            )

                        st.caption(
                            calculate_rank_change(
                                history
                            )
                        )

                        st.caption(
                            f"🕐 {latest_time or '-'}"
                        )

                        if st.button(
                            "🔍 상세분석",
                            key=make_widget_key(
                                "monitor_detail",
                                monitor_id,
                            ),
                            use_container_width=True,
                        ):
                            current_detail = (
                                st.session_state.get(
                                    "detail_item_id"
                                )
                            )

                            st.session_state[
                                "detail_item_id"
                            ] = (
                                None
                                if current_detail
                                == monitor_id
                                else monitor_id
                            )

                            st.rerun()

                        delete_checked = st.checkbox(
                            "🗑️ 삭제 선택",
                            key=make_widget_key(
                                "monitor_delete",
                                monitor_id,
                            ),
                        )

                        if delete_checked:
                            selected_for_deletion.append(
                                monitor_id
                            )

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button(
            "🗑️ 선택한 모니터링 항목 삭제",
            type="secondary",
            key="delete_selected_monitors",
        ):
            if not selected_for_deletion:
                st.warning(
                    "삭제할 항목을 선택하세요."
                )

            else:
                delete_ok, delete_message = (
                    delete_monitor_items(
                        selected_for_deletion
                    )
                )

                if delete_ok:
                    st.success(delete_message)
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(delete_message)

        detail_item_id = st.session_state.get(
            "detail_item_id"
        )

        if detail_item_id:
            selected_monitor = next(
                (
                    monitor
                    for monitor in monitor_records
                    if monitor.get("항목ID")
                    == detail_item_id
                ),
                None,
            )

            if selected_monitor:
                st.divider()

                with st.container(border=True):
                    if st.button(
                        "✖ 상세분석 닫기",
                        key="close_monitor_detail",
                    ):
                        st.session_state[
                            "detail_item_id"
                        ] = None
                        st.rerun()

                    render_detail_panel(
                        keyword=selected_monitor[
                            "키워드"
                        ],
                        target_product_name=(
                            selected_monitor.get(
                                "상품명",
                                "",
                            )
                        ),
                        target_product_id=(
                            selected_monitor.get(
                                "productId",
                                "",
                            )
                        ),
                    )

        st.divider()
        st.markdown(
            "### 🚀 등록 키워드 전체 일괄 수색"
        )

        st.caption(
            "모니터링 중인 고유 키워드를 한 번씩 검색하고, "
            "발견된 모든 자사 상품을 통합 순위기록에 저장합니다."
        )

        batch_search_button = st.button(
            "🛰️ 전체 키워드 일괄 수색 시작",
            type="primary",
            use_container_width=True,
            key="batch_rank_search",
        )

        if batch_search_button:
            summary = []
            total_keywords = len(
                unique_keywords
            )

            progress = st.progress(
                0,
                text="일괄 수색 준비 중...",
            )

            for keyword_index, keyword in enumerate(
                unique_keywords,
                start=1,
            ):
                progress.progress(
                    (
                        keyword_index - 1
                    )
                    / max(total_keywords, 1),
                    text=(
                        f"🔍 [{keyword_index}/{total_keywords}] "
                        f"{keyword}"
                    ),
                )

                (
                    found_items,
                    _,
                    _,
                    error,
                ) = collect_rank_data(
                    keyword=keyword,
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    max_rank=400,
                    exclude_used_rental_overseas=True,
                )

                if error and not found_items:
                    summary.append({
                        "키워드": keyword,
                        "결과": "❌ API 오류",
                        "저장건수": 0,
                        "최고순위": "",
                        "메모": error,
                    })

                    continue

                if found_items:
                    save_ok, save_message = (
                        save_rank_records(
                            keyword,
                            found_items,
                        )
                    )

                    best_rank = min(
                        safe_int(
                            item.get("순위")
                        )
                        for item in found_items
                        if safe_int(
                            item.get("순위")
                        ) > 0
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

                    summary.append({
                        "키워드": keyword,
                        "결과": (
                            "✅ 저장 완료"
                            if save_ok
                            else "❌ 저장 실패"
                        ),
                        "저장건수": (
                            len(found_items)
                            if save_ok
                            else 0
                        ),
                        "최고순위": best_rank,
                        "메모": (
                            f"가격비교 {catalog_count}개"
                            if save_ok
                            else save_message
                        ),
                    })

                else:
                    summary.append({
                        "키워드": keyword,
                        "결과": "⚠️ 400위 내 미노출",
                        "저장건수": 0,
                        "최고순위": "",
                        "메모": error or "",
                    })

                time.sleep(0.3)

            progress.progress(
                1.0,
                text="✅ 일괄 수색 완료",
            )

            st.session_state[
                "batch_rank_summary"
            ] = summary

            load_rank_history.clear()

        batch_summary = st.session_state.get(
            "batch_rank_summary"
        )

        if batch_summary:
            st.success(
                "일괄 수색 결과입니다."
            )

            st.dataframe(
                pd.DataFrame(batch_summary),
                use_container_width=True,
                hide_index=True,
            )

            if st.button(
                "결과 표 닫기",
                key="close_batch_summary",
            ):
                st.session_state[
                    "batch_rank_summary"
                ] = None
                st.rerun()


# =========================================================
# 9. TAB 3 — 키워드 분석
# =========================================================

if active_tab == "📊 키워드 분석":
    st.subheader("📊 네이버 검색광고 키워드 분석")

    keyword_column, button_column = st.columns(
        [4, 1]
    )

    with keyword_column:
        analysis_keyword = st.text_input(
            "분석할 키워드",
            placeholder="예: 타이라바 로드",
            label_visibility="collapsed",
            key="keyword_analysis_input",
        )

    with button_column:
        analysis_button = st.button(
            "🔍 분석 시작",
            type="primary",
            use_container_width=True,
            key="keyword_analysis_button",
        )

    if analysis_button:
        analysis_keyword = str(
            analysis_keyword
        ).strip()

        if not analysis_keyword:
            st.warning(
                "분석할 키워드를 입력하세요."
            )

        else:
            with st.spinner(
                "키워드 검색량과 연관 키워드를 불러오고 있습니다..."
            ):
                keyword_results = (
                    get_keyword_stats_list(
                        [analysis_keyword]
                    )
                )

            if not keyword_results:
                st.error(
                    f"'{analysis_keyword}'의 "
                    "키워드 데이터를 찾지 못했습니다."
                )

            else:
                normalized_target = (
                    normalize_keyword_for_compare(
                        analysis_keyword
                    )
                )

                main_result = next(
                    (
                        result
                        for result in keyword_results
                        if (
                            normalize_keyword_for_compare(
                                result.get(
                                    "키워드",
                                    "",
                                )
                            )
                            == normalized_target
                        )
                    ),
                    keyword_results[0],
                )

                st.session_state[
                    "analysis_keyword"
                ] = analysis_keyword

                st.session_state[
                    "analysis_results"
                ] = keyword_results

                st.session_state[
                    "main_keyword_result"
                ] = main_result

    main_result = st.session_state.get(
        "main_keyword_result"
    )

    keyword_results = st.session_state.get(
        "analysis_results"
    )

    stored_analysis_keyword = (
        st.session_state.get(
            "analysis_keyword",
            "",
        )
    )

    if main_result and keyword_results:
        st.divider()

        st.markdown(
            f"### 📌 '{stored_analysis_keyword}' 분석 결과"
        )

        metric1, metric2, metric3, metric4, metric5 = (
            st.columns(5)
        )

        metric1.metric(
            "💻 PC 검색량",
            f"{safe_int(main_result.get('PC 검색량')):,}",
        )

        metric2.metric(
            "📱 모바일 검색량",
            f"{safe_int(main_result.get('모바일 검색량')):,}",
        )

        metric3.metric(
            "🔢 총 검색량",
            f"{safe_int(main_result.get('총 검색량')):,}",
        )

        metric4.metric(
            "⚔️ 경쟁강도",
            main_result.get(
                "경쟁강도",
                "-",
            ),
        )

        metric5.metric(
            "🖱️ PC 평균클릭수",
            f"{safe_float(main_result.get('PC 평균클릭수')):,.1f}",
        )

        if main_result.get("검색량 추정"):
            st.caption(
                "※ '<10'으로 제공된 검색량은 "
                "계산 편의를 위해 5로 추정했습니다."
            )

        st.divider()
        st.markdown(
            "### 🔗 연관 키워드"
        )

        keyword_df = pd.DataFrame(
            keyword_results
        ).sort_values(
            "총 검색량",
            ascending=False,
        )

        display_columns = [
            column
            for column in [
                "키워드",
                "PC 검색량",
                "모바일 검색량",
                "총 검색량",
                "경쟁강도",
                "PC 평균클릭수",
                "모바일 평균클릭수",
                "PC 평균클릭률",
                "모바일 평균클릭률",
                "검색량 추정",
            ]
            if column in keyword_df.columns
        ]

        st.dataframe(
            keyword_df[display_columns],
            use_container_width=True,
            hide_index=True,
        )

        csv_data = (
            keyword_df[display_columns]
            .to_csv(index=False)
            .encode("utf-8-sig")
        )

        st.download_button(
            "📥 키워드 분석 CSV 다운로드",
            data=csv_data,
            file_name=(
                f"{stored_analysis_keyword}_키워드분석_"
                f"{now_kst().strftime('%Y%m%d')}.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )
# =========================================================
# 10. TAB 4 — 광고 진단 및 시즌
# =========================================================

if active_tab == "📢 광고 진단 & 시즌":
    import plotly.express as px

    st.subheader("📢 CPC 광고 진단 및 시즌 전략")

    ad_view = st.radio(
        "보기 선택",
        [
            "🩺 쇼핑광고 진단",
            "📅 시즌·순위 추세",
        ],
        horizontal=True,
        key="ad_main_view",
    )

    # =====================================================
    # 10-1. 쇼핑광고 진단
    # =====================================================

    if ad_view == "🩺 쇼핑광고 진단":
        st.caption(
            "쇼핑광고 소재의 노출·클릭·순위·품질지수를 "
            "불러와 자동으로 점검합니다."
        )

        diagnosis_mode = st.radio(
            "진단 방식",
            [
                "⚡ 선택 진단",
                "🩺 전체 진단",
            ],
            horizontal=True,
            key="ad_diagnosis_mode",
        )

        diagnosis_days = st.selectbox(
            "진단 기간",
            options=[7, 14, 30],
            index=0,
            format_func=lambda value: (
                f"최근 {value}일"
            ),
            key="ad_diagnosis_days",
        )

        with st.spinner(
            "광고 캠페인 목록을 불러오고 있습니다..."
        ):
            campaigns, campaign_error = (
                ad_get_campaigns()
            )

        if campaign_error:
            st.error(campaign_error)

        shopping_campaigns = [
            campaign
            for campaign in campaigns
            if (
                "SHOPPING"
                in str(
                    campaign.get(
                        "campaignTp",
                        "",
                    )
                ).upper()
            )
        ]

        if not campaign_error and not shopping_campaigns:
            st.warning(
                "쇼핑광고 캠페인을 찾지 못했습니다. "
                "네이버 검색광고 API 권한과 캠페인 유형을 확인하세요."
            )

        diagnosis_requested = False
        diagnosis_targets = []

        if shopping_campaigns:
            campaign_name_map = {}

            for campaign in shopping_campaigns:
                campaign_id = str(
                    campaign.get(
                        "nccCampaignId",
                        "",
                    )
                )

                campaign_name = str(
                    campaign.get(
                        "name",
                        campaign_id,
                    )
                )

                # 같은 이름의 캠페인이 있을 수 있으므로 ID 일부 표시
                display_name = campaign_name

                if display_name in campaign_name_map:
                    display_name = (
                        f"{campaign_name} "
                        f"({campaign_id[-6:]})"
                    )

                campaign_name_map[
                    display_name
                ] = campaign

            if diagnosis_mode == "⚡ 선택 진단":
                selected_campaign_names = st.multiselect(
                    "진단할 캠페인 선택",
                    options=list(
                        campaign_name_map.keys()
                    ),
                    help=(
                        "한 개를 선택하면 광고그룹까지 선택할 수 있습니다. "
                        "여러 개를 선택하면 선택한 캠페인의 전체 그룹을 진단합니다."
                    ),
                    key="selected_ad_campaigns",
                )

                if len(selected_campaign_names) == 1:
                    selected_display_name = (
                        selected_campaign_names[0]
                    )

                    selected_campaign = (
                        campaign_name_map[
                            selected_display_name
                        ]
                    )

                    selected_campaign_id = str(
                        selected_campaign.get(
                            "nccCampaignId",
                            "",
                        )
                    )

                    selected_campaign_name = str(
                        selected_campaign.get(
                            "name",
                            selected_display_name,
                        )
                    )

                    adgroups, adgroup_error = (
                        ad_get_adgroups(
                            selected_campaign_id
                        )
                    )

                    if adgroup_error:
                        st.warning(adgroup_error)

                    else:
                        adgroup_name_map = {}

                        for adgroup in adgroups:
                            adgroup_id = str(
                                adgroup.get(
                                    "nccAdgroupId",
                                    "",
                                )
                            )

                            adgroup_name = str(
                                adgroup.get(
                                    "name",
                                    adgroup_id,
                                )
                            )

                            display_group_name = adgroup_name

                            if (
                                display_group_name
                                in adgroup_name_map
                            ):
                                display_group_name = (
                                    f"{adgroup_name} "
                                    f"({adgroup_id[-6:]})"
                                )

                            adgroup_name_map[
                                display_group_name
                            ] = adgroup

                        group_options = [
                            "📦 캠페인 전체 광고그룹",
                            *list(
                                adgroup_name_map.keys()
                            ),
                        ]

                        selected_group_name = st.selectbox(
                            "광고그룹 선택",
                            options=group_options,
                            key="selected_ad_group",
                        )

                        if selected_group_name.startswith(
                            "📦"
                        ):
                            selected_groups = adgroups
                        else:
                            selected_groups = [
                                adgroup_name_map[
                                    selected_group_name
                                ]
                            ]

                        diagnosis_targets = [(
                            selected_campaign_name,
                            selected_groups,
                        )]

                elif len(selected_campaign_names) > 1:
                    st.info(
                        f"{len(selected_campaign_names)}개 캠페인의 "
                        "전체 광고그룹을 진단합니다."
                    )

                    for display_name in selected_campaign_names:
                        campaign = campaign_name_map[
                            display_name
                        ]

                        campaign_id = str(
                            campaign.get(
                                "nccCampaignId",
                                "",
                            )
                        )

                        campaign_name = str(
                            campaign.get(
                                "name",
                                display_name,
                            )
                        )

                        adgroups, adgroup_error = (
                            ad_get_adgroups(
                                campaign_id
                            )
                        )

                        if adgroup_error:
                            st.warning(
                                f"{campaign_name}: "
                                f"{adgroup_error}"
                            )
                            continue

                        diagnosis_targets.append((
                            campaign_name,
                            adgroups,
                        ))

                if st.button(
                    "⚡ 선택 진단 시작",
                    type="primary",
                    use_container_width=True,
                    key="start_selected_ad_diagnosis",
                ):
                    if not selected_campaign_names:
                        st.warning(
                            "진단할 캠페인을 한 개 이상 선택하세요."
                        )
                    elif not diagnosis_targets:
                        st.warning(
                            "진단할 광고그룹을 불러오지 못했습니다."
                        )
                    else:
                        diagnosis_requested = True

            else:
                exclude_off_campaigns = st.checkbox(
                    "꺼진 캠페인 제외",
                    value=True,
                    key="exclude_off_campaigns",
                )

                if exclude_off_campaigns:
                    target_campaigns = [
                        campaign
                        for campaign in shopping_campaigns
                        if (
                            campaign.get("userLock")
                            is not True
                            and str(
                                campaign.get(
                                    "status",
                                    "",
                                )
                            ).upper()
                            not in {
                                "PAUSED",
                                "STOPPED",
                                "DELETED",
                            }
                        )
                    ]
                else:
                    target_campaigns = (
                        shopping_campaigns
                    )

                st.info(
                    f"쇼핑광고 캠페인 "
                    f"{len(target_campaigns)}개를 진단합니다. "
                    "소재가 많으면 시간이 걸릴 수 있습니다."
                )

                if st.button(
                    "🩺 전체 광고 진단 시작",
                    type="primary",
                    use_container_width=True,
                    key="start_all_ad_diagnosis",
                ):
                    diagnosis_targets = []

                    campaign_progress = st.progress(
                        0,
                        text="광고그룹 목록 준비 중...",
                    )

                    for campaign_index, campaign in enumerate(
                        target_campaigns,
                        start=1,
                    ):
                        campaign_name = str(
                            campaign.get(
                                "name",
                                "",
                            )
                        )

                        campaign_id = str(
                            campaign.get(
                                "nccCampaignId",
                                "",
                            )
                        )

                        campaign_progress.progress(
                            (
                                campaign_index - 1
                            )
                            / max(
                                len(target_campaigns),
                                1,
                            ),
                            text=(
                                f"📡 [{campaign_index}/"
                                f"{len(target_campaigns)}] "
                                f"{campaign_name}"
                            ),
                        )

                        adgroups, adgroup_error = (
                            ad_get_adgroups(
                                campaign_id
                            )
                        )

                        if adgroup_error:
                            st.warning(
                                f"{campaign_name}: "
                                f"{adgroup_error}"
                            )
                            continue

                        diagnosis_targets.append((
                            campaign_name,
                            adgroups,
                        ))

                    campaign_progress.progress(
                        1.0,
                        text="✅ 광고그룹 목록 준비 완료",
                    )

                    if diagnosis_targets:
                        diagnosis_requested = True
                    else:
                        st.warning(
                            "진단할 광고그룹이 없습니다."
                        )

        # -------------------------------------------------
        # 실제 광고 진단 실행
        # -------------------------------------------------

        if diagnosis_requested:
            diagnosis_rows = []
            diagnosis_errors = []

            diagnosis_progress = st.progress(
                0,
                text="광고 진단 준비 중...",
            )

            for target_index, (
                campaign_name,
                target_adgroups,
            ) in enumerate(
                diagnosis_targets,
                start=1,
            ):
                diagnosis_progress.progress(
                    (
                        target_index - 1
                    )
                    / max(
                        len(diagnosis_targets),
                        1,
                    ),
                    text=(
                        f"🔍 [{target_index}/"
                        f"{len(diagnosis_targets)}] "
                        f"{campaign_name}"
                    ),
                )

                rows, errors = run_ad_diagnosis(
                    adgroups=target_adgroups,
                    campaign_name=campaign_name,
                    days=diagnosis_days,
                )

                diagnosis_rows.extend(rows)
                diagnosis_errors.extend(errors)

            diagnosis_progress.progress(
                1.0,
                text="✅ 광고 진단 완료",
            )

            if diagnosis_rows:
                (
                    save_ok,
                    save_message,
                    collected_at,
                ) = save_ad_diagnosis(
                    diagnosis_rows
                )

                st.session_state[
                    "ad_diag_rows"
                ] = diagnosis_rows

                st.session_state[
                    "ad_diag_collected_at"
                ] = collected_at

                st.session_state[
                    "ad_diag_errors"
                ] = diagnosis_errors

                if save_ok:
                    st.success(save_message)
                else:
                    st.warning(save_message)

            else:
                st.session_state[
                    "ad_diag_rows"
                ] = []

                st.session_state[
                    "ad_diag_errors"
                ] = diagnosis_errors

                st.warning(
                    "진단할 광고 소재를 찾지 못했습니다."
                )

        # -------------------------------------------------
        # 광고 진단 결과 표시
        # -------------------------------------------------

        diagnosis_rows = st.session_state.get(
            "ad_diag_rows"
        )

        collected_at = st.session_state.get(
            "ad_diag_collected_at"
        )

        diagnosis_errors = st.session_state.get(
            "ad_diag_errors",
            [],
        )

        if diagnosis_errors:
            with st.expander(
                f"⚠️ 광고 API 경고 "
                f"{len(diagnosis_errors)}건"
            ):
                for diagnosis_error in diagnosis_errors:
                    st.warning(diagnosis_error)

        if diagnosis_rows:
            st.divider()
            st.markdown(
                "## 📊 광고 진단 결과"
            )

            st.caption(
                f"진단 저장 시각: "
                f"{collected_at or '-'}"
            )

            total_impressions = sum(
                safe_int(row.get("노출수"))
                for row in diagnosis_rows
            )

            total_clicks = sum(
                safe_int(row.get("클릭수"))
                for row in diagnosis_rows
            )

            total_cost = sum(
                safe_int(row.get("광고비"))
                for row in diagnosis_rows
            )

            urgent_rows = [
                row
                for row in diagnosis_rows
                if row.get("상태")
                in {
                    "🔴",
                    "🟠",
                }
            ]

            check_rows = [
                row
                for row in diagnosis_rows
                if row.get("상태")
                in {
                    "🔴",
                    "🟠",
                    "🟡",
                }
            ]

            metric1, metric2, metric3, metric4, metric5 = (
                st.columns(5)
            )

            metric1.metric(
                "진단 소재",
                f"{len(diagnosis_rows)}개",
            )

            metric2.metric(
                "총 노출",
                f"{total_impressions:,}",
            )

            metric3.metric(
                "총 클릭",
                f"{total_clicks:,}",
            )

            metric4.metric(
                "총 광고비",
                f"{total_cost:,}원",
            )

            metric5.metric(
                "긴급 점검",
                f"{len(urgent_rows)}개",
                help=(
                    "빨간색·주황색 광고의 수입니다. "
                    "노란색은 일반 점검 권장 항목입니다."
                ),
            )

            st.divider()
            st.markdown(
                "### 📌 우선 점검 광고 TOP 5"
            )

            prioritized_rows = sorted(
                check_rows,
                key=lambda row: (
                    -safe_int(
                        row.get("우선순위")
                    ),
                    -safe_int(
                        row.get("광고비")
                    ),
                ),
            )

            if not prioritized_rows:
                st.success(
                    "현재 우선 점검이 필요한 광고가 없습니다."
                )

            else:
                for priority_index, row in enumerate(
                    prioritized_rows[:5],
                    start=1,
                ):
                    with st.container(border=True):
                        st.markdown(
                            f"**{priority_index}. "
                            f"{row.get('상태', '')} "
                            f"{row.get('상품명', '')}**"
                        )

                        st.caption(
                            f"캠페인: "
                            f"{row.get('캠페인', '')} · "
                            f"광고그룹: "
                            f"{row.get('광고그룹', '')}"
                        )

                        st.markdown(
                            f"**진단:** "
                            f"{row.get('진단', '')}"
                        )

                        st.info(
                            row.get(
                                "_advice",
                                "점검 안내가 없습니다.",
                            )
                        )

            st.divider()
            st.markdown(
                "### 📉 이전 진단보다 나빠진 광고"
            )

            previous_map, previous_time = (
                load_previous_ad_snapshot(
                    current_collected_at=collected_at
                )
            )

            if not previous_map:
                st.info(
                    "비교할 이전 광고 진단 기록이 없습니다. "
                    "다음 진단부터 광고 ID 기준으로 비교됩니다."
                )

            else:
                st.caption(
                    f"비교 기준: {previous_time}"
                )

                changed_rows = compare_ad_snapshots(
                    diagnosis_rows,
                    previous_map,
                )

                if not changed_rows:
                    st.success(
                        "이전 진단보다 크게 나빠진 광고가 없습니다."
                    )

                else:
                    for changed in changed_rows:
                        st.warning(
                            f"📉 **{changed['상품명']}** · "
                            f"{changed['변화']}"
                        )

            st.divider()
            st.markdown(
                "### 📋 전체 광고 성과"
            )

            diagnosis_df = pd.DataFrame(
                diagnosis_rows
            )

            diagnosis_columns = [
                "상태",
                "광고ID",
                "캠페인",
                "광고그룹",
                "상품명",
                "ON/OFF",
                "입찰가",
                "품질지수",
                "노출수",
                "클릭수",
                "CTR(%)",
                "평균순위",
                "광고비",
                "전환수",
                "진단",
            ]

            diagnosis_columns = [
                column
                for column in diagnosis_columns
                if column in diagnosis_df.columns
            ]

            st.dataframe(
                diagnosis_df[
                    diagnosis_columns
                ],
                use_container_width=True,
                hide_index=True,
            )

            diagnosis_csv = (
                diagnosis_df[
                    diagnosis_columns
                ]
                .to_csv(index=False)
                .encode("utf-8-sig")
            )

            st.download_button(
                "📥 광고 진단 CSV 다운로드",
                data=diagnosis_csv,
                file_name=(
                    "광고진단_"
                    + now_kst().strftime(
                        "%Y%m%d_%H%M"
                    )
                    + ".csv"
                ),
                mime="text/csv",
                use_container_width=True,
            )

            if st.button(
                "🧹 현재 광고 진단 화면 비우기",
                key="clear_ad_diagnosis",
            ):
                st.session_state[
                    "ad_diag_rows"
                ] = None

                st.session_state[
                    "ad_diag_collected_at"
                ] = None

                st.session_state[
                    "ad_diag_errors"
                ] = []

                st.rerun()

    # =====================================================
    # 10-2. 시즌·순위 추세
    # =====================================================

    else:
        st.caption(
            "통합 순위기록에 누적된 데이터를 이용해 "
            "키워드별 순위 변화와 계절성을 확인합니다."
        )

        with st.spinner(
            "모니터링 목록과 순위기록을 불러오고 있습니다..."
        ):
            season_monitors = (
                load_monitor_keywords()
            )

            season_keywords = tuple(sorted({
                monitor["키워드"]
                for monitor in season_monitors
                if monitor.get("키워드")
            }))

            season_history = (
                load_rank_history(
                    season_keywords
                )
                if season_keywords
                else {}
            )

        if not season_keywords:
            st.info(
                "모니터링 키워드가 없습니다. "
                "먼저 순위 검색 화면에서 상품을 등록하세요."
            )

        else:
            def date_best_rank_map(records):
                best_by_date = {}

                for record in records:
                    collected_at = str(
                        record.get("날짜", "")
                    )

                    if len(collected_at) < 10:
                        continue

                    date_value = collected_at[:10]
                    rank = safe_int(
                        record.get("순위")
                    )

                    if rank <= 0:
                        continue

                    if (
                        date_value
                        not in best_by_date
                        or rank
                        < best_by_date[date_value]
                    ):
                        best_by_date[
                            date_value
                        ] = rank

                return best_by_date

            current_month = (
                now_kst().strftime("%m")
            )

            previous_year = str(
                now_kst().year - 1
            )

            st.markdown(
                f"### 📅 이번 달 "
                f"({int(current_month)}월) "
                "준비 키워드"
            )

            seasonal_messages = []

            for keyword in season_keywords:
                records = season_history.get(
                    keyword,
                    [],
                )

                best_by_date = (
                    date_best_rank_map(
                        records
                    )
                )

                last_year_same_month = {
                    date_value: rank
                    for date_value, rank
                    in best_by_date.items()
                    if (
                        date_value[:4]
                        == previous_year
                        and date_value[5:7]
                        == current_month
                    )
                }

                if last_year_same_month:
                    last_year_best = min(
                        last_year_same_month.values()
                    )

                    seasonal_messages.append(
                        f"🎣 **{keyword}** — "
                        f"작년 {int(current_month)}월 "
                        f"최고 {last_year_best}위 기록"
                    )

            if seasonal_messages:
                for message in seasonal_messages:
                    st.success(message)

            else:
                st.info(
                    "작년 같은 달 데이터가 아직 없습니다. "
                    "데이터가 1년 이상 쌓이면 자동으로 표시됩니다."
                )

            st.divider()
            st.markdown(
                "### 📊 키워드별 최근 추세"
            )

            trend_summary = []

            for keyword in season_keywords:
                records = season_history.get(
                    keyword,
                    [],
                )

                best_by_date = (
                    date_best_rank_map(
                        records
                    )
                )

                sorted_dates = sorted(
                    best_by_date.keys()
                )

                if len(sorted_dates) < 2:
                    trend_summary.append({
                        "키워드": keyword,
                        "추세": "데이터 부족",
                        "이전순위": "",
                        "현재순위": (
                            best_by_date[
                                sorted_dates[-1]
                            ]
                            if sorted_dates
                            else ""
                        ),
                        "변화": "",
                    })

                    continue

                latest_date = sorted_dates[-1]

                comparison_date = sorted_dates[
                    max(
                        0,
                        len(sorted_dates) - 4,
                    )
                ]

                latest_rank = best_by_date[
                    latest_date
                ]

                comparison_rank = best_by_date[
                    comparison_date
                ]

                change = (
                    comparison_rank
                    - latest_rank
                )

                if change >= 3:
                    trend = "📈 상승"
                elif change <= -3:
                    trend = "📉 하락"
                else:
                    trend = "➡️ 정체"

                trend_summary.append({
                    "키워드": keyword,
                    "추세": trend,
                    "이전순위": comparison_rank,
                    "현재순위": latest_rank,
                    "변화": change,
                })

            st.dataframe(
                pd.DataFrame(trend_summary),
                use_container_width=True,
                hide_index=True,
            )

            st.divider()
            st.markdown(
                "### 🔍 키워드 상세 추세"
            )

            selected_trend_keyword = st.selectbox(
                "추세를 확인할 키워드",
                options=list(season_keywords),
                key="selected_trend_keyword",
            )

            selected_records = (
                season_history.get(
                    selected_trend_keyword,
                    [],
                )
            )

            selected_best_by_date = (
                date_best_rank_map(
                    selected_records
                )
            )

            if not selected_best_by_date:
                st.warning(
                    "선택한 키워드의 순위기록이 없습니다."
                )

            else:
                trend_df = pd.DataFrame([
                    {
                        "날짜": date_value,
                        "최고순위": rank,
                    }
                    for date_value, rank
                    in sorted(
                        selected_best_by_date.items()
                    )
                ])

                trend_df["날짜"] = pd.to_datetime(
                    trend_df["날짜"]
                )

                figure = px.line(
                    trend_df,
                    x="날짜",
                    y="최고순위",
                    markers=True,
                    title=(
                        f"'{selected_trend_keyword}' "
                        "순위 추세"
                    ),
                )

                # 순위는 숫자가 낮을수록 좋으므로 Y축 반전
                figure.update_yaxes(
                    autorange="reversed",
                    title="순위 (낮을수록 좋음)",
                )

                figure.update_xaxes(
                    title="날짜"
                )

                figure.update_layout(
                    hovermode="x unified",
                )

                st.plotly_chart(
                    figure,
                    use_container_width=True,
                )

                if len(trend_df) >= 2:
                    first_rank = safe_int(
                        trend_df.iloc[0][
                            "최고순위"
                        ]
                    )

                    latest_rank = safe_int(
                        trend_df.iloc[-1][
                            "최고순위"
                        ]
                    )

                    total_change = (
                        first_rank - latest_rank
                    )

                    if total_change > 0:
                        st.success(
                            f"기록 시작 이후 "
                            f"{total_change}위 상승했습니다."
                        )
                    elif total_change < 0:
                        st.warning(
                            f"기록 시작 이후 "
                            f"{abs(total_change)}위 하락했습니다."
                        )
                    else:
                        st.info(
                            "기록 시작 시점과 현재 순위가 같습니다."
                        )

                st.markdown(
                    "#### 🗓️ 작년 같은 달 비교"
                )

                current_year = str(
                    now_kst().year
                )

                last_year_data = {
                    date_value: rank
                    for date_value, rank
                    in selected_best_by_date.items()
                    if (
                        date_value[:4]
                        == previous_year
                        and date_value[5:7]
                        == current_month
                    )
                }

                current_year_data = {
                    date_value: rank
                    for date_value, rank
                    in selected_best_by_date.items()
                    if (
                        date_value[:4]
                        == current_year
                        and date_value[5:7]
                        == current_month
                    )
                }

                if (
                    last_year_data
                    and current_year_data
                ):
                    last_year_best = min(
                        last_year_data.values()
                    )

                    current_year_best = min(
                        current_year_data.values()
                    )

                    year_change = (
                        last_year_best
                        - current_year_best
                    )

                    if year_change > 0:
                        st.success(
                            f"작년 최고 {last_year_best}위 → "
                            f"올해 최고 {current_year_best}위 "
                            f"({year_change}위 개선)"
                        )
                    elif year_change < 0:
                        st.warning(
                            f"작년 최고 {last_year_best}위 → "
                            f"올해 최고 {current_year_best}위 "
                            f"({abs(year_change)}위 하락)"
                        )
                    else:
                        st.info(
                            f"작년과 올해 최고순위가 "
                            f"{current_year_best}위로 같습니다."
                        )

                else:
                    st.info(
                        "작년 또는 올해 같은 달 데이터가 부족합니다."
                    )

                display_trend_df = trend_df.copy()

                display_trend_df[
                    "날짜"
                ] = display_trend_df[
                    "날짜"
                ].dt.strftime("%Y-%m-%d")

                st.dataframe(
                    display_trend_df,
                    use_container_width=True,
                    hide_index=True,
                )

                monthly_count = {}

                for record in selected_records:
                    collected_at = str(
                        record.get("날짜", "")
                    )

                    if len(collected_at) < 7:
                        continue

                    month_value = collected_at[:7]

                    monthly_count[
                        month_value
                    ] = (
                        monthly_count.get(
                            month_value,
                            0,
                        )
                        + 1
                    )

                if monthly_count:
                    monthly_df = pd.DataFrame([
                        {
                            "월": month_value,
                            "수집건수": count,
                        }
                        for month_value, count
                        in sorted(
                            monthly_count.items()
                        )
                    ])

                    st.markdown(
                        "#### 📦 월별 수집 기록"
                    )

                    st.bar_chart(
                        monthly_df.set_index(
                            "월"
                        )["수집건수"]
                    )
# ============================================================
# 4-D. 교차구매 분석 / 사입 후보 / 데이터 관리
# ============================================================

import inspect
from io import BytesIO

NAVER_CLIENT_ID = globals().get("naver_client_id", "")
NAVER_CLIENT_SECRET = globals().get("naver_client_secret", "")
GOOGLE_SHEET_ID = globals().get("google_sheet_id", "")
APP_PASSWORD = globals().get("app_password", "")

def call_with_supported_arguments(func, argument_map):
    """
    함수 버전별 매개변수 차이를 최대한 흡수하기 위한 호출 도우미입니다.
    전달 가능한 매개변수만 골라서 호출합니다.
    """
    signature = inspect.signature(func)
    supported_arguments = {}

    for parameter_name, parameter in signature.parameters.items():
        if parameter_name in argument_map:
            supported_arguments[parameter_name] = argument_map[parameter_name]

    return func(**supported_arguments)


def extract_dataframe_from_result(result):
    """
    분석 함수 반환값이 DataFrame, tuple, dict 등이어도
    화면에 표시할 DataFrame을 최대한 찾아 반환합니다.
    """
    if isinstance(result, pd.DataFrame):
        return result

    if isinstance(result, tuple):
        dataframes = [
            item for item in result
            if isinstance(item, pd.DataFrame)
        ]

        if dataframes:
            return max(dataframes, key=len)

        for item in result:
            if isinstance(item, list):
                if item and isinstance(item[0], dict):
                    return pd.DataFrame(item)

                if not item:
                    continue

    if isinstance(result, dict):
        preferred_keys = [
            "result",
            "results",
            "data",
            "dataframe",
            "df",
            "cross_purchase",
            "candidates",
        ]

        for key in preferred_keys:
            value = result.get(key)

            if isinstance(value, pd.DataFrame):
                return value

        dataframes = [
            value for value in result.values()
            if isinstance(value, pd.DataFrame)
        ]

        if dataframes:
            return max(dataframes, key=len)

    if isinstance(result, list):
        try:
            return pd.DataFrame(result)
        except Exception:
            return pd.DataFrame()

    return pd.DataFrame()


def dataframe_to_excel_bytes(dataframe, sheet_name="분석결과"):
    """
    DataFrame을 다운로드 가능한 Excel 바이너리로 변환합니다.
    """
    output = BytesIO()

    safe_sheet_name = str(sheet_name)[:31]

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(
            writer,
            index=False,
            sheet_name=safe_sheet_name,
        )

    output.seek(0)
    return output.getvalue()


def render_result_download_buttons(
    dataframe,
    file_prefix,
    sheet_name="분석결과",
):
    """
    CSV 및 Excel 다운로드 버튼을 표시합니다.
    """
    if dataframe is None or dataframe.empty:
        return

    csv_data = dataframe.to_csv(
        index=False,
        encoding="utf-8-sig",
    ).encode("utf-8-sig")

    excel_data = dataframe_to_excel_bytes(
        dataframe,
        sheet_name=sheet_name,
    )

    download_col1, download_col2 = st.columns(2)

    with download_col1:
        st.download_button(
            label="⬇️ CSV 다운로드",
            data=csv_data,
            file_name=f"{file_prefix}_{now_kst().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with download_col2:
        st.download_button(
            label="⬇️ Excel 다운로드",
            data=excel_data,
            file_name=f"{file_prefix}_{now_kst().strftime('%Y%m%d_%H%M')}.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
        )


# 4-A에서 메뉴 변수명이 menu 또는 selected_menu로 작성된 경우 모두 대응합니다.
current_menu = globals().get(
    "selected_menu",
    globals().get("menu", ""),
)


# ============================================================
# 1. 교차구매 분석
# ============================================================

if current_menu == "🛒 교차구매 분석":
    st.title("🛒 교차구매 분석")

    st.info(
        "주문번호와 상품명이 포함된 주문 Excel 파일을 업로드하면, "
        "특정 상품과 함께 구매된 상품을 주문번호 기준으로 분석합니다."
    )

    cross_files = st.file_uploader(
        "주문내역 Excel 파일 업로드",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        key="cross_purchase_files",
        help=(
            "여러 파일을 한 번에 업로드할 수 있습니다. "
            "동일 주문번호의 중복 상품 행은 자동으로 정리됩니다."
        ),
    )

    target_product_keyword = st.text_input(
        "기준 상품명 또는 검색어",
        placeholder="예: 타이라바, 메탈지그, 에기",
        key="cross_target_product",
    )

    cross_option_col1, cross_option_col2 = st.columns(2)

    with cross_option_col1:
        cross_top_n = st.number_input(
            "표시할 연관상품 수",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
            key="cross_top_n",
        )

    with cross_option_col2:
        cross_min_orders = st.number_input(
            "최소 동시구매 주문 수",
            min_value=1,
            max_value=100,
            value=2,
            step=1,
            key="cross_min_orders",
        )

    if st.button(
        "🔎 교차구매 분석 실행",
        type="primary",
        use_container_width=True,
        key="run_cross_purchase",
    ):
        if not cross_files:
            st.warning("주문내역 Excel 파일을 먼저 업로드해 주세요.")

        elif not target_product_keyword.strip():
            st.warning("기준 상품명 또는 검색어를 입력해 주세요.")

        else:
            try:
                with st.spinner("주문내역을 통합하고 교차구매 상품을 분석 중입니다..."):
                    argument_map = {
                        # 업로드 파일 계열
                        "uploaded_files": cross_files,
                        "files": cross_files,
                        "excel_files": cross_files,
                        "order_files": cross_files,

                        # 기준상품 계열
                        "target_query": target_product_keyword.strip(),
                        "target_product": target_product_keyword.strip(),
                        "target_keyword": target_product_keyword.strip(),
                        "keyword": target_product_keyword.strip(),
                        "product_keyword": target_product_keyword.strip(),

                        # 옵션 계열
                        "top_n": int(cross_top_n),
                        "limit": int(cross_top_n),
                        "min_orders": int(cross_min_orders),
                        "min_count": int(cross_min_orders),
                    }

                    cross_result = call_with_supported_arguments(
                        analyze_cross_purchase,
                        argument_map,
                    )

                    cross_dataframe = extract_dataframe_from_result(
                        cross_result
                    )

                    if not cross_dataframe.empty:
                        count_column_candidates = [
                            "동시구매 주문수",
                            "교차구매 주문수",
                            "주문수",
                            "구매건수",
                            "건수",
                            "count",
                        ]

                        count_column = next(
                            (
                                column
                                for column in count_column_candidates
                                if column in cross_dataframe.columns
                            ),
                            None,
                        )

                        if count_column:
                            numeric_count = pd.to_numeric(
                                cross_dataframe[count_column],
                                errors="coerce",
                            ).fillna(0)

                            cross_dataframe = cross_dataframe.loc[
                                numeric_count >= int(cross_min_orders)
                            ].copy()

                            cross_dataframe = cross_dataframe.sort_values(
                                count_column,
                                ascending=False,
                            ).head(int(cross_top_n))

                    st.session_state["cross_purchase_result"] = (
                        cross_dataframe
                    )

                    st.session_state["cross_purchase_target"] = (
                        target_product_keyword.strip()
                    )

            except Exception as error:
                st.session_state.pop(
                    "cross_purchase_result",
                    None,
                )

                st.error(
                    "교차구매 분석 중 오류가 발생했습니다."
                )

                with st.expander("오류 상세 내용"):
                    st.code(str(error))

    saved_cross_result = st.session_state.get(
        "cross_purchase_result"
    )

    if isinstance(saved_cross_result, pd.DataFrame):
        st.divider()

        if saved_cross_result.empty:
            st.warning(
                "조건에 맞는 교차구매 결과가 없습니다. "
                "기준 상품명이나 최소 주문 수를 조정해 보세요."
            )

        else:
            st.subheader(
                f"📊 '{st.session_state.get('cross_purchase_target', '')}' "
                "교차구매 결과"
            )

            metric_col1, metric_col2, metric_col3 = st.columns(3)

            with metric_col1:
                st.metric(
                    "연관상품 수",
                    f"{len(saved_cross_result):,}개",
                )

            with metric_col2:
                numeric_columns = saved_cross_result.select_dtypes(
                    include="number"
                ).columns.tolist()

                if numeric_columns:
                    first_numeric_column = numeric_columns[0]
                    total_value = pd.to_numeric(
                        saved_cross_result[first_numeric_column],
                        errors="coerce",
                    ).fillna(0).sum()

                    st.metric(
                        "연관 구매 합계",
                        f"{int(total_value):,}건",
                    )
                else:
                    st.metric("연관 구매 합계", "-")

            with metric_col3:
                st.metric(
                    "분석 기준",
                    st.session_state.get(
                        "cross_purchase_target",
                        "-",
                    ),
                )

            st.dataframe(
                saved_cross_result,
                use_container_width=True,
                hide_index=True,
            )

            render_result_download_buttons(
                saved_cross_result,
                file_prefix="교차구매_분석",
                sheet_name="교차구매분석",
            )


# ============================================================
# 2. 사입 후보 찾기
# ============================================================

elif current_menu == "🎯 사입 후보 발굴":
    st.title("🎯 사입 후보 찾기")

    st.info(
        "자사 취급 상품과 네이버 쇼핑 검색 결과를 비교해 "
        "미취급 상품 및 제품군 후보를 찾습니다."
    )

    candidate_base_keywords = st.text_area(
        "기준 검색어",
        placeholder=(
            "검색어를 한 줄에 하나씩 입력하세요.\n"
            "예:\n"
            "타이라바\n"
            "메탈지그\n"
            "쭈꾸미 에기"
        ),
        height=140,
        key="candidate_base_keywords",
    )

    product_master_file = st.file_uploader(
        "자사 상품 마스터 Excel 업로드",
        type=["xlsx", "xls"],
        key="candidate_product_master",
        help=(
            "상품명, 브랜드, 모델명, 품번, 판매처 등의 컬럼이 있으면 "
            "동일상품 및 동일제품군 판정 정확도가 높아집니다."
        ),
    )

    with st.expander("🔧 검색 및 판정 옵션", expanded=True):
        candidate_col1, candidate_col2 = st.columns(2)

        with candidate_col1:
            candidate_max_results = st.number_input(
                "검색어별 최대 수집 상품 수",
                min_value=100,
                max_value=1000,
                value=300,
                step=100,
                key="candidate_max_results",
            )

            candidate_min_volume = st.number_input(
                "최소 월간 검색량",
                min_value=0,
                max_value=1000000,
                value=10,
                step=10,
                key="candidate_min_volume",
            )

            candidate_exclude_owned = st.checkbox(
                "자사 동일상품 제외",
                value=True,
                key="candidate_exclude_owned",
            )

        with candidate_col2:
            candidate_max_keywords = st.number_input(
                "최대 검색 조합 수",
                min_value=5,
                max_value=200,
                value=40,
                step=5,
                key="candidate_max_keywords",
            )

            candidate_limit = st.number_input(
                "최종 후보 표시 수",
                min_value=10,
                max_value=500,
                value=100,
                step=10,
                key="candidate_limit",
            )

            candidate_exclude_group = st.checkbox(
                "이미 취급 중인 동일제품군 제외",
                value=False,
                key="candidate_exclude_group",
                help=(
                    "브랜드·어종·장르·모델 등의 조합이 유사한 상품군을 "
                    "이미 취급 중인 것으로 판단해 제외합니다."
                ),
            )

        candidate_col3, candidate_col4, candidate_col5 = st.columns(3)

        with candidate_col3:
            candidate_exclude_used = st.checkbox(
                "중고상품 제외",
                value=True,
                key="candidate_exclude_used",
            )

        with candidate_col4:
            candidate_exclude_rental = st.checkbox(
                "렌탈상품 제외",
                value=True,
                key="candidate_exclude_rental",
            )

        with candidate_col5:
            candidate_exclude_overseas = st.checkbox(
                "해외직구 제외",
                value=True,
                key="candidate_exclude_overseas",
            )

    if st.button(
        "🚀 사입 후보 분석 실행",
        type="primary",
        use_container_width=True,
        key="run_candidate_search",
    ):
        base_keywords = [
            keyword.strip()
            for keyword in candidate_base_keywords.replace(",", "\n").splitlines()
            if keyword.strip()
        ]

        # 입력 순서를 유지하면서 중복 제거
        base_keywords = list(dict.fromkeys(base_keywords))

        if not base_keywords:
            st.warning("기준 검색어를 한 개 이상 입력해 주세요.")

        elif product_master_file is None:
            st.warning("자사 상품 마스터 Excel 파일을 업로드해 주세요.")

        else:
            try:
                with st.spinner("자사 상품 마스터를 불러오는 중입니다..."):
                    product_master_file.seek(0)

                    product_master_dataframe = pd.read_excel(
                        product_master_file,
                        dtype=str,
                        engine="openpyxl",
                    ).fillna("")

                    product_master_dataframe.columns = [
                        str(column).strip()
                        for column in product_master_dataframe.columns
                    ]

                if product_master_dataframe.empty:
                    st.warning(
                        "상품 마스터에서 분석 가능한 데이터를 찾지 못했습니다."
                    )

                else:
                    with st.spinner("자사 상품 취급 범위를 분석 중입니다..."):
                        coverage_argument_map = {
                            "store_dataframe": product_master_dataframe,
                            "product_df": product_master_dataframe,
                            "product_dataframe": product_master_dataframe,
                            "df": product_master_dataframe,
                            "master_df": product_master_dataframe,
                            "product_master": product_master_dataframe,
                        }

                        store_coverage = call_with_supported_arguments(
                            build_store_coverage,
                            coverage_argument_map,
                        )

                    progress_placeholder = st.empty()
                    progress_bar = st.progress(0)

                    progress_placeholder.info(
                        "네이버 쇼핑 검색 결과와 검색량을 분석하고 있습니다."
                    )

                    candidate_argument_map = {
                        # 기준 검색어
                        "base_keywords": base_keywords,
                        "keywords": base_keywords,
                        "seed_keywords": base_keywords,

                        # 자사 상품 마스터
                        "product_df": product_master_dataframe,
                        "product_dataframe": product_master_dataframe,
                        "master_df": product_master_dataframe,
                        "product_master": product_master_dataframe,

                        # 취급 범위
                        "store_coverage": store_coverage,
                        "coverage": store_coverage,
                        "owned_coverage": store_coverage,

                        # 검색 옵션
                        "max_results": int(candidate_max_results),
                        "max_items": int(candidate_max_results),
                        "display_limit": int(candidate_max_results),

                        "max_keywords": int(candidate_max_keywords),
                        "keyword_limit": int(candidate_max_keywords),

                        "min_volume": int(candidate_min_volume),
                        "minimum_volume": int(candidate_min_volume),

                        "limit": int(candidate_limit),
                        "top_n": int(candidate_limit),

                        # 제외 옵션
                        "exclude_owned": bool(candidate_exclude_owned),
                        "exclude_same_product": bool(
                            candidate_exclude_owned
                        ),
                        "exclude_owned_group": bool(
                            candidate_exclude_group
                        ),
                        "exclude_same_group": bool(
                            candidate_exclude_group
                        ),
                        "exclude_used": bool(candidate_exclude_used),
                        "exclude_rental": bool(candidate_exclude_rental),
                        "exclude_overseas": bool(
                            candidate_exclude_overseas
                        ),

                        # 인증정보
                        "client_id": NAVER_CLIENT_ID,
                        "client_secret": NAVER_CLIENT_SECRET,
                        "naver_client_id": NAVER_CLIENT_ID,
                        "naver_client_secret": NAVER_CLIENT_SECRET,

                        # Streamlit 진행 표시
                        "progress_bar": progress_bar,
                        "progress": progress_bar,
                        "status_placeholder": progress_placeholder,
                    }

                    with st.spinner(
                        "사입 후보를 수집하고 점수를 계산 중입니다..."
                    ):
                        candidate_result = call_with_supported_arguments(
                            find_candidates,
                            candidate_argument_map,
                        )

                    progress_bar.progress(100)
                    progress_placeholder.success(
                        "사입 후보 분석이 완료되었습니다."
                    )

                    candidate_dataframe = extract_dataframe_from_result(
                        candidate_result
                    )

                    if not candidate_dataframe.empty:
                        score_columns = [
                            "후보점수",
                            "종합점수",
                            "점수",
                            "score",
                        ]

                        score_column = next(
                            (
                                column
                                for column in score_columns
                                if column in candidate_dataframe.columns
                            ),
                            None,
                        )

                        if score_column:
                            candidate_dataframe[score_column] = pd.to_numeric(
                                candidate_dataframe[score_column],
                                errors="coerce",
                            ).fillna(0)

                            candidate_dataframe = (
                                candidate_dataframe
                                .sort_values(
                                    score_column,
                                    ascending=False,
                                )
                                .head(int(candidate_limit))
                                .reset_index(drop=True)
                            )
                        else:
                            candidate_dataframe = (
                                candidate_dataframe
                                .head(int(candidate_limit))
                                .reset_index(drop=True)
                            )

                    st.session_state["candidate_result"] = (
                        candidate_dataframe
                    )

                    st.session_state["candidate_keywords"] = (
                        base_keywords
                    )

                    st.session_state["candidate_master_count"] = len(
                        product_master_dataframe
                    )

            except Exception as error:
                st.session_state.pop("candidate_result", None)

                st.error("사입 후보 분석 중 오류가 발생했습니다.")

                with st.expander("오류 상세 내용"):
                    st.code(str(error))

    saved_candidate_result = st.session_state.get(
        "candidate_result"
    )

    if isinstance(saved_candidate_result, pd.DataFrame):
        st.divider()

        if saved_candidate_result.empty:
            st.warning(
                "조건에 맞는 사입 후보가 없습니다. "
                "최소 검색량을 낮추거나 제품군 제외 옵션을 해제해 보세요."
            )

        else:
            st.subheader("🏆 사입 후보 분석 결과")

            candidate_metric_col1, candidate_metric_col2, candidate_metric_col3 = (
                st.columns(3)
            )

            with candidate_metric_col1:
                st.metric(
                    "분석 검색어",
                    f"{len(st.session_state.get('candidate_keywords', [])):,}개",
                )

            with candidate_metric_col2:
                st.metric(
                    "자사 상품 수",
                    f"{st.session_state.get('candidate_master_count', 0):,}개",
                )

            with candidate_metric_col3:
                st.metric(
                    "발견 후보 수",
                    f"{len(saved_candidate_result):,}개",
                )

            display_candidate_dataframe = saved_candidate_result.copy()

            st.dataframe(
                display_candidate_dataframe,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "링크": st.column_config.LinkColumn(
                        "상품 링크",
                        display_text="상품 보기",
                    ),
                    "상품링크": st.column_config.LinkColumn(
                        "상품 링크",
                        display_text="상품 보기",
                    ),
                    "image": st.column_config.ImageColumn("이미지"),
                    "이미지": st.column_config.ImageColumn("이미지"),
                    "최저가": st.column_config.NumberColumn(
                        "최저가",
                        format="%d원",
                    ),
                    "가격": st.column_config.NumberColumn(
                        "가격",
                        format="%d원",
                    ),
                    "후보점수": st.column_config.ProgressColumn(
                        "후보점수",
                        min_value=0,
                        max_value=100,
                    ),
                },
            )

            render_result_download_buttons(
                saved_candidate_result,
                file_prefix="사입후보",
                sheet_name="사입후보",
            )

            with st.expander("📌 결과 해석 방법"):
                st.markdown(
                    """
                    - **동일상품 취급 여부**: productId, 브랜드, 모델명,
                      품번 등을 기준으로 판단합니다.
                    - **동일제품군 취급 여부**: 브랜드, 어종, 장르,
                      시즌 태그 등의 유사도를 기준으로 판단합니다.
                    - **검색량 추정 여부**: 네이버 검색광고 API에서
                      `<10`으로 제공한 값은 추정값으로 표시될 수 있습니다.
                    - **후보점수**: 검색량, 네이버 노출 정도, 판매처,
                      가격 경쟁력, 자사 미취급 여부 등을 종합한 값입니다.
                    - 최종 사입 결정 전에는 실제 도매가격, 마진,
                      최소주문수량, 배송비를 추가로 확인하세요.
                    """
                )


# ============================================================
# 3. 데이터 관리
# ============================================================

elif current_menu == "⚙️ 데이터 관리":
    st.title("⚙️ 데이터 관리")

    st.warning(
        "데이터 관리 기능은 Google Sheet 구조를 변경할 수 있습니다. "
        "실행 전 Google Sheet 사본을 만들어 두는 것을 권장합니다."
    )

    management_tab1, management_tab2, management_tab3 = st.tabs(
        [
            "📦 순위기록 통합",
            "🧹 캐시 관리",
            "ℹ️ 시스템 정보",
        ]
    )

    # --------------------------------------------------------
    # 3-1. 기존 키워드별 시트 → 통합 순위기록 시트 마이그레이션
    # --------------------------------------------------------
    with management_tab1:
        st.subheader("📦 기존 순위기록 통합")

        st.markdown(
            """
            기존 버전은 검색 키워드마다 별도의 워크시트에
            순위기록을 저장했습니다.

            새 버전은 모든 기록을 **`📊 통합 순위기록`**
            워크시트에 저장하고 `키워드` 컬럼으로 구분합니다.
            """
        )

        st.info(
            "마이그레이션은 한 번만 실행하면 됩니다. "
            "이미 이전된 행은 recordID 또는 기록정보를 기준으로 "
            "중복 저장되지 않도록 처리됩니다."
        )

        confirm_migration = st.checkbox(
            "Google Sheet 백업 또는 사본 생성을 확인했습니다.",
            value=False,
            key="confirm_rank_migration",
        )

        migration_col1, migration_col2 = st.columns(2)

        with migration_col1:
            if st.button(
                "🔄 기존 순위시트 통합 실행",
                type="primary",
                use_container_width=True,
                disabled=not confirm_migration,
                key="run_rank_migration",
            ):
                try:
                    with st.spinner(
                        "기존 키워드별 순위시트를 통합하고 있습니다..."
                    ):
                        migration_arguments = {
                            "dry_run": False,
                            "delete_legacy": False,
                            "remove_legacy": False,
                        }

                        migration_result = call_with_supported_arguments(
                            migrate_legacy_rank_sheets,
                            migration_arguments,
                        )

                    st.session_state["migration_result"] = (
                        migration_result
                    )

                    st.success(
                        "순위기록 통합 작업이 완료되었습니다. "
                        "기존 키워드별 시트는 삭제하지 않았습니다."
                    )

                except Exception as error:
                    st.error("순위기록 통합 중 오류가 발생했습니다.")

                    with st.expander("오류 상세 내용"):
                        st.code(str(error))

        with migration_col2:
            if st.button(
                "🔃 마이그레이션 결과 초기화",
                use_container_width=True,
                key="clear_migration_result",
            ):
                st.session_state.pop(
                    "migration_result",
                    None,
                )
                st.rerun()

        migration_result = st.session_state.get(
            "migration_result"
        )

        if migration_result is not None:
            st.divider()
            st.subheader("마이그레이션 결과")

            if isinstance(migration_result, pd.DataFrame):
                st.dataframe(
                    migration_result,
                    use_container_width=True,
                    hide_index=True,
                )

            elif isinstance(migration_result, dict):
                result_columns = st.columns(
                    min(max(len(migration_result), 1), 4)
                )

                for index, (key, value) in enumerate(
                    migration_result.items()
                ):
                    target_column = result_columns[
                        index % len(result_columns)
                    ]

                    with target_column:
                        if isinstance(
                            value,
                            (int, float, str, bool),
                        ):
                            st.metric(str(key), str(value))

                with st.expander("전체 마이그레이션 응답"):
                    st.json(migration_result)

            elif isinstance(migration_result, (list, tuple)):
                try:
                    migration_dataframe = pd.DataFrame(
                        migration_result
                    )

                    st.dataframe(
                        migration_dataframe,
                        use_container_width=True,
                        hide_index=True,
                    )

                except Exception:
                    st.write(migration_result)

            else:
                st.write(migration_result)

        st.divider()

        st.markdown(
            """
            #### 주의사항

            - 기존 키워드별 워크시트는 자동 삭제하지 않습니다.
            - 통합 결과를 확인한 후 필요할 때만 직접 정리하세요.
            - `📋 모니터링 목록`, `📢 광고진단 기록`,
              `⚙️ 마이그레이션 기록` 워크시트는 삭제하면 안 됩니다.
            - 자동수집은 통합 이후부터 `📊 통합 순위기록`에 저장됩니다.
            """
        )

    # --------------------------------------------------------
    # 3-2. Streamlit 캐시 관리
    # --------------------------------------------------------
    with management_tab2:
        st.subheader("🧹 Streamlit 캐시 관리")

        st.write(
            "API 응답이나 Google Sheet 조회 결과가 오래된 것처럼 "
            "보일 경우 캐시를 초기화할 수 있습니다."
        )

        if st.button(
            "🧹 전체 데이터 캐시 초기화",
            type="primary",
            use_container_width=True,
            key="clear_all_data_cache",
        ):
            try:
                st.cache_data.clear()

                cache_session_keys = [
                    "rank_search_result",
                    "batch_monitor_result",
                    "keyword_analysis_result",
                    "ad_diagnosis_result",
                    "cross_purchase_result",
                    "candidate_result",
                ]

                for session_key in cache_session_keys:
                    st.session_state.pop(
                        session_key,
                        None,
                    )

                st.success(
                    "데이터 캐시와 저장된 분석 결과를 초기화했습니다."
                )

            except Exception as error:
                st.error("캐시 초기화 중 오류가 발생했습니다.")
                st.code(str(error))

        st.caption(
            "캐시 초기화는 Google Sheet에 저장된 실제 데이터를 "
            "삭제하지 않습니다."
        )

    # --------------------------------------------------------
    # 3-3. 시스템 정보
    # --------------------------------------------------------
    with management_tab3:
        st.subheader("ℹ️ 시스템 정보")

        system_col1, system_col2 = st.columns(2)

        with system_col1:
            st.markdown("#### 현재 설정")

            st.write(
                "네이버 쇼핑 API:",
                "✅ 설정됨" if (
                    NAVER_CLIENT_ID and NAVER_CLIENT_SECRET
                ) else "❌ 미설정",
            )

            st.write(
                "Google Sheet ID:",
                "✅ 설정됨" if GOOGLE_SHEET_ID else "❌ 미설정",
            )

            st.write(
                "앱 비밀번호:",
                "✅ 설정됨" if APP_PASSWORD else "❌ 미설정",
            )

            st.write(
                "기준 시간대:",
                "Asia/Seoul",
            )

        with system_col2:
            st.markdown("#### 주요 워크시트")

            st.code(
                "\n".join(
                    [
                        "📊 통합 순위기록",
                        "📋 모니터링 목록",
                        "📢 광고진단 기록",
                        "⚙️ 마이그레이션 기록",
                    ]
                )
            )

        st.divider()

        st.markdown("#### 보안 점검")

        security_checks = {
            "NAVER_CLIENT_ID": bool(NAVER_CLIENT_ID),
            "NAVER_CLIENT_SECRET": bool(NAVER_CLIENT_SECRET),
            "GOOGLE_SHEET_ID": bool(GOOGLE_SHEET_ID),
            "APP_PASSWORD": bool(APP_PASSWORD),
        }

        security_dataframe = pd.DataFrame(
            [
                {
                    "설정 항목": key,
                    "상태": "✅ 설정됨" if value else "❌ 미설정",
                }
                for key, value in security_checks.items()
            ]
        )

        st.dataframe(
            security_dataframe,
            use_container_width=True,
            hide_index=True,
        )

        st.warning(
            "API 키, 서비스 계정 JSON, 앱 비밀번호는 "
            "main.py나 GitHub 공개 저장소에 직접 입력하지 마세요."
        )

        if GOOGLE_SHEET_ID:
            sheet_url = (
                "https://docs.google.com/spreadsheets/d/"
                f"{GOOGLE_SHEET_ID}"
            )

            st.link_button(
                "📗 Google Sheet 열기",
                sheet_url,
                use_container_width=True,
            )


# ============================================================
# 메뉴 변수 또는 메뉴명이 맞지 않을 경우 안내
# ============================================================

elif current_menu == "":
    st.warning(
        "메뉴 선택값을 확인할 수 없습니다. "
        "4-A 코드의 메뉴 변수명이 menu 또는 selected_menu인지 확인해 주세요."
    )
