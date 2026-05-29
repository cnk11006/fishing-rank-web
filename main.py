# =============================================
# 피싱템 순위 레이더 - 전체 코드 (최종 수정본)
# =============================================

import streamlit as st
import requests
import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pandas as pd
import hmac
import hashlib
import base64

# =============================================
# [0] 페이지 설정
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
    AD_CUSTOMER_ID = st.secrets["NAVER_AD_CUSTOMER_ID"]
    AD_ACCESS_LICENSE = st.secrets["NAVER_AD_ACCESS_LICENSE"]
    AD_SECRET_KEY = st.secrets["NAVER_AD_SECRET_KEY"]
except Exception:
    st.error("보안 설정(Secrets)이 완료되지 않았습니다.")
    st.stop()

# =============================================
# [2] 구글 시트 연결 함수 (캐싱 적용 - 속도 향상)
# =============================================
@st.cache_resource
def get_google_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)


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
        rows_to_add = [
            [
                today,
                item["순위"],
                item["상품명"],
                item["판매처"],
                item["가격"],
                item["링크"],
                item.get("썸네일", "")
            ]
            for item in found_items
        ]
        worksheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")
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
            has_header = any(cell in ["날짜", "순위", "상품명"] for cell in first_row)
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


# 데이터 로드 캐싱 적용 (_sh 언더바 적용하여 캐시 충돌 방지)
@st.cache_data(ttl=300)
def load_all_sheets_at_once(_sh, keywords):
    """모든 키워드 데이터를 한 번에 로드 (API 호출 최소화)"""
    all_data = {}
    for kw in keywords:
        try:
            worksheet = _sh.worksheet(kw)
            all_values = worksheet.get_all_values()
            if not all_values:
                all_data[kw] = []
                continue

            first_row = all_values[0]
            has_header = any(cell in ["날짜", "순위", "상품명"] for cell in first_row)
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

            def get_val(row, col_name, _col_map=col_map):
                idx = _col_map.get(col_name)
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
            all_data[kw] = records
            time.sleep(0.1) # 속도 개선을 위해 슬립 시간 단축

        except gspread.exceptions.WorksheetNotFound:
            all_data[kw] = []
        except Exception:
            all_data[kw] = []

    return all_data


# =============================================
# [3] 모니터링 목록 관리 함수
# =============================================
MONITOR_SHEET_NAME = "📋 모니터링 목록"

# 목록 불러오기 캐싱 적용
@st.cache_data(ttl=300)
def load_monitor_keywords(_sh=None):
    try:
        if _sh is None:
            _sh = get_google_sheet()
        worksheet = get_or_create_worksheet(_sh, MONITOR_SHEET_NAME, rows=500, cols=3)
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


# 다중 삭제 기능으로 변경
def delete_multiple_monitor_keywords(keywords_to_delete):
    try:
        sh = get_google_sheet()
        worksheet = sh.worksheet(MONITOR_SHEET_NAME)
        records = worksheet.get_all_records()
        
        # 삭제할 행 번호 찾기 (헤더가 있으므로 start=2)
        rows_to_delete = []
        for i, row in enumerate(records, start=2):
            if row["키워드"] in keywords_to_delete:
                rows_to_delete.append(i)
                
        # 아래 행부터 지워야 인덱스가 밀리지 않음
        for row_idx in sorted(rows_to_delete, reverse=True):
            worksheet.delete_rows(row_idx)
            time.sleep(0.1) # API 오류 방지
        return True
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
# [5] 네이버 광고 API 함수
# =============================================
def get_ad_api_header(method, uri):
    timestamp = str(int(time.time() * 1000))
    signature_raw = f"{timestamp}.{method}.{uri}"
    hashed = hmac.new(
        AD_SECRET_KEY.encode("utf-8"),
        signature_raw.encode("utf-8"),
        hashlib.sha256
    )
    signature = base64.b64encode(hashed.digest()).decode("utf-8")
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": AD_ACCESS_LICENSE,
        "X-Customer": str(AD_CUSTOMER_ID),
        "X-Signature": signature
    }

