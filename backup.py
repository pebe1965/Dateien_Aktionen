"""
Modul: backup.py
Datensicherung von Dateien und Ordnern.

Ein Sicherungsauftrag kopiert eine oder mehrere Quellen an ein Ziel:
- Ordner-Ziel: externe Festplatte, eingebundene NAS-Freigabe oder der Sync-Ordner
  eines Cloud-Dienstes (Google Drive, OneDrive, Nextcloud, iCloud Drive)
- Nextcloud direkt per WebDAV (Adresse, Benutzer und App-Passwort stehen nur in
  der lokalen .env des Nutzers)

Zwei Arten:
- "spiegel": 1:1-Kopie unter „Aktuell“. Geänderte und gelöschte Dateien werden nie
  überschrieben oder entfernt, sondern nach „Frühere Versionen/<Zeitstempel>“ verschoben.
- "zip": je Lauf ein vollständiges ZIP-Archiv; die letzten N Archive bleiben.

Aufgeräumt wird ausschließlich im eigenen, markierten Sicherungsordner.
Alle Daten des Nutzers (Aufträge, Protokoll) liegen in config.DATA_DIR, nie im Programm.
"""

import os
import re
import ssl
import json
import stat
import fcntl
import shutil
import base64
import hashlib
import zipfile
import threading
import subprocess
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import quote, unquote, urlparse
from typing import Any, Dict, List, Optional, Tuple

import config

BACKUP_DIR = config.DATA_DIR / "backup"
JOBS_FILE = BACKUP_DIR / "auftraege.json"
LOG_FILE = BACKUP_DIR / "protokoll.json"
LOCK_FILE = BACKUP_DIR / "lauf.lock"

SICHERUNGS_ORDNER = "Dateien_Aktionen-Sicherung"
MARKER = ".dateien_aktionen_sicherung.json"
TAGS_DATEI = ".dateien_aktionen_tags.json"
AKTUELL = "Aktuell"
FRUEHER = "Frühere Versionen"
STEMPEL = "%Y-%m-%d_%H%M%S"

_JOBS_LOCK = threading.Lock()

# Live-Status für die Oberfläche
STATUS: Dict[str, Any] = {
    "laeuft": False, "auftrag": "", "phase": "", "aktuell": 0, "gesamt": 0, "datei": "", "abbrechen": False
}


class SicherungsFehler(Exception):
    """Fehler mit einer Meldung, die dem Nutzer so angezeigt werden kann."""


class Abgebrochen(Exception):
    pass


# --------------------------------------------------------------------------
# Aufträge speichern und laden
# --------------------------------------------------------------------------

def _lade_json(pfad: Path, standard: Any) -> Any:
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return standard


def _schreibe_json(pfad: Path, daten: Any) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_suffix(pfad.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f, indent=2, ensure_ascii=False)
    os.replace(tmp, pfad)


def lade_auftraege() -> List[Dict[str, Any]]:
    daten = _lade_json(JOBS_FILE, [])
    return daten if isinstance(daten, list) else []


def _speichere_auftraege(auftraege: List[Dict[str, Any]]) -> None:
    _schreibe_json(JOBS_FILE, auftraege)


def hole_auftrag(job_id: str) -> Dict[str, Any]:
    for a in lade_auftraege():
        if a.get("id") == job_id:
            return a
    raise SicherungsFehler("Sicherungsauftrag nicht gefunden.")


def _ordnername(name: str) -> str:
    name = re.sub(r'[/\\:*?"<>|]', " ", str(name or ""))
    return re.sub(r"\s+", " ", name).strip().lstrip("._") or "Sicherung"


def speichere_auftrag(eingabe: Dict[str, Any]) -> Dict[str, Any]:
    """Legt einen Auftrag an oder ändert ihn. Prüft die Eingaben aus der Oberfläche."""
    name = _ordnername(eingabe.get("name"))[:60]

    quellen = []
    for q in eingabe.get("quellen") or []:
        q = str(q).strip()
        if q and q not in quellen:
            quellen.append(str(Path(q).expanduser()))
    if not quellen:
        raise SicherungsFehler("Bitte mindestens einen Ordner oder eine Datei als Quelle wählen.")
    for q in quellen:
        if not Path(q).exists():
            raise SicherungsFehler(f"Die Quelle gibt es nicht: {q}")

    ziel_typ = eingabe.get("ziel_typ") if eingabe.get("ziel_typ") in ("ordner", "nextcloud") else "ordner"
    ziel = str(eingabe.get("ziel") or "").strip()
    if ziel_typ == "ordner":
        if not ziel:
            raise SicherungsFehler("Bitte einen Zielordner wählen.")
        ziel = str(Path(ziel).expanduser())
        for q in quellen:
            if _liegt_in(Path(ziel), Path(q)):
                raise SicherungsFehler("Das Ziel liegt innerhalb einer Quelle – die Sicherung würde sich selbst sichern.")
    else:
        ziel = "/".join(t for t in re.split(r"[/\\]+", ziel) if t and t not in (".", ".."))

    art = eingabe.get("art") if eingabe.get("art") in ("spiegel", "zip") else "spiegel"

    zp = eingabe.get("zeitplan") or {}
    typ = zp.get("typ") if zp.get("typ") in ("manuell", "stuendlich", "taeglich", "woechentlich") else "manuell"
    uhrzeit = str(zp.get("uhrzeit") or "02:00")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", uhrzeit):
        raise SicherungsFehler("Die Uhrzeit muss im Format HH:MM angegeben sein.")
    wochentage = sorted({int(t) for t in (zp.get("wochentage") or []) if str(t).isdigit() and 0 <= int(t) <= 6})
    if typ == "woechentlich" and not wochentage:
        raise SicherungsFehler("Bitte mindestens einen Wochentag wählen.")

    nas_url = str(eingabe.get("nas_url") or "").strip()
    if nas_url and not re.fullmatch(r"(smb|afp)://[^\s\"'\\]+", nas_url):
        raise SicherungsFehler("Die NAS-Adresse muss mit smb:// beginnen, z. B. smb://nas.local/Sicherung.")

    def _zahl(wert: Any, standard: int, minimum: int, maximum: int) -> int:
        try:
            return max(minimum, min(maximum, int(wert)))
        except (TypeError, ValueError):
            return standard

    with _JOBS_LOCK:
        auftraege = lade_auftraege()
        job_id = str(eingabe.get("id") or "")
        alt = next((a for a in auftraege if a.get("id") == job_id), None)
        if any(a.get("name", "").lower() == name.lower() and a.get("id") != job_id for a in auftraege):
            raise SicherungsFehler(f"Einen Auftrag „{name}“ gibt es schon.")
        if alt and alt.get("name") != name and alt.get("letzter_lauf"):
            # Der Name ist der Ordnername im Ziel — nachträgliches Umbenennen würde die Sicherung verwaisen lassen
            raise SicherungsFehler("Der Name lässt sich nach dem ersten Lauf nicht mehr ändern (er ist der Ordnername im Ziel).")

        if alt and alt.get("art") != art and alt.get("letzter_lauf"):
            raise SicherungsFehler("Die Art (Spiegel oder ZIP) lässt sich nach dem ersten Lauf nicht mehr ändern. Lege dafür einen neuen Auftrag an.")

        job = dict(alt) if alt else {
            "id": hashlib.sha1(f"{name}{datetime.now().isoformat()}".encode()).hexdigest()[:10],
            "erstellt": datetime.now().isoformat(timespec="seconds"),
            "letzter_lauf": None, "letzter_versuch": None, "letztes_ergebnis": None,
        }
        job.update({
            "name": name, "quellen": quellen, "ziel_typ": ziel_typ, "ziel": ziel, "art": art,
            "zeitplan": {"typ": typ, "uhrzeit": uhrzeit, "wochentage": wochentage},
            "beim_anschliessen": bool(eingabe.get("beim_anschliessen")) and ziel_typ == "ordner",
            "aufbewahrung_tage": _zahl(eingabe.get("aufbewahrung_tage"), 90, 0, 3650),
            "zip_behalten": _zahl(eingabe.get("zip_behalten"), 5, 1, 365),
            "pruefsumme": bool(eingabe.get("pruefsumme")),
            "nas_url": nas_url if ziel_typ == "ordner" else "",
            "aktiv": eingabe.get("aktiv", True) is not False,
        })
        if alt:
            auftraege[auftraege.index(alt)] = job
        else:
            auftraege.append(job)
        _speichere_auftraege(auftraege)
    return job


