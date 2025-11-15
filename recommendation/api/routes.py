"""
API 라우트/엔드포인트 정의
"""

from datetime import date
from typing import Optional

from fastapi import HTTPException, Query

from ..models import (
    User,
    RecommendationRequest,
    RecommendationResponse
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

        사용자 프로필을 기반으로 맞춤형 프로그램을 추천합니다.

        **점수 체계:**
        - 학과 일치: 40점 (제한없음: 20점)
        - 학년 일치: 30점 (제한없음: 15점)
        - 관심사 일치: 카테고리 1개당 10점 (최대 30점)
        - 마감 임박: 10점 (7일 이내)

        **Example Request:**
        ```json
        {
            "user": {
                "department": "컴퓨터과학부",
                "grade": 2,
                "interests": ["공모전", "취업"],
                "interest_fields": ["AI", "머신러닝"]
            },
            "limit": 20,
            "include_closed": false,
            "min_score": 20.0
        }
        ```
        """
        try:
            # DB에서 프로그램 조회 (사전 필터링)
            programs = fetch_programs_from_db(
                department=request.user.department,
                grade=request.user.grade,
                categories=request.user.interests,
                include_closed=request.include_closed
            )

            # 추천 실행
            recommendations = recommender.recommend(
                user=request.user,
                programs=programs,
                limit=request.limit,
                include_closed=request.include_closed,
                min_score=request.min_score
            )

            return RecommendationResponse(
                recommendations=recommendations,
                total_count=len(recommendations),
                user=request.user
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}")

    @app.post("/explain")
    async def explain_score(user: User, program_id: int = Query(..., description="프로그램 ID")):
        """
        점수 계산 상세 설명 API

        특정 프로그램에 대한 추천 점수 계산 과정을 상세히 보여줍니다.

        **Example Request:**
        ```
        POST /explain?program_id=123
        {
            "department": "컴퓨터과학부",
            "grade": 2,
            "interests": ["공모전", "취업"],
            "interest_fields": ["AI", "머신러닝"]
        }
        ```

        **Example Response:**
        ```json
        {
            "total_score": 85.0,
            "breakdown": {
                "rule_based": {"score": 70.0, "weight": 0.6, "weighted": 42.0},
                "tfidf": {"score": 65.0, "weight": 0.4, "weighted": 26.0},
                "details": {...}
            }
        }
        ```
        """
        try:
            # 프로그램 조회
            programs = fetch_programs_from_db(include_closed=True)
            program = next((p for p in programs if p.id == program_id), None)

            if not program:
                raise HTTPException(status_code=404, detail=f"Program {program_id} not found")

            # 점수 상세 설명
            explanation = recommender.explain_score(user, program)

            return {
                "program_id": program_id,
                "program_title": program.title,
                **explanation
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Explanation failed: {str(e)}")

    @app.get("/programs")
    async def list_programs(
        department: Optional[str] = Query(None, description="학과 필터"),
        grade: Optional[int] = Query(None, ge=0, le=7, description="학년 필터"),
        category: Optional[str] = Query(None, description="카테고리 필터"),
        include_closed: bool = Query(False, description="마감된 프로그램 포함"),
        limit: int = Query(50, ge=1, le=200, description="최대 개수")
    ):
        """
        프로그램 목록 조회 API

        필터 조건에 맞는 프로그램 목록을 반환합니다.

        **Example:**
        ```
        GET /programs?department=컴퓨터과학부&grade=2&category=공모전&limit=20
        ```
        """
        try:
            categories = [category] if category else None

            programs = fetch_programs_from_db(
                department=department,
                grade=grade,
                categories=categories,
                include_closed=include_closed
            )

            return {
                "programs": programs[:limit],
                "total_count": len(programs[:limit])
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch programs: {str(e)}")

    @app.get("/categories")
    async def list_categories():
        """
        사용 가능한 카테고리 목록 조회

        **Response:**
        ```json
        {
            "categories": ["공모전", "멘토링", "봉사", "취업", "탐방", "특강", "비교과"]
        }
        ```
        """
        return {
            "categories": ["공모전", "멘토링", "봉사", "취업", "탐방", "특강", "비교과"]
        }