# 광고 API 결과도 캐싱하여 속도 개선
@st.cache_data(ttl=600)
def get_keyword_stats(keywords):
    uri = "/keywordstool"
    base_url = "https://api.naver.com"
    all_results = []

    competition_map = {
        "low": "🟢 낮음", "mid": "🟡 중간", "high": "🔴 높음",
        "Low": "🟢 낮음", "Mid": "🟡 중간", "High": "🔴 높음",
        "LOW": "🟢 낮음", "MID": "🟡 중간", "HIGH": "🔴 높음",
        "낮음": "🟢 낮음", "중간": "🟡 중간", "높음": "🔴 높음",
    }

    for i in range(0, len(keywords), 5):
        chunk = keywords[i:i+5]
        params = "&".join([f"hintKeywords={kw}" for kw in chunk])
        full_uri = f"{uri}?{params}&showDetail=1"
        headers = get_ad_api_header("GET", uri)

        try:
            response = requests.get(base_url + full_uri, headers=headers)
            if response.status_code == 200:
                data = response.json()
                keyword_list = data.get("keywordList", [])
                for item in keyword_list:
                    monthly_pc = item.get("monthlyPcQcCnt", 0)
                    monthly_mobile = item.get("monthlyMobileQcCnt", 0)
                    try:
                        monthly_pc = int(monthly_pc)
                    except Exception:
                        monthly_pc = 5
                    try:
                        monthly_mobile = int(monthly_mobile)
                    except Exception:
                        monthly_mobile = 5
                    competition = item.get("compIdx", "")
                    competition_label = competition_map.get(competition, f"{competition}")
                    all_results.append({
                        "키워드": item.get("relKeyword", ""),
                        "PC 검색량": monthly_pc,
                        "모바일 검색량": monthly_mobile,
                        "총 검색량": monthly_pc + monthly_mobile,
                        "경쟁강도": competition_label,
                        "PC 클릭률": item.get("monthlyAvePcClkCnt", 0),
                        "모바일 클릭률": item.get("monthlyAveMobileClkCnt", 0),
                    })
            time.sleep(0.2)
        except Exception as e:
            st.warning(f"광고 API 오류: {e}")

    return all_results


# =============================================
# [6] SEO 분석 함수 
# =============================================
def analyze_seo(keyword, product_name, selected_related_kws):
    issues = []
    goods = []
    score = 100

    name_len = len(product_name)
    if name_len < 15:
        issues.append(("❌ 상품명이 너무 짧아요", f"현재 {name_len}자 → 25~35자 권장"))
        score -= 20
    elif name_len > 50:
        issues.append(("⚠️ 상품명이 너무 길어요", f"현재 {name_len}자 → 25~35자 권장, 핵심 키워드만 남기세요"))
        score -= 10
    else:
        goods.append(f"✅ 상품명 길이 적정 ({name_len}자)")

    keyword_clean = keyword.replace(" ", "")
    name_clean = product_name.replace(" ", "")
    if keyword_clean in name_clean:
        goods.append(f"✅ 핵심 키워드 '{keyword}' 포함됨")
    else:
        issues.append(("❌ 핵심 키워드 미포함", f"상품명에 '{keyword}' 키워드를 추가하세요"))
        score -= 30

    special_chars = ['!', '@', '#', '$', '%', '^', '&', '*', '~', '+']
    found_special = [c for c in product_name if c in special_chars]
    if len(found_special) > 2:
        issues.append(("⚠️ 특수문자 과다 사용", f"'{' '.join(set(found_special))}' → 네이버 검색 불이익 가능"))
        score -= 10
    else:
        goods.append("✅ 특수문자 적정 사용")

    if product_name.startswith(TARGET_STORE):
        issues.append(("⚠️ 브랜드명이 맨 앞에 위치", "핵심 키워드를 앞으로, 브랜드명은 뒤로 이동 권장"))
        score -= 10
    else:
        goods.append("✅ 핵심 키워드 우선 배치")

    words = product_name.split()
    duplicates = [w for w in set(words) if words.count(w) > 1 and len(w) > 1]
    if duplicates:
        issues.append(("⚠️ 중복 단어 발견", f"'{', '.join(duplicates)}' → 중복 제거 권장"))
        score -= 10
    else:
        goods.append("✅ 중복 단어 없음")

    included = []
    not_included = []
    for kw in selected_related_kws:
        kw_clean = kw.replace(" ", "")
        if kw_clean in name_clean:
            included.append(kw)
        else:
            not_included.append(kw)

    if included:
        goods.append(f"✅ 연관 키워드 포함: {', '.join(included)}")
    if not_included:
        issues.append(("💡 추가 가능한 연관 키워드", f"'{', '.join(not_included)}' → 검색 노출 확대 가능"))

    score = max(0, score)
    recommended_name = generate_recommended_name(keyword, product_name, selected_related_kws)

    return {
        "score": score,
        "issues": issues,
        "goods": goods,
        "recommended_name": recommended_name,
        "related_keywords": selected_related_kws
    }


