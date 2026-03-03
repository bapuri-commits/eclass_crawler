"""이클래스 JSON 데이터를 옵시디언 The Record 볼트에 동기화한다.

실행 방법:
  1. 독립 실행:  python -m extensions.obsidian_sync
  2. main.py:    python main.py --obsidian
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sync_config import VAULT_PATH, school_path, sanitize_course_name
from extensions.md_renderer import render_course_note, render_dashboard
from extensions.daily_injector import inject_daily

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def sync(data: dict | None = None, do_daily: bool = True) -> dict:
    """JSON 데이터를 옵시디언 마크다운으로 변환하고 볼트에 저장한다.

    Args:
        data: 통합 semester JSON. None이면 output/ 에서 최신 파일을 읽는다.
        do_daily: True면 데일리 노트에도 마감/일정 주입.

    Returns:
        결과 요약 dict (생성 파일 수, 경로 등)
    """
    if data is None:
        data = _load_latest_json()

    semester = data.get("semester", "")
    courses = data.get("courses", [])
    calendar = data.get("calendar_events", [])

    print(f"\n{'='*50}")
    print(f"  옵시디언 동기화 시작 ({semester})")
    print(f"  볼트: {VAULT_PATH}")
    print(f"{'='*50}")

    if not VAULT_PATH.exists():
        raise FileNotFoundError(f"볼트 경로가 존재하지 않습니다: {VAULT_PATH}")

    target = school_path()
    target.mkdir(parents=True, exist_ok=True)

    result = {"course_notes": [], "dashboard": None, "daily": None}

    # 과목별 노트 생성
    for course in courses:
        name = sanitize_course_name(course.get("name", ""))
        if not name:
            continue

        md_content = render_course_note(course, semester)
        note_path = target / f"{name}.md"
        note_path.write_text(md_content, encoding="utf-8")
        result["course_notes"].append(str(note_path))
        print(f"  [과목] {name}.md")

    # 대시보드 생성
    dashboard_content = render_dashboard(data)
    dashboard_path = target / "_dashboard.md"
    dashboard_path.write_text(dashboard_content, encoding="utf-8")
    result["dashboard"] = str(dashboard_path)
    print(f"  [대시보드] _dashboard.md")

    # 데일리 노트 주입
    if do_daily and (calendar or courses):
        daily_path = inject_daily(calendar, courses)
        if daily_path:
            result["daily"] = str(daily_path)
            print(f"  [데일리] {daily_path.name}")
        else:
            print(f"  [데일리] 주입할 마감/일정 없음 — 건너뜀")

    print(f"\n  동기화 완료: {len(result['course_notes'])}개 과목 노트")
    return result


def _load_latest_json() -> dict:
    """output/ 에서 가장 최근 semester JSON을 찾아 로드한다."""
    if not OUTPUT_DIR.exists():
        raise FileNotFoundError(f"output 디렉토리가 없습니다: {OUTPUT_DIR}")

    json_files = sorted(
        OUTPUT_DIR.glob("*_semester.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not json_files:
        raise FileNotFoundError("output/ 에 semester JSON 파일이 없습니다. 먼저 크롤링을 실행하세요.")

    path = json_files[0]
    print(f"  JSON 로드: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    sync()
