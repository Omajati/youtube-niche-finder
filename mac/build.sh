#!/bin/bash
# Собирает «Поиск ниш.app» и архив для раздачи. Запуск: bash mac/build.sh OUT_DIR
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/dist}"
VER="$(tr -d '[:space:]' < "$ROOT/VERSION")"
APP="$OUT/Поиск ниш.app"
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/payload"
cp "$ROOT/mac/launch" "$APP/Contents/MacOS/launch"; chmod 755 "$APP/Contents/MacOS/launch"
P="$APP/Contents/Resources/payload"
cp -R "$ROOT/niche_finder" "$ROOT/dashboard" "$P/"
cp "$ROOT/app.py" "$ROOT/cli.py" "$ROOT/requirements.txt" "$ROOT/README.md" "$ROOT/.env.example" "$ROOT/mac/setup.sh" "$P/"
find "$P" -name '__pycache__' -type d -prune -exec rm -rf {} +
echo "$VER" > "$P/VERSION"
${PY:-python3} - "$ROOT/mac/icon-1024.png" "$APP/Contents/Resources/icon.icns" <<'PY'
import sys
from PIL import Image
Image.open(sys.argv[1]).convert("RGBA").save(sys.argv[2])
PY
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Поиск ниш</string>
  <key>CFBundleDisplayName</key><string>Поиск ниш</string>
  <key>CFBundleIdentifier</key><string>ru.nichefinder.app</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VER</string>
  <key>CFBundleVersion</key><string>$VER</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
</dict></plist>
PLIST
(cd "$OUT" && rm -f "Поиск ниш.zip" && zip -qry "Поиск ниш.zip" "Поиск ниш.app")
echo "$OUT/Поиск ниш.zip (версия $VER)"