def loesche_auftrag(job_id: str) -> None:
    """Entfernt nur den Auftrag. Die bereits gesicherten Dateien im Ziel bleiben unberührt."""
    with _JOBS_LOCK:
        auftraege = [a for a in lade_auftraege() if a.get("id") != job_id]
        _speichere_auftraege(auftraege)
    try:
        (BACKUP_DIR / f"index_{job_id}.json").unlink()
    except OSError:
        pass


def _merke_ergebnis(job_id: str, **felder: Any) -> None:
    with _JOBS_LOCK:
        auftraege = lade_auftraege()
        for a in auftraege:
            if a.get("id") == job_id:
                a.update(felder)
        _speichere_auftraege(auftraege)


def lade_protokoll(limit: int = 50) -> List[Dict[str, Any]]:
    daten = _lade_json(LOG_FILE, [])
    return daten[:limit] if isinstance(daten, list) else []


def _protokolliere(eintrag: Dict[str, Any]) -> None:
    daten = _lade_json(LOG_FILE, [])
    daten = ([eintrag] + daten)[:200] if isinstance(daten, list) else [eintrag]
    _schreibe_json(LOG_FILE, daten)


# --------------------------------------------------------------------------
# Hilfen: Pfade, Quellen, Tags
# --------------------------------------------------------------------------

def _liegt_in(pfad: Path, eltern: Path) -> bool:
    try:
        p, e = pfad.resolve(), eltern.resolve()
    except OSError:
        return False
    return p == e or e in p.parents


def quellnamen(job: Dict[str, Any]) -> Dict[str, Path]:
    """Eindeutiger Name je Quelle (Ordner- bzw. Dateiname; bei Dopplung mit Zähler)."""
    namen: Dict[str, Path] = {}
    for q in job.get("quellen", []):
        pfad = Path(q)
        basis = pfad.name or "Quelle"
        name, n = basis, 2
        while name in namen:
            name = f"{basis} ({n})"
            n += 1
        namen[name] = pfad
    return namen


def _ueberspringen(name: str) -> bool:
    return name in config.IGNORED_FILES or name in (".Trash", ".Trashes", ".fseventsd", ".Spotlight-V100", MARKER)


def _sammle_quellen(job: Dict[str, Any]) -> Tuple[Dict[str, Tuple[Path, int, float]], List[str], List[str]]:
    """Liest alle Quelldateien: rel → (Pfad, Größe, Änderungszeit).

    Gibt außerdem die Namen der Quellen zurück, die erreichbar waren, und Warnungen.
    Eine nicht erreichbare Quelle wird übersprungen — ihre Sicherung bleibt dann unangetastet
    (sonst sähe es aus, als wären alle ihre Dateien gelöscht worden).
    """
    dateien: Dict[str, Tuple[Path, int, float]] = {}
    erreichbar: List[str] = []
    warnungen: List[str] = []
    for name, wurzel in quellnamen(job).items():
        _pruefe_abbruch()
        try:
            if wurzel.is_file():
                st = wurzel.stat()
                dateien[name] = (wurzel, st.st_size, st.st_mtime)
                erreichbar.append(name)
                continue
            if not wurzel.is_dir():
                warnungen.append(f"Quelle nicht erreichbar, übersprungen: {wurzel}")
                continue
            os.listdir(wurzel)
        except OSError as e:
            warnungen.append(f"Quelle nicht lesbar, übersprungen: {wurzel} ({e.strerror or e})")
            continue
        erreichbar.append(name)
        for root, dirs, files in os.walk(wurzel):
            _pruefe_abbruch()
            dirs[:] = sorted(d for d in dirs if not _ueberspringen(d) and not os.path.islink(os.path.join(root, d)))
            for fname in files:
                if _ueberspringen(fname):
                    continue
                voll = Path(root) / fname
                try:
                    st = voll.lstat()
                except OSError:
                    continue
                if not stat.S_ISREG(st.st_mode):
                    continue  # Verknüpfungen und Sonderdateien werden nicht gesichert
                rel = name + "/" + voll.relative_to(wurzel).as_posix()
                dateien[rel] = (voll, st.st_size, st.st_mtime)
    return dateien, erreichbar, warnungen


def _lese_tags(pfad: Path) -> List[str]:
    from organizer import _lese_finder_tags
    import ctypes
    import ctypes.util
    global _LIBC
    try:
        if _LIBC is None:
            _LIBC = ctypes.CDLL(ctypes.util.find_library("c") or "/usr/lib/libSystem.B.dylib")
        return _lese_finder_tags(_LIBC, str(pfad).encode("utf-8"))
    except Exception:
        return []


_LIBC = None


def _hole_icloud_datei(pfad: Path) -> None:
    """Lädt eine nur in iCloud liegende Datei, bevor sie gesichert wird."""
    try:
        if getattr(pfad.lstat(), "st_flags", 0) & 0x40000000 and config.ICLOUD_BINARY.exists():
            subprocess.run([str(config.ICLOUD_BINARY), str(pfad), "120"], capture_output=True, timeout=130)
    except Exception:
        pass


def _sha256(pfad: Path) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _pruefe_abbruch() -> None:
    if STATUS.get("abbrechen"):
        raise Abgebrochen()


def _gleich(a: Tuple[int, float], b: Tuple[int, float]) -> bool:
    """Gleiche Größe und Änderungszeit (2 s Toleranz: exFAT und Netzlaufwerke runden)."""
    return a[0] == b[0] and abs(a[1] - b[1]) <= 2


# --------------------------------------------------------------------------
# Ziel: Ordner (externe Platte, NAS-Freigabe, Cloud-Sync-Ordner)
# --------------------------------------------------------------------------

