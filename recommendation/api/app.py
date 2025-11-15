"""
FastAPI 기반 추천 API 서버

Usage:
    uvicorn recommendation.api.app:app --reload --port 8000

Endpoints:
    POST /recommend - 프로그램 추천
    POST /explain - 점수 계산 상세 설명
    GET /health - 헬스체크
    GET /programs - 프로그램 목록 조회
    GET /categories - 카테고리 목록 조회
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import setup_routes

# FastAPI 앱 생성
app = FastAPI(
    title="UOS 공지사항 추천 API",
    description="사용자 맞춤형 공지사항 추천 시스템",
    version="1.0.0"
)

# CORS 설정 (프론트엔드 연동용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우트 등록
setup_routes(app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
