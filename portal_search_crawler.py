# portal_search_crawler.py
"""
서울시립대 포털 공지사항 검색 기반 크롤러
- 일반공지(FA1)에서 카테고리별 검색어로 크롤링
- 각 검색어(공모전, 특강, 봉사 등)별로 50개씩 수집
- link 기준으로 중복 체크 (제목 기준 병합은 별도 스크립트에서)
"""

import time
import re
import json
import random
import os
from typing import List, Optional, Dict
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import mysql.connector
from mysql.connector import Error
from io import BytesIO
from PIL import Image
import numpy as np
import easyocr
from playwright.sync_api import sync_playwright

# =========================
# 설정
# =========================

BASE_URL = "https://www.uos.ac.kr"
LIST_URL = f"{BASE_URL}/korNotice/list.do"
VIEW_URL = f"{BASE_URL}/korNotice/view.do"

# 검색 카테고리 정의 (검색어 = 카테고리)
SEARCH_CATEGORIES = [
    {"name": "공모전", "keyword": "공모"},
    {"name": "특강", "keyword": "특강"},
    {"name": "봉사", "keyword": "봉사"},
    {"name": "취업", "keyword": "취업"},
    {"name": "탐방", "keyword": "탐방"},
    {"name": "멘토링", "keyword": "멘토링"}
]

REQUEST_SLEEP_MIN = 4.0  # 최소 대기 시간 (초) - 증가
REQUEST_SLEEP_MAX = 7.0  # 최대 대기 시간 (초) - 증가
NOTICES_PER_CATEGORY = 25  # 각 카테고리별 수집할 공지 개수
MAX_PAGES = 10  # 최대 페이지 수
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 20

# 테스트 모드: 각 카테고리별로 랜덤 샘플링할 개수 (None이면 전체 크롤링)
# TEST_RANDOM_SAMPLE = 3  # 테스트용: 각 카테고리별로 랜덤 3개만
TEST_RANDOM_SAMPLE = None  # 실제 운영: 전체 크롤링

# =========================
# 환경 변수 로드
# =========================
from dotenv import load_dotenv
load_dotenv()

# OpenAI API 초기화
from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print(" OPENAI_API_KEY 확인하세요.")
    print("LLM 정보 추출 기능이 비활성화됩니다.")
    OPENAI_CLIENT = None
else:
    OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)
    print(" OpenAI API 초기화 완료")

# =========================
# EasyOCR 초기화
# =========================
log_print = lambda msg: print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")
log_print("EasyOCR 초기화 중... (최초 실행 시 모델 다운로드)")
OCR_READER = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
log_print("EasyOCR 초기화 완료")

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

# =========================
# 유틸리티
# =========================

def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")


def get_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": BASE_URL,
    }


def clean_content(text: str) -> str:
    """내용 정리: 과도한 줄바꿈 제거 및 문단 정리"""
    if not text:
        return ""

    # 연속된 공백/탭을 하나의 공백으로
    text = re.sub(r'[ \t]+', ' ', text)

    # 줄바꿈 정리
    text = re.sub(r'([^\n])\n([^\n])', r'\1 \2', text)
    text = re.sub(r'\n{2,}', '\n\n', text)
    text = text.strip()

    return text


def classify_program_categories(title: str, content: str) -> List[str]:
    """프로그램 제목과 내용을 기반으로 카테고리 자동 분류 (다중 선택 가능)"""
    text = (title + " " + content).lower()
    categories = []

    # 카테고리별 키워드 패턴
    patterns = {
        "공모전": r"공모전|콘테스트|contest",
        "멘토링": r"멘토링|멘토|멘티",
        "봉사": r"봉사|자원봉사|volunteer",
        "취업": r"취업|채용|면접|커리어|인턴|job|career|employment|입사",
        "탐방": r"탐방|견학|투어|답사|field.?trip",
        "특강": r"특강|강연|세미나|워크샵|seminar|workshop",
    }

    # 각 카테고리별로 매칭 확인 (여러 개 가능)
    for category, pattern in patterns.items():
        if re.search(pattern, text):
            categories.append(category)

    # 매칭되는 것이 없으면 기타
    if not categories:
        categories.append("기타")

    log(f"    ✅ 카테고리 분류: {', '.join(categories)}")
    return categories


