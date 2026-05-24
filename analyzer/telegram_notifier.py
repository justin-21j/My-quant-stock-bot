import os
import requests
import pandas as pd
from sqlalchemy import create_engine, text

def get_db_engine():
    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", "stock_db")
    db_user = os.getenv("DB_USER", "quant_user")
    db_password = os.getenv("DB_PASSWORD", "quant_password123!")
    
    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:5432/{db_name}"
    return create_engine(db_url)

def send_telegram_message(message):
    bot_token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("텔레그램 토큰이나 Chat ID 설정이 누락되었습니다.")
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"텔레그램 전송 실패: {response.text}")
    except Exception as e:
        print(f"텔레그램 연동 중 에러 발생: {e}")

def check_signals_and_notify():
    engine = get_db_engine()
    
    # 🚨 [동적 DB 연동]: JOIN을 사용하여 실시간으로 stock_info 테이블의 최신 종목명을 엮어옵니다.
    query = """
        SELECT DISTINCT ON (t.ticker) t.date, t.ticker, s.ticker_name, t.close, t.rsi14
        FROM technical_indicators t
        JOIN stock_info s ON t.ticker = s.ticker
        ORDER BY t.ticker, t.date DESC;
    """
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
    except Exception as e:
        print(f"지표 데이터베이스 조회 에러: {e}")
        return
        
    if df.empty:
        print("최신 지표 데이터가 없어 시그널을 확인하지 못했습니다.")
        return

    print("\n[ 실시간 투자 시그널 감시 중 (동적 종목명 대응) ]")
    
    for _, row in df.iterrows():
        ticker = row['ticker']
        ticker_name = row['ticker_name']  # 💡 DB에서 유동적으로 가져온 종목 한글명
        current_price = float(row['close'])
        rsi = float(row['rsi14'])
        date_str = str(row['date'])[:10]
        
        # 🚨 요청하신 '종목명(코드)' 형태로 문자열 포맷팅
        display_name = f"{ticker_name}({ticker})"
        
        if rsi < 35:
            msg = f"🚨 **[주식 매수 추천 알림]** \n 사랑스런 민갱 예주 예림 원재가 알려드립니다. \n 우리 예자매 사랑해🚨\n\n📅 날짜: {date_str}\n🎫 종목: {display_name}\n💵 현재가: {current_price:,.0f}원\n📊 RSI(14): {rsi:.2f}\n\n*과매도 구간 진입으로 분할 매수를 추천합니다.*"
            send_telegram_message(msg)
        elif rsi > 65:
            msg = f"💰 **[주식 매도 추천 알림]** \n 사랑스런 민갱 예주 예림 원재가 알려드립니다.  \n 우리 예자매 사랑해 💰\n\n📅 날짜: {date_str}\n🎫 종목: {display_name}\n💵 현재가: {current_price:,.0f}원\n📊 RSI(14): {rsi:.2f}\n\n*과열 구간 진입으로 이익 실현 및 매도를 추천합니다.*"
            send_telegram_message(msg)
        else:
            print(f"-> [{display_name}] RSI: {rsi:.2f} (관망 유지)")

if __name__ == "__main__":
    check_signals_and_notify()