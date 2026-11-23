# Dateien_Aktionen 🗂️⚡️

Ein maßgeschneidertes, KI- und OCR-gestütztes Werkzeug für macOS zum Katalogisieren, Verstehen und strukturierten Umbenennen von Dateien.

Entwickelt für Apple Silicon Macs (M-Serie) unter Ausnutzung der **Apple Neural Engine (macOS Vision OCR)** und flexiblen KI-Schnittstellen (**NotionaryAtlas Abo**, **Google Gemini API** oder **lokale LLMs**).

---

## Highlights (v1.2.0)

* 🔍 **Katalogisierung, Exakte Duplikate & Visuell Ähnliche Fotos:** Rekursiver Scan nach Dateitypen (`DOKUMENTE`, `BILDER`, `VIDEOS`, `AUDIO`, `ARCHIVE`, `CODE_DATEN`) mit SHA-256-Prüfsummen sowie **Perceptual Image Hashing (`--dhash` via Apple CoreGraphics)** zum Aufspüren von Serienbildern/Burst-Shots und komprimierten Fotokopien. Schutz für macOS-Pakete (`.photoslibrary`, `.logicx`, `.fcpbundle` etc.).
* 👁️ **Apple Vision OCR & Bild-Szenenerkennung (Native):** Scans und Fotos werden direkt über Apples Vision-Framework (`VNRecognizeTextRequest` + `VNClassifyImageRequest`) auf dem Mac analysiert – blitzschnell auf der Apple Neural Engine.
* 📸 **Multimodale Foto- & Medien-Intelligenz:** Liest tiefe macOS-Metadaten (`mdls` EXIF-Aufnahmedatum, GPS-Koordinaten, Kameramodell, Audio-/Video-Dauer) aus und übergibt komprimierte Bild-Thumbnails direkt an **Gemini / NotionaryAtlas Multimodal Vision**. Live-Browser-Vorschau auch für `.heic`-Fotos und Videos (`.mov`/`.mp4`).
* 🏷️ **Tiefe macOS-Integration:** Setzt beim Sortieren automatisch farbige **macOS Finder-Tags** (`_kMDItemUserTags`) und durchsuchbare **Spotlight-Kommentare** (`kMDItemFinderComment`) inkl. Direkt-Button „Im Finder zeigen“ (`📂`).
* ⚡ **Autopilot / Ordner-Wächter (Watch-Folder):** Überwacht auf Wunsch Ordner wie `~/Downloads` oder `~/Desktop` im Hintergrund (auch als nativer **macOS LaunchAgent** beim Systemstart) inklusive macOS System-Mitteilungen.
* 🚀 **Parallele Analyse & Lokaler KI-Cache:** 4-Worker-Multithreading mit Live-Fortschrittsbalken und lokalem Analyse-Cache (`~/Library/Application Support/Dateien_Aktionen/history/analysis_cache.json`), der bestehende Zielordner intelligent wiederverwendet.
* 🗄️ **Speicherplatz:** Findet große Dateien, prüft bekannte Netzwerk- und Grafikcaches und entfernt Apps mit einzeln auswählbaren Programmdaten.
* 🛡️ **100 % Sicherheit mit Dry-Run, Kollisionsschutz & Undo:**
  * Vor jedem Umbenennen/Verschieben gibt es eine interaktive Vorschau mit frei editierbaren Dateinamen und Zielordnern.
  * Jede Aktion (auch vom Autopiloten) wird in einem `manifest.json` protokolliert und lässt sich mit 1 Klick rückgängig machen.

---

## Handbuch

Die ausführliche Anleitung für Nutzer steht in [Handbuch_Dateien_Aktionen.md](Handbuch_Dateien_Aktionen.md) und ist im Programm im Reiter „Handbuch“ eingebaut – mit Inhaltsverzeichnis und Suche.

---

## Ordnungssystem: Eingang, Projekte, Ablage, Archiv

In den Einstellungen lässt sich unter „Ordnungssystem“ ein Basisordner wählen (z. B. in iCloud Drive). „Grundstruktur anlegen“ erzeugt dort vier Bereiche:

* `01 Eingang` – Briefkasten für alles Neue (Downloads, Scans, Anhänge)
* `02 Projekte` – Schreibtisch für aktuell Relevantes
* `03 Ablage` – dauerhafte Kategorien wie `Anschaffungen`, `Versicherung`, `Auto`
* `Archiv` – Abgeschlossenes, das aufbewahrt wird

