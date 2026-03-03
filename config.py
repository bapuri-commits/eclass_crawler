import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://eclass.dongguk.edu"

USERNAME = os.getenv("ECLASS_USERNAME", "")
PASSWORD = os.getenv("ECLASS_PASSWORD", "")

CURRENT_SEMESTER = "2026-1"

REQUEST_DELAY = 0.5
REQUEST_TIMEOUT = 30.0

GLOBAL_BOARD_IDS = {31, 32, 33}

MIN_DOWNLOAD_SIZE_BYTES = 512
