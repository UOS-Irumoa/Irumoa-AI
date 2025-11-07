# src/uosai/crawler/uostory_crawler_with_cookie.py
"""
UOS Story 비교과 프로그램 크롤러
- 브라우저 쿠키를 사용하여 로그인 상태 유지
"""

import time
import re
import json
import random
import os
from typing import List, Optional
from urllib.parse import urlencode
from datetime import datetime
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from PIL import Image
import numpy as np
import easyocr
from openai import OpenAI

# =========================
# 설정
# =========================

BASE_URL = "https://uostory.uos.ac.kr"
LIST_URL = f"{BASE_URL}/site/reservation/lecture/lectureList"
DETAIL_URL = f"{BASE_URL}/site/reservation/lecture/lectureDetail"
COOKIE_FILE = "uostory_cookies.json"

# 여러 메뉴에서 프로그램 수집 (중복 제거)
PROGRAM_MENUS = [
    {
        "name": "비교과 프로그램",
        "menuid": "001003002001",
        "submode": "lecture",
        "reservegroupid": "1",
        "rectype": "L"
    },
    {
        "name": "취업 프로그램",
        "menuid": "001002002002",
        "reservegroupid": "1",
        "rectype": "J"
    }
]

REQUEST_SLEEP_MIN = 5.0  # 최소 대기 시간 (초)
REQUEST_SLEEP_MAX = 10.0  # 최대 대기 시간 (초)
RECENT_WINDOW_PER_MENU = 50  # 각 메뉴별 수집할 프로그램 개수
MAX_PAGES = 10  # 최대 페이지 수
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 20

# =========================
# OpenAI API 초기화
# =========================
from dotenv import load_dotenv
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️ WARNING: OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
    print("OCR 텍스트 정리 기능이 비활성화됩니다.")
    OPENAI_CLIENT = None
else:
    OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI API 초기화 완료")

# =========================
# EasyOCR 초기화
# =========================
# 전역으로 한 번만 초기화 (한글, 영어 지원)
log_print = lambda msg: print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")
log_print("🔧 EasyOCR 초기화 중... (최초 실행 시 모델 다운로드)")
OCR_READER = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
log_print("✅ EasyOCR 초기화 완료")

# 쿠키 로드 (cookies.json 파일에서)
COOKIE_FILE_PATH = "cookies.json"

if not os.path.exists(COOKIE_FILE_PATH):
    print(f"ERROR: 쿠키 파일이 없습니다: {COOKIE_FILE_PATH}")
    print("cookies.json 파일을 생성해주세요.")
    exit(1)

try:
    with open(COOKIE_FILE_PATH, 'r', encoding='utf-8') as f:
        RAW_COOKIES = json.load(f)
    print(f"쿠키 로드 완료: {len(RAW_COOKIES)}개")
except json.JSONDecodeError as e:
    print(f"ERROR: 쿠키 JSON 파싱 실패: {e}")
    print(f"{COOKIE_FILE_PATH} 파일이 올바른 JSON 형식인지 확인해주세요.")
    exit(1)
except Exception as e:
    print(f"ERROR: 쿠키 파일 읽기 실패: {e}")
    exit(1)

# requests용 쿠키 딕셔너리 생성
COOKIES = {cookie['name']: cookie['value'] for cookie in RAW_COOKIES}

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
    # 1. 단일 줄바꿈을 공백으로 (문장 연결)
    text = re.sub(r'([^\n])\n([^\n])', r'\1 \2', text)

    # 2. 연속된 줄바꿈을 최대 2개로 (문단 구분)
    text = re.sub(r'\n{2,}', '\n\n', text)

    # 3. 앞뒤 공백 제거
    text = text.strip()

    return text


