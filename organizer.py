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
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from config import HISTORY_DIR
from classifier import Catalog, FileItem
from extractor import extract_content
from ai_engine import analyze_file_content, AnalysisResult


# Verlauf liegt im Benutzerordner (config.HISTORY_DIR), nicht im Programm —
# sonst löschte jedes Update die Möglichkeit, Umbenennungen rückgängig zu machen.
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


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
        prefix: Optional[str] = None
    ) -> List[PlannedAction]:
        """
        Scannt die Dateien, führt OCR / Extraktion durch und fragt die KI
        nach Namens- und Sortiervorschlägen.
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
            self.catalog.scan(compute_hashes=True)
            items = self.catalog.items
            if category_filter:
                items = [i for i in items if i.category == category_filter.upper()]
            if max_files:
                items = items[:max_files]

        for item in items:
            # 1. Inhalt extrahieren (OCR / Text)
            text_content, method = extract_content(item.path)

            # 2. KI befragen
            metadata_info = f"Dateigröße: {item.human_size}, Erstellt: {item.created_at.strftime('%Y-%m-%d')}"
            analysis = analyze_file_content(
                filename=item.filename,
                text_content=text_content,
                metadata_info=metadata_info,
                provider=self.provider if self.provider else None,
                prefix=prefix
            )

            # 3. Zielpfad ermitteln
            target_subfolder = self.target_dir / analysis.suggested_folder
            desired_target = target_subfolder / analysis.suggested_name
            final_target = get_unique_target_path(desired_target)

            action = PlannedAction(
                source_path=item.path,
                target_path=final_target,
                analysis=analysis
            )
            self.plan.append(action)

        return self.plan

    def execute_plan(self, copy_mode: bool = False) -> Path:
        """
        Führt den vorbereiteten Plan aus (Verschieben oder Kopieren)
        und speichert ein Manifest für ein mögliches Undo.
        """
        if not self.plan:
            raise ValueError("Kein Plan vorhanden. Bitte zuerst prepare_plan() ausführen.")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        manifest_file = HISTORY_DIR / f"manifest_{timestamp}.json"
        manifest_entries = []

        for action in self.plan:
            src = action.source_path
            dst = action.target_path

            if not src.exists():
                continue

            # Zielordner erstellen
            dst.parent.mkdir(parents=True, exist_ok=True)

            # Verschieben oder Kopieren
            if copy_mode:
                shutil.copy2(src, dst)
            else:
                shutil.move(src, dst)

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
