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
APP_VERSION = "1.10.1"
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
                    # Kommentar nur nach Leerzeichen abtrennen — ein Ordnerpfad darf „#“ enthalten
                    val = val.strip()
                    val = (val.split(" #")[0] if not val.startswith("#") else "").strip().strip('"').strip("'")
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

# --- ORDNUNGSSYSTEM (Eingang / Projekte / Ablage / Archiv) ---
# Basisordner, unter dem die vier Hauptordner liegen (z. B. in iCloud Drive).
# Leer = kein Ordnungssystem eingerichtet. Der Pfad steht nur in der lokalen
# .env des Nutzers, nie im Programm.
ORDNUNG_BASIS = os.getenv("ORDNUNG_BASIS", "")
# "frei"   -> die KI schlägt Ordner frei vor (Verhalten bis 1.4.0)
# "ablage" -> es wird in die Kategorien von „03 Ablage“ einsortiert; neue
#             Kategorien entstehen nur nach Bestätigung in der Vorschau
SORTIER_MODUS = os.getenv("SORTIER_MODUS", "frei")

# Namensstil der vorgeschlagenen Dateinamen:
# "schema" -> 2026-03-14_Telekom_Rechnung_Mobilfunk (Unterstriche, ohne Umlaute — wie bisher)
# "lesbar" -> 2026-03-14 Telekom Mobilfunk März (Leerzeichen, Umlaute erlaubt)
NAMENSSTIL = os.getenv("NAMENSSTIL", "schema")

ORDNUNG_ORDNER = {
    "eingang": "01 Eingang",    # Briefkasten: alles Neue, Unverarbeitete
    "projekte": "02 Projekte",  # Schreibtisch: aktuell Relevantes
    "ablage": "03 Ablage",      # Schränke & Regale: dauerhafte Kategorien
    "archiv": "Archiv",         # Keller: abgeschlossen, selten gebraucht
}
# Vorschlag für den Anfang — nur auf Wunsch angelegt, frei änderbar.
ABLAGE_STARTKATEGORIEN = [
    "Anschaffungen", "Arbeit", "Arzt", "Auto", "Finanzen", "Versicherung", "Wohnen",
]


def ordnung_pfad(name: str):
    """Pfad eines Hauptordners ("eingang", "projekte", "ablage", "archiv") oder None.

    Liest ORDNUNG_BASIS bei jedem Aufruf neu — die Oberfläche ändert den Wert
    zur Laufzeit.
    """
    basis = (ORDNUNG_BASIS or "").strip()
    if not basis:
        return None
    return Path(basis).expanduser() / ORDNUNG_ORDNER[name]


def ablage_ziel():
    """Der Ablage-Ordner, wenn der Ablage-Modus aktiv und eingerichtet ist — sonst None."""
    if SORTIER_MODUS != "ablage":
        return None
    ablage = ordnung_pfad("ablage")
    return ablage if ablage and ablage.is_dir() else None


# --- SICHERUNG: Nextcloud direkt (WebDAV) ---
# Adresse, Benutzer und App-Passwort der eigenen Nextcloud des Nutzers. Stehen nur
# in der lokalen .env — mitgeliefert wird nichts davon. In der Nextcloud unter
# „Einstellungen → Sicherheit → Geräte & Sitzungen“ ein App-Passwort erstellen.
NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL", "")
NEXTCLOUD_BENUTZER = os.getenv("NEXTCLOUD_BENUTZER", "")
NEXTCLOUD_APP_PASSWORT = os.getenv("NEXTCLOUD_APP_PASSWORT", "")

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

# macOS Package-Ordner (erscheinen im Finder als einzelne Datei/Mediathek und dürfen NICHT innerlich zerlegt werden)
MACOS_PACKAGE_EXTENSIONS = (
    ".app", ".framework", ".bundle", ".plugin", ".kext", ".xcodeproj", ".xcworkspace",
    ".playground", ".photoslibrary", ".aplibrary", ".theater", ".imovielibrary",
    ".fcpbundle", ".fcpproject", ".logicx", ".band", ".wand", ".rtfd", ".fdmdownload",
    ".download", ".sparsebundle", ".sparseimage", ".qlgenerator", ".mdimporter",
    ".prefpane", ".saver", ".slide", ".scptd", ".pkg", ".mpkg", ".abbu", ".vmsd", ".vmwarevm"
)


# --- SPEICHERPLATZ (Reiter „Speicherplatz“) ---
# Entstanden aus einer Aufräumaktion von Hand: Die Platte war fast voll und die
# Ursachen (30 GB in einem versteckten .turbo/cache, 38 GB Videos in einem
# Ordner namens „Cache“) ließen sich nur im Terminal finden. Die Listen hier
# sind Daten, keine Logik — die Einordnung macht speicher.py.

