#!/usr/bin/env python3
"""
Dateien_Aktionen GUI
Moderne Web-basierte Benutzeroberfläche für macOS.
Startet einen lokalen Server und öffnet das Dashboard automatisch im Browser.
"""

import os
import sys
import json
import socket
import webbrowser
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Projektpfad einbinden
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import config
from classifier import Catalog, ist_paket
from extractor import extract_content
from organizer import (
    Organizer, rollback_manifest, get_unique_target_path,
    set_macos_tags_and_comment, tags_fuer_analyse, lege_grundstruktur_an,
    liste_projekte, lege_projekt_an, schliesse_projekt_ab, discover_existing_subfolders,
    _projekt_ordner, zaehle_eingang, finde_steuer_belege, sammle_steuer_belege,
    HISTORY_DIR, ANALYSIS_PROGRESS
)
import backup
import speicher
from watcher import (
    GLOBAL_WATCHER, load_autopilot_config, save_autopilot_config,
    install_launch_agent, uninstall_launch_agent, is_launch_agent_installed
)


def _speichere_env(werte: dict) -> None:
    """Schreibt Einstellungen in die .env des Nutzers (config.ENV_PATH, nie ins Programm).

    Nur die übergebenen Schlüssel werden ersetzt; alle anderen Zeilen bleiben stehen.
    """
    env_file = config.ENV_PATH
    env_file.parent.mkdir(parents=True, exist_ok=True)
    zeilen = []
    if env_file.exists():
        try:
            zeilen = env_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            zeilen = []

    offen = dict(werte)
    neu = []
    for zeile in zeilen:
        key = zeile.split("=", 1)[0].strip() if "=" in zeile and not zeile.lstrip().startswith("#") else None
        if key in offen:
            neu.append(f"{key}={offen.pop(key)}")
        else:
            neu.append(zeile)
    for key, val in offen.items():
        neu.append(f"{key}={val}")

    env_file.write_text("\n".join(neu) + "\n", encoding="utf-8")
    os.chmod(env_file, 0o600)  # enthält Zugangscode bzw. Schlüssel


def _aktiviere_ordnung(basis: Path, mit_startkategorien: bool) -> dict:
    """Legt die Grundstruktur an, merkt sich den Basisordner und schaltet den Ablage-Modus ein."""
    ergebnis = lege_grundstruktur_an(basis, mit_startkategorien=mit_startkategorien)
    _speichere_env({"ORDNUNG_BASIS": str(basis), "SORTIER_MODUS": "ablage"})
    config.ORDNUNG_BASIS = str(basis)
    config.SORTIER_MODUS = "ablage"

    # Den Eingang dem Autopiloten als überwachten Ordner mitgeben (startet ihn nicht)
    eingang = str(config.ordnung_pfad("eingang"))
    ap_cfg = load_autopilot_config()
    folders = list(ap_cfg.get("watch_folders", []))
    if eingang not in folders:
        folders.append(eingang)
        save_autopilot_config({"watch_folders": folders})
    return ergebnis


def _speicher_vorschlaege() -> list:
    """Startordner, die im Reiter „Speicherplatz“ als Knöpfe angeboten werden."""
    heim = Path.home()
    kandidaten = [
        ("Benutzerordner", heim),
        ("Downloads", heim / "Downloads"),
        ("Schreibtisch", heim / "Desktop"),
        ("Filme", heim / "Movies"),
        ("Bilder", heim / "Pictures"),
        ("Dokumente", heim / "Documents"),
    ]
    return [{"name": name, "pfad": str(pfad)} for name, pfad in kandidaten if pfad.is_dir()]


def move_to_macos_trash(file_path: Path) -> bool:
    """Verschiebt eine Datei oder einen Ordner in den Papierkorb des Mac.

    Die Umsetzung steht in ``speicher.in_papierkorb()`` — sie meldet auch, wo
    im Papierkorb es gelandet ist, damit „Rückgängig“ es zurückholen kann.
    """
    try:
        if not Path(file_path).exists():
            return True  # schon weg: für den Aufrufer erledigt
    except Exception:
        pass
    return speicher.in_papierkorb(file_path) is not None