def generate_recommended_name(keyword, original_name, selected_related_kws):
    name_without_brand = original_name.replace(TARGET_STORE, "").strip()
    keyword_clean = keyword.replace(" ", "")
    name_clean = name_without_brand.replace(" ", "")

    if keyword_clean not in name_clean:
        base = f"{keyword} {name_without_brand}"
    else:
        base = name_without_brand

    for kw in selected_related_kws:
        kw_clean = kw.replace(" ", "")
        base_clean = base.replace(" ", "")
        if kw_clean not in base_clean and len(base) + len(kw) + 1 <= 35:
            base = f"{base} {kw}"

    if len(base) + len(TARGET_STORE) + 1 <= 40:
        recommended = f"{base} {TARGET_STORE}".strip()
    else:
        recommended = base.strip()

    return recommended


# =============================================
# [7] 상세 분석 패널 함수 
# =============================================
def render_detail_panel(kw, history, sh):
    st.markdown(f"## 🔍 '{kw}' 상세 분석")
    st.divider()

    st.markdown("#### 🏆 현재 경쟁사 TOP 10 실시간 분석")

    with st.spinner("🛰️ 경쟁사 데이터 수집 중..."):
        found, price_list, top100, err = collect_rank_data(kw, CLIENT_ID, CLIENT_SECRET)

    if err:
        st.error(f"데이터 수집 오류: {err}")
    else:
        our_prices = [i["가격"] for i in found if i["가격"] > 0]
        our_avg = int(sum(our_prices) / len(our_prices)) if our_prices else 0
        avg_price = int(sum(price_list) / len(price_list)) if price_list else 0
        our_best_rank = min(found, key=lambda x: x["순위"])["순위"] if found else None

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("피싱템 최고 순위", f"{our_best_rank}위" if our_best_rank else "미노출")
        c2.metric("피싱템 평균가", f"{our_avg:,}원" if our_avg else "-")
        c3.metric("시장 평균가", f"{avg_price:,}원" if avg_price else "-")
        if our_avg and avg_price:
            diff_pct = int((our_avg - avg_price) / avg_price * 100)
            c4.metric(
                "시장 대비 가격",
                f"{abs(diff_pct)}% {'비쌈 📈' if diff_pct > 0 else '저렴 📉'}",
                delta_color="inverse" if diff_pct > 0 else "normal"
            )

        st.markdown("**🥇 상위 10개 경쟁 상품**")
        top10 = top100[:10]
        for item in top10:
            is_ours = TARGET_STORE in item["판매처"] or TARGET_STORE in item["상품명"]
            badge = "🎯 **우리 상품**" if is_ours else ""
            col_img, col_info, col_price = st.columns([1, 5, 2])
            with col_img:
                if item["썸네일"]:
                    st.image(item["썸네일"], width=70)
            with col_info:
                st.markdown(
                    f"**{item['순위']}위** {badge}  \n"
                    f"[{item['상품명'][:40]}]({item['링크']})  \n"
                    f"🏪 {item['판매처']}"
                )
            with col_price:
                price_diff = item["가격"] - avg_price if avg_price else 0
                diff_str = f"▲{abs(price_diff):,}원" if price_diff > 0 else f"▼{abs(price_diff):,}원"
                st.markdown(f"**{item['가격']:,}원**  \n{diff_str}")
            st.markdown("---")

    st.divider()

    st.markdown("#### 🔍 SEO 진단 & 상품명 최적화 가이드")

    if not found:
        st.warning("피싱템 상품이 검색되지 않아 SEO 분석을 진행할 수 없습니다.")
        return

    product_options = [f"{i['순위']}위 - {i['상품명'][:30]}" for i in found]
    selected_idx = st.selectbox(
        "분석할 상품 선택",
        range(len(product_options)),
        format_func=lambda x: product_options[x],
        key=f"seo_select_{kw}"
    )
    selected_product = found[selected_idx]

    st.markdown(f"**현재 상품명:** `{selected_product['상품명']}`")
    st.markdown(f"**현재 순위:** {selected_product['순위']}위 · **판매가:** {selected_product['가격']:,}원")

    with st.spinner("📡 연관 키워드 분석 중..."):
        related_kw_data = get_keyword_stats([kw])
        related_kw_sorted = sorted(related_kw_data, key=lambda x: x["총 검색량"], reverse=True)
    
    top_candidates = [r["키워드"] for r in related_kw_sorted if r["키워드"] != kw][:10]
    st.markdown("**💡 추천 상품명 연관 키워드 필터링**")
    st.caption("상품과 전혀 관계없는 키워드(예: 낚시복 등)는 X 버튼을 눌러 제외해주세요.")
    actual_related_kws = st.multiselect(
        "SEO 최적화에 반영할 핵심 연관 키워드 (최대 3개 권장)",
        options=top_candidates,
        default=top_candidates[:3] if len(top_candidates) >= 3 else top_candidates
    )

    seo_result = analyze_seo(kw, selected_product["상품명"], actual_related_kws)

    score = seo_result["score"]
    score_color = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
    st.markdown(f"### {score_color} SEO 점수: **{score}점** / 100점")
    st.progress(score / 100)

    st.divider()

    if seo_result["goods"]:
        st.markdown("**✅ 잘된 점**")
        for good in seo_result["goods"]:
            st.markdown(f"- {good}")

    if seo_result["issues"]:
        st.markdown("**⚠️ 개선 필요 항목**")
        for title, desc in seo_result["issues"]:
            st.markdown(f"- {title}: {desc}")

    st.divider()

    st.markdown("**✏️ 추천 상품명 (SEO 최적화)**")
    st.info(f"💡 {seo_result['recommended_name']}")
    st.caption("※ 핵심 키워드 앞 배치 + 선택하신 연관 키워드 포함 + 브랜드명 후미 배치 기준으로 생성됩니다.")

    st.divider()

    st.markdown("**🖼️ 썸네일 최적화 가이드**")
    thumb_col1, thumb_col2 = st.columns(2)
    with thumb_col1:
        st.markdown("**기본 원칙**")
        st.markdown("""
- ✅ 흰색 단색 배경 (네이버 쇼핑 노출 가산점)
- ✅ 상품이 이미지의 70% 이상 차지
- ✅ 정면 + 45도 앵글 컷 모두 등록
- ❌ 워터마크/로고 과다 삽입 지양
- ❌ 텍스트 도배형 이미지 지양
        """)
    with thumb_col2:
        st.markdown("**클릭률 향상 팁**")
        st.markdown("""
- 💡 가격 강조 태그 삽입 (예: "최저가", "무료배송")
- 💡 세트 구성품 전체를 펼쳐서 촬영
- 💡 실제 사용 장면 이미지 추가 등록
- 💡 색상 다양성 보여주는 컷 별도 등록
- 💡 1:1 비율 정사각형 이미지 권장
        """)

    st.divider()

    st.markdown("**🔗 검색 노출 확대를 위한 추가 연관 키워드 목록**")
    st.caption("아래 키워드들을 상품 태그 또는 상세페이지 본문에 자연스럽게 추가하면 노출 범위가 넓어집니다.")
    if related_kw_sorted:
        df_related = pd.DataFrame(related_kw_sorted[:10])[["키워드", "총 검색량", "경쟁강도"]]
        df_related.index = df_related.index + 1
        st.dataframe(df_related, use_container_width=True, hide_index=False)


