"""Локальный веб-сервер с дашбордом.

python3 app.py           открыть в браузере
python3 app.py --window  своё окно (так запускает приложение «Поиск ниш» на Mac)
"""
import json
import os
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from niche_finder import config, pipeline, updater
from niche_finder.youtube import YouTubeClient

DASHBOARD = config.ROOT / "dashboard" / "index.html"

run_status = {"state": "idle"}
run_lock = threading.Lock()


def start_run(body):
    langs = [l for l in body.get("langs", []) if l in config.LANGUAGES] or ["en"]
    queries = [q.strip() for q in body.get("queries", []) if q.strip()]
    expand = max(0, min(int(body.get("expand", 0)), 10))
    max_niches = max(1, min(int(body.get("max_niches", 10)), 50))
    translate = bool(body.get("translate"))
    auto = body.get("mode") == "auto"
    budget = max(500, min(int(body.get("budget", 3000)), 40_000))

    def progress(status):
        run_status.clear()
        run_status.update(status)

    def worker():
        try:
            if auto:
                pipeline.run_auto(langs, budget, progress=progress)
            else:
                pipeline.run(queries, langs, expand, max_niches, progress=progress, translate=translate)
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
        if self.path in ("/icon.png", "/favicon.ico"):
            body = (config.ROOT / "dashboard" / "icon.png").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path in ("/", "/index.html"):
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
        elif self.path == "/api/vault":
            self._json({"items": pipeline.load_vault(), "statuses": pipeline.VAULT_STATUSES,
                        "min_score": pipeline.VAULT_MIN_SCORE})
        elif self.path == "/api/config":
            self._json({
                "languages": config.LANGUAGES,
                "seeds": pipeline.DEFAULT_SEEDS,
                "units_per_niche": pipeline.UNITS_PER_NICHE,
                "auto": pipeline.auto_summary(),
                "keys_configured": len(config.API_KEYS),
                "keys_masked": [f"…{k[-4:]}" for k in config.API_KEYS],
                "version": updater.current(),
                "quota": YouTubeClient().quota.summary(),
                "criteria": {
                    "min_duration_min": config.MIN_DURATION_SEC // 60,
                    "small_channel_max_subs": config.SMALL_CHANNEL_MAX_SUBS,
                    "big_channel_subs": config.BIG_CHANNEL_SUBS,
                    "new_channel_days": config.NEW_CHANNEL_DAYS,
                    "search_published_days": config.SEARCH_PUBLISHED_DAYS,
                },
            })
        elif self.path == "/api/update/check":
            self._json(updater.check())
        elif self.path == "/api/update/status":
            self._json(updater.state)
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
            pipeline.delete_result(body.get("query", ""), body.get("lang", ""))
            self._json({"ok": True})
        elif self.path == "/api/vault/add":
            self._json({"ok": pipeline.vault_add_by_key(body.get("query", ""), body.get("lang", ""))})
        elif self.path == "/api/vault/update":
            pipeline.vault_update(body.get("key", ""), body.get("status"), body.get("note"))
            self._json({"ok": True})
        elif self.path == "/api/vault/remove":
            pipeline.vault_remove(body.get("key", ""))
            self._json({"ok": True})
        elif self.path == "/api/keys":
            keys = config.save_api_keys(body.get("keys", ""))
            self._json({"ok": True, "count": len(keys)})
        elif self.path == "/api/update/apply":
            try:
                updater.start()
                self._json({"ok": True})
            except updater.UpdateError as e:
                self._json({"error": str(e)}, 400)
        elif self.path == "/api/shutdown":
            self._json({"ok": True})
            threading.Timer(0.5, lambda: os._exit(0)).start()
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, *args):
        pass


URL = f"http://127.0.0.1:{config.PORT}"


def port_busy():
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", config.PORT)) == 0


def serve():
    ThreadingHTTPServer(("127.0.0.1", config.PORT), Handler).serve_forever()


def run_browser():
    if port_busy():
        print("Программа уже запущена, открываю…")
        webbrowser.open(URL)
        return
    print(f"Дашборд: {URL}  (Ctrl+C чтобы остановить)")
    if not config.API_KEYS:
        print("Ключи не найдены: впишите их в «Настройках» на дашборде.")
    threading.Timer(0.8, lambda: webbrowser.open(URL)).start()
    try:
        serve()
    except KeyboardInterrupt:
        pass


def run_window():
    """Своё окно через системный WebKit (pywebview). Если не получилось, открываем в браузере."""
    try:
        import webview
    except Exception as e:
        print(f"Окно недоступно ({e}), открываю в браузере.")
        return run_browser()
    if not port_busy():
        threading.Thread(target=serve, daemon=True).start()
    for _ in range(80):
        if port_busy():
            break
        time.sleep(0.25)

    def watch_server():
        # «Выключить» или обновление останавливают сервер: окно закрывается тоже
        while port_busy():
            time.sleep(1)
        try:
            win.destroy()
        except Exception:
            pass

    def started():
        threading.Thread(target=watch_server, daemon=True).start()
        if sys.platform == "darwin":
            # Окно открывает Python, поэтому в Dock по умолчанию его значок: ставим свой
            try:
                from AppKit import NSApplication, NSImage
                NSApplication.sharedApplication().setApplicationIconImage_(
                    NSImage.alloc().initWithContentsOfFile_(str(config.ROOT / "dashboard" / "icon.png")))
            except Exception:
                pass

    if sys.platform == "darwin":
        try:  # в меню «Поиск ниш», а не «Python»
            from Foundation import NSBundle
            info = NSBundle.mainBundle().localizedInfoDictionary() or NSBundle.mainBundle().infoDictionary()
            info["CFBundleName"] = "Поиск ниш"
        except Exception:
            pass

    win = webview.create_window("Поиск ниш", URL, width=1360, height=880, min_size=(900, 600), text_select=True)
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    try:
        webview.start(started, private_mode=False, storage_path=str(config.DATA_DIR / "window"))
    except Exception as e:
        print(f"Окно не открылось ({e}), открываю в браузере.")
        webbrowser.open(URL)
        while port_busy():
            time.sleep(5)
    os._exit(0)  # окно закрыто: программа завершается


if __name__ == "__main__":
    os.chdir(config.ROOT)
    run_window() if "--window" in sys.argv else run_browser()
