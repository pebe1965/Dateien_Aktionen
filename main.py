#!/usr/bin/env python3
"""
Dateien_Aktionen CLI
Intelligente Datei-Organisation, OCR und KI-basierte Umbenennung für macOS.
"""

import sys
import argparse
from pathlib import Path

# Sicherstellen, dass das Projektverzeichnis im Pfad ist
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    AI_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL,
    LOCAL_API_URL, LOCAL_MODEL, OCR_BINARY
)
from classifier import Catalog
from extractor import extract_content
from organizer import Organizer, rollback_manifest, HISTORY_DIR

# ANSI-Farben für Terminal-Ausgabe
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[32m"
C_BLUE = "\033[34m"
C_CYAN = "\033[36m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_DIM = "\033[2m"


def print_header(title: str):
    print(f"\n{C_BOLD}{C_CYAN}{'='*60}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}  {title}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}{'='*60}{C_RESET}\n")


def cmd_catalog(args):
    """Katalogisiert einen Ordner und listet Dateitypen und Duplikate auf."""
    folder = Path(args.path).resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"{C_RED}Fehler: Ordner existiert nicht: {folder}{C_RESET}")
        return

    print_header(f"KATALOGISIERUNG: {folder.name}")
    print(f"Durchsuche '{folder}' ...")

    catalog = Catalog(folder)
    catalog.scan(compute_hashes=True)
    summary = catalog.summary()

    print(f"\n{C_BOLD}Gefundene Dateien insgesamt:{C_RESET} {summary['total_files']}")
    print(f"{C_BOLD}Gesamtgröße:{C_RESET} {summary['total_bytes'] / (1024*1024):.2f} MB\n")

    print(f"{C_BOLD}{'KATEGORIE':<18} {'ANZAHL':<10} {'GRÖSSE':<12}{C_RESET}")
    print("-" * 42)
    for cat, stats in sorted(summary["category_stats"].items(), key=lambda x: x[1]["count"], reverse=True):
        size_mb = stats["total_bytes"] / (1024 * 1024)
        print(f"{C_GREEN}{cat:<18}{C_RESET} {stats['count']:<10} {size_mb:>8.2f} MB")

    # Duplikate anzeigen
    if summary["duplicate_groups"] > 0:
        wasted_mb = summary["wasted_bytes"] / (1024 * 1024)
        print(f"\n{C_YELLOW}{C_BOLD}⚠ Duplikate gefunden:{C_RESET} {summary['duplicate_files_count']} doppelte Dateien ({wasted_mb:.2f} MB verschwendeter Platz)")
        print(f"{C_DIM}Beispiele für identische Dateien:{C_RESET}")
        shown = 0
        for h, items in catalog.duplicates.items():
            if shown >= 5:
                print(f"  ... und {len(catalog.duplicates) - 5} weitere Duplikat-Gruppen.")
                break
            print(f"  • {items[0].filename} ({len(items)} Kopien):")
            for it in items:
                print(f"    - {it.path.relative_to(folder)}")
            shown += 1
    else:
        print(f"\n{C_GREEN}✓ Keine identischen Duplikate gefunden.{C_RESET}")


def cmd_preview(args):
    """Führt Analyse & OCR durch und zeigt Namensvorschläge der KI ohne Änderungen an."""
    folder = Path(args.path).resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"{C_RED}Fehler: Ordner existiert nicht: {folder}{C_RESET}")
        return

    provider = args.provider or AI_PROVIDER
    print_header(f"VORSCHAU / DRY-RUN (KI: {provider})")
    print(f"Ordner: {folder}")
    if args.filter:
        print(f"Filter: Nur {args.filter}")

    organizer = Organizer(source_dir=folder, provider=provider)
    print("Analysiere Dateien & extrahiere Text/OCR ... Bitte warten.")
    plan = organizer.prepare_plan(category_filter=args.filter, max_files=args.limit)

    if not plan:
        print(f"\n{C_YELLOW}Keine passenden Dateien gefunden.{C_RESET}")
        return

    print(f"\n{C_BOLD}Ergebnis der KI-Analyse ({len(plan)} Dateien):{C_RESET}\n")
    for i, action in enumerate(plan, 1):
        a = action.analysis
        print(f"{C_CYAN}[{i}/{len(plan)}]{C_RESET} {C_BOLD}{action.source_path.name}{C_RESET}")
        print(f"   ➔ Neuer Name:    {C_GREEN}{C_BOLD}{a.suggested_name}{C_RESET}")
        print(f"   ➔ Ziel-Ordner:   {C_BLUE}{a.suggested_folder}{C_RESET}")
        print(f"   ➔ Typ / Absender:{a.doc_type} von '{a.sender}' (Datum: {a.doc_date or 'n/a'})")
        if a.summary:
            print(f"   ➔ Inhalt:        {C_DIM}{a.summary}{C_RESET}")
        print()

    print(f"{C_BOLD}{C_GREEN}✓ Vorschau abgeschlossen. Es wurden keine Dateien verändert.{C_RESET}")
    print(f"Um diese Änderungen anzuwenden, nutzen Sie: {C_BOLD}python main.py run {args.path}{C_RESET}\n")


