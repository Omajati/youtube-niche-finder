"""Оценка ниши 0–100 по шести критериям.

Веса:
  outlier      30%  медиана «просмотры / подписчики» у видео малых каналов
  new_channels 20%  каналы младше 3 месяцев, которые уже набирают просмотры
  competition  15%  каналы-миллионники в выдаче и насколько тема забита роликами
  evergreen    15%  старые ролики продолжают набирать, тема не держится на новостях и трендах
  stability    10%  просмотры распределены по разным каналам и роликам
  format       10%  длинные ролики и посильная частота загрузок
"""
import math
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from statistics import mean, median

from . import config

WEIGHTS = config.WEIGHTS   # меняются в окне «Настройки анализа»

# Признаки трендовой или новостной темы в названиях: такие ролики быстро устаревают
TREND_WORDS = re.compile(
    r"\b(20[12]\d|news|breaking|update|trailer|reaction|reacts?|live|today|tonight|this week|election|patch|"
    r"leaked?|rumou?rs?|noticias|última hora|hoy|en vivo|reacción|nachrichten|aktuell|heute|eilmeldung|"
    r"actualités?|actu|aujourd'hui|en direct|réaction)\b", re.I)

STOP_TAGS = {"shorts", "short", "video", "youtube", "viral", "trending", "new", "2024", "2025", "2026"}


def weighted_total(scores, scale=1):
    """Итоговый балл 0–100 из оценок критериев (0–1 при scale=100, 0–100 при scale=1)."""
    weight_sum = sum(WEIGHTS.values()) or 1
    return sum(scores.get(k, 0) * w for k, w in WEIGHTS.items()) * scale / weight_sum


