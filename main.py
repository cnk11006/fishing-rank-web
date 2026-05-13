import streamlit as st
import requests
import time

# --- [1. 보안 및 상호명 설정] ---
TARGET_STORE = "피싱템"

try:
    CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]
    MASTER_PASSWORD = st.secrets["APP_PASSWORD"]
except:
    st.error("보안 설정(Secrets)이 완료되지 않았습니다.")
    st.stop()

# --- [2. 로그인 로직] ---
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

# --- [3. 메인 화면] ---
st.set_page_config(page_title="피싱템 순위 추적기", layout="wide")
st.title("🎣 피싱템 순위 레이더 (400위 확장판)")

keyword = st.text_input("수색할 키워드를 입력하세요 (예: 타이라바 로드)")

if st.button("🚀 400위까지 정밀 수색 시작"):
    if not keyword:
        st.warning("키워드를 입력해주세요.")
    else:
        found_items = []
        progress_text = st.empty()

        for page in range(4):
            start_num = (page * 100) + 1
            progress_text.info(f"🛰️ {start_num}위 ~ {start_num + 99}위 구간 수색 중...")

            url = f"https://openapi.naver.com/v1/search/shop.json?query={keyword}&display=100&start={start_num}"
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
                    if TARGET_STORE in mall_name or TARGET_STORE in item['title']:
                        clean_title = item['title'].replace('<b>', '').replace('</b>', '')
                        found_items.append({
                            "순위": start_num + index,
                            "상품명": clean_title,
                            "판매처": mall_name,
                            "링크": item.get('link', ''),
                            "썸네일": item.get('image', '')  # ✅ 썸네일 URL
                        })

                time.sleep(0.1)
            else:
                st.error(f"API 호출 오류 (구간: {start_num}위)")
                break

        progress_text.empty()

        # --- [4. 결과 출력 - 카드형 레이아웃] ---
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
                            st.image(item["썸네일"], use_container_width=True)
                        else:
                            st.markdown(
                                "<div style='height:150px; background:#f0f0f0;"
                                "display:flex; align-items:center; justify-content:center;"
                                "border-radius:8px; color:#999;'>이미지 없음</div>",
                                unsafe_allow_html=True
                            )
                        st.markdown(f"### 🏆 {item['순위']}위")
                        st.markdown(f"**[{item['상품명']}]({item['링크']})**")
                        st.caption(f"🏪 판매처: {item['판매처']}")
                        st.markdown("---")
