import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from niche_finder import config, pipeline
from niche_finder.scoring import analyze, parse_duration
from niche_finder.youtube import Cache, QuotaExhausted, QuotaTracker, YouTubeClient

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def channel(cid, subs, age_days, videos=20):
    created = (NOW - timedelta(days=age_days)).isoformat().replace("+00:00", "Z")
    return {"id": cid, "snippet": {"title": cid, "publishedAt": created},
            "statistics": {"subscriberCount": str(subs), "viewCount": "0", "videoCount": str(videos)}}


def video(vid, cid, views, minutes=15, tags=(), lang=None):
    sn = {"title": vid, "channelId": cid, "publishedAt": "2026-09-01T00:00:00Z", "tags": list(tags),
          "thumbnails": {"high": {"url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}}}
    if lang:
        sn["defaultAudioLanguage"] = lang
    return {"id": vid, "snippet": sn, "statistics": {"viewCount": str(views)},
            "contentDetails": {"duration": f"PT{minutes}M"}}


class ScoringTest(unittest.TestCase):
    def test_duration(self):
        self.assertEqual(parse_duration("PT1H2M3S"), 3723)
        self.assertEqual(parse_duration("PT45S"), 45)
        self.assertEqual(parse_duration("P1DT1S"), 86401)

    def test_good_niche_beats_saturated(self):
        good_ch = [channel(f"s{i}", 5_000, 400 if i > 2 else 40) for i in range(8)]
        good_v = [video(f"g{i}", f"s{i}", 60_000, tags=["cold case", "mystery"]) for i in range(8)]
        good = analyze("odd niche", "en", good_v, good_ch, now=NOW)

        bad_ch = [channel(f"b{i}", 3_000_000, 3000) for i in range(6)] + [channel(f"t{i}", 50_000, 2000) for i in range(6)]
        bad_v = [video(f"x{i}", f"b{i}", 500_000) for i in range(6)] + [video(f"y{i}", f"t{i}", 2_000) for i in range(6)]
        bad = analyze("mass niche", "en", bad_v, bad_ch, now=NOW)

        self.assertGreater(good["score"], 75)
        self.assertLess(bad["score"], 30)
        self.assertEqual(good["metrics"]["new_successful"], 3)
        self.assertEqual(bad["scores"]["competition"], 0)
        self.assertIn("cold case", good["related"])

    def test_filters_shorts_and_other_languages(self):
        chs = [channel("a", 1000, 500)]
        vids = [video("short", "a", 9999, minutes=1), video("de", "a", 9999, lang="de"), video("ok", "a", 5000, lang="en-US")]
        r = analyze("q", "en", vids, chs, now=NOW)
        self.assertEqual((r["videos_long"], r["skipped_short"], r["skipped_lang"]), (1, 1, 1))
        self.assertTrue(r["low_data"])

    def test_filters_foreign_titles_without_declared_language(self):
        chs = [channel("a", 1000, 500), channel("b", 1000, 500)]
        hindi = video("h", "a", 9999)
        hindi["snippet"]["title"] = "The Untold History of Air Plane || Hindi Documentary"
        script = video("s", "b", 9999)
        script["snippet"]["title"] = "हवाई जहाज का इतिहास"
        ok = video("ok", "b", 9999)
        ok["snippet"]["title"] = "L'histoire méconnue de l'aéronautique"
        r = analyze("q", "fr", [hindi, script, ok], chs, now=NOW)
        self.assertEqual((r["videos_long"], r["skipped_lang"], r["skipped_region"]), (1, 1, 1))

    def test_low_view_videos_are_not_hits(self):
        # у крошечных каналов ratio огромный, но до 10K просмотров не дотягивает никто
        chs = [channel(f"c{i}", 100, 500) for i in range(10)]
        vids = [video(f"v{i}", f"c{i}", 3_000) for i in range(10)]
        r = analyze("q", "en", vids, chs, now=NOW)
        self.assertEqual(r["scores"]["outlier"], 0)
        self.assertEqual(r["top_videos"], [])
        self.assertTrue(r["low_data"])

    def test_fresh_videos_and_market_threshold(self):
        chs = [channel(f"c{i}", 2_000, 500) for i in range(6)]
        fresh_hit = video("fh", "c0", 20_000)
        fresh_hit["snippet"]["publishedAt"] = "2026-09-28T00:00:00Z"
        fresh_low = video("fl", "c1", 900)
        fresh_low["snippet"]["publishedAt"] = "2026-09-28T00:00:00Z"
        old = [video(f"o{i}", f"c{i}", 6_000) for i in range(2, 6)]
        en = analyze("q", "en", [fresh_hit, fresh_low] + old, chs, now=NOW)
        de = analyze("q", "de", [fresh_hit, fresh_low] + old, chs, now=NOW)
        self.assertEqual(en["metrics"]["too_young"], 1)          # свежий без порога не учитывается
        self.assertEqual(en["metrics"]["hits_small"], 1)         # свежий с порогом идёт в зачёт, 6K < 10K
        self.assertEqual(de["metrics"]["hits_small"], 5)         # для DE порог 5K
        self.assertTrue(en["low_data"])                         # один ролик с порогом: оценке верить нельзя

    def test_new_channel_by_first_upload(self):
        # аккаунт 2019 года, но первый длинный ролик вышел месяц назад
        chs = [channel("old", 3_000, 2500, videos=8)]
        vids = [video("v", "old", 50_000)]
        uploads = {"old": ["2026-09-01T00:00:00Z", "2026-09-10T00:00:00Z", "2026-09-20T00:00:00Z"]}
        r = analyze("q", "en", vids, chs, now=NOW, uploads=uploads)
        self.assertEqual(r["metrics"]["new_successful"], 1)
        ch = r["channels"][0]
        self.assertTrue(ch["uploads_exact"])
        self.assertEqual(ch["long_uploads_90d"], 3)
        self.assertLess(ch["uploads_per_week"], 1)
        self.assertEqual(analyze("q", "en", vids, chs, now=NOW)["metrics"]["new_successful"], 0)

    def test_skips_south_asian_channels(self):
        chs = [channel("in", 3000, 500), channel("hg", 3000, 500), channel("ok", 3000, 500)]
        chs[0]["snippet"]["country"] = "IN"
        v_in = video("a", "in", 50_000, lang="en")          # английский ролик, но канал из Индии
        v_hg = video("b", "hg", 50_000)
        v_hg["snippet"]["title"] = "Titanic ka rahasya | sach kya hai"
        v_ok = video("c", "ok", 50_000)
        v_ok["snippet"]["title"] = "What really happened to the Titanic"
        r = analyze("q", "en", [v_in, v_hg, v_ok], chs, now=NOW)
        self.assertEqual((r["videos_long"], r["skipped_region"]), (1, 2))

    def test_evergreen_and_saturation(self):
        chs = [channel(f"c{i}", 5_000, 500) for i in range(6)]
        old = [video(f"o{i}", f"c{i}", 40_000) for i in range(6)]
        for v in old:
            v["snippet"]["publishedAt"] = "2026-05-01T00:00:00Z"
        trendy = [video(f"t{i}", f"c{i}", 40_000) for i in range(6)]
        for i, v in enumerate(trendy):
            v["snippet"]["title"] = f"iPhone 18 leaks 2026 #{i}"
        ever = analyze("q", "en", old, chs, now=NOW)
        trend = analyze("q", "en", trendy, chs, now=NOW)
        self.assertGreater(ever["scores"]["evergreen"], trend["scores"]["evergreen"])
        narrow = analyze("q", "en", old, chs, now=NOW, search_total=1_500)
        crowded = analyze("q", "en", old, chs, now=NOW, search_total=500_000)
        self.assertGreater(narrow["scores"]["competition"], crowded["scores"]["competition"])

    def test_growth_monetization_and_ideas(self):
        chs = [channel("young", 2_000, 120), channel("old", 50_000, 2000)]
        vids = [video("a", "young", 30_000, minutes=20, tags=["x"]), video("b", "old", 60_000, minutes=20)]
        r = analyze("q", "en", vids, chs, now=NOW)
        m = r["metrics"]
        self.assertEqual((m["young_channels"], m["young_1k"]), (1, 1))
        self.assertAlmostEqual(m["months_to_1k"], 2.0, delta=0.1)     # 2000 подписчиков за ~4 месяца
        self.assertEqual(m["views_for_4000h"], int(4000 * 60 / (20 * 0.35)))
        self.assertEqual(m["videos_for_4000h"], round(m["views_for_4000h"] / 45_000, 1))
        self.assertEqual(len(r["hit_titles"]), 2)
        inc = pipeline.income_estimate("en", "economics")
        self.assertEqual(inc["rpm"], round(config.RPM["en"] * 1.6, 2))
        self.assertLess(inc["per_views"]["100000"][0], inc["per_views"]["100000"][1])

    def test_empty(self):
        self.assertEqual(analyze("q", "en", [], [], now=NOW)["score"], 0)


class FakeClient(YouTubeClient):
    """Отвечает как API; первый ключ сразу «исчерпан»."""

    def __init__(self, tmp):
        self.calls = []
        super().__init__(keys=["KEY_ONE", "KEY_TWO"], cache=Cache(tmp / "cache"))
        self.quota = QuotaTracker(self.keys, path=tmp / "quota.json")

    def _http_get(self, url):
        self.calls.append(url)
        if "translate.googleapis" in url:
            return json.dumps([[["perdidos", "lost", None]]]).encode()
        if "suggestqueries" in url:
            return json.dumps(["q", ["q one", "q two"]]).encode()
        if "KEY_ONE" in url:
            body = json.dumps({"error": {"errors": [{"reason": "quotaExceeded"}]}}).encode()
            raise urllib.error.HTTPError(url, 403, "quota", {}, BytesIO(body))
        if "/search?" in url:
            return json.dumps({"items": [{"id": {"videoId": "v1"}}, {"id": {"videoId": "v2"}}]}).encode()
        if "/videos?" in url:
            return json.dumps({"items": [video("v1", "c1", 50_000), video("v2", "c1", 20_000)]}).encode()
        if "/playlistItems?" in url:
            return json.dumps({"items": [{"contentDetails": {"videoPublishedAt": "2026-09-01T00:00:00Z",
                                                             "videoId": "v1"}},
                                         {"contentDetails": {"videoPublishedAt": "2026-08-01T00:00:00Z",
                                                             "videoId": "v2"}}]}).encode()
        if "/commentThreads?" in url:
            return json.dumps({"items": [{"snippet": {"topLevelComment": {"snippet": {
                "textDisplay": "great story", "likeCount": 5}}}}]}).encode()
        if "/channels?" in url:
            return json.dumps({"items": [channel("c1", 4_000, 60)]}).encode()
        raise AssertionError(url)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (config.RESULTS_FILE, config.VAULT_FILE, config.AUTO_FILE)
        config.RESULTS_FILE = self.tmp / "results.json"
        config.VAULT_FILE = self.tmp / "vault.json"
        config.AUTO_FILE = self.tmp / "autopilot.json"

    def tearDown(self):
        config.RESULTS_FILE, config.VAULT_FILE, config.AUTO_FILE = self._orig

    def test_rotation_cache_and_expand(self):
        client = FakeClient(self.tmp)
        status = pipeline.run(["q"], ["en"], expand=2, max_niches=3, client=client)
        self.assertEqual(status["state"], "finished")
        self.assertEqual(status["done"], 3)
        self.assertEqual(status["units"], 3 * 200 + 3)  # 2 поиска на нишу (medium + long), повторы из кэша  # одинаковые videos/channels берутся из кэша
        self.assertEqual({r["query"] for r in pipeline.load_results()}, {"q", "q one", "q two"})
        self.assertTrue(client.quota.summary()["keys"][0]["exhausted"])
        self.assertEqual(sum("key=KEY_ONE" in u for u in client.calls), 1)  # после исчерпания ключ не трогаем

        # повторный запуск идёт из кэша и квоту не тратит
        client2 = FakeClient(self.tmp)
        status2 = pipeline.run(["q"], ["en"], expand=2, max_niches=3, client=client2)
        self.assertEqual(status2["units"], 0)
        self.assertEqual(client2.calls, [])

    def test_translate_topic(self):
        client = FakeClient(self.tmp)
        plan = pipeline.plan_queries(client, ["lost"], ["es"], 0, 5, translate=True)
        self.assertEqual(plan, [("perdidos", "es")])

    def test_autopilot_scouts_deepens_and_queues(self):
        client = FakeClient(self.tmp)
        status = pipeline.run_auto(["en"], budget=1000, client=client)
        self.assertEqual(status["state"], "finished")
        self.assertLessEqual(status["units"], 1000)
        results = pipeline.load_results()
        depths = [r["depth"] for r in results]
        self.assertIn("scout", depths)
        self.assertIn("full", depths)
        self.assertTrue(all(r["source"] == "auto" and r["category"] for r in results))
        state = pipeline.load_auto_state()
        self.assertEqual(state["runs"], 1)
        self.assertTrue(state["seeded"]["en"])
        # следующий запуск не повторяет уже разобранные темы
        before = {r["query"] for r in results}
        pipeline.run_auto(["en"], budget=1000, client=FakeClient(self.tmp))
        after = [r["query"] for r in pipeline.load_results()]
        self.assertEqual(len(after), len(set(after)))
        self.assertGreater(len(set(after)), len(before))

    def test_vault_keeps_status_and_respects_rejection(self):
        r = {"query": "Odd Niche", "lang": "en", "score": 80, "depth": "full", "low_data": False}
        pipeline.save_result(r)                       # хороший балл: попадает в хранилище сам
        vault = pipeline.load_vault()
        self.assertEqual((len(vault), vault[0]["added_by"]), (1, "auto"))
        key = vault[0]["key"]
        pipeline.vault_update(key, status="Беру в работу", note="снимаю в ноябре")
        pipeline.save_result(dict(r, score=85))       # повторный анализ обновляет оценку, но не статус
        v = pipeline.load_vault()[0]
        self.assertEqual((v["score"], v["status"], v["note"]), (85, "Беру в работу", "снимаю в ноябре"))
        pipeline.vault_update(key, status="Отказ")
        pipeline.save_result(dict(r, score=90))       # отказ автопоиск не перебивает
        self.assertEqual(pipeline.load_vault()[0]["score"], 85)
        pipeline.save_result({"query": "weak", "lang": "en", "score": 40, "depth": "full", "low_data": False})
        pipeline.save_result({"query": "scout", "lang": "en", "score": 90, "depth": "scout", "low_data": False})
        self.assertEqual(len(pipeline.load_vault()), 1)
        self.assertTrue(pipeline.vault_add_by_key("weak", "en"))
        self.assertEqual(len(pipeline.load_vault()), 2)
        pipeline.vault_remove(key)
        self.assertEqual([v["query"] for v in pipeline.load_vault()], ["weak"])

    def test_settings_and_free_recheck(self):
        orig_file = config.SETTINGS_FILE
        config.SETTINGS_FILE = self.tmp / "settings.json"
        try:
            client = FakeClient(self.tmp)
            pipeline.run(["q"], ["en"], max_niches=1, client=client)
            before = pipeline.load_results()[0]
            # мусор и выход за пределы отбрасываются или зажимаются
            changed = config.save_settings({"min_views_en": 30_000, "weight_outlier": 100, "weight_format": 0,
                                            "uploads_check_channels": 999, "search_durations": "bogus",
                                            "exclude_countries": " in, pk ,"})
            self.assertEqual(config.MIN_VIEWS["en"], 30_000)
            self.assertEqual(config.UPLOADS_CHECK_CHANNELS, 50)
            self.assertEqual(config.SEARCH_DURATIONS, ["medium", "long"])
            self.assertEqual(config.EXCLUDE_COUNTRIES, {"IN", "PK"})
            self.assertIn("weight_outlier", changed)
            self.assertEqual(json.loads(config.SETTINGS_FILE.read_text())["min_views_en"], 30_000)

            status = pipeline.recheck_cached(cache=Cache(self.tmp / "cache"))
            self.assertEqual((status["state"], status["units"], status["from_cache"]), ("finished", 0, 1))
            after = pipeline.load_results()[0]
            self.assertEqual(after["metrics"]["hits_small"], 1)   # 20K-ролик ниже нового порога 30K
            self.assertLess(after["metrics"]["hits_small"], before["metrics"]["hits_small"])

            # без кэша ниша пересчитывается только по весам
            status = pipeline.recheck_cached(cache=Cache(self.tmp / "empty"))
            self.assertEqual(status["weights_only"], 1)
            r = pipeline.load_results()[0]
            weights = {"outlier": 100, "new_channels": 20, "competition": 15, "evergreen": 15, "stability": 10}
            self.assertEqual(r["score"], round(sum(r["scores"][k] * w for k, w in weights.items()) / 160))
        finally:
            config.reset_settings()
            config.SETTINGS_FILE = orig_file
        self.assertEqual(config.current_settings(), config.SETTINGS_DEFAULTS)
        self.assertEqual(config.WEIGHTS["outlier"], 30)

    def test_reports_collect_data_and_parse_claude_answer(self):
        from niche_finder import reports
        orig = (config.REPORTS_FILE, config.ANTHROPIC_API_KEY, reports._client)
        config.REPORTS_FILE = self.tmp / "reports.json"
        config.ANTHROPIC_API_KEY = "test"
        sent = {}

        class Stream:
            def __init__(self, **kw):
                sent.update(kw)
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def get_final_message(self):
                text = json.dumps({"summary": "ok", "verdict": {"score": 7}})
                return type("R", (), {"stop_reason": "end_turn", "model": sent["model"],
                                      "content": [type("B", (), {"type": "text", "text": text})()],
                                      "usage": type("U", (), {"input_tokens": 1_000_000, "output_tokens": 100_000,
                                                              "cache_creation_input_tokens": 0,
                                                              "cache_read_input_tokens": 0})()})()

        fake = type("C", (), {})()
        fake.beta = type("B", (), {"messages": type("M", (), {"stream": staticmethod(lambda **kw: Stream(**kw))})()})()
        reports._client = lambda: fake
        try:
            client = FakeClient(self.tmp)
            rep = reports.make_channel_report("UCabc", "claude-sonnet-5-5", client=client, niche="q")
            self.assertEqual(rep["data"]["verdict"]["score"], 7)
            self.assertEqual(rep["cost_usd"], 3.0)                      # 1M входа × $2 + 0.1M выхода × $10
            self.assertGreater(rep["youtube_units"], 0)
            content = sent["messages"][0]["content"]
            self.assertEqual(content[0]["type"], "image")                # обложки идут картинками
            self.assertIn("great story", content[-1]["text"])            # комментарии зрителей в данных
            self.assertEqual(sent["output_config"]["format"]["type"], "json_schema")
            self.assertIn("channel|UCabc", reports.load_reports())

            pipeline.run(["q"], ["en"], max_niches=1, client=FakeClient(self.tmp))
            rep = reports.make_niche_report(pipeline.load_results()[0], "claude-opus-5-5")
            self.assertEqual(rep["cost_usd"], 6.0)
            self.assertIn("успешные ролики малых каналов", sent["messages"][0]["content"][-1]["text"])
            with self.assertRaises(reports.ReportError):
                config.ANTHROPIC_API_KEY = ""
                reports.start({"kind": "niche", "query": "q", "lang": "en"}, pipeline.load_results())
        finally:
            config.REPORTS_FILE, config.ANTHROPIC_API_KEY, reports._client = orig

    def test_all_keys_exhausted(self):
        client = FakeClient(self.tmp)
        client.quota.mark("KEY_TWO", "exhausted")
        status = pipeline.run(["q"], ["en"], client=client)
        self.assertEqual(status["state"], "quota_exhausted")
        with self.assertRaises(QuotaExhausted):
            client.search_videos("other", "en")


class UpdaterTest(unittest.TestCase):
    def test_copy_parts_keeps_data(self):
        from niche_finder import updater
        tmp = Path(tempfile.mkdtemp())
        src, dest = tmp / "src", tmp / "dest"
        (src / "niche_finder").mkdir(parents=True)
        (src / "niche_finder" / "new.py").write_text("new")
        (src / "VERSION").write_text("2")
        (dest / "niche_finder").mkdir(parents=True)
        (dest / "niche_finder" / "old.py").write_text("old")
        (dest / "data").mkdir()
        (dest / "data" / ".env").write_text("YOUTUBE_API_KEYS=x")
        updater._copy_parts(src, dest)
        self.assertEqual(sorted(p.name for p in (dest / "niche_finder").iterdir()), ["new.py"])
        self.assertEqual((dest / "VERSION").read_text(), "2")
        self.assertEqual((dest / "data" / ".env").read_text(), "YOUTUBE_API_KEYS=x")

    def test_check_reports_newer_version(self):
        from niche_finder import updater
        orig = updater._latest
        updater._latest = lambda fresh=False: {"version": updater.current() + 1, "notes": "x"}
        try:
            self.assertTrue(updater.check()["available"])
        finally:
            updater._latest = orig


if __name__ == "__main__":
    unittest.main()
