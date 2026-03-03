"""게시판(공지사항/자료실) 추출."""

import asyncio
from config import BASE_URL, REQUEST_DELAY, GLOBAL_BOARD_IDS


async def extract_boards(page, course_id: int, scanned_boards: list[dict] | None = None) -> dict[str, list[dict]]:
    """과목의 모든 게시판 데이터를 추출한다.
    scanned_boards가 제공되면 재스캔 없이 그대로 사용한다.
    """
    if scanned_boards is not None:
        board_links = scanned_boards
    else:
        boards_url = f"{BASE_URL}/mod/ubboard/index.php?id={course_id}"
        await page.goto(boards_url, wait_until="networkidle")

        board_links = await page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a[href*="ubboard/view.php"]').forEach(a => {
                    const match = a.href.match(/id=(\\d+)/);
                    if (match) {
                        links.push({
                            id: parseInt(match[1]),
                            name: a.innerText.trim(),
                            url: a.href,
                        });
                    }
                });
                return links;
            }
        """)
        board_links = [b for b in board_links if b["id"] not in GLOBAL_BOARD_IDS]

    print(f"  [BOARDS] course={course_id}: {len(board_links)}개 과목 게시판")

    result = {}
    for board in board_links:
        await asyncio.sleep(REQUEST_DELAY)
        posts = await _extract_board_posts(page, board["id"], board["name"])
        result[board["name"]] = {
            "board_id": board["id"],
            "posts": posts,
        }

    return result


async def _extract_board_posts(page, board_id: int, board_name: str) -> list[dict]:
    url = f"{BASE_URL}/mod/ubboard/view.php?id={board_id}"
    await page.goto(url, wait_until="networkidle")

    posts = await page.evaluate("""
        () => {
            const posts = [];

            const table = document.querySelector('table.board_list, table.generaltable, .ubboard table, table');
            if (table) {
                const headers = [];
                table.querySelectorAll('thead th, tr:first-child th').forEach(th => {
                    headers.push(th.innerText.trim());
                });

                table.querySelectorAll('tbody tr, tr.board_list_tr').forEach(tr => {
                    const cells = {};
                    const link = tr.querySelector('a[href*="article.php"]');
                    tr.querySelectorAll('td').forEach((td, i) => {
                        const key = headers[i] || `col_${i}`;
                        cells[key] = td.innerText.trim();
                    });
                    if (link) {
                        cells['_link'] = link.href;
                    }
                    const values = Object.values(cells).join('');
                    if (Object.keys(cells).length > 0 && !values.includes('등록된 게시글이 없습니다')) {
                        posts.push(cells);
                    }
                });
            }

            return posts;
        }
    """)

    print(f"    - {board_name}: {len(posts)}개 글")
    return posts
