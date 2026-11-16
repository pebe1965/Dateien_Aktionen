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
einschließlich der Texte im Marketplace (Schritt 5 und 8) und des Handbuchs
(Schritt 5, siehe Abschnitt 5). Nicht nach dem Hochladen aufhören.

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
   Das Skript kopiert die Programmdateien **einzeln** ins Bundle. Jede neue
   `.py`-Datei und jede neue Datei, die das Programm zur Laufzeit liest
   (wie `Handbuch_Dateien_Aktionen.md`), dort als eigene `cp`-Zeile
   ergänzen — sonst fehlt sie im DMG und das Programm startet nicht.
3. **Nichts Geheimes im Paket:**
   `find Dateien_Aktionen.app -name ".env" -o -name ".env.*.local"; grep -rE "AIza[0-9A-Za-z_-]{30,}|na_[0-9A-Za-z]{20,}" Dateien_Aktionen.app`
   — darf nichts ausgeben (`.env.example` mit Platzhaltern ist erlaubt).
   Außerdem: `/usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" Dateien_Aktionen.app/Contents/Info.plist`
   zeigt die neue Version.
4. **Versionshinweise** auf Deutsch, für Nutzer (keine Code-Begriffe ohne
   Erklärung), Format: `## Neu in X.Y.Z` + Stichpunkte, darunter
   „Installation: DMG öffnen, App in „Programme“ ziehen (bei Nachfrage
   „Ersetzen“). Einstellungen, Verlauf und Zugangscode bleiben erhalten.“
5. **Handbuch und `marketplace.json` aktualisieren** — bei jedem Release
   prüfen, bei jeder neuen oder geänderten Funktion anpassen. Das Handbuch
   (`Handbuch_Dateien_Aktionen.md`) nach den Regeln in Abschnitt 5; für
   `marketplace.json` gilt:
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

## 5. Handbuch

Das Programm enthält ein Handbuch für Nutzer (Reiter „Handbuch“). **Einzige
Quelle ist `Handbuch_Dateien_Aktionen.md`** im Projektordner: Die Oberfläche
lädt die Datei über `/api/handbuch` und wandelt sie selbst in HTML um
(`hbRender()` in `templates/index.html`). Text also nie in der Oberfläche
ändern, immer in der Markdown-Datei.

- **Bei jeder neuen oder geänderten Funktion das Handbuch im selben Zug
  anpassen**: neuer Reiter, neuer Knopf, geänderte Bezeichnung, geändertes
  Verhalten, neue Einstellung, neue Fehlermeldung. Entfallenes streichen.
  Beschriftungen wörtlich so schreiben, wie sie in der Oberfläche stehen.
- **Aufbau beibehalten:** nummerierte Kapitel als `## 1. Titel`, darin
  `###`-Abschnitte. Neue Funktionen in das passende Kapitel einarbeiten;
  ein neues Kapitel nur für einen neuen Reiter oder Bereich. Kapitel 3
  (Tabelle der Reiter), Kapitel 16 (Problemlösungen) und Kapitel 17
  (Begriffe) mitpflegen.
- **Kapitelnamen sind Sprungziele:** `zeigeHandbuch('11. Sicherung')` in der
  Oberfläche springt über den exakten Titel. Wer ein Kapitel umbenennt oder
  umnummeriert, sucht in `templates/index.html` nach `zeigeHandbuch(` und
  passt die Aufrufe an.
- **Schreibweise:** Deutsch, Anrede „du“, Sprache für Nutzer ohne
  Fachwissen. Jede Anleitung als nummerierte Schritte, je Schritt eine
  Handlung. Erst sagen, wozu etwas dient, dann wie es geht. Keine
  Code-Begriffe ohne Erklärung, keine Versionsnummern, keine Emojis.
- **Nur diese Markdown-Mittel** — mehr kann die Anzeige nicht:
  Überschriften `#` bis `###`, Absätze, Listen mit `-` und `1.` (höchstens
  eine eingerückte Unterebene mit `-`), Tabellen, `**fett**`, `` `Code` ``,
  Links `[Text](https://…)` und Hinweiskästen mit `>`. Ein Kasten, der mit
  `Achtung:` oder `Wichtig:` beginnt, wird gelb, sonst blau (`Hinweis:`,
  `Tipp:`, `Voraussetzung:`). Keine Bilder, keine Code-Blöcke, kein HTML.
  Wird ein weiteres Mittel gebraucht, zuerst `hbRender()` erweitern.
- **Nur Zutreffendes:** Jede Aussage am Code prüfen. Was nicht getestet ist,
  nicht als sicher darstellen. Nichts Geheimes — die Datei ist öffentlich
  und wird mit dem Programm ausgeliefert.
- Die `README.md` richtet sich an Entwickler und GitHub-Besucher und bleibt
  kurz; ausführliche Anleitungen gehören ins Handbuch.

## 6. Aufbau und Wissenswertes

### Dateien

| Datei | Aufgabe |
| --- | --- |
| `config.py` | Einstellungen, Pfade, Ordnungssystem (`ordnung_pfad()`, `ablage_ziel()`) |
| `classifier.py` | Ordner einlesen, Kategorien, Prüfsummen, ähnliche Fotos |
| `extractor.py` | Text und Angaben aus Dateien lesen (Texterkennung, EXIF) |
| `ai_engine.py` | KI-Anfragen, Ablage-Modus, Steuer-Kennzeichen, Einrichtungsassistent |
| `organizer.py` | Plan, Ausführen, Manifest/Rückgängig, Finder-Tags, Projekte, Steuer-Suche |
| `watcher.py` | Autopilot und LaunchAgent |
| `backup.py` | Sicherung: Aufträge, Spiegel, ZIP, Nextcloud (WebDAV), Zeitplan, Wiederherstellen |
| `gui.py` | Lokaler Server mit allen `/api/…`-Endpunkten |
| `main.py` | Kommandozeile, auch `dienst` für den Hintergrunddienst |
| `templates/index.html` | Die gesamte Oberfläche (HTML und Skript in einer Datei) |
| `Handbuch_Dateien_Aktionen.md` | Quelle des Handbuchs |

