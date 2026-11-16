# Handbuch Dateien_Aktionen

Dateien_Aktionen ist ein Programm für den Mac, das Ordner aufräumt: Es liest Dateien ein, erkennt ihren Inhalt, schlägt sinnvolle Namen und Ordner vor, findet doppelte Dateien, hält ein festes Ordnungssystem ein und sichert deine Daten. Vor jeder Änderung siehst du eine Vorschau, und fast alles lässt sich rückgängig machen.

Dieses Handbuch erklärt jede Funktion Schritt für Schritt. Über das Suchfeld oben findest du Abschnitte nach Stichwort.

## 1. Überblick

### Was das Programm kann

| Bereich | Wozu |
| --- | --- |
| Dateikatalog | Verschafft dir den Überblick über einen Ordner: was liegt darin, wie viel, wie alt |
| Duplikate-Manager | Findet doppelte Dateien und optisch ähnliche Fotos |
| KI-Umbenennung & Vorschau | Liest Dokumente und Bilder, schlägt Namen und Zielordner vor |
| Ordnungssystem | Vier feste Bereiche: Eingang, Projekte, Ablage, Archiv |
| Projekte | Laufende Vorhaben mit oder ohne Termin |
| Steuer | Alle steuerrelevanten Belege eines Jahres auf einen Blick |
| Autopilot | Sortiert neue Dateien automatisch im Hintergrund |
| Sicherung | Sichert Ordner auf Festplatte, NAS oder in die Cloud |
| Protokoll & Rückgängig | Nimmt frühere Aktionen zurück |

### Die drei Grundsätze

1. **Erst Vorschau, dann Änderung.** Das Programm benennt nichts um und verschiebt nichts, bevor du es gesehen und bestätigt hast. Ausnahme ist der Autopilot, den du bewusst einschaltest.
2. **Rückgängig.** Jede Umbenennung und Verschiebung wird protokolliert und lässt sich mit einem Klick zurücknehmen.
3. **Gelöscht wird nur in den Papierkorb.** Was du im Programm löschst, liegt danach im Papierkorb des Mac und lässt sich dort zurückholen.

## 2. Erste Schritte

### Installieren

1. Die Datei `Dateien_Aktionen.dmg` öffnen.
2. Das Programmsymbol in den Ordner „Programme“ ziehen. Bei einer Nachfrage „Ersetzen“ wählen.
3. Das Programm aus „Programme“ starten. Beim ersten Start fragt der Mac eventuell nach, ob du das Programm öffnen willst.

Updates installierst du meist direkt im Programm (siehe Kapitel 15). Mit der DMG-Datei gehst du genauso vor wie beim ersten Installieren. In beiden Fällen bleiben Einstellungen, Verlauf, Zugangscode und Sicherungsaufträge erhalten.

> Voraussetzung: Mac mit macOS 12 oder neuer und installiertes Python 3. Fehlt Python 3, meldet das Programm das beim Start.

### KI einrichten

Die Erkennung von Inhalten läuft über eine KI. Empfohlen ist der Weg über dein NotionaryAtlas-Konto:

1. Im Marketplace von NotionaryAtlas bei „Dateien_Aktionen“ einen **Zugangscode** erstellen. Er beginnt mit `na_`.
2. Im Programm oben rechts auf „Einstellungen“ klicken.
3. Bei „KI-Provider“ den Eintrag „KI über NotionaryAtlas“ wählen.
4. Den Zugangscode in das Feld „NotionaryAtlas-Zugangscode“ einfügen.
5. „Verbindung testen“ klicken. Erscheint eine grüne Meldung, steht die Verbindung. Der Test kostet keine Credits.
6. „Einstellungen speichern“ klicken.

Oben rechts zeigt ein Feld den Zustand der KI. Steht dort „Zugangscode fehlt“, führt ein Klick darauf in die Einstellungen.

Andere Möglichkeiten erklärt Kapitel 13.

### Der erste Durchlauf

1. Oben bei „Quellordner“ auf „Durchsuchen...“ klicken und einen Ordner wählen, zum Beispiel „Downloads“.
2. „1. Katalogisieren“ klicken. Das Programm liest alle Dateien ein. Es verändert dabei nichts.
3. Den Reiter „Dateikatalog“ ansehen: Welche Dateitypen liegen im Ordner?
4. „2. KI-Vorschau“ klicken. Die KI liest die Dateien und schlägt Namen und Ordner vor. Auch das verändert noch nichts.
5. Im Reiter „KI-Umbenennung & Vorschau“ die Vorschläge prüfen, bei Bedarf ändern, einzelne Zeilen abwählen.
6. „Jetzt anwenden“ klicken. Erst jetzt wird umbenannt und verschoben.
7. Gefällt dir das Ergebnis nicht: Reiter „Protokoll & Rückgängig“, dort „Rückgängig machen“.

> Tipp: Beginne mit einem kleinen Ordner oder wähle im Katalog nur wenige Dateien aus. So lernst du die Vorschläge kennen, bevor du große Ordner bearbeitest.

### Zugriff auf Ordner erlauben

Der Mac schützt Ordner wie „Dokumente“, „Schreibtisch“ und „Downloads“. Beim ersten Zugriff fragt er, ob das Programm darauf zugreifen darf. Meldet das Programm „Zugriff verweigert“, erlaubst du den Zugriff in den Systemeinstellungen unter „Datenschutz & Sicherheit“ → „Dateien und Ordner“.

## 3. Die Oberfläche

Oben steht immer die **Ordnerauswahl** mit den beiden Knöpfen „1. Katalogisieren“ und „2. KI-Vorschau“. Darunter liegen die Reiter:

