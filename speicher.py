#!/usr/bin/env python3
"""
Speicherplatz: große Dateien und Ordner finden, einordnen und freigeben.

Entstanden aus einer Aufräumaktion von Hand (17.11.2026): Die Platte war fast
voll, und die Ursachen ließen sich nur im Terminal finden — 30 GB in einem
versteckten `.turbo/cache`, 38 GB eigene Videos in einem Ordner namens
„Cache“, 53 GB iOS-Simulatoren außerhalb des Benutzerordners. Dieses Modul
macht genau das, ohne Terminal und ohne Raten:

* **Messen** wie `du`: `st_blocks * 512` (belegter Platz), Hardlinks nur
  einmal, symbolischen Verknüpfungen wird nicht gefolgt, die Grenze des
  Laufwerks wird nicht überschritten. Versteckte Ordner zählen mit.
* **Einordnen** nach geschützten Orten und Paketen. Andere Einträge
  prüft der Nutzer in der Vorschau.
* **Freigeben** in den Papierkorb mit Manifest für „Rückgängig“.

Gelöscht wird nie außerhalb des Benutzerordners und nie mit
Administratorrechten.
"""

import json
import os
import shutil
import stat as stat_modul
import subprocess
import threading
import time
from uuid import uuid4
from datetime import datetime
from pathlib import Path

import config
from classifier import ist_paket

HOME = Path.home()


class SpeicherFehler(Exception):
    """Ein Fehler, dessen Text der Oberfläche gezeigt werden darf."""


class _Abbruch(Exception):
    """Intern: der Nutzer hat den Scan abgebrochen."""


# --------------------------------------------------------------------------
# Hilfsmittel
# --------------------------------------------------------------------------

def lesbar(bytes_zahl: int) -> str:
    """1536 → „1,5 KB“ (deutsche Schreibweise, wie in der Oberfläche)."""
    zahl = float(bytes_zahl or 0)
    for einheit in ("B", "KB", "MB", "GB", "TB"):
        if abs(zahl) < 1024 or einheit == "TB":
            if einheit == "B":
                return f"{int(zahl)} B"
            return f"{zahl:.1f}".replace(".", ",") + f" {einheit}"
        zahl /= 1024
    return f"{bytes_zahl} B"


def _expandiere(muster: str) -> Path:
    return Path(muster).expanduser()


_NICHT_DURCHSUCHEN = [(_expandiere(p), h) for p, h in config.SPEICHER_NICHT_DURCHSUCHEN]
_NICHT_ANFASSEN_PFADE = [(_expandiere(p), h) for p, h in config.NICHT_ANFASSEN_PFADE]


def _ist_unter(pfad: Path, moeglicher_elternteil: Path) -> bool:
    return pfad == moeglicher_elternteil or moeglicher_elternteil in pfad.parents


_ARTNAMEN = {
    "DOKUMENTE": "Dokument", "BILDER": "Bild", "VIDEOS": "Video",
    "AUDIO": "Musik", "ARCHIVE": "Archiv", "CODE_DATEN": "Daten",
}


def _art_nach_endung(name: str) -> str:
    """Art allein aus dem Namen — ohne die Platte zu fragen.

    Im Scan wird das je Datei gebraucht; jede zusätzliche Abfrage am
    Dateisystem kostet dort spürbar Zeit.
    """
    endung = Path(name).suffix.lower()
    for kategorie, endungen in config.FILE_CATEGORIES.items():
        if endung in endungen:
            return _ARTNAMEN.get(kategorie, "Datei")
    return "Datei"


def art_der_datei(pfad: Path) -> str:
    """Grobe Art für die Anzeige: Video, Bild, Dokument …"""
    pfad = Path(pfad)
    if ist_paket(pfad):
        return "Programm/Paket"
    art = _art_nach_endung(pfad.name)
    if art == "Datei" and pfad.is_dir():
        return "Ordner"
    return art


def _ist_eigene_datei(name: str, groesse: int) -> bool:
    """Ein Foto, Video, Musikstück oder Dokument des Nutzers?

    Mit Mindestgröße, damit die tausenden Symbole und Textdateien in einem
    `node_modules` nicht als eigene Dateien zählen.
    """
    endung = Path(name).suffix.lower()
    if endung in config.SPEICHER_EIGENE_MEDIEN_ENDUNGEN:
        return groesse >= config.SPEICHER_MEDIEN_MINDEST_BYTES
    if endung in config.SPEICHER_EIGENE_DOKUMENT_ENDUNGEN:
        return groesse >= config.SPEICHER_DOKUMENT_MINDEST_BYTES
    return False


# --------------------------------------------------------------------------
# Einordnung in die drei Stufen
# --------------------------------------------------------------------------

_GESCHUETZT_GEMERKT = {"basis": None, "liste": None}


def _geschuetzte_eigene_ordner() -> list:
    """Ordner der App selbst und das Ordnungssystem — nie zum Löschen anbieten.

    Das Ergebnis wird gemerkt: Bei einem Scan wird diese Liste zehntausendfach
    gebraucht, und der Basisordner ändert sich nur in den Einstellungen.
    """
    if _GESCHUETZT_GEMERKT["basis"] == config.ORDNUNG_BASIS and _GESCHUETZT_GEMERKT["liste"] is not None:
        return _GESCHUETZT_GEMERKT["liste"]
    ordner = [(config.DATA_DIR, "Einstellungen und Verlauf von Dateien_Aktionen.")]
    for schluessel in config.ORDNUNG_ORDNER:
        try:
            p = config.ordnung_pfad(schluessel)
        except Exception:
            p = None
        if p:
            ordner.append((p, f"Hauptordner deines Ordnungssystems ({p.name})."))
    _GESCHUETZT_GEMERKT["basis"] = config.ORDNUNG_BASIS
    _GESCHUETZT_GEMERKT["liste"] = ordner
    return ordner


