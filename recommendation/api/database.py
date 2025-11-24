"""
데이터베이스 연결 및 쿼리 함수
"""

import os
from typing import List, Optional

from fastapi import HTTPException
import mysql.connector
from mysql.connector import pooling, Error
from dotenv import load_dotenv

from ..models import Program

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

# 커넥션 풀 생성 (서버 시작 시 한 번만)
try:
    connection_pool = pooling.MySQLConnectionPool(
        pool_name="recommendation_pool",
        pool_size=5,  # 동시 연결 5개 유지
        pool_reset_session=True,
        **DB_CONFIG
    )
    print("[INFO] 커넥션 풀 생성 완료 (pool_size=5)")
except Error as e:
    print(f"[ERROR] 커넥션 풀 생성 실패: {e}")
    connection_pool = None


def get_db_connection():
    """커넥션 풀에서 연결 가져오기"""
    try:
        if connection_pool:
            connection = connection_pool.get_connection()
            if connection.is_connected():
                return connection
        # 풀이 없으면 직접 연결 (fallback)
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"MySQL 연결 실패: {e}")
        return None


def fetch_programs_from_db(
    departments: Optional[List[str]] = None,
    grade: Optional[int] = None,
    categories: Optional[List[str]] = None,
    include_closed: bool = False
) -> List[Program]:
    """
    DB에서 프로그램 조회

    Args:
        departments: 학과 필터 (선택, 최대 2개)
        grade: 학년 필터 (선택)
        categories: 카테고리 필터 (선택)
        include_closed: 마감된 프로그램 포함 여부

    Returns:
        프로그램 목록
    """
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cursor = connection.cursor(dictionary=True)

        # 기본 쿼리
        query = """
            SELECT DISTINCT
                p.id,
                p.title,
                p.link,
                p.content,
                p.app_start_date,
                p.app_end_date
            FROM program p
            WHERE 1=1
        """

        params = []

        # 마감 필터
        if not include_closed:
            query += " AND p.app_end_date IS NOT NULL AND p.app_end_date >= CURDATE()"

        # 학과 필터 (옵션, 복수 학과 지원)
        if departments and len(departments) > 0:
            dept_placeholders = ', '.join(['%s'] * len(departments))
            query += f"""
                AND (
                    EXISTS (
                        SELECT 1 FROM program_department pd
                        WHERE pd.program_id = p.id
                        AND pd.department IN ({dept_placeholders})
                    )
                    OR EXISTS (
                        SELECT 1 FROM program_department pd
                        WHERE pd.program_id = p.id
                        AND pd.department = '제한없음'
                    )
                )
            """
            params.extend(departments)

        # 학년 필터 (옵션)
        if grade is not None:
            query += """
                AND (
                    EXISTS (
                        SELECT 1 FROM program_grade pg
                        WHERE pg.program_id = p.id
                        AND pg.grade = %s
                    )
                    OR EXISTS (
                        SELECT 1 FROM program_grade pg
                        WHERE pg.program_id = p.id
                        AND pg.grade = 0
                    )
                )
            """
            params.append(grade)

        # 카테고리 필터 (옵션)
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

        # 최신순 정렬
        query += " ORDER BY p.id DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        if not rows:
            cursor.close()
            connection.close()
            return []

        # 프로그램 ID 목록
        program_ids = [row['id'] for row in rows]
        placeholders = ','.join(['%s'] * len(program_ids))

        # 카테고리 일괄 조회
        cursor.execute(
            f"SELECT program_id, category FROM program_category WHERE program_id IN ({placeholders})",
            program_ids
        )
        categories_map = {}
        for r in cursor.fetchall():
            pid = r['program_id']
            if pid not in categories_map:
                categories_map[pid] = []
            categories_map[pid].append(r['category'])

        # 학과 일괄 조회
        cursor.execute(
            f"SELECT program_id, department FROM program_department WHERE program_id IN ({placeholders})",
            program_ids
        )
        departments_map = {}
        for r in cursor.fetchall():
            pid = r['program_id']
            if pid not in departments_map:
                departments_map[pid] = []
            departments_map[pid].append(r['department'])

        # 학년 일괄 조회
        cursor.execute(
            f"SELECT program_id, grade FROM program_grade WHERE program_id IN ({placeholders})",
            program_ids
        )
        grades_map = {}
        for r in cursor.fetchall():
            pid = r['program_id']
            if pid not in grades_map:
                grades_map[pid] = []
            grades_map[pid].append(r['grade'])

        # 프로그램 객체 생성
        programs = []
        for row in rows:
            program_id = row['id']
            programs.append(
                Program(
                    id=program_id,
                    title=row['title'],
                    link=row['link'],
                    content=row['content'] or '',
                    categories=categories_map.get(program_id, []),
                    departments=departments_map.get(program_id, []),
                    grades=grades_map.get(program_id, []),
                    app_start_date=row['app_start_date'],
                    app_end_date=row['app_end_date'],
                    posted_date=None
                )
            )

        cursor.close()
        connection.close()

        return programs

    except Error as e:
        if connection:
            connection.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
