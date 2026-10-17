"""
Modul: watcher.py
Hintergrund-Ordner-Wächter (Autopilot / Watch-Folder) für macOS.
Überwacht ausgewählte Ordner (z. B. ~/Downloads oder ~/Desktop) auf neue Dateien,
analysiert diese automatisch per OCR/KI, sortiert sie in die Zielstruktur ein,
setzt macOS Finder-Tags und sendet eine native macOS-Mitteilung.
"""

import os
import sys
import time
import json
import plistlib
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from config import (
    BASE_DIR, IGNORED_FILES, IGNORED_DIRS, MACOS_PACKAGE_EXTENSIONS
)
from organizer import Organizer, HISTORY_DIR

AUTOPILOT_CONFIG_FILE = HISTORY_DIR / "autopilot_config.json"
AUTOPILOT_LOG_FILE = HISTORY_DIR / "autopilot_log.json"
LAUNCH_AGENT_LABEL = "com.dateienaktionen.watcher"
LAUNCH_AGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"

# Dateiendungen von laufenden/unfertigen Downloads (Safari, Chrome, Firefox, JDownloader etc.)
INCOMPLETE_DOWNLOAD_EXTENSIONS = (
    ".download", ".crdownload", ".part", ".partial", ".tmp",
    ".opdownload", ".filepart", ".fdmdownload", ".aria2"
)


def send_macos_notification(title: str, message: str, subtitle: str = "") -> None:
    """Sendet eine native macOS-Systemmitteilung über AppleScript (osascript)."""
    try:
        safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
        safe_msg = message.replace('\\', '\\\\').replace('"', '\\"')
        safe_sub = subtitle.replace('\\', '\\\\').replace('"', '\\"')
        if safe_sub:
            script = f'display notification "{safe_msg}" with title "{safe_title}" subtitle "{safe_sub}"'
        else:
            script = f'display notification "{safe_msg}" with title "{safe_title}"'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass


