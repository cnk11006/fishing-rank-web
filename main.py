# =============================================
# 피싱템 순위 레이더 - 전체 코드
# =============================================

import streamlit as st
import requests
import time
import gspread
from google.oauth2.service_account import Credentials
import plotly.graph_objects as go
from datetime import datetime
import pandas as pd

# =============================================
# [0] 페이지 설정 - 반드시 최상단에 위치
# =============================================
st.set_page_config(page_title="피싱템 순위 추적기", layout="wide")

# =============================================
# [1] 보안 및 상호명 설정
# =============================================
TARGET_STORE = "피싱템"

try:
    CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]
    MASTER_PASSWORD = st.secrets["APP_PASSWORD"]
    SHEET_ID = st.secrets["GOOGLE_SHEET_ID"]
except Exception:
    st.error("보안 설정(Secrets)이 완료되지 않았습니다.")
    st.stop()

# =============================================
# [2] 구글 시트 연결 함수 (세션당 1회만 연결)
# =============================================
def get_google_sheet():
    if "google_sheet" not in st.session_state:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scopes
        )
        client = gspread.authorize(creds)
        st.session_state["google_sheet"] = client.open_by_key(SHEET_ID)
    return st.session_state["google_sheet"]


def get_or_create_worksheet(sh, title, rows=1000, cols=10):
    try:
        return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=rows, cols=cols)


def save_to_sheet(keyword, found_items):
    try:
        sh = get_google_sheet()
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        worksheet = get_or_create_worksheet(sh, keyword)

        all_values = worksheet.get_all_values()
        non_empty_rows = [row for row in all_values if any(cell.strip() for cell in row)]

        if not non_empty_rows:
            worksheet.append_row(["날짜", "순위", "상품명", "판매처", "가격", "링크", "썸네일"])

        for item in found_items:
            worksheet.append_row([
                today,
                item["순위"],
                item["상품명"],
                item["판매처"],
                item["가격"],
                item["링크"],
                item.get("썸네일", "")
            ])
        return True
    except Exception as e:
        st.error(f"구글 시트 저장 오류: {e}")
        return False


def load_from_sheet(keyword, sh=None):
    try:
        if sh is None:
            sh = get_google_sheet()
        try:
            worksheet = sh.worksheet(keyword)
            all_values = worksheet.get_all_values()

            if not all_values:
                return []

            first_row = all_values[0]

            has_header = any(
                cell in ["날짜", "순위", "상품명"] for cell in first_row
            )

            if has_header:
                header = first_row
                data_rows = all_values[1:]
            else:
                data_rows = all_values
                col_count = len(first_row)
                if col_count >= 7:
                    header = ["날짜", "순위", "상품명", "판매처", "가격", "링크", "썸네일"]
                else:
                    header = ["날짜", "순위", "상품명", "판매처", "가격", "링크"]

            col_map = {name: i for i, name in enumerate(header)}

            def get_val(row, col_name):
                idx = col_map.get(col_name)
                if idx is None or idx >= len(row):
                    return ""
                return row[idx]

            records = []
            for row in data_rows:
                if not row or not any(row):
                    continue
                record = {
                    "날짜":   get_val(row, "날짜"),
                    "순위":   get_val(row, "순위"),
                    "상품명": get_val(row, "상품명"),
                    "판매처": get_val(row, "판매처"),
                    "가격":   get_val(row, "가격"),
                    "링크":   get_val(row, "링크"),
                    "썸네일": get_val(row, "썸네일"),
                }
                if record["날짜"] and str(record["순위"]).strip() and record["상품명"]:
                    records.append(record)

            return records

        except gspread.exceptions.WorksheetNotFound:
            return []
    except Exception:
        return []


# =============================================
# [3] 모니터링 목록 관리 함수
# =============================================
MONITOR_SHEET_NAME = "📋 모니터링 목록"

