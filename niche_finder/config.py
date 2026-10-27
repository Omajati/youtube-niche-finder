"""Настройки: читаются из .env (или переменных окружения)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
RESULTS_FILE = DATA_DIR / "results.json"
QUOTA_FILE = DATA_DIR / "quota.json"


def _load_dotenv():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _int(name, default):
    return int(os.environ.get(name, default))


API_KEYS = [k.strip() for k in os.environ.get("YOUTUBE_API_KEYS", "").split(",") if k.strip()]

LANGUAGES = {"en": "English", "es": "Español", "de": "Deutsch", "fr": "Français"}

# Критерии отбора
MIN_DURATION_SEC = _int("MIN_DURATION_MIN", 8) * 60   # длинные ролики от 8 минут
SMALL_CHANNEL_MAX_SUBS = _int("SMALL_CHANNEL_MAX_SUBS", 200_000)
BIG_CHANNEL_SUBS = _int("BIG_CHANNEL_SUBS", 1_000_000)
NEW_CHANNEL_DAYS = _int("NEW_CHANNEL_DAYS", 90)       # «новый канал» = создан за 3 месяца
MIN_VIEWS = _int("MIN_VIEWS", 10_000)                # ролик с меньшим числом просмотров успехом не считается
NEW_CHANNEL_MIN_VIEWS = _int("NEW_CHANNEL_MIN_VIEWS", MIN_VIEWS)
SEARCH_PUBLISHED_DAYS = _int("SEARCH_PUBLISHED_DAYS", 180)  # ищем видео за последние N дней
# Отдельный поиск на каждую длительность: medium = 4–20 мин, long = больше 20 мин.
# Без фильтра выдача забита шортсами, а каждый поиск стоит 100 единиц квоты.
SEARCH_DURATIONS = [d.strip() for d in os.environ.get("SEARCH_DURATIONS", "medium,long").split(",") if d.strip()]

# Сколько живёт кэш ответов API (часы)
CACHE_TTL_HOURS = {
    "search": _int("CACHE_TTL_SEARCH_H", 72),
    "videos": _int("CACHE_TTL_VIDEOS_H", 24),
    "channels": _int("CACHE_TTL_CHANNELS_H", 72),
    "suggest": _int("CACHE_TTL_SUGGEST_H", 168),
}

# Стоимость запросов в единицах квоты (лимит 10 000 в день на ключ)
UNIT_COST = {"search": 100, "videos": 1, "channels": 1}
DAILY_QUOTA_PER_KEY = 10_000

PORT = _int("PORT", 8000)
