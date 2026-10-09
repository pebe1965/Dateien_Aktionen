"""
Modul: ai_engine.py
Das semantische Gehirn für die Inhaltsanalyse und intelligente Benennung.
Unterstützt:
- Google Gemini API (z. B. gemini-3.7-flash, gemini-3.8-flash, gemini-2.5-flash)
- Lokale KI-Server (OpenAI-kompatibel via MLX, Ollama, LM Studio)
- Intelligente Offline-Heuristik (Fallback mit Regex & Metadaten)
"""

import os
import ssl
import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any

from config import (
    AI_PROVIDER,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LOCAL_API_URL,
    LOCAL_MODEL
)


def _get_ssl_context() -> ssl.SSLContext:
    """Erstellt einen funktionierenden SSL-Kontext für macOS."""
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        # Fallback für macOS Python-Umgebungen ohne installiertes certifi
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


@dataclass
class AnalysisResult:
    original_name: str
    extension: str
    suggested_name: str
    suggested_folder: str
    doc_date: Optional[str]
    sender: str
    doc_type: str
    topic: str
    summary: str
    provider_used: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_name": self.original_name,
            "suggested_name": self.suggested_name,
            "suggested_folder": self.suggested_folder,
            "doc_date": self.doc_date,
            "sender": self.sender,
            "doc_type": self.doc_type,
            "topic": self.topic,
            "summary": self.summary,
            "provider_used": self.provider_used
        }


def clean_filename(text: str) -> str:
    """Bereinigt einen Dateinamen von unzulässigen Zeichen."""
    cleaned = re.sub(r'[/\\:*?"<>|]', '', text)
    cleaned = re.sub(r'[\s_]+', '_', cleaned).strip('_')
    return cleaned


SYSTEM_PROMPT = """Du bist ein hochpräziser Assistent zur Organisation und Katalogisierung von Dokumenten und Dateien auf macOS.
Deine Aufgabe ist es, den tatsächlichen Inhalt (Text/OCR) und den Kontext der Datei tiefgehend zu verstehen und ein strukturiertes Namensschema zu erzeugen.

WICHTIGE REGELN FÜR DOKUMENTARTEN:
1. KONTOAUSZÜGE / TRANSAKTIONSÜBERSICHTEN (z. B. bunq, Sparkasse, N26, DKB, PayPal):
   - Der ABSENDER ist immer das Finanzinstitut bzw. die Bank (z. B. 'bunq', 'Sparkasse', 'DKB', 'PayPal'), NIEMALS ein Händler oder Zahlungsempfänger (wie Amazon, Rewe, Netflix), der nur als einzelne Buchungszeile im Kontoauszug auftaucht!
   - Der DOKUMENTENTYP ist 'Transaktionsuebersicht' oder 'Kontoauszug'.
   - Das DATUM ist das Auszugsdatum oder der Abrechnungszeitraum (z. B. 2026-07 oder 2024-03).
   - Falls eine IBAN oder Kontonummer im Dokument steht, binde die letzten 4-6 Zeichen der IBAN oder die Kontobezeichnung in das THEMA ein (z. B. 'Konto_...1234_Juli').

2. RECHNUNGEN & BELEGE:
   - Der ABSENDER ist der Rechnungssteller (Firma im Briefkopf / Logo oben), nicht der Kunde.
   - Das DATUM ist das Rechnungsdatum / Leistungsdatum.

3. VERTRÄGE & POLICEN:
   - Der ABSENDER ist der Vertragspartner / die Gesellschaft (z. B. Allianz, Telekom).

Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt in exakt folgendem Format:
{
  "doc_date": "YYYY-MM-DD",     // Das im Dokument gefundene Hauptdatum (Abrechnungsmonat oder Dokumentendatum). Falls unbekannt: null
  "sender": "Absender/Bank/Firma", // z.B. bunq, Telekom, Amazon, Finanzamt (Kurzname, keine Leerzeichen)
  "doc_type": "Dokumententyp",  // z.B. Transaktionsuebersicht, Kontoauszug, Rechnung, Vertrag, Gehaltsabrechnung, Bescheid
  "topic": "Thema_Kurz",        // z.B. Konto_IBAN1234, Internet_Kabel, KFZ_Versicherung (1-3 Worte, prägnant)
  "suggested_filename": "YYYY-MM-DD_Absender_Dokumententyp_Thema", // Ohne Dateiendung! Keine Sonderzeichen außer Unterstrichen
  "suggested_folder": "Kategorie/Absender", // z.B. Finanzen/bunq oder Rechnungen/Telekom
  "summary": "Prägnante 1-Satz-Zusammenfassung des Dokuments."
}

Wichtig:
- Wenn doc_date null ist, beginne suggested_filename direkt mit Absender_Dokumententyp_Thema.
- Verwende NIEMALS Leerzeichen im suggested_filename, sondern Unterstriche (_).
- Keine Umlaute im Dateinamen verwenden (ae, oe, ue, ss statt ä, ö, ü, ß).
- Antworte NUR als reines JSON-Objekt, kein Markdown, kein erklärender Text!
"""


