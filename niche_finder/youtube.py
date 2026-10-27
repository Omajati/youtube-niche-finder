"""Клиент YouTube Data API v3: ротация ключей при исчерпании квоты и кэш на диске."""
import hashlib
import json
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import config

API_BASE = "https://www.googleapis.com/youtube/v3/"
SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"


def ssl_context():
    """Сертификаты из certifi, если он есть: у Python из приложения системных сертификатов может не быть."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def http_get(url, timeout=30, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "youtube-niche-finder/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
        return resp.read()


class QuotaExhausted(Exception):
    """Все ключи исчерпали дневную квоту."""


class NoApiKeys(Exception):
    pass


class NotFound(Exception):
    pass


def _quota_day():
    # Квота YouTube сбрасывается в полночь по тихоокеанскому времени.
    # Берём UTC-8 круглый год: летом это на час позже реального сброса, зато никогда не раньше.
    return (datetime.now(timezone.utc) - timedelta(hours=8)).date().isoformat()


def _key_id(key):
    return hashlib.sha1(key.encode()).hexdigest()[:8]


class Cache:
    def __init__(self, directory=config.CACHE_DIR):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, kind, params):
        raw = kind + json.dumps(params, sort_keys=True, ensure_ascii=False)
        return self.dir / f"{kind}_{hashlib.sha1(raw.encode()).hexdigest()}.json"

    def get(self, kind, params):
        path = self._path(kind, params)
        if not path.exists():
            return None
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if time.time() - item["saved_at"] > config.CACHE_TTL_HOURS[kind] * 3600:
            return None
        return item["data"]

    def set(self, kind, params, data):
        path = self._path(kind, params)
        path.write_text(json.dumps({"saved_at": time.time(), "data": data}, ensure_ascii=False), encoding="utf-8")


class QuotaTracker:
    """Учёт потраченных единиц и исчерпанных ключей за текущие сутки (data/quota.json)."""

    def __init__(self, keys, path=config.QUOTA_FILE):
        self.keys = keys
        self.path = path
        self.lock = threading.Lock()
        self.state = self._load()

    def _load(self):
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        if state.get("day") != _quota_day():
            state = {"day": _quota_day(), "keys": {}}
        return state

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def _entry(self, key):
        if self.state.get("day") != _quota_day():
            self.state = {"day": _quota_day(), "keys": {}}
        return self.state["keys"].setdefault(_key_id(key), {"used": 0, "exhausted": False, "invalid": False})

    def available(self, key):
        e = self._entry(key)
        return not e["exhausted"] and not e["invalid"]

    def add_usage(self, key, units):
        with self.lock:
            self._entry(key)["used"] += units
            self._save()

    def mark(self, key, flag):
        with self.lock:
            self._entry(key)[flag] = True
            self._save()

    def summary(self):
        rows = []
        for i, key in enumerate(self.keys, 1):
            e = self._entry(key)
            rows.append({
                "key": f"Ключ {i} (…{key[-4:]})",
                "used": e["used"],
                "left_estimate": max(config.DAILY_QUOTA_PER_KEY - e["used"], 0),
                "exhausted": e["exhausted"],
                "invalid": e["invalid"],
            })
        return {"day": self.state["day"], "keys": rows}


class YouTubeClient:
    def __init__(self, keys=None, cache=None):
        self.keys = keys if keys is not None else config.API_KEYS
        self.cache = cache or Cache()
        self.quota = QuotaTracker(self.keys)
        self.current = 0
        self.units_this_run = 0
        self.search_totals = {}   # (запрос, язык) -> сколько роликов по теме нашёл YouTube (сумма по длительностям)

    # --- низкий уровень ---

    def _http_get(self, url):
        return http_get(url)

    def _call(self, endpoint, params):
        cached = self.cache.get(endpoint, params)
        if cached is not None:
            if cached.get("not_found"):
                raise NotFound("cached")
            return cached
        if not self.keys:
            raise NoApiKeys("Не задан YOUTUBE_API_KEYS в файле .env")

        for _ in range(len(self.keys)):
            key = self.keys[self.current]
            if not self.quota.available(key):
                self.current = (self.current + 1) % len(self.keys)
                continue
            url = API_BASE + endpoint + "?" + urllib.parse.urlencode({**params, "key": key})
            try:
                data = json.loads(self._http_get(url))
            except urllib.error.HTTPError as err:
                reason = _error_reason(err)
                if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
                    self.quota.mark(key, "exhausted")
                elif reason in ("keyInvalid", "accessNotConfigured", "keyExpired", "forbidden"):
                    self.quota.mark(key, "invalid")
                elif err.code == 404:
                    self.quota.add_usage(key, config.UNIT_COST[endpoint])
                    self.units_this_run += config.UNIT_COST[endpoint]
                    self.cache.set(endpoint, params, {"not_found": True})
                    raise NotFound(reason)
                else:
                    raise
                self.current = (self.current + 1) % len(self.keys)
                continue
            cost = config.UNIT_COST[endpoint]
            self.quota.add_usage(key, cost)
            self.units_this_run += cost
            self.cache.set(endpoint, params, data)
            return data
        raise QuotaExhausted("Квота всех ключей на сегодня закончилась")

    # --- запросы ---

    def search_videos(self, query, lang, duration=None, max_results=50):
        published_after = (datetime.now(timezone.utc) - timedelta(days=config.SEARCH_PUBLISHED_DAYS))
        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": max_results,
            "relevanceLanguage": lang,
            "order": "relevance",
            # округляем до понедельника, чтобы кэш срабатывал всю неделю
            "publishedAfter": (published_after - timedelta(days=published_after.weekday()))
            .strftime("%Y-%m-%dT00:00:00Z"),
        }
        if duration:
            params["videoDuration"] = duration
        data = self._call("search", params)
        # totalResults приблизительный, но хорошо отличает узкую тему (тысячи роликов) от массовой (сотни тысяч)
        key = (query.lower(), lang)
        self.search_totals[key] = self.search_totals.get(key, 0) + int(data.get("pageInfo", {}).get("totalResults", 0))
        return [item["id"]["videoId"] for item in data.get("items", []) if item.get("id", {}).get("videoId")]

    def videos(self, ids):
        out = []
        for chunk in _chunks(sorted(set(ids)), 50):
            data = self._call("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)})
            out.extend(data.get("items", []))
        return out

    def channels(self, ids):
        out = []
        for chunk in _chunks(sorted(set(ids)), 50):
            data = self._call("channels", {"part": "snippet,statistics", "id": ",".join(chunk)})
            out.extend(data.get("items", []))
        return out

    def recent_uploads(self, channel_id):
        """Даты последних (до 50) длинных роликов канала, новые первыми. None, если узнать не удалось.

        Плейлист UULF… содержит загрузки без шортсов (неофициально, но работает у всех каналов),
        UU… содержит все загрузки и нужен как запасной вариант.
        """
        for prefix in ("UULF", "UU"):
            try:
                data = self._call("playlistItems", {"part": "contentDetails", "maxResults": 50,
                                                    "playlistId": prefix + channel_id[2:]})
            except NotFound:
                continue
            return [i["contentDetails"].get("videoPublishedAt") for i in data.get("items", [])
                    if i.get("contentDetails", {}).get("videoPublishedAt")]
        return None

    def translate(self, text, lang):
        """Перевод темы на язык рынка через Google Translate (бесплатно, квоту не тратит).
        Если перевести не удалось, возвращает текст как есть."""
        params = {"client": "gtx", "sl": "auto", "tl": lang, "dt": "t", "q": text}
        cached = self.cache.get("suggest", params)
        if cached is not None:
            return cached
        try:
            data = json.loads(self._http_get(TRANSLATE_URL + "?" + urllib.parse.urlencode(params)).decode("utf-8"))
            out = "".join(part[0] for part in data[0] if part and part[0]).strip()
        except Exception:
            return text
        if out:
            self.cache.set("suggest", params, out)
        return out or text

    def suggest(self, query, lang):
        """Подсказки поиска YouTube. Бесплатно, квоту не тратит."""
        params = {"client": "firefox", "ds": "yt", "hl": lang, "q": query}
        cached = self.cache.get("suggest", params)
        if cached is not None:
            return cached
        try:
            raw = self._http_get(SUGGEST_URL + "?" + urllib.parse.urlencode(params))
            suggestions = json.loads(raw.decode("utf-8", errors="replace"))[1]
        except (urllib.error.URLError, ValueError, IndexError, OSError):
            return []
        self.cache.set("suggest", params, suggestions)
        return suggestions


def _error_reason(err):
    try:
        body = json.loads(err.read())
        return body["error"]["errors"][0]["reason"]
    except Exception:
        return "forbidden" if err.code == 403 else ""


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]
