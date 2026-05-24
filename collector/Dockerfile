FROM python:3.10-slim

WORKDIR /app

# 필수 패키지 설치 및 의존성 복사
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY main.py .

# 스크립트 실행
CMD ["python", "main.py"]
