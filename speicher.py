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
* **Einordnen** in drei Stufen (`gefahrlos`, `entscheidung`, `tabu`) nach den
  Listen in `config.py` — Name *und* Lage. Ein Zwischenspeicher, in dem eigene
  Fotos, Videos, Musik oder Dokumente liegen, wird zu „Ihre Entscheidung“.
* **Freigeben** standardmäßig in den Papierkorb (über den Finder, damit
  „Zurücklegen“ funktioniert), mit Vorschau und Manifest für „Rückgängig“.
  Endgültig gelöscht wird nur nach ausdrücklicher Bestätigung.

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


_GEFAHRLOS_PFADE = [(_expandiere(p), h) for p, h in config.GEFAHRLOS_PFADE]
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
    """Die Stufe nach Lage und Name — ohne Rücksicht auf den Inhalt.

    Es gilt immer die längste (also genaueste) passende Regel: `~/Library`
    ist „Nicht anfassen“, `~/Library/Caches` darin trotzdem „Gefahrlos“.

    Rückgabe: (stufe, hinweis) mit stufe aus „gefahrlos“, „entscheidung“, „tabu“.
    """
    pfad = Path(pfad)

    # Außerhalb des Benutzerordners wird grundsätzlich nichts angeboten.
    if not _ist_unter(pfad, HOME):
        return "tabu", "Liegt außerhalb deines Benutzerordners. Dort räumt die App nichts auf."
    if pfad == HOME:
        return "tabu", "Dein Benutzerordner."

    treffer_stufe, treffer_hinweis, treffer_laenge = "entscheidung", "", -1

    for ordner, hinweis in _geschuetzte_eigene_ordner():
        if _ist_unter(pfad, ordner) and len(str(ordner)) > treffer_laenge:
            treffer_stufe, treffer_hinweis, treffer_laenge = "tabu", hinweis, len(str(ordner))

    for ordner, hinweis in _NICHT_ANFASSEN_PFADE:
        if _ist_unter(pfad, ordner) and len(str(ordner)) > treffer_laenge:
            treffer_stufe, treffer_hinweis, treffer_laenge = "tabu", hinweis, len(str(ordner))

    for ordner, hinweis in _GEFAHRLOS_PFADE:
        if _ist_unter(pfad, ordner) and len(str(ordner)) > treffer_laenge:
            treffer_stufe, treffer_hinweis, treffer_laenge = "gefahrlos", hinweis, len(str(ordner))

    # Pakete (Fotomediathek, Programm …): der Pfad selbst oder ein Elternteil
    for teil in [pfad, *pfad.parents]:
        if not _ist_unter(teil, HOME) or teil == HOME:
            break
        endung = teil.suffix.lower()
        if endung in config.NICHT_ANFASSEN_PAKETE and len(str(teil)) > treffer_laenge:
            treffer_stufe = "tabu"
            treffer_hinweis = config.NICHT_ANFASSEN_PAKETE[endung]
            treffer_laenge = len(str(teil))
            break

    # Bekannte Zwischenspeicher nach Ordnername (der nächstliegende gewinnt)
    for teil in [pfad, *pfad.parents]:
        if not _ist_unter(teil, HOME) or teil == HOME:
            break
        hinweis = config.GEFAHRLOS_NAMEN.get(teil.name.lower())
        if hinweis:
            if len(str(teil)) > treffer_laenge:
                treffer_stufe, treffer_hinweis, treffer_laenge = "gefahrlos", hinweis, len(str(teil))
            break

    if treffer_stufe == "entscheidung" and not treffer_hinweis:
        treffer_hinweis = "Deine eigenen Dateien. Die App entscheidet das nicht für dich."
    return treffer_stufe, treffer_hinweis


