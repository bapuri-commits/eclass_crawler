"""수강 과목 목록 추출."""

import re
from config import BASE_URL


async def extract_courses(page) -> list[dict]:
    """대시보드에서 수강 과목 목록을 추출한다."""
    await page.goto(f"{BASE_URL}/", wait_until="networkidle")

    courses = await page.evaluate("""
        () => {
            const courses = [];
            document.querySelectorAll('a[href*="/course/view.php"]').forEach(a => {
                const href = a.href;
                const match = href.match(/id=(\\d+)/);
                if (match) {
                    const id = parseInt(match[1]);
                    if (!courses.find(c => c.id === id)) {
                        courses.push({
                            id: id,
                            name: a.innerText.trim(),
                            url: href,
                        });
                    }
                }
            });
            return courses;
        }
    """)

    for course in courses:
        parts = [p.strip() for p in course["name"].split('\n') if p.strip()]
        if len(parts) >= 3:
            course["name"] = parts[1].strip()
            course["professor"] = parts[-1].strip()
        elif len(parts) == 2:
            course["name"] = parts[0].strip()
            course["professor"] = parts[-1].strip()
        else:
            course["name"] = re.sub(r'\s+', ' ', course["name"]).strip()
            course["professor"] = ""

        # "NEW" 태그 정리
        course["name"] = re.sub(r'\s*NEW\s*$', '', course["name"]).strip()

    print(f"[COURSES] {len(courses)}개 과목 발견")
    for c in courses:
        print(f"  - [{c['id']}] {c['name']} ({c.get('professor', '')})")

    return courses
