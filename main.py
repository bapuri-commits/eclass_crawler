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
  python main.py --obsidian               # 크롤링 후 옵시디언 동기화
"""

import argparse
import asyncio
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Windows cp949 콘솔 한글 깨짐 방지
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

FEATURE_EXTRACTORS = {
    "syllabus": ("강의계획서", extract_syllabus),
    "grades": ("성적", extract_grades),
    "attendance": ("출석", extract_attendance),
    "boards": ("게시판", extract_boards),
    "activities": ("활동/과제", extract_assignments),
}

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
  python main.py --obsidian                옵시디언 동기화 포함
        """,
    )
    parser.add_argument("--list", action="store_true",
                        help="수강 과목 목록만 출력하고 종료")
    parser.add_argument("--scan", action="store_true",
                        help="과목별 구조 분석만 실행 (추출 없이)")
    parser.add_argument("--course", nargs="+", metavar="FILTER",
                        help="추출할 과목 (번호 또는 이름 키워드)")
    parser.add_argument("--only", nargs="+", metavar="TYPE",
                        choices=EXTRACTABLE_TYPES,
                        help=f"추출 데이터 타입: {', '.join(EXTRACTABLE_TYPES)}")
    parser.add_argument("--download", action="store_true",
                        help="수업자료 파일 다운로드 포함")
    parser.add_argument("--no-calendar", action="store_true",
                        help="캘린더 이벤트 추출 건너뛰기")
    parser.add_argument("--test", action="store_true",
                        help="첫 번째 과목만 추출 (테스트)")
    parser.add_argument("--obsidian", action="store_true",
                        help="추출 후 옵시디언 볼트에 마크다운 동기화")
    return parser


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name).strip('_')
    return name[:80]


def _save_json(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _filter_courses(courses: list[dict], filters: list[str]) -> list[dict]:
    selected = []
    for f in filters:
        if f.isdigit():
            idx = int(f) - 1
            if 0 <= idx < len(courses):
                if courses[idx] not in selected:
                    selected.append(courses[idx])
            else:
                print(f"  [경고] 과목 번호 {f}: 범위 초과 (1~{len(courses)})")
        else:
            for c in courses:
                if f.lower() in c["name"].lower() and c not in selected:
                    selected.append(c)
    return selected


def _print_scan_summary(courses: list[dict], scans: dict[int, CourseScan], extract_plan: list[str]):
    """스캔 결과 요약을 출력하고, 각 과목에서 무엇을 추출할지 보여준다."""
    print(f"\n{'='*60}")
    print(f"  스캔 결과 요약 (추출 계획)")
    print(f"{'='*60}")
    for course in courses:
        scan = scans.get(course["id"])
        if not scan:
            print(f"\n  [{course['id']}] {course['name']} - 스캔 실패")
            continue

        will_extract = []
        will_skip = []
        for key in extract_plan:
            if key == "materials":
                if scan.downloadable_resources:
                    will_extract.append(f"자료다운({len(scan.downloadable_resources)})")
                else:
                    will_skip.append("자료다운(없음)")
            elif key in FEATURE_EXTRACTORS:
                label = FEATURE_EXTRACTORS[key][0]
                if scan.has(key) or key == "activities":
                    will_extract.append(label)
                else:
                    will_skip.append(f"{label}(없음)")

        print(f"\n  [{course['id']}] {course['name']}")
        print(f"    추출: {', '.join(will_extract) if will_extract else '없음'}")
        if will_skip:
            print(f"    건너뜀: {', '.join(will_skip)}")
        if scan.boards:
            print(f"    게시판: {', '.join(b['name'] for b in scan.boards)}")
    print(f"{'='*60}")


async def extract_course_data(
    session, course: dict, scan: CourseScan,
    extract_types: list[str] | None = None, do_download: bool = False,
) -> dict:
    """스캔 결과를 기반으로 실제 존재하는 기능만 추출한다."""
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
        "scan": scan.to_dict(),
    }

    # 추출 대상 결정: --only가 있으면 그 중 스캔에서 발견된 것만
    if extract_types:
        targets = [t for t in extract_types if t in FEATURE_EXTRACTORS]
    else:
        targets = list(FEATURE_EXTRACTORS.keys())

    for key in targets:
        label, extractor_fn = FEATURE_EXTRACTORS[key]
        if not scan.has(key) and key != "activities":
            print(f"  [SKIP] {label}: 이 과목에 없음")
            continue
        try:
            if key == "boards":
                result[key] = await extractor_fn(page, cid, scanned_boards=scan.boards)
            else:
                result[key] = await extractor_fn(page, cid)
        except Exception as e:
            print(f"  [에러] {label} 추출 실패 (course={cid}): {e}")
            result[key] = {"_error": str(e)}
        await asyncio.sleep(REQUEST_DELAY)

    if do_download or (extract_types and "materials" in extract_types):
        if scan.downloadable_resources:
            try:
                dl_results = await download_materials(
                    page, cid, course["name"], scan.downloadable_resources
                )
                result["downloaded_materials"] = dl_results
            except Exception as e:
                print(f"  [에러] 자료 다운로드 실패: {e}")
                result["downloaded_materials"] = {"_error": str(e)}
        else:
            print(f"  [SKIP] 수업자료: 다운로드 가능한 리소스 없음")

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

        # --course
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
        do_download = args.download or (extract_types and "materials" in extract_types)

        # ============================================================
        # Phase 1: 구조 분석 (강제)
        # ============================================================
        print(f"\n--- Phase 1: 구조 분석 ({len(courses)}개 과목) ---")
        scans: dict[int, CourseScan] = {}
        for course in courses:
            try:
                scan = await scan_course(page, course["id"], course["name"])
                scans[course["id"]] = scan
            except Exception as e:
                print(f"  [에러] 스캔 실패 ({course['name']}): {e}")
            await asyncio.sleep(REQUEST_DELAY)

        # 스캔 결과 요약 (항상 출력)
        extract_plan = extract_types or (list(FEATURE_EXTRACTORS.keys()) + (["materials"] if do_download else []))
        _print_scan_summary(courses, scans, extract_plan)

        # 스캔 결과 JSON 저장 (항상)
        scan_output = {
            "semester": CURRENT_SEMESTER,
            "scanned_at": datetime.now().isoformat(),
            "courses": {str(cid): s.to_dict() for cid, s in scans.items()},
        }
        _save_json(scan_output, OUTPUT_DIR / "scan_result.json")

        # --scan: 여기서 종료
        if args.scan:
            print(f"\n  스캔 결과 저장: {OUTPUT_DIR / 'scan_result.json'}")
            return

        # ============================================================
        # Phase 2: 스캔 기반 데이터 추출
        # ============================================================
        calendar_events = []
        if not args.no_calendar and session.sesskey:
            try:
                calendar_events = await extract_calendar_events(
                    session.cookies_dict, session.sesskey
                )
            except Exception as e:
                print(f"  [에러] 캘린더 추출 실패: {e}")

        print(f"\n--- Phase 2: 데이터 추출 ---")
        course_data = []
        failed = []

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

        # Phase 3: 옵시디언 동기화 (--obsidian)
        if args.obsidian:
            try:
                from extensions.obsidian_sync import sync
                sync(full_result)
            except Exception as e:
                print(f"  [에러] 옵시디언 동기화 실패: {e}")
                traceback.print_exc()

    finally:
        await session.close()


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run(args))
