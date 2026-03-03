"""
브라우저 세션 매니저.
Playwright 로그인을 한 번 수행한 뒤, 여러 페이지를 탐색하며 데이터를 추출할 수 있게 한다.
"""

import asyncio
import re

from playwright.async_api import async_playwright, Browser, Page
from config import BASE_URL, USERNAME, PASSWORD, REQUEST_DELAY, REQUEST_TIMEOUT


class BrowserSession:
    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._logged_in = False
        self.sesskey: str | None = None
        self.cookies_dict: dict[str, str] = {}

    async def start(self, headless: bool = True):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)
        context = await self._browser.new_context()
        self._page = await context.new_page()
        return self

    async def login(self, username: str = "", password: str = ""):
        username = username or USERNAME
        password = password or PASSWORD

        if not username or not password:
            raise RuntimeError(".env에 ECLASS_USERNAME/ECLASS_PASSWORD를 입력해주세요.")

        await self._page.goto(f"{BASE_URL}/login/index.php", wait_until="networkidle")
        await self._page.fill('input[name="username"]', username)
        await self._page.fill('input[name="password"]', password)
        await self._page.click('button[type="submit"], input[type="submit"], #loginbtn')
        await self._page.wait_for_load_state("networkidle")

        if "login" in self._page.url and "index.php" in self._page.url:
            raise RuntimeError("로그인 실패 - ID/PW를 확인해주세요.")

        self._logged_in = True

        # sesskey 추출
        try:
            self.sesskey = await self._page.evaluate(
                "() => typeof M !== 'undefined' && M.cfg ? M.cfg.sesskey : null"
            )
        except Exception:
            pass
        if not self.sesskey:
            content = await self._page.content()
            match = re.search(r'"sesskey"\s*:\s*"([^"]+)"', content)
            if match:
                self.sesskey = match.group(1)

        # 쿠키 딕셔너리
        cookies = await self._page.context.cookies()
        self.cookies_dict = {c["name"]: c["value"] for c in cookies}

        print(f"[SESSION] 로그인 성공: {self._page.url}")

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("브라우저가 시작되지 않았습니다. start()를 먼저 호출하세요.")
        return self._page

    async def goto(self, url: str, delay: float = REQUEST_DELAY) -> Page:
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            await self._page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
        except Exception as e:
            print(f"[SESSION] 페이지 로드 실패 ({url}): {e}")
            raise
        return self._page

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


async def create_session(headless: bool = True) -> BrowserSession:
    session = BrowserSession()
    await session.start(headless=headless)
    await session.login()
    return session
