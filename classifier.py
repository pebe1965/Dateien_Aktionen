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

from config import FILE_CATEGORIES, IGNORED_FILES, IGNORED_DIRS, MACOS_PACKAGE_EXTENSIONS, OCR_BINARY


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
        name = path.name

        # Erkennt macOS iCloud Drive Platzhalter-Dateien (.Dokument.pdf.icloud)
        if name.startswith(".") and name.endswith(".icloud"):
            clean_name = name[1:-7]  # Schneidet führenden Punkt '.' und Endung '.icloud' ab
            self.filename = clean_name
            self.extension = Path(clean_name).suffix.lower()
            self.is_cloud_placeholder = True
        else:
            self.filename = name
            self.extension = path.suffix.lower()
            self.is_cloud_placeholder = is_dataless_cloud_file(self.path)

        self.category = get_file_category(self.extension)

        try:
            stat_res = self.path.stat()
            self.size_bytes = stat_res.st_size
            self.created_at = datetime.fromtimestamp(stat_res.st_ctime)
            self.modified_at = datetime.fromtimestamp(stat_res.st_mtime)
        except Exception:
            self.size_bytes = 0
            self.created_at = datetime.now()
            self.modified_at = datetime.now()

        self.file_hash: Optional[str] = None

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
        self.root_dir = root_dir.expanduser().resolve()
        self.items: List[FileItem] = []
        self.by_category: Dict[str, List[FileItem]] = {}
        self.duplicates: Dict[str, List[FileItem]] = {}
        self.similar_images: List[Dict[str, Any]] = []

    def scan(self, compute_hashes: bool = True, detect_similar_images: bool = True) -> "Catalog":
        """
        Scannt den angegebenen Ordner rekursiv.
        Nutzt ein hochperformantes 2-Phasen-Verfahren:
        1. Schnelles Erfassen aller Dateien & Metadaten (os.walk ohne Hashing).
        2. Intelligente Duplikaterkennung NUR für Dateien mit exakt identischer Dateigröße.
        3. Optionale Erkennung optisch ähnlicher Fotos (Serienbilder / komprimierte Kopien) via Perceptual Hash (dHash).
        """
        self.items.clear()
        self.by_category.clear()
        self.duplicates.clear()
        self.similar_images.clear()

        walk_errors = []
        def on_walk_error(err):
            walk_errors.append(err)

        # Phase 1: Rekursiver Inode-Scan (rasend schnell, liest keine Dateiinhalte)
        for root, dirs, files in os.walk(self.root_dir, topdown=True, onerror=on_walk_error):
            # Ignorierte Ordner & macOS Package-Bundles überspringen (z.B. .app, .photoslibrary, .logicx)
            dirs[:] = [
                d for d in dirs 
                if d not in IGNORED_DIRS 
                and not d.startswith(".") 
                and not d.lower().endswith(MACOS_PACKAGE_EXTENSIONS)
            ]

            for file_name in files:
                is_icloud_file = file_name.startswith(".") and file_name.endswith(".icloud")
                if not is_icloud_file:
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

        if not self.items and walk_errors:
            first_err = walk_errors[0]
            if isinstance(first_err, PermissionError) or "Permission" in str(first_err) or "Operation not permitted" in str(first_err):
                raise PermissionError(f"Zugriff verweigert auf: {self.root_dir}")

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

        # Phase 3: Optisch ähnliche Fotos erkennen (Perceptual dHash via CoreGraphics)
        if detect_similar_images and OCR_BINARY.exists():
            image_items = [
                it for it in self.by_category.get("BILDER", [])
                if not it.is_cloud_placeholder
                and it.extension in {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tiff", ".tif", ".bmp"}
            ][:400]  # Bis zu 400 lokale Bilder pro Scan blitzschnell per CoreGraphics prüfen

            if len(image_items) > 1:
                self._find_similar_images(image_items)

        return self

    def _find_similar_images(self, image_items: List[FileItem], max_hamming: int = 8) -> None:
        """Berechnet 64-Bit Perceptual Hashes über `vision_ocr --dhash` und gruppiert ähnliche Bilder."""
        import subprocess

        path_to_item = {str(it.path): it for it in image_items}
        dhashes: List[tuple] = []  # (int_hash, hex_str, FileItem)

        # In Batches von 100 Pfaden an vision_ocr --dhash übergeben
        batch_size = 100
        paths_list = list(path_to_item.keys())
        for idx in range(0, len(paths_list), batch_size):
            batch = paths_list[idx:idx + batch_size]
            try:
                res = subprocess.run(
                    [str(OCR_BINARY), "--dhash"] + batch,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=15
                )
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        if "\t" in line:
                            hex_h, p_str = line.split("\t", 1)
                            val = int(hex_h, 16)
                            if val != 0 and p_str in path_to_item:
                                dhashes.append((val, hex_h, path_to_item[p_str]))
            except Exception:
                continue

        # Bereits als 100% exakte Duplikate gelistete Paare merken, um sie nicht doppelt zu melden
        exact_dup_paths = set()
        for dup_list in self.duplicates.values():
            for it in dup_list[1:]:
                exact_dup_paths.add(str(it.path))

        visited = set()
        for i in range(len(dhashes)):
            val_i, hex_i, item_i = dhashes[i]
            if str(item_i.path) in visited:
                continue
            group = [item_i]
            max_dist_in_group = 0
            for j in range(i + 1, len(dhashes)):
                val_j, hex_j, item_j = dhashes[j]
                if str(item_j.path) in visited:
                    continue
                # Wenn beide exakt denselben SHA-256 haben, überspringen (schon bei Exakte Duplikate)
                if item_i.file_hash and item_j.file_hash and item_i.file_hash == item_j.file_hash:
                    continue
                if item_i.size_bytes == item_j.size_bytes and str(item_j.path) in exact_dup_paths:
                    continue

                dist = bin(val_i ^ val_j).count("1")
                if dist <= max_hamming:
                    group.append(item_j)
                    visited.add(str(item_j.path))
                    if dist > max_dist_in_group:
                        max_dist_in_group = dist

            if len(group) > 1:
                visited.add(str(item_i.path))
                similarity_pct = round((1.0 - (max_dist_in_group / 64.0)) * 100)
                self.similar_images.append({
                    "dhash": hex_i,
                    "similarity_pct": similarity_pct,
                    "files": [it.to_dict() for it in group]
                })

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
        similar_count = sum(len(g["files"]) - 1 for g in self.similar_images)

        return {
            "root_dir": str(self.root_dir),
            "total_files": len(self.items),
            "total_bytes": total_size,
            "category_stats": category_stats,
            "duplicate_groups": len(self.duplicates),
            "duplicate_files_count": dup_count,
            "wasted_bytes": wasted_bytes,
            "similar_image_groups": len(self.similar_images),
            "similar_images_count": similar_count
        }