def _query_gemini(prompt: str, api_key: str, model: str) -> Optional[Dict[str, Any]]:
    """Sendet eine Anfrage an die Google Gemini API mit SSL-Absicherung."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_PROMPT + "\n\n" + prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        ctx = _get_ssl_context()
        with urllib.request.urlopen(req, context=ctx, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
            candidates = result.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    raw_text = parts[0].get("text", "")
                    # Bereinigen falls Markdown-Wrapper vorliegt
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
                    raw_text = re.sub(r"\s*```$", "", raw_text)
                    return json.loads(raw_text)
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"[Gemini API HTTP Error {e.code}] {err_msg}")
        return None
    except Exception as e:
        print(f"[Gemini API Verbindungsfehler] {e}")
        return None
    return None


def _query_local_llm(prompt: str, api_url: str, model: str) -> Optional[Dict[str, Any]]:
    """Sendet eine Anfrage an einen lokalen OpenAI-kompatiblen Server."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }

    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        ctx = _get_ssl_context()
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            content = re.sub(r"^```(?:json)?\s*", "", content.strip())
            content = re.sub(r"\s*```$", "", content)
            return json.loads(content)
    except Exception as e:
        print(f"[Lokaler KI-Fehler] {e}")
        return None


def _heuristic_analysis(filename: str, text: str, ext: str) -> Dict[str, Any]:
    """
    Intelligente Offline-Heuristik (Fallback), falls die KI nicht erreichbar ist.
    Erkennt Bankauszüge, IBANs, Rechnungen und Dokumenten-Daten.
    """
    text_lower = (filename + " " + text[:3000]).lower()

    # 1. Datumssuche
    doc_date = None
    # Suche zuerst nach Abrechnungsmonaten wie "07-2026" oder "Juli 2026"
    month_match = re.search(r'\b(0[1-9]|1[0-2])[-_](\d{4})\b', filename + " " + text[:500])
    if month_match:
        m, y = month_match.groups()
        doc_date = f"{y}-{m}-01"
    else:
        date_patterns = [
            r'\b(\d{4})[-/.](\d{2})[-/.](\d{2})\b',
            r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b',
        ]
        for pat in date_patterns:
            match = re.search(pat, text[:1500])
            if match:
                g = match.groups()
                if len(g[0]) == 4:
                    doc_date = f"{g[0]}-{g[1]}-{g[2]}"
                else:
                    day, month, year = g[0].zfill(2), g[1].zfill(2), g[2]
                    doc_date = f"{year}-{month}-{day}"
                break

    # 2. Banken / Finanzdokumente erkennen
    is_banking = any(k in text_lower for k in ["transaktion", "transaktionsübersicht", "kontoauszug", "iban", "bic", "kontostand", "buchung", "bunq"])
    sender = "Unbekannt"
    doc_type = "Dokument"
    topic = clean_filename(Path(filename).stem)[:30]

    # IBAN suchen
    iban_match = re.search(r'\b([A-Z]{2}\d{2}[A-Z0-9]{10,28})\b', text.upper())
    iban_suffix = ""
    if iban_match:
        full_iban = iban_match.group(1)
        iban_suffix = f"_IBAN{full_iban[-4:]}"

    if is_banking:
        doc_type = "Transaktionsuebersicht" if "transaktion" in text_lower else "Kontoauszug"
        if "bunq" in text_lower:
            sender = "bunq"
        elif "sparkasse" in text_lower:
            sender = "Sparkasse"
        elif "dkb" in text_lower:
            sender = "DKB"
        elif "n26" in text_lower:
            sender = "N26"
        elif "revolut" in text_lower:
            sender = "Revolut"
        elif "paypal" in text_lower:
            sender = "PayPal"
        else:
            sender = "Bank"
        topic = f"Konto{iban_suffix}"
    else:
        # Rechnungen / Verträge
        if any(k in text_lower for k in ["rechnung", "invoice", "gesamtbetrag", "rechnungsbetrag", "mwst"]):
            doc_type = "Rechnung"
        elif any(k in text_lower for k in ["vertrag", "vereinbarung"]):
            doc_type = "Vertrag"
        elif any(k in text_lower for k in ["gehaltsabrechnung", "entgeltabrechnung"]):
            doc_type = "Gehaltsabrechnung"
        elif any(k in text_lower for k in ["bescheid", "finanzamt"]):
            doc_type = "Bescheid"

        # Bekannte Absender
        for brand in ["Telekom", "Vodafone", "Amazon", "Apple", "Google", "Finanzamt"]:
            if brand.lower() in text_lower and not is_banking:
                sender = brand
                break

    if doc_date:
        suggested = f"{doc_date}_{clean_filename(sender)}_{doc_type}_{topic}"
    else:
        suggested = f"{clean_filename(sender)}_{doc_type}_{topic}"

    return {
        "doc_date": doc_date,
        "sender": sender,
        "doc_type": doc_type,
        "topic": topic,
        "suggested_filename": clean_filename(suggested),
        "suggested_folder": f"Finanzen/{clean_filename(sender)}" if is_banking else f"{doc_type}en/{clean_filename(sender)}",
        "summary": "Klassifiziert per intelligenter Heuristik."
    }