# Mindestgröße (MB) für die Ansicht „Größte Dateien“
SPEICHER_MINDESTGROESSE_MB = int(os.getenv("SPEICHER_MINDESTGROESSE_MB", "100") or 100)

# Wie der Baum angezeigt wird: Tiefe, Einträge je Ebene, Gesamtzahl der Knoten
SPEICHER_BAUM_TIEFE = 6
SPEICHER_BAUM_BREITE = 15
# Wie viele Ordner je Ebene in den Baum dürfen. Je Ebene ein eigenes Budget:
# Ohne das verbrauchten die tiefen Ordner (node_modules!) das Gesamtbudget,
# und der Baum kam oben leer an.
SPEICHER_BAUM_KNOTEN_JE_TIEFE = {0: 1, 1: 40, 2: 300, 3: 800, 4: 1200, 5: 1500, 6: 1500}
# Ein Unterordner kommt nur in den Baum, wenn er mindestens so groß ist …
SPEICHER_BAUM_MINDEST_BYTES = 10 * 1024 * 1024
# … oder diesen Anteil des Startordners ausmacht
SPEICHER_BAUM_MINDEST_ANTEIL = 0.01

# Stufe „Gefahrlos“: Ordnernamen bekannter Zwischenspeicher, die sich von
# selbst neu aufbauen. Der Hinweis steht so in der Oberfläche.
# Achtung: Ein Treffer allein genügt nicht — enthält der Ordner eigene Fotos,
# Videos, Musik oder Dokumente, wird er zu „Ihre Entscheidung“ (Fall CapCut).
GEFAHRLOS_NAMEN = {
    "node_modules": "Pakete eines Projekts. „npm install“ lädt sie wieder.",
    ".next": "Build-Ausgabe von Next.js. Baut sich beim nächsten Build neu auf.",
    ".nuxt": "Build-Ausgabe von Nuxt. Baut sich beim nächsten Build neu auf.",
    ".turbo": "Zwischenspeicher von Turborepo. Baut sich neu auf.",
    ".parcel-cache": "Zwischenspeicher von Parcel. Baut sich neu auf.",
    ".vite": "Zwischenspeicher von Vite. Baut sich neu auf.",
    ".svelte-kit": "Build-Ausgabe von SvelteKit. Baut sich neu auf.",
    ".angular": "Zwischenspeicher von Angular. Baut sich neu auf.",
    ".pio": "Zwischenspeicher von PlatformIO. Baut sich neu auf.",
    "__pycache__": "Zwischendateien von Python. Entstehen bei Bedarf neu.",
    ".pytest_cache": "Zwischenspeicher von pytest.",
    ".mypy_cache": "Zwischenspeicher von mypy.",
    ".ruff_cache": "Zwischenspeicher von Ruff.",
    ".gradle": "Zwischenspeicher von Gradle. Lädt bei Bedarf neu.",
    "deriveddata": "Build-Ordner von Xcode. Xcode legt ihn neu an.",
    ".sass-cache": "Zwischenspeicher von Sass.",
    "cache": "Heißt „Cache“ — meist ein Zwischenspeicher.",
    "caches": "Heißt „Caches“ — meist ein Zwischenspeicher.",
}

# Stufe „Gefahrlos“ nach Lage: Es gilt die längste passende Regel, deshalb
# zählt „~/Library/Caches“ stärker als die Auffangregel „~/Library“.
GEFAHRLOS_PFADE = [
    ("~/.npm", "Zwischenspeicher von npm. Lädt bei Bedarf neu."),
    ("~/.cache", "Zwischenspeicher verschiedener Programme."),
    ("~/.yarn/cache", "Zwischenspeicher von Yarn."),
    ("~/.pnpm-store", "Zwischenspeicher von pnpm."),
    ("~/Library/pnpm/store", "Zwischenspeicher von pnpm. Lädt bei Bedarf neu."),
    ("~/.bun/install/cache", "Zwischenspeicher von Bun."),
    ("~/.gradle", "Zwischenspeicher von Gradle."),
    ("~/.cocoapods", "Zwischenspeicher von CocoaPods."),
    ("~/Library/Caches", "Zwischenspeicher eines Programms. Wird neu angelegt."),
    ("~/Library/Developer/Xcode/DerivedData", "Build-Ordner von Xcode. Xcode legt ihn neu an."),
    ("~/Library/Developer/Xcode/iOS DeviceSupport", "Hilfsdateien für angeschlossene Geräte. Werden bei Bedarf neu geladen."),
    ("~/Library/Logs", "Protokolle von Programmen."),
    ("~/.Trash", "Der Papierkorb."),
]

