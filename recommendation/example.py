"""
추천 시스템 사용 예시

이 스크립트는 추천 시스템을 테스트하는 다양한 예시를 제공합니다.
"""

import requests
from datetime import date
from typing import List
import json


# API 서버 URL (로컬 개발 환경)
API_BASE_URL = "http://localhost:8000"


def print_section(title: str):
    """섹션 제목 출력"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_recommendation(rec: dict, index: int):
    """추천 결과 출력"""
    program = rec['program']
    score = rec['score']
    reasons = rec['reasons']

    print(f"\n[{index}] {program['title']}")
    print(f"    점수: {score}점")
    print(f"    카테고리: {', '.join(program['categories'])}")
    print(f"    대상 학과: {', '.join(program['departments'][:3])}{'...' if len(program['departments']) > 3 else ''}")
    print(f"    대상 학년: {', '.join([str(g) for g in program['grades'][:5]])}")

    if program.get('app_end_date'):
        print(f"    신청 마감: {program['app_end_date']}")

    if reasons:
        print(f"    추천 이유:")
        for reason in reasons:
            print(f"      - {reason}")

    print(f"    링크: {program['link'][:80]}...")


def example_1_basic_recommendation():
    """예시 1: 기본 추천"""
    print_section("예시 1: 기본 추천 - 컴퓨터과학부 2학년, 공모전/취업 관심")

    payload = {
        "user": {
            "department": "컴퓨터과학부",
            "grade": 2,
            "interests": ["공모전", "취업"]
        },
        "limit": 10,
        "include_closed": False,
        "min_score": 20.0
    }

    response = requests.post(f"{API_BASE_URL}/recommend", json=payload)

    if response.status_code == 200:
        data = response.json()
        print(f"\n총 {data['total_count']}개 프로그램 추천")

        for idx, rec in enumerate(data['recommendations'], 1):
            print_recommendation(rec, idx)
    else:
        print(f"오류: {response.status_code} - {response.text}")


def example_2_multi_interests():
    """예시 2: 다중 관심사"""
    print_section("예시 2: 다중 관심사 - 경영학부 3학년, 멘토링/특강/봉사 관심")

    payload = {
        "user": {
            "department": "경영학부",
            "grade": 3,
            "interests": ["멘토링", "특강", "봉사"]
        },
        "limit": 10,
        "include_closed": False,
        "min_score": 15.0
    }

    response = requests.post(f"{API_BASE_URL}/recommend", json=payload)

    if response.status_code == 200:
        data = response.json()
        print(f"\n총 {data['total_count']}개 프로그램 추천")

        for idx, rec in enumerate(data['recommendations'][:5], 1):  # 상위 5개만
            print_recommendation(rec, idx)
    else:
        print(f"오류: {response.status_code} - {response.text}")


def example_3_score_explanation():
    """예시 3: 점수 설명"""
    print_section("예시 3: 점수 계산 상세 설명")

    # 먼저 프로그램 목록 조회
    response = requests.get(f"{API_BASE_URL}/programs?limit=1")

    if response.status_code != 200:
        print(f"프로그램 조회 실패: {response.status_code}")
        return

    programs = response.json()['programs']
    if not programs:
        print("프로그램이 없습니다.")
        return

    program_id = programs[0]['id']
    program_title = programs[0]['title']

    print(f"\n대상 프로그램: [{program_id}] {program_title}")

    # 점수 설명 요청
    user_data = {
        "department": "컴퓨터과학부",
        "grade": 2,
        "interests": ["공모전", "취업"]
    }

    response = requests.post(
        f"{API_BASE_URL}/explain?program_id={program_id}",
        json=user_data
    )

    if response.status_code == 200:
        data = response.json()

        print(f"\n총점: {data['total_score']}점")
        print("\n점수 분해:")

        for category, details in data['breakdown'].items():
            if details['score'] > 0:
                print(f"  - {category}: {details['score']}점 ({details['reason']})")
            else:
                print(f"  - {category}: {details['score']}점 (매칭 없음)")
    else:
        print(f"오류: {response.status_code} - {response.text}")


def example_4_filter_programs():
    """예시 4: 프로그램 필터링"""
    print_section("예시 4: 프로그램 필터링 - 공모전 카테고리만")

    response = requests.get(
        f"{API_BASE_URL}/programs",
        params={
            "category": "공모전",
            "limit": 5,
            "include_closed": False
        }
    )

    if response.status_code == 200:
        data = response.json()
        programs = data['programs']

        print(f"\n총 {data['total_count']}개 프로그램")

        for idx, program in enumerate(programs, 1):
            print(f"\n[{idx}] {program['title']}")
            print(f"    카테고리: {', '.join(program['categories'])}")
            print(f"    대상 학과: {', '.join(program['departments'][:3])}")
            if program.get('app_end_date'):
                print(f"    신청 마감: {program['app_end_date']}")
    else:
        print(f"오류: {response.status_code} - {response.text}")


def example_5_list_categories():
    """예시 5: 카테고리 목록 조회"""
    print_section("예시 5: 사용 가능한 카테고리 목록")

    response = requests.get(f"{API_BASE_URL}/categories")

    if response.status_code == 200:
        data = response.json()
        print("\n사용 가능한 카테고리:")
        for idx, category in enumerate(data['categories'], 1):
            print(f"  {idx}. {category}")
    else:
        print(f"오류: {response.status_code} - {response.text}")


def example_6_graduate_student():
    """예시 6: 졸업생/대학원생"""
    print_section("예시 6: 대학원생 추천 - 전자공학과 대학원생, 취업/특강 관심")

    payload = {
        "user": {
            "department": "전자공학과",
            "grade": 7,  # 7: 대학원생
            "interests": ["취업", "특강"]
        },
        "limit": 10,
        "include_closed": False,
        "min_score": 10.0
    }

    response = requests.post(f"{API_BASE_URL}/recommend", json=payload)

    if response.status_code == 200:
        data = response.json()
        print(f"\n총 {data['total_count']}개 프로그램 추천")

        for idx, rec in enumerate(data['recommendations'][:5], 1):  # 상위 5개만
            print_recommendation(rec, idx)
    else:
        print(f"오류: {response.status_code} - {response.text}")


def example_7_low_threshold():
    """예시 7: 낮은 점수 임계값 (더 많은 추천)"""
    print_section("예시 7: 낮은 점수 임계값 - 인문학부 1학년, 봉사 관심")

    payload = {
        "user": {
            "department": "국어국문학과",
            "grade": 1,
            "interests": ["봉사", "탐방"]
        },
        "limit": 15,
        "include_closed": False,
        "min_score": 5.0  # 낮은 임계값
    }

    response = requests.post(f"{API_BASE_URL}/recommend", json=payload)

    if response.status_code == 200:
        data = response.json()
        print(f"\n총 {data['total_count']}개 프로그램 추천")

        # 점수 분포 분석
        scores = [rec['score'] for rec in data['recommendations']]
        if scores:
            print(f"\n점수 통계:")
            print(f"  최고점: {max(scores)}점")
            print(f"  최저점: {min(scores)}점")
            print(f"  평균: {sum(scores) / len(scores):.1f}점")

        for idx, rec in enumerate(data['recommendations'][:5], 1):  # 상위 5개만
            print_recommendation(rec, idx)
    else:
        print(f"오류: {response.status_code} - {response.text}")


def health_check():
    """헬스체크"""
    print_section("API 서버 헬스체크")

    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)

        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ API 서버 정상 작동")
            print(f"   버전: {data['version']}")
            print(f"   시간: {data['timestamp']}")
            return True
        else:
            print(f"\n❌ API 서버 응답 오류: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"\n❌ API 서버 연결 실패: {e}")
        print(f"\n💡 서버를 실행해주세요:")
        print(f"   uvicorn recommendation.api:app --reload --port 8000")
        return False


def main():
    """메인 함수"""
    print("\n" + "=" * 80)
    print("  UOS 공지사항 추천 시스템 - 사용 예시")
    print("=" * 80)

    # 헬스체크
    if not health_check():
        return

    # 예시 실행
    try:
        example_1_basic_recommendation()
        example_2_multi_interests()
        example_3_score_explanation()
        example_4_filter_programs()
        example_5_list_categories()
        example_6_graduate_student()
        example_7_low_threshold()

        print("\n" + "=" * 80)
        print("  모든 예시 완료!")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
