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
SETTINGS_FILE = DATA_DIR / "settings.json"
REPORTS_FILE = DATA_DIR / "reports.json"    # разборы ниш и конкурентов через Claude  # настройки анализа из окна «Настройки анализа»


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
# Ключ Claude API для разборов ниш и конкурентов (console.anthropic.com), оплачивается отдельно от подписки
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()


def _save_env_line(name, value):
    lines = []
    if KEYS_FILE.exists():
        lines = [l for l in KEYS_FILE.read_text(encoding="utf-8").splitlines()
                 if not l.strip().startswith(name + "=")]
    lines.insert(0, f"{name}={value}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_api_keys(text):
    """Сохраняет ключи из настроек приложения в data/.env и сразу начинает ими пользоваться."""
    keys = _split_keys(text)
    _save_env_line("YOUTUBE_API_KEYS", ",".join(keys))
    API_KEYS[:] = keys
    return keys


def save_anthropic_key(text):
    global ANTHROPIC_API_KEY
    ANTHROPIC_API_KEY = text.strip()
    _save_env_line("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY)
    return bool(ANTHROPIC_API_KEY)

LANGUAGES = {"en": "English", "es": "Español", "de": "Deutsch", "fr": "Français", "ru": "Русский"}

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
    "ru": _int("MIN_VIEWS_RU", _int("MIN_VIEWS", 10_000)),
}
MIN_VIDEO_AGE_DAYS = _int("MIN_VIDEO_AGE_DAYS", 14)  # свежие ролики без порога ещё не успели, их не оцениваем
UPLOADS_CHECK_CHANNELS = _int("UPLOADS_CHECK_CHANNELS", 40)  # у скольких малых каналов смотреть последние ролики
SEARCH_PUBLISHED_DAYS = _int("SEARCH_PUBLISHED_DAYS", 180)  # ищем видео за последние N дней
# Отдельный поиск на каждую длительность: medium = 4–20 мин, long = больше 20 мин.
# Без фильтра выдача забита шортсами, а каждый поиск стоит 100 единиц квоты.
SEARCH_DURATIONS = [d.strip() for d in os.environ.get("SEARCH_DURATIONS", "medium,long").split(",") if d.strip()]

# Цели оценки: при каком значении критерий получает максимум
RATIO_TARGET = float(os.environ.get("RATIO_TARGET", 10))   # медиана «просмотры / подписчики» → максимум
NEW_CHANNELS_TARGET = _int("NEW_CHANNELS_TARGET", 3)      # столько новых каналов с успешным роликом → максимум
BIG_SHARE_MAX = _int("BIG_SHARE_MAX", 40)                 # доля миллионников в %, при которой конкуренция = 0
SATURATION_LOW = _int("SATURATION_LOW", 2_000)            # роликов по теме на YouTube: до стольких тема узкая
SATURATION_HIGH = _int("SATURATION_HIGH", 200_000)        # от стольких тема массовая
EVERGREEN_AGE_DAYS = _int("EVERGREEN_AGE_DAYS", 60)       # успешный ролик старше этого: его смотрят долго
LOW_DATA_MIN_HITS = _int("LOW_DATA_MIN_HITS", 3)          # меньше успешных роликов малых каналов → «мало данных»
VAULT_MIN_SCORE = _int("VAULT_MIN_SCORE", 65)             # с таким баллом ниша сама попадает в хранилище

# Доход: RPM (доллары на 1000 просмотров длинных роликов) по рынкам. Точный RPM видит только владелец канала,
# это средняя оценка для познавательных тем; у категорий есть свой множитель (catalog.py)
# В России монетизация YouTube для местных каналов отключена с 2022 года: RPM русскоязычной аудитории низкий,
# доход обычно идёт с интеграций и донатов (Boosty и т.п.)
RPM = {"en": 6.0, "de": 5.0, "fr": 4.0, "es": 2.5, "ru": 0.7}
RETENTION_PCT = _int("RETENTION_PCT", 35)   # среднее удержание для оценки часов просмотра, %

# Модели Claude для разборов: цена в долларах за миллион токенов (вход, выход)
CLAUDE_MODELS = {
    "claude-opus-5-5": {"name": "Opus 5.5 (умнее)", "in": 4.0, "out": 20.0},
    "claude-sonnet-5-5": {"name": "Sonnet 5.5 (дешевле)", "in": 2.0, "out": 10.0},
}
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")

# Веса критериев в итоговом балле (нормируются, сумма может быть любой)
WEIGHTS = {"outlier": 30, "new_channels": 20, "competition": 15, "evergreen": 15, "stability": 10, "format": 10}

# Сколько живёт кэш ответов API (часы)
CACHE_TTL_HOURS = {
    "search": _int("CACHE_TTL_SEARCH_H", 72),
    "videos": _int("CACHE_TTL_VIDEOS_H", 24),
    "channels": _int("CACHE_TTL_CHANNELS_H", 72),
    "playlistItems": _int("CACHE_TTL_UPLOADS_H", 72),
    "suggest": _int("CACHE_TTL_SUGGEST_H", 168),
    "commentThreads": _int("CACHE_TTL_COMMENTS_H", 72),
}

# Стоимость запросов в единицах квоты (лимит 10 000 в день на ключ)
UNIT_COST = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1, "commentThreads": 1}
DAILY_QUOTA_PER_KEY = 10_000