def load_monitor_keywords(sh=None):
    try:
        if sh is None:
            sh = get_google_sheet()
        worksheet = get_or_create_worksheet(sh, MONITOR_SHEET_NAME, rows=500, cols=3)
        existing = worksheet.get_all_values()
        if not existing or existing[0] != ["키워드", "등록일", "메모"]:
            worksheet.clear()
            worksheet.append_row(["키워드", "등록일", "메모"])
            return []
        records = worksheet.get_all_records()
        return [r["키워드"] for r in records if r.get("키워드")]
    except Exception as e:
        st.error(f"모니터링 목록 불러오기 오류: {e}")
        return []


def add_monitor_keyword(keyword, memo=""):
    try:
        sh = get_google_sheet()
        worksheet = get_or_create_worksheet(sh, MONITOR_SHEET_NAME, rows=500, cols=3)
        existing = worksheet.get_all_values()
        if not existing:
            worksheet.append_row(["키워드", "등록일", "메모"])
        records = worksheet.get_all_records()
        existing_keywords = [r["키워드"] for r in records]
        if keyword in existing_keywords:
            return False, "이미 등록된 키워드입니다."
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        worksheet.append_row([keyword, today, memo])
        return True, "등록 완료"
    except Exception as e:
        return False, f"등록 오류: {e}"


def delete_monitor_keyword(keyword):
    try:
        if "google_sheet" in st.session_state:
            del st.session_state["google_sheet"]
        sh = get_google_sheet()
        worksheet = sh.worksheet(MONITOR_SHEET_NAME)
        records = worksheet.get_all_records()
        for i, row in enumerate(records, start=2):
            if row["키워드"] == keyword:
                worksheet.delete_rows(i)
                return True
        return False
    except Exception as e:
        st.error(f"삭제 오류: {e}")
        return False


# =============================================
# [4] 네이버 쇼핑 순위 수집 함수
# =============================================
def collect_rank_data(keyword, client_id, client_secret):
    found_items = []
    price_list = []
    top100_items = []
    error_msg = None

    for page in range(4):
        start_num = (page * 100) + 1
        url = (
            f"https://openapi.naver.com/v1/search/shop.json"
            f"?query={keyword}&display=100&start={start_num}"
        )
        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret
        }
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            items = response.json().get('items', [])
            if not items:
                break
            for index, item in enumerate(items):
                mall_name = item.get('mallName', '')
                clean_title = item['title'].replace('<b>', '').replace('</b>', '')
                if page == 0:
                    try:
                        price = int(item.get('lprice', 0))
                        if price > 0:
                            price_list.append(price)
                            top100_items.append({
                                "순위": start_num + index,
                                "상품명": clean_title,
                                "판매처": mall_name,
                                "링크": item.get('link', ''),
                                "썸네일": item.get('image', ''),
                                "가격": price
                            })
                    except Exception:
                        pass
                if TARGET_STORE in mall_name or TARGET_STORE in item['title']:
                    found_items.append({
                        "순위": start_num + index,
                        "상품명": clean_title,
                        "판매처": mall_name,
                        "링크": item.get('link', ''),
                        "썸네일": item.get('image', ''),
                        "가격": int(item.get('lprice', 0))
                    })
            time.sleep(0.1)
        else:
            error_msg = f"API 오류 ({start_num}위 구간)"
            break

    return found_items, price_list, top100_items, error_msg


# =============================================
# [5] 순위 변동 그래프 함수
# =============================================
def render_rank_graph(keyword, sh=None):
    data = load_from_sheet(keyword, sh=sh)
    if not data:
        st.info(f"'{keyword}' 키워드의 저장된 데이터가 없습니다. 먼저 수색을 진행해주세요!")
        return

    products = {}
    for row in data:
        name = row.get("상품명", "")[:20]
        date = row.get("날짜", "")
        rank = row.get("순위", 0)
        if not name or not date or not rank:
            continue
        if name not in products:
            products[name] = {"dates": [], "ranks": []}
        products[name]["dates"].append(date)
        products[name]["ranks"].append(int(rank))

    if not products:
        st.info("유효한 그래프 데이터가 없습니다.")
        return

    fig = go.Figure()
    for name, values in products.items():
        fig.add_trace(go.Scatter(
            x=values["dates"],
            y=values["ranks"],
            mode="lines+markers",
            name=name,
            line=dict(width=2),
            marker=dict(size=8)
        ))

    fig.update_layout(
        title=f"'{keyword}' 순위 변동 추이",
        xaxis_title="날짜",
        yaxis_title="순위",
        yaxis=dict(autorange="reversed"),
        height=400,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=-0.4),
        margin=dict(t=40, b=80)
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"총 {len(data)}개의 기록 데이터 기반")


