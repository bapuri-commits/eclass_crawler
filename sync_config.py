"""옵시디언 동기화 설정."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", r"G:\CS_Study\The Record"))
SCHOOL_DIR = "3_Areas/School"
DAILY_DIR = "1_Daily"
DAILY_TEMPLATE = "Templates/daily.md"

ECLASS_MARKER_START = "<!-- eclass-start -->"
ECLASS_MARKER_END = "<!-- eclass-end -->"

DEADLINE_LOOKAHEAD_DAYS = 7


def school_path() -> Path:
    return VAULT_PATH / SCHOOL_DIR


def daily_base() -> Path:
    return VAULT_PATH / DAILY_DIR


def sanitize_course_name(name: str) -> str:
    """과목 이름을 파일명으로 정규화한다.

    '자료구조 - 2분반 [컴퓨터·AI학부] (1학기)' → '자료구조'
    교수명, 분반, 학부, 학기 등 부가정보를 제거하고 핵심 과목명만 남긴다.
    """
    name = name.split(" - ")[0].strip()
    name = re.sub(r"\s*[\[\(].*?[\]\)]", "", name)
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    return name.strip()
