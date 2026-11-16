"""
Modul: organizer.py
Orchestriert den Ablauf:
1. Katalogisieren
2. Analyse & Umbenennungs-Plan (Dry-Run / Preview)
3. Sicheres Verschieben / Umbenennen
4. Undo-Funktion (Rückgängigmachen anhand von Manifest-Dateien)
"""

import os
import re
import json
import shutil
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

import config
from config import HISTORY_DIR, IGNORED_DIRS, MACOS_PACKAGE_EXTENSIONS
from classifier import Catalog, FileItem
from extractor import extract_content
from ai_engine import analyze_file_content, AnalysisResult, clean_filename


# Verlauf & Cache liegen im Benutzerordner (config.HISTORY_DIR), nicht im Programm —
# sonst löschte jedes Update die Möglichkeit, Umbenennungen rückgängig zu machen.
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = HISTORY_DIR / "analysis_cache.json"
_CACHE_LOCK = threading.Lock()

# Globaler Live-Fortschrittsstatus für das Web-UI
ANALYSIS_PROGRESS = {
    "running": False,
    "current": 0,
    "total": 0,
    "current_file": "",
    "cached_hits": 0
}


def _load_analysis_cache() -> Dict[str, Any]:
    with _CACHE_LOCK:
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}


def _save_analysis_cache(cache_data: Dict[str, Any]) -> None:
    with _CACHE_LOCK:
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


def discover_existing_subfolders(root_dir: Path, max_depth: int = 2) -> List[str]:
    """
    Scannt die bereits vorhandenen Unterordner (bis Tiefe 2) im Zielverzeichnis,
    damit die KI bestehende Ordner wiederverwendet statt Duplikat-Ordner anzulegen.
    """
    subfolders: List[str] = []
    if not root_dir.exists() or not root_dir.is_dir():
        return subfolders

    try:
        for p in sorted(root_dir.iterdir()):
            if (
                p.is_dir()
                and not p.name.startswith((".", "_"))
                and p.name not in IGNORED_DIRS
                and not p.name.lower().endswith(MACOS_PACKAGE_EXTENSIONS)
            ):
                rel1 = p.name
                subfolders.append(rel1)
                if max_depth >= 2:
                    try:
                        for sub in sorted(p.iterdir()):
                            if (
                                sub.is_dir()
                                and not sub.name.startswith((".", "_"))
                                and sub.name not in IGNORED_DIRS
                                and not sub.name.lower().endswith(MACOS_PACKAGE_EXTENSIONS)
                            ):
                                subfolders.append(f"{rel1}/{sub.name}")
                    except (PermissionError, OSError):
                        continue
    except (PermissionError, OSError):
        pass

    return subfolders


class PlannedAction:
    """Repräsentiert eine geplante Umbenennung / Verschiebung."""

    def __init__(self, source_path: Path, target_path: Path, analysis: AnalysisResult):
        self.source_path = source_path
        self.target_path = target_path
        self.analysis = analysis

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "target_path": str(self.target_path),
            "original_name": self.source_path.name,
            "new_name": self.target_path.name,
            "analysis": self.analysis.to_dict()
        }


def get_unique_target_path(target_path: Path) -> Path:
    """Verhindert versehentliches Überschreiben, falls der Zieldateiname bereits existiert."""
    if not target_path.exists():
        return target_path

    parent = target_path.parent
    stem = target_path.stem
    suffix = target_path.suffix
    counter = 1

    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def lege_grundstruktur_an(basis: Path, mit_startkategorien: bool = False) -> Dict[str, Any]:
    """Legt die vier Hauptordner des Ordnungssystems unter `basis` an.

    Vorhandene Ordner bleiben unberührt (nichts wird überschrieben oder verschoben).
    Gibt zurück, was neu angelegt wurde und was schon da war.
    """
    basis = Path(basis).expanduser()
    angelegt: List[str] = []
    vorhanden: List[str] = []

    def _anlegen(pfad: Path) -> None:
        rel = str(pfad.relative_to(basis))
        if pfad.is_dir():
            vorhanden.append(rel)
        else:
            pfad.mkdir(parents=True, exist_ok=True)
            angelegt.append(rel)

    for name in config.ORDNUNG_ORDNER.values():
        _anlegen(basis / name)
    if mit_startkategorien:
        for kat in config.ABLAGE_STARTKATEGORIEN:
            _anlegen(basis / config.ORDNUNG_ORDNER["ablage"] / kat)

    return {"basis": str(basis), "angelegt": angelegt, "vorhanden": vorhanden}