def parse_duration(iso):
    """ISO 8601 (PT1H2M3S) -> секунды."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _parse_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _clamp(x):
    return max(0.0, min(1.0, x))


FOREIGN_WORDS = re.compile(r"\b(hindi|urdu|tamil|telugu|bangla|bengali|marathi|punjabi|kannada|malayalam|"
                           r"tagalog|indonesia|bahasa|türkçe|arabic)\b", re.I)
# Хинглиш: хинди латиницей. Эти слова не встречаются в английском, испанском, немецком и французском.
HINGLISH_WORDS = re.compile(r"\b(hai|hain|kya|kaise|kyun|kyu|aur|nahi|kahani|rahasya|itihas|duniya|"
                            r"bhai|bhaiya|ki kahani|ka sach|ka rahasya)\b", re.I)
SOUTH_ASIAN_SCRIPTS = ("DEVANAGARI", "BENGALI", "GURMUKHI", "GUJARATI", "ORIYA", "TAMIL", "TELUGU", "KANNADA",
                       "MALAYALAM", "SINHALA", "ARABIC")


def _south_asian(text):
    return any(unicodedata.name(ch, "").startswith(SOUTH_ASIAN_SCRIPTS) for ch in text if ch.isalpha())


def is_excluded_channel(country):
    return (country or "").upper() in config.EXCLUDE_COUNTRIES


def _south_asian_video(snippet, channel_title):
    """Индийские и соседние каналы не смотрим совсем, даже если ролик на английском."""
    text = " ".join([snippet.get("title", ""), channel_title, snippet.get("description", "")[:500]])
    return _south_asian(text) or bool(HINGLISH_WORDS.search(snippet.get("title", "") + " " + channel_title))


def _non_latin(text):
    """Есть ли в тексте буквы не латиницей (деванагари, кириллица, арабская вязь и т.д.)."""
    return any(ch.isalpha() and not unicodedata.name(ch, "").startswith("LATIN") for ch in text)


def _video_lang_ok(snippet, lang, channel_title=""):
    declared = snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage")
    if declared:
        return declared.lower().startswith(lang)
    # язык не указан: отсекаем по письменности и явным пометкам вроде «Hindi Documentary»
    text = snippet.get("title", "") + " " + channel_title
    return not _non_latin(text) and not FOREIGN_WORDS.search(text)


def _activity(dates, now, created_days):
    """По датам последних длинных роликов: частота в неделю за 90 дней и сколько дней назад вышел первый ролик.

    first_upload_days = None, если роликов 50 (больше не знаем) — тогда канал точно не новичок.
    """
    parsed = sorted(_parse_dt(d) for d in dates)
    if not parsed:
        return 0.0, None, 0
    window = min(90, max(created_days, 7))
    recent = [d for d in parsed if (now - d).days <= 90]
    per_week = len(recent) / (window / 7)
    first = (now - parsed[0]).days if len(parsed) < 50 else None
    return per_week, first, len(recent)


def analyze(query, lang, videos_raw, channels_raw, now=None, uploads=None, search_total=None):
    now = now or datetime.now(timezone.utc)
    uploads = uploads or {}
    min_views = config.MIN_VIEWS.get(lang, config.MIN_VIEWS["en"])
    channels = {}
    for c in channels_raw:
        st = c.get("statistics", {})
        created = _parse_dt(c["snippet"]["publishedAt"])
        age_days = max((now - created).days, 1)
        video_count = int(st.get("videoCount", 0))
        channels[c["id"]] = {
            "id": c["id"],
            "title": c["snippet"]["title"],
            "country": c["snippet"].get("country", ""),
            "subs": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0)),
            "views": int(st.get("viewCount", 0)),
            "video_count": video_count,
            "created": created.date().isoformat(),
            "age_days": age_days,
            "uploads_per_week": round(video_count / (age_days / 7), 2),
            "uploads_exact": False,
            # «Возраст» канала по первому ролику: старый пустой аккаунт, начавший выкладывать недавно, тоже новичок
            "active_days": age_days,
        }
        dates = uploads.get(c["id"])
        if dates is not None:
            per_week, first_days, recent = _activity(dates, now, age_days)
            ch = channels[c["id"]]
            ch.update(uploads_per_week=round(per_week, 2), uploads_exact=True, long_uploads_90d=recent)
            if first_days is not None:
                ch["active_days"] = min(first_days, age_days)

    videos = []
    skipped_short = skipped_lang = skipped_region = 0
    for v in videos_raw:
        sn = v["snippet"]
        duration = parse_duration(v.get("contentDetails", {}).get("duration"))
        if duration < config.MIN_DURATION_SEC:
            skipped_short += 1
            continue
        ch = channels.get(sn["channelId"])
        if ch and (is_excluded_channel(ch["country"]) or _south_asian_video(sn, ch["title"])):
            skipped_region += 1
            continue
        if not _video_lang_ok(sn, lang, ch["title"] if ch else ""):
            skipped_lang += 1
            continue
        if not ch or ch["subs"] is None:
            continue
        views = int(v.get("statistics", {}).get("viewCount", 0))
        age = max((now - _parse_dt(sn["publishedAt"])).days, 0)
        videos.append({
            "id": v["id"],
            "title": sn["title"],
            "channel_id": ch["id"],
            "channel": ch["title"],
            "subs": ch["subs"],
            "views": views,
            "duration_min": round(duration / 60, 1),
            "published": sn["publishedAt"][:10],
            "age_days": age,
            "views_per_day": round(views / max(age, 1)),
            "ratio": round(views / max(ch["subs"], 100), 2),
            "tags": sn.get("tags", []),
        })

    result = {
        "query": query,
        "lang": lang,
        "analyzed_at": now.isoformat(timespec="seconds"),
        "videos_found": len(videos_raw),
        "videos_long": len(videos),
        "skipped_short": skipped_short,
        "skipped_lang": skipped_lang,
        "skipped_region": skipped_region,
    }
    if not videos:
        result.update(score=0, scores={k: 0 for k in WEIGHTS}, low_data=True, metrics={},
                      top_videos=[], channels=[], related=[])
        return result

    used_channel_ids = {v["channel_id"] for v in videos}
    used_channels = [channels[c] for c in used_channel_ids]
    small = [v for v in videos if v["subs"] <= config.SMALL_CHANNEL_MAX_SUBS]
    big_channels = [c for c in used_channels if c["subs"] >= config.BIG_CHANNEL_SUBS]

    # Ролики малых каналов, набравшие от min_views просмотров (порог зависит от рынка). Всё, что ниже, успехом не считаем:
    # 3K просмотров на канале со 100 подписчиками даёт 30×, но спроса не доказывает.
    # Свежий ролик, который ещё не добрал порог, просто не успел: провалом его не считаем и не учитываем.
    # Свежий ролик, уже набравший порог, наоборот, сильный сигнал и идёт в зачёт.
    mature = [v for v in small if v["age_days"] >= config.MIN_VIDEO_AGE_DAYS or v["views"] >= min_views]
    hits = [v for v in mature if v["views"] >= min_views]
    hit_share = len(hits) / len(mature) if mature else 0

    # 1. Аутлайер-фактор: медиана ratio у таких роликов (0.3 -> 0, 10 -> 1, логарифмическая шкала)
    #    и какая доля роликов малых каналов вообще дотягивает до min_views (половина и больше -> 1)
    median_ratio = median(v["ratio"] for v in hits) if hits else 0
    top = math.log10(max(config.RATIO_TARGET, 1.01))
    s_ratio = _clamp((math.log10(median_ratio) + 0.5) / (top + 0.5)) if median_ratio > 0 else 0
    s_outlier = 0.7 * s_ratio + 0.3 * _clamp(hit_share / 0.5)

    # 2. Новые каналы: первый ролик (или создание канала) за последние NEW_CHANNEL_DAYS дней
    new_channels = [c for c in used_channels if c["active_days"] <= config.NEW_CHANNEL_DAYS]
    best_views = Counter()
    for v in videos:
        best_views[v["channel_id"]] = max(best_views[v["channel_id"]], v["views"])
    new_successful = [c for c in new_channels if best_views[c["id"]] >= min_views]
    s_new = _clamp(len(new_successful) / config.NEW_CHANNELS_TARGET) * 0.8 + _clamp(len(new_channels) / 5) * 0.2

    # 3. Конкуренция: доля каналов-миллионников (40% и больше -> 0) и насыщенность темы:
    #    сколько роликов по запросу нашёл YouTube за полгода (до 2 тыс. -> 1, от 200 тыс. -> 0)
    big_share = len(big_channels) / len(used_channels)
    s_big = 1 - _clamp(big_share / (config.BIG_SHARE_MAX / 100))
    if search_total:
        lo, hi = config.SATURATION_LOW, max(config.SATURATION_HIGH, config.SATURATION_LOW * 1.01)
        s_saturation = 1 - _clamp((math.log10(max(search_total, 1)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)))
        s_competition = 0.7 * s_big + 0.3 * s_saturation
    else:
        s_competition = s_big

    # Вечнозелёность: какая доля успешных роликов старше 2 месяцев (половина и больше -> 1)
    # и сколько из них не похожи на новости и тренды
    hits_old = [v for v in hits if v["age_days"] >= config.EVERGREEN_AGE_DAYS]
    trendy = [v for v in hits if TREND_WORDS.search(v["title"])]
    s_evergreen = (0.6 * _clamp((len(hits_old) / len(hits)) / 0.5) + 0.4 * (1 - len(trendy) / len(hits))) if hits else 0

    # 4. Стабильность: доля самого популярного ролика в сумме просмотров
    #    и сколько малых каналов имеют ролики с ratio >= 1
    total_views = sum(v["views"] for v in videos) or 1
    top_share = max(v["views"] for v in videos) / total_views
    strong_small_channels = {v["channel_id"] for v in hits if v["ratio"] >= 1}
    s_stability = 0.5 * (1 - top_share) + 0.5 * _clamp(len(strong_small_channels) / 5)

    # 5. Формат: длина успешных роликов и частота загрузок их каналов
    successful = [v for v in hits if v["ratio"] >= 1] or hits or small or videos
    avg_len = mean(v["duration_min"] for v in successful)
    succ_channels = [channels[c] for c in {v["channel_id"] for v in successful}]
    uploads_week = median(c["uploads_per_week"] for c in succ_channels)
    s_len = _clamp(avg_len / 8)
    s_freq = 1 - _clamp((uploads_week - 1) / 6)   # <=1 видео в неделю -> 1, 7+ -> 0
    s_format = 0.5 * s_len + 0.5 * s_freq

    # Рост: как быстро молодые (до года) малые каналы ниши набирают подписчиков
    young = [c for c in used_channels if c["active_days"] <= 365 and c["subs"] <= config.SMALL_CHANNEL_MAX_SUBS]
    months_to_1k = []
    for c in young:
        rate = c["subs"] / max(c["active_days"] / 30.4, 0.5)
        if rate > 0:
            months_to_1k.append(min(1000 / rate, 120))
    # Монетизация: 4000 часов просмотра за год при средней длине успешных роликов и типичном удержании
    views_for_4000h = 4000 * 60 / max(avg_len * config.RETENTION_PCT / 100, 0.1)
    hit_median_views = median(v["views"] for v in hits) if hits else 0

    scores = {
        "outlier": s_outlier,
        "new_channels": s_new,
        "competition": s_competition,
        "evergreen": s_evergreen,
        "stability": s_stability,
        "format": s_format,
    }
    total = weighted_total(scores, scale=100)

    tag_counter = Counter()
    for v in ([v for v in hits if v["ratio"] >= 1] or hits):
        for t in {t.lower().strip() for t in v["tags"]}:
            if t and t != query.lower() and t not in STOP_TAGS and len(t) > 3:
                tag_counter[t] += 1

    result.update(
        score=round(total),
        scores={k: round(v * 100) for k, v in scores.items()},
        low_data=len(videos) < 10 or len(mature) < 5 or len(hits) < config.LOW_DATA_MIN_HITS,
        metrics={
            "median_ratio_small": round(median_ratio, 2),
            "median_views": int(median(v["views"] for v in videos)),
            "median_views_small": int(median(v["views"] for v in small)) if small else 0,
            "hits_small": len(hits),
            "min_views": min_views,
            "too_young": len(small) - len(mature),
            "hit_share_small": round(hit_share * 100),
            "channels": len(used_channels),
            "small_channels": len({v["channel_id"] for v in small}),
            "big_channels": len(big_channels),
            "big_share": round(big_share * 100),
            "new_channels": len(new_channels),
            "new_successful": len(new_successful),
            "avg_length_min": round(mean(v["duration_min"] for v in videos), 1),
            "avg_length_successful_min": round(avg_len, 1),
            "uploads_per_week_successful": round(uploads_week, 2),
            "top_video_share": round(top_share * 100),
            "search_total": search_total or 0,
            "hits_old_share": round(len(hits_old) / len(hits) * 100) if hits else 0,
            "trendy_share": round(len(trendy) / len(hits) * 100) if hits else 0,
            "young_channels": len(young),
            "young_1k": sum(1 for c in young if c["subs"] >= 1000),
            "months_to_1k": round(median(months_to_1k), 1) if months_to_1k else None,
            "views_for_4000h": int(views_for_4000h),
            "videos_for_4000h": round(views_for_4000h / hit_median_views, 1) if hit_median_views else None,
            "ideas_hits": len({v["title"].lower().strip() for v in hits}),
        },
        # Все успешные ролики: запас идей и материал для разбора ниши
        hit_titles=[{k: v[k] for k in ("id", "title", "channel", "subs", "views", "ratio", "duration_min", "age_days")}
                    for v in sorted(hits, key=lambda x: x["views"], reverse=True)[:40]],
        top_videos=[{k: v[k] for k in ("id", "title", "channel", "subs", "views", "ratio", "duration_min", "published",
                                          "views_per_day")}
                    for v in sorted(hits, key=lambda x: x["ratio"], reverse=True)[:8]],
        channels=sorted(
            [{**c, "best_views": best_views[c["id"]], "is_new": c["active_days"] <= config.NEW_CHANNEL_DAYS}
             for c in used_channels],
            key=lambda c: c["best_views"] / max(c["subs"], 100), reverse=True)[:12],
        related=[t for t, _ in tag_counter.most_common(12)],
    )
    return result
