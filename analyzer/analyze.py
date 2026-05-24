import os
import time
import pandas as pd
from sqlalchemy import create_engine, text

def get_db_engine():
    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", "stock_db")
    db_user = os.getenv("DB_USER", "quant_user")
    db_password = os.getenv("DB_PASSWORD", "quant_password123!")
    
    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:5432/{db_name}"
    return create_engine(db_url)

def calculate_rsi(df, period=14):
    """Pandas를 이용해 RSI(상대강도지수)를 계산합니다."""
    # 종가 차이 계산
    delta = df['close'].diff()
    
    # 상승분과 하락분 분리
    gain = (delta.where(delta > 0, 0)).copy()
    loss = (-delta.where(delta < 0, 0)).copy()
    
    # 지수이동평균(EMA) 방식으로 평균 상승/하락폭 계산
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    
    # RS 및 RSI 계산
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def process_technical_indicators():
    engine = get_db_engine()
    
    # 1. DB에서 원시 주가 데이터 불러오기
    print("DB에서 원시 주가 데이터를 불러오는 중...")
    query = "SELECT date, ticker, close FROM daily_stock_prices ORDER BY ticker, date;"

    # 수정 전: query = "SELECT * FROM daily_stock_prices ORDER BY date ASC;"
    # 🚨 수정 후: 현재 활성화된 Top 10 종목의 주가만 동적으로 긁어와 분석합니다.
    query = """
        SELECT d.date, d.ticker, d.open, d.high, d.low, d.close, d.volume 
        FROM daily_stock_prices d
        JOIN stock_info s ON d.ticker = s.ticker
        ORDER BY d.date ASC;
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
        
    if df.empty:
        print("분석할 주가 데이터가 DB에 없습니다.")
        return

    # 2. 종목별(Ticker) 그룹화 후 기술적 지표 연산
    print("기술적 지표(이동평균선, RSI) 계산 중...")
    analyzed_list = []
    
    for ticker, group in df.groupby('ticker'):
        # 날짜 순 정렬 보장
        group = group.sort_values('date').copy()
        
        # 이동평균선(MA) 계산
        group['ma5'] = group['close'].rolling(window=5).mean()
        group['ma20'] = group['close'].rolling(window=20).mean()
        group['ma60'] = group['close'].rolling(window=60).mean()
        
        # RSI 지표 계산
        group['rsi14'] = calculate_rsi(group, period=14)
        
        analyzed_list.append(group)
        
    # 데이터 병합
    final_df = pd.concat(analyzed_list, ignore_index=True)
    
    # 결측치(초반 데이터는 rolling 평균을 못 내므로 NaN 발생) 행 제거
    final_df = final_df.dropna()

    # 3. 분석 결과 DB에 적재
    print(f"총 {len(final_df)}건의 분석 데이터를 DB에 저장합니다...")
    try:
        final_df.to_sql(
            name="technical_indicators",
            con=engine,
            if_exists="replace", # 매번 새로 계산하여 덮어쓰기 (테스트 편의성)
            index=False
        )
        print("지표 분석 및 데이터 적재 완료!")
    except Exception as e:
        print(f"DB 저장 실패: {e}")

if __name__ == "__main__":
    # 데이터 수집기가 먼저 실행되어 장착될 시간을 벌어줍니다.
    print("분석 엔진 작동 준비 중...")
    time.sleep(10) 
    process_technical_indicators()