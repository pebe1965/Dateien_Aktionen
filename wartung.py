"""Gezielte Bereinigung und Deinstallation auf dem Mac."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
import plistlib
import re
import secrets
import sqlite3
import stat
import subprocess
import threading
from pathlib import Path
from xml.parsers.expat import ExpatError

import config
import speicher

_SCHLUESSEL = secrets.token_bytes(32)
_SPERRE = threading.Lock()
_BROWSER = {
    "com.google.Chrome": "Google/Chrome",
    "com.microsoft.edgemac": "Microsoft Edge",
    "com.brave.Browser": "BraveSoftware/Brave-Browser",
    "org.chromium.Chromium": "Chromium",
}


def _direkt(pfad):
    try:
        return pfad.resolve() == pfad
    except (OSError, RuntimeError):
        return False


def _geschuetzt(pfad):
    return any(pfad == ort or pfad in ort.parents or ort in pfad.parents
               for ort, _ in speicher._geschuetzte_eigene_ordner())


def _programme():
    apps = {}
    for eintrag in speicher.installierte_programme():
        pfad = Path(eintrag["pfad"])
        info = pfad / "Contents/Info.plist"
        try:
            if not _direkt(info) or not info.is_file():
                continue
            with info.open("rb") as f:
                daten = plistlib.load(f)
            kennung = daten.get("CFBundleIdentifier", "")
            if (daten.get("CFBundlePackageType") != "APPL" or not isinstance(kennung, str)
                    or not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", kennung)):
                continue
            apps.setdefault(kennung.lower(), []).append((kennung, pfad))
        except (OSError, ValueError, AttributeError, plistlib.InvalidFileException, ExpatError, RuntimeError):
            continue
    return {kennung: liste[0] for kennung, liste in apps.items() if len(liste) == 1
            and not kennung.startswith("com.apple.") and kennung != "de.berthold.dateienaktionen"
            and not _geschuetzt(liste[0][1])}


def _laufende():
    skript = """ObjC.import('AppKit');
    JSON.stringify(ObjC.unwrap($.NSWorkspace.sharedWorkspace.runningApplications)
      .map(a => ObjC.unwrap(a.bundleIdentifier) || '').filter(Boolean))"""
    try:
        res = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", skript],
                             capture_output=True, text=True, timeout=15, check=True)
        ids = json.loads(res.stdout)
        if not ids:
            raise ValueError()
        prozesse = subprocess.run(["/bin/ps", "-axww", "-o", "comm="], check=True,
                                  capture_output=True, text=True, timeout=10)
        if not prozesse.stdout.strip():
            raise ValueError()
        return {i.lower() for i in ids} | {p.strip() for p in prozesse.stdout.splitlines()
                                         if p.strip().startswith("/")}
    except (ValueError, OSError, subprocess.SubprocessError):
        raise speicher.SpeicherFehler("Laufende Programme konnten nicht geprüft werden.")


def _aktiv(kennung, app, laufende):
    return any(i == kennung or i.startswith(kennung + ".") or i.startswith(str(app) + "/")
               for i in laufende)


def _signatur(pfad):
    st = pfad.lstat()
    return (str(pfad), st.st_dev, st.st_ino, st.st_ctime_ns, st.st_size)


def _grafikcache(pfad):
    """Nur vollständige Chromium-Blockdateisätze ohne fremde Einträge."""
    if not _direkt(pfad) or not pfad.is_dir() or _geschuetzt(pfad):
        return None
    teile = []
    namen = set()
    for datei in sorted(pfad.iterdir()):
        st = datei.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            return None
        if datei.name == "index":
            magic = 0xC103CAC3
        elif re.fullmatch(r"data_[0-9]+", datei.name):
            magic = 0xC104CAC3
        else:
            return None
        with datei.open("rb") as f:
            if int.from_bytes(f.read(4), "little") != magic:
                return None
        namen.add(datei.name)
        teile.append(_signatur(datei))
    if {"index", "data_0"} <= namen:
        return teile


def _netzwerkcache(datei):
    """Apples URL-Cache nur als geschlossene, einzeln verschiebbare Datenbank."""
    if not _direkt(datei) or not datei.is_file() or _geschuetzt(datei):
        return False
    if datei.stat().st_nlink != 1 or any(datei.parent.glob("Cache.db-*")):
        return False
    verbindung = None
    try:
        verbindung = sqlite3.connect(datei.as_uri() + "?mode=ro&immutable=1", uri=True)
        tabellen = {name for name, in verbindung.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        pflicht = {"cfurl_cache_response", "cfurl_cache_receiver_data", "cfurl_cache_blob_data"}
        return pflicht <= tabellen <= pflicht | {"cfurl_cache_schema_version", "sqlite_sequence"}
    except sqlite3.Error:
        return False
    finally:
        if verbindung is not None:
            verbindung.close()


def _bestand(pfad):
    """Größe und Fingerabdruck aus Metadaten, auch bei Änderungen tief im Ordner."""
    digest = hashlib.sha256()
    belegt = 0
    inodes = set()
    geraet = pfad.lstat().st_dev
    offen = [pfad]
    while offen:
        teil = offen.pop()
        st = teil.lstat()
        if st.st_dev != geraet:
            raise speicher.SpeicherFehler(f"„{pfad.name}“ enthält ein eingebundenes Laufwerk.")
        digest.update(json.dumps([str(teil), st.st_ino, st.st_ctime_ns, st.st_size]).encode())
        if st.st_ino not in inodes:
            belegt += st.st_blocks * 512
            inodes.add(st.st_ino)
        if stat.S_ISDIR(st.st_mode):
            offen.extend(sorted(teil.iterdir()))
    return belegt, digest.hexdigest()


def _eintrag(pfad, titel, grund, kontext, app, merkmale=()):
    groesse, stand = _bestand(pfad)
    daten = json.dumps([kontext, str(pfad), stand, merkmale]).encode()
    token = hmac.new(_SCHLUESSEL, daten, hashlib.sha256).hexdigest()
    return {"id": token, "kennung": kontext[1].lower(), "programm": str(app),
            "pfad": str(pfad), "titel": titel, "grund": grund, "bytes": groesse, "stand": stand}


def _deinstallierer(app):
    orte = [app / "Contents/Resources", app.parent]
    for ort in orte:
        if not ort.is_dir() or not _direkt(ort):
            continue
        for kandidat in ort.glob("*.app"):
            name = kandidat.stem.casefold()
            if kandidat == app or not _direkt(kandidat):
                continue
            if "uninstall" in name or "deinstall" in name:
                if ort != app.parent or app.stem.casefold() in name or (
                        app.parent not in (Path("/Applications"), speicher.HOME / "Applications")
                        and name in {"uninstall", "uninstaller", "deinstallieren"}):
                    return kandidat
    return None


@contextmanager
def _cache_pruefung(pfad, unlesbar):
    """Ein unzugänglicher Kandidat darf die übrige Suche nicht abbrechen."""
    try:
        yield
    except FileNotFoundError:
        pass  # Ein Cache kann während der Suche verschwinden.
    except (OSError, speicher.SpeicherFehler):
        unlesbar.add(str(pfad))


def _vorschau(modus, app_id):
    apps = _programme()
    if modus == "programme":
        return {"programme": [{"id": key, "name": pfad.stem} for key, (_, pfad)
                              in sorted(apps.items(), key=lambda item: item[1][1].stem.casefold())]}
    laufende = _laufende()
    library = speicher.HOME / "Library"
    zeilen, hinweise = [], []
    if modus == "cache":
        ausgelassen = set()
        unlesbar = set()
        for key, (kennung, app) in apps.items():
            datei = library / "Caches" / kennung / "Cache.db"
            with _cache_pruefung(datei, unlesbar):
                if not datei.is_file():
                    continue
                if _aktiv(key, app, laufende):
                    ausgelassen.add(app.stem)
                elif _netzwerkcache(datei):
                    zeilen.append(_eintrag(datei, app.stem, "Netzwerk-Zwischenspeicher. "
                                           "Die App kann die Inhalte erneut abrufen.", ["cache", key], app))
        for kennung, relativ in _BROWSER.items():
            key = kennung.lower()
            if key not in apps:
                continue
            app = apps[key][1]
            name = app.stem
            basis = library / "Application Support" / relativ
            profile = []
            with _cache_pruefung(basis, unlesbar):
                if not _direkt(basis) or not basis.is_dir():
                    continue
                profile = list(basis.iterdir())
            for profil in profile:
                if not re.fullmatch(r"Default|Profile [0-9]+", profil.name):
                    continue
                pfad = profil / "GPUCache"
                with _cache_pruefung(pfad, unlesbar):
                    if _aktiv(key, app, laufende):
                        if _direkt(pfad) and pfad.is_dir():
                            ausgelassen.add(name)
                        continue
                    teile = _grafikcache(pfad)
                    if teile:
                        zeilen.append(_eintrag(pfad, name + " · " + profil.name,
                                              "Grafik-Zwischenspeicher. Der Browser baut ihn neu auf.",
                                              ["cache", key], app, teile))
        return {"eintraege": zeilen, "hinweise": [], "laufende_programme": sorted(ausgelassen),
                "unlesbare_pfade": sorted(unlesbar)}
    elif modus == "app" and isinstance(app_id, str) and app_id in apps:
        kennung, app = apps[app_id]
        if _aktiv(app_id, app, laufende):
            raise speicher.SpeicherFehler(f"Beende zuerst {app.stem} und seine Hilfsprogramme.")
        deinstaller = _deinstallierer(app)
        if deinstaller:
            return {"eintraege": [], "hinweise": [f"Nutze den Deinstallierer des Herstellers: {deinstaller}"]}
        kontext = ["app", kennung, _signatur(app / "Contents/Info.plist")]
        zeilen.append(_eintrag(app, app.stem, "Installiertes Programm", kontext, app))
        for ordner, suffix, grund in (
            ("Caches", "", "Zwischenspeicher"),
            ("Preferences", ".plist", "Persönliche Einstellungen"),
            ("Saved Application State", ".savedState", "Gesicherter Fensterzustand"),
            ("Logs", "", "Protokolle"),
            ("Application Support", "", "Programmdaten, möglicherweise mit eigenen Projekten"),
            ("Containers", "", "Privater App-Ordner, möglicherweise mit Dokumenten und Konten"),
        ):
            pfad = library / ordner / (kennung + suffix)
            if not _direkt(pfad) or _geschuetzt(pfad):
                continue
            passt = pfad.is_file() if ordner == "Preferences" else pfad.is_dir()
            if passt and pfad.stat().st_uid == os.getuid():
                try:
                    zeilen.append(_eintrag(pfad, pfad.name, grund, kontext, app))
                except (OSError, speicher.SpeicherFehler):
                    hinweise.append(f"Ausgelassen, weil nicht vollständig prüfbar: {pfad}")
    else:
        raise speicher.SpeicherFehler("Bitte wähle das Programm erneut aus.")
    return {"eintraege": zeilen, "hinweise": hinweise}


def bearbeite(params):
    modus = params.get("modus")
    app_id = params.get("app")
    with _SPERRE:
        plan = _vorschau(modus, app_id)
        if "auswahl" not in params:
            return plan
        ids = params["auswahl"]
        erlaubt = {z["id"]: z for z in plan.get("eintraege", [])}
        if (not isinstance(ids, list) or not ids or
                any(not isinstance(i, str) or i not in erlaubt for i in ids)):
            raise speicher.SpeicherFehler("Die Auswahl hat sich geändert. Suche erneut.")
        if modus == "app" and plan["eintraege"][0]["id"] not in ids:
            raise speicher.SpeicherFehler("Wähle das Programm für die Deinstallation aus.")
        auswahl = [z for z in erlaubt.values() if z["id"] in ids]

        def pruefe_eintrag(z):
            pfad = Path(z["pfad"])
            if _aktiv(z["kennung"], z["programm"], _laufende()):
                raise speicher.SpeicherFehler("Das Programm läuft inzwischen.")
            if not _direkt(pfad) or _bestand(pfad)[1] != z["stand"]:
                raise speicher.SpeicherFehler("Der Eintrag hat sich geändert. Suche erneut.")
            if modus == "cache":
                if pfad.name == "GPUCache":
                    merkmale = _grafikcache(pfad)
                    if not merkmale:
                        raise speicher.SpeicherFehler("Der Grafik-Zwischenspeicher hat sich geändert.")
                elif not _netzwerkcache(pfad):
                    raise speicher.SpeicherFehler("Die Netzwerk-Datenbank wird ausgelassen.")

        return speicher.plan_in_papierkorb(auswahl, "Systemreinigung" if modus == "cache"
                                          else "Deinstallation", pruefe_eintrag=pruefe_eintrag)
