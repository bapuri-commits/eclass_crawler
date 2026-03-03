"""
수업자료 다운로드 추출기.
Moodle resource/folder 활동 및 게시판 첨부파일을 다운로드한다.
"""

import asyncio
import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from config import BASE_URL, REQUEST_DELAY

# Windows cp949 콘솔에서 한글 출력 시 UnicodeEncodeError 방지
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DOWNLOADS_DIR = Path(__file__).parent.parent / "output" / "downloads"


def _safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\n\r]', '', name).strip()
    name = name[:120] if name else "unnamed"
    return name


def _unique_path(dest_dir: Path, filename: str) -> Path:
    save_path = dest_dir / filename
    counter = 1
    original = save_path
    while save_path.exists():
        save_path = dest_dir / f"{original.stem}_{counter}{original.suffix}"
        counter += 1
    return save_path


async def download_materials(
    page,
    course_id: int,
    course_name: str,
    downloadable_resources: list[dict],
) -> list[dict]:
    if not downloadable_resources:
        print(f"  [MATERIALS] course={course_id}: 다운로드할 자료 없음")
        return []

    course_dir = DOWNLOADS_DIR / _safe_filename(course_name)
    course_dir.mkdir(parents=True, exist_ok=True)

    results = []
    seen_urls = set()

    for res in downloadable_resources:
        url = res.get("url", "")
        name = res.get("name") or res.get("title", "")
        source_type = res.get("type") or res.get("source", "unknown")

        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        try:
            if source_type == "board":
                files = await _download_board_attachments(page, url, name, course_dir)
                results.extend(files)
            elif source_type == "folder":
                files = await _download_folder(page, url, name, course_dir)
                results.extend(files)
            else:
                file_info = await _download_resource(page, url, name, course_dir)
                if file_info:
                    results.append(file_info)
                else:
                    print(f"    [SKIP] {name}: 다운로드 가능한 파일 없음")
        except Exception as e:
            print(f"    [에러] 다운로드 실패 ({name}): {e}")
            results.append({"name": name, "url": url, "error": str(e)})

        await asyncio.sleep(REQUEST_DELAY)

    success = len([r for r in results if "path" in r])
    total = len(results)
    print(f"  [MATERIALS] course={course_id}: {success}/{total}개 파일 다운로드 완료")
    return results


async def _download_folder(page, url: str, name: str, dest_dir: Path) -> list[dict]:
    """Moodle folder 모듈 페이지에서 파일들을 다운로드한다."""
    await page.goto(url, wait_until="networkidle")

    file_links = await page.evaluate("""
        () => {
            const files = [];
            // Moodle folder: pluginfile.php 링크 또는 다운로드 아이콘
            document.querySelectorAll(
                'a[href*="pluginfile.php"], ' +
                'a[href*="forcedownload"], ' +
                '.fp-filename a[href], ' +
                '.folder-content a[href], ' +
                '.foldertree a[href], ' +
                'span.fp-filename-icon a[href]'
            ).forEach(a => {
                const href = a.href;
                if (href && !href.startsWith('javascript')) {
                    files.push({ text: a.innerText.trim(), href: href });
                }
            });
            return files;
        }
    """)

    if not file_links:
        print(f"    [폴더] {name}: 파일 없음")
        return []

    # 중복 URL 제거 + 폴더 자기 자신 링크 제외
    seen = set()
    unique_links = []
    for fl in file_links:
        href = fl["href"].rstrip("#")
        if href not in seen and "pluginfile.php" in href:
            seen.add(href)
            fl["href"] = href
            unique_links.append(fl)

    print(f"    [폴더] {name}: {len(unique_links)}개 파일 발견")
    results = []
    for fl in unique_links:
        info = await _try_download(page, fl["href"], fl["text"] or name, dest_dir)
        if info:
            results.append(info)
        await asyncio.sleep(REQUEST_DELAY * 0.5)

    return results


async def _download_resource(page, url: str, name: str, dest_dir: Path) -> dict | None:
    """Moodle resource (파일) 활동에서 파일을 다운로드한다."""
    info = await _try_download(page, url, name, dest_dir)
    if info:
        return info

    # 다운로드가 트리거되지 않으면 페이지에서 파일 링크 찾기
    await page.goto(url, wait_until="networkidle")
    file_links = await page.evaluate("""
        () => {
            const links = [];
            document.querySelectorAll(
                'a[href*="pluginfile.php"], a[href*="forcedownload"]'
            ).forEach(a => {
                links.push({ text: a.innerText.trim(), href: a.href });
            });
            return links;
        }
    """)

    if file_links:
        return await _try_download(page, file_links[0]["href"], name, dest_dir)

    return None