def classify_program_categories(title: str, content: str) -> List[str]:
    """프로그램 제목과 내용을 기반으로 카테고리 자동 분류 (다중 선택 가능)"""
    text = (title + " " + content).lower()
    categories = []

    # 카테고리별 키워드 패턴
    patterns = {
        "공모전": r"공모전|경진대회|대회|콘테스트|contest|competition",
        "멘토링": r"멘토링|멘토|멘티|코칭|상담",
        "봉사": r"봉사|자원봉사|사회공헌|volunteer",
        "취업": r"취업|채용|면접|이력서|자기소개서|커리어|인턴|job|career|employment|입사",
        "탐방": r"탐방|견학|방문|투어|답사|field.?trip",
        "특강": r"특강|강연|세미나|워크샵|교육|lecture|seminar|workshop",
    }

    # 각 카테고리별로 매칭 확인 (여러 개 가능)
    for category, pattern in patterns.items():
        if re.search(pattern, text):
            categories.append(category)

    # 매칭되는 것이 없으면 기타
    if not categories:
        categories.append("기타")

    log(f"✅ 카테고리 분류: {', '.join(categories)}")
    return categories


def clean_ocr_text_with_ai(ocr_text: str) -> Optional[str]:
    """OpenAI API로 OCR 텍스트 정리 및 구조화"""
    if not OPENAI_CLIENT:
        log("⚠️ OpenAI API 미설정 - 원본 텍스트 반환")
        return ocr_text

    try:
        log(f"🤖 AI로 텍스트 정리 중... ({len(ocr_text)} 글자)")

        prompt = f"""다음은 포스터에서 OCR로 추출한 텍스트입니다.
오타와 띄어쓰기를 수정하고, 핵심 정보를 구조화된 형태로 정리해주세요.

가능한 정보를 추출하여 다음 형식으로 작성:
- 행사명/프로그램명: (있으면 작성)
- 일시: (있으면 작성)
- 장소: (있으면 작성)
- 강사/주제: (있으면 작성)
- 신청방법: (있으면 작성)
- 문의처: (있으면 작성)
- 기타 내용: (위에 포함되지 않은 중요 정보)

없는 항목은 생략하고, 있는 정보만 간결하게 정리해주세요.


OCR 텍스트:
{ocr_text}
"""

        response = OPENAI_CLIENT.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 OCR 텍스트를 정리하는 전문가입니다. 오타를 수정하고 정보를 구조화합니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )

        cleaned_text = response.choices[0].message.content.strip()
        log(f"✅ AI 정리 완료: {len(cleaned_text)} 글자")
        return cleaned_text

    except Exception as e:
        log(f"❌ AI 정리 실패: {e}")
        log("원본 OCR 텍스트를 반환합니다")
        return ocr_text


