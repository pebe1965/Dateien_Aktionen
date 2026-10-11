#!/usr/bin/env python3
"""
Dateien_Aktionen GUI
Moderne Web-basierte Benutzeroberfläche für macOS.
Startet einen lokalen Server und öffnet das Dashboard automatisch im Browser.
"""

import os
import sys
import json
import socket
import webbrowser
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Projektpfad einbinden
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import config
from classifier import Catalog
from extractor import extract_content
from organizer import Organizer, rollback_manifest, HISTORY_DIR


def move_to_macos_trash(file_path: Path) -> bool:
    """Verschiebt eine Datei sicher in den macOS Papierkorb (~/.Trash)."""
    try:
        # 1. Bevorzuge Applescript Finder delete (nativer Papierkorb mit Zurücklegen-Option)
        escaped_path = str(file_path.resolve()).replace('"', '\\"')
        cmd = ["osascript", "-e", f'tell application "Finder" to delete (POSIX file "{escaped_path}")']
        res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=6)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    # 2. Fallback: Direkt in ~/.Trash verschieben mit Zeitstempel bei Namensdopplung
    try:
        trash_dir = Path.home() / ".Trash"
        if trash_dir.exists():
            target = trash_dir / file_path.name
            if target.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                ts = datetime.now().strftime("%H%M%S")
                target = trash_dir / f"{stem}_{ts}{suffix}"
            shutil.move(str(file_path), str(target))
            return True
    except Exception:
        pass
    return False


