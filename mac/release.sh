#!/bin/bash
# Готовит выпуск новой версии: поднимите число в VERSION, затем из корня репозитория:
#   bash mac/release.sh "что нового"     (потом git commit и git push в main)
# Программа увидит release/latest.json и покажет кнопку «Обновить».
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NOTES="$1"
VER="$(tr -d '[:space:]' < "$ROOT/VERSION")"
TMP="$(mktemp -d)"
bash "$ROOT/mac/build.sh" "$TMP" >/dev/null
mkdir -p "$ROOT/release"
cp "$TMP/Поиск ниш.zip" "$ROOT/release/NicheFinder.zip"
rm -rf "$TMP"
REPO="$(grep -o '^REPO = "[^"]*' "$ROOT/niche_finder/updater.py" | cut -d'"' -f2)"
${PY:-python3} -c "import json, sys; print(json.dumps({'version': int(sys.argv[1]), 'notes': sys.argv[2], 'app_zip': f'https://raw.githubusercontent.com/{sys.argv[3]}/main/release/NicheFinder.zip'}, ensure_ascii=False, indent=1))" "$VER" "$NOTES" "$REPO" > "$ROOT/release/latest.json"
echo "Версия $VER: release/latest.json и release/NicheFinder.zip готовы"