def clean_and_extract_with_llm(title: str, raw_content: str) -> dict:
    """
    LLM을 사용해서 공지사항 내용을 정리하고 프로그램 정보 추출

    Returns:
        {
            'cleaned_content': str,    # 정리된 본문 내용
            'target_department': str,  # "제한없음" 또는 "컴퓨터과학부, 전자공학과"
            'target_grade': str,       # "제한없음" 또는 "1학년, 2학년"
            'application_start': str,  # "2025-11-01" 또는 None
            'application_end': str,    # "2025-11-30" 또는 None
            'operation_start': str,    # "2025-12-01" 또는 None
            'operation_end': str,      # "2025-12-15" 또는 None
            'capacity': int,           # 30 또는 None
            'location': str,           # "대강당" 또는 None
            'selection_method': str    # "선착순" 또는 None
        }
    """
    if not OPENAI_CLIENT:
        log(f"    ⚠️ OpenAI API 미설정 - 기본값 사용")
        return {
            'cleaned_content': raw_content,
            'target_department': '제한없음',
            'target_grade': '제한없음',
            'application_start': None,
            'application_end': None,
            'operation_start': None,
            'operation_end': None,
            'capacity': None,
            'location': None,
            'selection_method': None
        }

    try:
        log(f"    LLM으로 내용 정리 및 정보 추출 중...")

        prompt = f"""다음은 대학교 공지사항입니다. 본문과 OCR로 추출된 이미지 텍스트가 섞여있어 맥락이 끊겨있을 수 있습니다.

제목: {title}

원본 내용:
{raw_content[:3000]}  # 처음 3000자만

---
**작업 1: 내용 정리**
- 본문과 이미지 텍스트를 통합하여 맥락있는 하나의 글로 재구성
- 중복 정보는 제거하되, 중요한 정보는 모두 유지
- 오타나 띄어쓰기 오류 수정
- 문단을 논리적으로 정리 (프로그램 개요 → 일정 → 대상 → 신청방법 순서)

**작업 2: 정보 추출** (없으면 null 반환):
1. target_department: 대상 학과 (예: "컴퓨터과학부, 전자공학과" 또는 "제한없음")
2. target_grade: 대상 학년 (예: "1학년, 2학년" 또는 "제한없음")
3. application_start: 신청 시작일 (YYYY-MM-DD 형식)
4. application_end: 신청 마감일 (YYYY-MM-DD 형식)
5. operation_start: 운영/행사 시작일 (YYYY-MM-DD 형식)
6. operation_end: 운영/행사 종료일 (YYYY-MM-DD 형식)
7. capacity: 모집 인원 (숫자만, 예: 30)
8. location: 장소 (예: "대강당", "온라인")
9. selection_method: 선발 방식 (예: "선착순", "심사", "추첨")

**중요:**
- 대상이 명시되지 않으면 "제한없음"
- 날짜는 반드시 YYYY-MM-DD 형식
- JSON 형식으로만 답변

JSON 형식:
{{
    "cleaned_content": "정리된 본문 내용 (모든 중요 정보 포함)",
    "target_department": "제한없음",
    "target_grade": "제한없음",
    "application_start": "2025-11-01",
    "application_end": "2025-11-30",
    "operation_start": null,
    "operation_end": null,
    "capacity": 30,
    "location": "대강당",
    "selection_method": "선착순"
}}
"""

        response = OPENAI_CLIENT.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 대학교 공지사항을 정리하고 정보를 추출하는 전문가입니다. 원본의 정보를 최대한 유지하면서 맥락있게 재구성합니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )

        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)

        log(f"    ✅ LLM 정리 및 정보 추출 완료")

        # None 값을 명시적으로 처리
        return {
            'cleaned_content': result.get('cleaned_content') or raw_content,
            'target_department': result.get('target_department') or '제한없음',
            'target_grade': result.get('target_grade') or '제한없음',
            'application_start': result.get('application_start'),
            'application_end': result.get('application_end'),
            'operation_start': result.get('operation_start'),
            'operation_end': result.get('operation_end'),
            'capacity': result.get('capacity'),
            'location': result.get('location'),
            'selection_method': result.get('selection_method')
        }

    except Exception as e:
        log(f"    ❌ LLM 처리 실패: {e}")
        return {
            'cleaned_content': raw_content,
            'target_department': '제한없음',
            'target_grade': '제한없음',
            'application_start': None,
            'application_end': None,
            'operation_start': None,
            'operation_end': None,
            'capacity': None,
            'location': None,
            'selection_method': None
        }