PORT = 8765


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Ruhiges Logging im Terminal
        pass

    def do_GET(self):
        port = self.server.server_address[1]

        # Host-Header Prüfung (Schutz gegen DNS-Rebinding)
        host = self.headers.get("Host", "").strip().lower()
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Forbidden: Ungueltiger Host-Header")
            return

        # Origin-Header Prüfung (falls vorhanden, muss es der lokale Server sein)
        origin = self.headers.get("Origin")
        if origin and origin.strip().lower() not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Forbidden: Ungueltiger Origin-Header")
            return

        url = urlparse(self.path)

        if url.path == "/" or url.path == "/index.html":
            template_path = BASE_DIR / "templates" / "index.html"
            if not template_path.exists():
                template_path = BASE_DIR / "index.html"
            if template_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                with open(template_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Template index.html nicht gefunden.")
            return

        if url.path == "/api/progress":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(ANALYSIS_PROGRESS).encode("utf-8"))
            return

        if url.path == "/api/autopilot/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(GLOBAL_WATCHER.status()).encode("utf-8"))
            return

        if url.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "ai_provider": config.AI_PROVIDER,
                "gemini_key_set": bool(config.GEMINI_API_KEY),
                "app_code_set": bool(config.NOTIONARY_ZUGANGSCODE),
                "marketplace_url": config.NOTIONARY_MARKETPLACE_URL,
                "gemini_model": config.GEMINI_MODEL,
                "local_url": config.LOCAL_API_URL,
                "local_model": config.LOCAL_MODEL,
                "ocr_ready": config.OCR_BINARY.exists(),
                "folder_suggestion": str(Path.home() / "Downloads"),
                "ordnung_basis": config.ORDNUNG_BASIS,
                "sortier_modus": config.SORTIER_MODUS,
                "namensstil": config.NAMENSSTIL,
                "ordnung_eingerichtet": bool(config.ordnung_pfad("ablage") and config.ordnung_pfad("ablage").is_dir()),
                "ordnung_eingang": str(config.ordnung_pfad("eingang") or ""),
                "ordnung_ablage": str(config.ordnung_pfad("ablage") or ""),
                "app_version": getattr(config, "APP_VERSION", "1.0.0"),
                "github_repo": getattr(config, "GITHUB_REPO", "pebe1965/Dateien_Aktionen")
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if url.path == "/api/check_update":
            import re
            import urllib.request
            from ai_engine import _get_ssl_context

            current_v = getattr(config, "APP_VERSION", "1.0.0")
            repo = getattr(config, "GITHUB_REPO", "pebe1965/Dateien_Aktionen")

            update_info = {
                "current_version": current_v,
                "latest_version": current_v,
                "update_available": False,
                "release_name": "",
                "release_notes": "",
                "download_url": "",
                "html_url": f"https://github.com/{repo}/releases",
                "direct_update": False,
                "direct_update_reason": ""
            }
            try:
                import updater
                update_info["direct_update"], update_info["direct_update_reason"] = updater.direkt_update_moeglich()
            except Exception:
                pass

            try:
                api_url = f"https://api.github.com/repos/{repo}/releases/latest"
                req = urllib.request.Request(
                    api_url,
                    headers={"User-Agent": "Dateien-Aktionen-MacApp", "Accept": "application/vnd.github.v3+json"}
                )
                ctx = _get_ssl_context()
                with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                    if resp.status == 200:
                        rel = json.loads(resp.read().decode("utf-8"))
                        tag = rel.get("tag_name", "").lstrip("v")
                        update_info["latest_version"] = tag
                        update_info["release_name"] = rel.get("name", f"Version {tag}")
                        update_info["release_notes"] = rel.get("body", "")
                        update_info["html_url"] = rel.get("html_url", update_info["html_url"])

                        # Versionsvergleich (z. B. "1.2.0" > "1.1.4")
                        def vparts(v_str):
                            return [int(x) for x in re.findall(r'\d+', v_str)] or [0]

                        if vparts(tag) > vparts(current_v):
                            update_info["update_available"] = True

                        for asset in rel.get("assets", []):
                            name = asset.get("name", "").lower()
                            if name.endswith(".dmg") or name.endswith(".zip"):
                                update_info["download_url"] = asset.get("browser_download_url", "")
                                break
            except Exception:
                pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(update_info).encode("utf-8"))
            return

        if url.path == "/api/handbuch":
            # Quelle des Handbuchs ist die Markdown-Datei neben dem Programm
            handbuch = BASE_DIR / "Handbuch_Dateien_Aktionen.md"
            try:
                text = handbuch.read_text(encoding="utf-8")
            except OSError:
                text = "# Handbuch\n\nDie Handbuch-Datei wurde nicht gefunden."
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"markdown": text, "version": config.APP_VERSION}).encode("utf-8"))
            return

        if url.path == "/api/sicherung":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            daten = backup.uebersicht()
            daten["launch_agent_installed"] = is_launch_agent_installed()
            self.wfile.write(json.dumps(daten).encode("utf-8"))
            return

        if url.path == "/api/sicherung/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({k: v for k, v in backup.STATUS.items() if k != "abbrechen"}).encode("utf-8"))
            return

        if url.path == "/api/speicher/basis":
            # Zustand des Reiters, ohne zu scannen: Platte, Papierkorb, Vorschläge
            try:
                daten = {
                    "platte": speicher.platte(),
                    "papierkorb": speicher.papierkorb_info(),
                    "vollzugriff": speicher.hat_vollzugriff(),
                    "mindestgroesse_mb": config.SPEICHER_MINDESTGROESSE_MB,
                    "vorschlaege": _speicher_vorschlaege(),
                    "scan": speicher.status(mit_ergebnis=False),
                }
            except speicher.SpeicherFehler as exc:
                self.send_error_response(str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(daten).encode("utf-8"))
            return

        if url.path == "/api/speicher/status":
            query = parse_qs(url.query)
            mit_ergebnis = query.get("ergebnis", ["1"])[0] != "0"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(speicher.status(mit_ergebnis=mit_ergebnis)).encode("utf-8"))
            return

        if url.path == "/api/eingang":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"anzahl": zaehle_eingang()}).encode("utf-8"))
            return

        if url.path == "/api/steuer":
            belege = finde_steuer_belege()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "eingerichtet": bool((config.ORDNUNG_BASIS or "").strip()),
                "basis": config.ORDNUNG_BASIS,
                "jahre": [{"jahr": j, "anzahl": len(belege[j])} for j in sorted(belege, reverse=True)],
                "belege": belege
            }).encode("utf-8"))
            return

        if url.path == "/api/projekte":
            projekte_dir = config.ordnung_pfad("projekte")
            ablage_dir = config.ordnung_pfad("ablage")
            eingerichtet = bool(projekte_dir and projekte_dir.is_dir())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "eingerichtet": eingerichtet,
                "ordner": str(projekte_dir or ""),
                "projekte": liste_projekte() if eingerichtet else [],
                "kategorien": discover_existing_subfolders(ablage_dir) if ablage_dir and ablage_dir.is_dir() else []
            }).encode("utf-8"))
            return

        if url.path == "/api/history":
            manifests = []
            for f in sorted(HISTORY_DIR.glob("manifest_*.json"), reverse=True):
                try:
                    with open(f, "r", encoding="utf-8") as m_file:
                        m_data = json.load(m_file)
                    manifests.append({
                        "filename": f.name,
                        "beschreibung": m_data.get("beschreibung", ""),
                        "date": m_data.get("created_at", "unbekannt")[:19].replace("T", " "),
                        "total_actions": m_data.get("total_actions", 0),
                        # Endgültig Gelöschtes (Reiter „Speicherplatz“) steht im
                        # Protokoll, lässt sich aber nicht zurückholen.
                        "rueckgaengig": m_data.get("rueckgaengig", True),
                        "quelle": m_data.get("quelle", "")
                    })
                except Exception:
                    pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"manifests": manifests}).encode("utf-8"))
            return

        if url.path == "/api/file_preview":
            query = parse_qs(url.query)
            path_str = query.get("path", [""])[0]
            if not path_str:
                self.send_response(400)
                self.end_headers()
                return

            p = Path(path_str).resolve()
            if not p.exists() or not p.is_file():
                self.send_response(404)
                self.end_headers()
                return

            ext = p.suffix.lower()

            # Apple .heic / .heif / .tiff im Browser via macOS sips live als JPEG-Vorschau ausliefern
            if ext in {".heic", ".heif", ".tiff", ".tif"}:
                import tempfile
                tmp_jpg = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_f:
                        tmp_jpg = Path(tmp_f.name)
                    subprocess.run(
                        ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80", "-Z", "1400", str(p), "--out", str(tmp_jpg)],
                        capture_output=True,
                        check=False,
                        timeout=10
                    )
                    if tmp_jpg.exists() and tmp_jpg.stat().st_size > 0:
                        data = tmp_jpg.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "image/jpeg")
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                        return
                except Exception:
                    pass
                finally:
                    if tmp_jpg and tmp_jpg.exists():
                        try:
                            tmp_jpg.unlink()
                        except Exception:
                            pass

            mime_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
                ".ico": "image/x-icon",
                ".heic": "image/heic",
                ".heif": "image/heif",
                ".bmp": "image/bmp",
                ".tiff": "image/tiff",
                ".tif": "image/tiff",
                ".pdf": "application/pdf",
                ".mp3": "audio/mpeg",
                ".m4a": "audio/mp4",
                ".wav": "audio/wav",
                ".flac": "audio/flac",
                ".aac": "audio/aac",
                ".ogg": "audio/ogg",
                ".mp4": "video/mp4",
                ".mov": "video/quicktime",
                ".webm": "video/webm",
                ".m4v": "video/mp4",
                ".txt": "text/plain; charset=utf-8",
                ".md": "text/markdown; charset=utf-8",
                ".json": "application/json",
                ".csv": "text/csv; charset=utf-8",
            }
            content_type = mime_map.get(ext, "application/octet-stream")

            try:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(p.stat().st_size))
                self.end_headers()
                with open(p, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
            except Exception:
                pass
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        port = self.server.server_address[1]

        # 1. Host-Header Prüfung (Schutz gegen DNS-Rebinding)
        host = self.headers.get("Host", "").strip().lower()
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Forbidden: Ungültiger Host-Header"}).encode("utf-8"))
            return

        # 2. Origin-Header Prüfung (falls vorhanden, muss es der lokale Server sein)
        origin = self.headers.get("Origin")
        if origin and origin.strip().lower() not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Forbidden: Ungültiger Origin-Header"}).encode("utf-8"))
            return

        # 3. Content-Type Prüfung (muss application/json sein, außer bei leeren POSTs wie pick_folder)
        content_length = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_length > 0 and content_type != "application/json":
            self.send_response(415)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unsupported Media Type: Content-Type muss application/json sein"}).encode("utf-8"))
            return

        url = urlparse(self.path)
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            params = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError:
            self.send_error_response("Ungültiges JSON im Request-Body.")
            return

        if url.path == "/api/self_update":
            # Update direkt im Programm: neues Release laden, App ersetzen, neu starten
            import updater
            try:
                info = updater.installiere_update()
            except updater.UpdateFehler as exc:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode("utf-8"))
                return
            except Exception as exc:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": f"Update fehlgeschlagen: {exc}"}).encode("utf-8"))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "version": info["version"]}).encode("utf-8"))
            self.wfile.flush()
            updater.starte_neu(info["bundle"])
            return

        if url.path == "/api/pick_folder":
            # Öffnet den nativen macOS Ordnerauswahl-Dialog
            chosen = ""
            try:
                cmd = ["osascript", "-e", 'POSIX path of (choose folder with prompt "Wähle einen Ordner zum Scannen:")']
                res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if res.returncode == 0:
                    chosen = res.stdout.strip().rstrip("/")
            except Exception:
                pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"path": chosen}).encode("utf-8"))
            return

        if url.path == "/api/catalog":
            folder_str = params.get("path", "")
            without_subfolders = bool(params.get("without_subfolders", False))
            try:
                folder = Path(folder_str).expanduser().resolve()
                if not folder.exists() or not folder.is_dir():
                    self.send_error_response("Ordner existiert nicht oder ist kein Verzeichnis.")
                    return
                # Vorab-Prüfung auf Lesezugriff (triggert macOS TCC Prompt falls nötig)
                os.listdir(folder)
            except PermissionError:
                self.send_error_response(
                    "Zugriff verweigert (macOS Datenschutz): Bitte erlauben Sie 'Dateien_Aktionen' Zugriff auf diesen Ordner unter 'Systemeinstellungen > Datenschutz & Sicherheit > Dateien und Ordner' (oder Festplattenvollzugriff)."
                )
                return
            except Exception as e:
                self.send_error_response(f"Ungültiger Pfad: {e}")
                return

            try:
                cat = Catalog(folder)
                cat.scan(compute_hashes=True, detect_similar_images=True, recursive=not without_subfolders)
                summary = cat.summary()

                dups_export = {}
                for h, items in cat.duplicates.items():
                    dups_export[h] = [i.to_dict() for i in items]

                files_export = []
                for i in cat.items:
                    d = i.to_dict()
                    try:
                        d["relative_path"] = str(i.path.relative_to(folder))
                    except Exception:
                        d["relative_path"] = i.filename
                    files_export.append(d)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "summary": summary,
                    "duplicates": dups_export,
                    "similar_images": cat.similar_images,
                    "files": files_export
                }).encode("utf-8"))
            except PermissionError:
                self.send_error_response(
                    "Zugriff verweigert (macOS Datenschutz): Bitte erlauben Sie 'Dateien_Aktionen' Zugriff auf diesen Ordner unter 'Systemeinstellungen > Datenschutz & Sicherheit > Dateien und Ordner'."
                )
            except Exception as e:
                self.send_error_response(f"Fehler beim Scannen: {str(e)}")
            return

        if url.path == "/api/inspect_content":
            file_path = Path(params.get("path", "")).resolve()
            if not file_path.exists():
                self.send_error_response("Datei nicht gefunden.")
                return

            if ist_paket(file_path):
                text, method = ("Programm oder Paket. Es wird als Ganzes behandelt: verschieben, kopieren oder "
                                "in den Papierkorb legen – der Inhalt wird nicht gelesen oder verändert."), "Paket"
            else:
                text, method = extract_content(file_path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "text": text,
                "method": method,
                "char_count": len(text)
            }).encode("utf-8"))
            return

        if url.path == "/api/preview":
            folder_str = params.get("path", "")
            specific_paths = params.get("paths", [])
            prefix = params.get("prefix", None)
            force_refresh = bool(params.get("force_refresh", False))
            without_subfolders = bool(params.get("without_subfolders", False))

            folder = Path(folder_str).expanduser().resolve() if folder_str else BASE_DIR
            if specific_paths and not folder.exists():
                folder = Path(specific_paths[0]).parent

            if not folder.exists() or not folder.is_dir():
                self.send_error_response("Ordner existiert nicht.")
                return

            organizer = Organizer(source_dir=folder, provider=config.AI_PROVIDER)
            plan = organizer.prepare_plan(
                specific_paths=specific_paths if specific_paths else None,
                prefix=prefix if prefix else None,
                use_cache=not force_refresh,
                recursive=not without_subfolders
            )

            plan_data = []
            for p in plan:
                d = p.to_dict()
                # Basis für in der Vorschau geänderte Zielordner: im Ablage-Modus „03 Ablage“
                d["base_dir"] = str(organizer.target_dir)
                # Dateien, die zu einem laufenden Projekt gehören, landen in „02 Projekte“
                if p.analysis.projekt:
                    d["projekt_base"] = str(config.ordnung_pfad("projekte"))
                plan_data.append(d)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "plan": plan_data,
                "ablage_modus": organizer.ablage_modus,
                "skipped_subfolders": 0 if specific_paths else organizer.catalog.skipped_subfolders,
                "ziel": str(organizer.target_dir)
            }).encode("utf-8"))
            return

        if url.path.startswith("/api/sicherung/"):
            aktion = url.path[len("/api/sicherung/"):]
            try:
                if aktion == "speichern":
                    antwort = {"success": True, "auftrag": backup.speichere_auftrag(params)}
                elif aktion == "loeschen":
                    backup.loesche_auftrag(str(params.get("id", "")))
                    antwort = {"success": True}
                elif aktion == "ausfuehren":
                    # Läuft im Hintergrund weiter; die Oberfläche fragt den Fortschritt ab
                    job_id = str(params.get("id", ""))
                    backup.hole_auftrag(job_id)
                    if backup.STATUS["laeuft"]:
                        raise backup.SicherungsFehler("Es läuft bereits eine Sicherung.")
                    import threading
                    threading.Thread(target=backup.fuehre_aus, args=(job_id,), daemon=True).start()
                    antwort = {"success": True, "gestartet": True}
                elif aktion == "abbrechen":
                    backup.STATUS["abbrechen"] = True
                    antwort = {"success": True}
                elif aktion == "versionen":
                    antwort = {"versionen": backup.liste_versionen(str(params.get("id", "")))}
                elif aktion == "inhalt":
                    antwort = {"eintraege": backup.liste_inhalt(
                        str(params.get("id", "")), str(params.get("version", "")), str(params.get("pfad", "")))}
                elif aktion == "wiederherstellen":
                    ziel_ordner = None
                    if params.get("wohin") == "ordner":
                        ziel_ordner = str(params.get("ziel", "")).strip()
                        if not ziel_ordner:
                            res = subprocess.run(
                                ["osascript", "-e", 'POSIX path of (choose folder with prompt "Wohin soll wiederhergestellt werden?")'],
                                capture_output=True, text=True, check=False)
                            ziel_ordner = res.stdout.strip().rstrip("/") if res.returncode == 0 else ""
                        if not ziel_ordner:
                            antwort = {"success": False, "abgebrochen": True}
                            ziel_ordner = None
                    if params.get("wohin") != "ordner" or ziel_ordner:
                        antwort = {"success": True, **backup.stelle_wieder_her(
                            str(params.get("id", "")), str(params.get("version", "")),
                            str(params.get("pfad", "")), ziel_ordner)}
                elif aktion == "nextcloud":
                    # Leeres Passwort-Feld heißt: gespeichertes behalten (die Seite kennt es nicht)
                    nc_url = str(params.get("url", "")).strip().rstrip("/")
                    nc_benutzer = str(params.get("benutzer", "")).strip()
                    nc_pw = str(params.get("passwort") or "") or config.NEXTCLOUD_APP_PASSWORT
                    pruefung = backup.pruefe_nextcloud(nc_url, nc_benutzer, nc_pw) if nc_url else {"verbunden": False, "fehler": ""}
                    if params.get("nur_testen"):
                        antwort = pruefung
                    else:
                        _speichere_env({"NEXTCLOUD_URL": nc_url, "NEXTCLOUD_BENUTZER": nc_benutzer,
                                        "NEXTCLOUD_APP_PASSWORT": nc_pw if nc_url else ""})
                        config.NEXTCLOUD_URL, config.NEXTCLOUD_BENUTZER = nc_url, nc_benutzer
                        config.NEXTCLOUD_APP_PASSWORT = nc_pw if nc_url else ""
                        antwort = {"success": True, **pruefung}
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
            except backup.SicherungsFehler as e:
                self.send_error_response(str(e))
                return
            except Exception as e:
                self.send_error_response(f"Sicherung: {e}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(antwort).encode("utf-8"))
            return

        if url.path == "/api/steuer/sammeln":
            # Zielordner per Finder-Dialog wählen, dann die Belege des Jahres dorthin kopieren
            jahr = str(params.get("jahr", "")).strip()
            ziel_str = str(params.get("ziel", "")).strip()
            if not ziel_str:
                try:
                    cmd = ["osascript", "-e", f'POSIX path of (choose folder with prompt "Wohin sollen die Steuer-Belege {jahr[:4]} kopiert werden?")']
                    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                    ziel_str = res.stdout.strip().rstrip("/") if res.returncode == 0 else ""
                except Exception:
                    ziel_str = ""
            if not ziel_str:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "abgebrochen": True}).encode("utf-8"))
                return
            try:
                ergebnis = sammle_steuer_belege(jahr, Path(ziel_str))
            except ValueError as e:
                self.send_error_response(str(e))
                return
            except Exception as e:
                self.send_error_response(f"Die Belege konnten nicht kopiert werden: {e}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, **ergebnis}).encode("utf-8"))
            return

        if url.path == "/api/assistent/entwurf":
            # KI entwirft die Ablage-Kategorien — angelegt wird hier noch nichts
            from ai_engine import entwirf_ablage
            ablage_dir = config.ordnung_pfad("ablage")
            vorhandene = discover_existing_subfolders(ablage_dir) if ablage_dir and ablage_dir.is_dir() else []
            try:
                entwurf = entwirf_ablage(params.get("antworten") or {}, vorhandene)
            except Exception as e:
                self.send_error_response(f"Der Entwurf ist fehlgeschlagen: {e}")
                return
            entwurf["vorhandene"] = vorhandene
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(entwurf).encode("utf-8"))
            return

        if url.path == "/api/assistent/anlegen":
            from ai_engine import bereinige_ordner
            basis_str = str(params.get("basis", "")).strip() or config.ORDNUNG_BASIS
            if not basis_str or not Path(basis_str).expanduser().is_dir():
                self.send_error_response("Bitte zuerst in den Einstellungen einen vorhandenen Basisordner wählen.")
                return
            try:
                _aktiviere_ordnung(Path(basis_str).expanduser(), False)
                ablage_dir = config.ordnung_pfad("ablage")
                angelegt, vorhanden = [], []
                for roh in (params.get("ordner") or [])[:200]:
                    rel = bereinige_ordner(roh)
                    teile = rel.split("/") if rel else []
                    if not teile or len(teile) > 2 or any(t.startswith((".", "_")) for t in teile):
                        continue
                    pfad = ablage_dir.joinpath(*teile)
                    if pfad.is_dir():
                        vorhanden.append(rel)
                    else:
                        pfad.mkdir(parents=True, exist_ok=True)
                        angelegt.append(rel)
            except PermissionError:
                self.send_error_response("Zugriff verweigert: In diesem Ordner darf das Programm keine Ordner anlegen.")
                return
            except Exception as e:
                self.send_error_response(f"Ordner konnten nicht angelegt werden: {e}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "angelegt": angelegt, "vorhanden": vorhanden}).encode("utf-8"))
            return

        if url.path == "/api/projekte/anlegen":
            try:
                ergebnis = lege_projekt_an(params.get("titel", ""), params.get("termin") or None)
            except ValueError as e:
                self.send_error_response(str(e))
                return
            except Exception as e:
                self.send_error_response(f"Projekt konnte nicht angelegt werden: {e}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, **ergebnis}).encode("utf-8"))
            return

        if url.path == "/api/projekte/abschliessen":
            name = str(params.get("name", ""))
            ziel = str(params.get("ziel", ""))
            try:
                if ziel == "papierkorb":
                    pfad = _projekt_ordner(name)
                    if not move_to_macos_trash(pfad):
                        self.send_error_response("Das Projekt konnte nicht in den Papierkorb gelegt werden.")
                        return
                    ergebnis = {"ziel": "Papierkorb", "manifest": None}
                else:
                    ergebnis = schliesse_projekt_ab(name, ziel, str(params.get("kategorie", "")))
            except ValueError as e:
                self.send_error_response(str(e))
                return
            except Exception as e:
                self.send_error_response(f"Projekt konnte nicht abgeschlossen werden: {e}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, **ergebnis}).encode("utf-8"))
            return

        if url.path == "/api/ordnung/anlegen":
            # Legt „01 Eingang“, „02 Projekte“, „03 Ablage“ und „Archiv“ im gewählten Basisordner an
            basis_str = str(params.get("basis", "")).strip()
            if not basis_str:
                self.send_error_response("Bitte zuerst einen Basisordner wählen.")
                return
            basis = Path(basis_str).expanduser()
            if not basis.is_dir():
                self.send_error_response("Der Basisordner existiert nicht.")
                return
            try:
                ergebnis = _aktiviere_ordnung(basis, bool(params.get("startkategorien", False)))
            except PermissionError:
                self.send_error_response("Zugriff verweigert: In diesem Ordner darf das Programm keine Ordner anlegen.")
                return
            except Exception as e:
                self.send_error_response(f"Ordner konnten nicht angelegt werden: {e}")
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, **ergebnis}).encode("utf-8"))
            return

        if url.path == "/api/batch_move":
            paths = params.get("paths", [])
            target_dir_str = params.get("target_dir", "").strip()
            new_folder_name = params.get("new_folder_name", "").strip()
            copy_mode = params.get("copy_mode", False)

            if not paths:
                self.send_error_response("Keine Dateien zum Verschieben übergeben.")
                return

            if not target_dir_str:
                self.send_error_response("Kein Zielordner angegeben.")
                return

            target_path = Path(target_dir_str).expanduser().resolve()
            if new_folder_name:
                target_path = target_path / new_folder_name

            try:
                target_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.send_error_response(f"Konnte Zielordner nicht erstellen: {e}")
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            manifest_file = HISTORY_DIR / f"manifest_move_{timestamp}.json"
            manifest_entries = []
            moved_items = []
            errors = []

            for p_str in paths:
                src = Path(p_str).resolve()
                paket = ist_paket(src)
                if not src.exists() or not (src.is_file() or paket):
                    continue

                dst = get_unique_target_path(target_path / src.name)
                try:
                    if copy_mode and paket:
                        shutil.copytree(src, dst, symlinks=True)
                    elif copy_mode:
                        shutil.copy2(src, dst)
                    else:
                        shutil.move(src, dst)

                    manifest_entries.append({
                        "source": str(src),
                        "target": str(dst),
                        "copy_mode": copy_mode,
                        "timestamp": datetime.now().isoformat()
                    })
                    moved_items.append({
                        "original_path": str(src),
                        "new_path": str(dst),
                        "filename": dst.name
                    })
                except Exception as e:
                    errors.append(f"{src.name}: {str(e)}")

            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump({
                    "created_at": datetime.now().isoformat(),
                    "total_actions": len(manifest_entries),
                    "action_type": "copy" if copy_mode else "move",
                    "destination_folder": str(target_path),
                    "actions": manifest_entries
                }, f, indent=2, ensure_ascii=False)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "moved_count": len(moved_items),
                "target_dir": str(target_path),
                "manifest": manifest_file.name,
                "moved_items": moved_items,
                "errors": errors
            }).encode("utf-8"))
            return

        if url.path == "/api/execute":
            items = params.get("items", [])
            copy_mode = params.get("copy_mode", False)
            apply_tags = params.get("apply_tags", True)
            if not items:
                self.send_error_response("Keine Dateien zum Ausführen übergeben.")
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            manifest_file = HISTORY_DIR / f"manifest_{timestamp}.json"
            manifest_entries = []

            for it in items:
                src = Path(it["source_path"]).resolve()
                if not src.exists():
                    continue

                # Sicheren Dateinamen erzwingen (verhindert Path-Traversal durch "/" im Namen)
                safe_new_name = Path(it.get("new_name", src.name)).name
                if not safe_new_name:
                    safe_new_name = src.name

                # Editierten Zielordner sicher unterhalb des Basisordners auflösen
                custom_folder = it.get("custom_folder", "").strip().strip("/")
                base_dir_str = it.get("base_dir", "")
                # Steht im Zielfeld noch das erkannte Projekt, geht die Datei nach „02 Projekte“ —
                # wurde es überschrieben, gilt der eingetragene Ordner in der Ablage.
                projekt = (it.get("analysis") or {}).get("projekt")
                if projekt and custom_folder == projekt and it.get("projekt_base"):
                    base_dir_str = it["projekt_base"]
                if custom_folder and base_dir_str:
                    base_target_dir = Path(base_dir_str).resolve()
                    safe_parts = [pt for pt in Path(custom_folder).parts if pt not in ("..", ".", "/", "\\")]
                    target_parent = base_target_dir.joinpath(*safe_parts) if safe_parts else base_target_dir
                else:
                    target_parent = Path(it["target_path"]).resolve().parent

                target_parent.mkdir(parents=True, exist_ok=True)
                desired_dst = target_parent / safe_new_name

                # Kollisionsschutz gegen versehentliches Überschreiben existierender Dateien
                if src == desired_dst:
                    dst = desired_dst
                else:
                    dst = get_unique_target_path(desired_dst)

                if copy_mode:
                    shutil.copy2(src, dst)
                else:
                    if src != dst:
                        shutil.move(src, dst)

                # Native macOS Finder-Tags & Spotlight-Kommentar setzen
                if apply_tags and it.get("analysis"):
                    a = it["analysis"]
                    set_macos_tags_and_comment(dst, tags=tags_fuer_analyse(a), comment=a.get("summary") or "")

                manifest_entries.append({
                    "source": str(src),
                    "target": str(dst),
                    "copy_mode": copy_mode,
                    "timestamp": datetime.now().isoformat()
                })

            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump({
                    "created_at": datetime.now().isoformat(),
                    "total_actions": len(manifest_entries),
                    "actions": manifest_entries
                }, f, indent=2, ensure_ascii=False)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "manifest": manifest_file.name}).encode("utf-8"))
            return

        if url.path == "/api/undo":
            manifest_name = Path(params.get("manifest", "")).name
            if not manifest_name:
                self.send_error_response("Ungültiger Manifest-Name.")
                return
            manifest_path = (HISTORY_DIR / manifest_name).resolve()
            if manifest_path.parent != HISTORY_DIR.resolve():
                self.send_error_response("Zugriff auf Pfad außerhalb des History-Ordners verweigert.")
                return
            try:
                restored = rollback_manifest(manifest_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "restored": restored}).encode("utf-8"))
            except Exception as e:
                self.send_error_response(str(e))
            return

        if url.path == "/api/test_zugang":
            from ai_engine import pruefe_zugangscode
            code = str(params.get("notionary_zugangscode", "")).strip() or config.NOTIONARY_ZUGANGSCODE
            if not code:
                result = {"verbunden": False, "fehler": "Kein Zugangscode eingetragen."}
            else:
                result = pruefe_zugangscode(code)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        if url.path == "/api/save_config":
            # Speichere in .env — im Benutzerordner, nicht im Programm (übersteht Updates)
            prov = params.get("ai_provider", "app")
            g_key = params.get("gemini_api_key", "").strip()
            # Fehlt das Feld (alte Oberfläche), bleibt der gespeicherte Code stehen.
            z_code = params.get("notionary_zugangscode")
            z_code = config.NOTIONARY_ZUGANGSCODE if z_code is None else str(z_code).strip()
            g_mod = params.get("gemini_model", "gemini-2.5-flash").strip()
            l_url = params.get("local_url", "http://localhost:1234/v1/chat/completions").strip()

            # Ordnungssystem: Fehlen die Felder (alte Oberfläche), bleiben die Werte stehen.
            o_basis = params.get("ordnung_basis")
            o_basis = config.ORDNUNG_BASIS if o_basis is None else str(o_basis).strip()
            s_modus = params.get("sortier_modus")
            s_modus = s_modus if s_modus in ("frei", "ablage") else config.SORTIER_MODUS
            n_stil = params.get("namensstil")
            n_stil = n_stil if n_stil in ("schema", "lesbar") else config.NAMENSSTIL

            _speichere_env({
                "AI_PROVIDER": prov,
                "NOTIONARY_ZUGANGSCODE": z_code,
                "GEMINI_API_KEY": g_key or config.GEMINI_API_KEY,
                "GEMINI_MODEL": g_mod or "gemini-2.5-flash",
                "LOCAL_API_URL": l_url or "http://localhost:1234/v1/chat/completions",
                "LOCAL_MODEL": "local-model",
                "ORDNUNG_BASIS": o_basis,
                "SORTIER_MODUS": s_modus,
                "NAMENSSTIL": n_stil,
            })
            config.NAMENSSTIL = n_stil

            # Im laufenden Prozess aktualisieren
            config.ORDNUNG_BASIS = o_basis
            config.SORTIER_MODUS = s_modus
            config.AI_PROVIDER = prov
            config.NOTIONARY_ZUGANGSCODE = z_code
            if g_key:
                config.GEMINI_API_KEY = g_key
            config.GEMINI_MODEL = g_mod
            config.LOCAL_API_URL = l_url

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            return

        if url.path == "/api/reveal_in_finder":
            file_path = Path(params.get("path", "")).resolve()
            if not file_path.exists():
                self.send_error_response("Datei nicht gefunden.")
                return
            try:
                subprocess.run(["open", "-R", str(file_path)], check=False)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self.send_error_response(f"Fehler beim Anzeigen im Finder: {e}")
            return

        if url.path == "/api/open_file":
            file_path = Path(params.get("path", "")).resolve()
            if not file_path.exists():
                self.send_error_response("Datei nicht gefunden.")
                return

            # Aus Sicherheitsgründen keine Programme oder Skripte ausführen
            blocked_exts = {
                ".app", ".command", ".sh", ".bash", ".zsh", ".pkg", ".dmg",
                ".scpt", ".scptd", ".workflow", ".applescript", ".action",
                ".tool", ".bin", ".exe", ".bat", ".cmd"
            }
            if file_path.suffix.lower() in blocked_exts or file_path.name.lower().endswith(".app"):
                self.send_error_response(
                    f"Aus Sicherheitsgründen können Programme und Skripte ({file_path.suffix or '.app'}) nicht geöffnet werden."
                )
                return

            try:
                subprocess.run(["open", str(file_path)], check=False)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self.send_error_response(f"Fehler beim Öffnen: {e}")
            return

        if url.path in ["/api/trash_duplicates", "/api/trash_files"]:
            try:
                paths = params.get("paths", [])
                if not paths:
                    self.send_error_response("Keine Dateien zum Löschen übergeben.")
                    return

                trashed = []
                failed = []
                freed_bytes = 0

                # 1. Dateigrößen vorab erfassen
                file_sizes = {}
                for p_str in paths:
                    try:
                        p = Path(p_str).resolve()
                        if p.exists():
                            if p.is_file():
                                file_sizes[p] = p.stat().st_size
                            else:
                                file_sizes[p] = sum(f.stat().st_size for f in p.glob("**/*") if f.is_file())
                    except Exception:
                        pass

                # 2. Schneller Batch-Lauf über /usr/bin/trash (Apple-eigenes Tool, falls vorhanden)
                existing_candidates = list(file_sizes.keys())
                if existing_candidates and Path("/usr/bin/trash").is_file():
                    try:
                        cmd = ["/usr/bin/trash"] + [str(p) for p in existing_candidates]
                        subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
                    except Exception:
                        pass

                # 3. Status für alle Dateien prüfen bzw. per AppleScript / Fallback nachverschieben
                for p, size in file_sizes.items():
                    if not p.exists():
                        trashed.append(str(p))
                        freed_bytes += size
                    elif move_to_macos_trash(p):
                        trashed.append(str(p))
                        freed_bytes += size
                    else:
                        failed.append(str(p))

                # Dateien, die schon vorab nicht mehr existierten, als trashed verbuchen
                for p_str in paths:
                    p = Path(p_str).resolve()
                    if p not in file_sizes and not p.exists():
                        trashed.append(str(p))

                # Protokoll im Benutzerordner speichern
                log_name = None
                try:
                    log_file = HISTORY_DIR / f"trash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(log_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "timestamp": datetime.now().isoformat(),
                            "trashed_count": len(trashed),
                            "freed_bytes": freed_bytes,
                            "trashed_files": trashed,
                            "failed_files": failed
                        }, f, indent=2, ensure_ascii=False)
                    log_name = log_file.name
                except Exception as e:
                    sys.stderr.write(f"Fehler beim Speichern des Papierkorb-Protokolls: {e}\n")

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True,
                    "trashed_count": len(trashed),
                    "freed_mb": round(freed_bytes / (1024 * 1024), 2),
                    "failed_count": len(failed),
                    "failed_files": failed,
                    "log": log_name
                }).encode("utf-8"))
                return
            except Exception as e:
                sys.stderr.write(f"Fehler in trash_files: {e}\n")
                self.send_error_response(f"Fehler beim Verschieben in den Papierkorb: {str(e)}", status_code=500)
                return

        if url.path == "/api/autopilot/save":
            watch_folders = params.get("watch_folders", [])
            if isinstance(watch_folders, str):
                watch_folders = [f.strip() for f in watch_folders.split("\n") if f.strip()]
            new_cfg = {
                "watch_folders": watch_folders,
                "target_folder": params.get("target_folder", "").strip(),
                "interval_seconds": max(5, int(params.get("interval_seconds", 30))),
                "min_file_age_seconds": max(2, int(params.get("min_file_age_seconds", 10))),
                "copy_mode": bool(params.get("copy_mode", False)),
                "apply_tags": bool(params.get("apply_tags", True)),
                "notifications": bool(params.get("notifications", True)),
            }
            save_autopilot_config(new_cfg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(GLOBAL_WATCHER.status()).encode("utf-8"))
            return

        if url.path == "/api/autopilot/toggle":
            enable = bool(params.get("enabled", False))
            if enable:
                GLOBAL_WATCHER.start()
            else:
                GLOBAL_WATCHER.stop()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(GLOBAL_WATCHER.status()).encode("utf-8"))
            return

        if url.path == "/api/autopilot/scan_now":
            records = GLOBAL_WATCHER.scan_once()
            resp = GLOBAL_WATCHER.status()
            resp["scanned_count"] = len(records)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if url.path == "/api/autopilot/launch_agent":
            install = bool(params.get("install", False))
            res = install_launch_agent() if install else uninstall_launch_agent()
            resp = GLOBAL_WATCHER.status()
            resp["agent_result"] = res
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if url.path == "/api/speicher/scan":
            try:
                antwort = speicher.starte_scan(
                    params.get("path", ""),
                    params.get("mindestgroesse_mb"),
                )
            except speicher.SpeicherFehler as exc:
                self.send_error_response(str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(antwort).encode("utf-8"))
            return

        if url.path == "/api/speicher/abbrechen":
            antwort = speicher.brich_ab()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(antwort).encode("utf-8"))
            return

        if url.path == "/api/speicher/vorschau":
            try:
                antwort = speicher.vorschau(
                    params.get("pfade", []),
                    params.get("modus", "papierkorb"),
                )
            except speicher.SpeicherFehler as exc:
                self.send_error_response(str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(antwort).encode("utf-8"))
            return

        if url.path == "/api/speicher/freigeben":
            try:
                antwort = speicher.freigeben(
                    params.get("pfade", []),
                    params.get("modus", "papierkorb"),
                    bool(params.get("bestaetigt", False)),
                )
            except speicher.SpeicherFehler as exc:
                self.send_error_response(str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(antwort).encode("utf-8"))
            return

        if url.path == "/api/speicher/installer":
            try:
                antwort = speicher.finde_installationsdateien(params.get("ordner") or None)
            except speicher.SpeicherFehler as exc:
                self.send_error_response(str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(antwort).encode("utf-8"))
            return

        if url.path == "/api/speicher/papierkorb_leeren":
            try:
                antwort = speicher.papierkorb_leeren()
            except speicher.SpeicherFehler as exc:
                self.send_error_response(str(exc))
                return
            antwort["papierkorb"] = speicher.papierkorb_info()
            antwort["platte"] = speicher.platte()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(antwort).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def send_error_response(self, message: str, status_code: int = 400):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode("utf-8"))


