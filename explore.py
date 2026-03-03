"""
사이트 구조 탐색 스크립트.
로그인 후 대시보드, 수강 과목 목록, 과목 페이지의 HTML 구조를 파악한다.
"""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright
from config import BASE_URL, USERNAME, PASSWORD, REQUEST_TIMEOUT

OUTPUT_DIR = Path(__file__).parent / "output"


async def explore():
    OUTPUT_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 1. 로그인
        print("[1] 로그인 중...")
        await page.goto(f"{BASE_URL}/login/index.php", wait_until="networkidle")
        await page.fill('input[name="username"]', USERNAME)
        await page.fill('input[name="password"]', PASSWORD)
        await page.click('button[type="submit"], input[type="submit"], #loginbtn')
        await page.wait_for_load_state("networkidle")
        print(f"    URL: {page.url}")

        # 2. 대시보드 구조 파악
        print("\n[2] 대시보드 분석...")
        dashboard_html = await page.content()
        (OUTPUT_DIR / "explore_dashboard.html").write_text(dashboard_html, encoding="utf-8")

        # 코스 목록 추출 시도 (다양한 셀렉터)
        course_selectors = [
            ".course-listitem",
            ".coursebox",
            ".course_list .course",
            "[data-region='course-content']",
            ".courses .coursename",
            ".course-info-container",
            ".card.dashboard-card",
            ".list-group-item.course-listitem",
        ]

        for sel in course_selectors:
            elements = await page.query_selector_all(sel)
            if elements:
                print(f"    코스 셀렉터 발견: '{sel}' ({len(elements)}개)")

        # 네비게이션에서 과목 링크 찾기
        nav_links = await page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a[href*="/course/view.php"]').forEach(a => {
                    links.push({ text: a.innerText.trim(), href: a.href });
                });
                return links;
            }
        """)
        print(f"    과목 링크 수: {len(nav_links)}")
        for link in nav_links[:10]:
            print(f"      - {link['text'][:50]} -> {link['href']}")

        # 3. 나의 강좌 페이지 탐색
        print("\n[3] 나의 강좌 페이지 탐색...")
        await page.goto(f"{BASE_URL}/my/courses.php", wait_until="networkidle")
        my_courses_html = await page.content()
        (OUTPUT_DIR / "explore_my_courses.html").write_text(my_courses_html, encoding="utf-8")

        my_course_links = await page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a[href*="/course/view.php"]').forEach(a => {
                    links.push({ text: a.innerText.trim(), href: a.href });
                });
                return links;
            }
        """)
        print(f"    나의 강좌 링크 수: {len(my_course_links)}")
        for link in my_course_links[:10]:
            print(f"      - {link['text'][:60]} -> {link['href']}")

        # 4. 첫 번째 과목 페이지 구조 탐색
        if my_course_links:
            first_course = my_course_links[0]
            print(f"\n[4] 첫 번째 과목 페이지 탐색: {first_course['text'][:40]}")
            await page.goto(first_course["href"], wait_until="networkidle")
            course_html = await page.content()
            (OUTPUT_DIR / "explore_course_page.html").write_text(course_html, encoding="utf-8")

            # 과목 내 주요 메뉴/탭 찾기
            nav_items = await page.evaluate("""
                () => {
                    const items = [];
                    // secondary nav, tabs, course menu
                    document.querySelectorAll('.secondary-navigation a, .course-content-header a, [role="tablist"] a, .activity-navigation a').forEach(a => {
                        items.push({ text: a.innerText.trim(), href: a.href });
                    });
                    // 좌측 메뉴
                    document.querySelectorAll('.drawercontent a, #nav-drawer a').forEach(a => {
                        if (a.href && a.innerText.trim()) {
                            items.push({ text: a.innerText.trim(), href: a.href });
                        }
                    });
                    return items;
                }
            """)
            print(f"    과목 메뉴 항목 수: {len(nav_items)}")
            for item in nav_items[:15]:
                print(f"      - {item['text'][:40]} -> {item['href'][:80]}")

            # 섹션/활동 구조
            sections = await page.evaluate("""
                () => {
                    const sections = [];
                    document.querySelectorAll('.section, [data-region="section"]').forEach(sec => {
                        const title = sec.querySelector('.sectionname, .section-title');
                        const activities = sec.querySelectorAll('.activity, .modtype_');
                        sections.push({
                            title: title ? title.innerText.trim() : '(no title)',
                            activity_count: activities.length,
                        });
                    });
                    return sections;
                }
            """)
            print(f"    섹션 수: {len(sections)}")
            for sec in sections[:10]:
                print(f"      - {sec['title'][:40]} (활동 {sec['activity_count']}개)")

            # 강의계획서 링크 탐색
            syllabus_links = await page.evaluate("""
                () => {
                    const links = [];
                    document.querySelectorAll('a').forEach(a => {
                        const text = a.innerText.trim().toLowerCase();
                        const href = a.href || '';
                        if (text.includes('계획서') || text.includes('syllabus') ||
                            href.includes('syllabus') || href.includes('plan') ||
                            text.includes('강의계획') || text.includes('수업계획')) {
                            links.push({ text: a.innerText.trim(), href: href });
                        }
                    });
                    return links;
                }
            """)
            print(f"    강의계획서 관련 링크: {len(syllabus_links)}")
            for link in syllabus_links:
                print(f"      - {link['text'][:40]} -> {link['href'][:80]}")

            # 모든 링크 수집 (패턴 분석용)
            all_links = await page.evaluate("""
                () => {
                    const links = [];
                    document.querySelectorAll('a[href]').forEach(a => {
                        const href = a.href;
                        if (href && !href.startsWith('javascript') && !href.startsWith('#')) {
                            links.push({ text: a.innerText.trim().substring(0, 50), href: href });
                        }
                    });
                    return links;
                }
            """)
            # 링크 패턴 분류
            patterns = {}
            for link in all_links:
                from urllib.parse import urlparse
                path = urlparse(link["href"]).path
                if path not in patterns:
                    patterns[path] = []
                patterns[path].append(link["text"])

            print(f"    고유 URL 패턴 수: {len(patterns)}")
            interesting_patterns = {k: v for k, v in patterns.items()
                                    if any(kw in k for kw in ["grade", "assign", "attend", "board", "forum", "completion", "syllabus", "plan", "quiz"])}
            if interesting_patterns:
                print("    관심 패턴:")
                for path, texts in interesting_patterns.items():
                    print(f"      {path} -> {texts[:3]}")

        # 결과 요약 저장
        summary = {
            "dashboard_url": f"{BASE_URL}/my/",
            "course_links": my_course_links,
            "nav_items": nav_items if my_course_links else [],
            "sections": sections if my_course_links else [],
            "syllabus_links": syllabus_links if my_course_links else [],
        }
        (OUTPUT_DIR / "explore_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        await browser.close()
        print(f"\n[완료] HTML 파일들이 output/ 에 저장되었습니다.")


if __name__ == "__main__":
    asyncio.run(explore())