# Stufe „Nicht anfassen“: wird angezeigt, aber ohne Knopf zum Löschen.
# Der Hinweis sagt, wo man es stattdessen aufräumt.
NICHT_ANFASSEN_PFADE = [
    ("~/Library/Application Support", "Programmdaten. Hier liegen die Daten deiner Programme — aufräumen nur im Programm selbst."),
    ("~/Library/Containers", "Daten von Programmen aus dem App Store."),
    ("~/Library/Group Containers", "Gemeinsame Daten mehrerer Programme."),
    ("~/Library/Mobile Documents", "iCloud Drive. Hier löschst du besser im Finder."),
    ("~/Library/CloudStorage", "Cloud-Ordner (iCloud, Dropbox, OneDrive). Hier löschst du besser im Finder."),
    ("~/Library/Keychains", "Schlüsselbund mit deinen Passwörtern."),
    ("~/Library/Mail", "Deine Mails. Aufräumen in der Mail-App."),
    ("~/Library/Messages", "Deine Nachrichten. Aufräumen in der Nachrichten-App."),
    ("~/Library/Photos", "Daten der Fotos-App. Aufräumen in der Fotos-App."),
    ("~/Library/Developer/CoreSimulator", "iOS-Simulatoren. Aufräumen in Xcode unter „Window → Devices and Simulators“."),
    ("~/Library", "Programmdaten von macOS und deinen Programmen."),
    ("~/Applications", "Programme. Zum Entfernen das Programm deinstallieren."),
]

# Ordner, die beim Messen übersprungen werden. Cloud-Ordner antworten bei jeder
# Datei über das Netz — ein Scan des Benutzerordners blieb darin minutenlang
# hängen. Freigeben lässt sich dort ohnehin nichts; der Papierkorb wird im
# Reiter getrennt gemessen. Wer einen davon selbst als Startordner wählt,
# bekommt ihn trotzdem gemessen.
SPEICHER_NICHT_DURCHSUCHEN = [
    ("~/Library/Mobile Documents", "iCloud Drive – wird über das Netz gelesen und deshalb nicht mitgemessen."),
    ("~/Library/CloudStorage", "Cloud-Ordner (Dropbox, Google Drive, OneDrive) – wird nicht mitgemessen."),
    ("~/.Trash", "Der Papierkorb – seine Größe steht oben im Reiter."),
]

# Pakete, die als Ganzes nicht zum Löschen angeboten werden
NICHT_ANFASSEN_PAKETE = {
    ".app": "Ein Programm. Zum Entfernen in den Papierkorb ziehen.",
    ".photoslibrary": "Eine Fotomediathek. Aufräumen in der Fotos-App.",
    ".aplibrary": "Eine Fotomediathek. Aufräumen in der Fotos-App.",
    ".imovielibrary": "Eine iMovie-Mediathek. Aufräumen in iMovie.",
    ".theater": "Ein iMovie-Film. Aufräumen in iMovie.",
    ".fcpbundle": "Eine Final-Cut-Mediathek. Aufräumen in Final Cut Pro.",
    ".logicx": "Ein Logic-Projekt. Aufräumen in Logic Pro.",
    ".framework": "Programmbestandteil.",
}

# Woran „eigene Dateien“ erkannt werden: Fotos, Videos, Musik ab 2 MB und
# Dokumente ab 100 KB. Endungen wie .md, .json oder .svg zählen nicht mit —
# davon liegen tausende in jedem node_modules.
SPEICHER_EIGENE_MEDIEN_ENDUNGEN = (
    FILE_CATEGORIES["VIDEOS"] | FILE_CATEGORIES["BILDER"] | FILE_CATEGORIES["AUDIO"]
) - {".svg", ".gif", ".bmp", ".ico"}
SPEICHER_EIGENE_DOKUMENT_ENDUNGEN = {
    ".pdf", ".pages", ".numbers", ".key", ".doc", ".docx",
    ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".rtf",
}
SPEICHER_MEDIEN_MINDEST_BYTES = 2 * 1024 * 1024
SPEICHER_DOKUMENT_MINDEST_BYTES = 100 * 1024
# Ab so viel eigenen Dateien gilt ein Zwischenspeicher als „Ihre Entscheidung“
SPEICHER_EIGENE_SCHWELLE_BYTES = 20 * 1024 * 1024
SPEICHER_EIGENE_SCHWELLE_ANTEIL = 0.10
