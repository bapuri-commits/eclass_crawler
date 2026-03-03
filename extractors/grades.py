"""성적 추출."""

from config import BASE_URL


async def extract_grades(page, course_id: int) -> list[dict]:
    """성적 페이지에서 데이터를 추출한다."""
    url = f"{BASE_URL}/grade/report/user/index.php?id={course_id}"
    await page.goto(url, wait_until="networkidle")

    grades = await page.evaluate("""
        () => {
            const rows = [];
            // Moodle 성적표 테이블
            const table = document.querySelector('.user-grade table, #user-grade table, table.generaltable');
            if (!table) {
                // 테이블이 없으면 전체 텍스트
                const main = document.querySelector('#region-main, main');
                if (main) {
                    return [{ _raw_text: main.innerText.trim().substring(0, 3000) }];
                }
                return [];
            }

            const headers = [];
            table.querySelectorAll('thead th, tr:first-child th').forEach(th => {
                headers.push(th.innerText.trim());
            });

            table.querySelectorAll('tbody tr, tr:not(:first-child)').forEach(tr => {
                const cells = {};
                tr.querySelectorAll('td, th').forEach((td, i) => {
                    const key = headers[i] || `col_${i}`;
                    cells[key] = td.innerText.trim();
                });
                if (Object.keys(cells).length > 0) {
                    rows.push(cells);
                }
            });

            return rows;
        }
    """)

    print(f"  [GRADES] course={course_id}: {len(grades)}개 항목")
    return grades
