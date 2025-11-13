# update_dates_from_content.py
"""
DB의 content에서 날짜 정보를 추출하여 app_start_date, app_end_date 업데이트
"""

import os
import re
from datetime import datetime
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

DRY_RUN = False # True: 테스트 모드, False: 실제 업데이트


def extract_dates_from_content(content: str) -> dict:
    """
    content에서 신청 시작일/종료일 추출

    Returns:
        {
            'start': 'YYYY-MM-DD' or None,
            'end': 'YYYY-MM-DD' or None
        }
    """
    if not content:
        return {'start': None, 'end': None}

    # 패턴 1: "신청 기간: 2025년 9월 19일(금) 10:00 ~ 2025년 9월 23일(화)"
    # 요일과 시간 포함 가능, ~ 또는 - 구분자
    pattern1 = r'(?:신청|접수|모집)\s*기간[:\s]*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일(?:\s*\([^)]+\))?(?:\s*\d{1,2}:\d{2})?\s*[~\-]\s*(\d{4})?\s*년?\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일'
    match = re.search(pattern1, content, re.IGNORECASE)
    if match:
        start_year = match.group(1)
        start_month = int(match.group(2))
        start_day = int(match.group(3))
        end_year = match.group(4) or start_year  # 종료일에 연도 없으면 시작일 연도 사용
        end_month = int(match.group(5))
        end_day = int(match.group(6))

        start = f"{start_year}-{start_month:02d}-{start_day:02d}"
        end = f"{end_year}-{end_month:02d}-{end_day:02d}"
        return {'start': start, 'end': end}

    # 패턴 2: "신청 기간: 2025-06-19 ~ 2025-07-01" (이미 YYYY-MM-DD 형식)
    pattern2 = r'(?:신청|접수|모집)\s*기간[:\s]*(\d{4}-\d{1,2}-\d{1,2})(?:\s*\d{1,2}:\d{2}:\d{2})?\s*[~\-]\s*(\d{4}-\d{1,2}-\d{1,2})'
    match = re.search(pattern2, content, re.IGNORECASE)
    if match:
        start = normalize_date_format(match.group(1))
        end = normalize_date_format(match.group(2))
        return {'start': start, 'end': end}

    # 패턴 3: "신청 기간: 2025.6.19 ~ 2025.7.1" (점 구분자)
    pattern3 = r'(?:신청|접수|모집)\s*기간[:\s]*(\d{4})\.(\d{1,2})\.(\d{1,2})\s*[~\-]\s*(\d{4})?\.?(\d{1,2})\.(\d{1,2})'
    match = re.search(pattern3, content, re.IGNORECASE)
    if match:
        start_year = match.group(1)
        start_month = int(match.group(2))
        start_day = int(match.group(3))
        end_year = match.group(4) or start_year
        end_month = int(match.group(5))
        end_day = int(match.group(6))

        start = f"{start_year}-{start_month:02d}-{start_day:02d}"
        end = f"{end_year}-{end_month:02d}-{end_day:02d}"
        return {'start': start, 'end': end}

    # 패턴 4: "**신청 기간:**" 형식 (마크다운 볼드)
    pattern4 = r'\*\*(?:신청|접수|모집)\s*기간[:\s]*\*\*\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일(?:\s*\([^)]+\))?(?:\s*\d{1,2}:\d{2})?\s*[~\-]\s*(\d{4})?\s*년?\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일'
    match = re.search(pattern4, content, re.IGNORECASE)
    if match:
        start_year = match.group(1)
        start_month = int(match.group(2))
        start_day = int(match.group(3))
        end_year = match.group(4) or start_year
        end_month = int(match.group(5))
        end_day = int(match.group(6))

        start = f"{start_year}-{start_month:02d}-{start_day:02d}"
        end = f"{end_year}-{end_month:02d}-{end_day:02d}"
        return {'start': start, 'end': end}

    # 패턴 5: 시작일과 종료일이 별도 라인에 있는 경우
    start_match = re.search(
        r'(?:신청|접수)\s*시작[:\s]*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일',
        content,
        re.IGNORECASE
    )
    end_match = re.search(
        r'(?:신청|접수|마감)\s*(?:종료|마감|까지)[:\s]*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일',
        content,
        re.IGNORECASE
    )

    if start_match or end_match:
        start = None
        end = None

        if start_match:
            year, month, day = start_match.groups()
            start = f"{year}-{int(month):02d}-{int(day):02d}"

        if end_match:
            year, month, day = end_match.groups()
            end = f"{year}-{int(month):02d}-{int(day):02d}"

        return {'start': start, 'end': end}

    return {'start': None, 'end': None}


def normalize_date_format(date_str: str) -> str:
    """YYYY-M-D → YYYY-MM-DD 형식으로 변환"""
    match = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', date_str)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return date_str


def main():
    print("="*80)
    print("content에서 날짜 추출하여 업데이트")
    print("="*80)
    print(f"\n모드: {'DRY-RUN (테스트)' if DRY_RUN else '실제 실행'}")

    if not DRY_RUN:
        print("\n[!] 경고: 실제 업데이트 모드입니다!")
        response = input("계속하시겠습니까? (yes/no): ")
        if response.lower() != 'yes':
            print("취소됨")
            return

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        # 모든 프로그램 가져오기
        print("\n[1/3] 프로그램 데이터 로드 중...")
        cursor.execute("SELECT id, title, content, app_start_date, app_end_date FROM program ORDER BY id")
        programs = cursor.fetchall()
        print(f"총 {len(programs)}개 프로그램 로드 완료")

        # 각 프로그램 분석
        print("\n[2/3] 날짜 추출 및 업데이트 중...")

        update_count = 0
        skip_count = 0

        for prog in programs:
            program_id = prog['id']
            title = prog['title']
            content = prog['content']
            current_start = prog['app_start_date']
            current_end = prog['app_end_date']

            # 날짜 추출
            extracted = extract_dates_from_content(content)
            new_start = extracted['start']
            new_end = extracted['end']

            # 변경사항 있는지 확인
            changed = False
            if new_start and new_start != str(current_start):
                changed = True
            if new_end and new_end != str(current_end):
                changed = True

            if changed:
                print(f"\n프로그램 ID {program_id}: {title[:50]}...")
                print(f"  기존: {current_start} ~ {current_end}")
                print(f"  변경: {new_start or current_start} ~ {new_end or current_end}")

                if not DRY_RUN:
                    # 실제 업데이트
                    update_query = "UPDATE program SET "
                    updates = []
                    params = []

                    if new_start:
                        updates.append("app_start_date = %s")
                        params.append(new_start)
                    if new_end:
                        updates.append("app_end_date = %s")
                        params.append(new_end)

                    if updates:
                        update_query += ", ".join(updates) + " WHERE id = %s"
                        params.append(program_id)
                        cursor.execute(update_query, params)
                        conn.commit()
                        print(f"  [OK] 업데이트 완료")
                else:
                    print(f"  [DRY-RUN] 업데이트 예정")

                update_count += 1
            else:
                skip_count += 1

        # 통계
        print(f"\n[3/3] 완료!")
        print("="*80)
        print(f"총 처리: {len(programs)}개")
        print(f"날짜 업데이트: {update_count}개")
        print(f"변경 없음: {skip_count}개")
        print("="*80)

        if DRY_RUN:
            print("\n[i] DRY-RUN 모드였습니다.")
            print("    실제로 업데이트하려면 스크립트 상단의 DRY_RUN = False로 변경하세요.")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨")
        exit(0)
