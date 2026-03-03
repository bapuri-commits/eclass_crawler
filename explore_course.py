"""과목 페이지 내부 구조 탐색."""

import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from config import BASE_URL, USERNAME, PASSWORD

OUTPUT_DIR = Path(__file__).parent / "output"
COURSE_ID = 51011  # 자료구조


async def explore_course():
    OUTPUT_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 로그인
        print("[1] 로그인...")
        await page.goto(f"{BASE_URL}/login/index.php", wait_until="networkidle")
        await page.fill('input[name="username"]', USERNAME)
        await page.fill('input[name="password"]', PASSWORD)
        await page.click('button[type="submit"], input[type="submit"], #loginbtn')
        await page.wait_for_load_state("networkidle")

        # 과목 메인 페이지
        print(f"\n[2] 과목 페이지 탐색 (id={COURSE_ID})...")
        await page.goto(f"{BASE_URL}/course/view.php?id={COURSE_ID}", wait_until="networkidle")
        (OUTPUT_DIR / "explore_course_main.html").write_text(await page.content(), encoding="utf-8")

        # 과목 제목
        title = await page.evaluate("() => document.querySelector('h1, .page-header-headings h1, .coursename')?.innerText || ''")
        print(f"    과목명: {title}")

        # 모든 링크 수집 및 패턴 분석
        all_links = await page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.href;
                    if (href && !href.startsWith('javascript') && !href.startsWith('#') && href.includes('dongguk')) {
                        links.push({ text: a.innerText.trim().substring(0, 80), href: href });
                    }
                });
                return links;
            }
        """)

        # 관심 키워드별 분류
        keywords = {
            "성적/grade": ["grade", "성적"],
            "과제/assign": ["assign", "과제"],
            "출석/attend": ["attend", "출석"],
            "게시판/board": ["board", "게시판", "공지"],
            "강의계획서": ["syllabus", "계획서", "계획"],
            "강의영상/vod": ["vod", "영상", "동영상", "ubion", "video"],
            "퀴즈/quiz": ["quiz", "퀴즈", "시험"],
            "자료/resource": ["resource", "자료", "파일"],
            "포럼/forum": ["forum"],
            "완료/completion": ["completion"],
        }

        print(f"\n    전체 링크: {len(all_links)}개")
        print("\n    [관심 링크 분류]")
        for category, kws in keywords.items():
            matches = [l for l in all_links if any(kw in l["href"].lower() or kw in l["text"].lower() for kw in kws)]
            if matches:
                print(f"\n    --- {category} ({len(matches)}개) ---")
                seen = set()
                for m in matches:
                    key = m["href"]
                    if key not in seen:
                        seen.add(key)
                        print(f"      [{m['text'][:50]}]")
                        print(f"        {m['href'][:100]}")

        # 섹션 & 활동 구조
        sections = await page.evaluate("""
            () => {
                const result = [];
                document.querySelectorAll('.section.main, li.section').forEach(sec => {
                    const titleEl = sec.querySelector('.sectionname, .section-title, h3');
                    const activities = [];
                    sec.querySelectorAll('.activity, .modtype_resource, .modtype_assign, .modtype_url, .modtype_page, .modtype_forum, [class*="modtype_"]').forEach(act => {
                        const nameEl = act.querySelector('.instancename, .activityname, .aalink');
                        const typeClass = [...act.classList].find(c => c.startsWith('modtype_')) || '';
                        const link = act.querySelector('a[href]');
                        activities.push({
                            name: nameEl ? nameEl.innerText.trim().substring(0, 60) : '',
                            type: typeClass.replace('modtype_', ''),
                            href: link ? link.href : '',
                        });
                    });
                    result.push({
                        title: titleEl ? titleEl.innerText.trim() : '(untitled)',
                        activities: activities,
                    });
                });
                return result;
            }
        """)

        print(f"\n    [섹션 구조] ({len(sections)}개)")
        for sec in sections:
            if sec["activities"]:
                print(f"\n    섹션: {sec['title'][:50]}")
                for act in sec["activities"][:5]:
                    print(f"      - [{act['type']}] {act['name'][:50]}")
                    if act["href"]:
                        print(f"        {act['href'][:90]}")
                if len(sec["activities"]) > 5:
                    print(f"      ... +{len(sec['activities'])-5}개 더")

        # 좌측 네비게이션
        nav = await page.evaluate("""
            () => {
                const items = [];
                document.querySelectorAll('.secondary-navigation a, nav a').forEach(a => {
                    if (a.href && a.innerText.trim() && a.href.includes('dongguk')) {
                        items.push({ text: a.innerText.trim(), href: a.href });
                    }
                });
                return items;
            }
        """)
        print(f"\n    [네비게이션] ({len(nav)}개)")
        seen = set()
        for item in nav:
            if item["href"] not in seen:
                seen.add(item["href"])
                print(f"      {item['text'][:30]} -> {item['href'][:80]}")

        # 결과 저장
        (OUTPUT_DIR / "explore_course_structure.json").write_text(
            json.dumps({
                "course_id": COURSE_ID,
                "title": title,
                "links": all_links,
                "sections": sections,
                "navigation": nav,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        await browser.close()
        print(f"\n[완료] output/explore_course_*.* 저장됨")


if __name__ == "__main__":
    asyncio.run(explore_course())
