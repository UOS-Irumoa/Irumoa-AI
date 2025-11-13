# deduplicate.py
"""
서로 다른 출처(Portal, UOStory)에서 크롤링된 중복 프로그램 병합 스크립트

- 2단계 중복 판단:
  1) 같은 출처 내부: 제목 완전 일치만 (엄격)
  2) 다른 출처 간: 유사도 80% 이상 (느슨)
- 더 완전한 데이터를 우선적으로 보존
- Dry-run 모드로 안전하게 테스트 가능
"""

import os
import json
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import re

import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# =========================
# 설정
# =========================

load_dotenv()

# MySQL DB 설정
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', ''),
    'port': int(os.getenv('DB_PORT', 3306)),
    'charset': os.getenv('DB_CHARSET', 'utf8mb4'),
    'autocommit': os.getenv('DB_AUTOCOMMIT', 'False') == 'True',
    'use_pure': os.getenv('DB_USE_PURE', 'True') == 'True',
}

# 중복 판단 기준
# 정규화 후 제목이 정확히 일치하는 경우만 중복으로 판단
DRY_RUN = True  # True: 테스트 모드 (실제 삭제 안함), False: 실제 실행

# =========================
# 유틸리티
# =========================

def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")


def normalize_title_strict(title: str) -> str:
    """제목 정규화 (엄격): 대소문자/공백만 정리"""
    # 연속된 공백을 하나로
    title = re.sub(r'\s+', ' ', title)
    # 앞뒤 공백 제거 및 소문자 변환
    return title.strip().lower()


def normalize_title_loose(title: str) -> str:
    """제목 정규화 (느슨): 대괄호, 괄호, 특수문자 제거"""
    # 대괄호 안의 부서명 제거: [창업지원단] → 제거
    title = re.sub(r'\[.*?\]', '', title)
    # 괄호 안의 내용 제거: (마감임박) → 제거
    title = re.sub(r'\(.*?\)', '', title)
    # 특수문자 제거
    title = re.sub(r'[^\w\s가-힣]', '', title)
    # 연속된 공백을 하나로
    title = re.sub(r'\s+', ' ', title)
    # 앞뒤 공백 제거 및 소문자 변환
    return title.strip().lower()


def is_exact_match(title1: str, title2: str) -> bool:
    """두 제목이 정확히 일치하는지 확인 (엄격한 정규화)"""
    norm1 = normalize_title_strict(title1)
    norm2 = normalize_title_strict(title2)
    return norm1 == norm2


def calculate_similarity(title1: str, title2: str) -> float:
    """두 제목의 유사도 계산 (0.0 ~ 1.0)"""
    from difflib import SequenceMatcher

    norm1 = normalize_title_loose(title1)
    norm2 = normalize_title_loose(title2)

    # SequenceMatcher로 유사도 계산
    similarity = SequenceMatcher(None, norm1, norm2).ratio()
    return similarity


def get_source_from_link(link: str) -> str:
    """링크로부터 출처 판별"""
    if not link:
        return "unknown"
    if "uostory.uos.ac.kr" in link:
        return "uostory"
    elif "uos.ac.kr/korNotice" in link:
        return "portal"
    else:
        return "unknown"