| Reiter | Inhalt |
| --- | --- |
| Dateikatalog | Liste aller eingelesenen Dateien mit Filtern |
| Duplikate-Manager | Doppelte Dateien und ähnliche Fotos |
| KI-Umbenennung & Vorschau | Namens- und Ordnervorschläge vor dem Anwenden |
| Autopilot / Wächter | Automatisches Sortieren im Hintergrund |
| Projekte | Laufende Vorhaben |
| Steuer | Belege mit Steuer-Tag |
| Sicherung | Sicherungsaufträge und Wiederherstellen |
| Handbuch | Dieses Handbuch |
| Protokoll & Rückgängig | Frühere Aktionen zurücknehmen |
| Einstellungen | KI, Ordnungssystem, Namensstil, Updates |

### Die Ordnerauswahl

- **Quellordner:** Der Ordner, den du einlesen oder sortieren willst. Du kannst den Pfad auch eintippen.
- **Durchsuchen...:** Öffnet den Auswahldialog des Mac.
- **Eingang:** Erscheint, sobald das Ordnungssystem eingerichtet ist. Setzt „01 Eingang“ als Quellordner. Die Zahl zeigt, wie viele Dateien dort warten.
- **Ohne Unterordner:** Liest nur die Dateien direkt im Ordner, nicht in Unterordnern. Sinnvoll für „Downloads“ und „Schreibtisch“, wenn dort schon sortierte Unterordner liegen. Liegen alle Dateien bereits in Unterordnern, findet das Programm mit diesem Haken nichts und weist darauf hin.

## 4. Ordner katalogisieren

Katalogisieren heißt: Das Programm liest einen Ordner ein und zeigt, was darin liegt. Dateien werden dabei nicht verändert.

### So gehst du vor

1. Quellordner wählen.
2. „1. Katalogisieren“ klicken.
3. Im Reiter „Dateikatalog“ erscheinen die Dateitypen-Übersicht und die Dateiliste.

### Die Kategorien

| Kategorie | Beispiele |
| --- | --- |
| DOKUMENTE | PDF, Word, Excel, Pages, Numbers, Textdateien |
| BILDER | JPG, PNG, HEIC, RAW-Formate |
| VIDEOS | MP4, MOV |
| AUDIO | MP3, M4A, WAV |
| ARCHIVE | ZIP, DMG |
| CODE_DATEN | Programmcode, JSON, HTML |
| PROGRAMME | Programme (`.app`) und Pakete wie die Fotos-Mediathek oder Logic-Projekte |

Ein Klick auf eine Kategorie in der Übersicht filtert die Liste darunter.

### Die Dateiliste

- **Filtern:** nach Kategorie und nach Dateityp.
- **Sortieren:** nach Name, Größe, Datum oder Dateityp.
- **Seitengröße:** 50, 100 oder 250 Dateien pro Seite.
- **Ansehen:** Ein Klick auf eine Datei öffnet die Vorschau. Dort siehst du auch den erkannten Text, also das, was die Texterkennung gelesen hat.

### Mit ausgewählten Dateien arbeiten

Hake Dateien an. Über der Liste erscheint eine Leiste mit diesen Möglichkeiten:

- **KI-Vorschau für Auswahl:** Lässt nur die angehakten Dateien von der KI analysieren. Das spart Zeit und Credits.
- **KI-Präfix:** Ein Kürzel, das den neuen Namen vorangestellt wird, zum Beispiel `01_`.
- **In Ordner verschieben / kopieren...:** Verschiebt oder kopiert die Auswahl in einen Ordner deiner Wahl, auf Wunsch in einen neuen Unterordner.
- **Löschen:** Legt die Auswahl in den Papierkorb.

### Programme und Pakete

Programme (`.app`), die Fotos-Mediathek, Logic-Projekte und ähnliche Pakete erscheinen im Finder als eine Datei, sind technisch aber Ordner. Dateien_Aktionen behandelt sie wie der Finder als **einen Eintrag** in der Kategorie PROGRAMME, mit ihrer Gesamtgröße.

- Du kannst sie auswählen, in einen Ordner verschieben oder kopieren und in den Papierkorb legen.
- Hineingeschaut wird nicht: Ihr Inhalt wird nie gelesen, zerlegt oder umbenannt.
- Die KI-Vorschau und der Autopilot lassen sie aus. Beim Duplikat-Vergleich zählen sie nicht mit.

## 5. Duplikate und ähnliche Fotos

### Exakte Duplikate

Nach dem Katalogisieren zeigt der Reiter „Duplikate-Manager“ Gruppen von Dateien mit **identischem Inhalt**. Verglichen wird der Inhalt, nicht der Name: Zwei Dateien mit verschiedenen Namen, aber gleichem Inhalt gelten als Duplikat.

1. Ordner katalogisieren.
2. Reiter „Duplikate-Manager“ öffnen.
3. Bei „Auswahl“ wählen, was angehakt werden soll: „Älteste behalten“ oder „Neueste behalten“. Angehakt werden jeweils die übrigen Kopien.
4. Die Auswahl prüfen und bei Bedarf einzelne Haken ändern.
5. „Ausgewählte Duplikate in den Papierkorb“ klicken.

Die Dateien liegen danach im Papierkorb des Mac. Erst wenn du ihn leerst, sind sie endgültig weg.

### Optisch ähnliche Fotos

Darunter erscheinen Gruppen von Fotos, die sich stark ähneln: Serienbilder, leicht veränderte oder verkleinerte Kopien. Hier ist **nichts vorab angehakt**, denn ähnlich heißt nicht gleich. Du entscheidest selbst, welches Bild bleibt.

## 6. KI-Vorschau und Umbenennen

### Was bei der Analyse passiert

1. **Text lesen.** Aus PDFs, Office- und Textdateien wird der Text gelesen. Bei Scans und Fotos liest Apples Texterkennung den Text direkt auf dem Mac, bei PDFs höchstens die ersten fünf Seiten.
2. **Angaben sammeln.** Bei Fotos, Videos und Audio kommen Aufnahmedatum, Ort, Kamera und Dauer hinzu.
3. **KI befragen.** Der Anfang des Textes und bei Bildern eine verkleinerte Ansicht gehen an die KI. Sie bestimmt Datum, Absender, Art, Thema, einen Namen und einen Ordner.
4. **Vorschau zeigen.** Die Vorschläge erscheinen in einer Tabelle. Verändert ist bis dahin nichts.