# =============================================
# [6] 로그인 로직
# =============================================
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if not st.session_state['authenticated']:
    st.title("🔐 피싱템 보안 접속")
    pwd_input = st.text_input("접속 비밀번호를 입력하세요", type="password")
    if st.button("로그인"):
        if pwd_input == MASTER_PASSWORD:
            st.session_state['authenticated'] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    st.stop()

# =============================================
# [7] 메인 화면
# =============================================
st.title("🎣 피싱템 순위 레이더")

st.link_button(
    "📊 구글 시트에서 전체 기록 보기",
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
)

tab1, tab2 = st.tabs(["🔍 순위 수색", "📋 모니터링 관리"])


# =============================================
# TAB 1 - 순위 수색
# =============================================
with tab1:
    keyword = st.text_input("수색할 키워드를 입력하세요 (예: 타이라바 로드)")

    if st.button("🚀 400위까지 정밀 수색 시작"):
        if not keyword:
            st.warning("키워드를 입력해주세요.")
        else:
            progress_text = st.empty()
            found_items = []
            price_list = []
            top100_items = []

            for page in range(4):
                start_num = (page * 100) + 1
                progress_text.info(f"🛰️ {start_num}위 ~ {start_num + 99}위 구간 수색 중...")
                url = (
                    f"https://openapi.naver.com/v1/search/shop.json"
                    f"?query={keyword}&display=100&start={start_num}"
                )
                headers = {
                    "X-Naver-Client-Id": CLIENT_ID,
                    "X-Naver-Client-Secret": CLIENT_SECRET
                }
                response = requests.get(url, headers=headers)

                if response.status_code == 200:
                    items = response.json().get('items', [])
                    if not items:
                        break
                    for index, item in enumerate(items):
                        mall_name = item.get('mallName', '')
                        clean_title = item['title'].replace('<b>', '').replace('</b>', '')
                        if page == 0:
                            try:
                                price = int(item.get('lprice', 0))
                                if price > 0:
                                    price_list.append(price)
                                    top100_items.append({
                                        "순위": start_num + index,
                                        "상품명": clean_title,
                                        "판매처": mall_name,
                                        "링크": item.get('link', ''),
                                        "썸네일": item.get('image', ''),
                                        "가격": price
                                    })
                            except Exception:
                                pass
                        if TARGET_STORE in mall_name or TARGET_STORE in item['title']:
                            found_items.append({
                                "순위": start_num + index,
                                "상품명": clean_title,
                                "판매처": mall_name,
                                "링크": item.get('link', ''),
                                "썸네일": item.get('image', ''),
                                "가격": int(item.get('lprice', 0))
                            })
                    time.sleep(0.1)
                else:
                    st.error(f"API 호출 오류 (구간: {start_num}위)")
                    break

            progress_text.empty()

            if found_items:
                with st.spinner("📊 구글 시트에 기록 중..."):
                    if save_to_sheet(keyword, found_items):
                        st.success("✅ 구글 시트에 자동 저장 완료!")

            avg_price = 0
            min_price = 0
            max_price = 0
            our_avg = 0

            if price_list:
                min_price = min(price_list)
                max_price = max(price_list)
                avg_price = int(sum(price_list) / len(price_list))
                our_prices = [i["가격"] for i in found_items if i["가격"] > 0]
                our_avg = int(sum(our_prices) / len(our_prices)) if our_prices else 0
                diff_pct = int((our_avg - avg_price) / avg_price * 100) if avg_price > 0 else 0
                diff_label = (
                    f"시장 평균보다 {abs(diff_pct)}% "
                    f"{'💸 비쌈' if diff_pct > 0 else '✅ 저렴'}"
                )

                if found_items:
                    best_rank = min(found_items, key=lambda x: x["순위"])["순위"]
                    st.info(
                        f"**'{keyword}'** 키워드 · 피싱템 **{len(found_items)}개** 노출 중 · "
                        f"최고 순위 **{best_rank}위** · {diff_label}"
                    )

                st.subheader("💰 키워드 시장 가격 분석 (1위 ~ 100위 기준)")
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("최저가", f"{min_price:,}원")
                col2.metric("평균 판매가", f"{avg_price:,}원")
                col3.metric("최고가", f"{max_price:,}원")
                col4.metric("피싱템 평균가", f"{our_avg:,}원")
                col5.metric(
                    "시장 평균 대비",
                    f"{abs(diff_pct)}% {'↑' if diff_pct > 0 else '↓'}",
                    delta=f"{'비쌈' if diff_pct > 0 else '저렴'}",
                    delta_color="inverse" if diff_pct > 0 else "normal"
                )

                st.markdown("**📊 가격대별 상품 분포 (1위 ~ 100위)**")
                ranges = {
                    "1만원 이하": len([p for p in price_list if p <= 10000]),
                    "1만 ~ 3만원": len([p for p in price_list if 10000 < p <= 30000]),
                    "3만 ~ 5만원": len([p for p in price_list if 30000 < p <= 50000]),
                    "5만원 이상": len([p for p in price_list if p > 50000]),
                }
                rc1, rc2, rc3, rc4 = st.columns(4)
                for col, (label, count) in zip([rc1, rc2, rc3, rc4], ranges.items()):
                    col.metric(label, f"{count}개")

                st.divider()

                st.subheader("🏅 최저가 TOP 5 (1위 ~ 100위 기준)")
                top5 = sorted(top100_items, key=lambda x: x["가격"])[:5]
                t_cols = st.columns(5)
                for i, (col, item) in enumerate(zip(t_cols, top5)):
                    with col:
                        if item["썸네일"]:
                            st.image(item["썸네일"], width=120)
                        medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i]
                        st.markdown(f"**{medal} {item['가격']:,}원**")
                        st.markdown(
                            f"[{item['상품명'][:20]}...]({item['링크']})"
                            if len(item['상품명']) > 20
                            else f"[{item['상품명']}]({item['링크']})"
                        )
                        st.caption(f"검색 {item['순위']}위 · {item['판매처']}")

                st.divider()

            if not found_items:
                st.error(f"⚠️ 현재 '{TARGET_STORE}' 상품이 400위 내에 비노출 중입니다.")
            else:
                st.success(f"✅ 400위 내에서 총 {len(found_items)}개의 상품을 발견했습니다!")
                st.divider()

                COLS_PER_ROW = 3
                for row_start in range(0, len(found_items), COLS_PER_ROW):
                    row_items = found_items[row_start: row_start + COLS_PER_ROW]
                    cols = st.columns(COLS_PER_ROW)
                    for col, item in zip(cols, row_items):
                        with col:
                            if item["썸네일"]:
                                st.image(item["썸네일"], width=150)
                            else:
                                st.markdown(
                                    "<div style='height:150px; background:#f0f0f0;"
                                    "display:flex; align-items:center;"
                                    "justify-content:center; border-radius:8px;"
                                    "color:#999;'>이미지 없음</div>",
                                    unsafe_allow_html=True
                                )
                            st.markdown(f"### 🏆 {item['순위']}위")
                            st.markdown(f"**[{item['상품명']}]({item['링크']})**")
                            st.caption(f"🏪 판매처: {item['판매처']}")
                            if item["가격"] > 0 and avg_price > 0:
                                diff = int((item["가격"] - avg_price) / avg_price * 100)
                                diff_str = (
                                    f"📈 시장 평균보다 {abs(diff)}% 비쌈"
                                    if diff > 0
                                    else f"📉 시장 평균보다 {abs(diff)}% 저렴"
                                )
                                st.caption(f"💴 판매가: {item['가격']:,}원")
                                st.caption(diff_str)
                            st.markdown("---")


