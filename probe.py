"""
Moodle 내부 API 탐색 도구.
SSO 로그인 세션 쿠키를 사용하여 Moodle AJAX API를 호출한다.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import httpx
from auth import authenticate, AuthError
from config import BASE_URL, REQUEST_TIMEOUT, REQUEST_DELAY

OUTPUT_DIR = Path(__file__).parent / "output"
AJAX_ENDPOINT = f"{BASE_URL}/lib/ajax/service.php"

PROBE_FUNCTIONS = [
    "core_webservice_get_site_info",
    "core_enrol_get_users_courses",
    "core_course_get_contents",
    "core_course_get_enrolled_courses_by_timeline_field",
    "mod_assign_get_assignments",
    "mod_assign_get_submissions",
    "gradereport_user_get_grade_items",
    "gradereport_overview_get_course_grades",
    "core_calendar_get_calendar_events",
    "core_calendar_get_action_events_by_timesort",
    "core_message_get_messages",
    "mod_forum_get_forums_by_courses",
    "mod_resource_get_resources_by_courses",
    "mod_url_get_urls_by_courses",
    "mod_page_get_pages_by_courses",
    "mod_quiz_get_quizzes_by_courses",
    "core_completion_get_activities_completion_status",
    "core_course_get_updates_since",
    "core_block_get_dashboard_blocks",
]


async def call_ajax(
    client: httpx.AsyncClient,
    sesskey: str,
    function: str,
    args: dict | None = None,
) -> dict:
    """Moodle AJAX 서비스를 호출한다 (세션 쿠키 인증)."""
    payload = [
        {
            "index": 0,
            "methodname": function,
            "args": args or {},
        }
    ]

    response = await client.post(
        AJAX_ENDPOINT,
        params={"sesskey": sesskey, "info": function},
        json=payload,
    )
    response.raise_for_status()
    data = response.json()

    if isinstance(data, list) and len(data) > 0:
        item = data[0]
        if item.get("error"):
            return {"exception": True, "errorcode": item.get("exception", {}).get("errorcode", ""), "message": item.get("exception", {}).get("message", str(item))}
        return item.get("data", item)

    return data


async def probe_function(
    client: httpx.AsyncClient,
    sesskey: str,
    function: str,
) -> dict:
    """단일 API 함수의 사용 가능 여부를 테스트한다."""
    try:
        result = await call_ajax(client, sesskey, function)

        if isinstance(result, dict) and result.get("exception"):
            return {
                "function": function,
                "available": False,
                "error_code": result.get("errorcode", ""),
                "error": result.get("message", str(result)),
            }

        return {
            "function": function,
            "available": True,
            "sample_keys": _extract_keys(result),
        }

    except Exception as e:
        return {
            "function": function,
            "available": False,
            "error": str(e),
        }


def _extract_keys(data) -> list[str]:
    """응답 데이터의 최상위 구조를 요약한다."""
    if isinstance(data, dict):
        return list(data.keys())[:20]
    if isinstance(data, list) and len(data) > 0:
        first = data[0]
        if isinstance(first, dict):
            return [f"list[{len(data)}] -> {list(first.keys())[:10]}"]
        return [f"list[{len(data)}] -> {type(first).__name__}"]
    if isinstance(data, list):
        return ["empty list"]
    return [str(type(data).__name__)]


async def run_probe():
    """전체 API 탐색을 실행하고 결과를 저장한다."""
    print("=" * 60)
    print("  Moodle AJAX API 탐색 (세션 쿠키 기반)")
    print("=" * 60)

    auth = await authenticate(headless=True)

    if not auth.sesskey:
        print("[에러] sesskey가 없어서 AJAX API를 호출할 수 없습니다.")
        print("       브라우저 기반 크롤링만 가능합니다.")
        return None

    available = []
    unavailable = []

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        cookies=auth.get_cookies_dict(),
        headers={"Content-Type": "application/json"},
    ) as client:

        print(f"\nAPI 함수 {len(PROBE_FUNCTIONS)}개 탐색 중...")
        for i, func in enumerate(PROBE_FUNCTIONS, 1):
            result = await probe_function(client, auth.sesskey, func)
            status = "OK" if result["available"] else "FAIL"
            print(f"  [{i:2d}/{len(PROBE_FUNCTIONS)}] {status:4s} | {func}")

            if result["available"]:
                available.append(result)
            else:
                unavailable.append(result)

            await asyncio.sleep(REQUEST_DELAY)

    # 결과 저장
    report = {
        "probed_at": datetime.now().isoformat(),
        "auth_method": "playwright_sso",
        "userid": auth.userid,
        "probe_results": {
            "total_tested": len(PROBE_FUNCTIONS),
            "available_count": len(available),
            "unavailable_count": len(unavailable),
        },
        "available": available,
        "unavailable": unavailable,
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / "api_probe_result.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 요약
    print("\n" + "=" * 60)
    print("  탐색 결과 요약")
    print("=" * 60)
    print(f"  테스트: {len(PROBE_FUNCTIONS)}개")
    print(f"  사용 가능: {len(available)}개")
    print(f"  사용 불가: {len(unavailable)}개")

    if available:
        print("\n  [사용 가능한 함수]")
        for item in available:
            print(f"    - {item['function']}")
            if item.get("sample_keys"):
                print(f"      keys: {item['sample_keys']}")

    print(f"\n  전체 결과 저장: {output_path}")
    return report


if __name__ == "__main__":
    asyncio.run(run_probe())
