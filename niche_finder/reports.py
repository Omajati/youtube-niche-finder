"""Разборы через Claude API: ниша (чек-лист «Перспективность ниши») и конкурент (чек-лист «Разбор канала»).

Цифры собирает программа (YouTube API), смысл разбирает Claude. Отчёты хранятся в data/reports.json.
"""
import json
import threading
from datetime import datetime, timezone

from . import config
from .scoring import parse_duration
from .youtube import YouTubeClient

LANG_NAMES = {"en": "английский", "es": "испанский", "de": "немецкий", "fr": "французский", "ru": "русский"}

status = {"state": "idle"}
_lock = threading.Lock()
_run_lock = threading.Lock()


class ReportError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_reports():
    try:
        return json.loads(config.REPORTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_report(key, report):
    with _lock:
        reports = load_reports()
        reports[key] = report
        config.REPORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.REPORTS_FILE.write_text(json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8")


def load_spend():
    """Расходы на Claude. Если учёта ещё нет, начинаем с суммы уже сделанных разборов."""
    try:
        return json.loads(config.SPEND_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    spend = {"total": 0.0, "count": 0, "months": {}}
    for r in load_reports().values():
        cost = r.get("cost_usd") or 0
        month = (r.get("created_at") or _now())[:7]
        spend["total"] += cost
        spend["count"] += 1
        spend["months"][month] = spend["months"].get(month, 0) + cost
    return spend


def add_spend(cost):
    """Учитывает каждый ответ Claude, даже если разбор потом перезапишут или он упадёт на разборе ответа."""
    with _lock:
        spend = load_spend()
        month = _now()[:7]
        spend["total"] = round(spend["total"] + cost, 4)
        spend["count"] += 1
        spend["months"][month] = round(spend["months"].get(month, 0) + cost, 4)
        config.SPEND_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.SPEND_FILE.write_text(json.dumps(spend, ensure_ascii=False, indent=1), encoding="utf-8")


def spend_summary():
    spend = load_spend()
    return {"total": round(spend["total"], 2), "count": spend["count"],
            "month": round(spend["months"].get(_now()[:7], 0), 2), "months": spend["months"]}


def niche_key(query, lang):
    return f"niche|{lang}|{query.lower().strip()}"


def channel_key(channel_id):
    return f"channel|{channel_id}"


# --- схемы ответа ---

def _obj(props, required=None):
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


S = {"type": "string"}
I = {"type": "integer"}


def _arr(items):
    return {"type": "array", "items": items}


NICHE_SCHEMA = _obj({
    "summary": S,
    "criteria": _arr(_obj({"name": S, "score": I, "comment": S})),
    "total": I,
    "income": _obj({"rpm_comment": S, "at_100k": S, "at_500k": S, "at_1m": S, "extra_monetization": S}),
    "risks": _arr(S),
    "angle": S,
    "ideas": _arr(_obj({"title": S, "why": S})),
})

CHANNEL_SCHEMA = _obj({
    "summary": S,
    "format": _obj({"avg_duration": S, "structure": S, "retention": S, "script_template": S, "production": S}),
    "success": _obj({"top_topics": S, "common_traits": S, "title_triggers": S, "frequent_words": S,
                     "title_formula": S}),
    "thumbnails": _obj({"emotions": S, "patterns": S, "stand_out": S}),
    "audience": _obj({"who": S, "needs": S, "why_this_channel": S, "why_return": S}),
    "weaknesses": _arr(_obj({"issue": S, "how_to_use": S})),
    "launch": _obj({"format": S, "ideas": _arr(S), "thumbnail_tips": S, "duration": S}),
    "verdict": _obj({"score": I, "reasoning": S, "competitor_strengths": S, "difficulty": S}),
    "main_advantage": S,
})

SYSTEM = (
    "Ты аналитик YouTube, который помогает выбрать нишу для нового канала без лица с длинными роликами (от 8 минут) "
    "и вести его годами. Отвечай по-русски. Опирайся на данные, которые тебе дали: называй конкретные ролики, цифры "
    "и формулировки, а не общие советы. Где данных не хватает, так и скажи и дай лучшую оценку с пометкой «оценка». "
    "Оценки ставь целыми числами от 1 до 10. Названия роликов и идеи для роликов пиши на языке рынка, "
    "а пояснения к ним по-русски."
)

NICHE_TASK = """Оцени нишу по семи критериям, в этом порядке (поле criteria, ровно 7 элементов):
1. Потенциал заработка: примерный диапазон RPM, возможный доход при 100 000, 500 000 и 1 000 000 просмотров в месяц, возможности дополнительной монетизации.
2. Размер аудитории и спрос: насколько востребована тематика, какой у неё охват и хватит ли интереса для стабильного выпуска.
3. Уровень конкуренции: насколько ниша занята крупными каналами, легко ли новым получать просмотры, какие барьеры для входа.
4. Долговечность контента: набирают ли видео просмотры месяцами и годами или зависят от краткосрочных трендов.
5. Сложность производства: сколько времени и ресурсов нужно на контент без лица, реально ли одному человеку регулярно выпускать качественные ролики.
6. Запас идей: хватит ли тем минимум на 30 оригинальных роликов без повторов.
7. Потенциал роста: реально ли новому каналу получить первые 1000 подписчиков, выйти на монетизацию и масштабировать просмотры за 6–12 месяцев.

Затем: итоговая оценка перспективности от 1 до 10 (total), ровно три главных риска (risks), один конкретный, относительно свободный угол внутри ниши для выделения среди конкурентов (angle) и ровно 15 тем для первых роликов (ideas): рабочее название на языке рынка и почему зайдёт.
Доход (income) считай от оценки RPM ниже, поправь её, если по данным ниша дороже или дешевле. В summary коротко: стоит ли идти в нишу и почему."""

CHANNEL_TASK = """Разбери канал-конкурент:
1. Формат и структура (format): средняя длительность; как строится ролик (начало, основная часть, концовка); приёмы удержания внимания; есть ли повторяющийся сценарный шаблон; насколько сложно и дорого производить такой контент. Субтитров у тебя нет, структуру оценивай по названиям, описаниям, длительности и комментариям и пиши, что это оценка.
2. Формат успешных видео (success) по 10 самым популярным роликам: какие темы собирают больше всего просмотров; что объединяет самые успешные видео; какие триггеры в названиях; какие слова и формулировки повторяются чаще всего; есть ли универсальная формула заголовков, которую можно адаптировать.
3. Стратегия превью (thumbnails): на каких эмоциях строятся обложки; какие закономерности у самых популярных; как улучшить подачу, чтобы выделяться. Обложки топ-роликов приложены картинками в том же порядке, что и список.
4. Аудитория (audience): кто основная аудитория; какие потребности закрывает контент; почему выбирают именно этот канал; что заставляет возвращаться. Опирайся на комментарии.
5. Слабые стороны и возможности (weaknesses): минимум 5 недостатков или неиспользованных возможностей (недостаточно раскрытые темы, слабые сценарные решения, однообразные форматы, неиспользованные эмоциональные триггеры, направления, которые автор игнорирует), и для каждой как её использовать новому каналу.
6. Стратегия запуска конкурирующего канала (launch): формат с наибольшим потенциалом; ровно 10 идей для первых видео; рекомендации по превью; оптимальная продолжительность.
7. Итоговый вердикт (verdict): оценка от 1 до 10, насколько разумно запускать конкурирующий канал; какие преимущества у действующего конкурента; насколько сложно соперничать и за счёт чего новый канал привлечёт свою аудиторию.
В конце (main_advantage) сформулируй главное конкурентное преимущество, на котором строить свой канал, чтобы реально обойти этого конкурента."""


# --- сбор данных ---

def niche_payload(result):
    m = result.get("metrics", {})
    return {
        "тема": result["query"],
        "рынок": LANG_NAMES.get(result["lang"], result["lang"]),
        "балл программы (0-100)": result.get("score"),
        "оценки программы по критериям (0-100)": result.get("scores", {}),
        "метрики": m,
        "оценка дохода программы": result.get("income", {}),
        "успешные ролики малых каналов": result.get("hit_titles") or result.get("top_videos", []),
        "каналы": [{k: c.get(k) for k in ("title", "subs", "best_views", "video_count", "uploads_per_week", "created",
                                          "active_days", "is_new", "country")} for c in result.get("channels", [])],
        "теги успешных роликов": result.get("related", []),
        "подсказки поиска YouTube": result.get("suggestions", []),
        "пояснения": {
            "порог успеха": f"ролик успешен от {m.get('min_views')} просмотров",
            "малый канал": f"до {config.SMALL_CHANNEL_MAX_SUBS} подписчиков",
            "новый канал": f"первый ролик за последние {config.NEW_CHANNEL_DAYS} дней",
            "search_total": "сколько роликов по теме нашёл YouTube за период поиска",
            "months_to_1k": "медиана: за сколько месяцев молодые малые каналы ниши доходят до 1000 подписчиков",
            "views_for_4000h": "сколько просмотров нужно для 4000 часов при средней длине и удержании "
                               f"{config.RETENTION_PCT}%",
        },
    }


def channel_payload(client, channel_id):
    """Канал, топ-10 роликов по просмотрам, 10 последних и комментарии к топ-5. Около 10–15 единиц квоты."""
    ch = client.channels([channel_id])
    if not ch:
        raise ReportError("Канал не найден")
    ch = ch[0]
    ids = client.channel_video_ids(channel_id)
    videos = client.videos(ids)
    items = []
    for v in videos:
        sn, st = v["snippet"], v.get("statistics", {})
        thumbs = sn.get("thumbnails", {})
        items.append({
            "id": v["id"],
            "title": sn["title"],
            "published": sn["publishedAt"][:10],
            "views": int(st.get("viewCount", 0)),
            "likes": int(st.get("likeCount", 0)),
            "comments": int(st.get("commentCount", 0)),
            "duration_min": round(parse_duration(v.get("contentDetails", {}).get("duration")) / 60, 1),
            "description": sn.get("description", "")[:400],
            "tags": sn.get("tags", [])[:15],
            "thumb": (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", ""),
        })
    items = [v for v in items if v["duration_min"] * 60 >= config.MIN_DURATION_SEC] or items
    top = sorted(items, key=lambda v: v["views"], reverse=True)[:10]
    recent = sorted(items, key=lambda v: v["published"], reverse=True)[:10]
    for v in top[:5]:
        v["top_comments"] = client.comments(v["id"])
    st = ch.get("statistics", {})
    info = {
        "название": ch["snippet"]["title"],
        "описание": ch["snippet"].get("description", "")[:800],
        "страна": ch["snippet"].get("country", ""),
        "создан": ch["snippet"]["publishedAt"][:10],
        "подписчиков": int(st.get("subscriberCount", 0)),
        "всего просмотров": int(st.get("viewCount", 0)),
        "всего видео": int(st.get("videoCount", 0)),
        "длинных роликов разобрано": len(items),
        "средняя длина, мин": round(sum(v["duration_min"] for v in items) / len(items), 1) if items else 0,
    }
    strip = lambda v: {k: v[k] for k in v if k != "thumb"}
    return {"канал": info, "топ-10 по просмотрам": [strip(v) for v in top],
            "10 последних": [strip(v) for v in recent]}, [v["thumb"] for v in top if v["thumb"]], ch["snippet"]["title"]


# --- вызов Claude ---

def _client():
    if not config.ANTHROPIC_API_KEY:
        raise ReportError("Не задан ключ Claude API. Впишите его в «Ключи API».")
    import anthropic
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=600)


def _ask(model, task, payload, schema, images=()):
    import anthropic
    content = [{"type": "image", "source": {"type": "url", "url": u}} for u in images]
    content.append({"type": "text", "text": task + "\n\nДанные (JSON):\n" + json.dumps(payload, ensure_ascii=False)})
    params = dict(model=model, max_tokens=32000, system=SYSTEM,
                  output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
                  messages=[{"role": "user", "content": content}])
    client = _client()
    try:
        try:   # если модель откажется отвечать, запрос сам уйдёт на запасную модель
            with client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                             **params) as stream:
                response = stream.get_final_message()
        except anthropic.BadRequestError:
            # запасная модель доступна не везде: тогда обычный запрос, ошибка в нём уже настоящая
            with client.messages.stream(**params) as stream:
                response = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise ReportError("Ключ Claude API не подходит. Проверьте его в «Ключи API».")
    except anthropic.PermissionDeniedError:
        raise ReportError("У ключа Claude API нет доступа к этой модели.")
    except anthropic.RateLimitError:
        raise ReportError("Claude API просит подождать (лимит запросов). Попробуйте через минуту.")
    except anthropic.APIStatusError as e:
        raise ReportError(f"Claude API вернул ошибку {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise ReportError("Нет связи с Claude API. Проверьте интернет.")
    u = response.usage
    tokens_in = (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0) \
        + (getattr(u, "cache_read_input_tokens", 0) or 0)
    price = config.CLAUDE_MODELS.get(model, config.CLAUDE_MODELS["claude-opus-5-5"])
    cost = tokens_in / 1e6 * price["in"] + (u.output_tokens or 0) / 1e6 * price["out"]
    add_spend(cost)   # за ответ платим, даже если дальше он не подойдёт
    if response.stop_reason == "refusal":
        raise ReportError("Claude отказался разбирать эти данные.")
    if response.stop_reason == "max_tokens":
        raise ReportError("Ответ Claude не поместился. Попробуйте ещё раз.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except ValueError:
        raise ReportError("Claude вернул ответ не в том формате. Попробуйте ещё раз.")
    return data, {"input": tokens_in, "output": u.output_tokens or 0}, round(cost, 3), getattr(response, "model", model)


def make_niche_report(result, model):
    data, tokens, cost, served = _ask(model, NICHE_TASK, niche_payload(result), NICHE_SCHEMA)
    report = {"kind": "niche", "title": f"{result['query']} [{result['lang']}]", "query": result["query"],
              "lang": result["lang"], "model": served, "created_at": _now(), "cost_usd": cost, "tokens": tokens,
              "data": data}
    _save_report(niche_key(result["query"], result["lang"]), report)
    return report


def make_channel_report(channel_id, model, client=None, niche=None):
    client = client or YouTubeClient()
    units_before = client.units_this_run
    payload, thumbs, title = channel_payload(client, channel_id)
    if niche:
        payload["ниша, в которой найден канал"] = niche
    data, tokens, cost, served = _ask(model, CHANNEL_TASK, payload, CHANNEL_SCHEMA, images=thumbs)
    report = {"kind": "channel", "title": title, "channel_id": channel_id, "model": served, "created_at": _now(),
              "cost_usd": cost, "tokens": tokens, "youtube_units": client.units_this_run - units_before,
              "data": data}
    _save_report(channel_key(channel_id), report)
    return report


def start(body, results):
    """Запускает разбор в фоне. Одновременно идёт только один разбор."""
    kind = body.get("kind")
    model = body.get("model") if body.get("model") in config.CLAUDE_MODELS else config.CLAUDE_MODEL
    if kind == "niche":
        result = next((r for r in results if r["query"].lower() == str(body.get("query", "")).lower()
                       and r["lang"] == body.get("lang")), None)
        if not result:
            raise ReportError("Ниша не найдена")
        title, key = f"{result['query']} [{result['lang']}]", niche_key(result["query"], result["lang"])
        job = lambda: make_niche_report(result, model)
    elif kind == "channel":
        cid = str(body.get("channel_id", ""))
        if not cid.startswith("UC"):
            raise ReportError("Неверный канал")
        title, key = body.get("title") or cid, channel_key(cid)
        job = lambda: make_channel_report(cid, model, niche=body.get("niche"))
    else:
        raise ReportError("Неизвестный разбор")
    if not config.ANTHROPIC_API_KEY:
        raise ReportError("Не задан ключ Claude API. Впишите его в «Ключи API».")
    if not _run_lock.acquire(blocking=False):
        raise ReportError("Уже идёт другой разбор, дождитесь его.")

    def worker():
        try:
            report = job()
            status.update(state="finished", key=key, cost_usd=report["cost_usd"])
        except ReportError as e:
            status.update(state="error", error=str(e))
        except Exception as e:
            status.update(state="error", error=f"Не удалось сделать разбор: {e}")
        finally:
            _run_lock.release()

    status.clear()
    status.update(state="running", kind=kind, title=title, model=model, started_at=_now())
    threading.Thread(target=worker, daemon=True).start()