def laufende_version(port: int):
    """Version der Dateien_Aktionen-Instanz auf dem Port — oder None, wenn dort keine läuft.

    "unbekannt", wenn eine Instanz antwortet, aber (sehr alt) keine Version meldet.
    """
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/status",
            headers={"User-Agent": "Dateien-Aktionen-Ping"}
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if "ai_provider" in data or "app_version" in data:
                    return str(data.get("app_version") or "unbekannt")
    except Exception:
        pass
    return None


def is_server_already_running(port: int) -> bool:
    """Prüft, ob auf dem Port bereits eine Instanz von Dateien_Aktionen läuft."""
    return laufende_version(port) is not None


def beende_alte_instanz(port: int) -> bool:
    """Beendet die Dateien_Aktionen-Instanz, die auf dem Port lauscht.

    Nach einem Update lief sonst die alte Fassung weiter: Die neue sah „läuft
    schon", öffnete nur das Browserfenster und beendete sich. Man landete beim
    alten Server — neue Oberfläche (die wird bei jedem Aufruf frisch gelesen),
    alter Code, und neue Funktionen antworteten mit 404.

    Beendet wird nur, was vorher auf /api/status als Dateien_Aktionen
    geantwortet hat (Aufrufer prüft das), und nur der lauschende Prozess.
    """
    import signal
    import time
    try:
        res = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5
        )
        pids = [int(p) for p in res.stdout.split() if p.strip().isdigit() and int(p) != os.getpid()]
    except Exception:
        pids = []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    for _ in range(30):
        if laufende_version(port) is None:
            return True
        time.sleep(0.1)
    return False