# --- PROJEKTE („02 Projekte“ = Schreibtisch) -------------------------------
# Ein Projekt ist ein Ordner direkt in „02 Projekte“: mit Termin als
# „JJJJ-MM-TT_Name“ (sortiert sich von selbst chronologisch) oder ohne als „Name“.

_PROJEKT_DATUM = re.compile(r"^(\d{4}-\d{2}-\d{2})[_ ](.+)$")


def _projekt_ordner(name: str) -> Path:
    """Prüft einen Projektnamen aus der Oberfläche und gibt den Ordner zurück (nur direkte Unterordner)."""
    projekte = config.ordnung_pfad("projekte")
    if not projekte or not projekte.is_dir():
        raise ValueError("Das Ordnungssystem ist noch nicht eingerichtet.")
    name = str(name or "").strip()
    if not name or Path(name).name != name or name.startswith((".", "_")):
        raise ValueError("Ungültiger Projektname.")
    pfad = projekte / name
    if not pfad.is_dir():
        raise ValueError(f"Projekt nicht gefunden: {name}")
    return pfad


def liste_projekte() -> List[Dict[str, Any]]:
    """Alle laufenden Projekte, Termine zuerst (chronologisch), danach die ohne Termin."""
    projekte = config.ordnung_pfad("projekte")
    ergebnis: List[Dict[str, Any]] = []
    if not projekte or not projekte.is_dir():
        return ergebnis
    try:
        ordner = sorted(p for p in projekte.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
    except (PermissionError, OSError):
        return ergebnis

    for p in ordner:
        if p.name.lower().endswith(MACOS_PACKAGE_EXTENSIONS):
            continue
        m = _PROJEKT_DATUM.match(p.name)
        termin, titel = (m.group(1), m.group(2)) if m else (None, p.name)
        tage = None
        if termin:
            try:
                tage = (datetime.strptime(termin, "%Y-%m-%d").date() - datetime.now().date()).days
            except ValueError:
                termin, titel = None, p.name
        anzahl = 0
        try:
            for _root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                anzahl += sum(1 for f in files if not f.startswith(".") and f not in config.IGNORED_FILES)
                if anzahl > 5000:
                    break
        except OSError:
            pass
        ergebnis.append({
            "name": p.name, "titel": titel, "termin": termin, "tage_bis_termin": tage,
            "dateien": anzahl, "pfad": str(p)
        })
    ergebnis.sort(key=lambda e: (e["termin"] is None, e["termin"] or "", e["titel"].lower()))
    return ergebnis


def lege_projekt_an(titel: str, termin: Optional[str] = None) -> Dict[str, Any]:
    """Legt ein Projekt an. Mit Termin (JJJJ-MM-TT) heißt der Ordner „JJJJ-MM-TT_Titel“."""
    projekte = config.ordnung_pfad("projekte")
    if not projekte or not projekte.is_dir():
        raise ValueError("Das Ordnungssystem ist noch nicht eingerichtet (Einstellungen → Grundstruktur anlegen).")

    titel = re.sub(r'[/\\:*?"<>|]', " ", str(titel or ""))
    titel = re.sub(r"\s+", " ", titel).strip().lstrip("._")
    if not titel:
        raise ValueError("Bitte einen Projektnamen eingeben.")

    termin = str(termin or "").strip()
    if termin:
        try:
            datetime.strptime(termin, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Der Termin muss ein Datum im Format JJJJ-MM-TT sein.")
        name = f"{termin}_{titel}"
    else:
        name = titel

    pfad = projekte / name
    if pfad.exists():
        raise ValueError(f"Ein Projekt „{name}“ gibt es schon.")
    pfad.mkdir()
    return {"name": name, "pfad": str(pfad)}


def schliesse_projekt_ab(name: str, ziel: str, kategorie: str = "") -> Dict[str, Any]:
    """Verschiebt ein abgeschlossenes Projekt als Ganzes ins Archiv oder in eine Kategorie der Ablage.

    Schreibt ein Manifest, damit sich der Schritt über „Rückgängig“ zurücknehmen lässt.
    (Der Papierkorb läuft über die Oberfläche — dort holt man es im Finder zurück.)
    """
    quelle = _projekt_ordner(name)

    if ziel == "archiv":
        ziel_eltern = config.ordnung_pfad("archiv")
    elif ziel == "ablage":
        ablage = config.ordnung_pfad("ablage")
        teile = [t for t in re.split(r"[/\\]+", str(kategorie or "")) if t and t not in (".", "..")]
        ziel_eltern = ablage.joinpath(*teile) if teile else ablage
        if not ziel_eltern.is_dir():
            raise ValueError("Diese Kategorie gibt es in der Ablage nicht.")
    else:
        raise ValueError("Unbekanntes Ziel.")

    ziel_eltern.mkdir(parents=True, exist_ok=True)
    ziel_pfad = ziel_eltern / quelle.name
    zaehler = 1
    while ziel_pfad.exists():
        ziel_pfad = ziel_eltern / f"{quelle.name}_{zaehler}"
        zaehler += 1
    shutil.move(str(quelle), str(ziel_pfad))

    jetzt = datetime.now()
    manifest_file = HISTORY_DIR / f"manifest_{jetzt.strftime('%Y%m%d_%H%M%S')}.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump({
            "created_at": jetzt.isoformat(),
            "total_actions": 1,
            "beschreibung": f"Projekt „{quelle.name}“ abgeschlossen",
            "actions": [{"source": str(quelle), "target": str(ziel_pfad), "copy_mode": False, "timestamp": jetzt.isoformat()}]
        }, f, indent=2, ensure_ascii=False)

    return {"ziel": str(ziel_pfad), "manifest": manifest_file.name}