Ist die KI nicht erreichbar, springt eine einfachere Erkennung nach festen Regeln ein. Die Zeile ist dann entsprechend gekennzeichnet.

### Die Vorschau-Tabelle

| Spalte | Bedeutung |
| --- | --- |
| Haken | Nur angehakte Zeilen werden angewendet |
| Ursprüngliche Datei | Bisheriger Name und Ort |
| Neuer Name | Vorschlag, frei änderbar |
| Zielordner | Vorschlag, frei änderbar |
| KI-Erkennung | Art, Absender, Datum, Zusammenfassung und Kennzeichen |

Kennzeichen in der Tabelle:

- **Neue Kategorie – wird angelegt** (gelb): Im Sortiermodus „Ablage“ passt keine vorhandene Kategorie. Der gezeigte Ordner würde neu entstehen. Trage einen vorhandenen Ordner ein, wenn du das nicht willst.
- **Projekt – nach „02 Projekte“:** Die Datei gehört zu einem laufenden Projekt und landet dort. Überschreibst du den Ordner, geht sie stattdessen in die Ablage.
- **Steuer mit Jahr:** Der Beleg ist steuerrelevant und erhält den passenden Finder-Tag.
- **Cache:** Der Vorschlag stammt aus einer früheren Analyse derselben Datei und kostet keine neue Anfrage.

### Anwenden

1. Vorschläge prüfen und anpassen.
2. Optionen wählen:
   - **macOS Finder-Tags & Spotlight-Kommentar setzen:** Schreibt Art, Absender, Jahr und gegebenenfalls „Steuer“ mit Jahr als Tags an die Datei und die Zusammenfassung als Kommentar. Eigene Tags bleiben erhalten.
   - **Kopieren (statt Verschieben):** Lässt die Originale liegen und legt umbenannte Kopien an.
3. „Jetzt anwenden“ klicken und die Rückfrage bestätigen.

Gibt es am Ziel schon eine Datei mit demselben Namen, hängt das Programm einen Zähler an (`_1`, `_2`). Überschrieben wird nie.

### Neu analysieren

„Neu analysieren (Cache ignorieren)“ fragt die KI für alle Dateien erneut. Das ist sinnvoll, wenn du Einstellungen geändert hast oder ein Vorschlag offensichtlich falsch ist. Es kostet erneut Credits.

### Wie die Namen aufgebaut sind

Das Datum steht immer vorn im Format `JJJJ-MM-TT`. So sortieren sich Dateien von selbst zeitlich. Bei Rechnungen ist es das Rechnungsdatum, bei Fotos das Aufnahmedatum.

| Namensstil | Beispiel |
| --- | --- |
| Schema | `2026-03-14_Telekom_Rechnung_Mobilfunk.pdf` |
| Lesbar | `2026-03-14 Telekom Mobilfunk März.pdf` |

Den Stil wählst du in den Einstellungen. Die Regel dahinter: Benenne so, wie du in ein paar Jahren danach suchen würdest.

## 7. Das Ordnungssystem

### Die Idee: wie in einer Wohnung

Ordnung dient zwei Zielen: den Überblick behalten und handlungsfähig bleiben. Das Ordnungssystem kennt vier Bereiche:

| Ordner | Bild | Wofür |
| --- | --- | --- |
| `01 Eingang` | Briefkasten | Alles Neue und Unverarbeitete: Downloads, Scans, Anhänge |
| `02 Projekte` | Schreibtisch | Was gerade läuft oder ansteht |
| `03 Ablage` | Schränke und Regale | Dauerhafte Themen wie Anschaffungen, Versicherung, Auto |
| `Archiv` | Keller | Abgeschlossenes, das du aufbewahrst, aber kaum noch brauchst |

Der Weg einer Datei: Sie kommt im Eingang an, wird von dort in ein Projekt oder in die Ablage sortiert, und Abgeschlossenes wandert ins Archiv.

### Die Regeln

- **Kategorien sind Themen und bleiben stabil.** Zum Beispiel „Versicherung“, nicht „Allianz“.
- **Keine Jahresordner.** Das Jahr steht im Dateinamen. Jahresordner erzeugen nur zusätzliche Ebenen.
- **Kein Ordner „Steuer“.** Steuerliches bleibt bei seinem Thema und wird mit einem Tag markiert (Kapitel 9).
- **Keine überflüssigen Kürzel.** Im Ordner „Anschaffungen“ braucht eine Datei kein „Rechnung“ im Namen.
- **Datum vorn** im Format `JJJJ-MM-TT`.

### Einrichten

1. „Einstellungen“ öffnen, Abschnitt „Ordnungssystem“.
2. Bei „Basisordner“ auf „Wählen...“ klicken. Gut geeignet ist ein Ordner in iCloud Drive oder „Dokumente“.
3. Entscheiden, ob Start-Kategorien angelegt werden sollen (Anschaffungen, Arbeit, Arzt, Auto, Finanzen, Versicherung, Wohnen).
4. „Grundstruktur anlegen“ klicken und bestätigen.

Vorhandene Ordner und Dateien bleiben unberührt, es werden nur fehlende Ordner ergänzt. Danach ist der Sortiermodus „Ablage“ aktiv, und der Eingang wird dem Autopiloten als überwachter Ordner hinzugefügt. Gestartet wird der Autopilot dadurch nicht.

### Der Einrichtungsassistent

Statt der Start-Kategorien kannst du dir die Ablage passend zu deinem Alltag entwerfen lassen:

1. In den Einstellungen bei „Ordnungssystem“ einen Basisordner wählen.
2. „Assistent starten“ klicken.
3. Fünf Fragen beantworten: Beruf, Alltag (zum Ankreuzen), regelmäßige Unterlagen, Hobbys und Vorhaben, gewünschter Detailgrad.
4. „Vorschlag erstellen“ klicken.
5. Den Vorschlag prüfen. Hake ab, was du nicht brauchst. Unter dem Baum stehen Beispiele, wie deine Dateien heißen würden.
6. „Ausgewählte Ordner anlegen“ klicken.

