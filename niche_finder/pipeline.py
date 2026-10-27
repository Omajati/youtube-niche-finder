"""Запуск анализа: по запросу или с автопоиском подниш через подсказки YouTube."""
import json
import threading

from . import config
from .scoring import analyze, is_excluded_channel
from .youtube import NoApiKeys, QuotaExhausted, YouTubeClient

# Стартовые темы для автопоиска, если запрос не задан
DEFAULT_SEEDS = {
    "en": ["unsolved mysteries", "strange true stories", "unexplained events", "forgotten history",
           "bizarre historical events", "creepy true stories"],
    "es": ["misterios sin resolver", "historias reales extrañas", "casos inexplicables",
           "historia olvidada", "sucesos insólitos"],
    "de": ["ungelöste rätsel", "unglaubliche wahre geschichten", "mysteriöse fälle",
           "vergessene geschichte", "seltsame ereignisse"],
    "fr": ["mystères non résolus", "histoires vraies incroyables", "affaires inexpliquées",
           "histoire oubliée", "faits étranges"],
}

# Примерная стоимость анализа одной ниши: по поиску (100) на каждую длительность, videos и channels
# и последние ролики малых каналов (по единице на канал)
UNITS_PER_NICHE = 100 * max(len(config.SEARCH_DURATIONS), 1) + 4 + config.UPLOADS_CHECK_CHANNELS

_lock = threading.Lock()


def load_results():
    try:
        return json.loads(config.RESULTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_result(item):
    with _lock:
        results = [r for r in load_results() if not (r["query"].lower() == item["query"].lower()
                                                     and r["lang"] == item["lang"])]
        results.append(item)
        config.RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.RESULTS_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


def analyze_niche(client, query, lang):
    video_ids = []
    for duration in config.SEARCH_DURATIONS or [None]:
        video_ids += client.search_videos(query, lang, duration)
    videos = client.videos(video_ids)
    channel_ids = [v["snippet"]["channelId"] for v in videos]
    channels = client.channels(channel_ids)
    # Реальная частота загрузок и дата первого ролика: только у малых каналов, они и есть ориентир
    small = [c for c in channels if not c["statistics"].get("hiddenSubscriberCount")
             and not is_excluded_channel(c["snippet"].get("country"))
             and int(c["statistics"].get("subscriberCount", 0)) <= config.SMALL_CHANNEL_MAX_SUBS]
    small.sort(key=lambda c: int(c["statistics"].get("subscriberCount", 0)))
    uploads = {c["id"]: client.recent_uploads(c["id"]) for c in small[:config.UPLOADS_CHECK_CHANNELS]}
    return analyze(query, lang, videos, channels, uploads=uploads)


def plan_queries(client, queries, langs, expand, max_niches):
    """Список (запрос, язык). expand > 0 добавляет N подсказок YouTube к каждому запросу."""
    plan = []
    for lang in langs:
        base = queries or DEFAULT_SEEDS.get(lang, [])
        for q in base:
            items = [q]
            if expand:
                items += [s for s in client.suggest(q, lang) if s.lower() != q.lower()][:expand]
            for item in items:
                if (item, lang) not in plan:
                    plan.append((item, lang))
    return plan[:max_niches]


def run(queries, langs, expand=0, max_niches=10, progress=None, client=None):
    """Анализирует ниши по очереди. progress(dict) получает статус после каждого шага."""
    client = client or YouTubeClient()
    report = progress or (lambda s: None)
    status = {"state": "running", "done": 0, "total": 0, "current": None, "errors": [], "units": 0}

    plan = plan_queries(client, queries, langs, expand, max_niches)
    status["total"] = len(plan)
    status["plan"] = [f"{q} [{lang}]" for q, lang in plan]
    report(status)

    for query, lang in plan:
        status["current"] = f"{query} [{lang}]"
        report(status)
        try:
            save_result(analyze_niche(client, query, lang))
        except QuotaExhausted as e:
            status["errors"].append(str(e))
            status["state"] = "quota_exhausted"
            break
        except NoApiKeys as e:
            status["errors"].append(str(e))
            status["state"] = "error"
            break
        except Exception as e:  # одна неудачная ниша не должна ронять весь запуск
            status["errors"].append(f"{query} [{lang}]: {e}")
        status["done"] += 1
        status["units"] = client.units_this_run
        report(status)

    if status["state"] == "running":
        status["state"] = "finished"
    status["current"] = None
    status["units"] = client.units_this_run
    report(status)
    return status