def zaehle_eingang() -> Optional[int]:
    """Wie viele Dateien im Eingang auf Verarbeitung warten (None, wenn kein Eingang eingerichtet ist)."""
    eingang = config.ordnung_pfad("eingang")
    if not eingang or not eingang.is_dir():
        return None
    try:
        return sum(
            1 for e in eingang.iterdir()
            if e.is_file() and not e.name.startswith(".") and e.name not in config.IGNORED_FILES
        )
    except (PermissionError, OSError):
        return None


# --- STEUER: nur Tags, kein Ordner ------------------------------------------
_STEUER_TAG = re.compile(r"^Steuer ((?:19|20)\d{2})$")
STEUER_SAMMELORDNER = "Steuer-Belege"


def finde_steuer_belege() -> Dict[str, List[Dict[str, Any]]]:
    """Sucht im Ordnungssystem alle Dateien mit dem Finder-Tag „Steuer <Jahr>“, gruppiert nach Jahr.

    Liest die Tags direkt an den Dateien (unabhängig vom Spotlight-Index). Sammelkopien
    („Steuer-Belege …“) werden übersprungen, damit nichts doppelt zählt.
    """
    import ctypes
    import ctypes.util

    basis = Path(config.ORDNUNG_BASIS).expanduser() if (config.ORDNUNG_BASIS or "").strip() else None
    ergebnis: Dict[str, List[Dict[str, Any]]] = {}
    if not basis or not basis.is_dir():
        return ergebnis

    libc = ctypes.CDLL(ctypes.util.find_library("c") or "/usr/lib/libSystem.B.dylib")
    for root, dirs, files in os.walk(basis):
        dirs[:] = sorted(
            d for d in dirs
            if not d.startswith(".") and d not in IGNORED_DIRS
            and not d.startswith(STEUER_SAMMELORDNER) and not d.lower().endswith(MACOS_PACKAGE_EXTENSIONS)
        )
        for fname in sorted(files):
            if fname.startswith(".") or fname in config.IGNORED_FILES:
                continue
            pfad = Path(root) / fname
            for tag in _lese_finder_tags(libc, str(pfad).encode("utf-8")):
                m = _STEUER_TAG.match(tag.split("\n")[0].strip())
                if not m:
                    continue
                try:
                    groesse = pfad.stat().st_size
                except OSError:
                    groesse = 0
                ergebnis.setdefault(m.group(1), []).append({
                    "name": fname,
                    "pfad": str(pfad),
                    "ordner": str(Path(root).relative_to(basis)),
                    "groesse": groesse,
                })
    return ergebnis


