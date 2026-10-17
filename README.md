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
* 🛡️ **100 % Sicherheit mit Dry-Run, Kollisionsschutz & Undo:**
  * Vor jedem Umbenennen/Verschieben gibt es eine interaktive Vorschau mit frei editierbaren Dateinamen und Zielordnern.
  * Jede Aktion (auch vom Autopiloten) wird in einem `manifest.json` protokolliert und lässt sich mit 1 Klick rückgängig machen.

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