class OrdnerZiel:
    def __init__(self, job: Dict[str, Any]):
        self.job = job
        self.eltern = Path(job["ziel"])
        self.wurzel = self.eltern / SICHERUNGS_ORDNER / _ordnername(job["name"])

    def beschreibung(self) -> str:
        return str(self.wurzel)

    def verfuegbar(self) -> Tuple[bool, str]:
        teile = self.eltern.parts
        # /Volumes/<Name>: Ist die Platte nicht angeschlossen, darf dort nichts angelegt werden —
        # die Daten landeten sonst unbemerkt auf der internen Platte.
        if len(teile) >= 3 and teile[1] == "Volumes":
            volume = Path("/Volumes") / teile[2]
            if not os.path.ismount(volume):
                return False, f"„{teile[2]}“ ist nicht angeschlossen bzw. nicht verbunden."
        if not self.eltern.is_dir():
            return False, "Der Zielordner ist nicht erreichbar."
        if not os.access(self.eltern, os.W_OK):
            return False, "In den Zielordner kann nicht geschrieben werden."
        return True, ""

    def verbinde(self) -> None:
        """NAS-Freigabe einbinden, falls eine Adresse hinterlegt ist (Anmeldung aus dem Schlüsselbund)."""
        url = self.job.get("nas_url")
        if not url or self.verfuegbar()[0]:
            return
        try:
            subprocess.run(["osascript", "-e", f'mount volume "{url}"'], capture_output=True, timeout=45)
        except Exception:
            pass

    def bereite_vor(self) -> None:
        if self.wurzel.exists():
            marker = _lade_json(self.wurzel / MARKER, None)
            if marker is None:
                if any(self.wurzel.iterdir()):
                    raise SicherungsFehler(
                        f"Im Ziel gibt es schon einen Ordner „{self.wurzel.name}“, der nicht von dieser Sicherung stammt."
                    )
            elif marker.get("id") != self.job["id"]:
                raise SicherungsFehler(
                    f"Der Ordner „{self.wurzel.name}“ im Ziel gehört zu einem anderen Sicherungsauftrag."
                )
        self.wurzel.mkdir(parents=True, exist_ok=True)
        _schreibe_json(self.wurzel / MARKER, {
            "id": self.job["id"], "name": self.job["name"], "art": self.job["art"],
            "hinweis": "Sicherung von Dateien_Aktionen. Diesen Ordner nicht von Hand umbauen."
        })

    def frei(self) -> Optional[int]:
        try:
            return shutil.disk_usage(self.eltern).free
        except OSError:
            return None

    # --- Spiegel ---
    def vorhandene(self) -> Dict[str, Tuple[int, float]]:
        basis = self.wurzel / AKTUELL
        ergebnis: Dict[str, Tuple[int, float]] = {}
        if not basis.is_dir():
            return ergebnis
        for root, dirs, files in os.walk(basis):
            dirs[:] = [d for d in dirs if not _ueberspringen(d)]
            for fname in files:
                if _ueberspringen(fname) or fname.endswith(".da-teil"):
                    continue
                voll = Path(root) / fname
                try:
                    st = voll.stat()
                except OSError:
                    continue
                ergebnis[voll.relative_to(basis).as_posix()] = (st.st_size, st.st_mtime)
        return ergebnis

    def schreibe(self, rel: str, quelle: Path, mtime: float, pruefen: bool) -> None:
        ziel = self.wurzel / AKTUELL / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        teil = ziel.with_name(ziel.name + ".da-teil")
        try:
            shutil.copyfile(quelle, teil)
            if pruefen and _sha256(quelle) != _sha256(teil):
                raise SicherungsFehler("Prüfsumme stimmt nach dem Kopieren nicht überein.")
            os.replace(teil, ziel)
        finally:
            if teil.exists():
                try:
                    teil.unlink()
                except OSError:
                    pass
        try:
            os.utime(ziel, (mtime, mtime))
        except OSError:
            pass  # manche Netzlaufwerke lassen die Änderungszeit nicht setzen

    def archiviere(self, rel: str, stempel: str) -> None:
        quelle = self.wurzel / AKTUELL / rel
        ziel = self.wurzel / FRUEHER / stempel / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        os.replace(quelle, ziel)

    def schreibe_text(self, name: str, text: str) -> None:
        with open(self.wurzel / name, "w", encoding="utf-8") as f:
            f.write(text)

    def raeume_auf(self, tage: int) -> int:
        """Entfernt frühere Versionen, die älter als `tage` sind, und leere Ordner im Spiegel."""
        entfernt = 0
        frueher = self.wurzel / FRUEHER
        if tage > 0 and frueher.is_dir():
            grenze = datetime.now() - timedelta(days=tage)
            for eintrag in frueher.iterdir():
                try:
                    zeit = datetime.strptime(eintrag.name, STEMPEL)
                except ValueError:
                    continue  # nur eigene, datierte Ordner anfassen
                if zeit < grenze and eintrag.is_dir():
                    shutil.rmtree(eintrag, ignore_errors=True)
                    entfernt += 1
        aktuell = self.wurzel / AKTUELL
        if aktuell.is_dir():
            for root, dirs, files in os.walk(aktuell, topdown=False):
                if root != str(aktuell) and not dirs and not [f for f in files if f != ".DS_Store"]:
                    try:
                        for f in files:
                            os.unlink(os.path.join(root, f))
                        os.rmdir(root)
                    except OSError:
                        pass
        return entfernt

    def abschluss(self) -> None:
        pass

    # --- ZIP ---
    def zip_pfad(self, name: str) -> Path:
        return self.wurzel / name

    def lade_zip_hoch(self, lokal: Path, name: str) -> None:
        os.replace(lokal, self.wurzel / name)

    def zip_arbeitsordner(self) -> Path:
        return self.wurzel  # direkt im Ziel schreiben, danach umbenennen

    def liste_zips(self) -> List[str]:
        if not self.wurzel.is_dir():
            return []
        return sorted(p.name for p in self.wurzel.iterdir() if p.is_file() and p.suffix == ".zip")

    def loesche_zip(self, name: str) -> None:
        (self.wurzel / name).unlink()


# --------------------------------------------------------------------------
# Ziel: Nextcloud per WebDAV
# --------------------------------------------------------------------------

def nextcloud_eingerichtet() -> bool:
    return bool(config.NEXTCLOUD_URL and config.NEXTCLOUD_BENUTZER and config.NEXTCLOUD_APP_PASSWORT)


def _ssl_kontext() -> ssl.SSLContext:
    # Bewusst streng: Hier geht ein Passwort über die Leitung. Anders als bei der KI-Anfrage
    # wird die Zertifikatsprüfung nie abgeschaltet.
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