def extract_text_from_image(image_url: str) -> Optional[str]:
    """이미지 URL에서 OCR로 텍스트 추출"""
    import base64

    try:
        log(f"    이미지 OCR 시작: {image_url[:80]}...")

        # base64 데이터 URI 체크
        if image_url.startswith('data:image'):
            # data:image/png;base64,iVBORw0KG... 형식 처리
            try:
                header, encoded = image_url.split(',', 1)
                image_data = base64.b64decode(encoded)
                log(f"    base64 데이터 URI 디코딩 완료")
            except Exception as e:
                log(f"    base64 디코딩 실패: {e}")
                return None
        else:
            # 일반 URL에서 다운로드
            response = requests.get(
                image_url,
                headers=get_headers(),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
            )

            if response.status_code != 200:
                log(f"    이미지 다운로드 실패: HTTP {response.status_code}")
                return None

            image_data = response.content

        # PIL Image로 변환
        image = Image.open(BytesIO(image_data))

        # RGB로 변환 (RGBA 등의 경우 대비)
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # numpy array로 변환
        image_np = np.array(image)

        # OCR 실행
        log(f"    OCR 실행 중...")
        results = OCR_READER.readtext(image_np)

        # 결과 텍스트 추출 (신뢰도 0.3 이상만)
        extracted_lines = []
        for (bbox, text, confidence) in results:
            if confidence > 0.3:
                extracted_lines.append(text)

        extracted_text = '\n'.join(extracted_lines)

        log(f"    OCR 완료: {len(extracted_lines)}개 텍스트 라인 추출")
        return extracted_text.strip()

    except Exception as e:
        log(f"    OCR 실패: {e}")
        return None


def parse_departments(dept_text: str) -> list:
    """학과 텍스트를 파싱하여 학과 리스트 반환"""
    if not dept_text:
        return ['제한없음']

    dept_only = re.split(r'학년', dept_text)[0].strip()
    departments = re.split(r'[,/]', dept_only)

    result = []
    for dept in departments:
        dept = dept.strip()
        dept = re.sub(r'[:：\s]+$', '', dept)
        if dept and dept not in ['제한없음', '']:
            result.append(dept)

    return result if result else ['제한없음']


def parse_grades(grade_text: str) -> list:
    """학년 텍스트를 파싱하여 학년 코드 리스트 반환 (0: 제한없음, 1-5: 학년, 6: 졸업생, 7: 대학원생)"""
    if not grade_text:
        return [0]

    grades = []
    numeric_grades = re.findall(r'(\d+)학년', grade_text)
    for g in numeric_grades:
        grade_num = int(g)
        if 1 <= grade_num <= 5:
            grades.append(grade_num)

    if re.search(r'졸업생?', grade_text):
        grades.append(6)
    if re.search(r'대학원생?', grade_text):
        grades.append(7)
    if re.search(r'제한\s*없음|전체', grade_text) or not grades:
        return [0]

    return grades


