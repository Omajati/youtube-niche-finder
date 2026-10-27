"""Настройки: читаются из data/.env, .env в корне (или переменных окружения)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
RESULTS_FILE = DATA_DIR / "results.json"
QUOTA_FILE = DATA_DIR / "quota.json"
VAULT_FILE = DATA_DIR / "vault.json"      # хранилище подходящих ниш
AUTO_FILE = DATA_DIR / "autopilot.json"   # очередь подниш и пройденные категории автопоиска
# Ключи, вписанные в настройках приложения, хранятся в data/.env: обновление папку data не трогает.
KEYS_FILE = DATA_DIR / ".env"


def _load_dotenv():
    for env_file in (KEYS_FILE, ROOT / ".env"):
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _int(name, default):
    return int(os.environ.get(name, default))


def _split_keys(text):
    return [k.strip() for k in text.replace("\n", ",").split(",") if k.strip()]


API_KEYS = _split_keys(os.environ.get("YOUTUBE_API_KEYS", ""))


def save_api_keys(text):
    """Сохраняет ключи из настроек приложения в data/.env и сразу начинает ими пользоваться."""
    keys = _split_keys(text)
    lines = []
    if KEYS_FILE.exists():
        lines = [l for l in KEYS_FILE.read_text(encoding="utf-8").splitlines()
                 if not l.strip().startswith("YOUTUBE_API_KEYS=")]
    lines.insert(0, "YOUTUBE_API_KEYS=" + ",".join(keys))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    API_KEYS[:] = keys
    return keys

LANGUAGES = {"en": "English", "es": "Español", "de": "Deutsch", "fr": "Français"}

# Критерии отбора
MIN_DURATION_SEC = _int("MIN_DURATION_MIN", 8) * 60   # длинные ролики от 8 минут
SMALL_CHANNEL_MAX_SUBS = _int("SMALL_CHANNEL_MAX_SUBS", 200_000)
BIG_CHANNEL_SUBS = _int("BIG_CHANNEL_SUBS", 1_000_000)
NEW_CHANNEL_DAYS = _int("NEW_CHANNEL_DAYS", 90)       # «новый канал» = первый ролик за последние 3 месяца
# Каналы из этих стран не смотрим совсем (Индия и соседи): ни как примеры, ни как конкурентов.
EXCLUDE_COUNTRIES = {c.strip().upper() for c in os.environ.get("EXCLUDE_COUNTRIES", "IN,PK,BD,NP,LK").split(",")
                     if c.strip()}
# Ролик с меньшим числом просмотров успехом не считается. Рынки ES/DE/FR меньше английского, порог ниже.
MIN_VIEWS = {
    "en": _int("MIN_VIEWS_EN", _int("MIN_VIEWS", 10_000)),
    "es": _int("MIN_VIEWS_ES", _int("MIN_VIEWS", 5_000)),
    "de": _int("MIN_VIEWS_DE", _int("MIN_VIEWS", 5_000)),
    "fr": _int("MIN_VIEWS_FR", _int("MIN_VIEWS", 5_000)),
}
MIN_VIDEO_AGE_DAYS = _int("MIN_VIDEO_AGE_DAYS", 14)  # свежие ролики без порога ещё не успели, их не оцениваем
UPLOADS_CHECK_CHANNELS = _int("UPLOADS_CHECK_CHANNELS", 40)  # у скольких малых каналов смотреть последние ролики
SEARCH_PUBLISHED_DAYS = _int("SEARCH_PUBLISHED_DAYS", 180)  # ищем видео за последние N дней
# Отдельный поиск на каждую длительность: medium = 4–20 мин, long = больше 20 мин.
# Без фильтра выдача забита шортсами, а каждый поиск стоит 100 единиц квоты.
SEARCH_DURATIONS = [d.strip() for d in os.environ.get("SEARCH_DURATIONS", "medium,long").split(",") if d.strip()]

# Сколько живёт кэш ответов API (часы)
CACHE_TTL_HOURS = {
    "search": _int("CACHE_TTL_SEARCH_H", 72),
    "videos": _int("CACHE_TTL_VIDEOS_H", 24),
    "channels": _int("CACHE_TTL_CHANNELS_H", 72),
    "playlistItems": _int("CACHE_TTL_UPLOADS_H", 72),
    "suggest": _int("CACHE_TTL_SUGGEST_H", 168),
}

# Стоимость запросов в единицах квоты (лимит 10 000 в день на ключ)
UNIT_COST = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1}
DAILY_QUOTA_PER_KEY = 10_000

PORT = _int("PORT", 8766)
