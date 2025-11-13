# check_recent_inserts.py
"""최근 삽입된 프로그램 확인"""

import os
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

try:
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    # 최근 삽입된 프로그램 10개 확인
    query = """
    SELECT id, title, link
    FROM program
    ORDER BY id DESC
    LIMIT 10
    """

    cursor.execute(query)
    programs = cursor.fetchall()

    print("="*60)
    print("최근 삽입된 프로그램 (최신 10개)")
    print("="*60)

    for prog in programs:
        print(f"ID: {prog['id']}")
        print(f"제목: {prog['title'][:50]}...")
        print(f"링크: {prog['link'][:60]}...")
        print("-"*60)

    cursor.close()
    conn.close()

except Exception as e:
    print(f"에러: {e}")
    import traceback
    traceback.print_exc()