> Hinweis: Der Assistent stellt eine KI-Anfrage und übermittelt dafür deine Antworten an den eingestellten KI-Anbieter. Ohne KI erhältst du einen festen Standardvorschlag.

Du kannst die Kategorien jederzeit im Finder ändern: Ordner anlegen, umbenennen, verschieben. Das Programm arbeitet immer mit dem, was gerade in „03 Ablage“ liegt.

### Die Sortiermodi

| Modus | Verhalten |
| --- | --- |
| Frei | Die KI schlägt Ordner frei vor. Sortiert wird in Unterordner des gescannten Ordners. |
| Ablage | Die KI wählt aus den vorhandenen Kategorien in „03 Ablage“. Sortiert wird immer dorthin, egal welchen Ordner du scannst. |

Im Modus „Ablage“ entstehen neue Kategorien nur, wenn du sie in der Vorschau stehen lässt. Ordner, deren Name mit `_` beginnt (etwa `_Archiv`), werden nicht als Ziel angeboten.

### Der tägliche Ablauf

1. Neues landet im Eingang. Lege Downloads dort ab oder lass den Autopiloten „Downloads“ mit überwachen.
2. „Eingang“ klicken, dann „2. KI-Vorschau“.
3. Vorschläge prüfen, „Jetzt anwenden“.
4. Der Zähler am Knopf „Eingang“ zeigt, was noch wartet.

## 8. Projekte

Ein Projekt ist etwas zeitlich Begrenztes: ein Umzug, eine Steuererklärung, eine Feier, eine Bewerbung. Projekte liegen in „02 Projekte“.

### Projekt anlegen

1. Reiter „Projekte“ öffnen.
2. Einen Namen eingeben.
3. Optional einen Termin wählen.
4. „Projekt anlegen“ klicken.

Mit Termin heißt der Ordner zum Beispiel `2026-12-05_Umzug`. Solche Projekte sortieren sich von selbst nach Datum. Ohne Termin heißt er einfach `Voicey` und gilt als laufender Arbeitsordner.

### Die Projektliste

Die Liste zeigt je Projekt den Termin mit Abstand („in 19 Tagen“), die Zahl der Dateien und den Knopf „Im Finder“. Ist ein Termin vorbei, erinnert die Liste ans Abschließen.

### Dateien einem Projekt zuordnen

Im Sortiermodus „Ablage“ kennt die KI deine laufenden Projekte. Gehört eine Datei eindeutig dazu, schlägt die Vorschau den Projektordner vor. Du kannst das in der Vorschau ändern. Natürlich kannst du Dateien auch von Hand im Finder in den Projektordner legen.

### Projekt abschließen

1. Beim Projekt auf „Abschließen…“ klicken.
2. Wählen, wohin der ganze Ordner wandert:
   - **Archiv:** aufbewahren, wird kaum noch gebraucht.
   - **Ablage:** wird weiterhin gebraucht. Wähle die Kategorie.
   - **Papierkorb:** kann weg.
3. „Verschieben“ klicken und bestätigen.

Archiv und Ablage lassen sich unter „Protokoll & Rückgängig“ zurücknehmen. Aus dem Papierkorb holst du das Projekt im Finder über „Zurücklegen“ zurück.

## 9. Steuer

### Tags statt Ordner

Steuerrelevante Belege bleiben dort, wo sie thematisch hingehören: die Arztrechnung bei „Arzt“, der Versicherungsbeitrag bei „Versicherung“. Zusätzlich tragen sie den Finder-Tag `Steuer` mit Jahr, etwa `Steuer 2026`. So gibt es jede Datei nur einmal, und trotzdem findest du alle Belege eines Jahres sofort.

### Wie der Tag entsteht

- **Automatisch:** Erkennt die KI beim Sortieren einen Beleg als steuerrelevant, setzt das Programm den Tag beim Anwenden. Voraussetzung ist der Haken „Finder-Tags setzen“.
- **Von Hand:** Im Finder die Datei auswählen, Rechtsklick → „Tags…“, und `Steuer 2026` eintragen. Auch solche Tags findet die Übersicht.

Das Jahr ist das, für dessen Steuererklärung der Beleg zählt. Eine im Januar 2026 ausgestellte Lohnsteuerbescheinigung für 2025 erhält `Steuer 2025`.

> Hinweis: Die Einschätzung der KI ist eine Hilfe, keine Steuerberatung. Prüfe die Liste, bevor du sie weitergibst.

### Die Übersicht

1. Reiter „Steuer“ öffnen.
2. Oben das Jahr wählen. Die Liste zeigt alle Dateien mit diesem Tag samt Ordner.
3. „Im Finder“ zeigt eine Datei an ihrem Ort.

Gesucht wird im gesamten Basisordner des Ordnungssystems.

### Belege gesammelt kopieren

1. Jahr wählen.
2. „In Ordner kopieren…“ klicken.
3. Im Dialog einen Zielordner wählen.

Dort entsteht `Steuer-Belege` mit Jahr, unterteilt nach Kategorie. Es sind Kopien; die Originale bleiben an ihrem Platz. Die Kopien lassen sich unter „Protokoll & Rückgängig“ wieder entfernen.

## 10. Autopilot

Der Autopilot überwacht Ordner und sortiert neue Dateien **ohne Vorschau**. Schalte ihn ein, wenn du den Vorschlägen vertraust.

### Einrichten

1. Reiter „Autopilot / Wächter“ öffnen.
2. Bei „Überwachte Ordner“ die Ordner eintragen, einen pro Zeile, oder „Ordner hinzufügen...“ nutzen.
3. Optional einen „zentralen Zielordner“ wählen.
4. „Autopilot-Einstellungen speichern“ klicken.
5. „Autopilot starten“ klicken.

Mit „Jetzt sofort prüfen“ löst du einen einzelnen Durchlauf aus, ohne den Autopiloten dauerhaft zu starten.

