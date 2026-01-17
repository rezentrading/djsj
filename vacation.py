import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, date, timedelta
import requests

# 1. 보안 및 접속 설정
st.set_page_config(page_title="2026 동경한의원 세종 휴가 시스템", layout="wide")

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔒 시스템 접속")
    pwd = st.text_input("접속 암호를 입력하세요", type="password")
    if st.button("로그인"):
        if pwd == "7573":
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("암호가 틀렸습니다.")
    st.stop()

# 2. 구글 시트 및 라인 연결
@st.cache_resource
def init_conn():
    creds = st.secrets["gcp_service_account"]
    gc = gspread.service_account_from_dict(creds)
    return gc.open("세종점 동경한의원 연차월차관리 시트")

sh = init_conn()
status_sheet = sh.worksheet("직원현황")
record_sheet = sh.worksheet("휴가기록")

def send_line(msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {st.secrets['line']['access_token']}", "Content-Type": "application/json"}
    payload = {"to": st.secrets['line']['group_id'], "messages": [{"type": "text", "text": msg}]}
    requests.post(url, headers=headers, json=payload)

# 3. 대시보드
st.title("🌿 2026 동경한의원 세종 휴가 대시보드")
status_df = pd.DataFrame(status_sheet.get_all_records())
records_df = pd.DataFrame(record_sheet.get_all_records())

c1, c2 = st.columns(2)
with c1:
    d = status_df[status_df['이름'] == '정도희'].iloc[0]
    st.metric("정도희님 잔여 월차", f"{d['남은 월차']}개")
with c2:
    m = status_df[status_df['이름'] == '전미진'].iloc[0]
    st.metric("전미진님 잔여 연차", f"{m['남은 연차']}개")

st.divider()

# 4. 신청 사이드바
st.sidebar.header("📅 휴가 신청")
with st.sidebar.form("leave_form"):
    name = st.selectbox("신청자", ["정도희", "전미진"])
    t_date = st.date_input("날짜", min_value=date(2026, 1, 1))
    
    # [추가] 갑자기 아픈 경우 체크
    is_emergency = st.checkbox("❗ 갑자기 아파서 신청하시나요? (당일/전일)")
    
    options = ["연차", "월차", "0.5연차"]
    if name == "전미진": options.append("오전반차")
    
    l_type = st.selectbox("유형", options)
    reason = st.text_input("사유")
    submit = st.form_submit_button("신청하기")

if submit:
    today = date.today()
    diff = (t_date - today).days
    is_sat = t_date.weekday() == 5 # 토요일 체크

    # 로직 1: 갑자기 아픈 경우 (연차만 가능)
    if is_emergency and l_type in ["월차", "0.5연차", "오전반차"]:
        st.error("❌ 갑자기 아픈 경우 '연차'만 사용 가능합니다. 월차나 0.5연차는 미리 신청해 주세요.")
    
    # 로직 2: 일반 신청 시 7일 전 체크
    elif not is_emergency and l_type in ["월차", "0.5연차"] and diff < 7:
        st.error("❌ 월차와 0.5연차는 최소 일주일(7일) 전에 신청해야 합니다.")
    
    else:
        # 로직 3: 토요일 연속 사용 체크
        user_records = records_df[records_df['이름'] == name].copy()
        user_records['날짜'] = pd.to_datetime(user_records['날짜']).dt.date
        last_sat = user_records[pd.to_datetime(user_records['날짜']).dt.weekday == 5]['날짜'].max()
        
        sat_warning = ""
        if is_sat and last_sat and (t_date - last_sat).days <= 14:
            sat_warning = "\n⚠️ 주의: 토요일 연속 사용이 감지되었습니다."

        # 기록 및 알림
        emergency_str = " (당일아픔)" if is_emergency else ""
        new_row = [str(t_date), name, l_type + emergency_str, reason]
        record_sheet.append_row(new_row)
        
        msg = f"🔔 [휴가신청]{emergency_str}\n{name}님이 {t_date}({l_type}) 신청했습니다.{sat_warning}\n사유: {reason}"
        send_line(msg)
        
        st.success(f"신청 완료! {sat_warning}")
        st.rerun()

# 5. 하단 룰 설명
st.info("""
**📌 연차/월차 사용 원칙**
1. **갑자기 아픈 경우:** '연차'만 즉시 사용 가능합니다. (0.5연차, 월차는 불가)
2. **사전 예약:** 0.5연차와 월차는 최소 7일 전 신청이 원칙입니다.
3. **토요일:** 가급적 연속 사용을 지양하며, 시스템이 이전 기록을 체크합니다.
""")

st.subheader("📋 전체 기록")
st.dataframe(records_df.sort_values("날짜", ascending=False), use_container_width=True)