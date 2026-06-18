# =============================================
# 피싱템 순위 레이더 v3 - 쇼핑광고 진단(A)+시즌(B)+TOP10평균가
# [블록 1/4]
# =============================================

import streamlit as st
import requests
import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pandas as pd
import hmac
import hashlib
import base64
import urllib.parse
import os
import json

# ---------- [0] 페이지 설정 & CSS ----------
st.set_page_config(page_title="피싱템 순위 검색기", layout="wide", page_icon="🎣")
st.markdown("""
<style>
    .stApp { background-color: #F8F9FA; }
    header {visibility: hidden;} footer {visibility: hidden;} #MainMenu {visibility: hidden;}
    [data-testid="stMetric"] {
        background-color: #ffffff; border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.04);
        padding: 15px 20px; border-left: 5px solid #0A84FF;
    }
    [data-testid="stVerticalBlock"] > [style*="border"] {
        background-color: #ffffff !important; border-radius: 15px !important;
        border: none !important; box-shadow: 0 4px 10px rgba(0,0,0,0.05) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    [data-testid="stVerticalBlock"] > [style*="border"]:hover {
        transform: translateY(-4px); box-shadow: 0 8px 15px rgba(0,0,0,0.1) !important;
    }
    [data-testid="stForm"] {
        background-color: #ffffff; border-radius: 15px;
        border: 1px solid #eef0f5; box-shadow: 0 4px 10px rgba(0,0,0,0.03);
    }
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { font-size: 1.1rem; font-weight: 600; padding-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ---------- [1] 보안 & 상호명 ----------
TARGET_STORE = "피싱템"
AD_BASE_URL = "https://api.searchad.naver.com"

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

# ---------- [2] 구글 시트 ----------
@st.cache_resource
def get_google_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

def get_or_create_worksheet(sh, title, rows=1000, cols=12):
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
        non_empty = [r for r in all_values if any(c.strip() for c in r)]
        if not non_empty:
            worksheet.append_row(["날짜","순위","상품명","판매처","가격","링크","썸네일","productType"])
        rows_to_add = [[today, item["순위"], item["상품명"], item["판매처"],
                        item["가격"], item["링크"], item.get("썸네일",""),
                        item.get("productType","")] for item in found_items]
        worksheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        st.error(f"구글 시트 저장 오류: {e}")
        return False

@st.cache_data(ttl=300)
def load_all_sheets_at_once(_sh, keywords):
    all_data = {}
    for kw in keywords:
        try:
            ws = _sh.worksheet(kw)
            all_values = ws.get_all_values()
            if not all_values:
                all_data[kw] = []; continue
            first = all_values[0]
            has_header = any(c in ["날짜","순위","상품명"] for c in first)
            if has_header:
                header = first; data_rows = all_values[1:]
            else:
                data_rows = all_values; cc = len(first)
                if cc >= 8: header = ["날짜","순위","상품명","판매처","가격","링크","썸네일","productType"]
                elif cc >= 7: header = ["날짜","순위","상품명","판매처","가격","링크","썸네일"]
                else: header = ["날짜","순위","상품명","판매처","가격","링크"]
            col_map = {n: i for i, n in enumerate(header)}
            def gv(row, name, _m=col_map):
                idx = _m.get(name)
                if idx is None or idx >= len(row): return ""
                return row[idx]
            records = []
            for row in data_rows:
                if not row or not any(row): continue
                rec = {"날짜":gv(row,"날짜"),"순위":gv(row,"순위"),"상품명":gv(row,"상품명"),
                       "판매처":gv(row,"판매처"),"가격":gv(row,"가격"),"링크":gv(row,"링크"),
                       "썸네일":gv(row,"썸네일"),"productType":gv(row,"productType")}
                if rec["날짜"] and str(rec["순위"]).strip() and rec["상품명"]:
                    records.append(rec)
            all_data[kw] = records
            time.sleep(0.1)
        except gspread.exceptions.WorksheetNotFound:
            all_data[kw] = []
        except Exception:
            all_data[kw] = []
    return all_data

# ---------- [3] 모니터링 목록 ----------
MONITOR_SHEET_NAME = "📋 모니터링 목록"

@st.cache_data(ttl=300)
def load_monitor_keywords(_sh=None):
    try:
        if _sh is None: _sh = get_google_sheet()
        ws = get_or_create_worksheet(_sh, MONITOR_SHEET_NAME, rows=500, cols=3)
        existing = ws.get_all_values()
        if not existing or existing[0] != ["키워드","등록일","메모"]:
            ws.clear(); ws.append_row(["키워드","등록일","메모"]); return []
        recs = ws.get_all_records()
        return [{"키워드":r["키워드"],"메모":r.get("메모","")} for r in recs if r.get("키워드")]
    except Exception as e:
        st.error(f"모니터링 목록 불러오기 오류: {e}")
        return []

def add_monitor_keyword(keyword, memo=""):
    try:
        sh = get_google_sheet()
        ws = get_or_create_worksheet(sh, MONITOR_SHEET_NAME, rows=500, cols=3)
        existing = ws.get_all_values()
        if not existing: ws.append_row(["키워드","등록일","메모"])
        recs = ws.get_all_records()
        for r in recs:
            if r["키워드"] == keyword and r.get("메모","") == memo:
                return False, "이미 등록된 키워드+상품 조합입니다."
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        ws.append_row([keyword, today, memo])
        return True, "등록 완료"
    except Exception as e:
        return False, f"등록 오류: {e}"

def delete_multiple_monitor_keywords(items_to_delete):
    try:
        sh = get_google_sheet()
        ws = sh.worksheet(MONITOR_SHEET_NAME)
        recs = ws.get_all_records()
        rows_to_delete = []
        for i, row in enumerate(recs, start=2):
            key = f"{row['키워드']}|||{row.get('메모','')}"
            if key in items_to_delete: rows_to_delete.append(i)
        for idx in sorted(rows_to_delete, reverse=True):
            ws.delete_rows(idx); time.sleep(0.1)
        return True
    except Exception as e:
        st.error(f"삭제 오류: {e}")
        return False

# ---------- [4] 네이버 쇼핑 순위 수집 (묶음 탐지, TOP10 평균가) ----------
def get_catalog_badge(product_type):
    pt = int(product_type) if str(product_type).strip().isdigit() else 0
    if pt == 1: return "🔗 가격비교 묶음"
    elif pt == 2: return "🟡 독립(비매칭)"
    elif pt == 3: return "✅ 독립(매칭)"
    return ""

def collect_rank_data(keyword, client_id, client_secret):
    found_items, price_list_top10, top100_items, error_msg = [], [], [], None
    for page in range(4):
        start_num = (page * 100) + 1
        url = (f"https://openapi.naver.com/v1/search/shop.json"
               f"?query={keyword}&display=100&start={start_num}")
        headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            items = response.json().get('items', [])
            if not items: break
            for index, item in enumerate(items):
                rank = start_num + index
                mall_name = item.get('mallName', '')
                clean_title = item['title'].replace('<b>','').replace('</b>','')
                try: product_type = int(item.get('productType', 0))
                except Exception: product_type = 0
                is_catalog = (product_type == 1)
                is_ours = (TARGET_STORE in mall_name) or (TARGET_STORE in clean_title)
                try: price = int(item.get('lprice', 0))
                except Exception: price = 0
                if rank <= 10 and price > 0:
                    price_list_top10.append(price)
                if page == 0 and price > 0:
                    top100_items.append({"순위":rank,"상품명":clean_title,"판매처":mall_name,
                                         "링크":item.get('link',''),"썸네일":item.get('image',''),
                                         "가격":price,"productType":product_type,"묶음여부":is_catalog})
                if is_ours:
                    found_items.append({"순위":rank,"상품명":clean_title,"판매처":mall_name,
                                        "링크":item.get('link',''),"썸네일":item.get('image',''),
                                        "가격":price,"productType":product_type,"묶음여부":is_catalog})
            time.sleep(0.1)
        else:
            error_msg = f"API 오류 ({start_num}위 구간)"; break
    return found_items, price_list_top10, top100_items, error_msg
# =============================================
# [블록 2/4] 광고 API + 쇼핑광고 진단 + SEO
# =============================================

# ---------- [5] 광고 API 공통 헤더 ----------
def get_ad_api_header(method, uri):
    timestamp = str(int(time.time() * 1000))
    sig_raw = f"{timestamp}.{method}.{uri}"
    hashed = hmac.new(AD_SECRET_KEY.encode("utf-8"), sig_raw.encode("utf-8"), hashlib.sha256)
    signature = base64.b64encode(hashed.digest()).decode("utf-8")
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": AD_ACCESS_LICENSE,
        "X-Customer": str(AD_CUSTOMER_ID),
        "X-Signature": signature
    }

# ---------- [5-1] 키워드 검색량 ----------
@st.cache_data(ttl=600)
def get_keyword_stats(keywords):
    uri = "/keywordstool"
    all_results = []
    comp_map = {"low":"🟢 낮음","mid":"🟡 중간","high":"🔴 높음",
                "Low":"🟢 낮음","Mid":"🟡 중간","High":"🔴 높음",
                "LOW":"🟢 낮음","MID":"🟡 중간","HIGH":"🔴 높음",
                "낮음":"🟢 낮음","중간":"🟡 중간","높음":"🔴 높음"}
    for i in range(0, len(keywords), 5):
        chunk = [urllib.parse.quote(kw) for kw in keywords[i:i+5]]
        params = "&".join([f"hintKeywords={kw}" for kw in chunk])
        full_uri = f"{uri}?{params}&showDetail=1"
        headers = get_ad_api_header("GET", uri)
        try:
            res = requests.get(AD_BASE_URL + full_uri, headers=headers)
            if res.status_code == 200:
                for item in res.json().get("keywordList", []):
                    try: m_pc = int(item.get("monthlyPcQcCnt", 0))
                    except Exception: m_pc = 5
                    try: m_mo = int(item.get("monthlyMobileQcCnt", 0))
                    except Exception: m_mo = 5
                    comp = item.get("compIdx", "")
                    all_results.append({
                        "키워드": item.get("relKeyword",""),
                        "PC 검색량": m_pc, "모바일 검색량": m_mo,
                        "총 검색량": m_pc + m_mo,
                        "경쟁강도": comp_map.get(comp, f"{comp}"),
                        "PC 클릭률": item.get("monthlyAvePcClkCnt", 0),
                        "모바일 클릭률": item.get("monthlyAveMobileClkCnt", 0),
                    })
            time.sleep(0.2)
        except Exception as e:
            st.warning(f"광고 API 오류: {e}")
    return all_results

# ---------- [5-2] 캠페인/광고그룹/소재/성과 ----------
@st.cache_data(ttl=300)
def ad_get_campaigns():
    uri = "/ncc/campaigns"
    try:
        res = requests.get(AD_BASE_URL + uri, headers=get_ad_api_header("GET", uri))
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []

@st.cache_data(ttl=300)
def ad_get_adgroups(campaign_id):
    uri = "/ncc/adgroups"
    try:
        res = requests.get(AD_BASE_URL + uri,
                           params={"nccCampaignId": campaign_id},
                           headers=get_ad_api_header("GET", uri))
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []

@st.cache_data(ttl=300)
def ad_get_ads(adgroup_id):
    """광고그룹의 소재(쇼핑상품) 목록"""
    uri = "/ncc/ads"
    try:
        res = requests.get(AD_BASE_URL + uri,
                           params={"nccAdgroupId": adgroup_id},
                           headers=get_ad_api_header("GET", uri))
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []

@st.cache_data(ttl=300)
def ad_get_stats(ids, days=7):
    """소재 ID 리스트로 성과 조회. return: {id: {지표들}}"""
    if not ids: return {}
    uri = "/stats"
    until = datetime.now().strftime("%Y-%m-%d")
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    fields = '["impCnt","clkCnt","ctr","cpc","salesAmt","avgRnk","ccnt"]'
    time_range = json.dumps({"since": since, "until": until})
    result = {}
    for i in range(0, len(ids), 100):
        chunk = ids[i:i+100]
        params = {"ids": chunk, "fields": fields, "timeRange": time_range}
        try:
            res = requests.get(AD_BASE_URL + uri, params=params,
                               headers=get_ad_api_header("GET", uri))
            if res.status_code == 200:
                for row in res.json().get("data", []):
                    rid = row.get("id")
                    result[rid] = {
                        "impCnt":   row.get("impCnt", 0),
                        "clkCnt":   row.get("clkCnt", 0),
                        "ctr":      row.get("ctr", 0),
                        "cpc":      row.get("cpc", 0),
                        "salesAmt": row.get("salesAmt", 0),
                        "avgRnk":   row.get("avgRnk", 0),
                        "ccnt":     row.get("ccnt", 0),
                    }
            time.sleep(0.2)
        except Exception:
            pass
    return result

# ---------- [5-3] 자동 진단 (성과 + 품질지수 + 입찰가 추천) ----------
def diagnose_ad(stat, bid_amt=None, qi_grade=None):
    imp  = float(stat.get("impCnt", 0) or 0)
    clk  = float(stat.get("clkCnt", 0) or 0)
    ctr  = float(stat.get("ctr", 0) or 0)
    rnk  = float(stat.get("avgRnk", 0) or 0)
    advice = []

    # --- 입찰가 추천 (참고용, 실제 변경은 네이버에서) ---
    bid_tip = _recommend_bid(imp, ctr, rnk, bid_amt)
    if bid_tip:
        advice.append(bid_tip)

    if qi_grade is not None and qi_grade > 0:
        if qi_grade <= 3:
            advice.append(f"품질지수 {qi_grade}/10으로 낮습니다. 썸네일·상품명·리뷰 개선이 시급합니다.")
        elif qi_grade <= 6:
            advice.append(f"품질지수 {qi_grade}/10 (보통). 클릭률을 올리면 낮은 입찰가로도 상위 노출이 가능합니다.")

    if imp == 0:
        advice.append("입찰가가 낮거나 예산 소진/소재 일시중지/검수중일 수 있습니다.")
        advice.append("입찰가 상향, 일예산·비즈머니 잔액, 소재 ON 여부를 점검하세요.")
        return "🔴", "노출 안 됨", advice

    if rnk > 0 and rnk >= 5:
        advice.append(f"평균 노출순위 {rnk:.1f}위로 낮습니다. 상위 노출이 매출에 유리합니다.")
        advice.append("입찰가 상향 또는 품질지수 개선을 검토하세요.")
    if imp >= 100 and ctr < 0.5:
        advice.append(f"클릭률(CTR) {ctr:.2f}%로 낮습니다. 썸네일·상품명·가격을 개선하세요.")
    if 0 < imp < 100:
        advice.append("노출 데이터가 아직 적습니다. 며칠 더 운영하며 품질지수를 쌓으세요.")

    if not advice:
        return "🟢", "양호", ["노출·클릭·순위가 안정적입니다. 현 입찰가를 유지하세요."]
    if rnk >= 5 and ctr < 0.5:
        return "🟠", "노출·클릭 모두 개선 필요", advice
    elif rnk >= 5:
        return "🟡", "노출은 되나 순위 낮음", advice
    elif ctr < 0.5:
        return "🟡", "노출은 되나 클릭 저조", advice
    else:
        return "🟡", "점검 권장", advice

def _recommend_bid(imp, ctr, rnk, bid_amt):
    """성과 신호에 따라 입찰가 방향만 제안 (정확한 금액 단정 X)"""
    if not bid_amt or bid_amt <= 0:
        return None
    cur = int(bid_amt)

    # 노출 자체가 없음 → 올려서 노출 확보
    if imp == 0:
        suggest = int(cur * 1.3)
        return f"💰 입찰가 추천: 노출이 없어 상향이 필요합니다. {cur:,}원 → 약 {suggest:,}원 검토 (네이버에서 변경)."

    # 노출은 되는데 순위가 낮음 → 소폭 상향
    if rnk >= 5:
        suggest = int(cur * 1.2)
        return f"💰 입찰가 추천: 평균순위가 낮아 상향 여지가 있습니다. {cur:,}원 → 약 {suggest:,}원 검토."

    # 순위 좋고 클릭률도 좋음 → 살짝 낮춰도 유지 가능
    if rnk > 0 and rnk < 3 and ctr >= 1.0:
        suggest = int(cur * 0.9)
        return f"💰 입찰가 추천: 순위·클릭이 우수합니다. {cur:,}원 → 약 {suggest:,}원으로 낮춰도 순위 유지 가능성이 있습니다."

    # 그 외 안정 구간
    return f"💰 입찰가 추천: 현재 {cur:,}원 수준 유지가 무난합니다."

def run_ad_diagnosis(adgroups, campaign_name, days):
    """광고그룹 리스트 → 소재별 진단 행 리스트 (쇼핑광고 기준)"""
    rows = []
    for ag in adgroups:
        agid = ag.get("nccAdgroupId")
        agname = ag.get("name", "")

        # 그룹이 켜져 있는지 판단 (잠김=true 거나 정지=PAUSED 면 OFF)
        group_on = (ag.get("userLock") != True) and (ag.get("status") != "PAUSED")

        ads = ad_get_ads(agid)
        if not ads: continue
        ad_ids = [a.get("nccAdId") for a in ads]
        stats = ad_get_stats(ad_ids, days=days)
        for a in ads:
            aid = a.get("nccAdId")
            stat = stats.get(aid, {})
            ad_info = a.get("ad", {})
            ref = a.get("referenceData", {})
            qi = a.get("nccQi", {}).get("qiGrade", 0)
            bid = a.get("adAttr", {}).get("bidAmt", 0)
            pname = ad_info.get("productName", ref.get("productName", ""))

            # 상품 자체가 켜져 있는지
            ad_on = (a.get("userLock") != True) and (a.get("status") == "ELIGIBLE")
            # 그룹과 상품 둘 다 켜져 있어야 진짜 ON
            is_on = group_on and ad_on

            icon, verdict, advice = diagnose_ad(stat, bid_amt=bid, qi_grade=qi)

            # 꺼진 광고는 진단 아이콘 대신 회색 표시
            if not is_on:
                icon = "⚪"
                verdict = "꺼짐 (집행 안 됨)"

            rows.append({
                "상태": icon,
                "캠페인": campaign_name,
                "광고그룹": agname,
                "상품명": pname[:30],
                "ON/OFF": "ON" if is_on else "OFF",
                "입찰가": bid,
                "품질지수": qi,
                "노출수": stat.get("impCnt", 0),
                "클릭수": stat.get("clkCnt", 0),
                "CTR(%)": round(float(stat.get("ctr", 0) or 0), 2),
                "평균순위": round(float(stat.get("avgRnk", 0) or 0), 1),
                "광고비": int(float(stat.get("salesAmt", 0) or 0)),
                "진단": verdict,
                "_advice": " / ".join(advice),
            })
        time.sleep(0.2)
    return rows
# ---------- [5-4] 진단 결과 저장 & 어제 비교 ----------
AD_HISTORY_SHEET = "📢 광고진단 기록"

def save_ad_diagnosis(rows):
    """진단 결과를 구글 시트에 누적 저장 (어제 비교용)"""
    try:
        sh = get_google_sheet()
        ws = get_or_create_worksheet(sh, AD_HISTORY_SHEET, rows=5000, cols=8)
        today = datetime.now().strftime("%Y-%m-%d")
        existing = ws.get_all_values()
        if not existing:
            ws.append_row(["날짜","상품명","노출수","클릭수","CTR","평균순위","광고비"])
        # 오늘 이미 저장했으면 중복 저장 방지 (덮어쓰기 대신 그냥 추가 안 함)
        already = [r for r in existing[1:] if r and r[0] == today]
        if already:
            return  # 오늘 이미 기록됨
        to_add = [[today, r["상품명"], r["노출수"], r["클릭수"],
                   r["CTR(%)"], r["평균순위"], r["광고비"]] for r in rows]
        if to_add:
            ws.append_rows(to_add, value_input_option="USER_ENTERED")
    except Exception:
        pass  # 저장 실패해도 진단은 계속 진행

def load_yesterday_ad(rows):
    """어제(가장 최근 과거) 기록을 불러와 {상품명: {노출수, 평균순위}} 반환"""
    try:
        sh = get_google_sheet()
        ws = sh.worksheet(AD_HISTORY_SHEET)
        values = ws.get_all_values()
        if len(values) < 2:
            return {}
        today = datetime.now().strftime("%Y-%m-%d")
        # 오늘이 아닌 날짜 중 가장 최근 날짜 찾기
        past_dates = sorted(set(r[0] for r in values[1:] if r and r[0] != today))
        if not past_dates:
            return {}
        last_date = past_dates[-1]
        prev = {}
        for r in values[1:]:
            if r and r[0] == last_date and len(r) >= 6:
                try:
                    prev[r[1]] = {"노출수": int(float(r[2] or 0)),
                                  "평균순위": float(r[5] or 0)}
                except Exception:
                    continue
        return prev
    except Exception:
        return {}

# ---------- [6] SEO 분석 ----------
def analyze_seo(keyword, product_name, selected_related_kws):
    issues, goods, score = [], [], 100
    name_len = len(product_name)
    if name_len < 15:
        issues.append(("❌ 상품명이 너무 짧아요", f"현재 {name_len}자 → 25~35자 권장")); score -= 20
    elif name_len > 50:
        issues.append(("⚠️ 상품명이 너무 길어요", f"현재 {name_len}자 → 핵심 키워드만 남기세요")); score -= 10
    else:
        goods.append(f"✅ 상품명 길이 적정 ({name_len}자)")
    kw_clean = keyword.replace(" ", ""); name_clean = product_name.replace(" ", "")
    if kw_clean in name_clean:
        goods.append(f"✅ 핵심 키워드 '{keyword}' 포함됨")
    else:
        issues.append(("❌ 핵심 키워드 미포함", f"상품명에 '{keyword}' 키워드를 추가하세요")); score -= 30
    specials = ['!','@','#','$','%','^','&','*','~','+']
    found_sp = [c for c in product_name if c in specials]
    if len(found_sp) > 2:
        issues.append(("⚠️ 특수문자 과다", f"'{' '.join(set(found_sp))}' → 검색 불이익 가능")); score -= 10
    else:
        goods.append("✅ 특수문자 적정 사용")
    if product_name.startswith(TARGET_STORE):
        issues.append(("⚠️ 브랜드명이 맨 앞", "핵심 키워드를 앞으로, 브랜드명은 뒤로")); score -= 10
    else:
        goods.append("✅ 핵심 키워드 우선 배치")
    words = product_name.split()
    dups = [w for w in set(words) if words.count(w) > 1 and len(w) > 1]
    if dups:
        issues.append(("⚠️ 중복 단어", f"'{', '.join(dups)}' → 제거 권장")); score -= 10
    else:
        goods.append("✅ 중복 단어 없음")
    included, not_inc = [], []
    for kw in selected_related_kws:
        if kw.replace(" ","") in name_clean: included.append(kw)
        else: not_inc.append(kw)
    if included: goods.append(f"✅ 연관 키워드 포함: {', '.join(included)}")
    if not_inc: issues.append(("💡 추가 가능한 연관 키워드", f"'{', '.join(not_inc)}' → 노출 확대 가능"))
    score = max(0, score)
    rec_name = generate_recommended_name(keyword, product_name, selected_related_kws)
    return {"score":score,"issues":issues,"goods":goods,
            "recommended_name":rec_name,"related_keywords":selected_related_kws}

def generate_recommended_name(keyword, original_name, selected_related_kws):
    base = original_name.replace(TARGET_STORE, "").strip()
    if keyword.replace(" ","") not in base.replace(" ",""):
        base = f"{keyword} {base}"
    for kw in selected_related_kws:
        if kw.replace(" ","") not in base.replace(" ","") and len(base)+len(kw)+1 <= 35:
            base = f"{base} {kw}"
    if len(base) + len(TARGET_STORE) + 1 <= 40:
        return f"{base} {TARGET_STORE}".strip()
    return base.strip()
    # ---------- [10] 유입·상품 분석 (엑셀 업로드) ----------
def analyze_channel_file(uploaded_file):
    """유입경로 엑셀 → 정리된 DataFrame 반환"""
    df = pd.read_excel(uploaded_file)
    # 숫자 컬럼 정리 (없을 수도 있으니 안전하게)
    def num(col):
        return pd.to_numeric(df[col], errors="coerce").fillna(0) if col in df.columns else 0
    out = pd.DataFrame({
        "채널속성": df.get("채널속성", ""),
        "채널그룹": df.get("채널그룹", ""),
        "채널명": df.get("채널명", ""),
        "유입수": num("유입수"),
        "결제수": num("결제수(마지막클릭)"),
        "결제금액": num("결제금액(마지막클릭)"),
    })
    # 유입 대비 결제율(%)
    out["결제율(%)"] = (out["결제수"] / out["유입수"].replace(0, pd.NA) * 100).fillna(0).round(2)
    return out

def analyze_product_file(uploaded_file):
    """상품별 엑셀 → 정리된 DataFrame + 4분류"""
    df = pd.read_excel(uploaded_file)
    def num(col):
        return pd.to_numeric(df[col], errors="coerce").fillna(0) if col in df.columns else 0
    out = pd.DataFrame({
        "상품명": df.get("상품명", ""),
        "상품ID": df.get("상품ID", ""),
        "조회수": num("상품상세조회수"),
        "결제금액": num("결제금액"),
        "결제수량": num("결제상품수량"),
        "결제율": num("상세조회대비결제율"),
    })
    # 4분류 기준: 조회수 중앙값, 결제율 중앙값
    view_mid = out["조회수"][out["조회수"] > 0].median() if (out["조회수"] > 0).any() else 0
    rate_mid = out["결제율"][out["결제율"] > 0].median() if (out["결제율"] > 0).any() else 0

    def classify(row):
        high_view = row["조회수"] >= view_mid
        high_rate = row["결제율"] >= rate_mid
        if high_view and high_rate:   return "🟢 효자상품"
        if high_view and not high_rate: return "🔴 개선필요"
        if not high_view and high_rate: return "🟡 숨은보석"
        return "⚪ 정리검토"
    out["분류"] = out.apply(classify, axis=1)
    return out
def analyze_search_file(uploaded_file):
    """검색채널(키워드) 엑셀 → 정리된 DataFrame. 같은 키워드 합산."""
    df = pd.read_excel(uploaded_file)
    cols = list(df.columns)

    def find_col(keywords):
        for c in cols:
            for kw in keywords:
                if kw in str(c):
                    return c
        return None

    kw_col    = find_col(["키워드", "검색어"])
    visit_col = find_col(["유입수"])
    pay_cnt   = find_col(["결제수"])
    pay_amt   = find_col(["결제금액"])

    def num(col):
        return pd.to_numeric(df[col], errors="coerce").fillna(0) if col else 0

    out = pd.DataFrame({
        "검색어": df[kw_col].astype(str) if kw_col else "",
        "유입수": num(visit_col),
        "결제수": num(pay_cnt),
        "결제금액": num(pay_amt),
    })
    out = out[~out["검색어"].isin(["(검색어 없음)", "nan", ""])]
    out = out.groupby("검색어", as_index=False).agg(
        {"유입수": "sum", "결제수": "sum", "결제금액": "sum"})
    out["결제율(%)"] = (out["검색어"].map(lambda x: 0))  # 임시
    out["결제율(%)"] = (out["결제수"] / out["유입수"].replace(0, pd.NA) * 100).fillna(0).round(2)
    return out, cols
# =============================================
# [블록 3/4] 상세분석 패널 + 로그인 + 메인 + Tab1
# =============================================

# ---------- [7] 상세 분석 패널 (TOP10 평균가) ----------
def render_detail_panel(kw, history, sh, target_name=None):
    st.markdown(f"## 🔍 '{kw}' 상세 분석")
    st.divider()
    st.markdown("#### 🏆 현재 경쟁사 TOP 10 실시간 분석")
    with st.spinner("🛰️ 경쟁사 데이터 수집 중..."):
        found, price_top10, top100, err = collect_rank_data(kw, CLIENT_ID, CLIENT_SECRET)
    if err:
        st.error(f"데이터 수집 오류: {err}")
    else:
        our_prices = [i["가격"] for i in found if i["가격"] > 0]
        our_avg = int(sum(our_prices)/len(our_prices)) if our_prices else 0
        avg_price = int(sum(price_top10)/len(price_top10)) if price_top10 else 0
        our_best = min(found, key=lambda x:x["순위"])["순위"] if found else None
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("피싱템 최고 순위", f"{our_best}위" if our_best else "미노출")
        c2.metric("피싱템 평균가", f"{our_avg:,}원" if our_avg else "-")
        c3.metric("TOP10 평균가", f"{avg_price:,}원" if avg_price else "-")
        if our_avg and avg_price:
            diff = int((our_avg-avg_price)/avg_price*100)
            c4.metric("TOP10 대비 가격", f"{abs(diff)}% {'비쌈 📈' if diff>0 else '저렴 📉'}",
                      delta_color="inverse" if diff>0 else "normal")
        st.markdown("**🥇 상위 10개 경쟁 상품**")
        for item in top100[:10]:
            is_ours = TARGET_STORE in item["판매처"] or TARGET_STORE in item["상품명"]
            badge = "🎯 **우리 상품**" if is_ours else ""
            cat_badge = get_catalog_badge(item.get("productType",0))
            ci,cf,cp = st.columns([1,5,2])
            with ci:
                if item["썸네일"]: st.image(item["썸네일"], width=70)
            with cf:
                st.markdown(f"**{item['순위']}위** {badge}  \n"
                            f"[{item['상품명'][:40]}]({item['링크']})  \n"
                            f"🏪 {item['판매처']}　{cat_badge}")
            with cp:
                pd_ = item["가격"]-avg_price if avg_price else 0
                ds = f"▲{abs(pd_):,}원" if pd_>0 else f"▼{abs(pd_):,}원"
                st.markdown(f"**{item['가격']:,}원**  \n{ds}")
            st.markdown("---")
    st.divider()
    st.markdown("#### 🔍 SEO 진단 & 상품명 최적화 가이드")
    if not found:
        st.warning("피싱템 상품이 검색되지 않아 SEO 분석을 진행할 수 없습니다."); return
    selected = None
    if target_name:
        for item in found:
            if target_name == item['상품명'] or target_name in item['상품명']:
                selected = item; break
    if not selected: selected = found[0]
    st.markdown(f"**분석 대상 상품:** `{selected['상품명']}`")
    st.markdown(f"**현재 순위:** {selected['순위']}위 · **판매가:** {selected['가격']:,}원")
    pt_badge = get_catalog_badge(selected.get("productType",0))
    pt_val = selected.get("productType",0)
    if str(pt_val) == "1":
        st.warning("🔗 **가격비교 묶음 상품으로 노출 중입니다.** 여러 판매처가 하나의 카탈로그로 묶여 mallName이 '네이버'로 표기됩니다. 독립 노출을 원하면 카탈로그 매칭 해제 또는 상품명/가격 차별화를 검토하세요.")
    elif str(pt_val) in ["2","3"]:
        st.success(f"✅ **독립 상품으로 노출 중입니다.** ({pt_badge})")
    with st.spinner("📡 연관 키워드 분석 중..."):
        rel = get_keyword_stats([kw])
        rel_sorted = sorted(rel, key=lambda x:x["총 검색량"], reverse=True)
    cands = [r["키워드"] for r in rel_sorted if r["키워드"]!=kw][:10]
    st.markdown("**💡 추천 상품명 연관 키워드 필터링**")
    st.caption("상품과 관계없는 키워드는 X 버튼으로 제외하세요.")
    actual = st.multiselect("SEO 최적화 반영 연관 키워드 (최대 3개 권장)",
                            options=cands, default=cands[:3] if len(cands)>=3 else cands)
    seo = analyze_seo(kw, selected["상품명"], actual)
    sc = seo["score"]; sccol = "🟢" if sc>=80 else "🟡" if sc>=60 else "🔴"
    st.markdown(f"### {sccol} SEO 점수: **{sc}점** / 100점")
    st.progress(sc/100); st.divider()
    if seo["goods"]:
        st.markdown("**✅ 잘된 점**")
        for g in seo["goods"]: st.markdown(f"- {g}")
    if seo["issues"]:
        st.markdown("**⚠️ 개선 필요 항목**")
        for t,d in seo["issues"]: st.markdown(f"- {t}: {d}")
    st.divider()
    st.markdown("**✏️ 추천 상품명 (SEO 최적화)**")
    st.info(f"💡 {seo['recommended_name']}")
    st.divider()
    st.markdown("**🔗 추가 연관 키워드 목록**")
    if rel_sorted:
        dfr = pd.DataFrame(rel_sorted[:10])[["키워드","총 검색량","경쟁강도"]]
        dfr.index = dfr.index + 1
        st.dataframe(dfr, use_container_width=True, hide_index=False)

# ---------- [8] 로그인 ----------
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
if not st.session_state['authenticated']:
    st.title("🔐 피싱템 보안 접속")
    pwd = st.text_input("접속 비밀번호를 입력하세요", type="password")
    if st.button("로그인"):
        if pwd == MASTER_PASSWORD:
            st.session_state['authenticated'] = True; st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    st.stop()

# ---------- [9] 메인 / 로고 ----------
if os.path.exists("logo.png"):
    with open("logo.png","rb") as f:
        enc = base64.b64encode(f.read()).decode()
    html_code = f"""<div style='margin-bottom:20px;'>
        <a href="?" target="_self" title="초기 화면">
        <img src='data:image/png;base64,{enc}' style='width:140px;cursor:pointer;'></a></div>"""
else:
    html_code = """<div style='margin-bottom:20px;'>
        <a href="?" target="_self" title="초기 화면"><div style='font-size:70px;cursor:pointer;'>🎣</div></a></div>"""
st.markdown(html_code, unsafe_allow_html=True)
st.link_button("📊 구글 시트에서 전체 기록 보기",
               f"https://docs.google.com/spreadsheets/d/{SHEET_ID}")
st.markdown("<br>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🔍 순위 검색", "📋 모니터링 관리", "📊 키워드 분석",
     "📢 광고 진단 & 시즌", "📂 유입·상품 분석"])

# ---------- TAB 1 : 순위 검색 ----------
with tab1:
    keyword = st.text_input("수색할 키워드를 입력하세요 (예: 타이라바 로드)")
    if "search_results" not in st.session_state: st.session_state["search_results"] = None
    if "search_keyword" not in st.session_state: st.session_state["search_keyword"] = ""

    if st.button("🚀 400위까지 정밀 수색 시작"):
        if not keyword:
            st.warning("키워드를 입력해주세요.")
        else:
            with st.spinner("🛰️ 수색 중..."):
                found_items, price_top10, top100_items, err = collect_rank_data(
                    keyword, CLIENT_ID, CLIENT_SECRET)
            if err: st.error(err)
            if found_items:
                with st.spinner("📊 구글 시트 기록 중..."):
                    if save_to_sheet(keyword, found_items):
                        st.success("✅ 구글 시트 자동 저장 완료!")
            st.session_state["search_keyword"] = keyword
            st.session_state["search_results"] = {
                "found_items":found_items,"price_top10":price_top10,"top100_items":top100_items}

    if st.session_state["search_results"] is not None:
        sr = st.session_state["search_results"]
        saved_kw = st.session_state.get("search_keyword", "")
        found_items = sr.get("found_items", [])
        top100_items = sr.get("top100_items", [])
        price_top10 = sr.get("price_top10")
        if price_top10 is None:
            if top100_items:
                price_top10 = [it["가격"] for it in top100_items
                               if it.get("순위", 999) <= 10 and it.get("가격", 0) > 0]
            else:
                price_top10 = sr.get("price_list", [])[:10]
        avg_price = int(sum(price_top10)/len(price_top10)) if price_top10 else 0
        our_avg = 0
        if price_top10:
            our_prices = [i["가격"] for i in found_items if i["가격"]>0]
            our_avg = int(sum(our_prices)/len(our_prices)) if our_prices else 0
            diff_pct = int((our_avg-avg_price)/avg_price*100) if avg_price>0 else 0
            diff_label = f"TOP10 평균보다 {abs(diff_pct)}% {'💸 비쌈' if diff_pct>0 else '✅ 저렴'}"
            if found_items:
                best = min(found_items, key=lambda x:x["순위"])["순위"]
                st.info(f"**'{saved_kw}'** · 피싱템 **{len(found_items)}개** 노출 · "
                        f"최고 **{best}위** · {diff_label}")
            st.subheader("💰 키워드 시장 가격 분석 (TOP 10 기준)")
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("TOP10 최저가", f"{min(price_top10):,}원")
            c2.metric("TOP10 평균가", f"{avg_price:,}원")
            c3.metric("TOP10 최고가", f"{max(price_top10):,}원")
            c4.metric("피싱템 평균가", f"{our_avg:,}원" if our_avg else "-")
            st.divider()
        if not found_items:
            st.error(f"⚠️ 현재 '{TARGET_STORE}' 상품이 400위 내 비노출 중입니다.")
        else:
            st.success(f"✅ 총 {len(found_items)}개의 자사 상품 발견!")
            st.markdown("### 📌 선택 상품 모니터링 바로 등록")
            with st.form("add_monitor_form"):
                checked = {}
                CPR = 3
                for rs in range(0, len(found_items), CPR):
                    row = found_items[rs:rs+CPR]; cols = st.columns(CPR)
                    for col,item in zip(cols,row):
                        with col:
                            with st.container(border=True):
                                if item["썸네일"]: st.image(item["썸네일"], width=150)
                                st.markdown(f"### 🏆 {item['순위']}위")
                                if item.get("묶음여부"): st.warning("🔗 가격비교 묶음")
                                else: st.success("✅ 독립 노출")
                                st.markdown(f"**[{item['상품명']}]({item['링크']})**")
                                checked[item['상품명']] = st.checkbox(
                                    "모니터링 담기",
                                    key=f"chk_{item['순위']}_{item['상품명'][:10]}")
                                st.caption(f"🏪 {item['판매처']}")
                                if item["가격"]>0 and avg_price>0:
                                    d = int((item["가격"]-avg_price)/avg_price*100)
                                    ds = f"📈 TOP10보다 {abs(d)}% 비쌈" if d>0 else f"📉 TOP10보다 {abs(d)}% 저렴"
                                    st.caption(f"💴 {item['가격']:,}원"); st.caption(ds)
                submit = st.form_submit_button("🚀 선택 상품 모니터링 등록",
                                               type="primary", use_container_width=True)
                if submit:
                    sel = [n for n,c in checked.items() if c]
                    if not sel: st.warning("선택된 상품이 없습니다.")
                    else:
                        cnt = 0
                        for pn in sel:
                            ok,_ = add_monitor_keyword(saved_kw, memo=f"등록상품:{pn}")
                            if ok: cnt += 1
                        if cnt>0:
                            st.success(f"✅ {cnt}개 등록 완료!")
                            load_monitor_keywords.clear(); load_all_sheets_at_once.clear()
                            time.sleep(1); st.rerun()
                        else: st.warning("이미 등록되었거나 오류 발생.")
# =============================================
# [블록 4/4] Tab2 + Tab3 + Tab4(쇼핑광고 진단 A & 시즌 B)
# =============================================

# ---------- TAB 2 : 모니터링 관리 ----------
with tab2:
    st.subheader("📋 모니터링 키워드 관리")
    with st.spinner("목록 불러오는 중..."):
        sh = get_google_sheet()
        monitor_records = load_monitor_keywords(_sh=sh)
    if "detail_item" not in st.session_state: st.session_state["detail_item"] = None
    selected_for_deletion = []

    if not monitor_records:
        st.info("등록된 키워드가 없습니다. [순위 검색] 탭에서 등록해보세요!")
    else:
        st.caption(f"총 {len(monitor_records)}개 항목 모니터링 중")
        with st.spinner("📊 순위 데이터 불러오는 중..."):
            unique_kws = list(set(r["키워드"] for r in monitor_records))
            all_history = load_all_sheets_at_once(_sh=sh, keywords=unique_kws)
        CPR = 4
        for rs in range(0, len(monitor_records), CPR):
            row_recs = monitor_records[rs:rs+CPR]; cols = st.columns(CPR)
            for col,rec in zip(cols,row_recs):
                with col:
                    kw, memo = rec["키워드"], rec["메모"]
                    history = all_history.get(kw, [])
                    thumb=link=""; best_now=None; change_str="➖ 첫 수집"
                    status="⚪ 미노출"; latest_date="-"; pname="-"; latest_pt=None
                    if history:
                        try:
                            latest_date = max(set(r["날짜"] for r in history))
                            lat = [r for r in history if r["날짜"]==latest_date]
                            tgt = lat
                            if memo.startswith("등록상품:"):
                                tn = memo.replace("등록상품:","").strip()
                                f = [r for r in lat if tn in r["상품명"]]
                                tgt = f if f else []
                            if tgt:
                                br = min(tgt, key=lambda x:int(x["순위"]))
                                best_now = int(br["순위"]); pname = br.get("상품명","-")
                                thumb = br.get("썸네일",""); link = br.get("링크","")
                                ptr = br.get("productType","")
                                latest_pt = int(ptr) if str(ptr).strip().isdigit() else None
                                ad = sorted(set(r["날짜"] for r in history))
                                if len(ad)>=2:
                                    pv = [r for r in history if r["날짜"]==ad[-2]]
                                    pvt = pv
                                    if memo.startswith("등록상품:"):
                                        pf = [r for r in pv if tn in r["상품명"]]
                                        pvt = pf if pf else []
                                    if pvt:
                                        bp = min(int(r["순위"]) for r in pvt)
                                        ch = bp - best_now
                                        if ch>0: change_str=f"🔺 {ch}위 상승"
                                        elif ch<0: change_str=f"🔻 {abs(ch)}위 하락"
                                        else: change_str="➡️ 변동 없음"
                                if best_now<=10: status="🟢 TOP 10"
                                elif best_now<=50: status="🟢 TOP 50"
                                elif best_now<=100: status="🟡 TOP 100"
                                elif best_now<=200: status="🟠 TOP 200"
                                else: status="🔴 200위 밖"
                            else:
                                pname = memo.replace("등록상품:","").strip() if memo.startswith("등록상품:") else "-"
                        except Exception: pass
                    with st.container(border=True):
                        if thumb: st.image(thumb, width=100)
                        if link: st.markdown(f"**[🔑 {kw}]({link})**")
                        else: st.markdown(f"**🔑 {kw}**")
                        st.caption(f"📦 {pname[:20]}..." if len(pname)>20 else f"📦 {pname}")
                        if best_now:
                            st.markdown(f"🏆 **{best_now}위** · {status}")
                            if latest_pt==1: st.caption("🔗 가격비교 묶음")
                            elif latest_pt in [2,3]: st.caption("✅ 독립 노출")
                            else: st.caption("ℹ️ 노출형태 미확인")
                        else:
                            st.markdown("🏆 **순위 밖 (미수집)**")
                        st.caption(change_str); st.caption(f"🕐 {latest_date}")
                        if st.button("🔍 상세분석", key=f"detail_{kw}_{memo}", use_container_width=True):
                            cur = st.session_state.get("detail_item")
                            nd = f"{kw}|||{memo}"
                            st.session_state["detail_item"] = None if cur==nd else nd
                            st.rerun()
                        if st.checkbox("🗑️ 삭제 선택", key=f"del_{kw}_{memo}"):
                            selected_for_deletion.append(f"{kw}|||{memo}")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ 선택 항목 일괄 삭제", type="secondary"):
            if not selected_for_deletion: st.warning("삭제할 항목을 선택하세요.")
            else:
                with st.spinner("삭제 중..."):
                    if delete_multiple_monitor_keywords(selected_for_deletion):
                        st.success("✅ 삭제 완료!")
                        load_monitor_keywords.clear(); load_all_sheets_at_once.clear()
                        time.sleep(1); st.rerun()
        if st.session_state.get("detail_item"):
            dv = st.session_state["detail_item"]
            skw, smemo = dv.split("|||") if "|||" in dv else (dv, "")
            tpn = smemo.replace("등록상품:","").strip() if smemo.startswith("등록상품:") else None
            st.divider()
            with st.container(border=True):
                if st.button("✖ 닫기", key="close_detail"):
                    st.session_state["detail_item"] = None; st.rerun()
                render_detail_panel(skw, all_history.get(skw,[]), sh, tpn)
        st.divider()
        st.markdown("#### 🚀 등록 키워드 전체 일괄 수색")
        if st.button("🛰️ 전체 키워드 일괄 수색 시작", type="primary", use_container_width=True):
            total = len(unique_kws); prog = st.progress(0, text="준비 중...")
            summary = []
            for idx,kw in enumerate(unique_kws):
                prog.progress(idx/total, text=f"🔍 [{idx+1}/{total}] '{kw}'...")
                found, pt10, top100, err = collect_rank_data(kw, CLIENT_ID, CLIENT_SECRET)
                if err: summary.append({"키워드":kw,"결과":f"❌ {err}"}); continue
                if found:
                    save_to_sheet(kw, found)
                    best = min(found, key=lambda x:x["순위"])["순위"]
                    cc = sum(1 for i in found if i.get("묶음여부"))
                    note = f" (묶음 {cc}개)" if cc>0 else ""
                    summary.append({"키워드":kw,"결과":f"✅ {len(found)}개 (최고 {best}위){note}"})
                else:
                    summary.append({"키워드":kw,"결과":"⚠️ 400위 내 미노출"})
                time.sleep(0.3)
            prog.progress(1.0, text="✅ 완료!")
            st.success("🎉 일괄 수색 완료!")
            st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)
            load_all_sheets_at_once.clear(); time.sleep(1); st.rerun()

# ---------- TAB 3 : 키워드 분석 ----------
with tab3:
    st.subheader("📊 키워드 분석")
    col_kw, col_btn = st.columns([4,1])
    with col_kw:
        ak = st.text_input("분석할 키워드", placeholder="예: 타이라바 로드",
                           label_visibility="collapsed")
    with col_btn:
        abtn = st.button("🔍 분석 시작", type="primary", use_container_width=True)
    if abtn:
        if not ak: st.warning("키워드를 입력하세요.")
        else:
            with st.spinner("📡 데이터 불러오는 중..."):
                results = get_keyword_stats([ak])
            if not results:
                st.error(f"'{ak}' 데이터를 찾을 수 없습니다.")
            else:
                mr = next((r for r in results if r["키워드"]==ak), results[0])
                st.session_state["analysis_keyword"]=ak
                st.session_state["analysis_results"]=results
                st.session_state["main_result"]=mr
    if "main_result" in st.session_state:
        mr = st.session_state["main_result"]; results = st.session_state["analysis_results"]
        ak = st.session_state["analysis_keyword"]
        st.divider(); st.markdown(f"##### 📌 '{ak}' 분석 결과")
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("💻 PC 검색량", f"{mr['PC 검색량']:,}")
        c2.metric("📱 모바일 검색량", f"{mr['모바일 검색량']:,}")
        c3.metric("🔢 총 검색량", f"{mr['총 검색량']:,}")
        c4.metric("⚔️ 경쟁강도", mr["경쟁강도"])
        c5.metric("🖱️ PC 클릭수", f"{mr['PC 클릭률']:,}")
        st.divider(); st.markdown("#### 🔗 연관 키워드 분석")
        if results:
            dfr = pd.DataFrame(results).sort_values("총 검색량", ascending=False).reset_index(drop=True)
            dfr.index = dfr.index + 1
            disp = dfr[["키워드","PC 검색량","모바일 검색량","총 검색량","경쟁강도"]]
            st.dataframe(disp, use_container_width=True)
            csv = disp.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV 다운로드", csv,
                file_name=f"{ak}_키워드분석_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv", use_container_width=True)

# ---------- TAB 4 : 광고 진단(A) & 시즌(B) ----------
with tab4:
    st.subheader("📢 CPC 광고 진단 & 시즌 전략")
    sub_a, sub_b = st.tabs(["🩺 쇼핑광고 진단", "📅 시즌·추세 데이터"])

    # ===== A. 쇼핑광고 진단 (선택 / 전체) =====
    with sub_a:
        st.caption("쇼핑광고 소재 성과를 불러와 자동 진단합니다. 빠른 확인은 '선택 진단', "
                   "정기 점검은 '전체 진단'을 사용하세요.")
        diag_mode = st.radio("진단 방식", ["⚡ 선택 진단 (빠름)", "🩺 전체 진단 (전수·느림)"],
                             horizontal=True)
        diag_days = st.selectbox("진단 기간", [7, 14, 30], index=0,
                                 format_func=lambda x: f"최근 {x}일")
        with st.spinner("📡 캠페인 목록 불러오는 중..."):
            campaigns = ad_get_campaigns()
        # 쇼핑광고 캠페인만 필터
        shopping_camps = [c for c in campaigns
                          if "SHOPPING" in str(c.get("campaignTp",""))]

        if not shopping_camps:
            st.error("쇼핑광고 캠페인을 찾지 못했습니다. 광고 API 권한/키를 확인하세요.")
        else:
            # ----- 선택 진단 -----
            # ----- 선택 진단 (캠페인 다중 선택) -----
            if diag_mode.startswith("⚡"):
                camp_map = {c.get("name", c.get("nccCampaignId")): c.get("nccCampaignId")
                            for c in shopping_camps}
                sel_camp_names = st.multiselect(
                    "① 캠페인 선택 (여러 개 선택 가능)",
                    options=list(camp_map.keys()),
                    help="선택한 캠페인들의 모든 광고그룹을 진단합니다.")

                # 캠페인을 딱 1개만 골랐을 때는 그룹까지 세부 선택 허용
                target_groups = []
                sel_label = ""
                if len(sel_camp_names) == 1:
                    only_id = camp_map[sel_camp_names[0]]
                    adgroups = ad_get_adgroups(only_id)
                    if adgroups:
                        ag_map = {a.get("name", a.get("nccAdgroupId")): a.get("nccAdgroupId")
                                  for a in adgroups}
                        ag_options = ["📦 이 캠페인 전체 그룹"] + list(ag_map.keys())
                        sel_ag_name = st.selectbox("② 광고그룹 선택", ag_options)
                        if sel_ag_name.startswith("📦"):
                            target_groups = [(sel_camp_names[0], adgroups)]
                        else:
                            target_groups = [(sel_camp_names[0],
                                [a for a in adgroups
                                 if a.get("nccAdgroupId") == ag_map[sel_ag_name]])]
                    sel_label = sel_camp_names[0]
                elif len(sel_camp_names) >= 2:
                    st.info(f"{len(sel_camp_names)}개 캠페인의 전체 광고그룹을 진단합니다.")
                    for cn in sel_camp_names:
                        ags = ad_get_adgroups(camp_map[cn])
                        target_groups.append((cn, ags))
                    sel_label = f"{len(sel_camp_names)}개 캠페인"

                if st.button("⚡ 선택 진단 시작", type="primary"):
                    if not sel_camp_names:
                        st.warning("캠페인을 1개 이상 선택하세요.")
                    else:
                        rows = []
                        prog = st.progress(0, text="진단 준비 중...")
                        for ci, (cn, ags) in enumerate(target_groups):
                            prog.progress(ci/max(len(target_groups),1),
                                          text=f"🔍 [{ci+1}/{len(target_groups)}] {cn}")
                            rows += run_ad_diagnosis(ags, cn, diag_days)
                        prog.progress(1.0, text="✅ 진단 완료!")
                        st.session_state["ad_diag_rows"] = rows
            # ----- 전체 진단 -----
            else:
                skip_off = st.checkbox("꺼진(OFF) 캠페인 제외", value=True)
                st.info(f"쇼핑광고 캠페인 {len(shopping_camps)}개를 진단합니다. "
                        "데이터가 많으면 1~2분 소요될 수 있습니다.")
                if st.button("🩺 전체 진단 시작", type="primary"):
                    rows = []
                    target_camps = [c for c in shopping_camps
                                    if (not skip_off) or c.get("userLock") != True]
                    prog = st.progress(0, text="진단 준비 중...")
                    for ci, camp in enumerate(target_camps):
                        cid = camp.get("nccCampaignId"); cname = camp.get("name","")
                        prog.progress(ci/max(len(target_camps),1),
                                      text=f"🔍 [{ci+1}/{len(target_camps)}] {cname}")
                        adgroups = ad_get_adgroups(cid)
                        rows += run_ad_diagnosis(adgroups, cname, diag_days)
                    prog.progress(1.0, text="✅ 진단 완료!")
                    st.session_state["ad_diag_rows"] = rows

        # ----- 결과 표시 (공통) -----
        if st.session_state.get("ad_diag_rows"):
            rows = st.session_state["ad_diag_rows"]
            if not rows:
                st.warning("진단할 소재가 없습니다.")
            else:
                # 진단 결과를 시트에 저장 (어제 비교용) + 어제 기록 불러오기
                save_ad_diagnosis(rows)
                prev = load_yesterday_ad(rows)

                total_imp = sum(r["노출수"] for r in rows)
                total_cost = sum(r["광고비"] for r in rows)
                problem = [r for r in rows if r["상태"] in ["🔴","🟠"]]
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("진단 소재 수", f"{len(rows)}개")
                m2.metric("총 노출수", f"{total_imp:,}")
                m3.metric("총 광고비", f"{total_cost:,}원")
                m4.metric("⚠️ 점검 필요", f"{len(problem)}개")
                st.divider()

                # ===== 📌 오늘 할 일 TOP 5 =====
                st.markdown("### 📌 오늘 챙길 광고 TOP 5")
                # 우선순위 점수: 노출0(🔴)=3, 복합문제(🟠)=2, 단일문제(🟡)=1, 나머지 제외
                def _priority(r):
                    if r["상태"] == "🔴": return 3
                    if r["상태"] == "🟠": return 2
                    if r["상태"] == "🟡": return 1
                    return 0
                todo = [r for r in rows if _priority(r) > 0]
                todo.sort(key=lambda r: _priority(r), reverse=True)
                if not todo:
                    st.success("👍 오늘 급하게 손볼 광고가 없습니다. 모두 양호합니다!")
                else:
                    for i, r in enumerate(todo[:5], start=1):
                        # 핵심 조언 한 줄만 뽑기 (입찰가 추천 우선)
                        adv_parts = r["_advice"].split(" / ")
                        key_adv = next((a for a in adv_parts if a.startswith("💰")),
                                       adv_parts[0] if adv_parts else "")
                        st.markdown(f"**{i}. {r['상태']} {r['상품명']}** — {r['진단']}")
                        st.caption(f"　{key_adv}")
                st.divider()

                # ===== 📉 어제와 비교: 달라진 것만 =====
                st.markdown("### 📉 어제보다 나빠진 광고")
                if not prev:
                    st.info("비교할 어제 기록이 아직 없습니다. 내일 다시 진단하면 변화가 표시됩니다.")
                else:
                    changes = []
                    for r in rows:
                        p = prev.get(r["상품명"])
                        if not p:
                            continue
                        imp_now = r["노출수"]; imp_old = p["노출수"]
                        rnk_now = r["평균순위"]; rnk_old = p["평균순위"]
                        # 노출이 30% 이상 줄었거나, 순위가 3계단 이상 떨어진 경우
                        if imp_old > 0 and imp_now < imp_old * 0.7:
                            drop = int((1 - imp_now/imp_old) * 100)
                            changes.append(f"📉 **{r['상품명']}** · 노출 {drop}% 감소 "
                                           f"({imp_old:,} → {imp_now:,})")
                        elif rnk_old > 0 and rnk_now > 0 and rnk_now - rnk_old >= 3:
                            changes.append(f"📉 **{r['상품명']}** · 순위 하락 "
                                           f"({rnk_old:.1f}위 → {rnk_now:.1f}위)")
                    if not changes:
                        st.success("👍 어제보다 크게 나빠진 광고가 없습니다.")
                    else:
                        for c in changes:
                            st.warning(c)
                st.divider()

                # ===== 우선 점검 필요한 광고 (기존) =====
                if problem:
                    st.markdown("#### ⚠️ 우선 점검 필요한 광고")
                    for r in problem:
                        with st.container(border=True):
                            st.markdown(f"{r['상태']} **{r['상품명']}** · {r['진단']}")
                            st.caption(f"캠페인: {r['캠페인']} / 그룹: {r['광고그룹']} · "
                                       f"입찰가 {r['입찰가']:,}원 · 품질 {r['품질지수']}/10 · "
                                       f"노출 {r['노출수']:,} · 클릭 {r['클릭수']} · "
                                       f"CTR {r['CTR(%)']}% · 평균순위 {r['평균순위']}")
                            st.info(f"💡 {r['_advice']}")
                    st.divider()

                # ===== 전체 광고 성과 표 (기존) =====
                st.markdown("#### 📋 전체 광고 성과 표")
                df = pd.DataFrame(rows)[["상태","캠페인","광고그룹","상품명","ON/OFF",
                                         "입찰가","품질지수","노출수","클릭수","CTR(%)",
                                         "평균순위","광고비","진단"]]
                st.dataframe(df, use_container_width=True, hide_index=True)
                csv = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button("📥 진단 결과 CSV 다운로드", csv,
                    file_name=f"광고진단_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv")
                st.caption("※ 품질지수는 쇼핑광고 소재 기준(1~10)입니다.")

    # ===== B. 시즌·추세 데이터 =====
    with sub_b:
        st.caption("누적된 순위 기록으로 시즌 진입 시점과 추세를 파악합니다.")
        with st.spinner("📊 데이터 불러오는 중..."):
            sh_b = get_google_sheet()
            mon_b = load_monitor_keywords(_sh=sh_b)
            kws_b = list(set(r["키워드"] for r in mon_b)) if mon_b else []
            hist_b = load_all_sheets_at_once(_sh=sh_b, keywords=kws_b) if kws_b else {}

        if not kws_b:
            st.info("모니터링 키워드가 없습니다. 먼저 키워드를 등록하고 데이터를 쌓으세요.")
        else:
            # ---------- 공통: 키워드별 날짜별 최고순위 정리 ----------
            def _date_best_map(recs):
                dbest = {}
                for r in recs:
                    d = r["날짜"][:10]
                    try: rk = int(r["순위"])
                    except Exception: continue
                    if d not in dbest or rk < dbest[d]:
                        dbest[d] = rk
                return dbest

            # ===== 1. 이번 달 챙길 키워드 (시즌 캘린더) =====
            this_month = datetime.now().strftime("%m")      # 예: "06"
            last_year = str(datetime.now().year - 1)         # 작년 연도
            st.markdown(f"### 📅 이번 달({int(this_month)}월) 챙길 키워드")
            cal_rows = []
            for kw in kws_b:
                recs = hist_b.get(kw, [])
                dbest = _date_best_map(recs)
                # 작년 이번 달 데이터가 있는지 + 그달에 순위가 좋았는지
                ly_same_month = {d: v for d, v in dbest.items()
                                 if d[:4] == last_year and d[5:7] == this_month}
                if ly_same_month:
                    best_ly = min(ly_same_month.values())
                    cal_rows.append(f"🎣 **{kw}** — 작년 {int(this_month)}월 최고 {best_ly}위 "
                                    f"기록. 지금 광고·재고를 준비하세요!")
            if cal_rows:
                for c in cal_rows:
                    st.success(c)
            else:
                st.info("아직 '작년 이번 달' 데이터가 없습니다. 1년 이상 쌓이면 "
                        "이번 달에 미리 챙길 키워드를 자동으로 알려드립니다.")
            st.divider()

            # ===== 2. 키워드별 최근 추세 한 줄 요약 =====
            st.markdown("### 📊 키워드별 최근 추세 요약")
            for kw in kws_b:
                recs = hist_b.get(kw, [])
                dbest = _date_best_map(recs)
                if len(dbest) < 2:
                    st.caption(f"• {kw} — 데이터 부족 (수집 더 필요)")
                    continue
                sorted_d = sorted(dbest.keys())
                recent = sorted_d[-1]; before = sorted_d[max(0, len(sorted_d)-4)]  # 약 최근 구간
                gap = dbest[before] - dbest[recent]   # +면 상승(순위 숫자 감소)
                if gap >= 3:
                    st.markdown(f"📈 **{kw}** — 상승 중 ({dbest[before]}위 → {dbest[recent]}위)")
                elif gap <= -3:
                    st.markdown(f"📉 **{kw}** — 하락 중 ({dbest[before]}위 → {dbest[recent]}위)")
                else:
                    st.markdown(f"➡️ **{kw}** — 정체 (현재 {dbest[recent]}위)")
            st.divider()

            # ===== 3. 키워드 상세 추세 (기존 그래프 + 작년 비교) =====
            st.markdown("### 🔍 키워드별 상세 추세")
            sel_kw = st.selectbox("추세를 볼 키워드 선택", kws_b)
            recs = hist_b.get(sel_kw, [])
            if not recs:
                st.warning("아직 수집된 데이터가 없습니다. 며칠간 수색을 진행해 데이터를 쌓으세요.")
            else:
                dbest = _date_best_map(recs)
                if dbest:
                    df_trend = pd.DataFrame(
                        sorted([{"날짜":d,"최고순위":v} for d,v in dbest.items()],
                               key=lambda x:x["날짜"]))
                    st.markdown(f"#### 📈 '{sel_kw}' 순위 추세 (낮을수록 좋음)")
                    st.line_chart(df_trend.set_index("날짜")["최고순위"])
                    if len(df_trend) >= 2:
                        gap = df_trend.iloc[0]["최고순위"] - df_trend.iloc[-1]["최고순위"]
                        if gap > 0: st.success(f"📈 기록 시작 이후 순위가 {gap}위 상승했습니다.")
                        elif gap < 0: st.warning(f"📉 기록 시작 이후 순위가 {abs(gap)}위 하락했습니다.")
                        else: st.info("➡️ 순위 변동이 거의 없습니다.")

                    # --- 작년 이맘때 비교 ---
                    st.markdown("##### 🗓️ 작년 같은 달과 비교")
                    cur_m = datetime.now().strftime("%m")
                    ly = str(datetime.now().year - 1)
                    ly_data = {d: v for d, v in dbest.items()
                               if d[:4] == ly and d[5:7] == cur_m}
                    ty_data = {d: v for d, v in dbest.items()
                               if d[:4] == str(datetime.now().year) and d[5:7] == cur_m}
                    if ly_data and ty_data:
                        ly_best = min(ly_data.values()); ty_best = min(ty_data.values())
                        diff = ly_best - ty_best
                        if diff > 0:
                            st.success(f"작년 {int(cur_m)}월 최고 {ly_best}위 → 올해 {ty_best}위 "
                                       f"({diff}위 더 좋음 📈)")
                        elif diff < 0:
                            st.warning(f"작년 {int(cur_m)}월 최고 {ly_best}위 → 올해 {ty_best}위 "
                                       f"({abs(diff)}위 더 나쁨 📉). 광고 강화를 검토하세요.")
                        else:
                            st.info(f"작년과 올해 {int(cur_m)}월 순위가 비슷합니다 (최고 {ty_best}위).")
                    else:
                        st.info("작년 같은 달 데이터가 없어 비교할 수 없습니다. "
                                "데이터가 1년 이상 쌓이면 자동으로 비교됩니다.")

                    st.dataframe(df_trend, use_container_width=True, hide_index=True)
                st.divider()
                st.markdown("#### 📅 월별 수집 기록")
                month_count = {}
                for r in recs:
                    m = r["날짜"][:7]
                    month_count[m] = month_count.get(m, 0) + 1
                if month_count:
                    df_month = pd.DataFrame(
                        sorted([{"월":m,"수집건수":c} for m,c in month_count.items()],
                               key=lambda x:x["월"]))
                    st.bar_chart(df_month.set_index("월")["수집건수"])
# ---------- TAB 5 : 유입·상품 분석 (엑셀 업로드) ----------
with tab5:
    st.subheader("📂 유입·상품 분석")
    st.caption("스마트스토어에서 받은 엑셀(.xlsx)을 올리면 자동으로 분석합니다. "
               "두 파일은 따로 올려도 됩니다.")
    with st.expander("📥 각 파일은 어디서 받나요? (다운로드 경로)"):
        st.markdown("""
**1. 유입경로 파일 (전체채널)**
스마트스토어센터 → 데이터분석 → 마케팅분석(전체채널) → 조회기간 설정(월별) → 파일 다운로드

**2. 상품별 파일**
스마트스토어센터 → 데이터분석 → 쇼핑행동분석(상품별) → 조회기간 설정(월별) → 파일 다운로드

**3. 검색채널 파일 (키워드)**
스마트스토어센터 → 데이터분석 → 마케팅분석 → 검색채널 → 조회기간 설정(월별) → 파일 다운로드
        """)

    col_up1, col_up2, col_up3 = st.columns(3)
    with col_up1:
        st.markdown("##### 🚪 유입경로 파일")
        channel_file = st.file_uploader("전체채널 엑셀 올리기", type=["xlsx"],
                                        key="channel_uploader")
    with col_up2:
        st.markdown("##### 📦 상품별 파일")
        product_file = st.file_uploader("상품별 엑셀 올리기", type=["xlsx"],
                                        key="product_uploader")
    with col_up3:
        st.markdown("##### 🔎 검색채널 파일")
        search_file = st.file_uploader("검색채널 엑셀 올리기", type=["xlsx"],
                                       key="search_uploader")

    st.divider()

    # ===== 유입경로 분석 =====
    if channel_file is not None:
        st.markdown("## 🚪 유입경로 분석")
        try:
            ch = analyze_channel_file(channel_file)
            total_visit = int(ch["유입수"].sum())
            total_pay = int(ch["결제금액"].sum())
            c1, c2 = st.columns(2)
            c1.metric("총 유입수", f"{total_visit:,}")
            c2.metric("총 결제금액", f"{total_pay:,}원")

            st.markdown("#### 🔝 유입 많은 경로 TOP 10")
            top_visit = ch.sort_values("유입수", ascending=False).head(10)
            st.dataframe(top_visit[["채널명","채널속성","유입수","결제수","결제율(%)"]],
                         use_container_width=True, hide_index=True)

            st.markdown("#### 💰 결제금액 많은 경로 TOP 10")
            top_pay = ch.sort_values("결제금액", ascending=False).head(10)
            st.dataframe(top_pay[["채널명","채널속성","결제금액","결제수","결제율(%)"]],
                         use_container_width=True, hide_index=True)

            st.markdown("#### 💎 숨은 보석 / ⚠️ 점검 경로")
            # 유입 100 이상인 경로만 대상으로 결제율 판단
            meaningful = ch[ch["유입수"] >= 100]
            gems = meaningful.sort_values("결제율(%)", ascending=False).head(5)
            traps = meaningful[meaningful["유입수"] >= 500].sort_values("결제율(%)").head(5)
            cg, ct = st.columns(2)
            with cg:
                st.markdown("**💎 결제율 높은 경로 (키울 만함)**")
                for _, r in gems.iterrows():
                    st.success(f"{r['채널명']} · 결제율 {r['결제율(%)']}% "
                               f"(유입 {int(r['유입수']):,})")
            with ct:
                st.markdown("**⚠️ 유입 많은데 결제율 낮은 경로 (점검)**")
                for _, r in traps.iterrows():
                    st.warning(f"{r['채널명']} · 결제율 {r['결제율(%)']}% "
                               f"(유입 {int(r['유입수']):,})")
        except Exception as e:
            st.error(f"유입경로 파일을 읽는 중 오류: {e}")
        st.divider()

    # ===== 상품별 분석 =====
    if product_file is not None:
        st.markdown("## 📦 상품별 분석")
        try:
            pr = analyze_product_file(product_file)
            c1, c2, c3 = st.columns(3)
            c1.metric("분석 상품 수", f"{len(pr)}개")
            c2.metric("총 결제금액", f"{int(pr['결제금액'].sum()):,}원")
            c3.metric("총 조회수", f"{int(pr['조회수'].sum()):,}")

            # 분류별 개수
            st.markdown("#### 🗂️ 상품 4분류")
            cnt = pr["분류"].value_counts()
            cc1, cc2, cc3, cc4 = st.columns(4)
            cc1.metric("🟢 효자상품", f"{cnt.get('🟢 효자상품',0)}개")
            cc2.metric("🔴 개선필요", f"{cnt.get('🔴 개선필요',0)}개")
            cc3.metric("🟡 숨은보석", f"{cnt.get('🟡 숨은보석',0)}개")
            cc4.metric("⚪ 정리검토", f"{cnt.get('⚪ 정리검토',0)}개")

            # 상세페이지 고칠 TOP 10 = 개선필요 중 조회수 높은 순
            st.markdown("#### ⚠️ 이번 달 상세페이지 고칠 TOP 10")
            st.caption("많이 보는데 잘 안 사는 상품입니다. 상세페이지·가격·후기를 점검하세요.")
            fix = pr[pr["분류"] == "🔴 개선필요"].sort_values("조회수", ascending=False).head(10)
            if fix.empty:
                st.info("개선필요로 분류된 상품이 없습니다.")
            else:
                st.dataframe(fix[["상품명","조회수","결제수량","결제금액","결제율"]],
                             use_container_width=True, hide_index=True)

            # 효자상품 TOP 10
            st.markdown("#### 🟢 효자상품 TOP 10 (조회·판매 모두 좋음)")
            best = pr[pr["분류"] == "🟢 효자상품"].sort_values("결제금액", ascending=False).head(10)
            st.dataframe(best[["상품명","조회수","결제수량","결제금액","결제율"]],
                         use_container_width=True, hide_index=True)

            # 피싱템 상품만 보기
            st.markdown("#### 🎯 우리 브랜드(피싱템) 상품만 보기")
            ours = pr[pr["상품명"].astype(str).str.contains(TARGET_STORE, na=False)]
            if ours.empty:
                st.info("상품명에 '피싱템'이 포함된 상품이 없습니다.")
            else:
                st.dataframe(
                    ours[["상품명","분류","조회수","결제수량","결제금액","결제율"]]
                        .sort_values("조회수", ascending=False),
                    use_container_width=True, hide_index=True)

            # 전체 표 + CSV
            st.markdown("#### 📋 전체 상품 분석 표")
            st.dataframe(pr.sort_values("조회수", ascending=False),
                         use_container_width=True, hide_index=True)
            csv = pr.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 상품분석 결과 CSV 다운로드", csv,
                file_name=f"상품분석_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv")
        except Exception as e:
            st.error(f"상품별 파일을 읽는 중 오류: {e}")
    # ===== 검색채널(키워드) 분석 =====
    if search_file is not None:
        st.markdown("## 🔎 검색채널(키워드) 분석")
        try:
            sr, raw_cols = analyze_search_file(search_file)
            if sr.empty:
                st.warning("검색어 데이터를 찾지 못했습니다. "
                           f"이 파일의 열 이름: {raw_cols}")
            else:
                tv = int(sr["유입수"].sum()); tp = int(sr["결제금액"].sum())
                c1, c2 = st.columns(2)
                c1.metric("총 유입수", f"{tv:,}")
                c2.metric("총 결제금액", f"{tp:,}원")

                st.markdown("#### 🔝 유입 많은 키워드 TOP 15")
                top_v = sr.sort_values("유입수", ascending=False).head(15)
                st.dataframe(top_v[["검색어","유입수","결제수","결제금액","결제율(%)"]],
                             use_container_width=True, hide_index=True)

                st.markdown("#### 💰 매출 많은 키워드 TOP 15")
                top_p = sr.sort_values("결제금액", ascending=False).head(15)
                st.dataframe(top_p[["검색어","유입수","결제수","결제금액","결제율(%)"]],
                             use_container_width=True, hide_index=True)

                st.markdown("#### 💎 결제율 높은 알짜 키워드 (유입 30 이상)")
                st.caption("유입은 많지 않아도 들어오면 잘 사는 키워드입니다. 광고·SEO에 활용하세요.")
                gems = sr[sr["유입수"] >= 30].sort_values("결제율(%)", ascending=False).head(10)
                st.dataframe(gems[["검색어","유입수","결제수","결제율(%)"]],
                             use_container_width=True, hide_index=True)

                st.markdown("#### 🎯 우리 브랜드(피싱템) 검색 키워드")
                ours_kw = sr[sr["검색어"].str.contains(TARGET_STORE, na=False)]
                if ours_kw.empty:
                    st.info("'피싱템'이 포함된 검색어가 없습니다.")
                else:
                    st.dataframe(
                        ours_kw[["검색어","유입수","결제수","결제금액","결제율(%)"]]
                            .sort_values("유입수", ascending=False),
                        use_container_width=True, hide_index=True)

                csv = sr.to_csv(index=False).encode("utf-8-sig")
                st.download_button("📥 검색키워드 분석 CSV 다운로드", csv,
                    file_name=f"검색키워드분석_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv")
        except Exception as e:
            st.error(f"검색채널 파일을 읽는 중 오류: {e}")
        st.divider()

       if channel_file is None and product_file is None and search_file is None:
        st.info("위에서 엑셀 파일을 올리면 분석이 시작됩니다.")
