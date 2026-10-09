# Dateien_Aktionen 🗂️⚡️

Ein maßgeschneidertes, KI- und OCR-gestütztes Werkzeug für macOS zum Katalogisieren, Verstehen und strukturierten Umbenennen von Dateien.

Entwickelt für Apple Silicon Macs (M-Serie) unter Ausnutzung der **Apple Neural Engine (macOS Vision OCR)** und flexiblen KI-Schnittstellen (**Google Gemini API** oder **lokale LLMs**).

---

## Highlights

* 🔍 **Katalogisierung & Duplikaterkennung:** Rekursiver Scan nach Dateitypen (`DOKUMENTE`, `BILDER`, `VIDEOS`, `AUDIO`, `ARCHIVE`, `CODE_DATEN`) mit SHA-256-Prüfsummen zur Erkennung doppelter Dateien.
* 👁️ **Apple Vision OCR (Native):** Scans und Bilder werden direkt über Apples Vision-Framework auf dem Mac ausgelesen – blitzschnell und ohne externe OCR-Installationen.
* 📄 **Vielseitige Textextraktion:** Unterstützt digitale PDFs, gescannte PDFs, Office-Dateien (`.docx`, `.xlsx`), Apple iWork (`.pages`, `.numbers`), Text/Markdown und Bilddateien.
* 🧠 **KI-Inhaltsanalyse:** Erkennt automatisch:
  * Reales Dokumentdatum (`YYYY-MM-DD`)
  * Absender / Vertragspartner / Organisation
  * Dokumentenart (Rechnung, Vertrag, Kontoauszug, Bescheid, etc.)
  * Prägnanten Betreff
  * Standardisiertes Namensformat: `YYYY-MM-DD_Absender_Typ_Thema.ext`
* 🛡️ **100 % Sicherheit mit Dry-Run & Undo:**
  * Vor jedem Umbenennen/Verschieben gibt es eine tabellarische Vorschau (`preview`).
  * Jede Aktion wird in einem `manifest.json` protokolliert.
  * Mit `python main.py undo` lässt sich jede Operation mit einem Befehl rückgängig machen.

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

### 5. OCR & Extraktion an einer einzelnen Datei testen
```bash
python main.py ocr-test /Pfad/zu/Dokument_oder_Scan.pdf
```

---

## Projektstruktur

```
Dateien_Aktionen/
├── bin/
│   └── vision_ocr        # Natives macOS-Kommandozeilentool (Vision Framework OCR)
├── history/              # Gespeicherte Manifeste für die Undo-Funktion
├── config.py             # Zentrale Konfiguration (Pfade, Kategorien, KI-Modelle)
├── classifier.py         # Rekursiver Dateiscanner, Kategorisierung, Hashing
├── extractor.py          # Textextraktion (PDF, Office, iWork, OCR)
├── ai_engine.py          # KI-Schnittstelle (Gemini, Local LLM, Offline-Heuristik)
├── organizer.py          # Planung, Ausführung, Kollisionsschutz, Rollback
├── main.py               # Zentrales CLI-Werkzeug
├── .env.example          # Vorlage für Umgebungsvariablen
└── README.md
```