def regel_fuer(pfad: Path) -> tuple:
    """Geschützte Orte haben Vorrang vor Hinweisen aus einem Ordnernamen."""
    pfad = Path(pfad)
    if pfad == HOME or not _ist_unter(pfad, HOME):
        return "tabu", "Hier räumt die Speicheranalyse nichts auf."
    for ort, hinweis in (*_geschuetzte_eigene_ordner(), *_NICHT_ANFASSEN_PFADE):
        if _ist_unter(pfad, ort):
            return "tabu", hinweis
    for teil in (pfad, *pfad.parents):
        if teil == HOME:
            break
        if teil.suffix.lower() in config.NICHT_ANFASSEN_PAKETE:
            return "tabu", config.NICHT_ANFASSEN_PAKETE[teil.suffix.lower()]
    return "entscheidung", "Deine eigenen Dateien. Bitte selbst ansehen."


def _paket_regel(pfad: Path):
    """Für Pakete (.app, .photoslibrary …) gilt die Regel des Pakets selbst."""
    hinweis = config.NICHT_ANFASSEN_PAKETE.get(pfad.suffix.lower())
    return ("tabu", hinweis) if hinweis else None


# --------------------------------------------------------------------------
# Platte, Vollzugriff, Papierkorb
# --------------------------------------------------------------------------

def platte(pfad=None) -> dict:
    """Gesamt, belegt und frei für das Laufwerk eines Pfades (wie `df`)."""
    ziel = Path(pfad).expanduser() if pfad else HOME
    while not ziel.exists() and ziel != ziel.parent:
        ziel = ziel.parent
    try:
        nutzung = shutil.disk_usage(ziel)
    except OSError as exc:
        raise SpeicherFehler(f"Die Platte konnte nicht gelesen werden: {exc}")
    return {
        "gesamt": nutzung.total,
        "belegt": nutzung.used,
        "frei": nutzung.free,
        "laufwerk": str(ziel),
    }


# Diese Orte darf nur lesen, wer „Festplattenvollzugriff“ hat. Keiner von
# ihnen löst eine Nachfrage von macOS aus — es ist eine stille Prüfung.
_VOLLZUGRIFF_PROBEN = [
    HOME / ".Trash",
    HOME / "Library" / "Application Support" / "com.apple.TCC",
    HOME / "Library" / "Mail",
]


def hat_vollzugriff() -> dict:
    """Ob die App den ganzen Benutzerordner sehen darf.

    Ohne „Festplattenvollzugriff“ bleiben Teile unsichtbar (und der Papierkorb
    unlesbar). Das sagt die App beim ersten Scan, statt stillschweigend zu
    wenig zu melden.
    """
    gesperrt = []
    for probe in _VOLLZUGRIFF_PROBEN:
        if not probe.exists():
            continue
        try:
            with os.scandir(probe) as it:
                next(iter(it), None)
        except PermissionError:
            gesperrt.append(str(probe))
        except OSError:
            pass
    return {"ok": not gesperrt, "gesperrt": gesperrt}


def _finder_frage(befehl: str, grenze: int = 25):
    """Eine Frage an den Finder. Je Aufruf nur eine — `osascript` gibt bei
    mehreren `-e` nur das Ergebnis der letzten Zeile aus."""
    try:
        res = subprocess.run(
            ["osascript", "-e", f"tell application \"Finder\" to {befehl}"],
            capture_output=True, text=True, timeout=grenze, check=False,
        )
    except Exception:
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip()


_PAPIERKORB_GEMERKT = {"zeit": 0.0, "wert": None}


def papierkorb_info() -> dict:
    """Anzahl und Größe im Papierkorb — über den Finder gefragt.

    Direkt lesen lässt sich `~/.Trash` nur mit „Festplattenvollzugriff“;
    der Finder weiß es immer. Die Größe ist die des Finders (Inhalt
    zusammengerechnet), deshalb kann sie vom belegten Platz abweichen.
    """
    # Ein großer Papierkorb kostet beim Messen Zeit; die Oberfläche fragt oft.
    if _PAPIERKORB_GEMERKT["wert"] is not None and time.time() - _PAPIERKORB_GEMERKT["zeit"] < 60:
        return dict(_PAPIERKORB_GEMERKT["wert"])

    ergebnis = {"anzahl": 0, "bytes": 0, "ungefaehr": False, "gelesen": False}

    # Selbst messen, wenn die App den Papierkorb lesen darf: Das zählt auch
    # versteckte Einträge (.turbo, .next …), die der Finder nicht aufführt.
    papierkorb = HOME / ".Trash"
    try:
        with os.scandir(papierkorb) as eintraege:
            belegt = anzahl = 0
            for eintrag in eintraege:
                anzahl += 1
                if eintrag.is_dir(follow_symlinks=False):
                    belegt += messe(Path(eintrag.path))["bytes"]
                else:
                    try:
                        belegt += eintrag.stat(follow_symlinks=False).st_blocks * 512
                    except OSError:
                        pass
        return _papierkorb_merken({"anzahl": anzahl, "bytes": belegt, "ungefaehr": False, "gelesen": True})
    except (PermissionError, FileNotFoundError, OSError):
        pass  # ohne „Festplattenvollzugriff“ gesperrt — dann fragen wir den Finder

    anzahl_text = _finder_frage("get count of items of trash")
    if anzahl_text is None:
        return ergebnis
    try:
        ergebnis["anzahl"] = int(float(anzahl_text))
    except ValueError:
        return ergebnis
    ergebnis["gelesen"] = True
    if ergebnis["anzahl"] == 0:
        return _papierkorb_merken(ergebnis)

    groessen = _finder_frage("get size of every item of trash", grenze=60)
    if groessen is None:
        ergebnis["ungefaehr"] = True
        return _papierkorb_merken(ergebnis)
    # Der Finder führt versteckte Einträge nicht auf — die Zahl ist dann zu klein.
    ergebnis["ungefaehr"] = True
    gesamt = 0
    for teil in groessen.split(","):
        teil = teil.strip()
        try:
            gesamt += int(float(teil))
        except ValueError:
            ergebnis["ungefaehr"] = True  # „missing value“: Finder kennt die Größe nicht
    ergebnis["bytes"] = gesamt
    return _papierkorb_merken(ergebnis)


