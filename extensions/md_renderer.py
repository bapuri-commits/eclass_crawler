"""JSON 데이터를 옵시디언 마크다운으로 변환하는 렌더러."""

from __future__ import annotations

from datetime import datetime

from sync_config import sanitize_course_name


def render_course_note(course: dict, semester: str) -> str:
    """과목 전체 데이터를 하나의 마크다운 노트로 렌더링한다."""
    name = sanitize_course_name(course.get("name", ""))
    full_name = course.get("name", name)
    professor = course.get("professor", "")
    course_id = course.get("id", "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    parts = [
        _frontmatter(name, course_id, semester, professor),
        f"# {name}\n",
        f"> **{full_name}** | 교수: {professor} | 학기: {semester}\n",
    ]

    if "syllabus" in course and not _is_error(course["syllabus"]):
        parts.append(render_syllabus(course["syllabus"]))

    if "grades" in course and not _is_error(course["grades"]):
        parts.append(render_grades(course["grades"]))

    if "attendance" in course and not _is_error(course["attendance"]):
        parts.append(render_attendance(course["attendance"]))

    if "boards" in course and not _is_error(course["boards"]):
        parts.append(render_boards(course["boards"]))

    if "activities" in course and not _is_error(course["activities"]):
        parts.append(render_activities(course["activities"]))

    parts.append(f"\n---\n*마지막 동기화: {now}*\n")
    return "\n".join(parts)