def find_free_port(preferred_ports=(8765, 8766, 8767, 8768)) -> int:
    """Findet einen freien Port, bevorzugt aus der Liste oder vom Betriebssystem."""
    for port in preferred_ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                # Wie der Server selbst (allow_reuse_address): Ein gerade beendeter
                # Vorgänger hält den Port sonst noch kurz fest, und die neue
                # Version wich auf 8766 aus — die Webapp auf 8765 lief ins Leere.
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    # Zufälligen freien Port vom System zuweisen lassen
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def start_gui(open_browser: bool = True):
    eigene = getattr(config, "APP_VERSION", "1.0.0")

    # 1. Läuft dieselbe Version schon: Browser öffnen und bestehende Instanz nutzen.
    #    Läuft eine andere (nach einem Update die alte), wird sie beendet.
    for p in (PORT, 8766, 8767, 8768):
        v = laufende_version(p)
        if v is None:
            continue
        if v == eigene:
            url = f"http://127.0.0.1:{p}"
            print(f"\n============================================================")
            print(f"  ℹ️  Dateien_Aktionen läuft bereits im Hintergrund auf: {url}")
            if open_browser:
                print(f"  Öffne bestehendes Fenster im Browser...")
                webbrowser.open(url)
            print(f"============================================================\n")
            return
        if v != eigene:
            print(f"🔄 Beende ältere Version {v} auf Port {p} (diese Version: {eigene})...")
            if not beende_alte_instanz(p):
                print(f"⚠️ Version {v} auf Port {p} ließ sich nicht beenden.")

    # Falls der Autopilot zuletzt aktiviert war, beim Start direkt im Hintergrund anwerfen
    try:
        if load_autopilot_config().get("enabled", False):
            GLOBAL_WATCHER.start()
    except Exception:
        pass

    # Geplante Sicherungen prüfen, solange die App läuft
    backup.PLANER.start()

    # 2. Freien Port ermitteln (bevorzugt 8765, sonst nächsten freien Port)
    port = find_free_port(preferred_ports=(PORT, 8766, 8767, 8768))
    url = f"http://127.0.0.1:{port}"

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    server.daemon_threads = True

    print(f"\n============================================================")
    print(f"  🚀 Dateien_Aktionen GUI gestartet auf: {url}")
    if open_browser:
        print(f"  Öffne Browser...")
    print(f"  Zum Beenden: Ctrl + C im Terminal drücken")
    print(f"============================================================\n")

    # Browser öffnen (nur wenn nicht im reinen Fenster-/Dienst-Modus)
    if open_browser:
        webbrowser.open(url)

    # SIGTERM sauber behandeln (wenn die native Mac-App beendet wird)
    import signal
    def _sigterm_handler(signum, frame):
        try:
            GLOBAL_WATCHER.stop()
        except Exception:
            pass
        server.server_close()
        sys.exit(0)

    try:
        signal.signal(signal.SIGTERM, _sigterm_handler)
    except Exception:
        pass

    try:
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 Server beendet.")
        try:
            GLOBAL_WATCHER.stop()
        except Exception:
            pass
        server.server_close()


if __name__ == "__main__":
    should_open_browser = "--no-browser" not in sys.argv
    start_gui(open_browser=should_open_browser)
