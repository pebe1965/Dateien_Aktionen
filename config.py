"""
Konfiguration für Dateien_Aktionen
Zentrale Einstellungen für KI, OCR, Kategorien und Namenskonventionen.
"""

import os
import shutil
from pathlib import Path

# Basis-Verzeichnis des Programms (im App-Bundle: …/Contents/Resources/app)
BASE_DIR = Path(__file__).resolve().parent

# Anwendungs-Version & GitHub Repository für automatische Updates
APP_VERSION = "1.1.4"
GITHUB_REPO = "pebe1965/Dateien_Aktionen"

# --- DATEN DES NUTZERS ---
# Einstellungen (.env) und Verlauf für „Rückgängig“ liegen NICHT im Programm,
# sondern im Benutzerordner. Bis 1.1.0 lagen sie im App-Bundle: Ein Update
# (Programm ersetzen) löschte beides — Zugangscode weg, Umbenennungen nicht
# mehr rückgängig zu machen. Und weil das Bundle beim Bauen nur überschrieben
# wurde, landete die .env samt API-Schlüssel im veröffentlichten DMG.
DATA_DIR = Path(
    os.getenv("DATEIEN_AKTIONEN_DATA_DIR")
    or Path.home() / "Library" / "Application Support" / "Dateien_Aktionen"
)
ENV_PATH = DATA_DIR / ".env"
HISTORY_DIR = DATA_DIR / "history"


def _uebernehme_alte_daten() -> None:
    """Einmalig: .env und Verlauf vom alten Ort (neben dem Programm) übernehmen.

    Kopiert, verschiebt nicht — das Programmverzeichnis kann schreibgeschützt
    sein (DMG), und ein Fehlschlag soll nichts verlieren. Bereits vorhandene
    Dateien am neuen Ort werden nie überschrieben.
    """
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        alt_env = BASE_DIR / ".env"
        if alt_env.exists() and not ENV_PATH.exists():
            shutil.copy2(alt_env, ENV_PATH)
            os.chmod(ENV_PATH, 0o600)
        alt_history = BASE_DIR / "history"
        if alt_history.is_dir():
            for f in alt_history.glob("*.json"):
                ziel = HISTORY_DIR / f.name
                if not ziel.exists():
                    shutil.copy2(f, ziel)
    except Exception as e:
        print(f"⚠️ Alte Einstellungen/Verlauf konnten nicht übernommen werden: {e}")


_uebernehme_alte_daten()

# .env-Datei automatisch laden (falls vorhanden), ganz ohne externe Bibliothek
env_path = ENV_PATH
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
#   "app"     -> KI über das NotionaryAtlas-Konto (Zugangscode aus dem Marketplace)
#   "gemini"  -> Eigener Google-Gemini-Schlüssel
#   "local"   -> Lokaler Server (z.B. MLX / LM Studio / Ollama unter LOCAL_API_URL)
#   "offline" -> Regelbasierte Heuristik (ohne KI, via Regex & Metadaten)
AI_PROVIDER = os.getenv("AI_PROVIDER", "app")

# KI über NotionaryAtlas: Das Programm enthält bewusst KEINEN Gemini-Schlüssel.
# Im Marketplace der App erstellt man einen persönlichen Zugangscode; die App
# reicht die Anfrage mit ihrem Schlüssel an Gemini weiter und rechnet über die
# KI-Credits des Kontos ab. Der Code liegt nur in der lokalen .env.
NOTIONARY_ZUGANGSCODE = os.getenv("NOTIONARY_ZUGANGSCODE", "")
NOTIONARY_KI_URL = os.getenv("NOTIONARY_KI_URL", "https://app.pberthold.com/api/ai/desktop-tool")
NOTIONARY_MARKETPLACE_URL = "https://app.pberthold.com/marketplace"

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
