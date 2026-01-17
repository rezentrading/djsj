import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, date, timedelta
import requests

# 1. 페이지 설정 및 보안
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
    headers = {
        "Authorization": f"Bearer {st.secrets['line']['access_token']}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": st.secrets['line']['group_id'],
        "messages": [{"type": "text", "text": msg}]
    }
    requests.post(url, headers=headers, json=payload)

# 3. 데이터 로드
status_df = pd.DataFrame(status_sheet.get_all_records())
records_df = pd.DataFrame(record_sheet.get_all_records())

st.title("🌿 2026 동경한의원 세종 휴가 대시보드 (v2.2)")

# 현황 요약 표시
c1, c2 = st.columns(2)
with c1:
    d_row = status_df[status_df['이름'] == '정도희']
    if not d_row.empty:
        st.metric("정도희님 잔여 월차", f"{d_row.iloc[0]['남은 월차']}개")
with c2:
    m_row = status_df[status_df['이름'] == '전미진']
    if not m_row.empty:
        st.metric("전미진님 잔여 연차", f"{m_row.iloc[0]['남은 연차']}개")

st.divider()

# 4. 신청 사이드바
st.sidebar.header("📅 휴가 신청")
with st.sidebar.form("leave_form"):
    name = st.selectbox("신청자", ["정도희", "전미진"])
    t_date = st.date_input("날짜", min_value=date(2026, 1, 1))
    
    is_emergency = st.checkbox("❗ 갑자기 아파서 신청하시나요?")
    
    # [변경 사항] 직원별 선택 가능 유형 제한
    if name == "정도희":
        options = ["월차"]
    else: # 전미진
        options = ["연차", "0.5연차", "오전반차"]
    
    l_type = st.selectbox("유형", options)
    reason = st.text_input("사유")
    submit = st.form_submit_button("신청하기")

if submit:
    today = date.today()
    diff = (t_date - today).days
    is_sat = t_date.weekday() == 5 

    # [오전반차 특수 로직]
    if l_type == "오전반차":
        # 1. 25일 규정 체크
        if t_date.day >= 25:
            st.error("❌ 오전반차는 매달 25일 이전에만 사용 가능합니다. (25일부터 소멸)")
            st.stop()
        
        # 2. 이번 달 중복 사용 체크
        # records_df에서 같은 이름, 같은 달의 오전반차 기록이 있는지 확인
        records_df['날짜_dt'] = pd.to_datetime(records_df['날짜'])
        used_this_month = records_df[
            (records_df['이름'] == "전미진") & 
            (records_df['유형'].str.contains("오전반차")) & 
            (records_df['날짜_dt'].dt.month == t_date.month) &
            (records_df['날짜_dt'].dt.year == t_date.year)
        ]
        if not used_this_month.empty:
            st.error(f"❌ 전미진님은 이번 달({t_date.month}월) 오전반차를 이미 사용하셨습니다.")
            st.stop()

    # [일반 규칙 검증]
    if is_emergency and l_type in ["월차", "0.5연차", "오전반차"]:
        st.error("❌ 갑자기 아픈 경우 '연차'만 사용 가능합니다.")
    elif not is_emergency and l_type in ["월차", "0.5연차"] and diff < 7:
        st.error("❌ 월차/0.5연차는 최소 일주일(7일) 전 신청이 원칙입니다.")
    else:
        try:
            # 1. 일수 및 차감 로직 설정
            # 오전반차는 시트 차감을 하지 않으므로 deduct_val을 0으로 설정 가능하나, 로그에는 0.5 또는 1로 표시
            deduct_val = 0.5 if "0.5" in l_type or "오전반차" in l_type else 1.0
            
            # 2. 시트 업데이트 (오전반차는 숫자 차감 건너뜀)
            new_val_msg = ""
            if l_type != "오전반차":
                name_list = status_sheet.col_values(1)
                row_idx = name_list.index(name) + 1
                col_idx = 8 if "연차" in l_type else 9
                target_label = "남은 연차" if col_idx == 8 else "남은 월차"
                
                current_val = float(status_sheet.cell(row_idx, col_idx).value or 0)
                new_val = current_val - deduct_val
                status_sheet.update_cell(row_idx, col_idx, new_val)
                new_val_msg = f"\n현시점 {target_label}: {new_val}개"
            else:
                new_val_msg = "\n(오전반차는 잔여 개수에서 차감되지 않습니다)"

            # 3. 휴가기록 시트에 데이터 추가
            emergency_tag = " (당일아픔)" if is_emergency else ""
            new_row = [str(t_date), name, l_type + emergency_tag, reason, deduct_val]
            record_sheet.append_row(new_row)
            
            # 4. 토요일 연속 사용 체크
            sat_warning = ""
            if is_sat:
                user_records = records_df[records_df['이름'] == name]
                if not user_records.empty:
                    user_records['날짜_dt'] = pd.to_datetime(user_records['날짜'])
                    last_sat = user_records[user_records['날짜_dt'].dt.weekday == 5]['날짜_dt'].max()
                    if last_sat and (pd.Timestamp(t_date) - last_sat).days <= 14:
                        sat_warning = "\n⚠️ 주의: 토요일 연속 사용이 감지되었습니다."

            # 5. 라인 알림 전송
            msg = f"🔔 [휴가신청]{emergency_tag}\n{name}님이 {t_date}({l_type})을 신청했습니다.{new_val_msg}{sat_warning}\n사유: {reason}"
            send_line(msg)
            
            st.success(f"✅ 신청 완료! {new_val_msg}")
            st.rerun()
            
        except ValueError:
            st.error(f"시트에서 {name}님을 찾지 못했습니다.")

# 5. 하단 로그 표시
st.subheader("📋 전체 휴가 기록 (로그)")
updated_records = pd.DataFrame(record_sheet.get_all_records())
if not updated_records.empty:
    st.dataframe(updated_records.sort_values("날짜", ascending=False), use_container_width=True)