### Die Einstellungen

| Einstellung | Bedeutung |
| --- | --- |
| Überwachte Ordner | Nur Dateien direkt im Ordner werden beachtet, keine Unterordner |
| Zentraler Zielordner | Leer: im Modus „Ablage“ wird in die Ablage sortiert, sonst in Unterordner des überwachten Ordners |
| Prüf-Intervall | Wie oft nachgesehen wird, in Sekunden |
| Mindestalter Datei | Wartezeit, bevor eine neue Datei angefasst wird |
| Finder-Tags setzen | Wie in der Vorschau |
| System-Mitteilung | Meldet jede Sortierung |
| Kopieren statt Verschieben | Lässt die Originale liegen |

Unfertige Downloads werden übersprungen.

### Autopilot und Ablage

Im Sortiermodus „Ablage“ legt der Autopilot **keine neuen Kategorien** an. Dateien, für die keine Kategorie passt, bleiben im Eingang. Der Reiter zeigt dann, wie viele warten. Sortiere sie über die KI-Vorschau ein. Dateien, die zu einem laufenden Projekt gehören, legt der Autopilot in das Projekt.

> Achtung: Steht „Downloads“ in der Liste und ist der Modus „Ablage“ aktiv, räumt der Autopilot auch „Downloads“ in die Ablage.

### Hintergrunddienst

Mit „macOS Hintergrunddienst“ → „Aktivieren“ läuft der Autopilot ab der Anmeldung am Mac, auch ohne geöffnetes Fenster. Derselbe Dienst führt auch geplante Sicherungen aus. Der Autopilot arbeitet darin nur, solange er eingeschaltet ist.

Jede Sortierung des Autopiloten steht im Protokoll und lässt sich rückgängig machen.

## 11. Sicherung

Die Sicherung kopiert Ordner oder einzelne Dateien an einen zweiten Ort. Die Originale werden nie verändert.

> Wichtig: Die Sicherung ist nicht verschlüsselt und ersetzt kein Time Machine. Sie sichert die Ordner, die du auswählst, nicht das ganze System.

### Die Ziele

| Ziel | So trägst du es ein |
| --- | --- |
| Externe Festplatte oder USB-Stick | Ordner unter `/Volumes/Name der Platte` |
| NAS | Eingebundene Freigabe unter `/Volumes/Name der Freigabe` |
| Google Drive, OneDrive, iCloud Drive | Der Ordner, den das Programm des Dienstes auf dem Mac anlegt |
| Nextcloud mit Nextcloud-Programm | Der Nextcloud-Ordner auf dem Mac |
| Nextcloud ohne Nextcloud-Programm | Ziel „Nextcloud direkt“ |

Bei Cloud-Ordnern kopiert Dateien_Aktionen in den Ordner, und das Programm des Dienstes lädt die Dateien hoch. Im Ziel entsteht immer ein Ordner `Dateien_Aktionen-Sicherung` mit einem Unterordner je Auftrag.

### Die zwei Arten

| | Spiegel | ZIP-Archiv |
| --- | --- | --- |
| Was entsteht | Die Dateien einzeln, in gleicher Ordnerstruktur | Je Lauf eine gepackte Datei mit Datum im Namen |
| Was ein Lauf kopiert | Nur Neues und Geändertes | Jedes Mal alles |
| Ältere Stände | Ersetzte und gelöschte Dateien in „Frühere Versionen“ | Die letzten Archive |
| Aufräumen | Frühere Versionen nach einstellbaren Tagen | Ältere Archive über der eingestellten Anzahl |
| Geeignet für | Große Ordner, häufige Läufe | Kleinere Ordner, Weitergabe, platzsparendes Aufbewahren |

Beim Spiegel liegt der aktuelle Stand im Unterordner „Aktuell“. Wird eine Datei geändert oder gelöscht, wandert die bisherige Fassung nach „Frühere Versionen“ in einen Ordner mit Datum und Uhrzeit. Beim ZIP-Archiv entsteht kein neues Archiv, wenn sich seit dem letzten nichts geändert hat.

### Einen Auftrag anlegen

1. Reiter „Sicherung“ öffnen.
2. „Neuer Auftrag“ klicken.
3. Einen **Namen** vergeben, zum Beispiel „Ablage auf NAS“. Er ist zugleich der Ordnername im Ziel.
4. Bei **Was soll gesichert werden?** die Quellen eintragen, eine pro Zeile. „Ordner hinzufügen...“ öffnet den Auswahldialog, „Ordnungssystem“ trägt deinen Basisordner ein.
5. Bei **Wohin?** „Ordner“ oder „Nextcloud direkt“ wählen und das Ziel eintragen.
6. Die **Art** wählen: Spiegel oder ZIP-Archiv.
7. Festlegen, wie lange frühere Versionen bleiben (Spiegel) oder wie viele Archive (ZIP).
8. Den **Zeitplan** wählen.
9. Optional „mit Prüfsumme kontrollieren“ anhaken.
10. „Auftrag speichern“ klicken.
11. Mit „Jetzt sichern“ den ersten Lauf starten.

> Hinweis: Name und Art lassen sich nach dem ersten Lauf nicht mehr ändern. Lege dafür einen neuen Auftrag an.

### Der Zeitplan

| Zeitplan | Wann gesichert wird |
| --- | --- |
| Nur von Hand | Wenn du „Jetzt sichern“ klickst |
| Stündlich | Zu jeder vollen Stunde |
| Täglich | Zur gewählten Uhrzeit |
| Wöchentlich | An den gewählten Wochentagen zur gewählten Uhrzeit |

**Verpasste Termine werden nachgeholt:** War der Mac aus oder das Ziel nicht erreichbar, läuft die Sicherung bei der nächsten Gelegenheit.

Geplante Sicherungen laufen, solange das Programm geöffnet ist. Sollen sie auch ohne geöffnetes Fenster laufen, aktiviere im Reiter „Sicherung“ unter „Zeitplan im Hintergrund“ den Hintergrunddienst.