def sammle_steuer_belege(jahr: str, ziel_eltern: Path) -> Dict[str, Any]:
    """Kopiert alle Belege eines Steuerjahres nach `<ziel>/Steuer-Belege <Jahr>/<Kategorie>/`.

    Die Originale bleiben, wo sie sind. Ein Manifest erlaubt, die Kopien über „Rückgängig“ wieder zu entfernen.
    """
    jahr = str(jahr).strip()
    if not re.fullmatch(r"(19|20)\d{2}", jahr):
        raise ValueError("Ungültiges Jahr.")
    ziel_eltern = Path(ziel_eltern).expanduser()
    if not ziel_eltern.is_dir():
        raise ValueError("Der Zielordner existiert nicht.")
    belege = finde_steuer_belege().get(jahr, [])
    if not belege:
        raise ValueError(f"Keine Dateien mit dem Tag „Steuer {jahr}“ gefunden.")

    ziel = ziel_eltern / f"{STEUER_SAMMELORDNER} {jahr}"
    jetzt = datetime.now()
    eintraege = []
    for b in belege:
        quelle = Path(b["pfad"])
        if not quelle.is_file():
            continue
        unterordner = ziel / (Path(b["ordner"]).name or "Allgemein")
        unterordner.mkdir(parents=True, exist_ok=True)
        dst = get_unique_target_path(unterordner / quelle.name)
        shutil.copy2(quelle, dst)
        eintraege.append({"source": str(quelle), "target": str(dst), "copy_mode": True, "timestamp": jetzt.isoformat()})

    manifest_file = HISTORY_DIR / f"manifest_{jetzt.strftime('%Y%m%d_%H%M%S')}.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump({
            "created_at": jetzt.isoformat(),
            "total_actions": len(eintraege),
            "beschreibung": f"Steuer-Belege {jahr} kopiert",
            "actions": eintraege
        }, f, indent=2, ensure_ascii=False)
    return {"ziel": str(ziel), "kopiert": len(eintraege), "manifest": manifest_file.name}


def tags_fuer_analyse(analysis: Any) -> List[str]:
    """Finder-Tags zu einer Analyse: Art, Absender, Jahr — und „Steuer <Jahr>“ bei steuerrelevanten Belegen.

    Nimmt ein AnalysisResult oder dessen dict (so kommt es aus der Oberfläche zurück).
    """
    a = analysis if isinstance(analysis, dict) else analysis.to_dict()
    tags = [a.get("doc_type") or "", a.get("sender") or ""]
    doc_date = str(a.get("doc_date") or "")
    if len(doc_date) >= 4:
        tags.append(doc_date[:4])
    steuer_jahr = str(a.get("steuer_jahr") or "").strip()
    if steuer_jahr:
        tags.append(f"Steuer {steuer_jahr}")
    return tags


def _lese_finder_tags(libc: Any, c_path: bytes) -> List[str]:
    """Liest die vorhandenen Finder-Tags einer Datei (leer, wenn keine gesetzt sind)."""
    import plistlib
    import ctypes

    name = b"com.apple.metadata:_kMDItemUserTags"
    try:
        libc.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
        libc.getxattr.restype = ctypes.c_ssize_t
        size = libc.getxattr(c_path, name, None, 0, 0, 0)
        if size <= 0:
            return []
        buf = ctypes.create_string_buffer(size)
        got = libc.getxattr(c_path, name, buf, size, 0, 0)
        if got <= 0:
            return []
        werte = plistlib.loads(buf.raw[:got])
        return [str(w) for w in werte] if isinstance(werte, list) else []
    except Exception:
        return []


