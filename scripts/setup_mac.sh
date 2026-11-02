#!/usr/bin/env bash
# Setup dipendenze per macOS.
# Uso: ./scripts/setup_mac.sh
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
echo "▶ Setup bacheca_classeviva su macOS  (dir: $PROJECT_DIR)"

# 1) Python 3
if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ python3 non trovato. Installa Xcode Command Line Tools con: xcode-select --install"
  exit 1
fi
echo "✓ python3: $(python3 --version)"

# 2) Ambiente virtuale
if [ ! -d ".venv" ]; then
  echo "▶ Creo l'ambiente virtuale .venv…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "✓ venv attivo: $(which python)"

# 3) Dipendenze
echo "▶ Installo le dipendenze da requirements.txt…"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt
echo "✓ Dipendenze installate"

# 4) File .env
if [ ! -f ".env" ]; then
  echo "▶ Nessun .env trovato: lancio lo script di configurazione guidata…"
  python3 scripts/setup_env.py
else
  echo "✓ .env già presente, lo lascio invariato"
fi

echo ""
echo "✅ Setup completato!"
echo "   Prova con:  source .venv/bin/activate && python3 -m src.main --dry-run"