PORT = 8765

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dateien_Aktionen 🗂️ macOS</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    </style>
</head>
<body class="bg-slate-50 text-slate-900 min-h-screen">
    <!-- Header -->
    <header class="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
        <div class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center font-bold text-xl shadow-md">
                    📁
                </div>
                <div>
                    <h1 class="font-bold text-lg leading-tight text-slate-800">Dateien_Aktionen</h1>
                    <p class="text-xs text-slate-500">KI- & OCR-Dateimanager für macOS</p>
                </div>
            </div>

            <!-- Status Badges -->
            <div class="flex items-center gap-3 text-xs" id="status-badges">
                <span id="badge-ocr" class="px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 font-medium">OCR: Lädt...</span>
                <span id="badge-ai" class="px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 font-medium">KI: Lädt...</span>
                <button onclick="openTab('settings')" class="p-2 text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-100 transition">
                    ⚙️ Einstellungen
                </button>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
        <!-- Ordnerauswahl Box -->
        <div class="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 mb-8">
            <div class="flex flex-col md:flex-row gap-4 items-end">
                <div class="flex-1 w-full">
                    <label class="block text-sm font-semibold text-slate-700 mb-2">Quellordner zum Scannen & Organisieren:</label>
                    <div class="flex gap-2">
                        <input type="text" id="folder-path" placeholder="/Users/.../Downloads" class="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-mono bg-slate-50">
                        <button onclick="pickFolder()" class="px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-sm font-medium transition flex items-center gap-1.5 whitespace-nowrap">
                            📂 Durchsuchen...
                        </button>
                    </div>
                </div>
                <div class="flex gap-2 w-full md:w-auto">
                    <button onclick="startCatalog()" id="btn-catalog" class="flex-1 md:flex-none px-5 py-2.5 bg-slate-800 hover:bg-slate-900 text-white rounded-xl text-sm font-semibold transition flex items-center justify-center gap-2 shadow-sm">
                        🔍 1. Katalogisieren
                    </button>
                    <button onclick="startPreview()" id="btn-preview" class="flex-1 md:flex-none px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-semibold transition flex items-center justify-center gap-2 shadow-sm">
                        🧠 2. KI-Vorschau
                    </button>
                </div>
            </div>
        </div>

        <!-- Tabs Navigation -->
        <div class="flex border-b border-slate-200 mb-6 gap-2">
            <button onclick="openTab('preview')" id="tab-btn-preview" class="tab-btn active px-4 py-2.5 font-medium text-sm border-b-2 border-blue-600 text-blue-600">
                ✨ KI-Umbenennung & Vorschau
            </button>
            <button onclick="openTab('catalog')" id="tab-btn-catalog" class="tab-btn px-4 py-2.5 font-medium text-sm border-b-2 border-transparent text-slate-500 hover:text-slate-800">
                📊 Dateikatalog & Duplikate
            </button>
            <button onclick="openTab('history')" id="tab-btn-history" class="tab-btn px-4 py-2.5 font-medium text-sm border-b-2 border-transparent text-slate-500 hover:text-slate-800">
                🕒 Protokoll & Rückgängig (Undo)
            </button>
            <button onclick="openTab('settings')" id="tab-btn-settings" class="tab-btn px-4 py-2.5 font-medium text-sm border-b-2 border-transparent text-slate-500 hover:text-slate-800">
                ⚙️ Einstellungen
            </button>
        </div>

        <!-- TAB: PREVIEW / KI-UMBENENNUNG -->
        <div id="tab-preview" class="tab-content">
            <div id="preview-placeholder" class="text-center py-16 bg-white rounded-2xl border border-dashed border-slate-300">
                <div class="text-4xl mb-3">🪄</div>
                <h3 class="font-semibold text-slate-700 text-lg">Noch keine KI-Vorschau geladen</h3>
                <p class="text-sm text-slate-500 mt-1 max-w-md mx-auto">
                    Wählen Sie oben einen Ordner aus und klicken Sie auf <b>„2. KI-Vorschau“</b>, um Dokumente per OCR zu lesen und Namensvorschläge zu generieren.
                </p>
            </div>

            <div id="preview-results" class="hidden">
                <!-- Action Bar -->
                <div class="flex flex-wrap items-center justify-between gap-4 mb-4 bg-blue-50/70 p-4 rounded-xl border border-blue-100">
                    <div class="text-sm text-blue-900">
                        <span id="selected-count" class="font-bold">0</span> Dateien ausgewählt zur Organisation.
                    </div>
                    <div class="flex items-center gap-3">
                        <label class="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                            <input type="checkbox" id="copy-mode" class="rounded text-blue-600">
                            Kopieren (statt Verschieben)
                        </label>
                        <button onclick="executeRenaming()" id="btn-execute" class="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-semibold transition shadow-sm flex items-center gap-2">
                            🚀 Jetzt anwenden (<span id="btn-exec-count">0</span>)
                        </button>
                    </div>
                </div>

                <!-- Table -->
                <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-sm">
                            <thead class="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200 text-xs uppercase tracking-wider">
                                <tr>
                                    <th class="p-4 w-12 text-center">
                                        <input type="checkbox" id="select-all" onchange="toggleSelectAll(this)" checked class="rounded text-blue-600">
                                    </th>
                                    <th class="p-4">Ursprüngliche Datei</th>
                                    <th class="p-4">Neuer Name (editierbar)</th>
                                    <th class="p-4">Zielordner</th>
                                    <th class="p-4">Erkannt</th>
                                </tr>
                            </thead>
                            <tbody id="preview-tbody" class="divide-y divide-slate-100">
                                <!-- Zeilen werden per JS eingefügt -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB: KATALOG & DUPLIKATE -->
        <div id="tab-catalog" class="tab-content hidden">
            <div id="catalog-placeholder" class="text-center py-16 bg-white rounded-2xl border border-dashed border-slate-300">
                <div class="text-4xl mb-3">📊</div>
                <h3 class="font-semibold text-slate-700 text-lg">Noch kein Ordner katalogisiert</h3>
                <p class="text-sm text-slate-500 mt-1">Klicken Sie oben auf „1. Katalogisieren“ für eine Bestandsaufnahme.</p>
            </div>

            <div id="catalog-results" class="hidden space-y-6">
                <!-- Summary Stats -->
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" id="stats-grid">
                    <!-- Stat cards per JS -->
                </div>

                <!-- Categories & Duplicates split -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                        <h4 class="font-bold text-slate-800 mb-4 flex items-center gap-2">
                            📁 Dateitypen-Übersicht
                        </h4>
                        <div id="categories-list" class="space-y-3"></div>
                    </div>

                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                        <h4 class="font-bold text-slate-800 mb-4 flex items-center gap-2 text-amber-600">
                            ⚠️ Exakte Duplikate (gleicher Hash)
                        </h4>
                        <div id="duplicates-list" class="space-y-3 max-h-96 overflow-y-auto"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB: HISTORY / UNDO -->
        <div id="tab-history" class="tab-content hidden">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h4 class="font-bold text-slate-800 mb-2">Vergangene Ausführungen (Manifeste)</h4>
                <p class="text-sm text-slate-500 mb-6">Sie können jede frühere Dateiaktion mit einem einzigen Klick wieder in den Ursprungszustand zurückversetzen.</p>
                <div id="history-list" class="space-y-3">
                    <p class="text-slate-400 text-sm">Lade Historie...</p>
                </div>
            </div>
        </div>

        <!-- TAB: SETTINGS -->
        <div id="tab-settings" class="tab-content hidden">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 max-w-2xl">
                <h4 class="font-bold text-slate-800 mb-4">Einstellungen & KI-Konfiguration</h4>
                
                <div class="space-y-4">
                    <div>
                        <label class="block text-sm font-semibold text-slate-700 mb-1">KI-Provider</label>
                        <select id="cfg-provider" class="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm">
                            <option value="gemini">Google Gemini API (Cloud / Entwickler-Account)</option>
                            <option value="local">Lokaler KI-Server (LM Studio / MLX / Ollama)</option>
                            <option value="offline">Offline-Heuristik (ohne KI, via Regex & Metadaten)</option>
                        </select>
                    </div>

                    <div>
                        <label class="block text-sm font-semibold text-slate-700 mb-1">Gemini API-Schlüssel</label>
                        <input type="password" id="cfg-gemini-key" placeholder="AIzaSy..." class="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-mono">
                        <p class="text-xs text-slate-400 mt-1">Ihr bestehender Schlüssel aus Google AI Studio / WebApp.</p>
                    </div>

                    <div>
                        <label class="block text-sm font-semibold text-slate-700 mb-1">Gemini Modell</label>
                        <input type="text" id="cfg-gemini-model" placeholder="gemini-2.5-flash" class="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-mono">
                        <p class="text-xs text-slate-400 mt-1">z. B. gemini-2.5-flash, gemini-3.7-flash, gemini-3.8-flash, gemini-3.1-pro</p>
                    </div>

                    <div class="pt-2 border-t border-slate-100">
                        <label class="block text-sm font-semibold text-slate-700 mb-1">Lokale Server-URL (für LM Studio / MLX)</label>
                        <input type="text" id="cfg-local-url" placeholder="http://localhost:1234/v1/chat/completions" class="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-mono">
                    </div>

                    <button onclick="saveConfig()" class="w-full mt-4 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-semibold transition">
                        Einstellungen speichern
                    </button>
                    <div id="save-msg" class="text-xs text-emerald-600 font-medium text-center hidden">✓ Gespeichert!</div>
                </div>
            </div>
        </div>
    </main>

    <!-- Loading Spinner Modal -->
    <div id="loading-modal" class="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center z-50 hidden">
        <div class="bg-white p-6 rounded-2xl shadow-xl flex flex-col items-center gap-4 max-w-sm text-center">
            <div class="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
            <div>
                <h4 id="loading-title" class="font-bold text-slate-800">Verarbeite...</h4>
                <p id="loading-desc" class="text-xs text-slate-500 mt-1">Bitte einen Moment Geduld.</p>
            </div>
        </div>
    </div>

    <script>
        let currentPlan = [];

        function showLoading(title, desc) {
            document.getElementById('loading-title').innerText = title;
            document.getElementById('loading-desc').innerText = desc || 'Bitte warten...';
            document.getElementById('loading-modal').classList.remove('hidden');
        }

        function hideLoading() {
            document.getElementById('loading-modal').classList.add('hidden');
        }

        function openTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.remove('border-blue-600', 'text-blue-600');
                btn.classList.add('border-transparent', 'text-slate-500');
            });
            document.getElementById('tab-' + tabId).classList.remove('hidden');
            const activeBtn = document.getElementById('tab-btn-' + tabId);
            activeBtn.classList.remove('border-transparent', 'text-slate-500');
            activeBtn.classList.add('border-blue-600', 'text-blue-600');

            if (tabId === 'history') loadHistory();
        }

        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                // OCR Badge
                const bOcr = document.getElementById('badge-ocr');
                if (data.ocr_ready) {
                    bOcr.className = 'px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 font-medium';
                    bOcr.innerText = '✓ Apple Vision OCR aktiv';
                } else {
                    bOcr.className = 'px-2.5 py-1 rounded-full bg-amber-100 text-amber-700 font-medium';
                    bOcr.innerText = '⚠ OCR nicht bereit';
                }

                // AI Badge
                const bAi = document.getElementById('badge-ai');
                if (data.ai_provider === 'gemini') {
                    if (data.gemini_key_set) {
                        bAi.className = 'px-2.5 py-1 rounded-full bg-blue-100 text-blue-700 font-medium';
                        bAi.innerText = `Gemini (${data.gemini_model})`;
                    } else {
                        bAi.className = 'px-2.5 py-1 rounded-full bg-red-100 text-red-700 font-medium cursor-pointer';
                        bAi.innerText = '⚠ Gemini Key fehlt (hier klicken)';
                        bAi.onclick = () => openTab('settings');
                    }
                } else {
                    bAi.className = 'px-2.5 py-1 rounded-full bg-purple-100 text-purple-700 font-medium';
                    bAi.innerText = `KI: ${data.ai_provider}`;
                }

                // Pre-fill settings
                document.getElementById('cfg-provider').value = data.ai_provider;
                document.getElementById('cfg-gemini-model').value = data.gemini_model;
                document.getElementById('cfg-local-url').value = data.local_url;
                if (data.folder_suggestion) {
                    document.getElementById('folder-path').value = data.folder_suggestion;
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function pickFolder() {
            showLoading('Ordner auswählen', 'Warten auf Finder-Dialog...');
            try {
                const res = await fetch('/api/pick_folder', { method: 'POST' });
                const data = await res.json();
                if (data.path) {
                    document.getElementById('folder-path').value = data.path;
                }
            } catch (e) {
                console.error(e);
            } finally {
                hideLoading();
            }
        }

        async function startCatalog() {
            const folder = document.getElementById('folder-path').value.trim();
            if (!folder) return alert('Bitte zuerst einen Ordner angeben oder durchsuchen.');

            showLoading('Katalogisiere Ordner', 'Dateien werden gescannt und Prüfsummen berechnet...');
            try {
                const res = await fetch('/api/catalog', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ path: folder })
                });
                const data = await res.json();
                if (data.error) throw new Error(data.error);

                renderCatalog(data);
                openTab('catalog');
            } catch (e) {
                alert('Fehler: ' + e.message);
            } finally {
                hideLoading();
            }
        }

        function renderCatalog(data) {
            document.getElementById('catalog-placeholder').classList.add('hidden');
            document.getElementById('catalog-results').classList.remove('hidden');

            const s = data.summary;
            const mb = (s.total_bytes / (1024*1024)).toFixed(1);
            const wastedMb = (s.wasted_bytes / (1024*1024)).toFixed(1);
            let sizeStr = mb + ' MB';
            if (s.total_bytes >= 1024*1024*1024) {
                sizeStr = (s.total_bytes / (1024*1024*1024)).toFixed(2) + ' GB';
            }

            document.getElementById('stats-grid').innerHTML = `
                <div class="bg-white p-5 rounded-2xl border border-slate-200">
                    <div class="text-xs text-slate-500 font-semibold uppercase">Dateien insgesamt</div>
                    <div class="text-2xl font-bold text-slate-800 mt-1">${s.total_files}</div>
                    <div class="text-xs text-slate-400 mt-1">Eingelesene Elemente</div>
                </div>
                <div class="bg-white p-5 rounded-2xl border border-slate-200">
                    <div class="text-xs text-slate-500 font-semibold uppercase">Ordnergröße gesamt</div>
                    <div class="text-2xl font-bold text-indigo-600 mt-1">${sizeStr}</div>
                    <div class="text-xs text-slate-400 mt-1">${mb} MB auf Datenträger</div>
                </div>
                <div class="bg-white p-5 rounded-2xl border border-slate-200">
                    <div class="text-xs text-slate-500 font-semibold uppercase">Kategorien</div>
                    <div class="text-2xl font-bold text-blue-600 mt-1">${Object.keys(s.category_stats).length}</div>
                    <div class="text-xs text-slate-400 mt-1">Dokumente, Bilder etc.</div>
                </div>
                <div class="bg-white p-5 rounded-2xl border border-slate-200">
                    <div class="text-xs text-slate-500 font-semibold uppercase">Duplikate</div>
                    <div class="text-2xl font-bold ${s.duplicate_files_count > 0 ? 'text-amber-500' : 'text-emerald-600'} mt-1">${s.duplicate_files_count}</div>
                    <div class="text-xs text-slate-400 mt-1">${wastedMb} MB verschwendet</div>
                </div>
            `;

            // Categories
            const catHtml = Object.entries(s.category_stats).map(([cat, info]) => `
                <div class="flex items-center justify-between p-3 rounded-xl bg-slate-50 text-sm">
                    <span class="font-medium text-slate-700">${cat}</span>
                    <span class="text-slate-500 font-mono text-xs">${info.count} Dateien (${(info.total_bytes / (1024*1024)).toFixed(1)} MB)</span>
                </div>
            `).join('');
            document.getElementById('categories-list').innerHTML = catHtml || '<p class="text-xs text-slate-400">Keine Daten</p>';

            // Duplicates
            if (Object.keys(data.duplicates).length === 0) {
                document.getElementById('duplicates-list').innerHTML = '<p class="text-sm text-emerald-600 font-medium">✓ Keine Duplikate gefunden!</p>';
            } else {
                const dupHtml = Object.entries(data.duplicates).map(([hash, list]) => `
                    <div class="p-3 bg-amber-50 rounded-xl border border-amber-100 text-xs">
                        <div class="font-bold text-amber-900">${list[0].filename} (${list.length} identische Kopien)</div>
                        <ul class="mt-1 list-disc list-inside text-amber-700 truncate">
                            ${list.map(f => `<li>${f.path}</li>`).join('')}
                        </ul>
                    </div>
                `).join('');
                document.getElementById('duplicates-list').innerHTML = dupHtml;
            }
        }

        async function startPreview() {
            const folder = document.getElementById('folder-path').value.trim();
            if (!folder) return alert('Bitte zuerst einen Ordner angeben.');

            showLoading('KI-Analyse läuft', 'Extrahiere Text, führe OCR durch und frage die KI nach sinnvollen Namen...');
            try {
                const res = await fetch('/api/preview', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ path: folder })
                });
                const data = await res.json();
                if (data.error) throw new Error(data.error);

                currentPlan = data.plan;
                renderPreview(currentPlan);
                openTab('preview');
            } catch (e) {
                alert('Fehler: ' + e.message);
            } finally {
                hideLoading();
            }
        }

        function renderPreview(plan) {
            document.getElementById('preview-placeholder').classList.add('hidden');
            document.getElementById('preview-results').classList.remove('hidden');

            const tbody = document.getElementById('preview-tbody');
            if (plan.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="p-8 text-center text-slate-400">Keine Dateien gefunden.</td></tr>';
                return;
            }

            tbody.innerHTML = plan.map((item, idx) => `
                <tr class="hover:bg-slate-50 transition" data-idx="${idx}">
                    <td class="p-4 text-center">
                        <input type="checkbox" class="file-chk rounded text-blue-600" checked onchange="updateSelectedCount()">
                    </td>
                    <td class="p-4">
                        <div class="font-medium text-slate-800 break-all">${item.original_name}</div>
                        <div class="text-xs text-slate-400 mt-0.5">${item.source_path}</div>
                    </td>
                    <td class="p-4">
                        <input type="text" value="${item.new_name}" class="new-name-input w-full px-3 py-1.5 rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 text-sm font-semibold text-emerald-700 bg-emerald-50/30">
                    </td>
                    <td class="p-4">
                        <span class="px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 text-xs font-medium">${item.analysis.suggested_folder}</span>
                    </td>
                    <td class="p-4 text-xs">
                        <div class="font-semibold text-slate-700">${item.analysis.doc_type} / ${item.analysis.sender}</div>
                        <div class="text-slate-400 mt-0.5">${item.analysis.doc_date || 'Kein Datum'}</div>
                    </td>
                </tr>
            `).join('');

            updateSelectedCount();
        }

        function toggleSelectAll(master) {
            document.querySelectorAll('.file-chk').forEach(c => c.checked = master.checked);
            updateSelectedCount();
        }

        function updateSelectedCount() {
            const count = document.querySelectorAll('.file-chk:checked').length;
            document.getElementById('selected-count').innerText = count;
            document.getElementById('btn-exec-count').innerText = count;
        }

        async function executeRenaming() {
            const checkboxes = document.querySelectorAll('.file-chk');
            const itemsToExecute = [];

            checkboxes.forEach((cb, idx) => {
                if (cb.checked) {
                    const planItem = currentPlan[idx];
                    // Name aus dem Input übernehmen falls editiert
                    const row = cb.closest('tr');
                    const inputVal = row.querySelector('.new-name-input').value.trim();
                    planItem.new_name = inputVal;
                    itemsToExecute.push(planItem);
                }
            });

            if (itemsToExecute.length === 0) return alert('Keine Dateien ausgewählt.');

            const copyMode = document.getElementById('copy-mode').checked;
            const msg = `Möchten Sie ${itemsToExecute.length} Dateien jetzt wirklich ${copyMode ? 'kopieren' : 'verschieben/umbenennen'}?`;
            if (!confirm(msg)) return;

            showLoading('Wende Änderungen an...', 'Dateien werden sortiert und umbenannt...');
            try {
                const res = await fetch('/api/execute', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        items: itemsToExecute,
                        copy_mode: copyMode
                    })
                });
                const data = await res.json();
                if (data.error) throw new Error(data.error);

                alert(`✓ Erfolgreich abgeschlossen!\nManifest: ${data.manifest}`);
                openTab('history');
            } catch (e) {
                alert('Fehler: ' + e.message);
            } finally {
                hideLoading();
            }
        }

        async function loadHistory() {
            try {
                const res = await fetch('/api/history');
                const data = await res.json();
                const list = document.getElementById('history-list');

                if (data.manifests.length === 0) {
                    list.innerHTML = '<p class="text-xs text-slate-400">Bisher keine Aktionen durchgeführt.</p>';
                    return;
                }

                list.innerHTML = data.manifests.map(m => `
                    <div class="flex items-center justify-between p-4 rounded-xl border border-slate-200 bg-slate-50">
                        <div>
                            <div class="font-semibold text-slate-800 text-sm">${m.filename}</div>
                            <div class="text-xs text-slate-500 mt-0.5">${m.total_actions} Aktionen am ${m.date}</div>
                        </div>
                        <button onclick="undoManifest('${m.filename}')" class="px-3.5 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 text-xs font-semibold rounded-lg transition border border-rose-200">
                            ↩️ Rückgängig machen
                        </button>
                    </div>
                `).join('');
            } catch (e) {
                console.error(e);
            }
        }

        async function undoManifest(filename) {
            if (!confirm(`Sollen alle Aktionen aus '${filename}' rückgängig gemacht werden?`)) return;

            showLoading('Rückgängig machen...', 'Dateien werden an ihren Ursprungsort zurückversetzt...');
            try {
                const res = await fetch('/api/undo', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ manifest: filename })
                });
                const data = await res.json();
                if (data.error) throw new Error(data.error);

                alert(`✓ ${data.restored} Dateien wurden erfolgreich wiederhergestellt!`);
                loadHistory();
            } catch (e) {
                alert('Fehler: ' + e.message);
            } finally {
                hideLoading();
            }
        }

        async function saveConfig() {
            const payload = {
                ai_provider: document.getElementById('cfg-provider').value,
                gemini_api_key: document.getElementById('cfg-gemini-key').value,
                gemini_model: document.getElementById('cfg-gemini-model').value,
                local_url: document.getElementById('cfg-local-url').value
            };

            try {
                const res = await fetch('/api/save_config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    const msg = document.getElementById('save-msg');
                    msg.classList.remove('hidden');
                    setTimeout(() => msg.classList.add('hidden'), 3000);
                    fetchStatus();
                }
            } catch (e) {
                alert('Fehler beim Speichern');
            }
        }

        // Init
        fetchStatus();
    </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Ruhiges Logging im Terminal
        pass

    def do_GET(self):
        url = urlparse(self.path)

        if url.path == "/" or url.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            template_path = BASE_DIR / "templates" / "index.html"
            if template_path.exists():
                with open(template_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(HTML_DASHBOARD.encode("utf-8"))
            return

        if url.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "ai_provider": config.AI_PROVIDER,
                "gemini_key_set": bool(config.GEMINI_API_KEY),
                "app_code_set": bool(config.NOTIONARY_ZUGANGSCODE),
                "marketplace_url": config.NOTIONARY_MARKETPLACE_URL,
                "gemini_model": config.GEMINI_MODEL,
                "local_url": config.LOCAL_API_URL,
                "local_model": config.LOCAL_MODEL,
                "ocr_ready": config.OCR_BINARY.exists(),
                "folder_suggestion": str(Path.home() / "Downloads"),
                "app_version": getattr(config, "APP_VERSION", "1.0.0"),
                "github_repo": getattr(config, "GITHUB_REPO", "pebe1965/Dateien_Aktionen")
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if url.path == "/api/check_update":
            import re
            import urllib.request
            from ai_engine import _get_ssl_context

            current_v = getattr(config, "APP_VERSION", "1.0.0")
            repo = getattr(config, "GITHUB_REPO", "pebe1965/Dateien_Aktionen")

            update_info = {
                "current_version": current_v,
                "latest_version": current_v,
                "update_available": False,
                "release_name": "",
                "release_notes": "",
                "download_url": "",
                "html_url": f"https://github.com/{repo}/releases"
            }

            try:
                api_url = f"https://api.github.com/repos/{repo}/releases/latest"
                req = urllib.request.Request(
                    api_url,
                    headers={"User-Agent": "Dateien-Aktionen-MacApp", "Accept": "application/vnd.github.v3+json"}
                )
                ctx = _get_ssl_context()
                with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                    if resp.status == 200:
                        rel = json.loads(resp.read().decode("utf-8"))
                        tag = rel.get("tag_name", "").lstrip("v")
                        update_info["latest_version"] = tag
                        update_info["release_name"] = rel.get("name", f"Version {tag}")
                        update_info["release_notes"] = rel.get("body", "")
                        update_info["html_url"] = rel.get("html_url", update_info["html_url"])

                        # Versionsvergleich (z. B. "1.1.0" > "1.0.0")
                        def vparts(v_str):
                            return [int(x) for x in re.findall(r'\d+', v_str)] or [0]

                        if vparts(tag) > vparts(current_v):
                            update_info["update_available"] = True

                        for asset in rel.get("assets", []):
                            name = asset.get("name", "").lower()
                            if name.endswith(".dmg") or name.endswith(".zip"):
                                update_info["download_url"] = asset.get("browser_download_url", "")
                                break
            except Exception:
                pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(update_info).encode("utf-8"))
            return

        if url.path == "/api/history":
            manifests = []
            for f in sorted(HISTORY_DIR.glob("manifest_*.json"), reverse=True):
                try:
                    with open(f, "r", encoding="utf-8") as m_file:
                        m_data = json.load(m_file)
                    manifests.append({
                        "filename": f.name,
                        "date": m_data.get("created_at", "unbekannt")[:19].replace("T", " "),
                        "total_actions": m_data.get("total_actions", 0)
                    })
                except Exception:
                    pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"manifests": manifests}).encode("utf-8"))
            return

        if url.path == "/api/file_preview":
            query = parse_qs(url.query)
            path_str = query.get("path", [""])[0]
            if not path_str:
                self.send_response(400)
                self.end_headers()
                return

            p = Path(path_str).resolve()
            if not p.exists() or not p.is_file():
                self.send_response(404)
                self.end_headers()
                return

            ext = p.suffix.lower()
            mime_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
                ".ico": "image/x-icon",
                ".pdf": "application/pdf",
                ".mp3": "audio/mpeg",
                ".m4a": "audio/mp4",
                ".wav": "audio/wav",
            }
            content_type = mime_map.get(ext, "application/octet-stream")

            try:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(p.stat().st_size))
                self.end_headers()
                with open(p, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
            except Exception:
                pass
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        url = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        params = json.loads(body) if body else {}

        if url.path == "/api/pick_folder":
            # Öffnet den nativen macOS Ordnerauswahl-Dialog
            chosen = ""
            try:
                cmd = ["osascript", "-e", 'POSIX path of (choose folder with prompt "Wähle einen Ordner zum Scannen:")']
                res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if res.returncode == 0:
                    chosen = res.stdout.strip().rstrip("/")
            except Exception:
                pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"path": chosen}).encode("utf-8"))
            return

        if url.path == "/api/catalog":
            folder_str = params.get("path", "")
            try:
                folder = Path(folder_str).expanduser().resolve()
                if not folder.exists() or not folder.is_dir():
                    self.send_error_response("Ordner existiert nicht oder ist kein Verzeichnis.")
                    return
                # Vorab-Prüfung auf Lesezugriff (triggert macOS TCC Prompt falls nötig)
                os.listdir(folder)
            except PermissionError:
                self.send_error_response(
                    "Zugriff verweigert (macOS Datenschutz): Bitte erlauben Sie 'Dateien_Aktionen' Zugriff auf diesen Ordner unter 'Systemeinstellungen > Datenschutz & Sicherheit > Dateien und Ordner' (oder Festplattenvollzugriff)."
                )
                return
            except Exception as e:
                self.send_error_response(f"Ungültiger Pfad: {e}")
                return

            try:
                cat = Catalog(folder)
                cat.scan(compute_hashes=True)
                summary = cat.summary()

                dups_export = {}
                for h, items in cat.duplicates.items():
                    dups_export[h] = [i.to_dict() for i in items]

                files_export = []
                for i in cat.items:
                    d = i.to_dict()
                    try:
                        d["relative_path"] = str(i.path.relative_to(folder))
                    except Exception:
                        d["relative_path"] = i.filename
                    files_export.append(d)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "summary": summary,
                    "duplicates": dups_export,
                    "files": files_export
                }).encode("utf-8"))
            except PermissionError:
                self.send_error_response(
                    "Zugriff verweigert (macOS Datenschutz): Bitte erlauben Sie 'Terminal' Zugriff auf 'Dokumente' unter 'Systemeinstellungen > Datenschutz & Sicherheit > Dateien und Ordner'."
                )
            except Exception as e:
                self.send_error_response(f"Fehler beim Scannen: {str(e)}")
            return

        if url.path == "/api/inspect_content":
            file_path = Path(params.get("path", "")).resolve()
            if not file_path.exists():
                self.send_error_response("Datei nicht gefunden.")
                return

            text, method = extract_content(file_path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "text": text,
                "method": method,
                "char_count": len(text)
            }).encode("utf-8"))
            return

        if url.path == "/api/preview":
            folder_str = params.get("path", "")
            specific_paths = params.get("paths", [])
            prefix = params.get("prefix", None)

            folder = Path(folder_str).resolve() if folder_str else BASE_DIR
            if specific_paths and not folder.exists():
                folder = Path(specific_paths[0]).parent

            if not folder.exists() or not folder.is_dir():
                self.send_error_response("Ordner existiert nicht.")
                return

            organizer = Organizer(source_dir=folder, provider=config.AI_PROVIDER)
            plan = organizer.prepare_plan(
                specific_paths=specific_paths if specific_paths else None,
                prefix=prefix if prefix else None
            )

            plan_data = [p.to_dict() for p in plan]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"plan": plan_data}).encode("utf-8"))
            return

        if url.path == "/api/batch_move":
            paths = params.get("paths", [])
            target_dir_str = params.get("target_dir", "").strip()
            new_folder_name = params.get("new_folder_name", "").strip()
            copy_mode = params.get("copy_mode", False)

            if not paths:
                self.send_error_response("Keine Dateien zum Verschieben übergeben.")
                return

            if not target_dir_str:
                self.send_error_response("Kein Zielordner angegeben.")
                return

            target_path = Path(target_dir_str).resolve()
            if new_folder_name:
                target_path = target_path / new_folder_name

            try:
                target_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.send_error_response(f"Konnte Zielordner nicht erstellen: {e}")
                return

            from organizer import get_unique_target_path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            manifest_file = HISTORY_DIR / f"manifest_move_{timestamp}.json"
            manifest_entries = []
            moved_items = []
            errors = []

            for p_str in paths:
                src = Path(p_str).resolve()
                if not src.exists() or not src.is_file():
                    continue

                dst = get_unique_target_path(target_path / src.name)
                try:
                    if copy_mode:
                        shutil.copy2(src, dst)
                    else:
                        shutil.move(src, dst)

                    manifest_entries.append({
                        "source": str(src),
                        "target": str(dst),
                        "copy_mode": copy_mode,
                        "timestamp": datetime.now().isoformat()
                    })
                    moved_items.append({
                        "original_path": str(src),
                        "new_path": str(dst),
                        "filename": dst.name
                    })
                except Exception as e:
                    errors.append(f"{src.name}: {str(e)}")

            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump({
                    "created_at": datetime.now().isoformat(),
                    "total_actions": len(manifest_entries),
                    "action_type": "copy" if copy_mode else "move",
                    "destination_folder": str(target_path),
                    "actions": manifest_entries
                }, f, indent=2, ensure_ascii=False)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "moved_count": len(moved_items),
                "target_dir": str(target_path),
                "manifest": manifest_file.name,
                "moved_items": moved_items,
                "errors": errors
            }).encode("utf-8"))
            return

        if url.path == "/api/execute":
            items = params.get("items", [])
            copy_mode = params.get("copy_mode", False)
            if not items:
                self.send_error_response("Keine Dateien zum Ausführen übergeben.")
                return

            import shutil
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            manifest_file = HISTORY_DIR / f"manifest_{timestamp}.json"
            manifest_entries = []

            for it in items:
                src = Path(it["source_path"])
                dst = Path(it["target_path"]).parent / it["new_name"]

                if not src.exists():
                    continue

                dst.parent.mkdir(parents=True, exist_ok=True)
                if copy_mode:
                    shutil.copy2(src, dst)
                else:
                    shutil.move(src, dst)

                manifest_entries.append({
                    "source": str(src),
                    "target": str(dst),
                    "copy_mode": copy_mode,
                    "timestamp": datetime.now().isoformat()
                })

            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump({
                    "created_at": datetime.now().isoformat(),
                    "total_actions": len(manifest_entries),
                    "actions": manifest_entries
                }, f, indent=2, ensure_ascii=False)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "manifest": manifest_file.name}).encode("utf-8"))
            return

        if url.path == "/api/undo":
            manifest_name = params.get("manifest", "")
            manifest_path = HISTORY_DIR / manifest_name
            try:
                restored = rollback_manifest(manifest_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "restored": restored}).encode("utf-8"))
            except Exception as e:
                self.send_error_response(str(e))
            return

        if url.path == "/api/test_zugang":
            from ai_engine import pruefe_zugangscode
            code = str(params.get("notionary_zugangscode", "")).strip() or config.NOTIONARY_ZUGANGSCODE
            if not code:
                result = {"verbunden": False, "fehler": "Kein Zugangscode eingetragen."}
            else:
                result = pruefe_zugangscode(code)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        if url.path == "/api/save_config":
            # Speichere in .env — im Benutzerordner, nicht im Programm (übersteht Updates)
            env_file = config.ENV_PATH
            env_file.parent.mkdir(parents=True, exist_ok=True)
            prov = params.get("ai_provider", "app")
            g_key = params.get("gemini_api_key", "").strip()
            # Fehlt das Feld (alte Oberfläche), bleibt der gespeicherte Code stehen.
            z_code = params.get("notionary_zugangscode")
            z_code = config.NOTIONARY_ZUGANGSCODE if z_code is None else str(z_code).strip()
            g_mod = params.get("gemini_model", "gemini-2.5-flash").strip()
            l_url = params.get("local_url", "http://localhost:1234/v1/chat/completions").strip()

            content = f"""AI_PROVIDER={prov}
NOTIONARY_ZUGANGSCODE={z_code}
GEMINI_API_KEY={g_key or config.GEMINI_API_KEY}
GEMINI_MODEL={g_mod or 'gemini-2.5-flash'}
LOCAL_API_URL={l_url or 'http://localhost:1234/v1/chat/completions'}
LOCAL_MODEL=local-model
"""
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(env_file, 0o600)  # enthält Zugangscode bzw. Schlüssel

            # Im laufenden Prozess aktualisieren
            config.AI_PROVIDER = prov
            config.NOTIONARY_ZUGANGSCODE = z_code
            if g_key:
                config.GEMINI_API_KEY = g_key
            config.GEMINI_MODEL = g_mod
            config.LOCAL_API_URL = l_url

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            # Ohne Antwort und return lief die Anfrage in den Papierkorb-Zweig
            # weiter und bekam dort eine zweite (Fehler-)Antwort angehängt.
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            return

        if url.path in ["/api/trash_duplicates", "/api/trash_files"]:
            paths = params.get("paths", [])
            if not paths:
                self.send_error_response("Keine Dateien zum Löschen übergeben.")
                return

            trashed = []
            failed = []
            freed_bytes = 0

            for p_str in paths:
                p = Path(p_str).resolve()
                if p.exists():
                    try:
                        if p.is_file():
                            size = p.stat().st_size
                        else:
                            size = sum(f.stat().st_size for f in p.glob("**/*") if f.is_file())
                    except Exception:
                        size = 0
                    if move_to_macos_trash(p):
                        trashed.append(str(p))
                        freed_bytes += size
                    else:
                        failed.append(str(p))

            # Protokoll speichern
            log_file = HISTORY_DIR / f"trash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "trashed_count": len(trashed),
                    "freed_bytes": freed_bytes,
                    "trashed_files": trashed,
                    "failed_files": failed
                }, f, indent=2, ensure_ascii=False)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "trashed_count": len(trashed),
                "freed_mb": round(freed_bytes / (1024 * 1024), 2),
                "failed_count": len(failed),
                "failed_files": failed,
                "log": log_file.name
            }).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def send_error_response(self, message: str):
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode("utf-8"))


