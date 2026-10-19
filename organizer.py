"""
Modul: organizer.py
Orchestriert den Ablauf:
1. Katalogisieren
2. Analyse & Umbenennungs-Plan (Dry-Run / Preview)
3. Sicheres Verschieben / Umbenennen
4. Undo-Funktion (Rückgängigmachen anhand von Manifest-Dateien)
"""

import os
import json
import shutil
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
                and not p.name.startswith(".")
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
                                and not sub.name.startswith(".")
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

        # 1. Finder-Tags setzen (saubere, eindeutige Liste ohne leere Strings)
        clean_tags = []
        for t in tags:
            t_str = str(t).strip()
            if t_str and t_str.lower() not in {"unbekannt", "sonstiges", "sortiert", "none", "null"} and t_str not in clean_tags:
                clean_tags.append(t_str)

        if clean_tags:
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
        self.target_dir = target_dir.resolve() if target_dir else self.source_dir
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
        cache = _load_analysis_cache() if use_cache else {}
        cache_dirty = False
        active_prov = self.provider if self.provider else config.AI_PROVIDER
        progress_lock = threading.Lock()

        def process_single_item(item: FileItem) -> PlannedAction:
            nonlocal cache_dirty
            cache_key = f"{item.path}_{item.size_bytes}_{int(item.modified_at.timestamp())}_{active_prov}"

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
                    provider_used=f"{c_entry.get('provider_used', active_prov)} ⚡ Cache"
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
                    existing_folders=existing_folders
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

            # 3. Zielpfad ermitteln
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
                tags_to_set = [a.doc_type, a.sender]
                if a.doc_date and len(a.doc_date) >= 4:
                    tags_to_set.append(a.doc_date[:4])
                set_macos_tags_and_comment(dst, tags=tags_to_set, comment=a.summary or "")

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
