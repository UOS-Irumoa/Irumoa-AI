"""
FastAPI 기반 추천 API 서버

Usage:
    uvicorn recommendation.api:app --reload --port 8000

Endpoints:
    POST /recommend - 프로그램 추천
    POST /explain - 점수 계산 상세 설명
    GET /health - 헬스체크
"""

import os
from typing import List, Optional
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

from .models import (
    User,
    Program,
    RecommendationRequest,
    RecommendationResponse,
    RecommendationResult
)
from .rule_based import RuleBasedRecommender

# 환경 변수 로드
load_dotenv()

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

# 추천 엔진 초기화
recommender = RuleBasedRecommender()

# DB 설정
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', ''),
    'port': int(os.getenv('DB_PORT', 3306)),
    'charset': os.getenv('DB_CHARSET', 'utf8mb4'),
    'use_pure': True,
}


def get_db_connection():
    """MySQL 데이터베이스 연결"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"MySQL 연결 실패: {e}")
        return None


def fetch_programs_from_db(
    department: Optional[str] = None,
    grade: Optional[int] = None,
    categories: Optional[List[str]] = None,
    include_closed: bool = False
) -> List[Program]:
    """
    DB에서 프로그램 조회

    Args:
        department: 학과 필터 (선택)
        grade: 학년 필터 (선택)
        categories: 카테고리 필터 (선택)
        include_closed: 마감된 프로그램 포함 여부

    Returns:
        프로그램 목록
    """
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cursor = connection.cursor(dictionary=True)

        # 기본 쿼리
        query = """
            SELECT DISTINCT
                p.id,
                p.title,
                p.link,
                p.content,
                p.app_start_date,
                p.app_end_date,
                p.posted_date
            FROM program p
            WHERE 1=1
        """

        params = []

        # 마감 필터
        if not include_closed:
            query += " AND (p.app_end_date IS NULL OR p.app_end_date >= CURDATE())"

        # 학과 필터 (옵션)
        if department:
            query += """
                AND (
                    EXISTS (
                        SELECT 1 FROM program_department pd
                        WHERE pd.program_id = p.id
                        AND pd.department = %s
                    )
                    OR EXISTS (
                        SELECT 1 FROM program_department pd
                        WHERE pd.program_id = p.id
                        AND pd.department = '제한없음'
                    )
                )
            """
            params.append(department)

        # 학년 필터 (옵션)
        if grade is not None:
            query += """
                AND (
                    EXISTS (
                        SELECT 1 FROM program_grade pg
                        WHERE pg.program_id = p.id
                        AND pg.grade = %s
                    )
                    OR EXISTS (
                        SELECT 1 FROM program_grade pg
                        WHERE pg.program_id = p.id
                        AND pg.grade = 0
                    )
                )
            """
            params.append(grade)

        # 카테고리 필터 (옵션)
        if categories:
            placeholders = ', '.join(['%s'] * len(categories))
            query += f"""
                AND EXISTS (
                    SELECT 1 FROM program_category pc
                    WHERE pc.program_id = p.id
                    AND pc.category IN ({placeholders})
                )
            """
            params.extend(categories)

        # 최신순 정렬 (전체 조회)
        query += " ORDER BY p.id DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # 프로그램별 카테고리, 학과, 학년 조회
        programs = []
        for row in rows:
            program_id = row['id']

            # 카테고리 조회
            cursor.execute(
                "SELECT category FROM program_category WHERE program_id = %s",
                (program_id,)
            )
            categories_result = [r['category'] for r in cursor.fetchall()]

            # 학과 조회
            cursor.execute(
                "SELECT department FROM program_department WHERE program_id = %s",
                (program_id,)
            )
            departments = [r['department'] for r in cursor.fetchall()]

            # 학년 조회
            cursor.execute(
                "SELECT grade FROM program_grade WHERE program_id = %s",
                (program_id,)
            )
            grades = [r['grade'] for r in cursor.fetchall()]

            programs.append(
                Program(
                    id=row['id'],
                    title=row['title'],
                    link=row['link'],
                    content=row['content'] or '',
                    categories=categories_result,
                    departments=departments,
                    grades=grades,
                    app_start_date=row['app_start_date'],
                    app_end_date=row['app_end_date'],
                    posted_date=row['posted_date']
                )
            )

        cursor.close()
        connection.close()

        return programs

    except Error as e:
        if connection:
            connection.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


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
            "interests": ["공모전", "취업"]
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
        "interests": ["공모전", "취업"]
    }
    ```

    **Example Response:**
    ```json
    {
        "total_score": 85.0,
        "breakdown": {
            "department": {"score": 40.0, "reason": "학과 일치: 컴퓨터과학부"},
            "grade": {"score": 30.0, "reason": "학년 일치: 2학년"},
            "interests": {"score": 20.0, "reason": "관심사 일치: 공모전, 취업"},
            "deadline": {"score": 10.0, "reason": "마감 임박 (5일 남음)"}
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
