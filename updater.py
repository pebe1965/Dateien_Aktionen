"""Update direkt im Programm.

Lädt das ZIP des neuesten GitHub-Releases, prüft es, ersetzt damit die
installierte App (z. B. /Applications/Dateien_Aktionen.app) und startet sie neu.

- Nur möglich, wenn das Programm aus einem App-Bundle läuft (nicht aus dem
  Projektordner) und der Ordner der App beschreibbar ist.
- Die Daten des Nutzers liegen in ~/Library/Application Support/Dateien_Aktionen
  und sind davon nicht betroffen.
- Die Verbindung wird immer mit geprüftem Zertifikat aufgebaut — nie ohne
  Prüfung, denn hier wird Programmcode geladen.
"""

from __future__ import annotations

import os
import re
import ssl
import json
import shutil
import tempfile
import threading
import subprocess
import urllib.request
from pathlib import Path

import config

APP_NAME = "Dateien_Aktionen.app"
ZIP_NAME = "Dateien_Aktionen.zip"
_LOCK = threading.Lock()


class UpdateFehler(Exception):
    """Fehler mit einer Meldung, die der Nutzer lesen kann."""


def ssl_kontext_geprueft() -> ssl.SSLContext:
    """SSL-Kontext mit Stammzertifikaten — ohne unsicheren Rückfall.

    Das Python von python.org hat auf macOS keine Zertifikate, solange
    „Install Certificates.command“ nicht ausgeführt wurde. Dann nehmen wir
    certifi (falls installiert) oder die Zertifikate von macOS.
    """
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats().get("x509_ca", 0) > 0:
        return ctx
    kandidaten = []
    try:
        import certifi
        kandidaten.append(certifi.where())
    except Exception:
        pass
    kandidaten += ["/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"]
    for pfad in kandidaten:
        try:
            if os.path.isfile(pfad):
                ctx.load_verify_locations(cafile=pfad)
                if ctx.cert_store_stats().get("x509_ca", 0) > 0:
                    break
        except Exception:
            continue
    return ctx


def app_bundle() -> Path | None:
    """Pfad der laufenden App (…/Dateien_Aktionen.app) oder None im Projektordner."""
    # BASE_DIR = <Bundle>/Contents/Resources/app
    base = Path(config.BASE_DIR).resolve()
    if base.name == "app" and base.parent.name == "Resources" and base.parent.parent.name == "Contents":
        bundle = base.parent.parent.parent
        if bundle.suffix == ".app":
            return bundle
    return None


def direkt_update_moeglich() -> tuple[bool, str]:
    bundle = app_bundle()
    if bundle is None:
        return False, "Das Programm läuft nicht als installierte App (Entwicklungsordner)."
    if not os.access(bundle.parent, os.W_OK) or not os.access(bundle, os.W_OK):
        return False, f"Keine Schreibrechte für „{bundle.parent}“. Bitte das Update über den Download installieren."
    return True, ""


def _vparts(v: str):
    return [int(x) for x in re.findall(r"\d+", v)] or [0]


def _hole_release(ctx) -> dict:
    repo = getattr(config, "GITHUB_REPO", "pebe1965/Dateien_Aktionen")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"User-Agent": "Dateien-Aktionen-Updater", "Accept": "application/vnd.github.v3+json"},
    )
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _plist_version(bundle: Path) -> str:
    try:
        res = subprocess.run(
            ["/usr/libexec/PlistBuddy", "-c", "Print CFBundleShortVersionString",
             str(bundle / "Contents" / "Info.plist")],
            capture_output=True, text=True, timeout=5,
        )
        return res.stdout.strip()
    except Exception:
        return ""