def cmd_run(args):
    """Führt die Umbenennung und Sortierung nach Bestätigung aus."""
    folder = Path(args.path).resolve()
    target_dir = Path(args.target_dir).resolve() if args.target_dir else folder
    provider = args.provider or AI_PROVIDER

    print_header("DATEI-ORGANISATION AUSFÜHREN")
    print(f"Quelle:  {folder}")
    print(f"Ziel:    {target_dir}")
    print(f"KI:      {provider}")
    print(f"Modus:   {'Kopieren' if args.copy else 'Verschieben/Umbenennen'}\n")

    organizer = Organizer(source_dir=folder, target_dir=target_dir, provider=provider)
    print("Erstelle Plan ...")
    plan = organizer.prepare_plan(category_filter=args.filter, max_files=args.limit)

    if not plan:
        print(f"{C_YELLOW}Keine Dateien zum Organisieren gefunden.{C_RESET}")
        return

    print(f"\nEs wurden {C_BOLD}{len(plan)}{C_RESET} Dateien vorbereitet.")
    answer = input(f"\nMöchten Sie diese {len(plan)} Aktionen jetzt ausführen? [j/N]: ").strip().lower()
    if answer not in ["j", "ja", "y", "yes"]:
        print(f"{C_YELLOW}Vorgang abgebrochen. Keine Änderungen vorgenommen.{C_RESET}")
        return

    print("\nFühre Änderungen aus ...")
    manifest = organizer.execute_plan(copy_mode=args.copy)
    print(f"\n{C_BOLD}{C_GREEN}✓ Erfolgreich ausgeführt!{C_RESET}")
    print(f"Ein Wiederherstellungs-Protokoll wurde gespeichert unter:")
    print(f"  {C_CYAN}{manifest}{C_RESET}")
    print(f"\nFalls Sie alles rückgängig machen möchten:")
    print(f"  {C_BOLD}python main.py undo {manifest.name}{C_RESET}\n")


def cmd_undo(args):
    """Macht eine frühere Ausführung rückgängig."""
    print_header("UNDO / RÜCKGÄNGIG MACHEN")

    manifest_file = None
    if args.manifest:
        p = Path(args.manifest)
        if p.exists():
            manifest_file = p
        elif (HISTORY_DIR / args.manifest).exists():
            manifest_file = HISTORY_DIR / args.manifest
    else:
        # Neuestes Manifest wählen
        manifests = sorted(HISTORY_DIR.glob("manifest_*.json"))
        if manifests:
            manifest_file = manifests[-1]

    if not manifest_file or not manifest_file.exists():
        print(f"{C_RED}Kein Manifest zum Rückgängigmachen gefunden.{C_RESET}")
        return

    print(f"Nutze Manifest: {manifest_file.name}")
    confirm = input("Sind Sie sicher, dass Sie alle Aktionen rückgängig machen wollen? [j/N]: ").strip().lower()
    if confirm not in ["j", "ja", "y", "yes"]:
        print(f"{C_YELLOW}Abgebrochen.{C_RESET}")
        return

    restored = rollback_manifest(manifest_file)
    print(f"\n{C_BOLD}{C_GREEN}✓ {restored} Dateien wurden erfolgreich in den Ursprungszustand zurückversetzt!{C_RESET}\n")


def cmd_ocr_test(args):
    """Testet die OCR / Textextraktion an einer einzelnen Datei."""
    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"{C_RED}Datei existiert nicht: {file_path}{C_RESET}")
        return

    print_header(f"TEST EXTRAKTION: {file_path.name}")
    text, method = extract_content(file_path)

    print(f"{C_BOLD}Methode:{C_RESET} {C_GREEN}{method}{C_RESET}")
    print(f"{C_BOLD}Zeichen:{C_RESET} {len(text)}")
    print(f"\n{C_BOLD}Extrahierter Text (erste 1000 Zeichen):{C_RESET}\n")
    print(text[:1000] if text else f"{C_YELLOW}[Kein Text erkannt]{C_RESET}")
    print()