# =============================================
# [8] 로그인 로직
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
# [9] 메인 화면
# =============================================
st.title("🎣 피싱템 순위 레이더")

st.link_button(
    "📊 구글 시트에서 전체 기록 보기",
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
)

tab1, tab2, tab3 = st.tabs(["🔍 순위 수색", "📋 모니터링 관리", "📊 키워드 분석"])


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
                st.success(f"✅ 400위 내에서 총 {len(found_items)}개의 자사 상품을 발견했습니다!")
                
                st.markdown("### 📌 선택 상품 모니터링 바로 등록")
                st.caption("아래 목록에서 모니터링할 상품을 체크한 뒤 등록 버튼을 누르시면 관리 탭으로 연동됩니다.")
                
                selected_products = []
                
                COLS_PER_ROW = 3
                for row_start in range(0, len(found_items), COLS_PER_ROW):
                    row_items = found_items[row_start: row_start + COLS_PER_ROW]
                    cols = st.columns(COLS_PER_ROW)
                    for col, item in zip(cols, row_items):
                        with col:
                            with st.container(border=True):
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
                                
                                is_checked = st.checkbox(f"모니터링 담기", key=f"chk_{item['순위']}_{item['상품명'][:5]}")
                                if is_checked:
                                    selected_products.append(item['상품명'])
                                    
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
                
                if st.button("🚀 선택한 상품 모니터링 관리로 등록하기", type="primary", use_container_width=True):
                    if not selected_products:
                        st.warning("선택된 상품이 없습니다. 체크박스를 선택해주세요.")
                    else:
                        memo_text = ", ".join(selected_products)[:40]
                        success, msg = add_monitor_keyword(keyword, memo=f"등록상품: {memo_text}")
                        if success:
                            st.success(f"✅ '{keyword}' 키워드가 모니터링 탭에 성공적으로 추가되었습니다!")
                            # 데이터가 변경되었으므로 캐시 초기화
                            load_monitor_keywords.clear()
                            load_all_sheets_at_once.clear()
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"오류: {msg}")


