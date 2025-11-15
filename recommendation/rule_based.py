"""
규칙 기반 추천 엔진

사용자의 학과, 학년, 관심사를 기반으로 점수를 계산하여 추천합니다.

점수 체계:
- 학과 일치: 40점 (제한없음: 20점)
- 학년 일치: 30점 (제한없음: 15점)
- 관심사 일치: 카테고리 1개당 10점 (최대 30점)
- 마감 임박 보너스: 10점 (7일 이내)
"""

from typing import List, Tuple
from datetime import date

from .models import User, Program, RecommendationResult


class RuleBasedRecommender:
    """규칙 기반 추천 엔진"""

    # 점수 가중치 설정
    WEIGHT_DEPARTMENT_EXACT = 40.0
    WEIGHT_DEPARTMENT_UNRESTRICTED = 20.0
    WEIGHT_GRADE_EXACT = 30.0
    WEIGHT_GRADE_UNRESTRICTED = 15.0
    WEIGHT_INTEREST_PER_MATCH = 10.0
    BONUS_DEADLINE_NEAR = 10.0

    def __init__(self):
        pass

    def calculate_score(self, user: User, program: Program) -> Tuple[float, List[str]]:
        """
        사용자와 프로그램 간 매칭 점수 계산

        Args:
            user: 사용자 프로필
            program: 프로그램 정보

        Returns:
            (점수, 추천 이유 목록)
        """
        score = 0.0
        reasons = []

        # 1. 학과 매칭 (40점)
        dept_score, dept_reason = self._calculate_department_score(user, program)
        score += dept_score
        if dept_reason:
            reasons.append(dept_reason)

        # 2. 학년 매칭 (30점)
        grade_score, grade_reason = self._calculate_grade_score(user, program)
        score += grade_score
        if grade_reason:
            reasons.append(grade_reason)

        # 3. 관심사 매칭 (최대 30점)
        interest_score, interest_reasons = self._calculate_interest_score(user, program)
        score += interest_score
        reasons.extend(interest_reasons)

        # 4. 마감 임박 보너스 (10점)
        if program.is_deadline_near():
            score += self.BONUS_DEADLINE_NEAR
            days_remaining = (program.app_end_date - date.today()).days
            reasons.append(f"마감 임박 ({days_remaining}일 남음)")

        return score, reasons

    def _calculate_department_score(self, user: User, program: Program) -> Tuple[float, str]:
        """학과 매칭 점수 계산"""
        if not program.departments:
            return 0.0, ""

        # 정확한 학과 일치
        if user.department in program.departments:
            return self.WEIGHT_DEPARTMENT_EXACT, f"학과 일치: {user.department}"

        # 제한없음
        if "제한없음" in program.departments:
            return self.WEIGHT_DEPARTMENT_UNRESTRICTED, "학과 제한 없음"

        return 0.0, ""

    def _calculate_grade_score(self, user: User, program: Program) -> Tuple[float, str]:
        """학년 매칭 점수 계산"""
        if not program.grades:
            return 0.0, ""

        # 정확한 학년 일치
        if user.grade in program.grades:
            grade_name = self._get_grade_name(user.grade)
            return self.WEIGHT_GRADE_EXACT, f"학년 일치: {grade_name}"

        # 제한없음 (grade = 0)
        if 0 in program.grades:
            return self.WEIGHT_GRADE_UNRESTRICTED, "학년 제한 없음"

        return 0.0, ""

    def _calculate_interest_score(self, user: User, program: Program) -> Tuple[float, List[str]]:
        """관심사 매칭 점수 계산"""
        if not user.interests or not program.categories:
            return 0.0, []

        # 교집합 찾기
        matching_categories = set(user.interests) & set(program.categories)

        if not matching_categories:
            return 0.0, []

        score = len(matching_categories) * self.WEIGHT_INTEREST_PER_MATCH
        reasons = [f"관심사 일치: {', '.join(matching_categories)}"]

        return score, reasons

    def _get_grade_name(self, grade: int) -> str:
        """학년 코드를 이름으로 변환"""
        grade_names = {
            0: "제한없음",
            1: "1학년",
            2: "2학년",
            3: "3학년",
            4: "4학년",
            5: "5학년",
            6: "졸업생",
            7: "대학원생"
        }
        return grade_names.get(grade, f"{grade}학년")

    def recommend(
        self,
        user: User,
        programs: List[Program],
        limit: int = 20,
        include_closed: bool = False,
        min_score: float = 20.0
    ) -> List[RecommendationResult]:
        """
        프로그램 추천

        Args:
            user: 사용자 프로필
            programs: 추천 대상 프로그램 목록
            limit: 최대 추천 개수
            include_closed: 마감된 프로그램 포함 여부
            min_score: 최소 점수 (이 점수 이하는 제외)

        Returns:
            추천 결과 목록 (점수 내림차순 정렬)
        """
        recommendations = []

        for program in programs:
            # 마감된 프로그램 필터링
            if not include_closed and not program.is_application_open():
                continue

            # 점수 계산
            score, reasons = self.calculate_score(user, program)

            # 최소 점수 필터링
            if score < min_score:
                continue

            recommendations.append(
                RecommendationResult(
                    program=program,
                    score=score,
                    reasons=reasons
                )
            )

        # 점수 내림차순 정렬
        recommendations.sort(key=lambda x: x.score, reverse=True)

        # 상위 N개 반환
        return recommendations[:limit]

    def explain_score(self, user: User, program: Program) -> dict:
        """
        점수 계산 상세 설명 (디버깅용)

        Returns:
            {
                'total_score': 85.0,
                'breakdown': {
                    'department': {'score': 40.0, 'reason': '학과 일치: 컴퓨터과학부'},
                    'grade': {'score': 30.0, 'reason': '학년 일치: 2학년'},
                    'interests': {'score': 20.0, 'reason': '관심사 일치: 공모전, 취업'},
                    'deadline': {'score': 10.0, 'reason': '마감 임박 (5일 남음)'}
                }
            }
        """
        breakdown = {}

        # 학과 점수
        dept_score, dept_reason = self._calculate_department_score(user, program)
        breakdown['department'] = {'score': dept_score, 'reason': dept_reason}

        # 학년 점수
        grade_score, grade_reason = self._calculate_grade_score(user, program)
        breakdown['grade'] = {'score': grade_score, 'reason': grade_reason}

        # 관심사 점수
        interest_score, interest_reasons = self._calculate_interest_score(user, program)
        breakdown['interests'] = {
            'score': interest_score,
            'reason': '; '.join(interest_reasons) if interest_reasons else ''
        }

        # 마감 임박 점수
        deadline_score = 0.0
        deadline_reason = ''
        if program.is_deadline_near():
            deadline_score = self.BONUS_DEADLINE_NEAR
            days_remaining = (program.app_end_date - date.today()).days
            deadline_reason = f"마감 임박 ({days_remaining}일 남음)"

        breakdown['deadline'] = {'score': deadline_score, 'reason': deadline_reason}

        # 총점
        total_score = dept_score + grade_score + interest_score + deadline_score

        return {
            'total_score': total_score,
            'breakdown': breakdown
        }