### Regeln, die beim Ändern gelten

- **Rückgängig:** Alles, was Dateien verschiebt, umbenennt oder kopiert,
  schreibt ein Manifest nach `HISTORY_DIR` (`manifest_<Zeit>.json`, Felder
  `source`, `target`, `copy_mode`; optional `beschreibung` für den Verlauf).
  `rollback_manifest()` macht es rückgängig. Vorhandene Dateien nie
  überschreiben — `get_unique_target_path()` hängt einen Zähler an.
- **Gelöscht wird nur in den Papierkorb** (`move_to_macos_trash()`).
- **Finder-Tags** immer über `set_macos_tags_and_comment()` setzen: Es
  ergänzt und lässt vorhandene Tags stehen. Tags zu einer Analyse liefert
  `tags_fuer_analyse()`.
- **Ordnungssystem:** `01 Eingang`, `02 Projekte`, `03 Ablage`, `Archiv`
  unter `config.ORDNUNG_BASIS`. Im Sortiermodus `ablage` sind die
  vorhandenen Ordner der Ablage verbindlich; keine Jahresordner, kein
  Ordner „Steuer“ (nur der Tag `Steuer <Jahr>`). Neue Kategorien entstehen
  nur nach Bestätigung in der Vorschau, der Autopilot legt keine an.
- **Ordnervorschläge der KI** nie ungeprüft an einen Pfad hängen:
  `bereinige_ordner()` entfernt `..` und führende Schrägstriche. Dasselbe
  gilt für alle Pfade und Namen, die aus der Oberfläche kommen.
- **KI-Anfragen** laufen ausschließlich über `_query_generate()` (Abschnitt
  2). Ein anderer Auftrag als die Datei-Analyse wird als `system_prompt`
  übergeben, so macht es der Einrichtungsassistent.
- **Analyse-Cache:** Der Schlüssel enthält Anbieter, Sortiermodus, Ziel,
  Projektliste und Namensstil. Kommt eine Einstellung hinzu, die den
  Vorschlag verändert, gehört sie in den Schlüssel (`prepare_plan()`).
- **Sicherung (`backup.py`):**
  - Aufräumen und Löschen nur im markierten Ordner
    `Dateien_Aktionen-Sicherung/<Auftrag>` (Datei
    `.dateien_aktionen_sicherung.json`). Ein gleichnamiger Ordner ohne
    passende Markierung wird abgelehnt. Diese Prüfung nicht entfernen.
  - Liegt das Ziel unter `/Volumes/<Name>`, muss das Laufwerk eingebunden
    sein (`os.path.ismount`), sonst wird nichts geschrieben.
  - Eine nicht erreichbare Quelle wird ausgelassen; ihre Sicherung bleibt
    unangetastet und der Lauf gilt als nicht erledigt.
  - Im Spiegel wird nie überschrieben oder gelöscht: Ersetztes und
    Gelöschtes wandert nach `Frühere Versionen/<Zeitstempel>`.
  - Es läuft nur eine Sicherung gleichzeitig (Dateisperre `lauf.lock`),
    weil App und Hintergrunddienst denselben Zeitplan prüfen.
  - Zugangsdaten der Nextcloud (`NEXTCLOUD_URL`, `NEXTCLOUD_BENUTZER`,
    `NEXTCLOUD_APP_PASSWORT`) stehen nur in der `.env` des Nutzers. Das
    Passwort nie an die Oberfläche zurückgeben. Die Verbindung verlangt
    `https://` und prüft das Zertifikat immer.
  - Aufträge und Protokoll liegen in `config.DATA_DIR/backup/`.
- **Hintergrunddienst:** Der LaunchAgent startet `main.py dienst`. Darin
  läuft der Autopilot nur, wenn er eingeschaltet ist; fällige Sicherungen
  werden immer geprüft.
- **Oberfläche:** Jeder Wert, der in HTML eingesetzt wird, durch
  `escHtml()` schicken. Die Kennungen (`id="…"`) im HTML und im Skript
  müssen übereinstimmen, ebenso die Feldnamen zwischen Skript und Server —
  bis 1.4.0 passte das Skript der Autopilot-Seite zu keinem von beiden und
  die Seite war wirkungslos.

### Lokal testen, ohne etwas Echtes zu berühren

- **Eigener Datenordner:** `DATEIEN_AKTIONEN_DATA_DIR=<Testordner>` setzen.
  Achtung: `config._uebernehme_alte_daten()` kopiert beim ersten Start die
  `.env` aus dem Projektordner dorthin — sie kann einen echten Schlüssel
  enthalten. Die Datei im Testordner nie ausgeben, den Testordner danach
  löschen.
- **Ohne KI-Kosten:** `AI_PROVIDER=offline`.
- **Autopilot:** Die Standardeinstellung überwacht das echte `~/Downloads`.
  Vor jedem Prüflauf `watch_folders` in
  `<Testordner>/history/autopilot_config.json` auf einen Testordner setzen,
  sonst werden echte Dateien verschoben.
- **Server:** Nie `start_gui()` zum Testen aufrufen — es beendet eine
  laufende Instanz anderer Version auf Port 8765. Stattdessen
  `ThreadingHTTPServer(("127.0.0.1", <anderer Port>), gui.DashboardHandler)`.
- **Sicherung:** Nur in Testordner sichern; `backup.fuehre_aus(…,
  melden=False)` unterdrückt die Mitteilung des Mac.
