"""Sicherheitsregressionen mit synthetischen Programmen, Profilen und Papierkorb."""
import json
import os
import plistlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class WartungTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Vor dem Import eine leere .env anlegen, damit keine lokale .env migriert wird.
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        Path(temp.name, ".env").touch()
        umgebung = patch.dict(os.environ, DATEIEN_AKTIONEN_DATA_DIR=temp.name, AI_PROVIDER="offline")
        umgebung.start()
        cls.addClassCleanup(umgebung.stop)
        global wartung, speicher
        import wartung
        import speicher

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.heim = Path(temp.name).resolve()
        self.app = self.heim / "Applications/Browser.app"
        self.kennung = "com.google.Chrome"
        info = self.app / "Contents/Info.plist"
        info.parent.mkdir(parents=True)
        info.write_bytes(plistlib.dumps({"CFBundleIdentifier": self.kennung, "CFBundlePackageType": "APPL"}))
        self.library = self.heim / "Library"
        self.cache = self.library / "Application Support/Google/Chrome/Default/GPUCache"
        self.cache.mkdir(parents=True)
        for name, magic in (("index", 0xc103cac3), ("data_0", 0xc104cac3)):
            (self.cache / name).write_bytes(magic.to_bytes(4, "little"))
        self.db = self.library / "Caches" / self.kennung / "Cache.db"
        self.db.parent.mkdir(parents=True)
        conn = sqlite3.connect(self.db)
        for tabelle in ("response", "receiver_data", "blob_data"):
            conn.execute("CREATE TABLE cfurl_cache_" + tabelle + " (entry_ID INTEGER)")
        conn.close()
        self.laufende = set()
        self.apps = [{"pfad": str(self.app)}]
        self.papierkorb = self.heim / "Papierkorb"
        self.papierkorb.mkdir()
        for obj, feld, wert in (
            (speicher, "HOME", self.heim),
            (speicher, "installierte_programme", lambda: self.apps),
            (wartung, "_laufende", lambda: self.laufende),
            (speicher, "in_papierkorb", lambda p: p.rename(self.papierkorb / p.name)),
            (speicher.config, "HISTORY_DIR", self.heim / "Verlauf"),
        ):
            ersatz = patch.object(obj, feld, wert)
            ersatz.start()
            self.addCleanup(ersatz.stop)

    def test_cache_neu_pruefen(self):
        params = {"modus": "cache"}
        plan = wartung.bearbeite(params)["eintraege"]
        self.assertEqual({z["pfad"] for z in plan}, {str(self.db), str(self.cache)})
        params["auswahl"] = [z["id"] for z in plan]
        (self.cache / "Projekt.txt").touch()
        with self.assertRaises(speicher.SpeicherFehler):
            wartung.bearbeite(params)
        self.assertTrue(self.db.exists())
        self.assertFalse(any(self.papierkorb.iterdir()))

    def test_begleitdateien_links_laufende_apps(self):
        (self.db.parent / "Cache.db-wal").touch()
        (self.cache / "data_1").symlink_to(self.db)
        self.assertEqual(wartung.bearbeite({"modus": "cache"})["eintraege"], [])
        self.laufende.add(self.kennung.lower())
        with self.assertRaises(speicher.SpeicherFehler):
            wartung.bearbeite({"modus": "app", "app": self.kennung.lower()})

    def test_deinstallation_und_manifest(self):
        prefs = self.library / "Preferences" / (self.kennung + ".plist")
        prefs.parent.mkdir()
        prefs.touch()
        gruppe = self.library / "Group Containers" / self.kennung
        gruppe.mkdir(parents=True)
        params = {"modus": "app", "app": self.kennung.lower()}
        zeilen = wartung.bearbeite(params)["eintraege"]
        self.assertNotIn(str(gruppe), [z["pfad"] for z in zeilen])
        params["auswahl"] = [z["id"] for z in zeilen if z["pfad"] in (str(self.app), str(prefs))]
        res = wartung.bearbeite(params)
        self.assertEqual(res["erledigt"], 2)
        manifest = json.loads((speicher.config.HISTORY_DIR / res["manifest"]).read_text())
        self.assertEqual({a["source"] for a in manifest["actions"]}, {str(self.app), str(prefs)})
        self.assertTrue(all(Path(a["target"]).exists() for a in manifest["actions"]))
        self.assertTrue(gruppe.exists() and self.db.exists())
        with self.assertRaises(speicher.SpeicherFehler):
            wartung.bearbeite(params)

    def test_geaenderte_programmdaten(self):
        datei = self.library / "Application Support" / self.kennung / "Projekte" / "Entwurf.txt"
        datei.parent.mkdir(parents=True)
        datei.write_text("Erste Fassung")
        params = {"modus": "app", "app": self.kennung.lower()}
        plan = wartung.bearbeite(params)
        params["auswahl"] = [z["id"] for z in plan["eintraege"]]
        datei.write_text("Zweite Fassung")
        with self.assertRaises(speicher.SpeicherFehler):
            wartung.bearbeite(params)
        self.assertTrue(self.app.exists() and datei.exists())

    def test_deinstallierer_des_herstellers(self):
        helfer = self.app / "Contents/Resources/Uninstall.app"
        helfer.mkdir(parents=True)
        plan = wartung.bearbeite({"modus": "app", "app": self.kennung.lower()})
        self.assertEqual(plan["eintraege"], [])
        self.assertIn(str(helfer), plan["hinweise"][0])

    def test_papierkorb_leeren_braucht_bestaetigung(self):
        with patch.object(speicher.subprocess, "run") as finder:
            for wert in (None, False, 1, "true"):
                with self.assertRaises(speicher.SpeicherFehler):
                    speicher.papierkorb_leeren(wert)
            finder.assert_not_called()
            finder.return_value.returncode = 0
            self.assertIn("geleert", speicher.papierkorb_leeren(True)["meldung"])
            finder.assert_called_once()

    def test_finder_verweigert_leeren(self):
        with patch.object(speicher.subprocess, "run") as finder:
            finder.return_value.returncode = 1
            finder.return_value.stderr = "Apple events not permitted (-1743)"
            with self.assertRaisesRegex(speicher.SpeicherFehler, "Automation"):
                speicher.papierkorb_leeren(True)

    def test_deinstallation_meldet_grund_und_stoppt(self):
        params = {"modus": "app", "app": self.kennung.lower()}
        zeilen = wartung.bearbeite(params)["eintraege"]
        params["auswahl"] = [z["id"] for z in zeilen]
        with patch.object(speicher, "in_papierkorb", side_effect=speicher.SpeicherFehler("Zugriff verweigert (-54)")) as bewegen:
            res = wartung.bearbeite(params)
        bewegen.assert_called_once_with(self.app)
        self.assertEqual(res["erledigt"], 0)
        self.assertEqual(res["fehlgeschlagen"], [{"pfad": str(self.app), "grund": "Zugriff verweigert (-54)"}])

    def test_gesperrte_auswahl(self):
        with self.assertRaises(speicher.SpeicherFehler):
            wartung.bearbeite({"modus": "cache", "auswahl": [str(self.heim)]})
        with self.assertRaises(speicher.SpeicherFehler):
            speicher.freigeben([str(self.db)], "endgueltig", True)
        geheim = self.library / "Keychains/Cache"
        with patch.object(speicher, "_NICHT_ANFASSEN_PFADE", [(self.library, "Geschützt")]):
            self.assertEqual(speicher.regel_fuer(geheim)[0], "tabu")
        self.apps.extend(self.apps.copy())
        self.assertEqual(wartung.bearbeite({"modus": "programme"})["programme"], [])


if __name__ == "__main__":
    unittest.main()
