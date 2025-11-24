"""
DB에 있는 모든 프로그램의 카테고리를 재분류하는 스크립트
"""
import os
import re
from typing import List
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# MySQL DB 설정
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', ''),
    'port': int(os.getenv('DB_PORT', 3306)),
    'charset': 'utf8mb4',
    'use_pure': True,  # 순수 Python 구현 사용
}


def classify_program_categories(title: str, content: str) -> List[str]:
    """프로그램 제목과 내용을 기반으로 카테고리 자동 분류 (개선된 버전)"""
    title_lower = title.lower()
    content_lower = content.lower()
    categories = []

    # 카테고리별 키워드 패턴 (우선순위 순서)
    # 제목에서 먼저 확인하고, 내용은 보조적으로만 사용
    patterns = {
        "비교과": r"비교과",
        "공모전": r"공모전|경진대회|콘테스트|contest|competition",
        "멘토링": r"멘토링",  # "멘토링"만 명시적으로 매칭
        "봉사": r"봉사|자원봉사|사회공헌|volunteer",
        "취업": r"취업",  # "취업"만 명시적으로 매칭
        "탐방": r"탐방|견학|답사|field.?trip",
        "특강": r"특강|강연|세미나|워크샵|lecture|seminar|workshop",
    }

    # 1단계: 제목에서 명확한 카테고리 찾기 (우선순위)
    for category, pattern in patterns.items():
        if re.search(pattern, title_lower):
            categories.append(category)

    # 2단계: 제목에서 못 찾았으면 내용에서 찾기 (보조)
    if not categories:
        for category, pattern in patterns.items():
            if re.search(pattern, content_lower):
                categories.append(category)

    # 3단계: 여전히 없으면 "비교과"로 기본 분류
    if not categories:
        categories.append("비교과")

    # 중복 제거
    categories = list(dict.fromkeys(categories))

    return categories


def update_all_categories():
    """DB의 모든 프로그램 카테고리 업데이트"""
    try:
        # DB 연결
        print("DB 연결 중...")
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        # 모든 프로그램 조회
        print("프로그램 목록 조회 중...")
        cursor.execute("""
            SELECT id, title, content
            FROM program
            ORDER BY id
        """)
        programs = cursor.fetchall()

        print(f"총 {len(programs)}개 프로그램 발견\n")

        updated_count = 0
        error_count = 0

        for program in programs:
            program_id = program['id']
            title = program['title'] or ''
            content = program['content'] or ''

            try:
                # 기존 카테고리 조회
                cursor.execute("""
                    SELECT category
                    FROM program_category
                    WHERE program_id = %s
                """, (program_id,))
                old_categories = [row['category'] for row in cursor.fetchall()]

                # 새 카테고리 분류
                new_categories = classify_program_categories(title, content)

                # 카테고리가 변경되었는지 확인
                old_set = set(old_categories)
                new_set = set(new_categories)

                if old_set != new_set:
                    # 기존 카테고리 삭제
                    cursor.execute("""
                        DELETE FROM program_category
                        WHERE program_id = %s
                    """, (program_id,))

                    # 새 카테고리 삽입
                    for category in new_categories:
                        cursor.execute("""
                            INSERT INTO program_category (program_id, category)
                            VALUES (%s, %s)
                        """, (program_id, category))

                    connection.commit()

                    print(f"✅ ID {program_id}: {title[:50]}...")
                    print(f"   기존: {', '.join(old_categories) if old_categories else '(없음)'}")
                    print(f"   변경: {', '.join(new_categories)}")
                    print()

                    updated_count += 1
                else:
                    # 변경 없음 (조용히 스킵)
                    pass

            except Error as e:
                print(f"❌ ID {program_id} 업데이트 실패: {e}")
                error_count += 1
                connection.rollback()

        cursor.close()
        connection.close()

        print("=" * 60)
        print(f"완료!")
        print(f"- 총 프로그램: {len(programs)}개")
        print(f"- 업데이트됨: {updated_count}개")
        print(f"- 오류: {error_count}개")
        print(f"- 변경 없음: {len(programs) - updated_count - error_count}개")

    except Error as e:
        print(f"DB 오류: {e}")
        return


if __name__ == "__main__":
    print("=" * 60)
    print("프로그램 카테고리 일괄 업데이트 스크립트")
    print("=" * 60)
    print()

    # 사용자 확인
    response = input("모든 프로그램의 카테고리를 재분류하시겠습니까? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("취소되었습니다.")
        exit(0)

    print()
    update_all_categories()
