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

# 3. 데이터 로드 및 대시보드
st.title("🌿 2026 동경한의원 세종 휴가 대시보드")
status_data = status_sheet.get_all_records()
status_df = pd.DataFrame(status_data)
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
    is_emergency = st.checkbox("❗ 갑자기 아파서 신청하시나요? (당일/전일 병가)")
    
    options = ["연차", "월차", "0.5연차"]
    if name == "전미진": options.append("오전반차")
    
    l_type = st.selectbox("유형", options)
    reason = st.text_input("사유")
    submit = st.form_submit_button("신청하기")

if submit:
    today = date.today()
    diff = (t_date - today).days
    is_sat = t_date.weekday() == 5 

    # [로직 체크]
    if is_emergency and l_type in ["월차", "0.5연차", "오전반차"]:
        st.error("❌ 갑자기 아픈 경우 '연차'만 사용 가능합니다.")
    elif not is_emergency and l_type in ["월차", "0.5연차"] and diff < 7:
        st.error("❌ 월차와 0.5연차는 최소 7일 전 신청이 원칙입니다.")
    else:
        # 1. 차감할 일수 계산
        deduct_val = 0.5 if l_type == "0.5연차" else 1.0
        
        # 2. 직원현황 시트에서 해당 직원 및 열 찾기
        # 직원현황 시트의 이름 열(A열)에서 신청자 위치 찾기
        name_list = status_sheet.col_values(1)
        row_idx = name_list.index(name) + 1 # gspread는 1부터 시작
        
        # 차감할 항목 결정 (연차 계열인지 월차 계열인지)
        target_col_name = "남은 월차" if l_type in ["월차", "오전반차"] else "남은 연차"
        col_idx = status_df.columns.get_loc(target_col_name) + 1
        
        # 현재 값 가져와서 차감 후 업데이트
        current_val = float(status_sheet.cell(row_idx, col_idx).value)
        new_val = current_val - deduct_val
        status_sheet.update_cell(row_idx, col_idx, new_val)

        # 3. 휴가기록 시트에 로그 추가
        emergency_tag = " (당일아픔)" if is_emergency else ""
        new_row = [str(t_date), name, l_type + emergency_tag, reason, deduct_val]
        record_sheet.append_row(new_row)
        
        # 4. 토요일 연속 체크 (알림용)
        user_records = records_df[records_df['이름'] == name].copy()
        user_records['날짜'] = pd.to_datetime(user_records['날짜']).dt.date
        last_sat = user_records[pd.to_datetime(user_records['날짜']).dt.weekday == 5]['날짜'].max()
        sat_warning = "\n⚠️ 주의: 토요일 연속 사용 감지!" if is_sat and last_sat and (t_date - last_sat).days <= 14 else ""

        # 5. 라인 알림
        msg = f"🔔 [휴가신청]{emergency_tag}\n{name}님이 {t_date}({l_type}) 신청. 잔여: {new_val}개{sat_warning}\n사유: {reason}"
        send_line(msg)
        
        st.success(f"✅ 신청 완료 및 {target_col_name} 차감 완료!")
        st.rerun()

# 5. 안내 및 기록 테이블
st.info("💡 신청 시 '직원현황'의 잔여 일수가 실시간으로 차감됩니다.")
st.subheader("📋 전체 휴가 기록 (로그)")
st.dataframe(records_df.sort_values("날짜", ascending=False), use_container_width=True)