Im Sortiermodus **Ablage** wird aus jedem gescannten Ordner in die vorhandenen Kategorien von `03 Ablage` einsortiert – ohne Jahresordner. Passt keine Kategorie, markiert die Vorschau den Vorschlag als neu; angelegt wird er erst beim Anwenden. Der Autopilot legt keine neuen Kategorien an und lässt solche Dateien im Eingang liegen.

**Projekte:** Im Reiter „Projekte“ legt man laufende Vorhaben an – mit Termin als `JJJJ-MM-TT_Name` (sortiert sich von selbst nach Datum) oder ohne als `Name`. Im Modus „Ablage“ ordnet die KI-Vorschau passende Dateien direkt dem Projekt zu. Ein abgeschlossenes Projekt wandert als Ganzes ins Archiv, in eine Kategorie der Ablage oder in den Papierkorb; Archiv und Ablage lassen sich über das Protokoll rückgängig machen.

Steuerrelevante Belege bekommen keinen eigenen Ordner, sondern den Finder-Tag `Steuer <Jahr>`. Bereits vorhandene Finder-Tags einer Datei bleiben erhalten.

**Einrichtungsassistent:** Fünf kurze Fragen zu Beruf und Alltag, daraus entwirft die KI die Kategorien der Ablage samt Beispielen für Dateinamen. Angelegt wird nur, was im Vorschlag angehakt bleibt.

**Steuer-Übersicht:** Der Reiter „Steuer“ listet alle Dateien mit Steuer-Tag nach Jahr und kopiert sie auf Wunsch gesammelt in einen Ordner `Steuer-Belege <Jahr>` – die Originale bleiben, wo sie sind.

**Eingang-Zähler und Namensstil:** Der Knopf „Eingang“ zeigt, wie viele Dateien warten. In den Einstellungen lässt sich zwischen dem Schema mit Unterstrichen und einem lesbaren Stil mit Leerzeichen und Umlauten wählen.

## Sicherung

Im Reiter „Sicherung“ legt man Aufträge an: ein oder mehrere Ordner (oder einzelne Dateien) werden an ein Ziel gesichert – von Hand, stündlich, täglich oder wöchentlich. Verpasste Termine werden nachgeholt.

* **Ziele:** jeder erreichbare Ordner – externe Festplatte, eingebundene NAS-Freigabe oder der Ordner von Google Drive, OneDrive, Nextcloud oder iCloud Drive. Zusätzlich die eigene Nextcloud direkt per WebDAV (Adresse, Benutzer und App-Passwort stehen nur in der lokalen `.env`).
* **Spiegel:** kopiert nur Neues und Geändertes nach `Aktuell`. Ersetzte und gelöschte Dateien werden nicht überschrieben, sondern nach `Frühere Versionen/<Zeitstempel>` verschoben und nach einstellbarer Zeit aufgeräumt.
* **ZIP-Archiv:** je Lauf ein gepacktes Archiv mit Datum im Namen; die letzten N bleiben. Ohne Änderungen entsteht kein neues Archiv.
* **Schutz:** Ist die Platte nicht angeschlossen, wird nichts geschrieben. Aufgeräumt wird nur im eigenen, markierten Ordner `Dateien_Aktionen-Sicherung/<Auftrag>`. Finder-Tags werden in einer Begleitdatei mitgesichert und beim Wiederherstellen wieder gesetzt.
* **Wiederherstellen:** Dateien oder Ordner aus dem aktuellen Stand, einer früheren Version oder einem Archiv zurücklegen – vorhandene Dateien werden nie überschrieben.
* **Hintergrund:** Zeitpläne laufen, solange das Programm geöffnet ist, oder dauerhaft über den Hintergrunddienst (`python main.py dienst`).

Die Sicherung ist nicht verschlüsselt und ersetzt kein Time Machine.

## Speicherplatz

Der Reiter „Speicherplatz“ beantwortet die Frage, warum die Platte voll ist – ohne Terminal.