# =============================================
# TAB 2 - 모니터링 관리
# =============================================
with tab2:
    st.subheader("📋 모니터링 키워드 관리")
    st.caption("등록된 키워드를 모니터링하거나 불필요한 키워드를 체크하여 일괄 삭제할 수 있습니다.")

    st.markdown("#### ➕ 수동 키워드 추가 (옵션)")
    with st.expander("키워드 직접 입력하여 등록하기"):
        col_input, col_memo, col_btn = st.columns([2, 2, 1])
        with col_input:
            new_keyword = st.text_input("키워드", placeholder="예: 타이라바 로드", label_visibility="collapsed")
        with col_memo:
            new_memo = st.text_input("메모 (선택)", placeholder="예: 주력상품 키워드", label_visibility="collapsed")
        with col_btn:
            if st.button("➕ 수동 등록", use_container_width=True):
                if not new_keyword:
                    st.warning("키워드를 입력해주세요.")
                else:
                    with st.spinner("등록 중..."):
                        success, msg = add_monitor_keyword(new_keyword.strip(), new_memo.strip())
                    if success:
                        st.success(f"✅ '{new_keyword}' 등록 완료!")
                        # 데이터가 추가되었으므로 캐시 초기화
                        load_monitor_keywords.clear()
                        load_all_sheets_at_once.clear()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)

    st.divider()

    st.markdown("#### 📌 등록된 모니터링 키워드 현황")
    st.caption("삭제할 키워드의 하단 **[🗑️ 삭제 선택]**을 체크한 후 아래의 **삭제 버튼**을 눌러 일괄 제거하세요.")

    with st.spinner("목록 불러오는 중..."):
        sh = get_google_sheet()
        monitor_keywords = load_monitor_keywords(_sh=sh)

    if "detail_keyword" not in st.session_state:
        st.session_state["detail_keyword"] = None

    selected_for_deletion = []

    if not monitor_keywords:
        st.info("등록된 키워드가 없습니다. [🔍 순위 수색] 탭에서 키워드를 검색 후 등록해보세요!")
    else:
        st.caption(f"총 {len(monitor_keywords)}개 키워드 등록됨")

        with st.spinner("📊 순위 데이터 불러오는 중..."):
            all_history = load_all_sheets_at_once(_sh=sh, keywords=monitor_keywords)

        COLS_PER_ROW = 4
        for row_start in range(0, len(monitor_keywords), COLS_PER_ROW):
            row_kws = monitor_keywords[row_start: row_start + COLS_PER_ROW]
            cols = st.columns(COLS_PER_ROW)
            for col, kw in zip(cols, row_kws):
                with col:
                    history = all_history.get(kw, [])
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

                        if st.button("🔍 상세분석", key=f"detail_btn_{kw}", use_container_width=True):
                            if st.session_state["detail_keyword"] == kw:
                                st.session_state["detail_keyword"] = None
                            else:
                                st.session_state["detail_keyword"] = kw
                            st.rerun()
                        
                        # 체크박스로 삭제할 키워드 선택
                        is_delete_checked = st.checkbox("🗑️ 삭제 선택", key=f"del_chk_{kw}")
                        if is_delete_checked:
                            selected_for_deletion.append(kw)

        # 체크박스 다중 삭제 실행 버튼
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ 선택한 모니터링 키워드 일괄 삭제", type="secondary"):
            if not selected_for_deletion:
                st.warning("삭제할 키워드를 선택해주세요.")
            else:
                with st.spinner("삭제 중..."):
                    if delete_multiple_monitor_keywords(selected_for_deletion):
                        st.success(f"✅ {len(selected_for_deletion)}개 키워드가 모니터링 목록에서 삭제되었습니다!")
                        # 캐시 초기화로 화면 즉시 갱신
                        load_monitor_keywords.clear()
                        load_all_sheets_at_once.clear()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("삭제에 실패했습니다.")

        # 상세분석 패널
        if st.session_state["detail_keyword"]:
            selected_kw = st.session_state["detail_keyword"]
            st.divider()
            with st.container(border=True):
                close_col, _ = st.columns([1, 8])
                with close_col:
                    if st.button("✖ 닫기", key="close_detail"):
                        st.session_state["detail_keyword"] = None
                        st.rerun()
                selected_history = all_history.get(selected_kw, [])
                render_detail_panel(selected_kw, selected_history, sh)

        st.divider()

        # --- 섹션 4: 전체 일괄 수색 ---
        st.markdown("#### 🚀 등록 키워드 전체 일괄 수색")
        st.caption("등록된 모든 키워드를 순서대로 수색하고 결과를 구글 시트에 즉시 저장합니다.")

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
                    results_summary.append({"키워드": kw, "결과": f"❌ 오류: {err}", "발견 수": 0})
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
                    results_summary.append({"키워드": kw, "결과": "⚠️ 400위 내 미노출", "발견 수": 0})

                time.sleep(0.3)

            overall_progress.progress(1.0, text="✅ 전체 수색 완료!")
            st.success("🎉 일괄 수색 완료! 결과 요약:")
            df_result = pd.DataFrame(results_summary)
            st.dataframe(df_result, use_container_width=True, hide_index=True)

            # 수색 완료 후 새로운 데이터 반영을 위해 캐시 비우기
            load_all_sheets_at_once.clear()
            time.sleep(1)
            st.rerun()


