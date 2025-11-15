"""
데이터베이스 연결 및 쿼리 함수
"""

import os
from typing import List, Optional

from fastapi import HTTPException
import mysql.connector
from mysql.connector import Error
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


def get_db_connection():
    """MySQL 데이터베이스 연결"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"MySQL 연결 실패: {e}")
        return None


def fetch_programs_from_db(
    department: Optional[str] = None,
    grade: Optional[int] = None,
    categories: Optional[List[str]] = None,
    include_closed: bool = False
) -> List[Program]:
    """
    DB에서 프로그램 조회

    Args:
        department: 학과 필터 (선택)
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
            query += " AND (p.app_end_date IS NULL OR p.app_end_date >= CURDATE())"

        # 학과 필터 (옵션)
        if department:
            query += """
                AND (
                    EXISTS (
                        SELECT 1 FROM program_department pd
                        WHERE pd.program_id = p.id
                        AND pd.department = %s
                    )
                    OR EXISTS (
                        SELECT 1 FROM program_department pd
                        WHERE pd.program_id = p.id
                        AND pd.department = '제한없음'
                    )
                )
            """
            params.append(department)

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

        # 프로그램별 카테고리, 학과, 학년 조회
        programs = []
        for row in rows:
            program_id = row['id']

            # 카테고리 조회
            cursor.execute(
                "SELECT category FROM program_category WHERE program_id = %s",
                (program_id,)
            )
            categories_result = [r['category'] for r in cursor.fetchall()]

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
                    categories=categories_result,
                    departments=departments,
                    grades=grades,
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
