import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine, text

st.set_page_config(page_title="주식 봇 모니터링 대시보드", layout="wide")

def get_db_engine():
    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", "stock_db")
    db_user = os.getenv("DB_USER", "quant_user")
    db_password = os.getenv("DB_PASSWORD", "quant_password123!")
    
    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:5432/{db_name}"
    return create_engine(db_url)

@st.cache_data(ttl=60) # 60초 간격 동적 캐싱 리프레시
def load_data():
    engine = get_db_engine()
    # 🚨 [동적 DB 연동]: 데이터 로드 시점부터 실시간 시총 상위 마스터 테이블과 주가 지표를 결합
    query = """
        SELECT t.date, t.ticker, s.ticker_name, t.close, t.rsi14, t.ma5, t.ma20 
        FROM technical_indicators t
        JOIN stock_info s ON t.ticker = s.ticker
        ORDER BY t.date ASC;
    """
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)

st.title("📈 퀀트 투자 봇 실시간 모니터링 대시보드")
st.markdown("데이터베이스 중심(DB-driven) 아키텍처로 변환되어 실시간 시총 Top 10 종목을 완벽히 동적 추적합니다.")

try:
    df = load_data()
    
    if df.empty:
        st.warning("분석 데이터가 아직 데이터베이스에 적재되지 않았습니다. 분석 엔진 파이프라인 가동을 확인하세요.")
    else:
        # 🚨 요청하신 '종목명(코드)' 형태의 대시보드 표출용 컬럼 생성
        df['display_name'] = df['ticker_name'] + "(" + df['ticker'] + ")"
        
        # 1. 사이드바 - 유동적으로 변화하는 '종목명(코드)' 선택 박스 자동 갱신
        display_options = df['display_name'].unique()
        selected_display = st.sidebar.selectbox("🎯 분석할 종목을 선택하세요", display_options)
        
        # 선택된 종목 그룹으로 필터링
        ticker_df = df[df['display_name'] == selected_display].copy()
        ticker_df['date'] = pd.to_datetime(ticker_df['date'])
        
        # 2. 메인 그래픽 뷰포트 - 인터랙티브 차트 매핑
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.1, row_width=[0.4, 0.6])
        
        # (1) 상단 레이어: 종가 및 이평선 
        fig.add_trace(go.Scatter(x=ticker_df['date'], y=ticker_df['close'], name="종가", line=dict(color="royalblue", width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=ticker_df['date'], y=ticker_df['ma5'], name="5일 이평선", line=dict(color="orange", width=1, dash='dash')), row=1, col=1)
        fig.add_trace(go.Scatter(x=ticker_df['date'], y=ticker_df['ma20'], name="20일 이평선", line=dict(color="purple", width=1, dash='dash')), row=1, col=1)
        
        # (2) 하단 레이어: RSI 오실레이터 추이
        fig.add_trace(go.Scatter(x=ticker_df['date'], y=ticker_df['rsi14'], name="RSI(14)", line=dict(color="crimson", width=2)), row=2, col=1)
        
        fig.add_hline(y=65, line_dash="dash", line_color="red", annotation_text="과매수 제어선 (65)", row=2, col=1)
        fig.add_hline(y=35, line_dash="dash", line_color="green", annotation_text="과매도 제어선 (35)", row=2, col=1)
        
        # 대시보드 레이아웃 타이틀에 동적 명칭 결합 표출
        fig.update_layout(
            title=f"📊 {selected_display} 실시간 주가 추이 및 지표 분석 모니터링",
            xaxis_title="날짜",
            template="plotly_dark",
            height=700,
            showlegend=True
        )
        
        fig.update_yaxes(title_text="주가 (원)", row=1, col=1)
        fig.update_yaxes(title_text="RSI 수치", range=[0, 100], row=2, col=1)
        
        # 웹페이지에 반응형 차트 렌더링
        st.plotly_chart(fig, use_container_width=True)
        
        # 3. 하단 상세 내역 데이터프레임 구조화
        st.subheader("📋 실시간 퀀트 데이터프레임 백로그")
        output_df = ticker_df[['date', 'ticker', 'ticker_name', 'close', 'ma5', 'ma20', 'rsi14']].copy()
        output_df.columns = ['날짜', '종목코드', '종목명', '종가(원)', '5일선', '20일선', 'RSI(14)']
        st.dataframe(output_df.tail(30).sort_values('날짜', ascending=False), use_container_width=True)

except Exception as e:
    st.error(f"데이터 뷰포트 로딩 예외 발생: {e}")