"""
동국대 이클래스 인증 모듈.
SSO 인증을 사용하므로 Playwright로 브라우저 로그인 후 세션을 확보한다.
"""

import json
import re
from pathlib import Path

from playwright.async_api import async_playwright
from config import BASE_URL, USERNAME, PASSWORD, REQUEST_TIMEOUT


SESSION_FILE = Path(__file__).parent / ".session.json"


class AuthError(Exception):
    pass


class EclassAuth:
    def __init__(self, username: str = "", password: str = ""):
        self.username = username or USERNAME
        self.password = password or PASSWORD
        self.cookies: list[dict] = []
        self.sesskey: str | None = None
        self.userid: int | None = None

        if not self.username or not self.password:
            raise AuthError(
                ".env 파일에 ECLASS_USERNAME과 ECLASS_PASSWORD를 입력해주세요."
            )

    async def login(self, headless: bool = True) -> "EclassAuth":
        """Playwright로 SSO 로그인 후 세션 쿠키를 확보한다."""
        print("[AUTH] Playwright 브라우저 로그인 시작...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()

            await page.goto(f"{BASE_URL}/login/index.php", wait_until="networkidle")
            print("[AUTH] 로그인 페이지 로드 완료")

            await page.fill('input[name="username"]', self.username)
            await page.fill('input[name="password"]', self.password)
            await page.click('button[type="submit"], input[type="submit"], #loginbtn')
            print("[AUTH] 로그인 정보 제출...")

            try:
                await page.wait_for_url(
                    f"{BASE_URL}/**",
                    timeout=REQUEST_TIMEOUT * 1000,
                )
                await page.wait_for_load_state("networkidle")
            except Exception:
                pass

            current_url = page.url
            print(f"[AUTH] 현재 URL: {current_url}")

            if "login" in current_url.lower() and "index.php" in current_url.lower():
                error_el = await page.query_selector(".alert-danger, .loginerrors, #loginerrormessage")
                error_msg = ""
                if error_el:
                    error_msg = await error_el.inner_text()
                await browser.close()
                raise AuthError(f"로그인 실패. {error_msg}".strip())

            self.cookies = await context.cookies()
            print(f"[AUTH] 쿠키 {len(self.cookies)}개 확보")

            try:
                self.sesskey = await page.evaluate(
                    "() => typeof M !== 'undefined' && M.cfg ? M.cfg.sesskey : null"
                )
            except Exception:
                pass

            if not self.sesskey:
                content = await page.content()
                match = re.search(r'"sesskey"\s*:\s*"([^"]+)"', content)
                if match:
                    self.sesskey = match.group(1)

            try:
                self.userid = await page.evaluate(
                    "() => typeof M !== 'undefined' && M.cfg ? M.cfg.userid : null"
                )
            except Exception:
                pass

            await browser.close()

        if self.sesskey:
            print(f"[AUTH] sesskey 확보: {self.sesskey[:10]}...")
        else:
            print("[AUTH] [경고] sesskey를 찾지 못했습니다.")

        if self.userid:
            print(f"[AUTH] userid: {self.userid}")

        self._save_session()
        print("[AUTH] 로그인 성공!")
        return self

    def _save_session(self):
        session_data = {
            "cookies": self.cookies,
            "sesskey": self.sesskey,
            "userid": self.userid,
        }
        SESSION_FILE.write_text(
            json.dumps(session_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_session(self) -> bool:
        if not SESSION_FILE.exists():
            return False
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            self.cookies = data.get("cookies", [])
            self.sesskey = data.get("sesskey")
            self.userid = data.get("userid")
            return bool(self.cookies)
        except Exception:
            return False

    def get_cookie_header(self) -> str:
        return "; ".join(f"{c['name']}={c['value']}" for c in self.cookies)

    def get_cookies_dict(self) -> dict[str, str]:
        return {c["name"]: c["value"] for c in self.cookies}


async def authenticate(username: str = "", password: str = "", headless: bool = True) -> EclassAuth:
    auth = EclassAuth(username, password)
    await auth.login(headless=headless)
    return auth


if __name__ == "__main__":
    import asyncio

    async def main():
        try:
            auth = await authenticate(headless=True)
            print(f"\n[결과] 쿠키 수: {len(auth.cookies)}")
            print(f"[결과] sesskey: {auth.sesskey}")
            print(f"[결과] userid: {auth.userid}")
            print(f"[결과] 주요 쿠키: {[c['name'] for c in auth.cookies]}")
        except AuthError as e:
            print(f"\n[에러] {e}")

    asyncio.run(main())
