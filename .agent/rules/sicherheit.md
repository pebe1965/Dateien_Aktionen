# Sicherheit (immer beachten)

Lies vor jeder Änderung `AGENTS.md` im Hauptordner des Repos und befolge sie.

Die drei wichtigsten Regeln daraus:
1. **Niemals einen API-Schlüssel in Code, Build oder Paket** — auch nicht
   Base64-kodiert oder als Standardwert. Das Repo und die Downloads sind öffentlich.
2. **KI läuft über NotionaryAtlas** mit dem Zugangscode des Nutzers (`na_…`),
   über die eine vorhandene Funktion — keine zweite Stelle, die Gemini direkt aufruft.
3. **Vor jedem Release** das Paket auf `AIza…` und `.env` prüfen.