PORT = _int("PORT", 8766)


# --- настройки анализа, которые меняются в программе ---
# (ключ, группа, подпись, тип, минимум, максимум, подсказка)
DURATION_CHOICES = {"medium,long": "4–20 мин и 20+ мин (2 поиска)", "long": "только 20+ мин (дешевле вдвое)",
                    "medium": "только 4–20 мин"}
SETTINGS_SPEC = [
    ("min_duration_min", "Видео", "Минимальная длина ролика, мин", "int", 1, 120, "Ролики короче не смотрим совсем"),
    ("min_views_en", "Видео", "Порог успеха EN, просмотров", "int", 0, 10_000_000, "Ролик ниже порога успешным не считается"),
    ("min_views_es", "Видео", "Порог успеха ES, просмотров", "int", 0, 10_000_000, ""),
    ("min_views_de", "Видео", "Порог успеха DE, просмотров", "int", 0, 10_000_000, ""),
    ("min_views_fr", "Видео", "Порог успеха FR, просмотров", "int", 0, 10_000_000, ""),
    ("min_views_ru", "Видео", "Порог успеха RU, просмотров", "int", 0, 10_000_000, ""),
    ("min_video_age_days", "Видео", "Свежий ролик без порога не учитывать, дней", "int", 0, 90,
     "Ролик младше этого, ещё не набравший порог, просто не успел"),
    ("evergreen_age_days", "Видео", "Ролик «долгоиграющий», если старше, дней", "int", 7, 365,
     "Для оценки вечнозелёности"),
    ("search_published_days", "Поиск", "Искать ролики за последние, дней", "int", 7, 3650, ""),
    ("search_durations", "Поиск", "Какие длины искать", "choice", None, None, "Каждый поиск стоит 100 единиц"),
    ("uploads_check_channels", "Поиск", "У скольких малых каналов смотреть все ролики", "int", 0, 50,
     "Точная частота загрузок и дата первого ролика, 1 единица на канал"),
    ("small_channel_max_subs", "Каналы", "«Малый канал» до, подписчиков", "int", 100, 10_000_000,
     "Ориентиры и расчёт «просмотры / подписчики» только по ним"),
    ("big_channel_subs", "Каналы", "«Крупный конкурент» от, подписчиков", "int", 1000, 100_000_000, ""),
    ("new_channel_days", "Каналы", "«Новый канал»: первый ролик за последние, дней", "int", 7, 730, ""),
    ("exclude_countries", "Каналы", "Не учитывать каналы из стран", "text", None, None,
     "Коды стран через запятую, например IN,PK,BD"),
    ("ratio_target", "Цели оценки", "Просмотры/подписчики для максимума, ×", "float", 1, 1000, ""),
    ("new_channels_target", "Цели оценки", "Новых успешных каналов для максимума", "int", 1, 50, ""),
    ("big_share_max", "Цели оценки", "Доля миллионников, при которой конкуренция = 0, %", "int", 1, 100, ""),
    ("saturation_low", "Цели оценки", "Тема узкая, если роликов на YouTube до", "int", 10, 10_000_000, ""),
    ("saturation_high", "Цели оценки", "Тема массовая, если роликов от", "int", 100, 100_000_000, ""),
    ("low_data_min_hits", "Цели оценки", "«Мало данных», если успешных роликов меньше", "int", 1, 50, ""),
    ("weight_outlier", "Веса критериев", "Просмотры ≫ подписчики", "int", 0, 100, ""),
    ("weight_new_channels", "Веса критериев", "Новые каналы растут", "int", 0, 100, ""),
    ("weight_competition", "Веса критериев", "Мало конкурентов", "int", 0, 100, ""),
    ("weight_evergreen", "Веса критериев", "Вечнозелёность", "int", 0, 100, ""),
    ("weight_stability", "Веса критериев", "Стабильный спрос", "int", 0, 100, ""),
    ("weight_format", "Веса критериев", "Формат и нагрузка", "int", 0, 100, ""),
    ("rpm_en", "Доход", "RPM EN, $ за 1000 просмотров", "float", 0, 100, "Средняя оценка, точный RPM видит только владелец канала"),
    ("rpm_es", "Доход", "RPM ES, $ за 1000 просмотров", "float", 0, 100, ""),
    ("rpm_de", "Доход", "RPM DE, $ за 1000 просмотров", "float", 0, 100, ""),
    ("rpm_fr", "Доход", "RPM FR, $ за 1000 просмотров", "float", 0, 100, ""),
    ("rpm_ru", "Доход", "RPM RU, $ за 1000 просмотров", "float", 0, 100,
     "Монетизация в России отключена, доход в основном с интеграций"),
    ("retention_pct", "Доход", "Среднее удержание для оценки часов, %", "int", 5, 90,
     "Для монетизации нужно 4000 часов просмотра за год"),
    ("claude_model", "Разборы Claude", "Модель по умолчанию", "choice", None, None,
     "Можно поменять у каждой кнопки разбора"),
    ("vault_min_score", "Хранилище", "Сама попадает в хранилище от балла", "int", 0, 101, "101 = только вручную"),
]
# Настройки, от которых зависит, что ищется, а не как оценивается: их смена требует новых поисков (квота)
SEARCH_SETTINGS = {"search_published_days", "search_durations"}
CHOICES = {"search_durations": DURATION_CHOICES,
           "claude_model": {k: v["name"] for k, v in CLAUDE_MODELS.items()}}

