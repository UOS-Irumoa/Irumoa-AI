"""
추천 시스템 간단 테스트 스크립트
DB에서 직접 데이터 가져와서 추천 결과 출력
"""

import os
import time
from datetime import date
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

from recommendation.models import User, Program
from recommendation.recommenders.hybrid import HybridRecommender

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


def get_programs_from_db(categories=None):
    """
    DB에서 프로그램 조회

    Args:
        categories: 카테고리 필터 리스트 (예: ["공모전", "취업"])
    """
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        # 프로그램 목록 조회
        query = """
            SELECT DISTINCT p.id, p.title, p.link, p.content, p.app_start_date, p.app_end_date
            FROM program p
            WHERE (p.app_end_date IS NULL OR p.app_end_date >= CURDATE())
        """

        params = []

        # 카테고리 필터 추가
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

        query += " ORDER BY p.id DESC"

        cursor.execute(query, params)
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

            programs.append(
                Program(
                    id=row['id'],
                    title=row['title'],
                    link=row['link'],
                    content=row['content'] or '',
                    categories=categories,
                    departments=departments,
                    grades=grades,
                    app_start_date=row['app_start_date'],
                    app_end_date=row['app_end_date']
                )
            )

        cursor.close()
        connection.close()

        return programs

    except Error as e:
        print(f"DB 연결 실패: {e}")
        return []


def main():
    print("=" * 80)
    print("  UOS 공지사항 추천 시스템 - 간단 테스트 (카테고리 필터링)")
    print("=" * 80)

    # 1. 사용자 프로필 설정
    print("\n[1단계] 사용자 프로필 설정")
    user = User(
        departments=["컴퓨터과학부"],
        grade=2,
        interests=["공모전", "취업", "특강"],
        interest_fields=["AI", "머신러닝", "데이터분석", "인공지능"]
    )

    print(f"  - 학과: {', '.join(user.departments)}")
    print(f"  - 학년: {user.grade}학년")
    print(f"  - 관심사: {', '.join(user.interests)}")
    print(f"  - 관심분야: {', '.join(user.interest_fields)}")

    # 2. DB에서 프로그램 조회 (카테고리 필터링 적용)
    print(f"\n[2단계] DB에서 프로그램 조회 중... (카테고리: {', '.join(user.interests)})")

    start_time = time.time()
    programs = get_programs_from_db(categories=user.interests)
    db_time = time.time() - start_time

    if not programs:
        print("[ERROR] 프로그램이 없습니다. 크롤러를 먼저 실행해주세요.")
        return

    print(f"[OK] 총 {len(programs)}개 프로그램 조회 완료 (소요 시간: {db_time:.2f}초)")

    # 3. 추천 실행
    print("\n[3단계] 추천 실행 중...")
    recommender = HybridRecommender()

    start_time = time.time()
    recommendations = recommender.recommend(
        user=user,
        programs=programs,
        limit=5,
        include_closed=False,
        min_score=15.0
    )
    recommend_time = time.time() - start_time

    # 4. 결과 출력
    print(f"\n{'=' * 80}")
    print(f"  추천 결과: 총 {len(recommendations)}개 (소요 시간: {recommend_time:.2f}초)")
    print(f"  전체 소요 시간: {db_time + recommend_time:.2f}초")
    print(f"{'=' * 80}\n")

    if not recommendations:
        print("[ERROR] 추천할 프로그램이 없습니다.")
        print("   - min_score를 낮춰보세요 (현재: 15.0)")
        print("   - 또는 관심사를 더 추가해보세요")
        return

    for idx, rec in enumerate(recommendations, 1):
        program = rec.program
        score = rec.score

        print(f"[{idx}] {program.title}")
        print(f"    점수: {score:.1f}점")
        print(f"    카테고리: {', '.join(program.categories)}")
        print(f"    대상 학과: {', '.join(program.departments[:3]) if program.departments else '전체'}")
        print(f"    대상 학년: {', '.join([str(g) for g in program.grades]) if program.grades else '전체'}")

        if program.app_end_date:
            days_left = (program.app_end_date - date.today()).days
            print(f"    신청 마감: {program.app_end_date}")

        print(f"    링크: {program.link}")
        print()



if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n중단됨")
    except Exception as e:
        print(f"\n오류 발생: {e}")
        import traceback
        traceback.print_exc()