async def _download_board_attachments(
    page, article_url: str, title: str, dest_dir: Path,
) -> list[dict]:
    """게시판 글의 첨부파일들을 다운로드한다."""
    await page.goto(article_url, wait_until="networkidle")

    attachments = await page.evaluate("""
        () => {
            const files = [];
            // ubboard 첨부파일 - 다양한 셀렉터 시도
            document.querySelectorAll(
                'a[href*="pluginfile.php"], ' +
                'a[href*="forcedownload"], ' +
                '.attachments a[href], ' +
                '.file-attachment a[href], ' +
                'a.ubboard_file_download[href], ' +
                '.board_view_content a[href*="file"], ' +
                '.ubboard_article a[href*="download"], ' +
                'a[href*="mod_ubboard"]'
            ).forEach(a => {
                const href = a.href;
                if (href && !href.startsWith('javascript')) {
                    files.push({ text: a.innerText.trim(), href: href });
                }
            });
            return files;
        }
    """)

    if not attachments:
        print(f"    [게시판] {title}: 첨부파일 없음")
        return []

    # 중복 제거
    seen = set()
    unique = []
    for att in attachments:
        if att["href"] not in seen:
            seen.add(att["href"])
            unique.append(att)

    results = []
    for att in unique:
        info = await _try_download(page, att["href"], att["text"] or title, dest_dir)
        if info:
            info["board_article"] = title
            results.append(info)
        await asyncio.sleep(REQUEST_DELAY * 0.5)

    return results


async def _try_download(page, url: str, name: str, dest_dir: Path) -> dict | None:
    """파일 다운로드를 시도한다. Playwright download -> API fetch 순서로 폴백."""
    # pluginfile.php URL에 forcedownload 추가
    dl_url = url
    if "pluginfile.php" in url and "forcedownload" not in url:
        sep = "&" if "?" in url else "?"
        dl_url = f"{url}{sep}forcedownload=1"

    # 1차: Playwright download 이벤트
    try:
        async with page.expect_download(timeout=10000) as download_info:
            await page.goto(dl_url)

        download = await download_info.value
        suggested = download.suggested_filename
        if not suggested:
            parsed = urlparse(url)
            suggested = unquote(parsed.path.split("/")[-1]) or _safe_filename(name)

        save_path = _unique_path(dest_dir, suggested)
        await download.save_as(str(save_path))
        size_kb = save_path.stat().st_size / 1024
        print(f"    -> {save_path.name} ({size_kb:.1f}KB)")

        return {
            "name": name,
            "filename": save_path.name,
            "path": str(save_path),
            "size_kb": round(size_kb, 1),
            "url": url,
        }
    except Exception:
        pass

    # 2차: Playwright API request (브라우저 컨텍스트 쿠키 자동 사용)
    try:
        response = await page.context.request.get(dl_url)
        if response.ok:
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                return None

            # URL 경로에서 파일명 추출 (가장 신뢰할 수 있는 소스)
            parsed = urlparse(url)
            filename = unquote(parsed.path.split("/")[-1], encoding="utf-8")
            if not filename or "." not in filename:
                filename = _safe_filename(name)
                ext = _guess_extension(content_type)
                if ext and not filename.endswith(ext):
                    filename += ext

            save_path = _unique_path(dest_dir, filename)
            body = await response.body()
            save_path.write_bytes(body)
            size_kb = len(body) / 1024
            print(f"    -> {filename} ({size_kb:.1f}KB)")

            return {
                "name": name,
                "filename": filename,
                "path": str(save_path),
                "size_kb": round(size_kb, 1),
                "url": url,
            }
    except Exception as e:
        print(f"      [API fetch 실패] {type(e).__name__}")

    return None


def _guess_extension(content_type: str) -> str:
    ct_map = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        "application/vnd.ms-powerpoint": ".ppt",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/zip": ".zip",
        "image/png": ".png",
        "image/jpeg": ".jpg",
    }
    for ct, ext in ct_map.items():
        if ct in content_type:
            return ext
    return ""
