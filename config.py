"""
Konfiguration für Dateien_Aktionen
Zentrale Einstellungen für KI, OCR, Kategorien und Namenskonventionen.
"""

import os
from pathlib import Path

# Basis-Verzeichnis des Projekts
BASE_DIR = Path(__file__).resolve().parent

# Anwendungs-Version & GitHub Repository für automatische Updates
APP_VERSION = "1.0.2"
GITHUB_REPO = "pebe1965/Dateien_Aktionen"

# .env-Datei automatisch laden (falls vorhanden), ganz ohne externe Bibliothek
env_path = BASE_DIR / ".env"
if env_path.exists():
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    val = val.split("#")[0].strip().strip('"').strip("'")
                    os.environ.setdefault(key.strip(), val)
    except Exception:
        pass

# --- KI-KONFIGURATION ---
# Provider-Auswahl:
#   "gemini"  -> Google Gemini API
#   "local"   -> Lokaler Server (z.B. MLX / LM Studio / Ollama unter LOCAL_API_URL)
#   "offline" -> Regelbasierte Heuristik (ohne KI, via Regex & Metadaten)
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")

# Gemini-Einstellungen
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Standard-Modell (z. B. "gemini-2.5-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-3.1-pro")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Lokale KI-Einstellungen (falls AI_PROVIDER = "local")
LOCAL_API_URL = os.getenv("LOCAL_API_URL", "http://localhost:1234/v1/chat/completions")
LOCAL_MODEL = os.getenv("LOCAL_MODEL", "local-model")

# --- OCR & CLOUD-EINSTELLUNGEN ---
# Pfad zum kompilierten nativen macOS Vision-OCR-Tool
OCR_BINARY = BASE_DIR / "bin" / "vision_ocr"
ICLOUD_BINARY = BASE_DIR / "bin" / "icloud_download"
OCR_LANGUAGES = ["de-DE", "en-US"]
OCR_MAX_PAGES = 5  # Wie viele Seiten eines PDFs maximal per OCR gescannt werden

# --- KATEGORIEN-MAPPING (Dateiendungen) ---
FILE_CATEGORIES = {
    "DOKUMENTE": {
        ".pdf", ".pages", ".numbers", ".key",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".txt", ".rtf", ".odt", ".ods", ".odp",
        ".csv", ".tsv", ".md"
    },
    "BILDER": {
        ".jpg", ".jpeg", ".png", ".heic", ".heif",
        ".tiff", ".tif", ".webp", ".gif", ".bmp",
        ".svg", ".raw", ".cr2", ".nef", ".arw", ".dng"
    },
    "VIDEOS": {
        ".mp4", ".mov", ".m4v", ".mkv", ".avi",
        ".wmv", ".flv", ".webm"
    },
    "AUDIO": {
        ".mp3", ".m4a", ".flac", ".wav", ".aac",
        ".aiff", ".alac", ".ogg", ".wma"
    },
    "ARCHIVE": {
        ".zip", ".tar", ".gz", ".tgz", ".bz2",
        ".7z", ".rar", ".dmg", ".pkg", ".iso"
    },
    "CODE_DATEN": {
        ".py", ".swift", ".js", ".ts", ".html", ".css",
        ".json", ".xml", ".yaml", ".yml", ".sql", ".sh"
    }
}

# Standard-Zielordner-Struktur (falls sortiert werden soll)
TARGET_STRUCTURE = {
    "by_category": True,     # z. B. Zielordner/Dokumente/Rechnungen/2024/...
    "by_year": True,         # Ordner nach Erstellungsjahr gliedern
}

# Ignorierte Dateinamen & Systemdateien
IGNORED_FILES = {
    ".DS_Store", ".localized", "Thumbs.db", "desktop.ini"
}
IGNORED_DIRS = {
    ".git", ".svn", "__pycache__", "venv", ".venv", "node_modules", ".Trash",
    "DerivedData", ".gradle", ".cache", "Pods", "build", "dist", "Caches"
}