class WebdavZiel:
    def __init__(self, job: Dict[str, Any], url: Optional[str] = None, benutzer: Optional[str] = None,
                 passwort: Optional[str] = None):
        self.job = job
        self.url = (url if url is not None else config.NEXTCLOUD_URL).strip().rstrip("/")
        self.benutzer = (benutzer if benutzer is not None else config.NEXTCLOUD_BENUTZER).strip()
        self.passwort = passwort if passwort is not None else config.NEXTCLOUD_APP_PASSWORT
        teile = [t for t in str(job.get("ziel") or "").split("/") if t]
        self.wurzel_teile = teile + [SICHERUNGS_ORDNER, _ordnername(job.get("name", "Sicherung"))]
        self._ordner_da: set = set()
        self._index_datei = BACKUP_DIR / f"index_{job.get('id', 'test')}.json"
        self._index: Dict[str, List[float]] = {}

    def beschreibung(self) -> str:
        return f"Nextcloud: /{'/'.join(self.wurzel_teile)}"

    def _basis(self) -> str:
        return f"{self.url}/remote.php/dav/files/{quote(self.benutzer, safe='')}"

    def _adresse(self, teile: List[str]) -> str:
        return self._basis() + "/" + "/".join(quote(t, safe="") for t in teile)

    def _anfrage(self, methode: str, teile: List[str], daten: Any = None, kopf: Optional[Dict[str, str]] = None,
                 erlaubt: Tuple[int, ...] = ()) -> Tuple[int, bytes]:
        zugang = base64.b64encode(f"{self.benutzer}:{self.passwort}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(self._adresse(teile), data=daten, method=methode,
                                     headers={"Authorization": f"Basic {zugang}", **(kopf or {})})
        try:
            ctx = _ssl_kontext() if self.url.startswith("https://") else None
            # Kurze Wartezeit für Abfragen, lange für das Hochladen großer Dateien
            with urllib.request.urlopen(req, context=ctx, timeout=600 if methode == "PUT" else 30) as antwort:
                return antwort.status, antwort.read()
        except urllib.error.HTTPError as e:
            if e.code in erlaubt:
                return e.code, b""
            if e.code in (401, 403):
                raise SicherungsFehler("Nextcloud lehnt die Anmeldung ab. Bitte Benutzer und App-Passwort prüfen.")
            if e.code == 507:
                raise SicherungsFehler("Der Speicherplatz in der Nextcloud ist voll.")
            if e.code == 413:
                raise SicherungsFehler("Die Datei ist für diese Nextcloud zu groß (Grenze des Servers).")
            raise SicherungsFehler(f"Nextcloud meldet einen Fehler ({e.code}) bei {methode}.")
        except ssl.SSLError as e:
            raise SicherungsFehler(f"Die sichere Verbindung zur Nextcloud konnte nicht geprüft werden: {e.reason}")
        except (urllib.error.URLError, OSError) as e:
            raise SicherungsFehler(f"Nextcloud ist nicht erreichbar: {getattr(e, 'reason', e)}")

    def verfuegbar(self) -> Tuple[bool, str]:
        if not (self.url and self.benutzer and self.passwort):
            return False, "Nextcloud ist noch nicht eingerichtet (Adresse, Benutzer, App-Passwort)."
        host = urlparse(self.url).hostname or ""
        if not self.url.startswith("https://") and host not in ("localhost", "127.0.0.1"):
            return False, "Die Nextcloud-Adresse muss mit https:// beginnen."
        try:
            self._anfrage("PROPFIND", [], kopf={"Depth": "0"})
        except SicherungsFehler as e:
            return False, str(e)
        return True, ""

    def verbinde(self) -> None:
        pass

    def _lege_ordner_an(self, teile: List[str]) -> None:
        for i in range(1, len(teile) + 1):
            schluessel = "/".join(teile[:i])
            if schluessel in self._ordner_da:
                continue
            self._anfrage("MKCOL", teile[:i], erlaubt=(405,))  # 405 = gibt es schon
            self._ordner_da.add(schluessel)

    def _liste(self, teile: List[str]) -> List[Tuple[str, bool]]:
        """Namen der direkten Einträge eines Ordners: (Name, ist_Ordner)."""
        status, koerper = self._anfrage("PROPFIND", teile, kopf={"Depth": "1"}, erlaubt=(404,))
        if status == 404 or not koerper:
            return []
        eigen = unquote(urlparse(self._adresse(teile)).path).rstrip("/")
        ergebnis = []
        for antwort in ET.fromstring(koerper).iter("{DAV:}response"):
            href = antwort.findtext("{DAV:}href") or ""
            pfad = unquote(urlparse(href).path).rstrip("/")
            if not pfad or pfad == eigen:
                continue
            ergebnis.append((pfad.rsplit("/", 1)[-1], antwort.find(".//{DAV:}collection") is not None))
        return ergebnis

    def bereite_vor(self) -> None:
        self._lege_ordner_an(self.wurzel_teile)
        namen = [n for n, _ in self._liste(self.wurzel_teile)]
        if MARKER not in namen and namen:
            raise SicherungsFehler(
                f"In der Nextcloud gibt es schon einen Ordner „{self.wurzel_teile[-1]}“, der nicht von dieser Sicherung stammt."
            )
        self.schreibe_text(MARKER, json.dumps({"id": self.job["id"], "name": self.job["name"], "art": self.job["art"]}))
        gespeichert = _lade_json(self._index_datei, {})
        # Der Index merkt sich, was hochgeladen wurde — nur gültig für genau dieses Ziel
        if gespeichert.get("ziel") == self.beschreibung() and MARKER in namen:
            self._index = gespeichert.get("dateien", {})

    def frei(self) -> Optional[int]:
        return None

    def vorhandene(self) -> Dict[str, Tuple[int, float]]:
        return {rel: (int(w[0]), float(w[1])) for rel, w in self._index.items()}

    def schreibe(self, rel: str, quelle: Path, mtime: float, pruefen: bool) -> None:
        teile = self.wurzel_teile + [AKTUELL] + rel.split("/")
        self._lege_ordner_an(teile[:-1])
        groesse = quelle.stat().st_size
        with open(quelle, "rb") as f:
            self._anfrage("PUT", teile, daten=f, kopf={
                "Content-Length": str(groesse), "Content-Type": "application/octet-stream",
                "X-OC-Mtime": str(int(mtime))
            })
        self._index[rel] = [groesse, mtime]

    def archiviere(self, rel: str, stempel: str) -> None:
        von = self.wurzel_teile + [AKTUELL] + rel.split("/")
        nach = self.wurzel_teile + [FRUEHER, stempel] + rel.split("/")
        self._lege_ordner_an(nach[:-1])
        self._anfrage("MOVE", von, kopf={"Destination": self._adresse(nach), "Overwrite": "T"}, erlaubt=(404,))
        self._index.pop(rel, None)

    def schreibe_text(self, name: str, text: str) -> None:
        daten = text.encode("utf-8")
        self._anfrage("PUT", self.wurzel_teile + [name], daten=daten,
                      kopf={"Content-Length": str(len(daten)), "Content-Type": "application/json"})

    def raeume_auf(self, tage: int) -> int:
        entfernt = 0
        if tage <= 0:
            return entfernt
        grenze = datetime.now() - timedelta(days=tage)
        for name, ist_ordner in self._liste(self.wurzel_teile + [FRUEHER]):
            try:
                zeit = datetime.strptime(name, STEMPEL)
            except ValueError:
                continue
            if ist_ordner and zeit < grenze:
                self._anfrage("DELETE", self.wurzel_teile + [FRUEHER, name], erlaubt=(404,))
                entfernt += 1
        return entfernt

    def abschluss(self) -> None:
        _schreibe_json(self._index_datei, {"ziel": self.beschreibung(), "dateien": self._index})

    # --- ZIP ---
    def zip_arbeitsordner(self) -> Path:
        ordner = BACKUP_DIR / "tmp"
        ordner.mkdir(parents=True, exist_ok=True)
        return ordner

    def lade_zip_hoch(self, lokal: Path, name: str) -> None:
        try:
            with open(lokal, "rb") as f:
                self._anfrage("PUT", self.wurzel_teile + [name], daten=f, kopf={
                    "Content-Length": str(lokal.stat().st_size), "Content-Type": "application/zip"
                })
        finally:
            try:
                lokal.unlink()
            except OSError:
                pass

    def liste_zips(self) -> List[str]:
        return sorted(n for n, ist_ordner in self._liste(self.wurzel_teile) if not ist_ordner and n.endswith(".zip"))

    def loesche_zip(self, name: str) -> None:
        self._anfrage("DELETE", self.wurzel_teile + [name], erlaubt=(404,))


