---
trigger: always_on
---

# Release (immer vollständig)

Bei jeder neuen Version gilt Abschnitt 4 „Release“ in `AGENTS.md` —
**alle neun Schritte**, nicht nur Bauen und Hochladen. Besonders leicht
vergessen:

- **Version überall gleich** (siehe Schritt 1) und gleich dem Git-Tag `vX.Y.Z`.
- **`marketplace.json` mitpflegen** (Schritt 5): Beschreibung und
  Funktionsliste beschreiben das ganze Programm im aktuellen Stand. Neue
  Funktionen einarbeiten, Weggefallenes streichen.
- **Marketplace-Texte übernehmen** (Schritt 8):
  `node ~/Developer/pberthold-app/scripts/marketplace-desktop-text.mjs ~/Developer/Dateien_Aktionen --schreiben`
  — ohne diesen Schritt zeigt der Marketplace die neue Version mit alten Texten.
  Kein Deploy nötig.
- Im Repo `pberthold-app` sonst nichts ändern, dort **nie** committen oder pushen.

Am Ende dem Nutzer melden: Version, Release-Link, ob `marketplace.json`
geändert wurde und dass Schritt 8 „Marketplace aktualisiert“ bzw. „bereits
aktuell“ gemeldet hat.