def render_dashboard(data: dict) -> str:
    """학기 통합 데이터를 대시보드 마크다운으로 렌더링한다."""
    semester = data.get("semester", "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    courses = data.get("courses", [])
    calendar = data.get("calendar_events", [])

    lines = [
        "---",
        "type: school-dashboard",
        f'semester: "{semester}"',
        "tags:",
        "  - school",
        f'updated: "{now}"',
        "---",
        "",
        f"# {semester} 대시보드\n",
    ]

    # 수강 과목 테이블
    lines.append("## 수강 과목\n")
    lines.append("| 과목 | 교수 |")
    lines.append("|------|------|")
    for c in courses:
        cname = sanitize_course_name(c.get("name", ""))
        prof = c.get("professor", "")
        lines.append(f"| [[{cname}]] | {prof} |")
    lines.append("")

    # 다가오는 마감
    if calendar:
        lines.append("## 다가오는 마감\n")
        lines.append("| 마감일 | 과목 | 내용 | D-day |")
        lines.append("|--------|------|------|-------|")

        now_ts = datetime.now().timestamp()
        upcoming = sorted(
            [e for e in calendar if (e.get("time_start") or 0) >= now_ts],
            key=lambda e: e.get("time_start", 0),
        )
        for evt in upcoming[:20]:
            ts = evt.get("time_start", 0)
            due_dt = datetime.fromtimestamp(ts)
            due_str = due_dt.strftime("%m/%d %H:%M")
            d_day = (due_dt - datetime.now()).days
            d_str = "D-0" if d_day == 0 else f"D-{d_day}" if d_day > 0 else f"D+{abs(d_day)}"
            cname = sanitize_course_name(evt.get("course_name", ""))
            ename = evt.get("name", "")
            course_link = f"[[{cname}]]" if cname else ""
            lines.append(f"| {due_str} | {course_link} | {ename} | {d_str} |")
        lines.append("")

    # 출석 요약
    att_rows = []
    for c in courses:
        att = c.get("attendance", {})
        if _is_error(att) or not att:
            continue
        cname = sanitize_course_name(c.get("name", ""))
        summary = att.get("summary_text", "")
        att_rows.append(f"| [[{cname}]] | {summary} |")

    if att_rows:
        lines.append("## 출석 요약\n")
        lines.append("| 과목 | 현황 |")
        lines.append("|------|------|")
        lines.extend(att_rows)
        lines.append("")

    lines.append(f"\n---\n*마지막 동기화: {now}*\n")
    return "\n".join(lines)


# ── 섹션별 렌더러 ──────────────────────────────────────────


def render_syllabus(syllabus: dict) -> str:
    if not syllabus or "_raw_text" in syllabus:
        raw = syllabus.get("_raw_text", "")
        return f"## 강의 계획서\n\n{raw}\n" if raw else ""

    lines = ["## 강의 계획서\n"]
    for key, value in syllabus.items():
        if key.startswith("_"):
            continue
        value_oneline = value.replace("\n", " ").strip()
        if len(value_oneline) > 120:
            lines.append(f"**{key}**\n> {value.strip()}\n")
        else:
            lines.append(f"- **{key}**: {value_oneline}")
    lines.append("")
    return "\n".join(lines)


def render_grades(grades: list[dict]) -> str:
    if not grades:
        return ""

    if len(grades) == 1 and "_raw_text" in grades[0]:
        return f"## 성적\n\n{grades[0]['_raw_text']}\n"

    lines = ["## 성적\n"]

    headers = []
    for row in grades:
        for k in row:
            if k not in headers and not k.startswith("_"):
                headers.append(k)

    if not headers:
        return ""

    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in grades:
        cells = [row.get(h, "").replace("\n", " ") for h in headers]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def render_attendance(attendance: dict) -> str:
    if not attendance:
        return ""

    lines = ["## 출석 현황\n"]

    summary = attendance.get("summary_text", "")
    if summary:
        lines.append(f"> {summary}\n")

    records = attendance.get("records", [])
    if not records:
        raw = attendance.get("_raw_text", "")
        if raw:
            lines.append(raw)
        lines.append("")
        return "\n".join(lines)

    headers = []
    for rec in records:
        for k in rec:
            if k not in headers and not k.startswith("_"):
                headers.append(k)

    if headers:
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for rec in records:
            cells = [rec.get(h, "").replace("\n", " ") for h in headers]
            lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def render_boards(boards: dict) -> str:
    if not boards:
        return ""

    lines = ["## 게시판\n"]
    for board_name, board_data in boards.items():
        posts = board_data.get("posts", []) if isinstance(board_data, dict) else []
        lines.append(f"### {board_name} ({len(posts)}건)\n")

        if not posts:
            lines.append("게시글 없음\n")
            continue

        for i, post in enumerate(posts[:15], 1):
            title = _extract_post_title(post)
            link = post.get("_link", "")
            date = _extract_post_date(post)
            date_str = f" ({date})" if date else ""

            if link:
                lines.append(f"{i}. [{title}]({link}){date_str}")
            else:
                lines.append(f"{i}. {title}{date_str}")

        if len(posts) > 15:
            lines.append(f"\n... 외 {len(posts) - 15}건")
        lines.append("")
    return "\n".join(lines)


def render_activities(activities: dict) -> str:
    if not activities:
        return ""

    sections = activities.get("sections", [])
    if not sections:
        items = activities.get("activities", [])
        if not items:
            return ""
        lines = ["## 활동/과제\n"]
        for act in items:
            name = act.get("name", "")
            mod_type = act.get("type", "")
            info = act.get("info", "")
            type_badge = f"`{mod_type}` " if mod_type else ""
            info_str = f" — {info}" if info else ""
            lines.append(f"- {type_badge}{name}{info_str}")
        lines.append("")
        return "\n".join(lines)

    lines = ["## 주차별 활동\n"]
    for sec in sections:
        sec_name = sec.get("section", "")
        sec_acts = sec.get("activities", [])
        if sec_name:
            lines.append(f"### {sec_name}\n")
        for act in sec_acts:
            name = act.get("name", "")
            mod_type = act.get("type", "")
            type_badge = f"`{mod_type}` " if mod_type else ""
            lines.append(f"- {type_badge}{name}")
        lines.append("")
    return "\n".join(lines)


# ── 내부 유틸 ──────────────────────────────────────────


def _frontmatter(name: str, course_id, semester: str, professor: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d")
    return "\n".join([
        "---",
        "type: course",
        f"course_id: {course_id}",
        f'semester: "{semester}"',
        f'professor: "{professor}"',
        "tags:",
        "  - school",
        "  - course",
        f'updated: "{now}"',
        "---",
        "",
    ])


def _is_error(data) -> bool:
    if isinstance(data, dict) and "_error" in data:
        return True
    return False


def _extract_post_title(post: dict) -> str:
    for key in ("제목", "Title", "title", "col_1"):
        if key in post:
            return post[key]
    values = [v for k, v in post.items() if not k.startswith("_")]
    return values[0] if values else "(제목 없음)"


def _extract_post_date(post: dict) -> str:
    for key in ("작성일", "등록일", "날짜", "Date", "date", "col_3", "col_4"):
        if key in post:
            return post[key]
    return ""
