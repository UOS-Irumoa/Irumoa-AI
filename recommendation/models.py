"""
데이터 모델 정의
"""

from typing import List, Optional
from datetime import date, datetime
from pydantic import BaseModel, Field


class User(BaseModel):
    """사용자 프로필"""

    user_id: Optional[int] = None
    department: str = Field(..., description="학과명 (예: 컴퓨터과학부)")
    grade: int = Field(..., ge=1, le=7, description="학년 (1-5: 학년, 6: 졸업생, 7: 대학원생)")
    interests: List[str] = Field(
        ...,
        description="관심사 목록",
        examples=[["공모전", "취업"]]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "department": "컴퓨터과학부",
                "grade": 2,
                "interests": ["공모전", "취업", "특강"]
            }
        }


class Program(BaseModel):
    """프로그램 정보"""

    id: int
    title: str
    link: str
    content: str
    categories: List[str] = Field(default_factory=list)
    departments: List[str] = Field(default_factory=list)
    grades: List[int] = Field(default_factory=list)
    app_start_date: Optional[date] = None
    app_end_date: Optional[date] = None
    posted_date: Optional[date] = None

    def is_deadline_near(self, days: int = 7) -> bool:
        """마감일이 가까운지 확인 (기본: 7일 이내)"""
        if not self.app_end_date:
            return False

        today = date.today()
        days_remaining = (self.app_end_date - today).days

        return 0 <= days_remaining <= days

    def is_application_open(self) -> bool:
        """현재 신청 가능한지 확인"""
        today = date.today()

        # 시작일 체크
        if self.app_start_date and self.app_start_date > today:
            return False

        # 마감일 체크
        if self.app_end_date and self.app_end_date < today:
            return False

        return True

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "title": "2025 AI 해커톤 대회",
                "link": "https://www.uos.ac.kr/korNotice/view.do?seq=12345",
                "content": "AI 주제 해커톤...",
                "categories": ["공모전", "비교과"],
                "departments": ["컴퓨터과학부", "전자공학과"],
                "grades": [1, 2, 3, 4],
                "app_start_date": "2025-11-01",
                "app_end_date": "2025-11-30"
            }
        }


class RecommendationResult(BaseModel):
    """추천 결과"""

    program: Program
    score: float = Field(..., description="추천 점수 (0-100)")
    reasons: List[str] = Field(default_factory=list, description="추천 이유")

    class Config:
        json_schema_extra = {
            "example": {
                "program": {
                    "id": 1,
                    "title": "2025 AI 해커톤 대회",
                    "link": "https://www.uos.ac.kr/korNotice/view.do?seq=12345",
                    "content": "AI 주제 해커톤...",
                    "categories": ["공모전", "비교과"],
                    "departments": ["컴퓨터과학부"],
                    "grades": [1, 2, 3, 4],
                    "app_start_date": "2025-11-01",
                    "app_end_date": "2025-11-30"
                },
                "score": 85.0,
                "reasons": [
                    "학과 일치: 컴퓨터과학부",
                    "학년 일치: 2학년",
                    "관심사 일치: 공모전",
                    "마감 임박 (7일 이내)"
                ]
            }
        }


class RecommendationRequest(BaseModel):
    """추천 요청"""

    user: User
    limit: int = Field(default=20, ge=1, le=100, description="추천 개수")
    include_closed: bool = Field(default=False, description="마감된 프로그램 포함 여부")
    min_score: float = Field(default=20.0, ge=0, le=100, description="최소 점수")

    class Config:
        json_schema_extra = {
            "example": {
                "user": {
                    "department": "컴퓨터과학부",
                    "grade": 2,
                    "interests": ["공모전", "취업"]
                },
                "limit": 20,
                "include_closed": False,
                "min_score": 20.0
            }
        }


class RecommendationResponse(BaseModel):
    """추천 응답"""

    recommendations: List[RecommendationResult]
    total_count: int
    user: User

    class Config:
        json_schema_extra = {
            "example": {
                "recommendations": [
                    {
                        "program": {
                            "id": 1,
                            "title": "2025 AI 해커톤 대회",
                            "categories": ["공모전"],
                            "departments": ["컴퓨터과학부"],
                            "grades": [2]
                        },
                        "score": 85.0,
                        "reasons": ["학과 일치", "학년 일치", "관심사 일치"]
                    }
                ],
                "total_count": 1,
                "user": {
                    "department": "컴퓨터과학부",
                    "grade": 2,
                    "interests": ["공모전", "취업"]
                }
            }
        }