def extract_text_from_image(image_url: str) -> Optional[str]:
    """이미지 URL에서 OCR로 텍스트 추출"""
    try:
        log(f"🖼️  이미지 OCR 시작: {image_url}")

        # 이미지 다운로드
        response = requests.get(
            image_url,
            headers=get_headers(),
            cookies=COOKIES,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
        )

        if response.status_code != 200:
            log(f"❌ 이미지 다운로드 실패: HTTP {response.status_code}")
            return None

        # PIL Image로 변환
        image = Image.open(BytesIO(response.content))

        # RGB로 변환 (RGBA 등의 경우 대비)
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # numpy array로 변환
        image_np = np.array(image)

        # OCR 실행
        log(f"🔍 OCR 실행 중...")
        results = OCR_READER.readtext(image_np)

        # 결과 텍스트 추출 (신뢰도 0.3 이상만)
        extracted_lines = []
        for (bbox, text, confidence) in results:
            if confidence > 0.3:
                extracted_lines.append(text)

        extracted_text = '\n'.join(extracted_lines)

        log(f"✅ OCR 완료: {len(extracted_lines)}개 텍스트 라인 추출")
        return extracted_text.strip()

    except Exception as e:
        log(f"❌ OCR 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def parse_departments(dept_text: str) -> list:
    """학과 텍스트를 파싱하여 학과 리스트 반환"""
    if not dept_text:
        return ['제한없음']

    # "학년" 키워드가 있으면 학과 부분만 추출
    # 예: "제한없음학년 : 대학원생" → "제한없음"만 추출
    dept_only = re.split(r'학년', dept_text)[0].strip()

    # 쉼표나 / 로 구분된 학과들을 분리
    departments = re.split(r'[,/]', dept_only)

    result = []
    for dept in departments:
        dept = dept.strip()
        # 불필요한 키워드 제거
        dept = re.sub(r'[:：\s]+$', '', dept)  # 끝의 콜론, 공백 제거

        if dept and dept not in ['제한없음', '']:
            result.append(dept)

    return result if result else ['제한없음']


def parse_grades(grade_text: str) -> list:
    """학년 텍스트를 파싱하여 학년 코드 리스트 반환

    매핑:
    - 0: 제한없음/전체
    - 1~5: 1~5학년
    - 6: 졸업생
    - 7: 대학원생
    """
    if not grade_text:
        return [0]

    grades = []

    # 숫자 학년 추출 (1학년, 2학년 등)
    numeric_grades = re.findall(r'(\d+)학년', grade_text)
    for g in numeric_grades:
        grade_num = int(g)
        if 1 <= grade_num <= 5:
            grades.append(grade_num)

    # 졸업생 체크
    if re.search(r'졸업생?', grade_text):
        grades.append(6)

    # 대학원생 체크
    if re.search(r'대학원생?', grade_text):
        grades.append(7)

    # 제한없음/전체 체크
    if re.search(r'제한\s*없음|전체', grade_text) or not grades:
        return [0]

    return grades


def print_db_insert_info(data: dict) -> None:
    """DB 스키마에 맞게 저장될 데이터를 콘솔에 출력"""
    print("\n" + "="*100)
    print("📊 DB 저장 데이터 (콘솔 출력)")
    print("="*100)

    # 학과 파싱
    departments = parse_departments(data.get('target_department', ''))

    # 학년 파싱 (int 코드: 0=전체, 1-5=학년, 6=졸업생, 7=대학원)
    grades = parse_grades(data.get('target_grade', ''))

    # 카테고리
    categories = data.get('categories', ['기타'])

    # DB 저장용 데이터 구조 (ID는 자동 생성)
    db_data = {
        "title": data['title'],
        "category": categories,  # 배열
        "link": data.get('link', ''),
        "department": departments,  # 배열
        "grade": grades,  # 배열 (int 코드)
        "content": data.get('content', ''),
        "app_start_date": data.get('application_start'),
        "app_end_date": data.get('application_end')
    }

    print("\n[콘솔 출력 - JSON 형식]")
    print(json.dumps(db_data, ensure_ascii=False, indent=2))

    print("\n" + "="*100)
    print()


def print_program_info(data: dict) -> None:
    print("\n" + "="*80)
    print(f"프로그램 ID: {data['program_id']}")
    print(f"제목: {data['title']}")
    print(f"링크: {data.get('link', '')}")
    print("-"*80)

    if data.get('categories'):
        print(f"카테고리: {', '.join(data['categories'])}")
    elif data.get('category'):
        print(f"카테고리: {data['category']}")
    if data.get('target_department'):
        print(f"대상학과: {data['target_department']}")
    if data.get('target_grade'):
        print(f"대상학년: {data['target_grade']}")
    if data.get('selection_method'):
        print(f"선발방식: {data['selection_method']}")
    if data.get('capacity'):
        print(f"모집인원: {data['capacity']}명")
    if data.get('location'):
        print(f"장소: {data['location']}")

    print("-"*80)

    if data.get('application_start'):
        print(f"신청 시작: {data['application_start']}")
    if data.get('application_end'):
        print(f"신청 마감: {data['application_end']}")
    if data.get('operation_start'):
        print(f"운영 시작: {data['operation_start']}")
    if data.get('operation_end'):
        print(f"운영 마감: {data['operation_end']}")
    if data.get('status'):
        print(f"상태: {data['status']}")

    print("-"*80)

    if data.get('content'):
        cleaned = clean_content(data['content'])
        print(f"내용:\n{cleaned}")

    print("="*80 + "\n")


# =========================
# 목록 수집
# =========================

def extract_program_ids_from_html(html: str) -> List[int]:
    soup = BeautifulSoup(html, "html.parser")
    program_ids = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "lectureDetail" in href and "lecturegroupid" in href:
            match = re.search(r"lecturegroupid[=](\d+)", href)
            if match:
                program_ids.append(int(match.group(1)))

    seen = set()
    result = []
    for pid in program_ids:
        if pid not in seen:
            seen.add(pid)
            result.append(pid)

    return result


def collect_program_ids(limit_per_menu: int = RECENT_WINDOW_PER_MENU, max_pages: int = MAX_PAGES) -> List[int]:
    """여러 메뉴에서 프로그램 ID 수집 (각 메뉴별로 limit_per_menu개씩)"""
    all_program_ids = []
    global_seen = set()  # 전역 중복 체크

    # 각 메뉴별로 크롤링
    for menu in PROGRAM_MENUS:
        log(f"\n{'='*60}")
        log(f"[{menu['name']}] 메뉴 크롤링 시작 (목표: {limit_per_menu}개)")
        log(f"{'='*60}")

        menu_program_ids = []  # 이 메뉴에서 수집한 ID들

        for page in range(1, max_pages + 1):
            try:
                log(f"[{menu['name']}] 페이지 {page} 요청 중...")

                # 페이지별 파라미터
                params = menu.copy()
                params.pop('name')  # name은 파라미터가 아님
                params["currentpage"] = str(page)
                params["viewtype"] = "L"
                params["thumbnail"] = "Y"

                response = requests.get(
                    LIST_URL,
                    params=params,
                    headers=get_headers(),
                    cookies=COOKIES,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                    allow_redirects=True
                )

                if response.status_code != 200:
                    log(f"❌ 페이지 {page} HTTP {response.status_code}")
                    break

                if "login" in response.url.lower() or "sso" in response.url.lower():
                    log("⚠️ 로그인 필요 - 쿠키를 확인하세요")
                    break

                page_program_ids = extract_program_ids_from_html(response.text)

                # 이 메뉴에서 아직 안 본 프로그램만 추가
                new_count = 0
                duplicate_count = 0
                for pid in page_program_ids:
                    if pid in global_seen:
                        duplicate_count += 1  # 다른 메뉴에서 이미 수집함
                    elif len(menu_program_ids) < limit_per_menu:
                        menu_program_ids.append(pid)
                        global_seen.add(pid)
                        new_count += 1

                log(f"[{menu['name']}] 페이지 {page}: {len(page_program_ids)}개 발견, "
                    f"{new_count}개 신규, {duplicate_count}개 중복 "
                    f"(메뉴 누적: {len(menu_program_ids)}/{limit_per_menu})")

                # 이 메뉴에서 목표 개수 도달
                if len(menu_program_ids) >= limit_per_menu:
                    log(f"[{menu['name']}] 목표 {limit_per_menu}개 달성 - 다음 메뉴로")
                    break

                # 다음 페이지 요청 전 대기
                if page < max_pages:
                    time.sleep(2)

            except Exception as e:
                log(f"❌ 페이지 {page} 요청 실패: {e}")
                import traceback
                traceback.print_exc()
                break

        # 이 메뉴의 결과를 전체 리스트에 추가
        all_program_ids.extend(menu_program_ids)
        log(f"[{menu['name']}] 최종: {len(menu_program_ids)}개 수집")

    log(f"\n{'='*60}")
    log(f"✅ 전체 메뉴 크롤링 완료: 총 {len(all_program_ids)}개 프로그램 발견")
    log(f"{'='*60}\n")
    return all_program_ids


# =========================
# 상세 페이지 파싱
# =========================

def parse_date_range(text: str) -> tuple[Optional[str], Optional[str]]:
    """날짜 범위 파싱 (시간 포함 가능)

    예: "2025-11-07 10:00:00 ~ 2025-11-14 23:59:00" → ("2025-11-07", "2025-11-14")
    """
    if not text:
        return None, None

    # 패턴 1: 날짜+시간 범위 (YYYY-MM-DD HH:MM:SS ~ YYYY-MM-DD HH:MM:SS)
    match = re.search(r'(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}\s*~\s*(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}', text)
    if match:
        return match.group(1), match.group(2)

    # 패턴 2: 날짜만 범위 (YYYY-MM-DD ~ YYYY-MM-DD)
    match = re.search(r'(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})', text)
    if match:
        return match.group(1), match.group(2)

    # 패턴 3: 단일 날짜+시간 (YYYY-MM-DD HH:MM:SS)
    match = re.search(r'(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}', text)
    if match:
        return match.group(1), match.group(1)

    # 패턴 4: 단일 날짜 (YYYY-MM-DD)
    match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    if match:
        return match.group(1), match.group(1)

    return None, None


def fetch_program_html_with_playwright(program_id: int) -> Optional[str]:
    """Playwright로 자바스크립트 렌더링 후 HTML 가져오기"""
    try:
        params = {
            "menuid": "001003002001",
            "reservegroupid": "1",
            "viewtype": "L",
            "rectype": "L",
            "thumbnail": "Y",
            "lecturegroupid": str(program_id)
        }

        url = f"{DETAIL_URL}?{urlencode(params)}"
        log(f"📡 프로그램 {program_id} Playwright로 요청 중...")

        with sync_playwright() as p:
            # 브라우저 옵션 설정 (봇 감지 우회)
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )

            # 컨텍스트 설정 (일반 브라우저처럼)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='ko-KR',
                timezone_id='Asia/Seoul'
            )

            # 원본 쿠키 그대로 사용 (domain, path, expires 등 모두 포함)
            playwright_cookies = []
            for cookie in RAW_COOKIES:
                playwright_cookie = {
                    "name": cookie['name'],
                    "value": cookie['value'],
                    "domain": cookie.get('domain', '.uos.ac.kr'),
                    "path": cookie.get('path', '/'),
                }

                # expires 있으면 추가
                if 'expires' in cookie and cookie['expires'] != -1:
                    playwright_cookie['expires'] = cookie['expires']

                # httpOnly, secure 플래그
                if 'httpOnly' in cookie:
                    playwright_cookie['httpOnly'] = cookie['httpOnly']
                if 'secure' in cookie:
                    playwright_cookie['secure'] = cookie['secure']

                # sameSite
                if 'sameSite' in cookie:
                    playwright_cookie['sameSite'] = cookie['sameSite']

                playwright_cookies.append(playwright_cookie)

            context.add_cookies(playwright_cookies)
            log(f"🍪 {len(playwright_cookies)}개 쿠키 설정 완료")

            page = context.new_page()

            # 페이지 로드 (더 긴 타임아웃)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # 추가 대기 (자바스크립트 실행 대기)
                page.wait_for_timeout(3000)

                # 로그인 페이지로 리다이렉트 되었는지 확인
                current_url = page.url
                if "login" in current_url.lower() or "sso" in current_url.lower():
                    log(f"⚠️ 로그인 페이지로 리다이렉트됨: {current_url}")
                    log("쿠키가 만료되었을 수 있습니다. uostory_login.py를 다시 실행하세요.")
                    browser.close()
                    return None

            except Exception as e:
                log(f"⚠️ 페이지 로드 타임아웃: {e}")

            # HTML 가져오기
            html = page.content()

            browser.close()

        log(f"✅ 프로그램 {program_id} 로드 성공")
        return html

    except Exception as e:
        log(f"❌ 요청 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def parse_program_fields(html: str, program_id: int) -> Optional[dict]:
    soup = BeautifulSoup(html, "html.parser")

    # 제목 추출 (여러 패턴 시도)
    title = ""

    # 패턴 1: id="lecturetitle" (상세 페이지)
    title_el = soup.select_one("#lecturetitle")
    if title_el:
        title = title_el.get_text(strip=True)

    # 패턴 2: page_title 클래스
    if not title:
        title_el = soup.select_one("h2.page_title") or soup.select_one("h3")
        if title_el:
            title = title_el.get_text(strip=True)

    # 패턴 3: 테이블에서 "과정명" 찾기
    if not title:
        for tr in soup.select("tr"):
            th = tr.select_one("th")
            if th and "과정명" in th.get_text(strip=True):
                td = tr.select_one("td")
                if td:
                    link = td.select_one("a")
                    title = link.get_text(strip=True) if link else td.get_text(strip=True)
                    break

    if not title:
        log(f"⚠️ Program {program_id}: 제목 없음")
        return None

    fields = {}

    # trans_thead 스타일
    for tr in soup.select("tr.trans_thead"):
        th = tr.select_one("th")
        td = tr.select_one("td")
        if not th or not td:
            continue

        th_text = th.get_text(strip=True)
        td_text = td.get_text(strip=True)

        if "대상" in th_text:
            dept_match = re.search(r'학과\s*[:：]\s*([^\n]+)', td_text)
            grade_match = re.search(r'학년\s*[:：]\s*([^\n]+)', td_text)
            fields["target_department"] = dept_match.group(1).strip() if dept_match else None
            fields["target_grade"] = grade_match.group(1).strip() if grade_match else None
        elif "선발방식" in th_text or "선발" in th_text:
            fields["selection_method"] = td_text
        elif "모집인원" in th_text or "인원" in th_text:
            num_match = re.search(r'(\d+)', td_text)
            fields["capacity"] = int(num_match.group(1)) if num_match else None
        elif "장소" in th_text:
            fields["location"] = td_text
        elif "카테고리" in th_text or "핵심역량" in th_text:
            fields["category"] = td_text

    # 일반 테이블
    for tr in soup.select("tr"):
        th = tr.select_one("th")
        td = tr.select_one("td")
        if not th or not td:
            continue

        th_text = th.get_text(strip=True)
        td_text = td.get_text(strip=True)

        if "신청기간" in th_text:
            start, end = parse_date_range(td_text)
            fields["application_start"] = start
            fields["application_end"] = end
        elif "운영기간" in th_text:
            start, end = parse_date_range(td_text)
            fields["operation_start"] = start
            fields["operation_end"] = end
        elif "대상학과" in th_text and "target_department" not in fields:
            fields["target_department"] = td_text
        elif "대상학년" in th_text and "target_grade" not in fields:
            fields["target_grade"] = td_text

    # 본문 찾기: "상세내용" th 다음의 td
    content_el = None
    content = ""

    # "상세내용" th를 찾고 그 다음 tr의 td를 가져오기
    for th in soup.find_all('th'):
        if '상세내용' in th.get_text(strip=True):
            # 상세내용 th가 있는 tr의 다음 tr 찾기
            parent_tr = th.find_parent('tr')
            if parent_tr:
                next_tr = parent_tr.find_next_sibling('tr')
                if next_tr:
                    content_el = next_tr.find('td')
                    break

    # 폴백: "상세내용"을 못 찾으면 기존 방식
    if not content_el:
        content_el = soup.select_one("td[colspan='10']") or soup.select_one("tbody td")

    if content_el:
        content = content_el.get_text("\n", strip=True)

    # 내용 정리
    content = clean_content(content)

    # 🖼️ 본문 내 이미지 찾기 및 OCR 실행
    image_urls = []

    if content_el:
        # "상세내용" 아래 td 안의 모든 이미지 찾기
        for img in content_el.find_all('img'):
            img_src = img.get('src', '')
            if not img_src:
                continue

            # 상대 경로를 절대 경로로 변환
            if img_src.startswith('/'):
                img_url = BASE_URL + img_src
            elif img_src.startswith('http'):
                img_url = img_src
            else:
                img_url = BASE_URL + '/' + img_src

            # 중복 제거
            if img_url not in image_urls:
                image_urls.append(img_url)

    if image_urls:
        log(f"📸 본문 내 이미지 {len(image_urls)}개 발견")

    # 이미지가 있으면 OCR 실행 + AI 정리
    ocr_texts = []
    for idx, img_url in enumerate(image_urls, 1):
        log(f"  [{idx}/{len(image_urls)}] 이미지 OCR 처리 중...")
        ocr_text = extract_text_from_image(img_url)
        if ocr_text:
            # OpenAI API로 텍스트 정리
            cleaned_text = clean_ocr_text_with_ai(ocr_text)
            if cleaned_text:
                ocr_texts.append(f"[이미지 {idx} 정보]\n{cleaned_text}")

    # OCR 결과를 본문에 추가
    if ocr_texts:
        log(f"✅ {len(ocr_texts)}개 이미지에서 텍스트 추출 및 정리 완료")
        content = content + "\n\n" + "\n\n".join(ocr_texts)
        content = clean_content(content)
    elif image_urls:
        log(f"⚠️ 이미지는 있지만 OCR로 추출된 텍스트가 없습니다")

    # 🏷️ 카테고리 자동 분류
    categories = classify_program_categories(title, content)

    # 상태
    status = "모집중"
    if fields.get("application_end"):
        try:
            end_date = datetime.strptime(fields["application_end"], "%Y-%m-%d")
            if end_date < datetime.now():
                status = "마감"
        except:
            pass

    return {
        "program_id": program_id,
        "title": title,
        "categories": categories,  # 다중 카테고리 (리스트)
        "content": content,
        "target_department": fields.get("target_department"),
        "target_grade": fields.get("target_grade"),
        "selection_method": fields.get("selection_method"),
        "capacity": fields.get("capacity"),
        "location": fields.get("location"),
        "application_start": fields.get("application_start"),
        "application_end": fields.get("application_end"),
        "operation_start": fields.get("operation_start"),
        "operation_end": fields.get("operation_end"),
        "status": status,
        "posted_date": datetime.now().strftime("%Y-%m-%d"),
    }


def process_one_program(program_id: int) -> Optional[dict]:
    html = fetch_program_html_with_playwright(program_id)
    if not html:
        return None

    parsed = parse_program_fields(html, program_id)
    if not parsed:
        return None

    params = {
        "menuid": "001003002001",
        "reservegroupid": "1",
        "viewtype": "L",
        "rectype": "L",
        "thumbnail": "Y",
        "lecturegroupid": str(program_id)
    }
    parsed["link"] = f"{DETAIL_URL}?{urlencode(params)}"

    log(f"✅ 파싱 완료: {parsed['title'][:30]}...")
    return parsed


# =========================
# 메인
# =========================

def main():
    log("UOS Story 비교과 프로그램 크롤러")
    print()

    program_ids = collect_program_ids(limit_per_menu=RECENT_WINDOW_PER_MENU)

    if not program_ids:
        log("프로그램을 찾지 못했습니다")
        return 1

    log(f"{len(program_ids)}개 프로그램 처리")
    log(f"ID: {program_ids}")
    print()

    collected = []

    for idx, pid in enumerate(program_ids, 1):
        log(f"[{idx}/{len(program_ids)}] 프로그램 {pid} 처리 중...")

        data = process_one_program(pid)
        if data:
            collected.append(data)
            # 상세 정보 출력
            print_program_info(data)
            # DB 저장용 데이터 출력
            print_db_insert_info(data)

        if idx < len(program_ids):
            sleep_time = random.uniform(REQUEST_SLEEP_MIN, REQUEST_SLEEP_MAX)
            log(f"{sleep_time:.1f}초 대기 중...")
            time.sleep(sleep_time)

    log(f"총 {len(collected)}개 수집 완료")

    output_file = "uostory_programs.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(collected, f, ensure_ascii=False, indent=2)
    log(f"{output_file}에 저장")

    log("완료!")
    return 0


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n⚠️ 중단됨")
        exit(0)
    except Exception as e:
        log(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
