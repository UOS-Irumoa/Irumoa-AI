# ---- Runtime (single stage; 간단/빠름) ----
FROM python:3.11-slim

# 시스템 기본 패키지(필요 최소)
# EasyOCR, numpy, Pillow 등을 위한 최소 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libgomp1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements가 있다면 먼저 복사/설치해서 캐시 극대화
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . /app

# 서비스 포트
ENV PORT=8000
# 앱 모듈 경로
ENV APP_MODULE=recommendation.api.app:app

EXPOSE 8000

# uvicorn으로 실행 (FastAPI/ASGI 호환)
CMD ["sh", "-c", "python -m uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT}"]