def installiere_update() -> dict:
    """Lädt und installiert das neueste Release. Gibt {"version", "bundle"} zurück."""
    if not _LOCK.acquire(blocking=False):
        raise UpdateFehler("Ein Update läuft bereits.")
    try:
        ok, grund = direkt_update_moeglich()
        if not ok:
            raise UpdateFehler(grund)
        bundle = app_bundle()

        ctx = ssl_kontext_geprueft()
        try:
            rel = _hole_release(ctx)
        except Exception as exc:
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                raise UpdateFehler("Die sichere Verbindung zu GitHub konnte nicht geprüft werden. "
                                   "Bitte das Update über den Download installieren.")
            raise UpdateFehler("GitHub ist nicht erreichbar. Besteht eine Internetverbindung?")

        tag = rel.get("tag_name", "").lstrip("vV")
        aktuell = getattr(config, "APP_VERSION", "0")
        if _vparts(tag) <= _vparts(aktuell):
            raise UpdateFehler(f"Sie verwenden bereits die neueste Version ({aktuell}).")

        zip_url = next((a.get("browser_download_url") for a in rel.get("assets", [])
                        if a.get("name") == ZIP_NAME), None)
        if not zip_url:
            raise UpdateFehler("Im Release fehlt das Update-Paket. Bitte das Update über den Download installieren.")

        # Arbeitsordner neben der App (gleiches Laufwerk → Umbenennen ist atomar)
        with tempfile.TemporaryDirectory(prefix=".da_update_", dir=str(bundle.parent)) as tmp:
            tmp = Path(tmp)
            zip_pfad = tmp / ZIP_NAME
            req = urllib.request.Request(zip_url, headers={"User-Agent": "Dateien-Aktionen-Updater"})
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=120) as resp, open(zip_pfad, "wb") as f:
                    shutil.copyfileobj(resp, f)
            except Exception:
                raise UpdateFehler("Das Update-Paket konnte nicht geladen werden.")

            # ditto behält Ausführungsrechte und Signatur der App
            entpackt = tmp / "neu"
            res = subprocess.run(["/usr/bin/ditto", "-x", "-k", str(zip_pfad), str(entpackt)],
                                 capture_output=True, text=True, timeout=120)
            neue_app = entpackt / APP_NAME
            if res.returncode != 0 or not (neue_app / "Contents" / "Resources" / "app" / "gui.py").is_file() \
                    or not (neue_app / "Contents" / "MacOS" / "launcher").is_file():
                raise UpdateFehler("Das Update-Paket ist unvollständig.")
            neue_version = _plist_version(neue_app)
            if neue_version and _vparts(neue_version) != _vparts(tag):
                raise UpdateFehler(f"Das Update-Paket trägt Version {neue_version} statt {tag}.")
            subprocess.run(["/usr/bin/xattr", "-cr", str(neue_app)], capture_output=True, timeout=30)

            # Austauschen: alte App beiseite, neue an ihre Stelle, alte löschen.
            alt = tmp / "alt.app"
            os.rename(bundle, alt)
            try:
                os.rename(neue_app, bundle)
            except Exception:
                os.rename(alt, bundle)
                raise UpdateFehler("Die neue Version konnte nicht installiert werden. Die bisherige bleibt erhalten.")
            # Der TemporaryDirectory-Block räumt die alte App mit weg.

        return {"version": tag, "bundle": str(bundle)}
    finally:
        _LOCK.release()


def starte_neu(bundle: str):
    """Beendet App und Server und öffnet die (neue) App wieder.

    Läuft als eigenständiger Hintergrundprozess, damit er das Beenden des
    Servers übersteht.
    """
    launcher_pid = ""
    ppid = os.getppid()
    try:
        res = subprocess.run(["ps", "-o", "comm=", "-p", str(ppid)], capture_output=True, text=True, timeout=5)
        if res.stdout.strip().endswith("Contents/MacOS/launcher"):
            launcher_pid = str(ppid)
    except Exception:
        pass

    skript = (
        'sleep 1\n'
        'if [ -n "$1" ]; then kill -TERM "$1" 2>/dev/null; fi\n'
        'kill -TERM "$2" 2>/dev/null\n'
        'i=0; while kill -0 "$2" 2>/dev/null && [ $i -lt 50 ]; do sleep 0.2; i=$((i+1)); done\n'
        'if [ -n "$1" ]; then i=0; while kill -0 "$1" 2>/dev/null && [ $i -lt 50 ]; do sleep 0.2; i=$((i+1)); done; fi\n'
        'sleep 0.5\n'
        'open "$3"\n'
    )
    subprocess.Popen(
        ["/bin/sh", "-c", skript, "neustart", launcher_pid, str(os.getpid()), bundle],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True,
    )
