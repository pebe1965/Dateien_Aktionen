"""
Modul: classifier.py
Zuständig für das rekursive Scannen, Kategorisieren, Duplikaterkennung
und Erstellen eines Katalogs von Dateien auf der Festplatte.
"""

import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from config import FILE_CATEGORIES, IGNORED_FILES, IGNORED_DIRS


def get_file_category(extension: str) -> str:
    """Bestimmt die Kategorie basierend auf der Dateiendung."""
    ext = extension.lower()
    for category, extensions in FILE_CATEGORIES.items():
        if ext in extensions:
            return category
    return "SONSTIGES"


UF_DATALESS = 0x40000000


def is_dataless_cloud_file(file_path: Path, stat_res: Optional[os.stat_result] = None) -> bool:
    """
    Erkennt, ob eine Datei nur als Cloud-Platzhalter existiert (iCloud Drive / Nextcloud / OneDrive / Dropbox).
    Bei ausgelagerten Dateien verhindert dies, dass macOS die Datei ungewollt aus dem Internet herunterlädt.
    """
    try:
        if file_path.name.endswith(".icloud"):
            return True
        st = stat_res if stat_res is not None else file_path.stat()
        flags = getattr(st, "st_flags", 0)
        return bool(flags & UF_DATALESS)
    except Exception:
        return False


def calculate_file_hash(file_path: Path, block_size: int = 65536, max_read: Optional[int] = None) -> str:
    """
    Berechnet einen SHA-256 Hash.
    Verhindert Downloads von ausgelagerten Cloud-Dateien (iCloud/Nextcloud).
    """
    try:
        if is_dataless_cloud_file(file_path):
            return ""

        hasher = hashlib.sha256()
        bytes_read = 0
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(block_size)
                if not chunk:
                    break
                hasher.update(chunk)
                bytes_read += len(chunk)
                if max_read and bytes_read >= max_read:
                    break
        return hasher.hexdigest()
    except (PermissionError, OSError):
        return ""


def quick_header_hash(file_path: Path, header_size: int = 8192) -> str:
    """Berechnet einen schnellen Hash über die ersten 8 KB zur Vorab-Filterung von Duplikaten."""
    return calculate_file_hash(file_path, block_size=header_size, max_read=header_size)


class FileItem:
    """Repräsentiert eine gefundene Datei mit Metadaten."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.filename = path.name
        self.extension = path.suffix.lower()
        self.category = get_file_category(self.extension)
        
        stat_res = self.path.stat()
        self.size_bytes = stat_res.st_size
        self.created_at = datetime.fromtimestamp(stat_res.st_ctime)
        self.modified_at = datetime.fromtimestamp(stat_res.st_mtime)
        self.file_hash: Optional[str] = None
        
        # Cloud-Status prüfen (iCloud / Nextcloud online-only)
        self.is_cloud_placeholder = is_dataless_cloud_file(self.path, stat_res)

    def compute_hash(self) -> str:
        if self.file_hash is None:
            self.file_hash = calculate_file_hash(self.path)
        return self.file_hash

    @property
    def human_size(self) -> str:
        s = float(self.size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if s < 1024.0:
                return f"{s:.1f} {unit}"
            s /= 1024.0
        return f"{s:.1f} PB"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "filename": self.filename,
            "extension": self.extension,
            "category": self.category,
            "size_bytes": self.size_bytes,
            "human_size": self.human_size,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "hash": self.file_hash,
            "is_cloud_placeholder": self.is_cloud_placeholder
        }


class Catalog:
    """Verwaltet den Katalog aller gescannten Dateien."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.items: List[FileItem] = []
        self.by_category: Dict[str, List[FileItem]] = {}
        self.duplicates: Dict[str, List[FileItem]] = {}

    def scan(self, compute_hashes: bool = True) -> "Catalog":
        """
        Scannt den angegebenen Ordner rekursiv.
        Nutzt ein hochperformantes 2-Phasen-Verfahren:
        1. Schnelles Erfassen aller Dateien & Metadaten (os.walk ohne Hashing).
        2. Intelligente Duplikaterkennung NUR für Dateien mit exakt identischer Dateigröße.
        """
        self.items.clear()
        self.by_category.clear()
        self.duplicates.clear()

        # Phase 1: Rekursiver Inode-Scan (rasend schnell, liest keine Dateiinhalte)
        for root, dirs, files in os.walk(self.root_dir, topdown=True, onerror=None):
            # Ignorierte Ordner überspringen (inkl. .app Pakete und Frameworks)
            dirs[:] = [
                d for d in dirs 
                if d not in IGNORED_DIRS 
                and not d.startswith(".") 
                and not d.endswith(".app") 
                and not d.endswith(".framework")
                and not d.endswith(".bundle")
            ]

            for file_name in files:
                if file_name in IGNORED_FILES or file_name.startswith("."):
                    continue

                full_path = Path(root) / file_name
                try:
                    if full_path.is_file() and not full_path.is_symlink():
                        item = FileItem(full_path)
                        self.items.append(item)
                        self.by_category.setdefault(item.category, []).append(item)
                except (PermissionError, OSError):
                    continue

        # Phase 2: Intelligente & selektive Duplikaterkennung
        if compute_hashes and self.items:
            # 1. Nach Dateigröße vorfiltern: Dateien mit einzigartiger Größe KÖNNEN KEINE Duplikate sein!
            size_map: Dict[int, List[FileItem]] = {}
            for item in self.items:
                if item.size_bytes > 0 and not item.is_cloud_placeholder:
                    size_map.setdefault(item.size_bytes, []).append(item)

            same_size_groups = [items for items in size_map.values() if len(items) > 1]

            # 2. Schnellprüfung über Header-Hash (erste 8 KB)
            header_map: Dict[str, List[FileItem]] = {}
            for group in same_size_groups:
                for item in group:
                    h_quick = quick_header_hash(item.path)
                    if h_quick:
                        key = f"{item.size_bytes}_{h_quick}"
                        header_map.setdefault(key, []).append(item)

            same_header_groups = [items for items in header_map.values() if len(items) > 1]

            # 3. Vollständiger SHA-256 Hash NUR für verbleibende Kandidaten
            full_hash_map: Dict[str, List[FileItem]] = {}
            for group in same_header_groups:
                for item in group:
                    h_full = item.compute_hash()
                    if h_full:
                        full_hash_map.setdefault(h_full, []).append(item)

            self.duplicates = {h: items for h, items in full_hash_map.items() if len(items) > 1}

        return self

    def summary(self) -> Dict[str, Any]:
        """Gibt eine statistische Zusammenfassung des Katalogs zurück."""
        total_size = sum(item.size_bytes for item in self.items)
        category_stats = {}
        for cat, items in self.by_category.items():
            cat_size = sum(i.size_bytes for i in items)
            category_stats[cat] = {
                "count": len(items),
                "total_bytes": cat_size
            }

        dup_count = sum(len(items) - 1 for items in self.duplicates.values())
        wasted_bytes = sum((len(items) - 1) * items[0].size_bytes for items in self.duplicates.values())

        return {
            "root_dir": str(self.root_dir),
            "total_files": len(self.items),
            "total_bytes": total_size,
            "category_stats": category_stats,
            "duplicate_groups": len(self.duplicates),
            "duplicate_files_count": dup_count,
            "wasted_bytes": wasted_bytes
        }
