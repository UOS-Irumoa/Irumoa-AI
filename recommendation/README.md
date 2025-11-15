# UOS 공지사항 추천 시스템

사용자의 **단과대학, 학과, 학년, 관심사**를 기반으로 맞춤형 공지사항을 추천하는 시스템입니다.

---

## 📋 목차

1. [시스템 개요](#시스템-개요)
2. [점수 체계](#점수-체계)
3. [설치 및 실행](#설치-및-실행)
4. [API 사용법](#api-사용법)
5. [예시 코드](#예시-코드)
6. [파일 구조](#파일-구조)

---

## 🎯 시스템 개요

### 주요 기능

- **규칙 기반 추천**: 사용자 프로필과 프로그램 정보를 매칭하여 점수 계산
- **다중 필터링**: 학과, 학년, 관심사 조합으로 정확한 추천
- **실시간 우선순위**: 마감 임박 프로그램에 보너스 점수 부여
- **설명 가능성**: 각 추천에 대한 상세한 이유 제공
- **REST API**: FastAPI 기반 HTTP 엔드포인트 제공

### 지원 카테고리

```
공모전 | 멘토링 | 봉사 | 취업 | 탐방 | 특강 | 비교과
```

### 학년 코드

```
0: 제한없음
1-5: 1~5학년
6: 졸업생
7: 대학원생
```

---

## 🏆 점수 체계

### 기본 점수 (최대 100점)

| 항목 | 조건 | 점수 |
|-----|------|------|
| **학과 매칭** | 정확히 일치 | 40점 |
| | 제한없음 | 20점 |
| **학년 매칭** | 정확히 일치 | 30점 |
| | 제한없음 | 15점 |
| **관심사 매칭** | 카테고리 1개당 | 10점 (최대 30점) |
| **마감 임박 보너스** | 7일 이내 | 10점 |

### 점수 계산 예시

**사용자**: 컴퓨터과학부 2학년, 관심사: 공모전, 취업

**프로그램 A**: 컴퓨터과학부 대상, 2학년, 카테고리: 공모전, 비교과

```
학과 일치: 40점
학년 일치: 30점
관심사 일치 (공모전): 10점
총점: 80점
```

**프로그램 B**: 제한없음, 1-4학년, 카테고리: 공모전, 취업 (마감 5일 남음)

```
학과 제한없음: 20점
학년 일치: 30점
관심사 일치 (공모전, 취업): 20점
마감 임박 보너스: 10점
총점: 80점
```

---

## 🚀 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일에 DB 연결 정보가 있는지 확인:

```env
DB_HOST=your-db-host
DB_USER=your-db-user
DB_PASSWORD=your-db-password
DB_NAME=uoscholar_db
DB_PORT=3306
```

### 3. API 서버 실행

```bash
# 개발 모드 (자동 리로드)
uvicorn recommendation.api:app --reload --port 8000

# 프로덕션 모드
uvicorn recommendation.api:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4. API 문서 확인

서버 실행 후 브라우저에서:

```
http://localhost:8000/docs
```

Swagger UI로 모든 엔드포인트 테스트 가능합니다.

---

## 📡 API 사용법

### 1. 헬스체크

```bash
GET /health
```

**응답:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-11-14"
}
```

---

### 2. 프로그램 추천

```bash
POST /recommend
```

**요청 바디:**
```json
{
  "user": {
    "department": "컴퓨터과학부",
    "grade": 2,
    "interests": ["공모전", "취업"]
  },
  "limit": 20,
  "include_closed": false,
  "min_score": 20.0
}
```

**파라미터:**
- `user.department` (string, 필수): 학과명
- `user.grade` (int, 필수): 학년 (1-7)
- `user.interests` (array, 필수): 관심 카테고리 목록
- `limit` (int, 선택): 최대 추천 개수 (기본: 20)
- `include_closed` (bool, 선택): 마감된 프로그램 포함 (기본: false)
- `min_score` (float, 선택): 최소 점수 (기본: 20.0)

**응답:**
```json
{
  "recommendations": [
    {
      "program": {
        "id": 123,
        "title": "2025 AI 해커톤 대회",
        "link": "https://www.uos.ac.kr/...",
        "categories": ["공모전", "비교과"],
        "departments": ["컴퓨터과학부"],
        "grades": [1, 2, 3, 4],
        "app_end_date": "2025-11-30"
      },
      "score": 80.0,
      "reasons": [
        "학과 일치: 컴퓨터과학부",
        "학년 일치: 2학년",
        "관심사 일치: 공모전"
      ]
    }
  ],
  "total_count": 15,
  "user": { ... }
}
```

---

### 3. 점수 계산 설명

```bash
POST /explain?program_id=123
```

**요청 바디:**
```json
{
  "department": "컴퓨터과학부",
  "grade": 2,
  "interests": ["공모전", "취업"]
}
```

**응답:**
```json
{
  "program_id": 123,
  "program_title": "2025 AI 해커톤 대회",
  "total_score": 80.0,
  "breakdown": {
    "department": {
      "score": 40.0,
      "reason": "학과 일치: 컴퓨터과학부"
    },
    "grade": {
      "score": 30.0,
      "reason": "학년 일치: 2학년"
    },
    "interests": {
      "score": 10.0,
      "reason": "관심사 일치: 공모전"
    },
    "deadline": {
      "score": 0.0,
      "reason": ""
    }
  }
}
```

---

### 4. 프로그램 목록 조회

```bash
GET /programs?department=컴퓨터과학부&grade=2&category=공모전&limit=20
```

**쿼리 파라미터:**
- `department` (선택): 학과 필터
- `grade` (선택): 학년 필터 (0-7)
- `category` (선택): 카테고리 필터
- `include_closed` (선택): 마감 포함 (기본: false)
- `limit` (선택): 최대 개수 (기본: 50)

**응답:**
```json
{
  "programs": [ ... ],
  "total_count": 15
}
```

---

### 5. 카테고리 목록

```bash
GET /categories
```

**응답:**
```json
{
  "categories": [
    "공모전", "멘토링", "봉사", "취업", "탐방", "특강", "비교과"
  ]
}
```

---

## 💡 예시 코드

### Python 예시

```python
import requests

# 1. 기본 추천
response = requests.post("http://localhost:8000/recommend", json={
    "user": {
        "department": "컴퓨터과학부",
        "grade": 2,
        "interests": ["공모전", "취업"]
    },
    "limit": 10
})

recommendations = response.json()['recommendations']

for rec in recommendations:
    print(f"{rec['score']}점 - {rec['program']['title']}")
    print(f"  이유: {', '.join(rec['reasons'])}\n")
```

### JavaScript 예시

```javascript
// Fetch API 사용
const response = await fetch('http://localhost:8000/recommend', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    user: {
      department: '컴퓨터과학부',
      grade: 2,
      interests: ['공모전', '취업']
    },
    limit: 10
  })
});

const data = await response.json();

data.recommendations.forEach(rec => {
  console.log(`${rec.score}점 - ${rec.program.title}`);
  console.log(`이유: ${rec.reasons.join(', ')}`);
});
```

### cURL 예시

```bash
curl -X POST "http://localhost:8000/recommend" \
  -H "Content-Type: application/json" \
  -d '{
    "user": {
      "department": "컴퓨터과학부",
      "grade": 2,
      "interests": ["공모전", "취업"]
    },
    "limit": 10
  }'
```

---

## 🧪 테스트 실행

내장된 예시 스크립트로 7가지 시나리오 테스트:

```bash
python -m recommendation.example
```

**테스트 시나리오:**
1. 기본 추천 (컴퓨터과학부 2학년)
2. 다중 관심사 (경영학부 3학년)
3. 점수 계산 설명
4. 프로그램 필터링
5. 카테고리 목록 조회
6. 대학원생 추천
7. 낮은 점수 임계값

---

## 📁 파일 구조

```
recommendation/
├── __init__.py           # 패키지 초기화
├── models.py             # 데이터 모델 (Pydantic)
│   ├── User              # 사용자 프로필
│   ├── Program           # 프로그램 정보
│   ├── RecommendationResult
│   ├── RecommendationRequest
│   └── RecommendationResponse
├── rule_based.py         # 규칙 기반 추천 엔진
│   └── RuleBasedRecommender
│       ├── calculate_score()
│       ├── recommend()
│       └── explain_score()
├── api.py                # FastAPI 엔드포인트
│   ├── POST /recommend
│   ├── POST /explain
│   ├── GET /programs
│   ├── GET /categories
│   └── GET /health
├── example.py            # 사용 예시 스크립트
└── README.md             # 이 문서
```

---

## 🔧 커스터마이징

### 점수 가중치 조정

`recommendation/rule_based.py`에서 가중치 수정:

```python
class RuleBasedRecommender:
    WEIGHT_DEPARTMENT_EXACT = 40.0      # 학과 정확 일치
    WEIGHT_DEPARTMENT_UNRESTRICTED = 20.0  # 학과 제한없음
    WEIGHT_GRADE_EXACT = 30.0           # 학년 정확 일치
    WEIGHT_GRADE_UNRESTRICTED = 15.0    # 학년 제한없음
    WEIGHT_INTEREST_PER_MATCH = 10.0    # 관심사 1개당
    BONUS_DEADLINE_NEAR = 10.0          # 마감 임박 보너스
```

### DB 쿼리 최적화

`recommendation/api.py`의 `fetch_programs_from_db()` 함수에서:

```python
# 최대 조회 개수 조정
query += " ORDER BY p.id DESC LIMIT 200"  # 기본: 200개
```

---

## 🚀 다음 단계

### Phase 2: 사용자 행동 수집

```sql
-- 사용자 행동 로깅 테이블 추가
CREATE TABLE user_interactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    program_id INT,
    interaction_type ENUM('view', 'click', 'apply', 'bookmark'),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_program (program_id)
);
```

### Phase 3: 협업 필터링

```python
# 비슷한 사용자 찾기
from sklearn.metrics.pairwise import cosine_similarity

def collaborative_filtering(user_id):
    # User-Item Matrix 생성
    # 비슷한 사용자가 본 프로그램 추천
    ...
```

### Phase 4: ML 모델

```python
# LightGBM으로 클릭률 예측
import lightgbm as lgb

model = lgb.train(params, train_data)
predictions = model.predict(test_data)
```

---

## 📞 문의

- 이슈 제기: GitHub Issues
- 기능 제안: Pull Request

---

## 📄 라이선스

MIT License
