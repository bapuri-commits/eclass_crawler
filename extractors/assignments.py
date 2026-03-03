"""과제/활동 추출. 과목 메인 페이지의 섹션/활동에서 정보를 추출한다."""

from config import BASE_URL


async def extract_assignments(page, course_id: int) -> dict:
    """과목 페이지에서 과제/활동 정보를 추출한다."""
    url = f"{BASE_URL}/course/view.php?id={course_id}"
    await page.goto(url, wait_until="networkidle")

    activities = await page.evaluate("""
        () => {
            const items = [];

            document.querySelectorAll('.activity, [class*="modtype_"]').forEach(act => {
                const nameEl = act.querySelector('.instancename, .activityname, .aalink, a');
                const typeClass = [...act.classList].find(c => c.startsWith('modtype_')) || '';
                const modType = typeClass.replace('modtype_', '');
                const link = act.querySelector('a[href]');
                const dateEl = act.querySelector('.text-muted, .dimmed_text, .availabilityinfo');

                const name = nameEl ? nameEl.innerText.trim() : '';
                if (!name) return;

                items.push({
                    name: name,
                    type: modType,
                    url: link ? link.href : '',
                    info: dateEl ? dateEl.innerText.trim() : '',
                });
            });

            return items;
        }
    """)

    sections = await page.evaluate("""
        () => {
            const result = [];
            document.querySelectorAll('.section.main, li.section').forEach(sec => {
                const titleEl = sec.querySelector('.sectionname, h3');
                const activities = [];
                sec.querySelectorAll('.activity, [class*="modtype_"]').forEach(act => {
                    const nameEl = act.querySelector('.instancename, .activityname, a');
                    const typeClass = [...act.classList].find(c => c.startsWith('modtype_')) || '';
                    const name = nameEl ? nameEl.innerText.trim() : '';
                    if (!name) return;
                    activities.push({
                        name: name,
                        type: typeClass.replace('modtype_', ''),
                    });
                });
                if (activities.length > 0) {
                    result.push({
                        section: titleEl ? titleEl.innerText.trim() : '',
                        activities: activities,
                    });
                }
            });
            return result;
        }
    """)

    print(f"  [ACTIVITIES] course={course_id}: {len(activities)}개 활동, {len(sections)}개 섹션")
    return {"activities": activities, "sections": sections}
