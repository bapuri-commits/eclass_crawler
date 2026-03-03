"""
동국대 이클래스 크롤러 메인 진입점.
로그인 후 모든 수강 과목의 데이터를 JSON으로 추출한다.
"""

import asyncio
import json
import re
import traceback
from datetime import datetime
from pathlib import Path

from browser import create_session
from config import CURRENT_SEMESTER, REQUEST_DELAY
from extractors.courses import extract_courses
from extractors.syllabus import extract_syllabus
from extractors.grades import extract_grades
from extractors.attendance import extract_attendance
from extractors.notices import extract_boards
from extractors.assignments import extract_assignments
from extractors.calendar import extract_calendar_events

OUTPUT_DIR = Path(__file__).parent / "output"
COURSES_DIR = OUTPUT_DIR / "courses"


def _sanitize_filename(name: str) -> str:
    """파일명에 사용할 수 없는 문자를 제거한다."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name).strip('_')
    return name[:80]


def _save_json(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def extract_course_data(session, course: dict) -> dict | None:
    """단일 과목의 모든 데이터를 추출한다. 실패 시 None 반환."""
    cid = course["id"]
    print(f"\n{'='*50}")
    print(f"  과목: {course['name']} (id={cid})")
    print(f"{'='*50}")

    page = session.page
    result = {
        "id": cid,
        "name": course["name"],
        "professor": course.get("professor", ""),
        "url": course.get("url", ""),
    }

    # 각 추출기를 개별 try/except로 감싸서 하나가 실패해도 나머지는 계속 진행
    extractors = [
        ("syllabus", lambda: extract_syllabus(page, cid)),
        ("grades", lambda: extract_grades(page, cid)),
        ("attendance", lambda: extract_attendance(page, cid)),
        ("boards", lambda: extract_boards(page, cid)),
        ("activities", lambda: extract_assignments(page, cid)),
    ]

    for key, extractor in extractors:
        try:
            result[key] = await extractor()
        except Exception as e:
            print(f"  [에러] {key} 추출 실패 (course={cid}): {e}")
            result[key] = {"_error": str(e)}
        await asyncio.sleep(REQUEST_DELAY)

    return result


async def run(test_mode: bool = False):
    """전체 추출 파이프라인을 실행한다."""
    print("=" * 60)
    print(f"  동국대 이클래스 크롤러 - {CURRENT_SEMESTER}")
    print("=" * 60)

    session = await create_session(headless=True)
    page = session.page

    try:
        courses = await extract_courses(page)
        if not courses:
            print("[에러] 수강 과목을 찾지 못했습니다.")
            return

        if test_mode:
            courses = courses[:1]
            print(f"\n[테스트 모드] 첫 번째 과목만 추출: {courses[0]['name']}")

        # 캘린더 이벤트 (AJAX API, 전체 과목 공통)
        calendar_events = []
        if session.sesskey:
            try:
                calendar_events = await extract_calendar_events(
                    session.cookies_dict, session.sesskey
                )
            except Exception as e:
                print(f"  [에러] 캘린더 추출 실패: {e}")

        # 과목별 데이터 추출
        course_data = []
        failed = []

        for course in courses:
            try:
                data = await extract_course_data(session, course)
                if data:
                    course_data.append(data)

                    # 과목별 개별 JSON 저장
                    filename = f"{_sanitize_filename(data['name'])}.json"
                    course_output = {
                        "semester": CURRENT_SEMESTER,
                        "extracted_at": datetime.now().isoformat(),
                        **data,
                    }
                    _save_json(course_output, COURSES_DIR / filename)
                    print(f"  -> 저장: courses/{filename}")

            except Exception as e:
                print(f"  [에러] 과목 추출 실패 ({course['name']}): {e}")
                traceback.print_exc()
                failed.append(course["name"])

        # 전체 통합 JSON 저장
        full_result = {
            "semester": CURRENT_SEMESTER,
            "extracted_at": datetime.now().isoformat(),
            "course_count": len(course_data),
            "failed_courses": failed,
            "calendar_events": calendar_events,
            "courses": course_data,
        }

        OUTPUT_DIR.mkdir(exist_ok=True)
        full_path = OUTPUT_DIR / f"{CURRENT_SEMESTER}_semester.json"
        _save_json(full_result, full_path)

        print(f"\n{'='*60}")
        print(f"  완료!")
        print(f"  성공: {len(course_data)}개 과목")
        if failed:
            print(f"  실패: {len(failed)}개 과목 ({', '.join(failed)})")
        print(f"  통합 JSON: {full_path}")
        print(f"  과목별 JSON: {COURSES_DIR}/")
        print(f"  캘린더 이벤트: {len(calendar_events)}개")
        print(f"{'='*60}")

    finally:
        await session.close()


if __name__ == "__main__":
    import sys
    test = "--test" in sys.argv
    asyncio.run(run(test_mode=test))
