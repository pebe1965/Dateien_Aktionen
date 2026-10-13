#!/usr/bin/env bash
set -e

# Wechsle ins Hauptverzeichnis des Projekts
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

echo "=================================================="
echo "🔨 Erstelle Release-Pakete für Dateien_Aktionen"
echo "=================================================="

APP_BUNDLE="$PROJECT_DIR/Dateien_Aktionen.app"
APP_DIR="$APP_BUNDLE/Contents/Resources/app"

# 1. Verzeichnisstruktur sicherstellen
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_DIR/templates"
mkdir -p "$APP_DIR/bin"

# 2. Anwendungsdateien in das App-Bundle synchronisieren
echo "📦 1. Synchronisiere App-Ressourcen..."
cp "$PROJECT_DIR/gui.py" "$APP_DIR/"
cp "$PROJECT_DIR/config.py" "$APP_DIR/"
cp "$PROJECT_DIR/extractor.py" "$APP_DIR/"
cp "$PROJECT_DIR/classifier.py" "$APP_DIR/"
cp "$PROJECT_DIR/organizer.py" "$APP_DIR/"
cp "$PROJECT_DIR/ai_engine.py" "$APP_DIR/"
cp "$PROJECT_DIR/main.py" "$APP_DIR/"
cp "$PROJECT_DIR/templates/index.html" "$APP_DIR/templates/"
cp "$PROJECT_DIR/templates/index.html" "$APP_DIR/index.html" 2>/dev/null || true

# Native Binaries kopieren
if [ -d "$PROJECT_DIR/bin" ]; then
    cp -R "$PROJECT_DIR/bin/"* "$APP_DIR/bin/" 2>/dev/null || true
    chmod +x "$APP_DIR/bin/"* 2>/dev/null || true
fi

# Keine Zugangsdaten ausliefern: Das Bundle wird nicht neu angelegt, sondern
# nur ueberschrieben — eine einmal hineinkopierte .env bliebe sonst fuer immer
# darin und landete in jedem veroeffentlichten DMG.
rm -f "$APP_DIR/.env" "$APP_DIR"/.env.*.local
rm -rf "$APP_DIR/history"/*.json 2>/dev/null || true
if find "$APP_BUNDLE" -name ".env" | grep -q .; then
    echo "❌ Abbruch: Im App-Bundle liegt noch eine .env-Datei."
    exit 1
fi

# Launcher ausführbar machen
chmod +x "$APP_BUNDLE/Contents/MacOS/launcher"
chmod +x "$PROJECT_DIR/Dateien_Aktionen.command"

# 3. DMG erstellen
echo "💿 2. Erstelle macOS Disk Image (Dateien_Aktionen.dmg)..."
DMG_STAGING="/tmp/dmg_staging_da_$$"
rm -rf "$DMG_STAGING" "$PROJECT_DIR/Dateien_Aktionen.dmg"
mkdir -p "$DMG_STAGING"

cp -R "$APP_BUNDLE" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

hdiutil create -volname "Dateien_Aktionen" -srcfolder "$DMG_STAGING" -ov -format UDZO "$PROJECT_DIR/Dateien_Aktionen.dmg"
rm -rf "$DMG_STAGING"

# 4. ZIP erstellen
echo "🗜️ 3. Erstelle ZIP-Archiv (Dateien_Aktionen.zip)..."
rm -f "$PROJECT_DIR/Dateien_Aktionen.zip"
zip -rq "$PROJECT_DIR/Dateien_Aktionen.zip" Dateien_Aktionen.app

echo "=================================================="
echo "✅ Fertig! Folgende Release-Dateien wurden aktualisiert:"
echo "   🍏 macOS App:     Dateien_Aktionen.app"
echo "   💿 macOS DMG:     Dateien_Aktionen.dmg"
echo "   🗜️ macOS ZIP:     Dateien_Aktionen.zip"
echo "=================================================="
