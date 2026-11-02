#!/usr/bin/env bash
#
# Avvio di bacheca_classeviva — pensato per l'esecuzione da cron.
#
# • Tutto l'output (stdout+stderr) viene scritto in logs/bacheca.log
#   → cron non invia mail spurie.
# • Gli argomenti vengono passati a src.main (es. --dry-run, --backfill-days 30).
# • Lock su data/.lock: evita esecuzioni sovrapposte.
#
# Esempio di crontab (tutti i giorni alle 7:30):
#   30 7 * * * /Users/massimo/VSCode/bacheca_classeviva/scripts/run_bacheca.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/bacheca.log"

mkdir -p "$LOG_DIR" "$PROJECT_ROOT/data"

# Rotazione semplice: oltre 5 MB il log corrente diventa .1
if [ -f "$LOG_FILE" ]; then
  size="$(wc -c < "$LOG_FILE" | tr -d '[:space:]')"
  if [ "$size" -gt 5242880 ]; then
    mv -f "$LOG_FILE" "$LOG_FILE.1"
  fi
fi

# Lock portabile (mkdir è atomico; non richiede flock, assente su macOS)
LOCK_DIR="$PROJECT_ROOT/data/.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "$(date '+%F %T')  ⚠️  Un'altra esecuzione è già in corso: esco." >> "$LOG_FILE"
  exit 0
fi
cleanup() { rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

cd "$PROJECT_ROOT"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

set +e
{
  echo "════════════════════════════════════════════════"
  echo "$(date '+%F %T')  Avvio bacheca_classeviva (args: $*)"
  "$PYTHON_BIN" -m src.main "$@"
  status=$?
  echo "$(date '+%F %T')  Fine (exit=$status)"
} >> "$LOG_FILE" 2>&1
set -e

# In console (uso manuale) indica dove si trova il log; in cron (no TTY) silenzio totale
if [ -t 1 ]; then
  echo "Log: $LOG_FILE (exit=$status)"
fi

exit "$status"