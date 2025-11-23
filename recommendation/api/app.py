"""
FastAPI 기반 추천 API 서버

Usage:
    python recommendation/api/app.py
    또는
    uvicorn recommendation.api.app:app --reload --port 8000

Endpoints:
    POST /recommend - 프로그램 추천 (5개)
    GET /health - 헬스체크
"""

import sys
import os

# 직접 실행 시 프로젝트 루트를 sys.path에 추가
if __name__ == "__main__":
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, project_root)

from fastapi import FastAPI

if __name__ == "__main__":
    from recommendation.api.routes import setup_routes
else:
    from .routes import setup_routes

# FastAPI 앱 생성
app = FastAPI(
    title="UOS 공지사항 추천 API",
    description="사용자 맞춤형 공지사항 추천 시스템",
    version="1.0.0"
)

# CORS 설정 제거 - 백엔드에서 프록시로 처리

# 라우트 등록
setup_routes(app)


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 80)
    print("  UOS 공지사항 추천 API 서버 시작")
    print("  - 서버 주소: http://localhost:8000")
    print("  - Swagger 문서: http://localhost:8000/docs")
    print("  - 헬스체크: http://localhost:8000/health")
    print("=" * 80 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
