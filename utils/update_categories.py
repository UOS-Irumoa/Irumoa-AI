# update_categories.py
"""
기존 DB 데이터의 제목/내용을 재분석하여 누락된 카테고리 추가
"""

import os
import re
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', ''),
    'port': int(os.getenv('DB_PORT', 3306)),
    'charset': os.getenv('DB_CHARSET', 'utf8mb4'),
    'use_pure': True,
}

# 카테고리 패턴 (크롤러와 동일)
CATEGORY_PATTERNS = {
    "비교과": r"비교과",
    "공모전": r"공모전|경진대회|대회|콘테스트|contest|competition",
    "멘토링": r"멘토링|멘토|멘티|코칭|상담",
    "봉사": r"봉사|자원봉사|사회공헌|volunteer",
    "취업": r"취업|채용|면접|이력서|자기소개서|커리어|인턴|job|career|employment|입사",
    "탐방": r"탐방|견학|방문|투어|답사|field.?trip",
    "특강": r"특강|강연|세미나|워크샵|교육|lecture|seminar|workshop",
}

DRY_RUN = False  # True: 테스트 모드, False: 실제 실행


def classify_categories(title: str, content: str):
    """제목과 내용에서 카테고리 추출"""
    text = (title + " " + (content or "")).lower()
    categories = []

    for category, pattern in CATEGORY_PATTERNS.items():
        if re.search(pattern, text):
            categories.append(category)

    return categories


def get_existing_categories(cursor, program_id):
    """프로그램의 기존 카테고리 조회"""
    cursor.execute(
        "SELECT category FROM program_category WHERE program_id = %s",
        (program_id,)
    )
    return {row['category'] for row in cursor.fetchall()}


def main():
    print("="*80)
    print("기존 데이터 카테고리 재분석 및 업데이트")
    print("="*80)
    print(f"\n모드: {'DRY-RUN (테스트)' if DRY_RUN else '실제 실행'}")

    if not DRY_RUN:
        print("\n⚠️ 경고: 실제 실행 모드입니다!")
        response = input("계속하시겠습니까? (yes/no): ")
        if response.lower() != 'yes':
            print("취소됨")
            return

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        # 모든 프로그램 가져오기
        print("\n[1/3] 프로그램 데이터 로드 중...")
        cursor.execute("SELECT id, title, content FROM program ORDER BY id")
        programs = cursor.fetchall()
        print(f"총 {len(programs)}개 프로그램 로드 완료")

        # 각 프로그램 분석
        print("\n[2/3] 카테고리 재분석 중...")

        update_count = 0
        skip_count = 0

        for prog in programs:
            program_id = prog['id']
            title = prog['title']
            content = prog['content']

            # 현재 카테고리
            existing_categories = get_existing_categories(cursor, program_id)

            # 재분석된 카테고리
            analyzed_categories = set(classify_categories(title, content))

            # 추가할 카테고리 (기존에 없는 것만)
            missing_categories = analyzed_categories - existing_categories

            if missing_categories:
                print(f"\n프로그램 ID {program_id}: {title[:50]}...")
                print(f"  기존 카테고리: {', '.join(existing_categories) or '(없음)'}")
                print(f"  추가할 카테고리: {', '.join(missing_categories)}")

                if not DRY_RUN:
                    # 실제 추가
                    for category in missing_categories:
                        cursor.execute(
                            "INSERT INTO program_category (program_id, category) VALUES (%s, %s)",
                            (program_id, category)
                        )
                    conn.commit()
                    print(f"  ✅ 추가 완료")
                else:
                    print(f"  [DRY-RUN] 추가 예정")

                update_count += 1
            else:
                skip_count += 1

        # 통계
        print(f"\n[3/3] 완료!")
        print("="*80)
        print(f"총 처리: {len(programs)}개")
        print(f"카테고리 추가: {update_count}개")
        print(f"변경 없음: {skip_count}개")
        print("="*80)

        if DRY_RUN:
            print("\n💡 DRY-RUN 모드였습니다.")
            print("   실제로 추가하려면 스크립트 상단의 DRY_RUN = False로 변경하세요.")

        cursor.close()
        conn.close()

    except Error as e:
        print(f"\n❌ 에러: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨")
        exit(0)
