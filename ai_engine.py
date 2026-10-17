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

# Bewusst das Modul statt einzelner Namen: Die Oberfläche ändert die Werte zur
# Laufzeit (config.GEMINI_API_KEY = …). Mit `from config import …` hätte die
# Analyse bis zum Neustart mit den alten weitergearbeitet.
import config


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


SYSTEM_PROMPT = """Du bist ein hochpräziser Assistent zur Organisation und Katalogisierung von Dokumenten, Fotos, Screenshots und Mediendateien auf macOS.
Deine Aufgabe ist es, den tatsächlichen Inhalt (Text/OCR, EXIF-Metadaten, Apple Vision Bildmotive und ggf. das übergebene Bild) tiefgehend zu verstehen und ein strukturiertes Namensschema zu erzeugen.

WICHTIGE REGELN FÜR DOKUMENTE & MEDIEN:
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

4. FOTOS, SCREENSHOTS & MEDIEN (BILDER, VIDEOS, AUDIO):
   - Bei SCREENSHOTS (erkennbar an 'Bildschirmfoto', 'Screenshot', 'kMDItemIsScreenCapture = 1' oder UI-Inhalten im Bild):
     * doc_type = 'Screenshot'
     * sender = Name der App / Webseite / Quelle (z. B. 'Safari', 'Xcode', 'Terminal', 'System', 'Web')
     * topic = Konkreter Inhalt des Screenshots (z. B. 'Fehlermeldung_Build', 'Flugbuchung_Lufthansa', 'Rezept_Pasta', 'Code_Snippet')
     * suggested_folder = 'Medien/Screenshots' (oder bei Belegen direkt 'Finanzen/Belege')
   - Bei FOTOS (z. B. .jpg, .heic, .png ohne Dokumentencharakter):
     * Nutze das echte Aufnahmedatum aus den EXIF-Daten (kMDItemContentCreationDate), falls vorhanden!
     * doc_type = 'Foto'
     * sender = Aufnahmeort (Stadt/Land aus EXIF, falls vorhanden), sonst Kamera/Gerät (z. B. 'iPhone') oder 'Privat'
     * topic = Prägnante Beschreibung des Bildmotivs auf Deutsch (z. B. 'Strand_Sonnenuntergang', 'Familie_Garten', 'Hund_im_Park', 'Architektur')
     * suggested_folder = 'Medien/Fotos/YYYY' (mit dem Aufnahmejahr YYYY)
   - Bei VIDEOS & AUDIO:
     * doc_type = 'Video' bzw. 'Audio'
     * Nutze Titel, Album, Interpret oder Aufnahmedatum für einen sprechenden Namen und lege sie unter 'Medien/Videos' bzw. 'Medien/Audio' ab.

Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt in exakt folgendem Format:
{
  "doc_date": "YYYY-MM-DD",     // Das Hauptdatum (Dokumentendatum oder EXIF-Aufnahmedatum). Falls unbekannt: null
  "sender": "Absender/Ort/Quelle", // z.B. bunq, Telekom, iPhone, Rom, Xcode (Kurzname, keine Leerzeichen)
  "doc_type": "Dokumententyp",  // z.B. Transaktionsuebersicht, Kontoauszug, Rechnung, Vertrag, Foto, Screenshot, Video, Audio
  "topic": "Thema_Kurz",        // z.B. Konto_IBAN1234, Strand_Sonnenuntergang, Fehlermeldung_Login (1-3 Worte, prägnant)
  "suggested_filename": "YYYY-MM-DD_Absender_Dokumententyp_Thema", // Ohne Dateiendung! Keine Sonderzeichen außer Unterstrichen
  "suggested_folder": "Kategorie/Unterordner", // z.B. Finanzen/bunq, Rechnungen/Telekom, Medien/Fotos/2026, Medien/Screenshots
  "summary": "Prägnante 1-Satz-Zusammenfassung des Dokuments oder Bildmotivs auf Deutsch."
}

Wichtig:
- Wenn doc_date null ist, beginne suggested_filename direkt mit Absender_Dokumententyp_Thema.
- Verwende NIEMALS Leerzeichen im suggested_filename, sondern Unterstriche (_).
- Keine Umlaute im Dateinamen verwenden (ae, oe, ue, ss statt ä, ö, ü, ß).
- Antworte NUR als reines JSON-Objekt, kein Markdown, kein erklärender Text!
"""


