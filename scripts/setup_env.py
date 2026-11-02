#!/usr/bin/env python3
"""Configurazione guidata del file .env.

Fa le domande una alla volta e scrive .env nella root del progetto.
La password non viene mostrata a schermo (getpass).
Uso:  python3 scripts/setup_env.py
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


def ask(label: str, default: str = "", required: bool = False, secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        # getpass nasconde l'input solo con un terminale reale (TTY);
        # con stdin piped/redirectato funziona male, quindi usiamo input().
        if secret and sys.stdin.isatty():
            value = getpass.getpass(f"{label}{suffix}: ").strip()
        else:
            value = input(f"{label}{suffix}: ").strip()
        if not value:
            value = default
        if required and not value:
            print("  ⚠  Questo campo è obbligatorio.")
            continue
        return value


def main() -> int:
    print("=" * 60)
    print("  bacheca_classeviva — configurazione iniziale di .env")
    print("=" * 60)
    print("Premi INVIO per accettare il valore tra parentesi [default].\n")

    if ENV_PATH.exists():
        answer = input(f"Il file {ENV_PATH} esiste già. Sovrascrivo? [s/N]: ").strip().lower()
        if answer not in ("s", "si", "sì", "y", "yes"):
            print("Nessuna modifica apportata.")
            return 0

    print("\n── ClasseViva ──────────────────────────────")
    cv_uid = ask("Nome utente ClasseViva (CV_UID)", required=True)
    cv_password = ask("Password (CV_PASSWORD)", required=True, secret=True)
    cv_cid = ask("Codice scuola (CV_CID, INVIO se non richiesto)")
    cv_pin = ask("PIN (CV_PIN, INVIO se non impostato)")
    mark_as_read = ask(
        "Segnare gli avvisi come letti sul registro? (MARK_AS_READ) [false]"
    ).lower() or "false"
    while mark_as_read not in ("true", "false", "1", "0", "yes", "si", "sì", "no", "on", "off"):
        print("  ⚠  Valori ammessi: true / false")
        mark_as_read = ask("MARK_AS_READ [false]").lower() or "false"

    print("\n── Telegram ────────────────────────────────")
    print("Crea un bot con @BotFather su Telegram e incolla qui il token.")
    tg_token = ask("Token del bot (TG_BOT_TOKEN)", required=True)
    print("Avvia una chat con il tuo bot (comando /start), poi scopri la chat_id con:")
    print(f"  https://api.telegram.org/bot{tg_token}/getUpdates")
    tg_chat = ask("Chat ID (TG_CHAT_ID)", required=True)
    send_attachments = ask(
        "Inviare i PDF come documenti su Telegram? (SEND_ATTACHMENTS) [true]"
    ).lower() or "true"
    while send_attachments not in ("true", "false", "1", "0", "yes", "si", "sì", "no", "on", "off"):
        print("  ⚠  Valori ammessi: true / false")
        send_attachments = ask("SEND_ATTACHMENTS [true]").lower() or "true"

    print("\n── Sintesi LLM (opzionale, INVIO per saltare) ──")
    print("Endpoint compatibile OpenAI chat/completions.")
    print("  OpenAI:  https://api.openai.com/v1/chat/completions")
    print("  Claude:  https://api.anthropic.com/v1/chat/completions")
    print("  Gemini:  https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    print("  Ollama:  http://localhost:11434/v1/chat/completions")
    llm_url = ask("LLM_API_URL")
    llm_key = ask("LLM_API_KEY", secret=True) if llm_url else ""
    llm_model = ask("LLM_MODEL (es. gpt-4o-mini, claude-sonnet-4-5)") if llm_url else ""

    print("\n── Comportamento ───────────────────────────")
    backfill = ask("Giorni di storico alla prima esecuzione (BACKFILL_DAYS) [7]") or "7"
    delay = ask("Pausa tra richieste in secondi (REQUEST_DELAY) [1]") or "1"

    content = f"""# Generato da scripts/setup_env.py — NON committare
# ── ClasseViva ──
CV_UID={cv_uid}
CV_PASSWORD={cv_password}
CV_CID={cv_cid}
CV_PIN={cv_pin}
MARK_AS_READ={mark_as_read}

# ── Telegram ──
TG_BOT_TOKEN={tg_token}
TG_CHAT_ID={tg_chat}
SEND_ATTACHMENTS={send_attachments}

# ── Sintesi LLM (opzionale) ──
LLM_API_URL={llm_url}
LLM_API_KEY={llm_key}
LLM_MODEL={llm_model}

# ── Comportamento ──
BACKFILL_DAYS={backfill}
REQUEST_DELAY={delay}
"""
    ENV_PATH.write_text(content, encoding="utf-8")
    print(f"\n✅ File scritto: {ENV_PATH}")
    print("   (verifica che .env sia elencato nel .gitignore)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAnnullato.")
        sys.exit(130)