def _papierkorb_merken(wert: dict) -> dict:
    _PAPIERKORB_GEMERKT["zeit"] = time.time()
    _PAPIERKORB_GEMERKT["wert"] = dict(wert)
    return wert


def in_papierkorb(pfad: Path):
    """macOS wählt einen freien Papierkorb-Pfad und liefert genau dieses Ziel zurück."""
    import ctypes

    try:
        core = ctypes.CDLL("/System/Library/Frameworks/CoreServices.framework/CoreServices")
        verschiebe = core.FSPathMoveObjectToTrashSync
        verschiebe.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32]
        verschiebe.restype = ctypes.c_int32
        freigeben = ctypes.CDLL(None).free
        freigeben.argtypes = [ctypes.c_void_p]
        freigeben.restype = None
    except (AttributeError, OSError):
        return None
    ziel = ctypes.c_void_p()
    try:
        status = verschiebe(os.fsencode(pfad), ctypes.byref(ziel), 0)
        if status == 0 and ziel.value:
            return os.fsdecode(ctypes.string_at(ziel))
        return None
    finally:
        if ziel.value:
            freigeben(ziel)


def hole_aus_papierkorb(im_papierkorb: Path, zurueck_nach: Path) -> bool:
    """Holt einen Eintrag aus dem Papierkorb an seinen alten Platz zurück.

    Über den Finder, weil `~/.Trash` ohne „Festplattenvollzugriff“ für die App
    gesperrt ist — der Finder darf es immer.
    """
    im_papierkorb, zurueck_nach = Path(im_papierkorb), Path(zurueck_nach)
    if os.path.lexists(zurueck_nach):
        return False  # am Ursprungsort liegt schon wieder etwas — nichts überschreiben
    zurueck_nach.parent.mkdir(parents=True, exist_ok=True)
    # Der native Verschiebevorgang verwendet den exakten ursprünglichen Namen
    # und lehnt eine vorhandene Zieldatei auch bei gleichzeitigem Zugriff ab.
    skript = """ObjC.import('Foundation'); function run(argv) {
        if (!$.NSFileManager.defaultManager.moveItemAtPathToPathError(argv[0], argv[1], null))
            throw Error('Verschieben fehlgeschlagen');
    }"""
    try:
        subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", skript,
                        str(im_papierkorb), str(zurueck_nach)], capture_output=True,
                       text=True, timeout=180, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        if os.path.lexists(zurueck_nach):
            return False
    quelle = str(im_papierkorb).replace("\\", "\\\\").replace('"', '\\"')
    ordner = str(zurueck_nach.parent).replace("\\", "\\\\").replace('"', '\\"')
    try:
        res = subprocess.run(
            ["osascript", "-e",
             f'tell application "Finder" to move (POSIX file "{quelle}") to (POSIX file "{ordner}")'],
            capture_output=True, text=True, timeout=180, check=False,
        )
    except Exception:
        return False
    if res.returncode != 0:
        return False
    # Der Finder legt es unter seinem Namen ab; hieß es im Papierkorb anders
    # (Namensdopplung), wird es jetzt zurückbenannt.
    gelandet = zurueck_nach.parent / im_papierkorb.name
    if gelandet != zurueck_nach and gelandet.exists() and not zurueck_nach.exists():
        try:
            gelandet.rename(zurueck_nach)
        except OSError:
            return gelandet.exists()
    return zurueck_nach.exists() or gelandet.exists()


# --------------------------------------------------------------------------
# Scan: messen wie `du`, im Hintergrund, abbrechbar
# --------------------------------------------------------------------------

