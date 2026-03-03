"""
동국대 이클래스 크롤러 메인 진입점.

사용법:
  python main.py                          # 전체 과목, 전체 데이터
  python main.py --list                   # 수강 과목 목록만 출력
  python main.py --course 1 3             # 1번, 3번 과목만 추출
  python main.py --course 자료구조        # 이름에 '자료구조' 포함하는 과목만
  python main.py --only syllabus grades   # 강의계획서, 성적만 추출
  python main.py --course 2 --only syllabus attendance
  python main.py --test                   # 첫 과목만 추출 (테스트)
"""

import argparse
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

ALL_EXTRACTORS = {
    "syllabus": ("강의계획서", extract_syllabus),
    "grades": ("성적", extract_grades),
    "attendance": ("출석", extract_attendance),
    "boards": ("게시판", extract_boards),
    "activities": ("활동/과제", extract_assignments),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="동국대 이클래스 크롤러",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python main.py                            전체 추출
  python main.py --list                     과목 목록만 확인
  python main.py --course 1 3               1번, 3번 과목만
  python main.py --course 자료구조          이름 검색
  python main.py --only syllabus grades     특정 데이터만
  python main.py --course 2 --only syllabus 조합 가능
  python main.py --no-calendar              캘린더 제외
        """,
    )
    parser.add_argument(
        "--list", action="store_true",
        help="수강 과목 목록만 출력하고 종료",
    )
    parser.add_argument(
        "--course", nargs="+", metavar="FILTER",
        help="추출할 과목 지정 (번호 또는 이름 키워드, 여러 개 가능)",
    )
    parser.add_argument(
        "--only", nargs="+", metavar="TYPE",
        choices=list(ALL_EXTRACTORS.keys()),
        help=f"추출할 데이터 타입 선택: {', '.join(ALL_EXTRACTORS.keys())}",
    )
    parser.add_argument(
        "--no-calendar", action="store_true",
        help="캘린더 이벤트 추출 건너뛰기",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="첫 번째 과목만 추출 (테스트)",
    )
    return parser


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name).strip('_')
    return name[:80]


def _save_json(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _filter_courses(courses: list[dict], filters: list[str]) -> list[dict]:
    """번호(1-based) 또는 이름 키워드로 과목을 필터링한다."""
    selected = []
    for f in filters:
        if f.isdigit():
            idx = int(f) - 1
            if 0 <= idx < len(courses):
                if courses[idx] not in selected:
                    selected.append(courses[idx])
            else:
                print(f"  [경고] 과목 번호 {f}이(가) 범위를 벗어남 (1~{len(courses)})")
        else:
            for c in courses:
                if f.lower() in c["name"].lower() and c not in selected:
                    selected.append(c)
    return selected


async def extract_course_data(
    session, course: dict, extract_types: list[str] | None = None,
) -> dict:
    """단일 과목의 데이터를 추출한다."""
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

    targets = extract_types or list(ALL_EXTRACTORS.keys())

    for key in targets:
        if key not in ALL_EXTRACTORS:
            continue
        label, extractor_fn = ALL_EXTRACTORS[key]
        try:
            result[key] = await extractor_fn(page, cid)
        except Exception as e:
            print(f"  [에러] {label} 추출 실패 (course={cid}): {e}")
            result[key] = {"_error": str(e)}
        await asyncio.sleep(REQUEST_DELAY)

    return result


async def run(args):
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

        # --list: 과목 목록만 출력
        if args.list:
            print("\n  수강 과목 목록:")
            for i, c in enumerate(courses, 1):
                print(f"    {i}. [{c['id']}] {c['name']} ({c.get('professor', '')})")
            print(f"\n  사용법: python main.py --course {' '.join(str(i+1) for i in range(min(2, len(courses))))} --only syllabus grades")
            return

        # --course: 과목 필터링
        if args.course:
            courses = _filter_courses(courses, args.course)
            if not courses:
                print("[에러] 조건에 맞는 과목이 없습니다.")
                return
            print(f"\n[선택] {len(courses)}개 과목:")
            for c in courses:
                print(f"  - {c['name']}")

        # --test: 첫 과목만
        if args.test:
            courses = courses[:1]
            print(f"\n[테스트 모드] 첫 번째 과목만: {courses[0]['name']}")

        # 추출 대상 타입
        extract_types = args.only or None
        if extract_types:
            labels = [ALL_EXTRACTORS[t][0] for t in extract_types]
            print(f"[선택] 추출 타입: {', '.join(labels)}")

        # 캘린더 이벤트
        calendar_events = []
        if not args.no_calendar and session.sesskey:
            try:
                calendar_events = await extract_calendar_events(
                    session.cookies_dict, session.sesskey
                )
            except Exception as e:
                print(f"  [에러] 캘린더 추출 실패: {e}")

        # 과목별 추출
        course_data = []
        failed = []

        for course in courses:
            try:
                data = await extract_course_data(session, course, extract_types)
                course_data.append(data)

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

        # 통합 JSON 저장
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
            print(f"  실패: {len(failed)}개 ({', '.join(failed)})")
        print(f"  통합 JSON: {full_path}")
        print(f"  과목별 JSON: {COURSES_DIR}/")
        if calendar_events:
            print(f"  캘린더 이벤트: {len(calendar_events)}개")
        print(f"{'='*60}")

    finally:
        await session.close()


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run(args))
