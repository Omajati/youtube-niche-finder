"""Запуск анализа: по запросу, автопоиск по каталогу вечнозелёных тем и хранилище подходящих ниш."""
import json
import random
import threading
from datetime import datetime, timezone

from . import config
from .catalog import CATEGORIES, RPM_FACTOR
from .scoring import analyze, is_excluded_channel, weighted_total
from .youtube import NoApiKeys, QuotaExhausted, YouTubeClient

# Стартовые темы для поиска по запросу, если тема не задана: по первому запросу каждой категории
DEFAULT_SEEDS = {lang: [c["seeds"][lang][0] for c in CATEGORIES[:6]] for lang in config.LANGUAGES}

# Стоимость в единицах квоты. Разведка: один поиск (100) + статистика роликов и каналов.
# Полный анализ: поиск по каждой длительности, статистика и последние ролики малых каналов.
# Поиск разведки берётся из кэша, поэтому полный анализ после разведки стоит на 100 меньше.
UNITS_SCOUT = 102


def units_per_niche():
    return 100 * max(len(config.SEARCH_DURATIONS), 1) + 4 + config.UPLOADS_CHECK_CHANNELS


def units_deep_after_scout():
    return units_per_niche() - 100

# В хранилище сами попадают ниши с полным анализом, достаточными данными и баллом от config.VAULT_MIN_SCORE

_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _key(query, lang):
    return f"{lang}|{query.lower().strip()}"


# --- результаты ---

def load_results():
    return _read(config.RESULTS_FILE, [])


def save_result(item):
    with _lock:
        results = [r for r in load_results() if _key(r["query"], r["lang"]) != _key(item["query"], item["lang"])]
        results.append(item)
        _write(config.RESULTS_FILE, results)
    if (item.get("depth", "full") == "full" and not item.get("low_data")
            and item.get("score", 0) >= config.VAULT_MIN_SCORE):
        vault_add(item, auto=True)


def delete_result(query, lang):
    with _lock:
        _write(config.RESULTS_FILE, [r for r in load_results() if _key(r["query"], r["lang"]) != _key(query, lang)])


# --- хранилище подходящих ниш ---

VAULT_STATUSES = ["Новая", "Изучаю", "Беру в работу", "Отказ"]


def load_vault():
    return _read(config.VAULT_FILE, [])


def vault_add(result, auto=False):
    """Кладёт нишу в хранилище со снимком её оценки. Статус и заметка, если уже были, сохраняются."""
    with _lock:
        vault = load_vault()
        key = _key(result["query"], result["lang"])
        old = next((v for v in vault if v["key"] == key), None)
        if old and auto and old.get("status") == "Отказ":
            return
        entry = {
            "key": key,
            "query": result["query"],
            "lang": result["lang"],
            "category": result.get("category", ""),
            "topic": result.get("topic", ""),             # общая тема переводов: связывает языки
            "topic_title": result.get("topic_title", ""),
            "score": result.get("score", 0),
            "scores": result.get("scores", {}),
            "metrics": result.get("metrics", {}),
            "top_videos": result.get("top_videos", [])[:4],
            "analyzed_at": result.get("analyzed_at", ""),
            "added_at": old["added_at"] if old else _now(),
            "added_by": old["added_by"] if old else ("auto" if auto else "manual"),
            "status": old["status"] if old else VAULT_STATUSES[0],
            "note": old["note"] if old else "",
        }
        vault = [v for v in vault if v["key"] != key] + [entry]
        _write(config.VAULT_FILE, vault)


def vault_update(key, status=None, note=None):
    with _lock:
        vault = load_vault()
        for v in vault:
            if v["key"] == key:
                if status in VAULT_STATUSES:
                    v["status"] = status
                if note is not None:
                    v["note"] = str(note)[:2000]
        _write(config.VAULT_FILE, vault)


def vault_remove(key):
    with _lock:
        _write(config.VAULT_FILE, [v for v in load_vault() if v["key"] != key])


def vault_add_by_key(query, lang):
    r = next((r for r in load_results() if _key(r["query"], r["lang"]) == _key(query, lang)), None)
    if r:
        vault_add(r)
    return bool(r)


# --- анализ одной ниши ---

def income_estimate(lang, category=""):
    """Примерный RPM и доход в месяц при 100K, 500K и 1M просмотров (нижняя и верхняя граница)."""
    rpm = config.RPM.get(lang, config.RPM["en"]) * RPM_FACTOR.get(category, 1.0)
    lo, hi = rpm * 0.6, rpm * 1.4
    return {"rpm": round(rpm, 2), "rpm_low": round(lo, 2), "rpm_high": round(hi, 2),
            "per_views": {str(n): [round(n / 1000 * lo), round(n / 1000 * hi)] for n in (100_000, 500_000, 1_000_000)}}