def _query_gemini(
    prompt: str,
    api_key: str,
    model: str,
    image_base64: Optional[str] = None,
    image_mime: str = "image/jpeg"
) -> Optional[Dict[str, Any]]:
    """Sendet eine Anfrage an die Google Gemini API (eigener Schlüssel)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    return _query_generate(
        prompt, url, {"x-goog-api-key": api_key}, "Gemini API",
        image_base64=image_base64, image_mime=image_mime
    )


def _query_app(
    prompt: str,
    zugangscode: str,
    image_base64: Optional[str] = None,
    image_mime: str = "image/jpeg"
) -> Optional[Dict[str, Any]]:
    """Dieselbe Anfrage, aber über NotionaryAtlas — Modell und Schlüssel bestimmt die App."""
    return _query_generate(
        prompt, config.NOTIONARY_KI_URL, {"Authorization": f"Bearer {zugangscode}"}, "NotionaryAtlas",
        image_base64=image_base64, image_mime=image_mime
    )


def pruefe_zugangscode(zugangscode: str) -> Dict[str, Any]:
    """Fragt die App, ob der Zugangscode gilt. Verbraucht keine Credits."""
    req = urllib.request.Request(
        config.NOTIONARY_KI_URL,
        headers={"Authorization": f"Bearer {zugangscode.strip()}"},
        method="GET"
    )
    try:
        with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message")
        except Exception:
            msg = None
        return {"verbunden": False, "fehler": msg or f"HTTP {e.code}"}
    except Exception:
        return {"verbunden": False, "fehler": "NotionaryAtlas ist nicht erreichbar. Besteht eine Internetverbindung?"}


def _query_generate(
    prompt: str,
    url: str,
    auth_headers: Dict[str, str],
    ziel: str,
    image_base64: Optional[str] = None,
    image_mime: str = "image/jpeg"
) -> Optional[Dict[str, Any]]:
    """Gemeinsamer Weg für Gemini direkt und über die App (gleiches Anfrageformat, inkl. Multimodal Vision)."""
    parts = [{"text": SYSTEM_PROMPT + "\n\n" + prompt}]
    if image_base64:
        parts.append({
            "inlineData": {
                "mimeType": image_mime,
                "data": image_base64
            }
        })

    payload = {
        "contents": [
            {
                "parts": parts
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
        headers={"Content-Type": "application/json", **auth_headers},
        method="POST"
    )

    try:
        ctx = _get_ssl_context()
        with urllib.request.urlopen(req, context=ctx, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            candidates = result.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                resp_parts = content.get("parts", [])
                if resp_parts:
                    raw_text = resp_parts[0].get("text", "")
                    # Bereinigen falls Markdown-Wrapper vorliegt
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
                    raw_text = re.sub(r"\s*```$", "", raw_text)
                    return json.loads(raw_text)
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"[{ziel} HTTP Error {e.code}] {err_msg}")
        return None
    except Exception as e:
        print(f"[{ziel} Verbindungsfehler] {e}")
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
    Erkennt Bankauszüge, IBANs, Rechnungen, Screenshots, EXIF-Fotos und Apple Vision Bildmotive.
    """
    text_lower = (filename + " " + text[:3000]).lower()
    fn_lower = filename.lower()

    # 1. Datumssuche (zuerst EXIF ContentCreationDate prüfen, dann Text/Dateiname)
    doc_date = None
    exif_date_match = re.search(r'kMDItemContentCreationDate\s*=\s*(\d{4}-\d{2}-\d{2})', text)
    if exif_date_match:
        doc_date = exif_date_match.group(1)

    if not doc_date:
        # Suche nach Abrechnungsmonaten wie "07-2026"
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
                match = re.search(pat, filename + " " + text[:1500])
                if match:
                    g = match.groups()
                    if len(g[0]) == 4:
                        doc_date = f"{g[0]}-{g[1]}-{g[2]}"
                    else:
                        day, month, year = g[0].zfill(2), g[1].zfill(2), g[2]
                        doc_date = f"{year}-{month}-{day}"
                    break

    # 2. Prüfen ob Bild / Screenshot / Video / Audio
    is_image = ext in {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".webp", ".bmp", ".gif"}
    is_video = ext in {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
    is_audio = ext in {".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg"}
    is_screenshot = (
        "bildschirmfoto" in fn_lower
        or "screenshot" in fn_lower
        or "screen shot" in fn_lower
        or "kmditemisscreencapture = 1" in text_lower
    )

    # Apple Vision Bildmotive auslesen (falls vorhanden)
    scene_match = re.search(r'\[Apple Vision Bildmotive:\s*([^\]]+)\]', text)
    scene_top_label = ""
    if scene_match:
        raw_labels = scene_match.group(1).split(",")
        if raw_labels:
            # Erstes Label ohne Prozentzahl extrahieren
            first_lbl = re.sub(r'\(\d+%\)', '', raw_labels[0]).strip()
            scene_top_label = clean_filename(first_lbl)

    # EXIF-Kameramodell oder Ort suchen
    camera_match = re.search(r'kMDItemAcquisitionModel\s*=\s*"?([^"\n]+)"?', text)
    city_match = re.search(r'kMDItemCity\s*=\s*"?([^"\n]+)"?', text)

    # 3. Banken / Finanzdokumente erkennen
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
        for bank_name in ["bunq", "Sparkasse", "DKB", "N26", "Revolut", "PayPal"]:
            if bank_name.lower() in text_lower:
                sender = bank_name
                break
        else:
            sender = "Bank"
        topic = f"Konto{iban_suffix}"
        suggested_folder = f"Finanzen/{clean_filename(sender)}"
        summary_txt = f"Bankdokument ({doc_type}) von {sender}."
    elif is_screenshot:
        doc_type = "Screenshot"
        sender = "macOS"
        topic = scene_top_label if scene_top_label else clean_filename(Path(filename).stem)[:25]
        suggested_folder = "Medien/Screenshots"
        summary_txt = f"Bildschirmfoto ({topic})."
    elif is_image and not any(k in text_lower for k in ["rechnung", "invoice", "vertrag", "bescheid", "quittung"]):
        doc_type = "Foto"
        if city_match:
            sender = clean_filename(city_match.group(1))
        elif camera_match:
            sender = clean_filename(camera_match.group(1).replace("Apple ", ""))
        else:
            sender = "Aufnahme"
        topic = scene_top_label if scene_top_label else clean_filename(Path(filename).stem)[:20]
        year_folder = doc_date[:4] if doc_date else "Unsortiert"
        suggested_folder = f"Medien/Fotos/{year_folder}"
        summary_txt = f"Foto ({sender}, Motiv: {topic})."
    elif is_video:
        doc_type = "Video"
        sender = clean_filename(camera_match.group(1)) if camera_match else "Clip"
        year_folder = doc_date[:4] if doc_date else "Unsortiert"
        suggested_folder = f"Medien/Videos/{year_folder}"
        summary_txt = "Videodatei."
    elif is_audio:
        doc_type = "Audio"
        sender = "Medien"
        suggested_folder = "Medien/Audio"
        summary_txt = "Audiodatei."
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

        for brand in ["Telekom", "Vodafone", "Amazon", "Apple", "Google", "Finanzamt", "Allianz"]:
            if brand.lower() in text_lower:
                sender = brand
                break
        suggested_folder = f"{doc_type}en/{clean_filename(sender)}"
        summary_txt = "Klassifiziert per intelligenter Heuristik."

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
        "suggested_folder": suggested_folder,
        "summary": summary_txt
    }