def pruefe_nextcloud(url: str, benutzer: str, passwort: str) -> Dict[str, Any]:
    """Testet die Verbindung, ohne etwas zu verändern."""
    ziel = WebdavZiel({"ziel": "", "name": "Test", "id": "test"}, url=url, benutzer=benutzer, passwort=passwort)
    ok, meldung = ziel.verfuegbar()
    return {"verbunden": ok, "fehler": meldung}


def _ziel_fuer(job: Dict[str, Any]):
    return WebdavZiel(job) if job.get("ziel_typ") == "nextcloud" else OrdnerZiel(job)


# --------------------------------------------------------------------------
# Sicherung ausführen
# --------------------------------------------------------------------------

def _sichere_spiegel(job: Dict[str, Any], ziel: Any) -> Dict[str, Any]:
    STATUS.update(phase="Lese Quellen", aktuell=0, gesamt=0, datei="")
    quellen, erreichbar, warnungen = _sammle_quellen(job)
    if not erreichbar:
        raise SicherungsFehler("Keine der Quellen ist erreichbar.")

    STATUS.update(phase="Vergleiche mit der Sicherung")
    vorhanden = ziel.vorhandene()
    stempel = datetime.now().strftime(STEMPEL)

    zu_kopieren = [rel for rel, (_p, groesse, mtime) in quellen.items()
                   if rel not in vorhanden or not _gleich((groesse, mtime), vorhanden[rel])]
    # Nur in erreichbaren Quellen nach Gelöschtem suchen
    entfallen = [rel for rel in vorhanden
                 if rel not in quellen and rel.split("/", 1)[0] in erreichbar]
    # Quellen, die es im Auftrag nicht mehr gibt, bleiben im Spiegel stehen (kein stilles Wegräumen)

    bedarf = sum(quellen[rel][1] for rel in zu_kopieren)
    frei = ziel.frei()
    if frei is not None and bedarf > frei:
        raise SicherungsFehler(
            f"Im Ziel ist zu wenig Platz: benötigt {_groesse(bedarf)}, frei {_groesse(frei)}."
        )

    kopiert = geaendert = fehler = 0
    fehlerliste: List[str] = []
    STATUS.update(phase="Kopiere", aktuell=0, gesamt=len(zu_kopieren))
    for rel in sorted(zu_kopieren):
        _pruefe_abbruch()
        pfad, _groesse_alt, mtime = quellen[rel]
        STATUS.update(datei=pfad.name)
        try:
            _hole_icloud_datei(pfad)
            if rel in vorhanden:
                ziel.archiviere(rel, stempel)  # alte Fassung aufbewahren statt überschreiben
                geaendert += 1
            ziel.schreibe(rel, pfad, mtime, bool(job.get("pruefsumme")))
            kopiert += 1
        except SicherungsFehler as e:
            if "voll" in str(e) or "Anmeldung" in str(e) or "nicht erreichbar" in str(e):
                raise
            fehler += 1
            fehlerliste.append(f"{rel}: {e}")
        except OSError as e:
            if e.errno == 28:
                raise SicherungsFehler("Das Ziel ist voll.")
            fehler += 1
            fehlerliste.append(f"{rel}: {e.strerror or e}")
        STATUS["aktuell"] += 1

    STATUS.update(phase="Räume auf", datei="")
    verschoben = 0
    for rel in sorted(entfallen):
        _pruefe_abbruch()
        try:
            ziel.archiviere(rel, stempel)
            verschoben += 1
        except (OSError, SicherungsFehler) as e:
            fehler += 1
            fehlerliste.append(f"{rel}: {e}")

    # Finder-Tags sichern: Viele Platten, Freigaben und Cloud-Ordner speichern sie nicht mit
    tags = {}
    for rel, (pfad, _g, _m) in quellen.items():
        t = _lese_tags(pfad)
        if t:
            tags[rel] = t
    try:
        ziel.schreibe_text(TAGS_DATEI, json.dumps(tags, ensure_ascii=False))
    except (OSError, SicherungsFehler):
        warnungen.append("Die Finder-Tags konnten nicht mitgesichert werden.")

    aufgeraeumt = ziel.raeume_auf(int(job.get("aufbewahrung_tage") or 0))
    ziel.abschluss()
    return {
        "dateien": len(quellen), "kopiert": kopiert, "geaendert": geaendert, "entfernt_verschoben": verschoben,
        "alte_versionen_geloescht": aufgeraeumt, "fehler": fehler, "fehlerliste": fehlerliste[:20],
        "warnungen": warnungen, "groesse": bedarf
    }