def analyze_niche(client, query, lang, deep=True, meta=None, suggestions=None):
    """deep=False: разведка, один поиск и без последних роликов каналов (≈102 единицы)."""
    client.search_totals.pop((query.lower(), lang), None)
    durations = (config.SEARCH_DURATIONS or [None]) if deep else (config.SEARCH_DURATIONS or [None])[:1]
    video_ids = []
    for duration in durations:
        video_ids += client.search_videos(query, lang, duration)
    videos = client.videos(video_ids)
    channel_ids = [v["snippet"]["channelId"] for v in videos]
    channels = client.channels(channel_ids)
    uploads = {}
    if deep:
        # Реальная частота загрузок и дата первого ролика: только у малых каналов, они и есть ориентир
        small = [c for c in channels if not c["statistics"].get("hiddenSubscriberCount")
                 and not is_excluded_channel(c["snippet"].get("country"))
                 and int(c["statistics"].get("subscriberCount", 0)) <= config.SMALL_CHANNEL_MAX_SUBS]
        small.sort(key=lambda c: int(c["statistics"].get("subscriberCount", 0)))
        for c in small[:config.UPLOADS_CHECK_CHANNELS]:
            try:
                uploads[c["id"]] = client.recent_uploads(c["id"])
            except NoApiKeys:   # пересчёт из кэша: этого канала в кэше нет, частота будет оценена грубо
                pass
    total = client.search_totals.get((query.lower(), lang))
    result = analyze(query, lang, videos, channels, uploads=uploads, search_total=total)
    result.update(depth="full" if deep else "scout", **(meta or {}))
    result["income"] = income_estimate(lang, result.get("category", ""))
    if suggestions is None and deep:
        try:   # подсказки YouTube бесплатны: это ещё темы внутри ниши
            suggestions = [s for s in client.suggest(query, lang) if s.lower() != query.lower()]
        except Exception:
            suggestions = []
    result["suggestions"] = suggestions or []
    result["metrics"]["ideas_total"] = result["metrics"].get("ideas_hits", 0) + len(result["suggestions"])
    return result


# --- поиск по запросу ---

def plan_queries(client, queries, langs, expand, max_niches, translate=False, topics=None):
    """Список (запрос, язык). expand > 0 добавляет N подсказок YouTube к каждому запросу.
    translate=True переводит каждую тему на язык рынка. В topics (если передан словарь)
    попадает исходная тема каждого перевода, чтобы потом сравнить её на разных языках."""
    plan = []
    for lang in langs:
        base = queries or DEFAULT_SEEDS.get(lang, [])
        if queries and translate:
            base = [client.translate(q, lang) for q in queries]
            if topics is not None:
                for orig, q in zip(queries, base):
                    topics[(q, lang)] = orig
        for q in base:
            items = [q]
            if expand:
                items += [s for s in client.suggest(q, lang) if s.lower() != q.lower()][:expand]
            for item in items:
                if (item, lang) not in plan:
                    plan.append((item, lang))
    return plan[:max_niches]


def _new_status():
    return {"state": "running", "done": 0, "total": 0, "current": None, "errors": [], "units": 0}


def _analyze_step(client, status, report, query, lang, deep, meta):
    """Анализирует и сохраняет одну нишу. False, если дальше идти нельзя (кончилась квота, нет ключей)."""
    status["current"] = f"{query} [{lang}]" + ("" if deep else " · разведка")
    report(status)
    try:
        result = analyze_niche(client, query, lang, deep=deep, meta=meta)
        save_result(result)
        return result
    except QuotaExhausted as e:
        status["errors"].append(str(e))
        status["state"] = "quota_exhausted"
        return False
    except NoApiKeys as e:
        status["errors"].append(str(e))
        status["state"] = "error"
        return False
    except Exception as e:  # одна неудачная ниша не должна ронять весь запуск
        status["errors"].append(f"{query} [{lang}]: {e}")
        return None
    finally:
        status["done"] += 1
        status["units"] = client.units_this_run
        report(status)


def _finish(status, client, report):
    if status["state"] == "running":
        status["state"] = "finished"
    status["current"] = None
    status["units"] = client.units_this_run
    report(status)
    return status


