# Was an Datei-Funktionen noch möglich ist

Stand: 19.11.2026, erstellt zusammen mit dem Reiter „Speicherplatz“. Grundlage: der
vorhandene Code, die macOS-Bordmittel, die sich ohne Administratorrechte nutzen lassen,
und ein Blick darauf, was andere Mac-Programme in diesem Feld anbieten.

## Was das Programm heute kann

Katalog mit Prüfsummen und ähnlichen Fotos · Texterkennung und KI-Umbenennung ·
Ordnungssystem mit Eingang, Projekten, Ablage, Archiv · Finder-Tags und Steuer-Kennzeichen ·
Autopilot · Sicherung (Spiegel, ZIP, Nextcloud) · Speicherplatz · Protokoll mit Rückgängig.

Die Lücke, die sich daraus ergibt: Das Programm weiß viel über **einzelne** Dateien, aber
wenig über ihre **Nutzung über die Zeit** (wann zuletzt geöffnet, wie schnell wächst ein
Ordner) und es kann Platz bisher nur durch **Löschen** sparen, nicht durch Verkleinern,
Archivieren oder Auslagern.

## Empfehlung: die nächsten drei

| # | Funktion | Warum zuerst |
| --- | --- | --- |
| 1 | Installationsdateien, deren Programm schon installiert ist | Kleinster Aufwand, sofort sichtbarer Nutzen, null Risiko |
| 2 | „Lange nicht geöffnet“ | Beantwortet die Frage, die nach dem Speicherplatz-Scan als nächste kommt |
| 3 | Cloud-Dateien lokal entfernen | Gibt oft zweistellige GB frei, **ohne** dass etwas gelöscht wird |

---

## 1. Direkt am Speicherplatz angebaut

### 1.1 Installationsdateien, deren Programm schon installiert ist
`.dmg`, `.pkg`, `.zip` in Downloads mit `/Applications` und `~/Applications` abgleichen
(Name und Version aus dem Dateinamen). Treffer: „Programm X ist installiert – die
Installationsdatei (1,2 GB) wird nicht mehr gebraucht.“
*Aufwand gering · Risiko gering · passt als Zusatzliste in den Reiter Speicherplatz.*

### 1.2 „Lange nicht geöffnet“
Spotlight liefert mit `mdfind 'kMDItemLastUsedDate < $time.now(-2592000)'` alle Dateien,
die seit 30 Tagen (oder zwei Jahren) niemand geöffnet hat. Zusammen mit der Größe ergibt
das die Liste „groß und alt“ – die ehrlichste Grundlage fürs Ausmisten.
**Vorsicht:** Das Merkmal fehlt bei Dateien, die nie geöffnet wurden (etwa reine
Downloads); dort muss das Änderungsdatum einspringen. Das sagt die Oberfläche besser
dazu, statt „nie benutzt“ zu behaupten.
*Aufwand mittel · Risiko gering, solange nichts automatisch passiert.*

### 1.3 Cloud-Dateien lokal entfernen statt löschen
iCloud Drive, Dropbox und OneDrive halten Kopien auf der Platte. macOS kann sie
freigeben („Jetzt entfernen“), die Datei bleibt in der Cloud und lädt bei Bedarf neu.
Das Programm hat mit `bin/icloud_download` schon die Gegenrichtung.
Das wäre die einzige Funktion, die Platz schafft, **ohne** dass etwas verloren gehen kann.
*Aufwand mittel · Risiko gering · eigene vierte Stufe „Auslagern“ im Speicherplatz-Reiter.*

### 1.4 Aufräumen im Kleinen
Leere Ordner, 0-Byte-Dateien, defekte Verknüpfungen und Aliase, `.DS_Store`-Flut,
Bildschirmfotos auf dem Schreibtisch (nach Monat gruppiert).
Bringt wenig Platz, aber sichtbare Ordnung – und passt in die vorhandene Vorschau-Logik.
*Aufwand gering.*

### 1.5 Entwickler-Aufräumen
Alle Projektordner auflisten, die ein `node_modules`, `.next`, `DerivedData` oder
`.gradle` enthalten **und** seit Monaten nicht angefasst wurden – auf einen Streich
freigeben. Genau der Fall, der die Aufräumaktion ausgelöst hat (30 GB `.turbo`).
*Aufwand gering, baut vollständig auf `speicher.py` auf.*

### 1.6 Speicher-Verlauf
Nach jedem Scan Datum, Ordner und Summe in den Verlauf schreiben. Daraus: „Downloads ist
seit letzter Woche um 8 GB gewachsen“, „der Papierkorb belegt 12 GB“ – als Hinweis beim
Start oder im Autopilot, nie als automatische Löschung.
*Aufwand gering · der Autopilot bleibt wie bisher ohne Löschrechte.*

