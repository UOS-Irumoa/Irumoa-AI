"""
실제 DB 데이터로 Hybrid 추천 시스템 테스트

Usage:
    python -m recommendation.tests.test_hybrid

기본 설정: 전체 프로그램 조회 (limit=None)
빠른 테스트: test_hybrid.py 내에서 limit=100으로 변경
"""

import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

import os
from datetime import date
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

from recommendation.models import User, Program
from recommendation.recommenders.hybrid import HybridRecommender

# 환경 변수 로드
load_dotenv()

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
        print(f"[ERROR] MySQL 연결 실패: {e}")
        print(f"\n.env 파일을 확인해주세요:")
        print(f"  DB_HOST={DB_CONFIG['host']}")
        print(f"  DB_USER={DB_CONFIG['user']}")
        print(f"  DB_NAME={DB_CONFIG['database']}")
        print(f"  DB_PORT={DB_CONFIG['port']}")
        return None


def fetch_programs_from_db(limit=None):
    """
    DB에서 프로그램 조회

    Args:
        limit: 최대 조회 개수 (None이면 전체)
    """
    connection = get_db_connection()
    if not connection:
        return []

    try:
        cursor = connection.cursor(dictionary=True)

        # 마감되지 않은 프로그램만 조회
        if limit:
            query = """
                SELECT DISTINCT
                    p.id,
                    p.title,
                    p.link,
                    p.content,
                    p.app_start_date,
                    p.app_end_date
                FROM program p
                WHERE (p.app_end_date IS NULL OR p.app_end_date >= CURDATE())
                ORDER BY p.id DESC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
        else:
            query = """
                SELECT DISTINCT
                    p.id,
                    p.title,
                    p.link,
                    p.content,
                    p.app_start_date,
                    p.app_end_date
                FROM program p
                WHERE (p.app_end_date IS NULL OR p.app_end_date >= CURDATE())
                ORDER BY p.id DESC
            """
            cursor.execute(query)
        rows = cursor.fetchall()

        programs = []
        for row in rows:
            program_id = row['id']

            # 카테고리 조회
            cursor.execute(
                "SELECT category FROM program_category WHERE program_id = %s",
                (program_id,)
            )
            categories = [r['category'] for r in cursor.fetchall()]

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

            programs.append(Program(
                id=row['id'],
                title=row['title'],
                link=row['link'],
                content=row['content'] or '',
                categories=categories,
                departments=departments,
                grades=grades,
                app_start_date=row['app_start_date'],
                app_end_date=row['app_end_date'],
                posted_date=None
            ))

        cursor.close()
        connection.close()

        print(f"[INFO] DB에서 {len(programs)}개의 프로그램을 조회했습니다.\n")
        return programs

    except Error as e:
        if connection:
            connection.close()
        print(f"[ERROR] 프로그램 조회 실패: {e}")
        return []


def test_user_1():
    """테스트 1: 컴퓨터과학부 2학년, AI/머신러닝 관심"""
    print("="*80)
    print("테스트 1: 컴퓨터과학부 2학년, AI/머신러닝 관심")
    print("="*80)

    user = User(
        departments=["컴퓨터과학부"],
        grade=2,
        interests=["공모전", "취업"],
        interest_fields=["AI", "머신러닝", "데이터분석", "인공지능"]
    )

    print(f"\n사용자 프로필:")
    print(f"  학과: {', '.join(user.departments)}")
    print(f"  학년: {user.grade}학년")
    print(f"  관심사: {', '.join(user.interests)}")
    print(f"  관심분야: {', '.join(user.interest_fields)}")

    # 전체 프로그램 조회 (빠르게 하려면 limit=100)
    programs = fetch_programs_from_db(limit=None)
    if not programs:
        print("[ERROR] 프로그램 데이터가 없습니다.")
        return

    print(f"[INFO] {len(programs)}개 프로그램으로 추천 계산 중...\n")

    recommender = HybridRecommender()
    results = recommender.recommend(
        user=user,
        programs=programs,
        limit=10,
        min_score=10.0
    )

    print(f"\n총 {len(results)}개 추천:")
    for idx, result in enumerate(results, 1):
        print(f"\n[{idx}] {result.program.title}")
        print(f"    ID: {result.program.id}")
        print(f"    점수: {result.score:.1f}")
        print(f"    카테고리: {', '.join(result.program.categories)}")
        print(f"    대상 학과: {', '.join(result.program.departments[:3])}")
        print(f"    대상 학년: {', '.join([str(g) for g in result.program.grades])}")
        if result.program.app_end_date:
            print(f"    마감일: {result.program.app_end_date}")

    # 점수 상세 설명
    if results:
        print(f"\n\n{'='*80}")
        print(f"1위 프로그램 점수 상세 분석")
        print(f"{'='*80}")
        explanation = recommender.explain_score(user, results[0].program)
        print(f"\n총점: {explanation['total_score']:.1f}점")
        print(f"\n구성:")
        print(f"  규칙 기반: {explanation['breakdown']['rule_based']['score']:.1f}점 × {explanation['breakdown']['rule_based']['weight']} = {explanation['breakdown']['rule_based']['weighted']:.1f}점")
        print(f"  TF-IDF:   {explanation['breakdown']['tfidf']['score']:.1f}점 × {explanation['breakdown']['tfidf']['weight']} = {explanation['breakdown']['tfidf']['weighted']:.1f}점")

        print(f"\n규칙 기반 상세:")
        for key, value in explanation['breakdown']['details'].items():
            if value['score'] > 0:
                print(f"  - {key}: {value['score']:.1f}점 ({value['reason']})")


def test_user_2():
    """테스트 2: 경영학부 3학년, 마케팅/회계 관심"""
    print("\n\n" + "="*80)
    print("테스트 2: 경영학부 3학년, 마케팅/회계 관심")
    print("="*80)

    user = User(
        departments=["경영학부"],
        grade=3,
        interests=["특강", "멘토링"],
        interest_fields=["마케팅", "회계", "경영전략", "재무관리"]
    )

    print(f"\n사용자 프로필:")
    print(f"  학과: {', '.join(user.departments)}")
    print(f"  학년: {user.grade}학년")
    print(f"  관심사: {', '.join(user.interests)}")
    print(f"  관심분야: {', '.join(user.interest_fields)}")

    # 전체 프로그램 조회 (빠르게 하려면 limit=100)
    programs = fetch_programs_from_db(limit=None)
    if not programs:
        print("[ERROR] 프로그램 데이터가 없습니다.")
        return

    print(f"[INFO] {len(programs)}개 프로그램으로 추천 계산 중...\n")

    recommender = HybridRecommender()
    results = recommender.recommend(
        user=user,
        programs=programs,
        limit=10,
        min_score=10.0
    )

    print(f"\n총 {len(results)}개 추천:")
    for idx, result in enumerate(results, 1):
        print(f"\n[{idx}] {result.program.title}")
        print(f"    점수: {result.score:.1f}")


def test_user_3():
    """테스트 3: 제한없음으로 많이 나오는 학과"""
    print("\n\n" + "="*80)
    print("테스트 3: 국어국문학과 1학년, 봉사/탐방 관심")
    print("="*80)

    user = User(
        departments=["국어국문학과"],
        grade=1,
        interests=["봉사", "탐방"],
        interest_fields=["문학", "글쓰기", "독서"]
    )

    print(f"\n사용자 프로필:")
    print(f"  학과: {', '.join(user.departments)}")
    print(f"  학년: {user.grade}학년")
    print(f"  관심사: {', '.join(user.interests)}")
    print(f"  관심분야: {', '.join(user.interest_fields)}")

    # 전체 프로그램 조회 (빠르게 하려면 limit=100)
    programs = fetch_programs_from_db(limit=None)
    if not programs:
        print("[ERROR] 프로그램 데이터가 없습니다.")
        return

    print(f"[INFO] {len(programs)}개 프로그램으로 추천 계산 중...\n")

    recommender = HybridRecommender()
    results = recommender.recommend(
        user=user,
        programs=programs,
        limit=10,
        min_score=5.0  # 낮은 임계값
    )

    print(f"\n총 {len(results)}개 추천:")
    for idx, result in enumerate(results, 1):
        print(f"\n[{idx}] {result.program.title}")
        print(f"    점수: {result.score:.1f}")


def check_db_stats():
    """DB 통계 확인"""
    print("\n" + "="*80)
    print("DB 통계 확인")
    print("="*80)

    connection = get_db_connection()
    if not connection:
        return

    try:
        cursor = connection.cursor(dictionary=True)

        # 전체 프로그램 수
        cursor.execute("SELECT COUNT(*) as total FROM program")
        total_programs = cursor.fetchone()['total']

        # 마감 안 된 프로그램 수
        cursor.execute("""
            SELECT COUNT(*) as active
            FROM program
            WHERE app_end_date IS NULL OR app_end_date >= CURDATE()
        """)
        active_programs = cursor.fetchone()['active']

        # 카테고리별 분포
        cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM program_category
            GROUP BY category
            ORDER BY count DESC
        """)
        categories = cursor.fetchall()

        print(f"\n프로그램 통계:")
        print(f"  전체 프로그램: {total_programs}개")
        print(f"  활성 프로그램: {active_programs}개")

        print(f"\n카테고리별 분포:")
        for cat in categories:
            print(f"  {cat['category']}: {cat['count']}개")

        cursor.close()
        connection.close()

    except Error as e:
        if connection:
            connection.close()
        print(f"[ERROR] 통계 조회 실패: {e}")


def main():
    """메인 함수"""
    print("\n" + "="*80)
    print("실제 DB 데이터로 Hybrid 추천 시스템 테스트")
    print("="*80 + "\n")

    # DB 연결 테스트
    connection = get_db_connection()
    if not connection:
        print("\n[ERROR] DB 연결 실패. 테스트를 종료합니다.")
        return
    connection.close()

    print("[INFO] DB 연결 성공!\n")

    # DB 통계 확인
    check_db_stats()

    # 테스트 실행
    try:
        test_user_1()
        test_user_2()
        test_user_3()

        print("\n\n" + "="*80)
        print("모든 테스트 완료!")
        print("="*80 + "\n")

    except Exception as e:
        print(f"\n[ERROR] 테스트 실패: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