def stufe_fuer_ordner(pfad: Path, gesamt_bytes: int, eigene_bytes: int,
                      eigene_beispiel: str = "", regel: tuple = None) -> tuple:
    """Stufe eines Ordners — mit Blick auf den Inhalt.

    Ein Ordner heißt „Cache“, enthält aber 38 GB eigene Videos: Dann ist er
    keine gefahrlose Sache, sondern „Ihre Entscheidung“. Nie nach dem Namen
    allein entscheiden.
    """
    stufe, hinweis = regel or regel_fuer(pfad)
    if stufe != "gefahrlos":
        return stufe, hinweis
    anteil = (eigene_bytes / gesamt_bytes) if gesamt_bytes else 0
    viel = eigene_bytes >= config.SPEICHER_EIGENE_SCHWELLE_BYTES
    anteilig = anteil >= config.SPEICHER_EIGENE_SCHWELLE_ANTEIL and eigene_bytes > 0
    if viel or anteilig:
        beispiel = f" (z. B. {eigene_beispiel})" if eigene_beispiel else ""
        return "entscheidung", (
            f"Sieht nach Zwischenspeicher aus, enthält aber {lesbar(eigene_bytes)} "
            f"eigene Fotos, Videos, Musik oder Dokumente{beispiel}. Bitte selbst ansehen."
        )
    return "gefahrlos", hinweis


def _paket_regel(pfad: Path):
    """Für Pakete (.app, .photoslibrary …) gilt die Regel des Pakets selbst."""
    hinweis = config.NICHT_ANFASSEN_PAKETE.get(pfad.suffix.lower())
    return ("tabu", hinweis) if hinweis else None


def stufe_fuer_datei(pfad: Path, groesse: int, regel: tuple = None) -> tuple:
    """Stufe einer einzelnen Datei. Eine eigene Datei bleibt eine eigene Datei,
    auch wenn sie in einem Ordner namens „Cache“ liegt.

    `regel` ist die schon bekannte Regel des Ordners, in dem die Datei liegt —
    beim Scan spart das eine Prüfung je Datei.
    """
    stufe, hinweis = regel or regel_fuer(pfad)
    if stufe == "gefahrlos" and _ist_eigene_datei(pfad.name, groesse):
        return "entscheidung", (
            "Liegt in einem Zwischenspeicher, ist aber eine eigene Datei. Bitte selbst ansehen."
        )
    return stufe, hinweis


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
    """Legt eine Datei oder einen Ordner in den Papierkorb.

    Rückgabe: der Pfad im Papierkorb (für „Rückgängig“) oder None.
    Es wird nicht selbst nach `~/.Trash` verschoben — nur was der Finder bzw.
    `/usr/bin/trash` dorthin legt, lässt sich später „Zurücklegen“.
    """
    pfad = Path(pfad)
    try:
        if not pfad.exists() and not pfad.is_symlink():
            return None
    except OSError:
        return None

    # 1. /usr/bin/trash (ab macOS 15) — meldet mit -v, wohin es gelegt wurde
    if Path("/usr/bin/trash").is_file():
        try:
            res = subprocess.run(
                ["/usr/bin/trash", "-v", str(pfad)],
                capture_output=True, text=True, timeout=120, check=False,
            )
            if res.returncode == 0 and not pfad.exists():
                ziel = _trash_pfad_aus_meldung(res.stdout)
                return ziel or str(HOME / ".Trash" / pfad.name)
        except Exception:
            pass

    # 2. Finder (fragt beim ersten Mal nach Erlaubnis und nennt das Ziel)
    try:
        maskiert = str(pfad).replace("\\", "\\\\").replace('"', '\\"')
        res = subprocess.run(
            ["osascript",
             "-e", f'tell application "Finder" to set abgelegt to delete (POSIX file "{maskiert}")',
             "-e", "POSIX path of (abgelegt as alias)"],
            capture_output=True, text=True, timeout=180, check=False,
        )
        if res.returncode == 0 and not pfad.exists():
            ziel = res.stdout.strip().splitlines()[-1].strip() if res.stdout.strip() else ""
            return ziel.rstrip("/") or str(HOME / ".Trash" / pfad.name)
    except Exception:
        pass

    # 3. Letzter Ausweg: selbst nach ~/.Trash verschieben. Das braucht weder
    #    `trash` (erst ab macOS 15) noch die Erlaubnis, den Finder zu steuern.
    #    „Zurücklegen“ im Finder funktioniert damit nicht — „Rückgängig“ im
    #    Programm schon, denn der Zielpfad steht im Protokoll.
    try:
        papierkorb = HOME / ".Trash"
        if papierkorb.is_dir():
            ziel = papierkorb / pfad.name
            if ziel.exists():
                stempel = datetime.now().strftime("%H%M%S")
                ziel = papierkorb / f"{pfad.stem}_{stempel}{pfad.suffix}"
            shutil.move(str(pfad), str(ziel))
            return str(ziel)
    except Exception:
        pass
    return None


