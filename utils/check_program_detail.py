# check_program_detail.py
"""특정 ID의 프로그램 상세 정보 확인"""

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

if len(sys.argv) < 2:
    print("Usage: python check_program_detail.py <program_id>")
    sys.exit(1)

program_id = int(sys.argv[1])

try:
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    # 프로그램 정보
    cursor.execute("SELECT * FROM program WHERE id = %s", (program_id,))
    prog = cursor.fetchone()

    if not prog:
        print(f"ID {program_id} not found")
        sys.exit(1)

    print("="*80)
    print(f"Program ID: {program_id}")
    print("="*80)
    print(f"\n[Title]")
    print(prog['title'])
    print(f"\n[Link]")
    print(prog['link'])
    print(f"\n[Start Date]")
    print(prog['app_start_date'] or '(None)')
    print(f"\n[End Date]")
    print(prog['app_end_date'] or '(None)')

    # 카테고리
    cursor.execute("SELECT category FROM program_category WHERE program_id = %s", (program_id,))
    categories = [row['category'] for row in cursor.fetchall()]
    print(f"\n[Categories]")
    print(', '.join(categories) if categories else '(None)')

    # 내용 출력 (처음 1000자)
    print(f"\n[Content] (first 1000 chars)")
    content = prog['content'] or ''
    print(content[:1000])
    if len(content) > 1000:
        print(f"\n... (total {len(content)} chars)")

    print("\n" + "="*80)

    cursor.close()
    conn.close()

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