# =============================================
# TAB 3 - 키워드 분석
# =============================================
with tab3:
    st.subheader("📊 키워드 분석")
    st.caption("네이버 광고 API 기반 키워드 검색량, 경쟁강도, 연관 키워드를 분석합니다.")

    st.markdown("#### 🔍 키워드 기본 분석")
    col_kw, col_btn = st.columns([4, 1])
    with col_kw:
        analysis_keyword = st.text_input(
            "분석할 키워드 입력",
            placeholder="예: 타이라바 로드",
            label_visibility="collapsed"
        )
    with col_btn:
        analyze_btn = st.button("🔍 분석 시작", type="primary", use_container_width=True)

    if analyze_btn:
        if not analysis_keyword:
            st.warning("키워드를 입력해주세요.")
        else:
            with st.spinner("📡 네이버 광고 API에서 데이터 불러오는 중..."):
                results = get_keyword_stats([analysis_keyword])

            if not results:
                st.error("데이터를 불러오지 못했습니다. API 키를 확인해주세요.")
            else:
                main_result = next(
                    (r for r in results if r["키워드"] == analysis_keyword),
                    results[0]
                )
                st.session_state["analysis_keyword"] = analysis_keyword
                st.session_state["analysis_results"] = results
                st.session_state["main_result"] = main_result

    if "main_result" in st.session_state:
        main_result = st.session_state["main_result"]
        results = st.session_state["analysis_results"]
        analysis_keyword = st.session_state["analysis_keyword"]

        st.divider()
        st.markdown(f"##### 📌 '{analysis_keyword}' 키워드 분석 결과")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("💻 PC 검색량", f"{main_result['PC 검색량']:,}")
        c2.metric("📱 모바일 검색량", f"{main_result['모바일 검색량']:,}")
        c3.metric("🔢 총 검색량", f"{main_result['총 검색량']:,}")
        c4.metric("⚔️ 경쟁강도", main_result["경쟁강도"])
        c5.metric("🖱️ PC 클릭수", f"{main_result['PC 클릭률']:,}")

        st.divider()

        st.markdown("#### 🔗 연관 키워드 분석")
        st.caption("검색량 높은 순으로 정렬됩니다.")

        if len(results) > 0:
            df_results = pd.DataFrame(results)
            df_results = df_results.sort_values("총 검색량", ascending=False).reset_index(drop=True)
            df_results.index = df_results.index + 1

            display_df = df_results[["키워드", "PC 검색량", "모바일 검색량", "총 검색량", "경쟁강도"]].copy()
            st.dataframe(display_df, use_container_width=True)

            csv_data = df_results[["키워드", "PC 검색량", "모바일 검색량", "총 검색량", "경쟁강도"]].to_csv(
                index=False, encoding="utf-8-sig"
            ).encode("utf-8-sig")
            st.download_button(
                label="📥 엑셀(CSV)로 다운로드",
                data=csv_data,
                file_name=f"{analysis_keyword}_키워드분석_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv; charset=utf-8-sig",
                use_container_width=True
            )
