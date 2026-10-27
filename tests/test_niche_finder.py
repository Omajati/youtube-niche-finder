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
    sn = {"title": vid, "channelId": cid, "publishedAt": "2026-09-01T00:00:00Z", "tags": list(tags)}
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
        self.assertEqual((r["videos_long"], r["skipped_lang"]), (1, 2))

    def test_low_view_videos_are_not_hits(self):
        # у крошечных каналов ratio огромный, но до 10K просмотров не дотягивает никто
        chs = [channel(f"c{i}", 100, 500) for i in range(10)]
        vids = [video(f"v{i}", f"c{i}", 3_000) for i in range(10)]
        r = analyze("q", "en", vids, chs, now=NOW)
        self.assertEqual(r["scores"]["outlier"], 0)
        self.assertEqual(r["top_videos"], [])
        self.assertTrue(r["low_data"])

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
        if "suggestqueries" in url:
            return json.dumps(["q", ["q one", "q two"]]).encode()
        if "KEY_ONE" in url:
            body = json.dumps({"error": {"errors": [{"reason": "quotaExceeded"}]}}).encode()
            raise urllib.error.HTTPError(url, 403, "quota", {}, BytesIO(body))
        if "/search?" in url:
            return json.dumps({"items": [{"id": {"videoId": "v1"}}, {"id": {"videoId": "v2"}}]}).encode()
        if "/videos?" in url:
            return json.dumps({"items": [video("v1", "c1", 50_000), video("v2", "c1", 20_000)]}).encode()
        if "/channels?" in url:
            return json.dumps({"items": [channel("c1", 4_000, 60)]}).encode()
        raise AssertionError(url)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = config.RESULTS_FILE
        config.RESULTS_FILE = self.tmp / "results.json"

    def tearDown(self):
        config.RESULTS_FILE = self._orig

    def test_rotation_cache_and_expand(self):
        client = FakeClient(self.tmp)
        status = pipeline.run(["q"], ["en"], expand=2, max_niches=3, client=client)
        self.assertEqual(status["state"], "finished")
        self.assertEqual(status["done"], 3)
        self.assertEqual(status["units"], 3 * 200 + 2)  # 2 поиска на нишу (medium + long)  # одинаковые videos/channels берутся из кэша
        self.assertEqual({r["query"] for r in pipeline.load_results()}, {"q", "q one", "q two"})
        self.assertTrue(client.quota.summary()["keys"][0]["exhausted"])
        self.assertEqual(sum("key=KEY_ONE" in u for u in client.calls), 1)  # после исчерпания ключ не трогаем

        # повторный запуск идёт из кэша и квоту не тратит
        client2 = FakeClient(self.tmp)
        status2 = pipeline.run(["q"], ["en"], expand=2, max_niches=3, client=client2)
        self.assertEqual(status2["units"], 0)
        self.assertEqual(client2.calls, [])

    def test_all_keys_exhausted(self):
        client = FakeClient(self.tmp)
        client.quota.mark("KEY_TWO", "exhausted")
        status = pipeline.run(["q"], ["en"], client=client)
        self.assertEqual(status["state"], "quota_exhausted")
        with self.assertRaises(QuotaExhausted):
            client.search_videos("other", "en")


if __name__ == "__main__":
    unittest.main()