def _sichere_zip(job: Dict[str, Any], ziel: Any) -> Dict[str, Any]:
    STATUS.update(phase="Lese Quellen", aktuell=0, gesamt=0, datei="")
    quellen, erreichbar, warnungen = _sammle_quellen(job)
    if not erreichbar:
        raise SicherungsFehler("Keine der Quellen ist erreichbar.")
    if len(erreichbar) < len(quellnamen(job)):
        raise SicherungsFehler("Nicht alle Quellen sind erreichbar – ein unvollständiges Archiv wird nicht angelegt.")

    # Hat sich seit dem letzten Archiv nichts geändert, entsteht kein neues
    h = hashlib.sha1()
    for rel in sorted(quellen):
        h.update(f"{rel}|{quellen[rel][1]}|{int(quellen[rel][2])}\n".encode("utf-8"))
    signatur = h.hexdigest()
    if job.get("zip_signatur") == signatur and ziel.liste_zips():
        return {"dateien": len(quellen), "kopiert": 0, "unveraendert": True, "fehler": 0, "fehlerliste": [],
                "warnungen": warnungen, "groesse": 0}

    bedarf = sum(g for _p, g, _m in quellen.values())
    frei = ziel.frei()
    if frei is not None and bedarf > frei:
        raise SicherungsFehler(f"Im Ziel ist zu wenig Platz: benötigt bis zu {_groesse(bedarf)}, frei {_groesse(frei)}.")

    name = f"{_ordnername(job['name'])}_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.zip"
    teil = ziel.zip_arbeitsordner() / f".{name}.da-teil"
    fehler = 0
    fehlerliste: List[str] = []
    tags: Dict[str, List[str]] = {}
    STATUS.update(phase="Packe ZIP-Archiv", aktuell=0, gesamt=len(quellen))
    try:
        with zipfile.ZipFile(teil, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archiv:
            for rel in sorted(quellen):
                _pruefe_abbruch()
                pfad = quellen[rel][0]
                STATUS.update(datei=pfad.name)
                try:
                    _hole_icloud_datei(pfad)
                    archiv.write(pfad, rel)
                    t = _lese_tags(pfad)
                    if t:
                        tags[rel] = t
                except OSError as e:
                    if e.errno == 28:
                        raise SicherungsFehler("Das Ziel ist voll.")
                    fehler += 1
                    fehlerliste.append(f"{rel}: {e.strerror or e}")
                STATUS["aktuell"] += 1
            archiv.writestr(TAGS_DATEI, json.dumps(tags, ensure_ascii=False))
        if job.get("pruefsumme"):
            STATUS.update(phase="Prüfe ZIP-Archiv", datei="")
            with zipfile.ZipFile(teil) as archiv:
                defekt = archiv.testzip()
                if defekt:
                    raise SicherungsFehler(f"Das Archiv ist beschädigt (ab Datei {defekt}).")
        groesse = teil.stat().st_size
        STATUS.update(phase="Übertrage Archiv", datei=name)
        ziel.lade_zip_hoch(teil, name)
    finally:
        if teil.exists():
            try:
                teil.unlink()
            except OSError:
                pass

    # Nur die letzten N Archive behalten
    behalten = max(1, int(job.get("zip_behalten") or 5))
    geloescht = 0
    eigene = [z for z in ziel.liste_zips() if z.startswith(_ordnername(job["name"]) + "_")]
    for alt in eigene[:-behalten]:
        try:
            ziel.loesche_zip(alt)
            geloescht += 1
        except (OSError, SicherungsFehler):
            pass
    ziel.abschluss()
    _merke_ergebnis(job["id"], zip_signatur=signatur)
    return {"dateien": len(quellen), "kopiert": len(quellen) - fehler, "archiv": name, "groesse": groesse,
            "alte_archive_geloescht": geloescht, "fehler": fehler, "fehlerliste": fehlerliste[:20], "warnungen": warnungen}


def _groesse(b: float) -> str:
    for einheit in ("Bytes", "KB", "MB", "GB", "TB"):
        if b < 1024 or einheit == "TB":
            return f"{b:.0f} {einheit}" if einheit in ("Bytes", "KB") else f"{b:.1f} {einheit}".replace(".", ",")
        b /= 1024
    return ""


def fuehre_aus(job_id: str, ausloeser: str = "manuell", melden: bool = True) -> Dict[str, Any]:
    """Führt einen Sicherungsauftrag aus. Es läuft immer nur eine Sicherung gleichzeitig —
    auch über Programmgrenzen hinweg (App und Hintergrunddienst teilen sich die Sperre)."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    sperre = open(LOCK_FILE, "w")
    try:
        try:
            fcntl.flock(sperre, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return {"ok": False, "uebersprungen": True, "meldung": "Es läuft bereits eine Sicherung."}

        job = hole_auftrag(job_id)
        start = datetime.now()
        STATUS.update(laeuft=True, auftrag=job["name"], phase="Verbinde", aktuell=0, gesamt=0, datei="", abbrechen=False)
        ergebnis: Dict[str, Any] = {}
        ok, meldung = False, ""
        try:
            ziel = _ziel_fuer(job)
            ziel.verbinde()
            erreichbar, grund = ziel.verfuegbar()
            if not erreichbar:
                raise SicherungsFehler(grund)
            ziel.bereite_vor()
            ergebnis = _sichere_zip(job, ziel) if job["art"] == "zip" else _sichere_spiegel(job, ziel)
            ok = ergebnis.get("fehler", 0) == 0
            if ergebnis.get("unveraendert"):
                meldung = "Keine Änderungen seit dem letzten Archiv."
            elif job["art"] == "zip":
                meldung = f"Archiv mit {ergebnis['kopiert']} Dateien angelegt ({_groesse(ergebnis['groesse'])})."
            else:
                meldung = (f"{ergebnis['kopiert']} Dateien gesichert, {ergebnis['dateien'] - ergebnis['kopiert']} unverändert"
                           + (f", {ergebnis['entfernt_verschoben']} Gelöschte aufbewahrt" if ergebnis["entfernt_verschoben"] else "") + ".")
            if ergebnis.get("fehler"):
                meldung += f" {ergebnis['fehler']} Datei(en) konnten nicht gesichert werden."
            nicht_da = [w for w in ergebnis.get("warnungen", []) if w.startswith("Quelle nicht")]
            if nicht_da:
                # Unvollständig: gilt nicht als erledigt, damit der Zeitplan es erneut versucht
                ok = False
                meldung += f" {len(nicht_da)} Quelle(n) waren nicht erreichbar und wurden ausgelassen."
        except Abgebrochen:
            meldung = "Die Sicherung wurde abgebrochen."
        except SicherungsFehler as e:
            meldung = str(e)
        except Exception as e:  # nichts Unerwartetes darf den Dienst beenden
            meldung = f"Unerwarteter Fehler: {e}"
        finally:
            STATUS.update(laeuft=False, phase="", datei="", abbrechen=False)

        jetzt = datetime.now().isoformat(timespec="seconds")
        felder: Dict[str, Any] = {"letzter_versuch": jetzt, "letztes_ergebnis": {"ok": ok, "meldung": meldung, "zeit": jetzt}}
        if ok:
            felder["letzter_lauf"] = jetzt
        _merke_ergebnis(job_id, **felder)
        _protokolliere({
            "zeit": jetzt, "auftrag": job["name"], "auftrag_id": job_id, "ausloeser": ausloeser, "ok": ok,
            "meldung": meldung, "dauer_sekunden": round((datetime.now() - start).total_seconds(), 1),
            "fehlerliste": ergebnis.get("fehlerliste", []), "warnungen": ergebnis.get("warnungen", []),
        })
        # Wiederholt sich bei geplanten Läufen derselbe Fehler, nicht jedes Mal erneut melden
        vorher = (job.get("letztes_ergebnis") or {}).get("meldung")
        if melden and not (ausloeser != "manuell" and not ok and vorher == meldung):
            try:
                from watcher import send_macos_notification
                send_macos_notification("Dateien_Aktionen Sicherung", meldung,
                                        subtitle=f"{job['name']} – {'erledigt' if ok else 'nicht abgeschlossen'}")
            except Exception:
                pass
        return {"ok": ok, "meldung": meldung, **ergebnis}
    finally:
        try:
            fcntl.flock(sperre, fcntl.LOCK_UN)
        except OSError:
            pass
        sperre.close()


# --------------------------------------------------------------------------
# Zeitplan
# --------------------------------------------------------------------------

def _zeit(text: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def letzter_solltermin(job: Dict[str, Any], jetzt: datetime) -> Optional[datetime]:
    """Der jüngste geplante Termin, der schon erreicht ist (None bei „manuell“)."""
    zp = job.get("zeitplan") or {}
    typ = zp.get("typ")
    if typ == "stuendlich":
        return jetzt.replace(minute=0, second=0, microsecond=0)
    if typ not in ("taeglich", "woechentlich"):
        return None
    stunde, minute = (int(x) for x in str(zp.get("uhrzeit") or "02:00").split(":"))
    kandidat = jetzt.replace(hour=stunde, minute=minute, second=0, microsecond=0)
    for _ in range(8):
        if kandidat <= jetzt and (typ == "taeglich" or kandidat.weekday() in (zp.get("wochentage") or [])):
            return kandidat
        kandidat -= timedelta(days=1)
    return None


def naechster_termin(job: Dict[str, Any], jetzt: Optional[datetime] = None) -> Optional[str]:
    jetzt = jetzt or datetime.now()
    zp = job.get("zeitplan") or {}
    typ = zp.get("typ")
    if not job.get("aktiv", True) or typ not in ("stuendlich", "taeglich", "woechentlich"):
        return None
    if ist_faellig(job, jetzt):
        return "jetzt fällig"
    if typ == "stuendlich":
        return (jetzt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).isoformat(timespec="minutes")
    stunde, minute = (int(x) for x in str(zp.get("uhrzeit") or "02:00").split(":"))
    kandidat = jetzt.replace(hour=stunde, minute=minute, second=0, microsecond=0)
    for _ in range(8):
        if kandidat > jetzt and (typ == "taeglich" or kandidat.weekday() in (zp.get("wochentage") or [])):
            return kandidat.isoformat(timespec="minutes")
        kandidat += timedelta(days=1)
    return None


def ist_faellig(job: Dict[str, Any], jetzt: datetime) -> bool:
    """Fällig, wenn seit dem letzten erfolgreichen Lauf ein geplanter Termin verstrichen ist.
    Verpasste Termine (Mac aus, Platte nicht da) werden so beim nächsten Mal nachgeholt."""
    if not job.get("aktiv", True):
        return False
    soll = letzter_solltermin(job, jetzt)
    if soll is None:
        return False
    bezug = _zeit(job.get("letzter_lauf")) or _zeit(job.get("erstellt")) or jetzt
    return bezug < soll


_ZIEL_WAR_DA: Dict[str, bool] = {}


def pruefe_zeitplan(jetzt: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Ein Takt des Planers: startet fällige Aufträge. Wird von der App und vom Hintergrunddienst aufgerufen."""
    jetzt = jetzt or datetime.now()
    gelaufen = []
    for job in lade_auftraege():
        if not job.get("aktiv", True):
            continue
        job_id = job["id"]
        faellig = ist_faellig(job, jetzt)
        ausloeser = "Zeitplan"

        if job.get("ziel_typ") == "ordner" and job.get("beim_anschliessen"):
            da = OrdnerZiel(job).verfuegbar()[0]
            war_da = _ZIEL_WAR_DA.get(job_id)
            _ZIEL_WAR_DA[job_id] = da
            letzter = _zeit(job.get("letzter_lauf"))
            # Gerade angeschlossen (beim ersten Takt nach dem Start zählt „da“ nicht als neu)
            if da and war_da is False and (not letzter or jetzt - letzter > timedelta(hours=1)):
                faellig, ausloeser = True, "Laufwerk angeschlossen"

        if not faellig:
            continue
        # Nach einem Fehlversuch (Ziel nicht da) nicht jede Minute erneut probieren
        versuch = _zeit(job.get("letzter_versuch"))
        if versuch and jetzt - versuch < timedelta(minutes=15) and ausloeser == "Zeitplan":
            continue
        # Ist das Ziel nicht erreichbar, still warten — ohne Mitteilung bei jedem Takt
        ziel = _ziel_fuer(job)
        if job.get("ziel_typ") == "ordner" and not job.get("nas_url") and not ziel.verfuegbar()[0]:
            _merke_ergebnis(job_id, letzter_versuch=jetzt.isoformat(timespec="seconds"), letztes_ergebnis={
                "ok": False, "meldung": "Wartet: " + ziel.verfuegbar()[1], "zeit": jetzt.isoformat(timespec="seconds")})
            continue
        ergebnis = fuehre_aus(job_id, ausloeser=ausloeser)
        if not ergebnis.get("uebersprungen"):
            gelaufen.append({"auftrag": job["name"], **ergebnis})
    return gelaufen


class Planer:
    """Prüft im Hintergrund der App einmal pro Minute, ob eine Sicherung fällig ist."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._schleife, name="SicherungsPlaner", daemon=True)
        self._thread.start()

    def _schleife(self) -> None:
        self._stop.wait(20)
        while not self._stop.is_set():
            try:
                pruefe_zeitplan()
            except Exception as e:
                print(f"[Sicherung] Planer-Fehler: {e}")
            self._stop.wait(60)


PLANER = Planer()


# --------------------------------------------------------------------------
# Wiederherstellen (Ordner-Ziele)
# --------------------------------------------------------------------------

def _rel_teile(pfad: str) -> List[str]:
    return [t for t in re.split(r"[/\\]+", str(pfad or "")) if t and t not in (".", "..")]


def _ordnerziel(job: Dict[str, Any]) -> OrdnerZiel:
    if job.get("ziel_typ") != "ordner":
        raise SicherungsFehler("Sicherungen in der Nextcloud stellst du direkt in der Nextcloud wieder her – die Dateien liegen dort unverändert.")
    ziel = OrdnerZiel(job)
    ziel.verbinde()
    ok, grund = ziel.verfuegbar()
    if not ok:
        raise SicherungsFehler(grund)
    if not ziel.wurzel.is_dir():
        raise SicherungsFehler("Für diesen Auftrag gibt es im Ziel noch keine Sicherung.")
    return ziel


def liste_versionen(job_id: str) -> List[Dict[str, str]]:
    job = hole_auftrag(job_id)
    ziel = _ordnerziel(job)
    if job["art"] == "zip":
        return [{"id": z, "titel": z} for z in reversed(ziel.liste_zips())]
    versionen = [{"id": "aktuell", "titel": "Aktueller Stand"}]
    frueher = ziel.wurzel / FRUEHER
    if frueher.is_dir():
        for name in sorted((p.name for p in frueher.iterdir() if p.is_dir()), reverse=True):
            try:
                zeit = datetime.strptime(name, STEMPEL)
            except ValueError:
                continue
            versionen.append({"id": name, "titel": f"Ersetzt oder gelöscht am {zeit.strftime('%d.%m.%Y %H:%M')}"})
    return versionen


def _versionsordner(ziel: OrdnerZiel, version: str) -> Path:
    if version == "aktuell":
        return ziel.wurzel / AKTUELL
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{6}", version):
        raise SicherungsFehler("Unbekannte Version.")
    return ziel.wurzel / FRUEHER / version


def _zip_datei(ziel: OrdnerZiel, version: str) -> Path:
    if Path(version).name != version or not version.endswith(".zip") or version not in ziel.liste_zips():
        raise SicherungsFehler("Unbekanntes Archiv.")
    return ziel.wurzel / version


def liste_inhalt(job_id: str, version: str, pfad: str = "") -> List[Dict[str, Any]]:
    """Inhalt eines Ordners in der Sicherung (eine Ebene)."""
    job = hole_auftrag(job_id)
    ziel = _ordnerziel(job)
    teile = _rel_teile(pfad)
    eintraege: Dict[str, Dict[str, Any]] = {}

    if job["art"] == "zip":
        praefix = "/".join(teile) + "/" if teile else ""
        with zipfile.ZipFile(_zip_datei(ziel, version)) as archiv:
            for info in archiv.infolist():
                if info.filename == TAGS_DATEI or not info.filename.startswith(praefix):
                    continue
                rest = info.filename[len(praefix):]
                if not rest:
                    continue
                name, _, tiefer = rest.partition("/")
                if tiefer or info.is_dir():
                    eintraege.setdefault(name, {"name": name, "ordner": True, "groesse": 0})
                else:
                    eintraege[name] = {"name": name, "ordner": False, "groesse": info.file_size}
    else:
        ordner = _versionsordner(ziel, version).joinpath(*teile)
        if not ordner.is_dir():
            return []
        for p in ordner.iterdir():
            if _ueberspringen(p.name) or p.name.endswith(".da-teil"):
                continue
            try:
                eintraege[p.name] = {"name": p.name, "ordner": p.is_dir(), "groesse": 0 if p.is_dir() else p.stat().st_size}
            except OSError:
                continue
    return sorted(eintraege.values(), key=lambda e: (not e["ordner"], e["name"].lower()))


def stelle_wieder_her(job_id: str, version: str, pfad: str = "", ziel_ordner: Optional[str] = None) -> Dict[str, Any]:
    """Holt eine Datei oder einen Ordner aus der Sicherung zurück.

    Ohne `ziel_ordner` an den ursprünglichen Ort. Vorhandene Dateien werden nie überschrieben —
    die wiederhergestellte Datei bekommt dann einen Zähler im Namen. Schreibt ein Manifest für „Rückgängig“.
    """
    from organizer import get_unique_target_path, set_macos_tags_and_comment, HISTORY_DIR

    job = hole_auftrag(job_id)
    ziel = _ordnerziel(job)
    teile = _rel_teile(pfad)
    praefix = "/".join(teile)
    namen = quellnamen(job)

    def _zielpfad(rel: str) -> Optional[Path]:
        if ziel_ordner:
            # In einen gewählten Ordner: ab dem gewählten Eintrag, Struktur darunter bleibt erhalten
            basis_teile = teile[:-1] if teile else []
            rest = rel.split("/")[len(basis_teile):]
            return Path(ziel_ordner).expanduser().joinpath(*rest)
        wurzelname, _, rest = rel.partition("/")
        quelle = namen.get(wurzelname)
        if quelle is None:
            return None
        return quelle.joinpath(*rest.split("/")) if rest else quelle

    if ziel_ordner and not Path(ziel_ordner).expanduser().is_dir():
        raise SicherungsFehler("Der gewählte Ordner existiert nicht.")

    jetzt = datetime.now()
    eintraege: List[Dict[str, Any]] = []
    uebersprungen = 0

    def _fertig(rel: str, dst: Path, tags: Dict[str, List[str]]) -> None:
        if tags.get(rel):
            set_macos_tags_and_comment(dst, tags=[t.split("\n")[0] for t in tags[rel]])
        eintraege.append({"source": f"Sicherung: {rel}", "target": str(dst), "copy_mode": True, "timestamp": jetzt.isoformat()})

    STATUS.update(laeuft=True, auftrag=job["name"], phase="Stelle wieder her", aktuell=0, gesamt=0, datei="", abbrechen=False)
    try:
        if job["art"] == "zip":
            with zipfile.ZipFile(_zip_datei(ziel, version)) as archiv:
                try:
                    tags = json.loads(archiv.read(TAGS_DATEI).decode("utf-8"))
                except Exception:
                    tags = {}
                for info in archiv.infolist():
                    rel = "/".join(_rel_teile(info.filename))
                    if info.is_dir() or not rel or info.filename == TAGS_DATEI:
                        continue
                    if praefix and not (rel == praefix or rel.startswith(praefix + "/")):
                        continue
                    _pruefe_abbruch()
                    dst = _zielpfad(rel)
                    if dst is None:
                        uebersprungen += 1
                        continue
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst = get_unique_target_path(dst)
                    with archiv.open(info) as quelle, open(dst, "wb") as f:
                        shutil.copyfileobj(quelle, f)
                    try:
                        zeit = datetime(*info.date_time).timestamp()
                        os.utime(dst, (zeit, zeit))
                    except (OSError, ValueError):
                        pass
                    _fertig(rel, dst, tags)
        else:
            basis = _versionsordner(ziel, version)
            tags = _lade_json(ziel.wurzel / TAGS_DATEI, {}) if version == "aktuell" else {}
            start = basis.joinpath(*teile)
            if not start.exists():
                raise SicherungsFehler("Diesen Eintrag gibt es in der Sicherung nicht.")
            dateien = [start] if start.is_file() else [
                Path(r) / f for r, d, fs in os.walk(start) for f in fs if not _ueberspringen(f) and not f.endswith(".da-teil")
            ]
            STATUS["gesamt"] = len(dateien)
            for quelle in sorted(dateien):
                _pruefe_abbruch()
                rel = quelle.relative_to(basis).as_posix()
                dst = _zielpfad(rel)
                if dst is None:
                    uebersprungen += 1
                    continue
                STATUS.update(datei=quelle.name)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst = get_unique_target_path(dst)
                shutil.copy2(quelle, dst)
                _fertig(rel, dst, tags)
                STATUS["aktuell"] += 1
    except Abgebrochen:
        pass
    finally:
        STATUS.update(laeuft=False, phase="", datei="", abbrechen=False)

    manifest = None
    if eintraege:
        manifest_datei = HISTORY_DIR / f"manifest_{jetzt.strftime('%Y%m%d_%H%M%S')}.json"
        with open(manifest_datei, "w", encoding="utf-8") as f:
            json.dump({
                "created_at": jetzt.isoformat(), "total_actions": len(eintraege),
                "beschreibung": f"Aus Sicherung „{job['name']}“ wiederhergestellt", "actions": eintraege
            }, f, indent=2, ensure_ascii=False)
        manifest = manifest_datei.name
    return {"wiederhergestellt": len(eintraege), "uebersprungen": uebersprungen, "manifest": manifest,
            "beispiel": eintraege[0]["target"] if eintraege else ""}


def uebersicht() -> Dict[str, Any]:
    """Alles, was der Reiter „Sicherung“ anzeigt."""
    jetzt = datetime.now()
    auftraege = []
    for job in lade_auftraege():
        eintrag = dict(job)
        eintrag["naechster_termin"] = naechster_termin(job, jetzt)
        if job.get("ziel_typ") == "ordner":
            ok, grund = OrdnerZiel(job).verfuegbar()
            eintrag["ziel_erreichbar"], eintrag["ziel_hinweis"] = ok, grund
        else:
            eintrag["ziel_erreichbar"], eintrag["ziel_hinweis"] = nextcloud_eingerichtet(), (
                "" if nextcloud_eingerichtet() else "Nextcloud ist noch nicht eingerichtet.")
        auftraege.append(eintrag)
    return {
        "auftraege": auftraege,
        "status": {k: v for k, v in STATUS.items() if k != "abbrechen"},
        "protokoll": lade_protokoll(30),
        "nextcloud": {"eingerichtet": nextcloud_eingerichtet(), "url": config.NEXTCLOUD_URL,
                      "benutzer": config.NEXTCLOUD_BENUTZER, "passwort_gesetzt": bool(config.NEXTCLOUD_APP_PASSWORT)},
    }
