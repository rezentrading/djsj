import gspread
import requests
import os
import json
from datetime import datetime, timedelta

def send_line(msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {os.environ['LINE_TOKEN']}", "Content-Type": "application/json"}
    payload = {"to": os.environ['LINE_GROUP_ID'], "messages": [{"type": "text", "text": msg}]}
    requests.post(url, headers=headers, json=payload)

try:
    info = json.loads(os.environ['GCP_JSON'])
    gc = gspread.service_account_from_dict(info)
    sh = gc.open("세종점 동경한의원 연차월차관리 시트")
    records = sh.worksheet("휴가기록").get_all_records()
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    # 1. 내일 휴가자 확인
    tomorrow_list = [r['이름'] for r in records if str(r['날짜']) == tomorrow_str]
    
    # 2. 갑자기 아픈 휴가(당일아픔) 중 아직 날짜가 안 지난 것 확인
    emergency_list = []
    for r in records:
        if "(당일아픔)" in str(r['유형']) and str(r['날짜']) >= today_str:
            emergency_list.append(f"{r['날짜']} {r['이름']}님(사유:{r['사유']})")

    # 알림 구성
    final_msg = []
    if tomorrow_list:
        final_msg.append(f"📢 [내일 휴가 안내]\n내일({tomorrow_str})은 {', '.join(tomorrow_list)} 선생님 휴가입니다.")
    
    if emergency_list:
        final_msg.append(f"🚨 [긴급/병가 리마인드]\n오늘 이후 예정된 아픔 신청 내역입니다:\n" + "\n".join(emergency_list))

    if final_msg:
        send_line("\n\n".join(final_msg))

except Exception as e:
    print(f"Error: {e}")