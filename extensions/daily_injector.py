"""데일리 노트에 이클래스 마감/일정을 주입한다.

기존 사용자 작성 내용은 절대 삭제하지 않으며,
eclass 마커 블록(<!-- eclass-start --> ~ <!-- eclass-end -->)만 교체한다.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from sync_config import (
    VAULT_PATH,
    DAILY_DIR,
    DAILY_TEMPLATE,
    ECLASS_MARKER_START,
    ECLASS_MARKER_END,
    DEADLINE_LOOKAHEAD_DAYS,
    sanitize_course_name,
)


def inject_daily(
    calendar_events: list[dict],
    courses: list[dict],
    target_date: datetime | None = None,
) -> Path | None:
    """오늘(또는 지정 날짜)의 데일리 노트에 마감/일정을 주입한다.

    Returns:
        수정된 데일리 노트 경로, 주입할 내용이 없으면 None
    """
    target = target_date or datetime.now()
    date_str = target.strftime("%Y-%m-%d")
    month_str = target.strftime("%Y-%m")
    day_str = _weekday_kr(target)

    daily_dir = VAULT_PATH / DAILY_DIR / month_str
    daily_path = daily_dir / f"{date_str}.md"

    upcoming = _filter_upcoming_events(calendar_events, target)
    today_events = _filter_today_events(calendar_events, target)
    course_deadlines = _extract_course_deadlines(courses, target)

    all_deadlines = today_events + course_deadlines
    if not all_deadlines and not upcoming:
        return None

    if not daily_path.exists():
        daily_path.parent.mkdir(parents=True, exist_ok=True)
        content = _create_from_template(date_str, day_str)
        daily_path.write_text(content, encoding="utf-8")

    content = daily_path.read_text(encoding="utf-8")

    todo_block = _build_todo_block(all_deadlines, upcoming, target)
    schedule_block = _build_schedule_block(today_events, target)

    content = _inject_into_section(content, "## Todo", todo_block)
    content = _inject_into_section(content, "## 일정", schedule_block)

    daily_path.write_text(content, encoding="utf-8")
    return daily_path


# ── 이벤트 필터링 ──────────────────────────────────────


def _filter_today_events(events: list[dict], target: datetime) -> list[dict]:
    """target 날짜에 해당하는 이벤트만 필터링."""
    target_date = target.date()
    result = []
    for evt in events:
        ts = evt.get("time_start", 0)
        if not ts:
            continue
        evt_date = datetime.fromtimestamp(ts).date()
        if evt_date == target_date:
            result.append(evt)
    return sorted(result, key=lambda e: e.get("time_start", 0))


def _filter_upcoming_events(events: list[dict], target: datetime) -> list[dict]:
    """target 이후 ~ N일까지의 이벤트 필터링."""
    start = target.date()
    end = (target + timedelta(days=DEADLINE_LOOKAHEAD_DAYS)).date()
    result = []
    for evt in events:
        ts = evt.get("time_start", 0)
        if not ts:
            continue
        evt_date = datetime.fromtimestamp(ts).date()
        if start < evt_date <= end:
            result.append(evt)
    return sorted(result, key=lambda e: e.get("time_start", 0))


def _extract_course_deadlines(courses: list[dict], target: datetime) -> list[dict]:
    """activities에서 마감 정보가 있는 항목 추출 (보조 소스)."""
    result = []
    target_date = target.date()
    for course in courses:
        activities = course.get("activities", {})
        if not activities or isinstance(activities, dict) and "_error" in activities:
            continue
        for act in activities.get("activities", []):
            info = act.get("info", "")
            if not info:
                continue
            date_match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", info)
            if date_match:
                y, m, d = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                try:
                    act_date = datetime(y, m, d).date()
                except ValueError:
                    continue
                if act_date == target_date:
                    result.append({
                        "name": act.get("name", ""),
                        "course_name": course.get("name", ""),
                        "time_start": datetime(y, m, d, 23, 59).timestamp(),
                        "event_type": "activity_due",
                    })
    return result


# ── 마크다운 블록 생성 ─────────────────────────────────


def _build_todo_block(today: list[dict], upcoming: list[dict], target: datetime) -> str:
    """Todo 섹션에 주입할 마커 블록 생성."""
    lines = [ECLASS_MARKER_START]

    for evt in today:
        cname = sanitize_course_name(evt.get("course_name", ""))
        ename = evt.get("name", "")
        course_link = f"[[{cname}]]" if cname else ""
        ts = evt.get("time_start", 0)
        time_str = datetime.fromtimestamp(ts).strftime("%H:%M") if ts else ""
        time_part = f" ({time_str} 마감)" if time_str else ""
        lines.append(f"- [ ] {course_link} {ename}{time_part}")

    if upcoming:
        lines.append(f"- **향후 {DEADLINE_LOOKAHEAD_DAYS}일 마감:**")
        for evt in upcoming:
            cname = sanitize_course_name(evt.get("course_name", ""))
            ename = evt.get("name", "")
            ts = evt.get("time_start", 0)
            evt_date = datetime.fromtimestamp(ts).date() if ts else target.date()
            d_day = (evt_date - target.date()).days
            d_str = f"D-{d_day}"
            date_str = evt_date.strftime("%m/%d")
            course_link = f"[[{cname}]]" if cname else ""
            lines.append(f"  - {course_link} {ename} ({date_str}, {d_str})")

    lines.append(ECLASS_MARKER_END)
    return "\n".join(lines)


def _build_schedule_block(today_events: list[dict], target: datetime) -> str:
    """일정 섹션에 주입할 마커 블록 생성."""
    if not today_events:
        return ""

    lines = [ECLASS_MARKER_START]
    for evt in today_events:
        ts = evt.get("time_start", 0)
        time_str = datetime.fromtimestamp(ts).strftime("%H:%M") if ts else ""
        cname = sanitize_course_name(evt.get("course_name", ""))
        ename = evt.get("name", "")
        lines.append(f"| {time_str} | {cname} {ename} | 이클래스 |")
    lines.append(ECLASS_MARKER_END)
    return "\n".join(lines)


# ── 섹션 주입 ──────────────────────────────────────────


def _inject_into_section(content: str, section_header: str, block: str) -> str:
    """마크다운 내 특정 섹션에 eclass 마커 블록을 주입/교체한다.

    이미 마커 블록이 있으면 교체, 없으면 섹션 끝에 추가.
    """
    if not block:
        return content

    marker_pattern = re.compile(
        re.escape(ECLASS_MARKER_START) + r".*?" + re.escape(ECLASS_MARKER_END),
        re.DOTALL,
    )

    section_idx = content.find(section_header)
    if section_idx == -1:
        return content

    after_header = content[section_idx:]

    existing = marker_pattern.search(after_header)
    if existing:
        start = section_idx + existing.start()
        end = section_idx + existing.end()
        return content[:start] + block + content[end:]

    next_section = re.search(r"\n## ", after_header[len(section_header):])
    if next_section:
        insert_pos = section_idx + len(section_header) + next_section.start()
    else:
        insert_pos = len(content)

    return content[:insert_pos] + "\n" + block + "\n" + content[insert_pos:]


# ── 유틸 ──────────────────────────────────────────────


def _create_from_template(date_str: str, day_str: str) -> str:
    """Templates/daily.md 를 읽어서 Templater 문법을 치환한다."""
    template_path = VAULT_PATH / DAILY_TEMPLATE
    if template_path.exists():
        tmpl = template_path.read_text(encoding="utf-8")
    else:
        tmpl = _fallback_template()

    replacements = {
        "{{date:YYYY-MM-DD}}": date_str,
        "{{date:YYYY-MM-DD (ddd)}}": f"{date_str} ({day_str})",
        "{{date:ddd}}": day_str,
        "{{date:MM}}": date_str[5:7],
        "{{date:YYYY-MM}}": date_str[:7],
    }
    for pattern, value in replacements.items():
        tmpl = tmpl.replace(pattern, value)

    tmpl = re.sub(r"<%.*?%>", "", tmpl)
    return tmpl


def _fallback_template() -> str:
    return """---
type: daily
date: "{{date:YYYY-MM-DD}}"
day: "{{date:ddd}}"
tags:
  - daily
---

# {{date:YYYY-MM-DD (ddd)}}

---

## Todo
- [ ] 

## 일정
| 시간 | 내용 | 비고 |
|------|------|------|
|      |      |      |

## 개발 로그
- 

## 공부 기록
- 

## 메모
- 
"""


_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _weekday_kr(dt: datetime) -> str:
    return _WEEKDAYS[dt.weekday()]