def score_program(program: dict) -> int:
    """프로그램의 "완성도" 점수 계산 (높을수록 더 상세한 데이터)"""
    score = 0

    # 제목 길이
    if program.get('title'):
        score += min(len(program['title']), 50)

    # 내용 길이
    if program.get('content'):
        score += min(len(program['content']) // 10, 200)

    # 날짜 필드 완성도
    if program.get('app_start_date'):
        score += 10
    if program.get('app_end_date'):
        score += 10

    # UOStory는 일반적으로 더 상세하므로 보너스
    source = get_source_from_link(program.get('link', ''))
    if source == 'uostory':
        score += 20

    return score


# =========================
# DB 작업
# =========================

def get_db_connection():
    """MySQL 데이터베이스 연결 생성"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            log("[OK] MySQL 연결 성공")
            return connection
    except Error as e:
        log(f"[ERROR] MySQL 연결 실패: {e}")
        return None


def fetch_all_programs() -> List[dict]:
    """DB에서 모든 프로그램 데이터 가져오기"""
    connection = get_db_connection()
    if not connection:
        return []

    try:
        cursor = connection.cursor(dictionary=True)

        query = """
        SELECT
            id, title, link, content,
            app_start_date, app_end_date
        FROM program
        ORDER BY id ASC
        """

        cursor.execute(query)
        programs = cursor.fetchall()

        log(f"[INFO] 총 {len(programs)}개 프로그램 로드 완료")
        return programs

    except Error as e:
        log(f"[ERROR] 데이터 조회 실패: {e}")
        return []

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def delete_program(program_id: int, dry_run: bool = True) -> bool:
    """프로그램 삭제"""
    if dry_run:
        log(f"  [DRY-RUN] 삭제 예정: ID {program_id}")
        return True

    connection = get_db_connection()
    if not connection:
        return False

    try:
        cursor = connection.cursor()

        # 실제 삭제
        query = "DELETE FROM program WHERE id = %s"
        cursor.execute(query, (program_id,))
        connection.commit()

        log(f"  [OK] 삭제 완료: ID {program_id}")
        return True

    except Error as e:
        log(f"  [ERROR] 삭제 실패: {e}")
        if connection:
            connection.rollback()
        return False

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# =========================
# 중복 탐지 및 병합
# =========================

def find_duplicate_groups(programs: List[dict]) -> List[List[dict]]:
    """중복 프로그램 그룹 찾기 (2단계 체크)

    - 같은 출처: 완전 일치만
    - 다른 출처: 유사도 80% 이상
    """
    SIMILARITY_THRESHOLD = 0.80

    log(f"\n{'='*60}")
    log(f"중복 프로그램 탐지 중...")
    log(f"  - 같은 출처 내부: 제목 완전 일치")
    log(f"  - 다른 출처 간: 유사도 {SIMILARITY_THRESHOLD*100}% 이상")
    log(f"{'='*60}")

    duplicate_groups = []
    processed = set()

    for i, prog1 in enumerate(programs):
        if prog1['id'] in processed:
            continue

        # 현재 프로그램과 중복인 것들을 찾기
        group = [prog1]
        processed.add(prog1['id'])
        source1 = get_source_from_link(prog1.get('link', ''))

        for j in range(i + 1, len(programs)):
            prog2 = programs[j]

            if prog2['id'] in processed:
                continue

            source2 = get_source_from_link(prog2.get('link', ''))
            is_duplicate = False

            # 같은 출처끼리: 완전 일치만
            if source1 == source2:
                if is_exact_match(prog1['title'], prog2['title']):
                    is_duplicate = True
                    match_type = "완전 일치"

            # 다른 출처끼리: 유사도 체크
            else:
                similarity = calculate_similarity(prog1['title'], prog2['title'])
                if similarity >= SIMILARITY_THRESHOLD:
                    is_duplicate = True
                    match_type = f"유사도 {similarity*100:.1f}%"

            if is_duplicate:
                group.append(prog2)
                processed.add(prog2['id'])

                log(f"  [DUPLICATE] 중복 발견: ID {prog1['id']} <-> ID {prog2['id']} ({match_type})")
                log(f"     [{source1}] {prog1['title'][:50]}")
                log(f"     [{source2}] {prog2['title'][:50]}")

        # 그룹에 2개 이상 있으면 중복 그룹으로 추가
        if len(group) > 1:
            duplicate_groups.append(group)

    log(f"\n[INFO] 총 {len(duplicate_groups)}개의 중복 그룹 발견")
    return duplicate_groups


def select_best_program(group: List[dict]) -> Tuple[dict, List[dict]]:
    """중복 그룹에서 가장 좋은 프로그램 선택"""
    # 각 프로그램에 점수 부여
    scored = [(prog, score_program(prog)) for prog in group]
    scored.sort(key=lambda x: x[1], reverse=True)

    best_program = scored[0][0]
    duplicates = [prog for prog, _ in scored[1:]]

    return best_program, duplicates


def print_duplicate_report(groups: List[List[dict]]) -> None:
    """중복 현황 리포트 출력"""
    log(f"\n{'='*60}")
    log(f"중복 처리 리포트")
    log(f"{'='*60}\n")

    total_keep = 0
    total_delete = 0

    for idx, group in enumerate(groups, 1):
        best, duplicates = select_best_program(group)

        print(f"{'='*60}")
        print(f"[그룹 {idx}] 총 {len(group)}개 중복")
        print(f"{'='*60}")

        print(f"\n[KEEP] 보존할 프로그램 (점수: {score_program(best)})")
        print(f"   ID: {best['id']}")
        print(f"   출처: {get_source_from_link(best.get('link', ''))}")
        print(f"   제목: {best['title']}")
        print(f"   링크: {best.get('link', '')")
        print(f"   내용 길이: {len(best.get('content', ''))}자")

        print(f"\n[DELETE] 삭제할 프로그램들:")
        for dup in duplicates:
            print(f"   ID: {dup['id']} (점수: {score_program(dup)})")
            print(f"   출처: {get_source_from_link(dup.get('link', ''))}")
            print(f"   제목: {dup['title']}")
            print(f"   링크: {dup.get('link', '')")
            print()

        total_keep += 1
        total_delete += len(duplicates)

    print(f"\n{'='*60}")
    print(f"[SUMMARY] 통계 요약")
    print(f"{'='*60}")
    print(f"총 중복 그룹: {len(groups)}개")
    print(f"보존할 프로그램: {total_keep}개")
    print(f"삭제할 프로그램: {total_delete}개")
    print(f"{'='*60}\n")


def process_duplicates(groups: List[List[dict]], dry_run: bool = True) -> dict:
    """중복 프로그램 처리"""
    stats = {
        'total_groups': len(groups),
        'kept': 0,
        'deleted': 0,
        'failed': 0
    }

    log(f"\n{'='*60}")
    log(f"중복 처리 시작 {'(DRY-RUN 모드 - 실제 삭제 안함)' if dry_run else '(실제 삭제 모드)'}")
    log(f"{'='*60}\n")

    for idx, group in enumerate(groups, 1):
        log(f"[그룹 {idx}/{len(groups)}] 처리 중...")

        best, duplicates = select_best_program(group)

        log(f"  [KEEP] 보존: ID {best['id']} - {best['title'][:40]}...")
        stats['kept'] += 1

        for dup in duplicates:
            log(f"  [DELETE] 삭제: ID {dup['id']} - {dup['title'][:40]}...")

            if delete_program(dup['id'], dry_run=dry_run):
                stats['deleted'] += 1
            else:
                stats['failed'] += 1

    return stats


# =========================
# 메인
# =========================

def main():
    log("="*60)
    log("중복 프로그램 병합 스크립트")
    log("="*60)

    # 설정 출력
    log(f"\n설정:")
    log(f"  - 같은 출처 내부: 제목 완전 일치 (엄격)")
    log(f"  - 다른 출처 간: 유사도 80% 이상 (느슨)")
    log(f"  - 모드: {'DRY-RUN (테스트)' if DRY_RUN else '실제 실행'}")

    if not DRY_RUN:
        log(f"\n[WARNING] 경고: 실제 삭제 모드입니다!")
        log(f"[WARNING] 계속하기 전에 DB 백업을 권장합니다.")
        response = input(f"\n계속하시겠습니까? (yes/no): ")
        if response.lower() != 'yes':
            log("취소됨")
            return 0

    # 1. 모든 프로그램 로드
    programs = fetch_all_programs()

    if not programs:
        log("[ERROR] 프로그램을 찾을 수 없습니다")
        return 1

    # 2. 중복 그룹 찾기
    duplicate_groups = find_duplicate_groups(programs)

    if not duplicate_groups:
        log("\n[OK] 중복 프로그램이 없습니다!")
        return 0

    # 3. 리포트 출력
    print_duplicate_report(duplicate_groups)

    # 4. 중복 처리
    if DRY_RUN:
        log("\n[INFO] DRY-RUN 모드입니다. 실제로 삭제하려면 스크립트 상단의 DRY_RUN = False로 변경하세요.")
    else:
        stats = process_duplicates(duplicate_groups, dry_run=False)

        log(f"\n{'='*60}")
        log(f"처리 완료!")
        log(f"{'='*60}")
        log(f"  - 보존: {stats['kept']}개")
        log(f"  - 삭제: {stats['deleted']}개")
        if stats['failed'] > 0:
            log(f"  - 실패: {stats['failed']}개")
        log(f"{'='*60}")

    # 5. JSON 리포트 저장
    report_file = f"duplicate_report_{datetime.now():%Y%m%d_%H%M%S}.json"
    report_data = {
        'timestamp': datetime.now().isoformat(),
        'settings': {
            'same_source': 'exact_match',
            'different_source': 'similarity_80%',
            'dry_run': DRY_RUN
        },
        'duplicate_groups': [
            {
                'group_id': idx,
                'count': len(group),
                'kept': select_best_program(group)[0]['id'],
                'deleted': [prog['id'] for prog in select_best_program(group)[1]],
                'programs': [
                    {
                        'id': prog['id'],
                        'title': prog['title'],
                        'source': get_source_from_link(prog.get('link', '')),
                        'link': prog.get('link', ''),
                        'score': score_program(prog)
                    }
                    for prog in group
                ]
            }
            for idx, group in enumerate(duplicate_groups, 1)
        ]
    }

    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    log(f"\n[INFO] 상세 리포트가 {report_file}에 저장되었습니다")

    log("\n[OK] 완료!")
    return 0


if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        log("\n중단됨")
        exit(0)
    except Exception as e:
        log(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        exit(1)
