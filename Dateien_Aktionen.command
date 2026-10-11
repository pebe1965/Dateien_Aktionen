#!/usr/bin/env bash
# Doppelklickbarer Launcher für macOS
cd "$(dirname "$0")"

# Finde funktionierendes Python 3
PY_CMD=""
for p in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 $(which python3 2>/dev/null); do
    if [ -x "$p" ]; then
        PY_CMD="$p"
        break
    fi
done

if [ -z "$PY_CMD" ]; then
    osascript -e 'display dialog "Python 3 wurde auf diesem Mac nicht gefunden. Bitte installieren Sie Python 3." buttons {"OK"} default button "OK" with icon stop'
    exit 1
fi

exec "$PY_CMD" gui.py