class _Lauf:
    """Ein laufender Scan. Misst den belegten Platz, nicht die Länge der Dateien.

    Gemessen wird `st_blocks * 512` — derselbe Wert, den `du -sk` ausgibt.
    Hardlinks zählen einmal, symbolischen Verknüpfungen wird nicht gefolgt,
    und die Grenze des Laufwerks wird nicht überschritten (ein eingebundenes
    Laufwerk im Benutzerordner wird übersprungen und genannt).
    """

    def __init__(self, start: Path, mindest_bytes: int):
        self.start = start
        self.mindest_bytes = mindest_bytes
        self.abbrechen = False
        self.laeuft = True
        self.fertig = False
        self.abgebrochen = False
        self.fehler_text = ""
        self.begonnen = time.time()
        self.beendet = None
        self.ordner_gezaehlt = 0
        self.dateien_gezaehlt = 0
        self.bytes_gezaehlt = 0
        self.bytes_logisch = 0
        self.aktuell = str(start)
        self.uebersprungen = []
        self.uebersprungen_anzahl = 0
        self.grosse_dateien = []
        self.hardlinks_einmal = 0
        self._inodes = set()
        self.knoten_je_tiefe = {}
        self.ergebnis = None
        try:
            self.dev = start.stat().st_dev
        except OSError as exc:
            raise SpeicherFehler(f"Der Ordner konnte nicht gelesen werden: {exc}")

    # -- Meldungen ---------------------------------------------------------
    def _uebersprungen(self, pfad, grund: str) -> None:
        self.uebersprungen_anzahl += 1
        if len(self.uebersprungen) < 300:
            self.uebersprungen.append({"pfad": str(pfad), "grund": grund})

    def status(self) -> dict:
        return {
            "laeuft": self.laeuft,
            "fertig": self.fertig,
            "abgebrochen": self.abgebrochen,
            "fehler": self.fehler_text,
            "startordner": str(self.start),
            "ordner": self.ordner_gezaehlt,
            "dateien": self.dateien_gezaehlt,
            "bytes": self.bytes_gezaehlt,
            "aktuell": self.aktuell,
            "uebersprungen": self.uebersprungen_anzahl,
            "dauer": round((self.beendet or time.time()) - self.begonnen, 1),
        }

    def _wird_ausgelassen(self, pfad: Path):
        """Grund, warum ein Ordner nicht durchsucht wird — oder None.

        Der selbst gewählte Startordner wird immer gemessen, auch wenn er in
        der Liste steht.
        """
        if pfad == self.start:
            return None
        for ordner, grund in _NICHT_DURCHSUCHEN:
            if pfad == ordner:
                return grund
        return None

    # -- Messen ------------------------------------------------------------
    def _paket(self, pfad: Path) -> tuple:
        """Ein Paket (.app, .photoslibrary …) zählt als eine Einheit, wie im Katalog."""
        belegt = logisch = 0
        anzahl = 0
        for wurzel, _ordner, dateien in os.walk(pfad, followlinks=False):
            if self.abbrechen:
                raise _Abbruch
            for name in dateien:
                try:
                    st = os.lstat(os.path.join(wurzel, name))
                except OSError:
                    continue
                if stat_modul.S_ISLNK(st.st_mode):
                    continue
                belegt += st.st_blocks * 512
                logisch += st.st_size
                anzahl += 1
        return belegt, logisch, anzahl

    def _ordner(self, pfad: Path, tiefe: int):
        """Misst einen Ordner samt Inhalt und liefert seinen Knoten für den Baum."""
        if self.abbrechen:
            raise _Abbruch

        self.aktuell = str(pfad)
        self.ordner_gezaehlt += 1
        # Die Regel gilt für den Ordner und alles darin — einmal prüfen genügt.
        # Je Datei zu prüfen kostete bei einem großen Benutzerordner Minuten.
        regel = regel_fuer(pfad)
        belegt = logisch = 0
        dateien_anzahl = 0
        eigene_bytes = 0
        eigene_beispiel = ""
        eigene_beispiel_bytes = 0
        kinder = []
        datei_liste = []

        try:
            selbst = pfad.stat()
            belegt += selbst.st_blocks * 512
        except OSError:
            pass

        try:
            with os.scandir(pfad) as eintraege:
                liste = list(eintraege)
        except PermissionError:
            self._uebersprungen(pfad, "kein Leserecht")
            return None
        except OSError as exc:
            self._uebersprungen(pfad, f"nicht lesbar ({exc.strerror or exc})")
            return None

        for eintrag in liste:
            if self.abbrechen:
                raise _Abbruch
            try:
                st = eintrag.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat_modul.S_ISLNK(st.st_mode):
                continue  # Verknüpfungen nicht folgen und nicht mitzählen

            kind = Path(eintrag.path)

            if eintrag.is_dir(follow_symlinks=False):
                if st.st_dev != self.dev:
                    self._uebersprungen(kind, "anderes Laufwerk")
                    continue
                ausgelassen = self._wird_ausgelassen(kind)
                if ausgelassen:
                    self._uebersprungen(kind, ausgelassen)
                    continue
                if ist_paket(kind):
                    p_belegt, p_logisch, p_anzahl = self._paket(kind)
                    belegt += p_belegt
                    logisch += p_logisch
                    dateien_anzahl += p_anzahl
                    self.dateien_gezaehlt += p_anzahl
                    self.bytes_gezaehlt += p_belegt
                    paket_regel = _paket_regel(kind) or regel
                    stufe, hinweis = paket_regel
                    self._merke_grosse_datei(kind, p_belegt, st, paket=True, stufe=(stufe, hinweis))
                    datei_liste.append({
                        "name": kind.name, "pfad": str(kind), "bytes": p_belegt,
                        "geaendert": _zeit(st.st_mtime), "art": "Programm/Paket",
                        "versteckt": kind.name.startswith("."), "paket": True,
                        "stufe": stufe, "hinweis": hinweis,
                    })
                    continue

                knoten = self._ordner(kind, tiefe + 1)
                if knoten is None:
                    continue
                belegt += knoten["bytes"]
                logisch += knoten["bytes_logisch"]
                dateien_anzahl += knoten["dateien"]
                if knoten["eigene_bytes"] > eigene_beispiel_bytes and knoten["eigene_beispiel"]:
                    eigene_beispiel = knoten["eigene_beispiel"]
                    eigene_beispiel_bytes = knoten["eigene_bytes"]
                eigene_bytes += knoten["eigene_bytes"]
                kinder.append(knoten)
                continue

            # Eine gewöhnliche Datei
            if st.st_nlink > 1:
                schluessel = (st.st_dev, st.st_ino)
                if schluessel in self._inodes:
                    self.hardlinks_einmal += 1
                    continue
                self._inodes.add(schluessel)

            groesse = st.st_blocks * 512
            belegt += groesse
            logisch += st.st_size
            dateien_anzahl += 1
            self.dateien_gezaehlt += 1
            self.bytes_gezaehlt += groesse

            if _ist_eigene_datei(eintrag.name, st.st_size):
                eigene_bytes += groesse
                if groesse > eigene_beispiel_bytes:
                    eigene_beispiel = eintrag.name
                    eigene_beispiel_bytes = groesse

            stufe, hinweis = regel
            self._merke_grosse_datei(kind, groesse, st, stufe=(stufe, hinweis))
            datei_liste.append({
                "name": eintrag.name, "pfad": str(kind), "bytes": groesse,
                "geaendert": _zeit(st.st_mtime), "art": _art_nach_endung(eintrag.name),
                "versteckt": eintrag.name.startswith("."), "paket": False,
                "stufe": stufe, "hinweis": hinweis,
            })

        stufe, hinweis = regel

        # Nur die größten Einträge in den Baum: alles andere wäre unlesbar und
        # würde bei einem großen Benutzerordner den Arbeitsspeicher füllen.
        datei_liste.sort(key=lambda d: d["bytes"], reverse=True)
        weitere_dateien = {
            "anzahl": max(0, len(datei_liste) - 10),
            "bytes": sum(d["bytes"] for d in datei_liste[10:]),
        }
        datei_liste = datei_liste[:10]

        kinder.sort(key=lambda k: k["bytes"], reverse=True)
        schwelle = min(config.SPEICHER_BAUM_MINDEST_BYTES,
                       int(belegt * config.SPEICHER_BAUM_MINDEST_ANTEIL))
        behalten = []
        weggelassen_bytes = 0
        kind_tiefe = tiefe + 1
        budget = config.SPEICHER_BAUM_KNOTEN_JE_TIEFE.get(kind_tiefe, 0)
        for nummer, knoten in enumerate(kinder):
            passt = (nummer < 3 or knoten["bytes"] >= schwelle)
            if (passt and nummer < config.SPEICHER_BAUM_BREITE
                    and kind_tiefe <= config.SPEICHER_BAUM_TIEFE
                    and self.knoten_je_tiefe.get(kind_tiefe, 0) < budget):
                behalten.append(knoten)
                self.knoten_je_tiefe[kind_tiefe] = self.knoten_je_tiefe.get(kind_tiefe, 0) + 1
            else:
                weggelassen_bytes += knoten["bytes"]
        weitere_ordner = {
            "anzahl": len(kinder) - len(behalten),
            "bytes": weggelassen_bytes,
        }

        return {
            "pfad": str(pfad),
            "name": pfad.name or str(pfad),
            "bytes": belegt,
            "bytes_logisch": logisch,
            "dateien": dateien_anzahl,
            "eigene_bytes": eigene_bytes,
            "eigene_beispiel": eigene_beispiel,
            "versteckt": pfad.name.startswith("."),
            "paket": False,
            "stufe": stufe,
            "hinweis": hinweis,
            "kinder": behalten,
            "weitere_ordner": weitere_ordner,
            "weitere_dateien": weitere_dateien,
            "datei_liste": datei_liste,
        }

    def _merke_grosse_datei(self, pfad: Path, groesse: int, st,
                            paket: bool = False, stufe: tuple = None) -> None:
        if groesse < self.mindest_bytes or len(self.grosse_dateien) >= 2000:
            return
        stufe, hinweis = stufe or regel_fuer(pfad)
        self.grosse_dateien.append({
            "pfad": str(pfad), "name": pfad.name, "bytes": groesse,
            "geaendert": _zeit(st.st_mtime),
            "art": "Programm/Paket" if paket else _art_nach_endung(pfad.name),
            "versteckt": pfad.name.startswith("."), "paket": paket,
            "stufe": stufe, "hinweis": hinweis,
        })

    # -- Ablauf ------------------------------------------------------------
    def lauf(self) -> None:
        vollzugriff = hat_vollzugriff()
        try:
            baum = self._ordner(self.start, 0)
            if baum is None:
                raise SpeicherFehler(
                    f"„{self.start}“ ließ sich nicht lesen. "
                    "Oft fehlt der App dafür „Festplattenvollzugriff“."
                )
            self.grosse_dateien.sort(key=lambda d: d["bytes"], reverse=True)
            self.ergebnis = {
                "startordner": str(self.start),
                "gemessen_am": datetime.now().strftime("%d.%m.%Y %H:%M"),
                "dauer": round(time.time() - self.begonnen, 1),
                "platte": platte(self.start),
                "baum": baum,
                "grosse_dateien": self.grosse_dateien[:300],
                "grosse_dateien_gesamt": len(self.grosse_dateien),
                "mindestgroesse_mb": round(self.mindest_bytes / (1024 * 1024)),
                "uebersprungen": self.uebersprungen,
                "uebersprungen_anzahl": self.uebersprungen_anzahl,
                "hardlinks_einmal": self.hardlinks_einmal,
                "ordner": self.ordner_gezaehlt,
                "dateien": self.dateien_gezaehlt,
                "bytes": baum["bytes"],
                "bytes_logisch": baum["bytes_logisch"],
                "vollzugriff": vollzugriff,
                "papierkorb": papierkorb_info(),
            }
            self.fertig = True
        except _Abbruch:
            self.abgebrochen = True
        except SpeicherFehler as exc:
            self.fehler_text = str(exc)
        except Exception as exc:  # nichts darf den Hintergrund-Thread stehen lassen
            self.fehler_text = f"Der Scan ist fehlgeschlagen: {exc}"
        finally:
            self.laeuft = False
            self.beendet = time.time()


