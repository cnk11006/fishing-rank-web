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
        price_list = []       # 1~100위 가격 수집용
        top100_items = []     # 1~100위 전체 상품 수집용
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
                    clean_title = item['title'].replace('<b>', '').replace('</b>', '')

                    # ✅ 1~100위 가격 및 상품 데이터 수집
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
                        except:
                            pass

                    # ✅ 자사 상품 순위 수집
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

        # --- [4. 핵심 요약 배너] ---
        if price_list and found_items:
            min_price = min(price_list)
            max_price = max(price_list)
            avg_price = int(sum(price_list) / len(price_list))

            our_prices = [i["가격"] for i in found_items if i["가격"] > 0]
            our_avg = int(sum(our_prices) / len(our_prices)) if our_prices else 0
            diff_pct = int((our_avg - avg_price) / avg_price * 100) if avg_price > 0 else 0
            diff_label = f"시장 평균보다 {abs(diff_pct)}% {'💸 비쌈' if diff_pct > 0 else '✅ 저렴'}"
            best_rank = min(found_items, key=lambda x: x["순위"])["순위"]

            st.info(
                f"**'{keyword}'** 키워드 · 피싱템 **{len(found_items)}개** 노출 중 · "
                f"최고 순위 **{best_rank}위** · {diff_label}"
            )

        # --- [5. 가격 분석 섹션] ---
        if price_list:
            min_price = min(price_list)
            max_price = max(price_list)
            avg_price = int(sum(price_list) / len(price_list))
            our_prices = [i["가격"] for i in found_items if i["가격"] > 0]
            our_avg = int(sum(our_prices) / len(our_prices)) if our_prices else 0

            st.subheader("💰 키워드 시장 가격 분석 (1위 ~ 100위 기준)")

            # 가격 지표 카드
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

            # 가격대별 분포
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

            # 최저가 TOP 5
            st.subheader("🏅 최저가 TOP 5 (1위 ~ 100위 기준)")
            top5 = sorted(top100_items, key=lambda x: x["가격"])[:5]
            t_cols = st.columns(5)
            for i, (col, item) in enumerate(zip(t_cols, top5)):
                with col:
                    if item["썸네일"]:
                        st.image(item["썸네일"], width=120)
                    medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i]
                    st.markdown(f"**{medal} {item['가격']:,}원**")
                    st.markdown(f"[{item['상품명'][:20]}...]({item['링크']})" if len(item['상품명']) > 20 else f"[{item['상품명']}]({item['링크']})")
                    st.caption(f"검색 {item['순위']}위 · {item['판매처']}")

            st.divider()

        # --- [6. 자사 상품 순위 결과 출력] ---
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
                                "display:flex; align-items:center; justify-content:center;"
                                "border-radius:8px; color:#999;'>이미지 없음</div>",
                                unsafe_allow_html=True
                            )
                        st.markdown(f"### 🏆 {item['순위']}위")
                        st.markdown(f"**[{item['상품명']}]({item['링크']})**")
                        st.caption(f"🏪 판매처: {item['판매처']}")
                        if item["가격"] > 0:
                            diff = int((item["가격"] - avg_price) / avg_price * 100) if price_list else 0
                            diff_str = f"{'📈 시장 평균보다 ' + str(abs(diff)) + '% 비쌈' if diff > 0 else '📉 시장 평균보다 ' + str(abs(diff)) + '% 저렴'}"
                            st.caption(f"💴 판매가: {item['가격']:,}원")
                            st.caption(diff_str)
                        st.markdown("---")
