"""Оценка ниши 0–100 по пяти критериям.

Веса:
  outlier      35%  медиана «просмотры / подписчики» у видео малых каналов
  new_channels 25%  каналы младше 3 месяцев, которые уже набирают просмотры
  competition  20%  чем больше каналов-миллионников в выдаче, тем ниже балл
  stability    10%  просмотры распределены по разным каналам и роликам
  format       10%  длинные ролики и посильная частота загрузок
"""
import math
import re
from collections import Counter
from datetime import datetime, timezone
from statistics import mean, median

from . import config

WEIGHTS = {"outlier": 35, "new_channels": 25, "competition": 20, "stability": 10, "format": 10}

STOP_TAGS = {"shorts", "short", "video", "youtube", "viral", "trending", "new", "2024", "2025", "2026"}


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


def _video_lang_ok(snippet, lang):
    declared = snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage")
    return not declared or declared.lower().startswith(lang)


def analyze(query, lang, videos_raw, channels_raw, now=None):
    now = now or datetime.now(timezone.utc)
    channels = {}
    for c in channels_raw:
        st = c.get("statistics", {})
        created = _parse_dt(c["snippet"]["publishedAt"])
        age_days = max((now - created).days, 1)
        video_count = int(st.get("videoCount", 0))
        channels[c["id"]] = {
            "id": c["id"],
            "title": c["snippet"]["title"],
            "subs": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0)),
            "views": int(st.get("viewCount", 0)),
            "video_count": video_count,
            "created": created.date().isoformat(),
            "age_days": age_days,
            "uploads_per_week": round(video_count / (age_days / 7), 2),
        }

    videos = []
    skipped_short = skipped_lang = 0
    for v in videos_raw:
        sn = v["snippet"]
        duration = parse_duration(v.get("contentDetails", {}).get("duration"))
        if duration < config.MIN_DURATION_SEC:
            skipped_short += 1
            continue
        if not _video_lang_ok(sn, lang):
            skipped_lang += 1
            continue
        ch = channels.get(sn["channelId"])
        if not ch or ch["subs"] is None:
            continue
        views = int(v.get("statistics", {}).get("viewCount", 0))
        videos.append({
            "id": v["id"],
            "title": sn["title"],
            "channel_id": ch["id"],
            "channel": ch["title"],
            "subs": ch["subs"],
            "views": views,
            "duration_min": round(duration / 60, 1),
            "published": sn["publishedAt"][:10],
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
    }
    if not videos:
        result.update(score=0, scores={k: 0 for k in WEIGHTS}, low_data=True, metrics={},
                      top_videos=[], channels=[], related=[])
        return result

    used_channel_ids = {v["channel_id"] for v in videos}
    used_channels = [channels[c] for c in used_channel_ids]
    small = [v for v in videos if v["subs"] <= config.SMALL_CHANNEL_MAX_SUBS]
    big_channels = [c for c in used_channels if c["subs"] >= config.BIG_CHANNEL_SUBS]

    # 1. Аутлайер-фактор: ratio 0.3 -> 0, ratio 10 -> 1 (логарифмическая шкала)
    median_ratio = median(v["ratio"] for v in small) if small else 0
    s_outlier = _clamp((math.log10(median_ratio) + 0.5) / 1.5) if median_ratio > 0 else 0

    # 2. Новые каналы: созданы за последние NEW_CHANNEL_DAYS дней
    new_channels = [c for c in used_channels if c["age_days"] <= config.NEW_CHANNEL_DAYS]
    best_views = Counter()
    for v in videos:
        best_views[v["channel_id"]] = max(best_views[v["channel_id"]], v["views"])
    new_successful = [c for c in new_channels if best_views[c["id"]] >= config.NEW_CHANNEL_MIN_VIEWS]
    s_new = _clamp(len(new_successful) / 3) * 0.8 + _clamp(len(new_channels) / 5) * 0.2

    # 3. Конкуренция: доля каналов-миллионников; 40% и больше -> 0
    big_share = len(big_channels) / len(used_channels)
    s_competition = 1 - _clamp(big_share / 0.4)

    # 4. Стабильность: доля самого популярного ролика в сумме просмотров
    #    и сколько малых каналов имеют ролики с ratio >= 1
    total_views = sum(v["views"] for v in videos) or 1
    top_share = max(v["views"] for v in videos) / total_views
    strong_small_channels = {v["channel_id"] for v in small if v["ratio"] >= 1}
    s_stability = 0.5 * (1 - top_share) + 0.5 * _clamp(len(strong_small_channels) / 5)

    # 5. Формат: длина успешных роликов и частота загрузок их каналов
    successful = [v for v in small if v["ratio"] >= 1] or small or videos
    avg_len = mean(v["duration_min"] for v in successful)
    succ_channels = [channels[c] for c in {v["channel_id"] for v in successful}]
    uploads_week = median(c["uploads_per_week"] for c in succ_channels)
    s_len = _clamp(avg_len / 8)
    s_freq = 1 - _clamp((uploads_week - 1) / 6)   # <=1 видео в неделю -> 1, 7+ -> 0
    s_format = 0.5 * s_len + 0.5 * s_freq

    scores = {
        "outlier": s_outlier,
        "new_channels": s_new,
        "competition": s_competition,
        "stability": s_stability,
        "format": s_format,
    }
    total = sum(scores[k] * w for k, w in WEIGHTS.items())

    tag_counter = Counter()
    for v in successful:
        for t in {t.lower().strip() for t in v["tags"]}:
            if t and t != query.lower() and t not in STOP_TAGS and len(t) > 3:
                tag_counter[t] += 1

    result.update(
        score=round(total),
        scores={k: round(v * 100) for k, v in scores.items()},
        low_data=len(videos) < 10 or len(small) < 5,
        metrics={
            "median_ratio_small": round(median_ratio, 2),
            "median_views": int(median(v["views"] for v in videos)),
            "median_views_small": int(median(v["views"] for v in small)) if small else 0,
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
        },
        top_videos=[{k: v[k] for k in ("id", "title", "channel", "subs", "views", "ratio", "duration_min", "published")}
                    for v in sorted(small or videos, key=lambda x: x["ratio"], reverse=True)[:8]],
        channels=sorted(
            [{**c, "best_views": best_views[c["id"]], "is_new": c["age_days"] <= config.NEW_CHANNEL_DAYS}
             for c in used_channels],
            key=lambda c: c["best_views"] / max(c["subs"], 100), reverse=True)[:12],
        related=[t for t, _ in tag_counter.most_common(12)],
    )
    return result