_SPERRE = threading.Lock()
_AKTUELL = None


def starte_scan(startordner: str, mindestgroesse_mb=None) -> dict:
    """Startet den Scan im Hintergrund. Es läuft immer nur einer."""
    global _AKTUELL
    start = Path(str(startordner or "")).expanduser()
    if not str(startordner or "").strip():
        raise SpeicherFehler("Bitte einen Startordner wählen.")
    if not start.is_dir():
        raise SpeicherFehler(f"„{start}“ ist kein Ordner.")
    if start.is_symlink():
        raise SpeicherFehler("Der Startordner ist eine Verknüpfung. Bitte den echten Ordner wählen.")

    try:
        mb = int(mindestgroesse_mb) if mindestgroesse_mb else config.SPEICHER_MINDESTGROESSE_MB
    except (TypeError, ValueError):
        mb = config.SPEICHER_MINDESTGROESSE_MB
    mb = max(1, min(mb, 1024 * 1024))

    with _SPERRE:
        if _AKTUELL is not None and _AKTUELL.laeuft:
            raise SpeicherFehler("Es läuft schon ein Scan. Bitte abbrechen oder abwarten.")
        lauf = _Lauf(start.resolve(), mb * 1024 * 1024)
        _AKTUELL = lauf

    threading.Thread(target=lauf.lauf, name="speicher-scan", daemon=True).start()
    return lauf.status()


def status(mit_ergebnis: bool = True) -> dict:
    """Fortschritt des Scans — und das Ergebnis, sobald er fertig ist."""
    lauf = _AKTUELL
    if lauf is None:
        return {"laeuft": False, "fertig": False, "abgebrochen": False,
                "fehler": "", "startordner": "", "ordner": 0, "dateien": 0,
                "bytes": 0, "aktuell": "", "uebersprungen": 0, "dauer": 0}
    antwort = lauf.status()
    if mit_ergebnis and lauf.fertig and lauf.ergebnis:
        antwort["ergebnis"] = lauf.ergebnis
    return antwort


def brich_ab() -> dict:
    """Bricht den laufenden Scan ab. Der Thread beendet sich beim nächsten Eintrag."""
    lauf = _AKTUELL
    if lauf is None or not lauf.laeuft:
        return {"abgebrochen": False, "hinweis": "Es lief kein Scan."}
    lauf.abbrechen = True
    for _ in range(100):  # bis zu 10 Sekunden auf das Ende warten
        if not lauf.laeuft:
            break
        time.sleep(0.1)
    return {"abgebrochen": True, "lief_noch": lauf.laeuft}


