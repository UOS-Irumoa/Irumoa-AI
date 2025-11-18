"""
API 라우트/엔드포인트 정의
"""

from datetime import date

from fastapi import HTTPException

from ..models import (
    RecommendationRequest,
    RecommendationResponse,
    ProgramResponse
)
from ..recommenders.hybrid import HybridRecommender
from .database import fetch_programs_from_db

# 추천 엔진 초기화
recommender = HybridRecommender()


def setup_routes(app):
    """FastAPI 앱에 라우트 등록"""

    @app.get("/health")
    async def health_check():
        """헬스체크 엔드포인트"""
        return {
            "status": "healthy",
            "version": "1.0.0",
            "timestamp": date.today().isoformat()
        }

    @app.post("/recommend", response_model=RecommendationResponse)
    async def recommend_programs(request: RecommendationRequest):
        """
        프로그램 추천 API

        사용자 프로필을 기반으로 맞춤형 프로그램 5개를 추천합니다.

        **점수 체계 (0-100점):**
        - 규칙 기반 (60%): 학과 40점 + 학년 30점 + 관심사 최대 30점
        - TF-IDF (40%): 관심분야 텍스트 유사도

        **Example Request:**
        ```json
        {
            "user": {
                "departments": ["컴퓨터과학부"],
                "grade": 2,
                "interests": ["공모전", "취업"],
                "interest_fields": ["AI", "머신러닝"]
            }
        }
        ```

        **복수전공 Example:**
        ```json
        {
            "user": {
                "departments": ["컴퓨터과학부", "경영학부"],
                "grade": 2,
                "interests": ["공모전", "취업"],
                "interest_fields": ["AI", "머신러닝"]
            }
        }
        ```
        """
        try:
            # DB에서 프로그램 조회 (카테고리 필터링)
            programs = fetch_programs_from_db(
                departments=request.user.departments,
                grade=request.user.grade,
                categories=request.user.interests,
                include_closed=False
            )

            # 추천 실행 (최대 5개)
            recommendations = recommender.recommend(
                user=request.user,
                programs=programs,
                limit=5,
                include_closed=False,
                min_score=20.0
            )

            # 응답 형식 변환
            content = []
            for rec in recommendations:
                prog = rec.program
                content.append(
                    ProgramResponse(
                        id=prog.id,
                        title=prog.title,
                        link=prog.link,
                        content=prog.content,
                        appStartDate=prog.app_start_date.isoformat() if prog.app_start_date else None,
                        appEndDate=prog.app_end_date.isoformat() if prog.app_end_date else None,
                        categories=prog.categories,
                        departments=prog.departments,
                        grades=prog.grades
                    )
                )

            return RecommendationResponse(content=content)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}")