> Hinweis: Der Hintergrunddienst braucht eventuell die Erlaubnis, auf deine Ordner, externe Platten und Netzlaufwerke zuzugreifen. Scheitern geplante Läufe mit „nicht lesbar“, erlaube den Zugriff in den Systemeinstellungen unter „Datenschutz & Sicherheit“.

### Schritt für Schritt: externe Festplatte

1. Die Festplatte anschließen.
2. Neuen Auftrag anlegen, bei „Wohin?“ „Ordner“ wählen.
3. Bei „Zielordner“ auf „Wählen...“ klicken und die Festplatte oder einen Ordner darauf wählen.
4. Optional anhaken: „Zusätzlich sichern, sobald das Laufwerk angeschlossen wird“.
5. Speichern und „Jetzt sichern“.

Ist die Platte nicht angeschlossen, schreibt das Programm nichts und zeigt „Ziel nicht erreichbar“. Mit einem Zeitplan wartet der Auftrag, bis die Platte wieder da ist.

### Schritt für Schritt: NAS

1. Die Freigabe im Finder verbinden: „Gehe zu“ → „Mit Server verbinden…“, Adresse eingeben, anmelden und das Passwort im Schlüsselbund sichern.
2. Neuen Auftrag anlegen, Ziel „Ordner“, und die Freigabe unter `/Volumes` wählen.
3. Bei „NAS automatisch verbinden“ die Adresse eintragen, etwa `smb://nas.local/Sicherung`. Das Programm bindet die Freigabe dann vor jedem Lauf selbst ein.
4. Speichern und „Jetzt sichern“.

Das Passwort speichert Dateien_Aktionen nicht. Es kommt aus dem Schlüsselbund des Mac.

### Schritt für Schritt: Google Drive, OneDrive, iCloud Drive

1. Das Programm des Dienstes muss auf dem Mac eingerichtet sein, sodass sein Ordner im Finder erscheint.
2. Neuen Auftrag anlegen, Ziel „Ordner“.
3. Als Zielordner den Ordner des Dienstes wählen, am besten einen Unterordner wie „Sicherungen“.
4. Speichern und „Jetzt sichern“.

Das Hochladen übernimmt das Programm des Dienstes. Eine Sicherung ist erst wirklich in der Cloud, wenn dieses Programm fertig ist.

### Schritt für Schritt: Nextcloud direkt

1. In der Nextcloud im Browser anmelden, „Einstellungen“ → „Sicherheit“ öffnen und unter „Geräte & Sitzungen“ ein **App-Passwort** erstellen.
2. Im Reiter „Sicherung“ unter „Nextcloud direkt verbinden“ die Adresse (mit `https://`), den Benutzernamen und das App-Passwort eintragen.
3. „Verbindung testen“ klicken, danach „Speichern“.
4. Neuen Auftrag anlegen, bei „Wohin?“ „Nextcloud direkt“ wählen.
5. Bei „Ordner in der Nextcloud“ einen Ordner eintragen, zum Beispiel „Sicherungen“.
6. Speichern und „Jetzt sichern“.

> Hinweis: Verwende ein App-Passwort, nicht dein normales Passwort. Es lässt sich in der Nextcloud jederzeit einzeln widerrufen. Sehr große einzelne Dateien können an einer Größengrenze des Servers scheitern.

### Während einer Sicherung

Oben im Reiter erscheint ein Balken mit dem Fortschritt. „Abbrechen“ beendet den Lauf; bereits Gesichertes bleibt. Es läuft immer nur eine Sicherung zur selben Zeit.

### Wiederherstellen

Für Sicherungen in einen Ordner:

1. Beim Auftrag auf „Wiederherstellen“ klicken.
2. Oben den Stand wählen: „Aktueller Stand“, eine frühere Version oder ein Archiv.
3. Durch die Ordner klicken, bis du die Datei oder den Ordner siehst.
4. Wählen:
   - **Zurücklegen:** an den ursprünglichen Ort.
   - **In Ordner…:** in einen Ordner deiner Wahl.

Vorhandene Dateien werden nie überschrieben. Liegt am Ziel schon eine Datei mit dem Namen, bekommt die wiederhergestellte einen Zähler (`_1`). Finder-Tags werden wieder gesetzt. Der Schritt steht im Protokoll und lässt sich zurücknehmen.

Sicherungen mit „Nextcloud direkt“ stellst du in der Nextcloud selbst wieder her. Die Dateien liegen dort unverändert.

### Was die Sicherung schützt

- **Laufwerk nicht angeschlossen:** Es wird nichts geschrieben. Die Daten landen nicht versehentlich auf der internen Platte.
- **Quelle nicht erreichbar:** Ihre Sicherung bleibt unangetastet. Der Lauf gilt als nicht erledigt und wird wiederholt.
- **Aufräumen nur im eigenen Ordner:** Das Programm löscht ausschließlich in seinem Ordner `Dateien_Aktionen-Sicherung`.
- **Finder-Tags:** Viele Platten und Cloud-Ordner speichern keine Tags. Sie werden deshalb zusätzlich in einer Begleitdatei gesichert.
- **Auftrag löschen:** Entfernt nur den Auftrag. Die gesicherten Dateien bleiben im Ziel.

### Das Protokoll der Läufe

Unter „Letzte Läufe“ steht zu jedem Lauf Zeitpunkt, Auslöser, Dauer und Ergebnis. Konnte eine Datei nicht gesichert werden, steht sie dort mit dem Grund.

## 12. Protokoll & Rückgängig

Jede Aktion, die Dateien umbenennt, verschiebt oder kopiert, wird festgehalten: Anwenden aus der Vorschau, Autopilot, Projekt abschließen, Steuer-Belege kopieren, Wiederherstellen aus einer Sicherung.

### Eine Aktion zurücknehmen