def get_db_connection():
    """MySQL 데이터베이스 연결 생성"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        log(f"MySQL 연결 실패: {e}")
        return None


def insert_program_to_db(data: dict) -> str:
    """
    프로그램 데이터를 DB에 삽입 (기존 sp_create_program 사용)
    Returns: 'success', 'duplicate', 'error'
    """
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        if not connection:
            return 'error'

        cursor = connection.cursor()

        # 중복 체크: link가 이미 존재하는지 확인
        link = data.get('link', '')
        if link:
            check_query = "SELECT id FROM program WHERE link = %s LIMIT 1"
            cursor.execute(check_query, (link,))
            existing = cursor.fetchone()

            if existing:
                existing_id = existing[0]

                # 기존 카테고리 조회
                cursor.execute(
                    "SELECT category FROM program_category WHERE program_id = %s",
                    (existing_id,)
                )
                existing_categories = {row[0] for row in cursor.fetchall()}

                # 새로운 카테고리 파싱
                new_categories = set(data.get('categories', []))

                # 추가할 카테고리 찾기 (기존에 없는 것만)
                categories_to_add = new_categories - existing_categories

                if categories_to_add:
                    # 새 카테고리 추가
                    for category in categories_to_add:
                        cursor.execute(
                            "INSERT INTO program_category (program_id, category) VALUES (%s, %s)",
                            (existing_id, category)
                        )
                    connection.commit()
                    log(f"✅ 카테고리 병합: ID {existing_id} - {data.get('title', '')[:30]}... (+{', '.join(categories_to_add)})")
                    return 'merged'
                else:
                    log(f"⏭ 중복 건너뛰기: {data.get('title', '')[:40]}... (기존 ID: {existing_id})")
                    return 'duplicate'

        # 학과 및 학년 파싱
        departments = parse_departments(data.get('target_department', ''))
        grades = parse_grades(data.get('target_grade', ''))
        categories = data.get('categories', ['기타'])

        # 중복 제거
        departments = list(dict.fromkeys(departments))
        grades = list(dict.fromkeys(grades))
        categories = list(dict.fromkeys(categories))

        # JSON 데이터 생성
        program_data = {
            'title': data.get('title', ''),
            'link': data.get('link', ''),
            'content': data.get('content', ''),
            'categories': categories,
            'departments': departments,
            'grades': grades
        }

        # 날짜 필드가 있으면 추가
        if data.get('posted_date'):
            program_data['app_start_date'] = data.get('posted_date')

        # JSON 문자열로 변환
        json_data = json.dumps(program_data, ensure_ascii=False)

        # Stored Procedure 호출 (OUT 파라미터)
        args = [json_data, 0]
        result_args = cursor.callproc('sp_create_program', args)
        connection.commit()

        # OUT 파라미터에서 program_id 가져오기
        program_id = result_args[1]

        log(f"✅ DB 삽입 성공: {data.get('title', '')[:40]}... (ID: {program_id})")
        return 'success'

    except Error as e:
        log(f"❌ DB 삽입 실패: {e}")
        if connection:
            connection.rollback()
        return 'error'

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# =========================
# 목록 수집
# =========================

def collect_notices_by_search(search_keyword: str, category_name: str, limit: int = NOTICES_PER_CATEGORY) -> List[Dict]:
    """
    검색어로 공지사항 목록 수집

    Args:
        search_keyword: 검색어 (예: "공모전")
        category_name: 카테고리 이름 (예: "공모전")
        limit: 수집할 최대 개수

    Returns:
        [{"title": "...", "seq": "123", "category": "공모전"}, ...]
    """
    notices = []
    page = 1

    log(f"[{category_name}] 검색 시작: '{search_keyword}'")

    while len(notices) < limit and page <= MAX_PAGES:
        try:
            log(f"  페이지 {page} 요청 중...")

            # 검색 파라미터 (실제 URL과 동일하게 구성)
            params = {
                "list_id": "FA1",
                "seq": "0",
                "sort": "",
                "pageIndex": str(page),
                "searchCnd": "1",  # 1=제목 검색
                "searchWrd": search_keyword,
                "cate_id": "",
                "viewAuth": "Y",
                "writeAuth": "Y",  # Y로 변경
                "board_list_num": "10",
                "lpageCount": "12",
                "menuid": "2000005009002000000",
                "identified": "anonymous"  # 익명 접근 필수!
            }

            response = requests.get(
                LIST_URL,
                params=params,
                headers=get_headers(),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
            )

            if response.status_code != 200:
                log(f"  HTTP {response.status_code} 에러")
                break

            soup = BeautifulSoup(response.text, 'html.parser')

            # 게시물 목록 찾기: div.ti > a
            items = soup.select('div.ti > a')

            if not items:
                log(f"  더 이상 게시물 없음")
                break

            page_count = 0
            for item in items:
                if len(notices) >= limit:
                    break

                title = item.get_text(strip=True)
                href = item.get('href', '')

                # javascript:fnView('3', '30005'); 에서 seq 추출
                seq = None
                if 'fnView' in href:
                    match = re.search(r"fnView\(['\"](\d+)['\"]\s*,\s*['\"](\d+)['\"]\)", href)
                    if match:
                        seq = match.group(2)

                if seq and title:
                    # 링크 생성 (상세 페이지 URL)
                    link = f"{VIEW_URL}?identified=anonymous&list_id=FA1&seq={seq}"

                    notices.append({
                        'title': title,
                        'seq': seq,
                        'category': category_name,
                        'link': link
                    })
                    page_count += 1

            log(f"  페이지 {page}: {page_count}개 수집 (누적: {len(notices)}/{limit})")

            if page_count == 0:
                break

            page += 1
            # 요청 간격 늘리기 (차단 방지)
            time.sleep(random.uniform(2, 4))

        except Exception as e:
            log(f"  페이지 {page} 요청 실패: {e}")
            log(f"  10초 대기 후 계속...")
            time.sleep(10)  # 차단 해제 대기
            break  # 이 카테고리는 여기서 중단

    log(f"[{category_name}] 최종 수집: {len(notices)}개")
    return notices


# =========================
# 상세 페이지 파싱
# =========================

def crawl_notice_detail(seq: str, categories: List[str]) -> Optional[Dict]:
    """
    공지사항 상세 페이지 크롤링 (Playwright 사용 - JavaScript 렌더링)

    Args:
        seq: 공지사항 번호
        categories: 이 공지가 속한 카테고리 리스트

    Returns:
        공지사항 데이터 딕셔너리 또는 None
    """
    try:
        url = f"{VIEW_URL}?identified=anonymous&list_id=FA1&seq={seq}"

        log(f"  상세 페이지 요청: seq={seq}")

        # Playwright로 JavaScript 렌더링 후 HTML 가져오기
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )

            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='ko-KR',
                timezone_id='Asia/Seoul'
            )

            page = context.new_page()

            try:
                # 페이지 로드
                page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # JavaScript 실행 대기
                page.wait_for_timeout(3000)

                # HTML 가져오기
                html = page.content()

            except Exception as e:
                log(f"  ⚠️ 페이지 로드 실패: {e}")
                browser.close()
                return None

            browser.close()

        soup = BeautifulSoup(html, 'html.parser')

        # 제목 추출
        title = None
        title_el = soup.select_one('div.vw-tibx h4')
        if title_el:
            title = title_el.get_text(strip=True)

        if not title:
            log(f"  제목 없음 - 건너뜀")
            return None

        # 작성일 및 작성부서 추출
        posted_date = None
        department = None

        spans = soup.select('div.vw-tibx div.da span')
        if len(spans) >= 3:
            department = spans[1].get_text(strip=True)
            date_text = spans[2].get_text(strip=True)
            # "2025-11-12" 형식 추출
            match = re.search(r'(\d{4}-\d{2}-\d{2})', date_text)
            if match:
                posted_date = match.group(1)

        # 본문 추출 (수정: div.vw-con 사용)
        content = ""
        content_el = soup.select_one('div.vw-con')

        # 디버깅: 본문 요소 확인
        if not content_el:
            log(f"  ⚠️ div.vw-con을 찾을 수 없음")
            # 대안 셀렉터 시도
            content_el = soup.select_one('div.view-bx')
            if content_el:
                log(f"  ✓ div.view-bx 사용")

        if content_el:
            content = content_el.get_text("\n", strip=True)
            content = clean_content(content)
            log(f"  본문 길이: {len(content)}글자")
        else:
            log(f"  ⚠️ 본문을 찾을 수 없음")

        # 이미지 URL 추출 (본문 내 이미지)
        image_urls = []
        if content_el:
            for img in content_el.find_all('img'):
                img_src = img.get('src', '')
                if not img_src:
                    continue

                # 상대 경로를 절대 경로로 변환
                if img_src.startswith('http'):
                    img_url = img_src
                elif img_src.startswith('/'):
                    img_url = BASE_URL + img_src
                else:
                    img_url = BASE_URL + '/' + img_src

                # 중복 제거
                if img_url not in image_urls:
                    image_urls.append(img_url)

        # 이미지 OCR 실행
        if image_urls:
            log(f"  본문 내 이미지 {len(image_urls)}개 발견")
            ocr_texts = []
            for idx, img_url in enumerate(image_urls, 1):
                log(f"    [{idx}/{len(image_urls)}] 이미지 OCR 처리 중...")
                ocr_text = extract_text_from_image(img_url)
                if ocr_text:
                    ocr_texts.append(f"[이미지 {idx} 정보]\n{ocr_text}")

            # OCR 결과를 본문에 추가
            if ocr_texts:
                log(f"  {len(ocr_texts)}개 이미지에서 텍스트 추출 완료")
                content = content + "\n\n" + "\n\n".join(ocr_texts)
                content = clean_content(content)
            else:
                log(f"  이미지는 있지만 OCR로 추출된 텍스트가 없습니다")

        # 첨부파일 정보 (있으면 본문에 추가)
        attachments = []
        for file_link in soup.select('a[href*="board-download.do"]'):
            file_name = file_link.get_text(strip=True)
            if file_name and file_name not in attachments:
                attachments.append(file_name)

        if attachments:
            content += "\n\n[첨부파일]\n" + "\n".join(f"- {f}" for f in attachments)

        # LLM으로 내용 정리 및 정보 추출 (UOStory 형식에 맞추기)
        llm_result = clean_and_extract_with_llm(title, content)

        # 정리된 내용 사용
        cleaned_content = llm_result['cleaned_content']

        # 카테고리 자동 분류 (제목 + 정리된 본문 기반, 다중 선택 가능)
        auto_categories = classify_program_categories(title, cleaned_content)

        # 검색 카테고리와 자동 분류 카테고리 병합 (중복 제거)
        combined_categories = list(dict.fromkeys(categories + auto_categories))

        return {
            'title': title,
            'link': url,
            'content': cleaned_content,  # LLM이 정리한 내용 사용
            'categories': combined_categories,  # 병합된 카테고리 리스트
            'posted_date': posted_date,
            'department': department,
            'seq': seq,
            # LLM으로 추출한 정보 추가
            'target_department': llm_result['target_department'],
            'target_grade': llm_result['target_grade'],
            'application_start': llm_result['application_start'],
            'application_end': llm_result['application_end'],
            'operation_start': llm_result['operation_start'],
            'operation_end': llm_result['operation_end'],
            'capacity': llm_result['capacity'],
            'location': llm_result['location'],
            'selection_method': llm_result['selection_method']
        }

    except Exception as e:
        log(f"  상세 페이지 크롤링 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


# =========================
# 메인
# =========================

def print_program_info(data: dict, idx: int) -> None:
    """uostory_crawler와 동일한 형식으로 프로그램 정보 출력 + 프로시저 호출 형식"""
    print("\n" + "="*80)
    print(f"[{idx}] 프로그램 정보")
    print(f"제목: {data['title']}")
    print(f"링크: {data.get('link', '')}")
    print("-"*80)

    # 카테고리 (리스트 형식)
    if data.get('categories'):
        print(f"카테고리: {', '.join(data['categories'])}")

    # 대상 학과 및 학년
    if data.get('target_department'):
        print(f"대상학과: {data['target_department']}")
    if data.get('target_grade'):
        print(f"대상학년: {data['target_grade']}")

    # 선발방식, 모집인원, 장소
    if data.get('selection_method'):
        print(f"선발방식: {data['selection_method']}")
    if data.get('capacity'):
        print(f"모집인원: {data['capacity']}명")
    if data.get('location'):
        print(f"장소: {data['location']}")

    print("-"*80)

    # 날짜 정보
    if data.get('application_start'):
        print(f"신청 시작: {data['application_start']}")
    if data.get('application_end'):
        print(f"신청 마감: {data['application_end']}")
    if data.get('operation_start'):
        print(f"운영 시작: {data['operation_start']}")
    if data.get('operation_end'):
        print(f"운영 마감: {data['operation_end']}")
    if data.get('posted_date'):
        print(f"작성일: {data['posted_date']}")

    print("-"*80)

    # 본문 내용
    if data.get('content'):
        cleaned = clean_content(data['content'])
        print(f"내용:\n{cleaned}")

    print("-"*80)

    # 프로시저 호출 형식 출력
    departments = parse_departments(data.get('target_department', ''))
    grades = parse_grades(data.get('target_grade', ''))

    program_data = {
        'title': data.get('title', ''),
        'link': data.get('link', ''),
        'content': data.get('content', ''),
        'categories': data.get('categories', ['기타']),
        'departments': departments,
        'grades': grades
    }

    # 날짜 필드 추가
    if data.get('application_start'):
        program_data['app_start_date'] = data.get('application_start')
    if data.get('application_end'):
        program_data['app_end_date'] = data.get('application_end')

    # JSON 출력
    json_str = json.dumps(program_data, ensure_ascii=False, indent=2)
    print(f"\n프로시저 호출 형식:")
    print(f"SET @p = '{json_str}';")
    

    print("="*80 + "\n")


def main():
    log("="*60)
    log("서울시립대 포털 공지사항 검색 기반 크롤러")
    log("="*60)
    print()

    all_notices = []
    inserted_count = 0
    duplicate_count = 0
    merged_count = 0
    error_count = 0

    # 각 카테고리별로 검색 및 크롤링
    for category in SEARCH_CATEGORIES:
        log(f"\n{'='*60}")
        log(f"카테고리: [{category['name']}]")
        log(f"{'='*60}")

        # 1. 검색 결과 페이지에서 목록 수집
        notices = collect_notices_by_search(
            search_keyword=category['keyword'],
            category_name=category['name'],
            limit=NOTICES_PER_CATEGORY
        )

        if not notices:
            log(f"[{category['name']}] 검색 결과 없음")
            continue

        # 테스트 모드: 랜덤 샘플링
        if TEST_RANDOM_SAMPLE is not None and len(notices) > TEST_RANDOM_SAMPLE:
            log(f"[테스트 모드] {len(notices)}개 중 랜덤 {TEST_RANDOM_SAMPLE}개 샘플링")
            notices = random.sample(notices, TEST_RANDOM_SAMPLE)
        # 실제 운영 모드: 전체 크롤링
        # notices = notices  # 그대로 사용

        # 2. 각 공지사항 상세 크롤링 및 출력
        for idx, notice in enumerate(notices, 1):
            log(f"\n[{category['name']} {idx}/{len(notices)}] 처리 중...")

            # DB에 이미 있는지 빠른 체크 (OCR/LLM 실행 전)
            link = notice['link']

            # DB 연결해서 체크
            connection = get_db_connection()
            if connection:
                try:
                    cursor = connection.cursor()
                    check_query = "SELECT id FROM program WHERE link = %s LIMIT 1"
                    cursor.execute(check_query, (link,))
                    existing = cursor.fetchone()

                    if existing:
                        log(f"  ⏭ DB에 이미 존재 (ID: {existing[0]}) - 크롤링 건너뛰기")
                        duplicate_count += 1
                        cursor.close()
                        connection.close()
                        continue  # 다음 공지로

                    cursor.close()
                    connection.close()

                except Error as e:
                    log(f"  ⚠️ DB 체크 실패: {e}")
                    if connection:
                        connection.close()

            # 상세 페이지 크롤링 (DB에 없는 것만)
            data = crawl_notice_detail(
                seq=notice['seq'],
                categories=[notice['category']]
            )

            if data:
                all_notices.append(data)

                # uostory_crawler와 동일한 형식으로 상세 정보 출력
                print_program_info(data, len(all_notices))

                # DB 삽입
                result = insert_program_to_db(data)
                if result == 'success':
                    inserted_count += 1
                elif result == 'merged':
                    merged_count += 1
                elif result == 'duplicate':
                    duplicate_count += 1
                elif result == 'error':
                    error_count += 1
            else:
                error_count += 1

            # 다음 요청 전 대기
            if idx < len(notices):
                sleep_time = random.uniform(REQUEST_SLEEP_MIN, REQUEST_SLEEP_MAX)
                log(f"  {sleep_time:.1f}초 대기...")
                time.sleep(sleep_time)

    # 최종 통계 (uostory_crawler와 동일한 형식)
    log(f"\n{'='*60}")
    log(f"크롤링 완료 통계:")
    log(f"  - 총 수집: {len(all_notices)}개")
    log(f"  - DB 삽입: {inserted_count}개")
    log(f"  - 카테고리 병합: {merged_count}개")
    log(f"  - 중복 건너뜀: {duplicate_count}개")
    if error_count > 0:
        log(f"  - 처리 실패: {error_count}개")
    log(f"{'='*60}")

    # JSON 파일로도 저장
    output_file = "portal_notices.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_notices, f, ensure_ascii=False, indent=2)
    log(f"{output_file}에 저장 완료")

    log("\n✅ 완료!")
    return 0


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n중단됨")
        exit(0)
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
