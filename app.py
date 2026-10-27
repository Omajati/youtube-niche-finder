"""Локальный веб-сервер с дашбордом: python app.py, затем открыть http://localhost:8000"""
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from niche_finder import config, pipeline
from niche_finder.youtube import YouTubeClient

DASHBOARD = config.ROOT / "dashboard" / "index.html"

run_status = {"state": "idle"}
run_lock = threading.Lock()


def start_run(body):
    langs = [l for l in body.get("langs", []) if l in config.LANGUAGES] or ["en"]
    queries = [q.strip() for q in body.get("queries", []) if q.strip()]
    expand = max(0, min(int(body.get("expand", 0)), 10))
    max_niches = max(1, min(int(body.get("max_niches", 10)), 50))

    def progress(status):
        run_status.clear()
        run_status.update(status)

    def worker():
        try:
            pipeline.run(queries, langs, expand, max_niches, progress=progress)
        except Exception as e:
            run_status.update(state="error", errors=[str(e)])
        finally:
            run_lock.release()

    if not run_lock.acquire(blocking=False):
        return False
    run_status.clear()
    run_status.update(state="running", done=0, total=0, errors=[])
    threading.Thread(target=worker, daemon=True).start()
    return True


class Handler(BaseHTTPRequestHandler):
    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = DASHBOARD.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/results":
            self._json(pipeline.load_results())
        elif self.path == "/api/status":
            self._json(run_status)
        elif self.path == "/api/config":
            self._json({
                "languages": config.LANGUAGES,
                "seeds": pipeline.DEFAULT_SEEDS,
                "units_per_niche": pipeline.UNITS_PER_NICHE,
                "keys_configured": len(config.API_KEYS),
                "quota": YouTubeClient().quota.summary(),
                "criteria": {
                    "min_duration_min": config.MIN_DURATION_SEC // 60,
                    "small_channel_max_subs": config.SMALL_CHANNEL_MAX_SUBS,
                    "big_channel_subs": config.BIG_CHANNEL_SUBS,
                    "new_channel_days": config.NEW_CHANNEL_DAYS,
                    "search_published_days": config.SEARCH_PUBLISHED_DAYS,
                },
            })
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        if self.path == "/api/run":
            if start_run(body):
                self._json({"ok": True})
            else:
                self._json({"error": "Анализ уже идёт"}, 409)
        elif self.path == "/api/delete":
            with pipeline._lock:
                results = [r for r in pipeline.load_results()
                           if not (r["query"] == body.get("query") and r["lang"] == body.get("lang"))]
                config.RESULTS_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", config.PORT), Handler)
    url = f"http://localhost:{config.PORT}"
    print(f"Дашборд: {url}  (Ctrl+C чтобы остановить)")
    if not config.API_KEYS:
        print("Внимание: ключи не найдены. Скопируйте .env.example в .env и впишите YOUTUBE_API_KEYS.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
