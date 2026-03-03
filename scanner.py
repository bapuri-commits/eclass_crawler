"""
과목별 동적 구조 분석기.
각 과목 페이지의 네비게이션, 메뉴, 활동, 게시판 등을 스캔하여
실제 존재하는 항목만 파악한 뒤, 그에 맞는 추출 계획을 생성한다.
"""

import re
from dataclasses import dataclass, field, asdict
from config import BASE_URL


@dataclass
class CourseFeature:
    key: str
    label: str
    url: str
    feature_type: str  # "nav", "activity", "board"


@dataclass
class CourseScan:
    course_id: int
    course_name: str
    features: list[CourseFeature] = field(default_factory=list)
    boards: list[dict] = field(default_factory=list)
    downloadable_resources: list[dict] = field(default_factory=list)

    @property
    def available_keys(self) -> set[str]:
        return {f.key for f in self.features}

    def has(self, key: str) -> bool:
        return key in self.available_keys

    def get_url(self, key: str) -> str | None:
        for f in self.features:
            if f.key == key:
                return f.url
        return None

    def to_dict(self) -> dict:
        return {
            "course_id": self.course_id,
            "course_name": self.course_name,
            "available_features": [asdict(f) for f in self.features],
            "boards": self.boards,
            "downloadable_resources": self.downloadable_resources,
        }


# URL 패턴 -> feature key 매핑
URL_PATTERNS = [
    (r"/local/ubion/setting/syllabus\.php", "syllabus", "강의계획서"),
    (r"/grade/report/user/index\.php", "grades", "성적"),
    (r"/local/ubattendance/attendance_book\.php", "attendance", "출석"),
    (r"/mod/ubboard/index\.php", "boards", "게시판"),
    (r"/mod/assign/index\.php", "assignments_page", "과제"),
    (r"/local/ubion/user/index\.php", "vod", "강의영상"),
    (r"/mod/quiz/index\.php", "quiz", "퀴즈"),
    (r"/mod/forum/index\.php", "forum", "포럼"),
    (r"/report/completion/index\.php", "completion", "이수현황"),
]

# 활동 모듈 타입 -> feature key
ACTIVITY_TYPES = {
    "ubboard": "board",
    "assign": "assignment",
    "quiz": "quiz",
    "resource": "resource",
    "url": "url_resource",
    "page": "page_resource",
    "forum": "forum",
    "vod": "vod",
    "ubfile": "file",
    "folder": "folder",
}


async def scan_course(page, course_id: int, course_name: str = "") -> CourseScan:
    """과목 페이지를 스캔하여 사용 가능한 기능/구조를 파악한다."""
    scan = CourseScan(course_id=course_id, course_name=course_name)

    await page.goto(f"{BASE_URL}/course/view.php?id={course_id}", wait_until="networkidle")

    # 1. 네비게이션/메뉴 링크에서 기능 탐색
    nav_links = await page.evaluate("""
        () => {
            const links = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href || '';
                const text = a.innerText.trim();
                if (href.includes('dongguk.edu') && text && !href.startsWith('javascript')) {
                    links.push({ text: text.substring(0, 80), href: href });
                }
            });
            return links;
        }
    """)

    seen_keys = set()
    for link in nav_links:
        for pattern, key, label in URL_PATTERNS:
            if re.search(pattern, link["href"]) and key not in seen_keys:
                seen_keys.add(key)
                scan.features.append(CourseFeature(
                    key=key, label=label, url=link["href"], feature_type="nav",
                ))

    # 2. 활동(activity) 모듈에서 기능 탐색
    activities = await page.evaluate("""
        () => {
            const items = [];
            document.querySelectorAll('.activity, [class*="modtype_"]').forEach(act => {
                const typeClass = [...act.classList].find(c => c.startsWith('modtype_')) || '';
                const modType = typeClass.replace('modtype_', '');
                const nameEl = act.querySelector('.instancename, .activityname, a');
                const link = act.querySelector('a[href]');
                if (modType) {
                    items.push({
                        type: modType,
                        name: nameEl ? nameEl.innerText.trim().substring(0, 80) : '',
                        url: link ? link.href : '',
                    });
                }
            });
            return items;
        }
    """)

    # 활동 타입 집계
    activity_types_found = set()
    for act in activities:
        mod_type = act["type"]
        if mod_type in ACTIVITY_TYPES:
            feat_key = f"activity_{ACTIVITY_TYPES[mod_type]}"
            activity_types_found.add(feat_key)

        # 다운로드 가능한 리소스 수집
        if mod_type in ("resource", "ubfile", "folder"):
            scan.downloadable_resources.append({
                "name": act["name"],
                "type": mod_type,
                "url": act["url"],
            })

    for feat_key in activity_types_found:
        if feat_key not in seen_keys:
            seen_keys.add(feat_key)
            scan.features.append(CourseFeature(
                key=feat_key,
                label=feat_key.replace("activity_", ""),
                url="",
                feature_type="activity",
            ))

    # 3. 게시판 목록 스캔
    if scan.has("boards"):
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
        GLOBAL_BOARD_IDS = {31, 32, 33}
        scan.boards = [b for b in board_links if b["id"] not in GLOBAL_BOARD_IDS]

    # 4. 학습자료실 게시판에서 첨부파일 링크 수집
    for board in scan.boards:
        if any(kw in board["name"] for kw in ("자료", "학습", "resource", "파일")):
            await page.goto(board["url"], wait_until="networkidle")
            file_links = await page.evaluate("""
                () => {
                    const files = [];
                    document.querySelectorAll('a[href*="article.php"]').forEach(a => {
                        files.push({
                            title: a.innerText.trim(),
                            url: a.href,
                            source: 'board',
                        });
                    });
                    return files;
                }
            """)
            for fl in file_links:
                fl["board_name"] = board["name"]
                scan.downloadable_resources.append(fl)

    print(f"  [SCAN] course={course_id}: "
          f"{len(scan.features)}개 기능, "
          f"{len(scan.boards)}개 게시판, "
          f"{len(scan.downloadable_resources)}개 다운로드 가능 리소스")

    return scan
