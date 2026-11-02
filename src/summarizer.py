"""Sintesi dei contenuti tramite LLM (endpoint compatibile OpenAI chat/completions).

Se non è configurata alcuna API key, viene prodotta una sintesi "grezza"
(troncatura del testo) così il pipeline resta comunque funzionante.
"""
from __future__ import annotations

import logging

import requests

from .config import Config

log = logging.getLogger(__name__)

MAX_INPUT_CHARS = 24000
FALLBACK_EXCERPT = 2000
# Budget di generazione: include anche i token di 'reasoning' dei modelli
# che ragionano (che altrimenti esauriscono max_tokens lasciando content=None)
MAX_OUTPUT_TOKENS = 4000

SYSTEM_PROMPT = (
    "Sei un assistente che sintetizza comunicazioni scolastiche per genitori e studenti. "
    "Rispondi in italiano con un messaggio breve e chiaro, formato così:\n"
    "• 3-5 punti chiave (bullet)\n"
    "• 'Scadenze': elenco date/termini importanti, oppure 'nessuna'\n"
    "• 'Azioni richieste': cosa deve fare il destinatario, oppure 'nessuna'\n"
    "Se forniti, usa la data della comunicazione come riferimento temporale e la categoria come contesto.\n"
    "Non inventare informazioni non presenti nel testo."
)


class SummarizerError(RuntimeError):
    pass


def summarize_notice(
    title: str,
    notice_text: str,
    attachment_texts: list[tuple[str, str]],
    cfg: Config,
    notice_date: str = "",
    category: str = "",
) -> str:
    """Restituisce la sintesi dell'avviso.

    attachment_texts: lista di (nome_file, testo_estratto).
    notice_date / category: data e categoria della comunicazione, usate
    come contesto per la sintesi (opzionali).
    """
    # Composizione del documento da sintetizzare
    # Intestazione: data, poi titolo, poi categoria (uno per riga)
    lines = []
    if notice_date:
        lines.append(f"Data della comunicazione: {notice_date}")
    lines.append(f"Titolo: {title}")
    if category:
        lines.append(f"Categoria: {category}")
    parts = ["\n".join(lines)]
    if notice_text.strip():
        parts.append(f"Testo della comunicazione:\n{notice_text.strip()}")
    for name, text in attachment_texts:
        if text.strip():
            parts.append(f"Allegato '{name}':\n{text.strip()}")
        else:
            parts.append(f"Allegato '{name}': (nessun testo estraibile)")
    document = "\n\n".join(parts)[:MAX_INPUT_CHARS]

    if not (cfg.llm_api_url and cfg.llm_api_key and cfg.llm_model):
        log.warning("⚠️  LLM non configurato: uso sintesi grezza (troncatura del testo)")
        return _fallback_summary(document)

    log.info("🤖 Sintesi LLM con modello '%s' (%d caratteri di input)…", cfg.llm_model, len(document))
    payload = {
        "model": cfg.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": document},
        ],
        "temperature": 0.2,
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    log.debug("POST %s  payload=%s", cfg.llm_api_url, str(payload)[:500])
    try:
        resp = requests.post(
            cfg.llm_api_url,
            headers={
                "Authorization": f"Bearer {cfg.llm_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        log.debug("← HTTP %s  body=%s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()
        summary = _extract_summary(data)
        log.info("✨ Sintesi ottenuta (%d caratteri)", len(summary))
        return summary
    except requests.RequestException as exc:
        log.error("❌ Chiamata LLM fallita: %s — uso sintesi grezza", exc)
        return _fallback_summary(document)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        log.error("❌ Risposta LLM inattesa: %s — uso sintesi grezza", exc)
        return _fallback_summary(document)


def _extract_summary(data: dict) -> str:
    """Estrae il testo della risposta LLM (formato OpenAI chat/completions).

    I modelli 'reasoning' possono restituire content=None o vuoto quando i
    token di ragionamento esauriscono max_tokens: in tal caso viene sollevato
    ValueError e si ricade sulla sintesi grezza, invece di far fallire tutto.
    """
    try:
        choice = data["choices"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"struttura risposta inattesa: {str(data)[:200]}") from exc
    message = choice.get("message") or {}
    raw = message.get("content")
    content = raw.strip() if isinstance(raw, str) else ""
    if content:
        return content
    finish = choice.get("finish_reason", "?")
    if message.get("reasoning") or message.get("reasoning_details"):
        raise ValueError(
            f"contenuto vuoto: il modello ha prodotto solo 'reasoning' "
            f"(finish_reason={finish!r}, max_tokens={MAX_OUTPUT_TOKENS} esaurito?)"
        )
    raise ValueError(f"contenuto vuoto dal modello (finish_reason={finish!r})")


def _fallback_summary(document: str) -> str:
    excerpt = document[:FALLBACK_EXCERPT]
    suffix = "\n… (testo troncato)" if len(document) > FALLBACK_EXCERPT else ""
    return f"(Sintesi automatica non disponibile — estratto del contenuto)\n\n{excerpt}{suffix}"