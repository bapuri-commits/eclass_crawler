"""출석 기록 추출."""

from config import BASE_URL


async def extract_attendance(page, course_id: int) -> dict:
    """출석부 페이지에서 데이터를 추출한다."""
    url = f"{BASE_URL}/local/ubattendance/attendance_book.php?id={course_id}"
    await page.goto(url, wait_until="networkidle")

    data = await page.evaluate("""
        () => {
            const result = { summary: {}, records: [] };

            // 출석 테이블 (가장 큰 테이블을 대상으로)
            const tables = [...document.querySelectorAll('table')];
            if (tables.length === 0) {
                const main = document.querySelector('#region-main, main');
                if (main) result._raw_text = main.innerText.trim().substring(0, 5000);
                return result;
            }

            // 행 수가 가장 많은 테이블이 출석 데이터 테이블
            let mainTable = tables[0];
            let maxRows = 0;
            tables.forEach(t => {
                const rowCount = t.querySelectorAll('tr').length;
                if (rowCount > maxRows) {
                    maxRows = rowCount;
                    mainTable = t;
                }
            });

            const headers = [];
            mainTable.querySelectorAll('thead th, thead td').forEach(th => {
                headers.push(th.innerText.trim());
            });
            // thead가 없으면 첫 행에서
            if (headers.length === 0) {
                mainTable.querySelectorAll('tr:first-child th, tr:first-child td').forEach(th => {
                    headers.push(th.innerText.trim());
                });
            }

            const rows = headers.length > 0
                ? mainTable.querySelectorAll('tbody tr')
                : mainTable.querySelectorAll('tr:not(:first-child)');

            rows.forEach(tr => {
                const cells = {};
                tr.querySelectorAll('td, th').forEach((td, i) => {
                    const key = headers[i] || `col_${i}`;
                    cells[key] = td.innerText.trim();
                });
                if (Object.keys(cells).length > 1) {
                    result.records.push(cells);
                }
            });

            // 요약: "출석 N회, 결석 N회" 등 텍스트에서 추출
            const summaryEl = document.querySelector('.attendance-summary, .att_summary, .attendance-info');
            if (summaryEl) {
                result.summary_text = summaryEl.innerText.trim();
            }

            return result;
        }
    """)

    rec_count = len(data.get("records", []))
    print(f"  [ATTENDANCE] course={course_id}: {rec_count}개 기록")
    return data