### 1.7 Lokale Time-Machine-Schnappschüsse
`tmutil listlocalsnapshots /` zeigt sie; sie belegen oft zweistellige GB und tauchen im
Finder nirgends auf. Löschen verlangt Administratorrechte, gehört also in die Stufe
„Nicht anfassen“ – anzeigen und erklären, wo man es macht.
*Aufwand gering · nur Anzeige.*

## 2. Platz sparen, ohne zu löschen

### 2.1 Alte Ordner als ZIP archivieren
`backup.py` kann bereits ZIP. Daraus wird: „Projekt 2019 (4,2 GB) archivieren → 900 MB,
Original in den Papierkorb.“ Mit Vorschau und Manifest, also rückgängig zu machen.
*Aufwand gering bis mittel · hoher Nutzen bei abgeschlossenen Projekten.*

### 2.2 Fotos und Videos verkleinern
Bilder gehen mit dem mitgelieferten `sips` (Größe ändern, HEIC/JPEG). Videos bräuchten
ein kleines natives Werkzeug auf AVFoundation-Basis – so, wie `bin/vision_ocr` schon
gebaut ist. Regel: das Original wandert in den Papierkorb, nie überschreiben, und die
eingesparte Größe wird vorher angezeigt.
*Aufwand hoch (Video) · Risiko Qualitätsverlust, deshalb immer mit Vorher/Nachher.*

## 3. Finden und Ordnen

### 3.1 Spotlight-Suche im Programm
`mdfind` nach Finder-Tags (`Steuer 2025`), Dateiart und Zeitraum – auch außerhalb des
Ordnungssystems. Die Tags setzt das Programm ohnehin schon; sie wieder zu finden ist
heute Sache des Finders.
*Aufwand gering · passt in den Reiter Steuer oder als eigene Suche.*

### 3.2 Zeitstempel aus dem Foto übernehmen
`extractor.py` liest das EXIF-Aufnahmedatum bereits. Es als Änderungs-/Erstelldatum zu
setzen, bringt Fotos aus WhatsApp, Downloads und Scans in die richtige Reihenfolge.
*Aufwand gering · rückgängig über das Manifest (alte Zeiten mitschreiben).*

### 3.3 Serien-Umbenennen nach Regeln, ohne KI
Suchen/Ersetzen, Nummerieren, Datum voranstellen – für die Fälle, in denen die KI nichts
beitragen kann. Spart Credits und ist sofort erklärbar.
*Aufwand gering.*

### 3.4 Duplikate über mehrere Orte
Heute sucht der Katalog je Ordner. Mehrere Ordner und eine externe Platte zugleich, mit
der Regel „das Original im Ordnungssystem bleibt“, träfe den echten Fall: dieselben Fotos
auf Platte, in iCloud und im Backup-Ordner.
*Aufwand mittel.*

## 4. Verlässlichkeit

### 4.1 Sicherung gegen das Original prüfen
Prüfsummen zwischen Quelle und Spiegel vergleichen und melden, was fehlt oder sich
unbemerkt geändert hat. Eine Sicherung, die nie geprüft wurde, ist nur eine Vermutung.
*Aufwand mittel · passt zu `backup.py`.*

### 4.2 Beschädigte Dateien erkennen
0 Byte große Medien, nicht lesbare PDFs, abgebrochene Downloads (`.download`,
`.crdownload`). Beim Katalogisieren ohnehin fast umsonst zu haben.
*Aufwand gering.*

## Was bewusst draußen bleiben sollte

- **Automatisches Löschen** durch den Autopiloten – auch bei „gefahrlos“. Ein Hinweis
  genügt.
- **Systempflege mit Administratorrechten** (Caches außerhalb des Benutzerordners,
  Schnappschüsse, Simulatoren). Anzeigen ja, anfassen nein; dafür gibt es Xcode und die
  Systemeinstellungen.
- **„Systemdaten“ aufräumen** als Werbeversprechen. Was dort liegt, gehört macOS, und die
  Rubrik ist bei Apple selbst nicht klar abgegrenzt.

## Quellen

- [Macwelt: macOS 27, Speicher voll – Platz schaffen](https://www.macwelt.de/article/3229969/macos-27-speicher-voll-platz-schaffen.html)
- [Setapp: Mac-Systemdaten bereinigen](https://setapp.com/de/so-gehts/mac-systemdaten-bereinigen)
- [Dr. Buho: Mac bereinigen mit Bordmitteln](https://www.drbuho.com/de/how-to/clean-up-mac-with-built-in-tools)
- [AppleInsider: Best Mac disk space analyzer apps](https://appleinsider.com/inside/mac/best/best-mac-disk-space-analyzer-apps)
- [myunix: mdfind-Leitfaden zu Spotlight im Terminal](https://myunix.org/macos/macos-spotlight-terminal/)
- [orsolabs: kMDItemLastUsedDate bei heruntergeladenen Dateien](https://orsolabs.dev/filebo/guides/find-recently-downloaded-files-mac/)
- [MacScripter: Zuletzt-geöffnet-Datum auslesen](https://www.macscripter.net/t/get-last-opened-date-of-the-file/74522)
