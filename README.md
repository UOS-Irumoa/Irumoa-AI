# Irumoa-AI

서울시립대학교 학생을 위한 **맞춤형 공지사항 추천 시스템**

학생의 학과, 학년, 관심사를 기반으로 공모전, 비교과 프로그램, 특강, 취업 정보 등을 자동으로 수집하고 개인화된 추천을 제공합니다.

---

## 목차

- [주요 기능](#주요-기능)
- [시스템 구조](#시스템-구조)
- [설치 방법](#설치-방법)
- [사용 방법](#사용-방법)
- [프로젝트 구조](#프로젝트-구조)
- [API 문서](#api-문서)
- [개발 가이드](#개발-가이드)

---

## 주요 기능

### 1. 자동 크롤링 시스템
- **포털 공지사항 크롤러** (`portal_search_crawler.py`)
  - 서울시립대 포털 일반공지(FA1)에서 카테고리별 검색
  - 공모전, 특강, 봉사, 취업, 탐방, 멘토링, 비교과 등
  - OCR 기반 이미지 텍스트 추출 (EasyOCR)
  - GPT 기반 날짜 정보 파싱

- **UOStory 크롤러** (`uostory_crawler.py`)
  - 비교과/취업 프로그램 자동 수집
  - 쿠키 기반 로그인 상태 유지
  - 신청 기간, 대상 학과/학년 자동 파싱

### 2. AI 추천 엔진
- **Hybrid 추천 알고리즘** (규칙 기반 60% + TF-IDF 40%)
  - 학과/학년/관심사 정확 매칭
  - 관심분야 텍스트 유사도 계산
  - 최소 점수 필터링 (20점 이상)
  - 상위 5개 프로그램 추천

### 3. 데이터 관리
- **중복 제거** (`deduplicate.py`)
  - 같은 출처: 제목 완전 일치 (엄격)
  - 다른 출처: 유사도 80% 이상 (느슨)
  - Dry-run 모드 지원

- **유틸리티 스크립트** (`utils/`)
  - 프로그램 상세 조회 및 검증
  - 카테고리 일괄 업데이트
  - 날짜 정보 자동 추출 및 업데이트

---

## 시스템 구조

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   크롤러     │────▶│  MySQL DB    │────▶│  추천 API    │
│ (자동 수집)  │     │  (데이터 저장)│     │ (FastAPI)    │
└─────────────┘     └──────────────┘     └──────────────┘
      │                                           │
      ▼                                           ▼
  Portal / UOStory                        맞춤형 추천 결과
  (공지사항)                               (학생별 Top 5)
```

### 데이터베이스 스키마

**program** (프로그램 메타데이터)
- id, title, link, content
- app_start_date, app_end_date
- source (Portal/UOStory)

**program_category** (카테고리)
- program_id, category
- 예: 공모전, 특강, 봉사, 취업 등

**program_department** (대상 학과)
- program_id, department
- 예: 컴퓨터과학부, 경영학부, 제한없음

**program_grade** (대상 학년)
- program_id, grade
- 1-5: 학년, 6: 졸업생, 7: 대학원생, 0: 제한없음

---

## 설치 방법

### 1. 필수 요구사항
- Python 3.8+
- MySQL 8.0+
- OpenAI API Key (날짜 파싱용)

### 2. 설치

```bash
# 저장소 클론
git clone https://github.com/your-org/Irumoa-AI.git
cd Irumoa-AI

# 의존성 설치
pip install -r requirements.txt

# Playwright 브라우저 설치
playwright install chromium
```

### 3. 환경 변수 설정

`.env` 파일 생성:
```bash
# Database
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=irumoa
DB_PORT=3306
DB_CHARSET=utf8mb4

# OpenAI API (크롤러용)
OPENAI_API_KEY=sk-...

# Recommendation API (선택)
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

### 4. 데이터베이스 초기화

```sql
-- MySQL에서 실행
CREATE DATABASE irumoa CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 테이블 생성 (스키마는 별도 SQL 파일 참고)
```

---

## 사용 방법

### 1. 크롤링 실행

#### 포털 공지사항 크롤링
```bash
python crawler/portal_search_crawler.py
```
- 각 카테고리별로 50개씩 수집
- 최대 10페이지까지 탐색
- 4-7초 랜덤 대기 (서버 부하 방지)

#### UOStory 프로그램 크롤링
```bash
# 1. 쿠키 파일 생성 (수동 로그인 필요)
# 2. 크롤러 실행
python crawler/uostory_crawler.py
```
- 비교과/취업 프로그램 수집
- 신청 기간, 학과/학년 정보 자동 파싱

### 2. 데이터 정제

#### 중복 제거
```bash
# Dry-run (실제 삭제 없이 확인만)
python scripts/deduplicate.py

# 실제 실행
python scripts/deduplicate.py --execute
```

#### 날짜 정보 업데이트
```bash
python utils/update_dates_from_content.py
```

#### 카테고리 일괄 업데이트
```bash
python utils/update_categories.py
```

### 3. 추천 API 서버 실행

```bash
# 개발 모드
python recommendation/api/app.py

# 또는
uvicorn recommendation.api.app:app --reload --port 8000
```

서버 주소:
- API: http://localhost:8000
- Swagger 문서: http://localhost:8000/docs
- 헬스체크: http://localhost:8000/health

---

## 프로젝트 구조

```
Irumoa-AI/
├── crawler/                    # 크롤러 모듈
│   ├── portal_search_crawler.py   # 포털 공지사항 크롤러
│   └── uostory_crawler.py         # UOStory 비교과 크롤러
│
├── recommendation/             # 추천 시스템
│   ├── api/                      # FastAPI 서버
│   │   ├── app.py                  # FastAPI 앱
│   │   ├── routes.py               # API 엔드포인트
│   │   └── database.py             # DB 연결 및 쿼리
│   ├── recommenders/             # 추천 알고리즘
│   │   └── hybrid.py               # Hybrid 추천 엔진
│   ├── tests/                    # 테스트
│   │   ├── test_hybrid.py          # 추천 엔진 테스트
│   │   └── test_recommend.py       # API 테스트
│   └── models.py                 # 데이터 모델 (Pydantic)
│
├── scripts/                    # 유틸리티 스크립트
│   └── deduplicate.py            # 중복 제거
│
├── utils/                      # DB 관리 도구
│   ├── check_program_by_id.py    # 프로그램 ID 조회
│   ├── check_program_detail.py   # 프로그램 상세 조회
│   ├── check_recent_inserts.py   # 최근 추가 확인
│   ├── update_categories.py      # 카테고리 업데이트
│   └── update_dates_from_content.py # 날짜 추출 및 업데이트
│
├── .env                        # 환경 변수 (Git 제외)
├── .gitignore                  # Git 제외 파일
├── requirements.txt            # Python 의존성
├── cookies.json                # 크롤러 쿠키 (Git 제외)
└── README.md                   # 프로젝트 문서
```

---

## API 문서

### POST /recommend
사용자 맞춤 프로그램 추천 (최대 5개)

**Request:**
```json
{
  "user": {
    "department": "컴퓨터과학부",
    "grade": 2,
    "interests": ["공모전", "취업"],
    "interest_fields": ["AI", "머신러닝"]
  }
}
```

**Response:**
```json
{
  "content": [
    {
      "id": 1,
      "title": "[대학혁신] AI 해커톤 대회",
      "link": "https://www.uos.ac.kr/korNotice/view.do?seq=12345",
      "content": "AI 주제 해커톤 대회 개최...",
      "appStartDate": "2025-11-01",
      "appEndDate": "2025-11-30",
      "categories": ["공모전", "비교과"],
      "departments": ["컴퓨터과학부"],
      "grades": [1, 2, 3, 4]
    }
  ]
}
```

**점수 체계 (0-100점):**
- 규칙 기반 (60%): 학과 40점 + 학년 30점 + 관심사 최대 30점
- TF-IDF (40%): 관심분야 텍스트 유사도

### GET /health
서버 상태 확인

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-11-18"
}
```

---

## 개발 가이드

### 크롤러 커스터마이징

#### 새로운 카테고리 추가
`crawler/portal_search_crawler.py`:
```python
SEARCH_CATEGORIES = [
    {"name": "공모전", "keyword": "공모"},
    {"name": "새카테고리", "keyword": "검색어"},  # 추가
]
```

#### 수집 개수 조정
```python
NOTICES_PER_CATEGORY = 50  # 기본: 25
MAX_PAGES = 20             # 기본: 10
```

### 추천 알고리즘 튜닝

#### 점수 가중치 조정
`recommendation/recommenders/hybrid.py`:
```python
# 규칙 기반 점수
WEIGHT_DEPARTMENT_EXACT = 40.0       # 학과 정확 일치
WEIGHT_GRADE_EXACT = 30.0            # 학년 정확 일치
WEIGHT_INTEREST_PER_MATCH = 5.0      # 관심사 1개당

# Hybrid 결합 가중치
WEIGHT_RULE_BASED = 0.6  # 규칙 기반 60%
WEIGHT_TF_IDF = 0.4      # TF-IDF 40%
```

#### 최소 점수 조정
`recommendation/api/routes.py`:
```python
recommendations = recommender.recommend(
    user=request.user,
    programs=programs,
    limit=5,
    min_score=20.0  # 조정 가능 (0-100)
)
```

### 테스트 실행

```bash
# 추천 엔진 테스트 (실제 DB 사용)
python -m recommendation.tests.test_hybrid

# API 테스트
python -m recommendation.tests.test_recommend
```

---

## 기술 스택

- **Backend:** Python 3.8+, FastAPI, Uvicorn
- **ML/AI:** scikit-learn (TF-IDF), OpenAI GPT (날짜 파싱)
- **Database:** MySQL 8.0+, mysql-connector-python
- **Web Scraping:** Playwright, BeautifulSoup4, Requests
- **OCR:** EasyOCR, Pillow
- **Validation:** Pydantic

---

## 라이선스

이 프로젝트는 [MIT License](LICENSE) 하에 배포됩니다.

---

## 문의 및 기여

- **이슈 제보:** [GitHub Issues](https://github.com/your-org/Irumoa-AI/issues)
- **기여 방법:** Pull Request 환영합니다
- **문의:** your-email@example.com

---

## 업데이트 내역

### v1.0.0 (2025-11-18)
- 포털 공지사항 크롤러 구현
- UOStory 비교과 프로그램 크롤러 구현
- Hybrid 추천 엔진 (규칙 기반 + TF-IDF)
- FastAPI 기반 REST API 구현
- 중복 제거 및 데이터 정제 스크립트

---

**Made with ❤️ for UOS Students**