1. Reiter „Protokoll & Rückgängig“ öffnen.
2. Den Eintrag suchen. Er trägt Datum, Uhrzeit und die Zahl der Aktionen.
3. „Rückgängig machen“ klicken und bestätigen.

Verschobene Dateien kommen an ihren alten Ort und erhalten ihren alten Namen. Kopien werden wieder entfernt.

### Was sich nicht zurücknehmen lässt

- **Papierkorb:** Gelöschtes holst du im Finder aus dem Papierkorb zurück.
- **Gesetzte Finder-Tags** bleiben an der Datei.
- **Dateien, die du danach selbst verschoben hast:** Das Programm findet sie nicht mehr und überspringt sie.

## 13. Einstellungen

### KI-Provider

| Auswahl | Bedeutung |
| --- | --- |
| KI über NotionaryAtlas | Empfohlen. Läuft über dein Konto und dessen KI-Credits. |
| Eigener Google-Gemini-Schlüssel | Du nutzt einen eigenen Schlüssel von Google. |
| Lokaler KI-Server | Eine KI auf deinem Mac, etwa LM Studio oder Ollama. Nichts verlässt den Mac. |
| Offline-Heuristik | Ohne KI, mit festen Regeln. Schnell, aber grob. |

### Grenzen bei NotionaryAtlas

- Höchstens 4 MB je Anfrage.
- Höchstens 120 Anfragen pro Stunde je Zugangscode.
- Jede Analyse einer Datei und der Einrichtungsassistent verbrauchen Credits. Vorschläge aus dem Cache sind kostenlos.

### Ordnungssystem

Basisordner, Grundstruktur, Einrichtungsassistent und Sortiermodus. Siehe Kapitel 7.

### Namensstil

„Schema“ mit Unterstrichen und ohne Umlaute oder „Lesbar“ mit Leerzeichen und Umlauten. Siehe Kapitel 6.

### Scan-Verhalten

„Ohne Unterordner“ entspricht dem Haken in der Ordnerauswahl.

### Software-Aktualisierung

Zeigt die installierte Version und sucht auf Wunsch nach einer neueren. Siehe Kapitel 15.

## 14. Datenschutz und Sicherheit

### Was den Mac verlässt

| Vorgang | Was übertragen wird | Wohin |
| --- | --- | --- |
| KI-Analyse einer Datei | Dateiname, Anfang des erkannten Textes, Angaben wie Datum und Ort, bei Bildern eine verkleinerte Ansicht | Der eingestellte KI-Anbieter |
| Einrichtungsassistent | Deine fünf Antworten | Der eingestellte KI-Anbieter |
| Sicherung „Nextcloud direkt“ | Die gesicherten Dateien | Deine Nextcloud |
| Update-Suche und Direkt-Update | Eine Abfrage der neuesten Version; beim Direkt-Update der Download des neuen Programms | GitHub |

Mit „Lokaler KI-Server“ oder „Offline-Heuristik“ verlässt bei der Analyse nichts den Mac. Die Texterkennung läuft immer auf dem Mac.

### Wo deine Daten liegen

Einstellungen, Zugangscode, Verlauf und Sicherungsaufträge liegen in deinem Benutzerordner unter `~/Library/Application Support/Dateien_Aktionen/`, nicht im Programm. Deshalb überstehen sie jedes Update. Zugangscode, Schlüssel und App-Passwort stehen dort in einer Datei, die nur du lesen kannst.

### Was das Programm nie tut

- Dateien ohne Bestätigung umbenennen oder verschieben, außer im eingeschalteten Autopiloten.
- Vorhandene Dateien überschreiben.
- Endgültig löschen. Gelöschtes liegt im Papierkorb. Einzige Ausnahme ist das Aufräumen alter Stände im eigenen Sicherungsordner.

## 15. Updates

Das Programm prüft beim Start, ob eine neuere Version vorliegt. Gibt es eine, erscheint oben „Update verfügbar!“.

### Direkt im Programm aktualisieren

So bringst du das Programm mit wenigen Klicks auf den neuesten Stand, ohne etwas herunterzuladen und zu ziehen.

1. Auf „Update verfügbar!“ klicken. Es erscheinen die Neuerungen.
2. „Jetzt direkt updaten“ klicken.
3. Warten, bis „ist installiert. Das Programm startet jetzt neu …“ erscheint. Das kann eine Minute dauern.
4. Das Programm schließt sich und öffnet sich kurz darauf in der neuen Version.

> Hinweis: Das Programm lädt die neue Version von GitHub über eine geprüfte, sichere Verbindung und ersetzt sich dann selbst. Geht dabei etwas schief, bleibt die bisherige Version unverändert.

Der Knopf „Jetzt direkt updaten“ erscheint nur, wenn das Programm aus dem Ordner „Programme“ (oder einem anderen Ordner, in dem du schreiben darfst) gestartet wurde. Sonst bleibt nur der Download.

### Mit der DMG-Datei aktualisieren

1. Auf „Update verfügbar!“ klicken.
2. „Update herunterladen (.dmg)“ oder „Stattdessen herunterladen“ klicken.
3. Die heruntergeladene Datei öffnen und das Programm in „Programme“ ziehen, „Ersetzen“ wählen.
4. Das Programm neu starten.

In den Einstellungen kannst du mit „Auf GitHub nach Updates suchen“ jederzeit selbst nachsehen.

## 16. Problemlösungen

### Der Katalog oder die Vorschau findet keine Dateien

Meist ist „Ohne Unterordner“ angehakt, und die Dateien liegen in Unterordnern. Das passiert zum Beispiel bei „Downloads“, wenn dort schon früher einsortiert wurde: Auf der obersten Ebene liegt dann nichts mehr.

Das Programm zeigt in diesem Fall einen gelben Hinweis mit der Zahl der nicht durchsuchten Unterordner.

1. Im Hinweis auf „Mit Unterordnern einlesen“ klicken, oder den Haken „Ohne Unterordner“ oben entfernen.
2. Erneut „1. Katalogisieren“ klicken.

