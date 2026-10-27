#!/bin/bash
# Запуск двойным кликом на Mac: подтягивает обновления (если папка скачана через git / GitHub Desktop)
# и открывает дашборд. Окно Терминала не закрывайте, пока пользуетесь дашбордом.
cd "$(dirname "$0")" || exit 1

if [ -d .git ]; then
  echo "Проверяю обновления..."
  git pull --ff-only || echo "Обновиться не удалось, запускаю текущую версию."
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Создан файл .env. Впишите в него ключи и запустите снова."
  open -e .env
  exit 0
fi

python3 app.py