def run(queries, langs, expand=0, max_niches=10, progress=None, client=None, translate=False):
    """Анализирует ниши по очереди. progress(dict) получает статус после каждого шага."""
    client = client or YouTubeClient()
    report = progress or (lambda s: None)
    status = _new_status()
    topics = {}
    plan = plan_queries(client, queries, langs, expand, max_niches, translate, topics)
    status["total"] = len(plan)
    status["plan"] = [f"{q} [{lang}]" for q, lang in plan]
    report(status)
    for query, lang in plan:
        meta = {"source": "manual"}
        if (query, lang) in topics and len(langs) > 1:   # переводы одной темы попадают в сравнение языков
            orig = topics[(query, lang)]
            meta.update(topic=f"q|{orig.lower().strip()}", topic_title=orig)
        if _analyze_step(client, status, report, query, lang, True, meta) is False:
            break
    return _finish(status, client, report)


# --- сравнение одной ниши на разных языках ---

def run_compare(query, lang, langs=None, progress=None, client=None):
    """Переводит тему на другие рынки и делает полный анализ на каждом, чтобы сравнить баллы.
    Все ниши группы получают общий topic, по нему дашборд строит таблицу сравнения."""
    client = client or YouTubeClient()
    report = progress or (lambda s: None)
    status = _new_status()
    status["mode"] = "compare"
    langs = [l for l in (langs or config.LANGUAGES) if l in config.LANGUAGES and l != lang]
    results = {_key(r["query"], r["lang"]): r for r in load_results()}
    source = results.get(_key(query, lang), {})
    topic = source.get("topic") or _key(query, lang)
    title = source.get("topic_title") or query
    plan = [(query, lang)] + [(client.translate(query, l), l) for l in langs]
    status["total"] = len(plan)
    status["plan"] = [f"{q} [{l}]" for q, l in plan]
    report(status)
    for q, l in plan:   # повторное сравнение берёт данные из кэша, квота почти не тратится
        old = results.get(_key(q, l), {})
        meta = {"source": old.get("source", "compare"), "category": source.get("category", old.get("category", "")),
                "parent": old.get("parent", ""), "topic": topic, "topic_title": title}
        if _analyze_step(client, status, report, q, l, True, meta) is False:
            break
    return _finish(status, client, report)


# --- автопоиск ---

def load_auto_state():
    state = _read(config.AUTO_FILE, {})
    state.setdefault("queue", [])        # подниши лучших ниш, ждут разведки в следующих запусках
    state.setdefault("seeded", {})       # сколько раз категория уже давала темы, по языкам
    state.setdefault("runs", 0)
    return state