def set_macos_tags_and_comment(file_path: Path, tags: List[str], comment: str = "") -> bool:
    """
    Schreibt native macOS Finder-Tags (`com.apple.metadata:_kMDItemUserTags`) und
    Spotlight/Finder-Kommentare (`com.apple.metadata:kMDItemFinderComment`)
    direkt als Extended Attributes (xattr) im Binary-Plist-Format an die Datei.
    Dadurch sind KI-Kategorien und Zusammenfassungen sofort über Spotlight & Finder auffindbar.
    """
    import plistlib
    import ctypes
    import ctypes.util

    if not file_path.exists():
        return False

    try:
        libc_path = ctypes.util.find_library("c") or "/usr/lib/libSystem.B.dylib"
        libc = ctypes.CDLL(libc_path)
        # int setxattr(const char *path, const char *name, const void *value, size_t size, u_int32_t position, int options);
        libc.setxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
        libc.setxattr.restype = ctypes.c_int

        c_path = str(file_path.resolve()).encode("utf-8")

        # 1. Finder-Tags setzen (saubere, eindeutige Liste ohne leere Strings).
        # Bereits vorhandene Tags bleiben erhalten — eigene Tags des Nutzers (auch
        # farbige, gespeichert als "Name\n<Farbnummer>") dürfen nicht verschwinden.
        clean_tags = _lese_finder_tags(libc, c_path)
        schon_da = {t.split("\n")[0].strip().lower() for t in clean_tags}
        neue = 0
        for t in tags:
            t_str = str(t).strip()
            if t_str and t_str.lower() not in {"unbekannt", "sonstiges", "sortiert", "none", "null"} and t_str.lower() not in schon_da:
                clean_tags.append(t_str)
                schon_da.add(t_str.lower())
                neue += 1

        if neue:
            tag_bplist = plistlib.dumps(clean_tags, fmt=plistlib.FMT_BINARY)
            libc.setxattr(
                c_path,
                b"com.apple.metadata:_kMDItemUserTags",
                tag_bplist,
                len(tag_bplist),
                0,
                0
            )

        # 2. Finder/Spotlight-Kommentar setzen
        if comment and comment.strip():
            comment_bplist = plistlib.dumps(comment.strip(), fmt=plistlib.FMT_BINARY)
            libc.setxattr(
                c_path,
                b"com.apple.metadata:kMDItemFinderComment",
                comment_bplist,
                len(comment_bplist),
                0,
                0
            )
        return True
    except Exception:
        return False