def load_autopilot_config() -> Dict[str, Any]:
    """Lädt die Autopilot-Konfiguration oder gibt sinnvolle Standardwerte zurück."""
    default_cfg = {
        "enabled": False,
        "watch_folders": [str(Path.home() / "Downloads")],
        "target_folder": "",  # Leer = im jeweiligen überwachten Ordner selbst in Unterordner sortieren
        "interval_seconds": 30,
        "min_file_age_seconds": 10,
        "copy_mode": False,
        "apply_tags": True,
        "notifications": True
    }
    if AUTOPILOT_CONFIG_FILE.exists():
        try:
            with open(AUTOPILOT_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_cfg.update(data)
        except Exception:
            pass
    return default_cfg


def save_autopilot_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Speichert die Autopilot-Konfiguration persistent."""
    current = load_autopilot_config()
    current.update(cfg)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(AUTOPILOT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
    return current


def load_autopilot_log(limit: int = 50) -> List[Dict[str, Any]]:
    """Lädt das Protokoll der automatisch vom Autopiloten sortierten Dateien."""
    if AUTOPILOT_LOG_FILE.exists():
        try:
            with open(AUTOPILOT_LOG_FILE, "r", encoding="utf-8") as f:
                entries = json.load(f)
                if isinstance(entries, list):
                    return entries[:limit]
        except Exception:
            pass
    return []


def append_autopilot_log(new_entries: List[Dict[str, Any]]) -> None:
    """Fügt neue Einträge oben an das Autopilot-Protokoll an (max. 200 Einträge)."""
    existing = load_autopilot_log(limit=200)
    combined = new_entries + existing
    combined = combined[:200]
    try:
        with open(AUTOPILOT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


class AutopilotWatcher:
    """
    Hintergrund-Wächter, der konfigurierte Ordner regelmäßig auf neue Dateien prüft
    und diese automatisch per KI/OCR analysiert und einsortiert.
    """

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._seen_signatures: set = set()
        self.is_scanning: bool = False
        self.last_scan_time: Optional[str] = None
        self.total_processed_session: int = 0
        self.last_error: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    def start(self) -> bool:
        with self._lock:
            if self.running:
                return True
            self._stop_event.clear()
            cfg = load_autopilot_config()
            cfg["enabled"] = True
            save_autopilot_config(cfg)
            self._thread = threading.Thread(target=self._run_loop, name="AutopilotWatcher", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> bool:
        with self._lock:
            self._stop_event.set()
            cfg = load_autopilot_config()
            cfg["enabled"] = False
            save_autopilot_config(cfg)
            return True

    def status(self) -> Dict[str, Any]:
        cfg = load_autopilot_config()
        return {
            "running": self.running,
            "is_scanning": self.is_scanning,
            "last_scan_time": self.last_scan_time,
            "total_processed_session": self.total_processed_session,
            "last_error": self.last_error,
            "launch_agent_installed": is_launch_agent_installed(),
            "config": cfg,
            "recent_log": load_autopilot_log(limit=30)
        }

    def scan_once(self) -> List[Dict[str, Any]]:
        """Führt einen einzelnen Überwachungs-Durchlauf über alle Watch-Folders aus."""
        if self.is_scanning:
            return []

        self.is_scanning = True
        self.last_error = None
        processed_records: List[Dict[str, Any]] = []

        try:
            cfg = load_autopilot_config()
            watch_folders = cfg.get("watch_folders", [])
            custom_target = cfg.get("target_folder", "").strip()
            min_age = max(2, int(cfg.get("min_file_age_seconds", 10)))
            copy_mode = bool(cfg.get("copy_mode", False))
            apply_tags = bool(cfg.get("apply_tags", True))
            notify = bool(cfg.get("notifications", True))

            now = time.time()

            for folder_str in watch_folders:
                if not folder_str:
                    continue
                watch_dir = Path(folder_str).expanduser().resolve()
                if not watch_dir.exists() or not watch_dir.is_dir():
                    continue

                target_dir = Path(custom_target).expanduser().resolve() if custom_target else watch_dir

                # Nur Dateien auf oberster Ebene des überwachten Ordners betrachten,
                # damit bereits einsortierte Unterordner nicht erneut durchsucht werden!
                ready_files: List[Path] = []
                try:
                    for entry in sorted(watch_dir.iterdir()):
                        if entry.name.startswith(".") or entry.name in IGNORED_FILES:
                            continue
                        if entry.is_dir() or entry.is_symlink():
                            continue
                        name_lower = entry.name.lower()
                        if name_lower.endswith(INCOMPLETE_DOWNLOAD_EXTENSIONS) or name_lower.endswith(MACOS_PACKAGE_EXTENSIONS):
                            continue

                        try:
                            st = entry.stat()
                        except OSError:
                            continue

                        # Leerdateien oder noch im Schreibvorgang befindliche Dateien überspringen
                        if st.st_size == 0 or (now - st.st_mtime) < min_age:
                            continue

                        sig = (str(entry), int(st.st_mtime), st.st_size)
                        if sig in self._seen_signatures:
                            continue

                        ready_files.append(entry)
                except (PermissionError, OSError):
                    continue

                if not ready_files:
                    continue

                organizer = Organizer(source_dir=watch_dir, target_dir=target_dir)
                plan = organizer.prepare_plan(specific_files=ready_files, use_cache=True)
                if not plan:
                    continue

                manifest_path = organizer.execute_plan(copy_mode=copy_mode, apply_tags=apply_tags)

                # Ergebnisse protokollieren & Signaturen merken
                batch_records = []
                for action in plan:
                    # Neue Signatur am Zielort merken, falls Ziel im selben Ordner liegt
                    if action.target_path.exists():
                        try:
                            nst = action.target_path.stat()
                            self._seen_signatures.add((str(action.target_path), int(nst.st_mtime), nst.st_size))
                        except OSError:
                            pass
                    if action.source_path.exists():
                        try:
                            ost = action.source_path.stat()
                            self._seen_signatures.add((str(action.source_path), int(ost.st_mtime), ost.st_size))
                        except OSError:
                            pass

                    rec = {
                        "timestamp": datetime.now().isoformat(),
                        "original_name": action.source_path.name,
                        "new_name": action.target_path.name,
                        "source_path": str(action.source_path),
                        "target_path": str(action.target_path),
                        "folder": action.analysis.suggested_folder,
                        "doc_type": action.analysis.doc_type,
                        "sender": action.analysis.sender,
                        "manifest": manifest_path.name
                    }
                    batch_records.append(rec)
                    processed_records.append(rec)

                if batch_records:
                    append_autopilot_log(batch_records)
                    self.total_processed_session += len(batch_records)

                    if notify:
                        if len(batch_records) == 1:
                            r = batch_records[0]
                            send_macos_notification(
                                "Dateien_Aktionen Autopilot",
                                f"{r['original_name']} ➔ {r['folder']}/{r['new_name']}",
                                subtitle=f"Ordner: {watch_dir.name}"
                            )
                        else:
                            send_macos_notification(
                                "Dateien_Aktionen Autopilot",
                                f"{len(batch_records)} neue Dateien automatisch sortiert & umbenannt.",
                                subtitle=f"Ordner: {watch_dir.name}"
                            )

            self.last_scan_time = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            self.last_error = str(e)
        finally:
            self.is_scanning = False

        return processed_records

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.scan_once()
            cfg = load_autopilot_config()
            interval = max(5, int(cfg.get("interval_seconds", 30)))
            self._stop_event.wait(interval)


# Globale Singleton-Instanz für das Web-GUI
GLOBAL_WATCHER = AutopilotWatcher()


def is_launch_agent_installed() -> bool:
    """Prüft, ob der macOS LaunchAgent für den Autopiloten installiert ist."""
    return LAUNCH_AGENT_PLIST.exists()


def install_launch_agent() -> Dict[str, Any]:
    """
    Erstellt und aktiviert einen nativen macOS LaunchAgent unter
    ~/Library/LaunchAgents/com.dateienaktionen.watcher.plist,
    sodass der Ordner-Wächter automatisch beim macOS-Login im Hintergrund startet.
    """
    try:
        LAUNCH_AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
        venv_py = BASE_DIR / "venv" / "bin" / "python3"
        python_bin = str(venv_py) if venv_py.exists() else sys.executable
        main_script = str(BASE_DIR / "main.py")

        plist_content = {
            "Label": LAUNCH_AGENT_LABEL,
            "ProgramArguments": [python_bin, main_script, "watch"],
            "WorkingDirectory": str(BASE_DIR),
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": str(HISTORY_DIR / "autopilot_daemon.log"),
            "StandardErrorPath": str(HISTORY_DIR / "autopilot_daemon.err"),
        }

        with open(LAUNCH_AGENT_PLIST, "wb") as f:
            plistlib.dump(plist_content, f)

        subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT_PLIST)], capture_output=True)
        subprocess.run(["launchctl", "load", str(LAUNCH_AGENT_PLIST)], capture_output=True)
        return {"status": "ok", "installed": True, "plist": str(LAUNCH_AGENT_PLIST)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def uninstall_launch_agent() -> Dict[str, Any]:
    """Entfernt den macOS LaunchAgent wieder sauber."""
    try:
        if LAUNCH_AGENT_PLIST.exists():
            subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT_PLIST)], capture_output=True)
            LAUNCH_AGENT_PLIST.unlink()
        return {"status": "ok", "installed": False}
    except Exception as e:
        return {"status": "error", "error": str(e)}