def _zeit(zeitstempel: float) -> str:
    try:
        return datetime.fromtimestamp(zeitstempel).strftime("%d.%m.%Y")
    except (OSError, OverflowError, ValueError):
        return ""


# --------------------------------------------------------------------------
# Freigeben: Vorschau und Papierkorb
# --------------------------------------------------------------------------

def messe(pfad: Path) -> dict:
    """Belegten Platz, Anzahl Dateien und Anteil eigener Dateien eines Eintrags."""
    pfad = Path(pfad)
    belegt = dateien = eigene = 0
    beispiel = ""
    beispiel_bytes = 0
    try:
        st = pfad.lstat()
    except OSError as exc:
        raise SpeicherFehler(f"„{pfad.name}“ ließ sich nicht lesen: {exc.strerror or exc}")

    if not stat_modul.S_ISDIR(st.st_mode):
        return {"bytes": st.st_blocks * 512, "dateien": 1,
                "eigene_bytes": st.st_blocks * 512 if _ist_eigene_datei(pfad.name, st.st_size) else 0,
                "eigene_beispiel": pfad.name if _ist_eigene_datei(pfad.name, st.st_size) else ""}

    belegt += st.st_blocks * 512
    inodes = set()
    for wurzel, ordner, namen in os.walk(pfad, followlinks=False):
        ordner[:] = [o for o in ordner if not os.path.islink(os.path.join(wurzel, o))]
        try:
            belegt += os.lstat(wurzel).st_blocks * 512 if wurzel != str(pfad) else 0
        except OSError:
            pass
        for name in namen:
            try:
                dst = os.lstat(os.path.join(wurzel, name))
            except OSError:
                continue
            if stat_modul.S_ISLNK(dst.st_mode):
                continue
            if dst.st_nlink > 1:
                schluessel = (dst.st_dev, dst.st_ino)
                if schluessel in inodes:
                    continue
                inodes.add(schluessel)
            groesse = dst.st_blocks * 512
            belegt += groesse
            dateien += 1
            if _ist_eigene_datei(name, dst.st_size):
                eigene += groesse
                if groesse > beispiel_bytes:
                    beispiel, beispiel_bytes = name, groesse
    return {"bytes": belegt, "dateien": dateien, "eigene_bytes": eigene, "eigene_beispiel": beispiel}


def _geprueft(pfad_text: str) -> Path:
    """Prüft einen Pfad aus der Oberfläche, bevor etwas damit passiert.

    Gelöscht wird nur innerhalb des Benutzerordners, nie über eine Verknüpfung
    hinaus, nie der Benutzerordner selbst und nichts, was die App oder das
    Ordnungssystem zum Arbeiten braucht.
    """
    if not str(pfad_text or "").strip():
        raise SpeicherFehler("Ein Eintrag ohne Pfad wurde übergeben.")
    ziel = Path(str(pfad_text)).expanduser()
    if not ziel.is_absolute():
        raise SpeicherFehler(f"„{pfad_text}“ ist kein vollständiger Pfad.")
    if ziel.is_symlink():
        raise SpeicherFehler(f"„{ziel.name}“ ist eine Verknüpfung — die lässt die App stehen.")
    if not ziel.exists():
        raise SpeicherFehler(f"„{ziel}“ gibt es nicht mehr.")

    echt = ziel.resolve()
    for p in (ziel, echt):
        if p == HOME:
            raise SpeicherFehler("Das ist dein Benutzerordner — den löscht die App nicht.")
        if not _ist_unter(p, HOME):
            raise SpeicherFehler(
                f"„{p}“ liegt nicht in deinem Benutzerordner. Dort löscht die App nichts."
            )

    if ziel != echt:
        raise SpeicherFehler("Verknüpfte oder mehrdeutige Pfade werden ausgelassen.")

    if _ist_unter(echt, HOME / ".Trash"):
        raise SpeicherFehler(
            "Das liegt schon im Papierkorb. Du kannst ihn im Finder leeren."
        )

    # Nichts löschen, in dem die Daten der App oder das Ordnungssystem liegen
    for ordner, _hinweis in _geschuetzte_eigene_ordner():
        if _ist_unter(ordner, echt):
            raise SpeicherFehler(
                f"„{ziel.name}“ enthält „{ordner.name}“ und wird deshalb nicht gelöscht."
            )
    return ziel


def vorschau(pfade, modus: str = "papierkorb") -> dict:
    """Trockenlauf: was, wie viel, wohin — vor jedem Löschen.

    Einträge, die schon in einem anderen ausgewählten Ordner stecken, werden
    einmal gezählt und als solche gemeldet.
    """
    if modus != "papierkorb":
        raise SpeicherFehler("Unbekannte Art des Löschens.")
    if not pfade:
        raise SpeicherFehler("Es ist nichts ausgewählt.")

    geprueft = []
    for eintrag in pfade:
        geprueft.append(_geprueft(eintrag))
    geprueft.sort(key=lambda p: len(str(p)))

    einzeln, enthalten = [], []
    for ziel in geprueft:
        if any(_ist_unter(ziel, schon) and ziel != schon for schon in einzeln):
            enthalten.append(str(ziel))
            continue
        einzeln.append(ziel)

    eintraege = []
    gesamt_bytes = gesamt_dateien = 0
    braucht_bestaetigung = False
    for ziel in einzeln:
        stufe, hinweis = regel_fuer(ziel)
        if stufe == "tabu":
            raise SpeicherFehler(f"„{ziel.name}“ gehört zu „Nicht anfassen“: {hinweis}")
        gemessen = messe(ziel)
        eintraege.append({
            "pfad": str(ziel),
            "name": ziel.name,
            "ordner": str(ziel.parent),
            "bytes": gemessen["bytes"],
            "dateien": gemessen["dateien"],
            "ist_ordner": ziel.is_dir() and not ist_paket(ziel),
            "stufe": stufe,
            "hinweis": hinweis,
            "art": art_der_datei(ziel),
            "ziel": "Papierkorb",
        })
        gesamt_bytes += gemessen["bytes"]
        gesamt_dateien += gemessen["dateien"]

    return {
        "modus": modus,
        "eintraege": eintraege,
        "enthalten": enthalten,
        "gesamt_bytes": gesamt_bytes,
        "gesamt_dateien": gesamt_dateien,
        "gesamt_lesbar": lesbar(gesamt_bytes),
        "braucht_bestaetigung": braucht_bestaetigung,
        "papierkorb_hinweis": "Der Platz wird beim Leeren des Papierkorbs im Finder frei.",
    }