_ATTRS = {"min_video_age_days": "MIN_VIDEO_AGE_DAYS", "evergreen_age_days": "EVERGREEN_AGE_DAYS",
          "search_published_days": "SEARCH_PUBLISHED_DAYS", "uploads_check_channels": "UPLOADS_CHECK_CHANNELS",
          "small_channel_max_subs": "SMALL_CHANNEL_MAX_SUBS", "big_channel_subs": "BIG_CHANNEL_SUBS",
          "new_channel_days": "NEW_CHANNEL_DAYS", "ratio_target": "RATIO_TARGET",
          "new_channels_target": "NEW_CHANNELS_TARGET", "big_share_max": "BIG_SHARE_MAX",
          "saturation_low": "SATURATION_LOW", "saturation_high": "SATURATION_HIGH",
          "low_data_min_hits": "LOW_DATA_MIN_HITS", "vault_min_score": "VAULT_MIN_SCORE",
          "retention_pct": "RETENTION_PCT", "claude_model": "CLAUDE_MODEL"}


def _get_setting(key):
    g = globals()
    if key == "min_duration_min":
        return MIN_DURATION_SEC // 60
    if key.startswith("min_views_"):
        return MIN_VIEWS[key[-2:]]
    if key.startswith("rpm_"):
        return RPM[key[-2:]]
    if key.startswith("weight_"):
        return WEIGHTS[key[len("weight_"):]]
    if key == "search_durations":
        return ",".join(SEARCH_DURATIONS)
    if key == "exclude_countries":
        return ",".join(sorted(EXCLUDE_COUNTRIES))
    return g[_ATTRS[key]]


def _set_setting(key, value):
    g = globals()
    if key == "min_duration_min":
        g["MIN_DURATION_SEC"] = value * 60
    elif key.startswith("min_views_"):
        MIN_VIEWS[key[-2:]] = value
    elif key.startswith("rpm_"):
        RPM[key[-2:]] = value
    elif key.startswith("weight_"):
        WEIGHTS[key[len("weight_"):]] = value
    elif key == "search_durations":
        SEARCH_DURATIONS[:] = value.split(",")
    elif key == "exclude_countries":
        EXCLUDE_COUNTRIES.clear()
        EXCLUDE_COUNTRIES.update(value.split(",") if value else [])
    else:
        g[_ATTRS[key]] = value


def _clean(spec, value):
    key, _, _, kind, lo, hi, _ = spec
    if kind == "choice":
        value = str(value)
        if value not in CHOICES[key]:
            raise ValueError(key)
        return value
    if kind == "text":
        return ",".join(c.strip().upper() for c in str(value).split(",") if c.strip())
    value = float(value) if kind == "float" else int(float(value))
    return min(max(value, lo), hi)


SETTINGS_DEFAULTS = {spec[0]: _get_setting(spec[0]) for spec in SETTINGS_SPEC}


def current_settings():
    return {spec[0]: _get_setting(spec[0]) for spec in SETTINGS_SPEC}


def apply_settings(values):
    """Проверяет и применяет настройки. Возвращает ключи, которые реально изменились."""
    changed = []
    for spec in SETTINGS_SPEC:
        key = spec[0]
        if key not in values:
            continue
        try:
            value = _clean(spec, values[key])
        except (TypeError, ValueError):
            continue
        if value != _get_setting(key):
            _set_setting(key, value)
            changed.append(key)
    if sum(WEIGHTS.values()) <= 0:   # все веса в ноль оценку сломают
        WEIGHTS.update({k: 1 for k in WEIGHTS})
    return changed


def save_settings(values):
    """Применяет и сохраняет в data/settings.json только то, что отличается от значений по умолчанию."""
    import json
    changed = apply_settings(values)
    overrides = {k: v for k, v in current_settings().items() if v != SETTINGS_DEFAULTS[k]}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(overrides, ensure_ascii=False, indent=1), encoding="utf-8")
    return changed


def reset_settings():
    changed = apply_settings(SETTINGS_DEFAULTS)
    try:
        SETTINGS_FILE.unlink()
    except OSError:
        pass
    return changed


def _load_settings():
    import json
    try:
        apply_settings(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass


_load_settings()
