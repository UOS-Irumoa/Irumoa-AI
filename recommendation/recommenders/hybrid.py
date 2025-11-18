"""
Hybrid 추천 엔진 (규칙 기반 + TF-IDF)

사용자의 학과, 학년, 관심사, 관심분야를 기반으로 추천합니다.

점수 체계:
- 규칙 기반 (60%): 학과/학년/관심사 정확 매칭
  - 학과 일치: 40점 (제한없음: 20점)
  - 학년 일치: 30점 (제한없음: 15점)
  - 관심사 일치: 카테고리 1개당 5점 (최대 30점, 7개까지 선택 가능)
- TF-IDF (40%): 관심분야 텍스트 유사도

추천 방식:
1단계: 규칙 기반 필터링 (학과/학년 매칭)
2단계: TF-IDF 유사도 계산 (관심분야 텍스트 매칭)
3단계: 점수 결합 (규칙 60% + TF-IDF 40%)
"""

from typing import List, Tuple
from datetime import date
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..models import User, Program, RecommendationResult


class HybridRecommender:
    """Hybrid 추천 엔진 (규칙 기반 + TF-IDF)"""

    # 규칙 기반 점수 가중치
    WEIGHT_DEPARTMENT_EXACT = 40.0
    WEIGHT_DEPARTMENT_UNRESTRICTED = 20.0
    WEIGHT_GRADE_EXACT = 30.0
    WEIGHT_GRADE_UNRESTRICTED = 15.0
    WEIGHT_INTEREST_PER_MATCH = 5.0
    MAX_INTEREST_SCORE = 30.0

    # Hybrid 점수 결합 가중치
    WEIGHT_RULE_BASED = 0.6  # 규칙 기반 60%
    WEIGHT_TF_IDF = 0.4      # TF-IDF 40%

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            ngram_range=(1, 2),  # 1-gram, 2-gram
            min_df=1,
            stop_words=None  # 한국어 불용어는 별도 처리 가능
        )

    # ==================== 규칙 기반 메서드 ====================

    def calculate_score(self, user: User, program: Program) -> Tuple[float, List[str]]:
        """
        사용자와 프로그램 간 매칭 점수 계산 (규칙 기반)

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
        score = min(score, self.MAX_INTEREST_SCORE)  # 최대 30점 제한
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

    # ==================== TF-IDF 메서드 ====================

    def _preprocess_text(self, text: str) -> str:
        """텍스트 전처리"""
        # 소문자 변환
        text = text.lower()
        # 특수문자 제거 (한글, 영문, 숫자, 공백만 유지)
        text = re.sub(r'[^가-힣a-z0-9\s]', ' ', text)
        # 연속된 공백 제거
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _create_user_query(self, user: User) -> str:
        """사용자 프로필을 텍스트 쿼리로 변환"""
        parts = [
            user.department,
            ' '.join(user.interests),
            ' '.join(user.interest_fields)
        ]
        query = ' '.join(parts)
        return self._preprocess_text(query)

    def _create_program_text(self, program: Program) -> str:
        """프로그램 정보를 텍스트로 변환"""
        parts = [
            program.title,
            program.content[:500] if program.content else '',  # 내용 일부만
            ' '.join(program.categories),
            ' '.join(program.departments)
        ]
        text = ' '.join(parts)
        return self._preprocess_text(text)

    def calculate_tfidf_score(
        self,
        user: User,
        programs: List[Program]
    ) -> List[float]:
        """
        TF-IDF 유사도 점수 계산

        Args:
            user: 사용자 프로필
            programs: 프로그램 목록

        Returns:
            각 프로그램의 TF-IDF 점수 (0-100)
        """
        if not programs:
            return []

        # 사용자 쿼리 생성
        user_query = self._create_user_query(user)

        # 프로그램 텍스트 생성
        program_texts = [self._create_program_text(p) for p in programs]

        # TF-IDF 벡터화
        try:
            all_texts = [user_query] + program_texts
            tfidf_matrix = self.vectorizer.fit_transform(all_texts)

            # 코사인 유사도 계산
            user_vector = tfidf_matrix[0:1]
            program_vectors = tfidf_matrix[1:]
            similarities = cosine_similarity(user_vector, program_vectors).flatten()

            # 0-100 스케일로 변환
            scores = (similarities * 100).tolist()

            return scores

        except Exception as e:
            print(f"TF-IDF 계산 오류: {e}")
            return [0.0] * len(programs)

    # ==================== Hybrid 메서드 ====================

    def calculate_hybrid_score(
        self,
        user: User,
        program: Program,
        tfidf_score: float
    ) -> float:
        """
        Hybrid 점수 계산 (규칙 기반 + TF-IDF)

        Args:
            user: 사용자 프로필
            program: 프로그램 정보
            tfidf_score: TF-IDF 점수

        Returns:
            최종 점수
        """
        # 규칙 기반 점수 계산
        rule_score, _ = self.calculate_score(user, program)

        # 최종 점수 = 가중 평균
        final_score = (
            rule_score * self.WEIGHT_RULE_BASED +
            tfidf_score * self.WEIGHT_TF_IDF
        )

        return final_score

    def recommend(
        self,
        user: User,
        programs: List[Program],
        limit: int = 5,
        include_closed: bool = False,
        min_score: float = 20.0
    ) -> List[RecommendationResult]:
        """
        Hybrid 추천

        Args:
            user: 사용자 프로필
            programs: 추천 대상 프로그램 목록
            limit: 최대 추천 개수
            include_closed: 마감된 프로그램 포함 여부
            min_score: 최소 점수

        Returns:
            추천 결과 목록 (점수 내림차순 정렬)
        """
        # 마감 필터링
        if not include_closed:
            programs = [p for p in programs if p.is_application_open()]

        if not programs:
            return []

        # TF-IDF 점수 일괄 계산
        tfidf_scores = self.calculate_tfidf_score(user, programs)

        # 각 프로그램별 최종 점수 계산
        recommendations = []
        for program, tfidf_score in zip(programs, tfidf_scores):
            final_score = self.calculate_hybrid_score(
                user, program, tfidf_score
            )

            # 최소 점수 필터링
            if final_score < min_score:
                continue

            recommendations.append(
                RecommendationResult(
                    program=program,
                    score=final_score
                )
            )

        # 점수 내림차순 정렬
        recommendations.sort(key=lambda x: x.score, reverse=True)

        # 상위 N개 반환
        return recommendations[:limit]

    def explain_score(self, user: User, program: Program) -> dict:
        """
        Hybrid 점수 계산 상세 설명

        Returns:
            {
                'total_score': 85.0,
                'breakdown': {
                    'rule_based': {'score': 70.0, 'weight': 0.6, 'weighted': 42.0},
                    'tfidf': {'score': 65.0, 'weight': 0.4, 'weighted': 26.0},
                    'details': {...}
                }
            }
        """
        # 규칙 기반 점수 상세
        rule_breakdown = {}

        # 학과 점수
        dept_score, dept_reason = self._calculate_department_score(user, program)
        rule_breakdown['department'] = {'score': dept_score, 'reason': dept_reason}

        # 학년 점수
        grade_score, grade_reason = self._calculate_grade_score(user, program)
        rule_breakdown['grade'] = {'score': grade_score, 'reason': grade_reason}

        # 관심사 점수
        interest_score, interest_reasons = self._calculate_interest_score(user, program)
        rule_breakdown['interests'] = {
            'score': interest_score,
            'reason': '; '.join(interest_reasons) if interest_reasons else ''
        }

        # 규칙 기반 총점
        rule_score = dept_score + grade_score + interest_score

        # TF-IDF 점수
        tfidf_scores = self.calculate_tfidf_score(user, [program])
        tfidf_score = tfidf_scores[0] if tfidf_scores else 0.0

        # 최종 점수
        final_score = (
            rule_score * self.WEIGHT_RULE_BASED +
            tfidf_score * self.WEIGHT_TF_IDF
        )

        return {
            'total_score': final_score,
            'breakdown': {
                'rule_based': {
                    'score': rule_score,
                    'weight': self.WEIGHT_RULE_BASED,
                    'weighted': rule_score * self.WEIGHT_RULE_BASED
                },
                'tfidf': {
                    'score': tfidf_score,
                    'weight': self.WEIGHT_TF_IDF,
                    'weighted': tfidf_score * self.WEIGHT_TF_IDF
                },
                'details': rule_breakdown
            }
        }