def freigeben(pfade, modus: str = "papierkorb", bestaetigt: bool = False) -> dict:
    plan = vorschau(pfade, modus)
    return plan_in_papierkorb(plan["eintraege"], "Speicherplatz")


def plan_in_papierkorb(eintraege, beschreibung, pruefe_eintrag=None):
    """Nur geprüfte Vorschau-Einträge. Jeden abgeschlossenen Schritt protokollieren."""
    jetzt = datetime.now()
    datei = config.HISTORY_DIR / f"manifest_{jetzt:%Y%m%d_%H%M%S_%f}_{uuid4().hex}.json"
    config.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    temp = datei.with_suffix(".tmp")
    aktionen, fehler = [], []
    gesamt = 0
    for eintrag in eintraege:
        ziel = Path(eintrag["pfad"])
        if pruefe_eintrag:
            try:
                pruefe_eintrag(eintrag)
            except (OSError, SpeicherFehler) as exc:
                fehler.append({"pfad": str(ziel), "grund": str(exc)})
                break
        im_papierkorb = in_papierkorb(ziel)
        if not im_papierkorb:
            fehler.append({"pfad": str(ziel), "grund": "Der Papierkorb hat es nicht angenommen."})
            if pruefe_eintrag:
                break
            continue
        aktionen.append({"source": str(ziel), "target": str(im_papierkorb), "copy_mode": False,
                         "aktion": "papierkorb", "wiederherstellbar": True,
                         "bytes": eintrag["bytes"], "timestamp": datetime.now().isoformat()})
        gesamt += eintrag["bytes"]
        try:
            temp.write_text(json.dumps({"created_at": jetzt.isoformat(), "quelle": "speicherplatz",
                                        "beschreibung": beschreibung, "total_actions": len(aktionen),
                                        "rueckgaengig": True, "actions": aktionen}, ensure_ascii=False),
                            encoding="utf-8")
            temp.replace(datei)
        except OSError as exc:
            if hole_aus_papierkorb(Path(im_papierkorb), ziel):
                raise SpeicherFehler(f"Das Protokoll konnte nicht gespeichert werden. "
                                     f"„{ziel.name}“ wurde zurückgelegt.") from exc
            raise SpeicherFehler(f"Das Protokoll konnte nicht gespeichert werden. "
                                 f"„{ziel}“ liegt im Papierkorb unter „{im_papierkorb}“.") from exc
        _PAPIERKORB_GEMERKT["wert"] = None
    return {"modus": "papierkorb", "erledigt": len(aktionen), "bytes": gesamt,
            "lesbar": lesbar(gesamt), "manifest": datei.name if aktionen else "",
            "fehlgeschlagen": fehler, "hinweis": "Der Platz wird beim Leeren des Papierkorbs frei."}


# --------------------------------------------------------------------------
# Installationsdateien, deren Programm schon installiert ist
# --------------------------------------------------------------------------
# Eine `.dmg` oder `.pkg` wird nur zum Installieren gebraucht. Ist das Programm
# installiert, liegt die Datei meist jahrelang in „Downloads“ und belegt dort
# ein paar hundert Megabyte. Erkannt wird sie am Namen — auch dann, wenn dieses
# Programm sie schon umbenannt hat (2026-10-17_Absender_Dokument_Name.dmg).

INSTALLER_ENDUNGEN = {".dmg", ".pkg", ".mpkg"}

# Wörter, die im Dateinamen stehen, aber nichts über das Programm sagen
_INSTALLER_RAUSCHEN = {
    "mac", "macos", "osx", "installer", "install", "setup", "universal",
    "arm64", "x86", "x8664", "intel", "apple", "silicon", "final", "full",
    "latest", "version", "release", "signed", "notarized", "de", "en",
    "deutsch", "english", "download", "kopie", "copy",
}


def _wortteile(text: str) -> list:
    """Zerlegt einen Namen in Wörter: „LosslessCut-mac-arm64“ → [lossless, cut, mac, arm64]."""
    teile = []
    wort = ""
    for zeichen in text:
        if zeichen.isalnum():
            wort += zeichen
        elif wort:
            teile.append(wort.lower())
            wort = ""
    if wort:
        teile.append(wort.lower())
    return teile


def _kern(text: str) -> str:
    """Der Kern eines Namens: ohne Versionsnummern, Datum und Füllwörter."""
    teile = []
    for wort in _wortteile(text):
        if wort.isdigit():
            continue
        if wort in _INSTALLER_RAUSCHEN:
            continue
        teile.append(wort)
    return "".join(teile)


def _version_aus_name(text: str):
    """Die erste Versionsnummer im Namen, etwa „3.4.0“ aus „Vorssaint-3.4.0.dmg“."""
    zeichen = list(text)
    stellen = []
    aktuell = ""
    for z in zeichen:
        if z.isdigit() or (z == "." and aktuell and not aktuell.endswith(".")):
            aktuell += z
        else:
            if "." in aktuell:
                stellen.append(aktuell.strip("."))
            aktuell = ""
    if "." in aktuell:
        stellen.append(aktuell.strip("."))
    for stelle in stellen:
        if stelle.count(".") >= 1 and stelle[0].isdigit():
            # Ein Datum wie 2026.10.17 ist keine Programmversion
            erste = stelle.split(".")[0]
            if len(erste) == 4 and erste.startswith("20"):
                continue
            return stelle
    return None