def _trash_pfad_aus_meldung(ausgabe: str):
    """Aus `# Moved "…" to "/Users/…/.Trash/…"` den Zielpfad ziehen."""
    for zeile in reversed((ausgabe or "").strip().splitlines()):
        if '" to "' in zeile:
            try:
                return zeile.rsplit('" to "', 1)[1].rstrip('"').rstrip("/")
            except Exception:
                return None
    return None


def hole_aus_papierkorb(im_papierkorb: Path, zurueck_nach: Path) -> bool:
    """Holt einen Eintrag aus dem Papierkorb an seinen alten Platz zurück.

    Über den Finder, weil `~/.Trash` ohne „Festplattenvollzugriff“ für die App
    gesperrt ist — der Finder darf es immer.
    """
    im_papierkorb, zurueck_nach = Path(im_papierkorb), Path(zurueck_nach)
    if zurueck_nach.exists():
        return False  # am Ursprungsort liegt schon wieder etwas — nichts überschreiben
    zurueck_nach.parent.mkdir(parents=True, exist_ok=True)
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


def papierkorb_leeren() -> dict:
    """Leert den Papierkorb über den Finder. Das ist nicht rückgängig zu machen."""
    vorher = papierkorb_info()
    _PAPIERKORB_GEMERKT["wert"] = None
    try:
        res = subprocess.run(
            ["osascript", "-e", 'tell application "Finder" to empty trash'],
            capture_output=True, text=True, timeout=600, check=False,
        )
    except Exception as exc:
        raise SpeicherFehler(f"Der Papierkorb konnte nicht geleert werden: {exc}")
    if res.returncode != 0:
        meldung = (res.stderr or "").strip().splitlines()
        raise SpeicherFehler(
            "Der Papierkorb konnte nicht geleert werden: "
            + (meldung[-1] if meldung else "Der Finder hat abgelehnt.")
        )
    return {"vorher_bytes": vorher.get("bytes", 0), "vorher_anzahl": vorher.get("anzahl", 0)}


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
                    stufe, hinweis = stufe_fuer_datei(kind, p_belegt, regel=paket_regel)
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

            stufe, hinweis = stufe_fuer_datei(kind, st.st_size, regel=regel)
            self._merke_grosse_datei(kind, groesse, st, stufe=(stufe, hinweis))
            datei_liste.append({
                "name": eintrag.name, "pfad": str(kind), "bytes": groesse,
                "geaendert": _zeit(st.st_mtime), "art": _art_nach_endung(eintrag.name),
                "versteckt": eintrag.name.startswith("."), "paket": False,
                "stufe": stufe, "hinweis": hinweis,
            })

        stufe, hinweis = stufe_fuer_ordner(pfad, belegt, eigene_bytes, eigene_beispiel, regel=regel)

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
        stufe, hinweis = stufe or stufe_fuer_datei(pfad, groesse)
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
# Freigeben: Vorschau, Papierkorb, endgültig löschen
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

    if _ist_unter(echt, HOME / ".Trash"):
        raise SpeicherFehler(
            "Das liegt schon im Papierkorb. Oben im Reiter leerst du ihn mit „Papierkorb leeren“."
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
    if modus not in ("papierkorb", "endgueltig"):
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
        gemessen = messe(ziel)
        if ziel.is_dir() and not ist_paket(ziel):
            stufe, hinweis = stufe_fuer_ordner(ziel, gemessen["bytes"],
                                               gemessen["eigene_bytes"], gemessen["eigene_beispiel"])
        else:
            stufe, hinweis = stufe_fuer_datei(ziel, gemessen["bytes"])
        if stufe == "tabu":
            raise SpeicherFehler(f"„{ziel.name}“ gehört zu „Nicht anfassen“: {hinweis}")
        if modus == "endgueltig" and stufe != "gefahrlos":
            braucht_bestaetigung = True
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
            "ziel": "Papierkorb" if modus == "papierkorb" else "endgültig gelöscht",
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
        "papierkorb_hinweis": (
            "Der Platz wird erst frei, wenn der Papierkorb geleert ist."
            if modus == "papierkorb" else
            "Endgültig gelöscht: Das lässt sich nicht rückgängig machen."
        ),
    }


