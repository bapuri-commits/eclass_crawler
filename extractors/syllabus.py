"""강의 계획서 추출."""

from config import BASE_URL


async def extract_syllabus(page, course_id: int) -> dict:
    """강의 계획서 페이지에서 데이터를 추출한다."""
    url = f"{BASE_URL}/local/ubion/setting/syllabus.php?id={course_id}"
    await page.goto(url, wait_until="networkidle")

    data = await page.evaluate("""
        () => {
            const result = {};

            // 테이블 기반 강의계획서
            document.querySelectorAll('table tr, .syllabus-table tr').forEach(tr => {
                const th = tr.querySelector('th, td:first-child');
                const td = tr.querySelector('td:last-child, td:nth-child(2)');
                if (th && td && th !== td) {
                    const key = th.innerText.trim();
                    const value = td.innerText.trim();
                    if (key && value) {
                        result[key] = value;
                    }
                }
            });

            // div 기반 레이아웃도 시도
            if (Object.keys(result).length === 0) {
                document.querySelectorAll('.form-group, .fitem, [class*="syllabus"]').forEach(el => {
                    const label = el.querySelector('label, .col-form-label, dt, .label');
                    const value = el.querySelector('.form-control-static, dd, .value, .felement');
                    if (label && value) {
                        result[label.innerText.trim()] = value.innerText.trim();
                    }
                });
            }

            // 전체 텍스트 백업
            if (Object.keys(result).length === 0) {
                const main = document.querySelector('#region-main, .course-content, main');
                if (main) {
                    result['_raw_text'] = main.innerText.trim().substring(0, 5000);
                }
            }

            return result;
        }
    """)

    field_count = len([k for k in data if not k.startswith('_')])
    print(f"  [SYLLABUS] course={course_id}: {field_count}개 항목 추출")
    return data
