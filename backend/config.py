import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

STORAGE_ROOT = Path(
    os.getenv("STORAGE_ROOT", str(BASE_DIR / "storage"))
).resolve()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Lhf134652")
DB_NAME = os.getenv("DB_NAME", "shuijingTools")
DB_DRIVER = os.getenv("DB_DRIVER", "mysql").strip().lower()
SQLITE_DB_PATH = os.getenv(
    "SQLITE_DB_PATH",
    str(BASE_DIR / "shuijingtools.db"),
)

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8080"))
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(10 * 1024 * 1024 * 1024)))

DEFAULT_USERS = ["shuijing", "txt"]