Der Haken wird gemerkt und gilt auch beim nächsten Start. Versteckte Dateien und Systemdateien wie `.DS_Store` zählen nie mit. Programme (`.app`) erscheinen im Katalog, in der KI-Vorschau aber nicht – sie werden nie umbenannt.

### Die KI liefert keine Vorschläge

- **Zugangscode fehlt oder ist ungültig:** In den Einstellungen „Verbindung testen“. Bei einem Fehler im Marketplace einen neuen Code erstellen.
- **Keine Credits mehr:** Im NotionaryAtlas-Konto nachsehen.
- **Zu viele Anfragen:** Nach 120 Anfragen in einer Stunde ist Pause. Später weitermachen oder weniger Dateien auf einmal wählen.
- **Keine Internetverbindung:** Die Zeilen sind dann als einfache Erkennung gekennzeichnet.

### „Zugriff verweigert“

In den Systemeinstellungen unter „Datenschutz & Sicherheit“ → „Dateien und Ordner“ den Zugriff erlauben. Für Netzlaufwerke und externe Platten gilt das ebenso.

### Der Text eines Scans wird nicht erkannt

Oben zeigt ein Feld, ob die Texterkennung bereit ist. Sehr schlechte Scans oder Handschrift erkennt sie nur teilweise. Im Katalog zeigt ein Klick auf die Datei, welcher Text gelesen wurde.

### Dateien in iCloud

Liegt eine Datei nur in iCloud und nicht auf dem Mac, lädt das Programm sie bei Bedarf. Das kann dauern und braucht eine Internetverbindung.

### Der Autopilot sortiert nichts

- Ist er gestartet? Der Reiter zeigt „Aktiv“.
- Stehen die richtigen Ordner in der Liste, und wurde gespeichert?
- Liegen die Dateien direkt im Ordner und nicht in einem Unterordner?
- Im Modus „Ablage“: Vielleicht passt keine Kategorie. Der Reiter zeigt dann, wie viele Dateien warten.
- Steht im Reiter ein „Letzter Fehler“? Der Text nennt die Ursache.

### Die Sicherung läuft nicht

- **„Ziel nicht erreichbar“:** Platte anschließen oder Freigabe verbinden. Der Auftrag holt den Lauf nach.
- **Geplante Läufe bleiben aus:** Ist das Programm geöffnet oder der Hintergrunddienst aktiv?
- **„Im Ziel gibt es schon einen Ordner …“:** Im Ziel liegt ein gleichnamiger Ordner, der nicht von dieser Sicherung stammt. Gib dem Auftrag einen anderen Namen oder wähle ein anderes Ziel.
- **„Zu wenig Platz“:** Im Ziel Platz schaffen oder die Aufbewahrung verkürzen.
- **Nextcloud lehnt die Anmeldung ab:** Benutzername und App-Passwort prüfen, bei Bedarf ein neues App-Passwort erstellen.

### Das Direkt-Update meldet einen Fehler

- **„Keine Schreibrechte …“:** Das Programm darf seinen eigenen Ordner nicht ändern. Das Update mit „Stattdessen herunterladen“ über die DMG-Datei installieren.
- **„Die sichere Verbindung zu GitHub konnte nicht geprüft werden“ oder „GitHub ist nicht erreichbar“:** Internetverbindung prüfen und es noch einmal versuchen, sonst die DMG-Datei verwenden.

In allen Fällen bleibt die bisherige Version unverändert und funktioniert weiter.

### Nach einem Update läuft noch die alte Version

Das Programm vollständig beenden und neu starten.

## 17. Begriffe

| Begriff | Erklärung |
| --- | --- |
| Ablage | Der Ordner „03 Ablage“ mit den dauerhaften Kategorien |
| App-Passwort | Ein eigenes Passwort nur für ein Programm, in der Nextcloud erstellt und einzeln widerrufbar |
| Cache | Gemerkte Ergebnisse früherer Analysen, damit dieselbe Datei nicht zweimal Credits kostet |
| Credits | Guthaben im NotionaryAtlas-Konto für KI-Anfragen |
| Duplikat | Datei mit exakt gleichem Inhalt wie eine andere |
| Eingang | Der Ordner „01 Eingang“ für alles Neue |
| Finder-Tag | Schlagwort an einer Datei, im Finder sichtbar und durchsuchbar |
| Hintergrunddienst | Läuft ab der Anmeldung am Mac ohne geöffnetes Fenster |
| NAS | Netzwerkspeicher, ein Laufwerk im eigenen Netz |
| Spiegel | Sicherungsart, die die Dateien einzeln in gleicher Struktur ablegt |
| Texterkennung | Liest Text aus Scans und Fotos, auch OCR genannt |
| Vorschau | Zeigt geplante Änderungen, bevor etwas passiert |
| Zugangscode | Code aus dem NotionaryAtlas-Marketplace, der die KI freischaltet |

## 18. Für Fortgeschrittene: die Kommandozeile

Alle Kernfunktionen gibt es auch im Terminal. Die Befehle führst du im Programmordner aus.

| Befehl | Wirkung |
| --- | --- |
| `python3 main.py catalog <Ordner>` | Ordner einlesen, Typen und Duplikate anzeigen |
| `python3 main.py preview <Ordner>` | Vorschläge anzeigen, ohne etwas zu ändern |
| `python3 main.py run <Ordner>` | Umbenennen und sortieren nach Bestätigung |
| `python3 main.py undo` | Die letzte Aktion zurücknehmen |
| `python3 main.py watch <Ordner>` | Autopilot im Terminal starten |
| `python3 main.py dienst` | Hintergrunddienst: Autopilot, sofern eingeschaltet, und geplante Sicherungen |
| `python3 main.py ocr-test <Datei>` | Texterkennung an einer Datei prüfen |
| `python3 main.py config` | Aktuelle Einstellungen anzeigen |

Mit `--without-subfolders` lesen `catalog` und `preview` nur die Hauptebene. Mit `--target-dir` und `--copy` sortiert `run` in einen anderen Ordner und kopiert statt zu verschieben.