* **Messen:** `os.scandir` rekursiv mit `st_blocks * 512` (belegter Platz, deckt sich mit `du -sk`), Hardlinks nur einmal, keine Symlinks, keine Volume-Grenze. Pakete (`.app`, `.photoslibrary` …) zählen als eine Einheit. Der Scan läuft im Hintergrund, meldet Fortschritt und lässt sich abbrechen; nicht lesbare Ordner werden am Ende genannt.
* **Einordnen:** Geschützte Ordner und Pakete haben Vorrang. Im allgemeinen Scan prüft der Nutzer alle übrigen Funde selbst.
* **Freigeben:** Nach der Vorschau verschiebt macOS die Auswahl in den Papierkorb. Der tatsächliche Zielpfad wird für „Rückgängig“ protokolliert.
* **Installationsdateien:** `.dmg`/`.pkg` in Downloads und auf dem Schreibtisch werden gegen die installierten Programme in `/Applications` und `~/Applications` abgeglichen (Namenskern ohne Version und Füllwörter, Versionsvergleich über die `Info.plist`). Nur eindeutige Treffer werden angeboten; eine neuere Version in der Datei wird als „Bitte prüfen“ markiert.
* **Leserechte:** Die laufende App prüft den Zugriff auf Papierkorb und Programmordner in der Benutzer-Library. Die Detailansicht nennt die geprüften Pfade.

---

## Schnellstart

### 1. Konfiguration einrichten
Erstellen Sie eine Datei `.env` im Projektordner (Vorlage: `.env.example`):

```bash
cp .env.example .env
```

Tragen Sie in der `.env` Ihren Gemini-API-Schlüssel und Ihr bevorzugtes Modell ein:
```env
AI_PROVIDER=gemini
GEMINI_API_KEY=Ihr_Gemini_API_Key
GEMINI_MODEL=gemini-2.5-flash   # oder z. B. gemini-3.7-flash
```

*(Alternativ können Sie für lokale Modelle `AI_PROVIDER=local` mit LM Studio, MLX oder Ollama nutzen).*

### 2. Status prüfen
```bash
python main.py config
```

---

## Befehle & Verwendung

### 1. Ordner katalogisieren & Duplikate finden
Verschaffen Sie sich einen schnellen Überblick über einen Ordner:
```bash
python main.py catalog ~/Downloads
```

### 2. Vorschau / Dry-Run (Keine Dateien werden verändert!)
Lassen Sie die KI den Inhalt analysieren und Namensvorschläge generieren:
```bash
python main.py preview ~/Downloads/MeineScans
```
*Optional nach Kategorien filtern oder begrenzen:*
```bash
python main.py preview ~/Downloads --filter DOKUMENTE --limit 20
```

### 3. Ausführen (Umbenennen & Sortieren)
Nach Überprüfung der Vorschau die Aktionen anwenden:
```bash
python main.py run ~/Downloads/MeineScans
```
*In einen separaten Zielordner kopieren (anstatt verschieben):*
```bash
python main.py run ~/Downloads/MeineScans --target-dir ~/Documents/Archiv --copy
```

### 4. Rückgängig machen (Undo)
Macht die letzte Ausführung exakt rückgängig:
```bash
python main.py undo
```

### 5. Autopilot / Ordner-Wächter starten
Überwacht einen Ordner kontinuierlich auf neue Dateien:
```bash
python main.py watch ~/Downloads
```

### 6. OCR & Extraktion an einer einzelnen Datei testen
```bash
python main.py ocr-test /Pfad/zu/Dokument_oder_Scan.pdf
```

---

## Projektstruktur

```
Dateien_Aktionen/
├── bin/
│   ├── vision_ocr        # Natives macOS-Tool (Vision OCR, Szenen-Klassifikation & 64-Bit dHash)
│   └── icloud_download   # Natives macOS-Tool zum Nachladen von iCloud-Platzhaltern
├── history/              # Gespeicherte Manifeste (Undo), KI-Cache & Autopilot-Log
├── templates/
│   └── index.html        # Web-Dashboard Benutzeroberfläche
├── config.py             # Zentrale Konfiguration (Pfade, Kategorien, KI-Modelle, macOS-Pakete)
├── classifier.py         # Rekursiver Dateiscanner, Kategorisierung, SHA-256 & Perceptual Hashing
├── extractor.py          # Text- & EXIF/Medien-Extraktion (PDF, Office, iWork, mdls, Vision OCR)
├── ai_engine.py          # Multimodale KI-Schnittstelle (Gemini Vision, Local LLM, Offline-Heuristik)
├── organizer.py          # Parallele Planung, Ausführung, Finder-Tags, Kollisionsschutz, Rollback
├── watcher.py            # Autopilot / Hintergrund-Ordner-Wächter & macOS LaunchAgent
├── gui.py                # Lokaler Multithreaded Web-Server für das Dashboard
├── main.py               # Zentrales CLI-Werkzeug
├── .env.example          # Vorlage für Umgebungsvariablen
└── README.md
```