def cmd_config(args):
    """Zeigt die aktuelle Konfiguration an."""
    print_header("AKTUELLE KONFIGURATION")
    print(f"{C_BOLD}KI-Provider:{C_RESET}        {AI_PROVIDER}")
    import config as _cfg
    code_display = f"{C_GREEN}Gesetzt (…{_cfg.NOTIONARY_ZUGANGSCODE[-4:]}){C_RESET}" if _cfg.NOTIONARY_ZUGANGSCODE else f"{C_RED}Nicht gesetzt (NOTIONARY_ZUGANGSCODE){C_RESET}"
    print(f"{C_BOLD}NotionaryAtlas-Code:{C_RESET} {code_display}")
    print(f"{C_BOLD}Gemini-Modell:{C_RESET}      {GEMINI_MODEL}")
    has_gemini_key = bool(GEMINI_API_KEY)
    key_display = f"{C_GREEN}Gesetzt ({GEMINI_API_KEY[:6]}...){C_RESET}" if has_gemini_key else f"{C_RED}Nicht gesetzt (GEMINI_API_KEY){C_RESET}"
    print(f"{C_BOLD}Gemini-Key:{C_RESET}         {key_display}")
    print(f"{C_BOLD}Lokaler Server:{C_RESET}     {LOCAL_API_URL}")
    print(f"{C_BOLD}Lokales Modell:{C_RESET}     {LOCAL_MODEL}")
    ocr_status = f"{C_GREEN}Bereit ({OCR_BINARY}){C_RESET}" if OCR_BINARY.exists() else f"{C_RED}Nicht gefunden{C_RESET}"
    print(f"{C_BOLD}Apple Vision OCR:{C_RESET}   {ocr_status}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Dateien_Aktionen: KI-gestützte Datei-Organisation, OCR und Umbenennung für macOS"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: catalog
    p_cat = subparsers.add_parser("catalog", help="Scannt Ordner und listet Typen & Duplikate auf")
    p_cat.add_argument("path", help="Pfad zum Ordner")

    # Subcommand: preview
    p_prev = subparsers.add_parser("preview", help="Dry-Run: Zeigt KI-Namensvorschläge ohne Änderungen")
    p_prev.add_argument("path", help="Pfad zum Ordner")
    p_prev.add_argument("--provider", choices=["app", "gemini", "local", "offline"], help="KI-Provider überschreiben")
    p_prev.add_argument("--filter", help="Nur bestimmte Kategorie (z. B. DOKUMENTE, BILDER)")
    p_prev.add_argument("--limit", type=int, help="Maximale Anzahl an Dateien zur Analyse")

    # Subcommand: run
    p_run = subparsers.add_parser("run", help="Führt Umbenennung und Sortierung nach Freigabe aus")
    p_run.add_argument("path", help="Pfad zum Quellordner")
    p_run.add_argument("--target-dir", help="Optionaler Zielordner (Standard: Quellordner)")
    p_run.add_argument("--copy", action="store_true", help="Kopieren statt Verschieben")
    p_run.add_argument("--provider", choices=["app", "gemini", "local", "offline"], help="KI-Provider")
    p_run.add_argument("--filter", help="Kategorie-Filter")
    p_run.add_argument("--limit", type=int, help="Limit")

    # Subcommand: undo
    p_undo = subparsers.add_parser("undo", help="Macht frühere Operationen rückgängig")
    p_undo.add_argument("manifest", nargs="?", help="Name der Manifest-Datei (optional)")

    # Subcommand: ocr-test
    p_ocr = subparsers.add_parser("ocr-test", help="Testet OCR/Text an einer Datei")
    p_ocr.add_argument("file", help="Pfad zur Datei")

    # Subcommand: config
    subparsers.add_parser("config", help="Zeigt Konfiguration & Status an")

    args = parser.parse_args()

    dispatch = {
        "catalog": cmd_catalog,
        "preview": cmd_preview,
        "run": cmd_run,
        "undo": cmd_undo,
        "ocr-test": cmd_ocr_test,
        "config": cmd_config,
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