def _seed_candidates(client, state, langs, limit):
    """Темы из каталога: категории, которые разведывали реже всего, их запрос и подсказки YouTube."""
    done = {_key(r["query"], r["lang"]) for r in load_results()}
    out = []
    for lang in langs:
        seeded = state["seeded"].setdefault(lang, {})
        cats = sorted(CATEGORIES, key=lambda c: (seeded.get(c["id"], 0), random.random()))
        for cat in cats:
            if len([c for c in out if c["lang"] == lang]) >= limit:
                break
            n = seeded.get(cat["id"], 0)
            seeds = cat["seeds"][lang]
            seed = seeds[n % len(seeds)]
            # первый заход по категории берёт сам запрос, следующие уходят в подсказки YouTube
            options = [seed] + [s for s in client.suggest(seed, lang) if s.lower() != seed.lower()]
            pick = next((o for o in options[(n // len(seeds)):] if _key(o, lang) not in done), None)
            seeded[cat["id"]] = n + 1
            if pick:
                out.append({"query": pick, "lang": lang, "category": cat["id"], "parent": seed})
    return out


def _expand(client, state, result):
    """Лучшая ниша даёт подниши для следующих запусков: подсказки YouTube и теги успешных роликов."""
    done = {_key(r["query"], r["lang"]) for r in load_results()}
    queued = {_key(q["query"], q["lang"]) for q in state["queue"]}
    lang = result["lang"]
    ideas = [s for s in client.suggest(result["query"], lang) if s.lower() != result["query"].lower()][:4]
    ideas += result.get("related", [])[:3]
    for idea in ideas:
        k = _key(idea, lang)
        if k in done or k in queued:
            continue
        queued.add(k)
        state["queue"].append({"query": idea, "lang": lang, "category": result.get("category", ""),
                               "parent": result["query"], "priority": result["score"]})


def run_auto(langs, budget=3000, progress=None, client=None):
    """Автопоиск: разведка широкого круга тем → полный анализ лучших → подниши лучших в очередь.

    Бюджет делится примерно так: 60% на разведку, 40% на полный анализ.
    Очередь и пройденные категории хранятся между запусками, поэтому каждый запуск идёт дальше.
    """
    client = client or YouTubeClient()
    report = progress or (lambda s: None)
    status = _new_status()
    status["mode"] = "auto"
    state = load_auto_state()
    langs = [l for l in langs if l in config.LANGUAGES] or ["en"]

    n_scout = max(1, int(budget * 0.6) // UNITS_SCOUT)
    n_deep = max(1, (budget - n_scout * UNITS_SCOUT) // units_deep_after_scout())
    status["total"] = n_scout + n_deep
    status["phase"] = "разведка"
    report(status)

    # 1. Кого разведываем: половина из очереди подниш (лучшие родители первыми), половина из каталога
    done = {_key(r["query"], r["lang"]) for r in load_results()}
    state["queue"] = [q for q in state["queue"] if _key(q["query"], q["lang"]) not in done and q["lang"] in langs]
    state["queue"].sort(key=lambda q: -q.get("priority", 0))
    from_queue = state["queue"][:n_scout // 2]
    state["queue"] = state["queue"][len(from_queue):]
    per_lang = -(-(n_scout - len(from_queue)) // len(langs))
    picks = from_queue + _seed_candidates(client, state, langs, per_lang)
    picks = picks[:n_scout]
    _write(config.AUTO_FILE, state)

    scouted = []
    for p in picks:
        if client.units_this_run + UNITS_SCOUT > budget:
            break
        meta = {"source": "auto", "category": p.get("category", ""), "parent": p.get("parent", "")}
        r = _analyze_step(client, status, report, p["query"], p["lang"], False, meta)
        if r is False:
            break
        if r:
            scouted.append((r, meta))

    # 2. Полный анализ лучших по разведке
    if status["state"] == "running":
        status["phase"] = "полный анализ"
        ranked = sorted(scouted, key=lambda rm: (rm[0].get("low_data", True), -rm[0]["score"]))
        for r, meta in ranked[:n_deep]:
            if client.units_this_run + units_deep_after_scout() > budget:
                break
            full = _analyze_step(client, status, report, r["query"], r["lang"], True, meta)
            if full is False:
                break
            # 3. Подниши хороших ниш идут в очередь следующих запусков
            if full and full["score"] >= 50:
                _expand(client, state, full)

    state["runs"] += 1
    state["last_run"] = _now()
    _write(config.AUTO_FILE, state)
    status["queue"] = len(state["queue"])
    return _finish(status, client, report)


def auto_summary():
    state = load_auto_state()
    results = load_results()
    return {
        "runs": state["runs"],
        "last_run": state.get("last_run"),
        "queue": len(state["queue"]),
        "categories": len(CATEGORIES),
        "category_names": {c["id"]: c["name"] for c in CATEGORIES},
        "explored": sum(1 for r in results if r.get("source") == "auto"),
        "units_scout": UNITS_SCOUT,
        "units_deep": units_deep_after_scout(),
    }


# --- пересчёт по новым настройкам ---

META_FIELDS = ("source", "category", "parent", "topic", "topic_title")


def recheck_cached(progress=None, cache=None):
    """Пересчитывает все найденные ниши по текущим настройкам из кэша, квоту не тратит.

    Ниша, чьих данных в кэше уже нет (поиск хранится 3 дня), пересчитывается только по новым весам.
    """
    report = progress or (lambda s: None)
    client = YouTubeClient(keys=[], cache=cache)   # без ключей: только кэш, запросов к API нет
    status = _new_status()
    status["mode"] = "recheck"
    status["from_cache"] = status["weights_only"] = 0
    results = load_results()
    status["total"] = len(results)
    report(status)
    for old in results:
        status["current"] = f"{old['query']} [{old['lang']}]"
        meta = {k: old[k] for k in META_FIELDS if k in old}
        try:
            new = analyze_niche(client, old["query"], old["lang"], deep=old.get("depth", "full") == "full", meta=meta,
                                suggestions=old.get("suggestions", []))
            new["analyzed_at"] = old.get("analyzed_at", new.get("analyzed_at"))
            status["from_cache"] += 1
        except NoApiKeys:
            new = dict(old, score=round(weighted_total(old.get("scores", {}))),
                       income=income_estimate(old["lang"], old.get("category", "")))
            status["weights_only"] += 1
        except Exception as e:
            status["errors"].append(f"{old['query']} [{old['lang']}]: {e}")
            new = old
        save_result(new)
        status["done"] += 1
        report(status)
    # оценки в хранилище тоже по новым весам, статусы и заметки остаются
    with _lock:
        fresh = {_key(r["query"], r["lang"]): r for r in load_results()}
        vault = load_vault()
        for v in vault:
            r = fresh.get(v["key"])
            if r:
                v.update(score=r["score"], scores=r.get("scores", {}), metrics=r.get("metrics", {}),
                         topic=r.get("topic", ""), topic_title=r.get("topic_title", ""))
        _write(config.VAULT_FILE, vault)
    return _finish(status, client, report)
