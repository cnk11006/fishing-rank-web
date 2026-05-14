"""
auto_collect.py
GitHub Actions에서 매일 자동 실행되는 순위 수집 스크립트
"""

import os
import json
import requests
import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# =============================================
# 설정값 (환경변수에서 로드)
# =============================================
TARGET_STORE = "피싱템"
CLIENT_ID = os.environ["NAVER_CLIENT_ID"]
CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]
SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
GCP_JSON = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])
MONITOR_SHEET_NAME = "📋 모니터링 목록"


def get_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(GCP_JSON, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)


def get_or_create_worksheet(sh, title, rows=1000, cols=10):
    try:
        return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=rows, cols=cols)


def load_monitor_keywords(sh):
    try:
        ws = sh.worksheet(MONITOR_SHEET_NAME)
        records = ws.get_all_records()
        return [r["키워드"] for r in records if r.get("키워드")]
    except Exception as e:
        print(f"키워드 목록 불러오기 실패: {e}")
        return []


def save_to_sheet(sh, keyword, found_items):
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws = get_or_create_worksheet(sh, keyword)
    existing = ws.get_all_values()
    if not existing:
        ws.append_row(["날짜", "순위", "상품명", "판매처", "가격", "링크"])
    for item in found_items:
        ws.append_row([
            today,
            item["순위"],
            item["상품명"],
            item["판매처"],
            item["가격"],
            item["링크"]
        ])


def collect(keyword):
    found_items = []
    for page in range(4):
        start_num = (page * 100) + 1
        url = (
            f"https://openapi.naver.com/v1/search/shop.json"
            f"?query={keyword}&display=100&start={start_num}"
        )
        headers = {
            "X-Naver-Client-Id": CLIENT_ID,
            "X-Naver-Client-Secret": CLIENT_SECRET
        }
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            print(f"  ❌ API 오류: {start_num}위 구간")
            break
        items = res.json().get("items", [])
        if not items:
            break
        for idx, item in enumerate(items):
            mall_name = item.get("mallName", "")
            clean_title = item["title"].replace("<b>", "").replace("</b>", "")
            if TARGET_STORE in mall_name or TARGET_STORE in item["title"]:
                found_items.append({
                    "순위": start_num + idx,
                    "상품명": clean_title,
                    "판매처": mall_name,
                    "가격": int(item.get("lprice", 0)),
                    "링크": item.get("link", "")
                })
        time.sleep(0.2)
    return found_items


# =============================================
# 메인 실행
# =============================================
if __name__ == "__main__":
    print(f"🚀 자동 수집 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    sh = get_sheet()
    keywords = load_monitor_keywords(sh)

    if not keywords:
        print("⚠️ 등록된 모니터링 키워드가 없습니다.")
    else:
        print(f"📋 총 {len(keywords)}개 키워드 수집 시작")
        for kw in keywords:
            print(f"\n🔍 수색 중: {kw}")
            found = collect(kw)
            if found:
                save_to_sheet(sh, kw, found)
                best = min(found, key=lambda x: x["순위"])["순위"]
                print(f"  ✅ {len(found)}개 발견 (최고 {best}위) → 시트 저장 완료")
            else:
                print(f"  ⚠️ 400위 내 미노출")
            time.sleep(0.5)

    print(f"\n✅ 전체 수집 완료: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
