# check_program_by_id.py
"""특정 ID의 프로그램 데이터 상세 출력"""

import os
import sys
import mysql.connector
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

def get_program_by_id(program_id):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        # 기본 정보
        print("="*80)
        print(f"프로그램 ID: {program_id}")
        print("="*80)

        cursor.execute("SELECT * FROM program WHERE id = %s", (program_id,))
        program = cursor.fetchone()

        if not program:
            print(f"ID {program_id}를 찾을 수 없습니다.")
            return

        print(f"\n제목: {program['title']}")
        print(f"링크: {program['link']}")
        print(f"신청 시작일: {program.get('app_start_date', 'N/A')}")
        print(f"신청 종료일: {program.get('app_end_date', 'N/A')}")

        # 카테고리
        print("\n" + "-"*80)
        print("카테고리:")
        cursor.execute("SELECT category FROM program_category WHERE program_id = %s", (program_id,))
        categories = cursor.fetchall()
        if categories:
            for cat in categories:
                print(f"  - {cat['category']}")
        else:
            print("  (없음)")

        # 학과
        print("\n" + "-"*80)
        print("대상 학과:")
        cursor.execute("SELECT department FROM program_department WHERE program_id = %s", (program_id,))
        departments = cursor.fetchall()
        if departments:
            for dept in departments:
                print(f"  - {dept['department']}")
        else:
            print("  (없음)")

        # 학년
        print("\n" + "-"*80)
        print("대상 학년:")
        cursor.execute("SELECT grade FROM program_grade WHERE program_id = %s", (program_id,))
        grades = cursor.fetchall()
        if grades:
            grade_map = {0: "제한없음", 1: "1학년", 2: "2학년", 3: "3학년", 4: "4학년", 5: "5학년", 6: "졸업생", 7: "대학원생"}
            for g in grades:
                grade_num = g['grade']
                print(f"  - {grade_map.get(grade_num, grade_num)}")
        else:
            print("  (없음)")

        # 내용
        print("\n" + "-"*80)
        print("내용:")
        content = program.get('content', '')
        if content:
            # 처음 500자만 출력
            print(content[:500])
            if len(content) > 500:
                print(f"\n... (총 {len(content)}자, 500자까지 표시)")
        else:
            print("  (없음)")

        print("\n" + "="*80)

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"에러: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python check_program_by_id.py <program_id>")
        print("예시: python check_program_by_id.py 123")
        sys.exit(1)

    program_id = int(sys.argv[1])
    get_program_by_id(program_id)
