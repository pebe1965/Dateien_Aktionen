# Regeln für KI-Assistenten (Gemini/Antigravity, Claude, …)

Dieses Tool wird öffentlich auf GitHub veröffentlicht und als DMG
heruntergeladen. **Alles, was im Code oder im Paket steht, ist öffentlich.**

## 1. Niemals einen API-Schlüssel ausliefern

- Kein Gemini-, Google- oder sonstiger Schlüssel im Code, in
  `templates/`, im App-Bundle oder im DMG — auch nicht kodiert oder als
  Standardwert. Schlüssel und Zugangscodes gehören **nur** in die lokale
  `.env` des Nutzers (steht in `.gitignore`).
- **Daten des Nutzers liegen nie im Programm**, sondern in
  `~/Library/Application Support/Dateien_Aktionen/` (`config.DATA_DIR`,
  `ENV_PATH`, `HISTORY_DIR`). Nichts darf nach `BASE_DIR` schreiben — das ist
  das Programmverzeichnis bzw. App-Bundle, das bei jedem Update ersetzt wird.
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

## 3. Start und Updates

- Die Oberfläche läuft als lokaler Server auf Port 8765 (Webapps der Nutzer
  zeigen auf diese Adresse). `start_gui()` fragt laufende Instanzen nach ihrer
  Version (`/api/status` → `app_version`): gleiche Version → nur Browser
  öffnen; andere Version → alte beenden und selbst auf 8765 starten. Ohne das
  lief nach einem Update die alte Fassung weiter. `app_version` in
  `/api/status` deshalb nie entfernen.

## 4. Release — immer vollständig, in dieser Reihenfolge

Ein Release ist erst fertig, wenn **alle** Schritte erledigt sind —
einschließlich der Texte im Marketplace (Schritt 5 und 8). Nicht nach dem
Hochladen aufhören.

Wie das Programm im Marketplace von NotionaryAtlas erscheint:

| Was | Woher | Wer aktualisiert |
| --- | --- | --- |
| Version, Datum, Versionshinweise, Download-Knopf | neuestes GitHub-Release | automatisch (bis zu 10 min Verzögerung) |
| Beschreibung, Funktionsliste, Voraussetzungen | `marketplace.json` in diesem Repo → Datenbank der App | **du**, Schritt 5 und 8 |

Bis 17.10.2026 wurde Schritt 5/8 vergessen: v1.2.0 stand im Marketplace ohne
ähnliche Fotos, Finder-Tags und Autopilot.

1. **Version festlegen** (`X.Y.Z`: Fehlerbehebung → Z+1, neue Funktion →
   Y+1) und **überall gleich** eintragen:
   - `APP_VERSION` in `config.py`
   - `CFBundleShortVersionString` in
     `Dateien_Aktionen.app/Contents/Info.plist`
   Achtung: `Dateien_Aktionen.app/` steht in `.gitignore` und
   `build_release.sh` schreibt die Info.plist **nicht** — sie muss von Hand
   geändert werden, sonst trägt das DMG die alte Version. Die
   Update-Prüfung (`/api/check_update` in `gui.py`) und der Start
   (`start_gui()`) vergleichen `APP_VERSION` mit dem GitHub-Tag bzw. der
   laufenden Instanz.
2. **Bauen:** `./scripts/build_release.sh` (erzeugt `Dateien_Aktionen.dmg`
   und `Dateien_Aktionen.zip`). Bricht es ab (etwa wegen einer `.env` im
   Bundle), Ursache beheben — die Prüfung nie entfernen.
3. **Nichts Geheimes im Paket:**
   `find Dateien_Aktionen.app -name ".env" -o -name ".env.*.local"; grep -rE "AIza[0-9A-Za-z_-]{30,}|na_[0-9A-Za-z]{20,}" Dateien_Aktionen.app`
   — darf nichts ausgeben (`.env.example` mit Platzhaltern ist erlaubt).
   Außerdem: `/usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" Dateien_Aktionen.app/Contents/Info.plist`
   zeigt die neue Version.
