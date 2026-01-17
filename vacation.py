import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta

# 1. 페이지 기본 설정 및 보안 (암호: 7573)
st.set_page_config(page_title="2026 동경한의원 세종 휴가 대시보드", layout="wide")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 동경한의원 세종점 시스템")
        pwd = st.text_input("접속 암호를 입력하세요", type="password")
        if st.button("로그인"):
            if pwd == "7573":
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("암호가 틀렸습니다.")
        return False
    return True

if not check_password():
    st.stop()

# 2. 데이터 초기화 (코드 내 관리)
if 'leave_data' not in st.session_state:
    # 초기 기재된 휴가 내역
    st.session_state.leave_data = [
        {"날짜": date(2026, 1, 10), "이름": "정도희", "유형": "월차", "사유": "개인휴가", "일수": 1.0},
        {"날짜": date(2026, 3, 14), "이름": "정도희", "유형": "월차", "사유": "개인휴가(예정)", "일수": 1.0},
    ]

# 3. 사이드바 - 휴가 신청 폼
st.sidebar.header("📅 휴가 신청하기")
with st.sidebar.form("request_form"):
    input_name = st.selectbox("신청자", ["정도희", "전미진"])
    input_date = st.date_input("휴가 날짜", min_value=date(2026, 1, 1), max_value=date(2026, 12, 31))
    
    options = ["월차", "연차", "0.5연차"]
    if input_name == "전미진":
        options.append("오전반차(전용)")
    
    input_type = st.selectbox("휴가 유형", options)
    input_reason = st.text_input("사유")
    submit = st.form_submit_button("신청 완료")

    if submit:
        # 규칙 체크: 0.5연차는 7일 전 신청 필수
        today = date.today()
        days_diff = (input_date - today).days
        
        if input_type == "0.5연차" and days_diff < 7:
            st.error("⚠️ 0.5연차는 최소 일주일 전에 신청해야 합니다!")
        else:
            days_val = 0.5 if "0.5" in input_type or "반차" in input_type else 1.0
            st.session_state.leave_data.append({
                "날짜": input_date, "이름": input_name, "유형": input_type, "사유": input_reason, "일수": days_val
            })
            st.success(f"{input_name}님 신청 완료!")
            st.rerun()

# 4. 메인 대시보드 상단 - 잔여 현황 계산
st.title("🌿 2026 동경한의원 세종 휴가 관리 시스템")
df = pd.DataFrame(st.session_state.leave_data)

# 각 직원별 계산 로직
# 정도희: 월차 12개 (사용 내역 차감)
dohee_used = df[df['이름'] == '정도희']['일수'].sum()
dohee_remain = 12 - dohee_used

# 전미진: 연차 16개 + 오전반차 월 1개(총 12개)
mijin_df = df[df['이름'] == '전미진']
mijin_annual_used = mijin_df[mijin_df['유형'].str.contains("연차")]['일수'].sum()
mijin_half_used = mijin_df[mijin_df['유형'] == "오전반차(전용)"]['일수'].sum()

mijin_annual_remain = 16 - mijin_annual_used
mijin_half_remain = 12 - mijin_half_used # 월 1개 발생 기준 총량

col1, col2 = st.columns(2)

with col1:
    st.subheader("👤 정도희님 현황")
    st.metric(label="남은 월차", value=f"{dohee_remain} 개", delta=f"사용 {dohee_used}")
    st.caption("※ 연간 총 12개 월차 적립 기준")

with col2:
    st.subheader("👤 전미진님 현황")
    c1, c2 = st.columns(2)
    c1.metric(label="남은 연차", value=f"{mijin_annual_remain} 개", delta=f"사용 {mijin_annual_used}")
    c2.metric(label="남은 오전반차", value=f"{mijin_half_remain} 개", delta=f"사용 {mijin_half_used}")
    st.caption("※ 연차 16개 + 전용 오전반차 월 1개 기준")

st.divider()

# 5. 하단 - 전체 기록 테이블
st.subheader("🗒️ 전체 휴가 기록 (2026)")
if not df.empty:
    df_display = df.sort_values(by="날짜", ascending=True)
    st.dataframe(df_display, use_container_width=True)
else:
    st.write("기록된 데이터가 없습니다.")

# 6. 관리자용 안내
with st.expander("📌 관리 지침 (임원장님 확인용)"):
    st.write("- **0.5연차:** 일주일 전 사전 신청 필수 (시스템 자동 체크)")
    st.write("- **전미진쌤 오전반차:** 월 1회 소진 원칙 (25일 이전 사용 권장)")
    st.write("- **토요일:** 가급적 연속 사용 금지 (기록 리스트에서 날짜 확인)")