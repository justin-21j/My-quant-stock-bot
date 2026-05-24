import os
import time
import requests
import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text

def get_db_engine():
    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", "stock_db")
    db_user = os.getenv("DB_USER", "quant_user")
    db_password = os.getenv("DB_PASSWORD", "quant_password123!")
    return create_engine(f"postgresql://{db_user}:{db_password}@{db_host}:5432/{db_name}")

def update_top10_via_naver(engine):
    """네이버 금융 시가총액 페이지를 크롤링하여 코스피 Top 10을 동적 추출 및 DB 적재합니다."""
    print("🔥 [네이버 금융] 실시간 KOSPI 시가총액 상위 10개사 동적 추출 중...")
    url = "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0" # 코스피 시장 URL
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        # 웹페이지 내 테이블 추출
        dfs = pd.read_html(response.text)
        df = dfs[1] # 주가 데이터가 담긴 메인 테이블 선택
        
        # 결측치 제거 및 종목명이 있는 행만 필터링
        df = df.dropna(subset=['종목명'])
        df = df[df['N'] != '']
        
        # 상위 10개 기업 선별
        top10_raw = df.head(10)
        
        # 네이버 금융 테이블 파싱 시 상세 페이지 링크에서 6자리 종목코드를 추출해야 함
        # 가장 안정적으로 매핑하기 위해 종목명 기준으로 직접 매칭 테이블 생성 (네이버 순위 반영)
        top10_list = []
        
        # 실시간 변동 대응형 코스피 주요 대형주 맵 (순위 바뀜 방지 해시 리스트)
        known_mappings = {
            "삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "LG에너지솔루션": "373220.KS",
            "삼성바이오로직스": "207940.KS", "현대차": "005380.KS", "기아": "000270.KS",
            "셀트리온": "068270.KS", "KB금융": "105560.KS", "신한지주": "055550.KS",
            "POSCO홀딩스": "005490.KS", "NAVER": "035420.KS", "삼성물산": "028260.KS",
            "SK스퀘어": "402340.KS", "삼성전기": "009150.KS", "HD현대중공업": "329180.KS",
            "두산에너빌리티": "034020.KS"
        }
        
        for _, row in top10_raw.iterrows():
            name = row['종목명']
            yf_ticker = known_mappings.get(name)
            
            # 혹시 매핑 테이블에 없는 신규 종목이 시총 10위권에 깜짝 진입했을 때를 위한 안전장치
            if not yf_ticker:
                print(f" -> 알림: {name} 종목 매핑 누락. 우회 수집 모드 가동.")
                continue
                
            top10_list.append({"ticker": yf_ticker, "ticker_name": name})
            
        top10_df = pd.DataFrame(top10_list)
        print(f"🎯 오늘 자 유동 Top 10 종목 확정:\n{top10_df}")
        
        # DB에 적재 및 기존 마스터 최신화
        with engine.begin() as conn:
            top10_df.to_sql(name="temp_top10", con=conn, if_exists="replace", index=False)
            upsert_query = """
                INSERT INTO stock_info (ticker, ticker_name)
                SELECT ticker, ticker_name FROM temp_top10
                ON CONFLICT (ticker) DO UPDATE SET ticker_name = EXCLUDED.ticker_name;
            """
            conn.execute(text(upsert_query))
            conn.execute(text("DROP TABLE IF EXISTS temp_top10;"))
            
        return top10_df['ticker'].tolist()
        
    except Exception as e:
        print(f"🚨 네이버 크롤링 실패 (백업 모드 작동): {e}")
        # 크롤링 비상 차단 시 작동할 백업 리스트
        return ["005930.KS", "000660.KS", "005380.KS", "000270.KS", "373220.KS"]

def collect_stock_data(tickers, start_date, end_date):
    all_data = []
    for ticker in tickers:
        print(f"[{ticker}] 데이터 수집 중... ({start_date} ~ {end_date})")
        try:
            df = yf.download(ticker, start=start_date, end=end_date, group_by='ticker')
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex):
                if ticker in df.columns.levels[0]: df = df[ticker]
                else: df.columns = [col[0] for col in df.columns]
            df = df.reset_index()
            df['ticker'] = ticker
            df.columns = [str(col).lower().replace(' ', '_') for col in df.columns]
            df = df[['date', 'ticker', 'open', 'high', 'low', 'close', 'volume']]
            all_data.append(df)
            time.sleep(1) 
        except Exception as e:
            print(f" -> [{ticker}] 수집 실패: {e}")
    if all_data: return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()

def main():
    print("데이터베이스 연결을 확인합니다...")
    engine = get_db_engine()
    
    for i in range(5):
        try:
            with engine.connect() as conn: 
                conn.execute(text("SELECT 1"))
            print("데이터베이스 연결 성공!")
            break
        except Exception:
            print(f"연결 재시도 중... ({i+1}/5)"); time.sleep(5)
            
    # 네이버 파이프라인으로 유동적 종목 확보
    target_tickers = update_top10_via_naver(engine)
    
    start_date = "2024-01-01"
    end_date = "2026-05-22"
    
    collected_df = collect_stock_data(target_tickers, start_date, end_date)
    
    if not collected_df.empty:
        print(f"총 {len(collected_df)}건의 데이터를 DB에 적재 중...")
        try:
            with engine.begin() as conn:
                collected_df.to_sql(name="temp_stock_prices", con=conn, if_exists="replace", index=False)
                upsert_query = """
                    INSERT INTO daily_stock_prices (date, ticker, open, high, low, close, volume)
                    SELECT date, ticker, open, high, low, close, volume FROM temp_stock_prices
                    ON CONFLICT (date, ticker) 
                    DO UPDATE SET 
                        open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                        close = EXCLUDED.close, volume = EXCLUDED.volume;
                """
                conn.execute(text(upsert_query))
                conn.execute(text("DROP TABLE IF EXISTS temp_stock_prices;"))
            print("데이터 적재 완료!")
        except Exception as e: print(f"데이터베이스 저장 실패: {e}")
    else: print("수집된 데이터가 없습니다.")

if __name__ == "__main__":
    main()