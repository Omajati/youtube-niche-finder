"""Обновление с GitHub одной кнопкой (как в «Авто ютуб»).

release/latest.json в репозитории говорит, какая версия новейшая; сам код берётся из ветки main.
Обновление заменяет файлы программы в ~/NicheFinder, папку data (ключи, результаты, кэш) не трогает.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from .config import ROOT
from .youtube import http_get

REPO = "Omajati/youtube-niche-finder"
LATEST = f"https://raw.githubusercontent.com/{REPO}/main/release/latest.json"
CODE_ZIP = f"https://codeload.github.com/{REPO}/zip/refs/heads/main"
# Запасные адреса: raw.githubusercontent.com и codeload открываются не из каждой сети.
LATEST_API = f"https://api.github.com/repos/{REPO}/contents/release/latest.json"
CODE_ZIP_API = f"https://api.github.com/repos/{REPO}/zipball/main"
BUNDLE_ID = "ru.nichefinder.app"
APP_NAME = "Поиск ниш"
PARTS = ["niche_finder", "dashboard", "app.py", "cli.py", "requirements.txt", "README.md", ".env.example", "VERSION"]

state = {"status": "idle", "step": "", "error": ""}
_lock = threading.Lock()


class UpdateError(Exception):
    pass


def _get(url, timeout=30, headers=None):
    return http_get(url, timeout=timeout, headers=headers)


def current():
    try:
        return int((ROOT / "VERSION").read_text().strip())
    except (OSError, ValueError):
        return 0


def can_install():
    """Сама обновляется только программа, установленная как приложение на Mac."""
    return sys.platform == "darwin" and (ROOT / ".venv").exists()


def _latest(fresh=False):
    # GitHub кэширует файл на несколько минут; ручная проверка просит самую свежую копию
    stamp = int(time.time()) if fresh else int(time.time() // 300)
    try:
        return json.loads(_get(f"{LATEST}?t={stamp}", timeout=15))
    except Exception:
        return json.loads(_get(LATEST_API, timeout=20, headers={"Accept": "application/vnd.github.raw"}))


def check(fresh=False):
    try:
        r = _latest(fresh)
    except Exception as e:
        return {"current": current(), "latest": 0, "available": False, "error": f"GitHub недоступен: {e}"}
    latest = int(r.get("version") or 0)
    return {"current": current(), "latest": latest, "available": latest > current(), "label": r.get("label", ""),
            "notes": r.get("notes", ""), "can_install": can_install(), "download": r.get("app_zip", "")}


def start():
    with _lock:
        if state["status"] == "working":
            raise UpdateError("Обновление уже идёт.")
        if not can_install():
            raise UpdateError("Сама обновляется только программа, установленная как приложение на Mac.")
        state.update(status="working", step="готовлю", error="")
    threading.Thread(target=_run, daemon=True).start()


def _run():
    try:
        info = check()
        if not info["available"]:
            raise UpdateError("У вас уже последняя версия.")
        state["step"] = "скачиваю новую версию"
        try:
            data = _get(CODE_ZIP, timeout=180)
        except Exception:
            data = _get(CODE_ZIP_API, timeout=240)
        tmp = Path(tempfile.mkdtemp(prefix="nf-update-"))
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(tmp)
        src = next((d for d in tmp.iterdir() if (d / "niche_finder" / "pipeline.py").exists()), None)
        if not src:
            raise UpdateError("В скачанной версии нет файлов программы. Попробуйте позже.")
        state["step"] = "ставлю новую версию"
        _copy_parts(src, ROOT)
        state["step"] = "обновляю библиотеки"
        uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
        r = subprocess.run([uv, "pip", "install", "--python", str(ROOT / ".venv" / "bin" / "python"), "-q", "-r",
                            str(ROOT / "requirements.txt")], capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            raise UpdateError(f"Не удалось обновить библиотеки: {(r.stderr or r.stdout)[-400:]}")
        _update_bundle(src, info["latest"])
        (ROOT / "VERSION").write_text(str(info["latest"]))
        shutil.rmtree(tmp, ignore_errors=True)
        state.update(status="restarting", step="перезапускаю программу")
        _restart()
    except UpdateError as e:
        state.update(status="error", error=str(e))
    except Exception as e:
        state.update(status="error", error=f"Непредвиденная ошибка: {e}")


def _copy_parts(src, dest):
    for part in PARTS:
        s, d = src / part, dest / part
        if not s.exists():
            continue
        if s.is_dir():
            old = dest / f".{part}.old"
            shutil.rmtree(old, ignore_errors=True)
            if d.exists():
                d.rename(old)
            shutil.copytree(s, d)
            shutil.rmtree(old, ignore_errors=True)
        else:
            shutil.copy2(s, d)


def _bundle():
    env = os.environ.get("NF_APP")
    cands = [Path(env)] if env else []
    cands += [Path(f"/Applications/{APP_NAME}.app"), Path.home() / "Applications" / f"{APP_NAME}.app"]
    return next((c for c in cands if (c / "Contents" / "MacOS" / "launch").exists()
                 and os.access(c / "Contents", os.W_OK)), None)


def _update_bundle(src, version):
    """Копия программы внутри .app тоже обновляется, чтобы запуск приложения не вернул старую версию."""
    b = _bundle()
    if not b:
        return
    res = b / "Contents" / "Resources"
    new, payload, old = res / "payload.new", res / "payload", res / "payload.old"
    shutil.rmtree(new, ignore_errors=True)
    new.mkdir(parents=True)
    _copy_parts(src, new)
    shutil.copy2(src / "mac" / "setup.sh", new / "setup.sh")
    (new / "VERSION").write_text(str(version))
    shutil.rmtree(old, ignore_errors=True)
    if payload.exists():
        payload.rename(old)
    new.rename(payload)
    shutil.rmtree(old, ignore_errors=True)
    launch = b / "Contents" / "MacOS" / "launch"
    shutil.copy2(src / "mac" / "launch", launch)
    launch.chmod(0o755)
    plist = b / "Contents" / "Info.plist"
    try:
        t = plist.read_text("utf-8")
        t = re.sub(r"(<key>CFBundle(?:Short)?Version(?:String)?</key><string>)[^<]*", rf"\g<1>{version}", t)
        plist.write_text(t, "utf-8")
    except OSError:
        pass


def _restart():
    """Запускает приложение заново через пару секунд после выхода этой копии."""
    b = _bundle()
    target = f"open '{b}'" if b else f"open -b {BUNDLE_ID}"
    subprocess.Popen(["/bin/bash", "-c", f"sleep 3; {target}"], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Timer(1.0, lambda: os._exit(0)).start()