class Organizer:
    """Hauptklasse für Analyse, Organisation und Undo."""

    def __init__(self, source_dir: Path, target_dir: Optional[Path] = None, provider: Optional[str] = None):
        self.source_dir = source_dir.resolve()
        # Ablage-Modus: Ohne ausdrückliches Ziel wird in „03 Ablage“ einsortiert —
        # aus dem Eingang heraus in feste Kategorien, statt Unterordner im Eingang anzulegen.
        ablage = config.ablage_ziel()
        if target_dir:
            self.target_dir = target_dir.resolve()
        elif ablage:
            self.target_dir = ablage.resolve()
        else:
            self.target_dir = self.source_dir
        self.ablage_modus = bool(ablage and self.target_dir == ablage.resolve())
        self.provider = provider
        self.catalog = Catalog(self.source_dir)
        self.plan: List[PlannedAction] = []

    def prepare_plan(
        self,
        category_filter: Optional[str] = None,
        max_files: Optional[int] = None,
        specific_paths: Optional[List[str]] = None,
        prefix: Optional[str] = None,
        use_cache: bool = True,
        max_workers: int = 4,
        recursive: bool = True
    ) -> List[PlannedAction]:
        """
        Scannt die Dateien, prüft den lokalen Analyse-Cache, führt OCR / Extraktion parallel durch
        und fragt die KI (unter Berücksichtigung bestehender Unterordner) nach Namens- und Sortiervorschlägen.
        Gibt den fertigen Plan (ohne Dateien zu verändern) zurück.
        """
        self.plan.clear()

        if specific_paths:
            items = []
            for p_str in specific_paths:
                p = Path(p_str).resolve()
                if p.exists() and p.is_file():
                    items.append(FileItem(p))
        else:
            self.catalog.scan(compute_hashes=True, recursive=recursive)
            items = self.catalog.items
            if category_filter:
                items = [i for i in items if i.category == category_filter.upper()]
            if max_files:
                items = items[:max_files]

        total_items = len(items)
        ANALYSIS_PROGRESS["running"] = True
        ANALYSIS_PROGRESS["current"] = 0
        ANALYSIS_PROGRESS["total"] = total_items
        ANALYSIS_PROGRESS["current_file"] = "Starte Analyse..."
        ANALYSIS_PROGRESS["cached_hits"] = 0

        if total_items == 0:
            ANALYSIS_PROGRESS["running"] = False
            return self.plan

        existing_folders = discover_existing_subfolders(self.target_dir)
        # Laufende Projekte: Im Ablage-Modus darf die KI eine Datei einem Projekt zuordnen
        projekte_dir = config.ordnung_pfad("projekte") if self.ablage_modus else None
        projekt_namen = [p["name"] for p in liste_projekte()] if projekte_dir else []
        projekt_key = hashlib.sha1("|".join(projekt_namen).encode("utf-8")).hexdigest()[:8]
        cache = _load_analysis_cache() if use_cache else {}
        cache_dirty = False
        active_prov = self.provider if self.provider else config.AI_PROVIDER
        progress_lock = threading.Lock()

        def process_single_item(item: FileItem) -> PlannedAction:
            nonlocal cache_dirty
            modus_key = f"ablage:{self.target_dir}:{projekt_key}" if self.ablage_modus else "frei"
            if config.NAMENSSTIL == "lesbar":
                modus_key += ":lesbar"
            cache_key = f"{item.path}_{item.size_bytes}_{int(item.modified_at.timestamp())}_{active_prov}_{modus_key}"

            with progress_lock:
                ANALYSIS_PROGRESS["current_file"] = item.filename

            analysis: Optional[AnalysisResult] = None

            if use_cache and cache_key in cache:
                c_entry = cache[cache_key]
                base_stem = Path(c_entry.get("suggested_name", item.filename)).stem
                if prefix:
                    p_clean = clean_filename(prefix)
                    if not p_clean.endswith("_") and not prefix.endswith("-"):
                        p_clean += "_"
                    final_name = f"{p_clean}{base_stem}{item.extension}"
                else:
                    final_name = c_entry.get("suggested_name", item.filename)

                analysis = AnalysisResult(
                    original_name=item.filename,
                    extension=item.extension,
                    suggested_name=final_name,
                    suggested_folder=c_entry.get("suggested_folder", "Sortiert"),
                    doc_date=c_entry.get("doc_date"),
                    sender=c_entry.get("sender", "Unbekannt"),
                    doc_type=c_entry.get("doc_type", "Sonstiges"),
                    topic=c_entry.get("topic", ""),
                    summary=c_entry.get("summary", ""),
                    provider_used=f"{c_entry.get('provider_used', active_prov)} ⚡ Cache",
                    steuer_jahr=c_entry.get("steuer_jahr"),
                    projekt=c_entry.get("projekt")
                )
                with progress_lock:
                    ANALYSIS_PROGRESS["cached_hits"] += 1
            else:
                # 1. Inhalt extrahieren (OCR / Text / EXIF)
                text_content, method = extract_content(item.path)

                # 2. KI befragen (inkl. Bildpfad für Multimodal Vision & bestehende Ordner)
                metadata_info = f"Dateigröße: {item.human_size}, Erstellt: {item.created_at.strftime('%Y-%m-%d')}"
                raw_analysis = analyze_file_content(
                    filename=item.filename,
                    text_content=text_content,
                    metadata_info=metadata_info,
                    provider=self.provider if self.provider else None,
                    prefix=None,  # im Cache ohne Präfix speichern
                    file_path=item.path,
                    existing_folders=existing_folders,
                    ablage_modus=self.ablage_modus,
                    projekte=projekt_namen
                )

                # Im Cache ablegen (sofern nicht reiner Fallback bei gewünschter Cloud-KI)
                with _CACHE_LOCK:
                    cache[cache_key] = raw_analysis.to_dict()
                    cache_dirty = True

                if prefix:
                    p_clean = clean_filename(prefix)
                    if not p_clean.endswith("_") and not prefix.endswith("-"):
                        p_clean += "_"
                    prefixed_name = f"{p_clean}{Path(raw_analysis.suggested_name).stem}{item.extension}"
                    raw_analysis.suggested_name = prefixed_name

                analysis = raw_analysis

            # 3. Zielpfad ermitteln. Im Ablage-Modus hier frisch prüfen, ob die Kategorie
            # schon existiert — ein Cache-Eintrag kann älter sein als der Ordner.
            if analysis.projekt and analysis.projekt in projekt_namen:
                # Gehört zu einem laufenden Projekt → auf den Schreibtisch statt in die Ablage
                analysis.suggested_folder = analysis.projekt
                analysis.neuer_ordner = False
                target_subfolder = projekte_dir / analysis.projekt
            else:
                analysis.projekt = None
                if self.ablage_modus:
                    analysis.neuer_ordner = not (self.target_dir / analysis.suggested_folder).is_dir()
                target_subfolder = self.target_dir / analysis.suggested_folder
            desired_target = target_subfolder / analysis.suggested_name
            final_target = get_unique_target_path(desired_target)

            with progress_lock:
                ANALYSIS_PROGRESS["current"] += 1
                ANALYSIS_PROGRESS["current_file"] = item.filename

            return PlannedAction(
                source_path=item.path,
                target_path=final_target,
                analysis=analysis
            )

        try:
            workers = min(max_workers, max(1, total_items))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(process_single_item, items))
            self.plan.extend(results)
        finally:
            if cache_dirty:
                _save_analysis_cache(cache)
            ANALYSIS_PROGRESS["running"] = False

        return self.plan

    def execute_plan(self, copy_mode: bool = False, apply_tags: bool = True) -> Path:
        """
        Führt den vorbereiteten Plan aus (Verschieben oder Kopieren),
        setzt optional native macOS Finder-Tags & Spotlight-Kommentare
        und speichert ein Manifest für ein mögliches Undo.
        """
        if not self.plan:
            raise ValueError("Kein Plan vorhanden. Bitte zuerst prepare_plan() ausführen.")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        manifest_file = HISTORY_DIR / f"manifest_{timestamp}.json"
        manifest_entries = []

        for action in self.plan:
            src = action.source_path
            desired_dst = action.target_path

            if not src.exists():
                continue

            # Zielordner erstellen
            desired_dst.parent.mkdir(parents=True, exist_ok=True)

            # Kollisionsschutz unmittelbar vor dem Verschieben/Kopieren (falls mehrere Dateien im Plan denselben Namen erhielten)
            if src.resolve() == desired_dst.resolve():
                dst = desired_dst
            else:
                dst = get_unique_target_path(desired_dst)

            # Verschieben oder Kopieren
            if copy_mode:
                shutil.copy2(src, dst)
            else:
                if src.resolve() != dst.resolve():
                    shutil.move(src, dst)

            # Native macOS Finder-Tags & Spotlight-Kommentar setzen
            if apply_tags and action.analysis:
                a = action.analysis
                set_macos_tags_and_comment(dst, tags=tags_fuer_analyse(a), comment=a.summary or "")

            manifest_entries.append({
                "source": str(src),
                "target": str(dst),
                "copy_mode": copy_mode,
                "timestamp": datetime.now().isoformat()
            })

        # Manifest speichern
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({
                "created_at": datetime.now().isoformat(),
                "total_actions": len(manifest_entries),
                "actions": manifest_entries
            }, f, indent=2, ensure_ascii=False)

        return manifest_file


def rollback_manifest(manifest_path: Path) -> int:
    """
    Macht alle Operationen einer Manifest-Datei exakt rückgängig.
    Gibt die Anzahl der zurückgesetzten Dateien zurück.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest nicht gefunden: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    actions = data.get("actions", [])
    restored_count = 0

    # In umgekehrter Reihenfolge rückgängig machen
    for entry in reversed(actions):
        src = Path(entry["source"])
        dst = Path(entry["target"])
        is_copy = entry.get("copy_mode", False)

        if is_copy:
            # Bei einer Kopie wird die Kopie am Zielort wieder gelöscht
            if dst.exists():
                dst.unlink()
                restored_count += 1
        else:
            # Beim Verschieben wird die Datei zurück an den Quellort verschoben
            if dst.exists():
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(dst, src)
                restored_count += 1

    return restored_count
