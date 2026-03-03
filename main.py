"""
동국대 이클래스 크롤러 메인 진입점.

사용법:
  python main.py                          # 전체 과목, 전체 데이터
  python main.py --list                   # 수강 과목 목록만 출력
  python main.py --scan                   # 과목별 구조 분석만 실행
  python main.py --course 1 3             # 1번, 3번 과목만 추출
  python main.py --course 자료구조        # 이름에 '자료구조' 포함하는 과목만
  python main.py --only syllabus grades   # 강의계획서, 성적만 추출
  python main.py --download               # 수업자료 파일 다운로드 포함
  python main.py --course 2 --only syllabus --download
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
from scanner import scan_course, CourseScan
from extractors.courses import extract_courses
from extractors.syllabus import extract_syllabus
from extractors.grades import extract_grades
from extractors.attendance import extract_attendance
from extractors.notices import extract_boards
from extractors.assignments import extract_assignments
from extractors.calendar import extract_calendar_events
from extractors.materials import download_materials

OUTPUT_DIR = Path(__file__).parent / "output"
COURSES_DIR = OUTPUT_DIR / "courses"

# 스캔 결과의 feature key -> 추출기 매핑
FEATURE_EXTRACTORS = {
    "syllabus": ("강의계획서", extract_syllabus),
    "grades": ("성적", extract_grades),
    "attendance": ("출석", extract_attendance),
    "boards": ("게시판", extract_boards),
    "activities": ("활동/과제", extract_assignments),
}

# --only 옵션에서 사용 가능한 키 목록
EXTRACTABLE_TYPES = list(FEATURE_EXTRACTORS.keys()) + ["materials"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="동국대 이클래스 크롤러",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python main.py                            전체 추출
  python main.py --list                     과목 목록만 확인
  python main.py --scan                     과목별 구조 분석만
  python main.py --course 1 3               1번, 3번 과목만
  python main.py --course 자료구조          이름 검색
  python main.py --only syllabus grades     특정 데이터만
  python main.py --download                 수업자료 다운로드 포함
  python main.py --course 2 --download      특정 과목 자료 다운로드
  python main.py --no-calendar              캘린더 제외
        """,
    )
    parser.add_argument(
        "--list", action="store_true",
        help="수강 과목 목록만 출력하고 종료",
    )
    parser.add_argument(
        "--scan", action="store_true",
        help="과목별 구조 분석만 실행 (추출 없이 어떤 기능이 있는지 확인)",
    )
    parser.add_argument(
        "--course", nargs="+", metavar="FILTER",
        help="추출할 과목 지정 (번호 또는 이름 키워드, 여러 개 가능)",
    )
    parser.add_argument(
        "--only", nargs="+", metavar="TYPE",
        choices=EXTRACTABLE_TYPES,
        help=f"추출할 데이터 타입 선택: {', '.join(EXTRACTABLE_TYPES)}",
    )
    parser.add_argument(
        "--download", action="store_true",
        help="수업자료 파일 다운로드 포함",
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
    session,
    course: dict,
    scan: CourseScan,
    extract_types: list[str] | None = None,
    do_download: bool = False,
) -> dict:
    """스캔 결과를 기반으로 실제 존재하는 기능만 추출한다."""
    cid = course["id"]
    print(f"\n{'='*50}")
    print(f"  과목: {course['name']} (id={cid})")
    print(f"  발견된 기능: {', '.join(scan.available_keys)}")
    print(f"{'='*50}")

    page = session.page
    result = {
        "id": cid,
        "name": course["name"],
        "professor": course.get("professor", ""),
        "url": course.get("url", ""),
        "scan": scan.to_dict(),
    }

    # --only가 지정되면 그것만, 아니면 스캔에서 발견된 것만 추출
    if extract_types:
        targets = [t for t in extract_types if t in FEATURE_EXTRACTORS]
    else:
        targets = [
            key for key in FEATURE_EXTRACTORS
            if scan.has(key) or key == "activities"  # activities는 항상 추출
        ]

    for key in targets:
        label, extractor_fn = FEATURE_EXTRACTORS[key]
        if not scan.has(key) and key != "activities":
            print(f"  [SKIP] {label}: 이 과목에 없음")
            continue
        try:
            result[key] = await extractor_fn(page, cid)
        except Exception as e:
            print(f"  [에러] {label} 추출 실패 (course={cid}): {e}")
            result[key] = {"_error": str(e)}
        await asyncio.sleep(REQUEST_DELAY)

    # 수업자료 다운로드
    if do_download or (extract_types and "materials" in extract_types):
        try:
            dl_results = await download_materials(
                page, cid, course["name"], scan.downloadable_resources
            )
            result["downloaded_materials"] = dl_results
        except Exception as e:
            print(f"  [에러] 자료 다운로드 실패: {e}")
            result["downloaded_materials"] = {"_error": str(e)}

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

        # --list
        if args.list:
            print("\n  수강 과목 목록:")
            for i, c in enumerate(courses, 1):
                print(f"    {i}. [{c['id']}] {c['name']} ({c.get('professor', '')})")
            print(f"\n  사용법: python main.py --course 1 2 --only syllabus grades")
            return

        # --course 필터링
        if args.course:
            courses = _filter_courses(courses, args.course)
            if not courses:
                print("[에러] 조건에 맞는 과목이 없습니다.")
                return
            print(f"\n[선택] {len(courses)}개 과목:")
            for c in courses:
                print(f"  - {c['name']}")

        # --test
        if args.test:
            courses = courses[:1]
            print(f"\n[테스트 모드] 첫 번째 과목만: {courses[0]['name']}")

        extract_types = args.only or None
        if extract_types:
            labels = [FEATURE_EXTRACTORS[t][0] for t in extract_types if t in FEATURE_EXTRACTORS]
            if "materials" in extract_types:
                labels.append("수업자료 다운로드")
            print(f"[선택] 추출 타입: {', '.join(labels)}")

        # Phase 1: 전체 과목 구조 스캔
        print(f"\n--- Phase 1: 구조 분석 ({len(courses)}개 과목) ---")
        scans: dict[int, CourseScan] = {}
        for course in courses:
            try:
                scan = await scan_course(page, course["id"], course["name"])
                scans[course["id"]] = scan
            except Exception as e:
                print(f"  [에러] 스캔 실패 ({course['name']}): {e}")
            await asyncio.sleep(REQUEST_DELAY)

        # --scan: 스캔 결과만 출력
        if args.scan:
            print(f"\n--- 구조 분석 결과 ---")
            for course in courses:
                scan = scans.get(course["id"])
                if not scan:
                    continue
                print(f"\n  [{course['id']}] {course['name']}")
                print(f"    기능: {', '.join(f.label for f in scan.features)}")
                if scan.boards:
                    print(f"    게시판: {', '.join(b['name'] for b in scan.boards)}")
                if scan.downloadable_resources:
                    print(f"    다운로드 가능: {len(scan.downloadable_resources)}개 자료")

            scan_output = {
                "semester": CURRENT_SEMESTER,
                "scanned_at": datetime.now().isoformat(),
                "courses": {str(cid): s.to_dict() for cid, s in scans.items()},
            }
            scan_path = OUTPUT_DIR / "scan_result.json"
            _save_json(scan_output, scan_path)
            print(f"\n  스캔 결과 저장: {scan_path}")
            return

        # 캘린더
        calendar_events = []
        if not args.no_calendar and session.sesskey:
            try:
                calendar_events = await extract_calendar_events(
                    session.cookies_dict, session.sesskey
                )
            except Exception as e:
                print(f"  [에러] 캘린더 추출 실패: {e}")

        # Phase 2: 스캔 기반 데이터 추출
        print(f"\n--- Phase 2: 데이터 추출 ---")
        course_data = []
        failed = []
        do_download = args.download or (extract_types and "materials" in extract_types)

        for course in courses:
            scan = scans.get(course["id"])
            if not scan:
                failed.append(course["name"])
                continue

            try:
                data = await extract_course_data(
                    session, course, scan, extract_types, do_download
                )
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

        # 통합 JSON
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
        if do_download:
            print(f"  다운로드 폴더: output/downloads/")
        print(f"{'='*60}")

    finally:
        await session.close()


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run(args))
