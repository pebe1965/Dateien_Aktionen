# Aufgabe: Speicherplatz – große Dateien und Ordner finden und löschen

Stand: 17.11.2026. Entstanden aus einer Aufräumaktion von Hand: Die Platte war fast voll (15 GB frei von 460 GB),
die Ursachen ließen sich nur über das Terminal finden. Das soll die App selbst können.

## Ziel

Ein neuer Reiter „Speicherplatz“: Der Benutzer sieht, was auf seiner Platte den Platz belegt, und kann es dort
direkt freigeben – ohne Terminal und ohne zu raten, was gefahrlos ist.

## Was bei der Aufräumaktion aufgefallen ist

Diese Fälle muss die Funktion abdecken, sonst hilft sie nicht:

| Fund | Größe | Lehre |
|---|---|---|
| `.turbo/cache` in einem Projekt | 30 GB | Versteckte Ordner mitzählen. Im Finder war davon nichts zu sehen. |
| `.next` in zwei Projekten | 6,7 GB | Build-Ausgaben lassen sich gefahrlos löschen und bauen sich neu auf. |
| `~/Movies/CapCut/User Data/Cache/ImportMedias` | 38 GB | Heißt „Cache“, enthält aber die einzigen Kopien eigener Videos. Nie nach dem Namen entscheiden. |
| iOS-Simulatoren unter `/Library/Developer/CoreSimulator` | 53 GB | Liegt außerhalb des Benutzerordners; löschen nur über Xcode, nicht über die App. |
| `~/Library/Application Support/<Programm>` | 14 GB (Claude) | Programmdaten zeigen, aber nicht zum Löschen anbieten. |
| Finder meldete für den Ordner 189 GB, gemessen waren es 48 GB | – | Größen selbst messen und sagen, wie gemessen wurde. |

## Umfang

### 1. Analyse

- Startordner wählbar; Vorschläge: Benutzerordner, Downloads, Schreibtisch, Filme, ein frei gewählter Ordner.
- Anzeige oben: Platte gesamt, belegt, frei (wie `df`).
- Ergebnis als Baum oder Liste, nach Größe sortiert: Ordner mit ihrer Gesamtgröße, darunter aufklappbar die
  größten Unterordner und Dateien. Versteckte Ordner zählen mit und sind als solche gekennzeichnet.
- Zweite Ansicht „Größte Dateien“: flache Liste ab einer einstellbaren Mindestgröße (Vorschlag 100 MB) mit Pfad,
  Größe, letzter Änderung und Art.
- Der Scan läuft im Hintergrund mit Fortschritt und lässt sich abbrechen. Ordner ohne Leserecht werden übersprungen
  und am Ende genannt, nicht stillschweigend ausgelassen.
- macOS-Pakete (`.photoslibrary`, `.app`, `.fcpbundle` …) zählen als eine Einheit, wie schon im Katalog.

### 2. Einordnung

Jeder Fund bekommt eine von drei Stufen, damit der Benutzer nicht raten muss:

- **Gefahrlos:** bekannte Zwischenspeicher, die sich von selbst neu aufbauen. Feste Liste nach Ordnernamen *und*
  Lage, zum Start: `node_modules`, `.next`, `.turbo`, `.pio`, `__pycache__`, `.gradle`, `DerivedData`,
  `~/.npm`, `~/.cache`, `~/Library/Caches/*`, Papierkorb.
- **Ihre Entscheidung:** eigene Dateien – Videos, Bilder, Archive, Downloads, alte Installationsdateien (`.dmg`,
  `.zip`, `.pkg`).
- **Nicht anfassen:** Systemordner, `~/Library/Application Support`, Fotomediatheken, alles außerhalb des
  Benutzerordners. Wird angezeigt, aber ohne Knopf zum Löschen; stattdessen ein Hinweis, wo man es aufräumt
  (z. B. Simulatoren in Xcode).

Ein Ordner gilt nur dann als „gefahrlos“, wenn er keine Medien- oder Dokumentdateien enthält. Der CapCut-Fall
(Videos im Ordner „Cache“) muss als „Ihre Entscheidung“ erscheinen.

### 3. Freigeben

- Auswahl per Haken, darunter die Summe „X GB werden frei“.
- Standard ist **In den Papierkorb**. Der Hinweis dazu: Platz wird erst frei, wenn der Papierkorb geleert ist.
- **Endgültig löschen** nur für die Stufe „Gefahrlos“ oder nach einer zweiten Bestätigung, die Zahl und Größe der
  Dateien nennt.
- Vor dem Löschen eine Vorschau wie beim Umbenennen (Dry-Run): was, wie viel, wohin.
- Jede Aktion kommt ins Protokoll (`manifest.json`). Was im Papierkorb liegt, lässt sich mit „Rückgängig“
  zurückholen; endgültig Gelöschtes steht mit dem Vermerk „nicht wiederherstellbar“ im Protokoll.
- Knopf „Im Finder zeigen“ an jedem Fund, damit man vor dem Löschen hineinschauen kann.

## Nicht Teil der Aufgabe

- Löschen außerhalb des Benutzerordners oder mit Administratorrechten.
- Automatisches Löschen durch den Autopiloten. Denkbar wäre später nur ein Hinweis („Der Papierkorb belegt 12 GB“).
- Duplikate – die gibt es schon im Katalog. Die neue Ansicht darf auf sie verweisen.

## Umsetzung – Anhaltspunkte

- Größen messen: `os.scandir` rekursiv mit `st_blocks * 512` (belegter Platz, nicht die Länge der Datei); Hardlinks
  nur einmal zählen; symbolischen Links nicht folgen; nicht über die Grenze des Volumes hinaus.
- Papierkorb: über den Finder (`NSFileManager trashItemAtURL` bzw. AppleScript), nicht durch Verschieben nach
  `~/.Trash` – nur so funktioniert „Zurücklegen“.
- Die Liste der gefahrlosen Ordner gehört als Daten in `config.py`, nicht verstreut in den Code.
- Ohne die Freigabe „Festplattenvollzugriff“ sieht die App Teile des Benutzerordners nicht. Das beim ersten Scan
  erkennen und erklären.
- Oberfläche wie die übrigen Reiter in `templates/index.html`, Logik in einem eigenen Modul (z. B. `speicher.py`),
  Endpunkte in `gui.py`.
- Handbuch (`Handbuch_Dateien_Aktionen.md`) um ein Kapitel ergänzen, README-Highlights anpassen.

## Fertig, wenn

1. Ein Scan des Benutzerordners die oben genannten Funde zeigt, richtig eingeordnet.
2. Ein Testordner mit einem `node_modules` und einem Video-Ordner namens `Cache` ergibt: das eine „gefahrlos“, das
   andere „Ihre Entscheidung“.
3. In den Papierkorb gelegte Dateien lassen sich über das Protokoll zurückholen.
4. Endgültiges Löschen ohne zweite Bestätigung ist nur bei „gefahrlos“ möglich.
5. Die angezeigte Größe eines Testordners stimmt mit `du -sk` überein.
6. Abbrechen eines laufenden Scans hinterlässt keinen hängenden Prozess.

## Offene Fragen an Peter

- Soll „Endgültig löschen“ für eigene Dateien überhaupt angeboten werden, oder immer nur der Papierkorb?
- Soll der Reiter den Papierkorb selbst leeren können?
- Mindestgröße für „Größte Dateien“: 100 MB als Standard recht?