def _version_vergleich(eine: str, andere: str) -> int:
    """-1, 0 oder 1 — wie zwei Versionsnummern zueinander stehen."""
    def teile(v):
        return [int(t) if t.isdigit() else 0 for t in str(v).split(".")]
    a, b = teile(eine), teile(andere)
    laenge = max(len(a), len(b))
    a += [0] * (laenge - len(a))
    b += [0] * (laenge - len(b))
    return (a > b) - (a < b)


def installierte_programme() -> list:
    """Alle Programme in „Programme“ und im eigenen Programme-Ordner.

    Eine Ebene tiefer wird mitgenommen, weil viele Hersteller einen eigenen
    Ordner anlegen (etwa „Programme/Canon Utilities/…“).
    """
    import plistlib

    gefunden = []
    for ort in (Path("/Applications"), HOME / "Applications"):
        if not ort.is_dir():
            continue
        try:
            eintraege = list(os.scandir(ort))
        except OSError:
            continue
        for eintrag in eintraege:
            kandidaten = []
            if eintrag.name.lower().endswith(".app"):
                kandidaten.append(Path(eintrag.path))
            elif eintrag.is_dir(follow_symlinks=False):
                try:
                    with os.scandir(eintrag.path) as tiefer:
                        kandidaten.extend(
                            Path(t.path) for t in tiefer if t.name.lower().endswith(".app")
                        )
                except OSError:
                    continue
            for programm in kandidaten:
                version = ""
                try:
                    with open(programm / "Contents" / "Info.plist", "rb") as f:
                        angaben = plistlib.load(f)
                    version = str(angaben.get("CFBundleShortVersionString", "") or "")
                except Exception:
                    pass
                gefunden.append({
                    "name": programm.stem,
                    "pfad": str(programm),
                    "version": version,
                    "kern": _kern(programm.stem),
                })
    return gefunden


def _passendes_programm(dateiname: str, programme: list):
    """Das Programm, zu dem eine Installationsdatei gehört — oder None.

    Verglichen werden die Kerne beider Namen. Kurze Programmnamen müssen genau
    passen, sonst hielte „Blip“ jede Datei mit „blip“ darin für seine eigene.
    """
    kern_datei = _kern(Path(dateiname).stem)
    if len(kern_datei) < 3:
        return None
    treffer = None
    for programm in programme:
        kern = programm["kern"]
        if not kern:
            continue
        if len(kern) >= 5:
            passt = kern in kern_datei
        else:
            passt = kern == kern_datei
        if passt and (treffer is None or len(kern) > len(treffer["kern"])):
            treffer = programm  # der längste Treffer ist der genaueste
    return treffer


def finde_installationsdateien(ordner=None, tiefe: int = 4) -> dict:
    """Sucht `.dmg`- und `.pkg`-Dateien, deren Programm schon installiert ist.

    Ohne Angabe werden „Downloads“ und der Schreibtisch durchsucht.
    """
    orte = []
    for eintrag in (ordner or [HOME / "Downloads", HOME / "Desktop"]):
        pfad = Path(str(eintrag)).expanduser()
        if pfad.is_dir():
            orte.append(pfad)
    if not orte:
        raise SpeicherFehler("Kein Ordner zum Durchsuchen gefunden.")

    programme = installierte_programme()
    ausgelassen = [o for o, _h in _NICHT_DURCHSUCHEN]
    eintraege = []
    ohne_programm = 0

    for ort in orte:
        wurzel_tiefe = len(ort.parts)
        for wurzel, unterordner, dateien in os.walk(ort, followlinks=False):
            if len(Path(wurzel).parts) - wurzel_tiefe >= tiefe:
                unterordner[:] = []
            unterordner[:] = [
                u for u in unterordner
                if not os.path.islink(os.path.join(wurzel, u))
                and Path(wurzel, u) not in ausgelassen
            ]
            for name in dateien:
                if Path(name).suffix.lower() not in INSTALLER_ENDUNGEN:
                    continue
                datei = Path(wurzel, name)
                try:
                    st = datei.lstat()
                except OSError:
                    continue
                if stat_modul.S_ISLNK(st.st_mode):
                    continue

                programm = _passendes_programm(name, programme)
                if not programm:
                    ohne_programm += 1
                    continue

                version_datei = _version_aus_name(name)
                version_programm = programm["version"]
                empfehlung, erklaerung = "weg", ""
                if version_datei and version_programm:
                    stand = _version_vergleich(version_datei, version_programm)
                    if stand > 0:
                        empfehlung = "pruefen"
                        erklaerung = (
                            f"Die Datei enthält Version {version_datei}, installiert ist "
                            f"{version_programm} — vielleicht ist sie noch nicht eingespielt."
                        )
                    elif stand < 0:
                        erklaerung = (
                            f"Die Datei enthält die ältere Version {version_datei}, "
                            f"installiert ist {version_programm}."
                        )
                    else:
                        erklaerung = f"Die Datei enthält dieselbe Version {version_datei}."
                elif version_programm:
                    erklaerung = f"Installiert ist Version {version_programm}."

                stufe, hinweis = regel_fuer(datei)
                eintraege.append({
                    "pfad": str(datei),
                    "name": name,
                    "ordner": str(datei.parent),
                    "bytes": st.st_blocks * 512,
                    "geaendert": _zeit(st.st_mtime),
                    "art": "Installationsdatei",
                    "programm": programm["name"],
                    "programm_pfad": programm["pfad"],
                    "programm_version": version_programm,
                    "datei_version": version_datei or "",
                    "empfehlung": empfehlung,
                    "erklaerung": erklaerung,
                    "stufe": stufe,
                    "hinweis": hinweis,
                    "versteckt": name.startswith("."),
                    "paket": False,
                })

    eintraege.sort(key=lambda e: e["bytes"], reverse=True)
    return {
        "eintraege": eintraege,
        "durchsucht": [str(o) for o in orte],
        "programme": len(programme),
        "ohne_programm": ohne_programm,
        "gesamt_bytes": sum(e["bytes"] for e in eintraege if e["empfehlung"] == "weg"),
    }
