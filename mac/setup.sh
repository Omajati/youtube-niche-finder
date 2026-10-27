#!/bin/bash
# Ставит или обновляет программу в ~/NicheFinder. Запускается из «Поиск ниш.app»; папку data не трогает.
set -e
SRC="$1"
DEST="$HOME/NicheFinder"
mkdir -p "$DEST/data"

# Запущенная раньше копия останавливается, чтобы открылась новая.
curl -s -X POST --max-time 3 http://127.0.0.1:8766/api/shutdown >/dev/null 2>&1 && sleep 2 || true

# 1. Файлы программы
rm -rf "$DEST/niche_finder" "$DEST/dashboard"
cp -R "$SRC/niche_finder" "$SRC/dashboard" "$DEST/"
for f in app.py cli.py requirements.txt README.md .env.example; do [ -f "$SRC/$f" ] && cp "$SRC/$f" "$DEST/"; done
xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true
echo "✓ файлы программы"

# 2. uv ставит Python и библиотеки, не трогая систему
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
if [ ! -x "$DEST/.venv/bin/python" ]; then
  uv venv --python 3.12 "$DEST/.venv"
fi
uv pip install --python "$DEST/.venv/bin/python" -q -r "$DEST/requirements.txt"
echo "✓ Python и библиотеки"

cp "$SRC/VERSION" "$DEST/VERSION"
echo "✓ готово"
