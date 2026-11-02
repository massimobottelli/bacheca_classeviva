"""Invio di messaggi e documenti tramite Telegram Bot API."""
from __future__ import annotations

import logging
from pathlib import Path

import requests

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    pass


def _call(token: str, method: str, **params) -> dict:
    url = API.format(token=token, method=method)
    log.debug("POST %s  params=%s", url, {k: v for k, v in params.items() if k != "document"})
    if "document" in params:
        resp = requests.post(url, data={k: v for k, v in params.items() if k != "document"},
                             files={"document": params["document"]}, timeout=120)
    else:
        resp = requests.post(url, data=params, timeout=60)
    log.debug("← HTTP %s  body=%s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    body = resp.json()
    if not body.get("ok"):
        raise TelegramError(f"Telegram API KO: {body.get('description', body)}")
    return body


def send_message(token: str, chat_id: str, text: str) -> dict:
    """Invia un messaggio (Markdown). Il testo viene spezzato se supera i 4096 caratteri."""
    log.info("💬 Invio messaggio Telegram a chat_id=%s (%d caratteri)", chat_id, len(text))
    result: dict = {}
    # Telegram limita i messaggi a 4096 caratteri: spezziamo in blocchi sicuri
    chunk_size = 4000
    for start in range(0, len(text), chunk_size):
        chunk = text[start:start + chunk_size]
        result = _call(
            token, "sendMessage",
            chat_id=chat_id,
            text=chunk,
            parse_mode="Markdown",
            disable_web_page_preview="true",
        )
    return result


def send_document(token: str, chat_id: str, path: Path, caption: str = "") -> dict:
    """Invia un file (es. PDF) come documento."""
    log.info("📎 Invio documento Telegram: %s", path.name)
    with open(path, "rb") as fh:
        return _call(
            token, "sendDocument",
            chat_id=chat_id,
            document=fh,
            caption=caption[:1024] if caption else "",
        )