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

# 2. 구글 시트 연결
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

# 한국어 요일 및 기본 설정
WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']
# [설정] 직원별 기본 부여 개수 (전미진 선생님 연차 17개로 수정됨)
BASE_TOTALS = {
    "정도희": {"type": "월차", "total": 12},
    "전미진": {"type": "연차", "total": 17}
}

# 3. 데이터 로드 및 잔여량 계산 함수
def get_records():
    return pd.DataFrame(record_sheet.get_all_records())

def calculate_remaining(name, records_df):
    base_info = BASE_TOTALS.get(name)
    if not base_info:
        return 0.0, "알수없음"
    
    base_total = base_info["total"]
    leave_category = base_info["type"]
    
    # 해당 직원의 로그 중 '오전반차'를 제외한(오전반차는 별도 혜택이므로) 연차/월차 기록만 필터링
    # 유형에 해당 카테고리(연차 또는 월차)가 포함된 것만 합산
    used_df = records_df[
        (records_df['이름'] == name) & 
        (records_df['유형'].str.contains(leave_category)) &
        (~records_df['유형'].str.contains("오전반차")) # 오전반차 제외
    ]
    
    used_sum = used_df['일수'].sum()
    return float(base_total - used_sum), leave_category

# 초기 데이터 로드
records_df = get_records()

st.title("🌿 2026 동경한의원 세종 휴가 대시보드 (v2.5)")

# 4. 실시간 계산된 현황 표시
c1, c2 = st.columns(2)
with c1:
    rem_d, label_d = calculate_remaining("정도희", records_df)
    st.metric(f"정도희님 잔여 {label_d}", f"{rem_d}개")
with c2:
    rem_m, label_m = calculate_remaining("전미진", records_df)
    st.metric(f"전미진님 잔여 {label_m}", f"{rem_m}개")

st.divider()

# 5. 실시간 반응형 신청 사이드바
st.sidebar.header("📅 휴가 신청")
name = st.sidebar.selectbox("신청자 선택", ["정도희", "전미진"])

if name == "정도희":
    available_options = ["월차"]
else:
    available_options = ["연차", "0.5연차", "오전반차"]

with st.sidebar.form("leave_form", clear_on_submit=True):
    st.write(f"**{name}** 선생님 신청서")
    t_date = st.date_input("날짜", min_value=date(2026, 1, 1))
    is_emergency = st.checkbox("❗ 갑자기 아파서 신청하시나요?")
    l_type = st.selectbox("유형 선택", available_options)
    reason = st.text_input("사유 입력")
    submit = st.form_submit_button("신청 완료")

if submit:
    day_idx = t_date.weekday()
    weekday_str = WEEKDAYS[day_idx]
    
    # [오전반차 검증]
    if l_type == "오전반차":
        if t_date.day >= 25:
            st.error("❌ 오전반차는 25일 이후 소멸되어 신청할 수 없습니다.")
            st.stop()
        
        records_df['날짜_dt'] = pd.to_datetime(records_df['날짜'].str.split(' ').str[0])
        used_this_month = records_df[
            (records_df['이름'] == "전미진") & 
            (records_df['유형'].str.contains("오전반차")) & 
            (records_df['날짜_dt'].dt.month == t_date.month) &
            (records_df['날짜_dt'].dt.year == t_date.year)
        ]
        if not used_this_month.empty:
            st.error(f"❌ 이번 달({t_date.month}월) 오전반차를 이미 사용하셨습니다.")
            st.stop()

    # [일반 규칙 검증]
    diff = (t_date - date.today()).days
    if is_emergency and l_type in ["월차", "0.5연차", "오전반차"]:
        st.error("❌ 갑자기 아픈 경우 '연차'만 선택 가능합니다.")
    elif not is_emergency and l_type in ["월차", "0.5연차"] and diff < 7:
        st.error("❌ 월차/0.5연차는 최소 7일 전 신청이 원칙입니다.")
    else:
        try:
            # 일수 결정 (오전반차도 로그에는 0.5일로 기록하지만 계산에선 제외됨)
            deduct_val = 0.5 if "0.5" in l_type or "오전반차" in l_type else 1.0
            emergency_tag = " (당일아픔)" if is_emergency else ""
            
            # 1. 휴가기록 시트에 로그 먼저 추가 (이것이 계산의 기준이 됨)
            record_sheet.append_row([str(t_date), name, l_type + emergency_tag, reason, deduct_val])
            
            # 2. 추가된 로그를 포함하여 다시 계산
            new_records_df = get_records()
            new_rem, leave_label = calculate_remaining(name, new_records_df)
            
            # 3. 직원현황 시트의 '남은' 칸도 동기화 (선택사항이나, 다른 앱에서 읽을 수 있으므로 업데이트)
            name_list = status_sheet.col_values(1)
            row_idx = name_list.index(name) + 1
            col_idx = 8 if leave_label == "연차" else 9
            status_sheet.update_cell(row_idx, col_idx, new_rem)

            # 4. 토요일 체크
            sat_warning = ""
            if day_idx == 5:
                user_records = new_records_df[new_records_df['이름'] == name].copy()
                user_records['날짜_only'] = user_records['날짜'].str.split(' ').str[0]
                user_records['날짜_dt'] = pd.to_datetime(user_records['날짜_only'])
                last_sat = user_records[user_records['날짜_dt'].dt.weekday == 5]['날짜_dt'].sort_values().iloc[:-1].max()
                if last_sat and (pd.Timestamp(t_date) - last_sat).days <= 14:
                    sat_warning = "\n⚠️ 주의: 토요일 연속 사용 감지!"

            # 5. 라인 발송
            val_msg = f"\n현시점 잔여 {leave_label}: {new_rem}개" if l_type != "오전반차" else "\n(오전반차는 개수 차감 없음)"
            msg = f"🔔 [휴가신청]{emergency_tag}\n{name}님이 {t_date}({weekday_str})({l_type})을 신청했습니다.{val_msg}{sat_warning}\n사유: {reason}"
            send_line(msg)
            
            st.success(f"✅ 신청 완료! {val_msg}")
            st.rerun()
            
        except Exception as e:
            st.error(f"처리 중 오류 발생: {e}")

# 6. 하단 로그 표시 (요일 포함)
st.subheader("📋 전체 휴가 기록 (로그)")
if not records_df.empty:
    display_df = records_df.copy()
    display_df['날짜_dt'] = pd.to_datetime(display_df['날짜'].str.split(' ').str[0])
    display_df['날짜'] = display_df['날짜_dt'].dt.strftime('%Y-%m-%d') + " (" + display_df['날짜_dt'].dt.weekday.map(lambda x: WEEKDAYS[x]) + ")"
    st.dataframe(display_df.drop(columns=['날짜_dt']).sort_values("날짜", ascending=False), use_container_width=True)