def analyze_file_content(
    filename: str,
    text_content: str,
    metadata_info: str = "",
    provider: Optional[str] = None,
    prefix: Optional[str] = None,
    file_path: Optional[Path] = None,
    existing_folders: Optional[list] = None
) -> AnalysisResult:
    """
    Hauptfunktion: Analysiert Dateiname, extrahierten Text/EXIF und (bei Bildern) das Bild selbst
    mit dem gewählten KI-Provider und liefert ein strukturiertes AnalysisResult zurück.
    Falls ein Präfix angegeben ist (z.B. "01_"), wird es vorangestellt.
    Falls existing_folders übergeben wird, bevorzugt die KI bereits vorhandene Ordner.
    """
    ext = Path(filename).suffix.lower()
    active_provider = provider if provider else config.AI_PROVIDER

    text_snippet = text_content[:5000].strip()

    prompt = f"Dateiname: {filename}\n"
    if metadata_info:
        prompt += f"Zusätzliche Metadaten: {metadata_info}\n"
    if existing_folders:
        folders_str = ", ".join(existing_folders[:60])
        prompt += (
            f"\nBereits existierende Unterordner im Zielverzeichnis: [{folders_str}]\n"
            f"WICHTIG: Falls einer dieser bestehenden Ordner thematisch oder vom Absender her passt, "
            f"nutze EXAKT diesen Ordnerpfad für 'suggested_folder', um Ordner-Wildwuchs zu vermeiden!\n"
        )
    prompt += f"\nExtrahierter Inhalt / OCR / EXIF / Bildmotive:\n{text_snippet if text_snippet else '[Kein lesbarer Text gefunden]'}\n"

    ai_data: Optional[Dict[str, Any]] = None
    used_provider = "offline_heuristik"

    # Bild-Thumbnail für Multimodal Vision vorbereiten (falls Bilddatei und Cloud-KI aktiv)
    img_b64 = None
    img_mime = "image/jpeg"
    if (
        ((active_provider == "app" and config.NOTIONARY_ZUGANGSCODE) or (active_provider == "gemini" and config.GEMINI_API_KEY))
        and file_path
        and ext in {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tiff", ".tif", ".bmp"}
    ):
        from extractor import create_image_thumbnail_base64
        thumb = create_image_thumbnail_base64(file_path)
        if thumb:
            img_b64, img_mime = thumb

    # 1. Über NotionaryAtlas (Zugangscode)
    if active_provider == "app" and config.NOTIONARY_ZUGANGSCODE:
        mode_label = "Vision+Text" if img_b64 else "Text"
        print(f"🤖 [KI-Anfrage] Sende '{filename}' über NotionaryAtlas ({mode_label})...")
        ai_data = _query_app(prompt, config.NOTIONARY_ZUGANGSCODE, image_base64=img_b64, image_mime=img_mime)
        if ai_data:
            used_provider = "NotionaryAtlas"
            print(f"✓ [KI-Erfolg] Erkannt: {ai_data.get('sender')} | {ai_data.get('doc_type')} | {ai_data.get('suggested_filename')}")

    # 2. Gemini mit eigenem Schlüssel
    elif active_provider == "gemini" and config.GEMINI_API_KEY:
        mode_label = "Vision+Text" if img_b64 else "Text"
        print(f"🤖 [KI-Anfrage] Sende '{filename}' an Gemini ({config.GEMINI_MODEL}, {mode_label})...")
        ai_data = _query_gemini(prompt, config.GEMINI_API_KEY, config.GEMINI_MODEL, image_base64=img_b64, image_mime=img_mime)
        if ai_data:
            used_provider = f"gemini ({config.GEMINI_MODEL})"
            print(f"✓ [KI-Erfolg] Erkannt: {ai_data.get('sender')} | {ai_data.get('doc_type')} | {ai_data.get('suggested_filename')}")

    # 3. Lokaler Server
    elif active_provider == "local":
        print(f"🤖 [KI-Anfrage] Sende '{filename}' an lokalen Server...")
        ai_data = _query_local_llm(prompt, config.LOCAL_API_URL, config.LOCAL_MODEL)
        if ai_data:
            used_provider = f"local ({config.LOCAL_MODEL})"

    # 4. Fallback Heuristik
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