4. **Versionshinweise** auf Deutsch, für Nutzer (keine Code-Begriffe ohne
   Erklärung), Format: `## Neu in X.Y.Z` + Stichpunkte, darunter
   „Installation: DMG öffnen, App in „Programme“ ziehen (bei Nachfrage
   „Ersetzen“). Einstellungen, Verlauf und Zugangscode bleiben erhalten.“
5. **`marketplace.json` aktualisieren** — bei jedem Release prüfen, bei jeder
   neuen oder geänderten Funktion anpassen:
   - `description` (40–400 Zeichen): ein bis zwei Sätze, was das Programm
     insgesamt kann. Keine Versionsnummer — die zeigt der Marketplace selbst.
   - `integrations` (1–8 Einträge, je `module` 2–40 Zeichen und
     `description` 10–240 Zeichen): die wichtigsten Funktionsbereiche des
     **gesamten** Programms, nicht nur die Neuerungen. Neues in einen
     passenden Bereich einarbeiten oder einen Bereich ergänzen; bei mehr als
     acht zusammenfassen. Weggefallenes streichen.
   - `requirements` (1–6 Einträge): nur ändern, wenn sich Voraussetzungen
     ändern (Mac-Modell, macOS-Version, Python, …).
   - `slug` und `github_repo` **nie** ändern.
   - Deutsch, Nutzersprache, kein Markdown, keine Emojis. Die Datei ist
     öffentlich — nichts Geheimes hinein.
6. **Commit und Push** auf `main` (Code + `marketplace.json` zusammen), dann
   Tag: `git tag vX.Y.Z && git push origin main vX.Y.Z`.
7. **GitHub-Release** — veröffentlicht, kein Entwurf, keine Vorabversion
   (Marketplace und Update-Prüfung lesen nur `releases/latest`):
   ```bash
   gh release create vX.Y.Z Dateien_Aktionen.dmg Dateien_Aktionen.zip \
     --title "Dateien_Aktionen vX.Y.Z – <kurzer Titel>" --notes-file <hinweise.md>
   ```
   Genau diese Dateinamen, **DMG zuerst**: Die Update-Prüfung im Programm
   nimmt die erste `.dmg`/`.zip` als Download. Der Marketplace bietet nur das
   DMG an (`Dateien_Aktionen.zip` hat kein „mac“ im Namen und wird dort
   bewusst ignoriert) — nicht umbenennen.
8. **Marketplace-Texte übernehmen** (Probelauf, dann speichern):
   ```bash
   node ~/Developer/pberthold-app/scripts/marketplace-desktop-text.mjs ~/Developer/Dateien_Aktionen
   node ~/Developer/pberthold-app/scripts/marketplace-desktop-text.mjs ~/Developer/Dateien_Aktionen --schreiben
   ```
   Das Skript prüft die Datei, zeigt die Unterschiede und schreibt in die
   Datenbank der App — sofort sichtbar, **kein Deploy nötig**. Es liest den
   Datenbank-Schlüssel aus `~/Developer/pberthold-app/.env.local`; dafür
   braucht der Befehl Zugriff außerhalb dieses Ordners (Sandbox ggf.
   umgehen). **Diesen Schlüssel nie in dieses Repo kopieren**, nie ausgeben.
   Meldet das Skript einen Fehler, `marketplace.json` korrigieren und
   wiederholen.
9. **Kontrolle:** `gh release view vX.Y.Z --json tagName,isDraft,isPrerelease,assets`
   — Tag stimmt, beide Dateien da, kein Entwurf. Erneuter Probelauf aus
   Schritt 8 meldet „bereits aktuell“.

**Im Repo `pberthold-app` (NotionaryAtlas) sonst nichts ändern und dort nie
committen oder pushen** — jeder Push dort löst einen kostenpflichtigen Build
aus, und für ein Release ist keiner nötig.