# =============================================
# TAB 2 - 모니터링 관리
# =============================================
with tab2:
    st.subheader("📋 모니터링 키워드 관리")
    st.caption("등록한 키워드를 자동으로 추적합니다. GitHub Actions를 설정하면 매일 자동 수집됩니다.")

    # --- 섹션 1: 키워드 등록 ---
    st.markdown("#### ➕ 키워드 등록")
    col_input, col_memo, col_btn = st.columns([2, 2, 1])
    with col_input:
        new_keyword = st.text_input("키워드", placeholder="예: 타이라바 로드", label_visibility="collapsed")
    with col_memo:
        new_memo = st.text_input("메모 (선택)", placeholder="예: 주력상품 키워드", label_visibility="collapsed")
    with col_btn:
        if st.button("➕ 등록", use_container_width=True):
            if not new_keyword:
                st.warning("키워드를 입력해주세요.")
            else:
                with st.spinner("등록 중..."):
                    success, msg = add_monitor_keyword(new_keyword.strip(), new_memo.strip())
                if success:
                    st.success(f"✅ '{new_keyword}' 등록 완료!")
                    st.rerun()
                else:
                    st.error(msg)

    st.divider()

    # --- 섹션 2: 등록된 키워드 현황 (카드 형태) ---
    st.markdown("#### 📌 등록된 모니터링 키워드 현황")

    with st.spinner("목록 불러오는 중..."):
        sh = get_google_sheet()
        monitor_keywords = load_monitor_keywords(sh=sh)

    if not monitor_keywords:
        st.info("등록된 키워드가 없습니다. 위에서 키워드를 등록해보세요!")
    else:
        st.caption(f"총 {len(monitor_keywords)}개 키워드 등록됨")

        COLS_PER_ROW = 4
        for row_start in range(0, len(monitor_keywords), COLS_PER_ROW):
            row_kws = monitor_keywords[row_start: row_start + COLS_PER_ROW]
            cols = st.columns(COLS_PER_ROW)
            for col, kw in zip(cols, row_kws):
                with col:
                    history = load_from_sheet(kw, sh=sh)

                    thumbnail = ""
                    link = ""
                    best_rank_now = None
                    change_str = "➖ 첫 수집"
                    status = "⚪ 데이터 없음"
                    latest_date = "-"
                    product_name = "-"

                    if history:
                        try:
                            latest_date = max(set(r["날짜"] for r in history))
                            latest_records = [r for r in history if r["날짜"] == latest_date]
                            best_record = min(latest_records, key=lambda x: int(x["순위"]))
                            best_rank_now = int(best_record["순위"])
                            product_name = best_record.get("상품명", "-")
                            thumbnail = best_record.get("썸네일", "")
                            link = best_record.get("링크", "")

                            all_dates = sorted(set(r["날짜"] for r in history))
                            if len(all_dates) >= 2:
                                prev_date = all_dates[-2]
                                prev_records = [r for r in history if r["날짜"] == prev_date]
                                best_rank_prev = min(int(r["순위"]) for r in prev_records)
                                change = best_rank_prev - best_rank_now
                                if change > 0:
                                    change_str = f"🔺 {change}위 상승"
                                elif change < 0:
                                    change_str = f"🔻 {abs(change)}위 하락"
                                else:
                                    change_str = "➡️ 변동 없음"

                            if best_rank_now <= 50:
                                status = "🟢 TOP 50"
                            elif best_rank_now <= 100:
                                status = "🟡 TOP 100"
                            elif best_rank_now <= 200:
                                status = "🟠 TOP 200"
                            else:
                                status = "🔴 200위 밖"
                        except Exception:
                            pass

                    with st.container(border=True):
                        if thumbnail:
                            st.image(thumbnail, width=100)
                        else:
                            st.markdown(
                                "<div style='height:100px; background:#f0f0f0;"
                                "display:flex; align-items:center;"
                                "justify-content:center; border-radius:8px;"
                                "color:#999; font-size:12px;'>이미지 없음</div>",
                                unsafe_allow_html=True
                            )

                        if link:
                            st.markdown(f"**[🔑 {kw}]({link})**")
                        else:
                            st.markdown(f"**🔑 {kw}**")

                        st.caption(
                            f"📦 {product_name[:20]}..."
                            if len(product_name) > 20
                            else f"📦 {product_name}"
                        )

                        if best_rank_now:
                            st.markdown(f"🏆 **{best_rank_now}위** · {status}")
                        else:
                            st.markdown("🏆 **미수집**")

                        st.caption(change_str)
                        st.caption(f"🕐 {latest_date}")

        st.divider()

        # --- 섹션 3: 키워드 삭제 ---
        st.markdown("#### 🗑️ 키워드 삭제")
        del_col1, del_col2 = st.columns([3, 1])
        with del_col1:
            keyword_to_delete = st.selectbox(
                "삭제할 키워드 선택",
                monitor_keywords,
                label_visibility="collapsed",
                key="delete_select"
            )
        with del_col2:
            if st.button("🗑️ 삭제", use_container_width=True, type="secondary"):
                with st.spinner("삭제 중..."):
                    if delete_monitor_keyword(keyword_to_delete):
                        st.success(f"✅ '{keyword_to_delete}' 삭제 완료!")
                        st.rerun()
                    else:
                        st.error("삭제에 실패했습니다.")

        st.divider()

        # --- 섹션 4: 전체 일괄 수색 ---
        st.markdown("#### 🚀 등록 키워드 전체 일괄 수색")
        st.caption("등록된 모든 키워드를 순서대로 수색하고 결과를 구글 시트에 저장합니다.")

        if st.button("🛰️ 전체 키워드 일괄 수색 시작", type="primary", use_container_width=True):
            total = len(monitor_keywords)
            overall_progress = st.progress(0, text="준비 중...")
            results_summary = []

            for idx, kw in enumerate(monitor_keywords):
                overall_progress.progress(
                    idx / total,
                    text=f"🔍 [{idx+1}/{total}] '{kw}' 수색 중..."
                )
                found, prices, top100, err = collect_rank_data(kw, CLIENT_ID, CLIENT_SECRET)

                if err:
                    results_summary.append({
                        "키워드": kw,
                        "결과": f"❌ 오류: {err}",
                        "발견 수": 0
                    })
                    continue

                if found:
                    save_to_sheet(kw, found)
                    best = min(found, key=lambda x: x["순위"])["순위"]
                    results_summary.append({
                        "키워드": kw,
                        "결과": f"✅ {len(found)}개 발견 (최고 {best}위)",
                        "발견 수": len(found)
                    })
                else:
                    results_summary.append({
                        "키워드": kw,
                        "결과": "⚠️ 400위 내 미노출",
                        "발견 수": 0
                    })

                time.sleep(0.3)

            overall_progress.progress(1.0, text="✅ 전체 수색 완료!")
            st.success("🎉 일괄 수색 완료! 결과 요약:")
            df_result = pd.DataFrame(results_summary)
            st.dataframe(df_result, use_container_width=True, hide_index=True)

            if "google_sheet" in st.session_state:
                del st.session_state["google_sheet"]
            time.sleep(1)
            st.rerun()

        st.divider()

        # --- 섹션 5: 키워드별 순위 변동 그래프 (맨 마지막) ---
        st.markdown("#### 📈 키워드별 순위 변동 그래프")
        selected_kw = st.selectbox(
            "그래프로 볼 키워드 선택",
            monitor_keywords,
            key="graph_select"
        )
        if st.button("📊 그래프 보기", use_container_width=True):
            with st.spinner("데이터 불러오는 중..."):
                render_rank_graph(selected_kw, sh=sh)