def freigeben(pfade, modus: str = "papierkorb", bestaetigt: bool = False) -> dict:
    """Legt die Auswahl in den Papierkorb oder löscht sie endgültig.

    Jede Aktion kommt ins Protokoll (`manifest_*.json` im Verlauf). Was im
    Papierkorb liegt, holt „Rückgängig“ zurück; endgültig Gelöschtes steht mit
    dem Vermerk „nicht wiederherstellbar“ im Protokoll.
    """
    plan = vorschau(pfade, modus)
    if modus == "endgueltig" and plan["braucht_bestaetigung"] and not bestaetigt:
        raise SpeicherFehler(
            f"Endgültiges Löschen eigener Dateien braucht eine Bestätigung: "
            f"{plan['gesamt_dateien']} Dateien, {plan['gesamt_lesbar']}."
        )

    jetzt = datetime.now()
    aktionen = []
    freigegeben = 0
    fehlgeschlagen = []

    for eintrag in plan["eintraege"]:
        ziel = Path(eintrag["pfad"])
        if modus == "papierkorb":
            im_papierkorb = in_papierkorb(ziel)
            if not im_papierkorb:
                fehlgeschlagen.append({"pfad": str(ziel),
                                       "grund": "Der Papierkorb hat es nicht angenommen."})
                continue
            aktionen.append({
                "source": str(ziel), "target": im_papierkorb, "copy_mode": False,
                "aktion": "papierkorb", "bytes": eintrag["bytes"],
                "dateien": eintrag["dateien"], "stufe": eintrag["stufe"],
                "wiederherstellbar": True, "timestamp": datetime.now().isoformat(),
            })
        else:
            try:
                if ziel.is_dir() and not ziel.is_symlink():
                    shutil.rmtree(ziel)
                else:
                    ziel.unlink()
            except OSError as exc:
                fehlgeschlagen.append({"pfad": str(ziel), "grund": exc.strerror or str(exc)})
                continue
            aktionen.append({
                "source": str(ziel), "target": "", "copy_mode": False,
                "aktion": "endgueltig", "bytes": eintrag["bytes"],
                "dateien": eintrag["dateien"], "stufe": eintrag["stufe"],
                "wiederherstellbar": False, "timestamp": datetime.now().isoformat(),
            })
        freigegeben += eintrag["bytes"]

    _PAPIERKORB_GEMERKT["wert"] = None  # der Papierkorb ist jetzt ein anderer

    manifest_name = ""
    if aktionen:
        config.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        datei = config.HISTORY_DIR / f"manifest_{jetzt.strftime('%Y%m%d_%H%M%S')}.json"
        wohin = "in den Papierkorb" if modus == "papierkorb" else "endgültig gelöscht"
        stueck = "1 Eintrag" if len(aktionen) == 1 else f"{len(aktionen)} Einträge"
        with open(datei, "w", encoding="utf-8") as f:
            json.dump({
                "created_at": jetzt.isoformat(),
                "quelle": "speicherplatz",
                "beschreibung": f"Speicherplatz: {lesbar(freigegeben)} {wohin} ({stueck})",
                "total_actions": len(aktionen),
                "rueckgaengig": modus == "papierkorb",
                "actions": aktionen,
            }, f, indent=2, ensure_ascii=False)
        manifest_name = datei.name

    return {
        "modus": modus,
        "erledigt": len(aktionen),
        "bytes": freigegeben,
        "lesbar": lesbar(freigegeben),
        "manifest": manifest_name,
        "fehlgeschlagen": fehlgeschlagen,
        "hinweis": plan["papierkorb_hinweis"],
    }
