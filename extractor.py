"""
Modul: extractor.py
Extrahiert Textinhalte aus Dokumenten, Scans, Office-Dateien und Bildern.
Nutzt natives macOS Vision OCR für Scans/Bilder sowie eingebaute Parser.
"""

import os
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple

from config import OCR_BINARY, OCR_MAX_PAGES, ICLOUD_BINARY

# Versuche pypdf zu importieren (bereits auf dem System vorhanden)
try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


def run_macos_vision_ocr(file_path: Path, max_pages: int = OCR_MAX_PAGES) -> str:
    """Führt OCR mit dem nativen macOS Vision Framework aus."""
    if not OCR_BINARY.exists():
        return ""

    try:
        cmd = [str(OCR_BINARY), str(file_path), str(max_pages)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        pass
    return ""


def extract_from_pdf(file_path: Path) -> Tuple[str, str]:
    """
    Extrahiert Text aus einem PDF.
    Prüft zuerst die digitale Textebene (pypdf).
    Falls kein Text vorhanden ist (z. B. Scan), greift das macOS Vision OCR.
    Rückgabe: (extrahierter_text, methode)
    """
    text = ""
    # 1. Schnelle Extraktion aus digitaler Textebene
    if PYPDF_AVAILABLE:
        try:
            reader = pypdf.PdfReader(str(file_path))
            pages_to_read = min(len(reader.pages), OCR_MAX_PAGES)
            extracted = []
            for i in range(pages_to_read):
                page_text = reader.pages[i].extract_text()
                if page_text:
                    extracted.append(page_text)
            text = "\n".join(extracted).strip()
        except Exception:
            text = ""

    # 2. Wenn wenig oder kein Text gefunden wurde -> Reiner Scan -> Vision OCR
    if len(text.replace(" ", "").replace("\n", "")) < 30:
        ocr_text = run_macos_vision_ocr(file_path)
        if ocr_text:
            return ocr_text, "macOS_Vision_OCR"
        return text, "pypdf_minimal"

    return text, "pypdf_digital"


def extract_from_docx(file_path: Path) -> str:
    """Extrahiert Text aus einer .docx-Datei ohne externe Bibliotheken."""
    try:
        with zipfile.ZipFile(file_path, "r") as z:
            if "word/document.xml" in z.namelist():
                xml_content = z.read("word/document.xml")
                root = ET.fromstring(xml_content)
                # Word-XML Namensraum für Text: {http://schemas.openxmlformats.org/wordprocessingml/2006/main}t
                texts = [elem.text for elem in root.iter() if elem.text and elem.tag.endswith("}t")]
                return "\n".join(texts)
    except Exception:
        pass
    return ""


def extract_from_xlsx(file_path: Path) -> str:
    """Extrahiert Text (Shared Strings) aus einer .xlsx-Datei ohne externe Bibliotheken."""
    try:
        with zipfile.ZipFile(file_path, "r") as z:
            if "xl/sharedStrings.xml" in z.namelist():
                xml_content = z.read("xl/sharedStrings.xml")
                root = ET.fromstring(xml_content)
                texts = [elem.text for elem in root.iter() if elem.text and elem.tag.endswith("}t")]
                return " ".join(texts)
    except Exception:
        pass
    return ""


def extract_via_textutil(file_path: Path) -> str:
    """Nutzt das native macOS-Tool `textutil` für Word, RTF, HTML etc."""
    try:
        cmd = ["textutil", "-convert", "txt", "-stdout", str(file_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def extract_from_apple_iwork(file_path: Path) -> Tuple[str, str]:
    """
    Extrahiert Text aus Apple iWork-Dateien (.pages, .numbers, .key).
    Pages-Dateien enthalten oft eine QuickLook/Preview.pdf, die per OCR/PDF ausgelesen werden kann.
    """
    try:
        # Oft ist .pages ein Zip-Paket mit Preview.pdf
        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, "r") as z:
                for name in ["QuickLook/Preview.pdf", "preview.pdf"]:
                    if name in z.namelist():
                        temp_pdf = Path(f"/tmp/pages_preview_{file_path.stem}.pdf")
                        with open(temp_pdf, "wb") as f_out:
                            f_out.write(z.read(name))
                        text, method = extract_from_pdf(temp_pdf)
                        if temp_pdf.exists():
                            temp_pdf.unlink()
                        if text:
                            return text, f"iwork_preview_{method}"
    except Exception:
        pass

    # Fallback: metadata via mdls (macOS Spotlight)
    return extract_macos_metadata_text(file_path), "macos_metadata"


def extract_macos_metadata_text(file_path: Path) -> str:
    """Liest macOS Spotlight-Metadaten (Titel, Autoren, Beschreibung) aus."""
    try:
        res = subprocess.run(
            ["mdls", "-name", "kMDItemTitle", "-name", "kMDItemAuthors", "-name", "kMDItemDescription", "-name", "kMDItemHeadline", str(file_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=5
        )
        if res.returncode == 0:
            lines = [l.strip() for l in res.stdout.splitlines() if "(null)" not in l and "=" in l]
            return " ".join(lines)
    except Exception:
        pass
    return ""


def is_dataless_file(file_path: Path) -> bool:
    """Prüft, ob eine Datei ausgelagert ist (iCloud/Nextcloud)."""
    try:
        if file_path.name.endswith(".icloud"):
            return True
        st = file_path.stat()
        return bool(getattr(st, "st_flags", 0) & 0x40000000)
    except Exception:
        return False


def download_cloud_file(file_path: Path, timeout: int = 20) -> bool:
    """
    Lädt eine ausgelagerte Datei aus der iCloud / Cloud auf den lokalen Mac herunter.
    Nutzt das native macOS Foundation Tool `bin/icloud_download`.
    Gibt True zurück, wenn die Datei nun lokal verfügbar ist, sonst False.
    """
    if not is_dataless_file(file_path):
        return True

    if ICLOUD_BINARY.exists():
        try:
            print(f"☁️ [iCloud] Lade ausgelagerte Datei herunter: {file_path.name}...")
            res = subprocess.run(
                [str(ICLOUD_BINARY), str(file_path), str(timeout)],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout + 5
            )
            if res.returncode == 0 and not is_dataless_file(file_path):
                print(f"✓ [iCloud] Datei erfolgreich heruntergeladen: {file_path.name}")
                return True
        except Exception as e:
            print(f"⚠️ [iCloud] Fehler beim Laden von {file_path.name}: {e}")

    return not is_dataless_file(file_path)


def extract_content(file_path: Path, auto_download_cloud: bool = True) -> Tuple[str, str]:
    """
    Hauptfunktion: Ermittelt die passende Extraktionsmethode
    und gibt (extrahierter_text, extraktions_methode) zurück.
    Falls auto_download_cloud=True ist, werden ausgelagerte iCloud-Dateien
    automatisch auf Abruf heruntergeladen.
    """
    if is_dataless_file(file_path):
        if auto_download_cloud:
            downloaded = download_cloud_file(file_path, timeout=20)
            if not downloaded:
                return ("[Ausgelagerte Cloud-Datei: Konnte nicht aus iCloud geladen werden (evtl. offline)]", "cloud_placeholder")
        else:
            return ("[Ausgelagerte Cloud-Datei: Vor Analyse bitte im Finder anklicken/herunterladen]", "cloud_placeholder")

    ext = file_path.suffix.lower()

    # 1. PDF
    if ext == ".pdf":
        return extract_from_pdf(file_path)

    # 2. Bilder (OCR)
    if ext in {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".tif", ".webp", ".bmp"}:
        ocr_text = run_macos_vision_ocr(file_path)
        return ocr_text, "macOS_Vision_OCR"

    # 3. Reine Textdateien
    if ext in {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml"}:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(10000)  # Erste 10.000 Zeichen genügen für Analyse
                return content, "text_direct"
        except Exception:
            pass

    # 4. Word-Dokumente
    if ext == ".docx":
        text = extract_from_docx(file_path)
        if not text:
            text = extract_via_textutil(file_path)
        return text, "docx_parser"
    if ext in {".doc", ".rtf", ".rtfd"}:
        text = extract_via_textutil(file_path)
        return text, "textutil"

    # 5. Excel
    if ext == ".xlsx":
        text = extract_from_xlsx(file_path)
        return text, "xlsx_parser"

    # 6. Apple iWork (Pages, Numbers, Keynote)
    if ext in {".pages", ".numbers", ".key"}:
        return extract_from_apple_iwork(file_path)

    # 7. Fallback für Medien (Video, Audio etc.) -> Metadaten via Spotlight
    metadata = extract_macos_metadata_text(file_path)
    return metadata, "macos_spotlight_metadata"