def is_server_already_running(port: int) -> bool:
    """Prüft, ob auf dem Port bereits eine Instanz von Dateien_Aktionen läuft."""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/status",
            headers={"User-Agent": "Dateien-Aktionen-Ping"}
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return "ai_provider" in data or "app_version" in data
    except Exception:
        pass
    return False


def find_free_port(preferred_ports=(8765, 8766, 8767, 8768)) -> int:
    """Findet einen freien Port, bevorzugt aus der Liste oder vom Betriebssystem."""
    for port in preferred_ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    # Zufälligen freien Port vom System zuweisen lassen
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def start_gui():
    # 1. Wenn die App bereits läuft: Browser öffnen und bestehende Instanz nutzen
    if is_server_already_running(PORT):
        url = f"http://127.0.0.1:{PORT}"
        print(f"\n============================================================")
        print(f"  ℹ️  Dateien_Aktionen läuft bereits im Hintergrund auf: {url}")
        print(f"  Öffne bestehendes Fenster im Browser...")
        print(f"============================================================\n")
        webbrowser.open(url)
        return

    # 2. Freien Port ermitteln (bevorzugt 8765, sonst nächsten freien Port)
    port = find_free_port(preferred_ports=(PORT, 8766, 8767, 8768))
    url = f"http://127.0.0.1:{port}"

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    server.daemon_threads = True

    print(f"\n============================================================")
    print(f"  🚀 Dateien_Aktionen GUI gestartet auf: {url}")
    print(f"  Öffne Browser...")
    print(f"  Zum Beenden: Ctrl + C im Terminal drücken")
    print(f"============================================================\n")

    # Browser öffnen
    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server beendet.")
        server.server_close()


if __name__ == "__main__":
    start_gui()