def analyze_file_content(
    filename: str,
    text_content: str,
    metadata_info: str = "",
    provider: Optional[str] = None,
    prefix: Optional[str] = None
) -> AnalysisResult:
    """
    Hauptfunktion: Analysiert Dateiname & extrahierten Text mit dem gewählten KI-Provider
    und liefert ein strukturiertes AnalysisResult zurück.
    Falls ein Präfix angegeben ist (z.B. "01_"), wird es vorangestellt.
    """
    ext = Path(filename).suffix.lower()
    active_provider = provider if provider else AI_PROVIDER

    text_snippet = text_content[:5000].strip()

    prompt = f"Dateiname: {filename}\n"
    if metadata_info:
        prompt += f"Zusätzliche Metadaten: {metadata_info}\n"
    prompt += f"\nExtrahierter Inhalt / OCR:\n{text_snippet if text_snippet else '[Kein lesbarer Text gefunden]'}\n"

    ai_data: Optional[Dict[str, Any]] = None
    used_provider = "offline_heuristik"

    # 1. Gemini
    if active_provider == "gemini" and GEMINI_API_KEY:
        print(f"🤖 [KI-Anfrage] Sende '{filename}' an Gemini ({GEMINI_MODEL})...")
        ai_data = _query_gemini(prompt, GEMINI_API_KEY, GEMINI_MODEL)
        if ai_data:
            used_provider = f"gemini ({GEMINI_MODEL})"
            print(f"✓ [KI-Erfolg] Erkannt: {ai_data.get('sender')} | {ai_data.get('doc_type')} | {ai_data.get('suggested_filename')}")

    # 2. Lokaler Server
    elif active_provider == "local":
        print(f"🤖 [KI-Anfrage] Sende '{filename}' an lokalen Server...")
        ai_data = _query_local_llm(prompt, LOCAL_API_URL, LOCAL_MODEL)
        if ai_data:
            used_provider = f"local ({LOCAL_MODEL})"

    # 3. Fallback Heuristik
    if not ai_data:
        if active_provider != "offline":
            print(f"⚠️ [Fallback] KI nicht erreichbar, nutze Heuristik für '{filename}'")
        ai_data = _heuristic_analysis(filename, text_content, ext)
        if active_provider != "offline":
            used_provider = "fallback_heuristik"

    # Sichere Normalisierung des Dateinamens
    suggested_base = ai_data.get("suggested_filename", Path(filename).stem)
    suggested_clean = clean_filename(suggested_base)

    # Optionales Präfix voranstellen
    if prefix:
        p_clean = clean_filename(prefix)
        if not p_clean.endswith("_") and not prefix.endswith("-"):
            p_clean += "_"
        suggested_clean = f"{p_clean}{suggested_clean}"

    final_filename = f"{suggested_clean}{ext}"
    folder = ai_data.get("suggested_folder", "Sortiert")

    return AnalysisResult(
        original_name=filename,
        extension=ext,
        suggested_name=final_filename,
        suggested_folder=folder,
        doc_date=ai_data.get("doc_date"),
        sender=ai_data.get("sender", "Unbekannt"),
        doc_type=ai_data.get("doc_type", "Sonstiges"),
        topic=ai_data.get("topic", ""),
        summary=ai_data.get("summary", ""),
        provider_used=used_provider
    )
