# Regeln für KI-Assistenten (Gemini/Antigravity, Claude, …)

Dieses Tool wird öffentlich auf GitHub veröffentlicht und als DMG
heruntergeladen. **Alles, was im Code oder im Paket steht, ist öffentlich.**

## 1. Niemals einen API-Schlüssel ausliefern

- Kein Gemini-, Google- oder sonstiger Schlüssel im Code, in
  `templates/`, im App-Bundle oder im DMG — auch nicht kodiert oder als
  Standardwert. Schlüssel und Zugangscodes gehören **nur** in die lokale
  `.env` des Nutzers (steht in `.gitignore`).
- Hintergrund: Bis Version 1.0.2 lag eine `.env` mit dem
  Produktionsschlüssel von NotionaryAtlas im App-Bundle und damit in jedem
  veröffentlichten DMG. `scripts/build_release.sh` legt das Bundle nicht neu
  an, sondern überschreibt es — eine einmal hineinkopierte Datei blieb für
  immer darin. Das Skript entfernt die `.env` jetzt und **bricht ab**, wenn
  doch eine im Bundle liegt. Diese Prüfung nicht entfernen.

## 2. KI läuft über NotionaryAtlas

- Standard-Provider ist `app` (`AI_PROVIDER` in `config.py`). Der Nutzer
  erstellt im Marketplace von NotionaryAtlas
  (https://app.pberthold.com/marketplace) einen **Zugangscode** (`na_…`) und
  trägt ihn in den Einstellungen ein (`NOTIONARY_ZUGANGSCODE` in der `.env`).
- Alle Anfragen laufen über `_query_generate()` in `ai_engine.py`: gleiches
  Format wie Geminis `generateContent`, an `config.NOTIONARY_KI_URL` mit
  `Authorization: Bearer <Zugangscode>`. Die App reicht sie mit ihrem eigenen
  Schlüssel weiter und rechnet über die KI-Credits ab.
  `pruefe_zugangscode()` testet die Verbindung ohne Credits.
- Einstellungen immer zur Laufzeit über `config.<NAME>` lesen, nicht per
  `from config import …` — die Oberfläche ändert die Werte, ohne neu zu
  starten.
- Grenzen der App: höchstens 4 MB je Anfrage, 120 Anfragen je Code und
  Stunde, max. 8192 Ausgabe-Tokens. Modell und Werkzeuge bestimmt die App.
  Fehler: 401/403 Code ungültig/widerrufen, 402 keine Credits, 429 zu viele
  Anfragen.
- Ein **eigener** Gemini-Schlüssel des Nutzers (`AI_PROVIDER=gemini`) bleibt
  möglich — mitgeliefert wird nie einer.

## 3. Vor jedem Release

1. `APP_VERSION` in `config.py` und `CFBundleShortVersionString` in
   `Dateien_Aktionen.app/Contents/Info.plist` auf die neue Version setzen —
   die Update-Prüfung vergleicht sie mit dem GitHub-Tag.
2. `./scripts/build_release.sh`
3. Prüfen, dass nichts Geheimes im DMG steckt (DMG öffnen →
   Paketinhalt → `Contents/Resources/app/`): keine `.env`, kein `AIza…`.
4. Release auf GitHub mit Tag `vX.Y.Z` und der Datei `Dateien_Aktionen.dmg`.
   Der Marketplace zeigt es automatisch an.
